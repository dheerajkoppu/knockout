![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Knockout: drug side effects predicted from genetics

Ask about a drug, or about a kind of drug by the protein it blocks, and Knockout predicts its side effects from
the genetic diseases of the proteins it acts on. A drug that blocks a protein is a chemical knockout, so it should
cause a milder version of that protein's loss-of-function disease.

Every prediction comes with its chain and two checks:

- **Target:** ChEMBL mechanism (for example, eculizumab is an INHIBITOR of complement C5).
- **Genetic disease:** IUIS inborn errors of immunity catalog, with Orphanet phenotypes and their frequencies.
- **FDA label:** the sentence that names the effect, quoted verbatim from the openFDA label.
- **FDA adverse-event reports:** FAERS counts with the proportional reporting ratio (Evans criteria).

Verdicts: on the label, signal in reports (a candidate new signal when it is not on the label), no signal, or
unknown. Unknown is never shown as safe.

## Ask

- What side effects should a C5 blocker cause?
- Is eculizumab expected to cause infections?
- What does genetics predict for ibrutinib?
- Full report for eculizumab

The summary is free. The full report (every prediction, label quotes, report counts, sources, trend) is paid per
drug through the Agent Payment Protocol in FET.

The orchestrator calls four specialists: target-agent, genetics-agent, label-agent and signal-agent.

Research and drug-safety tool. Not medical advice.
