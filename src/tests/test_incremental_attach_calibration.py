from __future__ import annotations

import networkx as nx
import pytest
from networkx.readwrite import node_link_data

from ctx.core.graph.incremental_attach import (
    calibrate_attach_defaults,
    main,
    render_calibration_markdown,
)


def test_calibrate_attach_defaults_uses_existing_graph_distributions() -> None:
    G = nx.Graph()
    G.add_node("skill:a", type="skill")
    G.add_node("skill:b", type="skill")
    G.add_node("agent:c", type="agent")
    G.add_node("mcp-server:d", type="mcp-server")
    G.add_edge("skill:a", "skill:b", semantic_sim=0.9, final_weight=0.7, weight=0.7)
    G.add_edge("skill:a", "agent:c", semantic_sim=0.8, final_weight=0.5, weight=0.5)
    G.add_edge("skill:a", "mcp-server:d", semantic_sim=0.6, final_weight=0.3, weight=0.3)
    G.add_edge("skill:b", "agent:c", semantic_sim=0.4, final_weight=0.2, weight=0.2)

    summary = calibrate_attach_defaults(G)

    assert summary.node_count == 4
    assert summary.edge_count == 4
    assert summary.semantic_score_percentiles[50] == pytest.approx(0.7)
    assert summary.final_weight_percentiles[75] == pytest.approx(0.55)
    assert summary.degree_percentiles_by_type["skill"][75] == pytest.approx(2.75)
    assert summary.recommended_min_semantic_score == pytest.approx(0.76)
    assert summary.recommended_max_edges_per_node == 3
    assert summary.recommended_min_final_weight == pytest.approx(0.03)


def test_calibrate_attach_defaults_ignores_missing_semantic_scores() -> None:
    G = nx.Graph()
    G.add_node("skill:a", type="skill")
    G.add_node("skill:b", type="skill")
    G.add_edge("skill:a", "skill:b", weight=0.4)

    summary = calibrate_attach_defaults(G)

    assert summary.semantic_score_percentiles == {}
    assert summary.final_weight_percentiles[50] == pytest.approx(0.4)
    assert summary.recommended_min_semantic_score == pytest.approx(0.75)
    assert summary.recommended_max_edges_per_node == 1


def test_calibrate_attach_defaults_ignores_zero_semantic_edges_and_caps_degree() -> None:
    G = nx.Graph()
    for index in range(25):
        G.add_node(f"skill:{index}", type="skill")
    for source in range(25):
        for target in range(source + 1, 25):
            G.add_edge(
                f"skill:{source}",
                f"skill:{target}",
                semantic_sim=0.82,
                final_weight=0.1,
            )

    summary = calibrate_attach_defaults(G)

    assert summary.semantic_score_percentiles[50] == pytest.approx(0.82)
    assert summary.recommended_max_edges_per_node == 20


def test_render_calibration_markdown_includes_recommended_defaults() -> None:
    G = nx.Graph()
    G.add_node("skill:a", type="skill")
    summary = calibrate_attach_defaults(G)

    report = render_calibration_markdown(summary)

    assert "# Incremental Attach Calibration" in report
    assert "recommended_min_semantic_score" in report
    assert "recommended_max_edges_per_node" in report


def test_main_calibrate_outputs_json(tmp_path, capsys) -> None:
    G = nx.Graph()
    G.add_node("skill:a", type="skill")
    G.add_node("skill:b", type="skill")
    G.add_edge("skill:a", "skill:b", semantic_sim=0.8, final_weight=0.4)
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        __import__("json").dumps(node_link_data(G, edges="edges")),
        encoding="utf-8",
    )

    assert main(["calibrate", "--graph", str(graph_path), "--json"]) == 0

    output = capsys.readouterr().out
    assert '"node_count": 2' in output
    assert '"recommended_min_semantic_score": 0.8' in output
