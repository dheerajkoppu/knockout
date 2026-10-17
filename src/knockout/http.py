"""One HTTP client with retries and an on-disk JSON cache keyed by URL."""

import hashlib
import json
import time
from typing import Any

import httpx

from knockout.config import CACHE_DIR

RETRY_STATUSES = {429, 500, 502, 503, 504}

_client = httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": "knockout/0.1"})


class SourceError(RuntimeError):
    """An upstream source failed after retries."""


def _cache_path(url: str):
    return CACHE_DIR / "http" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def get_json(url: str, *, cache_key: str | None = None, not_found_ok: bool = False) -> Any:
    """GET a JSON document. A 404 returns None when `not_found_ok`, so "no records" is cached too."""
    path = _cache_path(cache_key or url)
    if path.exists():
        return json.loads(path.read_text())["body"]
    for attempt in range(4):
        try:
            response = _client.get(url)
        except httpx.HTTPError as error:
            if attempt == 3:
                raise SourceError(f"{url}: {error}") from error
            time.sleep(2**attempt)
            continue
        if response.status_code in RETRY_STATUSES and attempt < 3:
            time.sleep(2**attempt * (5 if response.status_code == 429 else 1))
            continue
        if response.status_code == 404 and not_found_ok:
            body = None
            break
        if response.status_code >= 400:
            raise SourceError(f"{url}: HTTP {response.status_code} {response.text[:200]}")
        body = response.json()
        break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": cache_key or url, "retrieved_at": time.time(), "body": body}))
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
