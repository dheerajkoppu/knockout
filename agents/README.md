# Knockout agents (Fetch.ai Agentverse and ASI:One)

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Five uAgents that put the whole Knockout workflow inside an ASI:One chat. Ask "What side effects should a C5
blocker cause?" or "Is eculizumab expected to cause infections?" and the orchestrator resolves the drug, calls four
specialists, and answers with the cited chain (drug → protein → genetic disease → symptom), each prediction's
check against the FDA label and FDA adverse-event reports, and an Interactive Card. The summary is free; the full
report is paid per drug through the Agent Payment Protocol.

Built at LA Hacks AI Hackathon 2026 for the Fetch.ai ASI:One Agent Challenge. Research and drug-safety tool, not
medical advice.

## The agents

<!-- addresses:start -->

_Fill in with your seeds: `python -m knockout_agents.addresses --write` (run from `agents/`)._
<!-- addresses:end -->

| Agent                   | Protocols                                                    | Does                                                                                                                                                          |
| ----------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `knockout-orchestrator` | AgentChatProtocol 0.3.0, AgentPaymentProtocol 0.1.0 (seller) | Reads the request, resolves the drug (ChEMBL, UniProt), calls the four specialists, assembles the answer and the Interactive Card, sells the full report      |
| `target-agent`          | KnockoutSliceProtocol 0.1.0                                  | Steps 1 and 2: the drug's ChEMBL parent molecule, its human protein targets, and which way it pushes each one                                                 |
| `genetics-agent`        | KnockoutSliceProtocol 0.1.0                                  | Steps 3 to 5: each target's IUIS genetic diseases, their direction and source, the fixed direction rule, the frequent phenotypes and their FDA reaction terms |
| `label-agent`           | KnockoutSliceProtocol 0.1.0                                  | Step 6: the label sentence that names each predicted effect, verbatim, with its section                                                                       |
| `signal-agent`          | KnockoutSliceProtocol 0.1.0                                  | Steps 7 and 8: FAERS counts, PRR, chi-squared and the Evans criteria per prediction, the verdict, and the watch agent's trend and alerts                      |

Each specialist calls the Knockout API (`KNOCKOUT_API_URL`) and returns its slice of the report. None of them
imports the engine, so the agents run on Python 3.12 while the engine runs on 3.14.

## How one question flows

```
ASI:One user ──ChatMessage──► knockout-orchestrator
                               │ 1. reads the request: a drug name, "a C5 blocker", an effect ("infections"),
                               │    or a card button; optional ASI:One LLM fallback only extracts names
                               │ 2. resolves it: exact ChEMBL name, or UniProt gene → ChEMBL target → approved
                               │    drugs, choosing the longest-marketed one
                               ├─SliceRequest──► target-agent      GET /api/drugs/{drug}/report  (runs the engine once)
                               ├─SliceRequest──► genetics-agent ─┐
                               ├─SliceRequest──► label-agent     ├ in parallel, from the cached report
                               └─SliceRequest──► signal-agent   ─┘ plus /trend and /alerts
                               │ 3. merges the four slices per prediction
ASI:One user ◄──ChatMessage── summary text + Interactive Card (custom element tree)
             ──"full report"─► RequestPayment (FET, fet_direct)
             ──CommitPayment─► transaction checked on the Fetch.ai ledger ──► CompletePayment + full report
```

**Failure handling.** Every specialist answers, whatever breaks: an unreachable API, a timeout, an unknown drug or
an exception becomes `status: "unknown"` with the reason. If a specialist does not answer within
`KNOCKOUT_SPECIALIST_TIMEOUT_SECONDS`, the orchestrator records it as unknown. The reply names the agent and the
protocol step that failed ("label-agent (step 6, FDA label) answered unknown: ...") and still shows everything the
other specialists returned. Unknown is never shown as safe. A card that fails validation falls back to the text.

