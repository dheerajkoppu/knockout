"""Score the drug set as benchmark/PROTOCOL.md states; writes benchmark/results/results.json and RESULTS.md.

Run from the repository root:
  .venv/bin/python -m benchmark.score                      scored run, reads only data/mappings/hpo.json
  .venv/bin/python -m benchmark.score --generate-mappings  first maps every phenotype the benchmark needs (Gemini)
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from benchmark import measures
from benchmark.report import render
from knockout import config, genetics, mapping, observability, openfda
from knockout.engine import predict
from knockout.gemini import GeminiUnavailable
from knockout.http import SourceError, is_cached
from knockout.signals import TermCounts

BENCHMARK_DIR = Path(__file__).resolve().parent
DRUG_SET_PATH = BENCHMARK_DIR / "drug_set.json"
RESULTS_DIR = BENCHMARK_DIR / "results"
REPORTS_DIR = RESULTS_DIR / "reports"
RESULTS_JSON = RESULTS_DIR / "results.json"
RESULTS_MD = RESULTS_DIR / "RESULTS.md"
REVIEW_CSV = RESULTS_DIR / "mapping_review.csv"
PROTOCOL_VERSION = 2
TOP_REACTIONS = 1000
# Without a key openFDA allows about 1,000 requests a day per address; leave room for the demo.
KEYLESS_OPENFDA_BUDGET = 600
OPENFDA_INTERVAL_WITHOUT_KEY = 1.6
OPENFDA_INTERVAL_WITH_KEY = 0.27


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class OpenFdaBudget:
    """Wraps openFDA's fetch: paces uncached requests and stops at a budget instead of exhausting the daily limit."""

    def __init__(self, fetch, limit: int | None) -> None:
        self.fetch = fetch
        self.limit = limit
        self.interval = OPENFDA_INTERVAL_WITH_KEY if config.openfda_api_key() else OPENFDA_INTERVAL_WITHOUT_KEY
        self.network_calls = 0
        self._last_call = 0.0

    def __call__(self, url: str, *, cache_key: str | None = None, not_found_ok: bool = False):
        if not is_cached(cache_key or url):
            if self.limit is not None and self.network_calls >= self.limit:
                raise SourceError(f"the benchmark's budget of {self.limit} uncached openFDA requests is spent")
            wait = self.interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self.network_calls += 1
            self._last_call = time.monotonic()
        return self.fetch(url, cache_key=cache_key, not_found_ok=not_found_ok)


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT_DIR, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def disease_pool() -> dict[str, list[tuple[str, str]]]:
    """Every catalog disease with a known direction, as (disease id, gene) pairs, by direction."""
    pool: dict[str, set[tuple[str, str]]] = {}
    for gene in genetics.catalog().genes:
        for disease in genetics.diseases(gene):
            direction = genetics.disease_direction(disease, gene.symbol).direction
            if direction != "unknown":
                pool.setdefault(direction, set()).add((disease.id, gene.symbol))
    return {direction: sorted(pairs) for direction, pairs in sorted(pool.items())}


@cache
def _phenotypes(disease_id: str) -> tuple:
    return tuple(genetics.qualifying_phenotypes(genetics.catalog().disease(disease_id)))


def needed_terms(pool: dict[str, list[tuple[str, str]]]) -> dict[str, str]:
    """Every HPO term a real or shuffled prediction can use: the qualifying phenotypes of the whole pool."""
    terms: dict[str, str] = {}
    for pairs in pool.values():
        for disease_id, _ in pairs:
            for phenotype in _phenotypes(disease_id):
                terms.setdefault(phenotype.hpo_id, phenotype.label or phenotype.hpo_id)
    return dict(sorted(terms.items()))


def generate_mappings(terms: dict[str, str]) -> str | None:
    try:
        mapping.ensure(terms)
    except GeminiUnavailable as error:
        return f"step 5 could not run: {error}"
    except SourceError as error:
        return f"step 5 stopped part way (progress is saved): {error}"
    return None


