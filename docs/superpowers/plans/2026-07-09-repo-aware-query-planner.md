# Repo-Aware Query Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local LLM query planner use a small repo-specific profile so natural-language queries expand into terms from the current codebase instead of generic framework guesses.

**Architecture:** Build a compact `RepoProfile` from the existing SQLite index before calling the planner. Pass only bounded metadata such as languages, source roots, representative files, symbols, and tokens to the model, then filter planner output against that repo vocabulary before retrieval consumes it. Keep the planner optional and deterministic on failure; do not add LLM reranking or full-source prompt context in this milestone.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, sqlite-backed `SQLiteStore`, existing `QueryPlannerConfig`, existing Ollama planner, existing retrieval pipeline, pytest, optional retrieval quality smoke runner after the quality scoring branch is available.

---

## Source Documents

- Existing query planner spec: `docs/superpowers/specs/2026-06-14-query-planner-design.md`
- Existing query planner plan: `docs/superpowers/plans/2026-06-14-query-planner.md`
- Retrieval quality scoring plan: `docs/superpowers/plans/2026-07-08-retrieval-quality-scoring-system.md`
- Fast-context-like roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

## Current Finding

The planner is already wired into retrieval, but `_user_payload()` currently sends:

```python
"language_hints": ["Java", "Spring"]
```

That explains the real-project smoke result on `psf/requests`: the local `qwen3.5:4b-mlx` planner rewrote Python requests queries into Java/Spring terms such as `HttpSession`, `RestTemplate`, and `RestController`.

The fix is not to give the small model more code. The fix is to give it a tiny, high-signal repo profile and then reject output that has no overlap with the repo vocabulary.

## Scope

Implement in this milestone:

- Replace hard-coded Java/Spring planner hints with a repo-derived profile.
- Keep profile payload under a small character budget, default target 2500 characters.
- Filter or drop planner hints that have no overlap with repo vocabulary.
- Expose profile diagnostics in JSON/MCP planner payloads without logging full source content.
- Add unit tests that reproduce the Python repo misdirection.
- Add optional smoke instructions for `psf/requests` after the quality scoring system is available on the implementation branch.

Do not implement in this milestone:

- No LLM reranking.
- No answer generation.
- No full file snippets in planner prompts.
- No multi-round model loop.
- No automatic weight tuning.
- No remote model provider work.
- No broad rewrite of `retrieval.py`.
- No Python AST symbol extractor in this milestone. Python repos should improve through language, path, file, and lexical-token profile signals first.

## Design

### Repo Profile Packet

The planner receives a compact packet like this:

```json
{
  "query": "where does requests keep cookies between multiple calls in a client session",
  "repo_profile": {
    "languages": ["python"],
    "source_roots": ["src/requests"],
    "important_files": [
      "src/requests/sessions.py",
      "src/requests/cookies.py",
      "src/requests/models.py",
      "src/requests/adapters.py"
    ],
    "symbols": [],
    "tokens": [
      "requests",
      "session",
      "cookies",
      "cookie",
      "jar",
      "prepared",
      "response",
      "adapter"
    ],
    "profile_hash": "sha256:..."
  }
}
```

The profile should be built from the index, not by reading source files again. It should prefer source files over docs/tests, but docs/tests may still appear in full-index runs if they are part of the index.

### Planner Contract

The prompt should instruct the model:

- Use repo profile terms when possible.
- Do not infer unrelated frameworks.
- Do not emit file paths unless they appear in `important_files`.
- If a useful term is not in the profile, keep it only when it is directly implied by the user query.
- Return only compact JSON.

### Output Filtering

The planner output remains a hint, not a fact. Before retrieval sees the plan:

- Clean a rewritten query by dropping unsupported tokens, then keep the cleaned query if it still has useful repo/original overlap.
- Keep a grep keyword or symbol hint only when all meaningful tokens are supported by the repo vocabulary. Original query tokens alone must not allow identifier-style hints such as `HttpSession`.
- Drop terms such as `RestTemplate` in a Python repo when they have no vocabulary overlap.
- Record dropped terms in diagnostics so smoke reports can explain planner behavior.

### Quality Gate

Use unit tests for CI. Use real model smoke tests locally.

Expected smoke direction on `psf/requests`:

- Full-index planner run should improve over the current 3/6 model-backed pass count.
- Source-only planner run should stay at or above 5/6 and should no longer fail because of Java/Spring expansions.
- Planner output for Python requests queries should not contain Spring/Java-only terms unless those terms exist in the indexed repo vocabulary.

## File Structure

Create:

- `src/context_search_tool/repo_profile.py`
  Builds bounded repo profiles from the index and provides vocabulary checks.
