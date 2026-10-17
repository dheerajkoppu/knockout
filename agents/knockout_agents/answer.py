"""Assembles the four slices into one answer: the free summary, its Interactive Card, and the paid full report."""

import json
import math
from dataclasses import dataclass, field

from knockout_agents import intent, settings
from knockout_agents.models import STATUS_OK, SliceResponse
from knockout_agents.resolver import TargetDrugs

STEPS = {
    "target-agent": "steps 1 and 2, targets",
    "genetics-agent": "steps 3 to 5, genetic diseases",
    "label-agent": "step 6, FDA label",
    "signal-agent": "steps 7 and 8, FDA reports",
}
VERDICT_LABELS = {
    "on_label": "On the label",
    "signal_in_reports": "Signal in FDA reports, not on the label",
    "no_signal": "No signal in FDA reports",
    "unknown": "Unknown",
}
VERDICT_BADGES = {"on_label": "success", "signal_in_reports": "warning", "no_signal": "info", "unknown": "info"}
EFFECT_VERBS = {"lowers": "lowers the activity of", "raises": "raises the activity of"}
VERDICT_ORDER = {"on_label": 0, "signal_in_reports": 1, "no_signal": 2, "unknown": 3}
CAVEATS = (
    "FDA adverse-event reports are voluntary and uneven; a boxed warning itself raises reporting of the effect it "
    "names; patients on immune drugs have immune diseases, so infections may come from the disease; a lifelong "
    "genetic loss is stronger than partial inhibition by a drug. Unknown never means safe. Research use only, "
    "not medical advice."
)
CARD_PREDICTIONS = 6
SUMMARY_PREDICTIONS = 5


@dataclass
class Assembled:
    drug: str
    responses: dict[str, SliceResponse]
    data: dict[str, dict]
    predictions: list[dict] = field(default_factory=list)

    def ok(self, agent: str) -> bool:
        response = self.responses.get(agent)
        return response is not None and response.status == STATUS_OK

    def molecule(self) -> dict | None:
        return self.data.get("target-agent", {}).get("molecule")

    def display_name(self) -> str:
        molecule = self.molecule()
        return (molecule or {}).get("name") or self.drug.title()


def _decode(response: SliceResponse | None) -> dict:
    if response is None:
        return {}
    try:
        return json.loads(response.data_json or "{}")
    except ValueError:
        return {}


def assemble(drug: str, responses: dict[str, SliceResponse]) -> Assembled:
    data = {agent: _decode(response) for agent, response in responses.items()}
    assembled = Assembled(drug=drug, responses=responses, data=data)
    label_by_hpo = {match["hpo_id"]: match for match in data.get("label-agent", {}).get("matches") or []}
    signal_predictions = data.get("signal-agent", {}).get("predictions") or []
    signal_response = responses.get("signal-agent")
    for index, genetic in enumerate(data.get("genetics-agent", {}).get("predictions") or []):
        merged = dict(genetic)
        signal = signal_predictions[index] if index < len(signal_predictions) else None
        if signal is not None and signal.get("hpo_id") != genetic.get("hpo_id"):
            signal = next((row for row in signal_predictions if row.get("hpo_id") == genetic.get("hpo_id")), None)
        label = label_by_hpo.get(genetic.get("hpo_id"))
        if label:
            merged.update({key: label.get(key) for key in ("label_section", "label_term", "label_sentence")})
        if signal is not None:
            merged.update({key: signal.get(key) for key in ("verdict", "reason", "candidate_new_signal", "counts")})
        else:
            merged["counts"] = []
            merged["candidate_new_signal"] = False
            merged["verdict"] = "on_label" if label else "unknown"
            merged["reason"] = None if label else (
                f"signal-agent: {signal_response.reason}" if signal_response and signal_response.reason
                else "signal-agent did not answer"
            )
        assembled.predictions.append(merged)
    assembled.predictions.sort(key=lambda row: VERDICT_ORDER.get(row.get("verdict") or "unknown", 3))
    return assembled


def _number(value: int | None) -> str:
    return f"{value:,}" if isinstance(value, int) else "?"


def format_prr(row: dict) -> str:
    """The API sends an infinite PRR as null plus prr_infinite, since JSON has no Infinity."""
    prr = row.get("prr")
    if row.get("prr_infinite") or (isinstance(prr, float) and math.isinf(prr)):
        return "unbounded (no reports of it with other drugs)"
    if prr is None:
        return "not computable"
    return f"{prr:,.0f}" if prr >= 100 else f"{prr:.1f}"


