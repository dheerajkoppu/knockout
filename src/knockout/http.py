"""One HTTP client with retries and an on-disk JSON cache keyed by URL."""

import contextlib
import contextvars
import hashlib
import json
import os
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from knockout.config import CACHE_DIR

RETRY_STATUSES = {429, 500, 502, 503, 504}
SECRET_PARAMETER = re.compile(r"((?:api_key|key)=)[^&\s\"']+", re.IGNORECASE)
# openFDA labels and report totals change; ChEMBL releases are fixed, so only openFDA entries expire.
EXPIRING_PREFIXES = ("https://api.fda.gov/",)

_client = httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": "knockout/0.1"})
_refresh_started = contextvars.ContextVar("knockout_http_refresh_started", default=0.0)


def scrub(text: str) -> str:
    return SECRET_PARAMETER.sub(r"\1[Filtered]", text)


class SourceError(RuntimeError):
    """An upstream source failed after retries. The message never carries an API key."""

    def __init__(self, message: str) -> None:
        super().__init__(scrub(message))


def _cache_path(url: str):
    return CACHE_DIR / "http" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def max_age_seconds() -> float:
    return float(os.environ.get("OPENFDA_CACHE_HOURS") or "24") * 3600


def _expires(key: str) -> bool:
    return key.startswith(EXPIRING_PREFIXES)


@contextlib.contextmanager
def refreshing() -> Iterator[None]:
    """Inside this block, expiring (openFDA) responses are fetched again even when cached."""
    token = _refresh_started.set(time.time())
    try:
        yield
    finally:
        _refresh_started.reset(token)


def _fresh_entry(key: str) -> dict | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    entry = json.loads(path.read_text())
    if _expires(key):
        fetched = entry.get("retrieved_at", 0)
        if fetched < _refresh_started.get() or time.time() - fetched > max_age_seconds():
            return None
    return entry


def is_cached(key: str) -> bool:
    return _fresh_entry(key) is not None


def retrieved_at(key: str) -> str | None:
    """When the cached response for this key was fetched, as an ISO time."""
    path = _cache_path(key)
    if not path.exists():
        return None
    stamp = json.loads(path.read_text()).get("retrieved_at")
    return datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds") if stamp else None


def get_json(url: str, *, cache_key: str | None = None, not_found_ok: bool = False) -> Any:
    """GET a JSON document. A 404 returns None when `not_found_ok`, so "no records" is cached too.

    `cache_key` is the public URL (without any key); every error message is built from it.
    """
    key = cache_key or url
    public = scrub(key)
    entry = _fresh_entry(key)
    if entry is not None:
        return entry["body"]
    for attempt in range(4):
        try:
            response = _client.get(url)
        except httpx.HTTPError as error:
            if attempt == 3:
                raise SourceError(f"{public}: {type(error).__name__}") from None
            time.sleep(2**attempt)
            continue
        if response.status_code in RETRY_STATUSES and attempt < 3:
            time.sleep(2**attempt * (5 if response.status_code == 429 else 1))
            continue
        if response.status_code == 404 and not_found_ok:
            body = None
            break
        if response.status_code >= 400:
            raise SourceError(f"{public}: HTTP {response.status_code} {response.text[:200]}")
        body = response.json()
        break
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": public, "retrieved_at": time.time(), "body": body}))
    return body


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
    for attempt in range(4):
        response = _client.post(url, json=payload, headers=headers)
        if response.status_code in RETRY_STATUSES and attempt < 3:
            time.sleep(2**attempt * 2)
            continue
        if response.status_code >= 400:
            raise SourceError(f"{url}: HTTP {response.status_code} {response.text[:300]}")
        return response.json()
    raise SourceError(f"{url}: retries exhausted")


def download(url: str, destination) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _client.stream("GET", url) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
