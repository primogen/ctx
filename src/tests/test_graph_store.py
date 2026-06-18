from __future__ import annotations

from pathlib import Path

import networkx as nx

from ctx.core.graph.graph_store import (
    build_graph_store,
    graph_store_stats,
    load_neighborhood,
    search_nodes,
)


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
