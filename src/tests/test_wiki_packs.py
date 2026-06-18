from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctx.core.wiki.wiki_packs import (
    WikiPackManifestError,
    compact_wiki_packs,
    discover_wiki_pack_manifests,
    load_merged_wiki_pages,
    promote_wiki_pack_set,
    read_wiki_pack_manifest,
    write_wiki_base_pack,
    write_wiki_overlay_pack,
)


def test_wiki_base_pack_manifest_round_trips(tmp_path: Path) -> None:
    pack_dir = tmp_path / "wiki-packs" / "base-export-1"

    manifest = write_wiki_base_pack(
        pack_dir=pack_dir,
        pack_id="base-export-1",
        base_export_id="wiki-export-1",
        pages={
            "index.md": "# Index\n",
            "entities/skills/python.md": "# Python\n",
        },
    )

    assert manifest.pack_type == "base"
    assert manifest.page_count == 2
    assert manifest.tombstone_count == 0
    assert read_wiki_pack_manifest(pack_dir / "wiki-pack-manifest.json") == manifest
    assert json.loads((pack_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()[0])[
        "path"
    ] == "entities/skills/python.md"


def test_load_merged_wiki_pages_applies_overlay_and_tombstones(tmp_path: Path) -> None:
    packs_dir = tmp_path / "wiki-packs"
    write_wiki_base_pack(
        pack_dir=packs_dir / "base-export-1",
        pack_id="base-export-1",
        base_export_id="wiki-export-1",
        pages={
            "entities/skills/python.md": "# Python\nold body\n",
            "entities/skills/docker.md": "# Docker\n",
        },
    )
    write_wiki_overlay_pack(
        pack_dir=packs_dir / "overlay-review",
        pack_id="overlay-review",
        base_export_id="wiki-export-1",
        parent_export_id="wiki-export-1",
        pages={
            "entities/skills/python.md": "# Python\nnew body\n",
            "entities/agents/reviewer.md": "# Reviewer\n",
        },
        tombstones=["entities/skills/docker.md"],
    )

    pages = load_merged_wiki_pages(packs_dir)

    assert pages == {
        "entities/agents/reviewer.md": "# Reviewer\n",
        "entities/skills/python.md": "# Python\nnew body\n",
    }


def test_discover_wiki_pack_manifests_rejects_parent_mismatch(tmp_path: Path) -> None:
    packs_dir = tmp_path / "wiki-packs"
    write_wiki_base_pack(
        pack_dir=packs_dir / "base-export-1",
        pack_id="base-export-1",
        base_export_id="wiki-export-1",
        pages={"index.md": "# Index\n"},
    )
    write_wiki_overlay_pack(
        pack_dir=packs_dir / "overlay-bad",
        pack_id="overlay-bad",
        base_export_id="wiki-export-1",
        parent_export_id="other-export",
        pages={"entities/skills/review.md": "# Review\n"},
        tombstones=[],
    )

    with pytest.raises(WikiPackManifestError, match="parent_export_id"):
        discover_wiki_pack_manifests(packs_dir)


def test_wiki_pack_writer_rejects_unsafe_page_paths(tmp_path: Path) -> None:
    with pytest.raises(WikiPackManifestError, match="unsafe"):
        write_wiki_base_pack(
            pack_dir=tmp_path / "wiki-packs" / "base-export-1",
            pack_id="base-export-1",
            base_export_id="wiki-export-1",
            pages={"../entities/skills/evil.md": "# Evil\n"},
        )


def test_load_merged_wiki_pages_rejects_page_checksum_drift(tmp_path: Path) -> None:
    packs_dir = tmp_path / "wiki-packs"
    base_dir = packs_dir / "base-export-1"
    write_wiki_base_pack(
        pack_dir=base_dir,
        pack_id="base-export-1",
        base_export_id="wiki-export-1",
        pages={"index.md": "# Index\n"},
    )
    rows = (base_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[0])
    payload["text"] = "# Tampered\n"
    (base_dir / "pages.jsonl").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(WikiPackManifestError, match="checksum mismatch"):
        load_merged_wiki_pages(packs_dir)


def test_compact_wiki_packs_writes_staged_base_without_mutating_active_packs(
    tmp_path: Path,
) -> None:
    active_packs = tmp_path / "active" / "wiki-packs"
    write_wiki_base_pack(
        pack_dir=active_packs / "base-export-1",
        pack_id="base-export-1",
        base_export_id="wiki-export-1",
        pages={
            "entities/skills/python.md": "# Python\nold\n",
            "entities/skills/docker.md": "# Docker\n",
        },
    )
    write_wiki_overlay_pack(
        pack_dir=active_packs / "overlay-review",
        pack_id="overlay-review",
        base_export_id="wiki-export-1",
        parent_export_id="wiki-export-1",
        pages={
            "entities/skills/python.md": "# Python\nnew\n",
            "entities/agents/reviewer.md": "# Reviewer\n",
        },
        tombstones=["entities/skills/docker.md"],
    )
    staged_pack = tmp_path / "staged" / "base-export-2"

    manifest = compact_wiki_packs(
        packs_dir=active_packs,
        compacted_pack_dir=staged_pack,
        base_export_id="wiki-export-2",
    )

    assert manifest.pack_type == "base"
    assert manifest.base_export_id == "wiki-export-2"
    assert [entry.manifest.pack_id for entry in discover_wiki_pack_manifests(active_packs)] == [
        "base-export-1",
        "overlay-review",
    ]
    assert load_merged_wiki_pages(tmp_path / "staged") == {
        "entities/agents/reviewer.md": "# Reviewer\n",
        "entities/skills/python.md": "# Python\nnew\n",
    }


def test_promote_wiki_pack_set_replaces_active_and_writes_rollback_metadata(
    tmp_path: Path,
) -> None:
    active_packs = tmp_path / "wiki" / "wiki-packs"
    write_wiki_base_pack(
        pack_dir=active_packs / "base-export-1",
        pack_id="base-export-1",
        base_export_id="wiki-export-1",
        pages={"entities/skills/old.md": "# Old\n"},
    )
    staged_packs = tmp_path / "staged-packs"
    write_wiki_base_pack(
        pack_dir=staged_packs / "base-export-2",
        pack_id="base-export-2",
        base_export_id="wiki-export-2",
        pages={"entities/skills/new.md": "# New\n"},
    )
    backup_packs = tmp_path / "wiki" / "wiki-packs.rollback"

    result = promote_wiki_pack_set(
        staged_packs_dir=staged_packs,
        active_packs_dir=active_packs,
        backup_packs_dir=backup_packs,
    )

    assert result.promoted_pack_ids == ["base-export-2"]
    assert result.replaced_pack_ids == ["base-export-1"]
    assert not staged_packs.exists()
    assert load_merged_wiki_pages(active_packs) == {"entities/skills/new.md": "# New\n"}
    assert load_merged_wiki_pages(backup_packs) == {"entities/skills/old.md": "# Old\n"}
    rollback_metadata = json.loads(result.rollback_metadata_path.read_text(encoding="utf-8"))
    assert rollback_metadata["backup_packs_dir"] == str(backup_packs)
    assert rollback_metadata["promoted_pack_ids"] == ["base-export-2"]
    assert rollback_metadata["replaced_pack_ids"] == ["base-export-1"]
