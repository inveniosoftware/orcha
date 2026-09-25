# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Langfuse prompt management."""

from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).with_name("prompts")


def sync_extraction_prompt(
    langfuse: Any, prompt_name: str = "medium"
) -> dict[str, Any]:
    """Create or version the extraction prompt in Langfuse and return its reference."""
    instructions = (PROMPTS_DIR / f"{prompt_name}.txt").read_text()

    created = langfuse.create_prompt(
        name=prompt_name,
        prompt=instructions,
        commit_message="Sync prompt from eval runner",
        type="text",
    )

    return {
        "name": prompt_name,
        "version": getattr(created, "version", None),
        "text": instructions,
    }
