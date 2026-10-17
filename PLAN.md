# Knockout: build plan for LA Hacks AI Hackathon 2026

Hacking runs Saturday 17 Oct 12:00 PDT to **Sunday 18 Oct 12:00 PDT**. Judging round 1 is 12:30,
round 2 is 14:00, in person in the Collins Conference Room. Team of four at most.

## The product in one paragraph

Every genetic disease shows what happens when a person lives without one working protein. A drug
that blocks that protein is a chemical knockout, so it should cause a milder version of the same
disease. Knockout takes a drug, finds the proteins it acts on and which way it pushes them, finds
the genetic diseases where that protein fails the same way, and predicts the drug's side effects
from those diseases' symptoms. It then checks every prediction against the FDA label and against
FDA adverse-event reports, and keeps checking as new reports arrive.

**Demo case, already verified on live data (17 Oct):**

- Helix's catalog lists "Recurrent Neisseria meningitidis infection" for C5 deficiency.
- ChEMBL records eculizumab as an INHIBITOR of complement C5.
- The eculizumab label's boxed warning is "SERIOUS MENINGOCOCCAL INFECTIONS".
- FAERS holds 86 reports pairing eculizumab with MENINGOCOCCAL INFECTION, out of 54,046
  eculizumab reports and 311 reports of that reaction across 20.7 million. The proportional
  reporting ratio is 146.

Second and third demo drugs: ibrutinib (ChEMBL: BTK INHIBITOR; BTK deficiency) and ruxolitinib
(JAK1 and JAK2). Tofacitinib gives no prediction, because ChEMBL files its target as a protein family and
the protocol uses single proteins only. Check both through the full pipeline before using them on stage.

## Where the code lives

A new public repository, `knockout`, with Helix installed as a dependency pinned to commit
`97f3704` (pushed 4 Oct 2026, before the event). Everything in the new repository is written at
LA Hacks. The rules allow open-source prior work if the new features are stated, and judges score
only those, so the README carries a "Built at LA Hacks" section listing what is new.

**Reused from Helix (built at Hack-Nation, 3 Oct):**

| What                                                                        | Where in Helix                                                            |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| IUIS catalog: 604 diseases, 511 genes, Orphanet phenotypes with frequencies | `helix.knowledge.catalog.load_catalog()`, `Catalog.diseases_for_gene()`   |
| Gain or loss of function per gene                                           | `helix.discovery.subject.resolve_mechanism()`                             |
| ChEMBL mechanisms for a drug                                                | `helix.services.compounds.compound_detail()`                              |
| Which way an action type pushes a protein                                   | `helix.discovery.rules.molecule_effect()` (`lowers`, `raises`, `unknown`) |
| Provenance and evidence records                                             | `helix.evidence`                                                          |
| Design system and fonts                                                     | `web/` (copy tokens, not pages)                                           |

**New at LA Hacks:** everything else in this plan.

## The engine

1. **Drug to targets.** ChEMBL mechanisms for the drug. Keep human protein targets only. Each
   target gets `lowers`, `raises` or `unknown` from `molecule_effect()`.
2. **Targets to diseases, with the direction rule.** A drug that lowers a protein maps to that
   protein's loss-of-function, haploinsufficiency or dominant-negative diseases. A drug that raises a
   protein maps to its gain-of-function diseases. Any other pairing is never used and is shown as
   "points the other way". `unknown` is never used.
3. **Better direction data.** Before step 2, add Orphanet product 6 as a direction source. Its
   gene associations say "loss of function" or "gain of function" for 78 catalog diseases, and the
   file is already cached at `data/.cache/orphadata_product6/en_product6.xml` in the Helix checkout.
   It resolves 10 of the 137 diseases Helix currently leaves unknown, including cystic fibrosis
   and APDS.
