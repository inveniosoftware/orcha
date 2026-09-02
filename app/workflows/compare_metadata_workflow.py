# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

from datetime import timedelta

from pydantic import Field, HttpUrl
from temporalio import workflow

from app.activities import (
    extract_metadata_with_llm,
    extract_pdf_text,
    resolve_metadata_suggestions,
)
from app.activities.compare_metadata import (
    COMPARE_METADATA_RETRY_POLICY,
    CompareMetadataRequest,
    compare_metadata_with_llm,
)
from app.activities.extract_metadata import (
    EXTRACT_METADATA_RETRY_POLICY,
    ExtractMetadataRequest,
)
from app.activities.extract_pdf_content import (
    EXTRACT_PDF_TEXT_RETRY_POLICY,
    ExtractPdfContentRequest,
)
from app.activities.resolve_metadata import (
    RESOLVE_METADATA_RETRY_POLICY,
    ResolveMetadataRequest,
)
from app.activities.update_workflow import (
    UPDATE_WORKFLOW_RETRY_POLICY,
    WorkflowUpdateRequest,
    update_workflow,
)
from app.database.models import WorkflowStatus
from app.schemas.metadata_comparison import CurrentMetadata, MetadataComparisons
from app.workflows.specs import WorkflowContext, WorkflowParams


class CompareMetadataParams(WorkflowParams):
    """Params for the compare_metadata workflow."""

    url: HttpUrl
    extractor: str = "pdfplumber"
    pages: list[int] | None = Field(default_factory=lambda: [1, 2])
    metadata: CurrentMetadata


@workflow.defn
class CompareMetadata:
    """Workflow that checks if a record's metadata matches the content of the record."""

    @workflow.run
    async def run(
        self,
        context: WorkflowContext,
        params: CompareMetadataParams,
    ) -> MetadataComparisons:
        """Execute the metadata comparison check."""
        try:
            await workflow.execute_activity(
                update_workflow,
                WorkflowUpdateRequest(
                    public_id=context.workflow_id,
                    tenant_id=context.tenant_id,
                    start_time=workflow.now(),
                ),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=UPDATE_WORKFLOW_RETRY_POLICY,
            )

            # Activity 1: Extract PDF text
            content = await workflow.execute_activity(
                extract_pdf_text,
                ExtractPdfContentRequest(
                    url=str(params.url),
                    extractor=params.extractor,
                    pages=params.pages,
                ),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=EXTRACT_PDF_TEXT_RETRY_POLICY,
            )

            # Activity 2: Generate raw metadata suggestions using LLM
            metadata = await workflow.execute_activity(
                extract_metadata_with_llm,
                args=[ExtractMetadataRequest(text=content.text), context],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=EXTRACT_METADATA_RETRY_POLICY,
            )

            # Activity 3: Resolve funders, awards, and licenses; format suggestions
            suggestions = await workflow.execute_activity(
                resolve_metadata_suggestions,
                ResolveMetadataRequest(metadata=metadata),
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RESOLVE_METADATA_RETRY_POLICY,
            )

            # Activity 4: compare the metadata suggestions with the deposit metadata
            result = await workflow.execute_activity(
                compare_metadata_with_llm,
                args=[
                    CompareMetadataRequest(
                        suggested_metadata=suggestions, current_metadata=params.metadata
                    ),
                    context,
                ],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=COMPARE_METADATA_RETRY_POLICY,
            )

        except Exception:
            await workflow.execute_activity(
                update_workflow,
                WorkflowUpdateRequest(
                    public_id=context.workflow_id,
                    tenant_id=context.tenant_id,
                    status=WorkflowStatus.ERROR,
                    result=None,
                    end_time=workflow.now(),
                ),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=UPDATE_WORKFLOW_RETRY_POLICY,
            )
            raise

        await workflow.execute_activity(
            update_workflow,
            WorkflowUpdateRequest(
                public_id=context.workflow_id,
                tenant_id=context.tenant_id,
                status=WorkflowStatus.SUCCESS,
                result=result.model_dump(),
                end_time=workflow.now(),
            ),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=UPDATE_WORKFLOW_RETRY_POLICY,
        )

        return result
