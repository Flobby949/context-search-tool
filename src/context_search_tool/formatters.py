from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from context_search_tool.context_pack import (
    ContextPack,
    ContextPackError,
    canonical_context_pack_bytes,
    context_pack_payload,
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    SemanticMatch,
)
from context_search_tool.retrieval import QueryBundle
from context_search_tool.retrieval_trace import (
    SOURCE_COUNT_KEYS,
    RetrievalTrace,
    RetrievalTraceError,
    retrieval_trace_payload,
)


def format_markdown(bundle: QueryBundle) -> str:
    planner_line = _planner_markdown_line(bundle.planner)
    lines = [
        "# Context Search Results",
        "",
        f"Query: {bundle.query}",
        f"Expanded tokens: {_format_list(bundle.expanded_tokens)}",
        *([planner_line, ""] if planner_line else [""]),
        "## Summary",
        "### Likely Entry Points",
        *_format_bullets(list(bundle.summary.entry_points)),
        "### Likely Implementation",
        *_format_bullets(list(bundle.summary.implementation)),
        "### Related Types",
        *_format_bullets(list(bundle.summary.related_types)),
        "### Possibly Legacy",
        *_format_bullets(list(bundle.summary.possibly_legacy)),
        "",
        "## Results",
    ]

    if not bundle.results:
        lines.append("No results.")
    else:
        for index, result in enumerate(bundle.results, start=1):
            fence = _markdown_fence(result.content)
            lines.extend(
                [
                    "",
                    (
                        f"### {index}. {result.file_path.as_posix()}:"
                        f"{result.start_line}-{result.end_line}"
                    ),
                    f"Score: {result.score}",
                    "",
                    "Reasons:",
                    *_format_bullets(result.reasons),
                    "",
                    "Score parts:",
                    *_format_score_parts(result.score_parts),
                    "",
                    "Snippet:",
                    fence,
                    result.content,
                    fence,
                ]
            )

    if bundle.evidence_anchors:
        lines.extend(
            [
                "",
                "## Evidence Anchors",
            ]
        )
        for index, anchor in enumerate(bundle.evidence_anchors, start=1):
            fence = _markdown_fence(anchor.content)
            lines.extend(
                [
                    "",
                    (
                        f"### {index}. {anchor.file_path.as_posix()}:"
                        f"{anchor.start_line}-{anchor.end_line}"
                    ),
                    f"Anchor kind: {anchor.anchor_kind}",
                    f"Score: {anchor.score}",
                    "",
                    "Reasons:",
                    *_format_bullets(list(anchor.reasons)),
                    "",
                    "Score parts:",
                    *_format_score_parts(anchor.score_parts),
                    "",
                    "Snippet:",
                    fence,
                    anchor.content,
                    fence,
                ]
            )

    lines.extend(
        [
            "",
            "## Follow-up Keywords",
            *_format_bullets(bundle.followup_keywords),
            "",
        ]
    )
    return "\n".join(lines)


def query_payload(bundle: QueryBundle) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
        "planner": _planner_payload(bundle.planner),
        "results": [
            {
                "file_path": result.file_path.as_posix(),
                "start_line": result.start_line,
                "end_line": result.end_line,
                "content": result.content,
                "score": result.score,
                "score_parts": result.score_parts,
                "reasons": result.reasons,
                "followup_keywords": result.followup_keywords,
                "semantic_matches": [
                    _semantic_match_payload(match)
                    for match in result.semantic_matches
                ],
            }
            for result in bundle.results
        ],
        "evidence_anchors": [
            _anchor_payload(anchor) for anchor in bundle.evidence_anchors
        ],
    }
    return payload


def format_json(bundle: QueryBundle) -> str:
    return json.dumps(query_payload(bundle), ensure_ascii=True, indent=2, sort_keys=True)


class TraceFormatError(RetrievalTraceError):
    pass


def trace_payload(
    repo: Path,
    query: str,
    trace: RetrievalTrace,
) -> dict[str, Any]:
    return {
        "ok": True,
        "repo": str(repo.resolve()),
        "query": query,
        "trace": retrieval_trace_payload(trace),
    }


