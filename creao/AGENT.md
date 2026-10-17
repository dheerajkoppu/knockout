# Knockout Watch: the CREAO agent

Knockout Watch is the agent that keeps checking Knockout's predictions after the report is made.
On every scheduled run it reads the Knockout watchlist. For each drug it takes every predicted
reaction term and counts FAERS reports through openFDA, quarter by quarter. It computes the PRR and
the Evans criteria, posts the run to the Knockout API, and builds a dashboard of what changed.

The report page's trend chart and its "crossed the threshold since the last run" alerts are built
only from this agent's posts (`POST /api/webhooks/creao/signals`). If you remove the agent, nothing
is monitored and the trend stays empty. That is the Creao "Best AI-First Disruptor" rule.

The agent runs `creao/watch.py`, which needs only `httpx`. Everything below is done by you in the
agent.creao.ai interface. Nothing in this repository signs in or holds a key.

---

## 0. Before you start

1. **A CREAO account** made through the hackathon link, which gives the upgraded plan needed for
   scheduled runs: https://creao.ai/signup?hackathon=ucla-ai. Send your account email to the CREAO
   booth if the plan has not been upgraded yet.
2. **The Knockout API on a public URL.** The sandbox has internet access but cannot reach
   `localhost`. Check that `curl https://YOUR-API/api/health` answers from your laptop.
3. **A webhook secret**, the same value on the API server and in CREAO. To generate one:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Set it as
   `KNOCKOUT_WEBHOOK_SECRET` in the API server's environment, then restart the API.
4. **`creao/watch.py` pushed to `main`** on the public repo, because the agent downloads it from
   `https://raw.githubusercontent.com/dheerajkoppu/knockout/main/creao/watch.py`. If the repo is
   not pushed yet, attach `creao/watch.py` to the chat in step 2 instead.
