"""PostgresStore against a real TimescaleDB. Each run uses its own schema and drops it, so any DATABASE_URL is safe."""

import copy
import math
import os
import uuid
from datetime import date

import psycopg
import pytest
from psycopg import sql

from knockout import config  # noqa: F401  (loads .env)
from knockout.store import (
    MissingEvidence,
    PostgresStore,
    _json_restore,
    _json_safe,
    quarter_label,
    quarter_start,
)

DATABASE_URL = os.environ.get("KNOCKOUT_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
needs_database = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set DATABASE_URL or KNOCKOUT_TEST_DATABASE_URL to a TimescaleDB to run store tests",
)


def fixture_report(drug: str) -> dict:
    """Test fixture shaped like engine Report.to_dict(); not a result."""
    return {
        "query": drug,
        "generated_at": "2026-10-17T20:00:00+00:00",
        "molecule": {
            "chembl_id": "CHEMBL_FIXTURE",
            "name": drug.title(),
            "max_phase": 4.0,
            "molecule_type": "Small molecule",
            "url": "https://example.org/fixture",
        },
        "targets": [
            {
                "chembl_id": "CHEMBL_T",
                "name": "Fixture protein",
                "accession": "P00000",
                "effect": "lowers",
                "action_types": ["INHIBITOR"],
                "gene": "FIX1",
                "used": True,
                "reason": None,
            }
        ],
        "diseases": [
            {
                "disease_id": "fixture-deficiency",
                "name": "Fixture deficiency",
                "gene": "FIX1",
                "direction": "decreased_activity",
                "direction_source": "disease_name",
                "direction_basis": "fixture",
                "pairing": "use",
                "phenotypes_used": 2,
            }
        ],
        "predictions": [
            {
                "hpo_id": "HP:0000001",
                "phenotype": "Fixture phenotype one",
                "frequency": "2/2",
                "kind": "clinical",
                "gene": "FIX1",
                "target": "Fixture protein",
                "disease_id": "fixture-deficiency",
                "disease": "Fixture deficiency",
                "reaction_terms": ["Fixture reaction"],
                "label_section": "boxed_warning",
                "label_term": "fixture reaction",
                "label_sentence": "FIXTURE REACTION SENTENCE.",
                "counts": [
                    {
                        "term": "Fixture reaction",
                        "a": 5,
                        "drug": 100,
                        "reaction": 5,
                        "all": 1000,
                        "prr": math.inf,
                        "chi_squared": 12.5,
                        "signal": True,
                        "expected": 0.5,
                        "query": "https://example.org/q",
                    }
                ],
                "verdict": "on_label",
                "reason": None,
                "candidate_new_signal": False,
                "records": [
                    {
                        "source": "chembl",
                        "description": "Fixture: INHIBITOR of Fixture protein",
                        "url": "https://example.org/chembl",
                    },
                    {"source": "disease_name", "description": "fixture direction", "url": None},
                ],
            },
            {
                "hpo_id": "HP:0000002",
                "phenotype": "Fixture phenotype two",
                "frequency": "Frequent",
                "kind": None,
                "gene": "FIX1",
                "target": "Fixture protein",
                "disease_id": "fixture-deficiency",
                "disease": "Fixture deficiency",
                "reaction_terms": [],
                "label_section": None,
                "label_term": None,
                "label_sentence": None,
                "counts": [],
                "verdict": "unknown",
                "reason": "phenotype not mapped yet (step 5)",
                "candidate_new_signal": False,
                "records": [
                    {"source": "chembl", "description": "Fixture: INHIBITOR of Fixture protein", "url": None}
                ],
            },
        ],
        "excluded_developmental": [],
        "label": None,
        "drug_reports": 100,
        "all_reports": 1000,
        "problems": [],
    }


@pytest.fixture(scope="module")
def store():
    schema = f"knockout_test_{uuid.uuid4().hex[:12]}"
    created = PostgresStore(DATABASE_URL, schema=schema)
    yield created
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(schema)))


def unique_drug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def count(store: PostgresStore, query: str, parameters: tuple) -> int:
    with store._connect() as connection:
        return connection.execute(query, parameters).fetchone()["count"]


def test_quarter_parsing():
    assert quarter_start("2025Q1") == date(2025, 1, 1)
    assert quarter_start("2025-q4") == date(2025, 10, 1)
    assert quarter_start("2025-08-19") == date(2025, 7, 1)
    assert quarter_label(date(2025, 4, 1)) == "2025Q2"
    with pytest.raises(ValueError):
        quarter_start("2025Q5")


def test_infinite_prr_survives_json():
    value = {"counts": [{"prr": math.inf, "term": "Infinity", "chi_squared": 1.0}]}
    safe = _json_safe(value)
    assert safe["counts"][0]["prr"] == "Infinity"
    assert _json_restore(safe) == value


