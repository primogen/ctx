from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast


def _load_builder() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "imported-skills"
        / "julius-caveman"
        / "build_manifest.py"
    )
    spec = importlib.util.spec_from_file_location("julius_caveman_build_manifest", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_frontmatter_handles_folded_description() -> None:
    builder = cast(Any, _load_builder())

    parsed = builder.parse_frontmatter(
        "---\n"
        "name: caveman\n"
        "description: >\n"
        "  Ultra-compressed communication mode.\n"
        "  Keeps technical accuracy.\n"
        "---\n"
        "body\n",
    )

    assert parsed["name"] == "caveman"
    assert parsed["description"] == (
        "Ultra-compressed communication mode. Keeps technical accuracy."
    )
