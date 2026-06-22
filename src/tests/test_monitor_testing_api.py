"""Stable testing facade for ctx monitor internals."""

from __future__ import annotations

import importlib


def test_monitor_testing_facade_exposes_public_helper_names() -> None:
    testing = importlib.import_module("ctx.monitor.testing")

    assert callable(testing.read_jsonl)
    assert callable(testing.render_graph)
    assert callable(testing.make_monitor_server)
