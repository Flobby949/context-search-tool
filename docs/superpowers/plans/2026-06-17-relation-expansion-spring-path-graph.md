# Relation Expansion And Spring Path Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce retrieval latency from relation expansion N+1 queries and make Java/Spring ranking use endpoint-centric business paths instead of only additive score boosts.

**Architecture:** First add measurable batch APIs in `SQLiteStore` and convert relation expansion to frontier-style batched traversal without changing result semantics. Then add a Java/Spring path graph layer that identifies exact route entrypoints and propagates bounded path scores to service implementations and executors, keeping Evidence Anchors and query planning out of scope.

**Tech Stack:** Python 3.11+, pytest, existing SQLite store, existing Java plugin signals/relations, existing BGE-M3 real-project smoke workflow, existing `context_search_tool.retrieval` rerank pipeline.

---

## 1. Problem Statement

The current retrieval pipeline has two connected bottlenecks:

1. **Performance:** `_relation_expansion_candidates` repeatedly calls `relations_for_source`, `chunks_matching_signal_or_symbol`, `signals_for_chunk`, `chunk_for_id`, and same-file/directory helpers one item at a time. Real-project profiling on the BGE-M3 temporary indexes showed relation expansion dominating query latency:
   - `/appCatalog/page canApply`: total about 6473ms, relation expansion about 3754ms, `chunks_matching_signal_or_symbol` about 3388ms over 358 calls.
   - `/apply/audit/pageEs INVOLVED_BY_ME`: total about 2704ms, relation expansion about 1210ms, `chunks_matching_signal_or_symbol` about 995ms over 141 calls.
2. **Ranking quality:** Java/Spring rerank now handles exact routes, sibling penalties, route tails, service impl boosts, and executor context, but these are still independent score parts. The system does not yet treat an endpoint path as a first-class graph: exact controller -> service implementation -> executor/filter should be scored as one coherent business path.

This task should not become another round of case-specific boosts. It should make the expensive graph traversal cheaper and make Spring business paths explicit enough that nearby but wrong routes, side executors, tests, and interfaces naturally sink.

## 2. Scope

### In Scope

- Add batch read APIs to `SQLiteStore` for signals, relations, chunks by id, chunks by target names, and chunks by file.
- Convert `_relation_expansion_candidates` to use depth-by-depth batched traversal.
- Preserve existing relation expansion score semantics unless a test explicitly documents an intentional change.
- Add a Spring endpoint path graph signal that starts from exact route endpoint signals and propagates bounded scores through service impl and executor chunks.
- Keep graph scoring generic: no hardcoded `canApply`, `INVOLVED_BY_ME`, `pageEs`, `AppCatalog`, or audit-specific names in production code.
- Add tests that cover performance-sensitive call patterns without relying on wall-clock timing in CI.
- Validate against the two real-project cases using BGE-M3 temporary copies and compare with fast-context.

### Out Of Scope

- Do not change Evidence Anchors payloads or display rules.
- Do not change embedding providers, model defaults, or index manifests.
- Do not make the query planner responsible for Spring path semantics.
- Do not add Chinese business alias maps.
- Do not replace the existing rerank pipeline wholesale.
- Do not introduce a generic framework plugin abstraction for non-Java languages in this task.

## 3. Acceptance Criteria

- Full pytest passes.
- Existing Java/Spring acceptance tests still pass.
- `tests/test_retrieval_pipeline.py` includes regression coverage for:
  - batched relation expansion preserving existing target ordering;
  - exact route graph boosting controller -> service impl -> executor;
  - sibling route not seeding the exact route graph;
  - service interface visible but ranked below implementation path;
  - route-tail matching not combining unrelated symbols.
- `tests/test_sqlite_store.py` includes coverage for each new batch API.
- Real-project BGE-M3 smoke results:
  - `/appCatalog/page canApply`: `AppCatalogController`, `PageAppCatalogQueryExe`, and `AppInfoServiceImpl` remain in the early result window; `AppCatalogOpenController` is not first.
  - `/apply/audit/pageEs INVOLVED_BY_ME`: `ResourceApplyAuditController`, `EsApplyAuditPageQryExe`, and `ResourceAuditServiceImpl` remain in the early result window; test files and non-ES executors stay lower.
- Real-project profiling shows `_relation_expansion_candidates` no longer dominated by hundreds of `chunks_matching_signal_or_symbol` calls. Target: reduce relation-expansion SQLite calls by at least 70% on both smoke cases. Wall-clock target is best-effort, not a CI assertion.

## 4. Current Code Map

- `src/context_search_tool/retrieval.py`
  - `query_repository` builds direct candidates, anchor candidates, relation candidates, ranks, expands snippets, and splits evidence anchors.
  - `_relation_expansion_candidates` currently traverses relation edges using per-signal/per-target store calls.
  - `_rank_chunks` computes score parts, role, route score parts, Java context parts, normalized score, rerank score, and final ordering.
  - `_route_score_parts`, `_route_tail_context_score_parts`, and `_role_exact_match_boost` currently contain the latest Java/Spring rerank improvements.
