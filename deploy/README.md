# Deploying Knockout

One Vultr Cloud Compute instance runs the API and the Fetch.ai agents with Docker Compose. The
report page runs on Vercel and calls the API from the browser. The Creao watch agent runs in Creao's
cloud and posts to the API's webhook.

| Where                    | What                                                                       | From                                |
| ------------------------ | -------------------------------------------------------------------------- | ----------------------------------- |
| Vultr instance           | `api`: FastAPI on port 8000, the engine, the store                         | `deploy/Dockerfile`                 |
| Vultr instance           | `agents`: five uAgents in one Bureau, reached through Agentverse           | `deploy/Dockerfile.agents`          |
| Vultr instance, optional | `timescaledb` (profile `db`): local TimescaleDB 2.30.2 on Postgres 17      | `timescale/timescaledb:2.30.2-pg17` |
| Vultr instance, optional | `caddy` (profile `https`): HTTPS for the API with an automatic certificate | `caddy:2.11.4-alpine`               |
| Vercel                   | `web/`: the report page                                                    | Next.js                             |
| Tiger Cloud              | The store for the submission (the evidence trigger runs only on Postgres)  | `DATABASE_URL`                      |
| Creao                    | The scheduled watch agent                                                  | `creao/watch.py`                    |

For the submission, set `DATABASE_URL` to the Tiger Cloud service, then from a machine with the
repository run `DATABASE_URL=<tiger url> .venv/bin/python -m knockout.store` and
`psql "$DATABASE_URL" -f db/demo_trigger.sql`, and check that `/api/health` reports `store: postgres`.
Tiger Cloud has not been used yet; only a local TimescaleDB container was tested.

You create every account, claim every credit and type every key yourself. Nothing in this folder
signs in anywhere or contains a secret; keys live only in `.env` on the server, which git ignores.

**The report page needs the API on HTTPS.** Vercel serves the page over HTTPS and the page fetches
the API from the browser, so the browser blocks a plain `http://` API as mixed content. Plan on step
7 (a domain, or the free `sslip.io` name) before you point Vercel at the server.

---

## 1. Create the instance

In the Vultr console (my.vultr.com):

1. Claim the Vultr credit MLH offers for LA Hacks, following MLH's link. **Billing** shows it once
   it is applied.
2. **Account → SSH Keys → Add SSH Key**: paste your public key (`cat ~/.ssh/id_ed25519.pub`).
3. **Deploy +** → **Deploy New Server**:
   - Type: **Shared CPU** (Cloud Compute)
   - Location: **Los Angeles**
   - Image: **Ubuntu 24.04 LTS x64** (26.04 LTS works the same way)
   - Plan: **2 vCPU, 4 GB** is comfortable. 2 GB should do with the swap file from step 3; 1 GB may
     run out of memory while the image builds. The API image is about 770 MB.
   - SSH key: the one you added. Hostname: `knockout`.
4. Deploy, wait for **Running**, and copy the instance's **IP address**. Below it is `203.0.113.10`;
   use yours.

## 2. Open the firewall

**Network → Firewall → Add Firewall Group**, name it `knockout`, and add these inbound rules (Vultr's
firewall only filters inbound traffic; outbound stays open):

| Protocol | Port | Source   | Why                                                     |
| -------- | ---- | -------- | ------------------------------------------------------- |
| TCP      | 22   | My IP    | SSH                                                     |
| TCP      | 80   | Anywhere | Caddy: the certificate challenge and the HTTPS redirect |
| TCP      | 443  | Anywhere | Caddy: the API over HTTPS                               |
| UDP      | 443  | Anywhere | Caddy: HTTP/3 (optional)                                |
| TCP      | 8000 | Anywhere | Only while testing without HTTPS; remove after step 7   |

Then **Linked Instances → Link** the `knockout` instance.

Never open 5432 (TimescaleDB) or 8100 (agents). Neither is published by the compose file, and
the agents need no inbound port because they poll their Agentverse mailboxes.

