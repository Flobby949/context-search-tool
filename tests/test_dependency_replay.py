from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from context_search_tool.config import QueryPlannerConfig, RetrievalConfig, ToolConfig
from context_search_tool.dependency_replay import (
    DependencyReplayCollector,
    canonical_sha256,
    capture_replay_state,
    replay_dependency_state,
)
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    ExactImportedSymbolProvenance,
    QueryPlan,
    RetrievalCandidate,
    SemanticMatch,
)
from context_search_tool.query_planner import OpenAICompatibleQueryPlanner
from context_search_tool.retrieval_core import (
    candidates,
    context_expansion,
    ranking,
    selection,
    types as core_types,
)


class _SignalLookup:
    graph_fault = None

    def __init__(self, signals: dict[str, CodeSignal]) -> None:
        self.signals = signals

    def signal_for_id(self, signal_id: str) -> CodeSignal | None:
        return self.signals.get(signal_id)


def _replay_inputs(
    *,
    plan: QueryPlan | None = None,
) -> tuple[
    QueryPlan,
    list[core_types._RankedChunk],
    dict[str, RetrievalCandidate],
    _SignalLookup,
]:
    resolved_plan = plan or QueryPlan(
        original_query="trace imports used by source_12",
        rewritten_queries=["trace source_12 dependencies"],
        grep_keywords=["source_12"],
        symbol_hints=["source_12"],
        source_module_hints=["source_12"],
        dependency_intent="follow_imports",
        imported_symbol_hints=["Target12"],
        imported_module_hints=["module_12"],
        intent="data_flow",
        status="ok",
        provider="openai-compatible",
        model="online-model",
        prompt_version="prompt-v1",
        prompt_hash="sha256:prompt",
        latency_ms=12,
        repo_profile_hash="",
        repo_profile_truncated=False,
        discarded_hints=["discarded"],
    )
    ranked: list[core_types._RankedChunk] = []
    candidate_map: dict[str, RetrievalCandidate] = {}
    for index in range(13):
        chunk_id = f"chunk-{index:02d}"
        path = f"src/module_{index:02d}.py"
        score = 1.0 - (index * 0.05)
        ranked.append(
            core_types._RankedChunk(
                chunk=DocumentChunk(
                    chunk_id=chunk_id,
                    file_path=Path(path),
                    start_line=1,
                    end_line=3,
                    content=f"secret source body {index}",
                    chunk_type="symbol",
                    metadata={
                        "owner": f"Owner{index}",
                        "cohort": "implementation",
                        "private": "must-not-serialize",
                    },
                ),
                score=score,
                score_parts={"rerank_score": score, "semantic": score / 2},
                reasons=["semantic match"],
                rank_tier=0,
                rerank_score=score,
                evidence_class="strong_original_direct",
                evidence_priority=index,
                semantic_matches=[SemanticMatch("original", score / 2)],
                pre_ceiling_rerank_score=score,
                was_ceiling_clamped=False,
            )
        )
        provenance: tuple[ExactImportedSymbolProvenance, ...] = ()
        if index == 12:
            provenance = (
                ExactImportedSymbolProvenance(
                    relation_id="relation-12",
                    source_signal_id="source-signal-12",
                    source_file_path="src/source_12.py",
                    source_chunk_id="source-chunk-12",
                    target_signal_id="target-signal-12",
                    target_file_path=path,
                    target_chunk_id=chunk_id,
                    relation_kind="imports",
                    resolution="resolved_exact",
                    producer="python_ast",
                    resolution_basis="exact_python_imported_symbol",
                    ordered_edge_position=12,
                ),
            )
        candidate_map[chunk_id] = RetrievalCandidate(
            chunk_id=chunk_id,
            score=score,
            source="semantic" if index < 12 else "relation",
            score_parts={"semantic": score / 2},
            semantic_matches=[SemanticMatch("original", score / 2)],
            exact_imported_symbol_provenance=provenance,
        )
    signals = {
        "source-signal-12": CodeSignal(
            signal_id="source-signal-12",
            chunk_id="source-chunk-12",
            file_path=Path("src/source_12.py"),
            kind="module",
            name="src/source_12.py",
            qualified_name="src/source_12.py",
            start_line=1,
            end_line=2,
            language="python",
            project_unit_key="src",
            producer="core_module",
            recallable=False,
        ),
        "target-signal-12": CodeSignal(
            signal_id="target-signal-12",
            chunk_id="chunk-12",
            file_path=Path("src/module_12.py"),
            kind="type",
            name="Target12",
            start_line=1,
            end_line=3,
            language="python",
            producer="python_ast",
        ),
    }
    return resolved_plan, ranked, candidate_map, _SignalLookup(signals)


