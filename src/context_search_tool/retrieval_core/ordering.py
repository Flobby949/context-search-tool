from __future__ import annotations


RERANK_SORT_DECIMALS = 3


def dedupe_lowered(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def ordered_unique_preserving_case(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(value)
    return ordered
