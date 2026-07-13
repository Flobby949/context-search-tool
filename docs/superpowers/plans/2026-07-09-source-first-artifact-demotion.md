# Source-First Artifact Demotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ordinary code-behavior queries rank production source above non-source artifacts by default, while preserving docs/config/test results when the query explicitly asks for those artifacts.

**Architecture:** Use `path_roles.classify_path_role()` as the artifact taxonomy instead of adding more suffix-specific checks in retrieval. Expand path roles to classify textual documentation beyond Markdown, then apply a bounded rerank penalty to non-source artifacts unless query intent or explicit file/path hints indicate the artifact is the target. Keep retrieval candidate generation, evidence anchors, planner behavior, and source snippets unchanged.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, existing retrieval rerank pipeline, existing `QueryIntent`, pytest, local Ollama/`psf/requests` smoke comparison.

---

## Source Documents

- Repo-aware planner plan: `docs/superpowers/plans/2026-07-09-repo-aware-query-planner.md`
- Current path-role taxonomy: `src/context_search_tool/path_roles.py`
- Current retrieval rerank and artifact penalties: `src/context_search_tool/retrieval.py`
- Current intent inference: `src/context_search_tool/query_intent.py`
- Current path role tests: `tests/test_path_roles.py`
- Current retrieval ranking tests: `tests/test_retrieval_pipeline.py`

## Current Finding

The repo-aware planner stopped the Java/Spring hallucination, but a full-index `psf/requests` query still ranks docs above source:

```text
where does requests keep cookies between multiple calls in a client session
```

Fast-context returns the useful source files first:

```text
1. src/requests/sessions.py
2. src/requests/cookies.py
```

The local retrieval currently recalls those files but ranks them below docs. The doc demotion exists, but it has gaps:

- `_is_non_readme_markdown_document()` only covers `.md`, so `.rst` docs are not display-demoted.
- `_generic_file_role()` applies only `0.03` doc/config penalty for implementation-looking queries, too small for strong direct/lexical document hits.
- `_query_intent_score_parts()` applies `doc_artifact_penalty` only when query intent is confident; this natural-language query has `confidence=0`.
- Hard-coding `.rst` and `.txt` into the markdown helper would keep chasing suffixes. The better rule is source-first by default, artifact-first only when the query asks for an artifact.

## Scope

Implement in this milestone:

- Classify common textual documentation artifacts beyond `.md`, including `.rst`, `.txt`, `.adoc`, `CHANGELOG`, `HISTORY`, `LICENSE`, and similar root/doc files.
- Replace the markdown-only display penalty with a role-based non-source artifact rerank penalty.
- Preserve artifact results when query intent explicitly asks for docs/config/tests/deployment artifacts.
- Preserve explicit file/path hits, so queries for `docs/user/advanced.rst`, `README`, or `HISTORY.md` still surface those files.
- Add regression tests covering `.rst`/`.txt` docs and default source-first ranking.
- Re-run the `psf/requests` smoke and compare against fast-context output.

Do not implement in this milestone:

- No retrieval candidate generation rewrite.
- No LLM reranking.
- No new model prompts.
- No changes to evidence anchor splitting.
- No broad score tuning unrelated to non-source artifact demotion.
- No automatic quality-runner fixture unless the existing quality runner is already present on the branch.

## File Structure

Modify:

- `src/context_search_tool/path_roles.py`
  Expands artifact classification so non-code text/doc files are recognized through role taxonomy.

- `src/context_search_tool/retrieval.py`
  Replaces suffix-specific markdown demotion with role-based artifact demotion during rerank scoring.

- `tests/test_path_roles.py`
  Adds coverage for `.rst`, `.txt`, `.adoc`, and common doc filenames.

- `tests/test_retrieval_pipeline.py`
  Adds ranking regressions for source-first defaults and artifact-intent escape behavior.

No new source modules are needed.

---

## Task 1: Expand Textual Artifact Path Roles

**Files:**
- Modify: `src/context_search_tool/path_roles.py`
- Modify: `tests/test_path_roles.py`

- [ ] **Step 1: Write failing path-role tests**

