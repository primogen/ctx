"""Graph pack manifest contract.

Graph packs are the planned modular graph artifact unit:

``base-*`` packs hold a complete graph export, while ``overlay-*`` packs hold
incremental nodes, edges, and tombstones that can be merged over a base pack.
This module defines only the manifest contract. Reader migration is a separate
phase so existing graph installs and recommendations keep their current path.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ctx.utils._fs_utils import atomic_write_text

GRAPH_PACK_MANIFEST = "graph-pack-manifest.json"
GRAPH_PACK_SCHEMA_VERSION = 1
PACK_TYPES = frozenset({"base", "overlay"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

PackType = Literal["base", "overlay"]


class GraphPackManifestError(ValueError):
    """Raised when a graph pack manifest is malformed."""


@dataclass(frozen=True)
class GraphPackManifest:
    """Validated manifest for one graph pack directory."""

    pack_id: str
    pack_type: PackType
    base_export_id: str
    parent_export_id: str | None
    config_hash: str
    model_id: str
    node_count: int
    edge_count: int
    checksums: dict[str, str]
    tombstone_count: int = 0
    created_at: str | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "GraphPackManifest":
        """Build and validate a manifest from JSON-decoded data."""
        if payload.get("schema_version") != GRAPH_PACK_SCHEMA_VERSION:
            raise GraphPackManifestError("graph pack manifest schema_version must be 1")
        pack_type = payload.get("pack_type")
        if pack_type not in PACK_TYPES:
            raise GraphPackManifestError("graph pack manifest pack_type must be base or overlay")
        manifest = cls(
            pack_id=_required_str(payload, "pack_id"),
            pack_type=pack_type,
            base_export_id=_required_str(payload, "base_export_id"),
            parent_export_id=_optional_str(payload, "parent_export_id"),
            config_hash=_required_str(payload, "config_hash"),
            model_id=_required_str(payload, "model_id"),
            node_count=_nonnegative_int(payload, "node_count"),
            edge_count=_nonnegative_int(payload, "edge_count"),
            checksums=_checksums(payload.get("checksums")),
            tombstone_count=_nonnegative_int(payload, "tombstone_count", default=0),
            created_at=_optional_str(payload, "created_at"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        """Validate cross-field invariants."""
        _validate_relative_manifest_name(self.pack_id, "pack_id")
        if self.pack_type == "base" and self.parent_export_id:
            raise GraphPackManifestError("base graph packs must not set parent_export_id")
        if self.pack_type == "overlay" and not self.parent_export_id:
            raise GraphPackManifestError("overlay graph packs must set parent_export_id")
        if not self.checksums:
            raise GraphPackManifestError("graph pack manifest checksums must not be empty")

    def to_mapping(self) -> dict[str, Any]:
        """Return deterministic JSON-serialisable manifest data."""
        payload: dict[str, Any] = {
            "schema_version": GRAPH_PACK_SCHEMA_VERSION,
            "pack_id": self.pack_id,
            "pack_type": self.pack_type,
            "base_export_id": self.base_export_id,
            "parent_export_id": self.parent_export_id,
            "config_hash": self.config_hash,
            "model_id": self.model_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "tombstone_count": self.tombstone_count,
            "checksums": dict(sorted(self.checksums.items())),
        }
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        return payload


def build_pack_manifest(
    *,
    pack_dir: Path,
    pack_id: str,
    pack_type: PackType,
    base_export_id: str,
    parent_export_id: str | None,
    config_hash: str,
    model_id: str,
    node_count: int,
    edge_count: int,
    artifact_paths: list[str],
    tombstone_count: int = 0,
    created_at: str | None = None,
) -> GraphPackManifest:
    """Create a manifest and compute SHA-256 checksums for pack artifacts."""
    checksums = {
        _normalise_artifact_name(name): sha256_file(pack_dir / name)
        for name in artifact_paths
    }
    return GraphPackManifest(
        pack_id=pack_id,
        pack_type=pack_type,
        base_export_id=base_export_id,
        parent_export_id=parent_export_id,
        config_hash=config_hash,
        model_id=model_id,
        node_count=node_count,
        edge_count=edge_count,
        checksums=checksums,
        tombstone_count=tombstone_count,
        created_at=created_at,
    )


def read_pack_manifest(path: Path) -> GraphPackManifest:
    """Read and validate ``graph-pack-manifest.json``."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphPackManifestError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise GraphPackManifestError(f"{path} did not contain a JSON object")
    return GraphPackManifest.from_mapping(payload)


def write_pack_manifest(path: Path, manifest: GraphPackManifest) -> None:
    """Atomically write a graph pack manifest."""
    manifest.validate()
    atomic_write_text(
        path,
        json.dumps(manifest.to_mapping(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GraphPackManifestError(f"graph pack manifest {key} must be a non-empty string")
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise GraphPackManifestError(f"graph pack manifest {key} must be a string or null")
    return value


def _nonnegative_int(payload: dict[str, Any], key: str, *, default: int | None = None) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int) or value < 0:
        raise GraphPackManifestError(f"graph pack manifest {key} must be a non-negative integer")
    return value


def _checksums(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise GraphPackManifestError("graph pack manifest checksums must be an object")
    result: dict[str, str] = {}
    for raw_name, raw_digest in value.items():
        if not isinstance(raw_name, str):
            raise GraphPackManifestError("graph pack manifest checksum names must be strings")
        name = _normalise_artifact_name(raw_name)
        if not isinstance(raw_digest, str) or not _SHA256_RE.match(raw_digest):
            raise GraphPackManifestError(
                f"graph pack manifest checksum for {name} must be a SHA-256 hex digest"
            )
        result[name] = raw_digest
    return result


def _normalise_artifact_name(name: str) -> str:
    normalised = name.replace("\\", "/").strip()
    _validate_relative_manifest_name(normalised, "artifact name")
    return normalised


def _validate_relative_manifest_name(value: str, label: str) -> None:
    path = Path(value)
    if path.is_absolute() or value.startswith(("/", "\\")):
        raise GraphPackManifestError(f"graph pack manifest {label} must be relative")
    parts = value.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise GraphPackManifestError(f"graph pack manifest {label} is unsafe")