def best_count(prediction: dict) -> dict | None:
    counts = prediction.get("counts") or []
    if not counts:
        return None
    return max(counts, key=lambda count: (bool(count.get("signal")), count.get("a") or 0))


def _quote(sentence: str, limit: int = 220) -> str:
    sentence = " ".join(sentence.split())
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def _section_name(section: str | None) -> str:
    return (section or "label").replace("_", " ").capitalize()


def reports_line(prediction: dict, drug_name: str) -> str | None:
    count = best_count(prediction)
    if count is None:
        return None
    signal = "a signal" if count.get("signal") else "no signal"
    return (
        f"{_number(count.get('a'))} of {_number(count.get('drug'))} {drug_name} reports name "
        f"{count.get('term')}; PRR {format_prr(count)}, {signal}"
    )


def _unique_predictions(assembled: Assembled) -> list[dict]:
    seen: dict[str, dict] = {}
    for prediction in assembled.predictions:
        key = prediction.get("hpo_id") or prediction.get("phenotype")
        if key in seen:
            diseases = seen[key].setdefault("all_diseases", [seen[key].get("disease")])
            if prediction.get("disease") not in diseases:
                diseases.append(prediction.get("disease"))
            continue
        seen[key] = dict(prediction)
    return list(seen.values())


def _chain_line(assembled: Assembled) -> str | None:
    target_data = assembled.data.get("target-agent", {})
    used = target_data.get("used_targets") or []
    if not used:
        return None
    parts = []
    for target in used:
        verb = EFFECT_VERBS.get(target.get("effect"), "acts on")
        actions = ", ".join(action for action in target.get("action_types") or [] if action)
        gene = f" ({target['gene']})" if target.get("gene") else ""
        parts.append(f"{verb} **{target['name']}**{gene}" + (f" (ChEMBL action type {actions})" if actions else ""))
    return f"**{assembled.display_name()}** " + "; it also ".join(parts) + "."


def _disease_line(assembled: Assembled) -> str | None:
    diseases = [
        disease for disease in assembled.data.get("genetics-agent", {}).get("diseases") or []
        if disease.get("pairing") == "use"
    ]
    if not diseases:
        return None
    names = ", ".join(f"**{disease['name']}**" for disease in diseases[:4])
    more = f" and {len(diseases) - 4} more" if len(diseases) > 4 else ""
    return f"People born with that protein not working have {names}{more}; their symptoms are the predictions."


def _focus_line(assembled: Assembled, focus: str | None) -> str | None:
    stems = intent.focus_terms(focus)
    if not stems:
        return None
    matching = [prediction for prediction in _unique_predictions(assembled) if intent.matches_focus(prediction, stems)]
    if not matching:
        return (f"You asked about *{focus}*: no symptom of the genetic diseases of its targets matches, so "
                f"Knockout does not predict it from genetics. That is not evidence that it cannot happen.")
    names = "; ".join(prediction["phenotype"] for prediction in matching[:3])
    verdicts = ", ".join(sorted({VERDICT_LABELS.get(prediction.get("verdict"), "Unknown") for prediction in matching}))
    return f"You asked about *{focus}*: **yes, genetics predicts it** ({names}). Check: {verdicts}."


def failures(assembled: Assembled) -> list[str]:
    lines = []
    for agent, step in STEPS.items():
        response = assembled.responses.get(agent)
        if response is None:
            lines.append(f"{agent} ({step}) did not answer")
        elif response.status != STATUS_OK:
            lines.append(f"{agent} ({step}) answered unknown: {response.reason}")
    return lines


def notes(assembled: Assembled) -> list[str]:
    lines = []
    for agent in STEPS:
        response = assembled.responses.get(agent)
        if response is not None and response.status == STATUS_OK and response.reason:
            lines.append(f"{agent}: {response.reason}")
    return lines


def _ordered_focus_first(predictions: list[dict], focus: str | None) -> list[dict]:
    stems = intent.focus_terms(focus)
    return sorted(predictions, key=lambda prediction: 0 if intent.matches_focus(prediction, stems) else 1)


def _agent_status_line(assembled: Assembled) -> str:
    parts = []
    for agent in STEPS:
        response = assembled.responses.get(agent)
        parts.append(f"{agent} {response.status if response else 'no answer'}")
    return "Agents: " + " · ".join(parts)


