"use client";

import { useState } from "react";

import { caveatsFor } from "@/lib/caveats";
import {
  countRatio,
  directionPhrase,
  effectVerb,
  formatAgainst,
  formatChiSquared,
  formatCount,
  formatDate,
  formatExpected,
  formatRatio,
  frequencySentence,
  predictionAnchor,
  SECTION_NAMES,
  strongestCount,
} from "@/lib/format";
import type { Alert, Prediction, Report, TermCount, Trend } from "@/lib/types";

import { TrendChart } from "./TrendChart";
import { VerdictTag } from "./VerdictMark";

const SOURCE_NAMES: Record<string, string> = {
  chembl: "ChEMBL",
  iuis_2024: "IUIS 2024",
  mondo: "Mondo",
  mondo_sssom_omim: "Mondo to OMIM",
  gencc: "GenCC",
  hpo_annotations: "HPO annotations",
  hpo_ontology: "HPO",
  disease_name: "Disease name",
  iuis: "IUIS",
  orphanet: "Orphanet",
  openfda_label: "FDA label",
};

export function PredictionEntry({
  prediction,
  report,
  trend,
  alerts,
}: {
  prediction: Prediction;
  report: Report;
  trend: Trend | null;
  alerts: Alert[];
}) {
  const drugName = report.molecule?.name ?? report.query;
  const target = report.targets.find(
    (item) => item.name === prediction.target && item.gene === prediction.gene,
  );
  const disease = report.diseases.find(
    (item) =>
      item.disease_id === prediction.disease_id &&
      item.gene === prediction.gene,
  );
  const checked = prediction.reaction_terms.length > 0;
  const caveats = caveatsFor(prediction);

  return (
    <article
      className={checked ? "entry" : "entry entry-compact"}
      id={predictionAnchor(prediction)}
    >
      <header>
        <div className="entry-tags">
          <VerdictTag verdict={prediction.verdict} />
          {prediction.candidate_new_signal ? (
            <span className="candidate-tag">Candidate new signal</span>
          ) : null}
          {prediction.kind ? (
            <span className="kind-tag">{prediction.kind}</span>
          ) : null}
        </div>
        <h3 className="entry-title">
          {prediction.phenotype}
          <span className="mono">{prediction.hpo_id}</span>
        </h3>
        <p className="entry-why">
          {drugName} {effectVerb(target?.effect ?? "unknown")}{" "}
          {prediction.target}. In <b>{prediction.disease}</b> the same protein
          has {directionPhrase(disease?.direction ?? "unknown")}, and{" "}
          {frequencySentence(prediction.frequency)}.
        </p>
        {prediction.reason ? (
          <p className="entry-reason">{reasonText(prediction.reason)}</p>
        ) : null}
        {prediction.candidate_new_signal ? (
          <p className="candidate-note">
            The reports carry a signal the label does not mention. This is a
            hypothesis to review, with the genetic reason above and the cautions
            below, not a finding.
          </p>
        ) : null}
      </header>

      {checked ? (
        <>
          <section className="evidence-block" aria-label="Reaction terms">
            <h4>
              Reaction terms
              <small>MedDRA, as FAERS records them</small>
            </h4>
            <div className="terms">
              {prediction.reaction_terms.map((term) => (
                <span className="term" key={term}>
                  {term}
                </span>
              ))}
            </div>
          </section>

          <section className="evidence-block" aria-label="FDA label">
            <h4>
              FDA label
              <small>Word for word, no model</small>
            </h4>
            <LabelEvidence prediction={prediction} report={report} />
          </section>

          <section
            className="evidence-block"
            aria-label="Adverse-event reports"
          >
            <h4>
              Adverse-event reports
              <small>FAERS, through openFDA</small>
            </h4>
            <ReportEvidence
              prediction={prediction}
              drugName={drugName}
              trend={trend}
              alerts={alerts}
            />
          </section>
        </>
      ) : null}

      <footer className="entry-foot">
        <span className="foot-label">
          {checked ? "Read with care" : "Sources"}
        </span>
        <div>
          {checked ? (
            <ul className="care">
              {caveats.map((caveat) => (
                <li key={caveat.key} title={caveat.text}>
                  {caveat.short}
                </li>
              ))}
              <li className="care-more">
                <a href="#caveats">Each caution in full</a>
              </li>
            </ul>
          ) : null}
          <details
            className="sources"
            style={checked ? { marginTop: "var(--space-4)" } : undefined}
          >
            <summary>
              {prediction.records.length} records behind this prediction
            </summary>
            <ol>
              {prediction.records.map((record, index) => (
                <li key={`${record.source}-${index}`}>
                  <span className="source-name">
                    {SOURCE_NAMES[record.source] ?? record.source}
                  </span>
                  <span className="source-description">
                    {record.url ? (
                      <a
                        href={record.url}
                        target="_blank"
                        rel="noreferrer"
                        className="external"
                      >
                        {record.description}
                      </a>
                    ) : (
                      record.description
                    )}
                  </span>
                </li>
              ))}
            </ol>
          </details>
        </div>
      </footer>
    </article>
  );
}

