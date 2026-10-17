# Knockout: Devpost submission text

Every field below is ready to paste into the Devpost form at la-ai-hackathon-2026.devpost.com.
Numbers come from live records read on 17 Oct 2026; the source of each is in `README.md`.

**Before pasting:**

1. Replace every _fill in_ with the real value, or delete the sentence that holds it. Never paste a
   _fill in_ and never guess a number.
2. Pick one of the two "Where it stands" paragraphs under "What it does": **A** if step 5 (the Gemini
   mapping) has run and you have seen the engine's own eculizumab verdict, **B** if it has not.
3. Delete the paragraph of any company challenge whose work is not done (see `SUBMISSION.md`), and
   do not select that challenge on Devpost.

---

## Project name

Knockout

## Elevator pitch (tagline)

Knockout predicts a drug's side effects from the genetic diseases of the proteins it blocks, then
checks each prediction against the FDA label and FDA adverse-event reports.

## Track

Applied Intelligence

---

## Inspiration

Some people are born without one working protein. Their genetic disease shows, over a lifetime,
what the human body does when that protein is missing. Many drugs work by blocking one protein on
purpose. So a drug that blocks a protein should cause a milder version of that protein's genetic
disease.

The clearest case we know: eculizumab blocks complement C5. People born without working C5 get
repeated meningococcal infections. The eculizumab label carries a boxed warning, the FDA's strongest,
for serious meningococcal infections. The genetic disease points straight at the warning.

We wanted a program that does this for any drug, shows every link in the chain as a public record,
and keeps checking each prediction as new adverse-event reports reach the FDA. Two weeks earlier,
at Hack-Nation, one of us had built Helix, a catalog of 604 inherited immune diseases and 511 genes
with their symptoms. Knockout uses it as a library and builds everything else new.

## What it does

You give Knockout a drug, or ask a question like "What side effects should a C5 blocker cause?".

1. It reads the drug's targets from ChEMBL and which way the drug pushes each one: an inhibitor
   lowers a protein's activity, an activator raises it.
2. It finds the genetic diseases of each target that fail **the same way**. A drug that lowers a
   protein is matched only with diseases where that protein does too little. This rule is fixed
   code; no model decides it.
3. It takes the symptoms those diseases show often (marked frequent, or seen in at least 30% of
   reported cases) and predicts them as side effects.
4. Gemini translates each symptom from the vocabulary geneticists use (the Human Phenotype
   Ontology) into the terms the FDA's adverse-event database uses. The model never sees the drug.
5. It looks for each predicted effect in the FDA label and quotes the sentence word for word. No
   model takes part in this step.
6. It counts FDA adverse-event reports (FAERS) and computes how much more often the effect is
   reported with this drug than with all other drugs (the proportional reporting ratio, PRR), with a
   standard test for whether that is a signal.
7. Each prediction gets one of four verdicts: on the label, signal in the reports, no signal, or
   unknown. Unknown is never shown as safe. A prediction found in the reports but missing from the
   label is a candidate new signal, shown with its genetic reason and its caveats.

**For eculizumab**, the records line up:

- ChEMBL records eculizumab (CHEMBL1201828) as an inhibitor of complement C5.
- The catalog lists C5 deficiency with "Recurrent Neisseria meningitidis infection" in 2 of 2
  reported cases (HP:0005381).
- The label's boxed warning reads "SERIOUS MENINGOCOCCAL INFECTIONS".
- 86 of 54,046 eculizumab reports in FAERS name meningococcal infection, against 311 of 20,692,690
  reports for all drugs: a PRR of 146.

**Where it stands (A, if step 5 has run):** Knockout reaches this result by itself: the
meningococcal prediction comes out _fill in: verdict_ with the boxed-warning sentence and a PRR of
_fill in_ from _fill in_ reports. Across the 52-drug benchmark, _fill in: label precision first,
then report precision and the lift over shuffled diseases, each with its n_.

**Where it stands (B, if step 5 has not run):** The engine builds the chain from drug to disease
to symptom by itself on live data. We checked the label quote and the report counts by hand with
the engine's own matching and counting code, giving it the term "MENINGOCOCCAL INFECTION" ourselves.
Until Gemini maps the symptoms, the engine reports every prediction as unknown, and the benchmark
has no number yet. We left it that way rather than fill the gap by hand.

**Where you use it:**

- **In an ASI:One chat**, through five Fetch.ai agents. The summary is free; the full report with
  every quote and count is paid per report through the Payment Protocol.
- **On the report page**: the chain, the verdicts, the label quote, the counts behind each PRR, the
  watch agent's per-quarter trend, what the rules set aside, and the caveats.
- **Through the API**, which a scheduled Creao agent feeds with fresh FAERS counts. Remove that
  agent and nothing is monitored.

