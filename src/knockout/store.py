"""Tiger Data (TimescaleDB on PostgreSQL) store, used when DATABASE_URL is set. Same methods as the file store."""

import logging
import math
import os
import re
import sys
from datetime import UTC, date, datetime

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from knockout.config import ROOT_DIR

SCHEMA_PATH = ROOT_DIR / "db" / "schema.sql"
SCHEMA_LOCK = 2026_10_17
FLOAT_KEYS = frozenset({"prr", "chi_squared", "expected"})
NON_FINITE = {"Infinity": math.inf, "-Infinity": -math.inf, "NaN": math.nan}
QUARTER_PATTERN = re.compile(r"^(\d{4})\s*-?\s*Q([1-4])$", re.IGNORECASE)
SCHEMA_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

logger = logging.getLogger(__name__)


class MissingEvidence(Exception):
    """The database refused a report because a prediction reached commit with no evidence row."""


def normalize_drug(name: str) -> str:
    normalized = " ".join(str(name).split()).lower()
    if not normalized:
        raise ValueError("drug name is empty")
    return normalized


def normalize_term(term: str) -> str:
    normalized = " ".join(str(term).split()).upper()
    if not normalized:
        raise ValueError("reaction term is empty")
    return normalized


def quarter_start(value: str | date) -> date:
    """'2025Q1', '2025-Q1' or any ISO date inside the quarter -> the quarter's first day."""
    if isinstance(value, date):
        day = value
    else:
        text = str(value).strip()
        match = QUARTER_PATTERN.match(text)
        if match:
            return date(int(match[1]), 3 * int(match[2]) - 2, 1)
        day = date.fromisoformat(text[:10])
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def quarter_label(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def _timestamp(value) -> datetime:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _iso(moment: datetime | None) -> str | None:
    return moment.astimezone(UTC).isoformat(timespec="seconds") if moment else None


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


def _strict_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"signal must be true or false, got {value!r}")


