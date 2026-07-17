from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    ExplorationGoalRecord,
    ExplorationLimits,
    ExplorationProbe,
    ExplorationRound,
    ExplorationTrace,
    ExplorationTraceError,
    FinalEvidence,
    RetrievalTrace,
    RetrievalTraceError,
    exploration_trace_payload,
    retrieval_trace_payload,
)

if TYPE_CHECKING:
    from context_search_tool.exploration.models import ExploredContext


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


_EXPLORE_KEYS = (
    "ok",
    "repo",
    "query",
    "retrieval",
    "context_pack",
    "trace",
)
_EXPLORE_RETRIEVAL_KEYS = (
    "initial_result_count",
    "initial_evidence_anchor_count",
    "fused_result_count",
    "fused_evidence_anchor_count",
    "planner_status",
    "planner_intent",
    "requested_final_top_k",
    "effective_initial_top_k",
)
_EXPLORATION_TRACE_KEYS = (
    "schema_version",
    "mode",
    "outcome",
    "termination_reason",
    "duration_ms",
    "limits",
    "initial_evidence_need_count",
    "candidate_goal_count",
    "retained_goal_count",
    "omitted_goal_count",
    "initial_satisfied_goal_count",
    "final_satisfied_goal_count",
    "planned_probe_count",
    "executed_probe_count",
    "stale_skipped_probe_count",
    "unexecuted_probe_count",
    "retrieval_call_count",
    "goals",
    "rounds",
    "final_evidence_count",
    "final_evidence_omitted_count",
    "final_evidence",
)
_EXPLORATION_LIMIT_KEYS = (
    "max_rounds",
    "max_followup_probes",
    "max_retrieval_calls",
    "max_planned_probes",
    "max_goals",
    "max_probe_code_points",
    "max_seed_paths",
    "max_frontend_import_header_bytes",
    "max_frontend_import_paths",
    "effective_initial_top_k",
    "followup_top_k",
    "max_fused_results",
    "max_fused_anchors",
    "final_evidence_top_k",
)
_EXPLORATION_GOAL_KEYS = (
    "id",
    "kind",
    "category",
    "accepted_roles",
    "required",
    "provenance",
    "initially_satisfied",
    "finally_satisfied",
)
_EXPLORATION_ROUND_KEYS = (
    "round_index",
    "kind",
    "duration_ms",
    "input_path_count",
    "output_path_count",
    "novel_path_count",
    "duplicate_path_count",
    "newly_satisfied_goal_ids",
    "probes",
)
_EXPLORATION_PROBE_KEYS = (
    "id",
    "query",
    "purpose",
    "source",
    "goal_ids",
    "seed_paths",
    "retrieval_outcome",
    "retrieval_termination_reason",
    "duration_ms",
    "result_count",
    "evidence_anchor_count",
    "unique_path_count",
    "duplicate_path_count",
    "novel_path_count",
    "newly_satisfied_goal_ids",
    "source_counts",
    "final_selection_count",
)
_EXPLORATION_EVIDENCE_KEYS = (
    "item_id",
    "file_path",
    "source_round",
    "probe_id",
    "probe_rank",
    "goal_ids",
    "selection_reason",
)
_PLANNER_STATUSES = {"disabled", "ok", "fallback"}
_PLANNER_INTENTS = {
    "feature_lookup",
    "endpoint_lookup",
    "bug_trace",
    "data_flow",
    "symbol_lookup",
    "unknown",
}


def explore_payload(
    repo: Path,
    query: str,
    explored: ExploredContext,
    *,
    requested_final_top_k: int | None,
) -> dict[str, Any]:
    """Return the shared bounded controlled-exploration success envelope."""
    initial = explored.initial_bundle
    fused = explored.fused_bundle
    trace = explored.trace
    if initial.query != query or fused.query != query:
        raise ExplorationTraceError("exploration query mismatch")
    envelope = {
        "ok": True,
        "repo": str(repo.resolve()),
        "query": query,
        "retrieval": {
            "initial_result_count": len(initial.results),
            "initial_evidence_anchor_count": len(initial.evidence_anchors),
            "fused_result_count": len(fused.results),
            "fused_evidence_anchor_count": len(fused.evidence_anchors),
            "planner_status": initial.planner.status,
            "planner_intent": initial.planner.intent,
            "requested_final_top_k": requested_final_top_k,
            "effective_initial_top_k": trace.limits.effective_initial_top_k,
        },
        "context_pack": context_pack_payload(explored.final_pack),
        "trace": exploration_trace_payload(trace),
    }
    return _validated_explore_payload(envelope)


