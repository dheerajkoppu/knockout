"""All five agents and a stand-in ASI:One user exchange real uAgents messages against the fake services."""

import asyncio
import json

from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent
from uagents_core.contrib.protocols.chat.cards import validate_card_payload_json
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RequestPayment,
)

from knockout_agents.local_chat import LocalChat


def _card(message: ChatMessage) -> tuple[str, dict] | None:
    for item in message.content:
        if isinstance(item, MetadataContent) and "card_payload" in item.metadata:
            kind = item.metadata["card_kind"]
            validate_card_payload_json(kind, item.metadata["card_payload"])
            return kind, json.loads(item.metadata["card_payload"])
    return None


def _run(scenario):
    async def wrapper():
        chat = LocalChat(allow_test_seeds=True)
        await chat.start()
        try:
            await scenario(chat)
        finally:
            await chat.stop()

    asyncio.run(wrapper())


def test_a_question_about_a_drug_gets_the_chain_the_checks_and_a_card(services):
    async def scenario(chat: LocalChat):
        await chat.say("Is eculizumab expected to cause infections?", start_session=True)
        reply = await chat.next((ChatMessage,))
        text = reply.text()
        assert "yes, genetics predicts it" in text
        assert "WARNING: SERIOUS MENINGOCOCCAL INFECTIONS" in text
        assert "PRR 146" in text
        assert "Agents: target-agent ok · genetics-agent ok · label-agent ok · signal-agent ok" in text
        kind, payload = _card(reply)
        assert kind == "custom"
        assert "Recurrent Neisseria meningitidis infection" in json.dumps(payload)

    _run(scenario)
    report_calls = [call for call in services.calls if call.endswith("/report")]
    assert len(report_calls) == 4
    assert "/api/drugs/eculizumab/trend" in services.calls


def test_a_protein_question_resolves_to_its_longest_marketed_drug(services):
    async def scenario(chat: LocalChat):
        await chat.say("What side effects should a C5 blocker cause?")
        reply = await chat.next((ChatMessage,))
        text = reply.text()
        assert "ChEMBL lists 2 approved drugs that block Complement C5. The genetic prediction is the same" in text
        assert "**Eculizumab** (first approved 2007)" in text
        assert "Others: ravulizumab." in text
        assert "Check ravulizumab" in json.dumps(_card(reply)[1])

    _run(scenario)


def test_which_drugs_lists_them_in_a_carousel_and_a_pick_runs_the_analysis(services):
    async def scenario(chat: LocalChat):
        await chat.say("Which drugs block C5?")
        reply = await chat.next((ChatMessage,))
        kind, payload = _card(reply)
        assert kind == "carousel"
        assert [item["title"] for item in payload["items"]] == ["Eculizumab", "Ravulizumab"]
        await chat.say(json.dumps(payload["items"][0]["primary_cta"]["selection"]))
        assert "**Eculizumab** lowers the activity of" in (await chat.next((ChatMessage,))).text()

    _run(scenario)


def test_unknown_drug_and_broken_sources_are_reported_not_hidden(services):
    services.broken.add("trend")

    async def scenario(chat: LocalChat):
        await chat.say('{"action": "analyze", "drug": "notadrug"}')
        text = (await chat.next((ChatMessage,))).text()
        assert "target-agent (steps 1 and 2, targets) answered unknown: the Knockout API has no record" in text
        assert "notadrug" in text

        services.broken.add("api")
        await chat.say("Is eculizumab expected to cause infections?")
        text = (await chat.next((ChatMessage,))).text()
        assert "target-agent (steps 1 and 2, targets) answered unknown: the Knockout API returned HTTP 500" in text
        assert "signal-agent (steps 7 and 8, FDA reports) answered unknown" in text

    _run(scenario)


def test_full_report_is_released_only_after_a_verified_payment(services):
    async def scenario(chat: LocalChat):
        await chat.say("Is eculizumab expected to cause infections?")
        await chat.next((ChatMessage,))
        await chat.say(json.dumps({"action": "full_report", "drug": "eculizumab"}))
        request = await chat.next((RequestPayment,))
        assert request.accepted_funds[0].currency == "FET"
        assert request.accepted_funds[0].payment_method == "fet_direct"
        assert request.recipient == str(chat.orchestrator.wallet.address())

        def commit(transaction_id: str) -> CommitPayment:
            return CommitPayment(funds=Funds(currency="FET", amount="0.1", payment_method="fet_direct"),
                                 recipient=request.recipient, transaction_id=transaction_id,
                                 reference=request.reference, metadata={"buyer_fet_wallet": "fetch1buyer"})

        services.ledger["UNPAIDHASH"] = {"tx_response": {"code": 0}, "tx": {"body": {"messages": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "fetch1buyer", "to_address": request.recipient,
            "amount": [{"denom": "atestfet", "amount": str(10**16)}]}]}}}
        await chat.send(commit("UNPAIDHASH"))
        cancel = await chat.next((CancelPayment, CompletePayment))
        assert isinstance(cancel, CancelPayment) and "needed" in cancel.reason

        services.ledger["PAIDHASH"] = {"tx_response": {"code": 0}, "tx": {"body": {"messages": [{
            "@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": "fetch1buyer", "to_address": request.recipient,
            "amount": [{"denom": "atestfet", "amount": str(10**17)}]}]}}}
        await chat.send(commit("PAIDHASH"))
        complete = await chat.next((CompletePayment, CancelPayment))
        assert isinstance(complete, CompletePayment) and complete.transaction_id == "PAIDHASH"
        report = (await chat.next((ChatMessage,))).text()
        assert report.startswith("# Knockout full report: Eculizumab")
        assert "chi-squared" in report

        await chat.send(commit("PAIDHASH"))
        replay = await chat.next((CancelPayment, CompletePayment))
        assert isinstance(replay, CancelPayment)

    _run(scenario)


def test_a_request_the_rules_cannot_read_goes_to_the_asi_one_fallback(services, monkeypatch):
    monkeypatch.setenv("ASI1_API_KEY", "test-value-for-the-local-fake")
    monkeypatch.setenv("ASI1_API_URL", f"{services.url}/asi1")

    async def scenario(chat: LocalChat):
        await chat.say("That complement medicine people take for PNH, could it give them meningitis?")
        text = (await chat.next((ChatMessage,))).text()
        assert "**Eculizumab** lowers the activity of **Complement C5**" in text
        assert "You asked about *meningitis*" in text

    _run(scenario)
    assert services.asi_one_prompts == ["That complement medicine people take for PNH, could it give them meningitis?"]
