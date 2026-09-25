# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import re
from difflib import SequenceMatcher
from itertools import zip_longest
from typing import Any

from langfuse import Evaluation


def norm_name(name: Any) -> str:
    """Normalize a person name to sorted lowercase tokens."""
    tokens = re.findall(r"\w+", str(name or "").lower())
    return " ".join(sorted(tokens))


def norm_orcid(orcid: Any) -> str:
    """Normalize an ORCID to its bare uppercase identifier."""
    return re.sub(r"[^0-9X]", "", str(orcid or "").upper())


def norm_doi(doi: Any) -> str:
    """Normalize a DOI by removing common prefixes."""
    doi = str(doi or "").strip().lower()
    return re.sub(r"^(https?://)?(dx\.)?doi\.org/|^doi:\s*", "", doi)


def creator_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Return creator rows in the flat app schema."""
    return [
        {
            "name": name,
            "orcid": orcid,
            "affiliation": [{"name": affiliation}] if affiliation else [],
        }
        for name, orcid, affiliation in zip_longest(
            source.get("creators") or [],
            source.get("creator_orcids") or [],
            source.get("creator_affiliations") or [],
            fillvalue="",
        )
        if name or orcid or affiliation
    ]


def sym_score(exp_vals: list, pred_vals: list, sim: Any) -> tuple[float, bool]:
    """Return a symmetric precision/recall score and GT presence."""
    if not exp_vals:
        return (1.0 if not pred_vals else 0.0), False
    if not pred_vals:
        return 0.0, True

    precision = sum(max(sim(p, e) for e in exp_vals) for p in pred_vals) / len(
        pred_vals
    )
    recall = sum(max(sim(p, e) for p in pred_vals) for e in exp_vals) / len(exp_vals)
    if precision + recall == 0:
        return 0.0, True
    return 2 * precision * recall / (precision + recall), True


def align_creators(
    exp_creators: list, pred_creators: list, threshold: float = 0.8
) -> dict[int, int]:
    """Match predicted creators to expected creators by name."""
    candidates = []
    for exp_index, expected in enumerate(exp_creators):
        if not isinstance(expected, dict):
            continue
        expected_name = norm_name(expected.get("name"))
        for pred_index, predicted in enumerate(pred_creators):
            if not isinstance(predicted, dict):
                continue
            score = SequenceMatcher(
                None, expected_name, norm_name(predicted.get("name"))
            ).ratio()
            if score >= threshold:
                candidates.append((score, exp_index, pred_index))

    matches = {}
    used_expected = set()
    used_predicted = set()
    for _score, exp_index, pred_index in sorted(candidates, reverse=True):
        if exp_index in used_expected or pred_index in used_predicted:
            continue
        used_expected.add(exp_index)
        used_predicted.add(pred_index)
        matches[exp_index] = pred_index
    return matches


def indexed_score(
    exp_creators: list,
    pred_creators: list,
    matches: dict[int, int],
    get_vals: Any,
    sim: Any,
) -> dict[str, Any]:
    """Score an attribute after creators have been matched by name."""
    exp_has = [
        index
        for index, creator in enumerate(exp_creators)
        if isinstance(creator, dict) and get_vals(creator)
    ]
    pred_has = [
        index
        for index, creator in enumerate(pred_creators)
        if isinstance(creator, dict) and get_vals(creator)
    ]
    predicted = [get_vals(pred_creators[index]) for index in pred_has]
    if not exp_has:
        return {
            "expected": [],
            "predicted": predicted,
            "score": 1.0 if not pred_has else 0.0,
            "matched": not pred_has,
            "gt_present": False,
        }

    pred_to_exp = {pred_index: exp_index for exp_index, pred_index in matches.items()}

    def pair(exp_index: int, pred_index: int) -> float:
        return sym_score(
            get_vals(exp_creators[exp_index]),
            get_vals(pred_creators[pred_index]),
            sim,
        )[0]

    recall = sum(
        pair(exp_index, matches[exp_index]) if exp_index in matches else 0.0
        for exp_index in exp_has
    ) / len(exp_has)
    precision = (
        sum(
            pair(pred_to_exp[pred_index], pred_index)
            if pred_index in pred_to_exp
            else 0.0
            for pred_index in pred_has
        )
        / len(pred_has)
        if pred_has
        else 0.0
    )
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "expected": [get_vals(exp_creators[index]) for index in exp_has],
        "predicted": predicted,
        "score": score,
        "matched": score == 1.0,
        "gt_present": True,
    }


class Evaluator:
    """Compare predicted metadata with expected metadata."""

    def __init__(self, item: dict[str, Any], predicted: dict[str, Any]) -> None:
        """Store expected and predicted metadata for later comparison."""
        self.exp = item["expected_output"]
        self.pred = predicted

    def _text_eval(self, exp_val: Any, pred_val: Any) -> dict[str, Any]:
        """Return the best match against one or more expected strings."""
        if isinstance(exp_val, list):
            candidates = [
                next(iter(value.values())) if isinstance(value, dict) else value
                for value in exp_val
            ]
        else:
            candidates = [exp_val]
        candidates = [candidate for candidate in candidates if candidate]

        gt_present = bool(candidates)
        if gt_present:
            score = max(
                SequenceMatcher(None, str(candidate), str(pred_val or "")).ratio()
                for candidate in candidates
            )
        else:
            score = 1.0 if not pred_val else 0.0

        return {
            "expected": candidates,
            "predicted": pred_val,
            "score": score,
            "matched": score == 1.0,
            "gt_present": gt_present,
        }

    def title_eval(self) -> dict[str, Any]:
        """Compare the predicted title with the expected title."""
        return self._text_eval(self.exp.get("title"), self.pred.get("title"))

    def description_eval(self) -> dict[str, Any]:
        """Compare the predicted description with the expected description."""
        return self._text_eval(
            self.exp.get("description"), self.pred.get("description")
        )

    def doi_eval(self) -> dict[str, Any]:
        """Compare DOI identifiers exactly after normalization."""
        exp_doi = self.exp.get("doi")
        pred_doi = self.pred.get("doi")
        exp_norm = norm_doi(exp_doi)
        pred_norm = norm_doi(pred_doi)
        gt_present = bool(exp_norm)
        score = (
            (1.0 if pred_norm == exp_norm else 0.0)
            if gt_present
            else (1.0 if not pred_norm else 0.0)
        )

        return {
            "expected": exp_doi,
            "predicted": pred_doi,
            "score": score,
            "matched": score == 1.0,
            "gt_present": gt_present,
        }

    def publication_date_eval(self) -> dict[str, Any]:
        """Compare a publication date at the ground truth's precision."""
        exp_date = self.exp.get("publication_date")
        pred_date = self.pred.get("publication_date")
        exp_str = str(exp_date or "").strip()
        pred_str = str(pred_date or "").strip()
        gt_present = bool(exp_str)
        score = (
            SequenceMatcher(None, exp_str, pred_str[: len(exp_str)]).ratio()
            if gt_present
            else (1.0 if not pred_str else 0.0)
        )
        return {
            "expected": exp_date,
            "predicted": pred_date,
            "score": score,
            "matched": score == 1.0,
            "gt_present": gt_present,
        }

    def creators_eval(self) -> dict[str, dict[str, Any]]:
        """Compare predicted creator names, ORCIDs, and affiliations."""
        exp_creators = self.exp.get("creators", [])
        pred_creators = creator_records(self.pred)

        results: dict[str, dict[str, Any]] = {}

        similarities = {
            "name": lambda p, e: SequenceMatcher(
                None, norm_name(p), norm_name(e)
            ).ratio(),
            "orcid": lambda p, e: 1.0 if norm_orcid(p) == norm_orcid(e) else 0.0,
        }
        for field in ["name", "orcid"]:
            exp_vals = [
                c.get(field)
                for c in exp_creators
                if isinstance(c, dict) and c.get(field)
            ]
            pred_vals = [
                c.get(field)
                for c in pred_creators
                if isinstance(c, dict) and c.get(field)
            ]

            score, gt_present = sym_score(exp_vals, pred_vals, similarities[field])

            results[f"creators_{field}"] = {
                "expected": exp_vals,
                "predicted": pred_vals,
                "score": score,
                "matched": score == 1.0,
                "gt_present": gt_present,
            }

        # Evaluate affiliation
        exp_affiliations = []
        for c in exp_creators:
            if isinstance(c, dict) and c.get("affiliation"):
                for aff in c["affiliation"]:
                    if isinstance(aff, dict) and aff.get("name"):
                        exp_affiliations.append(aff["name"])

        pred_affiliations = []
        for c in pred_creators:
            if isinstance(c, dict) and c.get("affiliation"):
                for aff in c["affiliation"]:
                    if isinstance(aff, dict) and aff.get("name"):
                        pred_affiliations.append(aff["name"])

        score, gt_present = sym_score(
            exp_affiliations,
            pred_affiliations,
            lambda p, e: SequenceMatcher(
                None, str(p or "").lower(), str(e or "").lower()
            ).ratio(),
        )

        results["creators_affiliation"] = {
            "expected": exp_affiliations,
            "predicted": pred_affiliations,
            "score": score,
            "matched": score == 1.0,
            "gt_present": gt_present,
        }

        matches = align_creators(exp_creators, pred_creators)

        def affiliations(creator: dict) -> list:
            return [
                affiliation["name"]
                for affiliation in creator.get("affiliation") or []
                if isinstance(affiliation, dict) and affiliation.get("name")
            ]

        def orcids(creator: dict) -> list:
            return [creator["orcid"]] if creator.get("orcid") else []

        results["creators_affiliation_indexed"] = indexed_score(
            exp_creators,
            pred_creators,
            matches,
            affiliations,
            lambda p, e: SequenceMatcher(
                None, str(p or "").lower(), str(e or "").lower()
            ).ratio(),
        )
        results["creators_orcid_indexed"] = indexed_score(
            exp_creators,
            pred_creators,
            matches,
            orcids,
            lambda p, e: 1.0 if norm_orcid(p) == norm_orcid(e) else 0.0,
        )

        return results

    def evaluate(self) -> dict[str, dict[str, Any]]:
        """Run all metadata comparisons and return the combined results."""
        return {
            "title": self.title_eval(),
            "description": self.description_eval(),
            "doi": self.doi_eval(),
            "publication_date": self.publication_date_eval(),
            **self.creators_eval(),
        }


