# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Write a README.md that compares every model evaluated in one CI run.

Usage: python app/evals/summarize_run.py RESULTS_DIR RUN_ID [--missing MODEL ...]

Reads RESULTS_DIR/RUN_ID/<model>/*.json, as written by ``orcha evals run
--save-json``, and compares each model with its latest earlier run in
RESULTS_DIR. Uses only the standard library, so CI can run it without
installing the project.
"""

import argparse
import json
import os
import statistics
from pathlib import Path
from typing import TypedDict

# Mirrors the fields build_comparison_payload leaves out of the average score.
DIAGNOSTIC_FIELDS = {"creators_orcid", "creators_affiliation"}


def load_model_results(run_dir: Path) -> dict[str, dict]:
    """Return each model folder's newest results JSON, keyed by folder name."""
    results = {}
    for model_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        files = sorted(model_dir.glob("*.json"))
        if files:
            results[model_dir.name] = json.loads(files[-1].read_text())
    return results


def previous_results(results_dir: Path, run_id: str, model: str) -> dict | None:
    """Return the model's results from the latest run before ``run_id``."""
    earlier = sorted(
        path
        for path in results_dir.iterdir()
        if path.is_dir() and path.name < run_id and any((path / model).glob("*.json"))
    )
    return load_model_results(earlier[-1]).get(model) if earlier else None


def scores_by_item(payload: dict) -> dict[str, dict]:
    """Map each item's PDF filename to its comparison payload."""
    return {item["pdf_filename"]: item["comparison"] for item in payload["items"]}


def mean(values) -> float | None:
    """Return the mean, or None when there are no values."""
    values = list(values)
    return sum(values) / len(values) if values else None


def fmt_score(value: float | None) -> str:
    """Format a score, or a dash when it is missing."""
    return "—" if value is None else f"{value:.3f}"


def fmt_duration(seconds: float | None) -> str:
    """Format seconds as minutes and seconds."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m {seconds:02d}s"


def fmt_change(change: float | None) -> str:
    """Format a score change with the indicator compare_results.py uses."""
    if change is None:
        return "—"
    # Pick the indicator from the shown value, so +0.000 is unchanged.
    change = round(change, 3) + 0.0  # + 0.0 turns -0.0 into 0.0
    indicator = "🟩" if change > 0 else "🔴" if change < 0 else "⬜"
    return f"{indicator} {change:+.3f}"


class Row(TypedDict):
    """One model's row in the run's leaderboard tables."""

    model: str
    run_score: float
    shared_score: float | None
    change: float | None
    own: float
    items: str
    errors: str
    duration: str
    median: str


def summarize(results_dir: Path, run_id: str, missing: list[str]) -> str:
    """Build the README for one run."""
    results = load_model_results(results_dir / run_id)
    items = {model: scores_by_item(payload) for model, payload in results.items()}
    common = set.intersection(*(set(scored) for scored in items.values()))
    first = next(iter(results.values()))

    # Header: what was compared.
    pipeline_url = os.environ.get("CI_PIPELINE_URL")
    pipeline_id = os.environ.get("CI_PIPELINE_ID")
    commit = os.environ.get("CI_COMMIT_SHORT_SHA")
    dataset_commit = first.get("dataset_commit")
    prompt = first.get("prompt_name")
    if prompt and first.get("prompt_version") is not None:
        prompt += f" v{first['prompt_version']}"
    facts = [
        f"Pipeline [#{pipeline_id}]({pipeline_url})" if pipeline_url else None,
        f"orcha `{commit}`" if commit else None,
        f"dataset `{dataset_commit[:7]}`" if dataset_commit else None,
        f"extractor `{first['extractor']}` (pages 1–2)",
        f"prompt `{prompt}`" if prompt else None,
    ]
    lines = [f"# Eval run {run_id}", "", " · ".join(fact for fact in facts if fact)]
    fallback = [m for m, p in results.items() if p.get("langfuse") == "unavailable"]
    if fallback:
        lines += [
            "",
            "⚠️ Langfuse was unavailable for "
            + ", ".join(fallback)
            + "; those results come from the local fallback.",
        ]

    rows: list[Row] = []
    for model, payload in results.items():
        scored = items[model]
        previous = previous_results(results_dir, run_id, model)
        change = None
        if previous:
            before = scores_by_item(previous)
            shared = scored.keys() & before.keys()
            change = mean(
                scored[name]["average_score"] - before[name]["average_score"]
                for name in shared
            )
        total = payload.get("total_items")
        durations = [
            item["duration_seconds"]
            for item in payload["items"]
            if "duration_seconds" in item
        ]
        own = payload["average_score"]
        rows.append(
            {
                "model": model,
                # Failed items count as 0; older results without a total use own.
                "run_score": own * len(scored) / total if total else own,
                "shared_score": mean(scored[name]["average_score"] for name in common),
                "change": change,
                "own": own,
                "items": f"{len(scored)}/{total}" if total else str(len(scored)),
                "errors": str(total - len(scored)) if total else "—",
                "duration": fmt_duration(payload.get("duration_seconds")),
                "median": fmt_duration(statistics.median(durations))
                if durations
                else "—",
            }
        )
    # Whole run: every dataset item, so completing more items counts.
    rows.sort(key=lambda row: row["run_score"], reverse=True)
    lines += [
        "",
        "## Leaderboard: whole run",
        "",
        "Scored on every dataset item; failed items count as 0. "
        "Own average leaves failed items out.",
        "",
        "| # | Model | Score | Δ prev run | Own average | Items | Errors "
        "| Duration | Median / item |",
        "|--:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(rows, 1):
        score = fmt_score(row["run_score"])
        lines.append(
            f"| {rank} | {row['model']} | {f'**{score}**' if rank == 1 else score} "
            f"| {fmt_change(row['change'])} | {row['own']:.3f} | {row['items']} "
            f"| {row['errors']} | {row['duration']} | {row['median']} |"
        )

    # Shared items: like-for-like, on the items every model completed.
    rows.sort(key=lambda row: row["shared_score"] or 0, reverse=True)
    lines += [
        "",
        "## Leaderboard: shared items",
        "",
        f"Scored on the {len(common)} items that all {len(results)} models completed.",
        "",
        "| # | Model | Score |",
        "|--:|---|---:|",
    ]
    for rank, row in enumerate(rows, 1):
        score = fmt_score(row["shared_score"])
        if rank == 1 and row["shared_score"] is not None:
            score = f"**{score}**"
        lines.append(f"| {rank} | {row['model']} | {score} |")

    # Per-field scores on the same shared items, best per field in bold.
    models = [row["model"] for row in rows]
    fields = list(
        dict.fromkeys(
            field
            for scored in items.values()
            for comparison in scored.values()
            for field in comparison["fields"]
            if field not in DIAGNOSTIC_FIELDS
        )
    )
    lines += [
        "",
        "## Scores per field",
        "",
        f"Best per field in bold; same {len(common)} items.",
        "",
        "| Field | " + " | ".join(models) + " |",
        "|---|" + "---:|" * len(models),
    ]
    for field in fields:
        values = {
            model: mean(
                items[model][name]["fields"][field]["score"]
                for name in common
                if field in items[model][name]["fields"]
            )
            for model in models
        }
        best = max((v for v in values.values() if v is not None), default=None)
        cells = [
            f"**{fmt_score(v)}**" if v is not None and v == best else fmt_score(v)
            for v in values.values()
        ]
        lines.append(f"| {field} | " + " | ".join(cells) + " |")

    # Pooled F1 per field, from the metrics saved in each results JSON.
    lines += [
        "",
        "## F1 per field",
        "",
        "Pass/fail F1, pooled over each model's completed items. "
        "Best per field in bold.",
        "",
        "| Field | " + " | ".join(models) + " |",
        "|---|" + "---:|" * len(models),
    ]
    for field in results[models[0]]["metrics"]:
        f1 = {model: results[model]["metrics"][field]["f1"] for model in models}
        best = max(f1.values())
        cells = [f"**{v:.3f}**" if v == best else f"{v:.3f}" for v in f1.values()]
        lines.append(f"| {field} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "Models with no results this run: "
        + (", ".join(missing) if missing else "none")
        + ".",
        "",
        "## Per-model reports",
        "",
        *(f"- [{model}]({model}/report.md)" for model in models),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Write a README.md comparing the models of one CI run."
    )
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("--missing", action="append", default=[])
    args = parser.parse_args()
    readme = summarize(args.results_dir, args.run_id, args.missing)
    (args.results_dir / args.run_id / "README.md").write_text(readme)