- `tests/test_repo_profile.py`
  Unit tests for profile construction, budgeting, and vocabulary filtering.

Modify:

- `src/context_search_tool/models.py`
  Add `RepoProfile` and planner diagnostic fields.
- `src/context_search_tool/sqlite_store.py`
  Add small read-only helpers for language counts, source files, symbols, and token counts.
- `src/context_search_tool/query_planner.py`
  Accept `RepoProfile`, remove hard-coded Java/Spring hints, update prompt/payload, and filter model output.
- `src/context_search_tool/retrieval.py`
  Build the repo profile after opening the index and pass it into the planner.
- `src/context_search_tool/formatters.py`
  Include repo-aware planner diagnostics in JSON.
- `src/context_search_tool/mcp_tools.py`
  Include safe planner diagnostics in MCP responses and feedback logs.
- `tests/test_query_planner.py`
  Cover repo-aware payload and output filtering.
- `tests/test_retrieval_pipeline.py`
  Cover retrieval wiring with a fake planner receiving the profile.
- `tests/test_formatters.py`
  Cover JSON diagnostics.
- `tests/test_mcp_tools.py`
  Cover MCP planner diagnostics.

Optional after retrieval quality scoring is merged:

- Add or update a smoke fixture for `psf/requests` natural-language planner cases.

---

## Task 1: Add RepoProfile Data Model And Store Readers

**Files:**
- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Create: `tests/test_repo_profile.py`

- [ ] **Step 1: Write failing tests for read-only profile inputs**

Create `tests/test_repo_profile.py` with tests that build a tiny SQLite index directly:

```python
from __future__ import annotations

from pathlib import Path

from context_search_tool.models import DocumentChunk, SourceFile, SymbolRef
from context_search_tool.sqlite_store import SQLiteStore


def _store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    return store


def _source(path: str, language: str = "python", is_test: bool = False) -> SourceFile:
    return SourceFile(
        path=Path(path),
        language=language,
        sha256=path,
        size=100,
        mtime_ns=1,
        is_test=is_test,
    )


def _chunk(chunk_id: str, path: str, content: str, symbols: list[str]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(path),
        start_line=1,
        end_line=20,
        content=content,
        chunk_type="code",
        symbols=[
            SymbolRef(
                name=name,
                kind="function",
                start_line=1,
                end_line=5,
                language="python",
            )
            for name in symbols
        ],
        lexical_tokens=["session", "cookies", "cookiejar", "response"],
    )


def test_store_exposes_language_file_symbol_and_token_inputs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_source_file(_source("src/requests/sessions.py"))
    store.upsert_source_file(_source("src/requests/cookies.py"))
    store.upsert_source_file(_source("tests/test_requests.py", is_test=True))
    store.replace_chunks(
        Path("src/requests/sessions.py"),
        [_chunk("c1", "src/requests/sessions.py", "class Session: pass", ["Session"])],
    )
    store.replace_chunks(
        Path("src/requests/cookies.py"),
        [
            _chunk(
                "c2",
                "src/requests/cookies.py",
                "class RequestsCookieJar: pass",
                ["RequestsCookieJar"],
            )
        ],
    )

    assert store.language_counts() == [("python", 3)]
    assert Path("src/requests/sessions.py") in store.source_files_for_profile(limit=10)
    assert "Session" in store.symbol_names_for_profile(limit=10)
    assert "cookies" in store.token_counts_for_profile(limit=10)
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
python -m pytest tests/test_repo_profile.py -q
```

Expected: FAIL because `language_counts`, `source_files_for_profile`, `symbol_names_for_profile`, and `token_counts_for_profile` do not exist.

- [ ] **Step 3: Add `RepoProfile`**

In `src/context_search_tool/models.py`, add:

```python
@dataclass(frozen=True)
class RepoProfile:
    languages: list[str] = field(default_factory=list)
    source_roots: list[str] = field(default_factory=list)
    important_files: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    profile_hash: str = ""
    truncated: bool = False
```

- [ ] **Step 4: Add store readers**

In `src/context_search_tool/sqlite_store.py`, add read-only methods near existing source and stats helpers:

```python
def language_counts(self) -> list[tuple[str, int]]:
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT language, COUNT(*) AS count
            FROM source_files
            GROUP BY language
            ORDER BY
              CASE
                WHEN language IN (
                  'python', 'java', 'kotlin', 'go', 'rust', 'typescript',
                  'typescriptreact', 'javascript', 'javascriptreact', 'vue',
                  'svelte', 'c', 'cpp', 'csharp', 'swift', 'php', 'ruby',
                  'lua', 'dart'
                ) THEN 0
                ELSE 1
              END,
              count DESC,
              language
            """
        ).fetchall()
    return [(str(row["language"]), int(row["count"])) for row in rows]


def source_files_for_profile(self, limit: int) -> list[Path]:
    if limit <= 0:
        return []
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT path
            FROM source_files
            ORDER BY
              is_generated ASC,
              is_test ASC,
              CASE
                WHEN language IN (
                  'python', 'java', 'kotlin', 'go', 'rust', 'typescript',
                  'typescriptreact', 'javascript', 'javascriptreact', 'vue',
                  'svelte', 'c', 'cpp', 'csharp', 'swift', 'php', 'ruby',
                  'lua', 'dart'
                ) THEN 0
                ELSE 1
              END,
              path
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [Path(row["path"]) for row in rows]


def symbol_names_for_profile(self, limit: int) -> list[str]:
    if limit <= 0:
        return []
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT symbols.name, COUNT(*) AS count
            FROM symbols
            JOIN chunk_symbols ON chunk_symbols.symbol_id = symbols.symbol_id
            JOIN chunks ON chunks.chunk_id = chunk_symbols.chunk_id
            WHERE chunks.deleted_at IS NULL
            GROUP BY symbols.name
            ORDER BY count DESC, symbols.name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(row["name"]) for row in rows]


def token_counts_for_profile(self, limit: int) -> list[str]:
    if limit <= 0:
        return []
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT chunk_tokens.token, COUNT(*) AS count
            FROM chunk_tokens
            JOIN chunks ON chunks.chunk_id = chunk_tokens.chunk_id
            WHERE chunks.deleted_at IS NULL
            GROUP BY chunk_tokens.token
            ORDER BY count DESC, chunk_tokens.token
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(row["token"]) for row in rows]
```

- [ ] **Step 5: Verify**

Run:

```bash
python -m pytest tests/test_repo_profile.py -q
```

Expected: PASS.

Commit:

```bash
git add src/context_search_tool/models.py src/context_search_tool/sqlite_store.py tests/test_repo_profile.py
git commit -m "feat: expose repo profile index inputs"
```

## Task 2: Build A Bounded Repo Profile

**Files:**
- Create: `src/context_search_tool/repo_profile.py`
- Modify: `tests/test_repo_profile.py`

- [ ] **Step 1: Write failing profile builder tests**

Append to `tests/test_repo_profile.py`:

```python
import json

from context_search_tool.repo_profile import (
    RepoProfileLimits,
    build_repo_profile,
    profile_vocabulary,
    repo_profile_payload,
    rewritten_query_is_repo_supported,
    term_is_repo_supported,
)


def test_build_repo_profile_prefers_source_vocabulary_and_hashes_payload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_source_file(_source("src/requests/sessions.py"))
    store.upsert_source_file(_source("src/requests/cookies.py"))
    store.replace_chunks(
        Path("src/requests/sessions.py"),
        [_chunk("c1", "src/requests/sessions.py", "class Session: pass", ["Session"])],
    )
    store.replace_chunks(
        Path("src/requests/cookies.py"),
        [_chunk("c2", "src/requests/cookies.py", "RequestsCookieJar", ["RequestsCookieJar"])],
    )

    profile = build_repo_profile(
        store,
        limits=RepoProfileLimits(max_files=4, max_symbols=8, max_tokens=8, max_chars=1000),
    )

    assert profile.languages == ["python"]
    assert "src/requests" in profile.source_roots
    assert "src/requests/sessions.py" in profile.important_files
    assert "Session" in profile.symbols
    assert "cookies" in profile.tokens
    assert profile.profile_hash.startswith("sha256:")
    assert profile.truncated is False


def test_profile_respects_character_budget(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for index in range(20):
        path = f"src/pkg/module_{index}.py"
        store.upsert_source_file(_source(path))
        store.replace_chunks(Path(path), [_chunk(f"c{index}", path, "content", [f"Symbol{index}"])])

    profile = build_repo_profile(
        store,
        limits=RepoProfileLimits(max_files=20, max_symbols=20, max_tokens=20, max_chars=260),
    )

    assert profile.truncated is True
    assert len(json.dumps(repo_profile_payload(profile), ensure_ascii=False, sort_keys=True)) <= 260


def test_term_support_rejects_unrelated_framework_terms(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_source_file(_source("src/requests/sessions.py"))
    store.replace_chunks(
        Path("src/requests/sessions.py"),
        [_chunk("c1", "src/requests/sessions.py", "class Session: pass", ["Session"])],
    )
    profile = build_repo_profile(store)
    vocabulary = profile_vocabulary(profile)

    assert rewritten_query_is_repo_supported(
        "persisted client session cookies",
        vocabulary,
        original_tokens=["client", "session", "cookies"],
    ) == "client session cookies"
    assert term_is_repo_supported("Session cookies", vocabulary)
    assert not term_is_repo_supported("Spring HttpSession cookies", vocabulary)
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_repo_profile.py -q
```

