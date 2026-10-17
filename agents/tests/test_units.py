import json

import pytest
from uagents_core.contrib.protocols.chat.cards import validate_card_payload

from fake_services import engine_output, mapped_report, trend, without_infinity
from knockout_agents import answer, intent, payments, slices
from knockout_agents.models import SliceResponse
from knockout_agents.resolver import Drug, TargetDrugs


@pytest.mark.parametrize(("text", "drug_words", "target", "focus"), [
    ("what side effects should a C5 blocker cause?", [], "c5", None),
    ("Is eculizumab expected to cause infections?", ["eculizumab"], None, "infections"),
    ("What would a BTK inhibitor do to patients?", [], "btk", None),
    ("drugs that block JAK3", [], "jak3", None),
    ("Can ibrutinib lead to bleeding?", ["ibrutinib"], None, "bleeding"),
    ("What side effects should complement C5 inhibitors cause", [], "complement c5", None),
])
def test_intent_reads_drugs_targets_and_focus(text, drug_words, target, focus):
    parsed = intent.parse(text)
    assert parsed.action == intent.ANALYZE
    assert parsed.drug_words == drug_words
    assert parsed.target_words == target
    assert parsed.focus == focus


def test_intent_reads_card_selections_and_full_report_requests():
    assert intent.parse('{"action": "full_report", "drug": "Eculizumab"}').action == intent.FULL_REPORT
    assert intent.parse('{"action": "full_report", "drug": "Eculizumab"}').drug == "eculizumab"
    assert intent.parse("", {"action": "analyze", "drug": "ravulizumab"}).drug == "ravulizumab"
    assert intent.parse("full report please").action == intent.FULL_REPORT
    assert intent.parse("hello").action == intent.HELP
    assert intent.focus_terms("infections") == ["infection"]
    assert intent.parse("Which drugs block C5?").action == intent.LIST_DRUGS
    assert intent.parse("What approved medicines are BTK inhibitors?").action == intent.LIST_DRUGS


def _responses(report: dict, *, trend_data=None) -> dict[str, SliceResponse]:
    built = {
        "target-agent": slices.target_slice(report),
        "genetics-agent": slices.genetics_slice(report),
        "label-agent": slices.label_slice(report),
        "signal-agent": slices.signal_slice(report, trend_data, {"alerts": []}),
    }
    return {
        agent: SliceResponse(request_id="r", agent=agent, drug="eculizumab", status=result.status,
                             reason=result.reason, data_json=json.dumps(result.data))
        for agent, result in built.items()
    }


def test_real_engine_output_without_step_5_is_reported_as_unknown_never_safe():
    report = engine_output()
    assert slices.target_slice(report).status == "ok"
    genetics = slices.genetics_slice(report)
    assert genetics.reason == "Step 5 could not map new phenotypes: GEMINI_API_KEY is not set in .env"
    assert slices.label_slice(report).status == "unknown"
    assert slices.signal_slice(report).status == "unknown"

    assembled = answer.assemble("eculizumab", _responses(report))
    assert {prediction["verdict"] for prediction in assembled.predictions} == {"unknown"}
    text = answer.summary_text(assembled)
    assert "Recurrent Neisseria meningitidis infection" in text
    assert "Why unknown: phenotype not mapped yet (step 5)" in text
    assert "label-agent (step 6, FDA label) answered unknown" in text
    validate_card_payload("custom", answer.summary_card(assembled))


def test_mapped_fixture_gives_the_label_quote_and_prr_146():
    assembled = answer.assemble("eculizumab", _responses(mapped_report(), trend_data=trend()))
    top = assembled.predictions[0]
    assert top["hpo_id"] == "HP:0005381" and top["verdict"] == "on_label"
    text = answer.summary_text(assembled, focus="infections")
    assert "yes, genetics predicts it" in text
    assert "SERIOUS MENINGOCOCCAL INFECTIONS" in text
    assert "86 of 54,046 eculizumab reports name MENINGOCOCCAL INFECTION; PRR 146, a signal" in text

    card = answer.summary_card(assembled, focus="infections")
    validate_card_payload("custom", card)
    selections = json.dumps(card)
    assert '"action": "full_report"' in selections

    full = answer.full_report_text(assembled)
    assert "chi-squared" in full and "Trend MENINGOCOCCAL INFECTION: 2026Q1: 3, 2026Q2: 5" in full


def test_infinite_prr_from_the_api_is_shown_as_unbounded():
    report = mapped_report()
    report["predictions"][1]["counts"][0]["prr"] = float("inf")
    assembled = answer.assemble("eculizumab", _responses(without_infinity(report)))
    assert "unbounded" in answer.summary_text(assembled)


