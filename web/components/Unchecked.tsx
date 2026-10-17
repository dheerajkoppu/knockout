import { frequencyPhrase, predictionAnchor } from "@/lib/format";
import type { Prediction } from "@/lib/types";

import { reasonText } from "./PredictionEntry";
import { VerdictMark } from "./VerdictMark";

function groupReason(reason: string): string {
  if (reason === "phenotype not mapped yet (step 5)") {
    return "These symptoms have not been mapped to adverse-event terms (step 5), so there is nothing to look for in the label or the reports.";
  }
  if (reason === "no reaction term survived step 5") {
    return "None of the reaction terms proposed for these symptoms appears in any FAERS report.";
  }
  return reasonText(reason);
}

// Predictions with no reaction terms have nothing to check yet, so they are listed, not argued.
export function Unchecked({ predictions }: { predictions: Prediction[] }) {
  if (!predictions.length) return null;
  const groups = new Map<string, Prediction[]>();
  for (const prediction of predictions) {
    const reason = prediction.reason ?? "not checked";
    groups.set(reason, [...(groups.get(reason) ?? []), prediction]);
  }
  return (
    <div className="unchecked">
      {Array.from(groups, ([reason, members]) => {
        const diseases = Array.from(new Set(members.map((prediction) => prediction.disease)));
        const oneDisease = diseases.length === 1;
        return (
        <section key={reason} className="unchecked-group" aria-label={reasonText(reason)}>
          <h3 className="subsection-title">
            Not checked yet <span className="ledger-count">{members.length}</span>
          </h3>
          <p className="empty-note">
            {groupReason(reason)} Each counts as unknown, never as safe.
            {oneDisease ? ` All come from ${diseases[0]}.` : ""}
          </p>
          <div className="excluded-table-wrap">
            <table className="unchecked-table">
              <thead>
                <tr>
                  <th scope="col">Predicted effect</th>
                  {oneDisease ? null : <th scope="col" className="column-disease">From the disease</th>}
                  <th scope="col">Frequency</th>
                </tr>
              </thead>
              <tbody>
                {members.map((prediction) => {
                  const phenotypeRecord = prediction.records.find((record) =>
                    record.url?.includes(prediction.hpo_id),
                  );
                  return (
                    <tr key={`${prediction.disease_id}-${prediction.hpo_id}`} id={predictionAnchor(prediction)}>
                      <td>
                        <span className="unchecked-name">
                          <VerdictMark verdict={prediction.verdict} />
                          {prediction.phenotype}
                        </span>
                        {phenotypeRecord?.url ? (
                          <a className="mono unchecked-id" href={phenotypeRecord.url} target="_blank" rel="noreferrer">
                            {prediction.hpo_id}
                          </a>
                        ) : (
                          <span className="mono unchecked-id">{prediction.hpo_id}</span>
                        )}
                      </td>
                      {oneDisease ? null : <td className="column-disease">{prediction.disease}</td>}
                      <td className="numeric">{frequencyPhrase(prediction.frequency)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
        );
      })}
    </div>
  );
}
