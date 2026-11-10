# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Observability helpers."""

from collections.abc import Generator
from contextlib import contextmanager

from app.config import get_settings
from app.workflows.specs import WorkflowContext


def _langfuse_metadata(context: WorkflowContext) -> dict[str, str | None]:
    """Build Langfuse metadata from workflow context."""
    return {
        "workflowId": context.workflow_id,
        "tenantId": context.tenant_id,
        "userId": context.user_id,
    }


@contextmanager
def propagate_langfuse_context(
    context: WorkflowContext,
    *,
    trace_name: str,
) -> Generator[None]:
    """Propagate workflow context to Langfuse at activity runtime."""
    if not get_settings().langfuse_enabled:
        yield
        return

    from langfuse import propagate_attributes

    with propagate_attributes(
        user_id=context.user_id,
        session_id=context.workflow_id,
        trace_name=trace_name,
        metadata=_langfuse_metadata(context),
    ):
        yield
