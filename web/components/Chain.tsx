import type { CSSProperties } from "react";

import {
  actionTypes,
  frequencyPhrase,
  DIRECTION_SOURCES,
  directionPhrase,
  predictionAnchor,
} from "@/lib/format";
import type { Disease, Prediction, Report, Target } from "@/lib/types";

import { VerdictMark } from "./VerdictMark";

const EFFECTS_SHOWN = 8;

type Branch = {
  target: Target;
  diseases: { disease: Disease; predictions: Prediction[] }[];
};

function place(row: number, span: number, column: number): CSSProperties {
  return { "--row": row, "--span": span, "--column": column } as CSSProperties;
}

function effectSentence(target: Target) {
  const types = actionTypes(target).toLowerCase();
  const kind = types.charAt(0).toUpperCase() + types.slice(1);
  if (target.effect === "lowers")
    return { kind, consequence: "lowers its activity" };
  if (target.effect === "raises")
    return { kind, consequence: "raises its activity" };
  return { kind, consequence: "effect unclear" };
}

export function Chain({
  report,
  predictions,
}: {
  report: Report;
  predictions: Prediction[];
}) {
  const molecule = report.molecule!;
  const branches: Branch[] = report.targets
    .filter((target) => target.used)
    .map((target) => ({
      target,
      diseases: report.diseases
        .filter(
          (disease) =>
            disease.gene === target.gene && disease.pairing === "use",
        )
        .map((disease) => ({
          disease,
          predictions: predictions.filter(
            (prediction) =>
              prediction.disease_id === disease.disease_id &&
              prediction.gene === disease.gene,
          ),
        })),
    }));

  if (!branches.length) {
    return (
      <div className="prose">
        <p>
          No protein this drug acts on leads to a genetic disease the rules can
          use.
        </p>
        <ul className="plain-list" style={{ marginTop: "var(--space-3)" }}>
          {report.targets.map((target) => (
            <li key={target.chembl_id}>
              <b>{target.name}</b>:{" "}
              {target.reason ?? "no disease pairs with the drug's effect"}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const totalRows = branches.reduce(
    (sum, branch) => sum + Math.max(branch.diseases.length, 1),
    0,
  );
  let row = 2;

  return (
    <div className="chain">
      <span className="chain-heading" style={{ gridColumn: 1, gridRow: 1 }}>
        Drug
      </span>
      <span className="chain-heading" style={{ gridColumn: 2, gridRow: 1 }}>
        Protein it acts on
      </span>
      <span className="chain-heading" style={{ gridColumn: 3, gridRow: 1 }}>
        Genetic disease, same direction
      </span>
      <span className="chain-heading" style={{ gridColumn: 4, gridRow: 1 }}>
        Predicted side effects
      </span>

      <div
        className="node node-drug node-desktop-place"
        style={place(2, totalRows, 1)}
      >
        <span className="node-role">Drug</span>
        <span className="node-title">{molecule.name}</span>
        <span className="node-meta">{molecule.chembl_id}</span>
        {molecule.molecule_type ? (
          <p className="node-relation">{molecule.molecule_type}</p>
        ) : null}
      </div>

      {branches.map((branch) => {
        const span = Math.max(branch.diseases.length, 1);
        const targetRow = row;
        row += span;
        const effect = effectSentence(branch.target);
        return [
          <div
            key={branch.target.chembl_id}
            className="node node-desktop-place"
            style={place(targetRow, span, 2)}
          >
            <span className="node-role">Protein it acts on</span>
            <span className="node-title">{branch.target.name}</span>
            <span className="node-meta">
              {[branch.target.gene, branch.target.accession]
                .filter(Boolean)
                .join(" · ")}
            </span>
            <p className="node-relation">
              <b>{effect.kind}</b>, so it {effect.consequence}
              <span className="node-source">ChEMBL mechanism</span>
            </p>
          </div>,
          ...branch.diseases.flatMap(
            ({ disease, predictions: diseasePredictions }, index) => [
              <div
                key={`${disease.disease_id}-disease`}
                className="node node-desktop-place"
                style={place(targetRow + index, 1, 3)}
                title={disease.direction_basis}
              >
                <span className="node-role">
                  Genetic disease, same direction
                </span>
                <span className="node-title">{disease.name}</span>
                <span className="node-meta">{disease.gene}</span>
                <p className="node-relation">
                  <b>
                    {directionPhrase(disease.direction).replace(
                      /^./,
                      (letter) => letter.toUpperCase(),
                    )}
                  </b>{" "}
                  of the protein
                  <span className="node-source">
                    Direction{" "}
                    {DIRECTION_SOURCES[disease.direction_source ?? ""] ??
                      "of unknown source"}
                  </span>
                </p>
              </div>,
              <div
                key={`${disease.disease_id}-effects`}
                className="node node-effects node-desktop-place"
                style={place(targetRow + index, 1, 4)}
              >
                <span className="node-role">Predicted side effects</span>
                {diseasePredictions.length ? (
                  <ul>
                    {diseasePredictions
                      .slice(0, EFFECTS_SHOWN)
                      .map((prediction) => (
                        <li key={prediction.hpo_id}>
                          <a
                            className="effect-link"
                            href={`#${predictionAnchor(prediction)}`}
                          >
                            <VerdictMark verdict={prediction.verdict} />
                            <span
                              className="effect-name"
                              data-verdict={prediction.verdict}
                            >
                              {prediction.phenotype}
                            </span>
                            <span className="effect-detail">
                              {frequencyPhrase(prediction.frequency)}
                            </span>
                          </a>
                        </li>
                      ))}
                    {diseasePredictions.length > EFFECTS_SHOWN ? (
                      <li className="effect-more">
                        <a href="#effects-title">
                          and {diseasePredictions.length - EFFECTS_SHOWN} more
                          below
                        </a>
                      </li>
                    ) : null}
                  </ul>
                ) : (
                  <p className="node-relation">
                    No symptom of this disease is frequent enough to use (at
                    least 30% of cases).
                  </p>
                )}
              </div>,
            ],
          ),
        ];
      })}
    </div>
  );
}