Vultr's Ubuntu image can also have `ufw` enabled with only SSH allowed (`ufw status` tells you).
Ports that Docker publishes bypass `ufw`, so the Vultr firewall group above is the one that decides.
If `ufw` is active, keep it consistent anyway:

```bash
sudo ufw allow 80,443/tcp
sudo ufw allow 443/udp
```

## 3. Install Docker

```bash
ssh root@203.0.113.10

apt-get update
apt-get install -y ca-certificates curl git make
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

docker compose version
```

On a 2 GB plan, add swap first so the build cannot run out of memory:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 4. Get the code and fill in `.env`

```bash
git clone https://github.com/dheerajkoppu/knockout.git
cd knockout
cp deploy/vultr.env.example .env
chmod 600 .env
nano .env
```

`deploy/vultr.env.example` lists every variable the deployment reads. The ones that matter first:

| Variable                  | Value                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`          | From Google AI Studio. Without it, new phenotypes are not mapped and their verdict is `unknown`   |
| `OPENFDA_API_KEY`         | From open.fda.gov. Optional for a few drugs; without it openFDA allows about 1,000 requests a day |
| `KNOCKOUT_WEBHOOK_SECRET` | A random value you make: `openssl rand -hex 32`. The same value goes into Creao Secrets           |
| `DATABASE_URL`            | Empty for the file store, or a Postgres URL (step 8)                                              |
| `SENTRY_DSN`              | From your Sentry project, or empty                                                                |
| `AGENT_SEED_*`            | One `openssl rand -hex 32` per agent (step 9)                                                     |

`.env` is read twice: Compose passes it into the containers, and `--env-file .env` lets Compose
read `COMPOSE_PROFILES` and fill `API_BIND`, `API_PORT`, `KNOCKOUT_DOMAIN` and `POSTGRES_PASSWORD`
into the compose file. The `make` targets below always pass it.

## 5. Start

```bash
make deploy-up
```

The same thing without `make`:

```bash
docker compose --env-file .env -f deploy/docker-compose.vultr.yml up -d --build
```

The first build takes several minutes. It installs the package with its pinned Helix dependency and
runs `knockout setup`, which bakes the pinned Helix catalog (commit `97f3704`) and Orphanet product 6
into the image and checks the Orphanet checksum against the release the protocol names. Later
builds reuse the dependency layer unless `pyproject.toml` changes; a change in `src/` reruns only the
quick reinstall and `knockout setup`.

Volumes keep state across rebuilds: `api-cache` (every ChEMBL and openFDA response), `api-store`
(reports, watchlist, trends and alerts when `DATABASE_URL` is empty), `api-reports`, `agents-data`
(uAgents storage) and, with the profiles, `timescale-data`, `caddy-data` and `caddy-config`.

Phenotype mappings are the exception. The image carries the committed `data/mappings/hpo.json`; a
mapping Gemini makes on the server for a new drug stays in the container until it is recreated.
Copy it out before rebuilding if you want to commit it:
`docker compose --env-file .env -f deploy/docker-compose.vultr.yml cp api:/app/data/mappings/hpo.json data/mappings/hpo.json`.

## 6. Check it and pre-warm the demo drugs

```bash
make health                       # for example {"status":"ok","gemini_key":true,"openfda_key":true,"store":"files"}
make warm                         # runs eculizumab, ibrutinib and ruxolitinib once each
make deploy-ps
make deploy-logs
```

From your laptop, while port 8000 is open: `curl http://203.0.113.10:8000/api/health`. The API's
interactive docs are at `/api/docs`.

A report is cached in the store after its first run, so the stage demo never waits on ChEMBL or
openFDA. A cached report reruns by itself when its phenotype mapping failed for want of a Gemini
key that is now set, or when its openFDA calls failed. To force a rerun: `curl "http://localhost:8000/api/drugs/eculizumab/report?refresh=true"`.

## 7. HTTPS

Caddy terminates TLS and gets a Let's Encrypt certificate by itself. It needs a name that resolves
to the instance, with ports 80 and 443 open.

