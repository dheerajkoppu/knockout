# Runbook

The exact commands, in order, to bring Knockout up on a laptop and to run the demo. Every command
runs from the repository root (`/Users/dheeraj/Downloads/Projects/knockout`) unless it starts with
`cd`. Deploying to Vultr and Vercel is in [`deploy/README.md`](deploy/README.md); the Creao steps
in the Creao interface are in [`creao/AGENT.md`](creao/AGENT.md).

## State on 17 Oct, 14:45 PDT

- Working with live data: ChEMBL targets and direction, the genetics catalog, the direction rule,
  the phenotype filter, the openFDA label and FAERS totals, the API with both stores, the report
  page, the five Fetch.ai agents talking locally, and the Creao watch script posting to the API.
- **Blocked on `GEMINI_API_KEY`:** step 5 (phenotype to reaction terms) cannot run, so every
  prediction is `unknown`, with the reason "phenotype not mapped yet (step 5)". No label quote, PRR
  or benchmark number comes out of the pipeline until the key is in `.env`. Nothing is faked to
  fill the gap. The web fixture (`?fixture=1`) is labelled FIXTURE on the page.
- Checked by hand: the eculizumab label's boxed warning matches `MENINGOCOCCAL INFECTION` with the
  engine's own `label_match.find`, and the engine's own counts give a=86, drug=54,046,
  reaction=311, all=20,692,690, PRR 145.96, signal true. So steps 6 to 8 are ready once step 5
  proposes that term.
- Tofacitinib has no prediction: ChEMBL's only tofacitinib mechanism is on a `PROTEIN FAMILY`
  target, and the protocol uses `SINGLE PROTEIN` only. The third demo drug is now ruxolitinib
  (JAK1, JAK3 and TYK2; 19 predictions).

## Environment variables

Put these in `.env` at the root (copy [`.env.example`](.env.example)); `knockout.config` loads it.
The web page and the agents have their own files.