**The Interactive Card** is a `custom` element tree: the chain as badges, one list item per prediction with its
verdict badge, the label quote and the report counts, the caveats, and buttons. "Full report" sends
`{"action": "full_report", "drug": ...}`; for a protein question, "Check ravulizumab" and the like run the other
drugs on the same target. The orchestrator reads card selections as card-response metadata, as JSON text
(direct @mention) or as prose (planner-mediated).

**The Payment Protocol.** The orchestrator is the seller. "Full report" sends `RequestPayment` for
`KNOCKOUT_FULL_REPORT_PRICE_FET` (default 0.1) FET by `fet_direct`, to the orchestrator's own wallet, on testnet
unless `FET_USE_TESTNET=false`. On `CommitPayment` it fetches the transaction from the Fetch.ai REST endpoint and
checks that it succeeded, sent at least the price to its wallet (and came from `buyer_fet_wallet` when given), and
was not used before. Only then does it send `CompletePayment` and the full report: every target, disease and
direction basis, every prediction with its reaction terms, the label sentence, every FAERS count with PRR and
chi-squared and the openFDA query, the label set id, the trend and alerts, and the problems. Otherwise it sends
`CancelPayment` with the reason. The model: drug-safety teams pay per drug they review; the summary stays free.

## What it needs

- The Knockout API from this repository (`src/knockout/api.py`), reachable at `KNOCKOUT_API_URL`.
- Public data services, no keys: [ChEMBL](https://www.ebi.ac.uk/chembl/api/data/docs) and
  [UniProt](https://rest.uniprot.org) for resolving drugs and proteins, and the
  [Fetch.ai REST API](https://rest-dorado.fetch.ai) for checking payments.
- An [Agentverse](https://agentverse.ai) account for the mailboxes and an [ASI:One](https://asi1.ai) account to
  chat. Optional: an ASI:One API key (`ASI1_API_KEY`) for the LLM fallback, and a Sentry DSN.

## Run it locally

Python 3.10 to 3.13 (uAgents does not support 3.14 yet). From the repository root:

```bash
/opt/homebrew/bin/python3.12 -m venv agents/.venv
agents/.venv/bin/pip install -r agents/requirements-dev.txt
cd agents
cp .env.example .env
.venv/bin/python -m knockout_agents.seeds >> .env   # one random seed per agent; keep .env private
```

Start the Knockout API (from the root: `make api`, or `uvicorn knockout.api:app --port 8000`), then:

```bash
.venv/bin/python -m knockout_agents.run --no-mailbox      # all five agents in one process on port 8100
.venv/bin/python -m knockout_agents.ask "Is eculizumab expected to cause infections?" --quiet
.venv/bin/python -m pytest -q                              # no network: a fake API, ChEMBL, UniProt and ledger
```

`ask` starts all five agents plus a stand-in ASI:One user in one process and prints the reply and the card JSON,
with real uAgents messages between them. `make agents` from the root runs the same as `run`, with mailboxes on.

`--test-seeds` uses public test seeds for local runs. Never register those on Agentverse.

## Put them on Agentverse (mailbox)

You need an Agentverse account (agentverse.ai; LA Hacks code for a month of Premium: `LAHACKSAI26AV`). The
agents run on your machine or the Vultr VM and reach Agentverse through mailboxes, so no inbound port is needed.

1. Set the five `AGENT_SEED_*` values in `agents/.env` (above) and keep `AGENT_MAILBOX=true`, so all five appear
   on Agentverse. `AGENT_MAILBOX=orchestrator` gives only the orchestrator a mailbox, if your plan limits
   mailboxes; the specialists still answer it from the same process.
2. Start the agents: `.venv/bin/python -m knockout_agents.run`. Each agent logs its address and an Agent Inspector
   link (`https://agentverse.ai/inspect/?uri=http%3A//127.0.0.1%3A8100&address=agent1q...`). The warning about
   funds for the Almanac contract is expected; registration goes through the Almanac API instead. So is
   "Agent mailbox not found: create one using the agent inspector" until step 3 is done.
3. Connect each mailbox, one of two ways:
   - **Inspector:** open each link while signed in to Agentverse, press **Connect**, choose **Mailbox**, then
     **Finish**. In Chrome, allow "access devices on your local network" when asked.
   - **API key:** create a key at Agentverse → Profile → API Keys, put it in `agents/.env` as
     `AGENTVERSE_API_KEY`, and in a second terminal run `.venv/bin/python -m knockout_agents.connect`
     (`make agents-connect` from the root, `make deploy-connect-agents` on the VM).
4. On Agentverse → Agents, each agent shows as a mailbox agent with its profile from
   `knockout_agents/profiles/*.md`. Open `knockout-orchestrator` → edit the profile: add an avatar, the keywords
   "drug safety, side effects, pharmacovigilance, genetics, FDA", and keep the README. The badges in it put it
   under Innovation Lab.
5. Fill the address table: `.venv/bin/python -m knockout_agents.addresses --write`, then copy the same rows into
   the root README's Agents table.

Keep the process running: ASI:One can reach an agent only while it is up.

## Use it in ASI:One

1. Sign in at asi1.ai (LA Hacks code for a month of Pro: `LAHACKSAI26`).
2. From the orchestrator's Agentverse profile, press **Chat with Agent**, or in ASI:One turn on agents and
   mention it by address or handle. Agentverse search indexes new agents after a while; the direct link works
   at once.
3. Ask "What side effects should a C5 blocker cause?" The card opens in the drawer. Press **Full report** to see
   the payment request; approving it needs testnet FET in the ASI:One wallet.

## Submit through the LA Hacks ASI:One Submission Agent

1. Submit on Devpost first.
2. Open `https://asi1.ai/auth/signup?returnTo=%2Ffestival%2Flahacksai2026%2Fdashboard%3Futm_source%3Dlahacksai2026`,
   sign in, and use the LA Hacks AI Hackathon dashboard's Submission Agent.
3. Give it the public GitHub link, the demo video (Fetch.ai asks 3 to 5 minutes), and the orchestrator's address
   and Agentverse profile link. The hackpack links a video walkthrough of this step.

## Configuration

Every setting is an environment variable; `agents/.env.example` lists them all. `agents/.env` and the root `.env`
are read, in that order, and neither is committed.

| Variable                             | Default                 | Meaning                                                                      |
| ------------------------------------ | ----------------------- | ---------------------------------------------------------------------------- |
| `KNOCKOUT_API_URL`                   | `http://localhost:8000` | The Knockout API                                                             |
| `AGENT_SEED_ORCHESTRATOR` and 4 more | none (required)         | One seed per agent; the address is derived from it                           |
| `AGENT_MAILBOX`                      | `true`                  | Connect through Agentverse mailboxes                                         |
| `KNOCKOUT_AGENTS_PORT`               | `8100`                  | Port of the process that runs all five                                       |
| `AGENTVERSE_API_KEY`                 | none                    | Only for `knockout_agents.connect`                                           |
| `KNOCKOUT_PAYMENT_ENABLED`           | `true`                  | `false` sends the full report free                                           |
| `KNOCKOUT_FULL_REPORT_PRICE_FET`     | `0.1`                   | Price of one full report                                                     |
| `FET_USE_TESTNET`                    | `true`                  | Testnet (`atestfet`) or mainnet (`afet`) payments                            |
| `ASI1_API_KEY`                       | none                    | Optional LLM fallback for requests the rules cannot read                     |
| `KNOCKOUT_REPORT_PAGE_URL`           | none                    | Links the report page from the full report                                   |
| `SENTRY_DSN`                         | none                    | Traces each chat as an `invoke_agent` transaction with a span per specialist |

## Limits

- Drug names are resolved by exact ChEMBL name or synonym only, and proteins by exact gene symbol (UniProt,
  reviewed human entries) or ChEMBL target search. A misspelled drug is not guessed.
- For a protein question the analysis covers the longest-marketed approved drug; the others are one button away.
- A first engine run for a new drug can take minutes. Warm the demo drugs first (`make warm` from the root).
- Payment verification reads the transfer from the Fetch.ai REST API. It is tested against transaction bodies
  shaped like that API's response, not yet against a live ASI:One wallet payment.
