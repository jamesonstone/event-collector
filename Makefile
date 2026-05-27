SHELL := /bin/bash

UV ?= uv
JQ ?= jq
EVENT_COLLECTOR ?= $(UV) run event-collector

CONFIG ?= examples/config.local.yaml
EVENT_FILE ?= examples/sample-event.json
GENERATED_EVENT_FILE ?= var/last-post-event.json
LAST_EVENT_ID_FILE ?= var/last-event-id

HOST ?= 127.0.0.1
PORT ?= 8920
BASE_URL ?= http://$(HOST):$(PORT)
STATUS_URL ?= $(BASE_URL)/readyz

PID_FILE ?= var/event-collector.pid
LOG_FILE ?= var/event-collector.log
CLEAN_PATHS ?= var examples/var

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available Make targets.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make <target> [VAR=value]\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: sync
sync: ## Install runtime and dev dependencies with uv.
	$(UV) sync --extra dev

.PHONY: format
format: ## Format code with Ruff.
	$(UV) run ruff format .

.PHONY: lint
lint: ## Run Ruff lint checks.
	$(UV) run ruff check .

.PHONY: typecheck
typecheck: ## Run mypy.
	$(UV) run mypy src

.PHONY: test
test: ## Run tests.
	$(UV) run pytest

.PHONY: check
check: lint typecheck test ## Run lint, typecheck, and tests.

.PHONY: clean
clean: ## Remove local runtime artifacts: generated events, SQLite DBs, logs, and event files.
	@set -euo pipefail; \
	if [ -f "$(PID_FILE)" ]; then \
		$(MAKE) --no-print-directory stop PID_FILE="$(PID_FILE)" >/dev/null 2>&1 || true; \
	fi; \
	rm -rf $(CLEAN_PATHS); \
	printf "cleaned: %s\n" "$(CLEAN_PATHS)"

.PHONY: db-init
db-init: ## Initialize the configured ingest ledger.
	@$(EVENT_COLLECTOR) db init --config $(CONFIG) | $(JQ)

.PHONY: run
run: ## Start the API server in the foreground.
	$(EVENT_COLLECTOR) server start --config $(CONFIG) --host $(HOST) --port $(PORT)

.PHONY: run-bg
run-bg: ## Start the API server in the background.
	@mkdir -p "$(dir $(PID_FILE))" "$(dir $(LOG_FILE))"
	@$(EVENT_COLLECTOR) server start \
		--config $(CONFIG) \
		--host $(HOST) \
		--port $(PORT) \
		--background \
		--pid-file $(PID_FILE) \
		--log-file $(LOG_FILE) | $(JQ)

.PHONY: status
status: ## Check API readiness.
	@$(EVENT_COLLECTOR) server status --url $(STATUS_URL) | $(JQ)

.PHONY: stop
stop: ## Stop the background API server.
	@$(EVENT_COLLECTOR) server stop --pid-file $(PID_FILE) | $(JQ)

.PHONY: post-event
post-event: ## Generate and POST a fresh event to the running HTTP API.
	@$(UV) run python scripts/generate_event.py \
		--template $(EVENT_FILE) \
		--output $(GENERATED_EVENT_FILE) \
		--event-id-file $(LAST_EVENT_ID_FILE) >/dev/null
	@response=$$(curl -fsS -X POST "$(BASE_URL)/v1/events" \
		-H "Content-Type: application/json" \
		--data @$(GENERATED_EVENT_FILE)); \
	printf '%s\n' "$$response" | $(JQ) \
		--arg generated_event_file "$(GENERATED_EVENT_FILE)" \
		--arg last_event_id_file "$(LAST_EVENT_ID_FILE)" \
		'. + {generated_event_file: $$generated_event_file, last_event_id_file: $$last_event_id_file}'

.PHONY: smoke
smoke: ## Run a local CLI and HTTP smoke test with a temporary runtime directory.
	@set -euo pipefail; \
	tmpdir=$$(mktemp -d); \
	cleanup() { \
		if [ -f "$$tmpdir/event-collector.pid" ]; then \
			$(MAKE) --no-print-directory stop PID_FILE="$$tmpdir/event-collector.pid" >/dev/null 2>&1 || true; \
		fi; \
		rm -rf "$$tmpdir"; \
	}; \
	trap cleanup EXIT; \
	config="$$tmpdir/config.yaml"; \
	printf '%s\n' \
		'server:' \
		'  host: 127.0.0.1' \
		'  port: 8929' \
		'ledger:' \
		'  adapter: sqlite' \
		"  path: $$tmpdir/ingest.sqlite" \
		'storage:' \
		'  adapter: filesystem' \
		"  root: $$tmpdir/event-lake" \
		'ingest:' \
		'  reject_hash_conflicts: true' \
		'  require_payload_hash: true' \
		'  require_event_hash: true' \
		> "$$config"; \
	$(EVENT_COLLECTOR) db init --config "$$config" >/dev/null; \
	$(EVENT_COLLECTOR) ingest file --config "$$config" --path $(EVENT_FILE) >/dev/null; \
	$(MAKE) --no-print-directory run-bg CONFIG="$$config" HOST=127.0.0.1 PORT=8929 PID_FILE="$$tmpdir/event-collector.pid" LOG_FILE="$$tmpdir/event-collector.log" >/dev/null; \
	ready=0; \
	for _ in 1 2 3 4 5 6 7 8 9 10; do \
		if $(MAKE) --no-print-directory status STATUS_URL="http://127.0.0.1:8929/readyz" >/dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		sleep 0.5; \
	done; \
	if [ "$$ready" != "1" ]; then \
		cat "$$tmpdir/event-collector.log" >&2; \
		exit 1; \
	fi; \
	curl -fsS http://127.0.0.1:8929/ >/dev/null; \
	curl -fsS http://127.0.0.1:8929/redoc >/dev/null; \
	$(UV) run python scripts/generate_event.py --template $(EVENT_FILE) --output "$$tmpdir/generated-event.json" --event-id-file "$$tmpdir/last-event-id" >/dev/null; \
	curl -fsS -X POST http://127.0.0.1:8929/v1/events -H "Content-Type: application/json" --data @"$$tmpdir/generated-event.json" >/dev/null; \
	$(EVENT_COLLECTOR) events get --config "$$config" --event-id "$$(cat "$$tmpdir/last-event-id")" >/dev/null; \
	$(MAKE) --no-print-directory stop PID_FILE="$$tmpdir/event-collector.pid" >/dev/null; \
	trap - EXIT; \
	rm -rf "$$tmpdir"; \
	printf "smoke ok\n"
