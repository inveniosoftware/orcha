"""PyMuPDF-based PDF extractor."""

from typing import Any, Dict, List, Optional

from .base import BaseExtractor
from .utils import resolve_pages


class PymupdfExtractor(BaseExtractor):
    """Extract metadata and content using PyMuPDF/pymupdf4llm."""

    def extract(
        self, pdf_bytes: bytes, pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Extract content from PDF using Pymupdf."""
        # Import inside function to avoid PyMuPDF initialization issues in
        # temporal worker. PyMuPDF's C++ bindings have documented incompatibility with
        # threading/worker environments that cause "AttributeError: 'FzDocument' object
        # has no attribute 'super'" when imported at module level.
        # See: https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html
        import pymupdf
        import pymupdf4llm

        # Open PDF from bytes using PyMuPDF's stream interface
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)

        # PDF embedded metadata (often sparse)
        pdf_meta = doc.metadata or {}

        # Resolve page selection
        resolved_pages = resolve_pages(pages, page_count)

        # Extract markdown
        markdown = pymupdf4llm.to_markdown(doc, pages=resolved_pages)

        # Extract hyperlinks
        hyperlinks = []
        page_indices = resolved_pages if resolved_pages else range(page_count)
        for page_idx in page_indices:
            page = doc[page_idx]
            for link in page.get_links():
                uri = link.get("uri")
                if uri:
                    link_type = self._classify_link(uri)
                    hyperlinks.append(
                        {
                            "url": uri,
                            "page": page_idx + 1,
                            "type": link_type,
                        }
                    )

        doc.close()

        return {
            "full_text": markdown,
            "page_count": page_count,
            "pages_extracted": (
                [i + 1 for i in page_indices]
                if resolved_pages
                else list(range(1, page_count + 1))
            ),
            "extra": {
                "hyperlinks": hyperlinks,
                "pdf_metadata": pdf_meta,
            },
        }
