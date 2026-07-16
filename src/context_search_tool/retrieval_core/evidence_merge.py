from __future__ import annotations

from context_search_tool.models import SemanticMatch


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
