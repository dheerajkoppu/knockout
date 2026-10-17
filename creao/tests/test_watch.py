"""Tests for creao/watch.py. openFDA and the Knockout API are mocked with FIXTURE data, never real results,
except the one test marked `live`, which reads openFDA."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote_plus

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knockout import openfda as engine_openfda
from knockout.signals import TermCounts

import watch

SECRET = "fixture-webhook-secret"
API_URL = "https://knockout.fixture.test"
NOW = datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc)
LAST_UPDATED = "2026-07-30"

FIXTURE_DRUG = "fixturemab"
FIXTURE_TERM = "FIXTURE REACTION"
OTHER_TERM = "OTHER FIXTURE REACTION"

# FIXTURE reports: (receivedate, generic name or None, reaction or None, number of such reports).
FIXTURE_REPORTS = [
    (date(2023, 5, 1), None, None, 900_000),
    (date(2023, 5, 1), FIXTURE_DRUG, None, 2_000),
    (date(2023, 5, 1), FIXTURE_DRUG, FIXTURE_TERM, 2),
    (date(2023, 5, 1), None, FIXTURE_TERM, 40),
    (date(2024, 8, 15), None, None, 300_000),
    (date(2024, 8, 15), FIXTURE_DRUG, None, 500),
    (date(2024, 8, 15), FIXTURE_DRUG, FIXTURE_TERM, 1),
    (date(2025, 2, 10), None, None, 310_000),
    (date(2025, 2, 10), FIXTURE_DRUG, None, 480),
    (date(2025, 2, 10), FIXTURE_DRUG, FIXTURE_TERM, 4),
    (date(2025, 2, 10), None, OTHER_TERM, 70),
    (date(2025, 6, 30), FIXTURE_DRUG, OTHER_TERM, 1),
    (date(2026, 4, 1), None, None, 320_000),
    (date(2026, 4, 1), FIXTURE_DRUG, FIXTURE_TERM, 3),
    # Received after openFDA's last update: must never be counted in a quarter.
    (date(2026, 8, 20), FIXTURE_DRUG, FIXTURE_TERM, 50),
] + [
    (date(year, month, 15), None, None, 100_000)
    for year in (2023, 2024, 2025, 2026)
    for month in (2, 5, 8, 11)
]


def matches(clause: str, record) -> bool:
    received, generic, reaction, _ = record
    if found := re.fullmatch(r'patient\.drug\.openfda\.generic_name:"(.+)"', clause):
        return generic == found.group(1)
    if found := re.fullmatch(r'patient\.reaction\.reactionmeddrapt\.exact:"(.+)"', clause):
        return reaction == found.group(1)
    if found := re.fullmatch(r"receivedate:\[(\d{8}) TO (\d{8})\]", clause):
        start, end = (datetime.strptime(value, "%Y%m%d").date() for value in found.groups())
        return start <= received <= end
    raise AssertionError(f"unexpected search clause {clause!r}")


def fixture_total(search: str | None) -> int:
    clauses = search.split(" AND ") if search else []
    return sum(record[3] for record in FIXTURE_REPORTS if all(matches(clause, record) for clause in clauses))


class FakeOpenFDA:
    def __init__(self, failures: list[int] | None = None):
        self.requests: list[httpx.Request] = []
        self.failures = list(failures or [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "api.fda.gov"
        if self.failures:
            return httpx.Response(self.failures.pop(0), json={"error": {"code": "FIXTURE"}})
        raw_query = request.url.query.decode()
        search = next(
            (unquote_plus(part[7:]) for part in raw_query.split("&") if part.startswith("search=")), None
        )
        total = fixture_total(search)
        if total == 0:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
        return httpx.Response(200, json={"meta": {"last_updated": LAST_UPDATED, "results": {"total": total}}})


def fixture_report(name: str, terms: list[list[str]]) -> dict:
    return {
        "query": name,
        "molecule": {"chembl_id": "CHEMBL_FIXTURE", "name": name.upper()},
        "predictions": [
            {"hpo_id": f"HP:{index:07d}", "reaction_terms": group} for index, group in enumerate(terms)
        ],
        "cached_at": "2026-10-17T20:00:00+00:00",
    }


class FakeKnockoutAPI:
    def __init__(self, reports: dict[str, dict], watchlist: list[str]):
        self.reports = reports
        self.watchlist = watchlist
        self.posts: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "knockout.fixture.test"
        path = request.url.path
        if request.method == "GET" and path == "/api/watchlist":
            return httpx.Response(200, json={"drugs": self.watchlist})
        if request.method == "GET" and (found := re.fullmatch(r"/api/drugs/(.+)/report", path)):
            report = self.reports.get(found.group(1))
            return (
                httpx.Response(200, json=report)
                if report
                else httpx.Response(404, json={"detail": "unknown"})
            )
        if request.method == "POST" and path == "/api/webhooks/creao/signals":
            self.posts.append(request)
            if request.headers.get("X-Knockout-Webhook-Secret") != SECRET:
                return httpx.Response(401, json={"detail": "wrong secret"})
            body = json.loads(request.content)
            return httpx.Response(200, json={"stored": len(body["terms"]), "alerts": 0})
        return httpx.Response(404, json={"detail": "no route"})


def no_sleep(seconds: float) -> None:
    pass


def make_run(fake_openfda, fake_api=None, api_key=None, **options):
    openfda = watch.OpenFDA(
        httpx.Client(transport=httpx.MockTransport(fake_openfda)), api_key, pause=0, sleep=no_sleep
    )
    api = None
    if fake_api is not None:
        api = watch.KnockoutAPI(
            httpx.Client(transport=httpx.MockTransport(fake_api)), API_URL, SECRET, sleep=no_sleep
        )
    return watch.run(openfda=openfda, api=api, now=NOW, run_id="fixture-run", **options)


def expected_rows(term: str, quarters: list[watch.Quarter]) -> list[dict]:
    """Brute-force counts straight from the fixture reports, independent of watch.count_quarters."""
    drug = f'patient.drug.openfda.generic_name:"{FIXTURE_DRUG}"'
    reaction = f'patient.reaction.reactionmeddrapt.exact:"{term}"'
    rows = []
    for quarter in quarters:
        within = f"receivedate:[{quarter.start:%Y%m%d} TO {quarter.end:%Y%m%d}]"
        through = f"receivedate:[19000101 TO {quarter.end:%Y%m%d}]"
        counts = TermCounts(
            term=term,
            a=fixture_total(f"{drug} AND {reaction} AND {through}"),
            drug=fixture_total(f"{drug} AND {through}"),
            reaction=fixture_total(f"{reaction} AND {through}"),
            all=fixture_total(through),
        )
        prr = counts.prr
        rows.append(
            {
                "term": term,
                "quarter": quarter.label,
                "reports": fixture_total(f"{drug} AND {reaction} AND {within}"),
                "prr": prr if prr is not None and math.isfinite(prr) else None,
                "prr_infinite": prr == math.inf,
                "signal": counts.is_signal,
            }
        )
    return rows


@pytest.mark.parametrize(
    ("a", "drug", "reaction", "total"),
    [
        (86, 54_046, 311, 20_692_690),
        (2, 100, 10, 1_000_000),
        (10, 100, 50, 1_000),
        (0, 50, 100, 10_000_000),
        (5, 500, 5, 1_000_000),
        (0, 0, 10, 1_000),
        (3, 1_000, 3, 1_000),
    ],
)
def test_prr_chi_squared_and_signal_match_the_engine(a, drug, reaction, total):
    mine = watch.QuarterCounts("X", "2026Q2", 0, a, drug, reaction, total)
    engine = TermCounts(term="X", a=a, drug=drug, reaction=reaction, all=total)
    assert mine.prr == engine.prr
    assert mine.chi_squared == engine.chi_squared
    assert mine.is_signal == engine.is_signal
    assert mine.expected == engine.expected


def test_the_eculizumab_table_gives_prr_146_and_a_signal():
    counts = watch.QuarterCounts("MENINGOCOCCAL INFECTION", "2026Q2", 0, 86, 54_046, 311, 20_692_690)
    assert round(counts.prr) == 146
    assert counts.is_signal


def test_an_infinite_prr_is_sent_as_null_with_a_flag_and_still_flags_the_signal():
    counts = watch.QuarterCounts("X", "2026Q2", 5, 5, 500, 5, 1_000_000)
    assert counts.prr == float("inf")
    assert counts.to_payload() == {
        "term": "X",
        "quarter": "2026Q2",
        "reports": 5,
        "prr": None,
        "prr_infinite": True,
        "signal": True,
    }
    assert counts.to_summary()["prr_infinite"] is True


@pytest.mark.parametrize(
    ("number", "start", "end"),
    [
        (1, date(2025, 1, 1), date(2025, 3, 31)),
        (2, date(2025, 4, 1), date(2025, 6, 30)),
        (3, date(2025, 7, 1), date(2025, 9, 30)),
        (4, date(2025, 10, 1), date(2025, 12, 31)),
    ],
)
def test_quarter_bounds(number, start, end):
    quarter = watch.Quarter(2025, number)
    assert (quarter.start, quarter.end, quarter.label) == (start, end, f"2025Q{number}")


@pytest.mark.parametrize(
    ("last_updated", "count", "expected"),
    [
        (
            date(2026, 7, 30),
            8,
            ["2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"],
        ),
        (date(2026, 6, 30), 2, ["2026Q1", "2026Q2"]),
        (date(2026, 6, 29), 2, ["2025Q4", "2026Q1"]),
        (date(2026, 2, 1), 3, ["2025Q2", "2025Q3", "2025Q4"]),
    ],
)
def test_recent_quarters_are_complete_and_oldest_first(last_updated, count, expected):
    assert [quarter.label for quarter in watch.recent_quarters(last_updated, count)] == expected


def test_queries_are_encoded_exactly_like_the_engine():
    openfda = watch.OpenFDA(httpx.Client(), pause=0)
    search = (
        f"{watch.drug_search('Eculizumab')} AND {watch.reaction_search('meningococcal infection')} "
        f"AND {watch.received_through(date(2026, 6, 30))}"
    )
    assert openfda.public_url(search) == engine_openfda._url("event", search, "&limit=1")[1]
    assert watch.drug_search("Eculizumab") == engine_openfda.drug_search("Eculizumab")
    assert watch.reaction_search("meningococcal infection") == engine_openfda.reaction_search(
        "meningococcal infection"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://knockout.fixture.test",
        "https://knockout.fixture.test/",
        "https://knockout.fixture.test/api",
        " https://knockout.fixture.test/api/ ",
    ],
)
def test_api_url_works_with_or_without_api_suffix(url):
    assert watch.api_base(url) == "https://knockout.fixture.test"


def test_reaction_terms_are_collected_once_in_report_order():
    report = fixture_report(
        FIXTURE_DRUG, [[FIXTURE_TERM, OTHER_TERM], [], [" fixture reaction "], [OTHER_TERM]]
    )
    assert watch.reaction_terms(report) == [FIXTURE_TERM, OTHER_TERM]


def test_a_full_run_posts_the_contract_payload_for_each_watched_drug():
    fake_openfda = FakeOpenFDA()
    fake_api = FakeKnockoutAPI(
        {FIXTURE_DRUG: fixture_report(FIXTURE_DRUG, [[FIXTURE_TERM], [OTHER_TERM]])}, [FIXTURE_DRUG]
    )
    summary = make_run(fake_openfda, fake_api, quarter_count=8)

    assert summary["quarters"][-1] == "2026Q2"
    assert summary["openfda_last_updated"] == LAST_UPDATED
    assert len(fake_api.posts) == 1
    post = fake_api.posts[0]
    assert post.headers["X-Knockout-Webhook-Secret"] == SECRET
    body = json.loads(post.content)
    assert set(body) == {"drug", "run_id", "run_at", "term_source", "terms"}
    assert body["term_source"] == "report"
    assert (body["drug"], body["run_id"], body["run_at"]) == (
        FIXTURE_DRUG,
        "fixture-run",
        "2026-10-17T21:00:00+00:00",
    )
    assert all(set(row) == {"term", "quarter", "reports", "prr", "prr_infinite", "signal"} for row in body["terms"])

    quarters = watch.recent_quarters(date.fromisoformat(LAST_UPDATED), 8)

    def order(row):
        return row["term"], row["quarter"]

    expected = expected_rows(FIXTURE_TERM, quarters) + expected_rows(OTHER_TERM, quarters)
    assert sorted(body["terms"], key=order) == sorted(expected, key=order)

    by_quarter = {row["quarter"]: row for row in body["terms"] if row["term"] == FIXTURE_TERM}
    assert by_quarter["2024Q3"]["reports"] == 1
    assert by_quarter["2025Q1"]["reports"] == 4
    assert by_quarter["2026Q2"]["reports"] == 3
    assert sum(row["reports"] for row in by_quarter.values()) == 8
    assert by_quarter["2024Q4"]["signal"] is True

    outcome = summary["drugs"][0]
    assert outcome["status"] == "posted"
    assert (outcome["stored"], outcome["alerts"]) == (len(body["terms"]), 0)
    assert outcome["generic_name"] == FIXTURE_DRUG
    assert all(row["term"] == FIXTURE_TERM for row in outcome["signals_in_latest_quarter"])


def test_dry_run_reads_the_api_but_never_posts():
    fake_api = FakeKnockoutAPI({FIXTURE_DRUG: fixture_report(FIXTURE_DRUG, [[FIXTURE_TERM]])}, [FIXTURE_DRUG])
    summary = make_run(FakeOpenFDA(), fake_api, quarter_count=2, dry_run=True)
    assert fake_api.posts == []
    outcome = summary["drugs"][0]
    assert outcome["status"] == "dry_run"
    assert [row["quarter"] for row in outcome["payload"]["terms"]] == ["2026Q1", "2026Q2"]


def test_drug_and_term_overrides_need_no_api():
    summary = make_run(
        FakeOpenFDA(), None, drugs=[FIXTURE_DRUG], terms=[FIXTURE_TERM], quarter_count=1, dry_run=True
    )
    payload = summary["drugs"][0]["payload"]
    assert payload["term_source"] == "manual"
    assert payload["terms"] == expected_rows(FIXTURE_TERM, [watch.Quarter(2026, 2)])


def test_a_report_without_reaction_terms_is_skipped_without_counting():
    fake_openfda = FakeOpenFDA()
    fake_api = FakeKnockoutAPI({FIXTURE_DRUG: fixture_report(FIXTURE_DRUG, [[], []])}, [FIXTURE_DRUG])
    summary = make_run(fake_openfda, fake_api, quarter_count=4)
    assert summary["drugs"][0]["status"] == "skipped"
    assert "step 5" in summary["drugs"][0]["reason"]
    assert fake_api.posts == []
    assert len(fake_openfda.requests) == 1


def test_one_failing_drug_does_not_stop_the_others():
    fake_api = FakeKnockoutAPI(
        {FIXTURE_DRUG: fixture_report(FIXTURE_DRUG, [[FIXTURE_TERM]])}, ["unknownmab", FIXTURE_DRUG]
    )
    summary = make_run(FakeOpenFDA(), fake_api, quarter_count=2)
    statuses = {outcome["drug"]: outcome["status"] for outcome in summary["drugs"]}
    assert statuses == {"unknownmab": "failed", FIXTURE_DRUG: "posted"}
    assert "404" in summary["drugs"][0]["reason"]


def test_a_wrong_webhook_secret_marks_the_drug_failed():
    fake_api = FakeKnockoutAPI({FIXTURE_DRUG: fixture_report(FIXTURE_DRUG, [[FIXTURE_TERM]])}, [FIXTURE_DRUG])
    openfda = watch.OpenFDA(
        httpx.Client(transport=httpx.MockTransport(FakeOpenFDA())), pause=0, sleep=no_sleep
    )
    api = watch.KnockoutAPI(
        httpx.Client(transport=httpx.MockTransport(fake_api)), API_URL, "wrong", sleep=no_sleep
    )
    summary = watch.run(openfda=openfda, api=api, quarter_count=1, now=NOW)
    assert summary["drugs"][0]["status"] == "failed"
    assert "401" in summary["drugs"][0]["reason"]


def test_openfda_rate_limits_are_retried_and_404_counts_as_zero():
    pauses = []
    fake_openfda = FakeOpenFDA(failures=[429, 503])
    openfda = watch.OpenFDA(
        httpx.Client(transport=httpx.MockTransport(fake_openfda)), pause=0, sleep=pauses.append
    )
    assert openfda.total('patient.drug.openfda.generic_name:"nothingmab"') == 0
    assert len(fake_openfda.requests) == 3
    assert 5 in pauses


def test_the_openfda_key_is_sent_but_never_reported():
    fake_openfda = FakeOpenFDA()
    summary = make_run(
        fake_openfda,
        None,
        api_key="fixture-openfda-key",
        drugs=[FIXTURE_DRUG],
        terms=[FIXTURE_TERM],
        quarter_count=1,
        dry_run=True,
    )
    assert all("api_key=fixture-openfda-key" in str(request.url) for request in fake_openfda.requests)
    assert summary["openfda_key"] is True
    assert "fixture-openfda-key" not in json.dumps(summary)


def test_an_openfda_error_message_never_contains_the_key():
    openfda = watch.OpenFDA(
        httpx.Client(transport=httpx.MockTransport(FakeOpenFDA(failures=[400]))),
        "fixture-openfda-key",
        pause=0,
        sleep=no_sleep,
    )
    with pytest.raises(watch.WatchError) as error:
        openfda.total(None)
    assert "fixture-openfda-key" not in str(error.value)


def test_terms_without_a_drug_are_refused():
    with pytest.raises(watch.WatchError):
        make_run(FakeOpenFDA(), None, terms=[FIXTURE_TERM])


def test_main_needs_the_webhook_secret_unless_dry_run(monkeypatch):
    monkeypatch.delenv("KNOCKOUT_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("KNOCKOUT_API_URL", API_URL)
    assert watch.main([]) == 2


@pytest.mark.filterwarnings("ignore:You should not use the 'timeout' argument")
def test_the_payload_is_accepted_by_the_real_api_and_builds_the_trend(tmp_path, monkeypatch):
    """watch.py against the actual FastAPI app and file store, with a FIXTURE report and FIXTURE counts."""
    api_module = pytest.importorskip("knockout.api")
    from fastapi.testclient import TestClient
    from knockout import engine
    from knockout.store_files import FileStore

    monkeypatch.setenv("KNOCKOUT_WEBHOOK_SECRET", SECRET)

    def fake_predict(query, **options):
        report = engine.Report(
            query=query,
            generated_at="2026-10-17T20:00:00+00:00",
            molecule={"chembl_id": "CHEMBL_FIXTURE", "name": FIXTURE_DRUG.upper()},
        )
        report.predictions.append(
            engine.Prediction(
                hpo_id="HP:0000000",
                phenotype="Fixture phenotype",
                frequency="1/1",
                kind="clinical",
                gene="FIXTURE",
                target="Fixture protein",
                disease_id="fixture-deficiency",
                disease="Fixture deficiency",
                reaction_terms=[FIXTURE_TERM],
            )
        )
        return report

    monkeypatch.setattr(engine, "predict", fake_predict)
    store = FileStore(tmp_path / "store")
    store.add_watch(FIXTURE_DRUG)
    client = TestClient(api_module.create_app(store=store))

    openfda = watch.OpenFDA(
        httpx.Client(transport=httpx.MockTransport(FakeOpenFDA())), pause=0, sleep=no_sleep
    )
    api = watch.KnockoutAPI(client, str(client.base_url), SECRET, sleep=no_sleep)
    summary = watch.run(openfda=openfda, api=api, quarter_count=4, now=NOW, run_id="fixture-run")
    assert summary["drugs"][0]["status"] == "posted", summary
    assert summary["drugs"][0]["stored"] == 4

    trend = client.get(f"/api/drugs/{FIXTURE_DRUG}/trend").json()
    assert trend["last_run_at"] == "2026-10-17T21:00:00+00:00"
    quarters = trend["terms"][0]["quarters"]
    assert [item["quarter"] for item in quarters] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert [item["reports"] for item in quarters] == [0, 0, 0, 3]


@pytest.mark.live
def test_eculizumab_meningococcal_infection_on_live_openfda():
    with httpx.Client(timeout=60.0) as client:
        openfda = watch.OpenFDA(client, pause=1.6)
        summary = watch.run(
            openfda=openfda,
            api=None,
            drugs=["eculizumab"],
            terms=["MENINGOCOCCAL INFECTION"],
            quarter_count=1,
            dry_run=True,
        )
    row = summary["drugs"][0]["rows"][-1]
    assert row["a"] >= 86
    assert row["drug_reports"] >= 54_046
    assert row["prr"] > 100
    assert row["signal"] is True


def test_a_run_with_hand_picked_terms_gets_a_manual_run_id():
    now = datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc)
    assert watch.new_run_id(now, manual=True).startswith("manual-20261017T210000Z-")
    assert watch.new_run_id(now).startswith("creao-20261017T210000Z-")