def _artifact(*, plan: QueryPlan | None = None) -> dict[str, object]:
    resolved_plan, ranked, candidate_map, signals = _replay_inputs(plan=plan)
    return capture_replay_state(
        query=resolved_plan.original_query,
        plan=resolved_plan,
        query_vector=np.asarray([0.25, -0.5, 0.75], dtype=np.float32),
        ranked_chunks=ranked,
        candidates=candidate_map,
        graph_session=signals,
        final_top_k=12,
    )


def test_capture_round_trip_replays_only_dependency_hint_factor() -> None:
    plan, _, _, _ = _replay_inputs()
    artifact = json.loads(json.dumps(_artifact()))

    assert artifact["plan"] == {**asdict(plan), "error": None}
    assert artifact["query_embedding_sha256"]
    assert [row["position"] for row in artifact["base_roster"]] == list(
        range(1, 14)
    )
    assert artifact["base_roster"][0]["chunk"]["metadata"] == {
        "cohort": "implementation",
        "owner": "Owner0",
    }
    serialized = json.dumps(artifact, sort_keys=True)
    assert "secret source body" not in serialized
    assert "must-not-serialize" not in serialized
    assert str(Path.cwd()) not in serialized

    control = replay_dependency_state(artifact, consume_dependency_hints=False)
    treatment = replay_dependency_state(artifact, consume_dependency_hints=True)

    assert len(control["top12"]) == len(treatment["top12"]) == 12
    assert "src/module_12.py" not in [row["path"] for row in control["top12"]]
    assert "src/module_12.py" in [row["path"] for row in treatment["top12"]]
    promoted = next(
        row for row in treatment["top12"] if row["path"] == "src/module_12.py"
    )
    assert promoted["planner_dependency_hint_promotion"] > 0
    assert "planner dependency target promotion" in promoted["reasons"]
    assert "planner exact dependency target" not in promoted["reasons"]
    assert promoted["closed_exact_witness"]["relation_id"] == "relation-12"


def test_replay_reports_the_existing_dependency_promotion_decision() -> None:
    observations: list[dict[str, object]] = []

    replay_dependency_state(
        _artifact(),
        consume_dependency_hints=True,
        promotion_observer=observations.append,
    )

    assert observations == [
        {
            "status": "promoted",
            "exact_source_hint_promoted": 1,
            "exact_target_hint_promoted": 0,
            "semantic_pair_fallback_promoted": 0,
            "promoted_path_count": 1,
        }
    ]


def test_control_replay_reports_disabled_without_changing_results() -> None:
    artifact = _artifact()
    observations: list[dict[str, object]] = []

    observed = replay_dependency_state(
        artifact,
        consume_dependency_hints=False,
        promotion_observer=observations.append,
    )

    assert observed == replay_dependency_state(
        artifact,
        consume_dependency_hints=False,
    )
    assert observations == [
        {
            "status": "disabled",
            "exact_source_hint_promoted": 0,
            "exact_target_hint_promoted": 0,
            "semantic_pair_fallback_promoted": 0,
            "promoted_path_count": 0,
        }
    ]


def test_fallback_plan_replay_is_unchanged_and_tampering_fails_closed() -> None:
    fallback = QueryPlan(
        original_query="trace imports used by source_12",
        status="fallback",
        provider="openai-compatible",
        model="online-model",
        error="provider response invalid",
    )
    artifact = _artifact(plan=fallback)

    assert replay_dependency_state(
        artifact, consume_dependency_hints=False
    ) == replay_dependency_state(artifact, consume_dependency_hints=True)

    tampered = copy.deepcopy(artifact)
    tampered["base_roster"][0]["ranked"]["rerank_score"] += 0.01
    with pytest.raises(ValueError, match="^replay artifact hash mismatch$"):
        replay_dependency_state(tampered, consume_dependency_hints=False)

    smuggled = copy.deepcopy(artifact)
    smuggled["base_roster"][0]["chunk"]["content"] = "source body"
    body = {key: value for key, value in smuggled.items() if key != "canonical_sha256"}
    smuggled["canonical_sha256"] = canonical_sha256(body)
    with pytest.raises(ValueError, match="^replay artifact chunk invalid$"):
        replay_dependency_state(smuggled, consume_dependency_hints=False)


