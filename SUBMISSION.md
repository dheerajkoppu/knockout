# Submission checklist

**Submit on Devpost by Sunday 18 Oct, 11:30 PDT.** Hacking ends at 12:00. Judging round 1 is at
12:30 and round 2 at 14:00, in person (Collins Conference Room, per `PLAN.md`); every team member
must be there.

Do the items in order: each one unblocks the ones after it. Owners follow `PLAN.md`: **A** engine
and Tiger Data, **B** Fetch.ai, **C** Creao, Sentry and Vultr, **D** design, video, Devpost,
domain and Devin.

Three rules for the whole list:

- **You type every key and password yourself**, into `.env` files or the provider's own page. Keys
  never go into the repository, a chat, a commit or the video. `.env`, `agents/.env` and
  `web/.env.local` are gitignored.
- **A company challenge is selected on Devpost only if its item below is done** and its proof (link,
  ID or screenshot) is in `README.md` and `DEVPOST.md` by the 09:30 feature freeze. Otherwise delete
  its paragraph from `DEVPOST.md`, its row from the README table, and leave it unselected.
- **No number is quoted until the pipeline produced it.** No benchmark number before
  `data/mappings/hpo.json` is committed. The fixture (`?fixture=1`) is shown only with its FIXTURE
  tag visible and said aloud.

## Where things stand (Sat 17 Oct, afternoon)

Working on live data: ChEMBL targets and direction, the catalog, the direction rule, the phenotype
filter, the openFDA label and FAERS totals, the API on both stores, the report page, the five agents
in one local process, and the watch script posting to the local API. 122 Python tests pass (11
skip without a database), 22 agent tests pass.

Blocked: `GEMINI_API_KEY` is not set, so step 5 has not run and every prediction is `unknown`.
Nothing is committed since `20ebd86`, so `creao/watch.py` is not on GitHub yet (its raw URL returns
404). Nothing is deployed. No account work (Agentverse, Creao, Tiger Cloud, Sentry, Vultr, Vercel,
Paper, Devin, GoDaddy) is done.

## Overview

| #   | By        | Owner | Item                                                  | Done when                                                                                  |
| --- | --------- | ----- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1   | Sat 15:00 | A     | Gemini and openFDA keys in `.env`                     | `/api/health` shows `gemini_key: true`, `openfda_key: true`                                |
| 2   | Sat 15:30 | A     | Step 5 on eculizumab, ibrutinib, ruxolitinib          | `knockout predict eculizumab` lists reaction terms for HP:0005381                          |
| 3   | Sat 16:00 | A     | Webhook secret chosen                                 | `KNOCKOUT_WEBHOOK_SECRET` in the root `.env`                                               |
| 4   | Sat 16:30 | A     | First commit and push                                 | `creao/watch.py` raw URL returns 200                                                       |
| 5   | Sat 17:00 | A     | Tiger Cloud service                                   | `/api/health` shows `store: postgres` against Tiger Cloud; trigger demo refuses the insert |
| 6   | Sat 18:00 | C     | Vultr instance with HTTPS                             | `curl https://<api>/api/health` answers from a laptop                                      |
| 7   | Sat 18:30 | D     | GoDaddy Registry domain                               | `dig +short api.<domain>` prints the Vultr IP                                              |
| 8   | Sat 19:00 | D     | Report page on Vercel                                 | `/drug/eculizumab` renders from the deployed API                                           |
| 9   | Sat 19:00 | C     | Sentry projects and DSNs                              | One trace with `gen_ai` spans in Sentry                                                    |
| 10  | Sat 20:00 | B     | Agentverse and ASI:One                                | The C5 question answered with a card inside ASI:One                                        |
| 11  | Sat 22:00 | C     | Creao watch agent, scheduled                          | A shared run that posted eculizumab                                                        |
| 12  | Sun 01:00 | A     | Benchmark mapped, reviewed, scored, committed         | `benchmark/results/RESULTS.md` has numbers, protocol version 2, 52 drugs                   |
| 13  | Sun 09:30 | D     | Paper design file (or drop the challenge)             | Paper share link in README and DEVPOST                                                     |
| 14  | Sun 09:30 | D     | Devin tasks (or drop the challenge)                   | Session links in README and DEVPOST                                                        |
| 15  | Sun 09:30 | D     | Every _fill in_ filled or removed; **feature freeze** | `grep -n "_fill in" README.md DEVPOST.md` prints nothing you mean to keep                  |
| 16  | Sun 11:00 | D     | 3:00 video uploaded                                   | `ffprobe` prints 180.0…; the link plays signed out                                         |
| 17  | Sun 11:30 | D     | Devpost submitted, track and challenges selected      | Devpost shows the project as submitted                                                     |
| 18  | Sun 11:30 | B     | Fetch.ai Submission Agent                             | The agent confirms the submission                                                          |
| 19  | Sun 11:30 | D     | Commit Fellowship supplemental form                   | Form confirmation received                                                                 |
| 20  | Sun 11:45 | A     | Final push                                            | `git status` clean, GitHub main matches the demo                                           |
| 21  | Sun 12:30 | all   | Judging, in person                                    | Every member present, warmed                                                              |

