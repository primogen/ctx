from __future__ import annotations

import gzip
import json
import tarfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from ctx.core.quality.skillspector_audit import (
    SKILLSPECTOR_REPO_URL,
    SkillSpectorAuditRecord,
)
from scripts.prune_skillspector_wiki import build_pruned_artifacts


def _record(slug: str, status: str) -> SkillSpectorAuditRecord:
    return SkillSpectorAuditRecord(
        schema_version=1,
        slug=slug,
        status=status,
        risk_score=100 if status == "blocked" else 0,
        risk_severity="CRITICAL" if status == "blocked" else "LOW",
        recommendation="review",
        issues=1 if status != "passed" else 0,
        components=1,
        content_sha256="abc",
        scanned_at="2026-06-18T00:00:00+00:00",
        scanner="NVIDIA SkillSpector",
        scanner_repo=SKILLSPECTOR_REPO_URL,
        scanner_version="2.2.3",
        mode="static-no-llm",
        llm_requested=False,
    )


def _write_audit(path: Path) -> None:
    records = [_record("remove-me", "blocked"), _record("keep-me", "passed")]
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record.to_json(), sort_keys=True))
            f.write("\n")


def _add_bytes(tf: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o644
    tf.addfile(info, BytesIO(payload))


def _add_text(tf: tarfile.TarFile, name: str, text: str) -> None:
    _add_bytes(tf, name, text.encode("utf-8"))


def _graph() -> dict:
    return {
        "graph": {"export_id": "old"},
        "nodes": [
            {"id": "skill:remove-me", "label": "remove-me", "type": "skill"},
            {"id": "skill:keep-me", "label": "keep-me", "type": "skill"},
            {"id": "agent:helper", "label": "helper", "type": "agent"},
        ],
        "edges": [
            {"source": "skill:remove-me", "target": "agent:helper", "weight": 0.8},
            {"source": "skill:keep-me", "target": "agent:helper", "weight": 0.7},
        ],
    }


def _communities() -> dict:
    return {
        "export_id": "old",
        "total_communities": 1,
        "communities": {
            "0": {
                "label": "demo",
                "members": ["skill:remove-me", "skill:keep-me", "agent:helper"],
            },
        },
    }


def _manifest() -> dict:
    return {
        "version": 1,
        "export_id": "old",
        "artifacts": {
            "graph": "graph.json",
            "delta": "graph-delta.json",
            "communities": "communities.json",
            "report": "graph-report.md",
        },
        "counts": {"nodes": 3, "edges": 2, "communities": 1},
    }


def _catalog() -> dict:
    return {
        "schema_version": 1,
        "skills": [
            {
                "ctx_slug": "remove-me",
                "body_available": True,
                "converted_path": "converted/remove-me/SKILL.md",
                "entity_path": "entities/skills/remove-me.md",
            },
            {
                "ctx_slug": "keep-me",
                "body_available": True,
                "converted_path": "converted/keep-me/SKILL.md",
                "entity_path": "entities/skills/keep-me.md",
            },
        ],
    }


def _write_tar(path: Path, *, runtime: bool = False) -> None:
    with tarfile.open(path, "w:gz") as tf:
        _add_text(tf, "./graphify-out/graph.json", json.dumps(_graph()))
        _add_text(tf, "./graphify-out/graph-delta.json", json.dumps({"export_id": "old"}))
        _add_text(tf, "./graphify-out/communities.json", json.dumps(_communities()))
        _add_text(tf, "./graphify-out/graph-report.md", "# Graph Report\n\n> Export ID: old\n")
        _add_text(tf, "./graphify-out/graph-export-manifest.json", json.dumps(_manifest()))
        _add_text(tf, "./graphify-out/dashboard-neighborhoods.sqlite3", "old")
        _add_text(tf, "./external-catalogs/skills-sh/catalog.json", json.dumps(_catalog()))
        if not runtime:
            _add_text(tf, "./security/skillspector-audit.jsonl.gz", b"".decode())
            _add_text(tf, "./entities/skills/remove-me.md", "# remove-me\n")
            _add_text(tf, "./entities/skills/keep-me.md", "# keep-me\n")
            _add_text(tf, "./converted/remove-me/SKILL.md", "# remove\n")
            _add_text(tf, "./converted/keep-me/SKILL.md", "# keep\n")


def _read_member_json(path: Path, member_name: str) -> dict:
    with tarfile.open(path, "r:gz") as tf:
        member = tf.extractfile(member_name)
        assert member is not None
        return json.loads(member.read().decode("utf-8"))


def _tar_names(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as tf:
        return {member.name.lstrip("./") for member in tf.getmembers()}


def test_prune_skillspector_wiki_dry_run_does_not_mutate(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl.gz"
    full = tmp_path / "wiki-graph.tar.gz"
    runtime = tmp_path / "wiki-graph-runtime.tar.gz"
    catalog = tmp_path / "skills-sh-catalog.json.gz"
    communities = tmp_path / "communities.json"
    _write_audit(audit)
    _write_tar(full)
    _write_tar(runtime, runtime=True)
    catalog.write_bytes(gzip.compress(json.dumps(_catalog()).encode("utf-8")))
    communities.write_text(json.dumps(_communities()), encoding="utf-8")

    stats = build_pruned_artifacts(
        audit_path=audit,
        full_tarball=full,
        runtime_tarball=runtime,
        root_catalog=catalog,
        root_communities=communities,
        graph_dir=tmp_path,
        apply=False,
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )

    assert stats.skill_pages_removed == 1
    assert stats.converted_members_removed == 1
    assert "entities/skills/remove-me.md" in _tar_names(full)


def test_prune_skillspector_wiki_apply_rewrites_artifacts(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl.gz"
    full = tmp_path / "wiki-graph.tar.gz"
    runtime = tmp_path / "wiki-graph-runtime.tar.gz"
    catalog = tmp_path / "skills-sh-catalog.json.gz"
    communities = tmp_path / "communities.json"
    preview = tmp_path / "viz-overview.html"
    _write_audit(audit)
    _write_tar(full)
    _write_tar(runtime, runtime=True)
    catalog.write_bytes(gzip.compress(json.dumps(_catalog()).encode("utf-8")))
    communities.write_text(json.dumps(_communities()), encoding="utf-8")
    preview.write_text(
        '<meta name="ctx-graph-export-id" content="old">\n'
        'const CTX_GRAPH_METADATA = {"export_id":"old","source_graph_nodes":3,'
        '"source_graph_edges":2};\n',
        encoding="utf-8",
    )

    stats = build_pruned_artifacts(
        audit_path=audit,
        full_tarball=full,
        runtime_tarball=runtime,
        root_catalog=catalog,
        root_communities=communities,
        graph_dir=tmp_path,
        apply=True,
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )

    names = _tar_names(full)
    assert "entities/skills/remove-me.md" not in names
    assert "converted/remove-me/SKILL.md" not in names
    assert "entities/skills/keep-me.md" in names
    graph = _read_member_json(full, "./graphify-out/graph.json")
    assert stats.graph_nodes_after == 2
    assert {node["id"] for node in graph["nodes"]} == {"skill:keep-me", "agent:helper"}
    assert graph["edges"] == [
        {"source": "skill:keep-me", "target": "agent:helper", "weight": 0.7},
    ]
    with gzip.open(catalog, "rt", encoding="utf-8") as f:
        root_catalog = json.load(f)
    assert [item["ctx_slug"] for item in root_catalog["skills"]] == ["keep-me"]
    assert "ctx-skillspector-prune-20260618T000000Z-2-1" in preview.read_text(
        encoding="utf-8",
    )
