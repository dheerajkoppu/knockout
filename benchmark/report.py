"""Render benchmark/results/results.json as RESULTS.md, with the protocol's caveats beside every number."""

from benchmark import measures

CAVEATS = {
    "voluntary": "FAERS reports are voluntary and uneven; counts are not incidence",
    "circular": "a boxed warning raises reporting of the reaction it warns about, so a signal for a labelled "
    "effect is partly circular",
    "indication": "patients on immune drugs have immune diseases, so an infection report may come from the "
    "disease rather than the drug",
    "milder": "a lifelong genetic loss is stronger than partial inhibition, so an effect may be milder or absent",
    "generic_name": "the drug match on generic name relies on openFDA's harmonised fields, which not every "
    "report or label has",
    "top_terms": "both arms read reports from the drug's 1,000 most-reported terms; a term outside them counts "
    "as no signal",
    "shuffle": "100 shuffles, seed 20261017, same direction, the drug's own target genes excluded",
}

KIND_NAMES = {"clinical": "Clinical", "laboratory": "Laboratory", "any_kind": "Any kind"}


def _mapping_caveat(review: dict) -> str:
    if review.get("status") in ("reviewed", "partly_reviewed"):
        kind, terms = review["kind_agreement"], review["terms_agreement"]
        return (
            f"in the reviewed sample of {review['reviewed']}, the kind agreed for {kind['numerator']} and the "
            f"reaction terms for {terms['numerator']}"
        )
    return "the 50-mapping review sample has not been checked yet"


def _caveats(results: dict, *keys: str) -> str:
    texts = [
        CAVEATS[key] if key != "mapping" else f"step 5 is a model output; {_mapping_caveat(results['mapping_review'])}"
        for key in keys
    ]
    return "; ".join(texts)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _fraction(row: dict) -> str:
    if not row["denominator"]:
        return "no predictions of this kind (0 / 0)"
    return f"{row['numerator']} / {row['denominator']} ({_percent(row['value'])})"


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return lines + [""]


def _not_computed(measure: dict) -> list[str]:
    word = "Not run" if measure.get("status") == "not_run" else "Not computed"
    return [f"{word}: {measure['reason']}.", ""]


def _header(results: dict) -> list[str]:
    inputs = results["inputs"]
    mappings = inputs["mappings"]
    status = results["status"]
    lines = [
        f"# Knockout benchmark results, protocol version {results['protocol_version']}",
        "",
        (f"Generated {results['generated_at']} by `benchmark/score.py` at commit `{inputs['git_commit']}`. "
        "Every rule is in [PROTOCOL.md](../PROTOCOL.md); this file is written by the script and never edited by hand."),
        "",
        (f"- Drug set: `benchmark/drug_set.json`, sha256 `{(inputs['drug_set']['sha256'] or '')[:16]}`, generated "
        f"{inputs['drug_set']['generated_at']} from {inputs['drug_set']['sources']['chembl_release']} and Helix "
        f"`{inputs['drug_set']['sources']['helix_commit']}`."),
        f"- Mappings: `{mappings['path']}`, "
        + (f"sha256 `{mappings['sha256'][:16]}`, model `{mappings['model']}`." if mappings["sha256"]
           else "missing (step 5 has not run)."),
        f"- Shuffles: {inputs['shuffles']}, seed {inputs['seed']}.",
        (f"- Keys: GEMINI_API_KEY {'set' if status['gemini_key'] else 'not set'}, "
        f"OPENFDA_API_KEY {'set' if status['openfda_key'] else 'not set'}. "
        f"Uncached openFDA requests this run: {results['openfda_network_calls']}."),
        "",
        "## Status",
        "",
    ]
    if status["blocked"]:
        lines += [
            f"> **{status['blocked'][0].upper() + status['blocked'][1:]}.**",
            "> No precision, lift, recall or signal number below was computed; each measure says why.",
            "",
        ]
    elif not status["complete"]:
        lines += [
            ("> **This run is incomplete.** "
            f"{status['real_predictions_unmapped']} of {status['real_predictions']} predictions have no mapping, "
            f"{status['terms_mapped']} of {status['terms_needed']} phenotypes the benchmark needs are mapped, and "
            f"{len(status['engine_failures'])} drug(s) failed, and "
            f"{status.get('predictions_with_a_failed_source', 0)} prediction(s) lost their report counts to a "
            "failed openFDA request. Numbers below cover only what ran."),
            "",
        ]
        if status.get("openfda_budget_spent"):
            lines += ["> The run's budget of uncached openFDA requests was spent; set OPENFDA_API_KEY and rerun.", ""]
    else:
        lines += [(f"Complete: every one of the {status['terms_needed']} phenotypes the benchmark needs is mapped, "
                  "and every drug in the set ran."), ""]
    if status["mapping_problem"]:
        lines += [f"Mapping: {status['mapping_problem']}.", ""]
    for failure in status["engine_failures"]:
        lines.append(f"- Engine failed for {failure['drug']} ({failure['chembl_id']}): {failure['error']}")
    if status["engine_failures"]:
        lines.append("")
    return lines