---

## 1. Keys: Gemini and openFDA (A, now)

1. **Gemini.** Open Google AI Studio (aistudio.google.com), sign in, choose **Get API key**, then
   **Create API key**. Copy it.
2. **openFDA.** Open https://open.fda.gov/apis/authentication/, enter an email address, and copy the
   key it gives you.
3. Create the root `.env` and type both keys into it yourself:

   ```bash
   cd /Users/dheeraj/Downloads/Projects/knockout
   cp .env.example .env
   open -e .env          # set GEMINI_API_KEY= and OPENFDA_API_KEY=, then save
   ```

4. Check, with the API running (`make api` in another terminal):

   ```bash
   curl -s localhost:8000/api/health    # gemini_key true, openfda_key true
   ```

## 2. Step 5 on the demo drugs (A)

```bash
.venv/bin/knockout predict eculizumab --json data/reports/eculizumab.json
make warm                                         # eculizumab, ibrutinib, ruxolitinib through the API
```

Look at the eculizumab output for HP:0005381 (Recurrent Neisseria meningitidis infection). The
expectation, not yet seen: its terms include `MENINGOCOCCAL INFECTION`, its verdict is `on_label`
with the boxed-warning sentence, and its counts show PRR 146 from 86 reports. Write down what
actually came out; that is what goes in the README example, `DEVPOST.md` (paragraph A) and the
video. If Gemini proposed other terms, the verdict follows those terms. Never edit
`data/mappings/hpo.json` by hand.

If Gemini fails (quota, model), record the problem text from the report and use paragraph B in
`DEVPOST.md`.

## 3. Webhook secret (A)

```bash
echo "KNOCKOUT_WEBHOOK_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
```

The same value later goes into the Vultr server's `.env` (item 6) and Creao Secrets (item 11). Keep
it out of chats and the video.

## 4. First commit and push (A)

Creao downloads `creao/watch.py` from GitHub `main`, so this comes before item 11.

```bash
.venv/bin/python -m pytest -q                                   # 122 passed, 11 skipped
.venv/bin/ruff check .
(cd agents && .venv/bin/python -m pytest -q)                    # 22 passed
(cd web && pnpm exec tsc --noEmit)
grep -rn 'api_key=\|key=' benchmark/results data/reports web/fixtures | grep -v '\[Filtered\]'   # must print nothing
git status --short | grep -E '(^|/)\.env' && echo "STOP: an .env file is staged"
git add -A && git status --short                                 # read the list before committing
git commit -m "Add the API, stores, agents, watch agent, report page, benchmark and deployment"
git push origin main
curl -s -o /dev/null -w "%{http_code}\n" https://raw.githubusercontent.com/dheerajkoppu/knockout/main/creao/watch.py   # 200
```

## 5. Tiger Cloud (A)

