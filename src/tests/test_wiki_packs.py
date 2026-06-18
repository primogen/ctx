from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctx.core.wiki.wiki_packs import (
    WikiPackManifestError,
    discover_wiki_pack_manifests,
    load_merged_wiki_pages,
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
