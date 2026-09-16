# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the extract_metadata activity's non-LLM guards.

Covers the two deterministic layers around the LLM call: the empty-text gate
(no LLM on image-only PDFs) and the post-hoc presence check (null values not
present in the source text). The LLM call itself is not exercised here.
"""

import asyncio

import pytest

from app.activities.extract_metadata import (
    MIN_TEXT_CHARS,
    ExtractMetadataRequest,
    _clear_absent_fields,
    extract_metadata_with_llm,
)
from app.schemas.metadata_suggestions import ExtractedMetadata, MetadataSuggestions
from app.workflows.specs import WorkflowContext

SOURCE = (
    "Deep Learning for Metadata Extraction\n\n"
    "Jane Doe, A. van der Berg\n\n"
    "Abstract: We present a method for extracting bibliographic metadata "
    "from scholarly PDFs using large language models.\n\n"
    "https://doi.org/10.1234/example.5678"
)


@pytest.mark.parametrize(
    ("field", "value", "kept"),
    [
        # title: verbatim substring is kept; a fabricated title is nulled
        ("title", "Deep Learning for Metadata Extraction", True),
        ("title", "A Concise Title Describing the Work", False),
        # description: near-verbatim (above 0.80 coverage) kept; invented nulled
        (
            "description",
            "We present a method for extracting bibliographic metadata "
            "from scholarly PDFs using large language models.",
            True,
        ),
        (
            "description",
            "A short summary of the document's purpose and findings.",
            False,
        ),
    ],
)
def test_null_absent_text_fields(field, value, kept):
    """Title/description present in the source survive; fabricated ones are nulled."""
    output = ExtractedMetadata(**{field: value})
    _clear_absent_fields(output, SOURCE)
    assert getattr(output, field) == (value if kept else None)


@pytest.mark.parametrize(
    ("doi", "kept"),
    [
        ("10.1234/example.5678", True),  # bare form present in the URL in text
        ("https://doi.org/10.1234/example.5678", True),  # normalized before match
        (
            "doi:10.1234/EXAMPLE.5678",
            True,
        ),  # prefix stripped, matched case-insensitively
        ("10.9999/not.in.text", False),  # fabricated DOI nulled
        ("not-a-doi", False),  # non-DOI cleared (would crash normalize_doi unguarded)
    ],
)
def test_null_absent_doi(doi, kept):
    """DOIs present in the text (bare or via URL) are kept; absent ones nulled."""
    output = ExtractedMetadata(doi=doi)
    _clear_absent_fields(output, SOURCE)
    assert (output.doi == doi) if kept else (output.doi is None)


def test_null_absent_wrapped_doi_matches_across_linebreak():
    """A DOI wrapped across a line break still matches (whitespace-insensitive)."""
    output = ExtractedMetadata(doi="10.1234/example.5678")
    _clear_absent_fields(output, "identifier 10.1234/\nexample.5678 end")
    assert output.doi == "10.1234/example.5678"


def test_null_absent_leaves_empty_fields_untouched():
    """The presence check never invents values for fields the model left empty."""
    output = ExtractedMetadata()
    _clear_absent_fields(output, SOURCE)
    assert output.title is None
    assert output.description is None
    assert output.doi is None


@pytest.mark.parametrize("text", ["", "   \n\t ", "x" * (MIN_TEXT_CHARS - 1)])
def test_skip_empty_returns_no_suggestions(text):
    """Below the char threshold the activity returns empty metadata, no LLM call."""
    # No settings/agent are required on this path; a real LLM would fabricate here.
    request = ExtractMetadataRequest(text=text)
    context = WorkflowContext(workflow_id="wf-1", tenant_id="t-1")
    result = asyncio.run(extract_metadata_with_llm(request, context))
    raw_suggestions = MetadataSuggestions.from_extracted(result)
    assert raw_suggestions.suggestions == []
