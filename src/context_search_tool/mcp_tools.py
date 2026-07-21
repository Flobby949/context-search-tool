from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import requests

from context_search_tool import index_health
from context_search_tool.config import ToolConfig, load_config
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    ContextPackError,
    build_context_pack,
    canonical_context_pack_bytes,
    resolve_context_pack_options,
)
from context_search_tool.formatters import (
    context_payload,
    explore_payload,
    format_explore_json,
    trace_payload,
)
from context_search_tool.indexer import (
    IncompatibleIndexError,
    RefreshFailure,
    RefreshSuccess,
    index_repository,
    refresh_repository,
    signal_schema_is_current,
)
from context_search_tool.graph_lifecycle import (
    IncompatibleOperationalSchemaError,
    IncompatibleSignalSchemaError,
    IndexBusyError,
)
from context_search_tool.manifest import (
    IncompatibleManifestSchemaError,
    embedding_config_hash,
)
from context_search_tool.models import (
    DocumentChunk,
    EvidenceAnchor,
    QueryVariant,
    RetrievalResult,
    SemanticMatch,
    SymbolRef,
)
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
)
from context_search_tool.retrieval import (
    QueryBundle,
    evidence_anchor_top_k,
    query_repository,
    trace_repository,
)
from context_search_tool.retrieval_trace import RetrievalTraceError
from context_search_tool.sqlite_store import SQLiteStore

_FEEDBACK_LOG_MAX_BYTES = 10 * 1024 * 1024
_CONTEXT_FAILED_MESSAGE = "Context pack construction failed"
_EXPLORE_FAILED_MESSAGE = "Controlled exploration failed"