- `src/context_search_tool/sqlite_store.py`
  - `signals_for_chunk`, `relations_for_source`, `chunks_matching_signal_or_symbol`, `chunk_for_id`, and `chunks_for_file` are single-key APIs.
  - New batch APIs should live next to these methods and share row conversion helpers.
- `src/context_search_tool/java_plugin.py`
  - Emits endpoint signals with joined Spring paths.
  - Emits method/field/class signals and usage relations consumed by retrieval.
  - This task should avoid changing plugin extraction unless graph tests prove a missing signal.
- `tests/test_retrieval_pipeline.py`
  - Owns synthetic retrieval and rerank behavior tests.
- `tests/test_sqlite_store.py`
  - Owns SQLite store read/write behavior tests.

## 5. Files And Responsibilities

- Modify: `src/context_search_tool/sqlite_store.py`
  - Add batch APIs that preserve the ordering of existing single-key APIs within each key.
- Modify: `src/context_search_tool/retrieval.py`
  - Use batch APIs in relation expansion.
  - Add Spring path graph scoring helpers and score parts.
- Test: `tests/test_sqlite_store.py`
  - Unit-test batch APIs.
- Test: `tests/test_retrieval_pipeline.py`
  - Unit-test relation expansion call patterns and Spring graph scoring.
- Optional create: `scripts/profile_retrieval.py`
  - A small local-only profiling helper for real-project smoke checks.
  - Create this only if repeating the profiling command manually becomes cumbersome during implementation.

## 6. Implementation Tasks

### Task 1: Add Store Batch APIs

**Files:**
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `tests/test_sqlite_store.py`

- [ ] **Step 1: Write failing tests for batched signals and relations**

Add tests near existing signal/relation tests in `tests/test_sqlite_store.py`:

```python
def test_signals_for_chunks_batches_and_preserves_per_chunk_order(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    first = _chunk("first", "src/First.java", ["first"])
    second = _chunk("second", "src/Second.java", ["second"])
    store.replace_chunks(first.file_path, [first])
    store.replace_chunks(second.file_path, [second])
    store.replace_signals(
        first.file_path,
        [
            CodeSignal("s2", "first", first.file_path, "method", "First.two", 8, 8, "java"),
            CodeSignal("s1", "first", first.file_path, "method", "First.one", 3, 3, "java"),
        ],
    )
    store.replace_signals(
        second.file_path,
        [CodeSignal("s3", "second", second.file_path, "method", "Second.one", 4, 4, "java")],
    )

    grouped = store.signals_for_chunks(["second", "missing", "first"])

    assert [signal.signal_id for signal in grouped["first"]] == ["s1", "s2"]
    assert [signal.signal_id for signal in grouped["second"]] == ["s3"]
    assert grouped["missing"] == []
```

```python
def test_relations_for_sources_batches_and_preserves_source_order(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = _chunk("source", "src/Source.java", ["source"])
    store.replace_chunks(source.file_path, [source])
    store.replace_signals(
        source.file_path,
        [
            CodeSignal("sig-a", "source", source.file_path, "method", "Source.a", 1, 1, "java"),
            CodeSignal("sig-b", "source", source.file_path, "method", "Source.b", 2, 2, "java"),
        ],
    )
    store.replace_relations(
        [
            CodeRelation("rel-2", "sig-a", "Target.two", "calls", 0.8),
            CodeRelation("rel-1", "sig-a", "Target.one", "calls", 0.9),
            CodeRelation("rel-3", "sig-b", "Target.three", "calls", 0.7),
        ]
    )

    grouped = store.relations_for_sources(["sig-b", "missing", "sig-a"])

    assert [relation.relation_id for relation in grouped["sig-a"]] == ["rel-1", "rel-2"]
    assert [relation.relation_id for relation in grouped["sig-b"]] == ["rel-3"]
    assert grouped["missing"] == []
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_sqlite_store.py -k "signals_for_chunks or relations_for_sources" -q
```

Expected: fails because `SQLiteStore.signals_for_chunks` and `SQLiteStore.relations_for_sources` do not exist.

- [ ] **Step 3: Implement `signals_for_chunks` and `relations_for_sources`**

Add methods next to the existing single-key methods in `src/context_search_tool/sqlite_store.py`:

```python
def signals_for_chunks(self, chunk_ids: list[str]) -> dict[str, list[CodeSignal]]:
    unique_ids = _dedupe_values(chunk_ids)
    grouped: dict[str, list[CodeSignal]] = {chunk_id: [] for chunk_id in unique_ids}
    if not unique_ids:
        return grouped
    placeholders = ",".join("?" for _ in unique_ids)
    with self._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM code_signals
            WHERE chunk_id IN ({placeholders})
              AND deleted_at IS NULL
            ORDER BY chunk_id, start_line, end_line, kind, name, signal_id
            """,
            unique_ids,
        ).fetchall()
    for row in rows:
        signal = _signal_from_row(row)
        grouped.setdefault(signal.chunk_id, []).append(signal)
    return grouped
```

