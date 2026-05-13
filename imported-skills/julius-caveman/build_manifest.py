#!/usr/bin/env python3
"""Generate MANIFEST.json for the imported Julius caveman set."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
MANIFEST_PATH = ROOT / "MANIFEST.json"
UPSTREAM_REVISION_PATH = ROOT / "UPSTREAM_REVISION"
UPSTREAM = "https://github.com/JuliusBrussee/caveman"
LICENSE = "MIT"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    out: dict[str, str] = {}
    pending_key: str | None = None
    for raw in match.group(1).splitlines():
        if pending_key and raw.startswith((" ", "\t")):
            out[pending_key] = (out[pending_key] + " " + raw.strip()).strip()
            continue
        pending_key = None
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        value = value.strip()
        if value in {"", ">", "|"}:
            pending_key = key.strip()
            out[pending_key] = ""
        else:
            out[key.strip()] = value.strip('"').strip("'")
    return out


def support_files(entity_dir: Path, entry_file: Path) -> list[str]:
    out: list[str] = []
    for path in sorted(entity_dir.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_file() and path != entry_file:
            out.append(path.relative_to(entity_dir).as_posix())
    return out


def upstream_revision() -> str:
    revision = UPSTREAM_REVISION_PATH.read_text(encoding="utf-8").strip()
    return revision or "unknown"


def build() -> dict[str, object]:
    skills = []
    for skill_md in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        entity_dir = skill_md.parent
        slug = entity_dir.name
        skills.append({
            "name": frontmatter.get("name", slug),
            "description": frontmatter.get("description", "").strip(),
            "slug": slug,
            "type": "skill",
            "source_path": skill_md.relative_to(ROOT).as_posix(),
            "support_files": support_files(entity_dir, skill_md),
            "lines": len(text.splitlines()),
        })

    agents = []
    for agent_md in sorted((ROOT / "agents").glob("*.md")):
        text = agent_md.read_text(encoding="utf-8")
        slug = agent_md.stem
        agents.append({
            "name": slug,
            "description": "",
            "slug": slug,
            "type": "agent",
            "source_path": agent_md.relative_to(ROOT).as_posix(),
            "support_files": [],
            "lines": len(text.splitlines()),
        })

    entries = skills + agents
    return {
        "upstream": UPSTREAM,
        "upstream_revision": upstream_revision(),
        "license": LICENSE,
        "namespace": "julius-caveman",
        "total": len(entries),
        "skills": len(skills),
        "agents": len(agents),
        "entries": entries,
    }


def main() -> None:
    manifest = build()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Manifest written: {manifest['total']} entries "
        f"({manifest['skills']} skills, {manifest['agents']} agents)",
    )


if __name__ == "__main__":
    main()
