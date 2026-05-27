# Debug Correlation Tools Plan

## Approach

- Keep the implementation in `src/event_collector/api/routes.py` because this is a
  debug-page enhancement, not a core ingest-service change.
- Extend `DebugEventBus` history from 200 to 1000 recent debug events.
- Keep stream fanout non-blocking and bounded.
- Implement filtering and copy in the `/debug` page JavaScript against the stream replay.
- Add a manual refresh control that reads the current debug buffer without adding public APIs.
- Add an open/collapse control for all visible event panels.
- Keep copied data as a JSON array of `message.event` values.
- Update README and constitution constraints to document the debug-only boundary.

## Validation

- Run `make check`.
- Run `make smoke`.
- Run `git diff --check`.
- Verify `/debug` in a browser with `EC_ENV=debug`, posted events, correlation filtering,
  time filtering, open/collapse behavior, and JSON copy controls.
