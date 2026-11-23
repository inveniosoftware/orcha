# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import asyncio
import os
from pathlib import Path

import typer

from app.evals.dataset import CATEGORIES
from app.evals.dataset_sync import sync_dataset
from app.evals.run import ITEM_TIMEOUT
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
    ignore_zenodo_errors: bool = typer.Option(
        False,
        "--ignore-zenodo-errors",
        help="Continue with GitHub LFS if fetching the dataset from Zenodo fails.",
    ),
):
    """Download the eval dataset into the local cache."""
    dataset_root, _ = sync_dataset(
        repo=repo,
        ref=ref,
        cache=cache,
        target=target,
        ignore_zenodo_errors=ignore_zenodo_errors,
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
    ignore_langfuse_errors: bool = typer.Option(
        False,
        "--ignore-langfuse-errors",
        help="With --langfuse, run on the local dataset if Langfuse is unavailable.",
    ),
    save_json: bool = typer.Option(
        False,
        "--save-json",
        help="Save per-item evaluation results to a local JSON file.",
    ),
    samples: int | None = typer.Option(
        None, "--samples", help="Sample this many items, proportionally per category."
    ),
    categories: list[str] | None = typer.Option(
        None,
        "--category",
        help=(
            "Only evaluate this category, by prefix or name. Repeat for more "
            "than one. Options: "
            + ", ".join(f"{prefix} ({name})" for prefix, name in CATEGORIES.items())
        ),
    ),
    seed: int = typer.Option(42, "--seed", help="Seed for the sampling."),
    item_timeout: float = typer.Option(
        ITEM_TIMEOUT,
        "--item-timeout",
        help="Seconds one item may take before it counts as failed.",
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
                ignore_langfuse_errors=ignore_langfuse_errors,
                save_json=save_json,
                samples=samples,
                categories=categories,
                seed=seed,
                item_timeout=item_timeout,
                results_dir=output,
                cache=cache,
                target=target,
            )
        )
    except (FileNotFoundError, ValueError) as error:
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
