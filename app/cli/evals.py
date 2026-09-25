# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import asyncio
import os
from pathlib import Path

import typer

from app.evals.dataset_sync import sync_dataset
from app.evals.run import run as run_evaluation

evals_app = typer.Typer(
    help="Run evaluation workflows.",
)


@evals_app.command("sync_dataset")
def sync_dataset_command(
    repo: str = typer.Option(
        "zenodo/orcha-eval-dataset",
        "--repo",
        help="GitHub repository containing the eval dataset.",
    ),
    ref: str = typer.Option(
        "main",
        "--ref",
        help="Git reference to sync from.",
    ),
    cache: Path | None = typer.Option(
        None,
        "--cache",
        help="Cache directory for the eval dataset.",
    ),
    target: Path | None = typer.Option(
        None,
        "--target",
        help="Target directory for the eval dataset.",
    ),
):
    """Download the eval dataset into the local cache."""
    dataset_root, _ = sync_dataset(
        repo=repo,
        ref=ref,
        cache=cache,
        target=target,
    )
    typer.echo(f"Dataset ready at {dataset_root}")


@evals_app.command()
def run(
    model: str | None = typer.Option(None, "--model", help="LLM model override."),
    extractor: str = typer.Option(
        "pdfplumber", "--extractor", help="PDF extractor to use."
    ),
    prompt_name: str = typer.Option(
        "prompt", "--prompt", help="Prompt name to sync and use."
    ),
    use_langfuse: bool = typer.Option(
        False,
        "--langfuse",
        help="Store and report the experiment in Langfuse.",
    ),
    samples: int | None = typer.Option(
        None, "--samples", help="Sample this many items, proportionally per category."
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Where to write local results (default: app/evals/eval_results).",
    ),
    cache: Path | None = typer.Option(
        None, "--cache", help="Cache directory for the eval dataset."
    ),
    target: Path | None = typer.Option(
        None, "--target", help="Target directory for the eval dataset."
    ),
):
    """Run a local metadata extraction evaluation."""
    if model:
        os.environ["LLM"] = model

    try:
        asyncio.run(
            run_evaluation(
                extractor=extractor,
                prompt_name=prompt_name,
                use_langfuse=use_langfuse,
                samples=samples,
                results_dir=output,
                cache=cache,
                target=target,
            )
        )
    except FileNotFoundError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    except ModuleNotFoundError as error:
        if error.name != "langfuse":
            raise
        typer.echo(
            "--langfuse requires the optional 'langfuse' dependency. "
            "Install it with: uv sync --extra langfuse",
            err=True,
        )
        raise typer.Exit(1) from error