Append to `tests/test_path_roles.py`:

```python
def test_path_roles_classify_common_textual_artifacts_as_docs() -> None:
    for relative_path in (
        "README.rst",
        "docs/user/advanced.rst",
        "docs/usage.txt",
        "docs/api.adoc",
        "docs/api.asciidoc",
        "CHANGELOG",
        "CHANGELOG.txt",
        "HISTORY.md",
        "LICENSE",
        "NOTICE",
        "AUTHORS",
        "CONTRIBUTORS.txt",
    ):
        role = classify_path_role(Path(relative_path))
        assert role.name == "doc", relative_path
        assert role.priority == 80


def test_path_roles_keep_production_source_as_source() -> None:
    assert classify_path_role(Path("src/requests/sessions.py")).name == "source"
    assert classify_path_role(Path("src/requests/cookies.py")).name == "source"
    assert classify_path_role(Path("src/utils/usage.ts")).name == "source"
```

- [ ] **Step 2: Run path-role tests and verify failure**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_path_roles.py::test_path_roles_classify_common_textual_artifacts_as_docs \
  tests/test_path_roles.py::test_path_roles_keep_production_source_as_source \
  -q
```

Expected: FAIL because `.txt`, `.adoc`, extensionless `CHANGELOG`, `LICENSE`, `NOTICE`, `AUTHORS`, and `CONTRIBUTORS.txt` are not all classified as `doc`.

- [ ] **Step 3: Add broad doc artifact classification**

In `src/context_search_tool/path_roles.py`, add constants near `_ARTIFACT_CONFIG_SUFFIXES`:

```python
_DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc", ".asciidoc"}
_DOC_FILE_NAMES = {
    "authors",
    "changelog",
    "code_of_conduct",
    "contributors",
    "copying",
    "history",
    "license",
    "notice",
    "readme",
}
```

Then replace the existing suffix check:

```python
    if path.suffix.lower() in {".md", ".mdx", ".rst"}:
        return PathRole("doc", 80)
```

with:

```python
    if (
        path.suffix.lower() in _DOC_SUFFIXES
        or name in _DOC_FILE_NAMES
        or stem in _DOC_FILE_NAMES
    ):
        return PathRole("doc", 80)
```

Keep this block after generated-output/config checks and before source role checks, matching the current order. That preserves generated JSON/YAML output classification and keeps production source extensions from being treated as docs.

- [ ] **Step 4: Verify path-role tests pass**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest tests/test_path_roles.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/path_roles.py tests/test_path_roles.py
git commit -m "feat: classify textual artifacts as docs"
```

---

## Task 2: Add Role-Based Artifact Demotion And Intent Escapes

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing source-first ranking test**

Append near the existing generic noise / doc ranking tests in `tests/test_retrieval_pipeline.py`:

```python
def test_behavior_query_demotes_non_source_artifacts_below_source(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    docs = DocumentChunk(
        chunk_id="docs-advanced",
        file_path=Path("docs/user/advanced.rst"),
        start_line=1,
        end_line=80,
        content="Session objects keep cookies across requests in client examples.",
        chunk_type="document",
        lexical_tokens=["session", "cookies", "requests", "client"],
        metadata={"language": "restructuredtext"},
    )
    txt = DocumentChunk(
        chunk_id="history",
        file_path=Path("HISTORY.txt"),
        start_line=1,
        end_line=60,
        content="Cookies and sessions changed across requests releases.",
        chunk_type="document",
        lexical_tokens=["cookies", "sessions", "requests"],
        metadata={"language": "text"},
    )
    source = DocumentChunk(
        chunk_id="sessions-source",
        file_path=Path("src/requests/sessions.py"),
        start_line=395,
        end_line=555,
        content=(
            "class Session: Provides cookie persistence. "
            "self.cookies = cookiejar_from_dict({}); "
            "merged_cookies = merge_cookies(RequestsCookieJar(), self.cookies)"
        ),
        chunk_type="code",
        lexical_tokens=["session", "cookies", "cookie", "persistence", "merge"],
        metadata={"language": "python"},
    )
    for chunk in (docs, txt, source):
        store.replace_chunks(chunk.file_path, [chunk])

    candidates = {
        "docs-advanced": RetrievalCandidate(
            chunk_id="docs-advanced",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.45,
                "lexical": 4.2,
                "path_symbol": 3.0,
                "direct_text": 1.0,
            },
        ),
        "history": RetrievalCandidate(
            chunk_id="history",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.40,
                "lexical": 3.8,
                "path_symbol": 2.5,
                "direct_text": 0.9,
            },
        ),
        "sessions-source": RetrievalCandidate(
            chunk_id="sessions-source",
            score=1.0,
            source="direct",
            score_parts={
                "semantic": 0.35,
                "lexical": 3.2,
                "path_symbol": 3.0,
                "direct_text": 0.8,
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["where", "requests", "cookies", "client", "session"],
        "where does requests keep cookies between multiple calls in a client session",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "sessions-source"
    assert by_id["docs-advanced"].score_parts["non_source_artifact_penalty"] < 0
    assert by_id["docs-advanced"].score_parts["doc_penalty"] < 0
    assert by_id["history"].score_parts["non_source_artifact_penalty"] < 0
    assert by_id["sessions-source"].score_parts["file_role_source_boost"] > 0
```

