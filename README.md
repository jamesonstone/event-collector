# event-collector

Generic Event Collector for event-based architectures.

`event-collector` accepts application fact events, validates a generic envelope, enforces
idempotency, writes raw immutable event objects, and records ingest state in a local ledger.

It is intentionally domain-neutral. It validates and stores opaque event envelopes without
applying business-specific rules.

🧰 Crafted with [kit](https://github.com/jamesonstone/kit)

## Core Semantics

```text
event received
  -> validate envelope
  -> verify payload/event hashes
  -> check event_id idempotency
  -> write raw event object
  -> mark ingest ledger stored
  -> acknowledge
```

Rules:

- same `event_id` + same `event_sha256` = duplicate success
- same `event_id` + different `event_sha256` = `409 hash_conflict`
- the raw event object is written before the collector acknowledges success
- the SQLite ledger is an ingest/index ledger, not the raw event archive

## Install

```bash
python -m pip install -e ".[dev]"
```

The package requires Python 3.12 or newer.

## Quickstart

```bash
event-collector db init --config examples/config.local.yaml

event-collector server start --config examples/config.local.yaml
```

In another terminal:

```bash
curl -sS -X POST \
  http://127.0.0.1:8920/v1/events \
  -H 'Content-Type: application/json' \
  --data @examples/sample-event.json
```

API docs are available at:

- Swagger UI: `http://127.0.0.1:8920/docs`
- ReDoc: `http://127.0.0.1:8920/redoc`
- OpenAPI JSON: `http://127.0.0.1:8920/openapi.json`

## Programmatic Runtime

The service can be started and stopped through the CLI:

```bash
event-collector server start \
  --config /abs/path/config.yaml \
  --host 127.0.0.1 \
  --port 8920 \
  --background \
  --pid-file /abs/path/event-collector.pid \
  --log-file /abs/path/event-collector.log

event-collector server status --url http://127.0.0.1:8920/readyz

event-collector server stop --pid-file /abs/path/event-collector.pid
```

## Make Commands

The repository also exposes the CLI and development workflow through `make`:

```bash
make help
make sync
make check
make clean
make db-init
make server-start
make server-start-bg
make server-status
make ingest-file
make generate-event
make events-get
make db-path
make db-counts
make db-events
make db-event
make db-attempts
make db-schema
make post-event
make event-file-path
make event-file
make server-stop
make smoke
```

Common variables are overridable:

```bash
make server-start-bg CONFIG=/abs/config.yaml HOST=127.0.0.1 PORT=8920
make ingest-file EVENT_FILE=/abs/event.json
make post-event EVENT_FILE=/abs/template-event.json
make events-get EVENT_ID=3ee6c93d-1f50-4e65-a867-f2f998be9ada
make db-events DB_LIMIT=50
make db-event EVENT_ID=3ee6c93d-1f50-4e65-a867-f2f998be9ada
```

`make post-event` generates a fresh event before posting it. The generated request is written
to `var/last-post-event.json`, and its id is written to `var/last-event-id`. That makes the
end-to-end loop repeatable:

```bash
make post-event
make events-get
make db-event
make event-file
```

JSON-producing Make targets are piped through `jq` for readability.

## Config

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

Relative `ledger.path` and `storage.root` values are resolved relative to the config file.

## Event Envelope

Minimum required fields:

```json
{
  "event_id": "3ee6c93d-1f50-4e65-a867-f2f998be9ada",
  "event_name": "example.order.created",
  "event_version": "1.0",
  "producer_service": "example-service",
  "occurred_at": "2026-04-30T12:00:00Z",
  "payload_sha256": "e115e781afebb0afae51c4f7b6b4225c851ffb0a60292ac735c8c2e7887ea937",
  "event_sha256": "4ad2a47ca6b2690eb052cf3dcedb97f0482b0c808e034c006fbb99859514f265",
  "payload": {
    "order_id": "ORD-001",
    "status": "created"
  }
}
```

`payload_sha256` is the SHA-256 hash of canonical JSON for `payload`.

`event_sha256` is the SHA-256 hash of canonical JSON for the full envelope excluding the
`event_sha256` field itself.

## HTTP API

```text
GET  /healthz
GET  /readyz
POST /v1/events
POST /v1/events:batch
GET  /v1/events/{event_id}
```

## CLI

```bash
event-collector db init --config examples/config.local.yaml
event-collector server start --config examples/config.local.yaml
event-collector ingest file --config examples/config.local.yaml --path examples/sample-event.json
event-collector events get --config examples/config.local.yaml --event-id 3ee6c93d-1f50-4e65-a867-f2f998be9ada
```

## Storage Layout

Filesystem storage writes raw canonical event JSON to:

```text
<storage.root>/raw/
  producer_service=<producer_service>/
  event_date=YYYY-MM-DD/
  event_name=<event_name>/
  event_id=<event_id>.json
```

## Development

```bash
pytest
ruff check .
mypy src
```

## 👤 Maintainer

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/jamesonstone">
        <img src="https://github.com/jamesonstone.png" width="100px;" alt="Jameson Stone"/>
        <br />
        <sub><b>Jameson Stone</b></sub>
      </a>
      <br />
      <sub>Lead Maintainer</sub>
    </td>
  </tr>
</table>
