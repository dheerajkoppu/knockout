import { DIRECTION_SOURCES, directionPhrase, effectVerb, frequencyPhrase, targetReason } from "@/lib/format";
import type { Disease, Report } from "@/lib/types";

function whyNot(disease: Disease, report: Report): string {
  const target = report.targets.find((item) => item.gene === disease.gene);
  const drug = report.molecule?.name ?? report.query;
  if (disease.pairing === "points_the_other_way" && target) {
    return `${drug} ${effectVerb(target.effect)} ${disease.gene}, but this disease comes from ${directionPhrase(disease.direction)}. A drug that pushes the protein the other way should not cause it.`;
  }
  if (disease.direction === "unknown") return `No source states its direction. ${disease.direction_basis}`;
  return `The drug's effect on ${disease.gene} is unknown, so no disease of it is used.`;
}

export function NotUsed({ report }: { report: Report }) {
  const diseases = report.diseases.filter((disease) => disease.pairing !== "use");
  const targets = report.targets.filter((target) => !target.used);
  const developmental = report.excluded_developmental;
  const infrequent = report.excluded_by_frequency ?? [];
  const diseaseNames = new Map(report.diseases.map((disease) => [disease.disease_id, disease.name]));
  // Step 5 classifies symptoms; until every prediction has a kind, a developmental one may still be in the list.
  const classified = report.predictions.every((prediction) => prediction.kind != null);

  if (!report.targets.length) {
    return <p className="empty-note">ChEMBL lists no protein this drug acts on, so nothing reached the rules.</p>;
  }

  const developmentalNote = classified ? (
    developmental.length ? null : (
      <p className="empty-note" style={{ marginTop: "var(--space-5)" }}>
        No symptom was developmental, so none was left out for that reason.
      </p>
    )
  ) : (
    <p className="empty-note" style={{ marginTop: "var(--space-5)" }}>
      Symptoms are not classified yet (step 5), so developmental ones, which a drug given after birth cannot cause,
      have not been removed from the predictions.
    </p>
  );

  return (
    <>
      {!diseases.length && !targets.length ? (
        <p className="empty-note" style={{ marginBottom: "var(--space-5)" }}>
          Every protein found leads to a disease that points the same way as the drug.
        </p>
      ) : null}
      {diseases.length ? (
        <div className="subsection">
          <h3 className="subsection-title">Diseases that point the other way, or have no known direction</h3>
          <div className="excluded-table-wrap">
            <table className="excluded-table">
              <thead>
                <tr>
                  <th scope="col">Disease</th>
                  <th scope="col">Its direction</th>
                  <th scope="col">Why it is not used</th>
                </tr>
              </thead>
              <tbody>
                {diseases.map((disease) => (
                  <tr key={`${disease.gene}-${disease.disease_id}`}>
                    <td>
                      {disease.name}
                      <span className="node-meta">{disease.gene}</span>
                    </td>
                    <td>
                      {directionPhrase(disease.direction)}
                      <span className="node-source">
                        {disease.direction_source ? DIRECTION_SOURCES[disease.direction_source] ?? disease.direction_source : "no source"}
                      </span>
                    </td>
                    <td className="why">{whyNot(disease, report)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {targets.length ? (
        <div className="subsection">
          <h3 className="subsection-title">Proteins not used</h3>
          <ul className="plain-list">
            {targets.map((target) => (
              <li key={target.chembl_id}>
                <b>{target.name}</b>
                {target.gene ? ` (${target.gene})` : ""}: {targetReason(target.reason)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {infrequent.length ? (
        <div className="subsection">
          <h3 className="subsection-title">Symptoms too rare in the catalog to use</h3>
          <p className="empty-note" style={{ marginBottom: "var(--space-3)" }}>
            Only symptoms seen in at least 30% of cases, or marked frequent, are predicted (step 4).
          </p>
          <ul className="plain-list">
            {infrequent.map((item) => (
              <li key={`${item.disease_id}-${item.hpo_id}`}>
                <b>{item.phenotype}</b> <span className="mono">{item.hpo_id}</span>,{" "}
                {item.frequency ? frequencyPhrase(item.frequency) : "no frequency recorded"}
                {diseaseNames.get(item.disease_id) ? ` (${diseaseNames.get(item.disease_id)})` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {developmentalNote}

      {developmental.length ? (
        <div className="subsection">
          <h3 className="subsection-title">Developmental symptoms left out</h3>
          <p className="empty-note" style={{ marginBottom: "var(--space-3)" }}>
            A drug given after birth cannot cause them.
          </p>
          <ul className="plain-list">
            {developmental.map((item) => (
              <li key={item.hpo_id}>
                <b>{item.phenotype}</b> <span className="mono">{item.hpo_id}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}
