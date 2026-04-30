#!/usr/bin/env python3
"""Generate a fresh event envelope from a template."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from event_collector.hashing import sha256_json


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_event(template_path: Path) -> dict:
    event = json.loads(template_path.read_text(encoding="utf-8"))
    event["event_id"] = str(uuid4())
    event["occurred_at"] = _utc_now()
    event["observed_at"] = _utc_now()
    event.pop("payload_sha256", None)
    event.pop("event_sha256", None)
    event["payload_sha256"] = sha256_json(event["payload"])
    event["event_sha256"] = sha256_json(event)
    return event


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a fresh event envelope.")
    parser.add_argument("--template", required=True, type=Path, help="Template event JSON.")
    parser.add_argument("--output", required=True, type=Path, help="Generated event JSON output.")
    parser.add_argument(
        "--event-id-file",
        required=True,
        type=Path,
        help="File that receives the generated event id.",
    )
    args = parser.parse_args()

    event = generate_event(args.template)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.event_id_file.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
    args.event_id_file.write_text(event["event_id"] + "\n", encoding="utf-8")
    print(event["event_id"])


if __name__ == "__main__":
    main()
