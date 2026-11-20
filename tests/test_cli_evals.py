import os
import subprocess
import sys
from pathlib import Path
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
            "--item-timeout",
            "30",
        ],
    )

    assert result.exit_code == 0
    assert os.environ["LLM"] == "litellm/test-model"
    fake_run.assert_called_once_with(
        extractor="pdfplumber",
        prompt_name="prompt",
        use_langfuse=False,
        ignore_langfuse_errors=False,
        save_json=False,
        samples=None,
        seed=42,
        item_timeout=30.0,
        results_dir=None,
        cache=None,
        target=None,
    )


def test_run_evals_can_enable_langfuse(monkeypatch):
    """`--langfuse` enables Langfuse without local JSON saving."""
    fake_run = Mock()

    monkeypatch.setattr("app.cli.evals.run_evaluation", fake_run)
    monkeypatch.setattr("app.cli.evals.asyncio.run", lambda coro: None)

    result = runner.invoke(app, ["evals", "run", "--langfuse"])

    assert result.exit_code == 0
    fake_run.assert_called_once_with(
        extractor="pdfplumber",
        prompt_name="prompt",
        use_langfuse=True,
        ignore_langfuse_errors=False,
        save_json=False,
        samples=None,
        seed=42,
        item_timeout=120.0,
        results_dir=None,
        cache=None,
        target=None,
    )


def test_run_evals_can_enable_langfuse_and_save_json(monkeypatch):
    """`--langfuse --ignore-langfuse-errors --save-json` passes all three flags."""
    fake_run = Mock()

    monkeypatch.setattr("app.cli.evals.run_evaluation", fake_run)
    monkeypatch.setattr("app.cli.evals.asyncio.run", lambda coro: None)

    result = runner.invoke(
        app, ["evals", "run", "--langfuse", "--ignore-langfuse-errors", "--save-json"]
    )

    assert result.exit_code == 0
    fake_run.assert_called_once_with(
        extractor="pdfplumber",
        prompt_name="prompt",
        use_langfuse=True,
        ignore_langfuse_errors=True,
        save_json=True,
        samples=None,
        seed=42,
        item_timeout=120.0,
        results_dir=None,
        cache=None,
        target=None,
    )


def test_cli_imports_without_the_langfuse_extra():
    """Any `orcha` command must start without the optional 'langfuse' extra."""
    code = "import sys; sys.modules['langfuse'] = None; import app.cli.main"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