4. **Diseases to predicted effects.** Each disease phenotype that is Obligate, Very frequent or
   Frequent, or seen in at least 30% of reported cases. Drop developmental phenotypes, because a drug
   given after birth cannot cause them. Gemini tags each HPO term clinical, laboratory or
   developmental once; the tags are committed before any scoring.
5. **Effects to reaction terms.** Gemini maps each HPO term to up to five FAERS reaction terms
   (MedDRA preferred terms) in the same pass. The prompt never names a drug. A term is kept only if
   FAERS has at least one report with it across all drugs. Mappings are committed to
   `data/mappings/hpo.json` and scored runs read only that file.
6. **Check against the label.** openFDA label sections `boxed_warning`, `warnings_and_cautions`,
   `warnings`, `precautions`, `adverse_reactions`. A prediction is on the label when a sentence
   contains one of its reaction terms as a whole phrase, ignoring case and a plural ending. The
   sentence is kept verbatim. No model takes part in this step.
7. **Check against reports.** FAERS counts through openFDA. A signal is PRR ≥ 2 with at least 3
   reports and chi-squared ≥ 4 (the Evans criteria). Counts are stored per quarter for trends.
8. **Verdict per predicted effect.** One of four: `on_label`, `signal_in_reports`, `no_signal`,
   `unknown` (even a doubled reporting rate could not reach 3 reports, or a source failed).
   `unknown` is never shown as safe. A prediction with a report signal and no label mention is a
   **candidate new signal**, shown with its genetic reason and the caveats below.

## Measurement, frozen before any result is seen

Commit `benchmark/PROTOCOL.md` before the first scoring run. It fixes:

- **Drug set:** approved drugs (ChEMBL max phase 4) with an openFDA label, whose mechanism lowers
  a protein encoded by a catalog gene with a loss-of-function disease, plus any that raise a gene with
  a gain-of-function disease. The set is generated by script, never picked by hand.
- **Precision:** the share of predicted effects confirmed on the label, and separately the share
  confirmed in reports. Report the unflattering number first.
- **Null baseline:** run the same pipeline with each drug given the phenotypes of a randomly chosen
  loss-of-function disease (100 shuffles, fixed seed). The lift over the shuffle is the evidence that
  genetics adds information beyond "drugs cause common side effects".
- **Boxed-warning recall:** for drugs in the set that carry a boxed warning, how many warnings
  Knockout predicted.
- **Every miss and every false prediction classified** by a script, as in Helix's
  `classify_discovery_misses.py`.

**Caveats that go next to every number:** FAERS reports are voluntary and uneven. A boxed warning
itself increases reporting of the warned reaction, so report signals for labelled effects are partly
circular. Patients taking immune drugs have immune diseases, so infection reports may come from the
disease rather than the drug (confounding by indication). A lifelong genetic loss is stronger than
partial pharmacological inhibition, so effects should be milder or absent.

## Storage: Tiger Data

- `drugs`, `targets`, `predictions`, `evidence`, `watchlist`.
- `faers_counts` as a hypertable keyed by quarter, drug and reaction term, with a continuous
  aggregate for the trend chart.
- A deferred constraint trigger on `predictions`: a transaction that inserts a prediction with no
  `evidence` row fails at commit. No prediction can be stored without its cited chain.

## Agents: Fetch.ai

All on Agentverse, Chat Protocol on the orchestrator, README badges `innovationlab` and `hackathon`.

| Agent                   | Does                                                                                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `knockout-orchestrator` | Reads the user's intent in ASI:One ("what side effects should a C5 blocker cause?"), resolves the drug, calls the four specialists, returns an Interactive Card |
| `target-agent`          | Steps 1 and 2                                                                                                                                                   |
| `genetics-agent`        | Steps 3 to 5                                                                                                                                                    |
| `label-agent`           | Step 6                                                                                                                                                          |
| `signal-agent`          | Steps 7 and 8, reading trends from Tiger Data                                                                                                                   |

