"""Phenotype classification and HPO-to-reaction-term mapping (protocol step 5), stored once and committed."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from knockout import gemini, openfda
from knockout.config import MAPPINGS_PATH

BATCH_SIZE = 25
MAX_TERMS = 5
KINDS = ("clinical", "laboratory", "developmental")

PROMPT = """For each Human Phenotype Ontology term below, return:

1. kind:
   - "clinical": a sign, symptom, infection or disease a person has.
   - "laboratory": a measured value or a test finding.
   - "developmental": present from birth or caused by abnormal development, such as a malformation,
     a congenital anomaly, or growth or developmental delay in childhood.
2. reaction_terms: up to five MedDRA preferred terms, in capital letters, that the FDA Adverse Event
   Reporting System would use to record the same condition as an adverse reaction, most specific
   first. Use only real MedDRA preferred terms. Return an empty list when none fits.

Return every term, with its hpo_id unchanged.

Terms:
{terms}"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "terms": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "hpo_id": {"type": "STRING"},
                    "kind": {"type": "STRING"},
                    "reaction_terms": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["hpo_id", "kind", "reaction_terms"],
            },
        }
    },
    "required": ["terms"],
}


@dataclass(frozen=True)
class TermMapping:
    hpo_id: str
    label: str
    kind: str
    reaction_terms: tuple[str, ...]
    rejected_terms: tuple[str, ...]


def _load() -> dict:
    if MAPPINGS_PATH.exists():
        return json.loads(MAPPINGS_PATH.read_text())
    return {"protocol_version": 1, "terms": {}}


def _save(store: dict) -> None:
    MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    store["terms"] = dict(sorted(store["terms"].items()))
    MAPPINGS_PATH.write_text(json.dumps(store, indent=1) + "\n")


def _as_mapping(hpo_id: str, row: dict) -> TermMapping:
    return TermMapping(
        hpo_id=hpo_id,
        label=row["label"],
        kind=row["kind"],
        reaction_terms=tuple(row["reaction_terms"]),
        rejected_terms=tuple(row["rejected_terms"]),
    )


def _validate(proposed: list[str]) -> tuple[list[str], list[str]]:
    """Keep a term only if FAERS holds at least one report of it, across all drugs."""
    kept, rejected = [], []
    for term in dict.fromkeys(term.strip().upper() for term in proposed if term.strip()):
        (kept if openfda.total(openfda.reaction_search(term)) >= 1 else rejected).append(term)
    return kept[:MAX_TERMS], rejected


def ensure(terms: dict[str, str]) -> dict[str, TermMapping]:
    """Mappings for every HPO id given ({hpo_id: label}). Missing ones are generated and saved.

    Raises GeminiUnavailable when terms are missing and no key is set; already-stored terms still load.
    """
    store = _load()
    missing = {hpo_id: label for hpo_id, label in terms.items() if hpo_id not in store["terms"]}
    if missing:
        store.setdefault("model", gemini.model())
        ids = list(missing)
        for start in range(0, len(ids), BATCH_SIZE):
            batch = {hpo_id: missing[hpo_id] for hpo_id in ids[start : start + BATCH_SIZE]}
            listing = "\n".join(f"- {hpo_id}: {label}" for hpo_id, label in batch.items())
            answer = gemini.generate_json(PROMPT.format(terms=listing), SCHEMA)
            returned = {row["hpo_id"]: row for row in answer.get("terms", [])}
            for hpo_id, label in batch.items():
                row = returned.get(hpo_id)
                if row is None:
                    continue
                kind = row["kind"] if row["kind"] in KINDS else "clinical"
                kept, rejected = _validate(row.get("reaction_terms", []))
                store["terms"][hpo_id] = {
                    "label": label,
                    "kind": kind,
                    "proposed": row.get("reaction_terms", []),
                    "reaction_terms": kept,
                    "rejected_terms": rejected,
                    "model": gemini.model(),
                    "mapped_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            _save(store)
    return {hpo_id: _as_mapping(hpo_id, store["terms"][hpo_id]) for hpo_id in terms if hpo_id in store["terms"]}


def stored(terms: dict[str, str]) -> dict[str, TermMapping]:
    """Only what is already in the committed file; never calls a model."""
    store = _load()
    return {hpo_id: _as_mapping(hpo_id, store["terms"][hpo_id]) for hpo_id in terms if hpo_id in store["terms"]}
