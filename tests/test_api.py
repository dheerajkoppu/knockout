"""API tests. The engine is stubbed with a hand-built test report; nothing here is a real prediction."""

import asyncio
import os
import time

import pytest

import knockout.config  # noqa: F401  (loads .env first, so the next line wins)

os.environ.pop("SENTRY_DSN", None)
# Adding to the watchlist starts a real Creao run when these are set.
os.environ.pop("CREAO_API_KEY", None)

import sentry_sdk
from fastapi.testclient import TestClient

from knockout import api, engine, gemini, mapping, observability
from knockout.http import SourceError
from knockout.store_files import FileStore

SECRET = "test-webhook-secret"


def stub_report(query: str) -> engine.Report:
    report = engine.Report(
        query=query,
        generated_at="2026-10-17T20:00:00+00:00",
        molecule={"chembl_id": "CHEMBL_TEST", "name": "TESTMAB", "max_phase": 4, "molecule_type": "Antibody",
                  "url": "https://example.invalid/test"},
    )
    report.predictions.append(
        engine.Prediction(
            hpo_id="HP:0000000", phenotype="Test phenotype", frequency="1/1", kind="clinical", gene="TEST",
            target="Test protein", disease_id="test-deficiency", disease="Test deficiency",
            reaction_terms=["TEST REACTION"],
        )
    )
    return report


@pytest.fixture
def store(tmp_path):
    return FileStore(tmp_path / "store")


@pytest.fixture
def engine_calls(monkeypatch):
    calls = []

    def fake_predict(query, **options):
        calls.append(query)
        return stub_report(query)

    monkeypatch.setattr(engine, "predict", fake_predict)
    return calls


@pytest.fixture
def client(store):
    return TestClient(api.create_app(store=store))


def test_health_reports_keys_and_store(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "set-for-test")
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)
    assert client.get("/api/health").json() == {
        "status": "ok", "gemini_key": True, "openfda_key": False, "store": "files",
    }


def test_report_runs_the_engine_once_and_then_reads_the_cache(client, engine_calls):
    first = client.get("/api/drugs/Eculizumab/report")
    assert first.status_code == 200
    body = first.json()
    assert body["molecule"]["name"] == "TESTMAB"
    assert body["predictions"][0]["reaction_terms"] == ["TEST REACTION"]
    assert body["cached_at"]

    second = client.get("/api/drugs/eculizumab%20/report")
    assert second.status_code == 200
    assert second.json()["predictions"] == body["predictions"]
    assert engine_calls == ["eculizumab"]

    client.get("/api/drugs/eculizumab/report", params={"refresh": "true"})
    assert engine_calls == ["eculizumab", "eculizumab"]


def test_unknown_drug_is_404_and_not_cached(client, store, monkeypatch):
    def no_molecule(query, **options):
        report = engine.Report(query=query, generated_at="2026-10-17T20:00:00+00:00")
        report.problems.append(f"ChEMBL has no molecule named {query!r}")
        return report

    monkeypatch.setattr(engine, "predict", no_molecule)
    response = client.get("/api/drugs/notadrug/report")
    assert response.status_code == 404
    assert "ChEMBL has no molecule" in response.json()["detail"]
    assert store.get_report("notadrug") is None


def test_source_failure_is_502_without_the_api_key(client, monkeypatch):
    def failing(query, **options):
        raise SourceError("https://api.fda.gov/drug/event.json?search=x&api_key=REALKEY: HTTP 500")

    monkeypatch.setattr(engine, "predict", failing)
    response = client.get("/api/drugs/eculizumab/report")
    assert response.status_code == 502
    assert "REALKEY" not in response.text


def test_report_cached_without_gemini_reruns_once_the_key_exists(client, store, engine_calls, monkeypatch):
    stale = stub_report("eculizumab").to_dict()
    stale["problems"] = ["Step 5 could not map new phenotypes: GEMINI_API_KEY is not set in .env"]
    store.save_report("eculizumab", stale)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client.get("/api/drugs/eculizumab/report")
    assert engine_calls == []

    monkeypatch.setenv("GEMINI_API_KEY", "set-for-test")
    client.get("/api/drugs/eculizumab/report")
    assert engine_calls == ["eculizumab"]


