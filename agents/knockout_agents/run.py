"""Runs the agents.

    python -m knockout_agents.run                       all five in one process, each with an Agentverse mailbox
    python -m knockout_agents.run --only orchestrator   one agent in its own process
    python -m knockout_agents.run --no-mailbox          local only, nothing reaches Agentverse
    AGENT_MAILBOX=orchestrator                          only the orchestrator gets a mailbox
"""

import argparse

from uagents import Bureau

from knockout_agents import build, observability, settings
from knockout_agents.settings import AGENT_SPECS


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Knockout Fetch.ai agents")
    parser.add_argument("--only", choices=sorted(AGENT_SPECS), help="run one agent in this process")
    parser.add_argument("--no-mailbox", action="store_true", help="do not connect to Agentverse")
    parser.add_argument("--test-seeds", action="store_true",
                        help="public test seeds for local runs; never register these on Agentverse")
    arguments = parser.parse_args()
    observability.setup()
    mailbox_keys = set() if arguments.no_mailbox else settings.mailbox_keys()
    if arguments.test_seeds and mailbox_keys:
        parser.error("--test-seeds needs --no-mailbox: anyone can derive the public test seeds, so agents on "
                     "Agentverse with them could be taken over")

    if arguments.only:
        agents = build.build((arguments.only,), mailbox_keys=mailbox_keys, allow_test_seeds=arguments.test_seeds)
        agents[arguments.only].run()
        return

    port = settings.bureau_port()
    agents = build.build(tuple(AGENT_SPECS), mailbox_keys=mailbox_keys, allow_test_seeds=arguments.test_seeds,
                         port=port, endpoint=[])
    # with no mailbox at all, the Bureau's own endpoint is what the Almanac registers
    endpoint = None if mailbox_keys else [f"http://127.0.0.1:{port}/submit"]
    bureau = Bureau(agents=list(agents.values()), port=port, endpoint=endpoint)
    bureau.run()


if __name__ == "__main__":
    main()
