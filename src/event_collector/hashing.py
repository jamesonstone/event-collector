"""Canonical JSON and hashing helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes for hashing and raw storage."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_json_text(value: Any) -> str:
    """Return stable JSON text with a trailing newline for object storage."""
    return canonical_json_bytes(value).decode("utf-8") + "\n"


def sha256_hex(value: bytes) -> str:
    """Return a SHA-256 hex digest."""
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    """Return the SHA-256 digest of canonical JSON."""
    return sha256_hex(canonical_json_bytes(value))
