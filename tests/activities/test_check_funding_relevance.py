# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the check_funding_relevance activity's deterministic guard.

Covers the insufficient-metadata gate (no LLM call).
"""

import asyncio

import pytest

from app.activities.check_funding_relevance import (
    CheckFundingRelevanceRequest,
    check_funding_relevance,
)
from app.workflows.specs import WorkflowContext

CONTEXT = WorkflowContext(workflow_id="wf-test", tenant_id="tenant-1")
AWARD = "This project investigates LLM-based metadata extraction."
RULE = "Return match=true if the record is about the same topic as the grant."


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("", ""),
        ("short title", "description"),
    ],
)
def test_insufficient_metadata_returns_no_match(title, description):
    """Below the char threshold the activity returns the fixed response, no LLM call."""
    request = CheckFundingRelevanceRequest(
        award_description=AWARD,
        metadata={"title": title, "description": description},
        rule=RULE,
    )
    result = asyncio.run(check_funding_relevance(request, CONTEXT))
    assert result.match is False
    assert result.message == "Insufficient metadata to check funding relevance."
