"""Utility functions for PDF extractors."""

from typing import List, Optional


def parse_pages(pages_str: Optional[str]) -> Optional[List[int]]:
    """Parse page specification string into list of page numbers.
    
    Args:
        pages_str: String like "1,3-5,10" or "-1" (last page)
        
    Returns:
        List of page numbers (1-indexed), or None for all pages
    """
    if not pages_str:
        return None
    
    pages = []
    for part in pages_str.split(','):
        part = part.strip()
        if '-' in part and not part.startswith('-'):
            # Range like "3-5"
            start, end = part.split('-', 1)
            start, end = int(start), int(end)
            pages.extend(range(start, end + 1))
        else:
            # Single page number (including negative like "-1")
            pages.append(int(part))
    
    return pages


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