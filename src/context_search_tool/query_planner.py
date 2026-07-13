from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

import requests

from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan, QueryVariant, RepoProfile
from context_search_tool.repo_profile import (
    profile_vocabulary,
    repo_profile_payload,
    rewritten_query_is_repo_supported,
    term_is_repo_supported,
)
from context_search_tool.tokenizer import tokenize_query

PROMPT_VERSION = "qwen-query-planner-v2"
MAX_PLANNER_QUERY_VARIANT_CODEPOINTS = 256

ALLOWED_INTENTS = {
    "feature_lookup",
    "endpoint_lookup",
    "bug_trace",
    "data_flow",
    "symbol_lookup",
    "unknown",
}

PLANNER_JSON_FIELDS = {
    "rewritten_queries",
    "grep_keywords",
    "symbol_hints",
    "intent",
}

SYSTEM_PROMPT = """You rewrite code-search queries. Return only one compact JSON object, no Markdown.
Required fields:
- rewritten_queries: string[]
- grep_keywords: string[]
- symbol_hints: string[]
- intent: feature_lookup | endpoint_lookup | bug_trace | data_flow | symbol_lookup | unknown

Do not explain. Do not guess file paths. Prefer identifiers and English code terms.
Use repo_profile terms when possible.
Do not infer unrelated frameworks, languages, libraries, or file paths.
If repo_profile is present, prefer its languages, files, symbols, and tokens.
Only return hints that would plausibly exist in this repository.
Use an empty array when a list has no useful values.

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
    def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
        ...


class DisabledQueryPlanner:
    def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
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

    def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
        start = time.perf_counter()
        try:
            response = self.session.post(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.config.model,
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(
                                _user_payload(query, self.config, repo_profile),
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
            payload = _decode_planner_json(raw_content)
            if payload is None:
                return self._fallback(query, start, "invalid planner JSON")
            return clean_planner_payload(
                original_query=query,
                payload=payload,
                config=self.config,
                provider=self.config.provider,
                model=self.config.model,
                latency_ms=_elapsed_ms(start),
                repo_profile=repo_profile,
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


def build_query_variants(
    query: str,
    plan: QueryPlan,
    max_rewritten_queries: int,
) -> tuple[list[QueryVariant], list[str]]:
    original_text = _normalize_query_variant_text(query)
    variants = [QueryVariant("original", original_text, "original")]
    if plan.status != "ok":
        return variants, []

    rewritten_queries, discarded = _retain_rewritten_queries(
        original_text,
        plan.rewritten_queries,
        max_rewritten_queries,
    )
    variants.extend(
        QueryVariant(
            variant_id=f"planner:{index}",
            text=text,
            source="planner",
        )
        for index, text in enumerate(rewritten_queries)
    )
    return variants, discarded


def clean_planner_payload(
    original_query: str,
    payload: dict[str, Any],
    config: QueryPlannerConfig,
    provider: str,
    model: str,
    latency_ms: int | None,
    repo_profile: RepoProfile | None = None,
) -> QueryPlan:
    try:
        raw_rewritten_queries = payload.get("rewritten_queries", [])
        if not isinstance(raw_rewritten_queries, list):
            raise ValueError("rewritten_queries must be a list")
        rewritten_queries, discarded_rewrites = _retain_rewritten_queries(
            original_query,
            raw_rewritten_queries,
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

    discarded_hints: list[str] = list(discarded_rewrites)
    if repo_profile is not None:
        vocabulary = profile_vocabulary(repo_profile)
        original_tokens = tokenize_query(original_query)
        rewritten_queries, dropped = _filter_rewritten_queries(
            rewritten_queries,
            vocabulary,
            original_tokens,
        )
        discarded_hints.extend(dropped)
        grep_keywords, dropped = _filter_identifier_hints(grep_keywords, vocabulary)
        discarded_hints.extend(dropped)
        symbol_hints, dropped = _filter_identifier_hints(symbol_hints, vocabulary)
        discarded_hints.extend(dropped)

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
        repo_profile_hash=repo_profile.profile_hash if repo_profile is not None else "",
        repo_profile_truncated=repo_profile.truncated
        if repo_profile is not None
        else False,
        discarded_hints=discarded_hints,
    )


def planner_from_config(config: QueryPlannerConfig) -> QueryPlanner:
    if not config.enabled:
        return DisabledQueryPlanner()
    if config.provider != "ollama":
        return DisabledQueryPlanner()
    return OllamaQueryPlanner(config)


def expand_query_plan_tokens(query: str, plan: QueryPlan) -> list[str]:
    original_tokens = _dedupe(tokenize_query(query))
    if plan.status != "ok":
        return original_tokens
    expanded: list[str] = []
    for rewritten_query in plan.rewritten_queries:
        expanded.extend(tokenize_query(rewritten_query))
    for keyword in [*plan.grep_keywords, *plan.symbol_hints]:
        expanded.extend(tokenize_query(keyword))
    return _dedupe([*original_tokens, *expanded])


def planner_hint_tokens(
    original_tokens: list[str],
    expanded_tokens: list[str],
) -> list[str]:
    original = {token.lower() for token in original_tokens}
    return [token for token in expanded_tokens if token.lower() not in original]


def _user_payload(
    query: str,
    config: QueryPlannerConfig,
    repo_profile: RepoProfile | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "query": query,
        "max_rewritten_queries": config.max_rewritten_queries,
        "max_keywords": config.max_keywords,
        "max_symbol_hints": config.max_symbol_hints,
    }
    if repo_profile is not None:
        payload["repo_profile"] = repo_profile_payload(repo_profile)
    return payload


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _decode_planner_json(raw_content: str) -> dict[str, Any] | None:
    for candidate in _whole_json_candidates(raw_content):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else None

    decoder = json.JSONDecoder()
    for index, char in enumerate(raw_content):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw_content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and PLANNER_JSON_FIELDS.intersection(payload):
            return payload
    return None


def _whole_json_candidates(raw_content: str) -> list[str]:
    stripped = raw_content.strip()
    candidates = [stripped]
    if not stripped.startswith("```"):
        return candidates

    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        candidates.append("\n".join(lines[1:-1]).strip())
    return candidates


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


def _retain_rewritten_queries(
    original_query: str,
    values: list[str],
    limit: int,
) -> tuple[list[str], list[str]]:
    if limit <= 0:
        return [], []

    retained: list[str] = []
    discarded: list[str] = []
    seen = {_normalize_query_variant_text(original_query).casefold()}
    for value in values:
        if not isinstance(value, str):
            raise ValueError("rewritten_queries must contain only strings")
        normalized = _normalize_query_variant_text(value)
        if not normalized:
            continue
        if len(normalized) > MAX_PLANNER_QUERY_VARIANT_CODEPOINTS:
            discarded.append(value)
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        retained.append(normalized)
        if len(retained) >= limit:
            break
    return retained, discarded


def _normalize_query_variant_text(value: str) -> str:
    return " ".join(value.split())


def _filter_rewritten_queries(
    terms: list[str],
    vocabulary: set[str],
    original_tokens: list[str],
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for term in terms:
        cleaned = rewritten_query_is_repo_supported(term, vocabulary, original_tokens)
        if not cleaned:
            dropped.append(term)
            continue
        kept.append(cleaned)
    return _dedupe_strings(kept), dropped


def _filter_identifier_hints(
    terms: list[str],
    vocabulary: set[str],
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for term in terms:
        if term_is_repo_supported(term, vocabulary):
            kept.append(term)
        else:
            dropped.append(term)
    return kept, dropped


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
