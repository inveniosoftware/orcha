import httpx
from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.extractors import get_extractor


class ExtractPdfContentRequest(BaseModel):
    """Request to extract PDF content from a URL."""

    url: str
    extractor: str = "pdfplumber"  # Default to pdfplumber
    pages: list[int] | None = None  # Optional list of page numbers (1-indexed)


class ExtractPdfContentResponse(BaseModel):
    """Response containing extracted PDF text and page numbers."""

    text: str
    extractor: str
    pages_extracted: list[int]  # List of 1-indexed page numbers that were extracted


@activity.defn
async def text_extraction(
    request: ExtractPdfContentRequest,
) -> ExtractPdfContentResponse:
    """Download PDF from a URL and extract its content using the specified extractor."""
    async with httpx.AsyncClient() as client:
        response = await client.get(request.url)
        response.raise_for_status()
        pdf_bytes = response.content

    # Extract content using the extraction module
    try:
        extractor = get_extractor(request.extractor)
    except ValueError as e:
        # Convert ValueError to non-retryable ApplicationError for proper
        # Temporal error handling
        raise ApplicationError(
            str(e),
            type="InvalidExtractor",
            non_retryable=True,
        ) from e

    result = extractor.extract(pdf_bytes, request.pages)

    return ExtractPdfContentResponse(
        text=result["full_text"],
        pages_extracted=result["pages_extracted"],
        extractor=request.extractor,
    )