Expected: FAIL because `context_search_tool.repo_profile` does not exist.

- [ ] **Step 3: Implement `repo_profile.py`**

Create `src/context_search_tool/repo_profile.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from context_search_tool.models import RepoProfile
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.tokenizer import tokenize_query


@dataclass(frozen=True)
class RepoProfileLimits:
    max_languages: int = 5
    max_files: int = 16
    max_symbols: int = 48
    max_tokens: int = 64
    max_chars: int = 2500


def build_repo_profile(
    store: SQLiteStore,
    limits: RepoProfileLimits = RepoProfileLimits(),
) -> RepoProfile:
    languages = [language for language, _ in store.language_counts()[: limits.max_languages]]
    files = [path.as_posix() for path in store.source_files_for_profile(limits.max_files)]
    profile = RepoProfile(
        languages=languages,
        source_roots=_source_roots(files),
        important_files=files,
        symbols=store.symbol_names_for_profile(limits.max_symbols),
        tokens=store.token_counts_for_profile(limits.max_tokens),
    )
    return _fit_budget(profile, limits.max_chars)


def profile_vocabulary(profile: RepoProfile) -> set[str]:
    values = [
        *profile.languages,
        *profile.source_roots,
        *profile.important_files,
        *profile.symbols,
        *profile.tokens,
    ]
    tokens: list[str] = []
    for value in values:
        tokens.extend(tokenize_query(value))
    return {token.lower() for token in tokens if len(token) >= 2}


def rewritten_query_is_repo_supported(
    term: str,
    vocabulary: set[str],
    original_tokens: list[str],
) -> str:
    tokens = [token.lower() for token in tokenize_query(term) if len(token) >= 2]
    if not tokens:
        return ""
    allowed = vocabulary | {token.lower() for token in original_tokens}
    cleaned = _dedupe([token for token in tokens if token in allowed])
    return " ".join(cleaned) if len(cleaned) >= 2 else ""


def term_is_repo_supported(
    term: str,
    vocabulary: set[str],
) -> bool:
    tokens = {token.lower() for token in tokenize_query(term) if len(token) >= 2}
    if not tokens:
        return False
    return tokens <= vocabulary


def repo_profile_payload(profile: RepoProfile) -> dict[str, object]:
    return {
        "languages": profile.languages,
        "source_roots": profile.source_roots,
        "important_files": profile.important_files,
        "symbols": profile.symbols,
        "tokens": profile.tokens,
        "profile_hash": profile.profile_hash,
        "truncated": profile.truncated,
    }


def _source_roots(files: list[str]) -> list[str]:
    roots: list[str] = []
    for raw_path in files:
        parts = Path(raw_path).parts
        if len(parts) >= 2 and parts[0] in {"src", "lib", "app", "packages"}:
            candidate = "/".join(parts[:2])
        elif parts:
            candidate = parts[0]
        else:
            continue
        if candidate not in roots:
            roots.append(candidate)
    return roots[:8]


def _fit_budget(profile: RepoProfile, max_chars: int) -> RepoProfile:
    current = profile
    truncated = False
    while _payload_len(current, truncated=truncated) > max_chars:
        truncated = True
        if current.tokens:
            current = RepoProfile(**{**asdict(current), "tokens": current.tokens[:-1]})
            continue
        if current.symbols:
            current = RepoProfile(**{**asdict(current), "symbols": current.symbols[:-1]})
            continue
        if current.important_files:
            current = RepoProfile(**{**asdict(current), "important_files": current.important_files[:-1]})
            continue
        if current.source_roots:
            current = RepoProfile(**{**asdict(current), "source_roots": current.source_roots[:-1]})
            continue
        if len(current.languages) > 1:
            current = RepoProfile(**{**asdict(current), "languages": current.languages[:-1]})
            continue
        break
    payload = {
        **repo_profile_payload(current),
        "profile_hash": "",
        "truncated": truncated,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return RepoProfile(**{**asdict(current), "profile_hash": f"sha256:{digest}", "truncated": truncated})


def _payload_len(profile: RepoProfile, truncated: bool) -> int:
    payload = {
        **repo_profile_payload(profile),
        "profile_hash": "sha256:" + ("0" * 64),
        "truncated": truncated,
    }
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result
```

