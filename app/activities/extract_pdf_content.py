from io import BytesIO
from typing import Union

import httpx
from pydantic import BaseModel
from temporalio import activity

from app.extractors import get_extractor


class ExtractPdfContentRequest(BaseModel):
    """Request to extract PDF content from a URL."""

    url: str
    extractor_type: str = "pdfplumber"  # Default to pdfplumber
    pages: str | None = None            # Optional page specification such as "1,3-5,-1"


class ExtractPdfContentResponse(BaseModel):
    """Response containing extracted PDF text and page count."""

    text: str
    num_pages: int
    extractor_used: str
    pages_extracted: int


@activity.defn
async def create(request: ExtractPdfContentRequest) -> ExtractPdfContentResponse:
    """Download a PDF from a URL and extract its content using the specified extractor."""
    async with httpx.AsyncClient() as client:
        response = await client.get(request.url)
        response.raise_for_status()
        pdf_bytes = response.content

    # Extract content using the extraction module
    extractor = get_extractor(request.extractor_type)
    result = extractor.extract(pdf_bytes, request.pages)
    
    return ExtractPdfContentResponse(
        text=result["full_text"],
        num_pages=result["page_count"],
        pages_extracted=result["pages_extracted"],
        extractor_used=request.extractor_type,
    )
