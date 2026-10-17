"""Tests for creao/trigger.py against a mocked CREAO API Trigger. The key and ids are fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trigger

FIXTURE_KEY = "capi_fixture"
FIXTURE_AGENT = "fixture-agent-id"


class FakeCreao:
    def __init__(self, statuses: list[str]):
        self.statuses = list(statuses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("Authorization") != f"Bearer {FIXTURE_KEY}":
            return httpx.Response(401, json={"error": "unauthorized"})
        if request.method == "POST" and request.url.path == "/api/v1/runs":
            return httpx.Response(
                202, json={"id": "fixture-run", "status": "pending", "appId": FIXTURE_AGENT}
            )
        if request.method == "GET" and request.url.path == "/api/v1/runs/fixture-run":
            status = self.statuses.pop(0)
            body = {"id": "fixture-run", "status": status}
            if status == "completed":
                body["threadId"] = "fixture-thread"
            return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": "no route"})


def make_trigger(fake: FakeCreao, key: str = FIXTURE_KEY) -> trigger.CreaoTrigger:
    return trigger.CreaoTrigger(httpx.Client(transport=httpx.MockTransport(fake)), key, FIXTURE_AGENT)


def test_start_sends_the_agent_inputs_and_optional_fields():
    fake = FakeCreao([])
    run = make_trigger(fake).start({"drugs": "eculizumab"}, "https://example.test/hook", "watch-fixture-0001")
    assert run["status"] == "pending"
    request = fake.requests[0]
    assert request.url == "https://agent.creao.ai/api/v1/runs"
    assert json.loads(request.content) == {
        "appId": FIXTURE_AGENT,
        "inputs": {"drugs": "eculizumab"},
        "webhookUrl": "https://example.test/hook",
        "idempotencyKey": "watch-fixture-0001",
    }


def test_wait_polls_until_the_run_finishes():
    pauses = []
    run = make_trigger(FakeCreao(["pending", "running", "completed"])).wait(
        "fixture-run", sleep=pauses.append
    )
    assert run == {"id": "fixture-run", "status": "completed", "threadId": "fixture-thread"}
    assert pauses == [trigger.POLL_SECONDS, trigger.POLL_SECONDS]


def test_wait_gives_up_after_the_limit():
    fake = FakeCreao(["running"] * 5)
    with pytest.raises(trigger.TriggerError):
        make_trigger(fake).wait("fixture-run", poll_seconds=10, wait_seconds=20, sleep=lambda seconds: None)


def test_a_rejected_key_is_an_error():
    with pytest.raises(trigger.TriggerError, match="401"):
        make_trigger(FakeCreao([]), key="capi_wrong").start()


def test_missing_settings_are_refused(monkeypatch):
    monkeypatch.delenv("CREAO_API_KEY", raising=False)
    monkeypatch.delenv("CREAO_AGENT_ID", raising=False)
    assert trigger.main([]) == 2
