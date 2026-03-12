"""PDF extraction modules."""

from .pdfplumber import PdfplumberExtractor
from .pymupdf import PymupdfExtractor


def get_extractor(extractor: str = "pdfplumber"):
    """Get an extractor instance by type.

    Args:
        extractor: Either "pdfplumber" or "pymupdf"

    Returns:
        Extractor instance

    Raises:
        ValueError: If unknown extractor type is specified
    """
    if extractor == "pdfplumber":
        return PdfplumberExtractor()
    elif extractor == "pymupdf":
        return PymupdfExtractor()
    else:
        raise ValueError(
            f"Unknown extractor: {extractor}. "
            f"Supported extractors: pdfplumber, pymupdf"
        )
