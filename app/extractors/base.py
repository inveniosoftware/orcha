"""Base class for PDF extractors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseExtractor(ABC):
    """Base class for PDF extractors."""

    @abstractmethod
    def extract(
        self, pdf_bytes: bytes, pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Extract content from PDF.

        Args:
            pdf_bytes: PDF file content as bytes.
            pages: Optional list of pages to extract. Positive numbers are 1-based,
                   negative numbers count from end (-1 = last page).
                   Example: [1, 2, 3, -2, -1] = first 3 + last 2 pages.

        Returns:
            Dictionary containing extracted content. Must include:
            - full_text: Extracted text content
            - page_count: Total number of pages in the PDF
            - pages_extracted: Number of pages that were actually extracted

        """
        pass

    def _classify_link(self, url: str) -> str:
        """Classify hyperlink type."""
        url_lower = url.lower()
        if "orcid.org" in url_lower:
            return "orcid"
        if "doi.org" in url_lower or url_lower.startswith("10."):
            return "doi"
        if url_lower.startswith("mailto:"):
            return "email"
        if "github.com" in url_lower or "gitlab.com" in url_lower:
            return "github"
        return "other"
