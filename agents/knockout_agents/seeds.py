"""Prints a new random seed for every agent whose seed is not set yet, ready to append to agents/.env.

    python -m knockout_agents.seeds >> .env
"""

import os
import secrets

from knockout_agents.settings import AGENT_SPECS


def main() -> None:
    for spec in AGENT_SPECS.values():
        if not os.environ.get(spec.seed_variable):
            print(f"{spec.seed_variable}={secrets.token_urlsafe(32)}")


if __name__ == "__main__":
    main()
