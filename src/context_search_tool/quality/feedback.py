from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def summarize_feedback_log(
    path: Path,
    include_query_terms: bool = False,
    include_query_examples: bool = False,
    max_examples: int = 10,
) -> dict[str, Any]:
    total_calls = 0
    ok_calls = 0
    empty_result_calls = 0
    planner_status: Counter[str] = Counter()
    embedding: Counter[str] = Counter()
    error_codes: Counter[str] = Counter()
    top_scores: list[float] = []
    query_terms: Counter[str] = Counter()
    queries: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        total_calls += 1

        if event.get("ok") is True:
            ok_calls += 1
        if event.get("result_count") == 0:
            empty_result_calls += 1

        planner = event.get("planner")
        if isinstance(planner, dict):
            status = planner.get("status")
            if status:
                planner_status[str(status)] += 1

        event_embedding = event.get("embedding")
        if isinstance(event_embedding, dict):
            provider = event_embedding.get("provider")
            model = event_embedding.get("model")
            if provider and model:
                embedding[f"{provider}/{model}"] += 1
            elif provider or model:
                embedding[str(provider or model)] += 1

        error_code = event.get("error_code")
        if error_code:
            error_codes[str(error_code)] += 1

        top_score = event.get("top_score")
        if isinstance(top_score, (int, float)) and not isinstance(top_score, bool):
            top_scores.append(float(top_score))

        query = event.get("query")
        if include_query_terms and isinstance(query, str):
            query_terms.update(
                query.lower().replace("/", " ").replace("_", " ").split()
            )
        if (
            include_query_examples
            and isinstance(query, str)
            and len(queries) < max_examples
        ):
            queries.append(query)

    summary: dict[str, Any] = {
        "total_calls": total_calls,
        "ok_calls": ok_calls,
        "error_calls": total_calls - ok_calls,
        "empty_result_calls": empty_result_calls,
        "planner_status": dict(planner_status),
        "embedding": dict(embedding),
        "error_codes": dict(error_codes),
    }
    if top_scores:
        summary["top_score"] = {
            "min": min(top_scores),
            "max": max(top_scores),
            "avg": sum(top_scores) / len(top_scores),
        }
    if include_query_terms:
        summary["query_terms"] = dict(query_terms.most_common(25))
    if include_query_examples:
        summary["queries"] = queries
    return summary
