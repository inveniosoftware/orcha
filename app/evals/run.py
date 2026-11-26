# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Langfuse experiments runner using the SDK Experiments API."""

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress

from app.activities.extract_metadata import extract_metadata_record
from app.config import get_settings
from app.extractors import get_extractor

from .dataset import (
    filter_categories,
    get_or_create_langfuse_dataset,
    load_local_dataset,
    sample_items,
)
from .evaluators import (
    average_score_evaluator,
    build_comparison_payload,
    classification_run_evaluator,
    item_summary_evaluator,
    metrics_from_counts,
    pool_counts,
)
from .prompts import sync_extraction_prompt

logger = logging.getLogger(__name__)

DATASET_NAME = "orcha-eval-dataset"
MAX_CONCURRENT_REQUESTS = 4
# Seconds one item may take, including LLM retries, before it counts as failed.
ITEM_TIMEOUT = 120.0
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def _with_retry(call, *, retries: int = 3, base_delay: float = 1.0):
    """Retry LLM calls that fail with transient HTTP errors."""
    for attempt in range(retries):
        try:
            return await call()
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if attempt == retries - 1 or status_code not in RETRYABLE_HTTP_STATUS_CODES:
                raise
            await asyncio.sleep(base_delay * (2**attempt))


def save_extracted_text(text: str, record_id: str, dataset_root: Path) -> None:
    """Save extracted text to a file in the extracted_text directory for inspection."""
    extracted_dir = dataset_root / "extracted_text"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    output_path = extracted_dir / f"{record_id}.txt"
    output_path.write_text(text, encoding="utf-8")