def summary_text(assembled: Assembled, *, focus: str | None = None, target_drugs: TargetDrugs | None = None) -> str:
    lines: list[str] = []
    if target_drugs is not None:
        others = [drug.name for drug in target_drugs.drugs if drug.name != assembled.drug]
        approved = f" (first approved {target_drugs.drugs[0].first_approval})" if target_drugs.drugs and \
            target_drugs.drugs[0].first_approval else ""
        verb = {"lowers": "that block", "raises": "that activate"}.get(target_drugs.effect or "", "acting on")
        shared = (
            "The genetic prediction is the same for all of them; the label and report checks are per drug"
            if target_drugs.same_effect else
            "They do not all act on it the same way, so the genetic prediction can differ between them"
        )
        lines.append(
            f"ChEMBL lists {len(target_drugs.drugs)} approved drug{'s' if len(target_drugs.drugs) != 1 else ''} {verb} "
            f"{target_drugs.target_name}. {shared}, so here is **{assembled.display_name()}**{approved}, the longest "
            f"on the market." + (f" Others: {', '.join(others[:6])}." if others else "")
        )
    for line in (_chain_line(assembled), _disease_line(assembled), _focus_line(assembled, focus)):
        if line:
            lines.append(line)

    predictions = _ordered_focus_first(_unique_predictions(assembled), focus)
    drug_name = assembled.display_name().lower()
    if predictions:
        lines.append(f"**Predicted side effects ({len(predictions)}):**")
        for number, prediction in enumerate(predictions[:SUMMARY_PREDICTIONS], start=1):
            frequency = f" ({prediction['frequency']} cases)" if "/" in str(prediction.get("frequency") or "") else (
                f" ({prediction['frequency'].lower()})" if prediction.get("frequency") else "")
            verdict = prediction.get("verdict") or "unknown"
            entry = [f"{number}. **{prediction['phenotype']}**{frequency}: {VERDICT_LABELS.get(verdict, verdict)}"]
            if verdict == "signal_in_reports" and prediction.get("candidate_new_signal"):
                entry[0] += " (candidate new signal)"
            if prediction.get("label_sentence"):
                entry.append(f"   {_section_name(prediction.get('label_section'))}: "
                             f"\"{_quote(prediction['label_sentence'])}\"")
            reports = reports_line(prediction, drug_name)
            if reports:
                entry.append(f"   FDA reports: {reports}")
            if verdict == "unknown" and prediction.get("reason"):
                entry.append(f"   Why unknown: {prediction['reason']}")
            lines.append("\n".join(entry))
        if len(predictions) > SUMMARY_PREDICTIONS:
            lines.append(f"…and {len(predictions) - SUMMARY_PREDICTIONS} more in the full report.")
    elif assembled.ok("genetics-agent"):
        reason = assembled.responses["genetics-agent"].reason
        lines.append(f"No prediction: {reason or 'no genetic disease pairs with this drug'}.")

    problems = failures(assembled)
    if problems:
        lines.append("**Could not run:** " + "; ".join(problems) + ".")
    extra = notes(assembled)
    if extra:
        lines.append("**Notes:** " + "; ".join(extra) + ".")
    lines.append(f"_{CAVEATS}_")
    price = settings.full_report_price_fet()
    paid = f" ({price} FET{' testnet' if settings.fet_use_testnet() else ''})" if settings.payment_enabled() else ""
    lines.append(
        f"Reply **full report** for every prediction with its label quote, report counts, sources and trend{paid}."
    )
    lines.append(_agent_status_line(assembled))
    return "\n\n".join(lines)


def _prediction_item(prediction: dict, drug_name: str) -> dict:
    verdict = prediction.get("verdict") or "unknown"
    children: list[dict] = [
        {"type": "heading", "value": prediction["phenotype"][:120], "level": 3},
        {"type": "badge", "label": VERDICT_LABELS.get(verdict, verdict),
         "variant": VERDICT_BADGES.get(verdict, "info")},
    ]
    source = ", ".join(prediction.get("all_diseases") or [prediction.get("disease") or ""])
    frequency = prediction.get("frequency")
    children.append({"type": "text", "value": f"From {source}{' · ' + frequency if frequency else ''}",
                     "style": "muted"})
    if prediction.get("label_sentence"):
        children.append({"type": "text", "style": "emphasis",
                         "value": f"{_section_name(prediction.get('label_section'))}: "
                                  f"\"{_quote(prediction['label_sentence'], 180)}\""})
    reports = reports_line(prediction, drug_name)
    if reports:
        children.append({"type": "text", "value": f"FDA reports: {reports}"})
    if verdict == "unknown" and prediction.get("reason"):
        children.append({"type": "text", "value": f"Why unknown: {prediction['reason'][:200]}", "style": "muted"})
    return {"children": children}


