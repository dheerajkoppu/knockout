"""Knockout watch: the script the CREAO agent runs in its sandbox on every scheduled run.

For each drug on the Knockout watchlist it reads the drug's report and, for every predicted
reaction term and each recent quarter, counts the FAERS reports received in that quarter and
computes the PRR and the Evans criteria on all reports received up to the quarter's end, with the
same formula as src/knockout/signals.py. It then posts the run to the Knockout API webhook.

Environment: KNOCKOUT_API_URL, KNOCKOUT_WEBHOOK_SECRET, OPENFDA_API_KEY (optional).
Needs only httpx (pip install httpx).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

import httpx

OPENFDA_EVENT_URL = "https://api.fda.gov/drug/event.json"
WATCHLIST_PATH = "/api/watchlist"
REPORT_PATH = "/api/drugs/{name}/report"
WEBHOOK_PATH = "/api/webhooks/creao/signals"
SECRET_HEADER = "X-Knockout-Webhook-Secret"

MIN_REPORTS = 3
MIN_PRR = 2.0
MIN_CHI_SQUARED = 4.0

DEFAULT_QUARTERS = 8
RETRY_STATUSES = {429, 500, 502, 503, 504}
# openFDA allows about 40 requests a minute without a key and 240 with one.
PAUSE_WITHOUT_KEY = 1.6
PAUSE_WITH_KEY = 0.3
REPORT_TIMEOUT = 600.0
CUMULATIVE_FROM = "19000101"


class WatchError(RuntimeError):
    """A source or the Knockout API failed after retries."""


@dataclass(frozen=True)
class QuarterCounts:
    """One reaction term at one quarter's end.

    `reports` were received during the quarter (the trend). `a`, `drug`, `reaction` and `all` are the
    2×2 table of every report received up to the quarter's end, which the PRR and the signal use, so
    the latest quarter matches the all-time PRR on the report page.
    """

    term: str
    quarter: str
    reports: int
    a: int
    drug: int
    reaction: int
    all: int

    @property
    def expected(self) -> float:
        return self.drug * self.reaction / self.all if self.all else 0.0

    @property
    def prr(self) -> float | None:
        background = self.reaction - self.a
        rest = self.all - self.drug
        if self.drug == 0 or rest <= 0:
            return None
        if background <= 0:
            return float("inf") if self.a else None
        return (self.a / self.drug) / (background / rest)

    @property
    def chi_squared(self) -> float:
        """Pearson chi-squared with Yates correction, 1 degree of freedom."""
        a, b = self.a, self.drug - self.a
        c, d = self.reaction - self.a, self.all - self.drug - (self.reaction - self.a)
        n = a + b + c + d
        denominator = (a + b) * (c + d) * (a + c) * (b + d)
        if denominator == 0:
            return 0.0
        difference = max(abs(a * d - b * c) - n / 2, 0.0)
        return n * difference**2 / denominator

    @property
    def is_signal(self) -> bool:
        prr = self.prr
        return (
            self.a >= MIN_REPORTS
            and prr is not None
            and prr >= MIN_PRR
            and self.chi_squared >= MIN_CHI_SQUARED
        )

    def to_payload(self) -> dict[str, Any]:
        prr = self.prr
        return {
            "term": self.term,
            "quarter": self.quarter,
            "reports": self.reports,
            "prr": prr if prr is not None and math.isfinite(prr) else None,
            "prr_infinite": prr == math.inf,
            "signal": self.is_signal,
        }

    def to_summary(self) -> dict[str, Any]:
        return self.to_payload() | {
            "a": self.a,
            "drug_reports": self.drug,
            "reaction_reports": self.reaction,
            "all_reports": self.all,
            "chi_squared": round(self.chi_squared, 2),
        }


@dataclass(frozen=True)
class Quarter:
    year: int
    number: int

    @property
    def label(self) -> str:
        return f"{self.year}Q{self.number}"

    @property
    def start(self) -> date:
        return date(self.year, 3 * self.number - 2, 1)

    @property
    def end(self) -> date:
        last_month = 3 * self.number
        last_day = 31 if last_month in (3, 12) else 30
        return date(self.year, last_month, last_day)

    def previous(self) -> Quarter:
        return Quarter(self.year - 1, 4) if self.number == 1 else Quarter(self.year, self.number - 1)


def recent_quarters(last_updated: date, count: int) -> list[Quarter]:
    """The `count` most recent complete quarters ending on or before openFDA's last update, oldest first."""
    quarter = Quarter(last_updated.year, (last_updated.month - 1) // 3 + 1)
    if quarter.end > last_updated:
        quarter = quarter.previous()
    quarters = []
    for _ in range(count):
        quarters.append(quarter)
        quarter = quarter.previous()
    return list(reversed(quarters))


def received_through(day: date) -> str:
    return f"receivedate:[{CUMULATIVE_FROM} TO {day:%Y%m%d}]"


def drug_search(generic_name: str) -> str:
    return f'patient.drug.openfda.generic_name:"{generic_name.lower()}"'


def reaction_search(term: str) -> str:
    return f'patient.reaction.reactionmeddrapt.exact:"{term.upper()}"'


def encode_search(search: str) -> str:
    """The same encoding as src/knockout/openfda.py, so a query here matches the engine's."""
    return quote(search.replace(" ", "+"), safe="+:._()*")


def _backoff(attempt: int, status: int | None) -> float:
    return 2**attempt * (5 if status == 429 else 1)


class OpenFDA:
    """openFDA FAERS search totals, paced to the rate limit and memoised for the run."""

    def __init__(
        self,
        client: httpx.Client,
        api_key: str | None = None,
        pause: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.api_key = api_key or None
        self.pause = pause if pause is not None else (PAUSE_WITH_KEY if self.api_key else PAUSE_WITHOUT_KEY)
        self.sleep = sleep
        self.requests = 0
        self._totals: dict[str, int] = {}

    def public_url(self, search: str | None) -> str:
        query = f"search={encode_search(search)}&" if search else ""
        return f"{OPENFDA_EVENT_URL}?{query}limit=1"

    def _get(self, search: str | None) -> dict | None:
        public = self.public_url(search)
        url = f"{public}&api_key={self.api_key}" if self.api_key else public
        for attempt in range(5):
            if self.requests:
                self.sleep(self.pause)
            self.requests += 1
            try:
                response = self.client.get(url)
            except httpx.HTTPError as error:
                if attempt == 4:
                    raise WatchError(f"openFDA {public}: {type(error).__name__}") from None
                self.sleep(_backoff(attempt, None))
                continue
            if response.status_code in RETRY_STATUSES and attempt < 4:
                self.sleep(_backoff(attempt, response.status_code))
                continue
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                raise WatchError(f"openFDA {public}: HTTP {response.status_code} {response.text[:200]}")
            return response.json()
        raise WatchError(f"openFDA {public}: retries exhausted")

    def total(self, search: str | None) -> int:
        """Reports matching a search. openFDA answers 404 when nothing matches, which is 0."""
        key = search or ""
        if key not in self._totals:
            body = self._get(search)
            self._totals[key] = int(body["meta"]["results"]["total"]) if body else 0
        return self._totals[key]

    def last_updated(self) -> date:
        body = self._get(None)
        if not body:
            raise WatchError("openFDA returned no metadata")
        self._totals[""] = int(body["meta"]["results"]["total"])
        return date.fromisoformat(body["meta"]["last_updated"])


def api_base(url: str) -> str:
    """KNOCKOUT_API_URL with or without a trailing /api."""
    base = url.strip().rstrip("/")
    return base.removesuffix("/api")


class KnockoutAPI:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        secret: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.base_url = api_base(base_url)
        self.secret = secret
        self.sleep = sleep

    def _request(self, method: str, path: str, **options: Any) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(4):
            try:
                response = self.client.request(method, url, **options)
            except httpx.HTTPError as error:
                if attempt == 3:
                    raise WatchError(f"Knockout API {method} {path}: {type(error).__name__}") from None
                self.sleep(_backoff(attempt, None))
                continue
            if response.status_code in RETRY_STATUSES and attempt < 3:
                self.sleep(_backoff(attempt, response.status_code))
                continue
            if response.status_code >= 400:
                raise WatchError(
                    f"Knockout API {method} {path}: HTTP {response.status_code} {response.text[:300]}"
                )
            return response.json()
        raise WatchError(f"Knockout API {method} {path}: retries exhausted")

    def watchlist(self) -> list[str]:
        return list(self._request("GET", WATCHLIST_PATH).get("drugs", []))

    def report(self, drug: str) -> dict:
        path = REPORT_PATH.format(name=quote(drug, safe=""))
        return self._request("GET", path, timeout=REPORT_TIMEOUT)

    def post_signals(self, payload: dict) -> dict:
        if not self.secret:
            raise WatchError("KNOCKOUT_WEBHOOK_SECRET is not set")
        return self._request("POST", WEBHOOK_PATH, json=payload, headers={SECRET_HEADER: self.secret})


def reaction_terms(report: dict) -> list[str]:
    """Every reaction term of every prediction in the report, once each, in report order."""
    terms: list[str] = []
    for prediction in report.get("predictions") or []:
        for term in prediction.get("reaction_terms") or []:
            term = term.strip()
            if term and term.upper() not in {existing.upper() for existing in terms}:
                terms.append(term)
    return terms


def generic_name(report: dict | None, fallback: str) -> str:
    molecule = (report or {}).get("molecule") or {}
    return (molecule.get("name") or fallback).lower()


def _tables(
    openfda: OpenFDA, drug: str, terms: list[str], day: date
) -> tuple[int, int, dict[str, tuple[int, int]]]:
    """All reports, drug reports, and per term (drug and term, term) received up to `day`."""
    window = received_through(day)
    all_reports = openfda.total(window)
    drug_reports = openfda.total(f"{drug} AND {window}")
    per_term = {}
    for term in terms:
        reaction = reaction_search(term)
        reaction_reports = openfda.total(f"{reaction} AND {window}")
        both = openfda.total(f"{drug} AND {reaction} AND {window}") if drug_reports else 0
        per_term[term] = (both, reaction_reports)
    return all_reports, drug_reports, per_term


def count_quarters(
    openfda: OpenFDA, generic: str, terms: list[str], quarters: list[Quarter]
) -> list[QuarterCounts]:
    """Receivedate ranges are disjoint, so a quarter's reports are the difference of two cumulative totals."""
    drug = drug_search(generic)
    previous = _tables(openfda, drug, terms, quarters[0].previous().end)
    rows = []
    for quarter in quarters:
        current = _tables(openfda, drug, terms, quarter.end)
        all_reports, drug_reports, per_term = current
        if all_reports > previous[0]:
            for term in terms:
                both, reaction_reports = per_term[term]
                reports = both - previous[2][term][0]
                rows.append(
                    QuarterCounts(
                        term, quarter.label, reports, both, drug_reports, reaction_reports, all_reports
                    )
                )
        previous = current
    return rows


def build_payload(
    drug: str, run_id: str, run_at: str, rows: list[QuarterCounts], term_source: str = "report"
) -> dict:
    return {
        "drug": drug,
        "run_id": run_id,
        "run_at": run_at,
        "term_source": term_source,
        "terms": [row.to_payload() for row in rows],
    }


def new_run_id(now: datetime, manual: bool = False) -> str:
    """`manual-` when a person chose the terms with --term, so no one mistakes it for a scheduled run."""
    prefix = "manual" if manual else "creao"
    return f"{prefix}-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run(
    *,
    openfda: OpenFDA,
    api: KnockoutAPI | None,
    drugs: list[str] | None = None,
    terms: list[str] | None = None,
    quarter_count: int = DEFAULT_QUARTERS,
    dry_run: bool = False,
    run_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    """One watch run. Returns a summary; each drug's outcome is recorded even when another fails."""
    now = now or datetime.now(timezone.utc)
    run_at = now.isoformat(timespec="seconds")
    run_id = run_id or new_run_id(now, manual=bool(terms))
    if quarter_count < 1:
        raise WatchError("--quarters must be at least 1")
    if terms and not drugs:
        raise WatchError("--term needs --drug")
    if api is None and not (drugs and terms):
        raise WatchError("KNOCKOUT_API_URL is not set; it is needed unless both --drug and --term are given")

    last_updated = openfda.last_updated()
    quarters = recent_quarters(last_updated, quarter_count)
    summary: dict[str, Any] = {
        "run_id": run_id,
        "run_at": run_at,
        "dry_run": dry_run,
        "openfda_last_updated": last_updated.isoformat(),
        "openfda_key": bool(openfda.api_key),
        "quarters": [quarter.label for quarter in quarters],
        "term_source": "manual" if terms else "report",
        "drugs": [],
    }
    watched = drugs if drugs else api.watchlist()
    log(f"run {run_id}: {len(watched)} drug(s), quarters {quarters[0].label} to {quarters[-1].label}")

    for drug in watched:
        outcome: dict[str, Any] = {"drug": drug}
        summary["drugs"].append(outcome)
        try:
            report = None if terms else api.report(drug)
            drug_terms = list(terms) if terms else reaction_terms(report)
            outcome["generic_name"] = generic_name(report, drug)
            outcome["terms"] = drug_terms
            if not drug_terms:
                outcome["status"] = "skipped"
                outcome["reason"] = (
                    "the report has no reaction terms yet (protocol step 5 has not mapped its phenotypes)"
                )
                log(f"{drug}: skipped, no reaction terms")
                continue
            log(f"{drug}: {len(drug_terms)} term(s) as {outcome['generic_name']!r}")
            rows = count_quarters(openfda, outcome["generic_name"], drug_terms, quarters)
            payload = build_payload(outcome["generic_name"], run_id, run_at, rows, "manual" if terms else "report")
            latest = quarters[-1].label
            outcome["latest_quarter"] = latest
            outcome["rows"] = [row.to_summary() for row in rows]
            outcome["signals_in_latest_quarter"] = [
                row.to_summary() for row in rows if row.quarter == latest and row.is_signal
            ]
            if dry_run:
                outcome["status"] = "dry_run"
                outcome["payload"] = payload
                continue
            response = api.post_signals(payload)
            outcome["status"] = "posted"
            outcome["stored"] = response.get("stored")
            outcome["alerts"] = response.get("alerts")
            log(f"{drug}: posted {len(rows)} row(s), stored {outcome['stored']}, alerts {outcome['alerts']}")
        except (WatchError, httpx.HTTPError, KeyError, ValueError) as error:
            outcome["status"] = "failed"
            outcome["reason"] = str(error)
            log(f"{drug}: failed, {error}")
    summary["openfda_requests"] = openfda.requests
    return summary


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the webhook payloads instead of posting them"
    )
    parser.add_argument(
        "--drug", action="append", help="watch this drug instead of the watchlist (repeatable)"
    )
    parser.add_argument(
        "--term", action="append", help="use this reaction term instead of the report's (repeatable)"
    )
    parser.add_argument(
        "--quarters", type=int, default=int(os.environ.get("WATCH_QUARTERS") or DEFAULT_QUARTERS)
    )
    parser.add_argument("--run-id", default=os.environ.get("CREAO_RUN_ID") or None)
    parser.add_argument("--summary", help="also write the run summary as JSON to this path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    api_url = os.environ.get("KNOCKOUT_API_URL") or None
    secret = os.environ.get("KNOCKOUT_WEBHOOK_SECRET") or None
    if not arguments.dry_run and not secret:
        log("KNOCKOUT_WEBHOOK_SECRET is not set; add it in CREAO Secrets, or use --dry-run")
        return 2
    with httpx.Client(
        timeout=60.0, follow_redirects=True, headers={"User-Agent": "knockout-watch/0.1"}
    ) as client:
        openfda = OpenFDA(client, os.environ.get("OPENFDA_API_KEY"))
        api = KnockoutAPI(client, api_url, secret) if api_url else None
        try:
            summary = run(
                openfda=openfda,
                api=api,
                drugs=arguments.drug,
                terms=arguments.term,
                quarter_count=arguments.quarters,
                dry_run=arguments.dry_run,
                run_id=arguments.run_id,
            )
        except WatchError as error:
            log(str(error))
            return 2
    text = json.dumps(summary, indent=2)
    print(text)
    if arguments.summary:
        with open(arguments.summary, "w") as handle:
            handle.write(text + "\n")
    return 1 if any(outcome["status"] == "failed" for outcome in summary["drugs"]) else 0


if __name__ == "__main__":
    sys.exit(main())