- **Payment Protocol:** the summary is free; the full report (every prediction, quotes, trend,
  export) is paid per report. Pitch: drug-safety teams pay for each drug they review.
- **Failure handling:** each specialist returns `unknown` with a reason when its source fails,
  and the orchestrator says which step failed. This counts for the reliability bonus.
- The complete workflow has to work inside an ASI:One chat with no other screen.

## Watch agent: Creao (Best AI-First Disruptor)

- Built on agent.creao.ai, scheduled.
- Each run, for every drug in `watchlist`: pull new FAERS counts, recompute the PRR for every stored
  prediction, and POST changes to `POST /webhooks/creao/signals`.
- The report page's trend chart and the "crossed the threshold since last run" alerts run on its
  output. Remove it and nothing is monitored.
- The openFDA key lives in Creao Secrets. Runs take minutes, so the UI shows the last run time and
  never waits on a run.
- README needs the agent ID and a share link to one run. Select the Creao track on Devpost.

## Web report page: Paper (Best Designed Hack)

- Design in Paper first (free Pro for teams), then build in Next.js with Helix's tokens.
- One page per drug: the chain drug → protein → disease → effect, verdict badges, the label quote,
  the PRR with its counts, the trend from the watch agent, and the caveats.
- Judged on hierarchy, legibility, consistency, contrast, ease of use and personal craft. Hand-set
  type and spacing; no default component-library look.

## Small integrations

| Sponsor                 | Exactly what                                                                                                                                                                                                          | Owner  |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Sentry                  | Python SDK with Tracing and Logs on the API and agents, AI agent monitoring on Gemini calls, Session Replay on the web page. Keep one screenshot of a trace that found a slow openFDA call and the cache added for it | Ops    |
| Tiger Data (MLH)        | The storage above                                                                                                                                                                                                     | Engine |
| Gemini API (MLH)        | Steps 4 and 5                                                                                                                                                                                                          | Engine |
| Vultr (MLH)             | One VM running the API and agents with Docker Compose                                                                                                                                                                 | Ops    |
| GoDaddy Registry (MLH)  | Register the domain                                                                                                                                                                                                   | Design |
| Devin                   | Three bounded tasks: the openFDA client with caching and tests, the Tiger Data migrations, the benchmark report renderer. Keep the session links                                                                      | Design |
| Commit Fellowship (MLH) | Opt in on Devpost and submit the supplemental form                                                                                                                                                                    | Design |

**Stretch, in this order, only with spare hands:** veri.studio fine-tune of a small model for
step 5, compared with Gemini on held-out pairs ($800); Step 5 Preview for one step (StepFun); a Photon
text to the safety team when a signal crosses the threshold. Ask at the StepFun and Photon booths
how they are judged; neither prize is listed.

## Who does what

| Person | Workstream                                                                  | Done when                                                                               |
| ------ | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| A      | Engine and Tiger Data: steps 1 to 8, storage, evidence trigger, benchmark   | `knockout predict eculizumab` prints meningococcal infection with a label quote and PRR |
| B      | Fetch.ai: five agents, Interactive Card, Payment Protocol, Submission Agent | The same answer appears in an ASI:One chat                                              |
| C      | Creao watch agent, webhook, Sentry, Vultr deploy                            | A scheduled run updates the trend in Tiger Data                                         |
| D      | Paper design, report page, video, Devpost, README, domain, Devin tasks      | The report page renders eculizumab from the live API                                    |

## Timeline (PDT)