def summary_card(assembled: Assembled, *, focus: str | None = None,
                 target_drugs: TargetDrugs | None = None) -> dict:
    drug_name = assembled.display_name()
    children: list[dict] = []
    chain = []
    for target in assembled.data.get("target-agent", {}).get("used_targets") or []:
        chain.append({"type": "badge", "label": f"{target.get('gene') or target['name']}: {target.get('effect')}",
                      "variant": "info"})
    for disease in (assembled.data.get("genetics-agent", {}).get("diseases") or [])[:3]:
        if disease.get("pairing") == "use":
            chain.append({"type": "badge", "label": disease["name"][:60], "variant": "info"})
    if chain:
        children.append({"type": "group", "direction": "row", "gap": 8, "children": chain})
    chain_text = _chain_line(assembled)
    if chain_text:
        children.append({"type": "text", "value": chain_text.replace("**", "")})
    focus_text = _focus_line(assembled, focus)
    if focus_text:
        children.append({"type": "text", "value": focus_text.replace("**", "").replace("*", ""), "style": "emphasis"})

    predictions = _ordered_focus_first(_unique_predictions(assembled), focus)
    if predictions:
        children.append({"type": "divider"})
        children.append({"type": "list", "items": [
            _prediction_item(prediction, drug_name.lower()) for prediction in predictions[:CARD_PREDICTIONS]
        ]})
        if len(predictions) > CARD_PREDICTIONS:
            children.append({"type": "text", "style": "muted",
                             "value": f"{len(predictions) - CARD_PREDICTIONS} more predictions in the full report."})
    for problem in failures(assembled):
        children.append({"type": "text", "value": f"Could not run: {problem}", "style": "muted"})
    children.append({"type": "divider"})
    children.append({"type": "text", "value": CAVEATS, "style": "muted"})

    price = settings.full_report_price_fet()
    label = f"Full report · {price} FET" if settings.payment_enabled() else "Full report"
    buttons = [{"type": "button", "label": label, "primary": True,
                "action": {"selection": {"action": "full_report", "drug": assembled.drug}}}]
    if target_drugs is not None:
        for drug in [drug for drug in target_drugs.drugs if drug.name != assembled.drug][:2]:
            buttons.append({"type": "button", "label": f"Check {drug.name}",
                            "action": {"selection": {"action": "analyze", "drug": drug.name}}})
    children.append({"type": "group", "direction": "row", "gap": 8, "children": buttons})
    return {"root": {
        "type": "section",
        "title": f"{drug_name}: side effects predicted from genetics",
        "subtitle": "Knockout · drug → protein → genetic disease → symptom, checked against the FDA label and reports",
        "children": children,
    }}