def format_explore_json(envelope: dict[str, Any]) -> str:
    validated = _validated_explore_payload(envelope)
    return json.dumps(
        validated,
        ensure_ascii=True,
        indent=2,
        sort_keys=False,
        allow_nan=False,
    )


def format_explore_markdown(envelope: dict[str, Any]) -> str:
    validated = _validated_explore_payload(envelope)
    trace = validated["trace"]
    retrieval = validated["retrieval"]
    lines = [
        "# Controlled Exploration",
        "",
        f"Repository: {validated['repo']}",
        f"Query: {validated['query']}",
        "",
        "## Exploration",
        f"- Outcome: {trace['outcome']}",
        f"- Termination: {trace['termination_reason']}",
        f"- Retrieval calls: {trace['retrieval_call_count']}",
        f"- Executed probes: {trace['executed_probe_count']}",
        f"- Duration: {trace['duration_ms']} ms",
    ]
    if trace["outcome"] == "partial":
        lines.extend(
            [
                "",
                "> Warning: exploration is partial; the final ContextPack "
                "contains the best validated evidence recovered so far.",
            ]
        )

    lines.extend(
        [
            "",
            "## Attempted Follow-up Probes",
            "",
            "| probe | source | outcome | paths | novel | gained goals | duration ms |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    followup_probes = [
        probe
        for round_record in trace["rounds"]
        if round_record["kind"] == "followup"
        for probe in round_record["probes"]
    ]
    if not followup_probes:
        lines.append("| (none) | - | - | 0 | 0 | 0 | 0 |")
    else:
        for probe in followup_probes:
            lines.append(
                f"| {probe['id']} | {probe['source']} | "
                f"{probe['retrieval_outcome']}/"
                f"{probe['retrieval_termination_reason']} | "
                f"{probe['unique_path_count']} | {probe['novel_path_count']} | "
                f"{len(probe['newly_satisfied_goal_ids'])} | "
                f"{probe['duration_ms']} |"
            )

    lines.extend(
        [
            "",
            "## Goal Gain",
            f"- Initially satisfied: {trace['initial_satisfied_goal_count']}",
            f"- Finally satisfied: {trace['final_satisfied_goal_count']}",
            f"- Retained goals: {trace['retained_goal_count']}",
        ]
    )
    gained = [
        goal
        for goal in trace["goals"]
        if not goal["initially_satisfied"] and goal["finally_satisfied"]
    ]
    if gained:
        for goal in gained:
            lines.append(
                f"- Gained {goal['id']}: {goal['category']} "
                f"({goal['provenance']})"
            )
    else:
        lines.append("- Newly satisfied: (none)")

    lines.extend(["", "## Final Evidence Provenance"])
    if not trace["final_evidence"]:
        lines.append("- (none)")
    else:
        for item in trace["final_evidence"]:
            goals = ", ".join(item["goal_ids"]) or "(none)"
            lines.append(
                f"- {item['item_id']} — {item['file_path']}; "
                f"round={item['source_round']}; probe={item['probe_id']}; "
                f"rank={item['probe_rank']}; goals={goals}; "
                f"selection={item['selection_reason']}"
            )
    if trace["final_evidence_omitted_count"]:
        lines.append(
            "- Omitted from provenance preview: "
            f"{trace['final_evidence_omitted_count']}"
        )

    context_envelope = {
        "ok": True,
        "repo": validated["repo"],
        "query": validated["query"],
        "retrieval": {
            "result_count": retrieval["fused_result_count"],
            "evidence_anchor_count": retrieval["fused_evidence_anchor_count"],
            "planner_status": retrieval["planner_status"],
            "planner_intent": retrieval["planner_intent"],
        },
        "context_pack": validated["context_pack"],
    }
    lines.extend(["", format_context_markdown(context_envelope)])
    return "\n".join(lines)


def _validated_explore_payload(
    envelope: dict[str, Any],
) -> dict[str, Any]:
    _require_ordered_dict(envelope, _EXPLORE_KEYS, "explore envelope")
    if envelope["ok"] is not True:
        raise ExplorationTraceError("invalid explore envelope")
    repo = envelope["repo"]
    query = envelope["query"]
    if type(repo) is not str or not repo or not Path(repo).is_absolute():
        raise ExplorationTraceError("invalid explore repository")
    if type(query) is not str:
        raise ExplorationTraceError("invalid explore query")

    retrieval = envelope["retrieval"]
    _require_ordered_dict(
        retrieval,
        _EXPLORE_RETRIEVAL_KEYS,
        "explore retrieval",
    )
    for key in _EXPLORE_RETRIEVAL_KEYS[:4]:
        _non_negative_payload_int(retrieval[key], key)
    if retrieval["planner_status"] not in _PLANNER_STATUSES:
        raise ExplorationTraceError("invalid explore planner status")
    if retrieval["planner_intent"] not in _PLANNER_INTENTS:
        raise ExplorationTraceError("invalid explore planner intent")
    requested = retrieval["requested_final_top_k"]
    if requested is not None and (type(requested) is not int or requested < 1):
        raise ExplorationTraceError("invalid requested final top-k")
    effective = retrieval["effective_initial_top_k"]
    if type(effective) is not int or not 1 <= effective <= 12:
        raise ExplorationTraceError("invalid effective initial top-k")

    pack_payload = envelope["context_pack"]
    encoded_pack = canonical_context_pack_bytes(pack_payload)
    normalized_pack = json.loads(encoded_pack)
    if pack_payload != normalized_pack:
        raise ContextPackError(
            "context_failed",
            "Context pack construction failed",
        )
    trace = _exploration_trace_from_payload(envelope["trace"])
    normalized_trace = exploration_trace_payload(trace)
    if envelope["trace"] != normalized_trace:
        raise ExplorationTraceError("invalid exploration trace payload")

    initial_probe = normalized_trace["rounds"][0]["probes"][0]
    if (
        retrieval["initial_result_count"] != initial_probe["result_count"]
        or retrieval["initial_evidence_anchor_count"]
        != initial_probe["evidence_anchor_count"]
        or retrieval["effective_initial_top_k"]
        != normalized_trace["limits"]["effective_initial_top_k"]
        or len(normalized_pack["items"])
        != normalized_trace["final_evidence_count"]
        or len(normalized_pack["items"])
        > retrieval["fused_result_count"]
        + retrieval["fused_evidence_anchor_count"]
        or retrieval["fused_result_count"]
        > normalized_trace["limits"]["max_fused_results"]
        or retrieval["fused_evidence_anchor_count"]
        > normalized_trace["limits"]["max_fused_anchors"]
        or retrieval["fused_result_count"]
        + retrieval["fused_evidence_anchor_count"]
        != normalized_trace["rounds"][-1]["output_path_count"]
    ):
        raise ExplorationTraceError("inconsistent explore envelope")

    return {
        "ok": True,
        "repo": repo,
        "query": query,
        "retrieval": dict(retrieval),
        "context_pack": dict(pack_payload),
        "trace": normalized_trace,
    }


def _exploration_trace_from_payload(payload: object) -> ExplorationTrace:
    _require_ordered_dict(payload, _EXPLORATION_TRACE_KEYS, "exploration trace")
    raw_limits = payload["limits"]
    _require_ordered_dict(
        raw_limits,
        _EXPLORATION_LIMIT_KEYS,
        "exploration limits",
    )
    limits = ExplorationLimits(**raw_limits)
    goals = tuple(
        _exploration_goal_from_payload(item)
        for item in _payload_list(payload["goals"], "exploration goals")
    )
    rounds = tuple(
        _exploration_round_from_payload(item)
        for item in _payload_list(payload["rounds"], "exploration rounds")
    )
    evidence = tuple(
        _exploration_evidence_from_payload(item)
        for item in _payload_list(
            payload["final_evidence"],
            "final exploration evidence",
        )
    )
    values = {
        key: payload[key]
        for key in _EXPLORATION_TRACE_KEYS
        if key not in {"limits", "goals", "rounds", "final_evidence"}
    }
    return ExplorationTrace(
        **values,
        limits=limits,
        goals=goals,
        rounds=rounds,
        final_evidence=evidence,
    )


def _exploration_goal_from_payload(payload: object) -> ExplorationGoalRecord:
    _require_ordered_dict(payload, _EXPLORATION_GOAL_KEYS, "exploration goal")
    return ExplorationGoalRecord(
        id=payload["id"],
        kind=payload["kind"],
        category=payload["category"],
        accepted_roles=_payload_string_tuple(
            payload["accepted_roles"],
            "accepted roles",
        ),
        required=payload["required"],
        provenance=payload["provenance"],
        initially_satisfied=payload["initially_satisfied"],
        finally_satisfied=payload["finally_satisfied"],
    )


def _exploration_round_from_payload(payload: object) -> ExplorationRound:
    _require_ordered_dict(payload, _EXPLORATION_ROUND_KEYS, "exploration round")
    return ExplorationRound(
        round_index=payload["round_index"],
        kind=payload["kind"],
        duration_ms=payload["duration_ms"],
        input_path_count=payload["input_path_count"],
        output_path_count=payload["output_path_count"],
        novel_path_count=payload["novel_path_count"],
        duplicate_path_count=payload["duplicate_path_count"],
        newly_satisfied_goal_ids=_payload_string_tuple(
            payload["newly_satisfied_goal_ids"],
            "round goal gain",
        ),
        probes=tuple(
            _exploration_probe_from_payload(item)
            for item in _payload_list(payload["probes"], "exploration probes")
        ),
    )


def _exploration_probe_from_payload(payload: object) -> ExplorationProbe:
    _require_ordered_dict(payload, _EXPLORATION_PROBE_KEYS, "exploration probe")
    raw_counts = payload["source_counts"]
    _require_ordered_dict(raw_counts, SOURCE_COUNT_KEYS, "probe source counts")
    return ExplorationProbe(
        id=payload["id"],
        query=payload["query"],
        purpose=payload["purpose"],
        source=payload["source"],
        goal_ids=_payload_string_tuple(payload["goal_ids"], "probe goals"),
        seed_paths=_payload_string_tuple(payload["seed_paths"], "seed paths"),
        retrieval_outcome=payload["retrieval_outcome"],
        retrieval_termination_reason=payload["retrieval_termination_reason"],
        duration_ms=payload["duration_ms"],
        result_count=payload["result_count"],
        evidence_anchor_count=payload["evidence_anchor_count"],
        unique_path_count=payload["unique_path_count"],
        duplicate_path_count=payload["duplicate_path_count"],
        novel_path_count=payload["novel_path_count"],
        newly_satisfied_goal_ids=_payload_string_tuple(
            payload["newly_satisfied_goal_ids"],
            "probe goal gain",
        ),
        source_counts=tuple(raw_counts.items()),
        final_selection_count=payload["final_selection_count"],
    )


def _exploration_evidence_from_payload(payload: object) -> FinalEvidence:
    _require_ordered_dict(
        payload,
        _EXPLORATION_EVIDENCE_KEYS,
        "final exploration evidence",
    )
    return FinalEvidence(
        item_id=payload["item_id"],
        file_path=payload["file_path"],
        source_round=payload["source_round"],
        probe_id=payload["probe_id"],
        probe_rank=payload["probe_rank"],
        goal_ids=_payload_string_tuple(payload["goal_ids"], "evidence goals"),
        selection_reason=payload["selection_reason"],
    )


def _require_ordered_dict(
    value: object,
    keys: tuple[str, ...],
    label: str,
) -> None:
    if type(value) is not dict or tuple(value) != keys:
        raise ExplorationTraceError(f"invalid {label}")


def _payload_list(value: object, label: str) -> list[Any]:
    if type(value) is not list:
        raise ExplorationTraceError(f"invalid {label}")
    return value


def _payload_string_tuple(value: object, label: str) -> tuple[str, ...]:
    values = _payload_list(value, label)
    if any(type(item) is not str for item in values):
        raise ExplorationTraceError(f"invalid {label}")
    return tuple(values)


def _non_negative_payload_int(value: object, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ExplorationTraceError(f"invalid {label}")


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
