import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark import drug_set, measures, report, sample_mappings, score
from knockout import label_match
from knockout.mapping import TermMapping
from knockout.openfda import Label
from knockout.signals import TermCounts

CAVEAT_PHRASES = tuple(text[:40] for text in report.CAVEATS.values()) + ("step 5 is a model output",)


def _count(term: str, signal: bool, a: int = 10) -> dict:
    return {"term": term, "a": a, "drug": 5000, "reaction": 100, "all": 1_000_000, "prr": 21.0,
            "chi_squared": 150.0, "signal": signal, "expected": 0.5, "query": "q"}


def _prediction(hpo_id: str, kind: str | None, verdict: str, *, terms=("TERM",), counts=(), section=None,
                sentence=None, candidate=False) -> dict:
    return {
        "hpo_id": hpo_id, "phenotype": f"phenotype {hpo_id}", "frequency": "Frequent", "kind": kind,
        "gene": "G1", "target": "Target 1", "disease_id": "D1", "disease": "Disease 1",
        "reaction_terms": list(terms), "label_section": section, "label_term": terms[0] if section else None,
        "label_sentence": sentence, "counts": list(counts), "verdict": verdict, "reason": None,
        "candidate_new_signal": candidate, "records": [{"source": "chembl", "description": "d", "url": None}],
    }


def _report(chembl_id: str, predictions: list[dict], *, drug_reports: int, sections=("warnings",)) -> dict:
    return {
        "query": chembl_id,
        "molecule": {"chembl_id": chembl_id, "name": f"Drug {chembl_id}"},
        "targets": [{"chembl_id": "T1", "name": "Target 1", "accession": None, "effect": "lowers",
                     "action_types": ["INHIBITOR"], "gene": "G1", "used": True, "reason": None}],
        "diseases": [{"disease_id": "D1", "name": "Disease 1", "gene": "G1", "direction": "decreased_activity",
                      "direction_source": "iuis", "direction_basis": "b", "pairing": "use", "phenotypes_used": 3}],
        "predictions": predictions,
        "excluded_developmental": [],
        "label": {"set_id": "s", "effective_time": "20260101", "generic_names": [], "sections": list(sections)},
        "drug_reports": drug_reports,
        "all_reports": 1_000_000,
        "problems": [],
    }


@pytest.fixture
def reports() -> list[dict]:
    first = [
        _prediction("HP:1", "clinical", "on_label", terms=("SERIOUS INFECTION",), counts=[_count("SERIOUS INFECTION", True)],
                    section="boxed_warning", sentence="WARNING: SERIOUS INFECTIONS"),
        _prediction("HP:2", "clinical", "signal_in_reports", terms=("NEUTROPENIA",),
                    counts=[_count("NEUTROPENIA", True)], candidate=True),
        _prediction("HP:3", "clinical", "no_signal", counts=[_count("TERM", False)]),
        _prediction("HP:4", "laboratory", "unknown", terms=()),
        _prediction("HP:5", "laboratory", "unknown", counts=[_count("TERM", False, a=0)]),
    ]
    second = [_prediction("HP:6", "clinical", "no_signal", counts=[_count("TERM", False)])]
    third = [_prediction("HP:7", "clinical", "no_signal", counts=[_count("TERM", False)])]
    return [
        _report("CHEMBL_A", first, drug_reports=5000, sections=("boxed_warning", "warnings")),
        _report("CHEMBL_B", second, drug_reports=50),
        _report("CHEMBL_C", third, drug_reports=5000, sections=("boxed_warning",)),
    ]


def _all(reports: list[dict]) -> list[dict]:
    return [prediction for row in reports for prediction in row["predictions"]]


def test_label_precision_counts_every_prediction_of_the_kind(reports):
    assert measures.label_precision(_all(reports), "clinical") == {"numerator": 1, "denominator": 5, "value": 0.2}
    assert measures.label_precision(_all(reports), "laboratory") == {"numerator": 0, "denominator": 2, "value": 0.0}
    assert measures.label_precision([], "clinical")["value"] is None


def test_report_precision_excludes_unknown_and_can_exclude_on_label(reports):
    predictions = _all(reports)
    assert measures.report_precision(predictions, "clinical") == {"numerator": 2, "denominator": 5, "value": 0.4}
    assert measures.report_precision(predictions, "clinical", include_on_label=False) == {
        "numerator": 1, "denominator": 4, "value": 0.25}
    assert measures.report_precision(predictions, "laboratory")["denominator"] == 0