## How we built it

- **Engine (Python):** a ChEMBL client for drugs, mechanisms and targets; Helix's IUIS catalog
  for diseases and symptoms; Orphanet product 6 as a new source of "loss of function" or "gain of
  function" per disease; the fixed direction rule; a frequency filter (symptoms in at least 30% of
  cases); Gemini at temperature 0 with a JSON schema for the symptom-to-reaction mapping, saved to a
  committed file that scored runs read; openFDA for the label and the FAERS totals; a plain
  whole-phrase label match; PRR, Yates chi-squared and the Evans criteria for signals.
- **Measurement first:** we wrote and committed the benchmark protocol before any measure was
  computed. It fixes the drug set (generated by script: 52 approved drugs whose mechanism matches a
  catalog disease's direction and that have an FDA label), the measures (label precision reported
  first), a baseline that gives each drug the symptoms of random unrelated diseases 100 times, and
  the caveats printed beside every number. When a review found gaps, we wrote version 2 with every
  change and its reason, still before any measure.
- **API and store:** FastAPI. Tiger Data (TimescaleDB) stores the reports, the predictions and
  their evidence, with FAERS counts as a hypertable, the trend as a continuous aggregate, and a
  deferred trigger that refuses to commit a prediction with no evidence row. A JSON file store with
  the same interface runs when no database is set.
- **Agents:** five Fetch.ai uAgents. The orchestrator speaks the Chat Protocol and the Payment
  Protocol, resolves a drug or a protein through ChEMBL and UniProt, asks four specialists in
  parallel and returns an Interactive Card. They call the API, so they run on Python 3.12 while the
  engine runs on 3.14.
- **Watch agent:** a Creao agent runs our watch script on a schedule, counts FAERS reports quarter
  by quarter for every watched prediction, and posts the results to the API's webhook.
- **Report page:** Next.js and TypeScript with hand-written CSS and IBM Plex type, checked at 1440
  px and 390 px in light and dark.
- **Operations:** Sentry for tracing, logs, AI agent monitoring of the Gemini calls and Session
  Replay; Docker Compose on Vultr with Caddy for HTTPS; Vercel for the page.
- **Checks:** 122 Python tests, one of them against live openFDA (133 with a database), 22 agent
  tests, ruff, a TypeScript type-check and a production build.

## Challenges we ran into

- **ChEMBL files some mechanisms on salt forms.** Our first query missed them, so six approved
  drugs, ruxolitinib among them, had no usable target. Querying by parent molecule fixed it:
  ruxolitinib now gets JAK1, JAK3 and TYK2 and 19 predictions, and the benchmark went from 389 to 525
  predictions on the same drug set.
- **Newer FDA labels are not harmonised in openFDA.** Searching by generic name alone dropped
  approved drugs such as zanubrutinib and atezolizumab, and for pembrolizumab it found a combination
  product first. The label rule now prefers an exact name, sorts by date and falls back to the
  label's product data. The drug set grew from 39 to 52 drugs and lost none.
- **An API key could reach an error message.** A failed openFDA request carried the key in its
  URL. Every error is now built from the public URL, and keys are scrubbed again before anything
  reaches Sentry. A test forces a failure with a fake key and checks that it appears nowhere.
- **Some drugs fall outside the method.** ChEMBL records tofacitinib against a protein family rather
  than a single protein, so the protocol gives it no prediction. We changed the demo drug instead
  of bending the rule.
- **Per-quarter counts are small.** Eculizumab's meningococcal reports were 0, 1, 0, 2, 1, 0, 2 and 0
  over the last 8 quarters, too few to test one quarter alone. The watch agent shows reports
  received each quarter and computes the PRR on all reports up to each quarter.
- **The Gemini key arrived late.** Until it did, step 5 could not run, so every live prediction is
  unknown. We kept it that way and labelled the one hand-filled development fixture FIXTURE on
  screen.

## Accomplishments that we're proud of

- Every prediction is a chain of public records, each one linked: the ChEMBL mechanism, the
  catalog entry, the source of the disease's direction, the symptom and its frequency, the label
  sentence and the report counts.
- The steps that decide a verdict use no model. Gemini only translates symptom names, sees no drug,
  and its output is committed and reviewed before scoring.
- The benchmark protocol was committed before any measure, and it reports the unflattering number
  first, beside a shuffled baseline.
- The database itself refuses a prediction without evidence.
- Unknown is never shown as safe, in the engine, the page and the agents.
- The whole workflow answers inside one ASI:One chat, and a failed source is named with its step.

## What we learned

- The direction of a genetic disease is often written only in its name. Of the catalog's 583
  gene–disease pairs, IUIS states the mechanism for 77, Orphanet product 6 supplied 61 more, and the
  disease name ("deficiency") 328; 119 have no usable direction.