def format_trace_json(envelope: dict[str, Any]) -> str:
    try:
        return json.dumps(
            envelope,
            ensure_ascii=True,
            indent=2,
            sort_keys=False,
            allow_nan=False,
        )
    except Exception as exc:
        raise TraceFormatError("Retrieval trace formatting failed") from exc


_TRACE_KEYS = {
    "schema_version",
    "outcome",
    "termination_reason",
    "duration_ms",
    "limits",
    "query",
    "source_counts",
    "stages",
    "final_selection_count",
    "final_selection_omitted_count",
    "final_selections",
}
_TRACE_LIMIT_KEYS = {
    "max_stages",
    "stage_top_k",
    "final_selection_top_k",
    "adjustment_top_k",
}
_TRACE_QUERY_KEYS = {
    "original_token_count",
    "expanded_token_count",
    "variant_retrieval_status",
    "variants",
    "planner",
}
_TRACE_VARIANT_KEYS = {"variant_id", "text", "source"}
_TRACE_PLANNER_KEYS = {
    "status",
    "provider",
    "model",
    "intent",
    "latency_ms",
    "discarded_hint_count",
}
_TRACE_DECISION_KEYS = (
    "selected_result",
    "selected_anchor",
    "duplicate_anchor",
    "result_limit",
    "anchor_limit",
)
_TRACE_STAGE_KEYS = {
    "name",
    "input_count",
    "output_count",
    "unique_output_count",
    "duration_ms",
    "source_counts",
    "decision_counts",
    "top_candidates",
}
_TRACE_CANDIDATE_KEYS = {
    "rank",
    "chunk_id",
    "file_path",
    "start_line",
    "end_line",
    "score",
    "sources",
    "variant_ids",
}
_TRACE_SELECTION_KEYS = {
    "rank",
    "selection_kind",
    "selection_reason",
    "file_path",
    "start_line",
    "end_line",
    "score",
    "origin_chunk_ids",
    "sources",
    "variant_ids",
    "rank_history",
    "adjustments",
    "adjustment_omitted_count",
    "reasons",
}


def _validated_trace(envelope: dict[str, Any]) -> dict[str, Any]:
    if type(envelope) is not dict or set(envelope) != {
        "ok",
        "repo",
        "query",
        "trace",
    }:
        raise ValueError("invalid trace envelope")
    trace = envelope["trace"]
    if type(trace) is not dict or set(trace) != _TRACE_KEYS:
        raise ValueError("invalid trace payload")
    if trace["schema_version"] != 1:
        raise ValueError("invalid trace schema")
    if (
        type(trace["limits"]) is not dict
        or set(trace["limits"]) != _TRACE_LIMIT_KEYS
    ):
        raise ValueError("invalid trace limits")
    query = trace["query"]
    if type(query) is not dict or set(query) != _TRACE_QUERY_KEYS:
        raise ValueError("invalid trace query")
    if type(query["variants"]) is not list or any(
        type(item) is not dict or set(item) != _TRACE_VARIANT_KEYS
        for item in query["variants"]
    ):
        raise ValueError("invalid trace variants")
    if (
        type(query["planner"]) is not dict
        or set(query["planner"]) != _TRACE_PLANNER_KEYS
    ):
        raise ValueError("invalid trace planner")
    if (
        type(trace["source_counts"]) is not dict
        or tuple(trace["source_counts"]) != SOURCE_COUNT_KEYS
    ):
        raise ValueError("invalid trace source counts")
    if type(trace["stages"]) is not list:
        raise ValueError("invalid trace stages")
    for stage in trace["stages"]:
        if type(stage) is not dict or set(stage) != _TRACE_STAGE_KEYS:
            raise ValueError("invalid trace stage")
        if (
            type(stage["source_counts"]) is not dict
            or type(stage["decision_counts"]) is not dict
            or type(stage["top_candidates"]) is not list
        ):
            raise ValueError("invalid trace stage details")
        stage_source_keys = tuple(stage["source_counts"])
        if stage_source_keys != tuple(
            key for key in SOURCE_COUNT_KEYS if key in stage["source_counts"]
        ):
            raise ValueError("invalid trace stage source counts")
        if tuple(stage["decision_counts"]) not in (
            (),
            _TRACE_DECISION_KEYS,
        ):
            raise ValueError("invalid trace decision counts")
        for candidate in stage["top_candidates"]:
            if (
                type(candidate) is not dict
                or set(candidate) != _TRACE_CANDIDATE_KEYS
            ):
                raise ValueError("invalid trace candidate")
    if type(trace["final_selections"]) is not list:
        raise ValueError("invalid trace selections")
    for selection in trace["final_selections"]:
        if type(selection) is not dict or set(selection) != _TRACE_SELECTION_KEYS:
            raise ValueError("invalid trace selection")
        if any(
            type(item) is not dict or set(item) != {"stage", "rank", "score"}
            for item in selection["rank_history"]
        ):
            raise ValueError("invalid trace rank history")
        if any(
            type(item) is not dict or set(item) != {"name", "value"}
            for item in selection["adjustments"]
        ):
            raise ValueError("invalid trace adjustments")
    json.dumps(trace, allow_nan=False)
    return trace


