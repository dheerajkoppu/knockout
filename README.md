# Knockout

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Predict a drug's side effects from the genetic diseases of the proteins it blocks.**

Every genetic disease shows what happens when a person lives without one working protein. A drug
that blocks that protein is a chemical knockout, so it should cause a milder version of the same
disease. Knockout finds what a drug acts on, finds the genetic diseases where that protein fails the
same way, predicts side effects from their symptoms, and checks every prediction against the FDA
label and FDA adverse-event reports.

Built at LA Hacks AI Hackathon 2026, 17–18 Oct, UCLA. Track: **Applied Intelligence**.

|                   | Link                          |
| ----------------- | ----------------------------- |
| Ask it in ASI:One | _fill in: ASI:One agent link_ |
| Report page       | _fill in: domain_             |
| Demo video (3:00) | _fill in_                     |
| Devpost           | _fill in_                     |

Knockout is a research and drug-safety tool. Nothing in it is medical advice, and a prediction is
a hypothesis built from public records.

---

## One example

| Step                | Record                                                                                          |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| The drug            | ChEMBL records eculizumab as an **inhibitor** of complement C5                                  |
| The genetic disease | C5 deficiency (IUIS classification); its name states that C5 does too little                    |
| Its symptom         | "Recurrent Neisseria meningitidis infection" (Orphanet)                                         |
| The label           | Boxed warning: "SERIOUS MENINGOCOCCAL INFECTIONS"                                               |
| The reports         | 86 FAERS reports pair eculizumab with meningococcal infection; proportional reporting ratio 146 |

## How it works

```
drug ──► targets and direction ──► genetic diseases that fail the same way ──► their symptoms
        (ChEMBL action type)       (direction rule: blocks ↔ loss of function,     │
                                    activates ↔ gain of function)                  ▼
                                                                  adverse-event terms
                                                                           │
                                     ┌─────────────────────────────────────┴───────────┐
                                     ▼                                                 ▼
                              FDA label check                              FDA adverse-event reports
                     (quote must appear verbatim)                    (PRR ≥ 2, ≥ 3 reports, χ² ≥ 4)
                                     └────────────────────┬────────────────────────────┘
                                                          ▼
                         on_label · signal_in_reports · no_signal · unknown
```

- **The direction rule is fixed.** A drug that blocks a protein maps only to that protein's
  loss-of-function diseases; a drug that activates one maps only to its gain-of-function diseases.
  The model never decides this.
- **Unknown is never safe.** Too few reports, or a source that failed, gives `unknown`.
- **No prediction without evidence.** A database trigger refuses to store a prediction that has no
  cited chain.
- **A candidate new signal** is a prediction found in the reports and absent from the label, shown
  with its genetic reason and its caveats.

## Built at LA Hacks