- [ ] **Step 4: Verify**

Run:

```bash
python -m pytest tests/test_repo_profile.py -q
```

Expected: PASS.

Commit:

```bash
git add src/context_search_tool/repo_profile.py tests/test_repo_profile.py
git commit -m "feat: build bounded repo profiles"
```

## Task 3: Make The Planner Repo-Aware

**Files:**
- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/query_planner.py`
- Modify: `tests/test_query_planner.py`

- [ ] **Step 1: Write failing planner tests**

Add tests to `tests/test_query_planner.py`:

```python
from context_search_tool.models import RepoProfile


def _python_requests_profile() -> RepoProfile:
    return RepoProfile(
        languages=["python"],
        source_roots=["src/requests"],
        important_files=["src/requests/sessions.py", "src/requests/cookies.py"],
        symbols=[],
        tokens=["requests", "session", "cookies", "cookie", "jar", "merge"],
        profile_hash="sha256:test",
    )


def test_ollama_planner_sends_repo_profile_without_java_spring_defaults() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rewritten_queries": ["session cookies"],
                            "grep_keywords": ["RequestsCookieJar"],
                            "symbol_hints": ["Session"],
                            "intent": "feature_lookup",
                        }
                    )
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("where are cookies kept", repo_profile=_python_requests_profile())

    assert plan.status == "ok"
    payload = json.loads(session.calls[0]["json"]["messages"][1]["content"])
    assert payload["repo_profile"]["languages"] == ["python"]
    assert payload["repo_profile"]["source_roots"] == ["src/requests"]
    assert "language_hints" not in payload


def test_clean_planner_payload_drops_terms_without_repo_overlap() -> None:
    plan = clean_planner_payload(
        original_query="where are cookies kept",
        payload={
            "rewritten_queries": ["Spring HttpSession cookies", "requests session cookies"],
            "grep_keywords": ["HttpSession", "RequestsCookieJar"],
            "symbol_hints": ["RestTemplate", "Session"],
            "intent": "feature_lookup",
        },
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
        repo_profile=_python_requests_profile(),
    )

    assert plan.rewritten_queries == ["session cookies", "requests session cookies"]
    assert plan.grep_keywords == ["RequestsCookieJar"]
    assert plan.symbol_hints == ["Session"]
    assert "HttpSession" in plan.discarded_hints
    assert "RestTemplate" in plan.discarded_hints
    assert plan.repo_profile_hash == "sha256:test"
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_query_planner.py -q
```

Expected: FAIL because planner signatures and `QueryPlan` diagnostics do not yet support repo profiles.

- [ ] **Step 3: Extend `QueryPlan` diagnostics**

In `src/context_search_tool/models.py`, add fields to `QueryPlan`:

```python
repo_profile_hash: str = ""
repo_profile_truncated: bool = False
discarded_hints: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Update planner protocol and prompt**

In `src/context_search_tool/query_planner.py`:

```python
from context_search_tool.models import QueryPlan, RepoProfile
from context_search_tool.repo_profile import (
    profile_vocabulary,
    repo_profile_payload,
    rewritten_query_is_repo_supported,
    term_is_repo_supported,
)
```

Change the protocol and implementations:

```python
class QueryPlanner(Protocol):
    def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
        ...


class DisabledQueryPlanner:
    def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
        return disabled_plan(query)
```

Update the Ollama method signature and user payload call:

```python
def plan(self, query: str, repo_profile: RepoProfile | None = None) -> QueryPlan:
    ...
    "content": json.dumps(
        _user_payload(query, self.config, repo_profile),
        ensure_ascii=False,
    ),
```

Update `SYSTEM_PROMPT` to include:

```text
Use repo_profile terms when possible.
Do not infer unrelated frameworks, languages, libraries, or file paths.
If repo_profile is present, prefer its languages, files, symbols, and tokens.
Only return hints that would plausibly exist in this repository.
```

Remove Java/Spring defaults from `_user_payload()`:

```python
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
```

- [ ] **Step 5: Filter planner output**

Update `clean_planner_payload()` signature:

```python
def clean_planner_payload(
    original_query: str,
    payload: dict[str, Any],
    config: QueryPlannerConfig,
    provider: str,
    model: str,
    latency_ms: int | None,
    repo_profile: RepoProfile | None = None,
) -> QueryPlan:
```

After cleaning lists, filter them:

```python
discarded_hints: list[str] = []
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
```

Add helper:

```python
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
    return _dedupe(kept), dropped


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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
```

Include diagnostics in `QueryPlan`:

```python
repo_profile_hash=repo_profile.profile_hash if repo_profile is not None else "",
repo_profile_truncated=repo_profile.truncated if repo_profile is not None else False,
discarded_hints=discarded_hints,
```

Pass `repo_profile` from `OllamaQueryPlanner.plan()` into `clean_planner_payload()`.

- [ ] **Step 6: Verify**

Run:

```bash
python -m pytest tests/test_query_planner.py tests/test_repo_profile.py -q
```

Expected: PASS.

Commit:

```bash
git add src/context_search_tool/models.py src/context_search_tool/query_planner.py tests/test_query_planner.py
git commit -m "feat: make query planner repo aware"
```

## Task 4: Wire RepoProfile Into Retrieval

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing retrieval wiring test**

Add a fake planner test to `tests/test_retrieval_pipeline.py` near existing planner tests:

```python
class FakePlanner:
    def __init__(self, plan: QueryPlan) -> None:
        self.query_plan = plan
        self.calls: list[str] = []
        self.repo_profiles: list[object] = []

    def plan_query(self, query: str) -> QueryPlan:
        self.calls.append(query)
        return self.query_plan

    def plan(self, query: str, repo_profile=None) -> QueryPlan:
        self.calls.append(query)
        self.repo_profiles.append(repo_profile)
        return self.query_plan


class CapturingPlanner:
    def __init__(self) -> None:
        self.repo_profile = None

    def plan(self, query: str, repo_profile=None) -> QueryPlan:
        self.repo_profile = repo_profile
        return QueryPlan(
            original_query=query,
            grep_keywords=["session"],
            status="ok",
            repo_profile_hash=repo_profile.profile_hash if repo_profile else "",
        )


def test_query_repository_passes_repo_profile_to_planner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sessions.py").write_text(
        "class Session:\n    def send(self):\n        return None\n",
        encoding="utf-8",
    )
    config = DEFAULT_CONFIG
    index_repository(repo, config)
    planner = CapturingPlanner()

    bundle = query_repository(repo, "where is session send handled", config, planner=planner)

    assert planner.repo_profile is not None
    assert "python" in planner.repo_profile.languages
    assert "session" in planner.repo_profile.tokens
    assert "sessions.py" in " ".join(planner.repo_profile.important_files)
    assert bundle.planner.repo_profile_hash == planner.repo_profile.profile_hash
```

This update intentionally changes the existing shared `FakePlanner.plan()` signature from `plan(self, query)` to `plan(self, query, repo_profile=None)`. Sweep any other local planner fakes in `tests/` and give them the same optional parameter before running the full retrieval test file.

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_query_repository_passes_repo_profile_to_planner -q
```

Expected: FAIL because `query_repository()` still calls `plan(query)` without a profile.

- [ ] **Step 3: Build profile in retrieval**

In `src/context_search_tool/retrieval.py`, import:

```python
from context_search_tool.repo_profile import build_repo_profile
```

After opening `SQLiteStore` and validating deleted IDs, build the profile:

```python
repo_profile = build_repo_profile(store)
query_planner = planner or planner_from_config(config.query_planner)
plan = query_planner.plan(query, repo_profile=repo_profile)
```

Keep disabled and fallback planner behavior unchanged.
Do not preserve backward compatibility for custom in-process planner fakes inside the test suite; update them to the new protocol in the same task. External CLI/MCP users are unaffected because they do not inject planner objects.

- [ ] **Step 4: Verify**

Run:

```bash
python -m pytest tests/test_retrieval_pipeline.py::test_query_repository_passes_repo_profile_to_planner -q
python -m pytest tests/test_query_planner.py tests/test_repo_profile.py tests/test_retrieval_pipeline.py -q
```

Expected: PASS.

Commit:

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: pass repo profile to query planner"
```

## Task 5: Expose Safe Planner Diagnostics

**Files:**
- Modify: `src/context_search_tool/formatters.py`
- Modify: `src/context_search_tool/mcp_tools.py`
- Modify: `tests/test_formatters.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write failing formatter and MCP tests**

Add formatter assertions that JSON includes safe diagnostics:

```python
def test_format_json_includes_repo_profile_planner_diagnostics() -> None:
    bundle = QueryBundle(
        query="cookies",
        expanded_tokens=["cookies"],
        results=[],
        followup_keywords=[],
        planner=QueryPlan(
            original_query="cookies",
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            repo_profile_hash="sha256:test",
            repo_profile_truncated=True,
            discarded_hints=["RestTemplate"],
        ),
    )

    payload = json.loads(format_json(bundle))

    assert payload["planner"]["repo_profile_hash"] == "sha256:test"
    assert payload["planner"]["repo_profile_truncated"] is True
    assert payload["planner"]["discarded_hint_count"] == 1
