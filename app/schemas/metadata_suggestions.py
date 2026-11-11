# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Typed metadata suggestions returned by the workflow."""

from difflib import SequenceMatcher

# from __future__ import annotations
from typing import Annotated, Literal

from idutils.normalizers import normalize_orcid
from idutils.validators import is_orcid
from pydantic import BaseModel, Field, field_validator

from .extracted_metadata import ExtractedMetadata
from .resolved_fields import ResolvedFunding, ResolvedLicense


class Creator(BaseModel):
    """A structured creator/author."""

    name: str = Field(
        description="Full name in '<family>, <given>' format",
        examples=["Doe, Jane", "van der Berg, A."],
    )
    affiliation: str | None = Field(
        default=None,
        description="Institution or organization the creator is affiliated with",
        examples=["CERN", "University of Cambridge"],
    )
    orcid: str | None = Field(
        default=None,
        description=(
            "ORCID identifier as the bare 16-digit ID (four groups of four, "
            "final character may be 'X'), without the orcid.org URL prefix"
        ),
        examples=["0000-0002-1111-1115", "0000-0002-6789-012X"],
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        """Normalize names to the canonical 'Family, Given' format."""
        cleaned = " ".join(v.split()).strip()
        if not cleaned:
            return cleaned
        if "," in cleaned:
            return cleaned
        parts = cleaned.split(" ")
        if len(parts) == 1:
            return f"{parts[0]},"
        family = parts[-1]
        given = " ".join(parts[:-1])
        return f"{family}, {given}"

    def matches(self, other: Creator) -> bool:
        """Logic to pair two creator entries."""
        name_self = " ".join(self.name.replace(",", "").split()).casefold()
        name_other = " ".join(other.name.replace(",", "").split()).casefold()
        return (
            name_self == name_other
            or SequenceMatcher(None, name_self, name_other).ratio() >= 0.85
        )

    def normalize_for_comparison(self, matched=None) -> dict:
        """Return the dictionary with name, affiliation, and ORCID."""
        return {"name": self.name, "orcid": self.orcid, "affiliation": self.affiliation}


class TitleSuggestion(BaseModel):
    """Suggestion for `title`."""

    field: Literal["title"] = "title"
    value: str


class DescriptionSuggestion(BaseModel):
    """Suggestion for `description` (abstract)."""

    field: Literal["description"] = "description"
    value: str


class CreatorsSuggestion(BaseModel):
    """Suggestion for `creators`."""

    field: Literal["creators"] = "creators"
    value: list[Creator]

    @field_validator("value")
    @classmethod
    def filter_empty_names(cls, v: list[Creator]) -> list[Creator]:
        """Filter out creators with empty names."""
        return [c for c in v if c.name]


class DoiSuggestion(BaseModel):
    """Suggestion for `doi`."""

    field: Literal["doi"] = "doi"
    value: str


class PublicationDateSuggestion(BaseModel):
    """Suggestion for `publication_date` ."""

    field: Literal["publication_date"] = "publication_date"
    value: str

    @field_validator("value")
    @classmethod
    def normalize_publication_date(cls, v: str) -> str:
        """Collapse whitespace; ISO 8601 date, year-month, and year are all kept."""
        return " ".join(v.split()).strip()


class LicenseSuggestion(BaseModel):
    """Suggestion for `license` ."""

    field: Literal["license"] = "license"
    value: list[ResolvedLicense]


class CopyrightSuggestion(BaseModel):
    """Suggestion for `copyright` ."""

    field: Literal["copyright"] = "copyright"
    value: str


class FundingSuggestion(BaseModel):
    """Suggestion for `funding` (awards/grants)."""

    field: Literal["funding"] = "funding"
    value: list[ResolvedFunding]


MetadataSuggestion = Annotated[
    TitleSuggestion
    | DescriptionSuggestion
    | CreatorsSuggestion
    | DoiSuggestion
    | PublicationDateSuggestion
    | LicenseSuggestion
    | CopyrightSuggestion
    | FundingSuggestion,
    Field(discriminator="field"),
]


class MetadataSuggestions(BaseModel):
    """Container for all metadata suggestions from a workflow run."""

    suggestions: list[MetadataSuggestion]

    @classmethod
    def from_extracted(cls, metadata: ExtractedMetadata) -> MetadataSuggestions:
        """Build suggestions from extracted metadata."""
        suggestions: list[MetadataSuggestion] = []
        if metadata.title:
            suggestions.append(TitleSuggestion(value=metadata.title))
        if metadata.description:
            suggestions.append(DescriptionSuggestion(value=metadata.description))
        if metadata.creators:
            value = []
            for i, name in enumerate(metadata.creators):
                # Validate/normalize here, not on the LLM output schema, where a
                # fed-back error would make the model invent a valid-looking fake.
                orcid = metadata.at(metadata.creator_orcids, i)
                orcid = normalize_orcid(orcid).upper() if is_orcid(orcid) else None
                value.append(
                    Creator(
                        name=name,
                        orcid=orcid,
                        affiliation=(
                            metadata.at(metadata.creator_affiliations, i) or None
                        ),
                    )
                )
            creators = CreatorsSuggestion(value=value)
            if creators.value:
                suggestions.append(creators)
        if metadata.doi:
            suggestions.append(DoiSuggestion(value=metadata.doi))
        if metadata.publication_date:
            suggestions.append(
                PublicationDateSuggestion(value=metadata.publication_date)
            )
        if metadata.copyright:
            suggestions.append(CopyrightSuggestion(value=metadata.copyright))
        return cls(suggestions=suggestions)
