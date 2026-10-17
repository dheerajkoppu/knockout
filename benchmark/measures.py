"""The protocol's measures as pure functions over report dictionaries (engine Report.to_dict())."""

import random
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from statistics import mean

from knockout.label_match import term_pattern
from knockout.signals import TermCounts

SEED = 20261017
SHUFFLES = 100
KINDS = ("clinical", "laboratory")
MIN_DRUG_REPORTS = 100

MISS_NO_TERMS = "no reaction term survived step 5"
MISS_FEW_REPORTS = "the drug has fewer than 100 reports"
MISS_UNKNOWN = "the verdict is unknown"
MISS_OTHER = "none of the above"
MISS_BUCKETS = (MISS_NO_TERMS, MISS_FEW_REPORTS, MISS_UNKNOWN, MISS_OTHER)
# Not a protocol bucket: only appears when step 5 has not run for a phenotype.
MISS_NOT_MAPPED = "phenotype not mapped (step 5 did not run)"


def ratio(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def has_report_signal(prediction: dict) -> bool:
    return any(count.get("signal") for count in prediction.get("counts") or [])


def of_kind(predictions: list[dict], kind: str) -> list[dict]:
    return [prediction for prediction in predictions if prediction.get("kind") == kind]


def label_precision(predictions: list[dict], kind: str) -> dict:
    """Measure 1: predictions on the label over all predictions of this kind."""
    rows = of_kind(predictions, kind)
    return ratio(sum(prediction["verdict"] == "on_label" for prediction in rows), len(rows))


def report_precision(predictions: list[dict], kind: str, *, include_on_label: bool = True) -> dict:
    """Measure 2: predictions with a report signal over predictions whose verdict is not unknown."""
    rows = [
        prediction
        for prediction in of_kind(predictions, kind)
        if prediction["verdict"] != "unknown" and (include_on_label or prediction["verdict"] != "on_label")
    ]
    return ratio(sum(has_report_signal(prediction) for prediction in rows), len(rows))


def verdict(on_label: bool, counts: list[TermCounts], has_terms: bool) -> str:
    """The engine's step 8, for predictions built outside the engine (the shuffled arm)."""
    if not has_terms:
        return "unknown"
    if on_label:
        return "on_label"
    if any(item.is_signal for item in counts):
        return "signal_in_reports"
    if not counts or all(item.underpowered for item in counts):
        return "unknown"
    return "no_signal"


def counts_as_dicts(counts: list[TermCounts]) -> list[dict]:
    return [{"term": item.term, "a": item.a, "signal": item.is_signal} for item in counts]


def lift(real: float | None, shuffled: list[float | None]) -> dict:
    """Measures 3 and 4: the real value, the shuffle mean and the share of shuffles at or above the real value."""
    values = [value for value in shuffled if value is not None]
    return {
        "real": real,
        "shuffle_mean": mean(values) if values else None,
        "share_at_or_above": (
            sum(value >= real for value in values) / len(values) if values and real is not None else None
        ),
        "shuffles": len(shuffled),
        "shuffles_with_a_value": len(values),
    }


@dataclass
class ShuffleDrug:
    """What a drug's shuffle needs: how many diseases it used per direction, and which genes to avoid."""

    drug: str
    diseases_by_direction: dict[str, int]
    excluded_genes: set[str] = field(default_factory=set)


def draw(rng: random.Random, drugs: list[ShuffleDrug], pool: dict[str, list[tuple[str, str]]]) -> dict:
    """One shuffle: each drug's diseases replaced by the same number drawn from the same direction."""
    assignment: dict[str, list[tuple[str, str]]] = {}
    for drug in drugs:
        drawn: list[tuple[str, str]] = []
        for direction in sorted(drug.diseases_by_direction):
            candidates = [pair for pair in pool.get(direction, []) if pair[1] not in drug.excluded_genes]
            drawn.extend(rng.sample(candidates, min(drug.diseases_by_direction[direction], len(candidates))))
        assignment[drug.drug] = drawn
    return assignment


def shuffles(
    drugs: list[ShuffleDrug], pool: dict[str, list[tuple[str, str]]], *, seed: int = SEED, count: int = SHUFFLES
) -> list[dict]:
    rng = random.Random(seed)
    ordered_pool = {direction: sorted(pairs) for direction, pairs in pool.items()}
    return [draw(rng, drugs, ordered_pool) for _ in range(count)]


class LabelIndex:
    """Whether a reaction term is on one label, with the same whole-phrase rule as knockout.label_match.

    A match never crosses a sentence boundary, because the pattern joins words with whitespace only and
    a sentence ends in punctuation; so searching each whole section is the same test as searching each sentence.
    """

    def __init__(self, sections: dict[str, str] | None) -> None:
        self.sections = list((sections or {}).values())
        self.lowered = [text.lower() for text in self.sections]
        self._answers: dict[str, bool] = {}

    def contains(self, term: str) -> bool:
        if term not in self._answers:
            words = term.lower().split()
            self._answers[term] = any(
                all(word in lowered for word in words) and _pattern(term).search(text)
                for text, lowered in zip(self.sections, self.lowered)
            )
        return self._answers[term]

    def any_term(self, terms: list[str]) -> bool:
        return any(self.contains(term) for term in terms)


@cache
def _pattern(term: str) -> re.Pattern[str]:
    return term_pattern(term)


def boxed_warning_recall(reports: list[dict], kind: str | None = None) -> dict:
    """Measure 5: drugs whose boxed warning holds a sentence matched by at least one prediction."""
    with_boxed = [report for report in reports if "boxed_warning" in ((report.get("label") or {}).get("sections") or [])]
    drugs = []
    for report in with_boxed:
        matched = [
            prediction
            for prediction in report["predictions"]
            if prediction.get("label_section") == "boxed_warning" and (kind is None or prediction.get("kind") == kind)
        ]
        drugs.append({
            "drug": (report.get("molecule") or {}).get("name") or report["query"],
            "matched": bool(matched),
            "sentences": sorted({prediction["label_sentence"] for prediction in matched}),
            "phenotypes": sorted({prediction["phenotype"] for prediction in matched}),
        })
    return ratio(sum(row["matched"] for row in drugs), len(drugs)) | {"drugs": drugs}


def classify_miss(prediction: dict, drug_reports: int | None) -> str | None:
    """The protocol's miss buckets, in order. None when the prediction is not a miss."""
    if prediction["verdict"] == "on_label" or has_report_signal(prediction):
        return None
    if prediction.get("kind") is None:
        return MISS_NOT_MAPPED
    if not prediction.get("reaction_terms"):
        return MISS_NO_TERMS
    if drug_reports is not None and drug_reports < MIN_DRUG_REPORTS:
        return MISS_FEW_REPORTS
    if prediction["verdict"] == "unknown":
        return MISS_UNKNOWN
    return MISS_OTHER


def classify_misses(reports: list[dict]) -> dict:
    """Bucket counts per kind, plus every miss with its bucket."""
    by_kind: dict[str, Counter] = {}
    rows = []
    for report in reports:
        for prediction in report["predictions"]:
            bucket = classify_miss(prediction, report.get("drug_reports"))
            if bucket is None:
                continue
            kind = prediction.get("kind") or "unmapped"
            by_kind.setdefault(kind, Counter())[bucket] += 1
            rows.append({
                "drug": (report.get("molecule") or {}).get("name") or report["query"],
                "hpo_id": prediction["hpo_id"],
                "phenotype": prediction["phenotype"],
                "kind": prediction.get("kind"),
                "gene": prediction["gene"],
                "disease": prediction["disease"],
                "verdict": prediction["verdict"],
                "bucket": bucket,
            })
    ordered = MISS_BUCKETS + (MISS_NOT_MAPPED,)
    return {
        "buckets": {
            kind: {bucket: counter[bucket] for bucket in ordered if counter[bucket] or bucket in MISS_BUCKETS}
            for kind, counter in sorted(by_kind.items(), key=lambda item: (item[0] not in KINDS, item[0]))
        },
        "misses": rows,
    }


def candidate_new_signals(reports: list[dict]) -> list[dict]:
    """Measure 6: every clinical prediction with a report signal and no label sentence, with its chain."""
    rows = []
    for report in reports:
        molecule = report.get("molecule") or {}
        for prediction in report["predictions"]:
            if not prediction.get("candidate_new_signal"):
                continue
            rows.append({
                "drug": molecule.get("name") or report["query"],
                "chembl_id": molecule.get("chembl_id"),
                "target": prediction["target"],
                "gene": prediction["gene"],
                "disease_id": prediction["disease_id"],
                "disease": prediction["disease"],
                "hpo_id": prediction["hpo_id"],
                "phenotype": prediction["phenotype"],
                "frequency": prediction["frequency"],
                "reaction_terms": prediction["reaction_terms"],
                "signal_counts": [count for count in prediction["counts"] if count.get("signal")],
                "counts": prediction["counts"],
                "records": prediction["records"],
            })
    return rows