5. **Optional: an openFDA API key** (free, from https://open.fda.gov/apis/authentication/). Without
   one, openFDA allows about 40 requests a minute and 1,000 a day, which is enough for one daily run
   over a short watchlist.

## 1. Secrets

In agent.creao.ai, click **Secrets** in the sidebar, then **Add secret**, once for each row. CREAO
puts every secret into the agent's sandbox as an environment variable with exactly this name.

| Name                      | Value                                                                                                   | Required |
| ------------------------- | ------------------------------------------------------------------------------------------------------- | -------- |
| `KNOCKOUT_API_URL`        | The public base URL of the Knockout API, for example `https://api.example.com` (with or without `/api`) | yes      |
| `KNOCKOUT_WEBHOOK_SECRET` | The same value as `KNOCKOUT_WEBHOOK_SECRET` on the API server                                           | yes      |
| `OPENFDA_API_KEY`         | Your openFDA key                                                                                        | no       |

Add the secrets before step 2, because the build chat runs the script for real.

## 2. Build the agent by chatting

Open a **new chat** on agent.creao.ai. Pick a low-cost model and Low effort; the agent only runs a
script and summarises its JSON. Paste this message:

```text
You are building "Knockout Watch", a monitoring agent for Knockout (github.com/dheerajkoppu/knockout).
Knockout predicts a drug's side effects from the genetic diseases of the proteins it blocks. This agent
re-checks those predictions against FDA adverse-event reports (FAERS) on a schedule.

Optional input: "drugs", a comma-separated list of drug names. When it is empty, watch the whole watchlist.

Do these steps in the sandbox and show me each command's output:
1. pip install httpx
2. curl -fsSL https://raw.githubusercontent.com/dheerajkoppu/knockout/main/creao/watch.py -o watch.py
3. python watch.py --dry-run --drug eculizumab --term "MENINGOCOCCAL INFECTION" --quarters 4
   This reads live openFDA data and prints the payload without posting anything.
4. python watch.py --summary watch_summary.json
   This is a real run: it reads the watchlist from KNOCKOUT_API_URL and posts each drug's counts to
   the Knockout webhook. The Secrets KNOCKOUT_API_URL, KNOCKOUT_WEBHOOK_SECRET and OPENFDA_API_KEY are
   already set as environment variables. Never print their values.
5. Build a dashboard from watch_summary.json only:
   - KPI cards: drugs watched, reaction terms checked, rows posted, new alerts, openFDA data last updated,
     openFDA requests used.
   - One table per drug for the latest quarter: term, reports received that quarter, PRR, signal (yes/no).
   - Each drug's status (posted, skipped, failed, dry_run) with its reason.
   - If a drug has alerts > 0, run curl -s "$KNOCKOUT_API_URL/api/drugs/<drug>/alerts" and list each
     alert's term, quarter and PRR.
   - One line of caveats: FAERS reports are voluntary and uneven, counts are not incidence, and a PRR
     measures reporting, not risk.
   Use only numbers from watch_summary.json and the alerts endpoint. Never estimate, round up or invent
   a drug, term or count.
```

Step 4 needs at least one drug on the watchlist whose report has reaction terms. Add a drug with
`curl -X POST "$KNOCKOUT_API_URL/api/watchlist" -H 'Content-Type: application/json' -d '{"drug":"eculizumab"}'`.
If the report has no reaction terms yet, because the Gemini mapping in protocol step 5 has not run on the
server, the drug is reported as `skipped`. That is correct behaviour, not a failure.

## 3. Create Agent

When the dashboard is right, click **Create Agent** in the chat input bar.

- **Output format:** Dashboard
- **Instructions:** paste the block below
- After saving, open the agent and set its name and description if the super agent chose others:
  - **Name:** `Knockout Watch`
  - **Description:** `Re-checks Knockout's genetic side-effect predictions against new FDA adverse-event reports every day and posts PRR trends and threshold alerts to the Knockout API.`

```text
You are Knockout Watch. On every run:

1. In the workspace, run: python -c "import httpx" || pip install httpx
2. Refresh the script, keeping the saved copy if the download fails (say so in the dashboard):
   curl -fsSL https://raw.githubusercontent.com/dheerajkoppu/knockout/main/creao/watch.py -o watch.py.new && mv watch.py.new watch.py
3. Run the watch. If the "drugs" input is not empty, add --drug "<name>" once for each comma-separated name.
   python watch.py --summary watch_summary.json
   Never add --dry-run on a scheduled run.
4. Exit code 0: all drugs done. Exit code 1: some drugs failed; show each failed drug's reason. Exit code 2:
   a setting is missing; show the message, which names the missing Secret, and stop.
5. Build the dashboard from watch_summary.json only: KPI cards (drugs watched, reaction terms checked,
   rows posted, new alerts, openFDA data last updated, openFDA requests used); one table per drug for the
   latest quarter (term, reports received that quarter, PRR, signal); each drug's status and reason.
   For every drug with alerts > 0, run curl -s "$KNOCKOUT_API_URL/api/drugs/<drug>/alerts" and list each
   alert's term, quarter and PRR.
6. End with: "FAERS reports are voluntary and uneven, counts are not incidence, and a PRR measures
   reporting, not risk."

Rules: use only numbers from watch_summary.json and the alerts endpoint. Never estimate or invent a drug,
term or count. Never print the value of any Secret. Never start another agent run.
```

## 4. Check the saved environment

Create Agent saves the sandbox state, including `httpx` and `watch.py`. To check or change it, open
the agent, click **Update Environment**, ask "list the installed packages and the files in the
workspace", install anything that is missing, then click **Save to Agent** in the blue banner.
Packages installed during an ordinary run are not saved.

## 5. Default model

In the agent sidebar, set **Default model** to the same low-cost model you used in step 2. Scheduled
runs and API runs use it, and every run spends credits.

## 6. Schedule

Open the agent's **Schedule** tab, click **+ Create Schedule** and set:

- **Frequency:** Daily at 06:00, timezone America/Los_Angeles. With an openFDA key, Custom with
  the cron `0 */6 * * *` (every 6 hours) stays well within the key's limits. CREAO refuses
  schedules less than 5 minutes apart.
- **Inputs:** leave "drugs" empty so the schedule watches the whole watchlist.
- **Delivery:** optionally, an email after each run, which links to the run's session.

openFDA refreshes FAERS about once a quarter (the summary shows `openfda_last_updated`), so most
runs confirm the same numbers. A threshold alert appears when a run finds a newly loaded quarter that
tips a term over the Evans criteria.

**Request budget**, with the default 8 quarters: `18 + 18 × terms` openFDA requests per drug, plus
one per run. Totals shared between drugs are fetched once. One term costs 37 requests in total,
measured on eculizumab. Ten terms cost about 200. Without a key that is about 5 minutes per drug, and
1,000 requests a day cover about five such drugs. `--quarters 4` roughly halves the cost.

## 7. Agent ID and run share link for the README

- **Agent ID:** shown on the agent's page in agent.creao.ai. It is the `appId` the API Trigger uses.
- **Run share link:** open the agent, then the **Sessions** tab. Open one completed run's chat thread
  and click the **share** icon in the thread header to copy its public, read-only link. Use a run
  that posted at least one drug, and keep sharing switched on until judging ends.

In the repository README, replace the two `_fill in_` lines under `### Creao watch agent` (in the
`## Agents` section) with:

```markdown
- Agent ID: **Knockout Watch**, `PASTE-AGENT-ID`
- Run: one scheduled run, shared read-only: PASTE-RUN-SHARE-LINK
```

Do not paste a new heading; the section and its description are already there.

The order that makes a shareable run possible: push `creao/watch.py` to `main` (check that the raw
URL in step 2 returns 200), deploy the API on HTTPS with `KNOCKOUT_WEBHOOK_SECRET`, run step 5 with
the Gemini key so reports have reaction terms, add eculizumab to the watchlist (with the
`X-Knockout-Webhook-Secret` header), then build the agent. A run started before step 5 skips every
drug.

## 8. Optional: start a run from the Knockout server (API Trigger)

With `CREAO_API_KEY` and `CREAO_AGENT_ID` set on the API server, `POST /api/watchlist` starts a run
for a newly watched drug through this trigger (in the background; a failure is logged and never fails
the watchlist write).

1. On the agent's page, create an **agent key** (`capi_…`). It can run only this agent.
2. Put it in the **API server's** environment, never in the web page or the repo:
   `CREAO_API_KEY=capi_…` and `CREAO_AGENT_ID=<the agent ID>`.
3. Start a run and wait for it: `python creao/trigger.py --wait`, or with inputs,
   `python creao/trigger.py --inputs '{"drugs": "eculizumab"}'`.

The run posts its results to the Knockout webhook itself, so the caller does not need to wait. Every
API run also appears in the agent.creao.ai sidebar as `[API] …`, where you can watch each step.

## 9. Showing it in the demo

1. On the agent's page, click **Run**. The run thread shows "Starting sandbox…", the `watch.py`
   command and its per-drug log lines (`eculizumab: posted 8 row(s), stored 8, alerts 0`).
2. Open the finished dashboard: the KPI cards and the latest-quarter table.
3. Switch to the Knockout report page for eculizumab. The trend chart shows the same quarters, and
   "last run" shows this run's time.
4. Say it out loud: "Remove the agent, and nothing is monitored."

## 10. What the numbers mean

For each reaction term and each of the last 8 complete quarters, up to openFDA's last update:

- `reports`: FAERS reports naming the drug and the term that FDA **received during that quarter**.
  This is the trend.
- `prr` and `signal`: computed on **every report received up to the end of that quarter**, with the
  formula in `src/knockout/signals.py`: PRR = (a / drug) / ((term − a) / (all − drug)). A signal
  needs a ≥ 3, PRR ≥ 2 and Yates chi-squared ≥ 4. Per-quarter counts are often 0 to 2 reports, too
  few to meet the criteria on their own. The cumulative table is the standard way to follow a signal
  over time, and its latest quarter equals the all-time PRR on the report page.
- The drug is matched with `patient.drug.openfda.generic_name:"<name>"` and the term with
  `patient.reaction.reactionmeddrapt.exact:"<TERM>"`, encoded exactly as the engine encodes them.

Measured on live openFDA on 17 Oct 2026 (data last updated 2026-07-30): for eculizumab and
MENINGOCOCCAL INFECTION, the table through 2026Q2 is 86 / 54,046 / 311 / 20,692,690, PRR 146.0,
signal. The reports received per quarter from 2024Q3 to 2026Q2 were 0, 1, 0, 2, 1, 0, 2, 0.

## Troubleshooting

| What you see                                  | Cause and fix                                                                           |
| --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `KNOCKOUT_WEBHOOK_SECRET is not set` (exit 2) | Add the Secret in CREAO (step 1)                                                        |
| `HTTP 401` on the webhook                     | The CREAO Secret and the server's `KNOCKOUT_WEBHOOK_SECRET` differ                      |
| `HTTP 503` on the webhook                     | The server has no `KNOCKOUT_WEBHOOK_SECRET`; set it and restart the API                 |
| `ConnectError` on the Knockout API            | `KNOCKOUT_API_URL` is not public (localhost or a private IP) or the API is down         |
| A drug is `skipped`                           | Its report has no reaction terms; the server needs `GEMINI_API_KEY` for protocol step 5 |
| Slow runs or `HTTP 429` from openFDA          | Add `OPENFDA_API_KEY`, or run with `--quarters 4`                                       |
| The schedule never fires                      | Scheduled runs need Pro Plus or higher: ask the CREAO booth to upgrade the account      |

## Running it locally

```bash
# Dry run against live openFDA, no API and no secret needed
.venv/bin/python creao/watch.py --dry-run --drug eculizumab --term "MENINGOCOCCAL INFECTION"

# A real run against an API (local or deployed)
KNOCKOUT_API_URL=http://127.0.0.1:8000 KNOCKOUT_WEBHOOK_SECRET=... .venv/bin/python creao/watch.py

# Tests (mocked HTTP; one test marked `live` reads openFDA)
.venv/bin/python -m pytest -q creao/tests
```
