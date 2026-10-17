"""Optional ASI:One LLM fallback for requests the rules cannot read. It only extracts names; ChEMBL confirms them.

Used only when ASI1_API_KEY is set. The model never decides a prediction, a direction or a verdict.
"""

import json
import os
import re

import httpx

SYSTEM_PROMPT = (
    "Extract from the user's message the drug name and the protein or gene the drug acts on, if either is "
    "named or clearly implied, and the side effect they ask about. Answer with one JSON object and nothing else: "
    '{"drug": string or null, "protein": string or null, "effect": string or null}. Use generic drug names. '
    "Do not guess a drug that is not implied."
)


async def extract(text: str) -> dict | None:
    key = os.environ.get("ASI1_API_KEY") or ""
    if not key:
        return None
    url = (os.environ.get("ASI1_API_URL") or "https://api.asi1.ai/v1").rstrip("/") + "/chat/completions"
    body = {
        "model": os.environ.get("ASI1_MODEL") or "asi1",
        "temperature": 0,
        "max_tokens": 200,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=body, headers={"Authorization": f"Bearer {key}"})
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        field_name: (str(parsed[field_name]).strip().lower() or None) if parsed.get(field_name) else None
        for field_name in ("drug", "protein", "effect")
    }
