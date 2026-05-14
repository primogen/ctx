from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from ctx.core.graph.semantic_edges import (
    _l2_normalize,
    _topk_pairs,
    _topk_pairs_subset_with_optional_index,
)
from ctx.core.wiki import wiki_graphify as wg


def test_shadow_indexed_subset_matches_batch_semantic_candidates() -> None:
    vecs = _l2_normalize(
        np.array(
            [
                [1.0, 0.0],
                [0.95, 0.05],
                [0.0, 1.0],
                [0.97, 0.03],
            ],
            dtype="float32",
        )
    )
    node_ids = ["skill:alpha", "skill:beta", "skill:gamma", "skill:new"]
    hashes = ["ha", "hb", "hc", "hn"]

    batch = {
        pair: score
        for pair, score in _topk_pairs(vecs, node_ids, top_k=2, min_cosine=0.5).items()
        if "skill:new" in pair
    }
    indexed = _topk_pairs_subset_with_optional_index(
        vecs,
        node_ids,
        hashes,
        [3],
        top_k=2,
        min_cosine=0.5,
        vector_index_kind="numpy-flat",
        model_id="model-a",
        ann_enabled_above_nodes=1,
        cache_dir=Path(),
        persist_index=False,
    )

    assert indexed == batch


def test_shadow_incremental_graph_matches_full_graph(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import ctx_config

    wiki = tmp_path / "wiki"
    _isolate_graphify(wiki, tmp_path / "quality", monkeypatch)
    monkeypatch.setattr(ctx_config.cfg, "graph_edge_weight_semantic", 0.0)

    _write_entity(wiki / "entities" / "skills" / "alpha.md", "alpha", ["python"])
    _write_entity(wiki / "entities" / "skills" / "beta.md", "beta", ["python"])
    prior, _ = wg.build_graph(incremental=False)

    _write_entity(wiki / "entities" / "skills" / "gamma.md", "gamma", ["python"])
    monkeypatch.setattr(wg, "load_prior_graph", lambda: prior.copy())
    incremental, _ = wg.build_graph(incremental=True)

    monkeypatch.setattr(wg, "load_prior_graph", lambda: None)
    full, _ = wg.build_graph(incremental=False)

    assert _node_snapshot(incremental) == _node_snapshot(full)
    assert _edge_snapshot(incremental) == _edge_snapshot(full)


def _isolate_graphify(wiki: Path, quality: Path, monkeypatch) -> None:
    monkeypatch.setattr(wg, "WIKI_DIR", wiki)
    monkeypatch.setattr(wg, "SKILL_ENTITIES", wiki / "entities" / "skills")
    monkeypatch.setattr(wg, "AGENT_ENTITIES", wiki / "entities" / "agents")
    monkeypatch.setattr(wg, "MCP_ENTITIES", wiki / "entities" / "mcp-servers")
    monkeypatch.setattr(wg, "HARNESS_ENTITIES", wiki / "entities" / "harnesses")
    monkeypatch.setattr(wg, "GRAPH_OUT", wiki / "graphify-out")
    monkeypatch.setattr(wg, "QUALITY_SIDECAR_DIR", quality)
    monkeypatch.setattr(wg, "load_prior_graph", lambda: None)


def _write_entity(path: Path, slug: str, tags: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"title: {slug}", "type: skill", "tags:"]
    lines.extend(f"  - {tag}" for tag in tags)
    lines.extend(["---", f"# {slug}", "body"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _node_snapshot(G: nx.Graph) -> dict[str, dict[str, Any]]:
    keys = {"label", "type", "tags", "never_load"}
    return {
        node_id: {key: G.nodes[node_id].get(key) for key in keys}
        for node_id in sorted(G.nodes)
    }


def _edge_snapshot(G: nx.Graph) -> dict[tuple[str, str], dict[str, Any]]:
    keys = {
        "weight",
        "final_weight",
        "semantic_sim",
        "tag_sim",
        "token_sim",
        "shared_tags",
        "shared_tokens",
        "edge_reasons",
    }
    return {
        tuple(sorted((left, right))): {key: attrs.get(key) for key in keys}
        for left, right, attrs in G.edges(data=True)
    }
