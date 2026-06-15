from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from scripts import dashboard_smoke as smoke


class FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _urlopen_for(bodies: dict[str, str]):
    def fake_urlopen(url: str, timeout: float) -> FakeResponse:
        path = url.replace("http://127.0.0.1:8765", "")
        return FakeResponse(200, bodies[path])

    return fake_urlopen


def test_run_smoke_checks_dashboard_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies = {spec.path: spec.marker for spec in smoke.DEFAULT_CHECKS}
    seen: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> FakeResponse:
        path = url.replace("http://127.0.0.1:8765", "")
        seen.append(path)
        return FakeResponse(200, bodies[path])

    times: Iterator[float] = iter(range(0, len(smoke.DEFAULT_CHECKS) * 2))
    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(times))

    results = smoke.run_smoke("http://127.0.0.1:8765", timeout=5)

    assert seen == [spec.path for spec in smoke.DEFAULT_CHECKS]
    assert all(result.ok for result in results)


def test_run_smoke_fails_when_marker_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies = {spec.path: spec.marker for spec in smoke.DEFAULT_CHECKS}
    bodies["/manage"] = "wrong page"
    times: Iterator[float] = iter(range(0, len(smoke.DEFAULT_CHECKS) * 2))
    monkeypatch.setattr(smoke.urllib.request, "urlopen", _urlopen_for(bodies))
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(times))

    results = smoke.run_smoke("http://127.0.0.1:8765", timeout=5)

    failed = [result for result in results if not result.ok]
    assert [result.name for result in failed] == ["manage"]
    assert failed[0].reason == "missing marker 'Manage catalog'"


def test_apply_latency_thresholds_marks_slow_warm_graph() -> None:
    results = [
        smoke.CheckResult(
            name="graph-api-warm",
            path="/api/graph/github.json?type=mcp-server&limit=20",
            status=200,
            elapsed=1.2,
            ok=True,
            reason="ok",
            bytes_read=123,
        ),
    ]

    smoke.apply_latency_thresholds(results, {"graph-api-warm": 0.5})

    assert not results[0].ok
    assert results[0].reason == "slow: 1.20s > 0.50s"


def test_emit_jsonl_outputs_structured_rows() -> None:
    result = smoke.CheckResult(
        name="home",
        path="/",
        status=200,
        elapsed=0.1,
        ok=True,
        reason="ok",
        bytes_read=50,
    )

    rows = smoke.results_to_jsonl([result]).splitlines()

    assert json.loads(rows[0]) == {
        "name": "home",
        "path": "/",
        "status": 200,
        "elapsed": 0.1,
        "ok": True,
        "reason": "ok",
        "bytes": 50,
    }