| When            | What                                                                                                                                                                                                                                             |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sat 13:30–14:30 | Accounts and keys: openFDA API key, Agentverse and ASI:One (codes `LAHACKSAI26`, `LAHACKSAI26AV`), Creao via the hackathon signup link, Tiger Data, Vultr credits, Sentry, Gemini, Devin, Paper. Create the repo. Commit `benchmark/PROTOCOL.md` |
| Sat 14:30–20:00 | Each workstream reaches its "done when" for eculizumab                                                                                                                                                                                           |
| **Sat 20:00**   | **Checkpoint 1:** eculizumab end to end in ASI:One                                                                                                                                                                                               |
| Sat 20:00–01:00 | Ibrutinib and ruxolitinib through the pipeline. First full benchmark run. Watch agent live. Payment Protocol and Interactive Card. Report page built from the Paper design                                                                       |
| **Sun 01:00**   | **Checkpoint 2:** benchmark numbers in the README                                                                                                                                                                                                |
| Sun 01:00–07:00 | Sleep in shifts. One person on error handling, retries and the Sentry fix                                                                                                                                                                        |
| Sun 07:00–09:30 | Polish. **Feature freeze at 09:30**                                                                                                                                                                                                              |
| Sun 09:30–11:15 | Record the 3:00 video. Devpost page, README, Fetch.ai Submission Agent, Creao track, Commit form                                                                                                                                                 |
| Sun 11:30       | Submitted. The remaining 30 minutes are buffer                                                                                                                                                                                                   |
| Sun 12:30       | Judging round 1, in person                                                                                                                                                                                                                       |

**If behind, cut in this order:** veri.studio fine-tune, Payment Protocol, the trend chart (keep
the watch agent run), the domain, the Interactive Card (fall back to a text table).

## Submission checklist

- [ ] Devpost: description naming **Applied Intelligence** as the track and explaining how the
      project fits each company challenge entered; tracks selected: Fetch.ai, Creao (AI-First
      Disruptor), Paper, Devin, Sentry, MLH Tiger Data, Gemini, Vultr, GoDaddy, Commit Fellowship
- [ ] Video exactly **3:00** (Devpost asks 2–3 minutes, Fetch.ai asks 3–5)
- [ ] Public GitHub repository with run instructions
- [ ] README: "Built at LA Hacks" section, agent names and addresses, Fetch.ai badges, Creao agent
      ID and run link, what is real and what is simulated, measured results
- [ ] Fetch.ai Submission Agent on ASI:One
- [ ] Commit Fellowship supplemental form
- [ ] Every team member present for judging at 12:30

## Video, 3:00

| Time | Beat                                                                                                                    |
| ---- | ----------------------------------------------------------------------------------------------------------------------- |
| 0:00 | Hook: C5 deficiency causes meningococcal infections; eculizumab blocks C5; its boxed warning is meningococcal infection |
| 0:20 | ASI:One: ask about a C5 blocker, the agents run, the card returns the prediction with its chain                         |
| 1:10 | Report page: the cited chain, the label quote, PRR 146 from 86 reports                                                  |
| 1:40 | The benchmark: precision on the label first, then lift over the shuffled baseline                                       |
| 2:10 | One candidate signal that is in the reports and not on the label, with its caveats                                      |
| 2:30 | The watch agent's last run updating a trend                                                                             |
| 2:45 | What is new at LA Hacks, the limits, close: "Every genetic disease already ran the trial."                              |

The file must be exactly 3:00: Devpost allows 2 to 3 minutes and Fetch.ai asks for 3 to 5, so 180 s is
the only length that meets both. Check with `ffprobe -v error -show_entries format=duration -of csv=p=0 video.mp4`
(it must print 180.0). Record from the live path once step 5 runs. If the benchmark is still missing at
the 09:30 freeze, replace 1:40 with "protocol frozen, scoring pending" on screen and 2:10 with the
watch agent's trend. If the fixture is used, the FIXTURE tag must be visible and said aloud.

## Known risks

- openFDA allows 240 requests a minute with a key. Cache every response in Tiger Data and pre-warm the
  demo drugs.
- FAERS reaction terms split one effect across several terms (meningococcal infection, meningococcal
  sepsis, meningitis meningococcal). Group terms per prediction and show the group.
- The name "Knockout" is generic. Check the domain before the video is recorded.
