"""Domain errors raised by event collector services."""

from __future__ import annotations


class EventCollectorError(Exception):
    """Base error for event collector failures."""


class ConfigError(EventCollectorError):
    """Raised when runtime configuration is invalid."""


class HashValidationError(EventCollectorError):
    """Raised when supplied envelope hashes do not match canonical content."""


class HashConflictError(EventCollectorError):
    """Raised when an event id is reused with different event content."""


class StorageError(EventCollectorError):
    """Raised when raw event storage fails."""


class StorageConflictError(StorageError):
    """Raised when an existing storage object disagrees with the event being stored."""
