"use client";

import { useState } from "react";

import { formatRatio } from "@/lib/format";
import type { TrendQuarter } from "@/lib/types";

import { ClientTime } from "./ClientTime";
import type { Monitoring } from "./ReportView";
import { TrendChart } from "./TrendChart";

export function MonitoringSection({
  name,
  monitoring,
  source,
  mappedTerms,
}: {
  name: string;
  query: string;
  monitoring: Monitoring | null;
  source: "live" | "fixture";
  mappedTerms: string[];
}) {
  return (
    <section className="section" aria-labelledby="monitoring-title">
      <div className="section-label">
        <span className="section-number">03</span>
        <h2 className="section-title" id="monitoring-title">
          Watching the reports
        </h2>
        <p className="section-note">
          A scheduled watch agent pulls new FAERS reports for every watched drug and recomputes each signal. This page
          never waits on a run.
        </p>
      </div>
      <div className="section-body">
        {source === "fixture" || !monitoring ? (
          <p className="empty-note">
            The fixture holds no watch-agent runs. Trends and threshold alerts appear here when the page reads the live
            API.
          </p>
        ) : (
          <LiveMonitoring name={name} monitoring={monitoring} mappedTerms={mappedTerms} />
        )}
      </div>
    </section>
  );
}

function latestQuarter(quarters: TrendQuarter[]): TrendQuarter | undefined {
  return [...quarters].sort((left, right) => left.quarter.localeCompare(right.quarter)).at(-1);
}

function LiveMonitoring({
  name,
  monitoring,
  mappedTerms,
}: {
  name: string;
  monitoring: Monitoring;
  mappedTerms: string[];
}) {
  const [busy, setBusy] = useState(false);
  const { trend, alerts, watched, watch, watchError } = monitoring;
  const trendValue = trend.status === "ready" ? trend.value : null;
  const alertList = alerts.status === "ready" ? alerts.value.alerts : [];
  const mapped = new Set(mappedTerms.map((term) => term.toUpperCase()));
  const terms = (trendValue?.terms.filter((item) => item.quarters.length) ?? []).map((item) => ({
    ...item,
    manual: item.source === "manual" || !mapped.has(item.term.toUpperCase()),
  }));
  const ordered = [...terms.filter((item) => !item.manual), ...terms.filter((item) => item.manual)];
  const alreadyAbove = terms
    .map((item) => ({ term: item.term, latest: latestQuarter(item.quarters) }))
    .filter((item) => item.latest?.signal);

  async function onWatch() {
    setBusy(true);
    await watch();
    setBusy(false);
  }

  return (
    <>
      <div className="monitor-head">
        <p className="monitor-run" aria-live="polite">
          {trend.status === "loading" ? "Reading the watch agent's last run." : null}
          {trendValue?.last_run_at ? (
            <>
              Last watch-agent run{" "}
              <b>
                <ClientTime value={trendValue.last_run_at} relative />
              </b>
              .
            </>
          ) : null}
          {trend.status !== "loading" && !trendValue?.last_run_at
            ? `The watch agent has not reported on ${name} yet.`
            : null}
        </p>
        <button
          type="button"
          className={watched ? "button" : "button button-solid"}
          onClick={onWatch}
          disabled={busy || watched === true}
        >
          {watched ? "On the watchlist" : busy ? "Adding" : "Add to the watchlist"}
        </button>
      </div>
      {watchError ? (
        <p className="entry-reason" role="alert" style={{ marginBottom: "var(--space-5)" }}>
          {watchError}
        </p>
      ) : null}

      {alertList.length ? (
        <ul className="alerts" aria-label="Threshold alerts">
          {alertList.map((alert) => (
            <li className="alert" key={`${alert.term}-${alert.quarter}`}>
              <span className="mono">{alert.term}</span>
              <span>
                crossed the signal threshold in {alert.quarter}
                {alert.prr_infinite ? ", PRR ∞" : alert.prr != null ? `, PRR ${formatRatio(alert.prr)}` : ""}
              </span>
              <ClientTime value={alert.crossed_at} />
            </li>
          ))}
        </ul>
      ) : alerts.status === "ready" && trendValue?.last_run_at ? (
        <p className="empty-note" style={{ marginBottom: "var(--space-6)" }}>
          {alreadyAbove.length
            ? `${alreadyAbove
                .map(
                  (item) =>
                    `${item.term} has been above the signal threshold since the first watch run${
                      item.latest?.prr_infinite
                        ? " (PRR ∞)"
                        : item.latest?.prr != null
                          ? ` (PRR ${formatRatio(item.latest.prr)})`
                          : ""
                    }`,
                )
                .join("; ")}. No new crossings since then.`
            : "No term has crossed the signal threshold since the watch began."}
        </p>
      ) : null}

      {ordered.length ? (
        <div className="trend-grid">
          {ordered.map((item) => (
            <TrendChart
              key={item.term}
              term={item.term}
              quarters={item.quarters}
              manual={item.manual}
              alertQuarters={alertList.filter((alert) => alert.term === item.term).map((alert) => alert.quarter)}
            />
          ))}
        </div>
      ) : trend.status === "absent" && trend.reason !== "none yet" ? (
        <p className="empty-note">The trend could not be read: {trend.reason}</p>
      ) : null}
    </>
  );
}