1. Sign up for Tiger Cloud through the MLH Tiger Data link in the hackpack, and create a service
   (TimescaleDB, the region nearest Los Angeles).
2. Copy the service's connection string (it ends in `sslmode=require`).
3. Point the local `.env` at it (replace the existing `DATABASE_URL` line), then:

   ```bash
   .venv/bin/python -m knockout.store                             # prints "Schema applied to" and the TimescaleDB version
   psql "$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" -f db/demo_trigger.sql   # step 1 must fail at commit
   KNOCKOUT_TEST_DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" .venv/bin/python -m pytest -q tests/test_store.py
   ```

4. Use the same `DATABASE_URL` on the Vultr server (item 6). `/api/health` must show
   `store: postgres`.
5. In the README "Store: Tiger Data" section, replace the Tiger Cloud _fill in_ with the region.

## 6. Vultr instance with HTTPS (C)

Follow [`deploy/README.md`](deploy/README.md) sections 1 to 8. In short:

1. Claim the MLH Vultr credit through MLH's link, and check that **Billing** shows it.
2. Add your SSH key, deploy a Shared CPU instance in **Los Angeles**, Ubuntu 24.04, 2 vCPU / 4 GB.
3. Firewall group: TCP 22 (your IP), TCP 80 and 443 (anywhere); never 5432 or 8100.
4. On the server: install Docker, `git clone https://github.com/dheerajkoppu/knockout.git`,
   `cp deploy/vultr.env.example .env`, `chmod 600 .env`, and type in `GEMINI_API_KEY`,
   `OPENFDA_API_KEY`, `KNOCKOUT_WEBHOOK_SECRET` (item 3), `DATABASE_URL` (item 5), and
   `SENTRY_DSN` once item 9 is done.
5. HTTPS: `COMPOSE_PROFILES=https`, `KNOCKOUT_DOMAIN=api.<domain>` (item 7) or
   `<ip>.sslip.io` until the domain works, `API_BIND=127.0.0.1`.
6. `make deploy-up`, then `make health` and `make warm`.
7. From a laptop: `curl https://<api>/api/health`. Put the URL in the README links table and in
   `DEVPOST.md` (Try it out, Vultr paragraph).

## 7. GoDaddy Registry domain (D)

1. Claim the domain through MLH's GoDaddy Registry offer in the hackpack. "Knockout" is a common
   word, so check what is free before choosing; the name is judged.
2. In the registrar's DNS settings add an `A` record: name `api`, value the Vultr IP, TTL 600.
3. When `dig +short api.<domain>` prints the IP, set `KNOCKOUT_DOMAIN=api.<domain>` on the server
   and `make deploy-up`. Caddy gets the certificate.
4. For the page: in Vercel, Project → Settings → Domains → add `<domain>` and create the DNS record
   Vercel shows. Then set `KNOCKOUT_ALLOWED_ORIGINS=https://<domain>` on the server and
   `make deploy-up`.
5. Fill the domain into the README (links, Deploy, sponsor table) and the GoDaddy paragraph in
   `DEVPOST.md`.

## 8. Report page on Vercel (D)

1. Vercel → Add New → Project → import `dheerajkoppu/knockout`; Root Directory `web`.
2. Environment variables: `NEXT_PUBLIC_API_URL=https://api.<domain>` (no trailing slash);
   `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT=production` and
   `NEXT_PUBLIC_SENTRY_TRACE_API=true` once item 9 is done. Leave `NEXT_PUBLIC_USE_FIXTURES` unset.
3. Deploy. After any `NEXT_PUBLIC_*` change, redeploy.
4. Open `/drug/eculizumab`: the footer must read `Store: postgres` and show no "Gemini key missing".

## 9. Sentry (C)