def _json_safe(value):
    """JSON has no Infinity; PRR is infinite when every report of a reaction names the drug."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _json_restore(value, key: str | None = None):
    if isinstance(value, dict):
        return {item_key: _json_restore(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_json_restore(item, key) for item in value]
    if key in FLOAT_KEYS and isinstance(value, str) and value in NON_FINITE:
        return NON_FINITE[value]
    return value


def _jsonb(value) -> Jsonb:
    return Jsonb(_json_safe(value))


class PostgresStore:
    kind = "postgres"

    def __init__(
        self, database_url: str | None = None, *, schema: str | None = None, apply_schema: bool = True
    ):
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        if schema is not None and not SCHEMA_NAME_PATTERN.match(schema):
            raise ValueError(f"schema name {schema!r} must be lowercase letters, digits and underscores")
        self.schema = schema
        if apply_schema:
            self.ensure_schema()

    def _connect(self, *, autocommit: bool = False) -> psycopg.Connection:
        options = {"options": f"-c search_path={self.schema},public"} if self.schema else {}
        return psycopg.connect(
            self.database_url, autocommit=autocommit, row_factory=dict_row, connect_timeout=10, **options
        )

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("select pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
            if self.schema:
                connection.execute(
                    sql.SQL("create schema if not exists {}").format(sql.Identifier(self.schema))
                )
            connection.execute(SCHEMA_PATH.read_text())

    @staticmethod
    def _ensure_drug(connection: psycopg.Connection, name: str, molecule: dict | None = None) -> None:
        molecule = molecule or {}
        connection.execute(
            """
            insert into drugs (name, chembl_id, display_name, max_phase, molecule_type, url)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (name) do update set
                chembl_id = coalesce(excluded.chembl_id, drugs.chembl_id),
                display_name = coalesce(excluded.display_name, drugs.display_name),
                max_phase = coalesce(excluded.max_phase, drugs.max_phase),
                molecule_type = coalesce(excluded.molecule_type, drugs.molecule_type),
                url = coalesce(excluded.url, drugs.url),
                updated_at = now()
            """,
            (
                name,
                molecule.get("chembl_id"),
                molecule.get("name"),
                molecule.get("max_phase"),
                molecule.get("molecule_type"),
                molecule.get("url"),
            ),
        )

    def save_report(self, drug: str, report: dict) -> None:
        """Report, predictions and evidence in one transaction; the commit fails if any prediction lacks evidence."""
        name = normalize_drug(drug)
        generated_at = _timestamp(report["generated_at"]) if report.get("generated_at") else None
        try:
            with self._connect() as connection:
                self._ensure_drug(connection, name, report.get("molecule"))
                connection.execute(
                    """
                    insert into reports (drug, report, generated_at, cached_at) values (%s, %s, %s, now())
                    on conflict (drug) do update set
                        report = excluded.report, generated_at = excluded.generated_at, cached_at = excluded.cached_at
                    """,
                    (name, _jsonb(report), generated_at),
                )
                connection.execute("delete from predictions where drug = %s", (name,))
                for position, prediction in enumerate(report.get("predictions") or []):
                    prediction_id = connection.execute(
                        """
                        insert into predictions (
                            drug, position, hpo_id, phenotype, frequency, kind, gene, target, disease_id, disease,
                            reaction_terms, label_section, label_term, label_sentence, counts, verdict, reason,
                            candidate_new_signal, generated_at
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        returning id
                        """,
                        (
                            name,
                            position,
                            prediction["hpo_id"],
                            prediction.get("phenotype") or prediction["hpo_id"],
                            prediction.get("frequency"),
                            prediction.get("kind"),
                            prediction["gene"],
                            prediction["target"],
                            prediction["disease_id"],
                            prediction["disease"],
                            list(prediction.get("reaction_terms") or []),
                            prediction.get("label_section"),
                            prediction.get("label_term"),
                            prediction.get("label_sentence"),
                            _jsonb(prediction.get("counts") or []),
                            prediction.get("verdict") or "unknown",
                            prediction.get("reason"),
                            bool(prediction.get("candidate_new_signal")),
                            generated_at,
                        ),
                    ).fetchone()["id"]
                    records = prediction.get("records") or []
                    if records:
                        with connection.cursor() as cursor:
                            cursor.executemany(
                                "insert into evidence (prediction_id, position, source, description, url)"
                                " values (%s, %s, %s, %s, %s)",
                                [
                                    (
                                        prediction_id,
                                        index,
                                        record["source"],
                                        record.get("description") or "",
                                        record.get("url"),
                                    )
                                    for index, record in enumerate(records)
                                ],
                            )
        except psycopg.errors.IntegrityConstraintViolation as error:
            raise MissingEvidence(error.diag.message_primary or str(error)) from error

    def get_report(self, drug: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "select report, cached_at from reports where drug = %s", (normalize_drug(drug),)
            ).fetchone()
        if row is None:
            return None
        return _json_restore(row["report"]) | {"cached_at": _iso(row["cached_at"])}

    def add_watch(self, drug: str) -> None:
        name = normalize_drug(drug)
        with self._connect() as connection:
            self._ensure_drug(connection, name)
            connection.execute(
                "insert into watchlist (drug) values (%s) on conflict (drug) do nothing", (name,)
            )

    def watchlist(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("select drug from watchlist order by added_at, drug").fetchall()
        return [row["drug"] for row in rows]

    def save_signal_run(self, payload: dict) -> tuple[int, int]:
        """Store one watch-agent run. An alert is a term whose latest-quarter signal was false in the previous
        run of this drug and is true in this one. The first run of a drug sets the baseline and raises none."""
        name = normalize_drug(payload["drug"])
        run_id = str(payload["run_id"]).strip()
        if not run_id:
            raise ValueError("run_id is empty")
        run_at = _timestamp(payload["run_at"])
        rows: dict[tuple[str, date], tuple] = {}
        for item in payload.get("terms") or []:
            term = normalize_term(item["term"])
            quarter = quarter_start(item["quarter"])
            reports = int(item["reports"])
            if reports < 0:
                raise ValueError(f"reports for {term} {quarter_label(quarter)} is negative")
            rows[(term, quarter)] = (
                term,
                quarter,
                reports,
                _optional_float(item.get("prr")),
                _strict_bool(item.get("signal")),
            )

        with self._connect() as connection:
            self._ensure_drug(connection, name)
            run_at = connection.execute(
                """
                insert into signal_runs (drug, run_id, run_at, term_source) values (%s, %s, %s, %s)
                on conflict (drug, run_id) do update set received_at = now(), term_source = excluded.term_source
                returning run_at
                """,
                (name, run_id, run_at, payload.get("term_source") or "report"),
            ).fetchone()["run_at"]
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into faers_counts (quarter, drug, term, reports, prr, signal, run_id, run_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (drug, term, run_id, quarter) do update set
                        reports = excluded.reports, prr = excluded.prr, signal = excluded.signal
                    """,
                    [
                        (quarter, name, term, reports, prr, signal, run_id, run_at)
                        for term, quarter, reports, prr, signal in rows.values()
                    ],
                )
            connection.execute(
                """
                update signal_runs set terms = (
                    select count(distinct term) from faers_counts where drug = %s and run_id = %s
                ) where drug = %s and run_id = %s
                """,
                (name, run_id, name, run_id),
            )
            previous = connection.execute(
                """
                select run_id from signal_runs
                where drug = %s and run_id <> %s and (run_at, run_id) < (%s, %s)
                order by run_at desc, run_id desc limit 1
                """,
                (name, run_id, run_at, run_id),
            ).fetchone()
            alerts = 0
            if previous is not None:
                current_states = self._latest_states(connection, name, run_id)
                previous_states = self._latest_states(connection, name, previous["run_id"])
                with connection.cursor() as cursor:
                    for term, state in current_states.items():
                        before = previous_states.get(term)
                        if state["signal"] and before is not None and not before["signal"]:
                            cursor.execute(
                                """
                                insert into alerts (drug, term, quarter, prr, run_id, previous_run_id, crossed_at)
                                values (%s, %s, %s, %s, %s, %s, %s)
                                on conflict (drug, term, run_id) do nothing
                                """,
                                (
                                    name,
                                    term,
                                    state["quarter"],
                                    state["prr"],
                                    run_id,
                                    previous["run_id"],
                                    run_at,
                                ),
                            )
                            alerts += cursor.rowcount
        self._refresh_trend()
        return len(rows), alerts

    @staticmethod
    def _latest_states(connection: psycopg.Connection, name: str, run_id: str) -> dict[str, dict]:
        rows = connection.execute(
            """
            select distinct on (term) term, quarter, prr, signal from faers_counts
            where drug = %s and run_id = %s
            order by term, quarter desc
            """,
            (name, run_id),
        ).fetchall()
        return {row["term"]: row for row in rows}

    def _refresh_trend(self) -> None:
        """Recounted past quarters sit behind the aggregate's watermark, so refresh after every run."""
        try:
            with self._connect(autocommit=True) as connection:
                connection.execute("call refresh_continuous_aggregate('faers_trend', null, null)")
        except psycopg.Error as error:
            logger.warning("faers_trend refresh failed; the hourly policy will catch up: %s", error)

    def trend(self, drug: str) -> dict:
        name = normalize_drug(drug)
        with self._connect() as connection:
            rows = connection.execute(
                "select term, quarter, reports, prr, signal from faers_trend where drug = %s order by term, quarter",
                (name,),
            ).fetchall()
            last_run = connection.execute(
                "select max(run_at) as last_run_at from signal_runs where drug = %s", (name,)
            ).fetchone()
            sources = {
                row["term"]: row["term_source"]
                for row in connection.execute(
                    """
                    select distinct on (counts.term) counts.term, runs.term_source
                    from faers_counts counts join signal_runs runs using (drug, run_id)
                    where counts.drug = %s order by counts.term, counts.run_at desc
                    """,
                    (name,),
                ).fetchall()
            }
        terms: dict[str, list[dict]] = {}
        for row in rows:
            terms.setdefault(row["term"], []).append(
                {
                    "quarter": quarter_label(row["quarter"]),
                    "reports": row["reports"],
                    "prr": row["prr"],
                    "signal": row["signal"],
                }
            )
        return {
            "drug": name,
            "terms": [
                {"term": term, "source": sources.get(term, "report"), "quarters": quarters}
                for term, quarters in terms.items()
            ],
            "last_run_at": _iso(last_run["last_run_at"]),
        }

    def alerts(self, drug: str) -> dict:
        name = normalize_drug(drug)
        with self._connect() as connection:
            rows = connection.execute(
                "select term, quarter, prr, crossed_at, run_id from alerts where drug = %s"
                " order by crossed_at desc, term",
                (name,),
            ).fetchall()
        return {
            "drug": name,
            "alerts": [
                {
                    "term": row["term"],
                    "quarter": quarter_label(row["quarter"]),
                    "prr": row["prr"],
                    "crossed_at": _iso(row["crossed_at"]),
                    "run_id": row["run_id"],
                }
                for row in rows
            ],
        }


if __name__ == "__main__":
    store = PostgresStore()
    with store._connect() as connection:
        version = connection.execute(
            "select extversion from pg_extension where extname = 'timescaledb'"
        ).fetchone()["extversion"]
        target = f"{connection.info.host}:{connection.info.port}/{connection.info.dbname}"
    print(f"Schema applied to {target} (TimescaleDB {version})", file=sys.stderr)
