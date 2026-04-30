SHELL := /bin/bash

UV ?= uv
JQ ?= jq
EVENT_COLLECTOR ?= $(UV) run event-collector
DB_INSPECT ?= $(UV) run python scripts/inspect_sqlite.py

CONFIG ?= examples/config.local.yaml
EVENT_FILE ?= examples/sample-event.json
GENERATED_EVENT_FILE ?= var/last-post-event.json
LAST_EVENT_ID_FILE ?= var/last-event-id
EVENT_ID ?=
SAMPLE_EVENT_ID ?= 3ee6c93d-1f50-4e65-a867-f2f998be9ada
DB_LIMIT ?= 20

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

.PHONY: install
install: sync ## Alias for sync.

.PHONY: test
test: ## Run tests.
	$(UV) run pytest

.PHONY: lint
lint: ## Run Ruff lint checks.
	$(UV) run ruff check .

.PHONY: format
format: ## Format code with Ruff.
	$(UV) run ruff format .

.PHONY: typecheck
typecheck: ## Run mypy.
	$(UV) run mypy src

.PHONY: check
check: lint typecheck test ## Run lint, typecheck, and tests.

.PHONY: clean
clean: ## Remove local runtime artifacts: generated events, SQLite DBs, logs, and event files.
	@set -euo pipefail; \
	if [ -f "$(PID_FILE)" ]; then \
		$(EVENT_COLLECTOR) server stop --pid-file $(PID_FILE) >/dev/null 2>&1 || true; \
	fi; \
	rm -rf $(CLEAN_PATHS); \
	printf "cleaned: %s\n" "$(CLEAN_PATHS)"

.PHONY: cli-help
cli-help: ## Show top-level event-collector CLI help.
	$(EVENT_COLLECTOR) --help

.PHONY: db-help
db-help: ## Show database/ledger command help.
	$(EVENT_COLLECTOR) db --help

.PHONY: server-help
server-help: ## Show server command help.
	$(EVENT_COLLECTOR) server --help

.PHONY: ingest-help
ingest-help: ## Show ingest command help.
	$(EVENT_COLLECTOR) ingest --help

.PHONY: events-help
events-help: ## Show event lookup command help.
	$(EVENT_COLLECTOR) events --help

.PHONY: db-init
db-init: ## Initialize the configured ingest ledger.
	@$(EVENT_COLLECTOR) db init --config $(CONFIG) | $(JQ)

.PHONY: db-path
db-path: ## Show the resolved SQLite ledger path.
	@$(DB_INSPECT) --config $(CONFIG) path | $(JQ)

.PHONY: db-counts
db-counts: ## Show SQLite event and attempt counts.
	@$(DB_INSPECT) --config $(CONFIG) counts | $(JQ)

.PHONY: db-events
db-events: ## List recent SQLite ingest events.
	@$(DB_INSPECT) --config $(CONFIG) events --limit $(DB_LIMIT) | $(JQ)

.PHONY: db-event
db-event: ## Fetch one SQLite ingest event by EVENT_ID or the last generated id.
	@event_id="$(EVENT_ID)"; \
	if [ -z "$$event_id" ]; then \
		if [ -f "$(LAST_EVENT_ID_FILE)" ]; then \
			event_id=$$(cat "$(LAST_EVENT_ID_FILE)"); \
		else \
			event_id="$(SAMPLE_EVENT_ID)"; \
		fi; \
	fi; \
	$(DB_INSPECT) --config $(CONFIG) event --event-id "$$event_id" | $(JQ)

.PHONY: db-attempts
db-attempts: ## List recent SQLite ingest attempts, optionally filtered by EVENT_ID.
	@event_id="$(EVENT_ID)"; \
	if [ -n "$$event_id" ]; then \
		$(DB_INSPECT) --config $(CONFIG) attempts --event-id "$$event_id" --limit $(DB_LIMIT) | $(JQ); \
	else \
		$(DB_INSPECT) --config $(CONFIG) attempts --limit $(DB_LIMIT) | $(JQ); \
	fi

.PHONY: db-schema
db-schema: ## Show SQLite ledger schema.
	@$(DB_INSPECT) --config $(CONFIG) schema | $(JQ)

.PHONY: server-start
server-start: ## Start the API server in the foreground.
	$(EVENT_COLLECTOR) server start --config $(CONFIG) --host $(HOST) --port $(PORT)

.PHONY: server-start-bg
server-start-bg: ## Start the API server in the background.
	@mkdir -p "$(dir $(PID_FILE))" "$(dir $(LOG_FILE))"
	@$(EVENT_COLLECTOR) server start \
		--config $(CONFIG) \
		--host $(HOST) \
		--port $(PORT) \
		--background \
		--pid-file $(PID_FILE) \
		--log-file $(LOG_FILE) | $(JQ)

.PHONY: server-status
server-status: ## Check API readiness.
	@$(EVENT_COLLECTOR) server status --url $(STATUS_URL) | $(JQ)

.PHONY: server-stop
server-stop: ## Stop the background API server.
	@$(EVENT_COLLECTOR) server stop --pid-file $(PID_FILE) | $(JQ)

