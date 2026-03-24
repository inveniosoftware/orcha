"""Typed metadata suggestions returned by the workflow."""

# from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class Creator(BaseModel):
    """A structured creator/author."""

    name: str = Field(
        description="Full name in '<family>, <given>' format",
        examples=["Smith, John"],
    )
    affiliation: str | None = None
    orcid: str | None = None

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
        """Apply normalization for publication dates."""
        cleaned = " ".join(v.split()).strip()
        # Keep existing canonical full dates.
        if len(cleaned) == 10 and cleaned[4] == "-" and cleaned[7] == "-":
            return cleaned
        # Convert YYYY-MM to YYYY.
        if len(cleaned) == 7 and cleaned[4] == "-":
            return cleaned[:4]
        # Keep year-only and unknown formats as-is.
        return cleaned


MetadataSuggestion = Annotated[
    TitleSuggestion
    | DescriptionSuggestion
    | CreatorsSuggestion
    | DoiSuggestion
    | PublicationDateSuggestion,
    Field(discriminator="field"),
]


class MetadataResult(BaseModel):
    """Container for all metadata suggestions from a workflow run."""

    suggestions: list[MetadataSuggestion]
