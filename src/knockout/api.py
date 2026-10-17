"""HTTP API for the report page, the agents and the Creao watch agent. Run with `uvicorn knockout.api:app`."""

import asyncio
import hmac
import logging
import math
import os
import threading
import time
from datetime import datetime
from typing import Annotated, Literal

import sentry_sdk
from fastapi import FastAPI, Header, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from knockout import config, engine, observability
from knockout.http import SourceError, refreshing
from knockout.store_files import DEFAULT_DIRECTORY, FileStore, drug_key, utc_iso

logger = logging.getLogger("knockout.api")

LOCAL_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
WATCHLIST_LIMIT = 10
ADMIN_HEADER = "X-Knockout-Webhook-Secret"
VERCEL_ORIGINS = r"https://[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.vercel\.app"
DrugName = Annotated[str, Path(min_length=1, max_length=120)]


def default_store():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        from knockout.store import PostgresStore

        return PostgresStore(database_url)
    return FileStore(os.environ.get("KNOCKOUT_STORE_DIR") or DEFAULT_DIRECTORY)


def store_kind(store) -> str:
    return getattr(store, "kind", "files" if isinstance(store, FileStore) else "postgres")


def is_stale(report: dict) -> bool:
    """A cached report that failed for a reason since fixed (a missing Gemini key, openFDA down) reruns."""
    problems = report.get("problems") or []
    if config.gemini_api_key() and any(problem.startswith("Step 5") for problem in problems):
        return True
    return any(problem.startswith("openFDA reports unavailable") for problem in problems) or any(
        (prediction.get("reason") or "").startswith("openFDA reports unavailable")
        for prediction in report.get("predictions") or []
    )


def json_safe(value):
    """JSON has no Infinity. A PRR is infinite when every report of the reaction names the drug, so the
    response carries null plus `<field>_infinite: true` instead."""
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if isinstance(item, float) and not math.isfinite(item):
                safe[key] = None
                if item > 0:
                    safe[f"{key}_infinite"] = True
            else:
                safe[key] = json_safe(item)
        return safe
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class UnknownDrug(Exception):
    pass


def canonical_key(report: dict) -> str | None:
    """The molecule's preferred name, so a brand name and the generic share watch data."""
    name = (report.get("molecule") or {}).get("name")
    return drug_key(name) if name else None


def _predict(key: str, refresh: bool) -> engine.Report:
    if not refresh:
        return engine.predict(key)
    with refreshing():
        return engine.predict(key)


def missing_evidence_types(store) -> tuple[type[Exception], ...]:
    """The Postgres store refuses a prediction without evidence; psycopg is only imported when it is in use."""
    if store_kind(store) != "postgres":
        return ()
    from knockout.store import MissingEvidence

    return (MissingEvidence,)


class ReportRunner:
    """Runs the engine in a worker thread, at most once at a time per drug, and caches through the store."""

    def __init__(self, store=None):
        self._store = store
        self._store_lock = threading.Lock()
        self._running: dict[str, asyncio.Task] = {}

    @property
    def store(self):
        # Opened on first use, so importing this module never connects to a database.
        with self._store_lock:
            if self._store is None:
                self._store = default_store()
            return self._store

    async def report(self, drug: str, refresh: bool = False) -> dict:
        key = drug_key(drug)
        if not refresh:
            cached = await run_in_threadpool(self.store.get_report, key)
            if cached is not None and not is_stale(cached):
                cached.setdefault("cached_at", cached.get("generated_at"))
                return cached
        task = self._running.get(key)
        if task is None:
            task = asyncio.create_task(self._run(key, refresh))
            self._running[key] = task
            task.add_done_callback(lambda finished: self._running.pop(key, None))
        # A client that disconnects must not cancel a run other requests are waiting on.
        return await asyncio.shield(task)

    async def _run(self, key: str, refresh: bool = False) -> dict:
        started = time.monotonic()
        with sentry_sdk.start_span(op="function", name="knockout.engine.predict") as span:
            span.set_data("knockout.drug", key)
            report = await run_in_threadpool(_predict, key, refresh)
            report_dict = report.to_dict()
            span.set_data("knockout.predictions", len(report_dict.get("predictions") or []))
        seconds = time.monotonic() - started
        if report_dict.get("molecule") is None:
            raise UnknownDrug("; ".join(report_dict.get("problems") or [f"no molecule named {key!r}"]))
        await run_in_threadpool(self.store.save_report, key, report_dict)
        canonical = canonical_key(report_dict)
        if canonical and canonical != key:
            await run_in_threadpool(self.store.save_report, canonical, report_dict)
        logger.info(
            "engine run for %s: %d predictions, %d problems, %.1f s",
            key, len(report_dict["predictions"]), len(report_dict["problems"]), seconds,
        )
        return report_dict | {"cached_at": utc_iso()}


class WatchRequest(BaseModel):
    drug: str = Field(min_length=1, max_length=120)


class SignalTerm(BaseModel):
    term: str = Field(min_length=1)
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$")
    reports: int = Field(ge=0)
    prr: float | None = None
    prr_infinite: bool = False
    signal: bool


class SignalRun(BaseModel):
    drug: str = Field(min_length=1, max_length=120)
    run_id: str = Field(min_length=1, max_length=200)
    run_at: datetime
    # "manual" when a person passed the terms to the watch agent (watch.py --term), not the report's mapping.
    term_source: Literal["report", "manual"] = "report"
    terms: list[SignalTerm]


