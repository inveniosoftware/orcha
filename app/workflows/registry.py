"""Workflow registry — maps workflow type names to Temporal dispatch details."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class WorkflowSpec:
    """Describes a Temporal workflow that the API can dispatch."""

    workflow_fn: Any
    """The ``@workflow.defn`` class's entry-point method (e.g. ``ExtractMetadata.run``)."""

    request_class: type[BaseModel]
    """Pydantic model used to validate workflow-specific parameters."""

    task_queue: str
    """Temporal task queue that workers listen on for this workflow."""

    id_prefix: str
    """Prefix used when constructing the Temporal workflow ID."""

    param_fields: tuple[str, ...] = field(default_factory=tuple)
    """Fields from the API ``params`` dict that are forwarded to *request_class*."""


# Global registry — populated at import time by each workflow module.
WORKFLOW_REGISTRY: dict[str, WorkflowSpec] = {}


def register_workflow(name: str, spec: WorkflowSpec) -> None:
    """Register a workflow type.

    Raises:
        ValueError: If *name* is already registered.
    """
    if name in WORKFLOW_REGISTRY:
        raise ValueError(f"Workflow type {name!r} is already registered")
    WORKFLOW_REGISTRY[name] = spec


def get_workflow_spec(name: str) -> WorkflowSpec:
    """Look up a registered workflow by type name.

    Raises:
        KeyError: If *name* has not been registered.
    """
    try:
        return WORKFLOW_REGISTRY[name]
    except KeyError:
        registered = ", ".join(sorted(WORKFLOW_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown workflow type {name!r}. Registered types: {registered}"
        ) from None


def get_registered_types() -> list[str]:
    """Return a sorted list of all registered workflow type names."""
    return sorted(WORKFLOW_REGISTRY)