- A report signal is not risk. A boxed warning itself raises reporting of the reaction it names, and
  patients on immune drugs have immune diseases, so an infection report may come from the disease.
  Those caveats have to sit beside every number.
- Writing the measurement rules before seeing a result changes what you build: it pushed us to log
  every dropped drug with its reason.
- A drug blocks a protein partly and for a while; a genetic loss is total and lifelong. The
  genetics points at which effects to look for, not how often they happen.

## What's next for Knockout

- Run step 5 and the full benchmark, publish label precision, report precision and the lift over
  the shuffled baseline, and have a person review 50 sampled mappings.
- Extend the catalog beyond inherited immune diseases, so drugs on other genes get predictions.
- Use the strength of the evidence: a stated mechanism should weigh more than a disease name.
- Alert drug-safety teams when a watched prediction crosses the signal threshold.
- Compare candidate new signals with later label changes, to see whether the genetics saw them first.

## Built with

python, fastapi, uvicorn, httpx, postgresql, timescaledb, tiger-data, psycopg, gemini-api,
google-ai-studio, chembl, openfda, faers, human-phenotype-ontology, orphanet, uniprot, helix,
fetch.ai, uagents, agentverse, asi-one, creao, sentry, next.js, react, typescript, css, docker,
docker-compose, caddy, vultr, vercel, playwright, pytest, ruff

Add "godaddy-registry", "paper" or "devin" only if those were used, and remove vultr, vercel or
tiger-data if that part was not deployed by the time you submit.

## Try it out

- GitHub: https://github.com/dheerajkoppu/knockout
- Ask it in ASI:One: _fill in_
- Report page: _fill in_
- API: _fill in_
- Creao watch agent run: _fill in_

## Video

_fill in: video URL (exactly 3:00)_

---

## Company challenges

Paste one paragraph per challenge entered, into the description or the challenge's own field.

**Fetch.ai: ASI:One Agent Challenge.** Five uAgents put the whole workflow in one ASI:One chat.
`knockout-orchestrator` (address _fill in_) speaks the Agent Chat Protocol, reads a question such as
"What side effects should a C5 blocker cause?", resolves the protein through UniProt and ChEMBL to
its approved drugs, and asks four specialists in parallel: `target-agent` (drug to targets and
direction), `genetics-agent` (diseases, direction rule, symptoms, reaction terms), `label-agent`
(the verbatim label sentence) and `signal-agent` (FAERS counts, PRR, verdict, and the watch agent's
trend). The answer comes back as an Interactive Card with the chain as badges, a verdict per
prediction, and buttons to check the other drugs on the same target. The summary is free; "Full
report" uses the Agent Payment Protocol for 0.1 FET, checked on the Fetch.ai ledger before the report
is sent. If a source fails, the specialist answers unknown with its reason and the reply names the
agent and the step. All five run on Agentverse mailboxes; the profile is _fill in_. The payment
check is tested against ledger-shaped transaction bodies; _fill in: whether a live wallet payment was
made_.

**Creao AI: Best AI-First Disruptor.** Knockout Watch, a scheduled Creao agent (ID _fill in_), is
the product's monitoring. On every run it reads Knockout's watchlist, counts FAERS reports for each
predicted reaction term quarter by quarter, recomputes the PRR and the Evans criteria, posts the run
to Knockout's webhook, and builds a dashboard of what changed. The report page's trend chart, its
"crossed the threshold since the last run" alerts and the trend in the agents' answer come only from
those posts. Remove the agent and nothing is monitored. Adding a drug to the watchlist starts a run
through the Creao API Trigger. On eculizumab, one run over 8 quarters costs 37 openFDA requests.
Shared run: _fill in_.

**Paper: Best Designed Hack.** The report page is set like a drug label. One accent, the amber of a
medicine bottle, marks only the places where the label or the reports agree with the genetics.
Verdicts differ by shape (filled, half, hollow and dashed squares), so they read without colour. A
boxed warning is quoted verbatim inside a black rule box, as on the label, with the matched term
marked. Each PRR is shown as the 2×2 table it comes from, with the Evans criteria checked one by one.
The page says what the rules set aside and why, and never shows unknown as safe. It is built by hand in
Next.js with IBM Plex type and checked at 1440 px and 390 px in light and dark. The Paper design
file: _fill in: Paper file link_.

**Cognition: Devin.** _fill in only if the sessions exist:_ We gave Devin _fill in: number_ bounded
tasks with written acceptance checks: _fill in: each task, for example "a GitHub Actions workflow
that runs the Python, agent and web checks on every push"_. We reviewed each pull request and merged
_fill in_. Session links: _fill in_.