def context_search_index_tool(repo: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
        index_health.preflight_public_operation(resolved_repo, "index")
        summary = index_repository(
            resolved_repo,
            config_loader=load_config,
        )
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        return _error(exc.code, str(exc))
    except requests.HTTPError:
        return _error("index_failed", "remote embedding request failed")
    except (
        RepositoryNotFoundError,
        IncompatibleIndexError,
        IndexBusyError,
        ValueError,
    ) as exc:
        return _error("index_failed", str(exc))

    return {
        "ok": True,
        "repo": str(resolved_repo),
        "summary": {
            "files_seen": summary.files_seen,
            "files_indexed": summary.files_indexed,
            "files_skipped": summary.files_skipped,
            "files_deleted": summary.files_deleted,
            "chunks_indexed": summary.chunks_indexed,
        },
    }


def context_search_query_tool(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    preflight_error = _consumer_preflight_error(resolved_repo, "query")
    if preflight_error is not None:
        return preflight_error

    try:
        config = _load_query_config(resolved_repo, final_top_k)
        bundle = query_repository(
            resolved_repo,
            query,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        payload = _query_payload(bundle)
        payload["ok"] = True
        payload["repo"] = str(resolved_repo)
        payload["index"] = _index_state(resolved_repo, config)
        _try_append_query_feedback(
            resolved_repo,
            query=query,
            payload=payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
        )
        return payload
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        return _error(exc.code, str(exc))
    except (ValueError, requests.HTTPError) as exc:
        error_payload = _error("query_failed", str(exc))
        _try_append_query_feedback(
            resolved_repo,
            query=query,
            payload=error_payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
        )
        return error_payload


def context_search_trace_tool(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    preflight_error = _consumer_preflight_error(resolved_repo, "trace")
    if preflight_error is not None:
        return preflight_error

    try:
        config = _load_query_config(resolved_repo, final_top_k)
        traced = trace_repository(
            resolved_repo,
            query,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        return trace_payload(resolved_repo, query, traced.trace)
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        return _error(exc.code, str(exc))
    except RetrievalTraceError:
        return _error("trace_failed", "Retrieval trace failed")
    except (ValueError, requests.HTTPError) as exc:
        return _error("query_failed", str(exc))
    except Exception:
        return _error("trace_failed", "Retrieval trace failed")


def context_search_context_tool(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
    max_items: int | None = None,
    max_context_bytes: int | None = None,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    preflight_error = _consumer_preflight_error(resolved_repo, "context")
    if preflight_error is not None:
        return preflight_error

    try:
        config = _load_query_config(resolved_repo, final_top_k)
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        return _error(exc.code, str(exc))
    except ValueError as exc:
        payload = _error("query_failed", str(exc))
        _try_append_query_feedback(
            resolved_repo,
            query=query,
            payload=payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
            tool="context_search_context",
        )
        return payload

    try:
        anchor_limit = evidence_anchor_top_k(config.retrieval.final_top_k)
        options = resolve_context_pack_options(
            config,
            context_lines=context_lines,
            max_evidence_anchors=anchor_limit,
            max_items=max_items,
            max_pack_bytes=max_context_bytes,
        )
    except ContextPackError as exc:
        payload = _error(exc.code, exc.message)
        _try_append_query_feedback(
            resolved_repo,
            query=query,
            payload=payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
            tool="context_search_context",
        )
        return payload
    try:
        bundle = query_repository(
            resolved_repo,
            query,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
    except IncompatibleSignalSchemaError as exc:
        return _error(exc.code, str(exc))
    except (ValueError, requests.HTTPError) as exc:
        payload = _error("query_failed", str(exc))
        _try_append_query_feedback(
            resolved_repo,
            query=query,
            payload=payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
            tool="context_search_context",
        )
        return payload

    try:
        pack = build_context_pack(bundle, options)
        payload = context_payload(resolved_repo, bundle, pack)
    except ContextPackError:
        payload = _error("context_failed", _CONTEXT_FAILED_MESSAGE)
    except Exception:
        payload = _error("context_failed", _CONTEXT_FAILED_MESSAGE)

    _try_append_query_feedback(
        resolved_repo,
        query=query,
        payload=payload,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
        tool="context_search_context",
    )
    return payload


def context_search_explore_tool(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
    max_items: int | None = None,
    max_context_bytes: int | None = None,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    preflight_error = _consumer_preflight_error(resolved_repo, "explore")
    if preflight_error is not None:
        return preflight_error

    from context_search_tool.exploration import (
        explore_repository,
        resolve_explore_pack_options,
    )
    from context_search_tool.exploration.options import (
        resolve_explore_config,
        validate_explore_request_options,
    )

    effective_initial_top_k: int | None = None
    embedding: dict[str, Any] | None = None
    request = {
        "context_lines": context_lines,
        "full_file": full_file,
        "requested_final_top_k": final_top_k,
        "max_items": max_items,
        "max_context_bytes": max_context_bytes,
    }
    try:
        validate_explore_request_options(
            final_top_k=final_top_k,
            context_lines=context_lines,
            full_file=full_file,
            max_items=max_items,
            max_context_bytes=max_context_bytes,
        )
    except ValueError as exc:
        payload = _error("query_failed", str(exc))
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=None,
            embedding=None,
        )
        return payload
    except ContextPackError as exc:
        payload = _error(exc.code, exc.message)
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=None,
            embedding=None,
        )
        return payload
    except Exception:
        payload = _error("explore_failed", _EXPLORE_FAILED_MESSAGE)
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=None,
            embedding=None,
        )
        return payload

    try:
        config = load_config(resolved_repo)
        explore_config, _, effective_initial_top_k = resolve_explore_config(
            config,
            final_top_k=final_top_k,
        )
        pack_options = resolve_explore_pack_options(
            explore_config,
            context_lines=context_lines,
            max_items=max_items,
            max_pack_bytes=max_context_bytes,
        )
        embedding = _explore_embedding(explore_config)
    except ValueError as exc:
        payload = _error("query_failed", str(exc))
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=effective_initial_top_k,
            embedding=None,
        )
        return payload
    except ContextPackError as exc:
        payload = _error(exc.code, exc.message)
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=effective_initial_top_k,
            embedding=None,
        )
        return payload
    except Exception:
        payload = _error("explore_failed", _EXPLORE_FAILED_MESSAGE)
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=effective_initial_top_k,
            embedding=None,
        )
        return payload

    try:
        explored = explore_repository(
            resolved_repo,
            query,
            explore_config,
            pack_options,
            context_lines=context_lines,
            full_file=full_file,
        )
    except (ValueError, requests.HTTPError) as exc:
        payload = _error("query_failed", str(exc))
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=effective_initial_top_k,
            embedding=None,
        )
        return payload
    except Exception:
        payload = _error("explore_failed", _EXPLORE_FAILED_MESSAGE)
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=effective_initial_top_k,
            embedding=None,
        )
        return payload

    try:
        payload = explore_payload(
            resolved_repo,
            query,
            explored,
            requested_final_top_k=final_top_k,
        )
        if (
            payload["retrieval"]["effective_initial_top_k"]
            != effective_initial_top_k
        ):
            raise ValueError("exploration limit mismatch")
    except Exception:
        payload = _error("explore_failed", _EXPLORE_FAILED_MESSAGE)
        _record_explore_feedback(
            resolved_repo,
            payload,
            request,
            effective_initial_top_k=effective_initial_top_k,
            embedding=None,
        )
        return payload

    _record_explore_feedback(
        resolved_repo,
        payload,
        request,
        effective_initial_top_k=effective_initial_top_k,
        embedding=embedding,
    )
    return payload