class _FailingSession:
    trust_env = False

    def post(self, *_args: object, **_kwargs: object) -> object:
        raise requests.ConnectionError("offline")


class _EmbeddingProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        if self.fail:
            raise ValueError("embedding failed")
        return [np.asarray([float(len(text))], dtype=np.float32) for text in texts]


def test_provider_observers_count_actual_boundaries_and_keep_identity_only() -> None:
    config = QueryPlannerConfig(
        enabled=True,
        provider="openai-compatible",
        model="online-model",
        base_url="https://api.example.test/v1",
        send_repo_profile=False,
    )
    endpoints: list[str] = []
    plan = OpenAICompatibleQueryPlanner(
        config,
        session=_FailingSession(),
        request_observer=endpoints.append,
    ).plan("query")

    assert plan.status == "fallback"
    assert endpoints == ["https://api.example.test/v1/chat/completions"]

    observations: list[tuple[list[str], list[object] | None, str]] = []
    vectors = candidates._observed_embed_texts(
        _EmbeddingProvider(),
        ["query"],
        lambda texts, output, outcome: observations.append(
            (texts, output, outcome)
        ),
    )
    assert len(vectors) == 1
    assert [(texts, outcome) for texts, _, outcome in observations] == [
        (["query"], "ok")
    ]

    with pytest.raises(ValueError, match="embedding failed"):
        candidates._observed_embed_texts(
            _EmbeddingProvider(fail=True),
            ["query"],
            lambda texts, output, outcome: observations.append(
                (texts, output, outcome)
            ),
        )
    assert observations[-1] == (["query"], None, "error")


def test_collector_serializes_observed_provider_identity_without_payloads() -> None:
    collector = DependencyReplayCollector(ToolConfig())
    collector._repo_profile_sent = False
    collector.observe_planner_request("https://api.example.test/v1/chat/completions")
    collector.expect_embedding_inputs(["query", "rewrite"])
    collector.observe_embedding(["query", "rewrite"], [[1.0], [2.0]], "ok")

    assert collector.provider_observations == [
        {
            "kind": "planner",
            "ordinal": 1,
            "provider": "ollama",
            "model": "qwen3.5:4b-mlx",
            "scheme": "https",
            "domain": "api.example.test",
            "endpoint_path": "/v1/chat/completions",
            "localhost": False,
            "ollama": True,
            "repo_profile_sent": False,
        },
        {
            "kind": "embedding",
            "ordinal": 1,
            "provider": "hash",
            "model": "hash-v1",
            "scheme": "",
            "domain": "",
            "endpoint_path": "/embeddings",
            "localhost": False,
            "ollama": False,
            "input_count": 2,
            "output_count": 2,
            "outcome": "ok",
            "query_text_only": True,
        },
    ]
    assert '"query"' not in json.dumps(collector.provider_observations)


class _EmptyStore:
    def chunk_for_id(self, chunk_id: str) -> DocumentChunk:
        raise KeyError(chunk_id)


