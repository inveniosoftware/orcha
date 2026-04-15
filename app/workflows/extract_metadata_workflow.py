from datetime import timedelta

from pydantic import BaseModel, Field
from pydantic_ai.durable_exec.temporal import (
    PydanticAIWorkflow,
)
from temporalio import workflow

from app.activities.extract_metadata import (
    ExtractMetadataRequest,
    extract_metadata_with_llm,
)
from app.activities.extract_pdf_content import (
    ExtractPdfContentRequest,
    extract_pdf_text,
)
from app.activities.store_workflow_result import (
    WorkflowResultInput,
    store_workflow_result,
)
from app.database.models import WorkflowStatus
from app.workflows.suggestions import MetadataResult


class ExtractMetadataWorkflowRequest(BaseModel):
    """Workflow request to extract PDF content and generate metadata suggestions."""

    workflow_id: str = Field(description="Workflow public_id (DB primary identifier)")
    tenant_id: str = Field(description="Tenant id (ownership check)")
    url: str
    extractor: str = "pdfplumber"
    pages: list[int] | None = None


@workflow.defn
class ExtractMetadata(PydanticAIWorkflow):
    """Workflow that extracts content from a PDF and uses an LLM to extract metadata."""

    @workflow.run
    async def run(self, request: ExtractMetadataWorkflowRequest) -> MetadataResult:
        """Execute the extraction + suggestions workflow."""
        try:
            # Activity 1: Extract PDF text
            content = await workflow.execute_activity(
                extract_pdf_text,
                ExtractPdfContentRequest(
                    url=request.url,
                    extractor=request.extractor,
                    pages=request.pages,
                ),
                start_to_close_timeout=timedelta(minutes=5),
            )

            # Activity 2: Generate metadata suggestions using LLM
            result = await workflow.execute_activity(
                extract_metadata_with_llm,
                ExtractMetadataRequest(text=content.text),
                start_to_close_timeout=timedelta(minutes=5),
            )
        except Exception:
            await workflow.execute_activity(
                store_workflow_result,
                WorkflowResultInput(
                    workflow_id=request.workflow_id,
                    tenant_id=request.tenant_id,
                    status=WorkflowStatus.ERROR,
                    result=None,
                ),
                start_to_close_timeout=timedelta(minutes=1),
            )
            raise

        await workflow.execute_activity(
            store_workflow_result,
            WorkflowResultInput(
                workflow_id=request.workflow_id,
                tenant_id=request.tenant_id,
                status=WorkflowStatus.SUCCESS,
                result=result.model_dump(),
            ),
            start_to_close_timeout=timedelta(minutes=1),
        )

        return result


# Self-register so the API router can dispatch this workflow by name.
from app.workflows.registry import WorkflowSpec, register_workflow

register_workflow(
    "extract_metadata",
    WorkflowSpec(
        workflow_fn=ExtractMetadata.run,
        request_class=ExtractMetadataWorkflowRequest,
        task_queue="extract-pdf-metadata-task-queue",
        id_prefix="extract-metadata",
        param_fields=("url", "extractor", "pages"),
    ),
)
