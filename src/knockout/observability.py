"""Sentry tracing, logs and AI agent monitoring. Nothing happens unless SENTRY_DSN is set."""

import functools
import json
import logging
import os
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import sentry_sdk
from sentry_sdk.consts import OP, SPANDATA
from sentry_sdk.integrations.logging import LoggingIntegration

GEN_AI_SYSTEM = "gcp.gemini"
MAPPER_AGENT = "knockout-phenotype-mapper"
MAX_TEXT = 20_000
SECRET_PARAMETER = re.compile(r"((?:api_key|key)=)[^&\s\"']+", re.IGNORECASE)
SOURCE_MODULES = ("chembl", "openfda")


def scrub(value: Any) -> Any:
    """Remove API keys carried in query strings (openFDA api_key, Gemini key) before anything leaves."""
    if isinstance(value, str):
        return SECRET_PARAMETER.sub(r"\1[Filtered]", value)
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item) for item in value)
    return value


def _scrub_event(event: dict, hint: dict) -> dict:
    return scrub(event)


def _scrub_log(log: dict, hint: dict) -> dict:
    return scrub(log)


def _release() -> str:
    try:
        return f"knockout@{version('knockout')}"
    except PackageNotFoundError:
        return "knockout@unknown"


def log_to_console() -> None:
    """Engine runs and webhook deliveries show in the server console, with or without Sentry."""
    package_logger = logging.getLogger("knockout")
    if not package_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        package_logger.addHandler(handler)
    package_logger.setLevel(logging.INFO)


