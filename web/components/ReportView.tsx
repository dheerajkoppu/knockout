"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import eculizumabFixture from "@/fixtures/eculizumab.json";
import {
  addToWatchlist,
  API_URL,
  ApiError,
  FIXTURES_BY_DEFAULT,
  fetchAlerts,
  fetchReport,
  fetchTrend,
  fetchWatchlist,
} from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { Alerts, Report, Trend } from "@/lib/types";

import { EXAMPLE_DRUGS } from "./DrugSearch";
import { ReportBody } from "./ReportBody";
import { RunningHeader } from "./RunningHeader";

const FIXTURES: Record<string, Report> = {
  eculizumab: eculizumabFixture as Report,
};

type ReportState =
  | { status: "loading" }
  | { status: "ready"; report: Report; source: "live" | "fixture" }
  | { status: "error"; error: ApiError };

export type Loadable<T> =
  | { status: "loading" }
  | { status: "ready"; value: T }
  | { status: "absent"; reason: string };

export interface Monitoring {
  trend: Loadable<Trend>;
  alerts: Loadable<Alerts>;
  watched: boolean | null;
  watch: () => Promise<void>;
  watchError: string | null;
}

function absentReason(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) return "none yet";
  if (error instanceof ApiError) return error.message;
  return "unavailable";
}

export function ReportView({
  name,
  fixtureRequested,
}: {
  name: string;
  fixtureRequested: boolean;
}) {
  const useFixture = fixtureRequested || FIXTURES_BY_DEFAULT;
  const fixture = FIXTURES[name];
  const [state, setState] = useState<ReportState>(() =>
    useFixture && fixture
      ? { status: "ready", report: fixture, source: "fixture" }
      : { status: "loading" },
  );
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [trend, setTrend] = useState<Loadable<Trend>>({ status: "loading" });
  const [alerts, setAlerts] = useState<Loadable<Alerts>>({ status: "loading" });
  const [watched, setWatched] = useState<boolean | null>(null);
  const [watchError, setWatchError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (refresh: boolean) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      try {
        const report = await fetchReport(name, {
          refresh,
          signal: controller.signal,
        });
        setState({ status: "ready", report, source: "live" });
        setRefreshError(null);
      } catch (error) {
        if (controller.signal.aborted) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError("The report could not be read.", "status");
        if (refresh) setRefreshError(`The new run failed, so this is still the stored report. ${apiError.message}`);
        setState((previous) =>
          refresh && previous.status === "ready"
            ? previous
            : { status: "error", error: apiError },
        );
      } finally {
        if (!controller.signal.aborted) setRefreshing(false);
      }
    },
    [name],
  );

  useEffect(() => {
    if (useFixture) return;
    load(false);
    return () => controllerRef.current?.abort();
  }, [load, useFixture]);

  const live = state.status === "ready" && state.source === "live";
  // Watch data is stored under the molecule's name, so /drug/soliris reads eculizumab's trend.
  const watchName =
    state.status === "ready" && state.report.molecule?.name
      ? state.report.molecule.name.toLowerCase()
      : name;

  useEffect(() => {
    if (!live) return;
    const controller = new AbortController();
    fetchTrend(watchName, controller.signal)
      .then((value) => setTrend({ status: "ready", value }))
      .catch(
        (error) =>
          !controller.signal.aborted &&
          setTrend({ status: "absent", reason: absentReason(error) }),
      );
    fetchAlerts(watchName, controller.signal)
      .then((value) => setAlerts({ status: "ready", value }))
      .catch(
        (error) =>
          !controller.signal.aborted &&
          setAlerts({ status: "absent", reason: absentReason(error) }),
      );
    fetchWatchlist(controller.signal)
      .then((value) =>
        setWatched(
          value.drugs.map((drug) => drug.toLowerCase()).includes(watchName),
        ),
      )
      .catch(() => !controller.signal.aborted && setWatched(null));
    return () => controller.abort();
  }, [live, watchName]);

  const watch = useCallback(async () => {
    setWatchError(null);
    try {
      const value = await addToWatchlist(watchName);
      setWatched(value.drugs.map((drug) => drug.toLowerCase()).includes(watchName));
    } catch (error) {
      setWatchError(
        error instanceof ApiError
          ? error.message
          : "The watchlist could not be updated.",
      );
    }
  }, [watchName]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    load(true);
  }, [load]);

  const displayName =
    state.status === "ready"
      ? (state.report.molecule?.name ?? titleCase(name))
      : titleCase(name);
  const sourceState =
    state.status === "ready"
      ? state.source === "fixture"
        ? ({ state: "fixture", label: "FIXTURE" } as const)
        : ({ state: "live", label: "Live API" } as const)
      : state.status === "error"
        ? state.error.kind === "unreachable"
          ? ({ state: "offline", label: "API not reachable" } as const)
          : ({ state: "live", label: "Live API" } as const)
        : ({ state: "pending", label: "Running" } as const);

  return (
    <>
      <RunningHeader current={displayName} sourceState={sourceState} />
      {state.status === "ready" && state.source === "fixture" ? (
        <FixtureBand report={state.report} />
      ) : null}
      <main>
        <div className="page">
          {state.status === "loading" && !(useFixture && !fixture) ? (
            <Loading name={displayName} />
          ) : null}
          {state.status === "error" ? (
            <LoadError
              name={name}
              displayName={displayName}
              error={state.error}
              hasFixture={Boolean(fixture)}
            />
          ) : null}
          {useFixture && !fixture ? <NoFixture name={name} /> : null}
          {state.status === "ready" ? (
            <ReportBody
              report={state.report}
              source={state.source}
              onRefresh={state.source === "live" ? refresh : undefined}
              refreshing={refreshing}
              refreshError={refreshError}
              monitoring={
                state.source === "live"
                  ? { trend, alerts, watched, watch, watchError }
                  : null
              }
            />
          ) : null}
        </div>
      </main>
    </>
  );
}

