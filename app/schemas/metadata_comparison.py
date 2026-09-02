# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Metadata comparison returned by the workflow."""

from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.extracted_metadata import FUNDER_NAMES_BY_ROR_ID
from app.schemas.metadata_suggestions import Creator
from app.schemas.resolved_fields import ResolvedFunding, ResolvedLicense

SCALAR_FIELDS = ("title", "description", "publication_date", "doi", "copyright")
LIST_FIELDS = ("creators", "license", "funding")

#####################
#  Current fields   #
#####################


class CurrentFunder(BaseModel):
    """Funder entry from deposit metadata."""

    id: str | None = None
    name: str | None = None


class CurrentAward(BaseModel):
    """Award entry from deposit metadata."""

    id: str | None = None
    number: str | None = None
    title: dict[str, str] | None = None  # e.g. {"en": "..."}


class CurrentFunding(BaseModel):
    """Funding entry from deposit metadata: funder and/or award."""

    funder: CurrentFunder | None = None
    award: CurrentAward | None = None

    def matches(self, other: ResolvedFunding) -> bool:
        """Logic to pair two funding entries."""
        funder_matches = False
        if self.funder and other.funder:
            funder_matches = self.funder.id == other.funder.id
        if not (self.award and other.award):
            return funder_matches

        award_matches = False
        if self.award and other.award:
            if self.award.id and self.award.id == other.award.id:
                award_matches = True
            elif self.award.number == other.award.number:
                award_matches = True
            elif self.award.title and other.award.title:
                award_en = self.award.title.get("en", "")
                if (
                    SequenceMatcher(
                        None, award_en.casefold(), other.award.title.casefold()
                    ).ratio()
                    >= 0.85
                ):
                    award_matches = True

        return funder_matches and award_matches

    def normalize_for_comparison(self, matched: ResolvedFunding | None = None) -> dict:
        """Normalize for comparisons. Borrows the resolved award title on a match."""
        normalized = {}
        if self.funder:
            normalized["funder_id"] = self.funder.id
            normalized["funder_name"] = self.funder.name or (
                FUNDER_NAMES_BY_ROR_ID.get(self.funder.id) if self.funder.id else None
            )
        if self.award:
            for k in self.award.model_dump().keys():
                normalized["award_" + k] = getattr(self.award, k)
            # Title comes from the matched suggested award
            if matched and matched.award and matched.award.title:
                normalized["award_title"] = matched.award.title
            # Multilanguage dict
            elif isinstance(normalized.get("award_title"), dict):
                title = normalized["award_title"]
                normalized["award_title"] = title.get("en") or next(
                    iter(title.values()), None
                )
        return normalized


class CurrentMetadata(BaseModel):
    """Deposit metadata."""

    title: str = ""
    description: str = ""
    creators: list[Creator] = Field(default_factory=list)
    publication_date: str = ""
    doi: str = ""
    license: list[ResolvedLicense] = Field(default_factory=list)
    copyright: str = ""
    funding: list[CurrentFunding] = Field(default_factory=list)


#####################
# Comparison fields #
#####################


class MetadataComparison(BaseModel):
    """Field comparison."""

    field: Literal[
        "title",
        "description",
        "creators",
        "doi",
        "publication_date",
        "license",
        "copyright",
        "funding",
    ]
    rationale: str
    suggested: str | list[dict | None] | None = None
    current: str | list[dict | None] | None = None


class MetadataComparisons(BaseModel):
    """Container for all metadata comparisons from a workflow run."""

    comparisons: list[MetadataComparison]
    describes_file: bool
    decision: str


class ComparedMetadata(BaseModel):
    """Flat schema the LLM fills, converted to ``MetadataComparisons``."""

    title: str | None = Field(
        default=None,
        description="Correctness of the field `Title`",
        examples=[
            "The title contains a typo in the word 'Weather'",
            "The suggested title and the current title are the same",
        ],
    )
    description: str | None = Field(
        default=None,
        description="Correctness of the field `Description`. Ignore html tags.",
        examples=["The abstract paraphrases the original abstract"],
    )
    creators: str | None = Field(
        default=None,
        description=(
            "Correctness of the field `Creators`. Take into consideration the name, "
            "ORCID and affiliation."
        ),
        examples=[
            "Missing author van der Berg, A.",
            "Author Doe, Jane is missing ORCID 0000-0002-1111-1115",
            "Affiliation does not match for author Doe, John",
        ],
    )
    doi: str | None = Field(
        default=None,
        description="Correctness of The Digital Object Identifier, as a bare DOI "
        "without a URL prefix",
        examples=[
            "DOI matches the one in the suggestions",
            "Missing DOI.",
        ],
    )
    publication_date: str | None = Field(
        default=None,
        description=(
            "Whether publication date matches suggested publication date. "
            "If suggested date's precision is different from the current date's "
            "precision, indicate that."
        ),
        examples=["Document does not indicate day, only 2014-07"],
    )
    license: str | None = Field(
        default=None,
        description="Whether the current `License` matches the suggested, based on the "
        "id and name.",
        examples=["License `MIT` does not match license `Apache 2.0` in the text"],
    )
    copyright: str | None = Field(
        default=None,
        description="Correctness of `Copyright` field.",
        examples=["Copyright matches", "Missing year in copyright"],
    )
    funding: str | None = Field(
        default=None,
        description=(
            "Whether the current `funding` recorded on the deposit matches the funding "
            "found in the document. Having the same funder (unless it is null) is a "
            "necessary but not sufficient criteria for matching awards. "
        ),
        examples=[
            "The award matches the one found in the document",
            "The award titles are similar, but the numbers do not match",
            "The document has a European Commission grant but there is no current "
            "award number in the deposit",
        ],
    )
    describes_file: bool = Field(
        description="Whether the current fields describes the underlying file"
    )
    decision: str = Field(description="Explanation of the describes_file decision")

    def to_comparisons(self, pairs: dict[str, dict]) -> MetadataComparisons:
        """Build the typed comparisons, dropping null/empty fields."""

        def get_clean_values(
            entry: dict[str, str | None] | None,
        ) -> dict[str, str] | None:
            if not entry:
                return None
            result = {}
            for key in entry.keys():
                if value := entry[key]:
                    result[key] = value
            return result

        comparisons: list[MetadataComparison] = []
        for field in SCALAR_FIELDS:
            if rationale := getattr(self, field):
                pair = pairs[field]
                comparisons.append(
                    MetadataComparison(
                        field=field,
                        rationale=rationale,
                        suggested=pair.get("suggested"),
                        current=pair.get("current"),
                    )
                )

        for field in LIST_FIELDS:
            if rationale := getattr(self, field):
                field_list = pairs[field]
                comparisons.append(
                    MetadataComparison(
                        field=field,
                        rationale=rationale,
                        suggested=[
                            get_clean_values(x.get("suggested")) for x in field_list
                        ],
                        current=[
                            get_clean_values(x.get("current")) for x in field_list
                        ],
                    )
                )

        return MetadataComparisons(
            comparisons=comparisons,
            describes_file=self.describes_file,
            decision=self.decision,
        )
