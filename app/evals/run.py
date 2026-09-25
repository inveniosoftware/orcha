# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Langfuse experiments runner using the SDK Experiments API."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.activities.extract_metadata import extract_metadata_record
from app.config import get_settings
from app.extractors import get_extractor

from .dataset import (
    get_or_create_langfuse_dataset,
    load_local_dataset,
    sample_items,
)
from .evaluators import (
    average_score_evaluator,
    build_comparison_payload,
    item_summary_evaluator,
)
from .prompts import sync_extraction_prompt

logger = logging.getLogger(__name__)

DATASET_NAME = "orcha-eval-dataset"
MAX_CONCURRENT_REQUESTS = 4
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
) -> Path:
    """Write a local run's per-item results and average score to disk as JSON."""
    scores = [item["comparison"]["average_score"] for item in results]
    payload = {
        "extractor": extractor,
        "model": model,
        "item_count": len(results),
        "average_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
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
    pdf_path = Path(input_data.get("pdf_path"))
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


async def run(
    extractor: str = "pdfplumber",
    prompt_name: str = "prompt",
    use_langfuse: bool = False,
    samples: int | None = None,
    results_dir: Path | None = None,
    cache: Path | None = None,
    target: Path | None = None,
):
    """Run extraction and evaluation experiment."""
    cache = cache or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    dataset_root = (target or cache / "orcha-eval-dataset") / "dataset"

    state_path = dataset_root / ".dataset-state.json"
    metadata_dir = dataset_root / "metadata"
    if not state_path.exists() or not metadata_dir.exists():
        raise FileNotFoundError(
            "Dataset is not downloaded. Run `orcha evals sync_dataset` first."
        )
    items = sample_items(load_local_dataset(dataset_root, DATASET_NAME), samples)

    client = None
    if use_langfuse:
        from langfuse import get_client

        client = get_client()

    settings = get_settings()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def task(*, item, **kwargs):
        async with semaphore:
            dataset_item = (
                item
                if client is None
                else {
                    "input": item.input,
                    "expected_output": item.expected_output,
                }
            )
            return await extraction_task(
                dataset_item=dataset_item,
                dataset_root=dataset_root,
                extractor_name=extractor,
            )

    effective_run_name = f"{extractor}__{settings.llm}"

    if client is None:
        outcomes = await asyncio.gather(
            *(task(item=item) for item in items),
            return_exceptions=True,
        )
        results: list[dict[str, Any]] = []
        for item, outcome in zip(items, outcomes):
            if isinstance(outcome, BaseException):
                record_id = item["input"].get("record_id").strip("_")
                logger.error(
                    "Evaluation failed for %s: %s",
                    record_id,
                    outcome,
                )
            else:
                results.append(outcome)

        output_path = save_local_results(
            results,
            results_dir or PROJECT_ROOT / "app/evals/eval_results",
            extractor,
            settings.llm,
        )
        print(f"Wrote {len(results)} results to {output_path}")
        return results

    prompt_ref = sync_extraction_prompt(client, prompt_name)
    dataset_items = get_or_create_langfuse_dataset(client, DATASET_NAME, items)

    result = client.run_experiment(
        name=effective_run_name,
        description="Extract and evaluate document metadata",
        data=dataset_items,
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
        run_evaluators=[average_score_evaluator],
    )

    print(result.format())
    return result