def _drug_set(results: dict) -> list[str]:
    counts = results["drug_set"]["counts"]
    sources = results["inputs"]["drug_set"]["sources"]
    lines = ["## Drug set", ""]
    lines += _table(
        ["Step", "Kept", "Dropped", "Caveat beside these numbers"],
        [
            ["1. Catalog genes with a UniProt accession and a disease of known direction",
             f"{counts['step1_genes_kept']} genes", f"{counts['step1_genes_dropped']} genes",
             "direction from IUIS, then Orphanet product 6, then the words of the disease name"],
            ["2. ChEMBL mechanism records on a SINGLE PROTEIN, Homo sapiens target, max phase 4",
             f"{counts['step2_records_kept']} records", f"{counts['step2_candidates_dropped']} candidates",
             (f"{sources['chembl_release']} ({sources['chembl_release_date']}); a drug recorded against a protein "
             "family or complex is dropped here")],
            ["3. Effect matches a disease direction", f"{counts['step3_molecules_kept']} molecules",
             f"{counts['step3_pairs_dropped']} molecule-target pairs",
             "effect from Helix molecule_effect(); records that disagree give unknown"],
            ["4. openFDA holds a label for the generic name", f"{counts['step4_drugs_kept']} drugs",
             f"{counts['step4_molecules_dropped']} molecules", CAVEATS["generic_name"]],
            ["Drugs in the set with a boxed warning", f"{counts['drugs_with_boxed_warning']} drugs", "",
             "most recent label by effective_time"],
        ],
    )
    dropped = results["drug_set"]["step4_dropped"]
    if dropped:
        lines += ["Dropped at step 4: " + ", ".join(row["name"] for row in dropped) + ". Every drop at every step, "
                  "with its reason, is in `benchmark/drug_set.json`.", ""]
    return lines


def _drugs(results: dict) -> list[str]:
    if not results["drugs"]:
        return []
    lines = ["## Drugs scored", ""]
    rows = [
        [
            drug["drug"],
            ", ".join(drug["targets_used"]),
            "; ".join(drug["diseases_used"]),
            drug["predictions"],
            drug["by_kind"].get("unmapped", 0),
            "n/a" if drug["drug_reports"] is None else f"{drug['drug_reports']:,}",
            "yes" if drug["has_boxed_warning"] else "no",
        ]
        for drug in results["drugs"]
    ]
    lines += _table(["Drug", "Genes used", "Diseases used", "Predictions", "Unmapped", "FAERS reports",
                     "Boxed warning"], rows)
    lines += [(f"Caveats beside these numbers: FAERS reports: {CAVEATS['voluntary']}; {CAVEATS['generic_name']}. "
              f"Predictions: {CAVEATS['milder']}."), ""]
    return lines