1. Create a Sentry account (use the hackathon's Sentry offer if the hackpack has one) and two
   projects: **Python / FastAPI** named `knockout-api` (the API, CLI and agents share it) and
   **Next.js** named `knockout-web`.
2. Type the first DSN into the root `.env`, `agents/.env` and the server `.env` as `SENTRY_DSN`; the
   second into Vercel as `NEXT_PUBLIC_SENTRY_DSN`.
3. Make traffic that fills each view:
   - AI agent monitoring: with `SENTRY_DSN` set locally, run `knockout predict` on a drug whose
     phenotypes are not mapped yet, or the benchmark mapping in item 12. Once `hpo.json` is
     committed the deployed API never calls Gemini, so these local runs are the ones that fill it.
   - Tracing: one cold `?refresh=true` report on the server; the trace shows a `source.openfda` or
     `source.chembl` span per lookup with `cache.hit`.
   - Session Replay: open the deployed report page.
   - Agents: one ASI:One chat (item 10) shows an `invoke_agent` transaction with a span per
     specialist.
4. Take screenshots of a trace, the AI agent view and a replay. Describe only what they show in the
   Sentry paragraph of `DEVPOST.md` and the README; do not claim a fix a trace did not find.

## 10. Fetch.ai: Agentverse and ASI:One (B)

Detail in [`agents/README.md`](agents/README.md).

1. **ASI:One:** sign in at asi1.ai and apply the code `LAHACKSAI26` (a month of Pro).
2. **Agentverse:** sign in at agentverse.ai and apply the code `LAHACKSAI26AV` (a month of
   Premium). Profile → API Keys → create a key.
3. **Seeds** (private; they fix the addresses, so make them once and keep them):

   ```bash
   cd agents && cp .env.example .env && .venv/bin/python -m knockout_agents.seeds >> .env
   ```

   Copy the same five `AGENT_SEED_*` lines into the Vultr server's `.env`, with
   `AGENTVERSE_API_KEY`. Run the agents in one place only: on the server with `make deploy-up`.

4. **Mailboxes:** on the server, `make deploy-connect-agents`. Then in Agentverse → Agents, open
   `knockout-orchestrator`, add an avatar and the keywords "drug safety, side effects,
   pharmacovigilance, genetics, FDA", and keep its README (the badges put it under Innovation Lab).
5. **Addresses:** from `agents/`, `.venv/bin/python -m knockout_agents.addresses --write`, then copy
   the five rows into the root README's Agents table.
6. **Test in ASI:One:** from the orchestrator's profile press **Chat with Agent** and ask "What side
   effects should a C5 blocker cause?". The card must show eculizumab, Complement C5 (INHIBITOR), C5
   deficiency and the meningococcal prediction. Press **Full report** and check the payment request
   for 0.1 FET appears. Paying needs testnet FET in the ASI:One wallet; if you pay, note it in the
   Fetch.ai paragraph, otherwise keep the "tested against ledger-shaped bodies" sentence.
7. Put the ASI:One chat link and the Agentverse profile URL in the README links table and
   `DEVPOST.md`.

## 11. Creao watch agent (C)

Needs items 2, 3, 4 and 6 done. Detail in [`creao/AGENT.md`](creao/AGENT.md).

1. Sign up through the hackathon link, https://creao.ai/signup?hackathon=ucla-ai (from
   `creao/AGENT.md`). Scheduled runs need the upgraded plan; if it is not applied, give your account
   email to the Creao booth.
2. Secrets: `KNOCKOUT_API_URL` (the HTTPS API from item 6), `KNOCKOUT_WEBHOOK_SECRET` (item 3),
   `OPENFDA_API_KEY`.
3. Add eculizumab to the watchlist:

   ```bash
   curl -s -X POST https://api.<domain>/api/watchlist -H 'content-type: application/json' \
     -H "X-Knockout-Webhook-Secret: <the secret>" -d '{"drug":"eculizumab"}'
   ```

4. Build the agent by chat with the message in `creao/AGENT.md` §2, then **Create Agent** with the
   instructions in §3, name `Knockout Watch`, output format Dashboard.
5. Schedule: daily 06:00 America/Los_Angeles, or `0 */6 * * *` with the openFDA key.
6. Press **Run** once. The run log must say `eculizumab: posted 8 row(s)`, and the report page's
   watch section must show this run's time. If it says `skipped`, step 5 has not run on the server.