- [ ] **Step 2: Run the source-first test and verify failure**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_retrieval_pipeline.py::test_behavior_query_demotes_non_source_artifacts_below_source \
  -q
```

Expected: FAIL because `.rst` and `.txt` artifacts either are not demoted or are demoted too weakly to fall below source.

- [ ] **Step 3: Replace markdown-only display penalty with artifact-role penalty**

In `src/context_search_tool/retrieval.py`, replace:

```python
_NON_README_DOCUMENT_DISPLAY_PENALTY = 0.30
```

with:

```python
_NON_SOURCE_ARTIFACT_DISPLAY_PENALTIES = {
    "doc": 0.45,
    "test": 0.25,
    "deployment_config": 0.35,
    "config_example": 0.35,
    "runtime_config": 0.25,
    "config": 0.20,
    "generated_output": 0.45,
    "lockfile": 0.35,
}
```

In the `_rank_chunks()` first pass, keep the existing `path_role = classify_path_role(chunk.file_path, chunk.content)` line and add `path_role` to the `ranked.append()` payload:

```python
        ranked.append({
            'chunk': chunk,
            'score': score,
            'score_parts': score_parts,
            'flags': flags,
            'role': role,
            'path_role': path_role,
            'signals': rank_tier_signals,
        })
```

Update the `_rerank_score()` call:

```python
        rerank_score = _rerank_score(
            normalized_score,
            item['score_parts'],
            item['chunk'],
            item['flags'],
            item['role'],
            path_role=item['path_role'],
            query_intent=query_intent,
            planner_ceiling=None,
        )
```

Update the `_rerank_score()` signature. Keep the new parameters keyword-only with defaults so existing direct unit tests that call `_rerank_score()` keep working:

```python
def _rerank_score(
    normalized_score: float,
    score_parts: dict[str, float],
    chunk: DocumentChunk,
    flags: dict,
    role: _ChunkRole,
    *,
    path_role: PathRole | None = None,
    query_intent: QueryIntent = QueryIntent(),
    planner_ceiling: float | None,
) -> float:
```

Replace the markdown-only block:

```python
    if _is_non_readme_markdown_document(chunk.file_path):
        rerank_score -= _NON_README_DOCUMENT_DISPLAY_PENALTY
        score_parts[
            "non_readme_document_penalty"
        ] = -_NON_README_DOCUMENT_DISPLAY_PENALTY
```

with:

```python
    artifact_penalty = _non_source_artifact_display_penalty(
        path_role,
        query_intent,
        score_parts,
    )
    if artifact_penalty:
        rerank_score -= artifact_penalty
        score_parts["non_source_artifact_penalty"] = -artifact_penalty
        score_parts[f"{path_role.name}_penalty"] = -artifact_penalty
