from __future__ import annotations

from pathlib import Path

import networkx as nx

from ctx.core.graph.graph_packs import (
    discover_pack_manifests,
    load_merged_pack_graph,
    write_base_pack,
    write_overlay_pack,
)
from ctx.core.wiki.pack_compaction import compact_active_pack_sets
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
