from __future__ import annotations

import numpy as np
import pytest

from ctx.core.graph import vector_index
from ctx.core.graph.vector_index import (
    MergedVectorIndex,
    VectorIndexUnavailable,
    build_vector_index,
    load_vector_index,
    upsert_numpy_flat_index_entry,
)


def _vectors() -> np.ndarray:
    return np.asarray(
        [
            [1.0, 0.0],
            [0.8, 0.2],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )


def test_numpy_flat_query_matches_cosine_topk() -> None:
    index = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["a", "b", "c"],
        content_hashes=["ha", "hb", "hc"],
        vectors=_vectors(),
    )

    rows = index.query(np.asarray([[1.0, 0.0]], dtype=np.float32), top_k=2, min_score=0.0)

    assert [(n.node_id, round(n.score, 4)) for n in rows[0]] == [
        ("a", 1.0),
        ("b", pytest.approx(0.9701, abs=1e-4)),
    ]

    top_one = index.query(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        top_k=1,
        min_score=0.0,
    )
    assert [n.node_id for n in top_one[0]] == ["a"]


def test_numpy_flat_query_excludes_node_ids_and_applies_min_score() -> None:
    index = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["a", "b", "c"],
        content_hashes=["ha", "hb", "hc"],
        vectors=_vectors(),
    )

    rows = index.query(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        top_k=3,
        min_score=0.5,
        exclude_node_ids={"a"},
    )

    assert [n.node_id for n in rows[0]] == ["b"]


def test_numpy_flat_query_rejects_wrong_dimension() -> None:
    index = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["a", "b"],
        content_hashes=["ha", "hb"],
        vectors=_vectors()[:2],
    )

    with pytest.raises(ValueError, match="query vector dim 3 does not match index dim 2"):
        index.query(
            np.asarray([[1.0, 0.0, 0.0]], dtype=np.float32),
            top_k=1,
            min_score=0.0,
        )


def test_merged_vector_index_queries_base_and_delta_topk() -> None:
    base = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["base-a", "base-b"],
        content_hashes=["ha", "hb"],
        vectors=np.asarray([[1.0, 0.0], [0.6, 0.4]], dtype=np.float32),
    )
    delta = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["delta-a", "delta-b"],
        content_hashes=["hda", "hdb"],
        vectors=np.asarray([[0.9, 0.1], [0.0, 1.0]], dtype=np.float32),
    )

    rows = MergedVectorIndex([base, delta]).query(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        top_k=3,
        min_score=0.0,
    )

    assert [neighbor.node_id for neighbor in rows[0]] == [
        "base-a",
        "delta-a",
        "base-b",
    ]


def test_merged_vector_index_deduplicates_by_best_score_and_excludes() -> None:
    base = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["shared", "base-only"],
        content_hashes=["ha", "hb"],
        vectors=np.asarray([[0.7, 0.3], [0.0, 1.0]], dtype=np.float32),
    )
    delta = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["shared", "delta-only"],
        content_hashes=["hda", "hdb"],
        vectors=np.asarray([[1.0, 0.0], [0.8, 0.2]], dtype=np.float32),
    )

    rows = MergedVectorIndex([base, delta]).query(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        top_k=3,
        min_score=0.0,
        exclude_node_ids={"delta-only"},
    )

    assert [(neighbor.node_id, round(neighbor.score, 3)) for neighbor in rows[0]] == [
        ("shared", 1.0),
        ("base-only", 0.0),
    ]


def test_merged_vector_index_rejects_incompatible_indexes() -> None:
    base = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["a"],
        content_hashes=["ha"],
        vectors=np.asarray([[1.0, 0.0]], dtype=np.float32),
    )
    other_model = build_vector_index(
        kind="numpy-flat",
        model_id="model-b",
        node_ids=["b"],
        content_hashes=["hb"],
        vectors=np.asarray([[1.0, 0.0]], dtype=np.float32),
    )

    with pytest.raises(ValueError, match="incompatible"):
        MergedVectorIndex([base, other_model])


def test_numpy_flat_round_trip_validates_model_and_fingerprint(tmp_path) -> None:
    index = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["a", "b"],
        content_hashes=["ha", "hb"],
        vectors=_vectors()[:2],
    )
    index.save(tmp_path)

    loaded = load_vector_index(
        tmp_path,
        expected_model_id="model-a",
        expected_content_fingerprint=index.meta.content_fingerprint,
    )
    assert loaded is not None
    assert loaded.meta.node_count == 2
    assert (tmp_path / "vector-index.meta.json.lock").exists()

    assert (
        load_vector_index(
            tmp_path,
            expected_model_id="model-b",
            expected_content_fingerprint=index.meta.content_fingerprint,
        )
        is None
    )

    np.savez_compressed(
        tmp_path / "vector-index.numpy.npz",
        node_ids=np.asarray(["a", "z"], dtype="U"),
        content_hashes=np.asarray(["ha", "hb"], dtype="U"),
        vecs=_vectors()[:2],
    )
    assert (
        load_vector_index(
            tmp_path,
            expected_model_id="model-a",
            expected_content_fingerprint=index.meta.content_fingerprint,
        )
        is None
    )


