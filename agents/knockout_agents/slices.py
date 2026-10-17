"""Each specialist's slice of a Knockout report. Pure functions over the report JSON, no network."""

from dataclasses import dataclass, field

from knockout_agents.models import STATUS_OK, STATUS_UNKNOWN


@dataclass
class Slice:
    status: str
    reason: str | None = None
    data: dict = field(default_factory=dict)


def _problems_about(report: dict, *words: str) -> list[str]:
    return [
        problem for problem in report.get("problems") or []
        if any(word.lower() in problem.lower() for word in words)
    ]


def target_slice(report: dict) -> Slice:
    molecule = report.get("molecule")
    targets = report.get("targets") or []
    problems = _problems_about(report, "chembl", "molecule")
    data = {
        "molecule": molecule,
        "targets": targets,
        "used_targets": [target for target in targets if target.get("used")],
        "problems": problems,
    }
    if molecule is None:
        return Slice(STATUS_UNKNOWN, problems[0] if problems else "ChEMBL returned no molecule", data)
    if not targets:
        return Slice(STATUS_OK, "ChEMBL records no mechanism with a protein target for this drug", data)
    if not data["used_targets"]:
        reasons = "; ".join(f"{target['name']}: {target.get('reason') or 'not used'}" for target in targets)
        return Slice(STATUS_OK, f"no target could be used ({reasons})", data)
    return Slice(STATUS_OK, None, data)


def genetics_slice(report: dict) -> Slice:
    predictions = [
        {
            key: prediction.get(key)
            for key in ("hpo_id", "phenotype", "frequency", "kind", "gene", "target", "disease_id",
                        "disease", "reaction_terms", "records")
        }
        for prediction in report.get("predictions") or []
    ]
    unmapped = [
        prediction["hpo_id"] for prediction in report.get("predictions") or []
        if prediction.get("reason") == "phenotype not mapped yet (step 5)"
    ]
    problems = _problems_about(report, "step 5", "gemini", "map")
    data = {
        "diseases": report.get("diseases") or [],
        "predictions": predictions,
        "excluded_developmental": report.get("excluded_developmental") or [],
        "unmapped": unmapped,
        "problems": problems,
    }
    if report.get("molecule") is None:
        return Slice(STATUS_UNKNOWN, "no molecule, so no target to look up", data)
    if not data["diseases"]:
        return Slice(STATUS_OK, "no target of this drug has a disease in the IUIS catalog", data)
    if not predictions:
        return Slice(STATUS_OK, "no disease pairs with the drug's effect and has a frequent phenotype", data)
    if unmapped and len(unmapped) == len(predictions):
        reason = problems[0] if problems else "phenotypes not mapped to reaction terms yet (step 5)"
        return Slice(STATUS_OK, reason, data)
    return Slice(STATUS_OK, None, data)


def label_slice(report: dict) -> Slice:
    label = report.get("label")
    predictions = report.get("predictions") or []
    checkable = [prediction for prediction in predictions if prediction.get("reaction_terms")]
    matches = [
        {
            "hpo_id": prediction.get("hpo_id"),
            "phenotype": prediction.get("phenotype"),
            "label_section": prediction.get("label_section"),
            "label_term": prediction.get("label_term"),
            "label_sentence": prediction.get("label_sentence"),
        }
        for prediction in predictions if prediction.get("label_sentence")
    ]
    data = {
        "label": label,
        "matches": matches,
        "checked": len(checkable),
        "not_on_label": [
            prediction.get("hpo_id") for prediction in checkable if not prediction.get("label_sentence")
        ],
    }
    if label is None:
        problems = _problems_about(report, "label")
        return Slice(STATUS_UNKNOWN, problems[0] if problems else "openFDA returned no label", data)
    if not checkable and predictions:
        return Slice(STATUS_UNKNOWN, "no prediction has reaction terms yet, so nothing could be checked", data)
    return Slice(STATUS_OK, None, data)


def signal_slice(report: dict, trend: dict | None = None, alerts: dict | None = None,
                 monitoring_problems: list[str] | None = None) -> Slice:
    predictions = [
        {
            key: prediction.get(key)
            for key in ("hpo_id", "phenotype", "verdict", "reason", "candidate_new_signal", "counts")
        }
        for prediction in report.get("predictions") or []
    ]
    data = {
        "drug_reports": report.get("drug_reports"),
        "all_reports": report.get("all_reports"),
        "predictions": predictions,
        "trend": trend,
        "alerts": alerts,
        "monitoring_problems": monitoring_problems or [],
    }
    if report.get("drug_reports") is None:
        problems = _problems_about(report, "reports")
        return Slice(STATUS_UNKNOWN, problems[0] if problems else "openFDA report totals unavailable", data)
    if predictions and not any(prediction["counts"] for prediction in predictions):
        return Slice(STATUS_UNKNOWN, "no prediction has reaction terms yet, so no reports were counted", data)
    return Slice(STATUS_OK, None, data)