def full_report_text(assembled: Assembled) -> str:
    name = assembled.display_name()
    molecule = assembled.molecule() or {}
    lines = [f"# Knockout full report: {name}"]
    if molecule:
        lines.append(f"ChEMBL {molecule.get('chembl_id')} · {molecule.get('molecule_type') or 'molecule'} · "
                     f"max phase {molecule.get('max_phase')} · {molecule.get('url')}")
    page = settings.report_page_url()
    if page:
        lines.append(f"Report page: {page}/drugs/{assembled.drug}")

    lines.append("## Targets (target-agent)")
    for target in assembled.data.get("target-agent", {}).get("targets") or []:
        actions = ", ".join(action for action in target.get("action_types") or [] if action)
        status = "used" if target.get("used") else f"not used: {target.get('reason') or 'no pairing disease'}"
        lines.append(f"- {target['name']} ({target.get('accession') or 'no accession'}, gene "
                     f"{target.get('gene') or '?'}): {actions or 'no action type'} → {target.get('effect')}; {status}")

    lines.append("## Genetic diseases (genetics-agent)")
    for disease in assembled.data.get("genetics-agent", {}).get("diseases") or []:
        lines.append(f"- {disease['name']} ({disease.get('gene')}): {disease.get('direction')} from "
                     f"{disease.get('direction_source')}; pairing **{disease.get('pairing')}**; "
                     f"{disease.get('phenotypes_used', 0)} phenotypes used. {disease.get('direction_basis') or ''}")
    excluded = assembled.data.get("genetics-agent", {}).get("excluded_developmental") or []
    if excluded:
        lines.append("Excluded as developmental: " + ", ".join(item["phenotype"] for item in excluded))

    drug_name = name.lower()
    lines.append(f"## Predictions ({len(assembled.predictions)})")
    for prediction in assembled.predictions:
        verdict = prediction.get("verdict") or "unknown"
        block = [f"### {prediction['phenotype']} ({prediction.get('hpo_id')})",
                 f"- From {prediction.get('disease')} ({prediction.get('gene')}), frequency "
                 f"{prediction.get('frequency') or '?'}, kind {prediction.get('kind') or 'not classified yet'}",
                 f"- Verdict: **{VERDICT_LABELS.get(verdict, verdict)}**"
                 + (" · candidate new signal" if prediction.get("candidate_new_signal") else "")
                 + (f" · {prediction['reason']}" if prediction.get("reason") else ""),
                 f"- Reaction terms: {', '.join(prediction.get('reaction_terms') or []) or 'none yet'}"]
        if prediction.get("label_sentence"):
            block.append(f"- Label, {_section_name(prediction.get('label_section'))} (term "
                         f"{prediction.get('label_term')}): \"{' '.join(prediction['label_sentence'].split())}\"")
        for count in prediction.get("counts") or []:
            block.append(
                f"- FAERS {count.get('term')}: {_number(count.get('a'))} with {drug_name}, "
                f"{_number(count.get('drug'))} {drug_name} reports, {_number(count.get('reaction'))} reports of the "
                f"reaction, {_number(count.get('all'))} in all; PRR {format_prr(count)}, chi-squared "
                f"{count.get('chi_squared') or 0:.1f}, {'signal' if count.get('signal') else 'no signal'}"
                + (f" · {count['query']}" if count.get("query") else "")
            )
        for record in prediction.get("records") or []:
            block.append(f"- Source {record.get('source')}: {record.get('description')}"
                         + (f" · {record['url']}" if record.get("url") else ""))
        lines.append("\n".join(block))

    label = assembled.data.get("label-agent", {}).get("label")
    lines.append("## FDA label (label-agent)")
    if label:
        lines.append(f"Set {label.get('set_id')}, effective {label.get('effective_time')}; sections searched: "
                     f"{', '.join(label.get('sections') or [])}. {label.get('url') or ''}")
    else:
        response = assembled.responses.get("label-agent")
        lines.append(f"Unavailable: {response.reason if response else 'label-agent did not answer'}")

    signal_data = assembled.data.get("signal-agent", {})
    lines.append("## Reports, trend and alerts (signal-agent)")
    lines.append(f"{_number(signal_data.get('drug_reports'))} FAERS reports for {drug_name}, "
                 f"{_number(signal_data.get('all_reports'))} in all.")
    trend = signal_data.get("trend") or {}
    for term in trend.get("terms") or []:
        quarters = term.get("quarters") or []
        recent = ", ".join(f"{row['quarter']}: {row['reports']}" for row in quarters[-6:])
        lines.append(f"- Trend {term.get('term')}: {recent or 'no quarters yet'}")
    if trend:
        lines.append(f"Watch agent last run: {trend.get('last_run_at') or 'never'}")
    for alert in (signal_data.get("alerts") or {}).get("alerts") or []:
        lines.append(f"- Alert: {alert.get('term')} crossed PRR {format_prr(alert)} in "
                     f"{alert.get('quarter')} (seen {alert.get('crossed_at')})")
    for problem in signal_data.get("monitoring_problems") or []:
        lines.append(f"- {problem}")

    problems = failures(assembled) + notes(assembled)
    if problems:
        lines.append("## Problems")
        lines.extend(f"- {problem}" for problem in problems)
    lines.append("## Limits")
    lines.append(CAVEATS)
    return "\n\n".join(lines)


def target_choices_card(target_drugs: TargetDrugs) -> dict:
    return {
        "title": f"Approved drugs acting on {target_drugs.target_name}",
        "subtitle": "Pick one to check its predicted side effects",
        "items": [
            {
                "id": drug.chembl_id,
                "title": drug.name.title(),
                "subtitle": ", ".join(drug.action_types).lower() or "mechanism recorded in ChEMBL",
                "secondary_text": f"First approved {drug.first_approval}" if drug.first_approval else "Approved",
                "primary_cta": {"label": "Check", "selection": {"action": "analyze", "drug": drug.name}},
            }
            for drug in target_drugs.drugs[:10]
        ],
    }


HELP_TEXT = (
    "I predict a drug's side effects from the genetic diseases of the proteins it blocks: a drug that blocks a "
    "protein is a chemical knockout, so it should cause a milder version of that protein's genetic disease. "
    "Every prediction is checked against the FDA label (quoted verbatim) and FDA adverse-event reports.\n\n"
    "Try:\n- What side effects should a C5 blocker cause?\n- Is eculizumab expected to cause infections?\n"
    "- What does genetics predict for ibrutinib?"
)
