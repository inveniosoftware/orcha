# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import pytest

from app.evals.evaluators import Evaluator, build_comparison_payload


def test_creator_score_penalizes_missing_expected_authors():
    """Missing expected authors reduce the creator score."""
    result = Evaluator(
        {"expected_output": {"creators": [{"name": "Alice"}, {"name": "Zorro"}]}},
        {"creators": ["Alice"]},
    ).creators_eval()

    assert result["creators_name"]["score"] == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("predicted", "score"),
    [
        ("https://doi.org/10.1234/example.5678", 1.0),
        ("10.1234/example.5679", 0.0),
    ],
)
def test_doi_score_requires_an_exact_normalized_identifier(predicted, score):
    """DOIs match exactly after common prefixes are removed."""
    result = Evaluator(
        {"expected_output": {"doi": "10.1234/example.5678"}},
        {"doi": predicted},
    ).doi_eval()

    assert result["score"] == score


def test_publication_date_uses_ground_truth_precision():
    """Extra date precision does not reduce the score."""
    result = Evaluator(
        {"expected_output": {"publication_date": "2026-07"}},
        {"publication_date": "2026-07-16"},
    ).publication_date_eval()

    assert result["score"] == 1.0


def test_null_ground_truth_is_excluded_and_spurious_output_is_counted():
    """Absent GT cannot improve accuracy and fabricated values are counted."""
    result = build_comparison_payload(
        {"title": "Expected title", "doi": "10.1234/invented"},
        {"title": "Expected title"},
    )

    assert result["average_score"] == 1.0
    assert result["gt_field_count"] == 1
    assert result["spurious_count"] == 1


def test_creator_attributes_stay_attached_to_their_authors():
    """Swapped ORCIDs receive no per-author credit."""
    expected = {
        "creators": [
            {"name": "Doe, Jane", "orcid": "0000-0002-1111-1115"},
            {"name": "Smith, John", "orcid": "0000-0002-1825-0097"},
        ]
    }
    predicted = {
        "creators": ["Jane Doe", "John Smith"],
        "creator_orcids": ["0000-0002-1825-0097", "0000-0002-1111-1115"],
    }

    result = Evaluator({"expected_output": expected}, predicted).creators_eval()

    assert result["creators_orcid"]["score"] == 1.0
    assert result["creators_orcid_indexed"]["score"] == 0.0
