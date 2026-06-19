from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from ctx.core.graph.graph_packs import (
    discover_pack_manifests,
    load_merged_pack_graph,
    write_base_pack,
    write_overlay_pack,
)
from ctx.core.wiki import pack_compaction
from ctx.core.wiki.pack_compaction import (
    PackCompactionError,
    compact_active_pack_sets,
    promote_staged_pack_sets,
)
from ctx.core.wiki.wiki_packs import (
    discover_wiki_pack_manifests,
    load_merged_wiki_pages,
    write_wiki_base_pack,
    write_wiki_overlay_pack,
)


def test_compact_active_pack_sets_stages_graph_and_wiki_without_mutating_active(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "wiki"
    graph_packs, wiki_packs = _write_active_pack_sets(wiki)
    staging_dir = tmp_path / "staged-compaction"

    result = compact_active_pack_sets(
        wiki_path=wiki,
        base_export_id="export-2",
        staging_dir=staging_dir,
    )

    assert result.graph_manifest.pack_id == "base-export-2"
    assert result.wiki_manifest.pack_id == "base-export-2"
    assert [entry.manifest.pack_id for entry in discover_pack_manifests(graph_packs)] == [
        "base-export-1",
        "overlay-new",
    ]
    assert [entry.manifest.pack_id for entry in discover_wiki_pack_manifests(wiki_packs)] == [
        "base-export-1",
        "overlay-new",
    ]
    compacted_graph = load_merged_pack_graph(staging_dir / "graph-packs")
    assert "skill:old" not in compacted_graph
    assert compacted_graph.has_edge("skill:new", "skill:keep")
    assert load_merged_wiki_pages(staging_dir / "wiki-packs") == {
        "entities/skills/keep.md": "# Keep\n",
        "entities/skills/new.md": "# New\n",
    }
    manifest = json.loads((staging_dir / "pack-compaction-manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["operation"] == "pack-compaction-stage"
    assert manifest["base_export_id"] == "export-2"
    assert manifest["staged_graph_packs_dir"] == str(staging_dir / "graph-packs")
    assert manifest["staged_wiki_packs_dir"] == str(staging_dir / "wiki-packs")
    assert manifest["graph"]["pack_id"] == "base-export-2"
    assert manifest["wiki"]["pack_id"] == "base-export-2"


def test_pack_compaction_cli_emits_json_for_staged_pack_sets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiki = tmp_path / "wiki"
    _write_active_pack_sets(wiki)
    staging_dir = tmp_path / "staged-compaction"

    result = pack_compaction.main([
        "compact",
        "--wiki-path",
        str(wiki),
        "--base-export-id",
        "export-2",
        "--staging-dir",
        str(staging_dir),
        "--json",
    ])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph"]["pack_id"] == "base-export-2"
    assert payload["wiki"]["pack_id"] == "base-export-2"
    assert payload["staged_graph_packs_dir"] == str(staging_dir / "graph-packs")
    assert payload["staged_wiki_packs_dir"] == str(staging_dir / "wiki-packs")
    assert "skill:old" not in load_merged_pack_graph(staging_dir / "graph-packs")
    assert "entities/skills/old.md" not in load_merged_wiki_pages(staging_dir / "wiki-packs")


def test_promote_staged_pack_sets_replaces_graph_and_wiki_with_backups(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "wiki"
    _write_active_pack_sets(wiki)
    staged = compact_active_pack_sets(
        wiki_path=wiki,
        base_export_id="export-2",
        staging_dir=tmp_path / "staged-compaction",
    )

    result = promote_staged_pack_sets(
        wiki_path=wiki,
        staged_graph_packs_dir=staged.staged_graph_packs_dir,
        staged_wiki_packs_dir=staged.staged_wiki_packs_dir,
        graph_backup_packs_dir=tmp_path / "graph-packs.backup",
        wiki_backup_packs_dir=tmp_path / "wiki-packs.backup",
    )

    active_graph = load_merged_pack_graph(wiki / "graphify-out" / "packs")
    assert "skill:old" not in active_graph
    assert active_graph.has_edge("skill:new", "skill:keep")
    assert load_merged_wiki_pages(wiki / "wiki-packs") == {
        "entities/skills/keep.md": "# Keep\n",
        "entities/skills/new.md": "# New\n",
    }
    backup_graph = load_merged_pack_graph(tmp_path / "graph-packs.backup")
    assert "skill:old" not in backup_graph
    assert backup_graph.has_edge("skill:new", "skill:keep")
    assert [entry.manifest.pack_id for entry in discover_pack_manifests(tmp_path / "graph-packs.backup")] == [
        "base-export-1",
        "overlay-new",
    ]
    assert load_merged_wiki_pages(tmp_path / "wiki-packs.backup") == {
        "entities/skills/keep.md": "# Keep\n",
        "entities/skills/new.md": "# New\n",
    }
    assert [entry.manifest.pack_id for entry in discover_wiki_pack_manifests(tmp_path / "wiki-packs.backup")] == [
        "base-export-1",
        "overlay-new",
    ]
    assert result.graph.promoted_pack_ids == ["base-export-2"]
    assert result.wiki.promoted_pack_ids == ["base-export-2"]


def test_pack_compaction_cli_promotes_staged_pack_sets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiki = tmp_path / "wiki"
    _write_active_pack_sets(wiki)
    staged = compact_active_pack_sets(
        wiki_path=wiki,
        base_export_id="export-2",
        staging_dir=tmp_path / "staged-compaction",
    )

    rc = pack_compaction.main([
        "promote",
        "--wiki-path",
        str(wiki),
        "--staged-graph-packs-dir",
        str(staged.staged_graph_packs_dir),
        "--staged-wiki-packs-dir",
        str(staged.staged_wiki_packs_dir),
        "--graph-backup-packs-dir",
        str(tmp_path / "graph-packs.backup"),
        "--wiki-backup-packs-dir",
        str(tmp_path / "wiki-packs.backup"),
        "--json",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph"]["promoted_pack_ids"] == ["base-export-2"]
    assert payload["wiki"]["promoted_pack_ids"] == ["base-export-2"]
    assert "skill:old" not in load_merged_pack_graph(wiki / "graphify-out" / "packs")
    assert "entities/skills/old.md" not in load_merged_wiki_pages(wiki / "wiki-packs")


def test_promote_staged_pack_sets_rejects_invalid_staged_wiki_before_graph_swap(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "wiki"
    _write_active_pack_sets(wiki)
    staged = compact_active_pack_sets(
        wiki_path=wiki,
        base_export_id="export-2",
        staging_dir=tmp_path / "staged-compaction",
    )
    pages_path = staged.staged_wiki_packs_dir / "base-export-2" / "pages.jsonl"
    pages_path.write_text('{"path":"entities/skills/new.md","text":"tampered","sha256":"bad"}\n')

    with pytest.raises(PackCompactionError, match="checksum mismatch"):
        promote_staged_pack_sets(
            wiki_path=wiki,
            staged_graph_packs_dir=staged.staged_graph_packs_dir,
            staged_wiki_packs_dir=staged.staged_wiki_packs_dir,
        )

    assert [entry.manifest.pack_id for entry in discover_pack_manifests(wiki / "graphify-out" / "packs")] == [
        "base-export-1",
        "overlay-new",
    ]
    assert [entry.manifest.pack_id for entry in discover_wiki_pack_manifests(wiki / "wiki-packs")] == [
        "base-export-1",
        "overlay-new",
    ]


def _write_active_pack_sets(wiki: Path) -> tuple[Path, Path]:
    graph_packs = wiki / "graphify-out" / "packs"
    wiki_packs = wiki / "wiki-packs"
    graph = nx.Graph()
    graph.add_node("skill:old", type="skill", label="old")
    graph.add_node("skill:keep", type="skill", label="keep")
    graph.add_edge("skill:old", "skill:keep", weight=0.2)
    write_base_pack(
        pack_dir=graph_packs / "base-export-1",
        pack_id="base-export-1",
        base_export_id="export-1",
        config_hash="config-1",
        model_id="model-1",
        graph=graph,
    )
    write_overlay_pack(
        pack_dir=graph_packs / "overlay-new",
        pack_id="overlay-new",
        base_export_id="export-1",
        parent_export_id="export-1",
        config_hash="config-1",
        model_id="model-1",
        nodes=[{"id": "skill:new", "type": "skill", "label": "new"}],
        edges=[{"source": "skill:new", "target": "skill:keep", "weight": 0.9}],
        tombstones=[{"node_id": "skill:old"}],
    )
    write_wiki_base_pack(
        pack_dir=wiki_packs / "base-export-1",
        pack_id="base-export-1",
        base_export_id="export-1",
        pages={
            "entities/skills/old.md": "# Old\n",
            "entities/skills/keep.md": "# Keep\n",
        },
    )
    write_wiki_overlay_pack(
        pack_dir=wiki_packs / "overlay-new",
        pack_id="overlay-new",
        base_export_id="export-1",
        parent_export_id="export-1",
        pages={"entities/skills/new.md": "# New\n"},
        tombstones=["entities/skills/old.md"],
    )
    return graph_packs, wiki_packs
