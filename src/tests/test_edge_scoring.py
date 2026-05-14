from __future__ import annotations

from ctx.core.graph.edge_scoring import (
    SLUG_STOP,
    adamic_adar_scores,
    canonical_pair,
    pairs_from_index,
    slug_tokens,
    type_affinity_score,
)


def test_slug_tokens_filters_short_and_stop_words() -> None:
    assert slug_tokens("fastapi-pro-skill") == ["fastapi"]
    assert "pro" in SLUG_STOP


def test_pairs_from_index_skips_dense_buckets_and_tracks_shared_keys() -> None:
    counts, shared = pairs_from_index(
        {
            "python": ["skill:b", "skill:a"],
            "too-dense": ["skill:a", "skill:b", "skill:c"],
        },
        dense_threshold=2,
    )

    pair = ("skill:a", "skill:b")
    assert counts[pair] == 1
    assert shared[pair] == ["python"]
    assert ("skill:a", "skill:c") not in counts


def test_adamic_adar_scores_only_scores_candidate_pairs() -> None:
    pair = canonical_pair("skill:a", "skill:b")
    scores = adamic_adar_scores(
        ["skill:a", "skill:b", "skill:c"],
        {pair, canonical_pair("skill:a", "skill:c"), canonical_pair("skill:b", "skill:c")},
    )

    assert 0 < scores[pair] <= 1.0


def test_type_affinity_score_matches_existing_graph_contract() -> None:
    assert type_affinity_score("skill", "agent") == 1.0
    assert type_affinity_score("skill", "mcp-server") == 0.9
    assert type_affinity_score("skill", "skill") == 0.35