```

Add this helper near `_query_intent_score_parts()`:

```python
def _non_source_artifact_display_penalty(
    path_role: PathRole | None,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> float:
    if path_role is None:
        return 0.0
    penalty = _NON_SOURCE_ARTIFACT_DISPLAY_PENALTIES.get(path_role.name, 0.0)
    if not penalty:
        return 0.0
    if _artifact_role_is_requested(path_role.name, intent, score_parts):
        return 0.0
    return penalty
```

Add intent-based artifact escapes in the same change. This avoids an intermediate commit where explicit deployment/config/test/doc queries regress:

```python
def _artifact_role_is_requested(
    path_role_name: str,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> bool:
    if path_role_name == "doc":
        return "doc" in intent.target_roles and intent.wants_artifact
    if path_role_name == "test":
        return "test" in intent.target_roles and intent.wants_artifact
    if path_role_name in {
        "config",
        "runtime_config",
        "config_example",
        "deployment_config",
    }:
        return bool(
            intent.wants_artifact
            and intent.target_roles.intersection({"config", "deploy"})
        )
    if path_role_name == "lockfile":
        return bool(intent.wants_artifact and "config_artifact" in intent.artifact_roles)
    if path_role_name == "generated_output":
        return bool(
            intent.wants_artifact
            and "generated_artifact" in intent.artifact_roles
        )
    return False
```

Task 3 adds the explicit filename/path-hint escape after the source-first and intent-based escape behavior is stable.

Remove `_is_non_readme_markdown_document()` after no callers remain. Keep `_is_readme_document()` because evidence anchors still use README classification.

- [ ] **Step 4: Verify the source-first test passes**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_retrieval_pipeline.py::test_behavior_query_demotes_non_source_artifacts_below_source \
  -q
```

Expected: PASS.

- [ ] **Step 5: Run focused ranking tests**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_path_roles.py \
  tests/test_retrieval_pipeline.py::test_behavior_query_demotes_non_source_artifacts_below_source \
  tests/test_retrieval_pipeline.py::test_non_readme_markdown_display_priority_is_lower_than_code \
  tests/test_retrieval_pipeline.py::test_generic_intent_rerank_prefers_config_save_logic_over_yaml_artifacts \
  tests/test_retrieval_pipeline.py::test_generic_intent_rerank_preserves_deployment_config_queries \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: demote non-source artifacts by default"
```

---

## Task 3: Preserve Explicit Artifact Filename Queries

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing explicit filename escape test**

Append to `tests/test_retrieval_pipeline.py`:

```python
def test_explicit_file_hint_does_not_apply_artifact_display_penalty(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    history = DocumentChunk(
        chunk_id="history",
        file_path=Path("HISTORY.txt"),
        start_line=1,
        end_line=40,
        content="History mentions cookies and sessions.",
        chunk_type="document",
        lexical_tokens=["history", "cookies", "sessions"],
        metadata={"language": "text"},
    )
    source = DocumentChunk(
        chunk_id="sessions-source",
        file_path=Path("src/requests/sessions.py"),
        start_line=395,
        end_line=555,
        content="class Session: Provides cookie persistence.",
        chunk_type="code",
        lexical_tokens=["session", "cookies", "persistence"],
        metadata={"language": "python"},
    )
    for chunk in (history, source):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "history": RetrievalCandidate(
                chunk_id="history",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.45,
                    "lexical": 3.5,
                    "path_symbol": 4.0,
                    "direct_text": 1.0,
                },
            ),
            "sessions-source": RetrievalCandidate(
                chunk_id="sessions-source",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.40,
                    "lexical": 3.0,
                    "path_symbol": 2.0,
                    "direct_text": 0.8,
                },
            ),
        },
        ["history", "cookies", "sessions"],
        "HISTORY.txt cookies sessions",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "history"
    assert "non_source_artifact_penalty" not in by_id["history"].score_parts
    assert by_id["history"].score_parts["identifier_exact_match_boost"] > 0
```

- [ ] **Step 2: Run explicit filename escape test and verify failure**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_retrieval_pipeline.py::test_explicit_file_hint_does_not_apply_artifact_display_penalty \
  -q
```