@needs_database
def test_trigger_rejects_a_prediction_without_evidence(store):
    drug = unique_drug("bare")
    with (
        pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="has no evidence row"),
        store._connect() as connection,
    ):
        connection.execute("insert into drugs (name) values (%s)", (drug,))
        connection.execute(
            """insert into predictions (drug, position, hpo_id, phenotype, gene, target, disease_id, disease,
                   verdict) values (%s, 0, 'HP:0000001', 'Fixture', 'FIX1', 'Fixture protein', 'fixture', 'Fixture',
                   'unknown')""",
            (drug,),
        )
    assert count(store, "select count(*) from drugs where name = %s", (drug,)) == 0


@needs_database
def test_trigger_accepts_evidence_inserted_later_in_the_same_transaction(store):
    drug = unique_drug("chained")
    with store._connect() as connection:
        connection.execute("insert into drugs (name) values (%s)", (drug,))
        prediction_id = connection.execute(
            """insert into predictions (drug, position, hpo_id, phenotype, gene, target, disease_id, disease,
               verdict) values (%s, 0, 'HP:0000001', 'Fixture', 'FIX1', 'Fixture protein', 'fixture', 'Fixture',
               'unknown') returning id""",
            (drug,),
        ).fetchone()["id"]
        connection.execute(
            "insert into evidence (prediction_id, position, source, description) values (%s, 0, 'chembl', 'x')",
            (prediction_id,),
        )
    assert count(store, "select count(*) from predictions where drug = %s", (drug,)) == 1


@needs_database
def test_trigger_rejects_deleting_the_last_evidence_row(store):
    drug = unique_drug("stripped")
    store.save_report(drug, fixture_report(drug))
    with (
        pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="no evidence row"),
        store._connect() as connection,
    ):
        connection.execute(
            "delete from evidence where prediction_id in (select id from predictions where drug = %s)",
            (drug,),
        )
    assert (
        count(
            store,
            "select count(*) from evidence e join predictions p on p.id = e.prediction_id where p.drug = %s",
            (drug,),
        )
        == 3
    )


@needs_database
def test_save_report_refuses_a_prediction_without_records_and_keeps_the_old_report(store):
    drug = unique_drug("refused")
    store.save_report(drug, fixture_report(drug))
    before = store.get_report(drug)
    broken = fixture_report(drug)
    broken["generated_at"] = "2026-10-17T21:00:00+00:00"
    broken["predictions"][1]["records"] = []
    with pytest.raises(MissingEvidence, match="HP:0000002"):
        store.save_report(drug, broken)
    assert store.get_report(drug) == before
    assert count(store, "select count(*) from predictions where drug = %s", (drug,)) == 2


@needs_database
def test_report_round_trip(store):
    drug = unique_drug("roundtrip")
    report = fixture_report(drug)
    original = copy.deepcopy(report)
    store.save_report(drug.upper(), report)
    stored = store.get_report(drug)
    assert stored is not None
    cached_at = stored.pop("cached_at")
    assert cached_at.endswith("+00:00")
    assert stored == original
    assert stored["predictions"][0]["counts"][0]["prr"] == math.inf
    assert count(store, "select count(*) from predictions where drug = %s", (drug,)) == 2

    store.save_report(drug, report)
    assert count(store, "select count(*) from predictions where drug = %s", (drug,)) == 2
    assert (
        count(
            store,
            "select count(*) from evidence e join predictions p on p.id = e.prediction_id where p.drug = %s",
            (drug,),
        )
        == 3
    )
    with store._connect() as connection:
        row = connection.execute(
            "select chembl_id, display_name from drugs where name = %s", (drug,)
        ).fetchone()
    assert row == {"chembl_id": "CHEMBL_FIXTURE", "display_name": drug.title()}


@needs_database
def test_unknown_drug_is_empty(store):
    drug = unique_drug("absent")
    assert store.get_report(drug) is None
    assert store.trend(drug) == {"drug": drug, "terms": [], "last_run_at": None}
    assert store.alerts(drug) == {"drug": drug, "alerts": []}


@needs_database
def test_watchlist(store):
    first, second = unique_drug("watch-a"), unique_drug("watch-b")
    store.add_watch(first)
    store.add_watch(second.upper())
    store.add_watch(first)
    listed = store.watchlist()
    assert listed.count(first) == 1
    assert listed.index(first) < listed.index(second)


def run(drug: str, run_id: str, run_at: str, terms: list[tuple]) -> dict:
    return {
        "drug": drug,
        "run_id": run_id,
        "run_at": run_at,
        "terms": [
            {"term": term, "quarter": quarter, "reports": reports, "prr": prr, "signal": signal}
            for term, quarter, reports, prr, signal in terms
        ],
    }