def format_trace_markdown(envelope: dict[str, Any]) -> str:
    try:
        trace = _validated_trace(envelope)
        query = trace["query"]
        planner = query["planner"]
        lines = [
            "# Retrieval Trace",
            "",
            f"Repository: {envelope['repo']}",
            f"Query: {envelope['query']}",
            f"Outcome: {trace['outcome']}",
            f"Termination: {trace['termination_reason']}",
            f"Duration: {trace['duration_ms']} ms",
            "",
            "## Query Understanding",
            "",
            (
                "Tokens: "
                f"{query['original_token_count']} original, "
                f"{query['expanded_token_count']} expanded"
            ),
            f"Variant retrieval: {query['variant_retrieval_status']}",
            (
                "Planner: "
                f"status={planner['status']}; "
                f"provider={planner['provider'] or '(none)'}; "
                f"model={planner['model'] or '(none)'}; "
                f"intent={planner['intent']}; "
                f"latency_ms={planner['latency_ms']}"
            ),
            "Variants:",
        ]
        lines.extend(
            (
                f"- {variant['variant_id']} ({variant['source']}): "
                f"{variant['text']}"
            )
            for variant in query["variants"]
        )
        lines.extend(["", "## Source Counts", ""])
        lines.extend(
            f"- {name}: {count}"
            for name, count in trace["source_counts"].items()
        )
        lines.extend(
            [
                "",
                "## Stages",
                "",
                "| stage | input | output | unique | duration ms |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for stage in trace["stages"]:
            lines.append(
                f"| {stage['name']} | {stage['input_count']} | "
                f"{stage['output_count']} | {stage['unique_output_count']} | "
                f"{stage['duration_ms']} |"
            )
        for stage in trace["stages"]:
            lines.extend(["", f"### {stage['name']}"])
            source_counts = ", ".join(
                f"{name}={count}"
                for name, count in stage["source_counts"].items()
            )
            decision_counts = ", ".join(
                f"{name}={count}"
                for name, count in stage["decision_counts"].items()
            )
            lines.append(f"- Source counts: {source_counts or '(none)'}")
            lines.append(f"- Decisions: {decision_counts or '(none)'}")
            for candidate in stage["top_candidates"]:
                sources = ", ".join(candidate["sources"]) or "(none)"
                variants = ", ".join(candidate["variant_ids"]) or "(none)"
                lines.append(
                    f"- {candidate['rank']}. {candidate['file_path']}:"
                    f"{candidate['start_line']}-{candidate['end_line']}; "
                    f"score={candidate['score']}; sources={sources}; "
                    f"variants={variants}"
                )
        lines.extend(
            [
                "",
                "## Final Selections",
                "",
                f"Selected: {trace['final_selection_count']}",
                f"Omitted from preview: {trace['final_selection_omitted_count']}",
            ]
        )
        for selection in trace["final_selections"]:
            lines.extend(
                [
                    "",
                    (
                        f"### {selection['rank']}. {selection['file_path']}:"
                        f"{selection['start_line']}-{selection['end_line']}"
                    ),
                    f"- Kind: {selection['selection_kind']}",
                    f"- Selection: {selection['selection_reason']}",
                    f"- Score: {selection['score']}",
                    "- Origin chunks: " + ", ".join(selection["origin_chunk_ids"]),
                    f"- Sources: {', '.join(selection['sources'])}",
                    f"- Variants: {', '.join(selection['variant_ids']) or '(none)'}",
                    "- Rank history: "
                    + ", ".join(
                        f"{item['stage']}#{item['rank']}={item['score']}"
                        for item in selection["rank_history"]
                    ),
                    (
                        "- Adjustments omitted from preview: "
                        f"{selection['adjustment_omitted_count']}"
                    ),
                    "- Adjustments: "
                    + (
                        ", ".join(
                            f"{item['name']}={item['value']}"
                            for item in selection["adjustments"]
                        )
                        or "(none)"
                    ),
                    "- Reasons: "
                    + (", ".join(selection["reasons"]) or "(none)"),
                ]
            )
        return "\n".join(lines) + "\n"
    except TraceFormatError:
        raise
    except Exception as exc:
        raise TraceFormatError("Retrieval trace formatting failed") from exc


def context_payload(
    repo: Path,
    bundle: QueryBundle,
    pack: ContextPack,
) -> dict[str, Any]:
    """Return the shared bounded context success envelope."""
    return {
        "ok": True,
        "repo": str(repo.resolve()),
        "query": bundle.query,
        "retrieval": {
            "result_count": len(bundle.results),
            "evidence_anchor_count": len(bundle.evidence_anchors),
            "planner_status": bundle.planner.status,
            "planner_intent": (
                bundle.planner.intent
                if bundle.planner.status == "ok"
                else "unknown"
            ),
        },
        "context_pack": context_pack_payload(pack),
    }


def format_context_json(envelope: dict[str, Any]) -> str:
    return json.dumps(
        envelope,
        ensure_ascii=True,
        indent=2,
        sort_keys=False,
        allow_nan=False,
    )


def format_context_markdown(envelope: dict[str, Any]) -> str:
    try:
        pack = _validated_context_pack_payload(envelope)
        retrieval = envelope["retrieval"]
        confidence = pack["confidence"]
        lines = [
            "# Context Pack",
            "",
            f"Repository: {envelope['repo']}",
            f"Query: {envelope['query']}",
            "",
            "## Status",
            f"- {pack['status']}",
            "",
            "## Confidence",
            f"- Level: {confidence['level']}",
            *_format_bullets(confidence["reasons"]),
            "",
            "## Retrieval",
            f"- Results: {retrieval['result_count']}",
            f"- Evidence anchors: {retrieval['evidence_anchor_count']}",
            f"- Planner status: {retrieval['planner_status']}",
            f"- Planner intent: {retrieval['planner_intent']}",
            "",
            "## Evidence Needs",
        ]

        if not pack["evidence_needs"]:
            lines.append("- (none)")
        else:
            for need in pack["evidence_needs"]:
                label = "Required" if need["required"] else "Recommended"
                subjects = ", ".join(need["subject_terms"]) or "(none)"
                lines.append(
                    f"- {label}: {need['category']} ({need['id']}); "
                    f"subjects: {subjects}; provenance: {need['provenance']}"
                )

        lines.extend(["", "## Read First"])
        items_by_id = {item["id"]: item for item in pack["items"]}
        if not pack["reading_order"]:
            lines.append("- (none)")
        else:
            for item_id in pack["reading_order"]:
                item = items_by_id[item_id]
                lines.extend(
                    [
                        "",
                        f"### {item_id} — {item['file_path']}",
                        f"- Group: {item['group']}",
                        f"- Role: {item['role']}",
                        f"- Classification: {item['classification_basis']}",
                        f"- Source: {item['source_kind']}",
                    ]
                )
                if item["reasons"]:
                    lines.extend(["", "Reasons:", *_format_bullets(item["reasons"])])
                for excerpt in item["excerpts"]:
                    fence = _markdown_fence(excerpt["content"])
                    lines.extend(
                        [
                            "",
                            (
                                f"#### Lines {excerpt['start_line']}-"
                                f"{excerpt['end_line']}"
                            ),
                            fence,
                            excerpt["content"],
                            fence,
                        ]
                    )

        lines.extend(["", "## Missing Evidence"])
        if not pack["missing_evidence"]:
            lines.append("- (none)")
        else:
            for evidence in pack["missing_evidence"]:
                label = "Required" if evidence["required"] else "Recommended"
                lines.append(
                    f"- {label}: {evidence['category']} "
                    f"({evidence['need_id']}) — {evidence['reason']}"
                )

        lines.extend(["", "## Omissions"])
        if not pack["omissions"]:
            lines.append("- (none)")
        else:
            for omission in pack["omissions"]:
                lines.append(
                    f"- {omission['file_path']} [{omission['group']}] — "
                    f"{omission['reason']}"
                )

        lines.extend(["", "## Next Queries"])
        if not pack["next_queries"]:
            lines.append("- (none)")
        else:
            for suggestion in pack["next_queries"]:
                lines.extend(
                    [
                        f"- Purpose: {suggestion['purpose']}",
                        f"  Query: {suggestion['query']}",
                        f"  Need: {suggestion['need_id']}",
                    ]
                )

        budget = pack["budget"]
        lines.extend(
            [
                "",
                "## Budget",
                f"- Max items: {budget['max_items']}",
                f"- Included items: {budget['included_items']}",
                f"- Included excerpts: {budget['included_excerpts']}",
                f"- Content bytes: {budget['content_bytes']}",
                (
                    "- Canonical JSON pack bytes: "
                    f"{budget['pack_bytes']} / {budget['max_pack_bytes']}"
                ),
                f"- Truncated items: {budget['truncated_item_count']}",
                f"- Omitted items: {budget['omitted_item_count']}",
                f"- Budget exhausted: {str(budget['budget_exhausted']).lower()}",
                "",
            ]
        )
        return "\n".join(lines)
    except ContextPackError:
        raise
    except Exception as exc:
        raise ContextPackError(
            "context_failed",
            "Context pack construction failed",
        ) from exc


def _validated_context_pack_payload(
    envelope: dict[str, Any],
) -> dict[str, Any]:
    if type(envelope) is not dict or set(envelope) != {
        "ok",
        "repo",
        "query",
        "retrieval",
        "context_pack",
    }:
        raise ContextPackError("context_failed", "Context pack construction failed")
    if envelope.get("ok") is not True:
        raise ContextPackError("context_failed", "Context pack construction failed")
    encoded = canonical_context_pack_bytes(envelope["context_pack"])
    return json.loads(encoded)


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


def _planner_payload(plan: QueryPlan) -> dict[str, Any]:
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


def _planner_markdown_line(plan: QueryPlan) -> str:
    if plan.status != "ok":
        return ""
    hints = [*plan.symbol_hints[:2], *plan.grep_keywords[:2]][:3]
    if not hints:
        return f"Query expanded by {plan.model}."
    hint_text = ", ".join(hints)
    total_hints = len(plan.symbol_hints) + len(plan.grep_keywords)
    if total_hints > 3:
        hint_text += f", ... (+{total_hints - 3} more)"
    return f"Query expanded by {plan.model}: {hint_text}"


def _format_list(items: list[str]) -> str:
    return ", ".join(items) if items else "(none)"


def _format_bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- (none)"]


def _markdown_fence(content: str) -> str:
    longest_run = 0
    current_run = 0
    for char in content:
        if char == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return "`" * max(3, longest_run + 1)


def _format_score_parts(score_parts: dict[str, float]) -> list[str]:
    return [
        f"- {key}: {score_parts[key]}"
        for key in sorted(score_parts)
    ] or ["- (none)"]


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
