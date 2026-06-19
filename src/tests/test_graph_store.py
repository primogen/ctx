from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import networkx as nx

from ctx.core.graph.graph_store import (
    build_graph_store,
    build_graph_store_from_graph_dir,
    ensure_graph_store,
    graph_store_metadata,
    graph_store_is_fresh,
    graph_store_stats,
    validate_graph_store,
    load_neighborhood,
    main,
    search_nodes,
)
from ctx.core.graph.graph_packs import write_base_pack, write_overlay_pack


def _sample_graph() -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(
        "skill:python-testing",
        label="python-testing",
        title="Python Testing",
        type="skill",
        tags=["python", "testing"],
        quality_score=0.9,
    )
    graph.add_node(
        "mcp-server:github",
        label="github",
        title="GitHub",
        type="mcp-server",
        tags=["github", "repos"],
    )
    graph.add_node(
        "agent:reviewer",
        label="reviewer",
        title="Code Reviewer",
        type="agent",
        tags=["review", "testing"],
    )
    graph.add_edge(
        "skill:python-testing",
        "mcp-server:github",
        weight=0.72,
        shared_tags=["testing"],
    )
    graph.add_edge(
        "skill:python-testing",
        "agent:reviewer",
        weight=0.81,
        shared_tags=["testing"],
    )
    return graph


def test_build_graph_store_persists_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"

    build_graph_store(db_path, _sample_graph())

    assert graph_store_stats(db_path) == {"nodes": 3, "edges": 2}


