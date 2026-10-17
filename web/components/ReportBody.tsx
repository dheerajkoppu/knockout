"use client";

import { useMemo, useState } from "react";

import { CAVEATS } from "@/lib/caveats";
import {
  countRatio,
  formatCount,
  formatDate,
  pluralize,
  strongestCount,
  targetReason,
  VERDICTS,
  verdictTally,
  wasChecked,
} from "@/lib/format";
import type { Prediction, Report, Verdict } from "@/lib/types";

import { Chain } from "./Chain";
import { ClientTime } from "./ClientTime";
import { MonitoringSection } from "./MonitoringSection";
import { NotUsed } from "./NotUsed";
import { PredictionEntry } from "./PredictionEntry";
import { Unchecked } from "./Unchecked";
import type { Monitoring } from "./ReportView";
import { VerdictMark } from "./VerdictMark";

const VERDICT_ORDER: Verdict[] = [
  "on_label",
  "signal_in_reports",
  "no_signal",
  "unknown",
];
const UNMAPPED = "phenotype not mapped yet (step 5)";

function rankRatio(count: ReturnType<typeof strongestCount>) {
  return count ? countRatio(count) : null;
}

const KIND_ORDER: Record<string, number> = { clinical: 0, laboratory: 2 };

function sortPredictions(predictions: Prediction[]) {
  return [...predictions].sort((left, right) => {
    const byVerdict =
      VERDICT_ORDER.indexOf(left.verdict) -
      VERDICT_ORDER.indexOf(right.verdict);
    if (byVerdict) return byVerdict;
    if (left.candidate_new_signal !== right.candidate_new_signal)
      return left.candidate_new_signal ? -1 : 1;
    const byKind =
      (KIND_ORDER[left.kind ?? ""] ?? 1) - (KIND_ORDER[right.kind ?? ""] ?? 1);
    if (byKind) return byKind;
    return (
      (rankRatio(strongestCount(right.counts)) ?? -1) -
      (rankRatio(strongestCount(left.counts)) ?? -1)
    );
  });
}

