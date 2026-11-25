# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Typed metadata suggestions returned by the workflow."""

# from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FunderEnum(str, Enum):
    """Name and acronym for known funding organizations."""

    NIH = "National Institutes of Health"
    NSF = "U.S. National Science Foundation"
    UKRI = "UK Research and Innovation"
    FNS = "Swiss National Science Foundation"
    EC = "European Commission"
    FCT = "Foundation for Science and Technology"
    NWO = "Dutch Research Council"
    NHMRC = "National Health and Medical Research Council"
    ANR = "National Agency for Research"
    ARC = "Australian Research Council"


class ExtractedMetadata(BaseModel):
    """Flat schema the LLM fills, converted to ``MetadataSuggestions``.

    Creators are parallel lists, not nested objects. gpt-oss-20b fills flat
    top-level lists in a tool call but drops a field nested under each creator,
    so a per-creator ``orcid`` gets lost. ``creator_orcids[i]`` and
    ``creator_affiliations[i]`` belong to ``creators[i]``.
    """

    title: str | None = Field(
        default=None,
        description="Document title",
        examples=["A Concise Title Describing the Work"],
    )
    description: str | None = Field(
        default=None,
        description=(
            "Abstract or executive summary of the document, copied word-for-word, "
            "complete and unchanged; never paraphrase, shorten, or write a new "
            "summary. Null if the document has no abstract or summary."
        ),
        examples=["The abstract of the document, word for word."],
    )
    creators: list[str] = Field(
        default_factory=list,
        description=(
            "Creator full names in '<family>, <given>' format, in order. Include "
            "every author named in the document; never truncate the list or use "
            "et al."
        ),
        examples=[["Doe, Jane", "van der Berg, A."]],
    )
    creator_orcids: list[str] = Field(
        default_factory=list,
        description=(
            "ORCID iD per creator, parallel to `creators` so creator_orcids[i] "
            "is the ORCID of creators[i]; empty string when an author has none. "
            "Bare 16-digit form (four groups of four, last may be 'X'), no URL."
        ),
        examples=[["0000-0002-1111-1115", ""]],
    )
    creator_affiliations: list[list[str]] = Field(
        default_factory=list,
        description=(
            "Affiliations per creator, parallel to `creators` so "
            "creator_affiliations[i] lists every affiliation of creators[i]; empty "
            "list when unknown. Affiliations are often marked with numbers or "
            "symbols after author names; resolve each of an author's markers to "
            "its affiliation, e.g. 'Smith1,2' gets affiliations 1 and 2. Copy each "
            "affiliation as written, including any department or institute, but "
            "leave out the marker and any street address, city, postal code, or "
            "country: 'CERN, Geneva, Switzerland' -> 'CERN'."
        ),
        examples=[
            [["CERN", "University of Oxford"], ["Department of Physics, ETH Zurich"]]
        ],
    )
    doi: str | None = Field(
        default=None,
        description="The Digital Object Identifier, as a bare DOI without a URL prefix",
        examples=["10.1234/example.5678"],
    )
    publication_date: str | None = Field(
        default=None,
        description=(
            "Publication date in ISO 8601, at the precision known: 'YYYY-MM-DD', "
            "'YYYY-MM', or 'YYYY'. Normalize written dates: '17 July 2023' -> "
            "'2023-07-17', 'July 2023' -> '2023-07', '2023' -> '2023'."
        ),
        examples=["2014-07-17", "2014-07", "2014"],
    )
    license: list[str] = Field(
        default_factory=list,
        description=(
            "SPDX id of the license. Might be preceded by 'licensed under'. Translate "
            "license names to the SPDX id. For example, 'Creative Commons Attribution "
            "4.0 International' should be returned as 'cc-by-4.0'."
        ),
        examples=[["mit", "apache-2.0", "cc-by-4.0", "gpl-3.0-only"]],
    )
    copyright: str | None = Field(
        default=None,
        description=(
            "Copyright statement. Often follows '© Copyright' and might include a "
            "year, which should also be returned. Do not include the © symbol, the "
            "word 'Copyright' itself, or any '(cid:N)' sequences."
        ),
        examples=["2025 CERN", "The Authors", "2020 Jane Doe", "The Authors 1999"],
    )
    funding_titles: list[str] = Field(
        default_factory=list,
        description=(
            "Name of funding awards or projects financing the research. Strip "
            "any surrounding phrases ('funded by', 'funded under', 'with support "
            "from', etc.) and trailing punctuation. Prefer this field over `funder` "
            "unless only a funding organization with no specific project is available."
        ),
        examples=[["SCOAP3", "ObsSea4Clim", "European Citizen Science (ECS)"]],
    )
    funding_numbers: list[str] = Field(
        default_factory=list,
        description=(
            "List of funding numbers or grant agreements, parallel to `funding_titles` "
            "so funding_numbers[i] is the grant agreement of funding_titles[i]; empty "
            "string if there is no grant agreement stated. Might be preceded by "
            "expressions such as 'grant agreement' or 'GA nr.' or 'project no.'."
        ),
        examples=[["101058509", "2410342", "5IK2BX005715-03"]],
    )
    funding_funders: list[Optional[FunderEnum]] = Field(
        default_factory=list,
        description=(
            "Funding organization, parallel to `funding_titles` so funding_funder"
            "[i] is the funder of funding_titles[i]. Return the full name when the "
            "funder matches by name or acronym: NIH = National Institutes of Health, "
            "NSF = U.S. National Science Foundation, UKRI = UK Research and Innovation,"
            " FNS = Swiss National Science Foundation, EC = European Commission. FCT = "
            "Foundation for Science and Technology, NWO = Dutch Research Council, "
            "NHMRC = National Health and Medical Research Council, ANR = National "
            "Agency for Research, ARC = Australian Research Council; or None."
        ),
        examples=[["European Commission", "U.S. National Science Foundation", None]],
    )

    @staticmethod
    def at(values: list[str], i: int) -> str:
        """Return the i-th parallel value, or '' when the list is shorter."""
        return values[i] if i < len(values) else ""

    @staticmethod
    def affiliations_at(values: list[list[str]], i: int) -> list[str]:
        """Return the non-empty i-th creator's affiliations, or [] if missing."""
        if i >= len(values):
            return []
        return [a.strip() for a in values[i] if a and a.strip()]
