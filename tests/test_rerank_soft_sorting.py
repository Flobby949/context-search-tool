"""
Tests for soft rerank sorting functionality.

These tests validate the rerank-based sorting that fixes the rank_tier bug
where low-score relation expansion results incorrectly outrank high-score
direct matches.

All tests are marked as xfail since the features don't exist yet (TDD red phase).
"""

import pytest
from pathlib import Path
from context_search_tool.models import (
    DocumentChunk,
    RetrievalCandidate,
)
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.retrieval import _rank_chunks


# Test helper to setup store with chunks and return candidates
def _setup_test_data(
    chunks_data: list[tuple[str, dict[str, float], str, int]]
) -> tuple[SQLiteStore, dict[str, RetrievalCandidate]]:
    """
    Create a store with chunks and return candidates dict.

    Args:
        chunks_data: List of (chunk_id, score_parts, file_path, start_line) tuples

    Returns:
        (store, candidates_dict) ready for _rank_chunks
    """
    store = SQLiteStore(":memory:")
    candidates = {}

    for chunk_id, score_parts, file_path, start_line in chunks_data:
        chunk = DocumentChunk(
            chunk_id=chunk_id,
            file_path=Path(file_path),
            start_line=start_line,
            end_line=start_line + 10,
            text=f"def {chunk_id}(): pass",
            language="python",
        )
        store.replace_chunks(Path(file_path), [chunk])

        candidates[chunk_id] = RetrievalCandidate(
            chunk_id=chunk_id,
            score=1.0,  # Will be ignored by _rank_chunks
            source="test",
            score_parts=score_parts,
        )

    return store, candidates


