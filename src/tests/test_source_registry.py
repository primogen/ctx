from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctx.core.source_registry import (
    BUILTIN_EXTERNAL_SOURCES,
    ExternalSourceRecord,
    LicenseGateError,
    load_source_registry,
    validate_import_plan,
)


def test_license_gate_allows_full_body_for_permissive_license() -> None:
    record = ExternalSourceRecord(
        name="optillm",
        url="https://github.com/algorithmicsuperintelligence/optillm",
        revision="df018d6",
        license="Apache-2.0",
        source_kind="harness",
        import_mode="full",
        permission_status="license",
    )

    assert validate_import_plan(record) is record


def test_license_gate_blocks_noncommercial_full_body_without_permission() -> None:
    record = ExternalSourceRecord(
        name="academic-research-skills",
        url="https://github.com/Imbad0202/academic-research-skills",
        revision="153203d",
        license="CC BY-NC 4.0",
        source_kind="skill-suite",
        import_mode="full",
        permission_status="license",
    )

    with pytest.raises(LicenseGateError, match="non-commercial"):
        validate_import_plan(record)


def test_license_gate_allows_metadata_only_for_restricted_license() -> None:
    record = ExternalSourceRecord(
        name="academic-research-skills",
        url="https://github.com/Imbad0202/academic-research-skills",
        revision="153203d",
        license="CC BY-NC 4.0",
        source_kind="skill-suite",
        import_mode="metadata-only",
        permission_status="license",
    )

    assert validate_import_plan(record) is record


def test_license_gate_allows_full_body_when_permission_is_recorded() -> None:
    record = ExternalSourceRecord(
        name="academic-research-skills",
        url="https://github.com/Imbad0202/academic-research-skills",
        revision="153203d",
        license="CC BY-NC 4.0",
        source_kind="skill-suite",
        import_mode="full",
        permission_status="explicit-permission",
        permission_reference="author email 2026-05-13",
    )

    assert validate_import_plan(record) is record


def test_builtin_registry_records_requested_sources() -> None:
    names = {source.name for source in BUILTIN_EXTERNAL_SOURCES}

    assert {
        "mattpocock-skills",
        "academic-research-skills",
        "agents-md",
        "lat-md",
        "optillm",
        "julius-caveman",
    } <= names


def test_builtin_registry_records_full_git_revisions() -> None:
    for source in BUILTIN_EXTERNAL_SOURCES:
        assert len(source.revision) == 40


def test_load_source_registry_validates_json_records(tmp_path: Path) -> None:
    registry_path = tmp_path / "sources.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "name": "lat-md",
                    "url": "https://github.com/1st1/lat.md",
                    "revision": "bf8d95c",
                    "license": "MIT",
                    "source_kind": "knowledge-protocol",
                    "import_mode": "metadata-only",
                    "permission_status": "license",
                }
            ],
        ),
        encoding="utf-8",
    )

    records = load_source_registry(registry_path)

    assert [record.name for record in records] == ["lat-md"]