def test_search_nodes_matches_label_title_and_tags(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"
    build_graph_store(db_path, _sample_graph())

    results = search_nodes(db_path, "testing", limit=10)

    assert [row["id"] for row in results] == [
        "skill:python-testing",
        "agent:reviewer",
    ]
    assert results[0]["type"] == "skill"


def test_load_neighborhood_returns_center_and_edges(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"
    build_graph_store(db_path, _sample_graph())

    neighborhood = load_neighborhood(db_path, "skill:python-testing", limit=10)

    assert {node["id"] for node in neighborhood["nodes"]} == {
        "skill:python-testing",
        "mcp-server:github",
        "agent:reviewer",
    }
    assert {edge["target"] for edge in neighborhood["edges"]} == {
        "mcp-server:github",
        "agent:reviewer",
    }


def test_build_graph_store_from_graph_dir_prefers_active_packs(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    packs_dir = graph_dir / "packs"
    base_graph = nx.Graph()
    base_graph.add_node(
        "skill:base",
        label="base",
        title="Base",
        type="skill",
        tags=["base"],
    )
    base_graph.add_node(
        "mcp-server:github",
        label="github",
        title="GitHub",
        type="mcp-server",
        tags=["github"],
    )
    base_graph.add_edge("skill:base", "mcp-server:github", weight=0.2)
    write_base_pack(
        pack_dir=packs_dir / "base-export-1",
        pack_id="base-export-1",
        base_export_id="export-1",
        config_hash="config-sha",
        model_id="bge-small-en-v1.5",
        graph=base_graph,
    )
    write_overlay_pack(
        pack_dir=packs_dir / "overlay-review",
        pack_id="overlay-review",
        base_export_id="export-1",
        parent_export_id="export-1",
        config_hash="config-sha",
        model_id="bge-small-en-v1.5",
        nodes=[
            {
                "id": "skill:review",
                "label": "review",
                "title": "Code Review",
                "type": "skill",
                "tags": ["review"],
            }
        ],
        edges=[
            {
                "source": "skill:review",
                "target": "mcp-server:github",
                "weight": 0.9,
            }
        ],
        tombstones=[],
    )
    db_path = tmp_path / "graph.sqlite3"

    build_graph_store_from_graph_dir(graph_dir, db_path)

    assert graph_store_stats(db_path) == {"nodes": 3, "edges": 2}
    assert [row["id"] for row in search_nodes(db_path, "review")] == ["skill:review"]
    neighborhood = load_neighborhood(db_path, "skill:review")
    assert {edge["target"] for edge in neighborhood["edges"]} == {"mcp-server:github"}
    metadata = graph_store_metadata(db_path)
    assert metadata["ctx_graph_pack_source"] == "packs"
    assert json.loads(metadata["ctx_pack_ids"]) == ["base-export-1", "overlay-review"]
    assert metadata["ctx_pack_base_export_id"] == "export-1"
    assert metadata["node_count"] == "3"
    assert metadata["edge_count"] == "2"
    assert graph_store_is_fresh(db_path, graph_dir) is True
    write_overlay_pack(
        pack_dir=packs_dir / "overlay-docs",
        pack_id="overlay-docs",
        base_export_id="export-1",
        parent_export_id="export-1",
        config_hash="config-sha",
        model_id="bge-small-en-v1.5",
        nodes=[
            {
                "id": "skill:docs",
                "label": "docs",
                "title": "Docs",
                "type": "skill",
                "tags": ["docs"],
            }
        ],
        edges=[],
        tombstones=[],
    )
    assert graph_store_is_fresh(db_path, graph_dir) is False


def test_build_graph_store_from_graph_dir_falls_back_to_legacy_graph_json(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    graph = _sample_graph()
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"

    build_graph_store_from_graph_dir(graph_dir, db_path)

    assert graph_store_stats(db_path) == {"nodes": 3, "edges": 2}
    assert search_nodes(db_path, "github")[0]["id"] == "mcp-server:github"
    assert graph_store_is_fresh(db_path, graph_dir) is True
    graph.add_node("skill:docs", label="docs", type="skill", tags=["docs"])
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    assert graph_store_is_fresh(db_path, graph_dir) is False


def test_cli_builds_graph_store_from_graph_dir(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    payload = nx.node_link_data(_sample_graph(), edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"

    assert main(["build", "--graph-dir", str(graph_dir), "--db", str(db_path)]) == 0

    assert graph_store_stats(db_path) == {"nodes": 3, "edges": 2}


def test_cli_validates_fresh_graph_store(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    payload = nx.node_link_data(_sample_graph(), edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"
    ensure_graph_store(graph_dir, db_path)

    result = main(["validate", "--graph-dir", str(graph_dir), "--db", str(db_path)])

    assert result == 0


def test_cli_validate_returns_1_for_stale_graph_store(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    graph = _sample_graph()
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"
    ensure_graph_store(graph_dir, db_path)
    graph.add_node("skill:docs", label="docs", type="skill", tags=["docs"])
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")

    result = main(["validate", "--graph-dir", str(graph_dir), "--db", str(db_path)])

    assert result == 1


def test_ensure_graph_store_reuses_fresh_store_and_rebuilds_stale_store(
    tmp_path: Path,
) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    graph = _sample_graph()
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"

    first = ensure_graph_store(graph_dir, db_path)
    second = ensure_graph_store(graph_dir, db_path)

    assert first == {"rebuilt": True, "nodes": 3, "edges": 2}
    assert second == {"rebuilt": False, "nodes": 3, "edges": 2}

    graph.add_node("skill:docs", label="docs", type="skill", tags=["docs"])
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")

    third = ensure_graph_store(graph_dir, db_path)

    assert third == {"rebuilt": True, "nodes": 4, "edges": 2}
    assert search_nodes(db_path, "docs")[0]["id"] == "skill:docs"


def test_validate_graph_store_reports_fresh_store(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    payload = nx.node_link_data(_sample_graph(), edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"
    ensure_graph_store(graph_dir, db_path)

    report = validate_graph_store(db_path, graph_dir)

    assert report == {
        "ok": True,
        "fresh": True,
        "nodes": 3,
        "edges": 2,
        "errors": [],
    }


def test_validate_graph_store_reports_stale_source(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    graph = _sample_graph()
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"
    ensure_graph_store(graph_dir, db_path)
    graph.add_node("skill:docs", label="docs", type="skill", tags=["docs"])
    payload = nx.node_link_data(graph, edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")

    report = validate_graph_store(db_path, graph_dir)

    assert report["ok"] is False
    assert report["fresh"] is False
    errors = report["errors"]
    assert isinstance(errors, list)
    assert "source fingerprint is stale" in errors


def test_validate_graph_store_reports_corrupt_count_metadata(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    payload = nx.node_link_data(_sample_graph(), edges="edges")
    (graph_dir / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "graph.sqlite3"
    ensure_graph_store(graph_dir, db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE metadata SET value = '99' WHERE key = 'node_count'")

    report = validate_graph_store(db_path, graph_dir)

    assert report["ok"] is False
    assert report["fresh"] is True
    errors = report["errors"]
    assert isinstance(errors, list)
    assert "metadata node_count 99 != actual 3" in errors
