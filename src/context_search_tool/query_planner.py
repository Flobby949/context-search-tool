from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

import requests

from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan
from context_search_tool.tokenizer import tokenize_query

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


class DisabledQueryPlanner:
    def plan(self, query: str) -> QueryPlan:
        return disabled_plan(query)


class OllamaQueryPlanner:
    def __init__(
        self,
        config: QueryPlannerConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.trust_env = config.use_system_proxy

    def plan(self, query: str) -> QueryPlan:
        start = time.perf_counter()
        try:
            response = self.session.post(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.config.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(
                                _user_payload(query, self.config),
                                ensure_ascii=False,
                            ),
                        },
                    ],
                },
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
            if not isinstance(response_payload, dict):
                return self._fallback(
                    query,
                    start,
                    "planner response must be an object",
                )
            message = response_payload.get("message", {})
            if not isinstance(message, dict):
                return self._fallback(
                    query,
                    start,
                    "planner response message must be an object",
                )
            raw_content = message.get("content", "")
            if not isinstance(raw_content, str):
                return self._fallback(
                    query,
                    start,
                    "planner response content must be a string",
                )
            try:
                payload = json.loads(raw_content)
            except json.JSONDecodeError:
                return self._fallback(query, start, "invalid planner JSON")
            if not isinstance(payload, dict):
                return self._fallback(query, start, "planner JSON must be an object")
            return clean_planner_payload(
                original_query=query,
                payload=payload,
                config=self.config,
                provider=self.config.provider,
                model=self.config.model,
                latency_ms=_elapsed_ms(start),
            )
        except requests.Timeout:
            return self._fallback(
                query,
                start,
                f"planner timed out after {self.config.timeout_seconds:g} seconds",
            )
        except requests.HTTPError as exc:
            return self._fallback(query, start, f"planner HTTP error: {exc}")
        except requests.RequestException as exc:
            return self._fallback(query, start, f"planner request failed: {exc}")

    def _fallback(self, query: str, start: float, error: str) -> QueryPlan:
        return fallback_plan(
            query,
            provider=self.config.provider,
            model=self.config.model,
            latency_ms=_elapsed_ms(start),
            error=error,
        )


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


def planner_from_config(config: QueryPlannerConfig) -> QueryPlanner:
    if not config.enabled:
        return DisabledQueryPlanner()
    if config.provider != "ollama":
        return DisabledQueryPlanner()
    return OllamaQueryPlanner(config)


def expand_query_plan_tokens(query: str, plan: QueryPlan) -> list[str]:
    original_tokens = _original_query_tokens(query)
    if plan.status != "ok":
        return original_tokens
    expanded: list[str] = []
    for rewritten_query in plan.rewritten_queries:
        expanded.extend(tokenize_query(rewritten_query))
    expanded.extend(plan.grep_keywords)
    expanded.extend(plan.symbol_hints)
    return _dedupe([*original_tokens, *expanded])


def planner_hint_tokens(
    original_tokens: list[str],
    expanded_tokens: list[str],
) -> list[str]:
    original = {token.lower() for token in original_tokens}
    return [token for token in expanded_tokens if token.lower() not in original]


def _original_query_tokens(query: str) -> list[str]:
    compact = _compact_ascii_query_token(query)
    if compact:
        return [compact]
    return _dedupe(tokenize_query(query))


def _compact_ascii_query_token(query: str) -> str:
    stripped = query.strip()
    if stripped.isascii() and stripped.isalnum():
        return stripped.lower()
    return ""


def _user_payload(query: str, config: QueryPlannerConfig) -> dict[str, object]:
    return {
        "query": query,
        "language_hints": ["Java", "Spring"],
        "max_rewritten_queries": config.max_rewritten_queries,
        "max_keywords": config.max_keywords,
        "max_symbol_hints": config.max_symbol_hints,
    }


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
