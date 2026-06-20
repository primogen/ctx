from __future__ import annotations

from pathlib import Path

from ctx.core.wiki.wiki_packs import load_merged_wiki_pages, write_wiki_base_pack

import versions_catalog as vc


def _dual_skill(tmp_path: Path, name: str = "react") -> dict[str, object]:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    original_md = skill_dir / "SKILL.md.original"
    skill_md.write_text("# transformed\n", encoding="utf-8")
    original_md.write_text("# original\nline two\n", encoding="utf-8")
    return {
        "name": name,
        "transformed_path": str(skill_md),
        "original_path": str(original_md),
        "transformed_lines": 1,
        "original_lines": 2,
    }


def test_versions_catalog_legacy_wiki_writes_files(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "entities" / "skills").mkdir(parents=True)
    (wiki / "index.md").write_text("# Index\n\n## Skills\n", encoding="utf-8")
    (wiki / "log.md").write_text("# Log\n", encoding="utf-8")
    skill = _dual_skill(tmp_path)

    catalog_path = vc.build_versions_catalog(wiki, [skill])
    vc.upsert_entity_page_versions(wiki, skill)
    vc.update_wiki_index(wiki, 1)
    vc.append_log(wiki, 1, catalog_path)

    assert (wiki / "versions-catalog.md").exists()
    assert "preferred_version: transformed" in (
        wiki / "entities" / "skills" / "react.md"
    ).read_text(encoding="utf-8")
    assert "[[versions-catalog]]" in (wiki / "index.md").read_text(encoding="utf-8")
    assert "versions-catalog" in (wiki / "log.md").read_text(encoding="utf-8")


def test_versions_catalog_pack_only_wiki_writes_overlays(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    write_wiki_base_pack(
        pack_dir=wiki / "wiki-packs" / "base-export-1",
        pack_id="base-export-1",
        base_export_id="export-1",
        pages={
            "index.md": "# Index\n\n## Skills\n",
            "log.md": "# Log\n",
        },
    )
    skill = _dual_skill(tmp_path)

    catalog_path = vc.build_versions_catalog(wiki, [skill])
    vc.upsert_entity_page_versions(wiki, skill)
    vc.update_wiki_index(wiki, 1)
    vc.append_log(wiki, 1, catalog_path)

    assert not (wiki / "versions-catalog.md").exists()
    assert not (wiki / "entities" / "skills" / "react.md").exists()
    merged = load_merged_wiki_pages(wiki / "wiki-packs")
    assert "react" in merged["versions-catalog.md"]
    assert "preferred_version: transformed" in merged["entities/skills/react.md"]
    assert "[[versions-catalog]]" in merged["index.md"]
    assert "versions-catalog" in merged["log.md"]
