"""Checks the eculizumab example by hand with the engine's own code, for the video's report scene.

The reaction term is chosen by a person here, not by the step 5 mapping; everything else (the label
lookup, the verbatim match, the FAERS totals, the PRR and the Evans criteria) is the engine's code on
live openFDA data.

    ../.venv/bin/python capture/handcheck.py [--drug eculizumab] [--term "MENINGOCOCCAL INFECTION"]
"""

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from knockout import genetics, label_match, openfda
from knockout.signals import TermCounts

RAW = Path(__file__).parent / "raw"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drug", default="eculizumab")
    parser.add_argument("--term", default="MENINGOCOCCAL INFECTION")
    arguments = parser.parse_args()

    label = openfda.label(arguments.drug)
    match = label_match.find(label, [arguments.term]) if label else None
    drug_search = openfda.drug_search(arguments.drug)
    reaction_search = openfda.reaction_search(arguments.term)
    counts = TermCounts(
        term=arguments.term,
        a=openfda.total(f"{drug_search} AND {reaction_search}"),
        drug=openfda.total(drug_search),
        reaction=openfda.total(reaction_search),
        all=openfda.total(None),
    )
    prr = counts.prr
    result = {
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "drug": arguments.drug,
        "term": arguments.term,
        "term_chosen_by": "a person (step 5 mapping not run)",
        "label": {
            "set_id": label.set_id if label else None,
            "effective_time": label.effective_time if label else None,
            "section": match.section if match else None,
            "sentence": match.sentence if match else None,
        },
        "counts": {
            "a": counts.a,
            "drug": counts.drug,
            "reaction": counts.reaction,
            "all": counts.all,
            "prr": None if prr is None or math.isinf(prr) else round(prr, 2),
            "chi_squared": round(counts.chi_squared, 1),
            "expected": round(counts.expected, 2),
            "signal": counts.is_signal,
        },
        "openfda_retrieved_at": openfda.total_retrieved_at(None),
        "catalog": {
            "diseases": len(genetics.catalog().diseases),
            "genes": len(genetics.catalog().genes),
            "release": genetics.catalog().release,
        },
    }
    RAW.mkdir(exist_ok=True)
    (RAW / "handcheck.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
