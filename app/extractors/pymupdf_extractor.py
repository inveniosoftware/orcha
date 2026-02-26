"""PyMuPDF-based PDF extractor."""

import re
import tempfile
from typing import Dict, Any, Optional

from .base import parse_pages, resolve_pages

from pathlib import Path


class PymupdfExtractor:
    """Extract metadata and content using PyMuPDF/pymupdf4llm."""
    
    def extract(self, pdf_bytes: bytes, pages: Optional[str] = None) -> Dict[str, Any]:
        """Extract content from PDF.

        Args:
            pdf_path: Path to PDF file.
            pages: Optional list of pages to extract. Positive numbers are 1-based,
                   negative numbers count from end (-1 = last page).
                   Example: [1, 2, 3, -2, -1] = first 3 + last 2 pages.
        """
        import pymupdf
        import pymupdf4llm

        # Save to temporary file (pymupdf needs file path)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_file.flush()
            
            doc = pymupdf.open(temp_file.name)
            page_count = len(doc)
            
            # PDF embedded metadata (often sparse)
            pdf_meta = doc.metadata or {}
            
            # Parse and resolve page selection
            parsed_pages = parse_pages(pages)
            resolved_pages = resolve_pages(parsed_pages, page_count)
            
            # Extract markdown
            markdown = pymupdf4llm.to_markdown(temp_file.name, pages=resolved_pages)
            
            # Extract hyperlinks
            hyperlinks = []
            page_indices = resolved_pages if resolved_pages else range(page_count)
            for page_idx in page_indices:
                page = doc[page_idx]
                for link in page.get_links():
                    uri = link.get("uri")
                    if uri:
                        link_type = self._classify_link(uri)
                        hyperlinks.append({
                            "url": uri,
                            "page": page_idx + 1,
                            "type": link_type,
                        })
            
            doc.close()
            
            return {
                "full_text": markdown,
                "hyperlinks": hyperlinks,
                "page_count": page_count,
                "pages_extracted": len(resolved_pages) if resolved_pages else page_count,
                "_pdf_metadata": pdf_meta,
            }

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
    
    def _parse_keywords(keywords_str: str) -> list[str]:
        """Parse keywords from PDF metadata string."""
        if not keywords_str:
            return []
        # Common separators: comma, semicolon
        return [k.strip() for k in re.split(r"[,;]", keywords_str) if k.strip()]


    def _parse_authors(author_str: str) -> list[dict]:
        """Parse author string into structured list."""
        if not author_str:
            return []
        # PDF author field is usually a simple string or comma/semicolon separated
        names = re.split(r"[,;]", author_str)
        return [{"name": n.strip(), "affiliation": "", "orcid": ""} for n in names if n.strip()]


    def extract_xmp(pdf_path: Path) -> dict:
        """Extract XMP/Dublin Core metadata using pypdf."""
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        xmp = reader.xmp_metadata
        if not xmp:
            return {}
        return {
            "dc_title": getattr(xmp, "dc_title", None),
            "dc_creator": getattr(xmp, "dc_creator", None),
            "dc_description": getattr(xmp, "dc_description", None),
            "dc_identifier": getattr(xmp, "dc_identifier", None),
        }