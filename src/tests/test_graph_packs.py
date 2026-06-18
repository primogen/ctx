from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctx.core.graph.graph_packs import (
    GraphPackManifest,
    GraphPackManifestError,
    build_pack_manifest,
    discover_pack_manifests,
    load_merged_pack_graph,
    read_pack_manifest,
    sha256_file,
    write_pack_manifest,
)


def test_base_pack_manifest_round_trips_with_file_checksums(tmp_path: Path) -> None:
    pack_dir = tmp_path / "graph" / "packs" / "base-export-1"
    pack_dir.mkdir(parents=True)
    (pack_dir / "graph.json").write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    (pack_dir / "communities.json").write_text('{"communities":[]}\n', encoding="utf-8")

    manifest = build_pack_manifest(
        pack_dir=pack_dir,
        pack_id="base-export-1",
        pack_type="base",
        base_export_id="export-1",
        parent_export_id=None,
        config_hash="config-sha",
        model_id="bge-small-en-v1.5",
        node_count=0,
        edge_count=0,
        artifact_paths=["graph.json", "communities.json"],
    )

    assert manifest.checksums["graph.json"] == sha256_file(pack_dir / "graph.json")

    manifest_path = pack_dir / "graph-pack-manifest.json"
    write_pack_manifest(manifest_path, manifest)

    assert read_pack_manifest(manifest_path) == manifest
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_overlay_pack_manifest_requires_parent_export_id() -> None:
    with pytest.raises(GraphPackManifestError, match="parent_export_id"):
        GraphPackManifest.from_mapping({
            "schema_version": 1,
            "pack_id": "overlay-1",
            "pack_type": "overlay",
            "base_export_id": "export-1",
            "parent_export_id": None,
            "config_hash": "config-sha",
            "model_id": "bge-small-en-v1.5",
            "node_count": 1,
            "edge_count": 2,
            "tombstone_count": 0,
            "checksums": {"entity-overlays.jsonl": "a" * 64},
        })


def test_manifest_rejects_unsafe_artifact_paths(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (tmp_path / "graph.json").write_text("{}", encoding="utf-8")

    with pytest.raises(GraphPackManifestError, match="unsafe"):
        build_pack_manifest(
            pack_dir=pack_dir,
            pack_id="base-export-1",
            pack_type="base",
            base_export_id="export-1",
            parent_export_id=None,
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=0,
            edge_count=0,
            artifact_paths=["../graph.json"],
        )


def test_manifest_rejects_bad_checksum_shape() -> None:
    payload = {
        "schema_version": 1,
        "pack_id": "base-export-1",
        "pack_type": "base",
        "base_export_id": "export-1",
        "parent_export_id": None,
        "config_hash": "config-sha",
        "model_id": "bge-small-en-v1.5",
        "node_count": 0,
        "edge_count": 0,
        "tombstone_count": 0,
        "checksums": {"graph.json": "not-a-digest"},
    }

    with pytest.raises(GraphPackManifestError, match="SHA-256"):
        GraphPackManifest.from_mapping(payload)


def test_discover_pack_manifests_orders_base_then_overlays(tmp_path: Path) -> None:
    packs_dir = tmp_path / "graph" / "packs"
    base_dir = packs_dir / "base-export-1"
    overlay_dir = packs_dir / "overlay-review-skill"
    base_dir.mkdir(parents=True)
    overlay_dir.mkdir()
    (base_dir / "graph.json").write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    (overlay_dir / "nodes.jsonl").write_text('{"id":"skill:review"}\n', encoding="utf-8")
    write_pack_manifest(
        base_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=base_dir,
            pack_id="base-export-1",
            pack_type="base",
            base_export_id="export-1",
            parent_export_id=None,
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=0,
            edge_count=0,
            artifact_paths=["graph.json"],
        ),
    )
    write_pack_manifest(
        overlay_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=overlay_dir,
            pack_id="overlay-review-skill",
            pack_type="overlay",
            base_export_id="export-1",
            parent_export_id="export-1",
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=1,
            edge_count=0,
            artifact_paths=["nodes.jsonl"],
            tombstone_count=2,
        ),
    )

    discovered = discover_pack_manifests(packs_dir)

    assert [entry.manifest.pack_id for entry in discovered] == [
        "base-export-1",
        "overlay-review-skill",
    ]
    assert discovered[1].manifest.tombstone_count == 2


def test_discover_pack_manifests_rejects_overlay_parent_mismatch(tmp_path: Path) -> None:
    packs_dir = tmp_path / "packs"
    base_dir = packs_dir / "base-export-1"
    overlay_dir = packs_dir / "overlay-stale"
    base_dir.mkdir(parents=True)
    overlay_dir.mkdir()
    (base_dir / "graph.json").write_text("{}", encoding="utf-8")
    (overlay_dir / "nodes.jsonl").write_text("{}", encoding="utf-8")
    write_pack_manifest(
        base_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=base_dir,
            pack_id="base-export-1",
            pack_type="base",
            base_export_id="export-1",
            parent_export_id=None,
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=0,
            edge_count=0,
            artifact_paths=["graph.json"],
        ),
    )
    write_pack_manifest(
        overlay_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=overlay_dir,
            pack_id="overlay-stale",
            pack_type="overlay",
            base_export_id="export-1",
            parent_export_id="old-export",
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=1,
            edge_count=0,
            artifact_paths=["nodes.jsonl"],
        ),
    )

    with pytest.raises(GraphPackManifestError, match="parent_export_id"):
        discover_pack_manifests(packs_dir)


