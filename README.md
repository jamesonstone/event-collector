```text
███████╗██╗   ██╗███████╗███╗   ██╗████████╗
██╔════╝██║   ██║██╔════╝████╗  ██║╚══██╔══╝
█████╗  ██║   ██║█████╗  ██╔██╗ ██║   ██║
██╔══╝  ╚██╗ ██╔╝██╔══╝  ██║╚██╗██║   ██║
███████╗ ╚████╔╝ ███████╗██║ ╚████║   ██║
╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═══╝   ╚═╝

 ██████╗ ██████╗ ██╗     ██╗     ███████╗ ██████╗████████╗ ██████╗ ██████╗
██╔════╝██╔═══██╗██║     ██║     ██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗
██║     ██║   ██║██║     ██║     █████╗  ██║        ██║   ██║   ██║██████╔╝
██║     ██║   ██║██║     ██║     ██╔══╝  ██║        ██║   ██║   ██║██╔══██╗
╚██████╗╚██████╔╝███████╗███████╗███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║
 ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝

                                                generic event collection
```

**`event-collector` is a tiny HTTP service and CLI for collecting generic event
envelopes.** It validates hashes, enforces `event_id` idempotency, writes raw
immutable JSON objects, and records ingest state in a local SQLite ledger.

No business-specific rules. No workflow semantics. Just durable collection for
application fact streams.

