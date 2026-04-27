"""Custom exceptions for PDF extractors."""


class InvalidPageSelectionError(ValueError):
    """Raised when a requested page selection is invalid for a PDF."""