.PHONY: ingest-file
ingest-file: ## Ingest EVENT_FILE directly through the CLI.
	@$(EVENT_COLLECTOR) ingest file --config $(CONFIG) --path $(EVENT_FILE) | $(JQ)

.PHONY: events-get
events-get: ## Fetch EVENT_ID, or the last generated event id, from the ingest ledger.
	@event_id="$(EVENT_ID)"; \
	if [ -z "$$event_id" ]; then \
		if [ -f "$(LAST_EVENT_ID_FILE)" ]; then \
			event_id=$$(cat "$(LAST_EVENT_ID_FILE)"); \
		else \
			event_id="$(SAMPLE_EVENT_ID)"; \
		fi; \
	fi; \
	$(EVENT_COLLECTOR) events get --config $(CONFIG) --event-id "$$event_id" | $(JQ)

.PHONY: generate-event
generate-event: ## Generate a fresh event from EVENT_FILE into GENERATED_EVENT_FILE.
	@event_id=$$($(UV) run python scripts/generate_event.py \
		--template $(EVENT_FILE) \
		--output $(GENERATED_EVENT_FILE) \
		--event-id-file $(LAST_EVENT_ID_FILE)); \
	$(JQ) -n \
		--arg event_id "$$event_id" \
		--arg event_file "$(GENERATED_EVENT_FILE)" \
		--arg event_id_file "$(LAST_EVENT_ID_FILE)" \
		'{event_id: $$event_id, event_file: $$event_file, event_id_file: $$event_id_file}'

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

.PHONY: event-file-path
event-file-path: ## Print the raw stored file path for EVENT_ID or the last generated event.
	@event_id="$(EVENT_ID)"; \
	if [ -z "$$event_id" ]; then \
		if [ -f "$(LAST_EVENT_ID_FILE)" ]; then \
			event_id=$$(cat "$(LAST_EVENT_ID_FILE)"); \
		else \
			event_id="$(SAMPLE_EVENT_ID)"; \
		fi; \
	fi; \
	record=$$($(EVENT_COLLECTOR) events get --config $(CONFIG) --event-id "$$event_id"); \
	printf '%s\n' "$$record" | $(UV) run python -c 'import json, pathlib, sys, urllib.parse; uri=json.load(sys.stdin)["storage_uri"]; parsed=urllib.parse.urlparse(uri); print(pathlib.Path(urllib.parse.unquote(parsed.path)))'

.PHONY: event-file
event-file: ## Print the raw stored event JSON for EVENT_ID or the last generated event.
	@path=$$($(MAKE) --no-print-directory event-file-path EVENT_ID="$(EVENT_ID)" CONFIG="$(CONFIG)" LAST_EVENT_ID_FILE="$(LAST_EVENT_ID_FILE)" SAMPLE_EVENT_ID="$(SAMPLE_EVENT_ID)"); \
	cat "$$path" | $(JQ)

.PHONY: redoc-url
redoc-url: ## Print the ReDoc API docs URL.
	@printf "%s/redoc\n" "$(BASE_URL)"

.PHONY: docs-url
docs-url: ## Print the Swagger UI API docs URL.
	@printf "%s/docs\n" "$(BASE_URL)"

.PHONY: openapi-url
openapi-url: ## Print the OpenAPI JSON URL.
	@printf "%s/openapi.json\n" "$(BASE_URL)"

.PHONY: smoke
smoke: ## Run a local CLI and HTTP smoke test with a temporary runtime directory.
	@set -euo pipefail; \
	tmpdir=$$(mktemp -d); \
	cleanup() { \
		if [ -f "$$tmpdir/event-collector.pid" ]; then \
			$(EVENT_COLLECTOR) server stop --pid-file "$$tmpdir/event-collector.pid" >/dev/null 2>&1 || true; \
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
	$(EVENT_COLLECTOR) server start --config "$$config" --host 127.0.0.1 --port 8929 --background --pid-file "$$tmpdir/event-collector.pid" --log-file "$$tmpdir/event-collector.log" >/dev/null; \
	ready=0; \
	for _ in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS http://127.0.0.1:8929/readyz >/dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		sleep 0.5; \
	done; \
	if [ "$$ready" != "1" ]; then \
		cat "$$tmpdir/event-collector.log" >&2; \
		exit 1; \
	fi; \
	curl -fsS http://127.0.0.1:8929/redoc >/dev/null; \
	$(UV) run python scripts/generate_event.py --template $(EVENT_FILE) --output "$$tmpdir/generated-event.json" --event-id-file "$$tmpdir/last-event-id" >/dev/null; \
	curl -fsS -X POST http://127.0.0.1:8929/v1/events -H "Content-Type: application/json" --data @"$$tmpdir/generated-event.json" >/dev/null; \
	$(EVENT_COLLECTOR) events get --config "$$config" --event-id "$$(cat "$$tmpdir/last-event-id")" >/dev/null; \
	$(EVENT_COLLECTOR) server stop --pid-file "$$tmpdir/event-collector.pid" >/dev/null; \
	trap - EXIT; \
	rm -rf "$$tmpdir"; \
	printf "smoke ok\n"