def _downstream_case(
    tmp_path: Path,
    kind: str,
) -> tuple[
    QueryPlan,
    list[core_types._RankedChunk],
    dict[str, RetrievalCandidate],
    _SignalLookup,
    ToolConfig,
    dict[str, float] | None,
]:
    plan = QueryPlan(
        original_query="trace imports used by source",
        source_module_hints=["pkg.source"],
        dependency_intent="follow_imports",
        status="ok",
    )
    paths = ["pkg/winner.py", "pkg/victim.py", "pkg/other.py", "pkg/target.py"]
    ranges = [(1, 2), (1, 2), (1, 2), (1, 2)]
    if kind == "evidence_anchor":
        paths[0] = "README.md"
    elif kind == "overlap_merge":
        paths[0] = paths[1] = "pkg/overlap.py"
        ranges[0] = (1, 2)
        ranges[1] = (2, 3)
    elif kind != "relation_slot":
        raise AssertionError(kind)

    ranked: list[core_types._RankedChunk] = []
    candidate_map: dict[str, RetrievalCandidate] = {}
    for index, (path, (start_line, end_line)) in enumerate(zip(paths, ranges)):
        source_path = tmp_path / path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        chunk_id = f"fixture-{index}"
        score = 1.0 - (index * 0.1)
        score_parts = {"rerank_score": score, "semantic": score}
        if kind == "relation_slot" and index == 3:
            score_parts.update(
                {
                    "resolved_relation": 0.2,
                    "graph_imports_match": 0.2,
                    "lexical": 0.1,
                }
            )
        ranked.append(
            core_types._RankedChunk(
                chunk=DocumentChunk(
                    chunk_id=chunk_id,
                    file_path=Path(path),
                    start_line=start_line,
                    end_line=end_line,
                    content="one\ntwo\nthree\nfour\n",
                    chunk_type="symbol",
                    lexical_tokens=[f"keyword-{index}"],
                ),
                score=score,
                score_parts=score_parts,
                reasons=[f"ranked reason {index}"],
                rank_tier=0,
                rerank_score=score,
                evidence_class="strong_original_direct",
                evidence_priority=index,
                pre_ceiling_rerank_score=score,
            )
        )
        provenance: tuple[ExactImportedSymbolProvenance, ...] = ()
        if index == 3:
            provenance = (
                ExactImportedSymbolProvenance(
                    relation_id="fixture-relation",
                    source_signal_id="fixture-source-signal",
                    source_file_path="pkg/source.py",
                    source_chunk_id="fixture-source-chunk",
                    target_signal_id="fixture-target-signal",
                    target_file_path=path,
                    target_chunk_id=chunk_id,
                    relation_kind="imports",
                    resolution="resolved_exact",
                    producer="python_ast",
                    resolution_basis="exact_python_imported_symbol",
                    ordered_edge_position=1,
                ),
            )
        candidate_map[chunk_id] = RetrievalCandidate(
            chunk_id=chunk_id,
            score=score,
            source="relation" if provenance else "semantic",
            score_parts=score_parts,
            exact_imported_symbol_provenance=provenance,
        )
    signals = _SignalLookup(
        {
            "fixture-source-signal": CodeSignal(
                signal_id="fixture-source-signal",
                chunk_id="fixture-source-chunk",
                file_path=Path("pkg/source.py"),
                kind="module",
                name="pkg.source",
                qualified_name="pkg.source",
                start_line=1,
                end_line=2,
                language="python",
                producer="core_module",
                recallable=False,
            ),
            "fixture-target-signal": CodeSignal(
                signal_id="fixture-target-signal",
                chunk_id="fixture-3",
                file_path=Path("pkg/target.py"),
                kind="type",
                name="Target",
                start_line=1,
                end_line=2,
                language="python",
                producer="python_ast",
            ),
        }
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            final_top_k=2,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    similarities = (
        {
            "fixture-0": 0.9,
            "fixture-1": 0.1,
            "fixture-2": 0.2,
            "fixture-3": 0.8,
        }
        if kind == "relation_slot"
        else None
    )
    if kind == "relation_slot":
        plan = replace(plan, status="fallback", dependency_intent="none")
    return plan, ranked, candidate_map, signals, config, similarities


def _real_downstream_bundle(
    tmp_path: Path,
    plan: QueryPlan,
    ranked: list[core_types._RankedChunk],
    candidate_map: dict[str, RetrievalCandidate],
    signals: _SignalLookup,
    config: ToolConfig,
    similarities: dict[str, float] | None,
    *,
    consume_dependency_hints: bool,
) -> SimpleNamespace:
    arm_ranked = list(ranked)
    if consume_dependency_hints:
        arm_ranked = ranking.apply_planner_dependency_hint_promotions(
            arm_ranked,
            candidate_map,
            plan,
            plan.original_query,
            signals,
            final_top_k=config.retrieval.final_top_k,
        )
    expanded = context_expansion.expand_ranked_chunks(
        tmp_path,
        arm_ranked,
        config,
        context_lines=0,
        full_file=False,
        protect_direct_graph=False,
    )
    resolver = (
        (lambda chunk_ids: {item: similarities[item] for item in chunk_ids})
        if similarities is not None
        else None
    )
    visible, anchors = selection.split_results_and_anchors(
        expanded,
        final_top_k=config.retrieval.final_top_k,
        anchor_top_k=1,
        similarity_resolver=resolver,
    )
    _, results, _ = selection.assemble_query_output(
        _EmptyStore(),
        visible,
        graph_session=None,
    )
    return SimpleNamespace(
        results=results,
        evidence_anchors=anchors,
    )


def test_expansion_capture_trims_trailing_blank_lines_and_range(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.py"
    source_path.write_text("value\n\nother\n\n", encoding="utf-8")
    ranked = core_types._RankedChunk(
        chunk=DocumentChunk(
            chunk_id="source",
            file_path=Path("source.py"),
            start_line=1,
            end_line=1,
            content="value",
            chunk_type="symbol",
        ),
        score=1.0,
        score_parts={"rerank_score": 1.0},
        reasons=[],
        rank_tier=0,
        rerank_score=1.0,
        evidence_class="strong_original_direct",
        evidence_priority=0,
    )
    layouts: list[dict[str, object]] = []

    expanded = context_expansion.expand_ranked_chunks(
        tmp_path,
        [ranked],
        ToolConfig(
            retrieval=RetrievalConfig(
                context_before_lines=0,
                context_after_lines=3,
            )
        ),
        context_lines=None,
        full_file=False,
        layout_observer=lambda raw: layouts.extend(
            context_expansion.capture_expansion_layouts(raw)
        ),
    )

    assert [(item.start_line, item.end_line, item.content) for item in expanded] == [
        (1, 4, "value\n\nother\n")
    ]
    assert [(item["start_line"], item["end_line"]) for item in layouts] == [
        (1, 3)
    ]
    replayed = context_expansion.replay_expansion_layouts(
        [ranked],
        layouts,
        protect_direct_graph=False,
    )
    assert [(item.start_line, item.end_line, item.content) for item in replayed] == [
        (1, 3, "xxxxx\n\nxxxxx")
    ]


@pytest.mark.parametrize(
    "kind",
    ["evidence_anchor", "overlap_merge", "relation_slot"],
)
def test_replay_matches_real_final_bundle_results_for_both_arms(
    tmp_path: Path,
    kind: str,
) -> None:
    plan, ranked, candidate_map, signals, config, similarities = _downstream_case(
        tmp_path,
        kind,
    )
    expansion_layouts: list[dict[str, object]] = []
    control_expanded = context_expansion.expand_ranked_chunks(
        tmp_path,
        ranked,
        config,
        context_lines=0,
        full_file=False,
        protect_direct_graph=False,
        layout_observer=lambda raw: expansion_layouts.extend(
            context_expansion.capture_expansion_layouts(raw)
        ),
    )
    _, additions = selection._summarize_results(
        _EmptyStore(),
        control_expanded,
        graph_session=None,
        test_intent=False,
    )
    artifact = capture_replay_state(
        query=plan.original_query,
        plan=plan,
        query_vector=np.asarray([0.25, 0.75], dtype=np.float32),
        ranked_chunks=ranked,
        candidates=candidate_map,
        graph_session=signals,
        final_top_k=config.retrieval.final_top_k,
        expansion_layouts=expansion_layouts,
        anchor_top_k=1,
        protect_direct_graph=False,
        relation_similarities=similarities,
        result_reason_additions=[
            {"chunk_ids": item.chunk_ids, "reasons": reasons}
            for item, reasons in zip(control_expanded, additions)
        ],
    )

    for consume in (False, True):
        bundle = _real_downstream_bundle(
            tmp_path,
            plan,
            ranked,
            candidate_map,
            signals,
            config,
            similarities,
            consume_dependency_hints=consume,
        )
        replayed = replay_dependency_state(
            artifact,
            consume_dependency_hints=consume,
        )
        assert [
            {
                "path": row["path"],
                "score": row["score"],
                "score_parts": row["score_parts"],
                "reasons": row["reasons"],
            }
            for row in replayed["top12"]
        ] == [
            {
                "path": result.file_path.as_posix(),
                "score": result.score,
                "score_parts": result.score_parts,
                "reasons": result.reasons,
            }
            for result in bundle.results
        ]


def test_planner_error_capture_drops_secrets_urls_and_absolute_paths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_error = (
        "Bearer stage2-secret https://api.example.test/v1/chat/completions "
        "/Users/private/source.py /tmp/provider-response"
    )
    fallback = QueryPlan(
        original_query="trace imports",
        status="fallback",
        provider="openai-compatible",
        model="online-model",
        error=raw_error,
    )
    plan, ranked, candidate_map, signals = _replay_inputs(plan=fallback)

    with caplog.at_level(logging.DEBUG):
        artifact = capture_replay_state(
            query=plan.original_query,
            plan=plan,
            query_vector=np.asarray([1.0], dtype=np.float32),
            ranked_chunks=ranked,
            candidates=candidate_map,
            graph_session=signals,
            final_top_k=12,
        )

    serialized = json.dumps(artifact, sort_keys=True)
    logs = caplog.text
    for forbidden in (
        "stage2-secret",
        "https://api.example.test",
        "/Users/private",
        "/tmp/provider-response",
    ):
        assert forbidden not in serialized
        assert forbidden not in logs
    assert artifact["plan"]["error"] is None
    assert artifact["planner_error_code"] == "unknown"
