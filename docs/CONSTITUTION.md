# CONSTITUTION

## Purpose

This document is the canonical project contract for `event-collector`. It defines the development rules, implementation invariants, operating strategy, and long-term direction that all future work must preserve.

`event-collector` is a domain-neutral collector for immutable application fact events. It accepts generic event envelopes, validates envelope integrity, enforces idempotency, writes raw canonical event objects, and records ingest state in a local ledger.

## Core Principles

- Preserve domain neutrality. The collector validates envelope shape and integrity, but it does not apply application-specific business rules to payload contents.
- Treat events as immutable facts. Once accepted, the raw canonical event object is an append-only archive artifact, not mutable application state.
- Acknowledge only after durability. The raw event object must be written before any successful ingest response is returned.
- Keep the ledger and archive separate. The ledger is an ingest/index ledger; the raw event object store is the source for archived event contents.
- Make idempotency explicit. Replays with identical `event_id` and content hash are successful duplicates; reused ids with different content are conflicts.
- Prefer small, composable layers over framework-coupled logic. Business behavior belongs in services, not HTTP route handlers, CLI handlers, storage adapters, or ledger adapters.
- Keep adapters replaceable. Storage and ledger integrations must sit behind narrow protocols so additional implementations can be added without changing ingest semantics.
- Keep configuration external. Runtime paths, adapters, host/port, and ingest flags are configuration, not hardcoded behavior.
- Make validation failures clear. Invalid hashes, conflicts, config errors, storage errors, and not-found cases must surface as specific errors or response statuses.
- Keep repo-local documentation current. When implementation reality changes, update the affected docs before considering the work complete.

## Current Architecture

### Runtime Flow

The core ingest path is:

1. receive an event envelope through HTTP or CLI
2. validate the Pydantic envelope model
3. verify `payload_sha256` against canonical payload JSON when enabled
4. verify `event_sha256` against canonical event JSON excluding `event_sha256` when enabled
5. look up `event_id` in the ingest ledger
6. return duplicate success for same id and same hashes
7. return or raise hash conflict for same id and different hashes
8. insert a received ledger row for new events
9. write canonical raw event JSON to storage
10. mark the ledger row stored and record an ingest attempt
11. return the ingest result

### Layers

- `src/event_collector/api/schemas.py` defines external request and response contracts with Pydantic.
- `src/event_collector/api/routes.py` adapts HTTP requests to the ingest service and maps domain errors to HTTP statuses.
- `src/event_collector/api/routes.py` also owns the optional debug page, debug stream route, and in-memory fanout used only when `EC_ENV=debug`.
- `src/event_collector/cli.py` adapts command-line commands to the same service path used by HTTP.
- `src/event_collector/ingest/service.py` owns core ingest orchestration and idempotency behavior.
- `src/event_collector/ledger/base.py` defines the ledger protocol.
- `src/event_collector/ledger/sqlite.py` implements the current SQLite ledger adapter.
- `src/event_collector/storage/base.py` defines the storage protocol.
- `src/event_collector/storage/filesystem.py` implements the current filesystem raw-event adapter.
- `src/event_collector/main.py` is the FastAPI app factory and dependency wiring point.
- `src/event_collector/config.py` owns YAML config loading, validation, and relative path resolution.
- `src/event_collector/hashing.py` owns canonical JSON and SHA-256 helpers.
- `src/event_collector/errors.py` owns domain-specific exception types.
- `scripts/` contains development and inspection utilities, not core runtime behavior.
- `tests/` covers API, CLI, hashing, idempotency, storage, and conflict behavior.

### Dependency Injection

- The app factory creates concrete adapters and injects them into `IngestService`.
- HTTP handlers retrieve the configured service from `app.state`.
- CLI commands build the same service from config.
- New ledger or storage implementations must satisfy the existing protocol before being wired into config.

### Data Model Boundaries

- Use Pydantic models for external API/config boundaries.
- Use frozen dataclasses for internal result and record snapshots.
- Use SQLAlchemy ORM models only inside the SQLite ledger adapter.
- Do not leak ORM rows across service, API, or CLI boundaries.

## Non-Negotiable Runtime Constraints