def test_concurrent_requests_share_one_engine_run(store, monkeypatch):
    calls = []

    def slow_predict(query, **options):
        calls.append(query)
        time.sleep(0.3)
        return stub_report(query)

    monkeypatch.setattr(engine, "predict", slow_predict)
    runner = api.ReportRunner(store)

    async def both():
        return await asyncio.gather(runner.report("Eculizumab"), runner.report("eculizumab"))

    first, second = asyncio.run(both())
    assert calls == ["eculizumab"]
    assert first["predictions"] == second["predictions"]


def test_an_infinite_prr_is_sent_as_null_with_a_flag(client, monkeypatch):
    def infinite(query, **options):
        report = stub_report(query)
        report.predictions[0].counts = [{"term": "TEST REACTION", "a": 3, "drug": 10, "reaction": 3,
                                         "all": 1000, "prr": float("inf"), "signal": True}]
        return report

    monkeypatch.setattr(engine, "predict", infinite)
    for attempt in range(2):
        response = client.get("/api/drugs/testmab/report")
        assert response.status_code == 200
        counts = response.json()["predictions"][0]["counts"][0]
        assert counts["prr"] is None
        assert counts["prr_infinite"] is True


def test_watchlist_adds_once(client):
    assert client.get("/api/watchlist").json() == {"drugs": []}
    assert client.post("/api/watchlist", json={"drug": "Eculizumab"}).json() == {"drugs": ["eculizumab"]}
    assert client.post("/api/watchlist", json={"drug": "eculizumab"}).json() == {"drugs": ["eculizumab"]}
    assert client.post("/api/watchlist", json={"drug": "ibrutinib"}).json() == {"drugs": ["eculizumab", "ibrutinib"]}
    assert client.post("/api/watchlist", json={"drug": ""}).status_code == 422


def signal_run(run_id, run_at, terms):
    return {"drug": "Eculizumab", "run_id": run_id, "run_at": run_at, "terms": terms}


def term(quarter, reports, prr, signal, name="Meningococcal infection"):
    return {"term": name, "quarter": quarter, "reports": reports, "prr": prr, "signal": signal}


def test_webhook_needs_the_shared_secret(client, monkeypatch):
    body = signal_run("run-1", "2026-10-17T20:00:00Z", [term("2025Q1", 1, 1.5, False)])
    monkeypatch.delenv("KNOCKOUT_WEBHOOK_SECRET", raising=False)
    assert client.post("/api/webhooks/creao/signals", json=body).status_code == 503

    monkeypatch.setenv("KNOCKOUT_WEBHOOK_SECRET", SECRET)
    assert client.post("/api/webhooks/creao/signals", json=body).status_code == 401
    wrong = {"X-Knockout-Webhook-Secret": "wrong"}
    assert client.post("/api/webhooks/creao/signals", json=body, headers=wrong).status_code == 401
    right = {"X-Knockout-Webhook-Secret": SECRET}
    assert client.post("/api/webhooks/creao/signals", json=body, headers=right).json() == {"stored": 1, "alerts": 0}


def test_webhook_rejects_a_malformed_quarter(client, monkeypatch):
    monkeypatch.setenv("KNOCKOUT_WEBHOOK_SECRET", SECRET)
    body = signal_run("run-1", "2026-10-17T20:00:00Z", [term("2025-01", 1, 1.5, False)])
    response = client.post("/api/webhooks/creao/signals", json=body, headers={"X-Knockout-Webhook-Secret": SECRET})
    assert response.status_code == 422


def test_webhook_runs_build_the_trend_and_threshold_alerts(client, monkeypatch):
    monkeypatch.setenv("KNOCKOUT_WEBHOOK_SECRET", SECRET)
    headers = {"X-Knockout-Webhook-Secret": SECRET}
    first = signal_run("run-1", "2026-10-17T20:00:00Z", [
        term("2025Q1", 1, 1.2, False), term("2025Q2", 2, 1.8, False),
    ])
    assert client.post("/api/webhooks/creao/signals", json=first, headers=headers).json() == {"stored": 2, "alerts": 0}

    second = signal_run("run-2", "2026-10-17T21:00:00Z", [
        term("2025Q2", 3, 2.4, True), term("2025Q3", 4, 2.9, True),
    ])
    assert client.post("/api/webhooks/creao/signals", json=second, headers=headers).json() == {"stored": 2, "alerts": 1}
    # The same run sent again, later, updates its rows and raises no second alert.
    replay = second | {"run_at": "2026-10-17T23:00:00Z"}
    assert client.post("/api/webhooks/creao/signals", json=replay, headers=headers).json() == {"stored": 2, "alerts": 0}

    trend = client.get("/api/drugs/eculizumab/trend").json()
    assert trend == {
        "drug": "eculizumab",
        "terms": [{"term": "MENINGOCOCCAL INFECTION", "source": "report", "quarters": [
            {"quarter": "2025Q1", "reports": 1, "prr": 1.2, "signal": False},
            {"quarter": "2025Q2", "reports": 3, "prr": 2.4, "signal": True},
            {"quarter": "2025Q3", "reports": 4, "prr": 2.9, "signal": True},
        ]}],
        "last_run_at": "2026-10-17T21:00:00+00:00",
    }
    assert client.get("/api/drugs/Eculizumab/alerts").json() == {
        "drug": "eculizumab",
        "alerts": [{"term": "MENINGOCOCCAL INFECTION", "quarter": "2025Q3", "prr": 2.9,
                    "crossed_at": "2026-10-17T21:00:00+00:00", "run_id": "run-2"}],
    }