Expected: FAIL because Task 2's intent-based escape does not yet treat actual filename hints from `infer_identifier_intent()` as an artifact request.

- [ ] **Step 3: Add explicit filename/path evidence to artifact escape logic**

Update `_artifact_role_is_requested()` in `src/context_search_tool/retrieval.py` by adding this check at the top:

```python
def _artifact_role_is_requested(
    path_role_name: str,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> bool:
    if _has_explicit_artifact_file_hint(score_parts):
        return True
    if path_role_name == "doc":
        return "doc" in intent.target_roles and intent.wants_artifact
    if path_role_name == "test":
        return "test" in intent.target_roles and intent.wants_artifact
    if path_role_name in {
        "config",
        "runtime_config",
        "config_example",
        "deployment_config",
    }:
        return bool(
            intent.wants_artifact
            and intent.target_roles.intersection({"config", "deploy"})
        )
    if path_role_name == "lockfile":
        return bool(intent.wants_artifact and "config_artifact" in intent.artifact_roles)
    if path_role_name == "generated_output":
        return bool(
            intent.wants_artifact
            and "generated_artifact" in intent.artifact_roles
        )
    return False
```

Add this helper nearby:

```python
def _has_explicit_artifact_file_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "identifier_exact_match_boost",
            "file_hint_match_boost",
            "project_file_hint_boost",
            "project_path_hint_boost",
            "path_role_hint_boost",
        )
    )
```

Do not rely only on `file_hint_match_boost`: that score part is computed later in `_rerank_score()` after the artifact penalty point. `identifier_exact_match_boost` already exists before the penalty because `_identifier_intent_score_parts()` runs before `_rerank_score()`.

- [ ] **Step 4: Verify explicit filename escape test passes**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_retrieval_pipeline.py::test_explicit_file_hint_does_not_apply_artifact_display_penalty \
  -q
```

Expected: PASS.

- [ ] **Step 5: Add explicit docs/config/test artifact regression tests**

Append to `tests/test_retrieval_pipeline.py`:

```python
def test_doc_query_does_not_apply_doc_artifact_display_penalty(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    docs = DocumentChunk(
        chunk_id="docs-advanced",
        file_path=Path("docs/user/advanced.rst"),
        start_line=1,
        end_line=80,
        content="Advanced docs explain Session cookies and cookie persistence.",
        chunk_type="document",
        lexical_tokens=["advanced", "docs", "session", "cookies", "persistence"],
        metadata={"language": "restructuredtext"},
    )
    source = DocumentChunk(
        chunk_id="sessions-source",
        file_path=Path("src/requests/sessions.py"),
        start_line=395,
        end_line=555,
        content="class Session: Provides cookie persistence.",
        chunk_type="code",
        lexical_tokens=["session", "cookies", "persistence"],
        metadata={"language": "python"},
    )
    for chunk in (docs, source):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "docs-advanced": RetrievalCandidate(
                chunk_id="docs-advanced",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.45,
                    "lexical": 3.5,
                    "path_symbol": 3.0,
                    "direct_text": 1.0,
                },
            ),
            "sessions-source": RetrievalCandidate(
                chunk_id="sessions-source",
                score=1.0,
                source="direct",
                score_parts={
                    "semantic": 0.40,
                    "lexical": 3.0,
                    "path_symbol": 2.0,
                    "direct_text": 0.8,
                },
            ),
        },
        ["docs", "session", "cookies"],
        "docs for requests session cookies",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "docs-advanced"
    assert "non_source_artifact_penalty" not in by_id["docs-advanced"].score_parts
    assert by_id["docs-advanced"].score_parts["doc_artifact_boost"] > 0