def test_lift_reports_real_mean_and_share_at_or_above():
    result = measures.lift(0.5, [0.2, 0.5, 0.8, None])
    assert result["real"] == 0.5
    assert result["shuffle_mean"] == pytest.approx(0.5)
    assert result["share_at_or_above"] == pytest.approx(2 / 3)
    assert result["shuffles"] == 4 and result["shuffles_with_a_value"] == 3
    assert measures.lift(None, [0.1])["share_at_or_above"] is None


POOL = {
    "decreased_activity": [("D1", "G1"), ("D2", "G2"), ("D3", "G3"), ("D4", "G4"), ("D5", "G1")],
    "increased_activity": [("D6", "G6"), ("D7", "G7")],
}


def test_shuffles_keep_count_and_direction_and_avoid_the_drugs_genes():
    drugs = [measures.ShuffleDrug("A", {"decreased_activity": 2, "increased_activity": 1}, {"G1"})]
    draws = measures.shuffles(drugs, POOL, seed=measures.SEED, count=measures.SHUFFLES)
    assert len(draws) == 100
    for assignment in draws:
        drawn = assignment["A"]
        assert len(drawn) == 3 and len(set(drawn)) == 3
        assert all(gene != "G1" for _, gene in drawn)
        assert sum(pair in POOL["increased_activity"] for pair in drawn) == 1


def test_shuffles_are_fixed_by_the_seed_and_ignore_pool_order():
    drugs = [measures.ShuffleDrug("A", {"decreased_activity": 2}, {"G1"}), measures.ShuffleDrug("B", {"decreased_activity": 1})]
    reversed_pool = {direction: list(reversed(pairs)) for direction, pairs in POOL.items()}
    assert measures.shuffles(drugs, POOL) == measures.shuffles(drugs, reversed_pool)
    assert measures.shuffles(drugs, POOL) != measures.shuffles(drugs, POOL, seed=1)


def test_draw_takes_what_exists_when_the_pool_is_small():
    drawn = measures.draw(random.Random(0), [measures.ShuffleDrug("A", {"increased_activity": 5})], POOL)
    assert sorted(drawn["A"]) == POOL["increased_activity"]


def test_verdict_matches_the_engine_order():
    signal = TermCounts(term="X", a=10, drug=1000, reaction=100, all=1_000_000)
    quiet = TermCounts(term="X", a=0, drug=50, reaction=100, all=10_000_000)
    plain = TermCounts(term="X", a=1, drug=50_000, reaction=10_000, all=10_000_000)
    assert measures.verdict(True, [], True) == "on_label"
    assert measures.verdict(False, [signal], True) == "signal_in_reports"
    assert measures.verdict(False, [quiet], True) == "unknown"
    assert measures.verdict(False, [], True) == "unknown"
    assert measures.verdict(False, [plain], True) == "no_signal"
    assert measures.verdict(True, [signal], False) == "unknown"


@pytest.mark.parametrize("term", ["MENINGOCOCCAL INFECTION", "SEPSIS", "INFECTION SEPSIS", "NEUTROPENIA",
                                  "SERIOUS INFECTION", "HEADACHE", "ASEPSIS", "INFECTIONS"])
def test_label_index_agrees_with_the_engines_label_match(term):
    sections = {
        "boxed_warning": "WARNING: SERIOUS MENINGOCOCCAL INFECTIONS. Vaccinate first.",
        "warnings": "Risk of infection. Sepsis occurred in 2%. Aseptic technique; asepsis is required. Neutropenias.",
    }
    label = Label(set_id="s", effective_time="1", generic_names=(), sections=sections)
    expected = label_match.find(label, [term]) is not None
    assert measures.LabelIndex(sections).contains(term) is expected


def test_boxed_warning_recall_needs_a_matched_boxed_sentence(reports):
    recall = measures.boxed_warning_recall(reports)
    assert (recall["numerator"], recall["denominator"]) == (1, 2)
    assert recall["drugs"][0]["sentences"] == ["WARNING: SERIOUS INFECTIONS"]
    assert measures.boxed_warning_recall(reports, "laboratory")["numerator"] == 0


