# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the compare_metadata activity."""

import asyncio
import json

import pytest

from app.activities.compare_metadata import (
    CompareMetadataRequest,
    _align,
    _build_pairs,
    compare_metadata_with_llm,
)
from app.schemas.metadata_comparison import (
    ComparedMetadata,
    CurrentAward,
    CurrentFunder,
    CurrentFunding,
    CurrentMetadata,
)
from app.schemas.metadata_suggestions import (
    Creator,
    CreatorsSuggestion,
    DescriptionSuggestion,
    DoiSuggestion,
    MetadataSuggestions,
    PublicationDateSuggestion,
    TitleSuggestion,
)
from app.schemas.resolved_fields import (
    ResolvedAward,
    ResolvedFunder,
    ResolvedFunding,
    ResolvedLicense,
)
from app.workflows.specs import WorkflowContext

EC_ROR_ID = "00k4n6c32"
NIH_ROR_ID = "01cwqze88"
NSF_ROR_ID = "021nxhr62"


def test_align_no_match():
    """On no match, two pairs are created."""
    suggested = [Creator(name="Doe, Jane")]
    current = [Creator(name="Poppins, Mary")]

    pairs = _align(suggested, current)

    assert pairs == [
        {
            "suggested": None,
            "current": {
                "name": "Poppins, Mary",
                "orcid": None,
                "affiliation": None,
            },
        },
        {
            "suggested": {
                "name": "Doe, Jane",
                "orcid": None,
                "affiliation": None,
            },
            "current": None,
        },
    ]


def test_align_none():
    """If one of the metadata sets does not have a field, pair is built with None."""
    suggested = [Creator(name="Doe, Jane")]

    assert _align(suggested, []) == [
        {
            "suggested": {
                "name": "Doe, Jane",
                "orcid": None,
                "affiliation": None,
            },
            "current": None,
        }
    ]


def test_align_license_id():
    """Licenses match by id."""
    suggested = [
        ResolvedLicense(
            id="cc-by-4.0", title="Creative Commons Attribution 4.0 International"
        )
    ]
    current = [ResolvedLicense(id="cc-by-4.0")]

    # Matches, so one pair is created, and the current title is filled in
    assert _align(suggested, current) == [
        {
            "suggested": {
                "id": "cc-by-4.0",
                "title": "Creative Commons Attribution 4.0 International",
            },
            "current": {
                "id": "cc-by-4.0",
                "title": "Creative Commons Attribution 4.0 International",
            },
        }
    ]


@pytest.mark.parametrize(
    "title",
    [
        "Creative Commons Attribution 4.0 International",
        "Creative Commons Attribution 4.0",
    ],
)
def test_align_license_name(title):
    """Licenses match by a (near-)identical title when the id differs."""
    suggested = [
        ResolvedLicense(
            id="cc-by-4.0", title="Creative Commons Attribution 4.0 International"
        )
    ]
    current = [ResolvedLicense(id="", title=title)]

    # Matches, so one pair is created, and the current title is retained
    assert _align(suggested, current) == [
        {
            "suggested": {
                "id": "cc-by-4.0",
                "title": "Creative Commons Attribution 4.0 International",
            },
            "current": {
                "id": "",
                "title": title,
            },
        }
    ]


def test_align_funder_name_on_match():
    """A funder with only an id gets its name filled in on a match."""
    suggested = [
        ResolvedFunding(funder=ResolvedFunder(id=EC_ROR_ID, name="European Commission"))
    ]
    current = [CurrentFunding(funder=CurrentFunder(id=EC_ROR_ID, name=None))]

    assert _align(suggested, current) == [
        {
            "suggested": {"funder_id": EC_ROR_ID, "funder_name": "European Commission"},
            "current": {"funder_id": EC_ROR_ID, "funder_name": "European Commission"},
        }
    ]


@pytest.mark.parametrize("title", [None, {"en": ""}, {"en": "Test"}, {"en": "SCOAP3"}])
def test_align_award_title_on_match(title):
    """A matched award gets the resolved award's title on match."""
    suggested = [
        ResolvedFunding(
            funder=ResolvedFunder(id=EC_ROR_ID, name="European Commission"),
            award=ResolvedAward(
                id=f"{EC_ROR_ID}::101166718", number="101166718", title="SCOAP3"
            ),
        )
    ]
    current = [
        CurrentFunding(
            funder=CurrentFunder(id=EC_ROR_ID, name=None),
            award=CurrentAward(number="101166718", title=title),
        )
    ]

    pairs = _align(suggested, current)

    assert len(pairs) == 1
    assert pairs[0]["suggested"]["award_title"] == "SCOAP3"
    # The multilingual dict is replaced by the plain resolved title on a match.
    assert pairs[0]["current"]["award_title"] == "SCOAP3"


@pytest.mark.parametrize(
    ("title_dict", "title"),
    [
        ({"fr": "Projet", "en": "Project"}, "Project"),
        ({"fr": "Projet", "es": "Projeto"}, "Projet"),
    ],
)
def test_align_multilingual_title_without_match(title_dict, title):
    """Without a match, the raw multilingual title is flattened.

    Uses 'en' if available, otherwise the first available language is used instead.
    """
    current = [
        CurrentFunding(
            funder=CurrentFunder(id=NIH_ROR_ID, name="National Institutes of Health"),
            award=CurrentAward(number="123", title=title_dict),
        )
    ]

    pairs = _align([], current)

    assert pairs == [
        {
            "suggested": None,
            "current": {
                "funder_id": NIH_ROR_ID,
                "funder_name": "National Institutes of Health",
                "award_id": None,
                "award_number": "123",
                "award_title": title,
            },
        }
    ]