def run_engine(drugs: list[dict], generate: bool) -> tuple[list[dict], list[dict]]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports, failures = [], []
    for position, drug in enumerate(drugs, start=1):
        _log(f"engine {position}/{len(drugs)}: {drug['name']}")
        try:
            report = predict(drug["chembl_id"], generate_mappings=generate).to_dict()
        except Exception as error:  # noqa: BLE001  one failed source fails one drug, not the run
            failures.append({"drug": drug["name"], "chembl_id": drug["chembl_id"], "error": f"{type(error).__name__}: {error}"})
            continue
        if report["molecule"] is None:
            failures.append({"drug": drug["name"], "chembl_id": drug["chembl_id"], "error": "; ".join(report["problems"])})
            continue
        (REPORTS_DIR / f"{drug['chembl_id']}.json").write_text(json.dumps(report, default=str) + "\n")
        reports.append(report)
    return reports, failures


class DrugContext:
    """One drug's label index and FAERS totals, shared by the real and the shuffled arm."""

    def __init__(self, report: dict) -> None:
        self.report = report
        self.chembl_id = report["molecule"]["chembl_id"]
        self.generic_name = report["molecule"]["name"].lower()
        label = openfda.label(self.generic_name) if report.get("label") else None
        self.label = measures.LabelIndex(label.sections if label else None)
        self.top_reactions: dict[str, int] | None = None

    def load_top_reactions(self) -> None:
        url, public = openfda._url(
            "event",
            openfda.drug_search(self.generic_name),
            f"&count=patient.reaction.reactionmeddrapt.exact&limit={TOP_REACTIONS}",
        )
        body = openfda.get_json(url, cache_key=public, not_found_ok=True)
        self.top_reactions = {row["term"]: int(row["count"]) for row in (body or {}).get("results", [])}

    def top_counts(self, terms: list[str]) -> list[TermCounts]:
        drug_reports, all_reports = self.report.get("drug_reports"), self.report.get("all_reports")
        if self.top_reactions is None or drug_reports is None or not all_reports:
            return []
        return [
            TermCounts(
                term=term,
                a=self.top_reactions.get(term, 0),
                drug=drug_reports,
                reaction=openfda.total(openfda.reaction_search(term)),
                all=all_reports,
            )
            for term in terms
        ]


def shuffle_drug(report: dict) -> measures.ShuffleDrug:
    directions = Counter(disease["direction"] for disease in report["diseases"] if disease["pairing"] == "use")
    excluded = {target["gene"] for target in report["targets"] if target.get("gene")}
    for target in report["targets"]:
        gene = genetics.gene_for_accession(target["accession"]) if target.get("accession") else None
        if gene is not None:
            excluded.add(gene.symbol)
    return measures.ShuffleDrug(report["molecule"]["chembl_id"], dict(directions), excluded)


class ShuffledArm:
    """Predictions from shuffled diseases, built with the engine's rules and memoised per drug and phenotype."""

    def __init__(self, contexts: dict, mappings: dict, with_reports: bool, phenotypes=None) -> None:
        self.contexts = contexts
        self.mappings = mappings
        self.with_reports = with_reports
        self.phenotypes = phenotypes or _phenotypes
        self._memo: dict[tuple[str, str], dict | None] = {}

    def prediction(self, drug_id: str, hpo_id: str) -> dict | None:
        key = (drug_id, hpo_id)
        if key not in self._memo:
            mapped = self.mappings.get(hpo_id)
            if mapped is not None and mapped.kind == "developmental":
                self._memo[key] = None
            else:
                context = self.contexts[drug_id]
                terms = list(mapped.reaction_terms) if mapped else []
                on_label = context.label.any_term(terms)
                counts = context.top_counts(terms) if self.with_reports and terms else []
                self._memo[key] = {
                    "kind": mapped.kind if mapped else None,
                    "verdict": measures.verdict(on_label, counts, bool(terms)) if self.with_reports
                    else ("on_label" if on_label else "not_on_label"),
                    "counts": measures.counts_as_dicts(counts),
                }
        return self._memo[key]

    def predictions(self, assignment: dict[str, list[tuple[str, str]]]) -> list[dict]:
        rows = []
        for drug_id, pairs in assignment.items():
            for disease_id, _ in pairs:
                for phenotype in self.phenotypes(disease_id):
                    row = self.prediction(drug_id, phenotype.hpo_id)
                    if row is not None:
                        rows.append(row)
        return rows