def test_trend_and_alerts_are_empty_before_any_run(client):
    assert client.get("/api/drugs/ibrutinib/trend").json() == {"drug": "ibrutinib", "terms": [], "last_run_at": None}
    assert client.get("/api/drugs/ibrutinib/alerts").json() == {"drug": "ibrutinib", "alerts": []}


def test_the_first_run_of_a_drug_is_the_baseline(store):
    stored, alerts = store.save_signal_run(
        signal_run("run-1", "2026-10-17T20:00:00Z", [term("2025Q1", 1, 1.0, False), term("2025Q2", 9, 3.0, True)])
    )
    assert (stored, alerts) == (2, 0)


def test_only_a_false_to_true_change_in_the_latest_quarter_alerts(store):
    store.save_signal_run(signal_run("run-1", "2026-10-17T20:00:00Z", [
        term("2025Q1", 9, 3.0, True), term("2025Q1", 1, 1.0, False, name="Headache"),
    ]))
    stored, alerts = store.save_signal_run(signal_run("run-2", "2026-10-17T21:00:00Z", [
        term("2025Q1", 9, 3.0, True), term("2025Q1", 2, 1.1, False, name="Headache"),
        term("2025Q1", 5, 4.0, True, name="Sepsis"),
    ]))
    assert (stored, alerts) == (3, 0)


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        ("http://localhost:3000", True),
        ("https://knockout.vercel.app", True),
        ("https://knockout-git-main-team.vercel.app", True),
        ("https://knockout.vercel.app.evil.example", False),
        ("http://knockout.vercel.app", False),
        ("https://evil.example", False),
    ],
)
def test_cors_allows_localhost_and_vercel_only(client, origin, allowed):
    response = client.options(
        "/api/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    assert (response.headers.get("access-control-allow-origin") == origin) is allowed


def test_scrub_removes_query_string_keys():
    assert observability.scrub("https://api.fda.gov/drug/event.json?search=x&api_key=REALKEY") == (
        "https://api.fda.gov/drug/event.json?search=x&api_key=[Filtered]"
    )
    assert observability.scrub({"url": ["models?pageSize=1000&key=GEMINIKEY"]}) == {
        "url": ["models?pageSize=1000&key=[Filtered]"]
    }


class CapturingTransport(sentry_sdk.Transport):
    def __init__(self):
        super().__init__()
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


@pytest.fixture
def sentry_capture():
    transport = CapturingTransport()
    sentry_sdk.init(dsn="https://public@sentry.invalid/1", transport=transport, traces_sample_rate=1.0)
    yield transport
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)


def captured_spans(transport):
    """Spans from transaction items and from the separate span items the SDK uses for gen_ai spans."""
    sentry_sdk.flush()
    spans = []
    for envelope in transport.envelopes:
        for item in envelope.items:
            if item.type == "transaction":
                spans.extend(item.payload.json.get("spans", []))
            elif item.type == "span":
                for row in item.payload.json.get("items", []):
                    attributes = {key: value["value"] for key, value in row.get("attributes", {}).items()}
                    spans.append({"op": attributes.get("sentry.op"), "description": row.get("name"), "data": attributes})
    return spans


