"""Connects the running agents to Agentverse mailboxes, the same call the Agent Inspector's Connect button makes.

Start the agents first (python -m knockout_agents.run), then in another terminal:

    AGENTVERSE_API_KEY=... python -m knockout_agents.connect
"""

import argparse
import os

import httpx

from knockout_agents import settings
from knockout_agents.build import address_for_seed
from knockout_agents.settings import AGENT_SPECS


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect running Knockout agents to Agentverse mailboxes")
    parser.add_argument("--only", choices=sorted(AGENT_SPECS), help="connect one agent")
    parser.add_argument("--port", type=int, help="agent server port (default: the Bureau port, or the agent's port "
                                                  "with --only)")
    arguments = parser.parse_args()
    token = os.environ.get("AGENTVERSE_API_KEY") or ""
    if not token:
        raise SystemExit("Set AGENTVERSE_API_KEY (Agentverse → Profile → API Keys) in agents/.env or the shell.")
    mailbox_keys = settings.mailbox_keys()
    keys = [arguments.only] if arguments.only else [key for key in AGENT_SPECS if key in mailbox_keys]
    if not keys:
        raise SystemExit("AGENT_MAILBOX is false, so no agent uses a mailbox.")
    for key in keys:
        spec = AGENT_SPECS[key]
        port = arguments.port or (spec.port if arguments.only else settings.bureau_port())
        address = address_for_seed(settings.seed_for(spec))
        response = httpx.post(
            f"http://127.0.0.1:{port}/connect",
            json={"user_token": token, "agent_type": "mailbox"},
            headers={"x-uagents-address": address},
            timeout=60.0,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text[:200]}
        outcome = "connected" if response.status_code == 200 and body.get("success") else f"failed: {body}"
        print(f"{spec.name} {address}: {outcome}")


if __name__ == "__main__":
    main()
