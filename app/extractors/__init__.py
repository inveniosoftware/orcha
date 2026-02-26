"""PDF extraction modules."""

from .pdfplumber_extractor import PdfplumberExtractor
from .pymupdf_extractor import PymupdfExtractor


def get_extractor(extractor_type: str = "pdfplumber"):
    """Get an extractor instance by type.
    
    Args:
        extractor_type: Either "pdfplumber" or "pymupdf"
        
    Returns:
        Extractor instance
    """
    if extractor_type == "pymupdf":
        return PymupdfExtractor()
    else:  # default to pdfplumber
        return PdfplumberExtractor()


