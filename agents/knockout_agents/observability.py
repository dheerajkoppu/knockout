"""Sentry tracing and logs for the agents, with AI agent monitoring spans. Nothing happens unless SENTRY_DSN is set."""

import logging
import os
import re

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

SECRET_PARAMETER = re.compile(r"((?:api_key|key|token)=)[^&\s\"']+", re.IGNORECASE)


def _scrub(value):
    if isinstance(value, str):
        return SECRET_PARAMETER.sub(r"\1[Filtered]", value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def setup() -> bool:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn or sentry_sdk.is_initialized():
        return bool(dsn)
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT") or "development",
        release=os.environ.get("SENTRY_RELEASE") or "knockout-agents@0.1.0",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "1.0"),
        enable_logs=True,
        send_default_pii=False,
        integrations=[LoggingIntegration(sentry_logs_level=logging.INFO)],
        before_send=lambda event, hint: _scrub(event),
        before_send_transaction=lambda event, hint: _scrub(event),
        before_send_log=lambda log, hint: _scrub(log),
    )
    return True


def chat_transaction(drug: str | None):
    transaction = sentry_sdk.start_transaction(op="gen_ai.invoke_agent", name="invoke_agent knockout-orchestrator")
    transaction.set_data("gen_ai.agent.name", "knockout-orchestrator")
    transaction.set_data("gen_ai.operation.name", "invoke_agent")
    if drug:
        transaction.set_data("knockout.drug", drug)
    return transaction


def specialist_span(agent_name: str, drug: str):
    span = sentry_sdk.start_span(op="gen_ai.invoke_agent", name=f"invoke_agent {agent_name}")
    span.set_data("gen_ai.agent.name", agent_name)
    span.set_data("gen_ai.operation.name", "invoke_agent")
    span.set_data("knockout.drug", drug)
    return span