def test_discover_pack_manifests_rejects_checksum_drift(tmp_path: Path) -> None:
    packs_dir = tmp_path / "packs"
    base_dir = packs_dir / "base-export-1"
    base_dir.mkdir(parents=True)
    graph_path = base_dir / "graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    write_pack_manifest(
        base_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=base_dir,
            pack_id="base-export-1",
            pack_type="base",
            base_export_id="export-1",
            parent_export_id=None,
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=0,
            edge_count=0,
            artifact_paths=["graph.json"],
        ),
    )
    graph_path.write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(GraphPackManifestError, match="checksum mismatch"):
        discover_pack_manifests(packs_dir)


def test_load_merged_pack_graph_applies_overlay_nodes_and_edges(tmp_path: Path) -> None:
    packs_dir = tmp_path / "packs"
    base_dir = packs_dir / "base-export-1"
    overlay_dir = packs_dir / "overlay-review"
    base_dir.mkdir(parents=True)
    overlay_dir.mkdir()
    (base_dir / "graph.json").write_text(
        json.dumps({
            "graph": {"export_id": "export-1"},
            "nodes": [
                {"id": "skill:python", "type": "skill", "tags": ["python"]},
                {"id": "mcp-server:github", "type": "mcp-server", "tags": ["github"]},
            ],
            "edges": [
                {"source": "skill:python", "target": "mcp-server:github", "weight": 0.4},
            ],
        }),
        encoding="utf-8",
    )
    (overlay_dir / "nodes.jsonl").write_text(
        json.dumps({"id": "skill:review", "type": "skill", "tags": ["review"]}) + "\n",
        encoding="utf-8",
    )
    (overlay_dir / "edges.jsonl").write_text(
        json.dumps({
            "source": "skill:review",
            "target": "mcp-server:github",
            "weight": 0.8,
            "provenance": "overlay-test",
        }) + "\n",
        encoding="utf-8",
    )
    write_pack_manifest(
        base_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=base_dir,
            pack_id="base-export-1",
            pack_type="base",
            base_export_id="export-1",
            parent_export_id=None,
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=2,
            edge_count=1,
            artifact_paths=["graph.json"],
        ),
    )
    write_pack_manifest(
        overlay_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=overlay_dir,
            pack_id="overlay-review",
            pack_type="overlay",
            base_export_id="export-1",
            parent_export_id="export-1",
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=1,
            edge_count=1,
            artifact_paths=["nodes.jsonl", "edges.jsonl"],
        ),
    )

    graph = load_merged_pack_graph(packs_dir)

    assert graph.number_of_nodes() == 3
    assert graph.has_edge("skill:review", "mcp-server:github")
    assert graph.edges["skill:review", "mcp-server:github"]["weight"] == 0.8
    assert graph.graph["ctx_pack_ids"] == ["base-export-1", "overlay-review"]


def test_load_merged_pack_graph_applies_tombstones(tmp_path: Path) -> None:
    packs_dir = tmp_path / "packs"
    base_dir = packs_dir / "base-export-1"
    overlay_dir = packs_dir / "overlay-delete"
    base_dir.mkdir(parents=True)
    overlay_dir.mkdir()
    (base_dir / "graph.json").write_text(
        json.dumps({
            "nodes": [
                {"id": "skill:python"},
                {"id": "skill:old"},
            ],
            "edges": [
                {"source": "skill:python", "target": "skill:old", "weight": 0.4},
            ],
        }),
        encoding="utf-8",
    )
    (overlay_dir / "tombstones.jsonl").write_text(
        json.dumps({"node_id": "skill:old", "reason": "deleted"}) + "\n",
        encoding="utf-8",
    )
    write_pack_manifest(
        base_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=base_dir,
            pack_id="base-export-1",
            pack_type="base",
            base_export_id="export-1",
            parent_export_id=None,
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=2,
            edge_count=1,
            artifact_paths=["graph.json"],
        ),
    )
    write_pack_manifest(
        overlay_dir / "graph-pack-manifest.json",
        build_pack_manifest(
            pack_dir=overlay_dir,
            pack_id="overlay-delete",
            pack_type="overlay",
            base_export_id="export-1",
            parent_export_id="export-1",
            config_hash="config-sha",
            model_id="bge-small-en-v1.5",
            node_count=0,
            edge_count=0,
            artifact_paths=["tombstones.jsonl"],
            tombstone_count=1,
        ),
    )

    graph = load_merged_pack_graph(packs_dir)

    assert "skill:old" not in graph
    assert graph.number_of_edges() == 0
