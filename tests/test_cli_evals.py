import os
from unittest.mock import Mock

from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()


def test_run_evals_sets_model_and_passes_options(monkeypatch):
    """`orcha evals run` sets the LLM and passes options to the evaluator."""
    fake_run = Mock()

    monkeypatch.delenv("LLM", raising=False)
    monkeypatch.setattr("app.cli.evals.run_evaluation", fake_run)
    monkeypatch.setattr("app.cli.evals.asyncio.run", lambda coro: None)

    result = runner.invoke(
        app,
        [
            "evals",
            "run",
            "--model",
            "litellm/test-model",
            "--extractor",
            "pdfplumber",
            "--prompt",
            "prompt",
        ],
    )

    assert result.exit_code == 0
    assert os.environ["LLM"] == "litellm/test-model"
    fake_run.assert_called_once_with(
        extractor="pdfplumber",
        prompt_name="prompt",
        use_langfuse=False,
        samples=None,
        results_dir=None,
        cache=None,
        target=None,
    )


def test_run_evals_can_enable_langfuse(monkeypatch):
    """`orcha evals run --langfuse` enables Langfuse reporting."""
    fake_run = Mock()

    monkeypatch.setattr("app.cli.evals.run_evaluation", fake_run)
    monkeypatch.setattr("app.cli.evals.asyncio.run", lambda coro: None)

    result = runner.invoke(app, ["evals", "run", "--langfuse"])

    assert result.exit_code == 0
    fake_run.assert_called_once_with(
        extractor="pdfplumber",
        prompt_name="prompt",
        use_langfuse=True,
        samples=None,
        results_dir=None,
        cache=None,
        target=None,
    )