function list(items: string[]) {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

function TargetPhrase({ targets }: { targets: Report["targets"] }) {
  const groups = [
    { verb: "blocks", names: targets.filter((target) => target.effect !== "raises").map((target) => target.name) },
    { verb: "activates", names: targets.filter((target) => target.effect === "raises").map((target) => target.name) },
  ].filter((group) => group.names.length);
  return (
    <>
      {groups.map((group, index) => (
        <span key={group.verb}>
          {index ? " and " : ""}
          {group.verb} <b>{list(group.names)}</b>
        </span>
      ))}
    </>
  );
}

/** Why a report has no predictions, from the engine's own reasons. */
function emptyReasons(report: Report): string[] {
  const reasons = report.targets
    .filter((target) => !target.used)
    .map((target) => `${target.name}: ${targetReason(target.reason)}.`);
  for (const disease of report.diseases.filter(
    (item) => item.pairing === "use" && item.phenotypes_used === 0,
  ))
    reasons.push(
      `${disease.name} (${disease.gene}) fails the same way the drug pushes ${disease.gene}, but the catalog records no symptom in at least 30% of its cases.`,
    );
  return reasons;
}

function checkedClause(
  predictions: Prediction[],
  report: Report,
  unmapped: number,
): string {
  const checked = predictions.filter((prediction) =>
    wasChecked(prediction, Boolean(report.label)),
  ).length;
  const reports =
    report.drug_reports != null
      ? `${formatCount(report.drug_reports)} adverse-event reports`
      : "FAERS reports";
  if (!checked)
    return unmapped === predictions.length
      ? "; none could be checked yet, because step 5 has not mapped their symptoms to adverse-event terms"
      : "; none could be checked yet (see the problems below)";
  const against = `against the FDA label${report.label ? "" : " (none found)"} and ${reports} for the drug`;
  if (checked === predictions.length) return `, each checked ${against}`;
  return `; ${formatCount(checked)} of ${formatCount(predictions.length)} checked ${against}`;
}

function plainProblem(problem: string): string | null {
  if (/GEMINI_API_KEY/.test(problem)) {
    return "Symptoms were not mapped to adverse-event terms, because the Gemini API key is not set on the server.";
  }
  if (/^openFDA has no label/.test(problem))
    return "No FDA label was found, so no prediction can be on the label.";
  if (/^openFDA reports unavailable/.test(problem))
    return "FAERS could not be read, so report counts are missing.";
  if (/^ChEMBL has no molecule/.test(problem))
    return "ChEMBL does not know this name. Try the generic name.";
  return null;
}

export function ReportBody({
  report,
  source,
  onRefresh,
  refreshing,
  refreshError,
  monitoring,
}: {
  report: Report;
  source: "live" | "fixture";
  onRefresh?: () => void;
  refreshing: boolean;
  refreshError?: string | null;
  monitoring: Monitoring | null;
}) {
  const [filter, setFilter] = useState<Verdict | "all">("all");
  const predictions = useMemo(
    () => sortPredictions(report.predictions),
    [report.predictions],
  );
  const tally = verdictTally(predictions);
  const visible =
    filter === "all"
      ? predictions
      : predictions.filter((prediction) => prediction.verdict === filter);
  const molecule = report.molecule;
  const name = molecule?.name ?? report.query;
  const usedTargets = report.targets.filter((target) => target.used);
  const usedDiseases = report.diseases.filter(
    (disease) => disease.pairing === "use",
  );
  const unmapped = predictions.filter(
    (prediction) => prediction.reason === UNMAPPED,
  ).length;
  const candidates = predictions.filter(
    (prediction) => prediction.candidate_new_signal,
  ).length;
  const checkedCount = predictions.filter((prediction) =>
    wasChecked(prediction, Boolean(report.label)),
  ).length;
  const trend =
    monitoring?.trend.status === "ready" ? monitoring.trend.value : null;
  const alerts =
    monitoring?.alerts.status === "ready" ? monitoring.alerts.value.alerts : [];

  const unmappedSentence = `${unmapped} of ${predictions.length} predicted effects could not be checked against the label or the reports, so they show as unknown, which is never read as safe.`;
  const problems = report.problems.map((problem) => {
    const plain = plainProblem(problem);
    return {
      raw: problem,
      plain: plain && unmapped && problem.startsWith("Step 5") ? `${plain} ${unmappedSentence}` : plain,
    };
  });
  if (unmapped && !report.problems.some((problem) => problem.startsWith("Step 5"))) {
    problems.unshift({
      raw: `${unmapped} predictions: ${UNMAPPED}`,
      plain: `${unmapped} of ${predictions.length} symptoms are not mapped to adverse-event terms yet. ${unmappedSentence}`,
    });
  }

  if (!molecule) {
    return (
      <section>
        <div className="masthead">
          <div className="masthead-kicker">
            <span className="eyebrow">Side-effect report</span>
          </div>
          <h1 className="masthead-title">{report.query}</h1>
        </div>
        <div className="notice" role="alert">
          <h2>No molecule by that name</h2>
          {problems.map((problem) => (
            <p key={problem.raw}>{problem.plain ?? problem.raw}</p>
          ))}
        </div>
      </section>
    );
  }

  return (
    <article>
      <header className="masthead">
        <div className="masthead-kicker">
          <span className="eyebrow">Side-effect report</span>
          {source === "fixture" ? (
            <span className="fixture-tag">FIXTURE</span>
          ) : null}
        </div>
        <h1 className="masthead-title">{name}</h1>
        <p className="masthead-deck">
          {usedTargets.length && predictions.length ? (
            <>
              {name} <TargetPhrase targets={usedTargets} />.{" "}
              {usedDiseases.length === 1 ? (
                <>
                  The genetic disease where that protein fails the same way,{" "}
                  <b>{usedDiseases[0].name}</b>, gives{" "}
                  {pluralize(predictions.length, "predicted side effect")}
                </>
              ) : (
                <>
                  {pluralize(usedDiseases.length, "genetic disease")} where{" "}
                  {usedTargets.length === 1
                    ? "that protein fails"
                    : "these proteins fail"}{" "}
                  the same way give{" "}
                  {pluralize(predictions.length, "predicted side effect")}
                </>
              )}
              {checkedClause(predictions, report, unmapped)}.
            </>
          ) : report.targets.length ? (
            <>
              {name} acts on {list(report.targets.map((target) => target.name))}, but there is nothing to predict
              from: {emptyReasons(report).join(" ") || "no genetic disease of those proteins pairs with the drug's effect."}
            </>
          ) : (
            <>ChEMBL records no mechanism for {name} on a protein, so there is nothing to predict from.</>
          )}
        </p>

        <dl className="masthead-meta">
          <div className="meta-item">
            <dt>ChEMBL</dt>
            <dd>
              <a
                className="mono external"
                href={molecule.url}
                target="_blank"
                rel="noreferrer"
              >
                {molecule.chembl_id}
              </a>
            </dd>
          </div>
          {molecule.molecule_type ? (
            <div className="meta-item">
              <dt>Type</dt>
              <dd>
                {molecule.molecule_type}
                {molecule.max_phase === 4
                  ? ", approved"
                  : molecule.max_phase != null
                    ? `, phase ${molecule.max_phase}`
                    : ""}
              </dd>
            </div>
          ) : null}
          <div className="meta-item">
            <dt>FDA label</dt>
            <dd>
              {report.label ? (
                <a
                  className="external"
                  href={report.label.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Effective {formatDate(report.label.effective_time)}
                </a>
              ) : (
                "None found"
              )}
            </dd>
          </div>
          <div className="meta-item">
            <dt>FAERS reports</dt>
            <dd className="numeric">
              {formatCount(report.drug_reports)}
              {report.all_reports ? (
                <span style={{ color: "var(--ink-tertiary)" }}>
                  {" "}
                  of {formatCount(report.all_reports)}
                </span>
              ) : null}
            </dd>
          </div>
          {report.openfda_retrieved_at ? (
            <div className="meta-item">
              <dt>openFDA read</dt>
              <dd>
                <ClientTime value={report.openfda_retrieved_at} />
              </dd>
            </div>
          ) : null}
          <div className="meta-item">
            <dt>{report.cached_at ? "Stored" : "Generated"}</dt>
            <dd>
              <ClientTime value={report.cached_at ?? report.generated_at} />
            </dd>
          </div>
          {onRefresh ? (
            <div className="meta-actions">
              <button
                type="button"
                className="button"
                onClick={onRefresh}
                disabled={refreshing}
              >
                {refreshing ? "Running again" : "Run again"}
              </button>
            </div>
          ) : null}
        </dl>
        {refreshing ? (
          <div
            className="progress-line"
            role="progressbar"
            aria-label="Running the pipeline again"
          />
        ) : null}
        {refreshError && !refreshing ? (
          <p className="entry-reason" role="alert" style={{ marginTop: "var(--space-4)" }}>
            {refreshError}
          </p>
        ) : null}

        {problems.length ? (
          <section className="problems" aria-labelledby="problems-title">
            <h2 id="problems-title">
              {problems.length === 1
                ? "One problem in this run"
                : `${problems.length} problems in this run`}
            </h2>
            <ul>
              {problems.map((problem) => (
                <li key={problem.raw}>
                  {problem.plain ?? problem.raw}
                  {problem.plain ? (
                    <span className="raw">{problem.raw}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </header>

      <section className="section section-wide" aria-labelledby="chain-title">
        <div className="section-label">
          <span className="section-number">01</span>
          <h2 className="section-title" id="chain-title">
            The chain
          </h2>
          <p className="section-note">
            Each link is a public record. A drug that blocks a protein borrows
            only from diseases where that protein does too little; one that
            activates it, only from diseases where it does too much.
          </p>
        </div>
        <Chain report={report} predictions={predictions} />
      </section>

      <section className="section" aria-labelledby="effects-title">
        <div className="section-label">
          <span className="section-number">02</span>
          <h2 className="section-title" id="effects-title">
            Predicted side effects
          </h2>
          <p className="section-note">
            {pluralize(predictions.length, "prediction")}
            {candidates
              ? `, ${pluralize(candidates, "candidate new signal")}`
              : ""}
            .{" "}
            {checkedCount === predictions.length && predictions.length
              ? "Each is checked against the label word for word, then against FAERS with the Evans criteria."
              : predictions.length
                ? `${formatCount(checkedCount)} of ${formatCount(predictions.length)} checked so far. A mapped effect is checked against the label word for word, then against FAERS with the Evans criteria.`
                : ""}
          </p>
        </div>
        <div className="section-body">
          {predictions.length ? (
            <>
              <div
                className="ledger"
                role="group"
                aria-label="Filter by verdict"
              >
                <button
                  type="button"
                  className="ledger-item"
                  aria-pressed={filter === "all"}
                  onClick={() => setFilter("all")}
                >
                  All <span className="ledger-count">{predictions.length}</span>
                </button>
                {VERDICT_ORDER.map((verdict) => (
                  <button
                    key={verdict}
                    type="button"
                    className="ledger-item"
                    aria-pressed={filter === verdict}
                    disabled={!tally[verdict]}
                    onClick={() =>
                      setFilter(filter === verdict ? "all" : verdict)
                    }
                    title={VERDICTS[verdict].meaning}
                  >
                    <VerdictMark verdict={verdict} />
                    {VERDICTS[verdict].label}{" "}
                    <span className="ledger-count">{tally[verdict]}</span>
                  </button>
                ))}
              </div>
              <div className="entries">
                {visible
                  .filter((prediction) => prediction.reaction_terms.length)
                  .map((prediction) => (
                    <PredictionEntry
                      key={`${prediction.disease_id}-${prediction.hpo_id}`}
                      prediction={prediction}
                      report={report}
                      trend={trend}
                      alerts={alerts}
                    />
                  ))}
              </div>
              <Unchecked predictions={visible.filter((prediction) => !prediction.reaction_terms.length)} />
            </>
          ) : (
            <div className="empty-note">
              <p>No predictions.</p>
              <ul className="plain-list">
                {(emptyReasons(report).length
                  ? emptyReasons(report)
                  : ["No disease paired with the drug's effect."]
                ).map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      <MonitoringSection
        name={name}
        query={report.query}
        monitoring={monitoring}
        source={source}
        mappedTerms={predictions.flatMap((prediction) => prediction.reaction_terms)}
      />

      <section className="section" aria-labelledby="not-used-title">
        <div className="section-label">
          <span className="section-number">04</span>
          <h2 className="section-title" id="not-used-title">
            Set aside
          </h2>
          <p className="section-note">What the rules kept out, and why.</p>
        </div>
        <div className="section-body">
          <NotUsed report={report} />
        </div>
      </section>

      <section className="section" aria-labelledby="caveats-title" id="caveats">
        <div className="section-label">
          <span className="section-number">05</span>
          <h2 className="section-title" id="caveats-title">
            Read with care
          </h2>
          <p className="section-note">
            From the benchmark protocol, reported beside every number.
          </p>
        </div>
        <div className="section-body">
          <ol className="caveats">
            {CAVEATS.map((caveat) => (
              <li key={caveat.key}>
                <span>
                  <b>{caveat.short}</b> {caveat.text}
                </span>
              </li>
            ))}
          </ol>
          {report.generated_at ? (
            <p
              className="evidence-note"
              style={{ marginTop: "var(--space-6)" }}
            >
              Report generated{" "}
              <ClientTime value={report.generated_at} relative />.
            </p>
          ) : null}
        </div>
      </section>
    </article>
  );
}
