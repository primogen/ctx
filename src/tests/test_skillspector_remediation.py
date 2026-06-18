from __future__ import annotations

import gzip
import json
from pathlib import Path

from ctx.core.quality.skillspector_audit import (
    SKILLSPECTOR_REPO_URL,
    SkillSpectorAuditRecord,
)
from ctx.core.quality.skillspector_remediation import (
    build_remediation_plan,
    decide_record,
    main,
    render_markdown_plan,
)


def _record(
    slug: str,
    *,
    status: str,
    severity: str | None = "LOW",
    issues: int = 0,
    rules: tuple[str, ...] = (),
) -> SkillSpectorAuditRecord:
    return SkillSpectorAuditRecord(
        schema_version=1,
        slug=slug,
        status=status,
        risk_score=100 if severity == "CRITICAL" else 0,
        risk_severity=severity,
        recommendation="review",
        issues=issues,
        components=1,
        content_sha256="abc",
        scanned_at="2026-06-18T00:00:00+00:00",
        scanner="NVIDIA SkillSpector",
        scanner_repo=SKILLSPECTOR_REPO_URL,
        scanner_version="2.2.3",
        mode="static-no-llm",
        llm_requested=False,
        elapsed_seconds=0.1,
        issue_rules=rules,
    )


def _write_audit(path: Path, *records: SkillSpectorAuditRecord) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record.to_json(), sort_keys=True))
            f.write("\n")


def test_decide_record_removes_blocked_and_no_body() -> None:
    blocked = decide_record(
        _record("danger", status="blocked", severity="CRITICAL", issues=3),
    )
    no_body = decide_record(_record("empty", status="not_scanned_no_body", severity=None))

    assert blocked.action == "remove"
    assert "blocked" in blocked.reason
    assert no_body.action == "remove"
    assert "no converted SKILL.md body" in no_body.reason


def test_build_remediation_plan_keeps_findings_review_only() -> None:
    records = {
        "safe": _record("safe", status="passed"),
        "finding": _record("finding", status="findings", issues=2, rules=("EA2", "E1")),
        "blocked": _record("blocked", status="blocked", severity="HIGH", issues=1),
    }

    plan = build_remediation_plan(
        records,
        audit_path=Path("audit.jsonl.gz"),
        generated_at="2026-06-18T00:00:00+00:00",
    )

    assert plan["summary"]["total"] == 3
    assert plan["summary"]["actions"] == {
        "keep": 1,
        "remove": 1,
        "review_remediate": 1,
    }
    assert plan["remove_slugs"] == ["blocked"]
    assert plan["review_slugs"] == ["finding"]
    assert plan["summary"]["top_issue_rules"] == [
        {"rule": "EA2", "count": 1},
        {"rule": "E1", "count": 1},
    ]


def test_render_markdown_plan_explains_non_destructive_scope() -> None:
    plan = build_remediation_plan(
        {
            "finding": _record("finding", status="findings", issues=1),
            "blocked": _record("blocked", status="blocked", severity="CRITICAL"),
        },
        generated_at="2026-06-18T00:00:00+00:00",
    )

    text = render_markdown_plan(plan)

    assert "Finding records are review/remediate candidates" in text
    assert "`remove`: **1**" in text
    assert "`review_remediate`: **1**" in text


def test_main_writes_json_plan(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl.gz"
    out = tmp_path / "plan.json"

    _write_audit(
        audit,
        _record("blocked", status="blocked", severity="HIGH", issues=1),
        _record("finding", status="findings", issues=1, rules=("EA2",)),
    )

    assert main(["--audit", str(audit), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["remove_slugs"] == ["blocked"]
    assert payload["review_slugs"] == ["finding"]