def real_top_arm(reports: list[dict], contexts: dict[str, DrugContext]) -> list[dict]:
    """The real arm re-read with each drug's 1,000 most-reported terms, as measure 4 requires."""
    rows = []
    for report in reports:
        context = contexts[report["molecule"]["chembl_id"]]
        for prediction in report["predictions"]:
            terms = prediction["reaction_terms"]
            on_label = prediction["verdict"] == "on_label"
            counts = context.top_counts(terms) if terms else []
            rows.append({
                "kind": prediction["kind"],
                "verdict": measures.verdict(on_label, counts, bool(terms)),
                "counts": measures.counts_as_dicts(counts),
            })
    return rows


def label_check(reports: list[dict], contexts: dict[str, DrugContext]) -> dict:
    """The shuffled arm's fast label test must agree with the engine on every real prediction."""
    checked, disagreements = 0, []
    for report in reports:
        context = contexts[report["molecule"]["chembl_id"]]
        for prediction in report["predictions"]:
            if not prediction["reaction_terms"]:
                continue
            checked += 1
            if context.label.any_term(prediction["reaction_terms"]) != (prediction["label_sentence"] is not None):
                disagreements.append({"drug": report["molecule"]["name"], "hpo_id": prediction["hpo_id"]})
    return {"predictions_checked": checked, "disagreements": disagreements}


def target_check(drugs: list[dict], reports: list[dict]) -> list[dict]:
    """Drugs whose engine run did not use the genes that brought them into the set."""
    expected = {drug["chembl_id"]: drug for drug in drugs}
    rows = []
    for report in reports:
        drug = expected[report["query"]]
        drug_set_genes = sorted({target["gene"] for target in drug["reason"]["targets"]})
        engine_genes = sorted({target["gene"] for target in report["targets"] if target["used"]})
        if drug_set_genes != engine_genes:
            rows.append({
                "drug": drug["name"],
                "chembl_id": drug["chembl_id"],
                "drug_set_genes": drug_set_genes,
                "engine_genes": engine_genes,
                "salt_form_records": sorted({
                    salt for target in drug["reason"]["targets"] for salt in target["records_on_salt_forms"]
                }),
            })
    return rows


def mapping_review() -> dict:
    """Agreement on the 50-mapping sample, once a team member has filled in mapping_review.csv."""
    if not REVIEW_CSV.exists():
        return {"status": "not_drawn", "reason": "benchmark/results/mapping_review.csv does not exist yet"}
    with REVIEW_CSV.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    reviewed = [row for row in rows if (row.get("kind_correct") or "").strip() and (row.get("terms_correct") or "").strip()]
    if not reviewed:
        return {"status": "not_reviewed", "sample_size": len(rows), "reason": "no row has been reviewed yet"}

    def agreed(column: str) -> int:
        return sum(row[column].strip().lower() == "yes" for row in reviewed)

    return {
        "status": "reviewed" if len(reviewed) == len(rows) else "partly_reviewed",
        "sample_size": len(rows),
        "reviewed": len(reviewed),
        "kind_agreement": measures.ratio(agreed("kind_correct"), len(reviewed)),
        "terms_agreement": measures.ratio(agreed("terms_correct"), len(reviewed)),
    }


def _drug_summary(report: dict) -> dict:
    predictions = report["predictions"]
    return {
        "drug": report["molecule"]["name"],
        "chembl_id": report["molecule"]["chembl_id"],
        "targets_used": sorted({target["gene"] for target in report["targets"] if target["used"]}),
        "diseases_used": [disease["name"] for disease in report["diseases"] if disease["pairing"] == "use"],
        "predictions": len(predictions),
        "by_kind": dict(Counter(prediction["kind"] or "unmapped" for prediction in predictions)),
        "by_verdict": dict(Counter(prediction["verdict"] for prediction in predictions)),
        "excluded_developmental": len(report["excluded_developmental"]),
        "drug_reports": report.get("drug_reports"),
        "has_boxed_warning": "boxed_warning" in ((report.get("label") or {}).get("sections") or []),
        "problems": report["problems"],
    }


def _not_computed(reason: str) -> dict:
    return {"status": "blocked", "reason": reason}