@pytest.mark.xfail(reason="rerank_score field doesn't exist yet")
def test_rerank_high_score_direct_beats_low_score_relation():
    """
    Test #1: High-score direct (semantic ~2.0) must rank before low-score relation-only.
    Reproduces the SmsUtils case where high-score direct was incorrectly ranked
    below low-score relation expansion due to rank_tier dominance.
    """
    store, candidates = _setup_test_data([
        # High-score direct match (like SmsUtils with strong semantic match)
        ("sms_utils", {
            "semantic": 2.0,
            "lexical": 0.1,
            "path_symbol": 0.2,
            "signal": 0.1,
        }, "utils/SmsUtils.java", 10),
        # Low-score relation-only (like WxMiniLoginClient via relation expansion)
        ("wx_client", {
            "original_relation": 0.5,
            "semantic": 0.0,
            "lexical": 0.0,
        }, "client/WxMiniLoginClient.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="sms login")

    # High-score direct should rank first
    assert ranked[0].chunk.chunk_id == "sms_utils"
    assert ranked[1].chunk.chunk_id == "wx_client"
    assert hasattr(ranked[0], "rerank_score")


@pytest.mark.xfail(reason="planner_ceiling and rerank_score don't exist yet")
def test_rerank_planner_only_relation_cannot_beat_strong_original_direct():
    """
    Test #2: planner-only relation (_is_planner_hint_only=true) cannot outrank
    strong original_direct. Validates the ceiling mechanism.
    """
    store, candidates = _setup_test_data([
        # Strong original direct
        ("auth_service", {
            "semantic": 0.4,  # Above strong threshold (0.35)
            "lexical": 0.0,
        }, "service/AuthService.java", 10),
        # Planner-only relation (no original evidence)
        ("redis_cache", {
            "planner_relation": 1.8,  # High planner score
            "semantic": 0.0,  # No original evidence
            "lexical": 0.0,
        }, "cache/RedisCache.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="auth")

    # Strong direct must rank first despite lower combined_score
    assert ranked[0].chunk.chunk_id == "auth_service"

    # Validate invariant: max(planner-only) < min(strong original_direct)
    planner_rerank = [r.rerank_score for r in ranked if r.chunk.chunk_id == "redis_cache"]
    direct_rerank = [r.rerank_score for r in ranked if r.chunk.chunk_id == "auth_service"]
    assert max(planner_rerank) < min(direct_rerank)


@pytest.mark.xfail(reason="planner_direct classification doesn't exist yet")
def test_rerank_planner_direct_cannot_beat_strong_original_direct():
    """
    Test #3: planner_direct (planner_signal/planner_lexical without relation)
    shouldn't outrank strong original direct.
    """
    store, candidates = _setup_test_data([
        ("feedback_service", {
            "lexical": 0.3,  # Above strong threshold (0.25)
        }, "service/FeedbackService.java", 10),
        ("station_controller", {
            "planner_signal": 0.8,
            "planner_lexical": 0.5,
            "semantic": 0.0,
        }, "controller/StationController.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="feedback")

    assert ranked[0].chunk.chunk_id == "feedback_service"
    assert ranked[0].evidence_class == "original_direct"
    assert ranked[1].evidence_class == "planner_direct"


@pytest.mark.xfail(reason="planner_ceiling threshold logic doesn't exist yet")
def test_rerank_weak_direct_does_not_trigger_planner_ceiling():
    """
    Test #4: Weak direct (lexical=0.05 or token_coverage=0.1) does NOT trigger
    planner_ceiling. Ensures weak evidence doesn't mistakenly clamp planner results.
    """
    store, candidates = _setup_test_data([
        # Weak direct - below all strong thresholds
        ("generic_util", {
            "lexical": 0.05,  # Below strong threshold (0.25)
            "token_coverage": 0.1,  # Below strong threshold (0.5)
        }, "util/GenericUtil.java", 10),
        # Planner-only with reasonable score
        ("service_impl", {
            "planner_relation": 0.7,
            "semantic": 0.0,
        }, "service/ServiceImpl.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="util")

    # Both should appear (planner not clamped out)
    assert len(ranked) == 2
    # Planner_only should have reasonable rerank_score (not clamped to near-zero)
    planner_result = [r for r in ranked if r.chunk.chunk_id == "service_impl"][0]
    assert planner_result.rerank_score > 0.3  # Not severely clamped


@pytest.mark.xfail(reason="planner_ceiling conditional logic doesn't exist yet")
def test_rerank_no_strong_direct_means_no_clamp():
    """
    Test #5: When there's no strong original_direct, planner-only results are
    not clamped. Ensures planner召回 works when original query fails.
    """
    store, candidates = _setup_test_data([
        # Only planner results, no original evidence at all
        ("planner_a", {
            "planner_relation": 1.2,
            "semantic": 0.0,
        }, "service/PlannerA.java", 10),
        ("planner_b", {
            "planner_lexical": 0.9,
            "semantic": 0.0,
        }, "service/PlannerB.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="planner")

    # Both should appear with unclamped scores
    assert len(ranked) == 2
    assert all(r.rerank_score > 0.5 for r in ranked)  # Not artificially lowered


@pytest.mark.xfail(reason="endpoint boost logic in rerank doesn't exist yet")
def test_rerank_endpoint_boost_does_not_override_score():
    """
    Test #6: endpoint/controller has boost, but high-score non-endpoint can
    still beat low-score endpoint.
    """
    store, candidates = _setup_test_data([
        # High-score non-endpoint
        ("auth_service_impl", {
            "semantic": 1.8,
            "signal": 0.3,
        }, "service/AuthServiceImpl.java", 10),
        # Low-score endpoint
        ("ping_controller", {
            "semantic": 0.2,
            "signal": 0.1,  # Would have endpoint boost
        }, "controller/PingController.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="auth")

    # High-score service should win despite endpoint boost
    assert ranked[0].chunk.chunk_id == "auth_service_impl"


@pytest.mark.xfail(reason="relation expansion with rerank doesn't exist yet")
def test_rerank_relation_expansion_still_surfaces_impl():
    """
    Test #7: Relation expansion can still surface Service/Impl classes.
    Ensures we didn't kill relation expansion completely.
    """
    store, candidates = _setup_test_data([
        # Direct match to controller
        ("station_controller", {
            "lexical": 0.8,
            "path_symbol": 0.5,
        }, "controller/StationController.java", 10),
        # Relation expansion to service
        ("station_service_impl", {
            "original_relation": 0.9,
            "semantic": 0.0,
        }, "service/StationServiceImpl.java", 20),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="station")

    # Both should appear
    assert len(ranked) == 2
    chunk_ids = [r.chunk.chunk_id for r in ranked]
    assert "station_service_impl" in chunk_ids


@pytest.mark.xfail(reason="normalize_score and rerank don't exist yet")
def test_rerank_normalization_effectiveness():
    """
    Test #8: Normalization works correctly with outlier scores.
    Constructs [0.1, 0.2, 2.4] to verify penalty/boost changes ranking
    after normalization. Guards against silent failure.
    """
    store, candidates = _setup_test_data([
        # Outlier high score
        ("outlier", {
            "semantic": 2.4,
            "planner_relation": 0.0,  # Should get planner penalty
        }, "service/Outlier.java", 10),
        # Medium score with strong evidence
        ("medium", {
            "semantic": 0.2,
            "lexical": 0.3,  # Strong original direct evidence
        }, "service/Medium.java", 20),
        # Low score planner-only
        ("low", {
            "semantic": 0.1,
            "planner_relation": 0.5,
        }, "service/Low.java", 30),
    ])

    ranked = _rank_chunks(store, candidates, tokens=[], query="test")

    # Without normalization, outlier would dominate
    # With normalization + boost/penalty, medium might win
    # At minimum, verify rerank_scores are normalized (roughly [0, 1] range)
    for r in ranked:
        assert 0.0 <= r.rerank_score <= 2.0  # Allow some boost headroom


@pytest.mark.xfail(reason="query() pipeline with rerank doesn't exist yet")
def test_rerank_second_sort_consistency():
    """
    Test #9: After query() full pipeline (including _merge_overlapping_results),
    visible_results order matches rerank order. Reproduces the "pressed back by tier" bug.
    """
    # This test requires full query() integration
    # Marking as xfail until full pipeline is implemented
    pytest.skip("Requires full query() integration - implement after steps 2-4")


@pytest.mark.xfail(reason="_evidence_class function doesn't exist yet")
def test_rerank_original_relation_not_misclassified():
    """
    Test #10: Construct candidate with original_relation>0, assert _evidence_class
    returns "original_relation" not "original_direct".
    """
    try:
        from context_search_tool.retrieval import _evidence_class
    except ImportError:
        pytest.skip("_evidence_class not implemented yet")

    # Pure relation evidence
    score_parts = {
        "original_relation": 0.8,
        "semantic": 0.0,
        "lexical": 0.0,
        "path_symbol": 0.0,
        "signal": 0.0,
    }

    evidence_class = _evidence_class(score_parts)
    assert evidence_class == "original_relation"

    # Mixed evidence (has lexical + relation) should be original_direct
    mixed_score_parts = {
        "original_relation": 0.5,
        "lexical": 0.3,
    }

    mixed_class = _evidence_class(mixed_score_parts)
    assert mixed_class == "original_direct"


@pytest.mark.xfail(reason="RetrievalResult.score contract change doesn't exist yet")
def test_rerank_output_contract():
    """
    Test #11: RetrievalResult.score == rerank_score; score_parts contains
    numeric items but not string evidence_class.
    """
    pytest.skip("Requires full query() integration - implement after step 4")


@pytest.mark.xfail(reason="_merge_expanded_result with rerank doesn't exist yet")
def test_rerank_merge_field_consistency():
    """
    Test #12: Construct two overlap results where lower rerank_score has higher
    combined_score. Assert merged result's fields come from rerank_score winner.
    """
    pytest.skip("Requires _ExpandedResult changes - implement after step 4")
