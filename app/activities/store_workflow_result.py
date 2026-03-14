"""Activity to persist workflow results and status in the database."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlmodel import Session, select
from temporalio import activity

from app.database.models import Workflow, WorkflowStatus
from app.database.session import get_engine


class StoreWorkflowResultRequest(BaseModel):
    """Request to persist a workflow result."""

    workflow_id: str = Field(description="Workflow public_id")
    tenant_id: str = Field(description="Tenant id (ownership check)")
    status: WorkflowStatus = Field(description="New workflow status")
    result: dict | None = Field(
        default=None,
        description="Serialized workflow result, stored as JSON (or null).",
    )


@activity.defn
async def store_workflow_result(request: StoreWorkflowResultRequest) -> None:
    """Persist workflow status/result to the database."""
    engine = get_engine()
    with Session(engine) as session:
        workflow = session.exec(
            select(Workflow).where(Workflow.public_id == request.workflow_id)
        ).one()
        # This check might be redundant given the tenant_id is part of the request
        # and the workflow is created with the tenant_id, it's a good safeguard
        # in case of manual calls.
        if workflow.tenant_id != request.tenant_id:
            raise ValueError("Tenant does not own this workflow")

        workflow.status = request.status
        workflow.result = request.result
        session.add(workflow)
        session.commit()
