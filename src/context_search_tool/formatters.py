from __future__ import annotations

import json
from typing import Any

from context_search_tool.context_pack import (
    INVALID_REFERENCE_ERROR,
    ContextPack,
    ContextPackError,
    context_pack_payload,
    resolve_context_item,
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    SemanticMatch,
)
from context_search_tool.retrieval import QueryBundle


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


def format_context_json(
    raw_payload: dict[str, Any],
    bundle: QueryBundle,
    pack: ContextPack,
) -> str:
    payload = dict(raw_payload)
    payload["context_pack"] = context_pack_payload(bundle, pack)
    return json.dumps(
        payload,
        ensure_ascii=True,
        indent=2,
        sort_keys=False,
        allow_nan=False,
    )


def format_context_markdown(bundle: QueryBundle, pack: ContextPack) -> str:
    context_pack_payload(bundle, pack)
    planner_line = _planner_markdown_line(bundle.planner)
    lines = [
        "# Context Pack",
        "",
        f"Query: {bundle.query}",
        f"Status: {pack.status}",
        f"Confidence: {pack.confidence.level}",
        f"Planner: {bundle.planner.status}",
        *([planner_line] if planner_line else []),
        "",
        "## Read First",
    ]

    items_by_id = {item.id: item for item in pack.items}
    if not pack.reading_order:
        lines.append("- (none)")
    else:
        for item_id in pack.reading_order:
            item = items_by_id.get(item_id)
            if item is None:
                raise ContextPackError(INVALID_REFERENCE_ERROR)
            source = resolve_context_item(bundle, item)
            fence = _markdown_fence(source.content)
            lines.extend(
                [
                    "",
                    (
                        f"### {item.id} - {item.file_path}:"
                        f"{item.start_line}-{item.end_line}"
                    ),
                    f"Group: {item.group}",
                    f"Role: {item.role}",
                    f"Source: {item.source}",
                    "",
                    "Reasons:",
                    *_format_bullets(list(source.reasons)),
                    "",
                    "Snippet:",
                    fence,
                    source.content,
                    fence,
                ]
            )

    lines.extend(["", "## Missing Evidence"])
    if not pack.missing_evidence:
        lines.append("- (none)")
    else:
        for evidence in pack.missing_evidence:
            label = "Required" if evidence.required else "Recommended"
            lines.append(f"- {label}: {evidence.category} — {evidence.reason}")

    lines.extend(["", "## Next Queries"])
    if not pack.next_queries:
        lines.append("- (none)")
    else:
        for suggestion in pack.next_queries:
            lines.extend(
                [
                    f"- Purpose: {suggestion.purpose}",
                    f"  Query: {suggestion.query}",
                    f"  Reason: {suggestion.reason}",
                ]
            )

    budget = pack.budget
    lines.extend(
        [
            "",
            "## Budget",
            f"- max_results: {budget.max_results}",
            f"- max_evidence_anchors: {budget.max_evidence_anchors}",
            f"- max_items: {budget.max_items}",
            f"- included_results: {budget.included_results}",
            (
                "- included_evidence_anchors: "
                f"{budget.included_evidence_anchors}"
            ),
            f"- content_bytes: {budget.content_bytes}",
            f"- context_before_lines: {budget.context_before_lines}",
            f"- context_after_lines: {budget.context_after_lines}",
            f"- full_file: {budget.full_file}",
            f"- max_full_file_bytes: {budget.max_full_file_bytes}",
            "",
        ]
    )
    return "\n".join(lines)


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
