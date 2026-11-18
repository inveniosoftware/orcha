# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Explicit workflow registry."""

from __future__ import annotations

from app.workflows.check_funding_relevance_workflow import (
    CheckFundingRelevance,
    CheckFundingRelevanceParams,
)
from app.workflows.compare_metadata_workflow import (
    CompareMetadata,
    CompareMetadataParams,
)
from app.workflows.extract_metadata_workflow import (
    ExtractMetadata,
    ExtractMetadataParams,
)
from app.workflows.queues import DEFAULT_TASK_QUEUE
from app.workflows.specs import WorkflowSpec

WORKFLOW_REGISTRY: dict[str, WorkflowSpec] = {
    "extract_metadata": WorkflowSpec(
        workflow_cls=ExtractMetadata,
        params_model=ExtractMetadataParams,
        task_queue=DEFAULT_TASK_QUEUE,
        id_prefix="extract-metadata",
    ),
    "check_funding_relevance": WorkflowSpec(
        workflow_cls=CheckFundingRelevance,
        params_model=CheckFundingRelevanceParams,
        task_queue=DEFAULT_TASK_QUEUE,
        id_prefix="check-funding-relevance",
    ),
    "compare_metadata": WorkflowSpec(
        workflow_cls=CompareMetadata,
        params_model=CompareMetadataParams,
        task_queue=DEFAULT_TASK_QUEUE,
        id_prefix="compare-metadata",
    ),
}


def get_workflow_spec(name: str) -> WorkflowSpec:
    """Look up a registered workflow by type name.

    Raises:
        KeyError: If *name* has not been registered.
    """
    try:
        return WORKFLOW_REGISTRY[name]
    except KeyError:
        registered = ", ".join(get_registered_types()) or "(none)"
        raise KeyError(
            f"Unknown workflow type {name!r}. Registered types: {registered}"
        ) from None


def get_registered_types() -> list[str]:
    """Return a sorted list of all registered workflow type names."""
    return sorted(WORKFLOW_REGISTRY)


def get_registered_specs() -> list[WorkflowSpec]:
    """Return registered workflow specs sorted by workflow type."""
    return [WORKFLOW_REGISTRY[name] for name in get_registered_types()]


def get_specs_for_task_queue(task_queue: str) -> list[WorkflowSpec]:
    """Return registered workflow specs served by a task queue."""
    return [spec for spec in get_registered_specs() if spec.task_queue == task_queue]


def get_registered_task_queues() -> list[str]:
    """Return task queues referenced by registered workflow specs."""
    return sorted({spec.task_queue for spec in WORKFLOW_REGISTRY.values()})
