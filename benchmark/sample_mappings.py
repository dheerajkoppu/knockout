"""Draw the protocol's 50-mapping review sample (seed 20261017) into benchmark/results/mapping_review.csv.

The population is every phenotype the benchmark can use (the qualifying phenotypes of every catalog disease
with a known direction) that data/mappings/hpo.json holds, sorted by HPO id, so mappings added later for
other drugs never change the sample. A team member fills in the last four columns; score.py reports agreement.

Run from the repository root: .venv/bin/python -m benchmark.sample_mappings
"""

import csv
import json
import random
import sys

from benchmark import measures
from benchmark.score import REVIEW_CSV, disease_pool, needed_terms
from knockout import config

SAMPLE_SIZE = 50
REVIEW_COLUMNS = ("kind_correct", "terms_correct", "reviewer", "notes")
COLUMNS = ("hpo_id", "label", "hpo_url", "kind", "reaction_terms", "rejected_terms", "proposed", "model", "mapped_at")


def draw(population: list[str], size: int = SAMPLE_SIZE, seed: int = measures.SEED) -> list[str]:
    ordered = sorted(population)
    return sorted(random.Random(seed).sample(ordered, min(size, len(ordered))))


def main() -> int:
    if not config.MAPPINGS_PATH.exists():
        print(f"{config.MAPPINGS_PATH} does not exist: step 5 has not run, so there is nothing to sample. "
              "Set GEMINI_API_KEY and run python -m benchmark.score --generate-mappings first.", file=sys.stderr)
        return 1
    if REVIEW_CSV.exists():
        print(f"{REVIEW_CSV} already exists; delete it first to redraw (a drawn sample may already be reviewed).",
              file=sys.stderr)
        return 1
    stored = json.loads(config.MAPPINGS_PATH.read_text())["terms"]
    population = [hpo_id for hpo_id in needed_terms(disease_pool()) if hpo_id in stored]
    if not population:
        print("hpo.json holds none of the phenotypes the benchmark uses.", file=sys.stderr)
        return 1
    sample = draw(population)
    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_CSV.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS + REVIEW_COLUMNS)
        for hpo_id in sample:
            row = stored[hpo_id]
            writer.writerow([
                hpo_id,
                row["label"],
                f"https://hpo.jax.org/browse/term/{hpo_id}",
                row["kind"],
                "; ".join(row["reaction_terms"]),
                "; ".join(row["rejected_terms"]),
                "; ".join(row.get("proposed", [])),
                row.get("model"),
                row.get("mapped_at"),
                "", "", "", "",
            ])
    print(f"wrote {len(sample)} of {len(population)} mappings to {REVIEW_CSV}. For each row, write yes or no in "
          "kind_correct and terms_correct, then rerun python -m benchmark.score.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
