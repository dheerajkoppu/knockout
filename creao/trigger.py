"""Start a run of the Knockout watch agent through the CREAO API Trigger, from a server, never a browser.

Environment: CREAO_API_KEY (a capi_ key from agent.creao.ai), CREAO_AGENT_ID (the agent's appId).
Runs take minutes, so callers start one and return; --wait polls until it finishes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from typing import Any

import httpx

CREAO_URL = "https://agent.creao.ai"
FINISHED = {"completed", "failed", "cancelled"}
POLL_SECONDS = 15.0
WAIT_SECONDS = 1_200.0


class TriggerError(RuntimeError):
    pass


class CreaoTrigger:
    def __init__(self, client: httpx.Client, api_key: str, agent_id: str, base_url: str = CREAO_URL):
        if not api_key or not agent_id:
            raise TriggerError("CREAO_API_KEY and CREAO_AGENT_ID must both be set")
        self.client = client
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def _check(self, response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise TriggerError(f"CREAO API: HTTP {response.status_code} {response.text[:300]}")
        return response.json()

    def start(
        self,
        inputs: dict[str, Any] | None = None,
        webhook_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"appId": self.agent_id, "inputs": inputs or {}}
        if webhook_url:
            body["webhookUrl"] = webhook_url
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        return self._check(self.client.post(f"{self.base_url}/api/v1/runs", json=body, headers=self.headers))

    def status(self, run_id: str) -> dict:
        return self._check(self.client.get(f"{self.base_url}/api/v1/runs/{run_id}", headers=self.headers))

    def wait(
        self,
        run_id: str,
        poll_seconds: float = POLL_SECONDS,
        wait_seconds: float = WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict:
        waited = 0.0
        while True:
            run = self.status(run_id)
            if run.get("status") in FINISHED:
                return run
            if waited >= wait_seconds:
                raise TriggerError(f"run {run_id} still {run.get('status')} after {wait_seconds:.0f} s")
            sleep(poll_seconds)
            waited += poll_seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inputs", default="{}", help="the agent's input form values as JSON")
    parser.add_argument("--webhook-url", help="public https URL CREAO calls when the run finishes")
    parser.add_argument("--idempotency-key", help="8 to 128 characters; resending it returns the same run")
    parser.add_argument("--wait", action="store_true", help="poll until the run finishes")
    arguments = parser.parse_args(argv)
    try:
        with httpx.Client(timeout=60.0) as client:
            trigger = CreaoTrigger(
                client, os.environ.get("CREAO_API_KEY", ""), os.environ.get("CREAO_AGENT_ID", "")
            )
            run = trigger.start(
                json.loads(arguments.inputs), arguments.webhook_url, arguments.idempotency_key
            )
            print(json.dumps(run, indent=2))
            if arguments.wait:
                run = trigger.wait(run["id"])
                print(json.dumps(run, indent=2))
    except (TriggerError, httpx.HTTPError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0 if run.get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
