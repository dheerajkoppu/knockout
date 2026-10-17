"""Prints each agent's address from its seed, and with --write fills the table in agents/README.md.

    python -m knockout_agents.addresses               seeds from agents/.env
    python -m knockout_agents.addresses --test-seeds  the public test seeds used by the tests
"""

import argparse
import re

from knockout_agents.build import address_for_seed
from knockout_agents.settings import AGENT_SPECS, AGENTS_DIR, seed_for

README_PATH = AGENTS_DIR / "README.md"
START_MARKER = "<!-- addresses:start -->"
END_MARKER = "<!-- addresses:end -->"


def table(*, test_seeds: bool) -> str:
    rows = ["| Agent | Address | Does |", "| --- | --- | --- |"]
    for spec in AGENT_SPECS.values():
        address = address_for_seed(seed_for(spec, allow_test_seed=test_seeds))
        rows.append(f"| `{spec.name}` | `{address}` | {spec.description} |")
    return "\n".join(rows)


def write_readme(markdown: str) -> None:
    text = README_PATH.read_text()
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.S)
    if not pattern.search(text):
        raise SystemExit(f"{README_PATH} has no {START_MARKER} ... {END_MARKER} block")
    README_PATH.write_text(pattern.sub(f"{START_MARKER}\n{markdown}\n{END_MARKER}", text))


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the Knockout agent addresses")
    parser.add_argument("--test-seeds", action="store_true", help="use the public test seeds")
    parser.add_argument("--write", action="store_true", help="write the table into agents/README.md")
    arguments = parser.parse_args()
    if arguments.write and arguments.test_seeds:
        raise SystemExit("refusing to write test-seed addresses into the README")
    markdown = table(test_seeds=arguments.test_seeds)
    print(markdown)
    if arguments.write:
        write_readme(markdown)
        print(f"\nwrote {README_PATH}")


if __name__ == "__main__":
    main()
