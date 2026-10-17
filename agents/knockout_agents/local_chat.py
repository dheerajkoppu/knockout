"""All five agents plus a stand-in for the ASI:One user, in one process with no network registration.

Used by `python -m knockout_agents.ask` and by the tests. Messages travel through uAgents' local dispatcher, so
the orchestrator, the specialists and the protocols run exactly as they do on Agentverse.
"""

import asyncio
import contextlib

from uagents import Agent, Context, Model, Protocol
from uagents.dispatch import dispatcher
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CompletePayment,
    RequestPayment,
    payment_protocol_spec,
)

from knockout_agents import build
from knockout_agents.settings import AGENT_SPECS

LOCAL_USER_SEED = "knockout-public-test-seed-local-user"


async def _no_status_update(active: bool) -> None:
    return None


async def _no_manifest(self, manifest: dict) -> None:
    return None


class LocalChat:
    def __init__(self, *, allow_test_seeds: bool = True):
        self.loop = asyncio.get_running_loop()
        self.inbox: asyncio.Queue[tuple[str, Model]] = asyncio.Queue()
        original_publish = Agent.publish_manifest
        Agent.publish_manifest = _no_manifest
        try:
            self.agents = build.build(tuple(AGENT_SPECS), mailbox_keys=set(), allow_test_seeds=allow_test_seeds,
                                      endpoint=[], loop=self.loop)
        finally:
            Agent.publish_manifest = original_publish
        self.user = Agent(name="local-user", seed=LOCAL_USER_SEED, loop=self.loop, enable_agent_inspector=False)
        self._attach_user_protocols()
        self.everyone = [*self.agents.values(), self.user]
        for agent in self.everyone:
            # no endpoint means no registration; the local dispatcher still delivers every message
            agent._update_agent_status = _no_status_update
            agent._shutdown_timeout = 5
        self.context = self.user._build_context()

    @property
    def orchestrator(self) -> Agent:
        return self.agents["orchestrator"]

    def _attach_user_protocols(self) -> None:
        chat = Protocol(spec=chat_protocol_spec)
        payment = Protocol(spec=payment_protocol_spec, role="buyer")
        inbox = self.inbox

        @chat.on_message(ChatMessage)
        async def on_chat(ctx: Context, sender: str, message: ChatMessage):
            await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=message.msg_id))
            await inbox.put((sender, message))

        @chat.on_message(ChatAcknowledgement)
        async def on_acknowledgement(ctx: Context, sender: str, acknowledgement: ChatAcknowledgement):
            await inbox.put((sender, acknowledgement))

        @payment.on_message(RequestPayment)
        async def on_request(ctx: Context, sender: str, request: RequestPayment):
            await inbox.put((sender, request))

        @payment.on_message(CompletePayment)
        async def on_complete(ctx: Context, sender: str, complete: CompletePayment):
            await inbox.put((sender, complete))

        @payment.on_message(CancelPayment)
        async def on_cancel(ctx: Context, sender: str, cancel: CancelPayment):
            await inbox.put((sender, cancel))

        self.user.include(chat)
        self.user.include(payment)

    async def start(self) -> None:
        for agent in self.everyone:
            agent.setup()
        await asyncio.sleep(0.2)

    async def stop(self) -> None:
        for agent in self.everyone:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(agent._shutdown([]), timeout=10)
            with contextlib.suppress(Exception):
                dispatcher.unregister(agent.address, agent)

    async def say(self, text: str, *, start_session: bool = False) -> None:
        content = [StartSessionContent(), TextContent(text=text)] if start_session else [TextContent(text=text)]
        await self.context.send(self.orchestrator.address, ChatMessage(content=content))

    async def send(self, message: Model) -> None:
        await self.context.send(self.orchestrator.address, message)

    async def next(self, kinds: tuple[type, ...], timeout: float = 60.0) -> Model:
        """The next message of one of these types; acknowledgements and other types are skipped."""
        deadline = self.loop.time() + timeout
        while True:
            remaining = deadline - self.loop.time()
            if remaining <= 0:
                raise TimeoutError(f"no {', '.join(kind.__name__ for kind in kinds)} within {timeout:.0f} s")
            _, message = await asyncio.wait_for(self.inbox.get(), timeout=remaining)
            if isinstance(message, kinds):
                return message