export function reasonText(reason: string): string {
  if (reason === "phenotype not mapped yet (step 5)") {
    return "Not checked yet: this symptom has not been mapped to adverse-event terms (step 5).";
  }
  if (reason === "no reaction term survived step 5") {
    return "Not checked: none of the proposed reaction terms appears in any FAERS report.";
  }
  if (reason === "too few reports for even a doubled rate to show") {
    return "Too few reports: even a doubled reporting rate could not reach 3 reports.";
  }
  if (reason.startsWith("openFDA reports unavailable")) {
    return "Not checked against the reports: openFDA did not answer, so no count was made. This is a source failure, not a result.";
  }
  return reason.charAt(0).toUpperCase() + reason.slice(1);
}

function highlight(sentence: string, term: string | null) {
  if (!term) return sentence;
  const words = term
    .toLowerCase()
    .split(/\s+/)
    .map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  words[words.length - 1] += "(?:e?s)?";
  const match = new RegExp(`\\b${words.join("\\s+")}\\b`, "i").exec(sentence);
  if (!match) return sentence;
  return (
    <>
      {sentence.slice(0, match.index)}
      <mark>{match[0]}</mark>
      {sentence.slice(match.index + match[0].length)}
    </>
  );
}

function LabelEvidence({
  prediction,
  report,
}: {
  prediction: Prediction;
  report: Report;
}) {
  if (!report.label)
    return <p className="empty-note">openFDA holds no label for this drug.</p>;
  const sections = report.label.sections.map(
    (section) => SECTION_NAMES[section] ?? section,
  );
  if (!prediction.label_sentence || !prediction.label_section) {
    return (
      <p className="empty-note">
        No sentence in the {sections.join(", ").toLowerCase() || "label"} names{" "}
        {prediction.reaction_terms.length === 1
          ? "this term"
          : "any of these terms"}
        .
      </p>
    );
  }
  return (
    <figure className="label-quote" data-section={prediction.label_section}>
      <figcaption>
        <span className="label-section">
          {SECTION_NAMES[prediction.label_section] ?? prediction.label_section}
        </span>
        <span>
          Label effective {formatDate(report.label.effective_time)} ·{" "}
          <a
            href={report.label.url}
            target="_blank"
            rel="noreferrer"
            className="external"
          >
            DailyMed
          </a>
        </span>
      </figcaption>
      <blockquote>
        {highlight(prediction.label_sentence, prediction.label_term)}
      </blockquote>
    </figure>
  );
}

