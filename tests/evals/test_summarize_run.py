import json

from app.evals.summarize_run import summarize


def _write(results_dir, run_id, model, scores, **run_info):
    items = [
        {
            "pdf_filename": f"{name}__doc.pdf",
            "duration_seconds": 2.0,
            "comparison": {
                "average_score": score,
                "fields": {
                    "title": {"score": score},
                    "creators_orcid": {"score": 0.0},
                },
            },
        }
        for name, score in scores.items()
    ]
    folder = results_dir / run_id / model
    folder.mkdir(parents=True)
    payload = {
        "extractor": "pdfplumber",
        "model": f"litellm/{model}",
        **run_info,
        "item_count": len(items),
        "average_score": sum(scores.values()) / len(scores),
        "items": items,
    }
    (folder / "results.json").write_text(json.dumps(payload))


def test_summary_ranks_whole_run_and_shared_items(tmp_path):
    """Whole run credits completing items; shared items compare like for like."""
    # model-a scores worse on x and y, but alone completes item z.
    _write(
        tmp_path,
        "2026-11-15T10-00-00",
        "model-a",
        {"x": 0.2, "y": 0.2, "z": 1.0},
        total_items=3,
        duration_seconds=437,
        langfuse="unavailable",
    )
    _write(
        tmp_path,
        "2026-11-15T10-00-00",
        "model-b",
        {"x": 0.4, "y": 0.4},
        total_items=3,
        duration_seconds=65,
        langfuse="ok",
    )
    _write(tmp_path, "2026-11-01T10-00-00", "model-b", {"x": 0.3, "y": 0.3})
    # A change too small to show reads as unchanged, not as an improvement.
    _write(
        tmp_path, "2026-11-01T10-00-00", "model-a", {"x": 0.2, "y": 0.2, "z": 0.9997}
    )

    readme = summarize(tmp_path, "2026-11-15T10-00-00", missing=["model-c"])

    whole_run, shared = readme.split("## Leaderboard: shared items")
    # Whole run: model-b's failed item z counts as 0, so (0.4 + 0.4 + 0) / 3.
    assert (
        "| 1 | model-a | **0.467** | ⬜ +0.000 | 0.467 | 3/3 | 0 | 7m 17s | 2.0s |"
        in whole_run
    )
    assert (
        "| 2 | model-b | 0.267 | 🟩 +0.100 | 0.400 | 2/3 | 1 | 1m 05s | 2.0s |"
        in whole_run
    )
    assert "Scored on the 2 items that all 2 models completed." in shared
    assert "| 1 | model-b | **0.400** |\n| 2 | model-a | 0.200 |" in shared
    assert "| title | **0.400** | 0.200 |" in readme
    assert "creators_orcid" not in readme
    assert "Langfuse was unavailable for model-a" in readme
    assert "Models with no results this run: model-c." in readme