```

Add MCP payload or feedback test in the local MCP test style:

```python
assert payload["planner"]["repo_profile_hash"] == "sha256:test"
assert payload["planner"]["discarded_hint_count"] == 1
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_formatters.py tests/test_mcp_tools.py -q
```

Expected: FAIL because diagnostics are not serialized yet.

- [ ] **Step 3: Update JSON and MCP payloads**

In both planner payload helpers, add:

```python
if plan.repo_profile_hash:
    payload["repo_profile_hash"] = plan.repo_profile_hash
    payload["repo_profile_truncated"] = plan.repo_profile_truncated
if plan.discarded_hints:
    payload["discarded_hint_count"] = len(plan.discarded_hints)
    payload["discarded_hints"] = plan.discarded_hints[:8]
```

For feedback logs, keep privacy and size bounded:

```python
"repo_profile_hash",
"repo_profile_truncated",
"discarded_hint_count",
```

Do not write full profile payloads or source snippets to feedback logs.

- [ ] **Step 4: Verify**

Run:

```bash
python -m pytest tests/test_formatters.py tests/test_mcp_tools.py -q
```

Expected: PASS.

Commit:

```bash
git add src/context_search_tool/formatters.py src/context_search_tool/mcp_tools.py tests/test_formatters.py tests/test_mcp_tools.py
git commit -m "feat: expose repo-aware planner diagnostics"
```

## Task 6: Add Quality Smoke Coverage

**Files:**
- Optional create: `tests/fixtures/retrieval_quality/requests_repo_aware_planner.json`
- Optional modify: `src/context_search_tool/quality/runner.py`
- Optional modify: `tests/test_quality_runner.py`

This task depends on the retrieval quality scoring system implementation being available. If the implementation branch is not merged yet, skip the file changes and run the manual commands in Task 7 after merging.

- [ ] **Step 1: Fix quality report planner metadata if needed**

If quality runner reports top-level planner config from the base config instead of the repo override config, add a regression test:

```python
def test_quality_report_records_repo_query_planner_override(tmp_path: Path) -> None:
    fixture = _fixture_with_default_config(
        tmp_path,
        {"query_planner": {"enabled": True, "timeout_seconds": 30}},
    )

    report = run_quality_fixture(
        fixture,
        profile="smoke",
        output_path=None,
        markdown_path=None,
    )

    assert report["repos"][0]["config"]["query_planner"]["enabled"] is True
```

Expected failure before implementation: the report only records the base planner config.

Implement by recording repo-level effective config under each repo record:

```python
"config": {
    "config_hash": _config_hash(repo_config),
    "embedding": asdict(repo_config.embedding),
    "query_planner": asdict(repo_config.query_planner),
},
```

Keep the existing top-level `planner` field for backward compatibility, but prefer repo-level config in new reports.

- [ ] **Step 2: Add smoke fixture for `psf/requests`**

Create `tests/fixtures/retrieval_quality/requests_repo_aware_planner.json`:

```json
{
  "schema_version": 1,
  "repos": [
    {
      "repo_key": "psf_requests",
      "repo_dir_name": "requests",
      "profiles": ["smoke"],
      "default_config": {
        "query_planner": {
          "enabled": true,
          "timeout_seconds": 30
        }
      },
      "queries": [
        {
          "id": "cookies-between-calls",
          "query": "where does requests keep cookies between multiple calls in a client session",
          "expected_any_top_k": [
            {
              "matchers": [
                {"path": "src/requests/sessions.py"},
                {"path": "src/requests/cookies.py"}
              ],
              "top_k": 5
            }
          ]
        },
        {
          "id": "retry-proxy-pooling-natural",
          "query": "where are retries proxy connections and connection pools configured for sending requests",
          "expected_top_k": [
            {"path": "src/requests/adapters.py", "top_k": 5}
          ]
        },
        {
          "id": "stream-response-body-natural",
          "query": "where can response body be streamed in chunks without loading everything",
          "expected_top_k": [
            {"path": "src/requests/models.py", "top_k": 5}
          ]
        }
      ]
    }
  ]
}
```

Do not make this fixture part of CI. It requires a real checkout and local Ollama.

- [ ] **Step 3: Verify quality tests**

Run:

```bash
python -m pytest tests/test_quality_runner.py -q
```

Expected: PASS when the quality package exists. If the quality package is not yet merged, document this task as pending in the implementation notes.

Commit if files changed:

```bash
git add src/context_search_tool/quality tests/test_quality_runner.py tests/fixtures/retrieval_quality/requests_repo_aware_planner.json
git commit -m "test: add repo-aware planner smoke fixture"
```

## Task 7: Run Real Model Smoke

**Files:**
- No required source changes.

- [ ] **Step 1: Prepare `psf/requests`**

Run:

```bash
mkdir -p /tmp/cst-quality-real
test -d /tmp/cst-quality-real/requests/.git || \
  git clone --depth 1 -c fetch.fsck.badTimezone=ignore \
    https://github.com/psf/requests.git \
    /tmp/cst-quality-real/requests
