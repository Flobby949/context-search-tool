from __future__ import annotations

import hashlib
from typing import Any, Protocol

from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan

PROMPT_VERSION = "qwen-query-planner-v1"

ALLOWED_INTENTS = {
    "feature_lookup",
    "endpoint_lookup",
    "bug_trace",
    "data_flow",
    "symbol_lookup",
    "unknown",
}

SYSTEM_PROMPT = """You rewrite code-search queries. Return only compact JSON matching the schema.
Do not explain. Do not guess file paths. Prefer identifiers and English code terms.

DO NOT:
- Add file paths such as src/main/java/com/example/Foo.java.
- Add framework annotations such as @Autowired, @Service, or @RequestMapping.
- Add implementation details such as extends BaseController.
- Repeat the original query verbatim in rewritten_queries.
- Return prose or Markdown.

DO:
- Add English code terms for Chinese business words.
- Use likely class or method names only when strongly implied.
- Keep keywords concise."""


class QueryPlanner(Protocol):
    def plan(self, query: str) -> QueryPlan:
        ...


def prompt_hash() -> str:
    digest = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def disabled_plan(query: str) -> QueryPlan:
    return QueryPlan(original_query=query, status="disabled")


def fallback_plan(
    query: str,
    provider: str,
    model: str,
    latency_ms: int | None,
    error: str,
) -> QueryPlan:
    return QueryPlan(
        original_query=query,
        status="fallback",
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        latency_ms=latency_ms,
        error=error,
    )


def clean_planner_payload(
    original_query: str,
    payload: dict[str, Any],
    config: QueryPlannerConfig,
    provider: str,
    model: str,
    latency_ms: int | None,
) -> QueryPlan:
    try:
        rewritten_queries = _clean_string_list(
            payload,
            "rewritten_queries",
            config.max_rewritten_queries,
        )
        grep_keywords = _clean_string_list(
            payload,
            "grep_keywords",
            config.max_keywords,
        )
        symbol_hints = _clean_string_list(
            payload,
            "symbol_hints",
            config.max_symbol_hints,
        )
    except ValueError as exc:
        return fallback_plan(
            original_query,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            error=str(exc),
        )

    raw_intent = payload.get("intent", "unknown")
    intent = (
        raw_intent
        if isinstance(raw_intent, str) and raw_intent in ALLOWED_INTENTS
        else "unknown"
    )
    return QueryPlan(
        original_query=original_query,
        rewritten_queries=rewritten_queries,
        grep_keywords=grep_keywords,
        symbol_hints=symbol_hints,
        intent=intent,
        status="ok",
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        latency_ms=latency_ms,
    )


def _clean_string_list(payload: dict[str, Any], key: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain only strings")
        stripped = item.strip()
        normalized = stripped.lower()
        if not normalized or normalized in seen:
            continue
        cleaned.append(stripped)
        seen.add(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned
