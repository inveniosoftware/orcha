"""PDFPlumber-based PDF extractor."""

from io import BytesIO
from typing import Any, Dict, List, Optional

from .base import BaseExtractor
from .utils import resolve_pages


class PdfplumberExtractor(BaseExtractor):
    """Extract content using pdfplumber."""

    def extract(
        self, pdf_bytes: bytes, pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Extract content from PDF using pdfplumber."""
        import pdfplumber

        full_text_parts = []
        tables = []
        hyperlinks = []

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            page_count = len(pdf.pages)

            # Resolve page selection
            resolved_pages = resolve_pages(pages, page_count)
            page_indices = resolved_pages if resolved_pages else range(page_count)

            for page_num in page_indices:
                page = pdf.pages[page_num]
                # Extract text with x_tolerance=2 to better detect word boundaries
                # Default x_tolerance=3 merges words like "PhilipBull" that have gaps
                text = page.extract_text(x_tolerance=2) or ""
                full_text_parts.append(text)

                # Extract tables
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        tables.append(
                            {
                                "page": page_num + 1,
                                "rows": len(table),
                                "data": table,
                            }
                        )

                # Extract hyperlinks (annotations with URI)
                if page.annots:
                    for annot in page.annots:
                        uri = annot.get("uri")
                        if uri:
                            link_type = self._classify_link(uri)
                            hyperlinks.append(
                                {
                                    "url": uri,
                                    "page": page_num + 1,
                                    "type": link_type,
                                }
                            )

        # Build full text including table content
        full_text = "\n\n".join(full_text_parts)

        # Add table content to full_text for searchability
        for table in tables:
            for row in table["data"]:
                if row:
                    row_text = " | ".join(str(cell) if cell else "" for cell in row)
                    full_text += "\n" + row_text

        # Extract ORCID IDs from hyperlinks and add to full_text
        # This makes ORCIDs discoverable even when they're only in link URLs
        # (not visible text)
        orcid_ids = [
            self._extract_orcid_id(h["url"]) for h in hyperlinks if h["type"] == "orcid"
        ]
        orcid_ids = [oid for oid in orcid_ids if oid]  # filter None
        if orcid_ids:
            full_text += "\n\nORCID IDs from hyperlinks: " + " ".join(orcid_ids)

        return {
            "full_text": full_text,
            "page_count": page_count,
            "pages_extracted": (
                [i + 1 for i in page_indices]
                if resolved_pages
                else list(range(1, page_count + 1))
            ),
            "extra": {
                "hyperlinks": hyperlinks,
                "tables": tables,
            },
        }

    def _extract_orcid_id(self, url: str) -> str | None:
        """Extract ORCID ID from an orcid.org URL."""
        import re

        match = re.search(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", url)
        return match.group(1) if match else None
