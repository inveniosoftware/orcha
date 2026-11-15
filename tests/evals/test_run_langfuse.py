import pytest

from app.config import get_settings
from app.evals.run import _run_langfuse

ITEMS = [
    {"id": "a", "input": {"record_id": "a"}, "expected_output": {"title": "A"}},
    {"id": "b", "input": {"record_id": "b"}, "expected_output": {"title": "B"}},
]


async def _extract(item):
    record_id = item["input"]["record_id"]
    return {
        "pdf_filename": f"{record_id}__doc.pdf",
        "comparison": {"average_score": 0.5, "fields": {}},
    }


@pytest.fixture
def unreachable_langfuse(monkeypatch):
    """Point the Langfuse client at a closed local port."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LANGFUSE_TIMEOUT", "1")


def test_run_langfuse_falls_back_to_local_items(unreachable_langfuse):
    """With ignore_errors, an unreachable Langfuse still evaluates every item."""
    results = _run_langfuse(
        ITEMS, _extract, "pdfplumber", "prompt", None, get_settings(), True
    )

    assert sorted(r["pdf_filename"] for r in results) == [
        "a__doc.pdf",
        "b__doc.pdf",
    ]


def test_run_langfuse_raises_without_ignore_errors(unreachable_langfuse):
    """Without ignore_errors, an unreachable Langfuse fails the run."""
    with pytest.raises(Exception):
        _run_langfuse(ITEMS, _extract, "pdfplumber", "prompt", None, get_settings())