**With a domain** (the GoDaddy Registry domain): in the registrar's DNS settings add an `A` record,
name `api`, value `203.0.113.10`, TTL 600. Wait until `dig +short api.example.com` prints the IP.

**Without a domain:** `203.0.113.10.sslip.io` resolves to `203.0.113.10` through the public sslip.io
service, and Let's Encrypt can usually issue a certificate for it. Fine for a demo; a real domain is
more dependable.

Then in `.env`:

```bash
COMPOSE_PROFILES=https            # or db,https with the local database
KNOCKOUT_DOMAIN=api.example.com   # or 203.0.113.10.sslip.io
API_BIND=127.0.0.1                # port 8000 is then reachable only through Caddy
```

```bash
make deploy-up
curl https://api.example.com/api/health
```

Remove the port 8000 rule from the Vultr firewall group afterwards. If the certificate does not
arrive, `make deploy-logs` shows Caddy's reason; it is almost always DNS that has not propagated yet or
port 80 closed.

## 8. Database

The API uses `DATABASE_URL` when it is set and the JSON file store otherwise. `/api/health` reports
which one is live. The Postgres store applies `db/schema.sql` itself at startup; every statement in
it is idempotent.

**Tiger Data (Tiger Cloud).** Create a service in the Tiger console and paste its connection string
as `DATABASE_URL` (keep the `sslmode=require` it ends with). Then `make deploy-up`.

**Local TimescaleDB on the instance** (profile `db`). In `.env`:

```bash
POSTGRES_PASSWORD=<openssl rand -hex 24>
DATABASE_URL=postgresql://knockout:<the same password>@timescaledb:5432/knockout
```

A hex password needs no escaping inside the URL. Add `db` to `COMPOSE_PROFILES` (`db`, or `db,https`)
and run `make deploy-up`.

The database is reachable only inside the Compose network; no port is published. The `api` service
waits until it reports healthy.

## 9. Fetch.ai agents

The `agents` container runs `python -m knockout_agents.run`: all five agents in one Bureau, each with
an Agentverse mailbox, calling the API at `http://api:8000` inside the Compose network. Details of
the agents themselves are in `agents/`.

1. Put one long random seed per agent in `.env` (`AGENT_SEED_ORCHESTRATOR`, `AGENT_SEED_TARGET`,
   `AGENT_SEED_GENETICS`, `AGENT_SEED_LABEL`, `AGENT_SEED_SIGNAL`). The seed fixes the agent's
   address, so keep the same values everywhere the agents run and never commit them.
2. Put your Agentverse API key (Agentverse → Profile → API Keys) in `.env` as `AGENTVERSE_API_KEY`.
   If the containers are already running, `make deploy-up` recreates them with the new value.
3. With the containers running, connect the mailboxes once:

   ```bash
   make deploy-connect-agents
   ```

   This runs `knockout_agents.connect` inside the container, because uAgents accepts the connect call
   only from 127.0.0.1 and a request forwarded into a container never comes from there. A mailbox
   stays connected to the agent's address, so later rebuilds need no reconnect.

4. `make deploy-logs` shows each agent's address. Copy them into the top-level README.

Run the agents in one place at a time. Stop a local `make agents` before starting the container, or
the two copies compete for the same mailboxes.

## 10. Creao watch agent

In Creao, add these to the agent's Secrets:

| Secret                    | Value                                                     |
| ------------------------- | --------------------------------------------------------- |
| `KNOCKOUT_API_URL`        | `https://api.example.com` (the public HTTPS name, step 7) |
| `KNOCKOUT_WEBHOOK_SECRET` | The same value as in the server's `.env`                  |
| `OPENFDA_API_KEY`         | Your openFDA key                                          |

Check that the webhook refuses a wrong secret without storing anything (this body has no terms):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://api.example.com/api/webhooks/creao/signals \
  -H "content-type: application/json" -H "X-Knockout-Webhook-Secret: wrong" \
  -d '{"drug":"eculizumab","run_id":"auth-check","run_at":"2026-10-17T00:00:00Z","terms":[]}'
