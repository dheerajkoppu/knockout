"""knockout-orchestrator: reads an ASI:One request, resolves the drug, calls the specialists, answers with a card."""

import asyncio
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.contrib.protocols.chat.cards import (
    create_card_content,
    extract_card_response,
    validate_card_payload,
)
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
    payment_protocol_spec,
)

from knockout_agents import answer, asi_one, intent, observability, payments, resolver, settings
from knockout_agents.models import STATUS_UNKNOWN, SliceRequest, SliceResponse
from knockout_agents.settings import AGENT_SPECS

SPECIALISTS = ("target", "genetics", "label", "signal")
PAID_TRANSACTIONS_KEY = "paid_transactions"


def text_message(text: str) -> ChatMessage:
    return ChatMessage(content=[TextContent(text=text)])


def card_message(text: str, card_kind: str, payload: dict, logger) -> ChatMessage:
    try:
        card = validate_card_payload(card_kind, payload)
        content = create_card_content(card, card_id=uuid4(), preferred_drawer_width_px=600)
    except Exception as error:  # a card that fails validation must never cost the person the text answer
        logger.warning(f"card dropped: {error}")
        return text_message(text)
    return ChatMessage(content=[TextContent(text=text), content])


def read_message(message: ChatMessage) -> tuple[str, dict | None]:
    selection = None
    for item in message.content:
        if isinstance(item, MetadataContent):
            response = extract_card_response(item)
            if response is not None and response.selection:
                selection = dict(response.selection)
    return message.text().strip(), selection