def save_local_results(
    results: list[dict],
    results_dir: Path,
    extractor: str,
    model: str,
    run_info: dict[str, Any] | None = None,
) -> Path:
    """Write a run's per-item results, average score and metrics to disk as JSON."""
    scores = [item["comparison"]["average_score"] for item in results]
    pooled = pool_counts(item["comparison"]["classification"] for item in results)
    payload = {
        "extractor": extractor,
        "model": model,
        "item_count": len(results),
        "average_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "metrics": {name: metrics_from_counts(c) for name, c in pooled.items()},
        "items": results,
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{extractor}__{model.replace('/', '_')}__{timestamp}.json"
    output_path = results_dir / filename
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


async def extraction_task(
    dataset_item,
    dataset_root: Path,
    extractor_name: str = "pdfplumber",
):
    """Extract text, run the agent, and build evaluator comparison data."""
    input_data = dataset_item.get("input")
    pdf_path = dataset_root / input_data["pdf_path"]
    expected = dataset_item.get("expected_output")
    record_id = input_data.get("record_id") or pdf_path.stem

    extractor = get_extractor(extractor_name)
    pdf_bytes = pdf_path.read_bytes()
    text = extractor.extract(pdf_bytes, pages=[1, 2])["full_text"]
    save_extracted_text(text, record_id, dataset_root)

    # Reuse the app's metadata helper without going through Temporal.
    metadata = await _with_retry(lambda: extract_metadata_record(text))
    output_dict = metadata.model_dump(mode="json")
    output_dict["comparison"] = build_comparison_payload(output_dict, expected)

    return {
        "pdf_filename": pdf_path.name,
        "comparison": output_dict["comparison"],
    }


def _resolve_dataset_root(cache: Path | None, target: Path | None) -> Path:
    cache = cache or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    root = (target or cache / "orcha-eval-dataset") / "dataset"
    if not (root / ".dataset-state.json").exists() or not (root / "metadata").exists():
        raise FileNotFoundError(
            "Dataset is not downloaded. Run `orcha evals sync_dataset` first."
        )
    return root


async def _run_local(items, extract) -> list[dict]:
    outcomes = await asyncio.gather(
        *(extract(item) for item in items),
        return_exceptions=True,
    )
    # Failures were already reported as each item finished.
    return [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]


def format_scores(results: list[dict]) -> str:
    """Summarize local results in the same format as Langfuse experiments."""
    values: dict[str, list[float]] = {}
    for result in results:
        for evaluation in item_summary_evaluator(output=result):
            values.setdefault(str(evaluation.name), []).append(float(evaluation.value))
    lines = ["Average Scores:"]
    lines += [f"  • {name}: {sum(v) / len(v):.3f}" for name, v in values.items()]
    summaries = values.get("item_summary", [])
    run_average = round(sum(summaries) / len(summaries), 2) if summaries else 0.0
    lines += ["", "Run Evaluations:", f"  • run_average_score: {run_average:.3f}"]
    return "\n".join(lines)


def _connect_langfuse(items, prompt_name, ignore_errors=False):
    """Sync the prompt and dataset to Langfuse.

    Returns the client, prompt reference, and Langfuse dataset items, or None
    when Langfuse is unavailable and ``ignore_errors`` is set.
    """
    try:
        from langfuse import get_client

        client = get_client()
        prompt_ref = sync_extraction_prompt(client, prompt_name)
        data = get_or_create_langfuse_dataset(client, DATASET_NAME, items)
    except Exception as exc:
        if not ignore_errors:
            raise
        # Error bodies can be whole HTML pages; log only the status or first line.
        status = getattr(exc, "status_code", None)
        detail = f"HTTP {status}" if status else str(exc).splitlines()[0][:200]
        logger.warning("Langfuse is unavailable (%s); running without it", detail)
        return None
    return client, prompt_ref, data


def _run_langfuse(client, prompt_ref, data, extract, extractor, settings) -> list[dict]:
    """Run the experiment in Langfuse and return its results."""
    results: list[dict] = []

    async def task(*, item, **_):
        outcome = await extract(
            {"input": item.input, "expected_output": item.expected_output}
        )
        results.append(outcome)
        return outcome

    experiment = client.run_experiment(
        name=f"{extractor}__{settings.llm}",
        description="Extract and evaluate document metadata",
        data=data,
        metadata={
            "dataset_name": DATASET_NAME,
            "model": settings.llm,
            "extractor": extractor,
            "prompt_name": prompt_ref["name"],
            "prompt_version": str(prompt_ref.get("version")),
            "pages": "1,2",
        },
        task=task,
        evaluators=[item_summary_evaluator],
        run_evaluators=[average_score_evaluator, classification_run_evaluator],
    )
    print(experiment.format())
    return results


async def run(
    extractor: str = "pdfplumber",
    prompt_name: str = "prompt",
    use_langfuse: bool = False,
    ignore_langfuse_errors: bool = False,
    save_json: bool = False,
    samples: int | None = None,
    categories: list[str] | None = None,
    seed: int = 42,
    item_timeout: float = ITEM_TIMEOUT,
    results_dir: Path | None = None,
    cache: Path | None = None,
    target: Path | None = None,
):
    """Run extraction and evaluation experiment."""
    dataset_root = _resolve_dataset_root(cache, target)
    items = filter_categories(
        load_local_dataset(dataset_root, DATASET_NAME), categories
    )
    items = sample_items(items, samples, seed)
    settings = get_settings()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    completed = 0

    def report(record_id: str, started: float, outcome: str, error=None) -> None:
        """Print one line per finished item, so CI logs show progress too."""
        nonlocal completed
        completed += 1
        progress.advance(progress_task)
        line = f"[{completed}/{len(items)}] {record_id} {outcome}"
        line += f" in {time.perf_counter() - started:.1f}s"
        progress.console.print(line + (f": {error}" if error else ""), markup=False)

    async def extract(item: dict):
        record_id = item["input"].get("record_id", "").strip("_")
        async with semaphore:
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    extraction_task(
                        dataset_item=item,
                        dataset_root=dataset_root,
                        extractor_name=extractor,
                    ),
                    timeout=item_timeout,
                )
            except TimeoutError:
                error = TimeoutError(f"timed out after {item_timeout:g}s")
                report(record_id, started, "failed", error)
                raise error from None
            except Exception as error:
                report(record_id, started, "failed", error)
                raise
            result["duration_seconds"] = round(time.perf_counter() - started, 2)
            report(record_id, started, f"{result['comparison']['average_score']:.3f}")
            return result

    started = time.perf_counter()
    langfuse = (
        _connect_langfuse(items, prompt_name, ignore_langfuse_errors)
        if use_langfuse
        else None
    )
    run_info: dict[str, Any] = {
        "langfuse": "unavailable" if use_langfuse else "disabled",
        "prompt_version": None,
    }
    # Progress goes to stderr, so it stays out of the results CI tees from stdout.
    with Progress(console=Console(stderr=True)) as progress:
        progress_task = progress.add_task("Running evaluations", total=len(items))
        if langfuse:
            client, prompt_ref, data = langfuse
            results = _run_langfuse(
                client, prompt_ref, data, extract, extractor, settings
            )
            run_info = {"langfuse": "ok", "prompt_version": prompt_ref.get("version")}
        else:
            results = await _run_local(items, extract)
    if not langfuse and results:
        print(format_scores(results))

    if save_json:
        state = json.loads((dataset_root / ".dataset-state.json").read_text())
        path = save_local_results(
            results,
            results_dir or PROJECT_ROOT / "app/evals/eval_results",
            extractor,
            settings.llm,
            run_info={
                "prompt_name": prompt_name,
                **run_info,
                "dataset_commit": state.get("dataset_git_commit"),
                "total_items": len(items),
                "duration_seconds": round(time.perf_counter() - started, 2),
            },
        )
        print(f"Wrote {len(results)} results to {path}")

    print(f"{extractor} / {settings.llm}")
    scores = []
    for result in results:
        score = result["comparison"]["average_score"]
        scores.append(score)
        name = result["pdf_filename"].split("__")[0]
        print(f"  {name}: {score:.4f}")
    average = sum(scores) / len(scores) if scores else 0.0
    print(f"Average: {average:.4f} ({len(results)}/{len(items)} items)")

    return results
