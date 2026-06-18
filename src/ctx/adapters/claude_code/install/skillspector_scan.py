"""Compatibility wrapper for the ctx-wide SkillSpector service."""

from __future__ import annotations

from ctx.core.quality.skillspector_service import SkillSpectorResult
from ctx.core.quality.skillspector_service import render_scan_report
from ctx.core.quality.skillspector_service import run_skillspector_scan
from ctx.core.quality.skillspector_service import skill_scan_target

__all__ = [
    "SkillSpectorResult",
    "render_scan_report",
    "run_skillspector_scan",
    "skill_scan_target",
]
