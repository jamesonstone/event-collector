# Debug Correlation Tools Spec

## Purpose

Add lightweight debug-only visibility controls for recent event streams without expanding the
stable ingest API or adding persisted query behavior.

## Requirements

- Keep all new controls gated behind `EC_ENV=debug`.
- Keep `/debug` as a browser-readable operational page.
- Preserve `/debug/stream` as the raw newline-delimited JSON stream.
- Use recent in-memory debug history as the only data source for selection and copy.
- Increase debug history to 1000 recent events for the current server process.
- Allow operators to filter visible debug events by `correlation_id`.
- Allow operators to filter visible debug events by collector stream time.
- Allow operators to manually refresh visible debug events from the current in-memory buffer.
- Allow operators to open and collapse all visible debug event panels.
- Allow operators to copy matching canonical event envelopes as a JSON array.
- Keep debug streaming cancellation-friendly so server shutdown does not require repeated
  interrupts.
- Do not add public `/v1` query or export endpoints.
- Do not add SQLite schema changes, migrations, or persisted query behavior.
- Avoid domain-specific terminology in user-facing labels, routes, code, and docs.

## Acceptance

- With `EC_ENV` unset, `/debug` and `/debug/stream` remain inaccessible.
- With `EC_ENV=debug`, `/debug` exposes compact controls for `correlation_id`, `from`, `to`,
  `Refresh`, `Open`/`Collapse`, and `Copy JSON`.
- The default time window tracks the last 15 minutes until either time field is manually edited.
- Copy output contains canonical event envelopes only, not debug wrapper metadata.
- Clipboard failure exposes a textarea fallback.
- Existing ingest, storage, idempotency, Swagger, ReDoc, and smoke behavior continue to pass.