def _measure_rows(results: dict) -> list[str]:
    found = results["measures"]
    lines = ["## Measures", "", "Clinical first, as the protocol orders them.", ""]

    lines += ["### 1. Label precision", ""]
    if "status" in found["label_precision"]:
        lines += _not_computed(found["label_precision"])
    else:
        lines += _table(["Kind", "On the label / all predictions", "Caveats beside this number"], [
            [KIND_NAMES[kind], _fraction(found["label_precision"][kind]), _caveats(results, "milder", "mapping")]
            for kind in measures.KINDS
        ])

    lines += ["### 2. Report precision", ""]
    if "status" in found["report_precision"]:
        lines += _not_computed(found["report_precision"])
    else:
        rows = []
        for kind in measures.KINDS:
            rows.append([KIND_NAMES[kind], "with on-label predictions",
                         _fraction(found["report_precision"][kind]["with_on_label"]),
                         _caveats(results, "voluntary", "circular", "indication", "generic_name", "mapping")])
            rows.append([KIND_NAMES[kind], "without on-label predictions",
                         _fraction(found["report_precision"][kind]["without_on_label"]),
                         _caveats(results, "voluntary", "indication", "generic_name", "mapping")])
        lines += _table(["Kind", "Variant", "With a report signal / verdict not unknown", "Caveats beside this number"],
                        rows)

    lines += ["### 3. Lift over shuffled diseases, label precision", ""]
    if "status" in found["label_precision_lift"]:
        lines += _not_computed(found["label_precision_lift"])
    else:
        lines += _table(["Kind", "Real", "Shuffle mean", "Share of shuffles at or above real",
                         "Caveats beside these numbers"], [
            [KIND_NAMES[kind], _percent(row["real"]), _percent(row["shuffle_mean"]),
             _percent(row["share_at_or_above"]), _caveats(results, "shuffle", "milder", "mapping")]
            for kind, row in found["label_precision_lift"].items()
        ])

    lines += ["### 4. Lift over shuffled diseases, report precision", ""]
    if "status" in found["report_precision_lift"]:
        lines += _not_computed(found["report_precision_lift"])
    else:
        rows = []
        for kind, variants in found["report_precision_lift"].items():
            for variant, row in variants.items():
                rows.append([KIND_NAMES[kind], variant.replace("_", " "), _percent(row["real"]),
                             _percent(row["shuffle_mean"]), _percent(row["share_at_or_above"]),
                             _caveats(results, "top_terms", "shuffle", "voluntary", "indication", "generic_name")
                             + ("; " + CAVEATS["circular"] if variant == "with_on_label" else "")])
        lines += _table(["Kind", "Variant", "Real", "Shuffle mean", "Share of shuffles at or above real",
                         "Caveats beside these numbers"], rows)
        lines += ["The exact counts from step 7 for the real arm are measure 2 above.", ""]

    lines += ["### 5. Boxed-warning recall", ""]
    if "status" in found["boxed_warning_recall"]:
        lines += _not_computed(found["boxed_warning_recall"])
    else:
        recall = found["boxed_warning_recall"]
        lines += _table(["Kind", "Boxed warnings with a matched sentence / drugs with a boxed warning",
                         "Caveats beside this number"], [
            [KIND_NAMES[kind], _fraction(recall[kind]), _caveats(results, "milder", "mapping")]
            for kind in ("clinical", "laboratory", "any_kind")
        ])
        lines += _table(["Drug with a boxed warning", "Matched", "Phenotypes", "Sentence"], [
            [row["drug"], "yes" if row["matched"] else "no", "; ".join(row["phenotypes"]),
             " / ".join(sentence[:200] for sentence in row["sentences"])]
            for row in recall["any_kind"]["drugs"]
        ])

    lines += ["### 6. Candidate new signals", ""]
    signals = found["candidate_new_signals"]
    if isinstance(signals, dict):
        lines += _not_computed(signals)
    elif not signals:
        lines += ["None: no clinical prediction had a report signal without a label sentence.", ""]
    else:
        rows = []
        for row in signals:
            counts = "; ".join(
                f"{count['term']}: {count['a']} of {count['drug']:,} drug reports, PRR {count['prr']:.1f}, "
                f"chi-squared {count['chi_squared']:.1f}"
                for count in row["signal_counts"]
            )
            rows.append([row["drug"], f"{row['gene']} -> {row['disease']}", f"{row['phenotype']} ({row['hpo_id']})",
                         counts, _caveats(results, "voluntary", "indication", "generic_name", "milder", "mapping")])
        lines += [f"{len(signals)} candidate(s). Each is a hypothesis from reports, not a finding.", ""]
        lines += _table(["Drug", "Gene -> disease", "Phenotype", "Signal counts", "Caveats beside these numbers"], rows)
    return lines