function FixtureBand({ report }: { report: Report }) {
  return (
    <div className="fixture-band" role="note">
      <div className="fixture-band-inner">
        <strong>FIXTURE</strong>
        <p>
          {report._fixture?.note ?? "Development data, not a result. This report was not produced by the API."}
        </p>
      </div>
    </div>
  );
}

const PIPELINE_STEPS = [
  "Finds the drug in ChEMBL and the proteins it acts on",
  "Looks up each protein's genetic diseases in the IUIS catalog",
  "Keeps the diseases where the protein fails the same way the drug pushes it",
  "Takes the symptoms seen in at least 30% of cases",
  "Maps each symptom to adverse-event reaction terms",
  "Searches the FDA label for those terms, word for word",
  "Counts FAERS reports and tests each term for a signal",
  "Gives each predicted effect its verdict",
];

function Loading({ name }: { name: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, []);
  const minutes = Math.floor(seconds / 60);
  const elapsed = `${minutes}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <section className="loading" aria-live="polite" aria-busy="true">
      <div className="masthead-kicker">
        <span className="eyebrow">Side-effect report</span>
        <span className="elapsed">{elapsed}</span>
      </div>
      <h1 className="masthead-title">{name}</h1>
      <p className="masthead-deck">
        Running the pipeline. A first run reads ChEMBL, the genetic catalog, the
        FDA label and FAERS live, and can take a minute or two. Later visits
        open the stored report at once.
      </p>
      <div
        className="progress-line"
        role="progressbar"
        aria-label="Running the pipeline"
      />
      <ol className="loading-steps">
        {PIPELINE_STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </section>
  );
}

function LoadError({
  name,
  displayName,
  error,
  hasFixture,
}: {
  name: string;
  displayName: string;
  error: ApiError;
  hasFixture: boolean;
}) {
  return (
    <section>
      <div className="masthead">
        <div className="masthead-kicker">
          <span className="eyebrow">Side-effect report</span>
        </div>
        <h1 className="masthead-title">{displayName}</h1>
      </div>
      <div className="notice" role="alert">
        <h2>
          {error.kind === "unreachable"
            ? "The Knockout API is not answering"
            : error.status === 404
              ? "ChEMBL has no molecule by that name"
              : "The report could not be built"}
        </h2>
        <p>{error.message}</p>
        {error.status === 404 ? (
          <p>
            Try the generic name, for example{" "}
            {EXAMPLE_DRUGS.map((drug, index) => (
              <span key={drug}>
                {index ? ", " : ""}
                <Link href={`/drug/${drug}`}>{drug}</Link>
              </span>
            ))}
            .
          </p>
        ) : null}
        {error.kind === "unreachable" ? (
          <p>
            Start the API on <code>{API_URL}</code>, or point{" "}
            <code>NEXT_PUBLIC_API_URL</code> at a running one, then reload this
            page. A browser origin the API does not allow (CORS) looks the same
            as an API that is down: open the page on an allowed address such as{" "}
            <code>http://localhost:3000</code>, or add this one to{" "}
            <code>KNOCKOUT_ALLOWED_ORIGINS</code>.
          </p>
        ) : null}
        <div className="actions">
{error.status === 404 ? null : (
          <button
            type="button"
            className="button button-solid"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
)}
          {hasFixture ? (
            <Link
              className="button"
              href={`/drug/${encodeURIComponent(name)}?fixture=1`}
            >
              Open the development fixture
            </Link>
          ) : null}
          <Link className="button" href="/">
            Search another drug
          </Link>
        </div>
      </div>
    </section>
  );
}

function NoFixture({ name }: { name: string }) {
  return (
    <div className="notice">
      <h2>No fixture for {titleCase(name)}</h2>
      <p>
        Fixtures exist for development only. The one fixture is{" "}
        <Link href="/drug/eculizumab?fixture=1">eculizumab</Link>. Every other
        drug needs the live API; try{" "}
        {EXAMPLE_DRUGS.filter((drug) => drug !== "eculizumab").map(
          (drug, index) => (
            <span key={drug}>
              {index ? " or " : ""}
              <Link href={`/drug/${drug}`}>{drug}</Link>
            </span>
          ),
        )}
        .
      </p>
    </div>
  );
}
