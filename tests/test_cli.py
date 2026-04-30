from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from event_collector.cli import app
from tests.conftest import make_event

runner = CliRunner()


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8920
ledger:
  adapter: sqlite
  path: {tmp_path / "ingest.sqlite"}
storage:
  adapter: filesystem
  root: {tmp_path / "event-lake"}
ingest:
  reject_hash_conflicts: true
  require_payload_hash: true
  require_event_hash: true
""",
        encoding="utf-8",
    )
    return config


def test_cli_db_init_ingest_and_get(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    event_path = tmp_path / "event.json"
    event = make_event()
    event_path.write_text(json.dumps(event), encoding="utf-8")

    init_result = runner.invoke(app, ["db", "init", "--config", str(config)])
    ingest_result = runner.invoke(
        app,
        ["ingest", "file", "--config", str(config), "--path", str(event_path)],
    )
    get_result = runner.invoke(
        app,
        ["events", "get", "--config", str(config), "--event-id", event["event_id"]],
    )

    assert init_result.exit_code == 0, init_result.output
    assert ingest_result.exit_code == 0, ingest_result.output
    assert json.loads(ingest_result.output)["status"] == "stored"
    assert get_result.exit_code == 0, get_result.output
    assert json.loads(get_result.output)["event_id"] == event["event_id"]
