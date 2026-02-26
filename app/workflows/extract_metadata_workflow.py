from datetime import timedelta

from pydantic import BaseModel, Field
from pydantic_ai.durable_exec.temporal import (
    PydanticAIWorkflow,
)
from temporalio import workflow

from app.activities import extract_pdf_content


class DocumentMetadata(BaseModel):
    """Structured metadata extracted from a PDF document."""

    title: str | None = Field(default=None, description="The title of the document")
    authors: list[str] | None = Field(
        default=None, description="List of document authors"
    )
    publication_date: str | None = Field(
        default=None,
        description="Publication date in ISO format (YYYY-MM-DD, YYYY-MM, or YYYY)",
    )
    abstract: str | None = Field(
        default=None,
        description="Abstract or summary of the document, extracted verbatim",
    )
    language: str | None = Field(
        default=None, description="Language of the document (e.g. 'en', 'fr')"
    )
    keywords: list[str] | None = Field(
        default=None, description="Key topics or keywords from the document"
    )
    num_pages: int | None = Field(
        default=None, description="Number of pages in the document"
    )


METADATA_INSTRUCTIONS = """\
You are an expert at extracting structured metadata from documents.

Given the raw text content of a PDF document, extract the following metadata fields:
- title: The main title of the document.
- authors: A list of authors. Look for names near the title,
  in headers, or in an authors section.
- publication_date: The publication date in ISO format (YYYY-MM-DD, YYYY-MM, or YYYY).
- abstract: The abstract or summary, extracted verbatim from the document.
- language: The language the document is written in (ISO 639-1 code, e.g. "en").
- keywords: Key topics or keywords mentioned in the document.
- num_pages: The number of pages (this will be provided to you).

IMPORTANT RULES:
1. Only include information explicitly stated in the document.
2. If a field is not present or cannot be determined, leave it as null.
3. For the abstract, include the text verbatim from the document.
4. Do not fabricate or infer information that is not in the text.
"""

# metadata_agent = Agent(
#     "openai:gpt-4o-mini",
#     instructions=METADATA_INSTRUCTIONS,
#     output_type=DocumentMetadata,
#     name="metadata_extractor",
# )
#
# temporal_metadata_agent = TemporalAgent(
#     metadata_agent,
#     model_activity_config=workflow.ActivityConfig(
#         start_to_close_timeout=timedelta(minutes=5),
#     ),
# )
#


@workflow.defn
class ExtractMetadata(PydanticAIWorkflow):
    """Workflow that extracts content from a PDF and uses an LLM to extract metadata."""

    # __pydantic_ai_agents__ = [temporal_metadata_agent]

    @workflow.run
    async def run(self, request_data: dict) -> DocumentMetadata:
        content = await workflow.execute_activity(
            extract_pdf_content.create,
            extract_pdf_content.ExtractPdfContentRequest(**request_data),
            start_to_close_timeout=timedelta(minutes=5),
        )

        # prompt = (
        #     f"The following is the text content extracted from a PDF document "
        #     f"({content.num_pages} pages).\n\n"
        #     f"---\n{content.text}\n---\n\n"
        #     f"Please extract the structured metadata from this document."
        # )

        # result = await temporal_metadata_agent.run(prompt)
        # return result.output
        return content
