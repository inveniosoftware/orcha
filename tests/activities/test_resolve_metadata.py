# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the resolve_metadata activity.

Mocks the response from an invenio instance.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import Response

from app.activities.resolve_metadata import (
    _INVENIO_HEADERS,
    FUNDER_ROR_IDS,
    ResolveMetadataRequest,
    resolve_metadata_suggestions,
)
from app.config import get_settings
from app.schemas.extracted_metadata import ExtractedMetadata, FunderEnum
from app.schemas.metadata_suggestions import (
    DoiSuggestion,
    FundingSuggestion,
    LicenseSuggestion,
    TitleSuggestion,
)
from app.schemas.resolved_fields import (
    ResolvedAward,
    ResolvedFunder,
    ResolvedFunding,
    ResolvedLicense,
)

BASE_URL = "https://invenio.test"

LICENSES = {
    "cc-by-4.0": {
        "id": "cc-by-4.0",
        "title_l10n": "Creative Commons Attribution 4.0 International",
        "description_l10n": "The Creative Commons Attribution license.",
        "props": {
            "url": "https://creativecommons.org/licenses/by/4.0/legalcode",
        },
    },
    "mit": {
        "id": "mit",
        "title_l10n": "MIT License",
        "description_l10n": "A short and simple permissive license.",
        "props": {
            "url": "https://opensource.org/licenses/MIT",
        },
    },
}
FUNDERS = {
    "EC": {
        "id": "00k4n6c32",
        "name": "European Commission",
    },
    "NIH": {
        "id": "01cwqze88",
        "name": "National Institutes of Health",
    },
    "NSF": {
        "id": "021nxhr62",
        "name": "U.S. National Science Foundation",
    },
}
AWARDS = {
    "101166718": {
        "id": "00k4n6c32::101166718",
        "number": "101166718",
        "title_l10n": "A Title",
        "acronym": "TITLE",
        "funder": FUNDERS["EC"],
    },
    "TEST - Test Entry Standard Title": {
        "id": "01cwqze88::101010101",
        "number": "101010101",
        "title_l10n": "TEST - Test Entry Standard Title",
        "acronym": "TEST",
        "funder": FUNDERS["NIH"],
    },
    "Test_similar": {
        "id": "021nxhr62::100000000",
        "number": "100000000",
        "title_l10n": "ASTA - Another Similar Test Award",
        "acronym": "ASTA",
        "funder": FUNDERS["NSF"],
    },
}


async def mocked_response(url, *args, params: dict | None = None, **kwargs):
    """Returns the mocked response."""
    if "/api/vocabularies/licenses/" in url:
        license_id = url.rsplit("/", 1)[-1]
        if lic := LICENSES.get(license_id):
            return Response(200, json=lic)

    elif "/api/awards" in url and params:
        query = params["q"]
        if query.startswith("number"):
            number = query.rsplit(":", 1)[-1]
            if award := AWARDS.get(number):
                return Response(200, json={"hits": {"hits": [award]}})
        else:
            awards = [AWARDS[key] for key in AWARDS if query in key]
            if awards:
                return Response(200, json={"hits": {"hits": awards}})
    return Response(400)


@pytest.fixture(autouse=True)
def base_url(monkeypatch):
    """Pin INVENIO_BASE_URL for tests."""
    monkeypatch.setenv("INVENIO_BASE_URL", BASE_URL)
    get_settings.cache_clear()


@patch("app.activities.resolve_metadata.http_verify", return_value=True)
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def resolve(mock_get, mock_verify, **metadata):
    """Resolve metadata based on mocked response."""
    request = ResolveMetadataRequest(metadata=ExtractedMetadata(**metadata))
    mock_get.side_effect = mocked_response
    result = await resolve_metadata_suggestions(request)
    return result, mock_get


def test_funder_ror_ids_cover_all_funders():
    """Every FunderEnum member must have a ROR id, or its funder never resolves."""
    assert set(FUNDER_ROR_IDS) == set(FunderEnum)


@pytest.mark.asyncio
async def test_plain_fields_need_no_requests():
    """With no license or funding, nothing is resolved and nothing is called."""
    result, mock_get = await resolve(title="A Title", doi="10.1234/example.5678")
    suggestions = result.suggestions
    assert suggestions == [
        TitleSuggestion(field="title", value="A Title"),
        DoiSuggestion(field="doi", value="10.1234/example.5678"),
    ]
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_license_resolved():
    """A known license comes back with its title, description, and link."""
    result, mock_get = await resolve(title="A Title", license=["cc-by-4.0"])
    suggestions = result.suggestions

    assert suggestions == [
        TitleSuggestion(field="title", value="A Title"),
        LicenseSuggestion(
            field="license",
            value=[
                ResolvedLicense(
                    id="cc-by-4.0",
                    title="Creative Commons Attribution 4.0 International",
                    description="The Creative Commons Attribution license.",
                    link="https://creativecommons.org/licenses/by/4.0/legalcode",
                )
            ],
        ),
    ]
    mock_get.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "license_ids",
    [["cc-by-4.0", "mit"], ["CC-BY-4.0", "MIT"]],
    ids=["lowercase", "mixed_case"],
)
async def test_multiple_license_ids(license_ids):
    """Several SPDX ids resolve in order, and are looked up in lowercase."""
    result, mock_get = await resolve(license=license_ids)
    suggestions = result.suggestions

    assert suggestions == [
        LicenseSuggestion(
            field="license",
            value=[
                ResolvedLicense(
                    id="cc-by-4.0",
                    title="Creative Commons Attribution 4.0 International",
                    description="The Creative Commons Attribution license.",
                    link="https://creativecommons.org/licenses/by/4.0/legalcode",
                ),
                ResolvedLicense(
                    id="mit",
                    title="MIT License",
                    description="A short and simple permissive license.",
                    link="https://opensource.org/licenses/MIT",
                ),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_unknown_license_falls_back_to_id():
    """A 404 keeps the id and leaves the rest of the license empty."""
    result, mock_get = await resolve(license=["not-a-license"])
    suggestions = result.suggestions

    assert suggestions == [
        LicenseSuggestion(field="license", value=[ResolvedLicense(id="not-a-license")])
    ]
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_award_resolved_by_number():
    """A grant number match yields the award and the funder from the hit."""
    result, mock_get = await resolve(
        funding_titles=["Wrong title"],
        funding_numbers=["101166718"],
        funding_funders=[],
    )
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(id="00k4n6c32", name="European Commission"),
                    award=ResolvedAward(
                        id="00k4n6c32::101166718", number="101166718", title="A Title"
                    ),
                )
            ],
        )
    ]
    mock_get.assert_called_once_with(
        f"{BASE_URL}/api/awards",
        params={"q": "number:101166718", "size": 1},
        headers=_INVENIO_HEADERS,
    )