def test_config_artifact_query_does_not_apply_config_display_penalty(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    config = DocumentChunk(
        chunk_id="runtime-config",
        file_path=Path("config/text_providers.yaml"),
        start_line=1,
        end_line=20,
        content="active_provider: openai",
        chunk_type="config",
        lexical_tokens=["config", "provider", "yaml", "active"],
        metadata={"language": "yaml"},
    )
    source = DocumentChunk(
        chunk_id="config-service",
        file_path=Path("backend/services/config.py"),
        start_line=1,
        end_line=40,
        content="class ConfigService: save active provider",
        chunk_type="code",
        lexical_tokens=["config", "provider", "save", "active"],
        metadata={"language": "python"},
    )
    for chunk in (config, source):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "runtime-config": RetrievalCandidate(
                chunk_id="runtime-config",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.5, "lexical": 3.5, "direct_text": 1.0},
            ),
            "config-service": RetrievalCandidate(
                chunk_id="config-service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.4, "lexical": 2.8, "direct_text": 0.7},
            ),
        },
        ["config", "yaml", "provider"],
        "config yaml provider file",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "runtime-config"
    assert "non_source_artifact_penalty" not in by_id["runtime-config"].score_parts


def test_test_artifact_query_does_not_apply_test_display_penalty(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    test_chunk = DocumentChunk(
        chunk_id="session-test",
        file_path=Path("tests/test_sessions.py"),
        start_line=1,
        end_line=60,
        content="def test_session_cookies_are_persisted(): pass",
        chunk_type="code",
        lexical_tokens=["test", "session", "cookies", "persisted"],
        metadata={"language": "python", "is_test": True},
    )
    source = DocumentChunk(
        chunk_id="sessions-source",
        file_path=Path("src/requests/sessions.py"),
        start_line=395,
        end_line=555,
        content="class Session: Provides cookie persistence.",
        chunk_type="code",
        lexical_tokens=["session", "cookies", "persistence"],
        metadata={"language": "python"},
    )
    for chunk in (test_chunk, source):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "session-test": RetrievalCandidate(
                chunk_id="session-test",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.5, "lexical": 3.5, "direct_text": 1.0},
            ),
            "sessions-source": RetrievalCandidate(
                chunk_id="sessions-source",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.4, "lexical": 2.8, "direct_text": 0.7},
            ),
        },
        ["test", "session", "cookies"],
        "test for session cookies",
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "session-test"
    assert "non_source_artifact_penalty" not in by_id["session-test"].score_parts
```

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_retrieval_pipeline.py::test_doc_query_does_not_apply_doc_artifact_display_penalty \
  tests/test_retrieval_pipeline.py::test_config_artifact_query_does_not_apply_config_display_penalty \
  tests/test_retrieval_pipeline.py::test_test_artifact_query_does_not_apply_test_display_penalty \
  -q
```

Expected: PASS. These are regression coverage for the intent-based escapes implemented in Task 2.

- [ ] **Step 6: Run focused artifact tests**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_path_roles.py \
  tests/test_retrieval_pipeline.py::test_behavior_query_demotes_non_source_artifacts_below_source \
  tests/test_retrieval_pipeline.py::test_doc_query_does_not_apply_doc_artifact_display_penalty \
  tests/test_retrieval_pipeline.py::test_config_artifact_query_does_not_apply_config_display_penalty \
  tests/test_retrieval_pipeline.py::test_test_artifact_query_does_not_apply_test_display_penalty \
  tests/test_retrieval_pipeline.py::test_explicit_file_hint_does_not_apply_artifact_display_penalty \
  tests/test_retrieval_pipeline.py::test_generic_intent_rerank_prefers_config_save_logic_over_yaml_artifacts \
  tests/test_retrieval_pipeline.py::test_generic_intent_rerank_preserves_deployment_config_queries \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: preserve explicit artifact retrieval intent"
```

---

## Task 4: Verify Requests Smoke Against Fast-Context Baseline

**Files:**
- No required source changes.

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest \
  tests/test_path_roles.py \
  tests/test_retrieval_pipeline.py \
  tests/test_query_planner.py \
  tests/test_repo_profile.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python -m pytest -q
```

Expected: PASS, with existing skips only.

- [ ] **Step 3: Prepare `psf/requests`**

Run:

```bash
mkdir -p /tmp/cst-quality-real
test -d /tmp/cst-quality-real/requests/.git || \
  git clone --depth 1 -c fetch.fsck.badTimezone=ignore \
    https://github.com/psf/requests.git \
    /tmp/cst-quality-real/requests
```