🧰 Crafted with [kit](https://github.com/jamesonstone/kit)

## Install

```sh
git clone https://github.com/jamesonstone/event-collector.git
cd event-collector
uv sync --extra dev
uv run event-collector --help
```

For an editable Python install:

```sh
python -m pip install -e ".[dev]"
event-collector --help
```

## Quick Start

```sh
# initialize the local SQLite ingest ledger
make db-init

# run the HTTP API on 127.0.0.1:8920
make run
```

In another terminal:

```sh
# generate and POST a fresh sample event
make post-event

# inspect the stored event through the CLI
uv run event-collector events get \
  --config examples/config.local.yaml \
  --event-id "$(cat var/last-event-id)"
```

`make post-event` writes the generated request to `var/last-post-event.json` and
the last event id to `var/last-event-id`.

API docs are served from the running API:

- Swagger UI: `http://127.0.0.1:8920/`
- ReDoc: `http://127.0.0.1:8920/redoc`
- OpenAPI JSON: `http://127.0.0.1:8920/openapi.json`

`/docs` is intentionally not registered; Swagger lives at the root URL.

## Behavior

- `POST /v1/events` accepts one event envelope.
- `POST /v1/events:batch` accepts multiple event envelopes.
- `GET /v1/events/{event_id}` returns the ingest ledger record and raw envelope.
- `GET /healthz` and `GET /readyz` expose process and storage readiness.
- Same `event_id` plus same `event_sha256` is treated as duplicate success.
- Same `event_id` plus different `event_sha256` or `payload_sha256` returns
  `409 hash_conflict`.
- Hash validation failures return `422`.
- Raw event JSON is written before success is acknowledged.
- SQLite is an ingest/index ledger, not the raw event archive.

Filesystem storage writes canonical event JSON under:

```text
<storage.root>/raw/
  producer_service=<producer_service>/
  event_date=YYYY-MM-DD/
  event_name=<event_name>/
  event_id=<event_id>.json
```

For deeper SQLite inspection, run `uv run python scripts/inspect_sqlite.py --help`.

## Debug

`GET /debug` opens a compact browser page for watching raw submitted events as
they pass through the collector. It consumes `GET /debug/stream`, a
newline-delimited JSON stream that can also be watched from a terminal.

The debug endpoint is disabled by default. It is registered only when the server
starts with `EC_ENV=debug`; otherwise `/debug` and `/debug/stream` return `404`
and are omitted from Swagger/OpenAPI.

```sh
EC_ENV=debug make run
```

```sh
curl -N http://127.0.0.1:8920/debug/stream | jq
```

The debug page keeps the most recent 1000 debug events in memory for the current
server process. It can filter by `correlation_id`, filter by stream time,
refresh from the in-memory buffer, open or collapse all visible event panels,
and copy matching canonical event envelopes as a JSON array.

Manual refresh uses the hidden `GET /debug/history` route. Like the stream, it
is registered only when `EC_ENV=debug`, is omitted from OpenAPI, and is not a
public query/export API. In debug mode, long-lived stream connections are
cancelled during shutdown so one interrupt can stop the server cleanly.

## Configuration

```yaml
server:
  host: 127.0.0.1
  port: 8920

ledger:
  adapter: sqlite
  path: ./var/ingest.sqlite

storage:
  adapter: filesystem
  root: ./var/event-lake

ingest:
  reject_hash_conflicts: true
  require_payload_hash: true
  require_event_hash: true
```

Relative `ledger.path` and `storage.root` values are resolved relative to the
config file.

## Event Envelope

```json
{
  "event_id": "3ee6c93d-1f50-4e65-a867-f2f998be9ada",
  "event_name": "example.order.created",
  "event_version": "1.0",
  "producer_service": "example-service",
  "producer_instance": "local-dev-1",
  "producer_deployment": "local",
  "occurred_at": "2026-04-30T12:00:00Z",
  "observed_at": "2026-04-30T12:00:01Z",
  "partition_id": "example-account",
  "subject_type": "order",
  "subject_id": "ORD-001",
  "aggregate_type": "order",
  "aggregate_id": "ORD-001",
  "correlation_id": "corr-001",
  "causation_id": "cmd-001",
  "actor": {
    "type": "user",
    "id": "user-001"
  },
  "payload": {
    "order_id": "ORD-001",
    "status": "created"
  },
  "payload_sha256": "e115e781afebb0afae51c4f7b6b4225c851ffb0a60292ac735c8c2e7887ea937",
  "event_sha256": "4ad2a47ca6b2690eb052cf3dcedb97f0482b0c808e034c006fbb99859514f265"
}
```

`payload_sha256` is the SHA-256 hash of canonical JSON for `payload`.
`event_sha256` is the SHA-256 hash of canonical JSON for the full envelope
excluding the `event_sha256` field itself.

## Make targets

The Makefile intentionally wraps only the common day-to-day workflows. Run
`make help` for the live list.

### Everyday workflow

- `make sync` — install runtime and dev dependencies with `uv`
- `make db-init` — initialize the configured SQLite ingest ledger
- `make run` — start the API in the foreground
- `make run-bg` — start the API in the background
- `make status` — check readiness at `STATUS_URL`
- `make stop` — stop the background API server
- `make post-event` — generate and POST a fresh sample event
- `make clean` — remove local runtime artifacts

### Quality checks

- `make format` — format the codebase with Ruff
- `make lint` — run Ruff lint checks
- `make typecheck` — run mypy
- `make test` — run pytest
- `make check` — run lint, typecheck, and tests
- `make smoke` — run a local CLI and HTTP smoke test

Common variables are overridable:

```sh
make run-bg CONFIG=/abs/config.yaml HOST=127.0.0.1 PORT=8920
make status STATUS_URL=http://127.0.0.1:8920/readyz
make stop PID_FILE=/abs/path/event-collector.pid
make post-event EVENT_FILE=/abs/template-event.json
make post-event BASE_URL=http://127.0.0.1:8920
```

### Advanced CLI and SQLite inspection

For lower-frequency inspection and debugging, use the CLI directly instead of
additional Make wrappers:

```sh
uv run event-collector --help
uv run event-collector events get --config examples/config.local.yaml --event-id "$(cat var/last-event-id)"
uv run python scripts/inspect_sqlite.py --config examples/config.local.yaml events --limit 20 | jq
```

JSON-producing Make targets are piped through `jq` for readability.

## Requirements

- Python 3.12+
- `uv`
- `jq` for readable Make target output
- SQLite for the local ingest ledger
- Filesystem storage for raw event objects

## Development

```sh
make sync
make format
make check
make smoke
```

The project intentionally stays small: FastAPI, Typer, SQLite, filesystem
storage, and generic event-envelope validation.

## 👤 Maintainer

- [Jameson Stone](https://github.com/jamesonstone) — Lead Maintainer