def test_misses_fall_into_the_first_bucket_that_applies(reports):
    first, second, _ = reports
    buckets = [measures.classify_miss(prediction, first["drug_reports"]) for prediction in first["predictions"]]
    assert buckets == [None, None, measures.MISS_OTHER, measures.MISS_NO_TERMS, measures.MISS_UNKNOWN]
    assert measures.classify_miss(second["predictions"][0], second["drug_reports"]) == measures.MISS_FEW_REPORTS
    no_terms_and_few_reports = _prediction("HP:9", "clinical", "unknown", terms=())
    assert measures.classify_miss(no_terms_and_few_reports, 10) == measures.MISS_NO_TERMS
    assert measures.classify_miss(_prediction("HP:9", None, "unknown", terms=()), 10) == measures.MISS_NOT_MAPPED
    summary = measures.classify_misses(reports)
    assert summary["buckets"]["clinical"][measures.MISS_FEW_REPORTS] == 1
    assert summary["buckets"]["laboratory"][measures.MISS_NO_TERMS] == 1


def test_candidate_new_signals_list_the_chain_and_signal_counts(reports):
    rows = measures.candidate_new_signals(reports)
    assert [row["hpo_id"] for row in rows] == ["HP:2"]
    assert rows[0]["signal_counts"][0]["term"] == "NEUTROPENIA" and rows[0]["records"]


def _item(parent: str, molecule: str, action_type: str, gene: str, directions: list[str], record_id: int) -> dict:
    return {
        "gene": {"gene": gene, "accession": f"P_{gene}",
                 "diseases": [{"disease_id": f"{gene}-{index}", "name": f"{gene} disease", "direction": direction,
                               "direction_source": "iuis", "direction_basis": "b"}
                              for index, direction in enumerate(directions)]},
        "target": {"target_chembl_id": f"T_{gene}", "pref_name": gene},
        "record": {"molecule_chembl_id": molecule, "parent_molecule_chembl_id": parent, "action_type": action_type,
                   "mec_id": record_id},
        "molecule": {"pref_name": parent},
    }


def test_drug_set_step3_applies_the_direction_rule():
    kept, dropped = drug_set.step3_pairs([
        _item("M1", "M1_SALT", "INHIBITOR", "BTK", ["decreased_activity"], 1),
        _item("M2", "M2", "AGONIST", "CSF3R", ["decreased_activity"], 2),
        _item("M3", "M3", "BINDING AGENT", "CD19", ["decreased_activity"], 3),
        _item("M4", "M4", "INHIBITOR", "JAK1", ["decreased_activity"], 4),
        _item("M4", "M4", "AGONIST", "JAK1", ["decreased_activity"], 5),
        _item("M5", "M5", "AGONIST", "TLR7", ["increased_activity", "decreased_activity"], 6),
    ])
    assert sorted(kept) == ["M1", "M5"]
    assert kept["M1"][0]["records_on_salt_forms"] == ["M1_SALT"]
    assert [disease["direction"] for disease in kept["M5"][0]["diseases_used"]] == ["increased_activity"]
    reasons = {row["molecule_chembl_id"]: row for row in dropped}
    assert reasons["M2"]["effect"] == "raises" and "points the other way" in reasons["M2"]["reason"]
    assert reasons["M3"]["effect"] == "unknown"
    assert reasons["M4"]["effect"] == "unknown" and reasons["M4"]["mechanism_record_ids"] == [4, 5]
    assert all(row["step"] == 3 for row in dropped)


def test_review_sample_is_fixed_by_the_seed():
    population = [f"HP:{number:07d}" for number in range(200)]
    sample = sample_mappings.draw(population)
    assert len(sample) == 50 and sample == sorted(sample) and set(sample) <= set(population)
    assert sample == sample_mappings.draw(list(reversed(population)))
    assert sample_mappings.draw(population[:10]) == population[:10]


class FakeContext:
    def __init__(self, sections: dict[str, str], top: dict[str, int], drug_reports: int) -> None:
        self.label = measures.LabelIndex(sections)
        self.top = top
        self.drug_reports = drug_reports

    def load_top_reactions(self) -> None:
        pass

    def top_counts(self, terms: list[str]) -> list[TermCounts]:
        return [TermCounts(term=term, a=self.top.get(term, 0), drug=self.drug_reports, reaction=100, all=1_000_000)
                for term in terms]