7. Sessions tab → open the run → share icon → copy the read-only link. Put the agent ID and the link
   in the README (`### Creao watch agent`) and `DEVPOST.md`. Keep sharing on until judging ends.
8. Optional: create an agent key (`capi_…`) and set `CREAO_API_KEY` and `CREAO_AGENT_ID` on the
   server, so adding a drug starts a run.

## 12. Benchmark (A, can run in the background from item 2 on)

```bash
.venv/bin/python -m benchmark.score --generate-mappings     # maps all 1,666 phenotypes the drugs and the shuffled baseline can use, then scores; about 30 min
.venv/bin/python -m benchmark.sample_mappings               # 50 rows for a person to review
# a team member fills in kind_correct, terms_correct, reviewer and notes in benchmark/results/mapping_review.csv
.venv/bin/python -m benchmark.score                         # rescore with the review
grep -rn 'api_key=\|key=' benchmark/results data/reports | grep -v '\[Filtered\]'   # must print nothing
git add data/mappings/hpo.json benchmark/results && git commit -m "Map phenotypes with Gemini and score the benchmark under protocol version 2" && git push
```

Check that `benchmark/results/RESULTS.md` now says protocol version 2 and 52 drugs (the current file
is the earlier version 1 run on 39 drugs). Then copy the measures, label precision first, into the
README "Measured results" table and `DEVPOST.md` paragraph A, each with its n and the caveats. If
scoring is not done by the 09:30 freeze, leave "not measured" in both and say "protocol frozen,
scoring pending" in the video.

## 13. Paper (D, decide by 09:30)

1. Claim Paper Pro for teams through the hackathon offer and create a team file.
2. Make the design in Paper: the report page at 1440 px and 390 px (chain, verdict list, boxed-warning
   quote, 2×2 table, watch section), using the page's real type and colours from `web/app/globals.css`.
3. Share the file read-only, put the link in the README sponsor table and the Paper paragraph of
   `DEVPOST.md`. Describe the order truthfully: the page was built in code first unless the Paper
   file really came first.
4. If no Paper file exists by 09:30, drop the challenge.

## 14. Devin (D, decide by 09:30)

1. Claim the Devin credits the hackathon offers (hackpack or the Cognition booth) and connect Devin to
   `dheerajkoppu/knockout`.
2. Give it two or three bounded tasks with acceptance checks, each as a pull request, for example:
   - a GitHub Actions workflow running `pytest -q -m "not live"`, `ruff check .`, the agent tests and
     `tsc --noEmit` on every push;
   - `ruff format` on the 15 files it would change, with every test still passing;
   - a Playwright smoke test that `/drug/eculizumab?fixture=1` shows the FIXTURE tag.
3. Review each pull request before merging; merge none after the 09:30 freeze.
4. Put the session links and what each task did in the README sponsor table and the Devin paragraph.
   If no session exists by 09:30, drop the challenge.

## 15. Fill every placeholder, then freeze (D, by 09:30)

```bash
grep -n "_fill in" README.md DEVPOST.md agents/README.md
```

- README: links table, the eculizumab "Where this stands" note, Measured results, agent addresses,
  Creao ID and run, Tiger Cloud region, Sentry, API and domain, sponsor rows, the last
  "real and simulated" row, Team.
- `DEVPOST.md`: keep paragraph A or B, delete the other; fill or delete each company paragraph.
- `PLAN.md` still names tofacitinib as a demo drug; it gives no prediction by protocol (protein family
  target), so the demo uses ruxolitinib.
- Commit and push. After 09:30, only text and links change.

## 16. Video, exactly 3:00 (D, 09:30 to 11:00)

Devpost asks for 2 to 3 minutes and Fetch.ai for 3 to 5, so 180 s is the only length that meets
both. Beats from `PLAN.md`:

