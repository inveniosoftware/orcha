"""PDF extraction modules."""

from .pdfplumber import PdfplumberExtractor
from .pymupdf import PymupdfExtractor


def get_extractor(extractor: str = "pdfplumber"):
    """Get an extractor instance by type.

    Args:
        extractor: Either "pdfplumber" or "pymupdf"

    Returns:
        Extractor instance
    """
    if extractor == "pymupdf":
        return PymupdfExtractor()
    else:  # default to pdfplumber
        return PdfplumberExtractor()