| Part                   | Variable                                                                                   | Needed                       | What it does                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------ | ---------------------------- | ------------------------------------------------------------------- |
| Engine                 | `GEMINI_API_KEY`                                                                           | **yes, for any verdict**     | Step 5 mapping (Google AI Studio key)                               |
| Engine                 | `GEMINI_MODEL`                                                                             | no                           | A specific model; newest flash model when empty                     |
| Engine, Creao          | `OPENFDA_API_KEY`                                                                          | yes for the benchmark        | 240 requests a minute instead of about 40, and no 1,000 a day cap   |
| API store              | `DATABASE_URL`                                                                             | no                           | Tiger Data / TimescaleDB; file store under `data/store/` when empty |
| API store              | `KNOCKOUT_STORE_DIR`                                                                       | no                           | File store location                                                 |
| API                    | `KNOCKOUT_WEBHOOK_SECRET`                                                                  | yes for Creao                | Shared secret for the watch agent's webhook; 503 until set          |
| API                    | `KNOCKOUT_ALLOWED_ORIGINS`                                                                 | only for a custom web domain | Extra CORS origins (localhost:3000 and *.vercel.app are built in)   |
| API, agents            | `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE`          | no                           | Tracing, logs and AI agent monitoring                               |
| Creao watch            | `KNOCKOUT_API_URL`, `KNOCKOUT_WEBHOOK_SECRET`, `OPENFDA_API_KEY`, `WATCH_QUARTERS`         | the first two                | Set as Creao Secrets for the scheduled agent                        |
| Creao trigger (server) | `CREAO_API_KEY`, `CREAO_AGENT_ID`                                                          | no                           | `creao/trigger.py` starts a run from the server                     |
| Web (`web/.env.local`) | `NEXT_PUBLIC_API_URL`                                                                      | yes when hosted              | API base URL, inlined at build time                                 |
| Web                    | `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT`, `NEXT_PUBLIC_SENTRY_TRACE_API` | no                           | Session Replay and browser traces                                   |
| Web                    | `NEXT_PUBLIC_USE_FIXTURES`                                                                 | never on stage               | Shows the labelled fixture instead of the API                       |
| Agents (`agents/.env`) | `AGENT_SEED_ORCHESTRATOR`, `_TARGET`, `_GENETICS`, `_LABEL`, `_SIGNAL`                     | yes for Agentverse           | Private seeds; addresses derive from them                           |
| Agents                 | `KNOCKOUT_API_URL`                                                                         | yes                          | The API the specialists call (default http://localhost:8000)        |
| Agents                 | `AGENT_MAILBOX`, `AGENTVERSE_API_KEY`                                                      | for ASI:One                  | Mailbox mode, and the key `knockout_agents.connect` uses            |
| Agents                 | `ASI1_API_KEY`, payment settings                                                           | no                           | See [`agents/.env.example`](agents/.env.example)                    |
| Vultr                  | everything in [`deploy/vultr.env.example`](deploy/vultr.env.example)                       | on the server                | The complete list for the deployment                                |

## 1. One-time setup

```bash
# API and engine (Python 3.14)
python3.14 -m venv .venv
.venv/bin/python -m pip install --editable ".[dev,api]"
.venv/bin/knockout setup                      # Helix catalog and Orphanet product 6 into data/
cp .env.example .env                          # then fill in GEMINI_API_KEY and OPENFDA_API_KEY

# Agents (Python 3.12; uAgents does not support 3.14)
/opt/homebrew/bin/python3.12 -m venv agents/.venv
agents/.venv/bin/pip install -r agents/requirements-dev.txt
cp agents/.env.example agents/.env
(cd agents && .venv/bin/python -m knockout_agents.seeds >> .env)

# Web
cd web && pnpm install && cp .env.example .env.local && cd ..
```

`make setup` does the first block.

## 2. Check

```bash
.venv/bin/python -m pytest -q                 # 11 store tests skip without KNOCKOUT_TEST_DATABASE_URL or DATABASE_URL
.venv/bin/ruff check .
(cd agents && .venv/bin/python -m pytest -q)  # 22 pass, no network
(cd web && pnpm exec tsc --noEmit)
```

## 3. Bring it up locally

Put the store and the secret in the root `.env` once, so the API, the CLI and the tests read the
same values (no per-terminal `export`):

```bash
echo "DATABASE_URL=postgresql://knockout:knockout@127.0.0.1:5433/knockout" >> .env
echo "KNOCKOUT_WEBHOOK_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
```

With `KNOCKOUT_WEBHOOK_SECRET` set, `POST /api/watchlist` and `?refresh=true` also need the
`X-Knockout-Webhook-Secret` header, so a public deployment cannot spend the openFDA or Gemini quota.
The page's "Add to the watchlist" and "Run again" buttons then say they are closed; use `curl` with
the header. The watchlist holds at most 10 drugs.

Four terminals.

```bash
# 1. Database (skip to use the file store, and remove DATABASE_URL from .env)
docker compose up -d timescaledb
.venv/bin/python -m knockout.store            # prints "Schema applied to ... (TimescaleDB 2.30.2)"
KNOCKOUT_TEST_DATABASE_URL=postgresql://knockout:knockout@127.0.0.1:5433/knockout .venv/bin/python -m pytest -q tests/test_store.py

# 2. API on :8000 (docs at http://localhost:8000/api/docs); it stays in the foreground
.venv/bin/uvicorn knockout.api:app --port 8000

# 3. Report page on :3000 (localhost:3000 or 127.0.0.1:3000 for CORS)
cd web && NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm build && pnpm start -p 3000
# open http://localhost:3000/drug/eculizumab

# 4. Fetch.ai agents on :8100 (local only; drop --no-mailbox for Agentverse)
cd agents && KNOCKOUT_API_URL=http://localhost:8000 .venv/bin/python -m knockout_agents.run --no-mailbox
```

Then, from any other terminal, once the API is up:

```bash
curl -s localhost:8000/api/health             # gemini_key must be true, store postgres, before the demo
make warm                                     # eculizumab, ibrutinib, ruxolitinib once each
(cd agents && .venv/bin/python -m knockout_agents.resolver c5 btk jak3)   # cache the agents' ChEMBL lookups
```

One chat message through all five agents, without starting `run` (it starts them in one process):

```bash
cd agents && KNOCKOUT_API_URL=http://localhost:8000 .venv/bin/python -m knockout_agents.ask "What side effects should a C5 blocker cause?" --quiet
```

The watch agent, locally:

```bash
# Dry run: live openFDA, no API, nothing posted (about 90 s and 37 requests without a key)
.venv/bin/python creao/watch.py --dry-run --drug eculizumab --term "MENINGOCOCCAL INFECTION"

# Real run against the local API: reads the watchlist and each report's reaction terms, posts one webhook per drug.
# watch.py does not read .env, so pass the secret from it.
SECRET=$(grep '^KNOCKOUT_WEBHOOK_SECRET=' .env | cut -d= -f2-)
curl -s -X POST localhost:8000/api/watchlist -H 'content-type: application/json' -H "X-Knockout-Webhook-Secret: $SECRET" -d '{"drug":"eculizumab"}'
KNOCKOUT_API_URL=http://localhost:8000 KNOCKOUT_WEBHOOK_SECRET=$SECRET .venv/bin/python creao/watch.py --summary /tmp/watch_summary.json
curl -s localhost:8000/api/drugs/eculizumab/trend
```

Until step 5 runs, a report has no reaction terms, so the real run skips the drug. Add
`--drug eculizumab --term "MENINGOCOCCAL INFECTION"` to post a term by hand; the counts are live,
but the term was chosen by a person. Such a run gets a `manual-` run ID and `term_source: manual`,
and the report page captions its chart "Term supplied to the watch agent by hand". The local run
`creao-20261017T214531Z-25e810` was made this way before the flag existed; it is marked `manual` in
the local database.

The evidence trigger, for the Tiger Data demo:

```bash
docker compose exec -T timescaledb psql -U knockout -d knockout -f /dev/stdin < db/demo_trigger.sql
```

## 4. Once `GEMINI_API_KEY` is in `.env`

```bash
curl -s localhost:8000/api/health                                    # gemini_key: true
.venv/bin/knockout predict eculizumab --json data/reports/eculizumab.json
```

Expected, and not yet seen: the Recurrent Neisseria meningitidis infection prediction maps to a
term set containing `MENINGOCOCCAL INFECTION`, its verdict is `on_label` with the boxed-warning
sentence, and its counts show PRR 146 from 86 reports. If the mapping proposes other terms, the
verdict follows those terms; do not edit `data/mappings/hpo.json` by hand.

Cached reports that hold the "Step 5" problem rerun on their own on the next API request once the
key is set. Then:

```bash
make warm                                                            # rerun the demo drugs through the API
.venv/bin/python -m benchmark.score --generate-mappings              # maps all 1,666 benchmark phenotypes, then scores (needs OPENFDA_API_KEY; about 30 min)
.venv/bin/python -m benchmark.sample_mappings                        # 50 rows for a person to review
.venv/bin/python -m benchmark.score                                  # rescore after the review CSV is filled in
```

Set `SENTRY_DSN` before these runs: `knockout predict` and `benchmark.score` start Sentry, so the
Gemini mapping shows as `gen_ai` spans in AI agent monitoring. Once `hpo.json` is committed the
deployed API never calls Gemini, so these runs are the ones that fill that view.

Commit `data/mappings/hpo.json` after mapping and before quoting any number, as the protocol requires.
Before committing results, check that no key reached them:
`grep -rn 'api_key=\|key=' benchmark/results data/reports` must show nothing but `[Filtered]`.

## 5. Demo order (3:00 video and judging)

1. `curl -s <api>/api/health`: `gemini_key` true, `store` postgres.
2. ASI:One, chat with `knockout-orchestrator`: "What side effects should a C5 blocker cause?". The
   card shows eculizumab, Complement C5 (INHIBITOR), C5 deficiency and the meningococcal prediction.
3. Report page `/drug/eculizumab`: the chain, the boxed-warning quote, the 2×2 table and PRR 146.
   Use `?fixture=1` only if the live path is still blocked, and say on camera that it is the fixture.
4. `benchmark/results/RESULTS.md`: label precision first, then lift over the shuffle. If scoring has
   not run by the 09:30 freeze, show the frozen protocol and say "scoring pending" instead.
5. The watch section of the report page: last run time and the per-quarter bars.
6. `db/demo_trigger.sql` refusing a prediction with no evidence.

## 6. Stop everything

```bash
# Ctrl-C the API, web and agents terminals, or:
lsof -ti :8000 -i :3000 -i :8100 | xargs kill
docker compose down                             # add -v to delete the local database
```