def test_build_pairs_scalar_fields():
    """Correctly build pairs for scalar fields.

    A field present in both sets builds a pair; if it's only present in one
    set, builds a pair with None.
    """
    suggested = MetadataSuggestions(
        suggestions=[
            TitleSuggestion(value="Suggested Title"),
            DoiSuggestion(value="10.1234/example.5678"),
        ]
    )
    current = CurrentMetadata(title="Current Title")

    pairs = json.loads(_build_pairs(suggested, current))

    assert pairs == {
        "title": {"suggested": "Suggested Title", "current": "Current Title"},
        "doi": {"suggested": "10.1234/example.5678", "current": None},
    }


def test_build_pairs_aligns_list_fields():
    """List fields (e.g. creators) go through `_align`, not the scalar branch."""
    suggested = MetadataSuggestions(
        suggestions=[CreatorsSuggestion(value=[Creator(name="Doe, Jane")])]
    )
    current = CurrentMetadata(creators=[Creator(name="Doe, Jane")])

    pairs = json.loads(_build_pairs(suggested, current))

    assert pairs["creators"] == [
        {
            "suggested": {"name": "Doe, Jane", "orcid": None, "affiliation": None},
            "current": {"name": "Doe, Jane", "orcid": None, "affiliation": None},
        }
    ]


def test_no_suggested_metadata():
    """No suggested metadata returns empty comparisons, no LLM call."""
    request = CompareMetadataRequest(
        suggested_metadata=MetadataSuggestions(suggestions=[]),
        current_metadata=CurrentMetadata(title="Current Title"),
    )
    context = WorkflowContext(workflow_id="wf-1", tenant_id="t-1")
    result = asyncio.run(compare_metadata_with_llm(request, context))

    assert result.comparisons == []
    assert not result.describes_file


def test_to_comparisons():
    """MetadataComparisons is built correctly given a valid CompareMetadataRequest."""
    suggested_metadata = MetadataSuggestions(
        suggestions=[
            TitleSuggestion(value="A title that matches"),
            DescriptionSuggestion(
                value="We discuss the theoretical bases that underpin matching."
            ),
            CreatorsSuggestion(
                value=[
                    Creator(name="Frederik, R.", affiliation="CERN"),
                    Creator(name="Doe, S.", affiliation="CERN"),
                ]
            ),
            DoiSuggestion(value="10.1234/example.5678"),
            PublicationDateSuggestion(value="2014-07-17"),
        ]
    )

    current_metadata = CurrentMetadata(
        title="A title that matcches",  # contains a typo
        description="We discuss the theoretical basis that underpin matching.",
        creators=[Creator(name="Frederik, R")],
        publication_date="2014-07",
        doi="10.1234/example.5678",
        license=[ResolvedLicense(id="cc-by-4.0")],
        copyright="The Authors",
    )

    request = CompareMetadataRequest(
        suggested_metadata=suggested_metadata, current_metadata=current_metadata
    )
    pairs = _build_pairs(request.suggested_metadata, request.current_metadata)

    mocked_output = ComparedMetadata.model_validate(
        {
            "title": "The suggested title and the current title are the same except "
            "for a typo.",
            "description": "Both descriptions are essentially the same; minor wording "
            "differences ('bases' vs 'basis') can be ignored.",
            "creators": "Creator lists match; discrepancies are missing affiliation and"
            " one author not present in current; acceptable.",
            "doi": "DOI matches the one in the extraction.",
            "publication_date": "Suggested date '2014-07-17' is more precise than "
            "'2014-07' – the current date provides only year "
            "and month, but refers to the same document.",
            "license": "Suggested metadata missing license, current metadata specifies "
            "cc‑by‑4.0; acceptable missing in suggested.",
            "copyright": "Missing in suggested metadata, present as 'The Authors'.",
            "funding": None,
            "describes_file": True,
            "decision": "All provided metadata components either match or exhibit "
            "differences that are considered acceptable (missing fields in "
            "suggested or current), indicating that the current metadata "
            "describes the same underlying document.",
        }
    )

    result = mocked_output.to_comparisons(json.loads(pairs))
    # Scalar field: Title
    assert result.comparisons[0].model_dump() == {
        "field": "title",
        "rationale": "The suggested title and the current title are the same except "
        "for a typo.",
        "suggested": "A title that matches",
        "current": "A title that matcches",
    }

    # Scalar field present in only one metadata set: Copyright
    assert result.comparisons[4].model_dump() == {
        "field": "copyright",
        "rationale": "Missing in suggested metadata, present as 'The Authors'.",
        "suggested": None,
        "current": "The Authors",
    }

    # List field: Creators, with a None value in one of the metadata sets
    assert result.comparisons[5].model_dump() == {
        "field": "creators",
        "rationale": "Creator lists match; discrepancies are missing affiliation and "
        "one author not present in current; acceptable.",
        "suggested": [
            {"name": "Frederik, R.", "affiliation": "CERN"},
            {"name": "Doe, S.", "affiliation": "CERN"},
        ],
        "current": [{"name": "Frederik, R"}, None],
    }

    # 7 fields, empty field `funding` is dropped
    assert len(result.comparisons) == 7
    assert result.describes_file is True
    assert result.decision
