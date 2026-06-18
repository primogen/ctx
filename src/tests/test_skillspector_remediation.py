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
    score: int | None = None,
    recommendation: str | None = "SAFE",
    issues: int = 0,
    rules: tuple[str, ...] = (),
) -> SkillSpectorAuditRecord:
    return SkillSpectorAuditRecord(
        schema_version=1,
        slug=slug,
        status=status,
        risk_score=score if score is not None else (100 if severity == "CRITICAL" else 0),
        risk_severity=severity,
        recommendation=recommendation,
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


def test_build_remediation_plan_removes_risky_findings_only() -> None:
    records = {
        "safe": _record("safe", status="passed"),
        "low_finding": _record(
            "low_finding",
            status="findings",
            issues=2,
            rules=("EA2", "E1"),
            score=10,
        ),
        "medium_finding": _record(
            "medium_finding",
            status="findings",
            severity="MEDIUM",
            score=25,
            recommendation="CAUTION",
            issues=1,
            rules=("TM1",),
        ),
        "dangerous_low_finding": _record(
            "dangerous_low_finding",
            status="findings",
            issues=1,
            rules=("SC2",),
            score=5,
        ),
        "blocked": _record("blocked", status="blocked", severity="HIGH", issues=1),
    }

    plan = build_remediation_plan(
        records,
        audit_path=Path("audit.jsonl.gz"),
        generated_at="2026-06-18T00:00:00+00:00",
    )

    assert plan["summary"]["total"] == 5
    assert plan["summary"]["actions"] == {
        "keep": 1,
        "remove": 3,
        "review_remediate": 1,
    }
    assert plan["remove_slugs"] == [
        "blocked",
        "dangerous_low_finding",
        "medium_finding",
    ]
    assert plan["review_slugs"] == ["low_finding"]
    assert plan["summary"]["top_issue_rules"][0] == {"rule": "EA2", "count": 1}


def test_render_markdown_plan_explains_finding_policy() -> None:
    plan = build_remediation_plan(
        {
            "finding": _record("finding", status="findings", issues=1, score=10),
            "blocked": _record("blocked", status="blocked", severity="CRITICAL"),
        },
        generated_at="2026-06-18T00:00:00+00:00",
    )

    text = render_markdown_plan(plan)

    assert "LOW/SAFE heuristic findings remain" in text
    assert "`remove`: **1**" in text
    assert "`review_remediate`: **1**" in text


def test_main_writes_json_plan(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl.gz"
    out = tmp_path / "plan.json"

    _write_audit(
        audit,
        _record("blocked", status="blocked", severity="HIGH", issues=1),
        _record("finding", status="findings", issues=1, rules=("EA2",), score=10),
    )

    assert main(["--audit", str(audit), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["remove_slugs"] == ["blocked"]
    assert payload["review_slugs"] == ["finding"]
