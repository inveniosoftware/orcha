"""Workflow API routes with tenant-scoped access control."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from temporalio.client import Client

from app.auth import AuthContext, decode_access_token
from app.database.models import Workflow, WorkflowStatus
from app.database.session import get_session
from app.dependencies import get_current_user
from app.workflows.extract_metadata_workflow import ExtractMetadata

router = APIRouter(
    prefix="/workflows",
    tags=["workflows"],
    responses={404: {"description": "Not found"}},
)

STREAM_DELAY = 1


class CreateWorkflowRequest(BaseModel):
    """Request body for creating a new workflow."""

    url: str
    extractor: str = "pdfplumber"  # Default to pdfplumber
    pages: list[int] | None = None  # Page selection


def _get_temporal_client(request: Request) -> Client:
    return request.app.state.temporal_client


def verify_workflow_access(auth: AuthContext, workflow_id: str) -> None:
    """Verify that the JWT payload allows access to the requested workflow."""
    if auth.workflow_id and auth.workflow_id != "*" and auth.workflow_id != workflow_id:
        raise HTTPException(status_code=403, detail="Not authorized for this workflow")


def verify_tenant_owns_workflow(auth: AuthContext, workflow: Workflow) -> None:
    """Verify the authenticated tenant owns the workflow.

    Args:
        auth: The authenticated request context.
        workflow: The workflow database record.

    Raises:
        HTTPException: 403 if the tenant does not own the workflow.
    """
    if workflow.tenant_id != auth.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this workflow",
        )


@router.get(
    "/",
)
async def read_all(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List all workflows for the authenticated tenant."""
    workflows = session.exec(
        select(Workflow).where(Workflow.tenant_id == auth.tenant_id)
    ).all()
    return [workflow.to_dict() for workflow in workflows]


@router.post(
    "/",
)
async def create(
    body: CreateWorkflowRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a new workflow and start the Temporal extraction."""
    workflow = Workflow(
        status=WorkflowStatus.PROCESSING,
        url=body.url,
        tenant_id=auth.tenant_id,
    )
    try:
        session.add(workflow)
        session.commit()
        workflow_id = workflow.public_id
    except SQLAlchemyError as e:
        print("Error(create)", e)
        raise HTTPException(status_code=500, detail="Could not create workflow")

    try:
        client = _get_temporal_client(request)
        await client.start_workflow(
            ExtractMetadata.run,
            args=[{"url": body.url, "extractor": body.extractor, "pages": body.pages}],
            id=f"extract-metadata-{workflow_id}",
            task_queue="extract-pdf-metadata-task-queue",
        )
        workflow.status = WorkflowStatus.SUCCESS
        session.commit()
    except Exception as e:
        print("Error(start_temporal_workflow)", e)
        try:
            workflow.status = WorkflowStatus.ERROR
            session.commit()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=500, detail="Could not start extraction workflow"
        )

    return {"public_id": workflow_id, "status": "PROCESSING"}


@router.get(
    "/{workflow_id}",
)
async def read(
    workflow_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get a single workflow by its public ID."""
    verify_workflow_access(auth, workflow_id)

    try:
        workflow = session.exec(
            select(Workflow).where(Workflow.public_id == workflow_id)
        ).one()
    except SQLAlchemyError as e:
        print("Error(read)", e)
        raise HTTPException(status_code=404, detail="Workflow not found")

    verify_tenant_owns_workflow(auth, workflow)
    return workflow.to_dict()


async def workflow_event(request: Request, workflow_id: str):
    """Generate SSE events for workflow status updates."""
    while True:
        if await request.is_disconnected():
            break

        with Session(request.app.state.db_engine) as session:
            try:
                workflow = session.exec(
                    select(Workflow).where(Workflow.public_id == workflow_id)
                ).one()
                if workflow.status.name == "ERROR" or workflow.status.name == "SUCCESS":
                    yield workflow.status.name
                    break

                yield workflow.status.name
            except SQLAlchemyError as e:
                print("Error(stream)", e)
                raise HTTPException(status_code=500)

        await asyncio.sleep(STREAM_DELAY)


@router.get("/{workflow_id}/stream")
async def stream(
    request: Request,
    workflow_id: str,
    token: str,
    session: Session = Depends(get_session),
):
    """Stream workflow status updates via SSE.

    Auth is via the `?token=` query parameter (required), since
    browser EventSource cannot set custom headers.
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing token query parameter",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.dependencies import get_tenant_registry

    registry = get_tenant_registry(request)
    auth = decode_access_token(token, registry)

    verify_workflow_access(auth, workflow_id)

    # Verify tenant owns the workflow before streaming
    try:
        workflow = session.exec(
            select(Workflow).where(Workflow.public_id == workflow_id)
        ).one()
    except SQLAlchemyError:
        raise HTTPException(status_code=404, detail="Workflow not found")

    verify_tenant_owns_workflow(auth, workflow)

    return StreamingResponse(
        workflow_event(request, workflow_id), media_type="text/event-stream"
    )
