from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import requests

from context_search_tool.config import ToolConfig, load_config
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    UNEXPECTED_CONTEXT_ERROR,
    ContextPackError,
    build_context_pack,
    context_pack_payload,
    resolve_context_pack_options,
)
from context_search_tool.indexer import (
    IncompatibleIndexError,
    index_repository,
    signal_schema_is_current,
)
from context_search_tool.manifest import embedding_config_hash, load_manifest
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
)
from context_search_tool.sqlite_store import SQLiteStore

_FEEDBACK_LOG_MAX_BYTES = 10 * 1024 * 1024


def context_search_index_tool(repo: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
        config = load_config(resolved_repo)
        summary = index_repository(resolved_repo, config)
    except (
        RepositoryNotFoundError,
        IncompatibleIndexError,
        ValueError,
        requests.HTTPError,
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

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

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


def context_search_context_tool(
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

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

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
        anchor_limit = evidence_anchor_top_k(config.retrieval.final_top_k)
        options = resolve_context_pack_options(
            config,
            context_lines=context_lines,
            full_file=full_file,
            max_evidence_anchors=anchor_limit,
        )
        pack = build_context_pack(bundle, options)
        payload["context_pack"] = context_pack_payload(bundle, pack)
    except ContextPackError as exc:
        payload = _error("context_failed", str(exc))
    except Exception:
        payload = _error("context_failed", UNEXPECTED_CONTEXT_ERROR)

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


def context_search_stats_tool(repo: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

    config = load_config(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    counts = store.stats()
    manifest = load_manifest(resolved_repo) if (index_dir / "manifest.json").exists() else None
    provider = manifest.embedding_provider if manifest is not None else config.embedding.provider
    model = manifest.embedding_model if manifest is not None else config.embedding.model
    dimensions = (
        manifest.embedding_dimensions if manifest is not None else config.embedding.dimensions
    )
    return {
        "ok": True,
        "repo": str(resolved_repo),
        "stats": {
            "total_files": counts["source_files"],
            "total_chunks": counts["active_chunks"],
            "deleted_chunks": counts["deleted_chunks"],
            "symbols": counts["symbols"],
            "lexical_tokens": counts["tokens"],
            "disk_usage_bytes": _disk_usage(index_dir),
        },
        "embedding": {
            "provider": provider,
            "model": model,
            "dimensions": dimensions,
        },
    }


def context_search_explain_tool(repo: str, location: str) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    try:
        file_path, line = _parse_location(location, resolved_repo)
    except ValueError as exc:
        return _error("invalid_location", str(exc))

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

    store = SQLiteStore(index_dir / "index.sqlite")
    try:
        chunk = store.chunk_for_line(file_path, line)
    except KeyError:
        return _error(
            "chunk_not_found",
            f"No indexed chunk covers {file_path.as_posix()}:{line}.",
        )

    return {
        "ok": True,
        "repo": str(resolved_repo),
        "chunk": _chunk_payload(chunk),
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
        "result_count": len(payload.get("results", [])),
        "top_score": _top_score(payload),
        "top_score_parts": _top_score_parts(payload),
        "summary_counts": _summary_counts(payload),
        "followup_keyword_count": len(payload.get("followup_keywords", [])),
        "embedding": payload.get("index", {}).get("embedding", {}),
        "planner": _feedback_planner_payload(payload),
        "variant_retrieval": _feedback_variant_payload(payload),
        "error_code": payload.get("error", {}).get("code"),
    }
    if tool == "context_search_context":
        context_pack_feedback = _feedback_context_pack_payload(payload)
        if context_pack_feedback is not None:
            event["context_pack"] = context_pack_feedback
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
    groups = pack.get("groups")
    if type(groups) is not dict:
        groups = {}
    group_counts: dict[str, int] = {}
    for group in CONTEXT_GROUPS:
        group_items = groups.get(group)
        group_counts[group] = len(group_items) if type(group_items) is list else 0

    required_categories: set[str] = set()
    recommended_categories: set[str] = set()
    missing_evidence = pack.get("missing_evidence")
    if type(missing_evidence) is list:
        for evidence in missing_evidence:
            if type(evidence) is not dict:
                continue
            category = evidence.get("category")
            required = evidence.get("required")
            if type(category) is not str or type(required) is not bool:
                continue
            if required and category in ("results", *CONTEXT_GROUPS):
                required_categories.add(category)
            elif not required and category in CONTEXT_GROUPS:
                recommended_categories.add(category)
    recommended_categories.difference_update(required_categories)

    next_queries = pack.get("next_queries")
    raw_budget = pack.get("budget")
    if type(raw_budget) is not dict:
        raw_budget = {}
    budget_keys = (
        "max_results",
        "max_evidence_anchors",
        "max_items",
        "included_results",
        "included_evidence_anchors",
        "content_bytes",
    )
    budget: dict[str, int] = {}
    for key in budget_keys:
        value = raw_budget.get(key)
        if type(value) is int and value >= 0:
            budget[key] = value
    return {
        "status": status,
        "confidence": confidence,
        "item_count": len(items) if type(items) is list else 0,
        "group_counts": group_counts,
        "required_missing_categories": [
            category
            for category in ("results", *CONTEXT_GROUPS)
            if category in required_categories
        ],
        "recommended_missing_categories": [
            category
            for category in CONTEXT_GROUPS
            if category in recommended_categories
        ],
        "next_query_count": len(next_queries) if type(next_queries) is list else 0,
        "budget": budget,
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


def _disk_usage(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


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
