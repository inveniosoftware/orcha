# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Langfuse dataset management."""

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from langfuse.api import NotFoundError


def _expected_output_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Map dataset metadata to the expected output schema."""
    title = metadata.get("title")
    if not title:
        title = metadata.get("titles")

    return {
        "title": title,
        "description": metadata.get("description")
        or metadata.get("abstract")
        or metadata.get("abstracts"),
        "creators": metadata.get("creators") or metadata.get("authors") or [],
        "doi": metadata.get("doi"),
        "publication_date": metadata.get("publication_date"),
    }


def load_local_dataset(dataset_root: Path, dataset_name: str) -> list[dict[str, Any]]:
    """Load dataset items from local metadata files."""
    items = []
    metadata_dir = dataset_root / "metadata"
    if not metadata_dir.exists():
        metadata_dir = dataset_root / "Metadata"

    if not metadata_dir.exists():
        raise FileNotFoundError(
            f"Could not find metadata directory under {dataset_root}"
        )

    for meta_path in metadata_dir.rglob("*.json"):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        file_paths = metadata.get("file_paths")
        if not file_paths:
            continue

        # Use first file listed
        pdf_path = dataset_root / file_paths[0]
        if not pdf_path.exists():
            continue
        pdf_parts = Path(file_paths[0]).parts
        category = pdf_parts[1] if len(pdf_parts) > 1 else "unknown"

        items.append(
            {
                "id": f"{Path(file_paths[0]).name}_{dataset_name}",
                "input": {
                    "record_id": meta_path.stem,
                    "category": category,
                    "metadata_file": str(meta_path.relative_to(metadata_dir)),
                    "pdf_path": str(pdf_path),
                },
                "expected_output": _expected_output_from_metadata(metadata),
            }
        )

    return items


def sample_items(
    items: list[dict[str, Any]], samples: int | None
) -> list[dict[str, Any]]:
    """Return a random subset, sampled proportionally by category."""
    if samples is None or samples >= len(items):
        return items

    items_by_category = defaultdict(list)
    for item in items:
        items_by_category[item["input"]["category"]].append(item)

    category_counts = {}
    for category, category_items in items_by_category.items():
        expected_count = samples * len(category_items) / len(items)
        category_counts[category] = (
            math.floor(expected_count),
            expected_count,
        )

    categories_by_remainder = sorted(
        category_counts.items(),
        key=lambda x: x[1][1] % 1,
        reverse=True,
    )

    remaining_samples = samples - sum(count[0] for _, count in categories_by_remainder)

    selected = []
    rng = random.Random()
    for category, (count, _) in categories_by_remainder:
        if remaining_samples > 0:
            count += 1
            remaining_samples -= 1

        selected.extend(rng.sample(items_by_category[category], count))

    rng.shuffle(selected)
    return selected[:samples]


def get_or_create_langfuse_dataset(
    langfuse: Any,
    dataset_name: str,
    dataset_items: list[dict[str, Any]],
) -> Any:
    """Get existing Langfuse dataset if it exists. If not, create and populate it."""
    try:
        langfuse_dataset = langfuse.get_dataset(name=dataset_name)
        langfuse_dataset_items = list(langfuse_dataset.items)
        if langfuse_dataset_items:
            return langfuse_dataset_items
    except NotFoundError:
        pass  # expected on first run, it will be created below
    except Exception as e:
        print(f"ERROR GETTING LANGFUSE DATASET: {e!r}")
        raise

    # Populate dataset if it doesn't exist yet in Langfuse
    dataset = langfuse.create_dataset(
        name=dataset_name, description="Evaluation Dataset"
    )
    for item in dataset_items:
        item_id = item.get("id") or item["input"].get("record_id")

        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            id=item_id,
            input=item["input"],
            expected_output=item["expected_output"],
        )
    dataset = langfuse.get_dataset(name=dataset_name)
    return list(dataset.items)