- `event_id` is a UUID and is normalized with `str(UUID)`.
- `payload_sha256` and `event_sha256` must be 64-character lowercase SHA-256 hex strings.
- `occurred_at` and `observed_at` values must include timezone information.
- `event_name` must not contain `/` or `\`.
- Event envelope extra fields are forbidden unless the schema is intentionally expanded.
- Canonical JSON must use sorted keys, compact separators, UTF-8, and `ensure_ascii=False`.
- Raw stored event JSON must be canonical event JSON with a trailing newline.
- `event_sha256` is computed from canonical event JSON with `event_sha256` excluded.
- `payload_sha256` is computed from canonical payload JSON.
- Same `event_id` plus same `event_sha256` and `payload_sha256` is duplicate success.
- Same `event_id` plus different `event_sha256` or `payload_sha256` is a hash conflict.
- Default ingest behavior rejects hash conflicts.
- The single-event HTTP endpoint maps hash conflicts to `409`, hash validation failures to `422`, storage failures to `500`, and missing events to `404`.
- Batch ingest returns per-event results and must not let one conflicting event prevent independent events in the batch from being reported.
- The raw event object must be written before a success acknowledgement.
- Swagger UI is served from `/`; `/docs` is not a supported docs route.
- The `/debug` page and `/debug/stream` must only be registered when `EC_ENV` exactly equals `debug`.
- When debug mode is disabled, debug routes must be inaccessible and omitted from OpenAPI/Swagger.
- `/debug` must be a finite browser-readable page, not the never-ending raw stream response.
- Debug streaming must not block event ingestion; slow debug consumers may miss messages.
- Debug streaming must shut down cleanly without requiring repeated interrupts.
- Debug filtering and bulk copy are bounded in-memory visibility tools and must not create a public event-query API by accident.
- Filesystem storage must be idempotent for identical existing content and reject different existing content.
- Filesystem path segments must be sanitized before writing.
- SQLite remains an ingest/index ledger and must not be treated as the raw event archive.
- Relative `ledger.path` and `storage.root` values resolve relative to the config file.
- Current supported adapters are `sqlite` for ledger and `filesystem` for storage.
- Health checks must remain cheap; readiness checks must verify ledger and storage availability.

## Code Style and Naming Conventions

- Target Python 3.12 or newer.
- Keep `from __future__ import annotations` in Python modules.
- Use full type hints and keep `mypy` strict mode passing.
- Format and lint with Ruff using the repository settings.
- Keep line length at or below 100 characters unless readability clearly improves otherwise.
- Use `snake_case` for modules, functions, methods, variables, and config keys.
- Use `PascalCase` for classes and dataclasses.
- Use uppercase names for constants.
- Use leading underscores for private helpers.
- Keep modules focused around one responsibility.
- Prefer protocol interfaces for adapter seams.
- Prefer explicit domain exceptions over generic exceptions.
- Keep route handlers and CLI commands thin.
- Keep comments rare; use docstrings or self-explanatory names first.
- Add public exports only when there is a concrete external use.
- Remove dead code, unused exports, and unnecessary public surface area.
- Prefer deterministic output for CLI and scripts, especially JSON output used by Make targets.

## Dependency Purposes

### Runtime

- `fastapi` provides HTTP routing, request validation integration, Swagger UI, ReDoc, and OpenAPI JSON.
- `uvicorn[standard]` serves the FastAPI app.
- `pydantic` validates API schemas and runtime configuration.
- `PyYAML` loads YAML config files.
- `SQLAlchemy` implements the SQLite ingest ledger.
- `typer` provides the command-line interface.
- `httpx` supports HTTP client behavior used by FastAPI testing and local workflows.

### Development

- `pytest` runs the test suite.
- `ruff` handles linting and formatting.
- `mypy` enforces static typing.
- `types-PyYAML` provides type information for YAML usage.
- `hatchling` builds the package.
- `uv` is the expected dependency and command runner.
- `jq` is used by Make targets to format JSON output.
- `curl` is used by local HTTP smoke and post-event workflows.

## Build, Test, and Tooling Strategy

- Use `make` targets as the preferred development interface.
- `make sync` installs runtime and dev dependencies with `uv`.
- `make test` runs `pytest`.
- `make lint` runs `ruff check .`.
- `make format` runs `ruff format .`.
- `make typecheck` runs `mypy src`.
- `make check` runs lint, typecheck, and tests.
- `make smoke` exercises local CLI ingest, HTTP startup, API docs, event post, event lookup, and shutdown.
- Runtime artifacts belong under `var/` or another ignored local path.
- Do not claim validation passed unless the command actually ran.
- If validation cannot run, record the exact blocker.

## Documentation and Process Rules

### Source of Truth

Authority order:

1. safety and permission constraints
2. current user request
3. this constitution
4. feature `SPEC.md`
5. feature `PLAN.md`
6. feature `TASKS.md`
7. feature `BRAINSTORM.md`
8. repository conventions

Execution order for feature work:

1. current `TASKS.md` item
2. relevant `PLAN.md` section
3. relevant `SPEC.md` requirement
4. this constitution when invariants are needed

### Repository Instruction Entrypoints

- `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` are routing files, not the full manual.
- Start with `docs/agents/README.md`.
- Load only the specific `docs/agents/*`, `docs/specs/*`, and `docs/references/*` artifacts needed for the immediate decision.
- Repo-local docs under `docs/` are primary.
- Documented global inputs are secondary after repo-local docs are exhausted.
- Do not create an always-loaded monolithic instruction file.

### Feature Documentation

- Feature-scoped source-of-truth artifacts live under `docs/specs/<feature>/`.
- Do not mix multiple features in one feature directory.
- Formal feature work uses optional `BRAINSTORM.md`, then `SPEC.md`, `PLAN.md`, `TASKS.md`, implementation, validation, and reflection.
- For feature-scoped work, read that feature's `SPEC.md` `## SKILLS` table first.
- Open each referenced `SKILL.md` and use only the skills needed for execution.
- Keep dependency, relationship, and skills sections current when feature docs are touched.
- If implementation changes behavior, requirements, or approach, update canonical docs first.
- `PROJECT_PROGRESS_SUMMARY.md` must reflect the highest completed artifact per feature at all times. If the repository stores this index under `docs/PROJECT_PROGRESS_SUMMARY.md`, that path satisfies the same rule.

### RLM and Context Loading

- Use RLM-style progressive disclosure when full-context loading would be noisy.
- Identify the immediate decision before opening another file.
- Prefer a specific section over a full file.
- Prefer the current feature over all features.
- Prefer explicit dependency links over broad search.
- Stop loading once the decision is supported.
- Inspect at most five prior feature directories before narrowing further or asking for clarification.

### Change Classification

Classify work before acting.

#### Spec-Driven

Use this track for:

- new features
- substantial behavioral changes
- substantial architectural changes
- cross-component changes
- work that already has active feature docs

Workflow:

1. understand the current task from `TASKS.md`
2. load the relevant `PLAN.md` section
3. load the relevant `SPEC.md` requirement
4. run the readiness gate
5. update docs first if reality diverges
6. implement
7. validate
8. update progress and feature docs

#### Ad Hoc

Use this track for:

- contained bug fixes
- small refactors
- dependency updates
- config updates
- security reviews
- small documentation refinements

Workflow:

1. inspect relevant files
2. follow existing patterns
3. implement minimal reversible changes
4. run the smallest relevant checks
5. update practical docs that changed

Do not create `SPEC.md`, `PLAN.md`, or `TASKS.md` for ad hoc work unless scope grows enough to require formal tracking.

#### Ad Hoc With Existing Specs

- If a change touches code governed by existing feature docs, update those docs by default.
- Skip spec updates only for purely mechanical changes such as formatting, typo fixes, or dependency bumps that do not change behavior.

### Readiness Gate

Before implementing feature work, challenge the active docs for:

- contradictions
- ambiguity
- hidden assumptions
- missing failure modes
- task gaps
- scope creep
- unmet dependency or skill requirements

If the gate fails, fix canonical docs first.

### Orchestration

- Drive to understanding before execution.
- Use subagents only after discovery narrows the work into distinct, low-overlap areas.
- Keep broad or ambiguous work in the main lane until overlap is predictable.
- Parallelize only independent areas.
- Serialize dependent or cross-cutting work.
- Keep the main agent responsible for synthesis, integration, validation, and final communication.
- If isolated checkouts are needed, keep worktrees flat under `~/worktrees/`.

## Security and Data Handling

- Do not log or expose secrets.
- Do not add hardcoded credentials or environment-specific secrets.
- Validate all external input at the boundary.
- Sanitize path components before filesystem writes.
- Keep raw event storage deterministic and conflict-aware.
- Prefer secure defaults for ingest integrity checks.
- Treat payload contents as opaque data; do not infer or persist business-specific projections in core code.

## Project Goals

- Provide a small, reliable event collector for immutable application fact streams.
- Offer both HTTP and CLI ingestion paths with identical core semantics.
- Maintain deterministic canonical hashing for payload and event integrity.
- Preserve idempotent ingest behavior for safe producer retries.
- Store raw event objects in a simple archive layout suitable for later lake-style processing.
- Maintain a local SQLite ledger for ingest state, lookup, and operational inspection.
- Keep local development fast through `uv`, `make`, `pytest`, `ruff`, and `mypy`.
- Keep the architecture ready for future adapter expansion without weakening the current local-first implementation.
- Keep generated OpenAPI documentation available through FastAPI.

## Non-Goals

- Do not enforce producer-specific business schemas in the core collector.
- Do not mutate accepted raw event objects.
- Do not treat SQLite as the long-term event archive.
- Do not implement business projections, read models, workflow orchestration, or analytics in the collector core.
- Do not add external infrastructure dependencies to the default local path unless a feature explicitly requires them.
- Do not add adapter abstractions without at least one concrete implementation need.
- Do not broaden public APIs or exports speculatively.
- Do not store secrets in config examples, test fixtures, event samples, or docs.

## Long-Term Vision

The project should remain a focused ingress component that other systems can trust as the first durable stop for application fact events. Its default runtime should stay simple enough for local development and small deployments, while its boundaries should support future production adapters.

Future work should extend through narrow seams:

- new ledger adapters behind the `Ledger` protocol
- new raw storage adapters behind the `Storage` protocol
- optional producer or deployment metadata fields through explicit schema changes
- stronger operational tooling through Make targets, CLI commands, and documented smoke checks
- feature documentation under `docs/specs/<feature>/` when changes become cross-cutting

The collector should not become a domain platform. It should remain a dependable, generic, integrity-checking event intake service.

## Definitions

- Event envelope: the generic Pydantic event contract accepted by HTTP and CLI ingest paths.
- Payload: the opaque domain-specific object nested under `payload`.
- Canonical JSON: stable JSON with sorted keys, compact separators, UTF-8 encoding, and no ASCII escaping.
- Raw event object: the canonical full event envelope persisted by the storage adapter.
- Ledger: the ingest/index database that tracks event status, hashes, storage URI, timestamps, errors, and attempts.
- Storage adapter: the component that writes raw event objects and returns a URI.
- Ledger adapter: the component that records and retrieves ingest state.
- Duplicate success: a replay with the same `event_id` and same content hashes.
- Hash conflict: reuse of an existing `event_id` with different payload or event hashes.
- RLM: just-in-time context routing that loads the smallest relevant repo-local artifact for the immediate decision.


## PRINCIPLES

<!-- TODO: define core principles that guide all decisions -->

## CONSTRAINTS

<!-- TODO: define invariant rules that must never be violated -->

### Kit-Managed Baseline Rules

<!-- BEGIN KIT-MANAGED BASELINE RULES -->
- Treat `docs/CONSTITUTION.md` as the canonical project contract.
- Keep `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` aligned with the repo-local docs tree.
- Treat `docs/notes/<feature>` as optional source material, not canonical truth; promote durable decisions into `SPEC.md`, `docs/CONSTITUTION.md`, or durable references.
- Use native agent planning for research, clarification, design, and implementation planning.
- Before implementation, inspect code and repository memory; create or adopt `SPEC.md` when material rationale exists.
- After validation, curate feature rationale, project invariants, reusable practices, and domain knowledge into their scope-appropriate canonical documents.
- Allow a justified `not required` repository-memory decision when code and tests preserve the complete durable truth.
- Prefer implementation/source code files around 300 lines or less when splitting improves clarity and ownership.
- Do not apply the code-file size guideline to documentation files, all `docs/**`, all `.kit/**`, or `.kit.yaml`.
- Do not split or rewrite docs, generated state, or Kit config artifacts solely because they exceed 300 lines.
<!-- END KIT-MANAGED BASELINE RULES -->

## CHANGE CLASSIFICATION

<!-- all work falls into one of two tracks — classify before acting -->

### Repository-Memory Work

<!-- use when: consequential product rationale, architecture, cross-component behavior, or historical decisions must survive -->
<!-- workflow: native plan → create/adopt SPEC.md before code → implement → validate → curate repository memory -->
<!-- legacy staged documents: BRAINSTORM.md, legacy SPEC.md, PLAN.md, TASKS.md only when explicitly chosen -->

### Ad Hoc (Lightweight)

<!-- use when: bug fixes, security reviews, refactors, dependency updates, config changes, small refinements -->
<!-- workflow: understand → implement → verify -->
<!-- docs: update practical canonical docs when behavior changes -->
<!-- do not create feature SPEC.md solely for ceremony; report a justified not-required memory decision -->

### Ad Hoc with Existing Specs

<!-- if change touches code with existing spec docs: update them when rationale, behavior, requirements, or approach changes -->
<!-- leave them unchanged when code and tests communicate the complete durable truth -->