function ReportEvidence({
  prediction,
  drugName,
  trend,
  alerts,
}: {
  prediction: Prediction;
  drugName: string;
  trend: Trend | null;
  alerts: Alert[];
}) {
  const strongest = strongestCount(prediction.counts);
  const [selectedTerm, setSelectedTerm] = useState(strongest?.term);
  if (!strongest) {
    return (
      <p className="empty-note">
        {prediction.reason
          ? reasonText(prediction.reason)
          : "No counts were returned."}
      </p>
    );
  }
  const selected =
    prediction.counts.find((count) => count.term === selectedTerm) ?? strongest;
  const termTrends =
    trend?.terms.filter((item) =>
      prediction.reaction_terms.some(
        (term) => term.toUpperCase() === item.term.toUpperCase(),
      ),
    ) ?? [];

  return (
    <div>
      {prediction.counts.length > 1 ? (
        <div className="term-table-wrap">
          <table className="term-table">
            <caption className="visually-hidden">
              Report counts per reaction term
            </caption>
            <thead>
              <tr>
                <th scope="col">Term</th>
                <th scope="col">Reports</th>
                <th scope="col">Expected</th>
                <th scope="col">PRR</th>
                <th scope="col">χ²</th>
                <th scope="col">Signal</th>
              </tr>
            </thead>
            <tbody>
              {prediction.counts.map((count) => (
                <tr
                  key={count.term}
                  aria-selected={count.term === selected.term}
                  onClick={() => setSelectedTerm(count.term)}
                >
                  <td>
                    <button
                      type="button"
                      className="mono"
                      onClick={() => setSelectedTerm(count.term)}
                      style={{
                        all: "unset",
                        cursor: "pointer",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {count.term}
                    </button>
                  </td>
                  <td>{formatCount(count.a)}</td>
                  <td>{formatExpected(count.expected)}</td>
                  <td>{formatRatio(countRatio(count))}</td>
                  <td>{formatChiSquared(count.chi_squared)}</td>
                  <td className={count.signal ? "signal-yes" : undefined}>
                    {count.signal ? "Yes" : "No"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <Statistic count={selected} drugName={drugName} />
      <TwoByTwo count={selected} drugName={drugName} />

      {termTrends.length ? (
        <div className="inline-trend">
          {termTrends.map((item) => (
            <TrendChart
              key={item.term}
              term={item.term}
              quarters={item.quarters}
              alertQuarters={alerts
                .filter((alert) => alert.term === item.term)
                .map((alert) => alert.quarter)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function TwoByTwo({ count, drugName }: { count: TermCount; drugName: string }) {
  const other = count.drug - count.a;
  const reactionElsewhere = count.reaction - count.a;
  const rest = count.all - count.drug - reactionElsewhere;
  return (
    <div className="two-by-two-wrap">
      <table className="two-by-two">
        <caption>
          Reports naming <span className="mono">{count.term}</span>
        </caption>
        <thead>
          <tr>
            <th scope="col">
              <span className="visually-hidden">Drug</span>
            </th>
            <th scope="col">This reaction</th>
            <th scope="col">Any other</th>
            <th scope="col">Total</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">{drugName}</th>
            <td className="cell-a">
              <span className="cell-letter">a</span>
              {formatCount(count.a)}
            </td>
            <td>
              <span className="cell-letter">b</span>
              {formatCount(other)}
            </td>
            <td>{formatCount(count.drug)}</td>
          </tr>
          <tr>
            <th scope="row">Other drugs</th>
            <td>
              <span className="cell-letter">c</span>
              {formatCount(reactionElsewhere)}
            </td>
            <td>
              <span className="cell-letter">d</span>
              {formatCount(rest)}
            </td>
            <td>{formatCount(count.all - count.drug)}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">All reports</th>
            <td>{formatCount(count.reaction)}</td>
            <td>{formatCount(count.all - count.reaction)}</td>
            <td>{formatCount(count.all)}</td>
          </tr>
        </tfoot>
      </table>
      <div className="two-by-two-notes">
        <p className="formula">
          <span>PRR = (a ÷ (a + b)) ÷ (c ÷ (c + d))</span>{" "}
          <span>
            = ({formatCount(count.a)} ÷ {formatCount(count.drug)}) ÷ ({formatCount(count.reaction - count.a)} ÷{" "}
            {formatCount(count.all - count.drug)})
          </span>
        </p>
        <a className="query-link external" href={count.query} target="_blank" rel="noreferrer">
          Count a on openFDA
        </a>
      </div>
    </div>
  );
}

function Statistic({ count, drugName }: { count: TermCount; drugName: string }) {
  const ratio = countRatio(count);
  const criteria = [
    { label: "At least 3 reports", met: count.a >= 3, value: `a = ${formatCount(count.a)}` },
    { label: "PRR at least 2", met: (ratio ?? 0) >= 2, value: formatAgainst(ratio, 2) },
    { label: "χ² at least 4", met: count.chi_squared >= 4, value: formatAgainst(count.chi_squared, 4, formatChiSquared) },
  ];
  return (
    <div className="statistic">
      <div>
        <div className="statistic-headline">
          <span className="statistic-value numeric" data-signal={count.signal}>
            {formatRatio(ratio)}
          </span>
          <span className="statistic-name">
            Proportional
            <br />
            reporting ratio
          </span>
        </div>
        <p className="statistic-gloss">
          {ratio == null
            ? "The ratio is undefined for these counts."
            : ratio >= 1
              ? `${drugName} reports name this reaction ${formatRatio(ratio)} times as often as reports for every other drug.`
              : `${drugName} reports name this reaction less often than reports for every other drug.`}{" "}
          {formatExpected(count.expected)} {count.expected === 1 ? "report" : "reports"} would be expected if the two
          were unrelated.
        </p>
      </div>
      <div>
        <p className="foot-label criteria-title">Evans criteria {count.signal ? "met" : "not met"}</p>
        <ul className="criteria">
          {criteria.map((criterion) => (
            <li key={criterion.label} data-met={criterion.met}>
              <span className="criterion-mark" aria-hidden="true">
                {criterion.met ? "✓" : "–"}
              </span>
              <span>
                {criterion.label}
                <span className="visually-hidden">{criterion.met ? ", met" : ", not met"}</span>
              </span>
              <span className="criterion-value">{criterion.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
