from __future__ import annotations

import networkx as nx

from ctx.core.wiki.pack_validation import validate_graph_wiki_consistency


def test_validate_graph_wiki_consistency_accepts_matching_entity_pages() -> None:
    graph = nx.Graph()
    graph.add_node("skill:python", type="skill")
    graph.add_node("agent:reviewer", type="agent")
    graph.add_node("mcp-server:github", type="mcp-server")
    graph.add_node("harness:mirage", type="harness")
    pages = {
        "entities/skills/python.md": "# Python\n",
        "entities/agents/reviewer.md": "# Reviewer\n",
        "entities/mcp-servers/g/github.md": "# GitHub\n",
        "entities/harnesses/mirage.md": "# Mirage\n",
    }

    report = validate_graph_wiki_consistency(graph, pages)

    assert report.ok is True
    assert report.missing_wiki_pages == []
    assert report.orphan_wiki_pages == []


def test_validate_graph_wiki_consistency_reports_missing_wiki_pages() -> None:
    graph = nx.Graph()
    graph.add_node("skill:python", type="skill")
    graph.add_node("mcp-server:github", type="mcp-server")

    report = validate_graph_wiki_consistency(graph, {"entities/skills/python.md": "# Python\n"})

    assert report.ok is False
    assert report.missing_wiki_pages == [
        {
            "node_id": "mcp-server:github",
            "expected_paths": [
                "entities/mcp-servers/g/github.md",
                "entities/mcp-servers/github.md",
            ],
        },
    ]


def test_validate_graph_wiki_consistency_reports_orphan_wiki_pages() -> None:
    graph = nx.Graph()
    graph.add_node("skill:python", type="skill")
    pages = {
        "entities/skills/python.md": "# Python\n",
        "entities/harnesses/mirage.md": "# Mirage\n",
    }

    report = validate_graph_wiki_consistency(graph, pages)

    assert report.ok is False
    assert report.orphan_wiki_pages == [
        {
            "path": "entities/harnesses/mirage.md",
            "expected_node_id": "harness:mirage",
        },
    ]
