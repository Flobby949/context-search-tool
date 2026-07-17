from __future__ import annotations

from context_search_tool.models import SemanticMatch
from context_search_tool.retrieval_core import relation_policy


def bounded_score(score: float) -> float:
    return min(max(score, 0.0), 1.0)


def merge_score_parts(
    left: dict[str, float],
    right: dict[str, float],
) -> dict[str, float]:
    merged = dict(left)
    for key, value in right.items():
        if key == "penalty" or key.endswith("_penalty"):
            merged[key] = min(merged.get(key, value), value)
        else:
            merged[key] = max(merged.get(key, value), value)
    graph_choices = [
        (value, key, parts)
        for parts in (left, right)
        for key in relation_policy.GRAPH_SCORE_KEYS
        if (value := parts.get(key, 0.0)) > 0.0
    ]
    if graph_choices:
        graph_priority = {
            key: priority
            for priority, key in enumerate(relation_policy.GRAPH_SCORE_KEYS)
        }
        _value, graph_key, graph_parts = min(
            graph_choices,
            key=lambda item: (
                -item[0],
                graph_priority[item[1]],
                0 if item[2].get("graph_seed_original", 0.0) > 0.0 else 1,
            ),
        )
        for key in (
            *relation_policy.GRAPH_SCORE_KEYS,
            "graph_seed_original",
            "graph_seed_planner",
        ):
            merged.pop(key, None)
        merged[graph_key] = _value
        merged["resolved_relation"] = 1.0
        if graph_parts.get("graph_seed_original", 0.0) > 0.0:
            merged["graph_seed_original"] = 1.0
        elif graph_parts.get("graph_seed_planner", 0.0) > 0.0:
            merged["graph_seed_planner"] = 1.0
    return merged


def merge_semantic_matches(
    left: list[SemanticMatch],
    right: list[SemanticMatch],
) -> list[SemanticMatch]:
    by_variant: dict[str, SemanticMatch] = {}
    for match in [*left, *right]:
        existing = by_variant.get(match.variant_id)
        if existing is None or match.score > existing.score:
            by_variant[match.variant_id] = match
    return sorted(by_variant.values(), key=_semantic_match_sort_key)


def _semantic_match_sort_key(match: SemanticMatch) -> tuple[int, int, str]:
    if match.variant_id == "original":
        return (0, 0, "")
    prefix, separator, raw_index = match.variant_id.partition(":")
    if prefix == "planner" and separator and raw_index.isdigit():
        return (1, int(raw_index), "")
    return (2, 0, match.variant_id)
