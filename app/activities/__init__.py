# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Activities for the Orcha application."""

from .check_funding_relevance import check_funding_relevance
from .compare_metadata import compare_metadata_with_llm
from .extract_metadata import extract_metadata_with_llm
from .extract_pdf_content import extract_pdf_text
from .resolve_metadata import resolve_metadata_suggestions
from .update_workflow import update_workflow

REGISTERED_ACTIVITIES = [
    extract_pdf_text,
    extract_metadata_with_llm,
    resolve_metadata_suggestions,
    update_workflow,
    check_funding_relevance,
    compare_metadata_with_llm,
]

__all__ = [
    "REGISTERED_ACTIVITIES",
    "extract_pdf_text",
    "extract_metadata_with_llm",
    "resolve_metadata_suggestions",
    "update_workflow",
    "check_funding_relevance",
    "compare_metadata_with_llm",
]