| Time | Beat                                                                                              |
| ---- | ------------------------------------------------------------------------------------------------- |
| 0:00 | C5 deficiency causes meningococcal infections; eculizumab blocks C5; its boxed warning names them |
| 0:20 | ASI:One: ask about a C5 blocker; the agents run; the card returns the chain and the prediction    |
| 1:10 | Report page: the chain, the label quote, the 2×2 table and PRR                                    |
| 1:40 | The benchmark: label precision first, then the lift over shuffled diseases                        |
| 2:10 | One candidate new signal, in the reports and not on the label, with its caveats                   |
| 2:30 | The Creao run updating the trend                                                                  |
| 2:45 | What is new at LA Hacks, the limits, and "Every genetic disease already ran the trial."           |

Fallbacks: no benchmark by 09:30 → 1:40 shows the frozen protocol and says "scoring pending"; no
candidate signal → 2:10 shows the watch trend; step 5 never ran → the report page shows "Not checked
yet" and the hand check is called a hand check. The fixture only with FIXTURE on screen, said aloud.
No key, secret or `.env` on screen.

```bash
ffmpeg -i raw.mp4 -t 180 -c:v libx264 -c:a aac -movflags +faststart knockout.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 knockout.mp4    # 180.0…
```

Upload to YouTube as Public or Unlisted, open the link in a signed-out window to check it plays, and
put it in the README links table and `DEVPOST.md`.

## 17. Devpost (D, by 11:30)

1. On la-ai-hackathon-2026.devpost.com, start the project and invite every teammate; each must accept
   the invite before the deadline.
2. Paste the fields from `DEVPOST.md`: name, elevator pitch, the story sections, Built with, Try it
   out links, video URL. Upload 3 or more images from `web/screenshots/` (retake them from the
   deployed page after step 5 if possible).
3. Track: **Applied Intelligence**.
4. Company challenges, only those whose item is done: Fetch.ai; Creao AI (Best AI-First Disruptor);
   Paper (Best Designed Hack); Cognition (Devin); Sentry; MLH Tiger Data; MLH Gemini API; MLH Vultr;
   MLH GoDaddy Registry; MLH Commit Fellowship (opt in).
5. Submit, then reload and check the project shows as submitted. It stays editable until 12:00.

## 18. Fetch.ai Submission Agent (B, after Devpost)

1. Open https://asi1.ai/auth/signup?returnTo=%2Ffestival%2Flahacksai2026%2Fdashboard%3Futm_source%3Dlahacksai2026
   (from `agents/README.md`), sign in, and open the LA Hacks AI Hackathon dashboard's Submission
   Agent.
2. Give it the GitHub link, the video link, the orchestrator's address and its Agentverse profile
   link. Keep the agents running on Vultr through judging.

## 19. Commit Fellowship (D, after Devpost)

1. The Devpost opt-in in item 17.4.
2. Submit the supplemental form linked from MLH's prize page for this event. The fellowship is a
   3-week sprint (2 to 20 Nov) for the same team, open to people in the US, Canada and Mexico
   (fellowship.mlh.com/commit-fellowship); questions go to fellowship@mlh.io.
3. Use the Commit Fellowship paragraph of `DEVPOST.md` for the problem and the customer.

## 20. Final push (A, by 11:45)

```bash
git status --short          # nothing but intended changes
grep -rn 'api_key=\|key=' benchmark/results data/reports web/fixtures | grep -v '\[Filtered\]'
git push origin main
```

Check on GitHub that the README renders, every link in its table opens, and the badges show.

## 21. Judging (all, 12:30)

- Every team member present at 12:30 (round 2 at 14:00).
- Laptop charged; the deployed page and an ASI:One tab open; `curl https://<api>/api/health` shows
  `gemini_key: true` and `store: postgres`; `make warm` run on the server that morning.
- Demo order from `RUNBOOK.md` §5: health, ASI:One, report page, results, watch section, trigger demo
  (`psql "$DATABASE_URL" -f db/demo_trigger.sql`).
- If the network fails: play the video and show `web/screenshots/`. Say plainly what is live and what
  is recorded.
