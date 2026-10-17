"""Builds the five agents from their seeds."""

import asyncio
from pathlib import Path

from uagents import Agent, Context
from uagents_core.identity import Identity

from knockout_agents import settings
from knockout_agents.orchestrator import attach_orchestrator
from knockout_agents.settings import AGENT_SPECS, AgentSpec
from knockout_agents.specialists import attach_specialist

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
SPECIALIST_KEYS = ("target", "genetics", "label", "signal")


def address_for_seed(seed: str) -> str:
    return Identity.from_seed(seed, 0).address


def inspector_url(port: int, address: str) -> str:
    return f"https://agentverse.ai/inspect/?uri=http%3A//127.0.0.1%3A{port}&address={address}"


def make_agent(spec: AgentSpec, seed: str, *, mailbox: bool, port: int | None = None,
               endpoint: list[str] | None = None, loop: asyncio.AbstractEventLoop | None = None) -> Agent:
    return Agent(
        name=spec.name,
        seed=seed,
        port=port,
        mailbox=mailbox,
        endpoint=None if mailbox else endpoint,
        readme_path=str(PROFILES_DIR / f"{spec.key}.md"),
        description=spec.description,
        publish_agent_details=True,
        handle_messages_concurrently=True,
        loop=loop,
    )


def build(keys: tuple[str, ...], *, mailbox_keys: set[str], allow_test_seeds: bool = False, port: int | None = None,
          endpoint: list[str] | None = None, loop: asyncio.AbstractEventLoop | None = None) -> dict[str, Agent]:
    seeds = {key: settings.seed_for(AGENT_SPECS[key], allow_test_seed=allow_test_seeds) for key in keys}
    agents = {}
    for key in keys:
        agent_port = port or AGENT_SPECS[key].port
        # None: the agent's own port; []: no endpoint, because a Bureau or the local dispatcher delivers
        agent_endpoint = endpoint if endpoint is not None else [f"http://127.0.0.1:{agent_port}/submit"]
        agents[key] = make_agent(AGENT_SPECS[key], seeds[key], mailbox=key in mailbox_keys, port=agent_port,
                                 endpoint=agent_endpoint, loop=loop)
    for key in keys:
        if key in SPECIALIST_KEYS:
            attach_specialist(agents[key], AGENT_SPECS[key])
    if "orchestrator" in agents:
        addresses = specialist_addresses(agents, allow_test_seeds=allow_test_seeds)
        attach_orchestrator(agents["orchestrator"], addresses)
    for key, agent in agents.items():
        _log_identity(agent, AGENT_SPECS[key], port or AGENT_SPECS[key].port)
    return agents


def specialist_addresses(agents: dict[str, Agent], *, allow_test_seeds: bool) -> dict[str, str]:
    """Specialists in this process first, then AGENT_ADDRESS_* overrides, then addresses derived from seeds."""
    addresses = {}
    configured = settings.specialist_addresses()
    for key in SPECIALIST_KEYS:
        if key in agents:
            addresses[key] = agents[key].address
        elif key in configured:
            addresses[key] = configured[key]
        else:
            try:
                addresses[key] = address_for_seed(settings.seed_for(AGENT_SPECS[key], allow_test_seed=allow_test_seeds))
            except RuntimeError:
                continue
    return addresses


def _log_identity(agent: Agent, spec: AgentSpec, port: int) -> None:
    @agent.on_event("startup")
    async def announce(ctx: Context):
        ctx.logger.info(f"{spec.name} address {agent.address}")
        ctx.logger.info(f"{spec.name} inspector {inspector_url(port, agent.address)}")