@needs_database
def test_signal_runs_feed_trend_and_alerts(store):
    drug = unique_drug("watched")
    first = run(
        drug,
        "run-1",
        "2026-10-17T18:00:00Z",
        [
            ("Fixture reaction", "2025Q1", 1, 1.2, False),
            ("Fixture reaction", "2025Q2", 2, 1.8, False),
            ("OTHER REACTION", "2025Q2", 9, 5.0, True),
        ],
    )
    assert store.save_signal_run(first) == (3, 0)

    second = run(
        drug,
        "run-2",
        "2026-10-17T19:00:00Z",
        [
            ("FIXTURE REACTION", "2025Q1", 1, 1.2, False),
            ("FIXTURE REACTION", "2025Q2", 4, 2.1, False),
            ("FIXTURE REACTION", "2025Q3", 6, 3.4, True),
            ("OTHER REACTION", "2025Q2", 9, 5.0, True),
            ("NEW REACTION", "2025Q3", 7, 4.0, True),
        ],
    )
    assert store.save_signal_run(second) == (5, 1)
    assert store.save_signal_run(second) == (5, 0)

    alerts = store.alerts(drug)
    assert alerts == {
        "drug": drug,
        "alerts": [
            {
                "term": "FIXTURE REACTION",
                "quarter": "2025Q3",
                "prr": 3.4,
                "crossed_at": "2026-10-17T19:00:00+00:00",
                "run_id": "run-2",
            },
        ],
    }

    trend = store.trend(drug)
    assert trend["last_run_at"] == "2026-10-17T19:00:00+00:00"
    by_term = {item["term"]: item["quarters"] for item in trend["terms"]}
    assert [(quarter["quarter"], quarter["reports"]) for quarter in by_term["FIXTURE REACTION"]] == [
        ("2025Q1", 1),
        ("2025Q2", 4),
        ("2025Q3", 6),
    ]
    assert by_term["FIXTURE REACTION"][-1]["signal"] is True
    assert set(by_term) == {"FIXTURE REACTION", "OTHER REACTION", "NEW REACTION"}


@needs_database
def test_a_signal_that_stays_true_or_falls_raises_no_alert(store):
    drug = unique_drug("steady")
    store.save_signal_run(
        run(
            drug,
            "a",
            "2026-10-01T00:00:00Z",
            [("STEADY", "2025Q1", 5, 3.0, True), ("FALLING", "2025Q1", 5, 3.0, True)],
        )
    )
    stored, alerts = store.save_signal_run(
        run(
            drug,
            "b",
            "2026-10-02T00:00:00Z",
            [
                ("STEADY", "2025Q2", 6, 3.1, True),
                ("FALLING", "2025Q2", 2, 1.1, False),
            ],
        )
    )
    assert (stored, alerts) == (2, 0)
    stored, alerts = store.save_signal_run(
        run(drug, "c", "2026-10-03T00:00:00Z", [("FALLING", "2025Q3", 8, 4.0, True)])
    )
    assert (stored, alerts) == (1, 1)
    assert [alert["term"] for alert in store.alerts(drug)["alerts"]] == ["FALLING"]


@needs_database
def test_recounts_reach_old_quarters_in_the_columnstore(store):
    drug = unique_drug("archived")
    store.save_signal_run(run(drug, "old", "2026-10-01T00:00:00Z", [("ARCHIVED", "2012Q1", 3, 1.0, False)]))
    with store._connect(autocommit=True) as connection:
        try:
            connection.execute(
                "select compress_chunk(chunk, if_not_compressed => true)"
                " from show_chunks('faers_counts', older_than => date '2015-01-01') as chunk"
            )
        except psycopg.errors.DuplicateObject:
            pass  # the background compression policy got there first
        compressed = connection.execute(
            "select bool_and(is_compressed) as compressed from timescaledb_information.chunks"
            " where hypertable_schema = %s and hypertable_name = 'faers_counts' and range_end <= '2015-01-01'",
            (store.schema,),
        ).fetchone()["compressed"]
    assert compressed is True
    store.save_signal_run(run(drug, "new", "2026-10-02T00:00:00Z", [("ARCHIVED", "2012Q1", 5, 2.5, True)]))
    quarters = store.trend(drug)["terms"][0]["quarters"]
    assert quarters == [{"quarter": "2012Q1", "reports": 5, "prr": 2.5, "signal": True}]
    assert store.alerts(drug)["alerts"][0]["term"] == "ARCHIVED"


@needs_database
def test_signal_run_rejects_bad_input(store):
    drug = unique_drug("bad")
    with pytest.raises(ValueError):
        store.save_signal_run(run(drug, "x", "2026-10-01T00:00:00Z", [("T", "2025Q1", 1, 1.0, "false")]))
    with pytest.raises(ValueError):
        store.save_signal_run(run(drug, " ", "2026-10-01T00:00:00Z", []))
