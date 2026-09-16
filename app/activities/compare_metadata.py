# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""LLM-based metadata comparison activity."""

import json
from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import activity
from temporalio.common import RetryPolicy

from app.agent import build_agent
from app.config import get_settings
from app.observability import propagate_langfuse_context
from app.schemas.metadata_comparison import (
    LIST_FIELDS,
    SCALAR_FIELDS,
    ComparedMetadata,
    CurrentMetadata,
    MetadataComparisons,
)
from app.schemas.metadata_suggestions import MetadataSuggestions
from app.workflows.specs import WorkflowContext

COMPARE_METADATA_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=20),
    maximum_attempts=3,
)


class CompareMetadataRequest(BaseModel):
    """Request to compare two sets of metadata."""

    suggested_metadata: MetadataSuggestions = Field(
        description="Metadata suggestions generated from text"
    )
    current_metadata: CurrentMetadata = Field(
        description="Current fields from the deposit form"
    )


INSTRUCTIONS = (
    "Compare each already aligned pair of fields given to decide if they can be "
    "considered to describe the same underlying document. Base every explanation "
    "only on the values present in the pair you are given; When one side is null, "
    "state plainly that the value is missing from that side. Give a reasoning per "
    "pair and an overall decision on the document (for which values absent in "
    "suggested but present in current metadata are acceptable)."
)


def _align(suggested_metadata: list, current_metadata: list) -> list[dict]:
    """Pair two lists by matching items, or keeping unmatched items paired with None."""
    remaining = list(suggested_metadata)
    pairs = []
    for current in current_metadata:
        match = next(
            (suggested for suggested in remaining if current.matches(suggested)), None
        )
        if match is not None:
            remaining.remove(match)
        pairs.append(
            {
                "suggested": match.normalize_for_comparison()
                if match is not None
                else None,
                "current": current.normalize_for_comparison(matched=match),
            }
        )
    return pairs + [
        {"suggested": suggested.normalize_for_comparison(), "current": None}
        for suggested in remaining
    ]


def _build_pairs(suggested: MetadataSuggestions, current: CurrentMetadata) -> str:
    scalar_fields: dict[str, str] = {}
    list_fields: dict[str, list] = {}
    for s in suggested.suggestions:
        if isinstance(s.value, list):
            list_fields[s.field] = s.value
        else:
            scalar_fields[s.field] = s.value

    pairs = {}
    for field in SCALAR_FIELDS:
        suggested_field = scalar_fields.get(field)
        current_field = getattr(current, field)
        if suggested_field or current_field:
            pairs[field] = {
                "suggested": suggested_field or None,
                "current": current_field or None,
            }
    for field in LIST_FIELDS:
        suggested_field = list_fields.get(field, [])
        current_field = getattr(current, field)
        if suggested_field or current_field:
            pairs[field] = _align(suggested_field, current_field)

    return json.dumps(pairs, indent=1, ensure_ascii=False)


@activity.defn
async def compare_metadata_with_llm(
    request: CompareMetadataRequest,
    context: WorkflowContext,
) -> MetadataComparisons:
    """Compare two sets of metadata using an LLM."""
    suggested_metadata = request.suggested_metadata
    if not suggested_metadata.suggestions:
        return MetadataComparisons(
            comparisons=[],
            describes_file=False,
            decision="File does not have enough text for the comparison.",
        )
    current_metadata = request.current_metadata
    pairs = _build_pairs(suggested_metadata, current_metadata)

    agent = build_agent(get_settings().llm, ComparedMetadata, INSTRUCTIONS)
    with propagate_langfuse_context(context, trace_name="compare_metadata"):
        result = await agent.run(pairs)

    return result.output.to_comparisons(json.loads(pairs))
