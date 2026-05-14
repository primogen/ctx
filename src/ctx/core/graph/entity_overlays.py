"""Shared helpers for runtime entity graph overlays."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

_EMPTY_VALUES: tuple[object, ...] = (None, "", [], {})
_NUMERIC_EDGE_ATTRS = frozenset(
    {
        "weight",
        "final_weight",
        "semantic_sim",
        "tag_sim",
        "token_sim",
        "similarity_score",
    }
)
_LIST_EDGE_ATTRS = frozenset(
    {
        "shared_tags",
        "shared_tokens",
        "shared_sources",
        "edge_reasons",
    }
)


def active_overlay_records(records: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return deduped active records, superseding stale rows by scope."""
    by_attach_key: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        if record.get("superseded_at"):
            continue
        attach_key = overlay_attach_key(record, fallback_index=index)
        if attach_key not in by_attach_key:
            by_attach_key[attach_key] = record

    by_scope: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(by_attach_key.values()):
        by_scope[overlay_replace_scope(record, fallback_index=index)] = record
    return list(by_scope.values())


def overlay_attach_key(record: Mapping[str, Any], *, fallback_index: int = 0) -> str:
    for key in ("attach_key", "idempotency_key", "overlay_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    node_id = _record_node_id(record)
    content_hash = record.get("content_hash")
    model_id = record.get("model_id", "legacy")
    if node_id and isinstance(content_hash, str) and content_hash:
        return f"ann:v1:{model_id}:{node_id}:{content_hash}"
    return f"legacy:{fallback_index}:{_canonical_hash(record)}"


def overlay_replace_scope(record: Mapping[str, Any], *, fallback_index: int = 0) -> str:
    value = record.get("replace_scope")
    if isinstance(value, str) and value:
        return value
    node_id = _record_node_id(record)
    model_id = record.get("model_id", "legacy")
    if node_id:
        return f"ann:v1:{model_id}:{node_id}"
    return overlay_attach_key(record, fallback_index=fallback_index)


def merge_node_attrs(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "id" or value in _EMPTY_VALUES:
            continue
        if key not in merged or merged.get(key) in _EMPTY_VALUES:
            merged[key] = value
    return merged


def merge_edge_attrs(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"source", "target"} or value in _EMPTY_VALUES:
            continue
        if key in _NUMERIC_EDGE_ATTRS:
            merged[key] = max(_as_float(merged.get(key)), _as_float(value))
        elif key in _LIST_EDGE_ATTRS:
            merged[key] = _ordered_union(merged.get(key), value)
        elif key == "direct_link":
            merged[key] = bool(merged.get(key)) or bool(value)
        elif key not in merged or merged.get(key) in _EMPTY_VALUES:
            merged[key] = value
    return merged


def _record_node_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("node_id")
    if isinstance(value, str) and value:
        return value
    nodes = record.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, Mapping):
                node_id = node.get("id")
                if isinstance(node_id, str) and node_id:
                    return node_id
    return None


def _canonical_hash(record: Mapping[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _ordered_union(left: object, right: object) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for values in (left, right):
        if isinstance(values, list):
            iterable = values
        else:
            iterable = [values]
        for value in iterable:
            key = json.dumps(value, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
    return result