**Sentry.** The API, the CLI and the agents send traces and logs. Each ChEMBL and openFDA lookup is
a span marked with whether our disk cache answered it, so a trace shows where a cold engine run
spends its time. AI agent monitoring covers the model: each Gemini call is a `gen_ai.chat` span
with the model, temperature, prompt, answer and token counts, the phenotype mapper is a
`gen_ai.invoke_agent` span, and each ASI:One chat is an `invoke_agent` transaction with one span per
specialist agent. The report page has Session Replay and browser tracing. Every event, span and log
has API keys scrubbed before it leaves. _fill in: what one trace showed, with a screenshot link, once
a DSN is set._

**MLH: Best Use of Tiger Data.** Tiger Data holds the evidence and the monitoring. FAERS counts from
the watch agent go into a hypertable keyed by quarter, old quarters move to the columnstore, and the
trend chart reads a continuous aggregate that keeps the latest count per drug, term and quarter. A
deferred constraint trigger fails any transaction that commits a prediction with no evidence row, so
no prediction can be stored without its cited chain, and a second trigger stops evidence being
removed from a prediction that stays. We tested it on a local TimescaleDB 2.30.2 and run it on Tiger
Cloud (_fill in: confirm `store: postgres` on the deployed API_).

**MLH: Best Use of Gemini API.** Gemini does the one step that needs language: the catalog writes
symptoms in the Human Phenotype Ontology, and FDA reports record reactions in MedDRA terms. For each
symptom, Gemini at temperature 0 with a JSON schema returns its kind (clinical, laboratory or
developmental) and up to five reaction terms. The prompt holds only the symptom's id and name, never
a drug, so the model cannot work backwards from what it knows about the drug. Every proposed term
must exist in FAERS, developmental symptoms are dropped, the mappings are committed with the model
name before scoring, and the protocol has a person review 50 of them. The label check and the statistics use no
model. _fill in: number of symptoms mapped and the model name, from `data/mappings/hpo.json`._

**MLH: Best Use of Vultr.** One Vultr Cloud Compute instance in Los Angeles runs the API and the
five agents with Docker Compose, with Caddy issuing the HTTPS certificate the Vercel page and the
Creao agent need. The agents reach Agentverse through mailboxes, so no inbound port is opened for
them, and the database port is never published. Volumes keep the ChEMBL and openFDA cache, and a report
is stored after its first run, so the stage demo does not wait on those sources. API: _fill in_.

**MLH: Best Domain Name from GoDaddy Registry.** _fill in: the domain_. "Knockout" is the idea in
one word: a drug that blocks a protein is a chemical knockout of a gene. The API answers at
`api.`_fill in_ and the report page at _fill in_.

**MLH: Commit Fellowship.** The problem: many side effects are recognised only after a drug is on
the market, from voluntary reports. Drug-safety teams at drug makers and regulators review safety
signals drug by drug. Knockout gives them a reason to look before reports pile up: each predicted
effect comes with the genetic disease that predicts it, the label sentence if one exists, and the
report counts, and the watch agent keeps checking. The prototype already sells the full report per
drug through the Fetch.ai Payment Protocol, which is the business model we want to test with
drug-safety teams. Team: _fill in: names and roles_.

---

## Built at LA Hacks, and what was reused

Knockout uses [Helix](https://github.com/dheerajkoppu/helix) (MIT), built at Hack-Nation on
3 Oct 2026 and pinned at commit `97f3704` from 4 Oct 2026, as a library.

**Reused from Helix:** exactly three imports, plus one copied list:

- the IUIS catalog loader (`helix.knowledge.catalog`): 604 inherited immune diseases, 511 genes and
  their symptoms;
- `resolve_mechanism`: a disease's stated or named mechanism;
- `molecule_effect`: a ChEMBL action type read as lowers or raises;
- the agents carry a copy of Helix's lists of lowering and raising action types.

**Built at LA Hacks, 17–18 Oct 2026:** everything else. The ChEMBL client, the drug-first pipeline
and the direction rule for side effects, Orphanet product 6 as a direction source, the frequency
filter, the Gemini mapping, the label check, the FAERS signal test, the benchmark protocol and
scoring, the API, the Tiger Data store and its evidence trigger, the five Fetch.ai agents, the Creao
watch agent, the report page, the Sentry instrumentation and the deployment.

## Limits we state

- The catalog covers inherited immune diseases only, so Knockout covers drugs acting on immune genes.
- FAERS reports are voluntary and uneven, and counts are not incidence.
- A boxed warning raises reporting of the reaction it names, so a report signal for a labelled
  effect is partly circular.
- Patients on immune drugs have immune diseases, so an infection report may come from the disease.
- A drug's partial, temporary block is weaker than a lifelong genetic loss, so effects may be
  milder or absent.
- Knockout is a research and drug-safety tool, not medical advice.
