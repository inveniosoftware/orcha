from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.evals.dataset import get_or_create_langfuse_dataset
from app.evals.run import _connect_langfuse, format_scores

ITEMS = [
    {"id": "a", "input": {"record_id": "a"}, "expected_output": {"title": "A"}},
    {"id": "b", "input": {"record_id": "b"}, "expected_output": {"title": "B"}},
]


@pytest.fixture
def unreachable_langfuse(monkeypatch):
    """Point the Langfuse client at a closed local port."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LANGFUSE_TIMEOUT", "1")


def test_connect_langfuse_returns_none_when_ignoring_errors(unreachable_langfuse):
    """With ignore_errors, an unreachable Langfuse means running without it."""
    assert _connect_langfuse(ITEMS, "prompt", ignore_errors=True) is None


def test_connect_langfuse_raises_without_ignore_errors(unreachable_langfuse):
    """Without ignore_errors, an unreachable Langfuse fails the run."""
    with pytest.raises(Exception):
        _connect_langfuse(ITEMS, "prompt")


def test_format_scores_matches_the_langfuse_summary():
    """Local runs print the per-evaluation averages CI checks and compares."""

    def result(title, doi):
        return {
            "comparison": {
                "average_score": (title + doi) / 2,
                "fields": {
                    "title": {
                        "score": title,
                        "expected": "",
                        "predicted": "",
                        "matched": False,
                    },
                    "doi": {
                        "score": doi,
                        "expected": "",
                        "predicted": "",
                        "matched": False,
                    },
                },
            }
        }

    summary = format_scores([result(1.0, 0.0), result(0.5, 1.0)])

    assert summary.splitlines() == [
        "Average Scores:",
        "  • title_score: 0.750",
        "  • doi_score: 0.500",
        "  • item_summary: 0.625",
        "",
        "Run Evaluations:",
        "  • run_average_score: 0.620",
    ]


def test_langfuse_dataset_returns_only_the_items_being_run():
    """Items stored in Langfuse but not being run are left out."""
    stored = [SimpleNamespace(id=item_id) for item_id in ("a", "b", "stale")]
    langfuse = Mock()
    langfuse.get_dataset.return_value = SimpleNamespace(items=stored)

    data = get_or_create_langfuse_dataset(langfuse, "dataset", ITEMS[:1])

    assert [item.id for item in data] == ["a"]
    langfuse.create_dataset_item.assert_not_called()