```python
def relations_for_sources(self, source_signal_ids: list[str]) -> dict[str, list[CodeRelation]]:
    unique_ids = _dedupe_values(source_signal_ids)
    grouped: dict[str, list[CodeRelation]] = {signal_id: [] for signal_id in unique_ids}
    if not unique_ids:
        return grouped
    placeholders = ",".join("?" for _ in unique_ids)
    with self._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM code_relations
            WHERE source_signal_id IN ({placeholders})
              AND deleted_at IS NULL
            ORDER BY source_signal_id, kind, target_name, relation_id
            """,
            unique_ids,
        ).fetchall()
    for row in rows:
        relation = _relation_from_row(row)
        grouped.setdefault(relation.source_signal_id, []).append(relation)
    return grouped
```

Add a small private helper near other module helpers:

```python
def _dedupe_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
```

- [ ] **Step 4: Add tests for target-name and chunk batch APIs**

Add tests:

```python
def test_chunks_for_ids_batches_existing_chunks(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    first = _chunk("first", "src/First.java", ["first"])
    second = _chunk("second", "src/Second.java", ["second"])
    store.replace_chunks(first.file_path, [first])
    store.replace_chunks(second.file_path, [second])

    chunks = store.chunks_for_ids(["second", "missing", "first"])

    assert list(chunks) == ["second", "first"]
    assert chunks["second"].file_path == second.file_path
    assert chunks["first"].file_path == first.file_path
```

```python
def test_chunks_matching_signal_or_symbols_batches_by_target(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service = _chunk("service", "src/AppInfoServiceImpl.java", ["app", "info"])
    executor = _chunk("executor", "src/PageAppCatalogQueryExe.java", ["page", "catalog"])
    store.replace_chunks(service.file_path, [service])
    store.replace_chunks(executor.file_path, [executor])

    grouped = store.chunks_matching_signal_or_symbols(
        ["AppInfoServiceImpl.page", "PageAppCatalogQueryExe.execute", "missing"],
        limit_per_target=3,
    )

    assert "service" in [chunk.chunk_id for chunk in grouped["AppInfoServiceImpl.page"]]
    assert "executor" in [chunk.chunk_id for chunk in grouped["PageAppCatalogQueryExe.execute"]]
    assert grouped["missing"] == []
```

- [ ] **Step 5: Implement `chunks_for_ids` and `chunks_matching_signal_or_symbols`**

Add:

```python
def chunks_for_ids(self, chunk_ids: list[str]) -> dict[str, DocumentChunk]:
    unique_ids = _dedupe_values(chunk_ids)
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    with self._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM chunks
            WHERE chunk_id IN ({placeholders})
              AND deleted_at IS NULL
            """,
            unique_ids,
        ).fetchall()
        chunks = {row["chunk_id"]: self._chunk_from_row(connection, row) for row in rows}
    return {chunk_id: chunks[chunk_id] for chunk_id in unique_ids if chunk_id in chunks}
```

Implement `chunks_matching_signal_or_symbols` conservatively by reusing the existing helper behavior per target inside one connection:

```python
def chunks_matching_signal_or_symbols(
    self,
    target_names: list[str],
    limit_per_target: int,
) -> dict[str, list[DocumentChunk]]:
    unique_names = _dedupe_values(target_names)
    grouped: dict[str, list[DocumentChunk]] = {name: [] for name in unique_names}
    if not unique_names or limit_per_target <= 0:
        return grouped
    with self._connect() as connection:
        for target_name in unique_names:
            rows = _chunks_matching_name(connection, target_name, limit_per_target)
            if not rows and "." in target_name:
                owner_name, member_name = target_name.rsplit(".", 1)
                rows = _chunks_matching_member_name(
                    connection,
                    owner_name,
                    member_name,
                    limit_per_target,
                )
            grouped[target_name] = [self._chunk_from_row(connection, row) for row in rows]
    return grouped
```

This is a first performance step because it removes repeated connection setup. Task 2 can later reduce query count further if profiling still shows target matching dominates.

- [ ] **Step 6: Run store tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_sqlite_store.py -q
```

Expected: all SQLite store tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/context_search_tool/sqlite_store.py tests/test_sqlite_store.py
git commit -m "Add batched SQLite store reads for retrieval"
```

### Task 2: Batch Relation Expansion Traversal

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add a call-count regression test**

Add a store wrapper test that makes the old N+1 shape visible without asserting wall-clock time:

```python
def test_relation_expansion_uses_batched_store_reads(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = _java_chunk("source", "src/Controller.java", ["controller"])
    service = _java_chunk("service", "src/AppInfoServiceImpl.java", ["service"])
    executor = _java_chunk("executor", "src/PageAppCatalogQueryExe.java", ["executor"])
    store.replace_chunks(source.file_path, [source])
    store.replace_chunks(service.file_path, [service])
    store.replace_chunks(executor.file_path, [executor])
    store.replace_signals(
        source.file_path,
        [CodeSignal("sig-source", "source", source.file_path, "endpoint", "POST /appCatalog/page", 1, 1, "java", metadata={"path": "/appCatalog/page"})],
    )
    store.replace_signals(
        service.file_path,
        [CodeSignal("sig-service", "service", service.file_path, "method", "AppInfoServiceImpl.page", 1, 1, "java")],
    )
    store.replace_signals(
        executor.file_path,
        [CodeSignal("sig-executor", "executor", executor.file_path, "method", "PageAppCatalogQueryExe.execute", 1, 1, "java")],
    )
    store.replace_relations(
        [
            CodeRelation("rel-service", "sig-source", "AppInfoServiceImpl.page", "calls", 1.0),
            CodeRelation("rel-executor", "sig-service", "PageAppCatalogQueryExe.execute", "calls", 1.0),
        ]
    )

    call_counts = {"relations_for_sources": 0, "chunks_matching_signal_or_symbols": 0}
    original_relations = store.relations_for_sources
    original_chunks = store.chunks_matching_signal_or_symbols

    def counted_relations(source_signal_ids: list[str]) -> dict[str, list[CodeRelation]]:
        call_counts["relations_for_sources"] += 1
        return original_relations(source_signal_ids)

    def counted_chunks(target_names: list[str], limit_per_target: int) -> dict[str, list[DocumentChunk]]:
        call_counts["chunks_matching_signal_or_symbols"] += 1
        return original_chunks(target_names, limit_per_target)

    store.relations_for_sources = counted_relations  # type: ignore[method-assign]
    store.chunks_matching_signal_or_symbols = counted_chunks  # type: ignore[method-assign]

    expanded = retrieval._relation_expansion_candidates(
        store,
        [RetrievalCandidate("source", 1.0, "signal", {"signal": 1.0})],
        ToolConfig(retrieval=RetrievalConfig(semantic_top_k=0, lexical_top_k=10, final_top_k=5)),
    )

    assert {candidate.chunk_id for candidate in expanded} == {"service", "executor"}
    assert call_counts["relations_for_sources"] <= retrieval.MAX_EXPANSION_DEPTH
    assert call_counts["chunks_matching_signal_or_symbols"] <= retrieval.MAX_EXPANSION_DEPTH
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_relation_expansion_uses_batched_store_reads -q
```

Expected: fails because `_relation_expansion_candidates` still calls single-key methods.

- [ ] **Step 3: Rewrite `_relation_expansion_candidates` by frontier**

Replace the inner traversal with depth batches:

```python
queue: deque[tuple[str, float, int, bool, bool]] = deque(initial_signal_states)
while queue:
    current_level = list(queue)
    queue.clear()
    source_ids = [
        source_signal_id
        for source_signal_id, _score, depth, _planner_seeded, _original_seeded in current_level
        if depth < MAX_EXPANSION_DEPTH and source_signal_id not in visited_signals
    ]
    for source_signal_id in source_ids:
        visited_signals.add(source_signal_id)
    if not source_ids:
        continue

    state_by_source = {
        source_signal_id: (current_score, depth, planner_seeded, original_seeded)
        for source_signal_id, current_score, depth, planner_seeded, original_seeded in current_level
        if source_signal_id in source_ids
    }
    relations_by_source = store.relations_for_sources(source_ids)
    target_names = [
        relation.target_name
        for source_signal_id in source_ids
        for relation in relations_by_source.get(source_signal_id, [])
        if relation.confidence >= _MIN_RELATION_CONFIDENCE
    ]
    chunks_by_target = store.chunks_matching_signal_or_symbols(
        target_names,
        limit_per_target=MAX_EXPANSION_CANDIDATES,
    )
    reached_chunk_ids = []
    for source_signal_id in source_ids:
        current_score, depth, planner_seeded, original_seeded = state_by_source[source_signal_id]
        next_depth = depth + 1
        for relation in relations_by_source.get(source_signal_id, []):
            if relation.confidence < _MIN_RELATION_CONFIDENCE:
                continue
            next_score = current_score * relation.confidence * _RELATION_SCORE_DECAY
            for chunk in chunks_by_target.get(relation.target_name, []):
                reached_chunk_ids.append(chunk.chunk_id)
                existing = expanded_by_chunk.get(chunk.chunk_id)
                seed_score = seed_scores.get(
                    chunk.chunk_id,
                    _RelationSeed(0.0, False, False),
                ).score
                should_add_relation = (
                    chunk.chunk_id not in seed_scores or next_score > seed_score
                )
                if should_add_relation and (existing is None or next_score > existing.score):
                    score_parts = {"relation": next_score}
                    if planner_seeded:
                        score_parts["planner_relation"] = next_score
                    if original_seeded:
                        score_parts["original_relation"] = next_score
                    expanded_by_chunk[chunk.chunk_id] = RetrievalCandidate(
                        chunk_id=chunk.chunk_id,
                        score=next_score,
                        source="relation",
                        score_parts=score_parts,
                    )
                if len(expanded_by_chunk) >= MAX_EXPANSION_CANDIDATES:
                    _log_expansion_limit()
                    return list(expanded_by_chunk.values())

    signals_by_chunk = store.signals_for_chunks(reached_chunk_ids)
    for chunk_id in reached_chunk_ids:
        if chunk_id in seen_chunks:
            continue
        seen_chunks.add(chunk_id)
        for signal in signals_by_chunk.get(chunk_id, []):
            if signal.signal_id in visited_signals:
                continue
            parent_score = expanded_by_chunk.get(chunk_id)
            if parent_score is None:
                continue
            relation_seed = _candidate_relation_seed(parent_score)
            queue.append(
                (
                    signal.signal_id,
                    relation_seed.score,
                    next_depth,
                    relation_seed.planner_seeded,
                    relation_seed.original_seeded,
                )
            )
```

