"""Coordinated graph/wiki pack compaction.

This module stages a new immutable graph base pack and matching wiki base pack
from the active base+overlay sets. Promotion remains a separate step so callers
can validate both staged artifacts before replacing the active packs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ctx.core.graph.graph_packs import (
    GraphPackManifest,
    GraphPackManifestError,
    GraphPackPromotion,
    compact_graph_packs,
    load_merged_pack_graph,
    promote_graph_pack_set,
)
from ctx.core.wiki.wiki_packs import (
    WikiPackManifest,
    WikiPackManifestError,
    WikiPackPromotion,
    compact_wiki_packs,
    load_merged_wiki_pages,
    promote_wiki_pack_set,
)
from ctx.utils._fs_utils import atomic_write_text

PACK_COMPACTION_MANIFEST = "pack-compaction-manifest.json"
PACK_COMPACTION_SCHEMA_VERSION = 1


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
    manifest_path: Path
    graph_manifest: GraphPackManifest
    wiki_manifest: WikiPackManifest

    def to_mapping(self) -> dict[str, object]:
        """Return deterministic JSON-serialisable compaction metadata."""
        return {
            "schema_version": PACK_COMPACTION_SCHEMA_VERSION,
            "operation": "pack-compaction-stage",
            "wiki_path": str(self.wiki_path),
            "staging_dir": str(self.staging_dir),
            "graph_packs_dir": str(self.graph_packs_dir),
            "wiki_packs_dir": str(self.wiki_packs_dir),
            "staged_graph_packs_dir": str(self.staged_graph_packs_dir),
            "staged_wiki_packs_dir": str(self.staged_wiki_packs_dir),
            "manifest_path": str(self.manifest_path),
            "base_export_id": self.graph_manifest.base_export_id,
            "graph": self.graph_manifest.to_mapping(),
            "wiki": self.wiki_manifest.to_mapping(),
        }


@dataclass(frozen=True)
class PackPromotionResult:
    """Coordinated graph/wiki pack promotion result."""

    wiki_path: Path
    graph: GraphPackPromotion
    wiki: WikiPackPromotion

    def to_mapping(self) -> dict[str, object]:
        """Return deterministic JSON-serialisable promotion metadata."""
        return {
            "wiki_path": str(self.wiki_path),
            "graph": self.graph.to_mapping(),
            "wiki": self.wiki.to_mapping(),
        }


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
    manifest_path = stage_root / PACK_COMPACTION_MANIFEST
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
        result = PackCompactionResult(
            wiki_path=wiki_root,
            staging_dir=stage_root,
            graph_packs_dir=graph_packs_dir,
            wiki_packs_dir=wiki_packs_dir,
            staged_graph_packs_dir=staged_graph_packs_dir,
            staged_wiki_packs_dir=staged_wiki_packs_dir,
            manifest_path=manifest_path,
            graph_manifest=graph_manifest,
            wiki_manifest=wiki_manifest,
        )
        _write_compaction_manifest(result, created_at=created_at)
    except (GraphPackManifestError, WikiPackManifestError, OSError) as exc:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise PackCompactionError(str(exc)) from exc

    return result


def promote_staged_pack_sets(
    *,
    wiki_path: Path,
    staged_graph_packs_dir: Path,
    staged_wiki_packs_dir: Path,
    graph_backup_packs_dir: Path | None = None,
    wiki_backup_packs_dir: Path | None = None,
) -> PackPromotionResult:
    """Promote staged graph/wiki pack sets into the active wiki.

    Both staged roots are validated before any active directory is touched. If
    graph promotion succeeds but wiki promotion fails, the previous graph pack
    directory is restored from the graph backup.
    """
    wiki_root = Path(wiki_path)
    graph_stage = Path(staged_graph_packs_dir)
    wiki_stage = Path(staged_wiki_packs_dir)
    active_graph_packs = wiki_root / "graphify-out" / "packs"
    active_wiki_packs = wiki_root / "wiki-packs"
    _validate_staged_pack_roots(graph_stage, wiki_stage)

    graph_result: GraphPackPromotion | None = None
    try:
        graph_result = promote_graph_pack_set(
            staged_packs_dir=graph_stage,
            active_packs_dir=active_graph_packs,
            backup_packs_dir=Path(graph_backup_packs_dir) if graph_backup_packs_dir else None,
        )
        wiki_result = promote_wiki_pack_set(
            staged_packs_dir=wiki_stage,
            active_packs_dir=active_wiki_packs,
            backup_packs_dir=Path(wiki_backup_packs_dir) if wiki_backup_packs_dir else None,
        )
    except (GraphPackManifestError, WikiPackManifestError, OSError) as exc:
        if graph_result is not None:
            _restore_graph_packs_after_partial_promotion(graph_result)
        raise PackCompactionError(str(exc)) from exc

    return PackPromotionResult(
        wiki_path=wiki_root,
        graph=graph_result,
        wiki=wiki_result,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI for staging coordinated graph/wiki pack compaction."""
    parser = argparse.ArgumentParser(
        prog="python -m ctx.core.wiki.pack_compaction",
        description="Stage compacted ctx graph and LLM-wiki base packs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    compact = sub.add_parser(
        "compact",
        help="Stage compacted graph/wiki base packs without mutating active packs.",
    )
    compact.add_argument("--wiki-path", required=True, help="Path to the ctx wiki root")
    compact.add_argument("--base-export-id", required=True, help="New compacted export id")
    compact.add_argument("--staging-dir", help="Destination staging root")
    compact.add_argument("--graph-config-hash", help="Override graph config hash")
    compact.add_argument("--graph-model-id", help="Override graph model id")
    compact.add_argument("--created-at", help="Optional created_at value for staged manifests")
    compact.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    promote = sub.add_parser(
        "promote",
        help="Promote validated staged graph/wiki packs into the active wiki.",
    )
    promote.add_argument("--wiki-path", required=True, help="Path to the ctx wiki root")
    promote.add_argument(
        "--staged-graph-packs-dir",
        required=True,
        help="Validated staged graph packs root",
    )
    promote.add_argument(
        "--staged-wiki-packs-dir",
        required=True,
        help="Validated staged wiki packs root",
    )
    promote.add_argument("--graph-backup-packs-dir", help="Optional graph backup directory")
    promote.add_argument("--wiki-backup-packs-dir", help="Optional wiki backup directory")
    promote.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    if args.command == "compact":
        try:
            compact_result = compact_active_pack_sets(
                wiki_path=Path(args.wiki_path),
                base_export_id=args.base_export_id,
                staging_dir=Path(args.staging_dir) if args.staging_dir else None,
                graph_config_hash=args.graph_config_hash,
                graph_model_id=args.graph_model_id,
                created_at=args.created_at,
            )
        except PackCompactionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        payload = compact_result.to_mapping()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                "staged graph/wiki compaction: "
                f"{compact_result.graph_manifest.node_count} graph nodes, "
                f"{compact_result.graph_manifest.edge_count} graph edges, "
                f"{compact_result.wiki_manifest.page_count} wiki pages"
            )
        return 0
    if args.command == "promote":
        try:
            promotion_result = promote_staged_pack_sets(
                wiki_path=Path(args.wiki_path),
                staged_graph_packs_dir=Path(args.staged_graph_packs_dir),
                staged_wiki_packs_dir=Path(args.staged_wiki_packs_dir),
                graph_backup_packs_dir=(
                    Path(args.graph_backup_packs_dir)
                    if args.graph_backup_packs_dir
                    else None
                ),
                wiki_backup_packs_dir=(
                    Path(args.wiki_backup_packs_dir)
                    if args.wiki_backup_packs_dir
                    else None
                ),
            )
        except PackCompactionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        payload = promotion_result.to_mapping()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                "promoted graph/wiki packs: "
                f"{', '.join(promotion_result.graph.promoted_pack_ids)} / "
                f"{', '.join(promotion_result.wiki.promoted_pack_ids)}"
            )
        return 0
    return 1


def _pack_id(base_export_id: str) -> str:
    value = base_export_id.strip()
    return value if value.startswith("base-") else f"base-{value}"


def _write_compaction_manifest(
    result: PackCompactionResult,
    *,
    created_at: str | None,
) -> None:
    payload = result.to_mapping()
    payload["created_at"] = created_at or datetime.now(UTC).isoformat()
    atomic_write_text(
        result.manifest_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_staged_pack_roots(
    staged_graph_packs_dir: Path,
    staged_wiki_packs_dir: Path,
) -> None:
    try:
        graph = load_merged_pack_graph(staged_graph_packs_dir)
        pages = load_merged_wiki_pages(staged_wiki_packs_dir)
    except (GraphPackManifestError, WikiPackManifestError) as exc:
        raise PackCompactionError(str(exc)) from exc
    if graph.number_of_nodes() == 0:
        raise PackCompactionError("staged graph packs do not contain a graph")
    if not pages:
        raise PackCompactionError("staged wiki packs do not contain pages")


def _restore_graph_packs_after_partial_promotion(result: GraphPackPromotion) -> None:
    active = result.active_packs_dir
    backup = result.backup_packs_dir
    _remove_path(active)
    if backup is not None and backup.exists():
        backup.replace(active)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