def test_gemini_calls_become_gen_ai_spans(sentry_capture, monkeypatch):
    monkeypatch.setattr(gemini, "model", lambda: "gemini-test-flash")

    def fake_post_json(url, payload, headers):
        return {"usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40, "totalTokenCount": 160},
                "modelVersion": "gemini-test-flash-001", "candidates": [{"finishReason": "STOP"}]}

    recorded_post = observability.recording_usage(fake_post_json)

    def fake_generate_json(prompt, schema):
        recorded_post("https://example.invalid/generateContent", {}, {})
        return {"terms": [{"hpo_id": "HP:0005381", "kind": "clinical", "reaction_terms": ["TEST REACTION"]}]}

    traced = observability.traced_generate_json(fake_generate_json)
    agent = observability.traced_mapping(lambda terms: {hpo_id: object() for hpo_id in terms})
    with sentry_sdk.start_transaction(op="test", name="mapping test"):
        agent({"HP:0005381": "Recurrent Neisseria meningitidis infection"})
        answer = traced("- HP:0005381: Recurrent Neisseria meningitidis infection", {})

    assert answer["terms"][0]["reaction_terms"] == ["TEST REACTION"]
    spans = {span["op"]: span for span in captured_spans(sentry_capture)}
    chat = spans["gen_ai.chat"]
    assert chat["description"] == "chat gemini-test-flash"
    assert chat["data"]["gen_ai.system"] == "gcp.gemini"
    assert chat["data"]["gen_ai.request.model"] == "gemini-test-flash"
    assert chat["data"]["gen_ai.response.model"] == "gemini-test-flash-001"
    assert chat["data"]["gen_ai.usage.input_tokens"] == 120
    assert chat["data"]["gen_ai.usage.total_tokens"] == 160
    assert "HP:0005381" in chat["data"]["gen_ai.request.messages"]
    invoke = spans["gen_ai.invoke_agent"]
    assert invoke["data"]["gen_ai.agent.name"] == observability.MAPPER_AGENT
    assert invoke["data"]["knockout.terms_mapped"] == 1


def test_instrumenting_gemini_patches_once(monkeypatch):
    monkeypatch.setattr(gemini, "generate_json", gemini.generate_json)
    monkeypatch.setattr(gemini, "post_json", gemini.post_json)
    monkeypatch.setattr(mapping, "ensure", mapping.ensure)
    original = gemini.generate_json
    observability.instrument_gemini()
    observability.instrument_gemini()
    assert gemini.generate_json._knockout_traced
    assert gemini.generate_json.__wrapped__ is original
    assert mapping.ensure._knockout_traced


def test_writes_that_spend_quota_need_the_secret_once_it_is_set(client, engine_calls, monkeypatch):
    monkeypatch.setenv("KNOCKOUT_WEBHOOK_SECRET", SECRET)
    assert client.post("/api/watchlist", json={"drug": "eculizumab"}).status_code == 401
    assert client.get("/api/drugs/eculizumab/report", params={"refresh": "true"}).status_code == 401
    assert engine_calls == []
    headers = {"X-Knockout-Webhook-Secret": SECRET}
    assert client.post("/api/watchlist", json={"drug": "eculizumab"}, headers=headers).json() == {
        "drugs": ["eculizumab"]}
    assert client.get("/api/drugs/eculizumab/report", params={"refresh": "true"}, headers=headers).status_code == 200


def test_the_watchlist_has_a_limit(client, monkeypatch):
    monkeypatch.delenv("KNOCKOUT_WEBHOOK_SECRET", raising=False)
    for number in range(api.WATCHLIST_LIMIT):
        assert client.post("/api/watchlist", json={"drug": f"drug {number}"}).status_code == 200
    assert client.post("/api/watchlist", json={"drug": "one more"}).status_code == 409
    assert client.post("/api/watchlist", json={"drug": "drug 0"}).status_code == 200


def test_a_brand_name_report_is_also_stored_under_the_molecule(client, store, engine_calls):
    client.get("/api/drugs/soliris/report")
    assert store.get_report("testmab")["query"] == "soliris"


def test_an_infinite_prr_from_the_watch_agent_comes_back_flagged(client, monkeypatch):
    monkeypatch.setenv("KNOCKOUT_WEBHOOK_SECRET", SECRET)
    headers = {"X-Knockout-Webhook-Secret": SECRET}
    body = signal_run("run-1", "2026-10-17T20:00:00Z", [term("2025Q1", 5, None, True) | {"prr_infinite": True}])
    body["term_source"] = "manual"
    assert client.post("/api/webhooks/creao/signals", json=body, headers=headers).json() == {"stored": 1, "alerts": 0}
    trend = client.get("/api/drugs/eculizumab/trend").json()
    assert trend["terms"][0]["source"] == "manual"
    assert trend["terms"][0]["quarters"][0] == {
        "quarter": "2025Q1", "reports": 5, "prr": None, "prr_infinite": True, "signal": True}