class Orchestrator:
    def __init__(self, agent: Agent, addresses: dict[str, str]):
        self.agent = agent
        self.addresses = addresses

    def wallet_address(self) -> str:
        return str(self.agent.wallet.address())

    async def ask(self, ctx: Context, key: str, request: SliceRequest) -> SliceResponse:
        name = AGENT_SPECS[key].name
        address = self.addresses.get(key)
        if not address:
            return SliceResponse(request_id=request.request_id, agent=name, drug=request.drug,
                                 status=STATUS_UNKNOWN, reason=f"no address configured for {name}")
        with observability.specialist_span(name, request.drug) as span:
            response, status = await ctx.send_and_receive(
                address, request, response_type=SliceResponse, timeout=settings.specialist_timeout_seconds()
            )
            if not isinstance(response, SliceResponse):
                response = SliceResponse(request_id=request.request_id, agent=name, drug=request.drug,
                                         status=STATUS_UNKNOWN, reason=f"{name} did not answer ({status.detail})")
            span.set_data("knockout.status", response.status)
            if response.reason:
                span.set_data("knockout.reason", response.reason)
        return response

    async def gather(self, ctx: Context, drug: str, *, refresh: bool = False) -> answer.Assembled:
        request = SliceRequest(request_id=str(uuid4()), drug=drug, refresh=refresh)
        # target-agent goes first so the report is computed once; the other three then read the cached report
        responses = {"target-agent": await self.ask(ctx, "target", request)}
        cached = SliceRequest(request_id=request.request_id, drug=drug, refresh=False)
        later = await asyncio.gather(*(self.ask(ctx, key, cached) for key in SPECIALISTS[1:]))
        for key, response in zip(SPECIALISTS[1:], later, strict=True):
            responses[AGENT_SPECS[key].name] = response
        return answer.assemble(drug, responses)

    async def drug_from_words(self, ctx: Context, words: list[str]) -> str | None:
        for word in words:
            try:
                found = await resolver.find_drug(word)
            except resolver.ResolverError as error:
                # ChEMBL is down for the lookup; the Knockout API resolves the name itself, or says why it cannot
                ctx.logger.warning(f"drug lookup failed, passing {word!r} through: {error}")
                return word
            if found is not None:
                return found.name
        return None

    async def drug_from_target(self, words: str, effect: str | None = None):
        try:
            target_drugs = await resolver.drugs_for_target(words, effect)
        except resolver.ResolverError as error:
            return None, None, f"I could not look up {words!r}: {error}."
        if target_drugs is None:
            return None, None, f"ChEMBL has no human protein matching {words!r}."
        if not target_drugs.drugs:
            kind = {"lowers": " that blocks or inhibits", "raises": " that activates"}.get(effect or "", " acting on")
            return None, None, (f"ChEMBL lists no approved drug{kind} {target_drugs.target_name}, "
                                f"so there is no label or report record to check a prediction against.")
        return target_drugs.drugs[0].name, target_drugs, None

    async def resolve(self, ctx: Context, sender: str, request: intent.Intent):
        """Returns (drug, target_drugs, message); message is set when there is nothing to analyse."""
        if request.drug:
            return request.drug, None, None
        drug = await self.drug_from_words(ctx, request.drug_words)
        if drug:
            return drug, None, None
        if request.target_words:
            return await self.drug_from_target(request.target_words, request.target_effect)
        if request.action == intent.FULL_REPORT:
            last = ctx.storage.get(f"last_drug:{sender}")
            if last:
                return last, None, None
        extracted = await asi_one.extract(request.text)
        if extracted:
            ctx.logger.info(f"ASI:One extracted {extracted}")
            request.focus = request.focus or extracted.get("effect")
            drug = await self.drug_from_words(ctx, [extracted["drug"]]) if extracted.get("drug") else None
            if drug:
                return drug, None, None
            if extracted.get("protein"):
                return await self.drug_from_target(extracted["protein"])
        return None, None, f"I could not find a drug or a protein in that.\n\n{answer.HELP_TEXT}"

    async def handle_chat(self, ctx: Context, sender: str, message: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=message.msg_id))
        text, selection = read_message(message)
        if not text and not selection:
            return
        request = intent.parse(text, selection)
        ctx.logger.info(f"request from {sender[:16]}: {request.action} drug={request.drug or request.drug_words} "
                        f"target={request.target_words} focus={request.focus}")
        if request.action == intent.HELP:
            await ctx.send(sender, text_message(answer.HELP_TEXT))
            return
        if request.action == intent.LIST_DRUGS:
            drug, target_drugs, problem = await self.drug_from_target(request.target_words, request.target_effect)
            if problem:
                await ctx.send(sender, text_message(problem))
                return
            names = ", ".join(drug.name for drug in target_drugs.drugs)
            await ctx.send(sender, card_message(
                f"ChEMBL lists {len(target_drugs.drugs)} approved drugs acting on {target_drugs.target_name}: "
                f"{names}. Pick one to check its predicted side effects.",
                "carousel", answer.target_choices_card(target_drugs), ctx.logger,
            ))
            return
        drug, target_drugs, problem = await self.resolve(ctx, sender, request)
        if problem:
            await ctx.send(sender, text_message(problem))
            return
        ctx.storage.set(f"last_drug:{sender}", drug)
        if request.action == intent.FULL_REPORT:
            if settings.payment_enabled():
                await self.request_payment(ctx, sender, drug)
            else:
                await ctx.send(sender, text_message(answer.full_report_text(await self.gather(ctx, drug))))
            return
        assembled = await self.gather(ctx, drug)
        summary = answer.summary_text(assembled, focus=request.focus, target_drugs=target_drugs)
        card = answer.summary_card(assembled, focus=request.focus, target_drugs=target_drugs)
        await ctx.send(sender, card_message(summary, "custom", card, ctx.logger))

    async def request_payment(self, ctx: Context, sender: str, drug: str):
        price = settings.full_report_price_fet()
        reference = str(uuid4())
        network = "stable-testnet" if settings.fet_use_testnet() else "mainnet"
        ctx.storage.set(f"invoice:{reference}", {"drug": drug, "sender": sender, "amount": price})
        ctx.storage.set(f"open_invoice:{sender}", reference)
        description = (f"Knockout full report for {drug}: every prediction with its label quote, FDA report counts, "
                       f"sources and trend")
        await ctx.send(sender, text_message(
            f"The full report for {drug} costs {price} FET ({network}). Approve the payment request and the report "
            f"follows here once the transfer is confirmed on the Fetch.ai ledger. The summary stays free."
        ))
        await ctx.send(sender, RequestPayment(
            accepted_funds=[Funds(currency="FET", amount=price, payment_method="fet_direct")],
            recipient=self.wallet_address(),
            deadline_seconds=300,
            reference=reference,
            description=description,
            metadata={
                "agent": AGENT_SPECS["orchestrator"].name,
                "service": "full_report",
                "drug": drug,
                "fet_network": network,
                "mainnet": "false" if settings.fet_use_testnet() else "true",
                "provider_agent_wallet": self.wallet_address(),
                "content": description,
            },
        ))

    async def handle_commit(self, ctx: Context, sender: str, commit: CommitPayment):
        reference = commit.reference or ctx.storage.get(f"open_invoice:{sender}")
        invoice = ctx.storage.get(f"invoice:{reference}") if reference else None
        if invoice is None or invoice.get("sender") != sender:
            await ctx.send(sender, CancelPayment(transaction_id=commit.transaction_id,
                                                 reason="no open invoice from Knockout matches this payment"))
            return
        if commit.funds.payment_method != "fet_direct" or commit.funds.currency != "FET":
            await ctx.send(sender, CancelPayment(transaction_id=commit.transaction_id,
                                                 reason="Knockout accepts FET by direct transfer only"))
            return
        used = ctx.storage.get(PAID_TRANSACTIONS_KEY) or []
        if commit.transaction_id in used:
            await ctx.send(sender, CancelPayment(transaction_id=commit.transaction_id,
                                                 reason="this transaction already paid for a report"))
            return
        # claimed before the await, so a second commit with the same hash cannot slip past the check
        ctx.storage.set(PAID_TRANSACTIONS_KEY, [*used, commit.transaction_id])
        metadata = commit.metadata or {}
        buyer = metadata.get("buyer_fet_wallet") or metadata.get("buyer_fet_address")
        verification = await payments.verify_payment(
            commit.transaction_id, recipient=self.wallet_address(), amount_fet=invoice["amount"],
            sender=buyer if isinstance(buyer, str) else None,
        )
        if not verification.paid:
            claimed = ctx.storage.get(PAID_TRANSACTIONS_KEY) or []
            ctx.storage.set(PAID_TRANSACTIONS_KEY, [item for item in claimed if item != commit.transaction_id])
            ctx.logger.warning(f"payment {commit.transaction_id} not accepted: {verification.reason}")
            await ctx.send(sender, CancelPayment(transaction_id=commit.transaction_id, reason=verification.reason))
            await ctx.send(sender, text_message(f"The payment could not be confirmed: {verification.reason}. "
                                                f"Nothing was released; ask for the full report to try again."))
            return
        ctx.storage.remove(f"invoice:{reference}")
        await ctx.send(sender, CompletePayment(transaction_id=commit.transaction_id))
        assembled = await self.gather(ctx, invoice["drug"])
        await ctx.send(sender, text_message(answer.full_report_text(assembled)))

    async def handle_reject(self, ctx: Context, sender: str, rejection: RejectPayment):
        ctx.storage.remove(f"open_invoice:{sender}")
        await ctx.send(sender, text_message(
            f"No payment was made{': ' + rejection.reason if rejection.reason else ''}. The free summary above "
            f"stands; ask for the full report any time."
        ))