The hackathon rules allow open-source prior work when the new features are stated. Knockout uses
[Helix](https://github.com/dheerajkoppu/helix) (MIT), pinned to commit `97f3704` from 4 Oct 2026,
as a library.

| Reused from Helix                                                    | Built at LA Hacks                                                                                 |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| IUIS catalog of 604 diseases and 511 genes, with Orphanet phenotypes | Everything in this repository                                                                     |
| ChEMBL mechanism client                                              | The drug-first pipeline and the direction rule for side effects                                   |
| Gain or loss of function per gene                                    | Orphanet gain/loss-of-function data as a new direction source                                     |
| Action-type vocabulary (lowers, raises)                              | Symptom-to-reaction mapping, label check, FAERS signal detection                                  |
| Provenance records                                                   | Tiger Data store and evidence trigger, Fetch.ai agents, Creao watch agent, report page, benchmark |

## Measured results

_Not measured yet. The protocol in [`benchmark/PROTOCOL.md`](benchmark/PROTOCOL.md) was committed
before the first scoring run._

| Measure                                        | Result    | n         |
| ---------------------------------------------- | --------- | --------- |
| Predicted effects confirmed on the label       | _fill in_ | _fill in_ |
| Predicted effects with a signal in the reports | _fill in_ | _fill in_ |
| Lift over shuffled diseases (100 shuffles)     | _fill in_ | _fill in_ |
| Boxed warnings predicted                       | _fill in_ | _fill in_ |
| Candidate new signals                          | _fill in_ | _fill in_ |

## Agents

### Fetch.ai (Agentverse and ASI:One)

| Agent                   | Address   | Does                                                                                  |
| ----------------------- | --------- | ------------------------------------------------------------------------------------- |
| `knockout-orchestrator` | _fill in_ | Reads the request in ASI:One, calls the four specialists, returns an Interactive Card |
| `target-agent`          | _fill in_ | Drug to targets and direction                                                         |
| `genetics-agent`        | _fill in_ | Targets to genetic diseases and their symptoms                                        |
| `label-agent`           | _fill in_ | Checks the FDA label, with verbatim quotes                                            |
| `signal-agent`          | _fill in_ | Checks FDA adverse-event reports and trends                                           |

The full workflow runs inside an ASI:One chat. The summary is free; the full report is paid per
report through the Payment Protocol.

### Creao watch agent

- Agent ID: _fill in_
- Run: _fill in: share link to one run_

On a schedule, it pulls new adverse-event reports for every watched drug, recomputes each
prediction's signal and posts the changes to Knockout. The trend chart and the alerts run on its
output.

### Built with Devin

| Task                                  | Session   |
| ------------------------------------- | --------- |
| openFDA client with caching and tests | _fill in_ |
| Tiger Data migrations                 | _fill in_ |
| Benchmark report renderer             | _fill in_ |

## Sponsor challenges entered

| Challenge                         | How Knockout uses it                                                                    |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| Fetch.ai: ASI:One Agent Challenge | Five agents on Agentverse; the whole workflow in ASI:One; Payment Protocol              |
| Creao AI: Best AI-First Disruptor | The watch agent produces the monitoring the product shows                               |
| Paper: Best Designed Hack         | The report page, designed in Paper                                                      |
| Cognition: Best Use of Devin      | Three components built by Devin, sessions linked above                                  |
| Sentry                            | Tracing, Logs, AI agent monitoring and Session Replay; _fill in: the fix a trace found_ |
| MLH: Tiger Data                   | Reports as a time series, continuous aggregates, the evidence trigger                   |
| MLH: Gemini API                   | Symptom-to-reaction mapping and label quotes                                            |
| MLH: Vultr                        | Hosts the API and agents                                                                |
| MLH: GoDaddy Registry             | _fill in: domain_                                                                       |

## What is real and what is simulated

| Real      | Simulated |
| --------- | --------- |
| _fill in_ | _fill in_ |

## Verified, and not yet

**Verified:** _fill in_

**Not yet:** _fill in_

## Run it

_Fill in once the setup is final._

```bash
cp .env.example .env    # OPENFDA_API_KEY, GEMINI_API_KEY, TIGER_DATABASE_URL, SENTRY_DSN, AGENT_SEEDS
```

## Limits

- FAERS reports are voluntary and uneven, and a reaction can be under- or over-reported.
- A boxed warning raises reporting of the reaction it warns about, so a report signal for a labelled
  effect is partly circular.
- Patients on immune drugs have immune diseases, so an infection report can come from the disease
  rather than the drug.
- A lifelong genetic loss is stronger than partial inhibition by a drug, so predicted effects may be
  milder or absent.
- Developmental and congenital symptoms are excluded, because a drug given to an adult cannot
  cause them.
- A drug with no ChEMBL mechanism on a human protein gets no prediction.

## Data and licence

Code: MIT. Data keeps the terms of its source: ChEMBL, Orphanet, the Human Phenotype Ontology,
openFDA and the IUIS classification, each listed with its terms in `ATTRIBUTION.md`.
