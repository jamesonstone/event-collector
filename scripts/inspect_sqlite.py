#!/usr/bin/env python3
"""Inspect the configured SQLite ingest ledger."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from event_collector.config import load_config


def _connect(config_path: Path) -> tuple[Path, sqlite3.Connection]:
    config = load_config(config_path)
    ledger_path = config.ledger.path
    if not ledger_path.exists():
        raise SystemExit(f"SQLite ledger does not exist: {ledger_path}")
    conn = sqlite3.connect(ledger_path)
    conn.row_factory = sqlite3.Row
    return ledger_path, conn


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True))


def ledger_path(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    _print_json({"ledger_path": str(config.ledger.path), "exists": config.ledger.path.exists()})


def counts(args: argparse.Namespace) -> None:
    ledger, conn = _connect(args.config)
    with conn:
        event_count = conn.execute("select count(*) from ingest_event").fetchone()[0]
        attempt_count = conn.execute("select count(*) from ingest_attempt").fetchone()[0]
    _print_json(
        {
            "ledger_path": str(ledger),
            "event_count": event_count,
            "attempt_count": attempt_count,
        }
    )


def events(args: argparse.Namespace) -> None:
    ledger, conn = _connect(args.config)
    with conn:
        rows = _rows(
            conn.execute(
                """
                select
                  id,
                  event_id,
                  event_name,
                  event_version,
                  producer_service,
                  partition_id,
                  subject_type,
                  subject_id,
                  status,
                  storage_uri,
                  received_at,
                  stored_at,
                  last_error
                from ingest_event
                order by id desc
                limit ?
                """,
                (args.limit,),
            )
        )
    _print_json({"ledger_path": str(ledger), "events": rows})


def event(args: argparse.Namespace) -> None:
    ledger, conn = _connect(args.config)
    with conn:
        row = conn.execute(
            "select * from ingest_event where event_id = ?",
            (args.event_id,),
        ).fetchone()
    if row is None:
        raise SystemExit(f"Event not found: {args.event_id}")
    record = dict(row)
    raw = record.pop("raw_envelope_json", None)
    if raw:
        record["raw_envelope"] = json.loads(raw)
    _print_json({"ledger_path": str(ledger), "event": record})


def attempts(args: argparse.Namespace) -> None:
    ledger, conn = _connect(args.config)
    query = """
        select id, event_id, attempt_status, message, created_at
        from ingest_attempt
    """
    params: tuple[Any, ...] = ()
    if args.event_id:
        query += " where event_id = ?"
        params = (args.event_id,)
    query += " order by id desc limit ?"
    params = (*params, args.limit)
    with conn:
        rows = _rows(conn.execute(query, params))
    _print_json({"ledger_path": str(ledger), "attempts": rows})


def schema(args: argparse.Namespace) -> None:
    ledger, conn = _connect(args.config)
    with conn:
        tables = _rows(
            conn.execute(
                """
                select name, sql
                from sqlite_master
                where type = 'table'
                order by name
                """
            )
        )
        indexes = _rows(
            conn.execute(
                """
                select name, tbl_name, sql
                from sqlite_master
                where type = 'index'
                order by name
                """
            )
        )
    _print_json({"ledger_path": str(ledger), "tables": tables, "indexes": indexes})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect an event-collector SQLite ledger.")
    parser.add_argument("--config", required=True, type=Path, help="Path to config YAML.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    path_parser = subparsers.add_parser("path", help="Print the resolved ledger path.")
    path_parser.set_defaults(func=ledger_path)

    counts_parser = subparsers.add_parser("counts", help="Print event and attempt counts.")
    counts_parser.set_defaults(func=counts)

    events_parser = subparsers.add_parser("events", help="List recent ingest events.")
    events_parser.add_argument("--limit", type=int, default=20)
    events_parser.set_defaults(func=events)

    event_parser = subparsers.add_parser("event", help="Fetch one ingest event.")
    event_parser.add_argument("--event-id", required=True)
    event_parser.set_defaults(func=event)

    attempts_parser = subparsers.add_parser("attempts", help="List recent ingest attempts.")
    attempts_parser.add_argument("--event-id")
    attempts_parser.add_argument("--limit", type=int, default=20)
    attempts_parser.set_defaults(func=attempts)

    schema_parser = subparsers.add_parser("schema", help="Print ledger schema.")
    schema_parser.set_defaults(func=schema)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
