from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlparse

import numpy as np

from context_search_tool.config import ToolConfig
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    ExactImportedSymbolProvenance,
    QueryPlan,
    RetrievalCandidate,
    SemanticMatch,
)
from context_search_tool.retrieval_core import (
    context_expansion,
    ordering,
    ranking,
    selection,
    types as core_types,
)


REPLAY_SCHEMA_VERSION = "p15-v9-dependency-replay-v3"
_CHUNK_METADATA_FIELDS = {"cohort", "owner", "project_name", "project_unit_key"}


@dataclass(frozen=True)
class CapturedDependencyQuery:
    bundle: Any
    replay_state: dict[str, Any]
    provider_observations: tuple[dict[str, Any], ...]


class DependencyReplayCollector:
    def __init__(self, config: ToolConfig) -> None:
        self.config = config
        self.provider_observations: list[dict[str, Any]] = []
        self.replay_state: dict[str, Any] | None = None
        self._repo_profile_sent = False
        self._expected_embedding_texts: tuple[str, ...] = ()
        self._expansion_layouts: list[dict[str, Any]] | None = None

    def plan(self, planner: Any, query: str, repo_profile: Any) -> QueryPlan:
        self._repo_profile_sent = repo_profile is not None
        return planner.plan(query, repo_profile=repo_profile)

    def observe_planner_request(self, endpoint: str) -> None:
        ordinal = 1 + sum(
            item["kind"] == "planner" for item in self.provider_observations
        )
        observation = _provider_identity_from_endpoint(
            kind="planner",
            ordinal=ordinal,
            provider=self.config.query_planner.provider,
            model=self.config.query_planner.model,
            endpoint=endpoint,
        )
        observation["repo_profile_sent"] = self._repo_profile_sent
        self.provider_observations.append(observation)

    def expect_embedding_inputs(self, texts: list[str]) -> None:
        self._expected_embedding_texts = tuple(texts)

    def observe_embedding(
        self,
        texts: list[str],
        vectors: list[Any] | None,
        outcome: str,
    ) -> None:
        ordinal = 1 + sum(
            item["kind"] == "embedding" for item in self.provider_observations
        )
        observation = _provider_identity(
            kind="embedding",
            ordinal=ordinal,
            provider=self.config.embedding.provider,
            model=self.config.embedding.model,
            base_url=self.config.embedding.base_url or "",
            endpoint_suffix="/embeddings",
        )
        observation.update(
            {
                "input_count": len(texts),
                "output_count": len(vectors) if vectors is not None else 0,
                "outcome": outcome,
                "query_text_only": tuple(texts)
                == self._expected_embedding_texts[: len(texts)],
            }
        )
        self.provider_observations.append(observation)

    def capture(
        self,
        *,
        query: str,
        plan: QueryPlan,
        query_vector: Any,
        ranked_chunks: list[core_types._RankedChunk],
        candidates: dict[str, RetrievalCandidate],
        graph_session: Any,
        final_top_k: int,
    ) -> None:
        self.replay_state = capture_replay_state(
            query=query,
            plan=plan,
            query_vector=query_vector,
            ranked_chunks=ranked_chunks,
            candidates=candidates,
            graph_session=graph_session,
            final_top_k=final_top_k,
        )

    def observe_expansion_layouts(
        self,
        expanded: list[core_types._ExpandedResult],
    ) -> None:
        self._expansion_layouts = context_expansion.capture_expansion_layouts(
            expanded
        )

    def finalize_downstream(
        self,
        *,
        expanded: list[core_types._ExpandedResult],
        store: Any,
        graph_session: Any,
        test_intent: bool,
        anchor_top_k: Callable[[int], int],
        protect_direct_graph: bool,
        similarity_resolver: Any,
    ) -> Any:
        if self.replay_state is None or self._expansion_layouts is None:
            raise ValueError("dependency replay downstream state unavailable")
        _, additions = selection._summarize_results(
            store,
            expanded,
            graph_session=graph_session,
            test_intent=test_intent,
        )
        reason_additions = [
            {"chunk_ids": list(item.chunk_ids), "reasons": reasons}
            for item, reasons in zip(expanded, additions)
        ]
        relation_similarities = None
        if similarity_resolver is not None:
            chunk_ids = ordering.dedupe_lowered(
                [chunk_id for item in expanded for chunk_id in item.chunk_ids]
            )
            relation_similarities = similarity_resolver(chunk_ids)
        self.replay_state = attach_downstream_state(
            self.replay_state,
            expansion_layouts=self._expansion_layouts,
            anchor_top_k=anchor_top_k(self.config.retrieval.final_top_k),
            protect_direct_graph=protect_direct_graph,
            relation_similarities=relation_similarities,
            result_reason_additions=reason_additions,
        )
        if relation_similarities is None:
            return None
        return lambda chunk_ids: {
            chunk_id: relation_similarities[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in relation_similarities
        }

    def verify_control_bundle(self, bundle: Any) -> None:
        if self.replay_state is None:
            raise ValueError("dependency replay state unavailable")
        replayed = replay_dependency_state(
            self.replay_state,
            consume_dependency_hints=False,
        )
        replay_projection = [
            (row["path"], row["score"], row["score_parts"], row["reasons"])
            for row in replayed["top12"]
        ]
        bundle_projection = [
            (
                result.file_path.as_posix(),
                result.score,
                result.score_parts,
                result.reasons,
            )
            for result in bundle.results
        ]
        if replay_projection != bundle_projection:
            raise ValueError("dependency replay control projection mismatch")


def capture_query_repository_state(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
) -> CapturedDependencyQuery:
    from context_search_tool.retrieval import _query_repository_v5

    if config.retrieval.consume_dependency_hints:
        raise ValueError("capture requires dependency hints disabled")
    collector = DependencyReplayCollector(config)
    bundle = _query_repository_v5(
        repo,
        query,
        config,
        context_lines=context_lines,
        full_file=full_file,
        dependency_replay_collector=collector,
    )
    if collector.replay_state is None:
        raise ValueError("dependency replay state unavailable")
    return CapturedDependencyQuery(
        bundle=bundle,
        replay_state=collector.replay_state,
        provider_observations=tuple(collector.provider_observations),
    )


def capture_replay_state(
    *,
    query: str,
    plan: QueryPlan,
    query_vector: Any,
    ranked_chunks: list[core_types._RankedChunk],
    candidates: dict[str, RetrievalCandidate],
    graph_session: Any,
    final_top_k: int,
    expansion_layouts: list[dict[str, Any]] | None = None,
    anchor_top_k: int | None = None,
    protect_direct_graph: bool = False,
    relation_similarities: dict[str, float] | None = None,
    result_reason_additions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    roster = []
    signal_ids: set[str] = set()
    for position, ranked in enumerate(ranked_chunks, start=1):
        candidate = candidates.get(ranked.chunk.chunk_id)
        if candidate is None:
            raise ValueError("dependency replay candidate missing")
        provenance = [asdict(atom) for atom in candidate.exact_imported_symbol_provenance]
        for atom in candidate.exact_imported_symbol_provenance:
            signal_ids.add(atom.source_signal_id)
            signal_ids.add(atom.target_signal_id)
        roster.append(
            {
                "position": position,
                "chunk": {
                    "chunk_id": ranked.chunk.chunk_id,
                    "file_path": _repo_path(ranked.chunk.file_path.as_posix()),
                    "start_line": ranked.chunk.start_line,
                    "end_line": ranked.chunk.end_line,
                    "chunk_type": ranked.chunk.chunk_type,
                    "metadata": {
                        key: value
                        for key, value in ranked.chunk.metadata.items()
                        if key in _CHUNK_METADATA_FIELDS
                        and isinstance(value, (str, int, float, bool, type(None)))
                    },
                },
                "ranked": {
                    "score": ranked.score,
                    "score_parts": ranked.score_parts,
                    "rank_tier": ranked.rank_tier,
                    "rerank_score": ranked.rerank_score,
                    "evidence_class": ranked.evidence_class,
                    "evidence_priority": ranked.evidence_priority,
                    "pre_ceiling_rerank_score": ranked.pre_ceiling_rerank_score,
                    "was_ceiling_clamped": ranked.was_ceiling_clamped,
                    "reasons": list(ranked.reasons),
                    "semantic_matches": [
                        asdict(match) for match in ranked.semantic_matches
                    ],
                },
                "candidate": {
                    "score": candidate.score,
                    "source": candidate.source,
                    "score_parts": candidate.score_parts,
                    "semantic_matches": [
                        asdict(match) for match in candidate.semantic_matches
                    ],
                    "exact_imported_symbol_provenance": provenance,
                },
            }
        )
    signals = []
    for signal_id in sorted(signal_ids):
        signal = graph_session.signal_for_id(signal_id) if graph_session else None
        if signal is not None:
            signals.append(_signal_payload(signal))
    plan_payload, planner_error_code = _plan_payload(plan)
    body: dict[str, Any] = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "query": query,
        "plan": plan_payload,
        "planner_error_code": planner_error_code,
        "query_embedding_sha256": _vector_sha256(query_vector),
        "final_top_k": final_top_k,
        "base_roster": roster,
        "signals": signals,
    }
    artifact = {**body, "canonical_sha256": canonical_sha256(body)}
    if expansion_layouts is None:
        return artifact
    return attach_downstream_state(
        artifact,
        expansion_layouts=expansion_layouts,
        anchor_top_k=(
            max(1, min(5, final_top_k // 3))
            if anchor_top_k is None
            else anchor_top_k
        ),
        protect_direct_graph=protect_direct_graph,
        relation_similarities=relation_similarities,
        result_reason_additions=result_reason_additions or [],
    )


def attach_downstream_state(
    artifact: dict[str, Any],
    *,
    expansion_layouts: list[dict[str, Any]],
    anchor_top_k: int,
    protect_direct_graph: bool,
    relation_similarities: dict[str, float] | None,
    result_reason_additions: list[dict[str, Any]],
) -> dict[str, Any]:
    body = validate_replay_state(artifact)
    body["downstream"] = {
        "anchor_top_k": anchor_top_k,
        "protect_direct_graph": protect_direct_graph,
        "expansion_layouts": expansion_layouts,
        "relation_similarities": relation_similarities,
        "result_reason_additions": result_reason_additions,
    }
    return {**body, "canonical_sha256": canonical_sha256(body)}


def replay_dependency_state(
    artifact: dict[str, Any],
    *,
    consume_dependency_hints: bool,
    promotion_observer: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, Any]:
    body = validate_replay_state(artifact)
    plan = QueryPlan(**body["plan"])
    ranked_chunks: list[core_types._RankedChunk] = []
    candidates: dict[str, RetrievalCandidate] = {}
    for row in body["base_roster"]:
        chunk_payload = row["chunk"]
        ranked_payload = row["ranked"]
        candidate_payload = row["candidate"]
        chunk = DocumentChunk(
            chunk_id=chunk_payload["chunk_id"],
            file_path=Path(chunk_payload["file_path"]),
            start_line=chunk_payload["start_line"],
            end_line=chunk_payload["end_line"],
            content="",
            chunk_type=chunk_payload["chunk_type"],
            metadata=chunk_payload["metadata"],
        )
        ranked_chunks.append(
            core_types._RankedChunk(
                chunk=chunk,
                score=ranked_payload["score"],
                score_parts=ranked_payload["score_parts"],
                reasons=ranked_payload["reasons"],
                rank_tier=ranked_payload["rank_tier"],
                rerank_score=ranked_payload["rerank_score"],
                evidence_class=ranked_payload["evidence_class"],
                evidence_priority=ranked_payload["evidence_priority"],
                semantic_matches=[
                    SemanticMatch(**match)
                    for match in ranked_payload["semantic_matches"]
                ],
                pre_ceiling_rerank_score=ranked_payload[
                    "pre_ceiling_rerank_score"
                ],
                was_ceiling_clamped=ranked_payload["was_ceiling_clamped"],
            )
        )
        candidates[chunk.chunk_id] = RetrievalCandidate(
            chunk_id=chunk.chunk_id,
            score=candidate_payload["score"],
            source=candidate_payload["source"],
            score_parts=candidate_payload["score_parts"],
            semantic_matches=[
                SemanticMatch(**match)
                for match in candidate_payload["semantic_matches"]
            ],
            exact_imported_symbol_provenance=tuple(
                ExactImportedSymbolProvenance(**atom)
                for atom in candidate_payload["exact_imported_symbol_provenance"]
            ),
        )
    if consume_dependency_hints:
        signals = {
            signal.signal_id: signal
            for signal in (_signal_from_payload(row) for row in body["signals"])
        }
        signal_lookup = _CapturedSignalLookup(signals)
        ranked_chunks = ranking.apply_planner_dependency_hint_promotions(
            ranked_chunks,
            candidates,
            plan,
            body["query"],
            signal_lookup,
            final_top_k=body["final_top_k"],
            observation_callback=promotion_observer,
        )
    else:
        if promotion_observer is not None:
            promotion_observer(
                {
                    "status": "disabled",
                    "exact_source_hint_promoted": 0,
                    "exact_target_hint_promoted": 0,
                    "semantic_pair_fallback_promoted": 0,
                    "promoted_path_count": 0,
                }
            )
        signal_lookup = _CapturedSignalLookup({})
    downstream = body.get("downstream")
    if downstream is not None:
        expanded = context_expansion.replay_expansion_layouts(
            ranked_chunks,
            downstream["expansion_layouts"],
            protect_direct_graph=downstream["protect_direct_graph"],
        )
        similarities = downstream["relation_similarities"]
        similarity_resolver = (
            None
            if similarities is None
            else lambda chunk_ids: {
                chunk_id: similarities[chunk_id]
                for chunk_id in chunk_ids
                if chunk_id in similarities
            }
        )
        visible, _anchors = selection.split_results_and_anchors(
            expanded,
            final_top_k=body["final_top_k"],
            anchor_top_k=downstream["anchor_top_k"],
            similarity_resolver=similarity_resolver,
        )
        additions = {
            tuple(row["chunk_ids"]): row["reasons"]
            for row in downstream["result_reason_additions"]
        }
        return _final_replay_projection(
            visible,
            ranked_chunks,
            candidates,
            plan,
            signal_lookup,
            additions,
        )
    return _replay_projection(
        ranked_chunks,
        candidates,
        plan,
        signal_lookup,
        body["final_top_k"],
    )


def validate_replay_state(artifact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("replay artifact invalid")
    body = {key: value for key, value in artifact.items() if key != "canonical_sha256"}
    if artifact.get("canonical_sha256") != canonical_sha256(body):
        raise ValueError("replay artifact hash mismatch")
    if body.get("schema_version") != REPLAY_SCHEMA_VERSION:
        raise ValueError("replay artifact schema mismatch")
    _validate_replay_body(body)
    return body


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_replay_body(body: dict[str, Any]) -> None:
    if set(body) != {
        "schema_version",
        "query",
        "plan",
        "planner_error_code",
        "query_embedding_sha256",
        "final_top_k",
        "base_roster",
        "signals",
    } and set(body) != {
        "schema_version",
        "query",
        "plan",
        "planner_error_code",
        "query_embedding_sha256",
        "final_top_k",
        "base_roster",
        "signals",
        "downstream",
    }:
        raise ValueError("replay artifact schema mismatch")
    if not isinstance(body["query"], str):
        raise ValueError("replay artifact query invalid")
    embedding_sha = body["query_embedding_sha256"]
    if embedding_sha is not None and (
        not isinstance(embedding_sha, str)
        or len(embedding_sha) != 64
        or any(character not in "0123456789abcdef" for character in embedding_sha)
    ):
        raise ValueError("replay artifact embedding identity invalid")
    final_top_k = body["final_top_k"]
    if (
        not isinstance(final_top_k, int)
        or isinstance(final_top_k, bool)
        or final_top_k <= 0
    ):
        raise ValueError("replay artifact top-k invalid")
    _validate_plan(body["plan"])
    _validate_roster(body["base_roster"])
    _validate_signals(body["signals"])
    if body["planner_error_code"] not in {
        None,
        "http_error",
        "request_error",
        "timeout",
        "invalid_response",
        "unknown",
    }:
        raise ValueError("replay artifact planner error code invalid")
    if "downstream" in body:
        _validate_downstream(body["downstream"])


def _validate_plan(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        field.name for field in fields(QueryPlan)
    }:
        raise ValueError("replay artifact plan invalid")
    try:
        plan = QueryPlan(**value)
    except TypeError as exc:
        raise ValueError("replay artifact plan invalid") from exc
    if plan.error is not None:
        raise ValueError("replay artifact plan error must be sanitized")
    if not all(
        isinstance(getattr(plan, field), list)
        and all(isinstance(item, str) for item in getattr(plan, field))
        for field in (
            "rewritten_queries",
            "grep_keywords",
            "symbol_hints",
            "source_symbol_hints",
            "source_module_hints",
            "imported_symbol_hints",
            "imported_module_hints",
            "discarded_hints",
        )
    ):
        raise ValueError("replay artifact plan invalid")


def _validate_roster(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("replay artifact roster invalid")
    seen_chunks: set[str] = set()
    for position, row in enumerate(value, start=1):
        if not isinstance(row, dict) or set(row) != {
            "position",
            "chunk",
            "ranked",
            "candidate",
        }:
            raise ValueError("replay artifact roster invalid")
        if row["position"] != position:
            raise ValueError("replay artifact roster order invalid")
        chunk = row["chunk"]
        if not isinstance(chunk, dict) or set(chunk) != {
            "chunk_id",
            "file_path",
            "start_line",
            "end_line",
            "chunk_type",
            "metadata",
        }:
            raise ValueError("replay artifact chunk invalid")
        chunk_id = chunk["chunk_id"]
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in seen_chunks:
            raise ValueError("replay artifact chunk invalid")
        seen_chunks.add(chunk_id)
        _repo_path(chunk["file_path"])
        if not isinstance(chunk["metadata"], dict) or not set(
            chunk["metadata"]
        ) <= _CHUNK_METADATA_FIELDS:
            raise ValueError("replay artifact chunk metadata invalid")
        ranked = row["ranked"]
        if not isinstance(ranked, dict) or set(ranked) != {
            "score",
            "score_parts",
            "rank_tier",
            "rerank_score",
            "evidence_class",
            "evidence_priority",
            "pre_ceiling_rerank_score",
            "was_ceiling_clamped",
            "reasons",
            "semantic_matches",
        }:
            raise ValueError("replay artifact ranked state invalid")
        _validate_score_map(ranked["score_parts"])
        _validate_semantic_matches(ranked["semantic_matches"])
        candidate = row["candidate"]
        if not isinstance(candidate, dict) or set(candidate) != {
            "score",
            "source",
            "score_parts",
            "semantic_matches",
            "exact_imported_symbol_provenance",
        }:
            raise ValueError("replay artifact candidate invalid")
        _validate_score_map(candidate["score_parts"])
        _validate_semantic_matches(candidate["semantic_matches"])
        provenance = candidate["exact_imported_symbol_provenance"]
        provenance_fields = {
            field.name for field in fields(ExactImportedSymbolProvenance)
        }
        if not isinstance(provenance, list):
            raise ValueError("replay artifact provenance invalid")
        for atom in provenance:
            if not isinstance(atom, dict) or set(atom) != provenance_fields:
                raise ValueError("replay artifact provenance invalid")
            _repo_path(atom["source_file_path"])
            _repo_path(atom["target_file_path"])


def _validate_score_map(value: object) -> None:
    if not isinstance(value, dict) or not all(
        isinstance(key, str)
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and np.isfinite(score)
        for key, score in value.items()
    ):
        raise ValueError("replay artifact score state invalid")


def _validate_semantic_matches(value: object) -> None:
    if not isinstance(value, list):
        raise ValueError("replay artifact semantic state invalid")
    for match in value:
        if (
            not isinstance(match, dict)
            or set(match) != {"variant_id", "score"}
            or not isinstance(match["variant_id"], str)
            or not isinstance(match["score"], (int, float))
            or isinstance(match["score"], bool)
            or not np.isfinite(match["score"])
        ):
            raise ValueError("replay artifact semantic state invalid")


def _validate_signals(value: object) -> None:
    expected = {
        "signal_id",
        "chunk_id",
        "file_path",
        "kind",
        "name",
        "start_line",
        "end_line",
        "language",
        "qualified_name",
        "project_unit_key",
        "producer",
    }
    if not isinstance(value, list):
        raise ValueError("replay artifact signals invalid")
    seen: set[str] = set()
    for signal in value:
        if not isinstance(signal, dict) or set(signal) != expected:
            raise ValueError("replay artifact signals invalid")
        signal_id = signal["signal_id"]
        if not isinstance(signal_id, str) or not signal_id or signal_id in seen:
            raise ValueError("replay artifact signals invalid")
        seen.add(signal_id)
        _repo_path(signal["file_path"])


def _validate_downstream(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "anchor_top_k",
        "protect_direct_graph",
        "expansion_layouts",
        "relation_similarities",
        "result_reason_additions",
    }:
        raise ValueError("replay artifact downstream state invalid")
    if (
        not isinstance(value["anchor_top_k"], int)
        or isinstance(value["anchor_top_k"], bool)
        or value["anchor_top_k"] < 0
        or not isinstance(value["protect_direct_graph"], bool)
        or not isinstance(value["expansion_layouts"], list)
        or not isinstance(value["result_reason_additions"], list)
    ):
        raise ValueError("replay artifact downstream state invalid")
    for layout in value["expansion_layouts"]:
        if not isinstance(layout, dict) or set(layout) != {
            "chunk_id",
            "file_path",
            "start_line",
            "end_line",
            "content_line_byte_lengths",
            "context_line_byte_lengths",
            "followup_keywords",
        }:
            raise ValueError("replay artifact expansion layout invalid")
        _repo_path(layout["file_path"])
        if (
            not isinstance(layout["chunk_id"], str)
            or not isinstance(layout["start_line"], int)
            or isinstance(layout["start_line"], bool)
            or not isinstance(layout["end_line"], int)
            or isinstance(layout["end_line"], bool)
            or layout["start_line"] <= 0
            or layout["end_line"] < layout["start_line"]
            or not isinstance(layout["followup_keywords"], list)
            or not all(
                isinstance(item, str) for item in layout["followup_keywords"]
            )
        ):
            raise ValueError("replay artifact expansion layout invalid")
        for key in ("content_line_byte_lengths", "context_line_byte_lengths"):
            if not isinstance(layout[key], list) or not all(
                isinstance(length, int)
                and not isinstance(length, bool)
                and length >= 0
                for length in layout[key]
            ):
                raise ValueError("replay artifact expansion layout invalid")
            if len(layout[key]) != layout["end_line"] - layout["start_line"] + 1:
                raise ValueError("replay artifact expansion layout invalid")
    similarities = value["relation_similarities"]
    if similarities is not None:
        _validate_score_map(similarities)
    for row in value["result_reason_additions"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"chunk_ids", "reasons"}
            or not isinstance(row["chunk_ids"], list)
            or not isinstance(row["reasons"], list)
            or not all(
                isinstance(item, str)
                for item in [*row["chunk_ids"], *row["reasons"]]
            )
        ):
            raise ValueError("replay artifact result reasons invalid")


def _plan_payload(plan: QueryPlan) -> tuple[dict[str, Any], str | None]:
    payload = asdict(plan)
    payload["error"] = None
    return payload, _planner_error_code(plan.error)


def _planner_error_code(error: str | None) -> str | None:
    if error is None:
        return None
    normalized = error.casefold()
    if "timed out" in normalized or "timeout" in normalized:
        return "timeout"
    if "http error" in normalized:
        return "http_error"
    if "request failed" in normalized or "connection" in normalized:
        return "request_error"
    if any(
        token in normalized
        for token in ("invalid", "response must", "response content")
    ):
        return "invalid_response"
    return "unknown"


def _vector_sha256(vector: Any) -> str | None:
    if vector is None:
        return None
    values = np.asarray(vector, dtype="<f4")
    if values.ndim != 1 or not bool(np.isfinite(values).all()):
        raise ValueError("query embedding is invalid")
    identity = {
        "dtype": "float32-le",
        "shape": list(values.shape),
        "bytes_sha256": hashlib.sha256(values.tobytes(order="C")).hexdigest(),
    }
    return canonical_sha256(identity)


def _signal_payload(signal: CodeSignal) -> dict[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "chunk_id": signal.chunk_id,
        "file_path": _repo_path(signal.file_path.as_posix()),
        "kind": signal.kind,
        "name": signal.name,
        "start_line": signal.start_line,
        "end_line": signal.end_line,
        "language": signal.language,
        "qualified_name": signal.qualified_name,
        "project_unit_key": signal.project_unit_key,
        "producer": signal.producer,
    }


def _signal_from_payload(payload: dict[str, Any]) -> CodeSignal:
    return CodeSignal(
        signal_id=payload["signal_id"],
        chunk_id=payload["chunk_id"],
        file_path=Path(payload["file_path"]),
        kind=payload["kind"],
        name=payload["name"],
        start_line=payload["start_line"],
        end_line=payload["end_line"],
        language=payload["language"],
        qualified_name=payload["qualified_name"],
        project_unit_key=payload["project_unit_key"],
        producer=payload["producer"],
    )


def _provider_identity(
    *,
    kind: str,
    ordinal: int,
    provider: str,
    model: str,
    base_url: str,
    endpoint_suffix: str,
) -> dict[str, Any]:
    return _provider_identity_from_endpoint(
        kind=kind,
        ordinal=ordinal,
        provider=provider,
        model=model,
        endpoint=base_url.rstrip("/") + endpoint_suffix,
    )


def _provider_identity_from_endpoint(
    *,
    kind: str,
    ordinal: int,
    provider: str,
    model: str,
    endpoint: str,
) -> dict[str, Any]:
    parsed = urlparse(endpoint)
    return {
        "kind": kind,
        "ordinal": ordinal,
        "provider": provider,
        "model": model,
        "scheme": parsed.scheme,
        "domain": parsed.hostname or "",
        "endpoint_path": parsed.path,
        "localhost": (parsed.hostname or "") in {"localhost", "127.0.0.1", "::1"},
        "ollama": provider == "ollama",
    }


def _repo_path(value: str) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("replay artifact path must be repository-relative")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError("replay artifact path must be repository-relative")
    return path.as_posix()


class _CapturedSignalLookup:
    graph_fault = None

    def __init__(self, signals: dict[str, CodeSignal]) -> None:
        self.signals = signals

    def signal_for_id(self, signal_id: str) -> CodeSignal | None:
        return self.signals.get(signal_id)


def _replay_projection(
    ranked_chunks: list[core_types._RankedChunk],
    candidates: dict[str, RetrievalCandidate],
    plan: QueryPlan,
    signal_lookup: _CapturedSignalLookup,
    final_top_k: int,
) -> dict[str, Any]:
    rows = []
    seen: set[str] = set()
    for ranked in ranked_chunks:
        path = ranked.chunk.file_path.as_posix()
        if path in seen:
            continue
        seen.add(path)
        marker = ranked.score_parts.get("planner_dependency_hint_promotion", 0.0)
        row: dict[str, Any] = {
            "path": path,
            "chunk_id": ranked.chunk.chunk_id,
            "score": ranked.rerank_score,
            "reasons": selection._result_reasons(ranked.reasons),
            "rerank_score": ranked.rerank_score,
            "planner_dependency_hint_promotion": marker,
        }
        if marker > 0:
            witness = _closed_witness(
                ranked,
                candidates[ranked.chunk.chunk_id],
                plan,
                signal_lookup,
            )
            if witness is None:
                raise ValueError("replay promotion witness unavailable")
            row["closed_exact_witness"] = asdict(witness)
        rows.append(row)
        if len(rows) >= final_top_k:
            break
    return {"top12": rows, "top12_sha256": canonical_sha256(rows)}


def _final_replay_projection(
    visible: list[core_types._ExpandedResult],
    ranked_chunks: list[core_types._RankedChunk],
    candidates: dict[str, RetrievalCandidate],
    plan: QueryPlan,
    signal_lookup: _CapturedSignalLookup,
    reason_additions: dict[tuple[str, ...], list[str]],
) -> dict[str, Any]:
    ranked_by_id = {
        ranked.chunk.chunk_id: ranked for ranked in ranked_chunks
    }
    rows: list[dict[str, Any]] = []
    for item in visible:
        marker = item.score_parts.get("planner_dependency_hint_promotion", 0.0)
        row: dict[str, Any] = {
            "path": item.file_path.as_posix(),
            "chunk_id": item.chunk_ids[0],
            "score": item.rerank_score,
            "score_parts": {
                **item.score_parts,
                "combined_score": item.score,
                "rerank_score": item.rerank_score,
                "evidence_priority": float(item.evidence_priority),
            },
            "reasons": selection._result_reasons(
                [
                    *item.reasons,
                    *reason_additions.get(tuple(item.chunk_ids), []),
                ]
            ),
            "rerank_score": item.rerank_score,
            "planner_dependency_hint_promotion": marker,
        }
        if marker > 0:
            witness = None
            for chunk_id in item.chunk_ids:
                ranked = ranked_by_id[chunk_id]
                witness = _closed_witness(
                    ranked,
                    candidates[chunk_id],
                    plan,
                    signal_lookup,
                )
                if witness is not None:
                    break
            if witness is None:
                raise ValueError("replay promotion witness unavailable")
            row["closed_exact_witness"] = asdict(witness)
        rows.append(row)
    return {"top12": rows, "top12_sha256": canonical_sha256(rows)}


def _closed_witness(
    ranked: core_types._RankedChunk,
    candidate: RetrievalCandidate,
    plan: QueryPlan,
    signal_lookup: _CapturedSignalLookup,
) -> ExactImportedSymbolProvenance | None:
    source_hints = {
        normalized
        for value in (*plan.source_symbol_hints, *plan.source_module_hints)
        if (normalized := ranking._normalized_dependency_hint(value))
    }
    if not source_hints:
        source_hints = {
            normalized
            for value in plan.imported_module_hints
            if (normalized := ranking._normalized_dependency_hint(value))
        }
    target_hints = {
        normalized
        for value in (
            *plan.imported_symbol_hints,
            *(
                plan.source_symbol_hints
                if plan.imported_symbol_hints
                else ()
            ),
        )
        if (normalized := ranking._normalized_dependency_hint(value))
    }
    semantic_pair_fallback = False
    for atom in candidate.exact_imported_symbol_provenance:
        source = signal_lookup.signal_for_id(atom.source_signal_id)
        target = signal_lookup.signal_for_id(atom.target_signal_id)
        if not (
            ranking._closed_exact_dependency_atom(ranked, atom)
            and source is not None
            and ranking._closed_dependency_source_signal(atom, source)
            and target is not None
            and ranking._closed_dependency_target_signal(atom, target)
        ):
            continue
        owner_matches = ranking._dependency_source_owner_matches(
            atom,
            source,
            plan.source_symbol_hints,
        )
        identity_matches = ranking._dependency_hint_identity_matches(
                source_signal=source,
                target_signal=target,
                source_hints=source_hints,
                target_hints=target_hints,
                semantic_pair_fallback=semantic_pair_fallback,
            )[0]
        if owner_matches is not False and (
            owner_matches is True or identity_matches
        ):
            return atom
    return None