Expected: `/tmp/cst-quality-real/requests` exists.

- [ ] **Step 4: Run local retrieval smoke**

Run:

```bash
PYTHONPATH=src /tmp/cst-repo-aware-venv/bin/python - <<'PY'
from dataclasses import replace
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository

repo = Path("/tmp/cst-quality-real/requests")
query = "where does requests keep cookies between multiple calls in a client session"
config = replace(
    DEFAULT_CONFIG,
    query_planner=replace(
        DEFAULT_CONFIG.query_planner,
        enabled=True,
        timeout_seconds=30,
    ),
)
index_repository(repo, config)
bundle = query_repository(repo, query, config)
print("planner:", bundle.planner.status)
print("rewritten:", bundle.planner.rewritten_queries)
print("grep:", bundle.planner.grep_keywords)
print("symbols:", bundle.planner.symbol_hints)
print("discarded:", bundle.planner.discarded_hints)
for index, result in enumerate(bundle.results[:10], 1):
    print(index, result.file_path.as_posix(), result.score, result.reasons)
    print("  score_parts:", result.score_parts)
PY
```

Expected:

- No `Spring`, `RestTemplate`, `HttpSession`, or `RestController` in planner output.
- `src/requests/sessions.py` or `src/requests/cookies.py` appears in the top 5.
- `.rst`, `.txt`, `HISTORY`, or other docs that remain in top 10 include `non_source_artifact_penalty` in `score_parts`, unless they have a clear artifact-intent escape score part.

- [ ] **Step 5: Run fast-context comparison**

Use `mcp__fast_context.fast_context_search` with:

```json
{
  "project_path": "/tmp/cst-quality-real/requests",
  "query": "where does requests keep cookies between multiple calls in a client session",
  "tree_depth": 3,
  "max_turns": 3,
  "max_results": 10,
  "exclude_paths": [".git", ".pytest_cache", "__pycache__", ".tox", "build", "dist"],
  "include_code_snippets": false
}
```

Expected:

- fast-context still returns `src/requests/sessions.py` and `src/requests/cookies.py` near the top.
- Local retrieval now agrees on at least one of those source files in top 5.

- [ ] **Step 6: Inspect diff scope**

Run:

```bash
git diff --stat HEAD
git diff -- src/context_search_tool/retrieval.py src/context_search_tool/path_roles.py
```

Expected:

- Changes are limited to path role classification, artifact rerank demotion, intent/file-hint escapes, and tests.
- No planner prompt changes.
- No candidate generation rewrite.
- No evidence anchor rewrite.

- [ ] **Step 7: Commit verification notes if no source changes remain**

If all changes are already committed by Tasks 1-3, do not create an empty commit. Record smoke results in the final response instead.

## Acceptance Checklist

- [ ] Default behavior queries prefer production source over docs/tests/config/generated artifacts when scores are otherwise comparable.
- [ ] `.rst`, `.txt`, `.adoc`, extensionless `CHANGELOG`, `HISTORY`, `LICENSE`, and similar text artifacts are classified as docs.
- [ ] Artifact demotion is based on `PathRole`, not a hard-coded Markdown-only suffix check.
- [ ] Explicit docs/config/test/deployment/file-path queries preserve those artifacts.
- [ ] Existing config/deployment/query-intent tests continue to pass.
- [ ] `psf/requests` cookies/session smoke has `src/requests/sessions.py` or `src/requests/cookies.py` in top 5.
- [ ] The fix does not add LLM reranking, prompt changes, or broad retrieval rewrites.

## Plan Self-Review

- Spec coverage: The plan covers broad non-code artifact demotion, intent escapes, explicit file/path protection, regression tests, and `psf/requests` comparison.
- Placeholder scan: No task contains placeholder markers, open-ended implementation instructions, or missing commands.
- Type consistency: The plan uses existing `PathRole`, `QueryIntent`, `DocumentChunk`, `RetrievalCandidate`, and `_rank_chunks()` names from the codebase. New helpers are introduced before they are used.
