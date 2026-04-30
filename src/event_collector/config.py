"""Configuration loading for event-collector."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from event_collector.errors import ConfigError


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8920, ge=1, le=65535)


class LedgerConfig(BaseModel):
    adapter: Literal["sqlite"] = "sqlite"
    path: Path


class StorageConfig(BaseModel):
    adapter: Literal["filesystem"] = "filesystem"
    root: Path


class IngestConfig(BaseModel):
    reject_hash_conflicts: bool = True
    require_payload_hash: bool = True
    require_event_hash: bool = True


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    ledger: LedgerConfig
    storage: StorageConfig
    ingest: IngestConfig = Field(default_factory=IngestConfig)

    @model_validator(mode="after")
    def _validate_paths(self) -> AppConfig:
        if not self.ledger.path:
            raise ValueError("ledger.path is required")
        if not self.storage.root:
            raise ValueError("storage.root is required")
        return self


def _resolve_path(path: Path, *, base_dir: Path) -> Path:
    path = Path(path).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_config(path: str | Path) -> AppConfig:
    """Load YAML config and resolve relative paths relative to the config file."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML config: {config_path}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping")

    config = AppConfig.model_validate(raw)
    base_dir = config_path.parent
    config.ledger.path = _resolve_path(config.ledger.path, base_dir=base_dir)
    config.storage.root = _resolve_path(config.storage.root, base_dir=base_dir)
    return config
