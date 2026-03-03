"""Utility functions for PDF extractors."""

from typing import List, Optional


def resolve_pages(pages: Optional[List[int]], total_pages: int) -> Optional[List[int]]:
    """Resolve page list with negative indices to 0-based page numbers."""
    if pages is None:
        return None
    resolved = []
    for p in pages:
        if p < 0:
            idx = total_pages + p  # -1 -> last page
        else:
            idx = p - 1  # convert 1-based to 0-based
        if 0 <= idx < total_pages:
            resolved.append(idx)
    return sorted(set(resolved))
