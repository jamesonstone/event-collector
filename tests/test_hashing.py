from __future__ import annotations

from event_collector.hashing import canonical_json_bytes, sha256_json


def test_canonical_json_is_stable() -> None:
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}

    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert sha256_json(left) == sha256_json(right)