def context_search_status_tool(
    repo: str,
    verify: bool = False,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError:
        return index_health.status_error_envelope("repo_not_found")
    try:
        report = index_health.inspect_repository_health(
            resolved_repo,
            mode="verified" if verify else "quick",
        )
    except Exception:
        return index_health.status_error_envelope("status_failed")
    return index_health.status_success_envelope(str(resolved_repo), report)


def context_search_refresh_tool(repo: str) -> dict[str, Any]:
    """Mutate an existing index and return the closed RefreshEnvelope v1."""
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError:
        return index_health.refresh_error_envelope("repo_not_found")
    try:
        result = refresh_repository(
            resolved_repo,
            config_loader=load_config,
        )
    except Exception:
        return index_health.refresh_error_envelope("refresh_failed")
    if isinstance(result, RefreshFailure):
        return index_health.refresh_error_envelope(
            result.code,
            result.network_egress_outcome,
        )
    if not isinstance(result, RefreshSuccess):
        return index_health.refresh_error_envelope("refresh_failed", "possible")
    try:
        report = index_health.inspect_repository_health(
            resolved_repo,
            mode="quick",
        )
        return index_health.refresh_success_envelope(
            str(resolved_repo),
            summary=result.summary,
            indexed_before=result.indexed_before,
            configured=result.configured,
            network_egress_performed=result.network_egress_performed,
            report=report,
        )
    except Exception:
        return index_health.refresh_error_envelope(
            "refresh_failed",
            "performed" if result.network_egress_performed else "not_attempted",
        )


def context_search_stats_tool(
    repo: str,
    verify: bool = False,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    try:
        index_health.preflight_public_operation(resolved_repo, "stats")
        report = index_health.inspect_repository_health(
            resolved_repo,
            mode="verified" if verify else "quick",
        )
        payload = index_health.build_index_stats_payload(resolved_repo, report)
    except index_health.MissingIndexError:
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        return _error(exc.code, str(exc))
    except index_health.IndexCorruptionError as exc:
        return _error(exc.code, str(exc))
    except Exception:
        return _error("stats_failed", "statistics inspection failed")

    if report.integrity.graph == "stale":
        logging.getLogger("context_search_tool.mcp_tools").warning(
            "graph_index_stale"
        )
    return payload


def context_search_explain_tool(repo: str, location: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    preflight_error = _consumer_preflight_error(resolved_repo, "explain")
    if preflight_error is not None:
        return preflight_error

    try:
        file_path, line = _parse_location(location, resolved_repo)
    except ValueError as exc:
        return _error("invalid_location", str(exc))

    index_dir = index_dir_for(resolved_repo)

    try:
        store = SQLiteStore(index_dir / "index.sqlite")
        with store.graph_read_session() as graph_session:
            chunk = graph_session.chunk_for_line(file_path, line)
            if chunk is None:
                raise KeyError(file_path)
            graph = graph_session.explain_projection(chunk)
    except KeyError:
        return _error(
            "chunk_not_found",
            f"No indexed chunk covers {file_path.as_posix()}:{line}.",
        )
    except IncompatibleSignalSchemaError as exc:
        return _error(exc.code, str(exc))

    if graph["status"] == "stale":
        logging.getLogger("context_search_tool.mcp_tools").warning("graph_index_stale")

    return {
        "ok": True,
        "repo": str(resolved_repo),
        "chunk": _chunk_payload(chunk),
        "graph": graph,
    }


def _load_query_config(repo: Path, final_top_k: int | None) -> ToolConfig:
    config = load_config(repo)
    if final_top_k is None:
        return config
    if final_top_k < 1:
        raise ValueError("final_top_k must be greater than zero")
    return replace(
        config,
        retrieval=replace(config.retrieval, final_top_k=final_top_k),
    )


def _consumer_preflight_error(
    repo: Path,
    operation: str,
) -> dict[str, Any] | None:
    try:
        index_health.preflight_public_operation(repo, operation)
    except index_health.MissingIndexError:
        return _error(
            "missing_index",
            f"Missing index for {repo}. Run context_search_index first.",
        )
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        return _error(exc.code, str(exc))
    except index_health.IndexCorruptionError as exc:
        return _error("query_failed", str(exc))
    return None


def _query_payload(bundle: QueryBundle) -> dict[str, Any]:
    return {
        "query": bundle.query,
        "expanded_tokens": bundle.expanded_tokens,
        "query_variants": [
            _query_variant_payload(variant) for variant in bundle.query_variants
        ],
        "variant_retrieval_status": bundle.variant_retrieval_status,
        "followup_keywords": bundle.followup_keywords,
        "summary": {
            "entry_points": bundle.summary.entry_points,
            "implementation": bundle.summary.implementation,
            "related_types": bundle.summary.related_types,
            "possibly_legacy": bundle.summary.possibly_legacy,
        },
        "planner": _planner_payload(bundle),
        "results": [_result_payload(result) for result in bundle.results],
        "evidence_anchors": [
            _anchor_payload(anchor) for anchor in bundle.evidence_anchors
        ],
    }


def _query_variant_payload(variant: QueryVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "text": variant.text,
        "source": variant.source,
    }


def _semantic_match_payload(match: SemanticMatch) -> dict[str, Any]:
    return {
        "variant_id": match.variant_id,
        "score": match.score,
    }


def _planner_payload(bundle: QueryBundle) -> dict[str, Any]:
    plan = bundle.planner
    payload: dict[str, Any] = {
        "enabled": plan.status != "disabled",
        "provider": plan.provider,
        "model": plan.model,
        "prompt_version": plan.prompt_version,
        "prompt_hash": plan.prompt_hash,
        "status": plan.status,
        "latency_ms": plan.latency_ms,
    }
    if plan.status == "ok":
        payload.update(
            {
                "rewritten_queries": plan.rewritten_queries,
                "grep_keywords": plan.grep_keywords,
                "symbol_hints": plan.symbol_hints,
                "intent": plan.intent,
            }
        )
    if plan.status == "fallback":
        payload["error"] = plan.error
    if plan.repo_profile_hash:
        payload["repo_profile_hash"] = plan.repo_profile_hash
        payload["repo_profile_truncated"] = plan.repo_profile_truncated
    if plan.discarded_hints:
        payload["discarded_hint_count"] = len(plan.discarded_hints)
        payload["discarded_hints"] = plan.discarded_hints[:8]
    return payload


def _result_payload(result: RetrievalResult) -> dict[str, Any]:
    return {
        "file_path": result.file_path.as_posix(),
        "start_line": result.start_line,
        "end_line": result.end_line,
        "content": result.content,
        "score": result.score,
        "score_parts": result.score_parts,
        "reasons": result.reasons,
        "followup_keywords": result.followup_keywords,
        "semantic_matches": [
            _semantic_match_payload(match) for match in result.semantic_matches
        ],
    }


def _anchor_payload(anchor: EvidenceAnchor) -> dict[str, Any]:
    return {
        "file_path": anchor.file_path.as_posix(),
        "start_line": anchor.start_line,
        "end_line": anchor.end_line,
        "content": anchor.content,
        "score": anchor.score,
        "score_parts": anchor.score_parts,
        "reasons": anchor.reasons,
        "anchor_kind": anchor.anchor_kind,
        "semantic_matches": [
            _semantic_match_payload(match) for match in anchor.semantic_matches
        ],
    }


def _chunk_payload(chunk: DocumentChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "file_path": chunk.file_path.as_posix(),
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "chunk_type": chunk.chunk_type,
        "symbols": [_symbol_payload(symbol) for symbol in chunk.symbols],
        "lexical_tokens": chunk.lexical_tokens,
        "embedding_id": chunk.embedding_id,
        "metadata": chunk.metadata,
    }


def _symbol_payload(symbol: SymbolRef) -> dict[str, Any]:
    return {
        "name": symbol.name,
        "kind": symbol.kind,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "language": symbol.language,
        "metadata": symbol.metadata,
    }


def _index_state(repo: Path, config: ToolConfig) -> dict[str, Any]:
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    store.initialize()
    return {
        "signal_schema_current": signal_schema_is_current(store),
        "embedding": {
            "provider": config.embedding.provider,
            "model": config.embedding.model,
            "dimensions": config.embedding.dimensions,
            "config_hash": embedding_config_hash(config.embedding),
        },
    }


_EXPLORE_PROJECTION_KEYS = (
    "ok",
    "error_code",
    "request",
    "exploration",
    "context_pack",
    "embedding",
)
_EXPLORE_REQUEST_KEYS = (
    "context_lines",
    "full_file",
    "requested_final_top_k",
    "effective_initial_top_k",
    "max_items",
    "max_context_bytes",
)
_EXPLORE_AGGREGATE_KEYS = (
    "schema_version",
    "outcome",
    "termination_reason",
    "round_count",
    "planned_probe_count",
    "executed_probe_count",
    "stale_skipped_probe_count",
    "retrieval_call_count",
    "initial_satisfied_goal_count",
    "final_satisfied_goal_count",
)
_EXPLORE_PACK_FEEDBACK_KEYS = (
    "schema_version",
    "status",
    "confidence",
    "included_items",
    "content_bytes",
    "pack_bytes",
    "budget_exhausted",
)
_EXPLORE_EMBEDDING_KEYS = (
    "provider",
    "model",
    "dimensions",
    "config_hash",
)
_EXPLORE_ERROR_CODES = {
    "repo_not_found",
    "missing_index",
    "invalid_context_options",
    "query_failed",
    "explore_failed",
}
_EXPLORE_OUTCOMES = {"complete", "empty", "partial"}
_EXPLORE_TERMINATIONS = {
    "context_budget_zero",
    "exact_satisfied",
    "initial_satisfied",
    "no_grounded_probe",
    "satisfied",
    "no_marginal_gain",
    "probe_budget_exhausted",
    "initial_missing_index",
    "initial_empty",
    "initial_retrieval_incomplete",
    "followup_query_failed",
}
_CONTEXT_PACK_STATUSES = {"empty", "partial", "ready"}
_CONTEXT_PACK_CONFIDENCE = {"none", "low", "medium", "high"}
_MAX_FEEDBACK_INTEGER = 2_147_483_647


def _explore_embedding(config: ToolConfig) -> dict[str, Any]:
    return {
        "provider": config.embedding.provider,
        "model": config.embedding.model,
        "dimensions": config.embedding.dimensions,
        "config_hash": embedding_config_hash(config.embedding),
    }


def _record_explore_feedback(
    repo: Path,
    payload: dict[str, Any],
    request: dict[str, Any],
    *,
    effective_initial_top_k: int | None,
    embedding: dict[str, Any] | None,
) -> None:
    try:
        projection = _explore_feedback_projection(
            payload,
            context_lines=request.get("context_lines"),
            full_file=request.get("full_file"),
            requested_final_top_k=request.get("requested_final_top_k"),
            effective_initial_top_k=effective_initial_top_k,
            max_items=request.get("max_items"),
            max_context_bytes=request.get("max_context_bytes"),
            embedding=embedding,
        )
    except Exception:
        return
    _try_append_explore_feedback(repo, projection)


def _explore_feedback_projection(
    payload: dict[str, Any],
    *,
    context_lines: Any,
    full_file: Any,
    requested_final_top_k: Any,
    effective_initial_top_k: Any,
    max_items: Any,
    max_context_bytes: Any,
    embedding: dict[str, Any] | None,
) -> dict[str, Any]:
    success = payload.get("ok") is True
    if success:
        validated = json.loads(format_explore_json(payload))
        trace = validated["trace"]
        pack = validated["context_pack"]
        budget = pack["budget"]
        validated_embedding = _validated_explore_embedding(embedding)
        error_code = None
        exploration = {
            "schema_version": trace["schema_version"],
            "outcome": trace["outcome"],
            "termination_reason": trace["termination_reason"],
            "round_count": len(trace["rounds"]),
            "planned_probe_count": trace["planned_probe_count"],
            "executed_probe_count": trace["executed_probe_count"],
            "stale_skipped_probe_count": trace["stale_skipped_probe_count"],
            "retrieval_call_count": trace["retrieval_call_count"],
            "initial_satisfied_goal_count": trace[
                "initial_satisfied_goal_count"
            ],
            "final_satisfied_goal_count": trace["final_satisfied_goal_count"],
        }
        context_pack = {
            "schema_version": pack["schema_version"],
            "status": pack["status"],
            "confidence": pack["confidence"]["level"],
            "included_items": budget["included_items"],
            "content_bytes": budget["content_bytes"],
            "pack_bytes": budget["pack_bytes"],
            "budget_exhausted": budget["budget_exhausted"],
        }
    else:
        error_code = _validated_explore_error(payload)
        exploration = {
            "schema_version": None,
            "outcome": None,
            "termination_reason": None,
            "round_count": 0,
            "planned_probe_count": 0,
            "executed_probe_count": 0,
            "stale_skipped_probe_count": 0,
            "retrieval_call_count": 0,
            "initial_satisfied_goal_count": 0,
            "final_satisfied_goal_count": 0,
        }
        context_pack = {
            "schema_version": None,
            "status": None,
            "confidence": None,
            "included_items": 0,
            "content_bytes": 0,
            "pack_bytes": 0,
            "budget_exhausted": False,
        }
        validated_embedding = {
            "provider": None,
            "model": None,
            "dimensions": None,
            "config_hash": None,
        }

    projection = {
        "ok": success,
        "error_code": error_code,
        "request": {
            "context_lines": _bounded_feedback_int(context_lines, minimum=0),
            "full_file": full_file if type(full_file) is bool else None,
            "requested_final_top_k": _bounded_feedback_int(
                requested_final_top_k,
                minimum=1,
            ),
            "effective_initial_top_k": _bounded_feedback_int(
                effective_initial_top_k,
                minimum=1,
                maximum=12,
            ),
            "max_items": _bounded_feedback_int(max_items, minimum=1),
            "max_context_bytes": _bounded_feedback_int(
                max_context_bytes,
                minimum=4096,
            ),
        },
        "exploration": exploration,
        "context_pack": context_pack,
        "embedding": validated_embedding,
    }
    _validated_explore_projection(projection)
    return projection


def _validated_explore_error(payload: object) -> str:
    if type(payload) is not dict or tuple(payload) != ("ok", "error"):
        raise ValueError("invalid explore error envelope")
    error = payload["error"]
    if payload["ok"] is not False or type(error) is not dict or tuple(error) != (
        "code",
        "message",
    ):
        raise ValueError("invalid explore error envelope")
    code = error["code"]
    if (
        code not in _EXPLORE_ERROR_CODES
        or type(error["message"]) is not str
        or not error["message"]
    ):
        raise ValueError("invalid explore error envelope")
    return code


def _validated_explore_embedding(
    embedding: dict[str, Any] | None,
) -> dict[str, Any]:
    if type(embedding) is not dict or tuple(embedding) != _EXPLORE_EMBEDDING_KEYS:
        raise ValueError("invalid explore embedding projection")
    provider = embedding["provider"]
    model = embedding["model"]
    dimensions = embedding["dimensions"]
    config_hash = embedding["config_hash"]
    if (
        type(provider) is not str
        or not provider
        or type(model) is not str
        or not model
        or type(dimensions) is not int
        or dimensions < 1
        or type(config_hash) is not str
        or not config_hash
    ):
        raise ValueError("invalid explore embedding projection")
    return dict(embedding)


def _bounded_feedback_int(
    value: Any,
    *,
    minimum: int,
    maximum: int = _MAX_FEEDBACK_INTEGER,
) -> int | None:
    if type(value) is not int or not minimum <= value <= maximum:
        return None
    return value


def _try_append_explore_feedback(
    repo: Path,
    projection: dict[str, Any],
) -> None:
    try:
        _append_explore_feedback(repo, projection)
    except Exception:
        pass


def _append_explore_feedback(
    repo: Path,
    projection: dict[str, Any],
) -> None:
    validated = _validated_explore_projection(projection)
    index_dir = index_dir_for(repo)
    if not index_dir.exists():
        return
    timestamp = int(time.time())
    if timestamp < 0:
        raise ValueError("invalid explore feedback timestamp")
    event = {
        "timestamp": timestamp,
        "tool": "context_search_explore",
        "ok": validated["ok"],
        "error_code": validated["error_code"],
        "repo_hash": _short_hash(str(repo)),
        "request": validated["request"],
        "exploration": validated["exploration"],
        "context_pack": validated["context_pack"],
        "embedding": validated["embedding"],
    }
    log_path = index_dir / "mcp_calls.jsonl"
    _rotate_feedback_log(log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                event,
                ensure_ascii=True,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )


def _validated_explore_projection(
    projection: object,
) -> dict[str, Any]:
    if type(projection) is not dict or tuple(projection) != _EXPLORE_PROJECTION_KEYS:
        raise ValueError("invalid explore feedback projection")
    if type(projection["ok"]) is not bool:
        raise ValueError("invalid explore feedback projection")
    error_code = projection["error_code"]
    if error_code is not None and error_code not in _EXPLORE_ERROR_CODES:
        raise ValueError("invalid explore feedback projection")
    if (projection["ok"] and error_code is not None) or (
        not projection["ok"] and error_code is None
    ):
        raise ValueError("invalid explore feedback projection")
    for key, expected_keys in (
        ("request", _EXPLORE_REQUEST_KEYS),
        ("exploration", _EXPLORE_AGGREGATE_KEYS),
        ("context_pack", _EXPLORE_PACK_FEEDBACK_KEYS),
        ("embedding", _EXPLORE_EMBEDDING_KEYS),
    ):
        value = projection[key]
        if type(value) is not dict or tuple(value) != expected_keys:
            raise ValueError("invalid explore feedback projection")

    request = projection["request"]
    request_ranges = {
        "context_lines": (0, _MAX_FEEDBACK_INTEGER),
        "requested_final_top_k": (1, _MAX_FEEDBACK_INTEGER),
        "effective_initial_top_k": (1, 12),
        "max_items": (1, _MAX_FEEDBACK_INTEGER),
        "max_context_bytes": (4096, _MAX_FEEDBACK_INTEGER),
    }
    for key, (minimum, maximum) in request_ranges.items():
        value = request[key]
        if value is not None and (
            type(value) is not int or not minimum <= value <= maximum
        ):
            raise ValueError("invalid explore feedback projection")
    if request["full_file"] is not None and type(request["full_file"]) is not bool:
        raise ValueError("invalid explore feedback projection")

    exploration = projection["exploration"]
    context_pack = projection["context_pack"]
    embedding = projection["embedding"]
    if projection["ok"]:
        if (
            exploration["schema_version"] != 2
            or exploration["outcome"] not in _EXPLORE_OUTCOMES
            or exploration["termination_reason"] not in _EXPLORE_TERMINATIONS
            or type(exploration["round_count"]) is not int
            or not 1 <= exploration["round_count"] <= 2
        ):
            raise ValueError("invalid explore feedback projection")
        for key in _EXPLORE_AGGREGATE_KEYS[4:]:
            value = exploration[key]
            if type(value) is not int or value < 0:
                raise ValueError("invalid explore feedback projection")
        if (
            exploration["executed_probe_count"] > 2
            or exploration["planned_probe_count"] > 8
            or exploration["retrieval_call_count"]
            != 1 + exploration["executed_probe_count"]
            or exploration["initial_satisfied_goal_count"]
            > exploration["final_satisfied_goal_count"]
        ):
            raise ValueError("invalid explore feedback projection")
        if (
            context_pack["schema_version"] != 2
            or context_pack["status"] not in _CONTEXT_PACK_STATUSES
            or context_pack["confidence"] not in _CONTEXT_PACK_CONFIDENCE
        ):
            raise ValueError("invalid explore feedback projection")
        for key in ("included_items", "content_bytes", "pack_bytes"):
            value = context_pack[key]
            if type(value) is not int or value < 0:
                raise ValueError("invalid explore feedback projection")
        if (
            context_pack["pack_bytes"] < 1
            or type(context_pack["budget_exhausted"]) is not bool
        ):
            raise ValueError("invalid explore feedback projection")
        _validated_explore_embedding(embedding)
    else:
        if exploration != {
            "schema_version": None,
            "outcome": None,
            "termination_reason": None,
            "round_count": 0,
            "planned_probe_count": 0,
            "executed_probe_count": 0,
            "stale_skipped_probe_count": 0,
            "retrieval_call_count": 0,
            "initial_satisfied_goal_count": 0,
            "final_satisfied_goal_count": 0,
        } or context_pack != {
            "schema_version": None,
            "status": None,
            "confidence": None,
            "included_items": 0,
            "content_bytes": 0,
            "pack_bytes": 0,
            "budget_exhausted": False,
        } or embedding != {
            "provider": None,
            "model": None,
            "dimensions": None,
            "config_hash": None,
        }:
            raise ValueError("invalid explore feedback projection")
    return {
        key: dict(value) if type(value) is dict else value
        for key, value in projection.items()
    }


def _try_append_query_feedback(
    repo: Path,
    query: str,
    payload: dict[str, Any],
    context_lines: int | None,
    full_file: bool,
    final_top_k: int | None,
    tool: str = "context_search_query",
) -> None:
    try:
        _append_query_feedback(
            repo,
            query=query,
            payload=payload,
            context_lines=context_lines,
            full_file=full_file,
            final_top_k=final_top_k,
            tool=tool,
        )
    except OSError:
        pass


def _append_query_feedback(
    repo: Path,
    query: str,
    payload: dict[str, Any],
    context_lines: int | None,
    full_file: bool,
    final_top_k: int | None,
    tool: str = "context_search_query",
) -> None:
    index_dir = index_dir_for(repo)
    if not index_dir.exists():
        return
    event = {
        "timestamp": int(time.time()),
        "tool": tool,
        "ok": bool(payload.get("ok")),
        "repo_hash": _short_hash(str(repo)),
        "query": query,
        "context_lines": context_lines,
        "full_file": full_file,
        "final_top_k": final_top_k,
        "error_code": payload.get("error", {}).get("code"),
    }
    if tool == "context_search_context":
        context_pack_feedback = _feedback_context_pack_payload(payload)
        if context_pack_feedback is not None:
            event["context_pack"] = context_pack_feedback
    else:
        event.update(
            {
                "result_count": len(payload.get("results", [])),
                "top_score": _top_score(payload),
                "top_score_parts": _top_score_parts(payload),
                "summary_counts": _summary_counts(payload),
                "followup_keyword_count": len(
                    payload.get("followup_keywords", [])
                ),
                "embedding": payload.get("index", {}).get("embedding", {}),
                "planner": _feedback_planner_payload(payload),
                "variant_retrieval": _feedback_variant_payload(payload),
            }
        )
    log_path = index_dir / "mcp_calls.jsonl"
    _rotate_feedback_log(log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")


def _feedback_context_pack_payload(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    pack = payload.get("context_pack")
    if type(pack) is not dict:
        return None
    try:
        encoded = canonical_context_pack_bytes(pack)
    except Exception:
        return None
    raw_budget = pack.get("budget")
    if type(raw_budget) is not dict:
        return None
    declared_pack_bytes = raw_budget.get("pack_bytes")
    if (
        type(declared_pack_bytes) is not int
        or declared_pack_bytes <= 0
        or declared_pack_bytes != len(encoded)
    ):
        return None
    if type(pack.get("schema_version")) is not int or pack["schema_version"] != 2:
        return None
    status = pack.get("status")
    if type(status) is not str or status not in {"empty", "partial", "ready"}:
        return None
    confidence_payload = pack.get("confidence")
    if type(confidence_payload) is not dict:
        return None
    confidence = confidence_payload.get("level")
    if type(confidence) is not str or confidence not in {
        "none",
        "low",
        "medium",
        "high",
    }:
        return None

    items = pack.get("items")
    if type(items) is not list or any(type(item) is not dict for item in items):
        return None
    groups = pack.get("groups")
    if type(groups) is not dict or tuple(groups) != CONTEXT_GROUPS:
        return None
    group_counts: dict[str, int] = {}
    for group in CONTEXT_GROUPS:
        group_items = groups.get(group)
        if type(group_items) is not list:
            return None
        group_counts[group] = len(group_items)
    if sum(group_counts.values()) != len(items):
        return None

    excerpt_count = 0
    computed_truncated_items = 0
    for item in items:
        excerpts = item.get("excerpts")
        if type(excerpts) is not list or any(
            type(excerpt) is not dict
            or type(excerpt.get("truncated")) is not bool
            for excerpt in excerpts
        ):
            return None
        excerpt_count += len(excerpts)
        computed_truncated_items += int(
            any(excerpt["truncated"] for excerpt in excerpts)
        )

    evidence_needs = pack.get("evidence_needs")
    if type(evidence_needs) is not list or any(
        type(need) is not dict or type(need.get("required")) is not bool
        for need in evidence_needs
    ):
        return None
    required_need_count = sum(need["required"] for need in evidence_needs)

    required_categories: set[str] = set()
    recommended_categories: set[str] = set()
    missing_evidence = pack.get("missing_evidence")
    if type(missing_evidence) is not list:
        return None
    for evidence in missing_evidence:
        if type(evidence) is not dict:
            return None
        category = evidence.get("category")
        required = evidence.get("required")
        if category not in CONTEXT_GROUPS or type(required) is not bool:
            return None
        if required:
            required_categories.add(category)
        else:
            recommended_categories.add(category)
    recommended_categories.difference_update(required_categories)

    next_queries = pack.get("next_queries")
    if type(next_queries) is not list:
        return None
    omissions = pack.get("omissions")
    if type(omissions) is not list:
        return None
    budget_keys = (
        "max_items",
        "max_pack_bytes",
        "content_bytes",
        "pack_bytes",
    )
    budget: dict[str, int] = {}
    for key in budget_keys:
        value = raw_budget.get(key)
        if type(value) is not int or value < 0:
            return None
        budget[key] = value
    counter_keys = (
        "included_items",
        "included_excerpts",
        "truncated_item_count",
        "omitted_item_count",
    )
    counters: dict[str, int] = {}
    for key in counter_keys:
        value = raw_budget.get(key)
        if type(value) is not int or value < 0:
            return None
        counters[key] = value
    if (
        counters["included_items"] != len(items)
        or counters["included_excerpts"] != excerpt_count
        or counters["truncated_item_count"] != computed_truncated_items
        or len(omissions) > counters["omitted_item_count"]
    ):
        return None
    return {
        "schema_version": 2,
        "status": status,
        "confidence": confidence,
        "group_counts": group_counts,
        "need_count": len(evidence_needs),
        "required_need_count": required_need_count,
        "selected_item_count": len(items),
        "excerpt_count": excerpt_count,
        "truncated_item_count": counters["truncated_item_count"],
        "omitted_item_count": counters["omitted_item_count"],
        "required_missing_categories": [
            category
            for category in CONTEXT_GROUPS
            if category in required_categories
        ],
        "recommended_missing_categories": [
            category
            for category in CONTEXT_GROUPS
            if category in recommended_categories
        ],
        "budget": budget,
        "next_query_count": len(next_queries),
    }


def _feedback_planner_payload(payload: dict[str, Any]) -> dict[str, Any]:
    planner = dict(payload.get("planner", {}))
    return {
        key: planner.get(key)
        for key in (
            "enabled",
            "provider",
            "model",
            "prompt_version",
            "prompt_hash",
            "status",
            "latency_ms",
            "intent",
            "error",
            "repo_profile_hash",
            "repo_profile_truncated",
            "discarded_hint_count",
        )
        if key in planner
    }


def _feedback_variant_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("variant_retrieval_status", "original_only")
    if status not in ("original_only", "hybrid", "embedding_fallback"):
        status = "original_only"
    variants = payload.get("query_variants", [])
    if not isinstance(variants, list):
        variants = []
    bounded = []
    for position, item in enumerate(variants):
        if not isinstance(item, dict):
            continue
        variant_id = item.get("variant_id")
        source = item.get("source")
        is_original = source == "original" and variant_id == "original"
        is_planner = False
        if source == "planner" and isinstance(variant_id, str):
            prefix, separator, raw_index = variant_id.partition(":")
            is_planner = (
                prefix == "planner"
                and separator == ":"
                and raw_index.isascii()
                and raw_index.isdecimal()
                and (raw_index == "0" or not raw_index.startswith("0"))
            )
        if not (is_original or is_planner):
            continue
        text = item.get("text", "")
        bounded.append(
            {
                "variant_id": variant_id,
                "source": source,
                "position": position,
                "text_hash": _short_hash(text if isinstance(text, str) else ""),
            }
        )
    return {
        "status": status,
        "count": len(bounded),
        "variants": bounded,
    }


def _rotate_feedback_log(log_path: Path) -> None:
    if not log_path.exists() or log_path.stat().st_size <= _FEEDBACK_LOG_MAX_BYTES:
        return
    rotated_path = log_path.with_name(f"mcp_calls.{time.time_ns()}.jsonl")
    log_path.replace(rotated_path)


def _top_score(payload: dict[str, Any]) -> float | None:
    results = payload.get("results", [])
    if not results:
        return None
    return results[0].get("score")


def _top_score_parts(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results", [])
    if not results:
        return {}
    return dict(results[0].get("score_parts", {}))


def _summary_counts(payload: dict[str, Any]) -> dict[str, int]:
    summary = payload.get("summary", {})
    return {
        "entry_points": len(summary.get("entry_points", [])),
        "implementation": len(summary.get("implementation", [])),
        "related_types": len(summary.get("related_types", [])),
        "possibly_legacy": len(summary.get("possibly_legacy", [])),
    }


def _parse_location(location: str, repo: Path) -> tuple[Path, int]:
    if ":" not in location:
        raise ValueError("location must be file:line")
    raw_path, raw_line = location.rsplit(":", 1)
    try:
        line = int(raw_line)
    except ValueError as exc:
        raise ValueError("line must be an integer") from exc
    if line < 1:
        raise ValueError("line must be greater than zero")

    path = Path(raw_path)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(repo)
        except ValueError:
            raise ValueError("absolute path must be inside repo") from None
    return path, line


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