def attach_orchestrator(agent: Agent, addresses: dict[str, str]) -> Orchestrator:
    orchestrator = Orchestrator(agent, addresses)
    chat = Protocol(spec=chat_protocol_spec)
    payment = Protocol(spec=payment_protocol_spec, role="seller")

    @chat.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, message: ChatMessage):
        try:
            with observability.chat_transaction(None):
                await orchestrator.handle_chat(ctx, sender, message)
        except Exception as error:  # the person always hears back, with what broke
            ctx.logger.exception("chat handler failed")
            await ctx.send(sender, text_message(f"Knockout hit an internal error ({error.__class__.__name__}: "
                                                f"{error}). Nothing was predicted; please ask again."))

    @chat.on_message(ChatAcknowledgement)
    async def on_acknowledgement(ctx: Context, sender: str, acknowledgement: ChatAcknowledgement):
        return None

    @payment.on_message(CommitPayment)
    async def on_commit(ctx: Context, sender: str, commit: CommitPayment):
        await orchestrator.handle_commit(ctx, sender, commit)

    @payment.on_message(RejectPayment)
    async def on_reject(ctx: Context, sender: str, rejection: RejectPayment):
        await orchestrator.handle_reject(ctx, sender, rejection)

    agent.include(chat, publish_manifest=True)
    agent.include(payment, publish_manifest=True)
    return orchestrator