```

- [ ] **Step 2: Confirm local planner model**

Run:

```bash
curl -sS --max-time 3 http://localhost:11434/api/tags
```

Expected: output includes `qwen3.5:4b-mlx`.

- [ ] **Step 3: Run direct planner inspection**

Run a small script to inspect planner output:

```bash
PYTHONPATH=src python - <<'PY'
from dataclasses import replace
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository

repo = Path("/tmp/cst-quality-real/requests")
config = replace(
    DEFAULT_CONFIG,
    query_planner=replace(
        DEFAULT_CONFIG.query_planner,
        enabled=True,
        timeout_seconds=30,
    ),
)
index_repository(repo, config)
bundle = query_repository(
    repo,
    "where does requests keep cookies between multiple calls in a client session",
    config,
)
print(bundle.planner.status)
print(bundle.planner.rewritten_queries)
print(bundle.planner.grep_keywords)
print(bundle.planner.symbol_hints)
print(bundle.planner.discarded_hints)
print([result.file_path.as_posix() for result in bundle.results[:5]])
PY
```

Expected:

- Planner status is `ok`.
- Output does not include `Spring`, `RestTemplate`, `HttpSession`, or `RestController` unless those terms exist in the repo vocabulary.
- Top 5 includes `src/requests/sessions.py` or `src/requests/cookies.py`.

- [ ] **Step 4: Run quality smoke when available**

Only run this step when both conditions are true:

- the quality runner package from `docs/superpowers/plans/2026-07-08-retrieval-quality-scoring-system.md` is merged into the current implementation branch;
- `tests/fixtures/retrieval_quality/requests_repo_aware_planner.json` exists from Task 6.

If either condition is false, skip this step and use the direct planner inspection from Step 3 as the smoke check for this milestone.

If both conditions are true:

```bash
CST_SMOKE_REPOS_DIR=/tmp/cst-quality-real \
PYTHONPATH=src python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/requests_repo_aware_planner.json \
  --profile smoke \
  --output /tmp/cst-requests-repo-aware.json \
  --markdown /tmp/cst-requests-repo-aware.md
```

Expected:

- The fixture runs against copied workspaces.
- No planner output is dominated by unrelated Java/Spring terms.
- Aggregate pass count is at least as good as the previous model-backed source-only run.

## Task 8: Final Verification

**Files:**
- All files touched above.

- [ ] **Step 1: Run focused planner suite**

Run:

```bash
python -m pytest \
  tests/test_repo_profile.py \
  tests/test_query_planner.py \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py \
  tests/test_mcp_tools.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS, except any pre-existing skips.

- [ ] **Step 3: Inspect diff scope**

Run:

```bash
git diff --stat HEAD
git diff -- src/context_search_tool/query_planner.py src/context_search_tool/retrieval.py
```

Expected:

- Changes are limited to repo profile, planner payload/filtering, retrieval wiring, diagnostics, and tests.
- No unrelated ranking rewrite.
- No full source content is logged to MCP feedback.

- [ ] **Step 4: Commit verification**

Run:

```bash
git status --short
git add src/context_search_tool tests
git commit -m "feat: add repo-aware query planning"
```

If Task 6 added only optional smoke fixtures after the main commit, amend the final commit rather than leaving extra commit noise:

```bash
git add tests/fixtures/retrieval_quality/requests_repo_aware_planner.json
git commit --amend --no-edit
```

## Acceptance Checklist

- [ ] Hard-coded `["Java", "Spring"]` planner hints are removed.
- [ ] Planner payload includes a bounded repo profile when an index is available.
- [ ] Small-model prompt stays under the configured profile budget.
- [ ] Planner output with no repo overlap is dropped before retrieval uses it.
- [ ] JSON and MCP output expose `repo_profile_hash`, `repo_profile_truncated`, and dropped-hint count.
- [ ] Unit tests cover Python repo planner behavior.
- [ ] Real `psf/requests` smoke no longer produces Spring/Java planner terms for Python-only queries.
- [ ] No LLM reranking or broad retrieval rewrite is introduced.

Plan complete and saved to `docs/superpowers/plans/2026-07-09-repo-aware-query-planner.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.