Preserve these existing behaviors:

- Skip relations below `_MIN_RELATION_CONFIDENCE`.
- Use `next_score = current_score * relation.confidence * _RELATION_SCORE_DECAY`.
- Preserve `planner_relation` and `original_relation` provenance.
- Preserve `visited_signals`, `seen_chunks`, `MAX_EXPANSION_DEPTH`, and `MAX_EXPANSION_CANDIDATES`.
- Return deterministic candidate order by sorting final candidates with the same tie-breakers already implied by the current traversal.

- [ ] **Step 4: Run focused relation tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py -k "relation_expansion" -q
```

Expected: all relation expansion tests pass.

- [ ] **Step 5: Run retrieval pipeline tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py -q
```

Expected: all retrieval pipeline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "Batch relation expansion traversal"
```

### Task 3: Add Spring Endpoint Path Graph Scoring

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add graph scoring tests for exact route path**

Add a synthetic test:

```python
def test_spring_path_graph_scores_exact_controller_service_and_executor(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    controller = _java_chunk("controller", "src/AppCatalogController.java", ["app", "catalog", "page"])
    service = _java_chunk("service", "src/AppInfoServiceImpl.java", ["app", "info", "service", "page"])
    executor = _java_chunk("executor", "src/PageAppCatalogQueryExe.java", ["page", "app", "catalog"])
    open_controller = _java_chunk("open-controller", "src/AppCatalogOpenController.java", ["open", "app", "catalog", "page"])
    for chunk in (controller, service, executor, open_controller):
        store.replace_chunks(chunk.file_path, [chunk])
    store.replace_signals(
        controller.file_path,
        [CodeSignal("sig-controller", "controller", controller.file_path, "endpoint", "POST /appCatalog/page", 1, 1, "java", tokens=["app", "catalog", "page"], metadata={"path": "/appCatalog/page"})],
    )
    store.replace_signals(
        open_controller.file_path,
        [CodeSignal("sig-open", "open-controller", open_controller.file_path, "endpoint", "POST /openApi/appCatalog/page", 1, 1, "java", tokens=["open", "api", "app", "catalog", "page"], metadata={"path": "/openApi/appCatalog/page"})],
    )
    store.replace_signals(
        service.file_path,
        [CodeSignal("sig-service", "service", service.file_path, "method", "AppInfoServiceImpl.page", 1, 1, "java", tokens=["app", "info", "page"])],
    )
    store.replace_signals(
        executor.file_path,
        [CodeSignal("sig-executor", "executor", executor.file_path, "method", "PageAppCatalogQueryExe.execute", 1, 1, "java", tokens=["page", "app", "catalog"])],
    )
    store.replace_relations(
        [
            CodeRelation("rel-service", "sig-controller", "AppInfoServiceImpl.page", "calls", 1.0),
            CodeRelation("rel-executor", "sig-service", "PageAppCatalogQueryExe.execute", "calls", 1.0),
        ]
    )

    candidates = retrieval._merge_candidates(
        [
            RetrievalCandidate("controller", 0.8, "signal", {"signal": 0.8}),
            RetrievalCandidate("open-controller", 1.0, "signal", {"signal": 1.0}),
            RetrievalCandidate("service", 0.5, "semantic", {"semantic": 0.5}),
            RetrievalCandidate("executor", 0.5, "semantic", {"semantic": 0.5}),
        ]
    )
    ranked = retrieval._rank_chunks(
        store,
        candidates,
        ["app", "catalog", "page", "can", "apply"],
        "/appCatalog/page canApply",
    )

    positions = {item.chunk.chunk_id: index for index, item in enumerate(ranked)}
    assert positions["controller"] < positions["open-controller"]
    assert ranked[positions["controller"]].score_parts["spring_path_endpoint_match"] == 0.45
    assert ranked[positions["service"]].score_parts["spring_path_service_match"] == 0.30
    assert ranked[positions["executor"]].score_parts["spring_path_executor_match"] == 0.28
    assert "spring_path_endpoint_match" not in ranked[positions["open-controller"]].score_parts
```

- [ ] **Step 2: Verify graph test fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py::test_spring_path_graph_scores_exact_controller_service_and_executor -q
```

Expected: fails because the `spring_path_*` score parts do not exist.

- [ ] **Step 3: Implement path graph helper**

Add small constants near existing route constants:

```python
_SPRING_PATH_ENDPOINT_BOOST = 0.45
_SPRING_PATH_SERVICE_BOOST = 0.30
_SPRING_PATH_EXECUTOR_BOOST = 0.28
_SPRING_PATH_MAX_DEPTH = 2
```

Add helper:

```python
def _spring_path_score_parts(
    store: SQLiteStore,
    candidate_chunks: dict[str, DocumentChunk],
    query_route: str,
) -> dict[str, dict[str, float]]:
    if not query_route:
        return {}
    chunk_ids = list(candidate_chunks)
    signals_by_chunk = store.signals_for_chunks(chunk_ids)
    exact_endpoint_signals = [
        signal
        for signals in signals_by_chunk.values()
        for signal in signals
        if signal.kind == "endpoint"
        and isinstance(signal.metadata.get("path"), str)
        and _normalize_route(signal.metadata["path"]) == query_route
    ]
    if not exact_endpoint_signals:
        return {}
    parts_by_chunk: dict[str, dict[str, float]] = {}
    for signal in exact_endpoint_signals:
        parts_by_chunk.setdefault(signal.chunk_id, {})["spring_path_endpoint_match"] = _SPRING_PATH_ENDPOINT_BOOST
    queue: deque[tuple[str, int]] = deque(
        (signal.signal_id, 0) for signal in exact_endpoint_signals
    )
    visited_signals = {signal.signal_id for signal in exact_endpoint_signals}
    while queue:
        current_level = list(queue)
        queue.clear()
        source_ids = [
            source_signal_id
            for source_signal_id, depth in current_level
            if depth < _SPRING_PATH_MAX_DEPTH
        ]
        relations_by_source = store.relations_for_sources(source_ids)
        target_names = [
            relation.target_name
            for source_signal_id in source_ids
            for relation in relations_by_source.get(source_signal_id, [])
            if relation.confidence >= _MIN_RELATION_CONFIDENCE
        ]
        chunks_by_target = store.chunks_matching_signal_or_symbols(
            target_names,
            limit_per_target=MAX_EXPANSION_CANDIDATES,
        )
        next_chunk_ids: list[str] = []
        for source_signal_id, depth in current_level:
            next_depth = depth + 1
            for relation in relations_by_source.get(source_signal_id, []):
                if relation.confidence < _MIN_RELATION_CONFIDENCE:
                    continue
                for chunk in chunks_by_target.get(relation.target_name, []):
                    if chunk.chunk_id not in candidate_chunks:
                        continue
                    role = _chunk_role(chunk)
                    chunk_parts = parts_by_chunk.setdefault(chunk.chunk_id, {})
                    if next_depth == 1 and role.name == "service_impl":
                        chunk_parts["spring_path_service_match"] = max(
                            chunk_parts.get("spring_path_service_match", 0.0),
                            _SPRING_PATH_SERVICE_BOOST,
                        )
                    elif next_depth == 1 and role.name == "service_interface":
                        chunk_parts["spring_path_service_interface_match"] = max(
                            chunk_parts.get("spring_path_service_interface_match", 0.0),
                            _SPRING_PATH_SERVICE_INTERFACE_BOOST,
                        )
                    elif role.name == "executor":
                        chunk_parts["spring_path_executor_match"] = max(
                            chunk_parts.get("spring_path_executor_match", 0.0),
                            _SPRING_PATH_EXECUTOR_BOOST,
                        )
                    next_chunk_ids.append(chunk.chunk_id)
        signals_by_chunk = store.signals_for_chunks(next_chunk_ids)
        for chunk_id in next_chunk_ids:
            for signal in signals_by_chunk.get(chunk_id, []):
                if signal.signal_id in visited_signals:
                    continue
                visited_signals.add(signal.signal_id)
                queue.append((signal.signal_id, next_depth))
    return parts_by_chunk
```

Use the batched traversal from Task 2 and `_chunk_role` to decide which score part to add:

- depth 1 and role `service_impl`: `spring_path_service_match`.
- depth 1 and role `service_interface`: `spring_path_service_interface_match` with a lower value `0.10`.
- depth 1 or 2 and role `executor`: `spring_path_executor_match`.

- [ ] **Step 4: Wire graph parts into `_rank_chunks`**

At the start of `_rank_chunks`, after loading candidate chunks, compute graph parts once:

```python
candidate_chunks = store.chunks_for_ids(list(candidates))
spring_path_parts = _spring_path_score_parts(store, candidate_chunks, query_route)
```

Then use `candidate_chunks` instead of calling `store.chunk_for_id` per candidate when possible. Inside the candidate loop:

```python
chunk = candidate_chunks.get(candidate.chunk_id)
if chunk is None:
    continue
score_parts = dict(candidate.score_parts)
score_parts.update(spring_path_parts.get(candidate.chunk_id, {}))
```

- [ ] **Step 5: Add graph parts to combined score, rerank score, and reasons**

Update `_combined_score`:

```python
+ score_parts.get("spring_path_endpoint_match", 0.0)
+ score_parts.get("spring_path_service_match", 0.0)
+ score_parts.get("spring_path_service_interface_match", 0.0)
+ score_parts.get("spring_path_executor_match", 0.0)
```

Update `_rerank_score` with the same values so the final sort can see the graph signal.

Update `_reasons`:

```python
if score_parts.get("spring_path_endpoint_match", 0.0) > 0:
    reasons.append("Spring endpoint path match")
if score_parts.get("spring_path_service_match", 0.0) > 0:
    reasons.append("Spring service implementation path match")
if score_parts.get("spring_path_executor_match", 0.0) > 0:
    reasons.append("Spring executor path match")
```

- [ ] **Step 6: Run focused graph tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_retrieval_pipeline.py -k "spring_path_graph or route_rerank or route_java_context" -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "Add Spring endpoint path graph reranking"
```

### Task 4: Add Real-Project Profiling Helper

**Files:**
- Create: `scripts/profile_retrieval.py`
- Test: no unit test required; this is a local diagnostic script.

- [ ] **Step 1: Create a small profiling script**

Create `scripts/profile_retrieval.py`:

```python
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import time

from context_search_tool.config import load_config
from context_search_tool import retrieval
from context_search_tool.sqlite_store import SQLiteStore


PROFILED_FUNCTIONS = [
    "_semantic_candidates",
    "_lexical_candidates",
    "_direct_text_candidates",
    "_signal_candidates",
    "_planner_hint_candidates",
    "_anchor_expansion_candidates",
    "_relation_expansion_candidates",
    "_rank_chunks",
    "_expand_ranked_chunks",
    "_split_code_results_and_evidence_anchors",
    "_summarize_results",
]

PROFILED_STORE_METHODS = [
    "deleted_chunk_ids",
    "signal_search",
    "path_symbol_search",
    "signals_for_chunk",
    "signals_for_chunks",
    "relations_for_source",
    "relations_for_sources",
    "chunks_matching_signal_or_symbol",
    "chunks_matching_signal_or_symbols",
    "chunk_for_id",
    "chunks_for_ids",
    "chunks_for_file",
    "chunks_in_directory",
    "lexical_search",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("query")
    args = parser.parse_args()
    timings: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    originals: dict[str, object] = {}

    def wrap_module_function(name: str) -> None:
        fn = getattr(retrieval, name)
        originals[f"retrieval.{name}"] = fn

        def inner(*fn_args, **fn_kwargs):
            start = time.perf_counter()
            try:
                return fn(*fn_args, **fn_kwargs)
            finally:
                timings[name] += time.perf_counter() - start
                counts[name] += 1

        setattr(retrieval, name, inner)

    def wrap_store_method(name: str) -> None:
        if not hasattr(SQLiteStore, name):
            return
        fn = getattr(SQLiteStore, name)
        originals[f"store.{name}"] = fn

        def inner(self, *fn_args, **fn_kwargs):
            start = time.perf_counter()
            try:
                return fn(self, *fn_args, **fn_kwargs)
            finally:
                timings[f"store.{name}"] += time.perf_counter() - start
                counts[f"store.{name}"] += 1

        setattr(SQLiteStore, name, inner)

    for name in PROFILED_FUNCTIONS:
        wrap_module_function(name)
    for name in PROFILED_STORE_METHODS:
        wrap_store_method(name)

    start = time.perf_counter()
    try:
        bundle = retrieval.query_repository(args.repo, args.query, load_config(args.repo))
    finally:
        total = time.perf_counter() - start
        for key, fn in originals.items():
            owner, name = key.split(".", 1)
            if owner == "retrieval":
                setattr(retrieval, name, fn)
            else:
                setattr(SQLiteStore, name, fn)

    print(f"total_ms={total * 1000:.1f} results={len(bundle.results)}")
    for name, seconds in sorted(timings.items(), key=lambda item: -item[1]):
        print(f"{name}: {seconds * 1000:.1f}ms calls={counts[name]}")
    print("top:")
    for index, result in enumerate(bundle.results[:5], 1):
        print(f"{index}. {result.file_path}:{result.start_line}-{result.end_line} score={result.score:.4f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run helper on one indexed temporary repo**

Run:

```bash
.venv/bin/python scripts/profile_retrieval.py /private/tmp/cst-real-compare-20260617134449/irs-catalog-base "/appCatalog/page canApply"
```

Expected: prints per-stage timings and top results.

- [ ] **Step 3: Commit**

```bash
git add scripts/profile_retrieval.py
git commit -m "Add retrieval profiling helper"
```

### Task 5: Real-Project Validation And Fast-Context Comparison

**Files:**
- Modify only if validation exposes a bug: `src/context_search_tool/retrieval.py`, `src/context_search_tool/sqlite_store.py`, or tests.

- [ ] **Step 1: Run focused tests**

```bash
.venv/bin/python -m pytest tests/test_sqlite_store.py tests/test_retrieval_pipeline.py -q
```

Expected: pass.

- [ ] **Step 2: Run core retrieval tests**

```bash
.venv/bin/python -m pytest tests/test_acceptance_java_fixture.py tests/test_retrieval_pipeline.py tests/test_rerank_soft_sorting.py -q
```

Expected: pass.

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: pass, with only expected skips.

- [ ] **Step 4: Reuse or recreate BGE-M3 real-project temporary copies**

Use temporary copies to avoid modifying `/Users/flobby/work/code/irs-catalog-base` and `/Users/flobby/work/code/irs-portal-base`.

If the previous temporary directory still exists and indexes are current, reuse:

```bash
ls /private/tmp/cst-real-compare-20260617134449/irs-catalog-base/.context-search
ls /private/tmp/cst-real-compare-20260617134449/irs-portal-base/.context-search
```

If it does not exist, recreate the temporary copies and set BGE-M3 config before indexing.

- [ ] **Step 5: Profile the two real cases**

```bash
.venv/bin/python scripts/profile_retrieval.py /private/tmp/cst-real-compare-20260617134449/irs-catalog-base "/appCatalog/page canApply"
.venv/bin/python scripts/profile_retrieval.py /private/tmp/cst-real-compare-20260617134449/irs-portal-base "/apply/audit/pageEs INVOLVED_BY_ME"
```

Expected:

- `store.relations_for_sources` call count is small and bounded by traversal depth.
- `store.chunks_matching_signal_or_symbols` call count is small and bounded by traversal depth.
- The old single-key relation calls are zero or near zero in relation expansion.
- Top results still satisfy the two real-project acceptance criteria.

- [ ] **Step 6: Compare with fast-context**

Run fast-context with these parameters:

```text
project_path=/Users/flobby/work/code/irs-catalog-base
query=/appCatalog/page canApply
tree_depth=3
max_turns=3
max_results=10
include_code_snippets=false
```

```text
project_path=/Users/flobby/work/code/irs-portal-base
query=/apply/audit/pageEs INVOLVED_BY_ME
tree_depth=3
max_turns=3
max_results=12
include_code_snippets=false
```

Expected comparison notes:

- For catalog, CST should keep exact `AppCatalogController` ahead of `AppCatalogOpenController`.
- For portal, CST should keep `ResourceApplyAuditController`, `EsApplyAuditPageQryExe`, and `ResourceAuditServiceImpl` in the early result window.
- If fast-context higher-turn runs fail with `resource_exhausted`, record that explicitly rather than retrying until the comparison becomes noisy.

- [ ] **Step 7: Commit any validation fix**

If validation exposes a bug and a fix is needed:

```bash
git add src/context_search_tool/retrieval.py src/context_search_tool/sqlite_store.py tests/test_retrieval_pipeline.py tests/test_sqlite_store.py
git commit -m "Validate Spring path graph retrieval on real projects"
```

If validation passes without code changes, do not create an empty commit.

## 7. Risks And Guardrails

- **Risk: batching changes traversal order.** Guard with existing relation expansion tests and explicit deterministic ordering assertions.
- **Risk: graph scoring becomes another hardcoded boost pile.** Keep graph scoring route/signal/relation/role based; production code must not mention real business names.
- **Risk: batch target matching still loops per target inside one connection.** This is acceptable for Task 1, but profile after Task 2. If it still dominates, add a second plan to index target-name lookup tables or implement a true multi-target SQL query.
- **Risk: service interface disappears.** It should remain retrievable, but implementation path should rank higher for endpoint-path queries.
- **Risk: wall-clock timing flakes.** CI tests should assert call shape and ranking, not hard timing. Real-project profiling is a manual acceptance artifact.

## 8. Suggested Execution Mode

Use subagent-driven development:

1. Store batch APIs.
2. Batched relation expansion.
3. Spring path graph scoring.
4. Profiling helper.
5. Real-project validation and fast-context comparison.

Run spec review and code-quality review after each task because the risk profile alternates between performance semantics and ranking behavior.
