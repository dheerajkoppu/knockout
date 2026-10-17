# Knockout. `make help` lists the targets.

PYTHON ?= python3.14
AGENTS_PYTHON ?= python3.12
VENV ?= .venv
AGENTS_VENV ?= agents/.venv
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
API_URL ?= http://localhost:$(API_PORT)
DRUG ?=
DEMO_DRUGS ?= eculizumab ibrutinib ruxolitinib
PROFILES ?=

VENV_PYTHON := $(VENV)/bin/python
AGENTS_VENV_PYTHON := $(AGENTS_VENV)/bin/python

ENV_FILE := $(wildcard .env)
COMPOSE = docker compose $(if $(ENV_FILE),--env-file .env) -f deploy/docker-compose.vultr.yml $(foreach profile,$(PROFILES),--profile $(profile))

export SENTRY_RELEASE ?= knockout@$(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)

.DEFAULT_GOAL := help
.PHONY: help setup test lint api web agents agents-setup agents-connect predict benchmark benchmark-mappings benchmark-drug-set \
	docker-build deploy-up deploy-down deploy-logs deploy-ps deploy-connect-agents health warm

help:
	@echo "Local"
	@echo "  make setup                 venv in $(VENV), the package and API extras, then 'knockout setup'"
	@echo "  make test                  pytest"
	@echo "  make lint                  ruff"
	@echo "  make api                   API with reload on http://$(API_HOST):$(API_PORT)"
	@echo "  make web                   report page on http://localhost:3000 against API_URL=$(API_URL)"
	@echo "  make agents                Fetch.ai agents (Python 3.12, own venv in $(AGENTS_VENV))"
	@echo "  make agents-connect        connect the running agents to Agentverse mailboxes (AGENTVERSE_API_KEY)"
	@echo "  make predict DRUG=name     one report, saved to data/reports/<name>.json"
	@echo "  make benchmark             scored run on benchmark/drug_set.json, reading only committed mappings"
	@echo "  make benchmark-mappings    map every phenotype the benchmark needs with Gemini, then score"
	@echo "  make benchmark-drug-set    regenerate benchmark/drug_set.json (the protocol freezes it)"
	@echo "Docker and Vultr (see deploy/README.md)"
	@echo "  make docker-build          build the api and agents images"
	@echo "  make deploy-up             start them; COMPOSE_PROFILES in .env (or PROFILES=\"db https\") adds TimescaleDB and Caddy"
	@echo "  make deploy-logs | deploy-ps | deploy-down"
	@echo "  make deploy-connect-agents connect the agents container to Agentverse mailboxes"
	@echo "  make health | warm         check API_URL, or run the demo drugs ($(DEMO_DRUGS)) once"

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

setup: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable ".[dev,api]"
	$(VENV)/bin/knockout setup

test:
	$(VENV_PYTHON) -m pytest -q

lint:
	$(VENV)/bin/ruff check src tests benchmark creao agents/knockout_agents agents/tests

api:
	$(VENV)/bin/uvicorn knockout.api:app --reload --host $(API_HOST) --port $(API_PORT)

web:
	cd web && (test -d node_modules || pnpm install --frozen-lockfile) \
		&& NEXT_PUBLIC_API_URL="$${NEXT_PUBLIC_API_URL:-$(API_URL)}" pnpm dev

agents/requirements.txt:
	@echo "agents/requirements.txt is missing; the agents workstream writes it"; exit 1

$(AGENTS_VENV)/.installed: agents/requirements.txt
	test -x $(AGENTS_VENV_PYTHON) || $(AGENTS_PYTHON) -m venv $(AGENTS_VENV)
	$(AGENTS_VENV_PYTHON) -m pip install -r agents/requirements.txt
	touch $@

agents-setup: $(AGENTS_VENV)/.installed

agents: $(AGENTS_VENV)/.installed
	cd agents && KNOCKOUT_API_URL="$${KNOCKOUT_API_URL:-$(API_URL)}" $(CURDIR)/$(AGENTS_VENV_PYTHON) -m knockout_agents.run

agents-connect: $(AGENTS_VENV)/.installed
	cd agents && $(CURDIR)/$(AGENTS_VENV_PYTHON) -m knockout_agents.connect

predict:
	@test -n "$(DRUG)" || { echo "usage: make predict DRUG=eculizumab"; exit 2; }
	$(VENV)/bin/knockout predict "$(DRUG)" --json "data/reports/$(DRUG).json"

benchmark-drug-set:
	$(VENV_PYTHON) -m benchmark.drug_set

benchmark:
	test -f benchmark/drug_set.json || $(VENV_PYTHON) -m benchmark.drug_set
	$(VENV_PYTHON) -m benchmark.score

benchmark-mappings:
	$(VENV_PYTHON) -m benchmark.score --generate-mappings

docker-build:
	$(COMPOSE) build

deploy-up:
	$(COMPOSE) up -d --build

deploy-down:
	$(COMPOSE) --profile "*" down

deploy-logs:
	$(COMPOSE) logs --follow --tail 200

deploy-ps:
	$(COMPOSE) ps

deploy-connect-agents:
	$(COMPOSE) exec agents python -m knockout_agents.connect

health:
	curl -fsS "$(API_URL)/api/health"
	@echo

warm:
	@for drug in $(DEMO_DRUGS); do \
		echo "$$drug"; \
		curl -fsS --max-time 900 -o /dev/null -w "  HTTP %{http_code} in %{time_total}s\n" "$(API_URL)/api/drugs/$$drug/report" \
			|| echo "  failed"; \
	done