def setup() -> bool:
    """Initialise Sentry when SENTRY_DSN is set, and trace Gemini and the data sources. Returns whether it is on."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    if not sentry_sdk.is_initialized():
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT") or "development",
            release=os.environ.get("SENTRY_RELEASE") or _release(),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "1.0"),
            enable_logs=True,
            send_default_pii=False,
            integrations=[LoggingIntegration(sentry_logs_level=logging.INFO)],
            before_send=_scrub_event,
            before_send_transaction=_scrub_event,
            before_send_log=_scrub_log,
        )
    instrument_gemini()
    instrument_sources()
    return True


def _start(operation: str, name: str):
    """A child span inside a running transaction, or a new transaction when there is none (the CLI)."""
    current = sentry_sdk.get_current_span()
    if current is None or current.containing_transaction is None:
        return sentry_sdk.start_transaction(op=operation, name=name)
    return sentry_sdk.start_span(op=operation, name=name)


def _model_name() -> str:
    from knockout import gemini
    from knockout.http import SourceError

    try:
        return gemini.model()
    except (gemini.GeminiUnavailable, SourceError):
        return "unknown"


def traced_generate_json(generate_json):
    """Wrap knockout.gemini.generate_json in a gen_ai.chat span (OpenTelemetry gen_ai conventions)."""

    @functools.wraps(generate_json)
    def traced(prompt: str, schema: dict[str, Any]) -> Any:
        model_name = _model_name()
        with _start(OP.GEN_AI_CHAT, f"chat {model_name}") as span:
            span.set_data(SPANDATA.GEN_AI_OPERATION_NAME, "chat")
            span.set_data(SPANDATA.GEN_AI_SYSTEM, GEN_AI_SYSTEM)
            span.set_data(SPANDATA.GEN_AI_PROVIDER_NAME, GEN_AI_SYSTEM)
            span.set_data(SPANDATA.GEN_AI_AGENT_NAME, MAPPER_AGENT)
            span.set_data(SPANDATA.GEN_AI_REQUEST_MODEL, model_name)
            span.set_data(SPANDATA.GEN_AI_REQUEST_TEMPERATURE, 0)
            # The prompt holds only HPO ids and labels, never a drug or a person.
            span.set_data(
                SPANDATA.GEN_AI_REQUEST_MESSAGES,
                json.dumps([{"role": "user", "content": prompt[:MAX_TEXT]}]),
            )
            answer = generate_json(prompt, schema)
            span.set_data(SPANDATA.GEN_AI_RESPONSE_TEXT, json.dumps([json.dumps(answer)[:MAX_TEXT]]))
            return answer

    traced._knockout_traced = True
    return traced


def recording_usage(post_json):
    """Copy Gemini's usage and model version onto the open gen_ai.chat span."""

    @functools.wraps(post_json)
    def recorded(url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        body = post_json(url, payload, headers)
        span = sentry_sdk.get_current_span()
        if span is not None and span.op == OP.GEN_AI_CHAT and isinstance(body, dict):
            usage = body.get("usageMetadata") or {}
            for attribute, field in (
                (SPANDATA.GEN_AI_USAGE_INPUT_TOKENS, "promptTokenCount"),
                (SPANDATA.GEN_AI_USAGE_OUTPUT_TOKENS, "candidatesTokenCount"),
                (SPANDATA.GEN_AI_USAGE_TOTAL_TOKENS, "totalTokenCount"),
            ):
                if field in usage:
                    span.set_data(attribute, usage[field])
            if body.get("modelVersion"):
                span.set_data(SPANDATA.GEN_AI_RESPONSE_MODEL, body["modelVersion"])
            finish_reasons = [candidate.get("finishReason") for candidate in body.get("candidates", [])]
            if any(finish_reasons):
                span.set_data(SPANDATA.GEN_AI_RESPONSE_FINISH_REASONS, json.dumps(finish_reasons))
        return body

    recorded._knockout_traced = True
    return recorded


def traced_mapping(ensure):
    """Wrap knockout.mapping.ensure, the Gemini-driven phenotype mapper, in a gen_ai.invoke_agent span."""

    @functools.wraps(ensure)
    def traced(terms: dict[str, str]):
        with _start(OP.GEN_AI_INVOKE_AGENT, f"invoke_agent {MAPPER_AGENT}") as span:
            span.set_data(SPANDATA.GEN_AI_OPERATION_NAME, "invoke_agent")
            span.set_data(SPANDATA.GEN_AI_AGENT_NAME, MAPPER_AGENT)
            span.set_data(SPANDATA.GEN_AI_SYSTEM, GEN_AI_SYSTEM)
            span.set_data("knockout.terms_requested", len(terms))
            mappings = ensure(terms)
            span.set_data("knockout.terms_mapped", len(mappings))
            return mappings

    traced._knockout_traced = True
    return traced


def instrument_gemini() -> None:
    """Patch knockout.gemini and knockout.mapping at runtime; their source files stay untouched."""
    from knockout import gemini, mapping

    if not getattr(gemini.generate_json, "_knockout_traced", False):
        gemini.generate_json = traced_generate_json(gemini.generate_json)
    if not getattr(gemini.post_json, "_knockout_traced", False):
        gemini.post_json = recording_usage(gemini.post_json)
    if not getattr(mapping.ensure, "_knockout_traced", False):
        mapping.ensure = traced_mapping(mapping.ensure)


def traced_source(source: str, get_json):
    """One span per ChEMBL or openFDA lookup, marking whether the on-disk cache answered it."""
    from knockout import http

    @functools.wraps(get_json)
    def traced(url: str, *, cache_key: str | None = None, not_found_ok: bool = False) -> Any:
        public_url = scrub(cache_key or url)
        hit = http.is_cached(cache_key or url)
        with sentry_sdk.start_span(op=f"source.{source}", name=public_url) as span:
            span.set_data("cache.hit", hit)
            span.set_data("knockout.source", source)
            return get_json(url, cache_key=cache_key, not_found_ok=not_found_ok)

    traced._knockout_traced = True
    return traced


def instrument_sources() -> None:
    import importlib

    for name in SOURCE_MODULES:
        module = importlib.import_module(f"knockout.{name}")
        if not getattr(module.get_json, "_knockout_traced", False):
            module.get_json = traced_source(name, module.get_json)