def _misses(results: dict) -> list[str]:
    lines = ["## Misses", ""]
    misses = results["misses"]
    if "status" in misses:
        return lines + _not_computed(misses)
    lines += [("Every prediction that is neither on the label nor a report signal, in exactly one bucket, in the "
              "protocol's order. Each miss is listed in `results.json`."), ""]
    rows = [
        [KIND_NAMES.get(kind, kind), bucket, count, _caveats(results, "voluntary", "milder")]
        for kind, buckets in misses["buckets"].items()
        for bucket, count in buckets.items()
    ]
    return lines + _table(["Kind", "Bucket", "Predictions", "Caveats beside this number"], rows)


def _checks(results: dict) -> list[str]:
    checks = results.get("checks") or {}
    lines = ["## Checks", ""]
    targets = checks.get("drug_set_targets_match_engine")
    if targets is not None:
        if targets:
            lines += [(f"For {len(targets)} drug(s) the engine did not use the gene that brought the drug into the "
                       "set, so the predictions that gene gives are missing from every measure until the two agree:"),
                      ""]
            lines += _table(["Drug", "Genes in the drug set", "Genes the engine used", "Mechanism records on salt forms"],
                            [[row["drug"], ", ".join(row["drug_set_genes"]), ", ".join(row["engine_genes"]) or "none",
                              ", ".join(row["salt_form_records"]) or "none"] for row in targets])
        else:
            lines += ["Every drug's engine run used the genes that brought it into the set.", ""]
    label = checks.get("label_index_agrees_with_engine")
    if label is not None:
        lines += [(f"The shuffled arm's label test was compared with the engine on {label['predictions_checked']} "
                   f"real predictions with reaction terms: {len(label['disagreements'])} disagreement(s)."), ""]
    return lines if len(lines) > 2 else []


def _caveat_list(results: dict) -> list[str]:
    return ["## Caveats in full", "",
            "- FAERS reports are voluntary and uneven, and counts are not incidence.",
            ("- A boxed warning increases reporting of the reaction it warns about, so a report signal for a labelled "
            "effect is partly circular. Report precision is shown with and without on-label predictions."),
            ("- Patients taking immune drugs have immune diseases, so an infection report may come from the disease "
            "rather than the drug."),
            ("- A lifelong genetic loss is stronger than partial inhibition by a drug, so a predicted effect may be "
            "milder or absent."),
            "- The drug match on generic name relies on openFDA's harmonised fields, which not every report has.",
            ("- The mapping in step 5 is a model output. A sample of 50 mappings, drawn with seed 20261017, is "
             f"checked by a team member: {_mapping_caveat(results['mapping_review'])}."),
            ""]


def render(results: dict) -> str:
    lines = _header(results) + _drug_set(results) + _drugs(results) + _measure_rows(results)
    lines += _misses(results) + _checks(results) + _caveat_list(results)
    return "\n".join(lines).rstrip() + "\n"