# 401; 503 means KNOCKOUT_WEBHOOK_SECRET is not set on the server
```

Add the drugs to watch: `curl -X POST https://api.example.com/api/watchlist -H "content-type: application/json" -d '{"drug":"eculizumab"}'`.

## 11. The report page on Vercel

1. Vercel → **Add New → Project** → import `dheerajkoppu/knockout`.
2. **Root Directory:** `web`. Vercel detects Next.js and pnpm (from `web/pnpm-lock.yaml`). If the
   build complains about the pnpm version, add the environment variable
   `ENABLE_EXPERIMENTAL_COREPACK=1` so Vercel uses the `packageManager` version in `package.json`.
3. **Environment Variables:**

   | Name                       | Value                                                              |
   | -------------------------- | ------------------------------------------------------------------ |
   | `NEXT_PUBLIC_API_URL`      | `https://api.example.com`, no trailing slash                       |
   | `NEXT_PUBLIC_USE_FIXTURES` | Leave unset. Fixtures are labelled development data, never results |

   For Session Replay and tracing on the page, also set `NEXT_PUBLIC_SENTRY_DSN` (the web project's
   DSN), `NEXT_PUBLIC_SENTRY_ENVIRONMENT=production` and, to join browser and API traces,
   `NEXT_PUBLIC_SENTRY_TRACE_API=true`.

4. Deploy. `NEXT_PUBLIC_*` values are compiled into the page, so redeploy after changing one.

The API already allows `https://*.vercel.app` and `http://localhost:3000`. For a custom web domain
(for example `https://knockout.example.com`), set `KNOCKOUT_ALLOWED_ORIGINS=https://knockout.example.com`
in the server's `.env` and run `make deploy-up`.

## 12. Day to day

```bash
git pull && make deploy-up                 # update; rebuilds only what changed
make deploy-logs                           # every service; or: docker compose ... logs -f api
make deploy-down                           # stop every service, profiles included; volumes stay
```

Back up the file store before experimenting:

```bash
docker run --rm -v knockout-vultr_api-store:/store -v "$PWD":/backup alpine \
  tar czf /backup/store-$(date +%Y%m%d-%H%M).tgz -C /store .
```

After judging, destroy the instance in the Vultr console if you no longer need it; a stopped
instance is still billed.

## Running it locally

Every service runs without Docker too; `make help` lists the targets.

```bash
make setup                    # .venv with Python 3.14, the package, API packages, then knockout setup
make test
make api                      # http://127.0.0.1:8000
make web                      # http://localhost:3000 against API_URL (default http://localhost:8000)
make agents                   # agents/.venv with Python 3.12
make predict DRUG=eculizumab  # also writes data/reports/eculizumab.json
make benchmark                # the protocol's scored run, reading only committed mappings
make docker-build             # both images, as the server builds them
```

## Troubleshooting

| Symptom                                                    | Cause and fix                                                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| The report page says the API did not answer                | `NEXT_PUBLIC_API_URL` is `http://` (mixed content), or the domain is not in `KNOCKOUT_ALLOWED_ORIGINS` |
| Every verdict is `unknown`, problem "Step 5 could not map" | `GEMINI_API_KEY` is empty; set it and `make deploy-up`. Cached reports with that problem rerun         |
| `"store":"files"` although `DATABASE_URL` is set           | `.env` is not in the repository root, or the container was not recreated: `make deploy-up`             |
| Caddy exits with "KNOCKOUT_DOMAIN is empty"                | Set `KNOCKOUT_DOMAIN` in `.env`; run Compose with `--env-file .env` (the `make` targets do)            |
| The webhook returns 503                                    | `KNOCKOUT_WEBHOOK_SECRET` is not set on the server                                                     |
| openFDA HTTP 429 in the logs                               | No `OPENFDA_API_KEY`, or the daily limit is used up                                                    |
| The build is killed on a small plan                        | Out of memory; add the swap file from step 3                                                           |
