"""Command-line interface for event-collector."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import Annotated
from urllib.error import URLError
from urllib.request import urlopen

import typer
import uvicorn
from fastapi import FastAPI

from event_collector.api.routes import DebugEventBus
from event_collector.api.schemas import EventEnvelope
from event_collector.config import load_config
from event_collector.errors import EventCollectorError, HashConflictError, HashValidationError
from event_collector.ingest.service import IngestService
from event_collector.ledger.sqlite import SQLiteLedger
from event_collector.main import DEBUG_ENV_VALUE, create_app
from event_collector.storage.filesystem import FilesystemStorage

DEBUG_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS = 1

app = typer.Typer(help="Generic event collector for immutable application fact streams.")
db_app = typer.Typer(help="Database/ledger commands.")
server_app = typer.Typer(help="Server runtime commands.")
ingest_app = typer.Typer(help="Ingest commands.")
events_app = typer.Typer(help="Event lookup commands.")

app.add_typer(db_app, name="db")
app.add_typer(server_app, name="server")
app.add_typer(ingest_app, name="ingest")
app.add_typer(events_app, name="events")


ConfigPath = Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")]


@db_app.command("init")
def db_init(config: ConfigPath) -> None:
    """Initialize the configured ingest ledger."""
    cfg = load_config(config)
    ledger = SQLiteLedger(cfg.ledger.path)
    ledger.initialize()
    typer.echo(json.dumps({"status": "initialized", "ledger": str(cfg.ledger.path)}))


@server_app.command("start")
def server_start(
    config: ConfigPath,
    host: Annotated[str | None, typer.Option("--host", help="Override configured host.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Override configured port.")] = None,
    background: Annotated[
        bool,
        typer.Option("--background", help="Start server in the background."),
    ] = False,
    pid_file: Annotated[
        Path | None,
        typer.Option("--pid-file", help="PID file for background mode."),
    ] = None,
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Log file for background mode."),
    ] = None,
) -> None:
    """Start the FastAPI event collector server."""
    cfg = load_config(config)
    resolved_host = host or cfg.server.host
    resolved_port = port or cfg.server.port
    if background:
        _start_background(config.resolve(), resolved_host, resolved_port, pid_file, log_file)
        return

    api_app = create_app(cfg)
    debug_event_bus = getattr(api_app.state, "debug_event_bus", None)
    _run_server(
        api_app,
        host=resolved_host,
        port=resolved_port,
        debug_event_bus=debug_event_bus if isinstance(debug_event_bus, DebugEventBus) else None,
    )


class EventCollectorServer(uvicorn.Server):
    def __init__(
        self,
        config: uvicorn.Config,
        *,
        debug_event_bus: DebugEventBus | None,
    ) -> None:
        super().__init__(config)
        self._debug_event_bus = debug_event_bus

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        if self._debug_event_bus is not None:
            self._debug_event_bus.close()
        super().handle_exit(sig, frame)


def _run_server(
    api_app: FastAPI,
    *,
    host: str,
    port: int,
    debug_event_bus: DebugEventBus | None,
) -> None:
    server = EventCollectorServer(
        uvicorn.Config(
            api_app,
            host=host,
            port=port,
            log_level="info",
            timeout_graceful_shutdown=_graceful_shutdown_timeout(),
        ),
        debug_event_bus=debug_event_bus,
    )
    server.run()


@server_app.command("status")
def server_status(
    url: Annotated[
        str,
        typer.Option("--url", help="Readiness URL."),
    ] = "http://127.0.0.1:8920/readyz",
) -> None:
    """Check server readiness."""
    try:
        with urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
    except URLError as exc:
        raise typer.Exit(code=1) from exc
    typer.echo(body)


@server_app.command("stop")
def server_stop(
    pid_file: Annotated[Path, typer.Option("--pid-file", help="PID file to stop.")] = Path(
        "event-collector.pid"
    ),
) -> None:
    """Stop a background server by PID file."""
    if not pid_file.exists():
        typer.echo(f"PID file not found: {pid_file}", err=True)
        raise typer.Exit(code=1)
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    os.kill(pid, signal.SIGTERM)
    pid_file.unlink(missing_ok=True)
    typer.echo(json.dumps({"status": "stopped", "pid": pid}))


@ingest_app.command("file")
def ingest_file(config: ConfigPath, path: Annotated[Path, typer.Option("--path", "-p")]) -> None:
    """Ingest one event envelope from a JSON file without running the HTTP server."""
    service = _service_from_config(config)
    raw = json.loads(path.read_text(encoding="utf-8"))
    envelope = EventEnvelope.model_validate(raw)
    try:
        result = service.ingest(envelope)
    except (HashConflictError, HashValidationError, EventCollectorError) as exc:
        typer.echo(json.dumps({"status": "failed", "message": str(exc)}), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        json.dumps(
            {
                "event_id": result.event_id,
                "status": result.status,
                "storage_uri": result.storage_uri,
                "received_at": result.received_at.isoformat(),
                "stored_at": result.stored_at.isoformat() if result.stored_at else None,
                "message": result.message,
            },
            sort_keys=True,
        )
    )


@events_app.command("get")
def events_get(config: ConfigPath, event_id: Annotated[str, typer.Option("--event-id")]) -> None:
    """Fetch an event record from the ingest ledger."""
    service = _service_from_config(config)
    record = service.get_event(event_id)
    if record is None:
        typer.echo(json.dumps({"status": "not_found", "event_id": event_id}), err=True)
        raise typer.Exit(code=1)
    typer.echo(
        json.dumps(
            {
                "event_id": record.event_id,
                "event_name": record.event_name,
                "event_version": record.event_version,
                "producer_service": record.producer_service,
                "status": record.status,
                "storage_uri": record.storage_uri,
                "received_at": record.received_at.isoformat(),
                "stored_at": record.stored_at.isoformat() if record.stored_at else None,
            },
            sort_keys=True,
        )
    )


def _service_from_config(config_path: Path) -> IngestService:
    cfg = load_config(config_path)
    ledger = SQLiteLedger(cfg.ledger.path)
    ledger.initialize()
    storage = FilesystemStorage(cfg.storage.root)
    return IngestService(ledger=ledger, storage=storage, config=cfg.ingest)


def _graceful_shutdown_timeout() -> int | None:
    if os.environ.get("EC_ENV") == DEBUG_ENV_VALUE:
        return DEBUG_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
    return None


def _start_background(
    config: Path,
    host: str,
    port: int,
    pid_file: Path | None,
    log_file: Path | None,
) -> None:
    pid_path = pid_file or Path("event-collector.pid")
    log_path = log_file or Path("event-collector.log")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "event_collector.cli",
        "server",
        "start",
        "--config",
        str(config),
        "--host",
        host,
        "--port",
        str(port),
    ]
    with log_path.open("ab") as log_handle:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path.write_text(str(process.pid), encoding="utf-8")
    typer.echo(
        json.dumps(
            {
                "status": "started",
                "pid": process.pid,
                "pid_file": str(pid_path),
                "log_file": str(log_path),
                "url": f"http://{host}:{port}",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