def test_load_vector_index_rejects_corrupt_vector_shape(tmp_path) -> None:
    index = build_vector_index(
        kind="numpy-flat",
        model_id="model-a",
        node_ids=["a", "b"],
        content_hashes=["ha", "hb"],
        vectors=_vectors()[:2],
    )
    index.save(tmp_path)
    np.savez_compressed(
        tmp_path / "vector-index.numpy.npz",
        node_ids=np.asarray(["a", "b"], dtype="U"),
        content_hashes=np.asarray(["ha", "hb"], dtype="U"),
        vecs=np.asarray([1.0, 0.0], dtype=np.float32),
    )

    assert (
        load_vector_index(
            tmp_path,
            expected_model_id="model-a",
            expected_content_fingerprint=index.meta.content_fingerprint,
        )
        is None
    )


def test_build_vector_index_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValueError, match="duplicate node_id"):
        build_vector_index(
            kind="numpy-flat",
            model_id="model-a",
            node_ids=["a", "a"],
            content_hashes=["ha", "hb"],
            vectors=_vectors()[:2],
        )


def test_upsert_numpy_flat_index_entry_creates_appends_and_replaces(tmp_path) -> None:
    first = upsert_numpy_flat_index_entry(
        tmp_path,
        model_id="model-a",
        node_id="a",
        content_hash="ha",
        vector=np.asarray([1.0, 0.0], dtype=np.float32),
    )
    assert first.node_ids == ["a"]
    assert first.content_hashes == ["ha"]

    second = upsert_numpy_flat_index_entry(
        tmp_path,
        model_id="model-a",
        node_id="b",
        content_hash="hb",
        vector=np.asarray([[0.0, 1.0]], dtype=np.float32),
    )
    assert second.node_ids == ["a", "b"]
    assert second.content_hashes == ["ha", "hb"]

    third = upsert_numpy_flat_index_entry(
        tmp_path,
        model_id="model-a",
        node_id="a",
        content_hash="ha2",
        vector=np.asarray([0.6, 0.8], dtype=np.float32),
    )

    loaded = load_vector_index(
        tmp_path,
        expected_model_id="model-a",
        expected_content_fingerprint=third.meta.content_fingerprint,
    )
    assert loaded is not None
    assert loaded.meta.index_kind == "numpy-flat"
    assert loaded.node_ids == ["a", "b"]
    assert loaded.content_hashes == ["ha2", "hb"]
    rows = loaded.query(
        np.asarray([[0.6, 0.8]], dtype=np.float32),
        top_k=1,
        min_score=0.0,
    )
    assert [neighbor.node_id for neighbor in rows[0]] == ["a"]


def test_upsert_numpy_flat_index_entry_rejects_incompatible_existing_index(
    tmp_path,
) -> None:
    upsert_numpy_flat_index_entry(
        tmp_path,
        model_id="model-a",
        node_id="a",
        content_hash="ha",
        vector=np.asarray([1.0, 0.0], dtype=np.float32),
    )

    with pytest.raises(ValueError, match="incompatible"):
        upsert_numpy_flat_index_entry(
            tmp_path,
            model_id="model-b",
            node_id="b",
            content_hash="hb",
            vector=np.asarray([0.0, 1.0], dtype=np.float32),
        )


def test_auto_falls_back_to_numpy_when_hnswlib_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(vector_index, "_import_hnswlib", lambda: None)

    index = build_vector_index(
        kind="auto",
        model_id="model-a",
        node_ids=["a", "b"],
        content_hashes=["ha", "hb"],
        vectors=_vectors()[:2],
        ann_enabled_above_nodes=1,
    )

    assert index.meta.index_kind == "numpy-flat"


def test_forced_hnswlib_reports_missing_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr(vector_index, "_import_hnswlib", lambda: None)

    with pytest.raises(VectorIndexUnavailable, match="hnswlib"):
        build_vector_index(
            kind="hnswlib",
            model_id="model-a",
            node_ids=["a", "b"],
            content_hashes=["ha", "hb"],
            vectors=_vectors()[:2],
        )
