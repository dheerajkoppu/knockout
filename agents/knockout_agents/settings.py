"""Every setting comes from the environment. Seeds and keys are never written to the repository."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

AGENTS_DIR = Path(__file__).resolve().parents[1]
load_dotenv(AGENTS_DIR / ".env")
load_dotenv(AGENTS_DIR.parent / ".env")


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    seed_variable: str
    port: int
    description: str


AGENT_SPECS = {
    "orchestrator": AgentSpec(
        "orchestrator", "knockout-orchestrator", "AGENT_SEED_ORCHESTRATOR", 8101,
        "Answers drug side-effect questions in ASI:One by orchestrating four Knockout specialists",
    ),
    "target": AgentSpec(
        "target", "target-agent", "AGENT_SEED_TARGET", 8102,
        "Knockout step 1 and 2: a drug's protein targets and which way it pushes them (ChEMBL)",
    ),
    "genetics": AgentSpec(
        "genetics", "genetics-agent", "AGENT_SEED_GENETICS", 8103,
        "Knockout steps 3 to 5: genetic diseases of the target and their symptoms (IUIS, Orphanet, HPO)",
    ),
    "label": AgentSpec(
        "label", "label-agent", "AGENT_SEED_LABEL", 8104,
        "Knockout step 6: checks each predicted effect against the FDA label, quoting it verbatim",
    ),
    "signal": AgentSpec(
        "signal", "signal-agent", "AGENT_SEED_SIGNAL", 8105,
        "Knockout steps 7 and 8: FDA adverse-event report signals, trends and alerts",
    ),
}

TEST_SEED_PREFIX = "knockout-public-test-seed-"


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def seed_for(spec: AgentSpec, *, allow_test_seed: bool = False) -> str:
    seed = os.environ.get(spec.seed_variable) or ""
    if seed:
        return seed
    if allow_test_seed:
        return f"{TEST_SEED_PREFIX}{spec.key}"
    raise RuntimeError(
        f"{spec.seed_variable} is not set. Put a long random phrase in agents/.env "
        f"(see agents/.env.example) so {spec.name} keeps the same address."
    )


def api_url() -> str:
    return (os.environ.get("KNOCKOUT_API_URL") or "http://localhost:8000").rstrip("/")


def report_page_url() -> str | None:
    value = os.environ.get("KNOCKOUT_REPORT_PAGE_URL") or ""
    return value.rstrip("/") or None


def chembl_url() -> str:
    return (os.environ.get("CHEMBL_API_URL") or "https://www.ebi.ac.uk/chembl/api/data").rstrip("/")


def uniprot_url() -> str:
    return (os.environ.get("UNIPROT_API_URL") or "https://rest.uniprot.org").rstrip("/")


def api_timeout_seconds() -> float:
    return float(os.environ.get("KNOCKOUT_API_TIMEOUT_SECONDS") or 150)


def specialist_timeout_seconds() -> int:
    return int(os.environ.get("KNOCKOUT_SPECIALIST_TIMEOUT_SECONDS") or 180)


def mailbox_keys() -> set[str]:
    """AGENT_MAILBOX: true gives every agent a mailbox, "orchestrator" only the one ASI:One talks to, false none."""
    value = (os.environ.get("AGENT_MAILBOX") or "true").strip().lower()
    if value == "orchestrator":
        return {"orchestrator"}
    return set(AGENT_SPECS) if _flag("AGENT_MAILBOX", True) else set()


def bureau_port() -> int:
    return int(os.environ.get("KNOCKOUT_AGENTS_PORT") or 8100)


def specialist_addresses() -> dict[str, str]:
    """Addresses of specialists running elsewhere (for example hosted on Agentverse)."""
    addresses = {}
    for key in ("target", "genetics", "label", "signal"):
        value = os.environ.get(f"AGENT_ADDRESS_{key.upper()}") or ""
        if value:
            addresses[key] = value
    return addresses


def payment_enabled() -> bool:
    return _flag("KNOCKOUT_PAYMENT_ENABLED", True)


def full_report_price_fet() -> str:
    return os.environ.get("KNOCKOUT_FULL_REPORT_PRICE_FET") or "0.1"


def fet_use_testnet() -> bool:
    return _flag("FET_USE_TESTNET", True)


def fet_rest_url() -> str:
    default = "https://rest-dorado.fetch.ai" if fet_use_testnet() else "https://rest-fetchhub.fetch.ai"
    return (os.environ.get("FET_REST_URL") or default).rstrip("/")


def fet_denomination() -> str:
    return "atestfet" if fet_use_testnet() else "afet"