def start_watch_run(drug: str) -> None:
    """Start the Creao watch agent for a newly watched drug, when CREAO_API_KEY and CREAO_AGENT_ID are set."""
    api_key, agent_id = os.environ.get("CREAO_API_KEY"), os.environ.get("CREAO_AGENT_ID")
    if not (api_key and agent_id):
        return

    def start() -> None:
        try:
            import httpx

            from creao.trigger import CreaoTrigger

            with httpx.Client(timeout=30.0) as client:
                started = CreaoTrigger(client, api_key, agent_id).start({"drugs": drug})
            logger.info("creao run %s started for %s", started.get("id"), drug)
        except Exception as error:  # noqa: BLE001 - a failed trigger must never fail the watchlist write
            logger.warning("creao trigger failed for %s: %s", drug, error)

    threading.Thread(target=start, daemon=True).start()


def allowed_origins() -> list[str]:
    extra = os.environ.get("KNOCKOUT_ALLOWED_ORIGINS", "")
    return LOCAL_ORIGINS + [origin.strip().rstrip("/") for origin in extra.split(",") if origin.strip()]


def create_app(store=None) -> FastAPI:
    observability.log_to_console()
    observability.setup()
    runner = ReportRunner(store)

    app = FastAPI(
        title="Knockout API",
        description="Predicts a drug's side effects from the genetic diseases of the proteins it blocks.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.runner = runner
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_origin_regex=VERCEL_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "gemini_key": bool(config.gemini_api_key()),
            "openfda_key": bool(config.openfda_api_key()),
            "store": store_kind(runner.store),
        }

    def require_admin(secret: str | None) -> None:
        """Writes that spend openFDA or Gemini quota need the server secret once KNOCKOUT_WEBHOOK_SECRET is set."""
        expected = os.environ.get("KNOCKOUT_WEBHOOK_SECRET")
        if expected and (secret is None or not hmac.compare_digest(secret.encode(), expected.encode())):
            raise HTTPException(
                status_code=401,
                detail="Adding to the watchlist and running again are closed on this server; they need the "
                f"server's {ADMIN_HEADER} header, so the team runs them.",
            )

    @app.get("/api/drugs/{name}/report")
    async def drug_report(
        name: DrugName,
        refresh: bool = Query(False),
        admin_secret: Annotated[str | None, Header(alias=ADMIN_HEADER)] = None,
    ) -> dict:
        if refresh:
            require_admin(admin_secret)
        try:
            return json_safe(await runner.report(name, refresh=refresh))
        except UnknownDrug as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except missing_evidence_types(runner.store) as error:
            sentry_sdk.capture_exception(error)
            logger.error("store refused the report for %s: %s", drug_key(name), error)
            raise HTTPException(status_code=500, detail=f"the store refused the report: {error}") from error
        except SourceError as error:
            detail = observability.scrub(str(error))
            logger.warning("engine source failure for %s: %s", drug_key(name), detail)
            raise HTTPException(status_code=502, detail=f"an upstream source failed: {detail}") from error

    @app.get("/api/drugs/{name}/trend")
    async def drug_trend(name: DrugName) -> dict:
        return json_safe(await run_in_threadpool(runner.store.trend, drug_key(name)))

    @app.get("/api/drugs/{name}/alerts")
    async def drug_alerts(name: DrugName) -> dict:
        return json_safe(await run_in_threadpool(runner.store.alerts, drug_key(name)))

    @app.get("/api/watchlist")
    async def get_watchlist() -> dict:
        return {"drugs": await run_in_threadpool(runner.store.watchlist)}

    @app.post("/api/watchlist")
    async def add_to_watchlist(
        request: WatchRequest,
        admin_secret: Annotated[str | None, Header(alias=ADMIN_HEADER)] = None,
    ) -> dict:
        require_admin(admin_secret)
        drug = drug_key(request.drug)
        watched = await run_in_threadpool(runner.store.watchlist)
        if drug not in watched and len(watched) >= WATCHLIST_LIMIT:
            raise HTTPException(status_code=409, detail=f"the watchlist is full ({WATCHLIST_LIMIT} drugs)")
        await run_in_threadpool(runner.store.add_watch, drug)
        if drug not in watched:
            start_watch_run(drug)
        return {"drugs": await run_in_threadpool(runner.store.watchlist)}

    @app.post("/api/webhooks/creao/signals")
    async def creao_signals(
        run: SignalRun,
        webhook_secret: Annotated[str | None, Header(alias="X-Knockout-Webhook-Secret")] = None,
    ) -> dict:
        expected = os.environ.get("KNOCKOUT_WEBHOOK_SECRET")
        if not expected:
            raise HTTPException(status_code=503, detail="KNOCKOUT_WEBHOOK_SECRET is not set on the server")
        if webhook_secret is None or not hmac.compare_digest(webhook_secret.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="wrong or missing X-Knockout-Webhook-Secret")
        payload = run.model_dump(mode="json")
        payload["drug"] = drug_key(run.drug)
        for term in payload["terms"]:
            if term.pop("prr_infinite", False):
                term["prr"] = math.inf
        payload["run_at"] = utc_iso(run.run_at)
        stored, alerts = await run_in_threadpool(runner.store.save_signal_run, payload)
        logger.info("creao run %s for %s: %d rows, %d alerts", run.run_id, payload["drug"], stored, alerts)
        return {"stored": stored, "alerts": alerts}

    return app


app = create_app()