@pytest.mark.asyncio
async def test_known_funder_scopes_the_award_search():
    """Without a known funder the award search is not filtered by funder."""
    result, mock_get = await resolve(
        funding_titles=[],
        funding_numbers=["101166718"],
        funding_funders=["European Commission"],
    )
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(id="00k4n6c32", name="European Commission"),
                    award=ResolvedAward(
                        id="00k4n6c32::101166718", number="101166718", title="A Title"
                    ),
                )
            ],
        )
    ]
    mock_get.assert_called_once_with(
        f"{BASE_URL}/api/awards",
        params={"q": "number:101166718", "funders": "00k4n6c32", "size": 1},
        headers=_INVENIO_HEADERS,
    )


@pytest.mark.asyncio
async def test_award_resolved_by_title_when_number_misses():
    """A number with no match falls through to a unique title match."""
    result, mock_get = await resolve(
        funding_titles=["TEST - Test Entry Standard Title"],
        funding_numbers=["fakenumber"],
    )
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(
                        id="01cwqze88", name="National Institutes of Health"
                    ),
                    award=ResolvedAward(
                        id="01cwqze88::101010101",
                        number="101010101",
                        title="TEST - Test Entry Standard Title",
                    ),
                )
            ],
        )
    ]


@pytest.mark.asyncio
async def test_ambiguous_title_rejected():
    """Several title matches whose acronym is absent keep a custom award."""
    result, mock_get = await resolve(funding_titles=["Test"])
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=None,
                    award=ResolvedAward(id=None, number=None, title="Test"),
                )
            ],
        )
    ]


@pytest.mark.asyncio
async def test_ambiguous_title_accepted_when_acronym_matches():
    """Several matches are disambiguated by the acronym appearing in the title."""
    result, mock_get = await resolve(funding_titles=["TEST"])
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(
                        id="01cwqze88", name="National Institutes of Health"
                    ),
                    award=ResolvedAward(
                        id="01cwqze88::101010101",
                        number="101010101",
                        title="TEST - Test Entry Standard Title",
                    ),
                )
            ],
        )
    ]


@pytest.mark.asyncio
async def test_no_match_keeps_number_and_title_as_custom_award():
    """When nothing resolves, the extracted number and title are kept as-is."""
    result, mock_get = await resolve(
        funding_titles=["Some Project"],
        funding_numbers=["12345"],
        funding_funders=["National Institutes of Health"],
    )
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(
                        id="01cwqze88", name="National Institutes of Health"
                    ),
                    award=ResolvedAward(id=None, number="12345", title="Some Project"),
                )
            ],
        )
    ]


@pytest.mark.asyncio
async def test_funder_only():
    """A funder with no award produces a funder and no award."""
    result, mock_get = await resolve(
        funding_funders=["U.S. National Science Foundation"]
    )
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(
                        id="021nxhr62", name="U.S. National Science Foundation"
                    ),
                    award=None,
                )
            ],
        )
    ]


@pytest.mark.asyncio
async def test_parallel_lists_of_unequal_length():
    """Entries are built for the longest list; missing positions read as empty."""
    result, mock_get = await resolve(
        funding_titles=["A Title", "Second Project"],
        funding_numbers=["101166718"],
        funding_funders=["European Commission"],
    )
    suggestions = result.suggestions

    assert suggestions == [
        FundingSuggestion(
            field="funding",
            value=[
                ResolvedFunding(
                    funder=ResolvedFunder(id="00k4n6c32", name="European Commission"),
                    award=ResolvedAward(
                        id="00k4n6c32::101166718", number="101166718", title="A Title"
                    ),
                ),
                ResolvedFunding(
                    funder=None,
                    award=ResolvedAward(id=None, number=None, title="Second Project"),
                ),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_no_resolved_funding():
    """Do not return a ResolvedFunding when both funder and award are None."""
    result, mock_get = await resolve(
        license=["mit"],
        funding_titles=[""],
        funding_numbers=[""],
    )
    suggestions = result.suggestions

    assert suggestions == [
        LicenseSuggestion(
            field="license",
            value=[
                ResolvedLicense(
                    id="mit",
                    title="MIT License",
                    description="A short and simple permissive license.",
                    link="https://opensource.org/licenses/MIT",
                ),
            ],
        ),
    ]
