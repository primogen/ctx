"""Coordinated graph/wiki pack compaction.

This module stages a new immutable graph base pack and matching wiki base pack
from the active base+overlay sets. Promotion remains a separate step so callers
can validate both staged artifacts before replacing the active packs.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ctx.core.graph.graph_packs import (
    GraphPackManifest,
    GraphPackManifestError,
    compact_graph_packs,
)
from ctx.core.wiki.wiki_packs import (
    WikiPackManifest,
    WikiPackManifestError,
    compact_wiki_packs,
)


class PackCompactionError(ValueError):
    """Raised when coordinated graph/wiki pack compaction cannot be staged."""


@dataclass(frozen=True)
class PackCompactionResult:
    """Staged graph/wiki compaction result."""

    wiki_path: Path
    staging_dir: Path
    graph_packs_dir: Path
    wiki_packs_dir: Path
    staged_graph_packs_dir: Path
    staged_wiki_packs_dir: Path
    graph_manifest: GraphPackManifest
    wiki_manifest: WikiPackManifest


def compact_active_pack_sets(
    *,
    wiki_path: Path,
    base_export_id: str,
    staging_dir: Path | None = None,
    graph_config_hash: str | None = None,
    graph_model_id: str | None = None,
    created_at: str | None = None,
) -> PackCompactionResult:
    """Stage matching compacted graph and wiki base packs.

    The active pack directories are not mutated. The caller can validate the
    staged roots and promote them in a later operation.
    """
    if not base_export_id.strip():
        raise PackCompactionError("base_export_id must be non-empty")
    wiki_root = Path(wiki_path)
    graph_packs_dir = wiki_root / "graphify-out" / "packs"
    wiki_packs_dir = wiki_root / "wiki-packs"
    stage_root = Path(staging_dir) if staging_dir is not None else (
        wiki_root / "graphify-out" / "pack-compaction-staging" / _pack_id(base_export_id)
    )
    if stage_root.exists():
        raise PackCompactionError(f"staging directory already exists: {stage_root}")

    staged_graph_packs_dir = stage_root / "graph-packs"
    staged_wiki_packs_dir = stage_root / "wiki-packs"
    pack_id = _pack_id(base_export_id)
    try:
        graph_manifest = compact_graph_packs(
            packs_dir=graph_packs_dir,
            compacted_pack_dir=staged_graph_packs_dir / pack_id,
            base_export_id=base_export_id,
            config_hash=graph_config_hash,
            model_id=graph_model_id,
            created_at=created_at,
        )
        wiki_manifest = compact_wiki_packs(
            packs_dir=wiki_packs_dir,
            compacted_pack_dir=staged_wiki_packs_dir / pack_id,
            base_export_id=base_export_id,
            created_at=created_at,
        )
    except (GraphPackManifestError, WikiPackManifestError) as exc:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise PackCompactionError(str(exc)) from exc

    return PackCompactionResult(
        wiki_path=wiki_root,
        staging_dir=stage_root,
        graph_packs_dir=graph_packs_dir,
        wiki_packs_dir=wiki_packs_dir,
        staged_graph_packs_dir=staged_graph_packs_dir,
        staged_wiki_packs_dir=staged_wiki_packs_dir,
        graph_manifest=graph_manifest,
        wiki_manifest=wiki_manifest,
    )


def _pack_id(base_export_id: str) -> str:
    value = base_export_id.strip()
    return value if value.startswith("base-") else f"base-{value}"
