"""Utility functions for PDF extractors."""

from typing import List, Optional


def resolve_pages(pages: Optional[List[int]], total_pages: int) -> Optional[List[int]]:
    """Resolve page list with negative indices to 0-based page numbers."""
    if pages is None:
        return None
    resolved = set()
    for p in pages:
        idx = p % total_pages if p < 0 else p - 1
        resolved.add(idx)
    return sorted(resolved)
