# Knockout store on Tiger Data

Knockout keeps reports, predictions, their evidence and the watch agent's FAERS counts in Tiger Data
(TimescaleDB on PostgreSQL). The API uses this store whenever `DATABASE_URL` is set
(`knockout.api.default_store`); without it, it falls back to JSON files under `data/store/`.

| File               | What                                                                    |
| ------------------ | ----------------------------------------------------------------------- |
| `schema.sql`       | Every table, the hypertable, the continuous aggregate and both triggers |
| `demo_trigger.sql` | Shows the evidence trigger refusing a prediction, then rolls back       |

`schema.sql` is idempotent. `PostgresStore()` applies it on start, under an advisory lock, so a new
database needs no separate migration step.

## What is in it

| Object                      | Kind                        | Holds                                                                                                     |
| --------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------- |
| `drugs`                     | table                       | One row per drug name (lowercase), with its ChEMBL id                                                     |
| `reports`                   | table                       | The latest engine report per drug, as JSONB, with `cached_at`                                             |
| `predictions`               | table                       | One row per predicted effect: phenotype, disease, reaction terms, label quote, counts, verdict            |
| `evidence`                  | table                       | One row per cited record of a prediction (ChEMBL mechanism, catalog records, direction, phenotype, label) |
| `watchlist`                 | table                       | Drugs the Creao watch agent re-checks                                                                     |
| `signal_runs`               | table                       | One row per watch-agent run per drug                                                                      |
| `faers_counts`              | hypertable                  | Reports, PRR and signal per quarter, drug, reaction term and run; partitioned by quarter                  |
| `faers_trend`               | continuous aggregate        | Per drug, term and quarter, the count from the latest run; real-time, refreshed after every run           |
| `alerts`                    | table                       | Terms whose signal crossed from false to true since the previous run                                      |
| `predictions_need_evidence` | deferred constraint trigger | Fails the commit when a prediction has no evidence row                                                    |
| `evidence_keeps_chain`      | deferred constraint trigger | Fails the commit when deleting evidence leaves a prediction with none                                     |

**No prediction without its cited chain.** Both triggers are `DEFERRABLE INITIALLY DEFERRED`, so they
run at commit: a transaction may insert a prediction first and its evidence after, but it cannot
commit a prediction that has no evidence. `PostgresStore.save_report` writes the report, its
predictions and their evidence in one transaction; if any prediction arrives without records, the
whole report is refused (`knockout.store.MissingEvidence`) and the previous report stays.

**Alerts.** For each term, the run's state is its signal in the latest quarter the run reports. An
alert is a term whose state was `false` in the previous run of the same drug (by `run_at`) and is
`true` now. The first run of a drug sets the baseline and raises none. Re-posting a run is safe: counts
are upserted and an alert is stored once per term and run.

**Columnstore.** Chunks of `faers_counts` older than six years move to the columnstore; late recounts
of those quarters still upsert into them.

Reaction terms from the watch agent are stored uppercase, as FAERS spells them.

## Tiger Cloud (what the user does)

The agents never create accounts. To use Tiger Cloud:

1. Sign in to Tiger Cloud at tigerdata.com and create a service on the free plan (any region near the
   API host; Time-series and Analytics type).
2. Copy the service's connection string. It has this shape:
   `postgres://tsdbadmin:<password>@<service-id>.<project-id>.tsdb.cloud.timescale.com:<port>/tsdb?sslmode=require`
3. Put it in `.env` (gitignored) and in the deploy host's environment as `DATABASE_URL`. Never commit it.
4. Apply the schema once and check it:

   ```bash
   .venv/bin/python -m knockout.store            # prints "Schema applied to ... (TimescaleDB x.y.z)"
   psql "$DATABASE_URL" -f db/demo_trigger.sql   # shows the trigger refusing a bare prediction
   ```

5. Run the store tests against it. They create a schema named `knockout_test_<random>` and drop it at the
   end, so they never touch the real tables:

   ```bash
   .venv/bin/python -m pytest -q tests/test_store.py
   ```

   To run them against a different database than the app's, set `KNOCKOUT_TEST_DATABASE_URL`.

## Local TimescaleDB (Docker)

```bash
docker compose up -d timescaledb
export DATABASE_URL=postgresql://knockout:knockout@127.0.0.1:5433/knockout
.venv/bin/python -m pytest -q tests/test_store.py
```

The container listens on 127.0.0.1 only, on port 5433 (`TIMESCALEDB_PORT` changes it), and applies
`schema.sql` on its first start. Its password defaults to `knockout` for local use; set
`POSTGRES_PASSWORD` before starting it anywhere else. `docker compose down -v` deletes its data.

## Useful queries

```sql
-- the cited chain behind every prediction for a drug
select p.phenotype, p.verdict, e.source, e.description, e.url
from predictions p join evidence e on e.prediction_id = p.id
where p.drug = 'eculizumab' order by p.position, e.position;

-- the trend the report page draws
select term, quarter, reports, prr, signal from faers_trend where drug = 'eculizumab' order by term, quarter;
```
