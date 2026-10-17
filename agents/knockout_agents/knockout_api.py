"""Async client for the Knockout API. Every failure becomes ApiError with a reason a person can read."""

from urllib.parse import quote

import httpx

from knockout_agents import settings


class ApiError(RuntimeError):
    """The Knockout API could not answer."""


async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{settings.api_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.api_timeout_seconds()) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException as error:
        raise ApiError(f"the Knockout API at {settings.api_url()} timed out ({error.__class__.__name__})") from error
    except httpx.HTTPError as error:
        raise ApiError(f"the Knockout API at {settings.api_url()} is unreachable ({error})") from error
    if response.status_code == 404:
        detail = _detail(response)
        raise ApiError(f"the Knockout API has no record for this request{': ' + detail if detail else ''}")
    if response.status_code >= 400:
        detail = _detail(response) or response.text[:200]
        raise ApiError(f"the Knockout API returned HTTP {response.status_code}: {detail}")
    try:
        return response.json()
    except ValueError as error:
        raise ApiError("the Knockout API returned something that is not JSON") from error


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail if isinstance(detail, str) else ""


async def health() -> dict:
    return await _get("/api/health")


async def report(drug: str, *, refresh: bool = False) -> dict:
    return await _get(f"/api/drugs/{quote(drug.lower())}/report", {"refresh": "true"} if refresh else None)


async def trend(drug: str) -> dict:
    return await _get(f"/api/drugs/{quote(drug.lower())}/trend")


async def alerts(drug: str) -> dict:
    return await _get(f"/api/drugs/{quote(drug.lower())}/alerts")
