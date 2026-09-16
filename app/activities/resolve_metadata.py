# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Activity that resolves funders, awards, and licenses via Invenio vocabularies."""

import asyncio
import json
import logging
from datetime import timedelta

import httpx
from pydantic import BaseModel, Field
from temporalio import activity
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from app.activities.utils import http_verify
from app.config import get_settings
from app.schemas.extracted_metadata import FUNDER_ROR_IDS, ExtractedMetadata, FunderEnum
from app.schemas.metadata_suggestions import (
    FundingSuggestion,
    LicenseSuggestion,
    MetadataSuggestions,
)
from app.schemas.resolved_fields import (
    ResolvedAward,
    ResolvedFunder,
    ResolvedFunding,
    ResolvedLicense,
)

logger = logging.getLogger(__name__)

RESOLVE_METADATA_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

_INVENIO_HEADERS = {"Accept": "application/vnd.inveniordm.v1+json"}


class ResolveMetadataRequest(BaseModel):
    """Request to resolve and generate metadata suggestions from raw metadata."""

    metadata: ExtractedMetadata = Field(description="Raw metadata to resolve")


def _log_resolve_error(
    field: str, instance: str, error: httpx.HTTPError | json.JSONDecodeError
) -> None:
    reason = (
        "request failed"
        if isinstance(error, httpx.HTTPError)
        else "invalid JSON response"
    )
    logger.error(f"Error resolving {field} {instance} ({reason})", exc_info=error)


async def _resolve_license(
    client: httpx.AsyncClient, license_id: str, base_url: str
) -> ResolvedLicense:
    try:
        response = await client.get(
            f"{base_url}/api/vocabularies/licenses/{license_id}",
            headers=_INVENIO_HEADERS,
        )
        if response.is_success:
            data = response.json()
            return ResolvedLicense(
                id=data["id"],
                title=data.get("title_l10n"),
                description=data.get("description_l10n"),
                link=data.get("props", {}).get("url"),
            )
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        _log_resolve_error("license", license_id, e)
    return ResolvedLicense(id=license_id)


async def _resolve_award_by_number(
    client: httpx.AsyncClient,
    number: str,
    funder_id: str | None,
    base_url: str,
) -> tuple[None, None] | tuple[ResolvedAward, ResolvedFunder]:
    try:
        params: dict = {"q": f"number:{number}", "size": 1}
        if funder_id:
            params["funders"] = funder_id
        resp = await client.get(
            f"{base_url}/api/awards",
            params=params,
            headers=_INVENIO_HEADERS,
        )
        if not resp.is_success:
            return None, None
        hits = resp.json().get("hits", {}).get("hits", [])
        if not hits:
            return None, None
        hit = hits[0]
        return ResolvedAward(
            id=hit.get("id"),
            number=hit.get("number"),
            title=hit.get("title_l10n"),
        ), ResolvedFunder(id=hit["funder"]["id"], name=hit["funder"]["name"])
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        _log_resolve_error("award by number", number, e)
    return None, None


async def _resolve_award_by_title(
    client: httpx.AsyncClient,
    title: str,
    funder_id: str | None,
    base_url: str,
) -> tuple[None, None] | tuple[ResolvedAward, ResolvedFunder]:
    try:
        params: dict = {"q": title, "size": 2, "sort": "bestmatch"}
        if funder_id:
            params["funders"] = funder_id
        resp = await client.get(
            f"{base_url}/api/awards",
            params=params,
            headers=_INVENIO_HEADERS,
        )
        if not resp.is_success:
            return None, None
        hits = resp.json().get("hits", {}).get("hits", [])
        # Use the result when unambiguous: 1 match or acronym is found in the 1st result
        if len(hits) != 1:
            if (
                not hits
                or not (acronym := hits[0].get("acronym"))
                or acronym not in title
            ):
                return None, None
        hit = hits[0]
        return ResolvedAward(
            id=hit.get("id"),
            number=hit.get("number"),
            title=hit.get("title_l10n"),
        ), ResolvedFunder(id=hit["funder"]["id"], name=hit["funder"]["name"])
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        _log_resolve_error("award by title", title, e)
    return None, None


async def _resolve_funding_entry(
    client: httpx.AsyncClient,
    funder_name: FunderEnum | None,
    title: str | None,
    number: str | None,
    base_url: str,
) -> ResolvedFunding | None:
    ror_id = FUNDER_ROR_IDS.get(funder_name) if funder_name else None

    resolved_award: ResolvedAward | None = None
    resolved_funder: ResolvedFunder | None = None
    if number:
        resolved_award, resolved_funder = await _resolve_award_by_number(
            client, number, ror_id, base_url
        )
    if resolved_award is None and title:
        resolved_award, resolved_funder = await _resolve_award_by_title(
            client, title, ror_id, base_url
        )
    # 0 or >1 award matches: pass whatever info we have as a custom award
    if resolved_award is None and (number or title):
        resolved_award = ResolvedAward(
            number=number or None,
            title=title or None,
        )
    if not resolved_funder and funder_name and ror_id:
        resolved_funder = ResolvedFunder(id=ror_id, name=funder_name)

    if resolved_funder is None and resolved_award is None:
        return None
    return ResolvedFunding(funder=resolved_funder, award=resolved_award)


@activity.defn
async def resolve_metadata_suggestions(
    request: ResolveMetadataRequest,
) -> MetadataSuggestions:
    """Resolve funders, awards, and licenses, and return typed metadata suggestions."""
    extracted = request.metadata
    result = MetadataSuggestions.from_extracted(extracted)

    base_url = get_settings().invenio_base_url
    if not base_url:
        logger.warning("INVENIO_BASE_URL is not configured, skipping resolution")
        return result

    try:
        verify = http_verify(base_url)
    except ValueError as e:
        raise ApplicationError(
            str(e),
            type="HostNotAllowed",
            non_retryable=True,
        ) from e

    async with httpx.AsyncClient(verify=verify) as client:
        # Resolve licenses in parallel, fall back to id if unable to resolve
        if extracted.license:
            resolved_licenses = await asyncio.gather(
                *[
                    _resolve_license(client, lic.lower(), base_url)
                    for lic in extracted.license
                ]
            )
            result.suggestions.append(LicenseSuggestion(value=list(resolved_licenses)))

        # Resolve Funding (awards and funders)
        funders = extracted.funding_funders
        size = max(
            len(extracted.funding_titles),
            len(extracted.funding_numbers),
            len(funders),
        )
        if size:
            resolved = await asyncio.gather(
                *[
                    _resolve_funding_entry(
                        client,
                        funders[i] if i < len(funders) else None,
                        extracted.at(extracted.funding_titles, i),
                        extracted.at(extracted.funding_numbers, i),
                        base_url,
                    )
                    for i in range(size)
                ]
            )
            entries = [r for r in resolved if r is not None]
            if entries:
                result.suggestions.append(FundingSuggestion(value=entries))

    return result