def build_comparison_payload(
    predicted_output: dict[str, Any],
    expected_output: dict[str, Any],
) -> dict[str, Any]:
    """Build comparison data using the Evaluator class."""
    evaluator = Evaluator({"expected_output": expected_output}, predicted_output)
    comparison = evaluator.evaluate()

    diagnostic_only = {"creators_orcid", "creators_affiliation"}
    headline = {
        name: field for name, field in comparison.items() if name not in diagnostic_only
    }
    gt_fields = [field for field in headline.values() if field["gt_present"]]
    scored = gt_fields or list(headline.values())

    return {
        "average_score": round(
            sum(field["score"] for field in scored) / len(scored), 4
        ),
        "mismatch_count": sum(not field["matched"] for field in gt_fields),
        "field_count": len(headline),
        "gt_field_count": len(gt_fields),
        "spurious_count": sum(
            1
            for field in headline.values()
            if not field["gt_present"] and field["score"] < 1.0
        ),
        "fields": comparison,
    }


def item_summary_evaluator(
    output: dict[str, Any],
    **kwargs: Any,
) -> list[Evaluation]:
    """Builds field-level and summary evaluations for Langfuse tracking."""
    comparison = output["comparison"]
    evals: list[Evaluation] = []

    for field, field_row in comparison["fields"].items():
        evals.append(
            Evaluation(
                name=f"{field}_score",
                value=field_row["score"],
                metadata={
                    "expected": field_row["expected"],
                    "predicted": field_row["predicted"],
                    "matched": field_row["matched"],
                },
            )
        )

    summary_score = float(comparison.get("average_score", 0.0))
    mismatch_count = int(comparison.get("mismatch_count", 0))
    field_count = int(comparison.get("field_count", 0))

    evals.append(
        Evaluation(
            name="item_summary",
            value=summary_score,
            metadata={
                "mismatch_count": mismatch_count,
                "field_count": field_count,
            },
        )
    )

    return evals


def average_score_evaluator(item_results: list[Any], **kwargs: Any) -> Evaluation:
    """Aggregates scores across all items in the run."""
    all_scores = [
        evaluation.value
        for result in item_results
        for evaluation in result.evaluations
        if evaluation.name == "item_summary"
    ]

    avg = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0

    return Evaluation(
        name="run_average_score",
        value=avg,
    )
