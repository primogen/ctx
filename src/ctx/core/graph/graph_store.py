"""SQLite operational store for merged ctx graph reads.

The JSON/pack graph remains the source artifact. This module materializes a
small local SQLite store for fast node search and neighborhood lookups.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import networkx as nx

SCHEMA_VERSION = 1


def build_graph_store(db_path: Path, graph: nx.Graph) -> None:
    """Materialize *graph* into a SQLite store at *db_path*."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS metadata;
            DROP TABLE IF EXISTS nodes;
            DROP TABLE IF EXISTS edges;
            CREATE TABLE metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE nodes (
              id TEXT PRIMARY KEY,
              type TEXT,
              label TEXT,
              title TEXT,
              tags_json TEXT NOT NULL,
              attrs_json TEXT NOT NULL,
              search_text TEXT NOT NULL
            );
            CREATE TABLE edges (
              source TEXT NOT NULL,
              target TEXT NOT NULL,
              weight REAL NOT NULL DEFAULT 0.0,
              attrs_json TEXT NOT NULL,
              PRIMARY KEY (source, target)
            );
            CREATE INDEX idx_nodes_type ON nodes(type);
            CREATE INDEX idx_nodes_search_text ON nodes(search_text);
            CREATE INDEX idx_edges_source ON edges(source);
            CREATE INDEX idx_edges_target ON edges(target);
            """
        )
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES(?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        conn.executemany(
            """
            INSERT INTO nodes(id, type, label, title, tags_json, attrs_json, search_text)
            VALUES(:id, :type, :label, :title, :tags_json, :attrs_json, :search_text)
            """,
            (_node_row(node_id, attrs) for node_id, attrs in graph.nodes(data=True)),
        )
        conn.executemany(
            """
            INSERT INTO edges(source, target, weight, attrs_json)
            VALUES(:source, :target, :weight, :attrs_json)
            """,
            (_edge_row(source, target, attrs) for source, target, attrs in graph.edges(data=True)),
        )


def graph_store_stats(db_path: Path) -> dict[str, int]:
    """Return node/edge counts for an existing graph store."""
    with _connect(db_path) as conn:
        return {
            "nodes": int(conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]),
            "edges": int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]),
        }


def search_nodes(db_path: Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search nodes by id, label, title, type, or tags."""
    term = query.strip().lower()
    if not term or limit <= 0:
        return []
    like = f"%{term}%"
    prefix = f"{term}%"
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, type, label, title, tags_json
            FROM nodes
            WHERE search_text LIKE ?
            ORDER BY
              CASE
                WHEN lower(id) = ? OR lower(label) = ? THEN 0
                WHEN lower(id) LIKE ? OR lower(label) LIKE ? THEN 1
                WHEN lower(title) LIKE ? THEN 2
                ELSE 3
              END,
              id
            LIMIT ?
            """,
            (like, term, term, prefix, prefix, like, limit),
        ).fetchall()
    return [_node_result(row) for row in rows]


def load_neighborhood(db_path: Path, node_id: str, *, limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    """Return a 1-hop neighborhood centered on *node_id*."""
    if limit <= 0:
        limit = 1
    with _connect(db_path) as conn:
        center = conn.execute(
            "SELECT id, type, label, title, tags_json FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if center is None:
            return {"nodes": [], "edges": []}
        edge_rows = conn.execute(
            """
            SELECT source, target, weight, attrs_json
            FROM edges
            WHERE source = ? OR target = ?
            ORDER BY weight DESC, source, target
            LIMIT ?
            """,
            (node_id, node_id, limit),
        ).fetchall()
        neighbor_ids = {
            row["target"] if row["source"] == node_id else row["source"]
            for row in edge_rows
        }
        nodes = [_node_result(center)]
        if neighbor_ids:
            placeholders = ",".join("?" for _ in neighbor_ids)
            nodes.extend(
                _node_result(row)
                for row in conn.execute(
                    f"SELECT id, type, label, title, tags_json FROM nodes WHERE id IN ({placeholders})",
                    tuple(sorted(neighbor_ids)),
                ).fetchall()
            )
    edges = [_edge_result(row, center_id=node_id) for row in edge_rows]
    return {"nodes": nodes, "edges": edges}


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _node_row(node_id: str, attrs: dict[str, Any]) -> dict[str, Any]:
    label = _optional_str(attrs.get("label")) or node_id.split(":", 1)[-1]
    title = _optional_str(attrs.get("title")) or label
    entity_type = _optional_str(attrs.get("type"))
    tags = _string_list(attrs.get("tags"))
    search_text = " ".join([node_id, label, title, entity_type or "", *tags]).lower()
    return {
        "id": node_id,
        "type": entity_type,
        "label": label,
        "title": title,
        "tags_json": json.dumps(tags, sort_keys=True),
        "attrs_json": json.dumps(_jsonable(attrs), sort_keys=True),
        "search_text": search_text,
    }


def _edge_row(source: str, target: str, attrs: dict[str, Any]) -> dict[str, Any]:
    weight = attrs.get("final_weight", attrs.get("weight", 0.0))
    try:
        numeric_weight = float(weight)
    except (TypeError, ValueError):
        numeric_weight = 0.0
    return {
        "source": source,
        "target": target,
        "weight": numeric_weight,
        "attrs_json": json.dumps(_jsonable(attrs), sort_keys=True),
    }


def _node_result(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "label": row["label"],
        "title": row["title"],
        "tags": json.loads(row["tags_json"]),
    }


def _edge_result(row: sqlite3.Row, *, center_id: str) -> dict[str, Any]:
    source = row["source"]
    target = row["target"]
    if target == center_id:
        source, target = target, source
    attrs = json.loads(row["attrs_json"])
    return {
        "source": source,
        "target": target,
        "weight": row["weight"],
        "attrs": attrs,
    }


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _jsonable(value: object) -> object:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value
