"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from event_collector.api.routes import router
from event_collector.config import AppConfig, load_config
from event_collector.ingest.service import IngestService
from event_collector.ledger.sqlite import SQLiteLedger
from event_collector.storage.filesystem import FilesystemStorage


def create_app(config: AppConfig) -> FastAPI:
    """Create a configured FastAPI application."""
    ledger = SQLiteLedger(config.ledger.path)
    ledger.initialize()
    storage = FilesystemStorage(config.storage.root)
    service = IngestService(ledger=ledger, storage=storage, config=config.ingest)

    app = FastAPI(
        title="event-collector",
        version="0.1.0",
        description="Generic collector for immutable application fact event streams.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.config = config
    app.state.ingest_service = service
    app.include_router(router)
    return app


def create_app_from_path(config_path: str | Path) -> FastAPI:
    return create_app(load_config(config_path))


def create_app_from_env() -> FastAPI:
    config_path = os.environ.get("EVENT_COLLECTOR_CONFIG")
    if not config_path:
        raise RuntimeError("EVENT_COLLECTOR_CONFIG is required")
    return create_app_from_path(config_path)