def test_a_failed_specialist_is_named_with_its_step():
    responses = _responses(mapped_report())
    responses["signal-agent"] = SliceResponse(request_id="r", agent="signal-agent", drug="eculizumab",
                                              status="unknown", reason="the Knockout API timed out")
    assembled = answer.assemble("eculizumab", responses)
    assert assembled.predictions[0]["verdict"] == "on_label"
    assert "signal-agent (steps 7 and 8, FDA reports) answered unknown: the Knockout API timed out" in \
        answer.summary_text(assembled)


def test_target_choices_card_is_a_valid_carousel():
    target_drugs = TargetDrugs("c5", "CHEMBL2364163", "Complement C5", "C5", "P01031", [
        Drug("CHEMBL1201828", "eculizumab", 4.0, 2007, ("INHIBITOR",)),
        Drug("CHEMBL4594316", "ravulizumab", 4.0, 2018, ("INHIBITOR",)),
    ])
    validate_card_payload("carousel", answer.target_choices_card(target_drugs))
    assembled = answer.assemble("eculizumab", _responses(mapped_report()))
    card = answer.summary_card(assembled, target_drugs=target_drugs)
    validate_card_payload("custom", card)
    assert "Check ravulizumab" in json.dumps(card)


RECIPIENT = "fetch1recipient"


def _transaction(amount: str, *, code: int = 0, to_address: str = RECIPIENT, denom: str = "atestfet") -> dict:
    return {"tx_response": {"code": code}, "tx": {"body": {"messages": [{
        "@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "fetch1buyer", "to_address": to_address,
        "amount": [{"denom": denom, "amount": amount}],
    }]}}}


def test_payment_check_needs_the_amount_the_recipient_and_success(monkeypatch):
    monkeypatch.setenv("FET_USE_TESTNET", "true")
    enough = str(10**17)
    assert payments.check_transaction(_transaction(enough), recipient=RECIPIENT, amount_fet="0.1", sender=None).paid
    assert payments.check_transaction(_transaction(enough), recipient=RECIPIENT, amount_fet="0.1",
                                      sender="fetch1buyer").paid
    assert not payments.check_transaction(_transaction(enough), recipient=RECIPIENT, amount_fet="0.1",
                                          sender="fetch1someoneelse").paid
    assert not payments.check_transaction(_transaction(str(10**16)), recipient=RECIPIENT, amount_fet="0.1",
                                          sender=None).paid
    assert not payments.check_transaction(_transaction(enough, code=5), recipient=RECIPIENT, amount_fet="0.1",
                                          sender=None).paid
    assert not payments.check_transaction(_transaction(enough, to_address="fetch1other"), recipient=RECIPIENT,
                                          amount_fet="0.1", sender=None).paid
    assert not payments.check_transaction(_transaction(enough, denom="afet"), recipient=RECIPIENT,
                                          amount_fet="0.1", sender=None).paid


def test_address_table_is_written_between_the_markers(monkeypatch, tmp_path):
    from knockout_agents import addresses
    from knockout_agents.build import address_for_seed

    for name in ("ORCHESTRATOR", "TARGET", "GENETICS", "LABEL", "SIGNAL"):
        monkeypatch.setenv(f"AGENT_SEED_{name}", f"unit-test-seed-{name.lower()}")
    readme = tmp_path / "README.md"
    readme.write_text(f"before\n{addresses.START_MARKER}\nold\n{addresses.END_MARKER}\nafter\n")
    monkeypatch.setattr(addresses, "README_PATH", readme)
    addresses.write_readme(addresses.table(test_seeds=False))
    written = readme.read_text()
    assert written.startswith("before\n") and written.endswith("after\n") and "old" not in written
    assert f"| `knockout-orchestrator` | `{address_for_seed('unit-test-seed-orchestrator')}` |" in written


def test_a_drug_effect_needs_every_action_type_to_agree():
    from knockout_agents.resolver import Drug, TargetDrugs, drug_effect

    assert drug_effect(("ANTAGONIST",)) == "lowers"
    assert drug_effect(("AGONIST",)) == "raises"
    assert drug_effect(("AGONIST", "INHIBITOR")) == "unknown"
    mixed = TargetDrugs("tlr7", "CHEMBL_T", "Toll-like receptor 7", "TLR7", "Q9NYK1", drugs=[
        Drug("CHEMBL1", "hydroxychloroquine", 4.0, 1955, ("ANTAGONIST",)),
        Drug("CHEMBL2", "imiquimod", 4.0, 1997, ("AGONIST",)),
    ])
    assert not mixed.same_effect


def test_a_blocker_question_asks_only_for_lowering_drugs():
    from knockout_agents import intent

    assert intent.parse("What side effects should a TLR7 blocker cause?").target_effect == "lowers"
    assert intent.parse("drugs that target tlr7").target_effect is None
