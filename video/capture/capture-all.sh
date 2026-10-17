#!/bin/zsh
# Captures everything the video shows from the running app, into capture/raw/:
#   the report page (home search, live report, fixture), the hand check, one local agents chat,
#   a watch-agent dry run, and the evidence-trigger demo.
#
#   capture/capture-all.sh            uses an API and a web build that are already running
#   capture/capture-all.sh --serve    starts the API on :8800 and the web build on :3300 for the capture, then stops them
#
# Environment: API_URL (default http://127.0.0.1:8800), WEB_URL (default http://127.0.0.1:3300),
# BUILT_API_URL (the NEXT_PUBLIC_API_URL the web build was made with, default http://localhost:8000),
# DATABASE_URL (read from ../.env when unset; the local TimescaleDB keeps the watch agent's trend).
set -e
cd "$(dirname "$0")/.."
VIDEO=$PWD
REPO=$VIDEO:h
API_URL=${API_URL:-http://127.0.0.1:8800}
WEB_URL=${WEB_URL:-http://127.0.0.1:3300}
BUILT_API_URL=${BUILT_API_URL:-http://localhost:8000}
RAW=$VIDEO/capture/raw
LOGS=$VIDEO/capture/logs
mkdir -p $RAW $LOGS

started=()
stop_database=false
cleanup() {
  for pid in $started; do pkill -P $pid 2>/dev/null || true; kill $pid 2>/dev/null || true; done
  if $stop_database; then (cd $REPO && docker compose stop timescaledb >/dev/null 2>&1) || true; fi
}
trap cleanup EXIT

if [[ "$1" == "--serve" ]]; then
  if [[ -z "$DATABASE_URL" && -f $REPO/.env ]]; then
    DATABASE_URL=$(grep '^DATABASE_URL=' $REPO/.env | cut -d= -f2- || true)
  fi
  DATABASE_URL=${DATABASE_URL:-postgresql://knockout:knockout@127.0.0.1:5433/knockout}
  if ! (cd $REPO && docker compose exec -T timescaledb true >/dev/null 2>&1); then
    # Started here, so stopped again at the end; its data volume is kept.
    (cd $REPO && docker compose up -d --wait timescaledb >/dev/null 2>&1) && stop_database=true || echo "TimescaleDB not started; the API uses whatever DATABASE_URL points at"
  fi
  (cd $REPO && DATABASE_URL=$DATABASE_URL KNOCKOUT_ALLOWED_ORIGINS=$WEB_URL .venv/bin/uvicorn knockout.api:app --host 127.0.0.1 --port ${API_URL##*:} > $LOGS/api.log 2>&1) &
  started+=($!)
  (cd $REPO/web && ./node_modules/.bin/next start -p ${WEB_URL##*:} -H 127.0.0.1 > $LOGS/web.log 2>&1) &
  started+=($!)
  for attempt in {1..60}; do
    curl -sf $API_URL/api/health >/dev/null && curl -sf $WEB_URL/ >/dev/null && break
    sleep 1
  done
fi

echo "health: $(curl -sf $API_URL/api/health || echo 'API not reachable')"
curl -sf $API_URL/api/health >/dev/null || { echo "Start the API first (RUNBOOK.md section 3) or pass --serve"; exit 1; }

echo "1/5 report page"
node capture/capture.mjs --web=$WEB_URL --api=$API_URL --builtApi=$BUILT_API_URL

echo "2/5 hand check with the engine's own code"
(cd $VIDEO && $REPO/.venv/bin/python capture/handcheck.py > /dev/null)

echo "3/5 one question through the five agents, locally"
date -u +%FT%TZ > $RAW/agents-ask.started
(cd $REPO/agents && KNOCKOUT_API_URL=$API_URL .venv/bin/python -m knockout_agents.ask "What side effects should a C5 blocker cause?" > $RAW/agents-ask.txt 2> $LOGS/agents-ask.log)

echo "4/5 watch agent dry run (live openFDA, about 90 s without a key)"
mapped=$(curl -sf $API_URL/api/drugs/eculizumab/report | python3 -c "import json,sys; r=json.load(sys.stdin); print(any(p.get('reaction_terms') for p in r.get('predictions', [])))")
term_arguments=()
[[ "$mapped" == "True" ]] || term_arguments=(--term "MENINGOCOCCAL INFECTION")
(date -u +%FT%TZ; cd $REPO && KNOCKOUT_API_URL=$API_URL .venv/bin/python creao/watch.py --dry-run --drug eculizumab $term_arguments --summary $RAW/watch-dry-run.json 2>&1; date -u +%FT%TZ) > $RAW/watch-dry-run.txt

echo "5/5 evidence trigger demo (changes nothing: both transactions fail or roll back)"
if (cd $REPO && docker compose exec -T timescaledb true >/dev/null 2>&1); then
  (cd $REPO && docker compose exec -T timescaledb sh -c 'cat > /tmp/demo.sql; psql -U knockout -d knockout -f /tmp/demo.sql 2>&1; rm /tmp/demo.sql' < db/demo_trigger.sql) > $RAW/trigger.txt
  (cd $REPO && docker compose exec -T timescaledb psql -U knockout -d knockout -tAc "select extversion from pg_extension where extname='timescaledb'") > $RAW/timescaledb-version.txt
else
  echo "   TimescaleDB container not running; kept the previous capture/raw/trigger.txt"
fi

echo "captured into capture/raw/; next: ./build.sh"