def compute_measures(reports: list[dict], pool: dict, stored: dict, contexts: dict, *, with_reports: bool,
                     phenotypes=None) -> dict:
    """Measures 1 to 6 in the protocol's order, the miss buckets, and the label-test check."""
    real = [prediction for report in reports for prediction in report["predictions"]]
    results_measures: dict = {}

    results_measures["label_precision"] = {kind: measures.label_precision(real, kind) for kind in measures.KINDS}
    results_measures["report_precision"] = {
        kind: {
            "with_on_label": measures.report_precision(real, kind),
            "without_on_label": measures.report_precision(real, kind, include_on_label=False),
        }
        for kind in measures.KINDS
    }

    assignments = measures.shuffles([shuffle_drug(report) for report in reports], pool)
    label_arm = ShuffledArm(contexts, stored, with_reports=False, phenotypes=phenotypes)
    label_values = {kind: [] for kind in measures.KINDS}
    for assignment in assignments:
        shuffled = label_arm.predictions(assignment)
        for kind in measures.KINDS:
            label_values[kind].append(measures.label_precision(shuffled, kind)["value"])
    results_measures["label_precision_lift"] = {
        kind: measures.lift(results_measures["label_precision"][kind]["value"], label_values[kind])
        | {"shuffle_values": label_values[kind]}
        for kind in measures.KINDS
    }

    if not with_reports:
        results_measures["report_precision_lift"] = {
            "status": "not_run",
            "reason": "measure 4 reads each drug's 1,000 most-reported reaction terms from the openFDA count "
            "endpoint, which needs OPENFDA_API_KEY; it is not set in .env",
        }
    else:
        try:
            for context in contexts.values():
                context.load_top_reactions()
            real_top = real_top_arm(reports, contexts)
            report_arm = ShuffledArm(contexts, stored, with_reports=True, phenotypes=phenotypes)
            report_values = {(kind, flag): [] for kind in measures.KINDS for flag in (True, False)}
            for assignment in assignments:
                shuffled = report_arm.predictions(assignment)
                for (kind, flag), values in report_values.items():
                    values.append(measures.report_precision(shuffled, kind, include_on_label=flag)["value"])
            results_measures["report_precision_lift"] = {
                kind: {
                    ("with_on_label" if flag else "without_on_label"): measures.lift(
                        measures.report_precision(real_top, kind, include_on_label=flag)["value"],
                        report_values[(kind, flag)],
                    ) | {"real_counts": measures.report_precision(real_top, kind, include_on_label=flag),
                         "shuffle_values": report_values[(kind, flag)]}
                    for flag in (True, False)
                }
                for kind in measures.KINDS
            }
        except SourceError as error:
            results_measures["report_precision_lift"] = {"status": "not_run", "reason": f"a source failed: {error}"}

    results_measures["boxed_warning_recall"] = {
        "clinical": measures.boxed_warning_recall(reports, "clinical"),
        "laboratory": measures.boxed_warning_recall(reports, "laboratory"),
        "any_kind": measures.boxed_warning_recall(reports),
    }
    results_measures["candidate_new_signals"] = measures.candidate_new_signals(reports)
    return {
        "measures": results_measures,
        "misses": measures.classify_misses(reports),
        "label_check": label_check(reports, contexts),
    }


