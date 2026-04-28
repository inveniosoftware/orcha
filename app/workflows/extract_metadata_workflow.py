from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
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
from app.schemas.metadata_suggestions import MetadataSuggestions
from app.workflows.registry import (
    WorkflowContext,
    WorkflowSpec,
    register_workflow,
)


class ExtractMetadataParams(BaseModel):
    """User-provided params for the extract_metadata workflow."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    extractor: str = "pdfplumber"
    pages: list[int] | None = Field(default_factory=lambda: [1, 2])


class ExtractMetadataWorkflowRequest(BaseModel):
    """Workflow request to extract PDF content and generate metadata suggestions."""

    workflow_id: str = Field(description="Workflow public_id (DB primary identifier)")
    tenant_id: str = Field(description="Tenant id (ownership check)")
    url: str
    extractor: str = "pdfplumber"
    pages: list[int] | None = Field(default_factory=lambda: [1, 2])


def build_extract_metadata_request(
    context: WorkflowContext,
    params: BaseModel,
) -> ExtractMetadataWorkflowRequest:
    """Combine validated workflow params with server-generated context."""
    if not isinstance(params, ExtractMetadataParams):
        raise TypeError("Expected ExtractMetadataParams")

    return ExtractMetadataWorkflowRequest(
        workflow_id=context.workflow_id,
        tenant_id=context.tenant_id,
        url=str(params.url),
        extractor=params.extractor,
        pages=params.pages,
    )


@workflow.defn
class ExtractMetadata(PydanticAIWorkflow):
    """Workflow that extracts content from a PDF and uses an LLM to extract metadata."""

    @workflow.run
    async def run(self, request: ExtractMetadataWorkflowRequest) -> MetadataSuggestions:
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


register_workflow(
    "extract_metadata",
    WorkflowSpec(
        workflow_fn=ExtractMetadata.run,
        params_model=ExtractMetadataParams,
        request_builder=build_extract_metadata_request,
        task_queue="extract-pdf-metadata-task-queue",
        id_prefix="extract-metadata",
    ),
)
