"""Gemini through the REST API, with JSON output at temperature 0."""

import json
import re
from functools import lru_cache
from typing import Any

from knockout.config import gemini_api_key, gemini_model
from knockout.http import get_json, post_json

API = "https://generativelanguage.googleapis.com/v1beta"
EXCLUDED_VARIANTS = ("lite", "image", "tts", "live", "audio", "embedding", "thinking", "exp")


class GeminiUnavailable(RuntimeError):
    """No key, or no usable model."""


def _key() -> str:
    key = gemini_api_key()
    if not key:
        raise GeminiUnavailable("GEMINI_API_KEY is not set in .env")
    return key


def _version(name: str) -> tuple[float, int]:
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    stable = 0 if "preview" in name else 1
    return (float(match.group(1)) if match else 0.0, stable)


@lru_cache(maxsize=1)
def model() -> str:
    """The configured model, or the newest stable flash model this key can call."""
    configured = gemini_model()
    if configured:
        return configured
    body = get_json(f"{API}/models?pageSize=1000&key={_key()}", cache_key=f"{API}/models")
    names = [
        row["name"].removeprefix("models/")
        for row in body.get("models", [])
        if "generateContent" in row.get("supportedGenerationMethods", [])
        and "flash" in row["name"]
        and not any(variant in row["name"] for variant in EXCLUDED_VARIANTS)
    ]
    if not names:
        raise GeminiUnavailable("No Gemini flash model is available for this key")
    return max(names, key=_version)


def generate_json(prompt: str, schema: dict[str, Any]) -> Any:
    body = post_json(
        f"{API}/models/{model()}:generateContent",
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        },
        headers={"x-goog-api-key": _key()},
    )
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)