def score(arguments: argparse.Namespace) -> dict:
    drug_set = json.loads(DRUG_SET_PATH.read_text())
    budget = OpenFdaBudget(openfda.get_json, arguments.openfda_budget)
    openfda.get_json = budget

    pool = disease_pool()
    terms = needed_terms(pool)
    mapping_problem = generate_mappings(terms) if arguments.generate_mappings else None

    # The pool covers every drug-set phenotype, so after a failed mapping pass the engine only reads stored ones.
    reports, failures = run_engine(drug_set["drugs"], arguments.generate_mappings and mapping_problem is None)
    stored = mapping.stored(terms)
    real = [prediction for report in reports for prediction in report["predictions"]]
    unmapped = sum(prediction["kind"] is None for prediction in real)
    status = {
        "gemini_key": bool(config.gemini_api_key()),
        "openfda_key": bool(config.openfda_api_key()),
        "mappings_file": str(config.MAPPINGS_PATH.relative_to(config.ROOT_DIR)),
        "mappings_file_exists": config.MAPPINGS_PATH.exists(),
        "terms_needed": len(terms),
        "terms_mapped": len(stored),
        "real_predictions": len(real),
        "real_predictions_unmapped": unmapped,
        "mapping_problem": mapping_problem,
        "engine_failures": failures,
    }
    blocked_reason = None
    if not real:
        blocked_reason = "the engine produced no predictions"
    elif unmapped == len(real):
        why = "GEMINI_API_KEY is not set in .env" if not config.gemini_api_key() else (
            mapping_problem or "data/mappings/hpo.json holds no mapping for these phenotypes; run with --generate-mappings")
        blocked_reason = (
            f"scoring is blocked on step 5: {why}, so none of the {len(real)} predictions has a kind or "
            "reaction terms, and no label or report check could run"
        )
    status["blocked"] = blocked_reason
    status["openfda_budget_spent"] = budget.limit is not None and budget.network_calls >= budget.limit
    status["predictions_with_a_failed_source"] = sum(
        (prediction["reason"] or "").startswith("openFDA reports unavailable") for prediction in real)
    status["drugs_with_a_failed_source"] = sorted(
        (report.get("molecule") or {}).get("name") or report["query"]
        for report in reports
        if any(problem.startswith("openFDA reports unavailable") for problem in report.get("problems") or [])
    )
    status["complete"] = (
        blocked_reason is None and unmapped == 0 and not failures and len(stored) == len(terms)
        and not status["predictions_with_a_failed_source"] and not status["drugs_with_a_failed_source"]
    )

    results: dict = {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generated_by": "benchmark/score.py",
        "inputs": {
            "git_commit": _git_commit(),
            "drug_set": {"path": "benchmark/drug_set.json", "sha256": _sha256(DRUG_SET_PATH),
                         "generated_at": drug_set["generated_at"], "sources": drug_set["sources"]},
            "mappings": {"path": status["mappings_file"], "sha256": _sha256(config.MAPPINGS_PATH),
                         "model": json.loads(config.MAPPINGS_PATH.read_text()).get("model")
                         if config.MAPPINGS_PATH.exists() else None},
            "seed": measures.SEED,
            "shuffles": measures.SHUFFLES,
            "generate_mappings": arguments.generate_mappings,
        },
        "status": status,
        "drug_set": {"counts": drug_set["counts"], "step4_dropped": [
            {"name": row["name"], "reason": row["reason"]} for row in drug_set["dropped"]["step4"]]},
        "drugs": [_drug_summary(report) for report in reports],
        "mapping_review": mapping_review(),
        "checks": {"drug_set_targets_match_engine": target_check(drug_set["drugs"], reports)},
    }

    if blocked_reason:
        results["measures"] = {name: _not_computed(blocked_reason) for name in (
            "label_precision", "report_precision", "label_precision_lift", "report_precision_lift",
            "boxed_warning_recall", "candidate_new_signals")}
        results["misses"] = _not_computed(blocked_reason)
        results["openfda_network_calls"] = budget.network_calls
        return results

    contexts = {report["molecule"]["chembl_id"]: DrugContext(report) for report in reports}
    computed = compute_measures(reports, pool, stored, contexts, with_reports=bool(config.openfda_api_key()))
    results["measures"] = computed["measures"]
    results["misses"] = computed["misses"]
    results["checks"]["label_index_agrees_with_engine"] = computed["label_check"]
    results["openfda_network_calls"] = budget.network_calls
    return results


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmark.score")
    parser.add_argument("--generate-mappings", action="store_true",
                        help="map every phenotype the benchmark needs with Gemini before scoring (writes hpo.json)")
    parser.add_argument("--openfda-budget", type=int,
                        default=None if config.openfda_api_key() else KEYLESS_OPENFDA_BUDGET,
                        help="stop after this many uncached openFDA requests (default: none with a key, "
                        f"{KEYLESS_OPENFDA_BUDGET} without)")
    arguments = parser.parse_args()
    observability.setup()
    if not DRUG_SET_PATH.exists():
        _log("benchmark/drug_set.json is missing; run python -m benchmark.drug_set first")
        return 1
    results = score(arguments)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, indent=1, default=str) + "\n")
    RESULTS_MD.write_text(render(results))
    _log(f"wrote {RESULTS_JSON} and {RESULTS_MD}")
    if results["status"]["blocked"]:
        _log(results["status"]["blocked"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