def _results(computed: dict | None, blocked: str | None) -> dict:
    counts = {key: 1 for key in ("step1_genes_kept", "step1_genes_dropped", "step2_records_kept",
                                 "step2_candidates_dropped", "step3_molecules_kept", "step3_pairs_dropped",
                                 "step4_drugs_kept", "step4_molecules_dropped", "drugs_with_boxed_warning")}
    results = {
        "protocol_version": 1, "generated_at": "2026-10-17T00:00:00+00:00", "openfda_network_calls": 0,
        "inputs": {"git_commit": "abc", "seed": measures.SEED, "shuffles": measures.SHUFFLES,
                   "drug_set": {"sha256": "0" * 64, "generated_at": "t",
                                "sources": {"chembl_release": "ChEMBL_37", "chembl_release_date": "d", "helix_commit": "h"}},
                   "mappings": {"path": "data/mappings/hpo.json", "sha256": None if blocked else "1" * 64, "model": "m"}},
        "status": {"gemini_key": not blocked, "openfda_key": True, "blocked": blocked, "complete": not blocked,
                   "mapping_problem": None, "engine_failures": [], "real_predictions": 7,
                   "real_predictions_unmapped": 7 if blocked else 0, "terms_mapped": 0, "terms_needed": 2},
        "drug_set": {"counts": counts, "step4_dropped": [{"name": "Zanubrutinib", "reason": "no label"}]},
        "drugs": [], "mapping_review": {"status": "not_drawn"},
        "checks": {"drug_set_targets_match_engine": []},
    }
    if blocked:
        results["measures"] = {name: {"status": "blocked", "reason": blocked} for name in (
            "label_precision", "report_precision", "label_precision_lift", "report_precision_lift",
            "boxed_warning_recall", "candidate_new_signals")}
        results["misses"] = {"status": "blocked", "reason": blocked}
    else:
        results["measures"] = computed["measures"]
        results["misses"] = computed["misses"]
        results["checks"]["label_index_agrees_with_engine"] = computed["label_check"]
    return results


def test_compute_measures_end_to_end_and_render_caveats_beside_every_number(reports):
    phenotypes = {disease_id: [SimpleNamespace(hpo_id=f"HP:{disease_id}")] for disease_id in ("D2", "D3", "D4", "D5")}
    stored = {
        "HP:D2": TermMapping("HP:D2", "infection", "clinical", ("SERIOUS INFECTION",), ()),
        "HP:D3": TermMapping("HP:D3", "neutropenia", "laboratory", ("NEUTROPENIA",), ()),
        "HP:D4": TermMapping("HP:D4", "malformation", "developmental", ("X",), ()),
        "HP:D5": TermMapping("HP:D5", "headache", "clinical", ("HEADACHE",), ()),
    }
    contexts = {
        row["molecule"]["chembl_id"]: FakeContext({"boxed_warning": "WARNING: SERIOUS INFECTIONS."},
                                                  {"NEUTROPENIA": 40}, row["drug_reports"])
        for row in reports
    }
    computed = score.compute_measures(reports, POOL, stored, contexts, with_reports=True,
                                      phenotypes=lambda disease_id: phenotypes.get(disease_id, []))
    found = computed["measures"]
    assert found["label_precision"]["clinical"]["value"] == 0.2
    lift = found["label_precision_lift"]["clinical"]
    assert lift["shuffles"] == 100 and 0 <= lift["shuffle_mean"] <= 1
    assert found["report_precision_lift"]["laboratory"]["with_on_label"]["shuffles"] == 100
    assert found["boxed_warning_recall"]["any_kind"]["value"] == 0.5
    assert len(found["candidate_new_signals"]) == 1
    assert computed["label_check"]["predictions_checked"] == 6

    rendered = report.render(_results(computed, None))
    assert "| Clinical | 1 / 5 (20.0%)" in rendered
    for line in rendered.splitlines():
        if line.startswith(("| Clinical", "| Laboratory", "| Any kind")):
            assert any(phrase in line for phrase in CAVEAT_PHRASES), line


def test_measure_four_is_not_run_without_the_openfda_key(reports):
    contexts = {row["molecule"]["chembl_id"]: FakeContext({}, {}, row["drug_reports"]) for row in reports}
    computed = score.compute_measures(reports, POOL, {}, contexts, with_reports=False, phenotypes=lambda _: [])
    assert computed["measures"]["report_precision_lift"]["status"] == "not_run"
    assert "OPENFDA_API_KEY" in computed["measures"]["report_precision_lift"]["reason"]


def test_blocked_results_render_without_numbers():
    rendered = report.render(_results(None, "scoring is blocked on step 5: GEMINI_API_KEY is not set"))
    assert "Scoring is blocked on step 5" in rendered
    measures_part = rendered.split("## Measures")[1].split("## Caveats in full")[0]
    assert "%" not in measures_part
    assert measures_part.count("Not computed") == 7
