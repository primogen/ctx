"""Tests for the persistent wiki/graph ingest queue."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ctx.core.wiki import wiki_queue


def test_init_queue_enables_wal_and_creates_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    raw_connect = sqlite3.connect
    closed = 0

    class TrackingConnection:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def __getattr__(self, name: str) -> object:
            return getattr(self._conn, name)

        @property
        def row_factory(self) -> Any:
            return self._conn.row_factory

        @row_factory.setter
        def row_factory(self, value: Any) -> None:
            self._conn.row_factory = value

        def close(self) -> None:
            nonlocal closed
            closed += 1
            self._conn.close()

    def tracking_connect(*args: Any, **kwargs: Any) -> TrackingConnection:
        return TrackingConnection(raw_connect(*args, **kwargs))

    monkeypatch.setattr(wiki_queue.sqlite3, "connect", tracking_connect)

    wiki_queue.init_queue(db_path)

    assert closed == 1
    with raw_connect(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        table_count = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='wiki_queue_jobs'",
        ).fetchone()[0]
    assert table_count == 1


def test_enqueue_is_idempotent_by_key(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"

    first = wiki_queue.enqueue(
        db_path,
        kind="entity-upsert",
        payload={"slug": "alpha"},
        idempotency_key="entity-upsert:skill:alpha",
        now=10.0,
    )
    second = wiki_queue.enqueue(
        db_path,
        kind="entity-upsert",
        payload={"slug": "beta"},
        idempotency_key="entity-upsert:skill:alpha",
        now=11.0,
    )

    assert second.id == first.id
    assert second.payload == {"slug": "alpha"}
    assert wiki_queue.list_jobs(db_path) == [first]


def test_enqueue_maintenance_job_is_idempotent_by_payload(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db_path = wiki_queue.queue_db_path(wiki)

    first = wiki_queue.enqueue_maintenance_job(
        wiki,
        kind=wiki_queue.GRAPH_EXPORT_JOB,
        payload={"graph_only": True, "incremental": True},
        source="test",
        now=10.0,
    )
    second = wiki_queue.enqueue_maintenance_job(
        wiki,
        kind=wiki_queue.GRAPH_EXPORT_JOB,
        payload={"incremental": True, "graph_only": True},
        source="test",
        now=11.0,
    )

    assert second.id == first.id
    assert second.kind == wiki_queue.GRAPH_EXPORT_JOB
    assert second.payload["source"] == "test"
    assert second.payload["graph_only"] is True
    assert wiki_queue.list_jobs(db_path) == [first]

    leased = wiki_queue.lease_next(db_path, worker_id="worker-a", now=20.0)
    assert leased is not None
    wiki_queue.mark_succeeded(db_path, leased.id, worker_id="worker-a", now=21.0)

    third = wiki_queue.enqueue_maintenance_job(
        wiki,
        kind=wiki_queue.GRAPH_EXPORT_JOB,
        payload={"incremental": True, "graph_only": True},
        source="test",
        now=30.0,
    )
    fourth = wiki_queue.enqueue_maintenance_job(
        wiki,
        kind=wiki_queue.GRAPH_EXPORT_JOB,
        payload={"graph_only": True, "incremental": True},
        source="test",
        now=31.0,
    )

    assert third.id != first.id
    assert third.status == wiki_queue.STATUS_PENDING
    assert fourth.id == third.id
    assert [job.id for job in wiki_queue.list_jobs(db_path)] == [first.id, third.id]


def test_enqueue_maintenance_job_rejects_unknown_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported maintenance job kind"):
        wiki_queue.enqueue_maintenance_job(
            tmp_path / "wiki",
            kind="unknown-maintenance",
            payload={},
            source="test",
        )


def test_count_jobs_by_status_and_list_recent_jobs_are_bounded(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    jobs = [
        wiki_queue.enqueue(
            db_path,
            kind="graph-export",
            payload={"n": index},
            now=float(index),
        )
        for index in range(25)
    ]

    assert wiki_queue.count_jobs_by_status(db_path) == {wiki_queue.STATUS_PENDING: 25}
    assert [job.id for job in wiki_queue.list_recent_jobs(db_path, limit=5)] == [
        job.id for job in reversed(jobs[-5:])
    ]
    assert wiki_queue.list_recent_jobs(db_path, limit=0) == []


def test_lease_next_claims_oldest_available_job(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    first = wiki_queue.enqueue(db_path, kind="graph-export", payload={"n": 1}, now=10.0)
    second = wiki_queue.enqueue(db_path, kind="graph-export", payload={"n": 2}, now=11.0)

    leased = wiki_queue.lease_next(
        db_path,
        worker_id="worker-a",
        lease_seconds=30.0,
        now=20.0,
    )

    assert leased is not None
    assert leased.id == first.id
    assert leased.status == "running"
    assert leased.attempts == 1
    assert leased.worker_id == "worker-a"
    assert leased.leased_until == 50.0
    assert wiki_queue.get_job(db_path, second.id).status == "pending"


def test_lease_next_can_filter_job_kinds(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    graph = wiki_queue.enqueue(db_path, kind="graph-export", payload={}, now=10.0)
    entity = wiki_queue.enqueue(db_path, kind="entity-upsert", payload={}, now=11.0)

    leased = wiki_queue.lease_next(
        db_path,
        worker_id="worker-a",
        kinds=("entity-upsert",),
        now=20.0,
    )

    assert leased is not None
    assert leased.id == entity.id
    assert wiki_queue.get_job(db_path, graph.id).status == "pending"


def test_mark_failed_retries_until_max_attempts_then_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    job = wiki_queue.enqueue(
        db_path,
        kind="graph-link-refresh",
        payload={"slug": "alpha"},
        max_attempts=2,
        now=10.0,
    )

    leased = wiki_queue.lease_next(db_path, worker_id="worker-a", now=20.0)
    assert leased is not None
    retry = wiki_queue.mark_failed(
        db_path,
        leased.id,
        error="temporary failure",
        retry=True,
        delay_seconds=15.0,
        now=21.0,
    )
    assert retry.status == "pending"
    assert retry.available_at == 36.0
    assert retry.last_error == "temporary failure"
    assert wiki_queue.lease_next(db_path, worker_id="worker-a", now=30.0) is None

    leased_again = wiki_queue.lease_next(db_path, worker_id="worker-a", now=40.0)
    assert leased_again is not None
    assert leased_again.id == job.id
    terminal = wiki_queue.mark_failed(
        db_path,
        leased_again.id,
        error="permanent failure",
        retry=True,
        now=41.0,
    )
    assert terminal.status == "failed"
    assert terminal.last_error == "permanent failure"
    assert wiki_queue.lease_next(db_path, worker_id="worker-a", now=50.0) is None


def test_expired_running_job_is_recovered_for_retry(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    job = wiki_queue.enqueue(db_path, kind="tar-refresh", payload={}, now=10.0)

    first = wiki_queue.lease_next(
        db_path,
        worker_id="worker-a",
        lease_seconds=5.0,
        now=20.0,
    )
    assert first is not None
    assert first.id == job.id
    assert wiki_queue.lease_next(db_path, worker_id="worker-b", now=24.0) is None

    recovered = wiki_queue.lease_next(db_path, worker_id="worker-b", now=26.0)

    assert recovered is not None
    assert recovered.id == job.id
    assert recovered.worker_id == "worker-b"
    assert recovered.attempts == 2

    with pytest.raises(RuntimeError, match="not leased by worker worker-a"):
        wiki_queue.mark_succeeded(db_path, job.id, worker_id="worker-a", now=27.0)

    current = wiki_queue.get_job(db_path, job.id)
    assert current.status == wiki_queue.STATUS_RUNNING
    assert current.worker_id == "worker-b"

    with pytest.raises(RuntimeError, match="not leased by worker worker-a"):
        wiki_queue.mark_failed(
            db_path,
            job.id,
            worker_id="worker-a",
            error="late failure",
            retry=True,
            now=27.0,
        )

    current = wiki_queue.get_job(db_path, job.id)
    assert current.status == wiki_queue.STATUS_RUNNING
    assert current.worker_id == "worker-b"
    assert current.last_error is None

    recovery_db = tmp_path / "wiki-queue-recovery.sqlite3"
    retryable = wiki_queue.enqueue(
        recovery_db,
        kind="graph-export",
        payload={"n": 1},
        max_attempts=2,
        now=30.0,
    )
    exhausted = wiki_queue.enqueue(
        recovery_db,
        kind="tar-refresh",
        payload={"n": 2},
        max_attempts=1,
        now=31.0,
    )
    first_lease = wiki_queue.lease_next(
        recovery_db,
        worker_id="worker-a",
        lease_seconds=5.0,
        now=40.0,
    )
    assert first_lease is not None
    assert first_lease.id == retryable.id
    second_lease = wiki_queue.lease_next(
        recovery_db,
        worker_id="worker-b",
        lease_seconds=5.0,
        now=41.0,
    )
    assert second_lease is not None
    assert second_lease.id == exhausted.id

    recovered_counts = wiki_queue.recover_expired_leases(recovery_db, now=47.0)

    assert recovered_counts == {"requeued": 1, "failed": 1}
    assert wiki_queue.get_job(recovery_db, retryable.id).status == wiki_queue.STATUS_PENDING
    terminal = wiki_queue.get_job(recovery_db, exhausted.id)
    assert terminal.status == wiki_queue.STATUS_FAILED
    assert terminal.last_error == "lease expired; max attempts exhausted"


def test_mark_succeeded_makes_job_unavailable(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki-queue.sqlite3"
    wiki_queue.enqueue(db_path, kind="graph-export", payload={}, now=10.0)
    leased = wiki_queue.lease_next(db_path, worker_id="worker-a", now=20.0)
    assert leased is not None

    done = wiki_queue.mark_succeeded(db_path, leased.id, now=21.0)

    assert done.status == "succeeded"
    assert done.leased_until is None
    assert done.worker_id is None
    assert wiki_queue.lease_next(db_path, worker_id="worker-a", now=22.0) is None

    first = wiki_queue.enqueue(db_path, kind="graph-export", payload={"n": 1}, now=30.0)
    second = wiki_queue.enqueue(db_path, kind="tar-refresh", payload={"n": 2}, now=31.0)

    cancelled = wiki_queue.cancel_job(
        db_path,
        first.id,
        reason="superseded by newer artifact refresh",
        now=32.0,
    )

    assert cancelled.status == wiki_queue.STATUS_CANCELLED
    assert cancelled.last_error == "superseded by newer artifact refresh"
    assert cancelled.worker_id is None
    assert cancelled.leased_until is None
    assert wiki_queue.cancel_job(db_path, first.id, now=33.0).id == first.id
    leased_second = wiki_queue.lease_next(db_path, worker_id="worker-a", now=40.0)
    assert leased_second is not None
    assert leased_second.id == second.id
    assert wiki_queue.count_jobs_by_status(db_path) == {
        wiki_queue.STATUS_SUCCEEDED: 1,
        wiki_queue.STATUS_CANCELLED: 1,
        wiki_queue.STATUS_RUNNING: 1,
    }

    running_job = wiki_queue.enqueue(db_path, kind="graph-export", payload={}, now=50.0)
    running_lease = wiki_queue.lease_next(db_path, worker_id="worker-b", now=60.0)
    assert running_lease is not None
    assert running_lease.id == running_job.id

    cancelled_running = wiki_queue.cancel_job(
        db_path,
        running_job.id,
        worker_id="worker-b",
        reason="operator cancelled hung graph export",
        now=61.0,
    )

    assert cancelled_running.status == wiki_queue.STATUS_CANCELLED
    with pytest.raises(RuntimeError, match="not leased by worker worker-b"):
        wiki_queue.mark_succeeded(db_path, running_job.id, worker_id="worker-b", now=62.0)


def test_queue_rejects_symlinked_database_path(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(wiki_queue.QueueStorageError, match="queue database is not readable"):
        wiki_queue.count_jobs_by_status(corrupt)

    real = tmp_path / "real.sqlite3"
    link = tmp_path / "queue.sqlite3"
    real.write_text("", encoding="utf-8")
    try:
        link.symlink_to(real)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable in this environment: {exc}")

    with pytest.raises(ValueError, match="symlink"):
        wiki_queue.init_queue(link)
