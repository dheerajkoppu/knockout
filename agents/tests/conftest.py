import pytest

from fake_services import Services

SEED_VARIABLES = ("AGENT_SEED_ORCHESTRATOR", "AGENT_SEED_TARGET", "AGENT_SEED_GENETICS", "AGENT_SEED_LABEL",
                  "AGENT_SEED_SIGNAL")


@pytest.fixture
def services(monkeypatch, tmp_path):
    with Services() as running:
        monkeypatch.setenv("KNOCKOUT_API_URL", running.url)
        monkeypatch.setenv("CHEMBL_API_URL", f"{running.url}/chembl")
        monkeypatch.setenv("UNIPROT_API_URL", f"{running.url}/uniprot")
        monkeypatch.setenv("FET_REST_URL", f"{running.url}/ledger")
        monkeypatch.setenv("FET_USE_TESTNET", "true")
        monkeypatch.setenv("KNOCKOUT_PAYMENT_ENABLED", "true")
        monkeypatch.setenv("KNOCKOUT_FULL_REPORT_PRICE_FET", "0.1")
        monkeypatch.setenv("KNOCKOUT_API_TIMEOUT_SECONDS", "5")
        monkeypatch.setenv("KNOCKOUT_SPECIALIST_TIMEOUT_SECONDS", "15")
        monkeypatch.delenv("KNOCKOUT_REPORT_PAGE_URL", raising=False)
        for variable in SEED_VARIABLES:
            monkeypatch.delenv(variable, raising=False)
        # uAgents writes each agent's storage file into the working directory
        monkeypatch.chdir(tmp_path)
        yield running
