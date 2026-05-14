"""Incremental graph attach helpers.

This module starts with calibration only. Later phases add vector indexing and
overlay writes on top of the same public contract.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from dataclasses import asdict
from math import ceil
from pathlib import Path
import sys
from typing import Any, Iterable

import networkx as nx
import numpy as np

_PERCENTILES = (50, 60, 75, 90, 95)
_DEFAULT_MIN_SEMANTIC_SCORE = 0.75
_DEFAULT_MIN_FINAL_WEIGHT = 0.03


@dataclass(frozen=True)
class AttachCalibrationSummary:
    """Calibration snapshot used to pick incremental attach defaults."""

    node_count: int
    edge_count: int
    semantic_score_percentiles: dict[int, float]
    final_weight_percentiles: dict[int, float]
    degree_percentiles_by_type: dict[str, dict[int, float]]
    recommended_min_semantic_score: float
    recommended_max_edges_per_node: int
    recommended_min_final_weight: float


def calibrate_attach_defaults(
    graph: nx.Graph,
    *,
    semantic_percentile: int = 60,
    degree_percentile: int = 75,
    max_edges_hard_cap: int = 20,
    min_final_weight: float = _DEFAULT_MIN_FINAL_WEIGHT,
) -> AttachCalibrationSummary:
    """Summarize current graph density and return conservative defaults.

    The semantic floor follows the existing semantic edge distribution. The
    final-weight floor intentionally defaults to the graph builder floor because
    ctx already treats that as the calibrated inclusion gate.
    """
    semantic_scores: list[float] = []
    final_weights: list[float] = []
    for _source, _target, data in graph.edges(data=True):
        semantic = _float_or_none(data.get("semantic_sim"))
        if semantic is not None and semantic > 0.0:
            semantic_scores.append(semantic)
        weight = _float_or_none(data.get("final_weight", data.get("weight")))
        if weight is not None:
            final_weights.append(weight)

    degree_by_type: dict[str, list[float]] = {}
    for node_id, data in graph.nodes(data=True):
        entity_type = str(data.get("type") or str(node_id).split(":", 1)[0])
        degree_by_type.setdefault(entity_type, []).append(float(graph.degree(node_id)))

    semantic_percentiles = _percentiles(semantic_scores)
    final_weight_percentiles = _percentiles(final_weights)
    degree_percentiles_by_type = {
        entity_type: _percentiles(degrees)
        for entity_type, degrees in sorted(degree_by_type.items())
    }

    recommended_semantic = semantic_percentiles.get(
        semantic_percentile,
        _DEFAULT_MIN_SEMANTIC_SCORE,
    )
    recommended_max_edges = _recommended_degree_cap(
        degree_percentiles_by_type,
        degree_percentile=degree_percentile,
        hard_cap=max_edges_hard_cap,
    )
    return AttachCalibrationSummary(
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        semantic_score_percentiles=semantic_percentiles,
        final_weight_percentiles=final_weight_percentiles,
        degree_percentiles_by_type=degree_percentiles_by_type,
        recommended_min_semantic_score=round(recommended_semantic, 4),
        recommended_max_edges_per_node=recommended_max_edges,
        recommended_min_final_weight=round(float(min_final_weight), 4),
    )


def render_calibration_markdown(summary: AttachCalibrationSummary) -> str:
    """Render a compact calibration report for review before setting defaults."""
    lines = [
        "# Incremental Attach Calibration",
        "",
        f"- node_count: {summary.node_count}",
        f"- edge_count: {summary.edge_count}",
        f"- recommended_min_semantic_score: {summary.recommended_min_semantic_score}",
        f"- recommended_max_edges_per_node: {summary.recommended_max_edges_per_node}",
        f"- recommended_min_final_weight: {summary.recommended_min_final_weight}",
        "",
        "## Semantic Score Percentiles",
        _render_percentiles(summary.semantic_score_percentiles),
        "",
        "## Final Weight Percentiles",
        _render_percentiles(summary.final_weight_percentiles),
        "",
        "## Degree Percentiles By Type",
    ]
    if summary.degree_percentiles_by_type:
        for entity_type, percentiles in summary.degree_percentiles_by_type.items():
            lines.append(f"- {entity_type}: {_inline_percentiles(percentiles)}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ctx.core.graph.incremental_attach",
        description="Incremental graph attach utilities.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    calibrate = sub.add_parser("calibrate", help="Calibrate attach defaults from graph.json")
    calibrate.add_argument("--graph", required=True, help="Path to graphify-out/graph.json")
    calibrate.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)
    if args.command == "calibrate":
        from ctx.core.graph.resolve_graph import load_graph  # noqa: PLC0415

        graph = load_graph(Path(args.graph))
        summary = calibrate_attach_defaults(graph)
        if args.json:
            print(json.dumps(asdict(summary), indent=2))
        else:
            print(render_calibration_markdown(summary), end="")
        return 0
    return 1


def _percentiles(values: Iterable[float]) -> dict[int, float]:
    series = [value for value in values if value >= 0.0]
    if not series:
        return {}
    array = np.asarray(series, dtype=np.float64)
    return {
        percentile: round(float(np.percentile(array, percentile)), 4)
        for percentile in _PERCENTILES
    }


def _recommended_degree_cap(
    degree_percentiles_by_type: dict[str, dict[int, float]],
    *,
    degree_percentile: int,
    hard_cap: int,
) -> int:
    if not degree_percentiles_by_type:
        return 1
    cap = max(
        percentiles.get(degree_percentile, 0.0)
        for percentiles in degree_percentiles_by_type.values()
    )
    return max(1, min(int(hard_cap), int(ceil(cap))))


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _render_percentiles(percentiles: dict[int, float]) -> str:
    if not percentiles:
        return "- none"
    return "\n".join(f"- p{key}: {value}" for key, value in percentiles.items())


def _inline_percentiles(percentiles: dict[int, float]) -> str:
    return ", ".join(f"p{key}={value}" for key, value in percentiles.items())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
