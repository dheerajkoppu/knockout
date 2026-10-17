import { DrugSearch } from "@/components/DrugSearch";
import { RunningHeader } from "@/components/RunningHeader";

const EXAMPLE = [
  {
    role: "The drug",
    text: "Eculizumab is an inhibitor of complement C5.",
    source: "ChEMBL CHEMBL1201828, mechanism record",
  },
  {
    role: "The genetic disease",
    text: "People born without working C5 have C5 deficiency.",
    source: "IUIS classification, through the Helix catalog",
  },
  {
    role: "Its symptom, the prediction",
    text: "Recurrent Neisseria meningitidis infection, in 2 of 2 reported cases.",
    source: "HPO annotations (OMIM:609536), HP:0005381",
  },
  {
    role: "What the record says",
    text: "The label's boxed warning: “SERIOUS MENINGOCOCCAL INFECTIONS”. 86 FAERS reports, PRR 146.",
    source: "openFDA label and adverse-event reports",
  },
];

export default function Home() {
  return (
    <>
      <RunningHeader />
      <main>
        <div className="page home">
          <p className="home-kicker">Side effects, read from genetics</p>
          <h1 className="home-title">
            Predict a drug’s side effects from the genetic diseases of the proteins it <em>blocks</em>.
          </h1>
          <p className="home-lede">
            A drug that blocks a protein is a chemical knockout, so it should cause a milder version of that
            protein’s loss-of-function disease. Knockout checks each prediction against the FDA label and FDA
            adverse-event reports.
          </p>
          <DrugSearch />

          <section className="worked-example" aria-labelledby="worked-example-title">
            <div className="worked-example-head">
              <h2 className="eyebrow" id="worked-example-title">
                One prediction, from public records
              </h2>
              <p>Checked by hand against live records, 17 Oct 2026</p>
            </div>
            <ol className="example-steps">
              {EXAMPLE.map((step) => (
                <li className="example-step" key={step.role}>
                  <span className="example-step-role">{step.role}</span>
                  <p className="example-step-text">{step.text}</p>
                  <p className="example-step-source">{step.source}</p>
                </li>
              ))}
            </ol>
            <p className="example-closing">Every genetic disease already ran the trial.</p>
          </section>
        </div>
      </main>
    </>
  );
}
