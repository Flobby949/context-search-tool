# P1 Query Understanding Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close roadmap Phase 1 by searching the vector index with the original query plus bounded planner rewrites, preserving per-variant semantic provenance, and proving hybrid recall improves cross-language queries without weakening exact retrieval.

**Architecture:** Keep planning as the single pre-retrieval planning pass. Build an ordered list of public QueryVariant values, invoke EmbeddingProvider.embed_texts once for that list, search the existing NumpyVectorStore once per returned vector, and merge candidates by chunk while retaining SemanticMatch provenance. Carry provenance through ranking and context merging, expose it additively in JSON/MCP and quality reports, and protect exact original evidence with the existing ceiling plus a corrected tie-break.

**Tech Stack:** Python 3.11+, frozen dataclasses, NumPy vector search, existing Ollama-backed BGE-M3 and Qwen planner providers, Typer/MCP JSON contracts, pytest, and the canonical retrieval-quality fixture.

---

## Planning Constraints

- Treat docs/superpowers/specs/2026-07-13-p1-query-understanding-closure-design.md as authoritative.
- Do not add a translation lexicon, language detector, preliminary vector pass, second planner request, reranker, ContextPack, RetrievalTrace, or provider auto-selection.
- Do not add user configuration. The planner semantic weight is an internal constant.
- Preserve the existing embedding-provider and vector-store APIs. BGE may continue splitting one embed_texts call into transport batches internally.
- Keep planner-disabled, planner-fallback, and planner-empty behavior on the original-query vector path.
- Retry only the original query after a multi-variant embedding call fails. If that retry fails, or index compatibility fails, propagate the existing query error.
- Keep QueryBundle defaults backward compatible, but include the original QueryVariant in every real query_repository return, including empty-result returns.
- Use an initial internal planner semantic weight of 0.85. This is below the original semantic contribution, lets a materially stronger rewrite replace weak original similarity, and is accepted only if the Phase 1 profile-pair gate passes. A different value requires a design/plan checkpoint.
- Do not mark the roadmap Phase 1 complete until both model-backed Phase 1 profiles execute and the focused acceptance test passes. Missing BGE or Qwen is unverified_dependency, not completion.

## File Map

**Public contracts and query preparation**

- Modify: src/context_search_tool/models.py
  - add QueryVariant and SemanticMatch;
  - add default-empty semantic_matches to RetrievalCandidate, RetrievalResult, and EvidenceAnchor.
- Modify: src/context_search_tool/query_planner.py
  - normalize, length-check, deduplicate, and cap rewrite variants in the specified order;
  - expose build_query_variants for runtime validation and stable IDs.
- Test: tests/test_query_planner.py

**Retrieval, ranking, and provenance**

- Modify: src/context_search_tool/retrieval.py
  - add QueryBundle variant fields;
  - batch-embed variants, run per-variant searches, and retry original-only after a variant batch failure;
  - merge SemanticMatch values through candidates, ranked chunks, expanded results, and evidence anchors;
  - add planner semantic max/effective scoring and the corrected evidence/tie ordering.
- Test: tests/test_retrieval_pipeline.py
- Test: tests/test_rerank_soft_sorting.py
- Modify: tests/test_quality_catalog.py
  - update its private candidate-pool helper for the new _initial_candidates return contract.

**CLI, MCP, and privacy**

- Modify: src/context_search_tool/formatters.py
- Modify: src/context_search_tool/mcp_tools.py
- Test: tests/test_formatters.py
- Test: tests/test_mcp_tools.py

**Quality schema, gates, and reports**

- Modify: src/context_search_tool/quality/cases.py
  - add typed profile expectations and exact Phase 1 profile validation.
- Modify: src/context_search_tool/quality/metrics.py
  - retain semantic matches in normalized top-result records.
- Modify: src/context_search_tool/quality/runner.py
  - gate cases on profile expectations and serialize executed variants/status.
- Test: tests/test_quality_cases.py
- Test: tests/test_quality_metrics.py
- Test: tests/test_quality_runner.py

**Canonical cases, model acceptance, and handoff**

- Modify: tests/fixtures/retrieval_quality/queries.json
- Modify: tests/test_quality_catalog.py
- Create: tests/test_quality_p1.py
- Modify: docs/retrieval-quality.md
- Modify after model-backed acceptance only: roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md

**Explicitly unchanged**

- src/context_search_tool/config.py
- src/context_search_tool/embeddings.py
- src/context_search_tool/embeddings_bge.py
- src/context_search_tool/vector_store.py
- src/context_search_tool/quality/compare.py

## Success Criteria

1. Variant construction follows normalize → 256-code-point validation → case-insensitive deduplication → count limit → stable ID assignment.
2. A successful hybrid query makes one planner call, one retrieval-layer embed_texts call, and one vector search per executed variant.
3. Duplicate variants cannot inflate score; planner semantic blending is max-based and preserves negative similarities.
4. Semantic matches survive candidate merging, adjacent-chunk merging, final RetrievalResult creation, and EvidenceAnchor creation.
5. Strong original exact evidence remains protected; weak original and direct planner evidence share priority, with pre-ceiling score breaking ceiling ties.
6. JSON, MCP, quality reports, and raw MCP feedback satisfy the additive provenance and privacy contracts.
7. The canonical p1_vector_bge and p1_hybrid_bge profiles select the same seven required committed-snapshot cases.
8. Full tests and ci pass, both P1 profiles execute and pass, and the focused pair gate reports no negative MRR, Recall@5, or entrypoint Top3 delta.

### Task 1: Establish the public variant contract and exact rewrite cleanup

**Files:**

- Modify: src/context_search_tool/models.py
- Modify: src/context_search_tool/query_planner.py
- Modify: tests/test_query_planner.py

- [ ] **Step 1: Record the pre-change baseline**

Run:

~~~bash
conda run -n base python -m pytest -q
~~~

Expected: PASS with the design baseline (1121 passed, 3 skipped) or a newer clean baseline if unrelated committed tests were added before execution. Stop if any existing test fails.

- [ ] **Step 2: Write failing model and variant-construction tests**

Add QueryVariant to the imports in tests/test_query_planner.py and add:

~~~python
def test_build_query_variants_normalizes_dedupes_bounds_and_assigns_stable_ids() -> None:
    overlong = "x" * 257
    plan = QueryPlan(
        original_query="  Data   Dashboard  ",
        rewritten_queries=[
            overlong,
            "data dashboard",
            "  dashboard   statistics  ",
            "DASHBOARD STATISTICS",
            "chart service",
            "ignored after limit",
        ],
        status="ok",
    )

    variants, discarded = build_query_variants(
        "  Data   Dashboard  ",
        plan,
        max_rewritten_queries=2,
    )

    assert variants == [
        QueryVariant(
            variant_id="original",
            text="Data Dashboard",
            source="original",
        ),
        QueryVariant(
            variant_id="planner:0",
            text="dashboard statistics",
            source="planner",
        ),
        QueryVariant(
            variant_id="planner:1",
            text="chart service",
            source="planner",
        ),
    ]
    assert discarded == [overlong]


@pytest.mark.parametrize("status", ["disabled", "fallback"])
def test_build_query_variants_uses_original_only_unless_plan_is_ok(status: str) -> None:
    variants, discarded = build_query_variants(
        "  target   query ",
        QueryPlan(
            original_query="target query",
            rewritten_queries=["planner rewrite"],
            status=status,
        ),
        max_rewritten_queries=4,
    )

    assert variants == [
        QueryVariant("original", "target query", "original"),
    ]
    assert discarded == []


def test_build_query_variants_ok_without_rewrites_is_original_only() -> None:
    variants, discarded = build_query_variants(
        "query",
        QueryPlan(original_query="query", status="ok"),
        max_rewritten_queries=4,
    )

    assert variants == [QueryVariant("original", "query", "original")]
    assert discarded == []


def test_build_query_variants_accepts_256_code_points_without_truncation() -> None:
    accepted = "界" * 256
    variants, discarded = build_query_variants(
        "query",
        QueryPlan(
            original_query="query",
            rewritten_queries=[accepted],
            status="ok",
        ),
        max_rewritten_queries=4,
    )

    assert variants[1].text == accepted
    assert discarded == []


def test_clean_planner_payload_discards_overlong_rewrite_before_count_limit() -> None:
    overlong = "x" * 257
    plan = clean_planner_payload(
        original_query="target",
        payload={
            "rewritten_queries": [
                overlong,
                "target",
                "first valid",
                "second valid",
                "third valid",
            ],
            "grep_keywords": [],
            "symbol_hints": [],
            "intent": "feature_lookup",
        },
        config=QueryPlannerConfig(max_rewritten_queries=2),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=1,
    )

    assert plan.status == "ok"
    assert plan.rewritten_queries == ["first valid", "second valid"]
    assert plan.discarded_hints == [overlong]
~~~

Also extend the existing default-constructor test to assert that new semantic provenance fields default to empty lists:

~~~python
def test_semantic_provenance_models_keep_existing_constructors_compatible() -> None:
    candidate = RetrievalCandidate("chunk", 0.4, "lexical")
    result = RetrievalResult(
        file_path=Path("App.py"),
        start_line=1,
        end_line=1,
        content="pass",
        score=0.4,
        score_parts={},
        reasons=[],
        followup_keywords=[],
    )
    anchor = EvidenceAnchor(
        file_path=Path("README.md"),
        start_line=1,
        end_line=1,
        content="docs",
        score=0.1,
        score_parts={},
        reasons=[],
        anchor_kind="document",
    )

    assert candidate.semantic_matches == []
    assert result.semantic_matches == []
    assert anchor.semantic_matches == []
~~~

Import Path, EvidenceAnchor, RetrievalCandidate, and RetrievalResult for that test.

- [ ] **Step 3: Run the new tests and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_query_planner.py::test_build_query_variants_normalizes_dedupes_bounds_and_assigns_stable_ids \
  tests/test_query_planner.py::test_build_query_variants_uses_original_only_unless_plan_is_ok \
  tests/test_query_planner.py::test_build_query_variants_ok_without_rewrites_is_original_only \
  tests/test_query_planner.py::test_build_query_variants_accepts_256_code_points_without_truncation \
  tests/test_query_planner.py::test_clean_planner_payload_discards_overlong_rewrite_before_count_limit \
  tests/test_query_planner.py::test_semantic_provenance_models_keep_existing_constructors_compatible \
  -q
~~~

Expected: FAIL because QueryVariant, SemanticMatch, semantic_matches, and build_query_variants do not exist.

- [ ] **Step 4: Add the public data models and default-empty provenance**

In src/context_search_tool/models.py, add these frozen dataclasses after QueryPlan:

~~~python
@dataclass(frozen=True)
class QueryVariant:
    variant_id: str
    text: str
    source: str


@dataclass(frozen=True)
class SemanticMatch:
    variant_id: str
    score: float
~~~

Add the following final field to RetrievalCandidate, RetrievalResult, and EvidenceAnchor:

~~~python
semantic_matches: list[SemanticMatch] = field(default_factory=list)
~~~

Keep the field last so all existing constructors remain valid.

- [ ] **Step 5: Implement one shared normalization/validation path**

In src/context_search_tool/query_planner.py, import QueryVariant and define:

~~~python
MAX_PLANNER_QUERY_VARIANT_CODEPOINTS = 256


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
~~~

In clean_planner_payload, validate rewritten_queries before grep/symbol cleanup and use the same helper:

~~~python
raw_rewritten_queries = payload.get("rewritten_queries", [])
if not isinstance(raw_rewritten_queries, list):
    raise ValueError("rewritten_queries must be a list")
rewritten_queries, discarded_rewrites = _retain_rewritten_queries(
    original_query,
    raw_rewritten_queries,
    config.max_rewritten_queries,
)
~~~

Place this inside the existing try block. Initialize discarded_hints with the rejected overlong rewrites before appending repository-filtered drops:

~~~python
discarded_hints: list[str] = list(discarded_rewrites)
~~~

Keep _clean_string_list unchanged for grep_keywords and symbol_hints. This preserves their existing behavior while making rewrite ordering exact and reusable by custom/fake planners at runtime.

- [ ] **Step 6: Run focused and full planner tests**

Run:

~~~bash
conda run -n base python -m pytest tests/test_query_planner.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Commit**

~~~bash
git add \
  src/context_search_tool/models.py \
  src/context_search_tool/query_planner.py \
  tests/test_query_planner.py
git commit -m "feat: define bounded semantic query variants"
~~~

### Task 2: Batch semantic recall and original-only embedding fallback

**Files:**

- Modify: src/context_search_tool/retrieval.py
- Modify: tests/test_retrieval_pipeline.py
- Modify: tests/test_quality_catalog.py

- [ ] **Step 1: Write failing batch, search-count, merge, and fallback tests**

In tests/test_retrieval_pipeline.py, import QueryVariant, SemanticMatch, and VectorSearchResult. Add controlled fakes:

~~~python
class CapturingEmbeddingProvider:
    def __init__(self, vectors: list[list[float]], fail_multi: bool = False) -> None:
        self.vectors = [np.asarray(vector, dtype=np.float32) for vector in vectors]
        self.fail_multi = fail_multi
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        self.calls.append(list(texts))
        if self.fail_multi and len(texts) > 1:
            raise RuntimeError("variant batch failed")
        return self.vectors[: len(texts)]


class CapturingVectorStore:
    def __init__(self, results_by_vector: dict[tuple[float, ...], list[VectorSearchResult]]) -> None:
        self.results_by_vector = results_by_vector
        self.calls: list[tuple[tuple[float, ...], int, set[str]]] = []

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        deleted_ids: set[str],
    ) -> list[VectorSearchResult]:
        key = tuple(float(value) for value in query_vector)
        self.calls.append((key, top_k, set(deleted_ids)))
        return self.results_by_vector[key]
~~~

Add:

~~~python
def test_semantic_candidates_embeds_once_searches_each_variant_and_merges_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variants = [
        QueryVariant("original", "原始查询", "original"),
        QueryVariant("planner:0", "dashboard statistics", "planner"),
        QueryVariant("planner:1", "chart service", "planner"),
    ]
    provider = CapturingEmbeddingProvider([[1, 0], [0, 1], [-1, 0]])
    vector_store = CapturingVectorStore(
        {
            (1.0, 0.0): [VectorSearchResult("shared", 0.20)],
            (0.0, 1.0): [VectorSearchResult("shared", 0.84)],
            (-1.0, 0.0): [VectorSearchResult("shared", 0.60)],
        }
    )
    monkeypatch.setattr(retrieval, "provider_from_config", lambda config: provider)
    monkeypatch.setattr(retrieval, "NumpyVectorStore", lambda index_dir: vector_store)

    candidates, executed, status = retrieval._semantic_candidates(
        tmp_path,
        variants,
        DEFAULT_CONFIG,
        set(),
    )
    merged = retrieval._merge_candidates(candidates)["shared"]

    assert provider.calls == [[
        "原始查询",
        "dashboard statistics",
        "chart service",
    ]]
    assert len(vector_store.calls) == 3
    assert executed == variants
    assert status == "hybrid"
    assert merged.score_parts == {
        "semantic": 0.20,
        "planner_semantic": 0.84,
    }
    assert merged.semantic_matches == [
        SemanticMatch("original", 0.20),
        SemanticMatch("planner:0", 0.84),
        SemanticMatch("planner:1", 0.60),
    ]


def test_semantic_candidates_retries_original_once_after_variant_batch_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variants = [
        QueryVariant("original", "query", "original"),
        QueryVariant("planner:0", "rewrite", "planner"),
    ]
    provider = CapturingEmbeddingProvider([[1, 0], [0, 1]], fail_multi=True)
    vector_store = CapturingVectorStore(
        {(1.0, 0.0): [VectorSearchResult("original-hit", 0.75)]}
    )
    monkeypatch.setattr(retrieval, "provider_from_config", lambda config: provider)
    monkeypatch.setattr(retrieval, "NumpyVectorStore", lambda index_dir: vector_store)

    candidates, executed, status = retrieval._semantic_candidates(
        tmp_path,
        variants,
        DEFAULT_CONFIG,
        set(),
    )

    assert provider.calls == [["query", "rewrite"], ["query"]]
    assert executed == [variants[0]]
    assert status == "embedding_fallback"
    assert [candidate.chunk_id for candidate in candidates] == ["original-hit"]
    assert candidates[0].semantic_matches == [SemanticMatch("original", 0.75)]


def test_semantic_candidates_propagates_original_retry_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AlwaysFailingProvider:
        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            raise RuntimeError(f"failed for {len(texts)}")

    monkeypatch.setattr(
        retrieval,
        "provider_from_config",
        lambda config: AlwaysFailingProvider(),
    )

    with pytest.raises(RuntimeError, match="failed for 1"):
        retrieval._semantic_candidates(
            tmp_path,
            [
                QueryVariant("original", "query", "original"),
                QueryVariant("planner:0", "rewrite", "planner"),
            ],
            DEFAULT_CONFIG,
            set(),
        )
~~~

Add direct cardinality regressions for both validation boundaries:

- `test_semantic_candidates_retries_original_after_variant_batch_count_mismatch`
  must prove a short multi-variant embedding response performs exactly one
  original-only retry, searches no partial variant batch, and reports
  `embedding_fallback` with original provenance;
- `test_semantic_candidates_propagates_original_retry_count_mismatch` must
  prove a short response from that original retry raises instead of returning
  a partial or empty success.

Each test must mutation-kill removal of its corresponding count check.

Add NumPy as np to the test imports. Import QueryVariant in both
tests/test_retrieval_pipeline.py and tests/test_quality_catalog.py because both
private candidate-pool helpers now construct the public original variant.

- [ ] **Step 2: Run the new tests and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py::test_semantic_candidates_embeds_once_searches_each_variant_and_merges_provenance \
  tests/test_retrieval_pipeline.py::test_semantic_candidates_retries_original_once_after_variant_batch_failure \
  tests/test_retrieval_pipeline.py::test_semantic_candidates_propagates_original_retry_failure \
  -q
~~~

Expected: FAIL because _semantic_candidates still accepts one query string and does not return executed variants/status.

- [ ] **Step 3: Add QueryBundle execution fields and build runtime variants**

In src/context_search_tool/retrieval.py:

- import replace from dataclasses;
- import QueryVariant and SemanticMatch from models;
- import build_query_variants from query_planner.

Add final defaulted fields to QueryBundle:

~~~python
query_variants: list[QueryVariant] = field(default_factory=list)
variant_retrieval_status: str = "original_only"
~~~

At the start of query_repository, create the original-only value used by early returns:

~~~python
query_variants = [QueryVariant("original", " ".join(query.split()), "original")]
variant_retrieval_status = "original_only"
~~~

After the planner returns:

~~~python
query_variants, discarded_variants = build_query_variants(
    query,
    plan,
    config.query_planner.max_rewritten_queries,
)
if discarded_variants:
    plan = replace(
        plan,
        discarded_hints=_ordered_unique(
            [*plan.discarded_hints, *discarded_variants]
        ),
    )
~~~

Pass query_variants and variant_retrieval_status into every QueryBundle return. Before planning or retrieval has run, use the original-only values above.

- [ ] **Step 4: Replace single-query semantic recall with one batch and per-vector search**

Replace _semantic_candidates with:

~~~python
def _semantic_candidates(
    index_dir: Path,
    variants: list[QueryVariant],
    config: ToolConfig,
    deleted_ids: set[str],
) -> tuple[list[RetrievalCandidate], list[QueryVariant], str]:
    provider = provider_from_config(config.embedding)
    vector_store = NumpyVectorStore(index_dir)

    try:
        vectors = provider.embed_texts([variant.text for variant in variants])
        if len(vectors) != len(variants):
            raise ValueError(
                "embedding response count does not match query variant count"
            )
        executed_variants = variants
        status = "hybrid" if len(variants) > 1 else "original_only"
    except Exception:
        if len(variants) == 1:
            raise
        executed_variants = variants[:1]
        vectors = provider.embed_texts([executed_variants[0].text])
        if len(vectors) != 1:
            raise ValueError(
                "embedding response count does not match original query"
            )
        status = "embedding_fallback"

    candidates: list[RetrievalCandidate] = []
    for variant, vector in zip(executed_variants, vectors):
        score_key = "semantic" if variant.source == "original" else "planner_semantic"
        source = "semantic" if variant.source == "original" else "planner_semantic"
        candidates.extend(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                score=item.score,
                source=source,
                score_parts={score_key: item.score},
                semantic_matches=[
                    SemanticMatch(variant_id=variant.variant_id, score=item.score)
                ],
            )
            for item in vector_store.search(
                vector,
                config.retrieval.semantic_top_k,
                deleted_ids,
            )
        )
    return candidates, executed_variants, status
~~~

The broad Exception catch is deliberately scoped only to the multi-text embedding invocation and its result-count validation. NumpyVectorStore construction/search stays outside that catch, so index incompatibility is not converted into a fallback. The original-only retry is allowed to raise normally.

- [ ] **Step 5: Return execution metadata from _initial_candidates**

Change _initial_candidates to accept variants and return a tuple:

~~~python
def _initial_candidates(
    index_dir: Path,
    store: SQLiteStore,
    query: str,
    original_tokens: list[str],
    query_variants: list[QueryVariant],
    config: ToolConfig,
    deleted_ids: set[str],
) -> tuple[list[RetrievalCandidate], list[QueryVariant], str]:
    semantic, executed_variants, status = _semantic_candidates(
        index_dir,
        query_variants,
        config,
        deleted_ids,
    )
    return (
        [
            *semantic,
            *_lexical_candidates(
                store,
                original_tokens,
                config.retrieval.lexical_top_k,
            ),
            *store.path_symbol_search(
                original_tokens,
                config.retrieval.lexical_top_k,
            ),
            *_direct_text_candidates(store, query, original_tokens, config),
        ],
        executed_variants,
        status,
    )
~~~

Update query_repository:

~~~python
(
    initial_candidates,
    query_variants,
    variant_retrieval_status,
) = _initial_candidates(
    index_dir,
    store,
    query,
    original_tokens,
    query_variants,
    config,
    deleted_ids,
)
~~~

Update the private _candidate_pool_paths_before_rerank helpers in tests/test_retrieval_pipeline.py and tests/test_quality_catalog.py to pass one original QueryVariant and unpack only the candidate list:

~~~python
initial_candidates, _, _ = retrieval._initial_candidates(
    index_dir,
    store,
    query,
    original_tokens,
    [QueryVariant("original", " ".join(query.split()), "original")],
    config,
    deleted_ids,
)
~~~

- [ ] **Step 6: Merge per-variant provenance by maximum score**

Add:

~~~python
def _merge_semantic_matches(
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
~~~

In both branches of _merge_candidates, set semantic_matches. The existing-candidate branch must use:

~~~python
semantic_matches=_merge_semantic_matches(
    existing.semantic_matches,
    candidate.semantic_matches,
),
~~~

Extend _normalized_score_parts:

~~~python
if candidate.source == "planner_semantic":
    return {
        "planner_semantic": candidate.score_parts.get(
            "planner_semantic",
            candidate.score,
        )
    }
~~~

- [ ] **Step 7: Run focused retrieval tests**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py::test_semantic_candidates_embeds_once_searches_each_variant_and_merges_provenance \
  tests/test_retrieval_pipeline.py::test_semantic_candidates_retries_original_once_after_variant_batch_failure \
  tests/test_retrieval_pipeline.py::test_semantic_candidates_propagates_original_retry_failure \
  -q
~~~

Expected: PASS.

- [ ] **Step 8: Commit**

~~~bash
git add \
  src/context_search_tool/retrieval.py \
  tests/test_retrieval_pipeline.py \
  tests/test_quality_catalog.py
git commit -m "feat: search semantic query variants in one batch"
~~~

### Task 3: Carry semantic provenance through ranking and context merging

**Files:**

- Modify: src/context_search_tool/retrieval.py
- Modify: tests/test_retrieval_pipeline.py

- [ ] **Step 1: Write failing propagation and union tests**

Add:

~~~python
def test_merge_candidates_preserves_semantic_matches_when_lexical_evidence_merges() -> None:
    merged = retrieval._merge_candidates(
        [
            RetrievalCandidate(
                chunk_id="chunk",
                score=0.8,
                source="planner_semantic",
                score_parts={"planner_semantic": 0.8},
                semantic_matches=[SemanticMatch("planner:0", 0.8)],
            ),
            RetrievalCandidate(
                chunk_id="chunk",
                score=1.0,
                source="lexical",
                score_parts={"lexical": 1.0},
            ),
        ]
    )["chunk"]

    assert merged.semantic_matches == [SemanticMatch("planner:0", 0.8)]


def test_merge_expanded_result_unions_matches_in_variant_order() -> None:
    left = retrieval._ExpandedResult(
        chunk_ids=["left"],
        file_path=Path("App.java"),
        start_line=1,
        end_line=3,
        content="one\ntwo\nthree",
        score=0.5,
        score_parts={"rerank_score": 0.5},
        reasons=["left"],
        followup_keywords=[],
        rank_tier=3,
        rerank_score=0.5,
        evidence_class="planner_direct",
        evidence_priority=1,
        semantic_matches=[
            SemanticMatch("planner:1", 0.7),
            SemanticMatch("original", 0.2),
        ],
    )
    right = retrieval._ExpandedResult(
        chunk_ids=["right"],
        file_path=Path("App.java"),
        start_line=3,
        end_line=5,
        content="three\nfour\nfive",
        score=0.6,
        score_parts={"rerank_score": 0.6},
        reasons=["right"],
        followup_keywords=[],
        rank_tier=3,
        rerank_score=0.6,
        evidence_class="planner_direct",
        evidence_priority=1,
        semantic_matches=[
            SemanticMatch("planner:0", 0.8),
            SemanticMatch("planner:1", 0.9),
        ],
    )

    merged = retrieval._merge_expanded_result(left, right)

    assert merged.semantic_matches == [
        SemanticMatch("original", 0.2),
        SemanticMatch("planner:0", 0.8),
        SemanticMatch("planner:1", 0.9),
    ]


def test_query_repository_returns_original_variant_on_empty_results(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.py").write_text("pass\n", encoding="utf-8")
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=0,
            final_top_k=1,
        )
    )
    index_repository(repo, config)

    bundle = query_repository(repo, "missing query", config)

    assert bundle.results == []
    assert bundle.query_variants == [
        QueryVariant("original", "missing query", "original")
    ]
    assert bundle.variant_retrieval_status == "original_only"
~~~

Also add
`test_query_repository_evidence_anchor_preserves_retrieval_semantic_matches`.
It must exercise the real `query_repository` semantic retrieval path and
assert the resulting `EvidenceAnchor.semantic_matches`; manually constructing
an anchor is not sufficient. Removing the runtime propagation assignment must
fail this test.

- [ ] **Step 2: Run and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py::test_merge_candidates_preserves_semantic_matches_when_lexical_evidence_merges \
  tests/test_retrieval_pipeline.py::test_merge_expanded_result_unions_matches_in_variant_order \
  tests/test_retrieval_pipeline.py::test_query_repository_returns_original_variant_on_empty_results \
  -q
~~~

Expected: FAIL because internal ranked/expanded structures and final results do not carry semantic_matches yet.

- [ ] **Step 3: Add defaulted fields to internal structures**

Add this final field to _RankedChunk and _ExpandedResult:

~~~python
semantic_matches: list[SemanticMatch] = field(default_factory=list)
~~~

Using defaults keeps the existing direct test constructors valid.

- [ ] **Step 4: Propagate and union provenance at every boundary**

Apply these exact rules:

- _rank_chunks final _RankedChunk: candidate.semantic_matches.
- _apply_frontend_import_cohort_rerank reconstructed _RankedChunk: ranked.semantic_matches.
- _expand_ranked_chunks: ranked.semantic_matches.
- _cap_expanded_result: result.semantic_matches.
- _merge_expanded_result: _merge_semantic_matches(left.semantic_matches, right.semantic_matches).
- query_repository final RetrievalResult: item.semantic_matches.
- _evidence_anchor_from_expanded final EvidenceAnchor: item.semantic_matches.

For example, the final result constructor gains:

~~~python
semantic_matches=item.semantic_matches,
~~~

and the expanded merge gains:

~~~python
semantic_matches=_merge_semantic_matches(
    left.semantic_matches,
    right.semantic_matches,
),
~~~

No non-semantic source should manufacture a match.

- [ ] **Step 5: Run focused and complete retrieval tests**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py \
  tests/test_rerank_soft_sorting.py \
  -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: preserve semantic variant provenance"
~~~

### Task 4: Implement max-based planner semantic scoring and corrected evidence ordering

**Files:**

- Modify: src/context_search_tool/retrieval.py
- Modify: tests/test_rerank_soft_sorting.py

- [ ] **Step 1: Write failing score and evidence tests**

Add:

~~~python
def test_effective_semantic_uses_max_without_variant_count_inflation() -> None:
    parts = retrieval._with_effective_semantic(
        {
            "semantic": 0.20,
            "planner_semantic": 0.80,
        }
    )

    assert parts["effective_semantic"] == pytest.approx(0.68)
    assert retrieval._combined_score(parts) == pytest.approx(0.68 * 0.55)


@pytest.mark.parametrize(
    "score_parts,expected",
    [
        ({"semantic": -0.40}, -0.40),
        ({"planner_semantic": -0.40}, -0.40),
        ({"semantic": -0.30, "planner_semantic": -0.40}, -0.30),
        ({"semantic": 0.20, "planner_semantic": 0.80}, 0.68),
    ],
)
def test_effective_semantic_preserves_absence_and_non_positive_scores(
    score_parts: dict[str, float],
    expected: float,
) -> None:
    parts = retrieval._with_effective_semantic(score_parts)
    assert parts["effective_semantic"] == pytest.approx(expected)


def test_planner_semantic_is_direct_planner_evidence_but_not_strong_original() -> None:
    score_parts = {"planner_semantic": 0.99}

    assert retrieval._has_planner_direct_evidence(score_parts) is True
    assert retrieval._has_strong_original_direct_evidence(score_parts) is False
    assert retrieval._evidence_class(score_parts) == "planner_direct"
    assert retrieval._evidence_priority("planner_direct") == 1
    assert "planner semantic match" in retrieval._reasons(score_parts, "query")


def test_ceiling_tie_uses_pre_ceiling_score_before_role_priority() -> None:
    high_pre_ceiling = retrieval._RankedChunk(
        chunk=DocumentChunk(
            chunk_id="planner",
            file_path=Path("z/Planner.java"),
            start_line=1,
            end_line=1,
            content="planner",
            chunk_type="symbol",
        ),
        score=0.8,
        score_parts={"role_priority": 9.0},
        reasons=[],
        rank_tier=3,
        rerank_score=0.50,
        evidence_class="planner_direct",
        evidence_priority=1,
        pre_ceiling_rerank_score=0.90,
        was_ceiling_clamped=True,
    )
    low_pre_ceiling = retrieval._RankedChunk(
        chunk=DocumentChunk(
            chunk_id="weak",
            file_path=Path("a/Weak.java"),
            start_line=1,
            end_line=1,
            content="weak",
            chunk_type="symbol",
        ),
        score=0.7,
        score_parts={"role_priority": 0.0},
        reasons=[],
        rank_tier=3,
        rerank_score=0.50,
        evidence_class="weak_original_direct",
        evidence_priority=1,
        pre_ceiling_rerank_score=0.60,
        was_ceiling_clamped=True,
    )

    assert sorted(
        [low_pre_ceiling, high_pre_ceiling],
        key=retrieval._ranked_chunk_sort_key,
    )[0].chunk.chunk_id == "planner"
~~~

Also add regression coverage for the approved review corrections:

- a negative ceiling tie where an actually clamped `_RankedChunk` with the
  higher exact and pre-ceiling scores must not sort behind a non-clamped item
  because the pre-ceiling score is negative;
- the equivalent `_ExpandedResult` ordering case;
- mixed `planner_semantic` plus `original_relation` evidence classifies as
  `planner_direct` with priority 1;
- adding `original_relation` to a planner-direct candidate cannot make it lose
  a ceiling tie solely by downgrading its evidence priority.

Import pytest if it is not already imported in tests/test_rerank_soft_sorting.py.

- [ ] **Step 2: Run and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_rerank_soft_sorting.py::test_effective_semantic_uses_max_without_variant_count_inflation \
  tests/test_rerank_soft_sorting.py::test_effective_semantic_preserves_absence_and_non_positive_scores \
  tests/test_rerank_soft_sorting.py::test_planner_semantic_is_direct_planner_evidence_but_not_strong_original \
  tests/test_rerank_soft_sorting.py::test_ceiling_tie_uses_pre_ceiling_score_before_role_priority \
  -q
~~~

Expected: FAIL because planner_semantic, effective_semantic, shared direct priority, and pre-ceiling ordering are absent.

Run the four review-correction regressions against the uncorrected Task 4
implementation as a second RED check. Expected: FAIL because the non-clamped
`0.0` sentinel is sign-sensitive and `original_relation` is checked before
planner-direct evidence.

- [ ] **Step 3: Add semantic constants and effective-score calculation**

Near the existing ranking constants, add:

~~~python
_SEMANTIC_SCORE_WEIGHT = 0.55
_PLANNER_SEMANTIC_WEIGHT = 0.85
~~~

Add:

~~~python
def _with_effective_semantic(
    score_parts: dict[str, float],
) -> dict[str, float]:
    updated = dict(score_parts)
    original_exists = "semantic" in updated
    planner_exists = "planner_semantic" in updated
    if not original_exists and not planner_exists:
        return updated

    adjusted_planner: float | None = None
    if planner_exists:
        planner_score = updated["planner_semantic"]
        adjusted_planner = (
            planner_score * _PLANNER_SEMANTIC_WEIGHT
            if planner_score > 0
            else planner_score
        )

    if original_exists and adjusted_planner is not None:
        effective = max(updated["semantic"], adjusted_planner)
    elif original_exists:
        effective = updated["semantic"]
    else:
        assert adjusted_planner is not None
        effective = adjusted_planner
    updated["effective_semantic"] = effective
    return updated
~~~

In _rank_chunks, call this after all candidate score parts are merged and before _combined_score:

~~~python
score_parts = _with_effective_semantic(score_parts)
score = _combined_score(score_parts)
~~~

Change the first term of _combined_score to:

~~~python
score_parts.get(
    "effective_semantic",
    score_parts.get("semantic", 0.0),
) * _SEMANTIC_SCORE_WEIGHT
~~~

Keep semantic, planner_semantic, and effective_semantic in score_parts so JSON/MCP diagnostics expose all existing raw values plus the consumed value.

- [ ] **Step 4: Make planner semantic evidence direct and share priority**

Add planner_semantic to _has_planner_direct_evidence and _has_planner_hint. Do not add it to any original-evidence predicate.

Use this evidence priority map:

~~~python
priority_map = {
    "original_direct": 0,
    "weak_original_direct": 1,
    "planner_direct": 1,
    "original_relation": 2,
    "planner_relation": 3,
    "weak_or_generic": 4,
}
~~~

Keep _evidence_class ordering as:

1. strong original direct;
2. weak original direct;
3. planner direct;
4. original relation;
5. planner relation;
6. weak/generic.

A chunk containing weak original plus planner direct evidence may retain the weak_original_direct label; both labels now have the same numeric priority and are ordered by score.
Planner-direct evidence must be checked before original relation so merging
additional relation evidence cannot downgrade a direct planner candidate from
priority 1 to priority 2.

In _reasons, add before the generic planner-hint reason:

~~~python
if score_parts.get("planner_semantic", 0.0) > 0:
    reasons.append("planner semantic match")
~~~

- [ ] **Step 5: Preserve pre-ceiling score only for ceiling-clamped tie-breaks**

Add the following final fields to _RankedChunk and _ExpandedResult:

~~~python
pre_ceiling_rerank_score: float = 0.0
was_ceiling_clamped: bool = False
~~~

When _rank_chunks first computes rerank_score with planner_ceiling=None, save it on each temporary item:

~~~python
item["pre_ceiling_rerank_score"] = rerank_score
~~~

When applying planner_ceiling, record whether the ceiling actually changed each
eligible item before replacing rerank_score:

~~~python
item["was_ceiling_clamped"] = (
    item["evidence_class"] in _CLAMPED_EVIDENCE_CLASSES
    and planner_ceiling is not None
    and item["rerank_score"] > planner_ceiling
)
if item["was_ceiling_clamped"]:
    item["rerank_score"] = planner_ceiling
~~~

Keep _CLAMPED_EVIDENCE_CLASSES unchanged so the ceiling's scope does not
broaden. Propagate both fields through every _RankedChunk and _ExpandedResult
constructor, and select both values from the winning member in
_merge_expanded_result.

Change _ranked_chunk_sort_key so the pre-ceiling value comes before role
priority only when the item was actually clamped:

~~~python
return (
    -round(item.rerank_score, _RERANK_SORT_DECIMALS),
    item.evidence_priority,
    0 if item.was_ceiling_clamped else 1,
    -(
        item.pre_ceiling_rerank_score
        if item.was_ceiling_clamped
        else 0.0
    ),
    item.score_parts.get("role_priority", 99.0),
    -item.rerank_score,
    -item.score,
    item.chunk.file_path.as_posix(),
    item.chunk.start_line,
    item.chunk.chunk_id,
)
~~~

Apply the same conditional ordering to _expanded_result_sort_key. Update the
tuple return annotations to match the added discriminator and float. The
explicit clamp-status discriminator makes ceiling-created tie handling
independent of score sign. This leaves the existing role-priority ordering
unchanged for ordinary, non-clamped near ties while making actually clamped
ties reflect their pre-ceiling score.

- [ ] **Step 6: Run rerank and retrieval suites**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_rerank_soft_sorting.py \
  tests/test_retrieval_pipeline.py \
  -q
~~~

Expected: PASS. Existing strong-original ceiling tests must remain green.

- [ ] **Step 7: Commit**

~~~bash
git add \
  src/context_search_tool/retrieval.py \
  tests/test_rerank_soft_sorting.py
git commit -m "feat: blend planner semantic evidence safely"
~~~

### Task 5: Prove the end-to-end retrieval modes and exact-search protections

**Files:**

- Modify: tests/test_retrieval_pipeline.py

- [ ] **Step 1: Add a deterministic vector-path integration fixture**

Add a helper that indexes with three-dimensional hash vectors, replaces the stored chunk vectors with controlled vectors, then monkeypatches only query-time embedding:

~~~python
def _controlled_semantic_repo(
    tmp_path: Path,
) -> tuple[Path, ToolConfig, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Incidental.java").write_text(
        "class Incidental { void weak() {} }\n",
        encoding="utf-8",
    )
    (repo / "PlannerTarget.java").write_text(
        "class PlannerTarget { void bridge() {} }\n",
        encoding="utf-8",
    )
    config = ToolConfig(
        embedding=EmbeddingConfig(
            provider="hash",
            model="hash-v1",
            dimensions=3,
        ),
        retrieval=RetrievalConfig(
            # Keep this at one so the original zero-similarity target cannot
            # enter the candidate pool before the planner variant is searched.
            semantic_top_k=1,
            lexical_top_k=0,
            final_top_k=2,
            context_before_lines=0,
            context_after_lines=0,
        ),
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    ids = {
        path: store.chunk_for_line(Path(path), 1).chunk_id
        for path in ("Incidental.java", "PlannerTarget.java")
    }
    vector_store = retrieval.NumpyVectorStore(index_dir_for(repo))
    vector_store.upsert_many(
        [
            (
                ids["Incidental.java"],
                np.asarray([0.40, 0.0, 0.916515], dtype=np.float32),
            ),
            (
                ids["PlannerTarget.java"],
                np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
            ),
        ]
    )
    vector_store.persist()
    return repo, config, ids
~~~

- [ ] **Step 2: Add the hybrid-recall and score-order integration test**

~~~python
def test_planner_rewrite_recalls_target_by_vector_and_outranks_weak_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config, _ = _controlled_semantic_repo(tmp_path)

    class QueryEmbeddingProvider:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            self.calls.append(list(texts))
            vectors = {
                "原始问题": np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
                "semantic bridge": np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
            }
            return [vectors[text] for text in texts]

    provider = QueryEmbeddingProvider()
    monkeypatch.setattr(retrieval, "provider_from_config", lambda config: provider)
    planner = FakePlanner(
        QueryPlan(
            original_query="原始问题",
            rewritten_queries=["semantic bridge"],
            status="ok",
        )
    )

    bundle = query_repository(repo, "原始问题", config, planner=planner)

    assert planner.calls == ["原始问题"]
    assert provider.calls == [["原始问题", "semantic bridge"]]
    assert bundle.variant_retrieval_status == "hybrid"
    assert bundle.results[0].file_path == Path("PlannerTarget.java")
    assert [
        match.variant_id for match in bundle.results[0].semantic_matches
    ] == ["planner:0"]
    assert [
        match.score for match in bundle.results[0].semantic_matches
    ] == pytest.approx([1.0])
    assert bundle.results[0].score_parts["planner_semantic"] == pytest.approx(1.0)
    assert "planner_lexical" not in bundle.results[0].score_parts
~~~

- [ ] **Step 3: Add mode/fallback/deduplication regression tests**

Add:

~~~python
def test_disabled_failure_and_empty_plans_use_identical_original_vector_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config, _ = _controlled_semantic_repo(tmp_path)
    provider = CapturingEmbeddingProvider([[1, 0, 0]])
    monkeypatch.setattr(retrieval, "provider_from_config", lambda config: provider)
    query = "query"

    plans = [
        QueryPlan(original_query=query, status="disabled"),
        QueryPlan(
            original_query=query,
            status="fallback",
            error="planner timed out",
        ),
        QueryPlan(
            original_query=query,
            status="fallback",
            error="planner returned invalid JSON",
        ),
        QueryPlan(
            original_query=query,
            status="fallback",
            error="planner returned unsupported payload",
        ),
        QueryPlan(original_query=query, rewritten_queries=[], status="ok"),
    ]
    bundles = [
        query_repository(repo, query, config, planner=FakePlanner(plan))
        for plan in plans
    ]
    baseline_paths = [result.file_path for result in bundles[0].results]
    baseline_scores = [result.score for result in bundles[0].results]

    assert provider.calls == [[query]] * len(plans)
    assert baseline_paths == [Path("Incidental.java")]
    expected_semantic = bundles[0].results[0].score_parts["semantic"]
    expected_matches = [SemanticMatch("original", expected_semantic)]
    assert expected_semantic == pytest.approx(0.40)

    for bundle in bundles:
        assert [result.file_path for result in bundle.results] == baseline_paths
        assert [result.score for result in bundle.results] == baseline_scores
        assert bundle.results[0].score_parts["semantic"] == expected_semantic
        assert bundle.results[0].semantic_matches == expected_matches
        assert bundle.variant_retrieval_status == "original_only"
        assert bundle.query_variants == [
            QueryVariant("original", query, "original")
        ]


def test_variant_embedding_fallback_reports_only_executed_original_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config, _ = _controlled_semantic_repo(tmp_path)

    class FailVariantBatchProvider:
        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            if len(texts) > 1:
                raise RuntimeError("variant batch failed")
            return [np.asarray([1.0, 0.0, 0.0], dtype=np.float32)]

    monkeypatch.setattr(
        retrieval,
        "provider_from_config",
        lambda config: FailVariantBatchProvider(),
    )
    bundle = query_repository(
        repo,
        "query",
        config,
        planner=FakePlanner(
            QueryPlan(
                original_query="query",
                rewritten_queries=["semantic bridge"],
                status="ok",
            )
        ),
    )

    assert bundle.variant_retrieval_status == "embedding_fallback"
    assert bundle.query_variants == [
        QueryVariant("original", "query", "original")
    ]


def test_duplicate_rewrites_do_not_change_score_or_search_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config, _ = _controlled_semantic_repo(tmp_path)
    vector_store = retrieval.NumpyVectorStore(index_dir_for(repo))
    search_calls: list[tuple[tuple[float, ...], int]] = []
    real_search = vector_store.search

    def recording_search(query_vector, top_k, deleted_ids):
        search_calls.append((tuple(float(value) for value in query_vector), top_k))
        return real_search(query_vector, top_k, deleted_ids)

    monkeypatch.setattr(retrieval, "NumpyVectorStore", lambda index_dir: vector_store)
    monkeypatch.setattr(vector_store, "search", recording_search)

    baseline_provider = CapturingEmbeddingProvider([[1, 0, 0], [0, 1, 0]])
    monkeypatch.setattr(
        retrieval, "provider_from_config", lambda config: baseline_provider
    )
    baseline = query_repository(
        repo,
        "query",
        config,
        planner=FakePlanner(
            QueryPlan(
                original_query="query",
                rewritten_queries=["semantic bridge"],
                status="ok",
            )
        ),
    )
    baseline_search_calls = list(search_calls)
    search_calls.clear()

    duplicate_provider = CapturingEmbeddingProvider([[1, 0, 0], [0, 1, 0]])
    monkeypatch.setattr(
        retrieval, "provider_from_config", lambda config: duplicate_provider
    )
    duplicate = query_repository(
        repo,
        "query",
        config,
        planner=FakePlanner(
            QueryPlan(
                original_query="query",
                rewritten_queries=[
                    "semantic bridge",
                    "  SEMANTIC   BRIDGE ",
                    "query",
                ],
                status="ok",
            )
        ),
    )
    duplicate_search_calls = list(search_calls)

    expected_provider_calls = [["query", "semantic bridge"]]
    expected_variants = [
        QueryVariant("original", "query", "original"),
        QueryVariant("planner:0", "semantic bridge", "planner"),
    ]
    expected_search_calls = [
        ((1.0, 0.0, 0.0), config.retrieval.semantic_top_k),
        ((0.0, 1.0, 0.0), config.retrieval.semantic_top_k),
    ]
    assert baseline_provider.calls == expected_provider_calls
    assert duplicate_provider.calls == expected_provider_calls
    assert baseline_search_calls == expected_search_calls
    assert duplicate_search_calls == expected_search_calls
    assert [(result.file_path, result.score) for result in duplicate.results] == [
        (result.file_path, result.score) for result in baseline.results
    ]

    for bundle in (baseline, duplicate):
        assert bundle.query_variants == expected_variants
        assert bundle.variant_retrieval_status == "hybrid"
        assert bundle.results[0].score_parts["planner_semantic"] == pytest.approx(1.0)
        assert bundle.results[0].semantic_matches == [
            SemanticMatch("planner:0", 1.0)
        ]
~~~

The timeout, invalid-JSON, and unsupported-payload planner parser tests already
in tests/test_query_planner.py establish that those provider outcomes become
fallback QueryPlan values; the vector-only table above verifies that their
shared runtime contract reaches the same original semantic result, raw semantic
score, and provenance without relying on lexical saturation. The deduplication
test compares the duplicate-rewrite run against a unique-rewrite baseline and
requires identical ordered scores as well as one batch and two vector searches
per run. Extend the existing planner
fallback, exact route/path, symbol, and literal tests to assert:

~~~python
assert bundle.query_variants[0].variant_id == "original"
assert bundle.variant_retrieval_status in {"original_only", "hybrid"}
~~~

For exact tests with an ok planner and no useful rewrite, require original_only. For exact tests with a retained rewrite, require the existing expected Top 1 and do not require a particular variant status.

- [ ] **Step 4: Run the focused integration and exact regressions**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py::test_planner_rewrite_recalls_target_by_vector_and_outranks_weak_original \
  tests/test_retrieval_pipeline.py::test_disabled_failure_and_empty_plans_use_identical_original_vector_results \
  tests/test_retrieval_pipeline.py::test_variant_embedding_fallback_reports_only_executed_original_variant \
  tests/test_retrieval_pipeline.py::test_duplicate_rewrites_do_not_change_score_or_search_count \
  tests/test_retrieval_pipeline.py::test_query_planner_fallback_returns_original_query_results \
  tests/test_retrieval_pipeline.py::test_noisy_route_query_keeps_lexical_evidence \
  -q
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add tests/test_retrieval_pipeline.py
git commit -m "test: lock hybrid recall and exact fallback behavior"
~~~

### Task 6: Expose additive CLI/MCP provenance without leaking rewrite text to feedback

**Files:**

- Modify: src/context_search_tool/formatters.py
- Modify: src/context_search_tool/mcp_tools.py
- Modify: tests/test_formatters.py
- Modify: tests/test_mcp_tools.py

- [ ] **Step 1: Write failing JSON, MCP, Markdown, and feedback tests**

In tests/test_formatters.py, import QueryVariant and SemanticMatch and add:

~~~python
def test_json_formatter_exposes_query_variants_and_semantic_matches() -> None:
    bundle = QueryBundle(
        query="数据看板统计图表功能",
        expanded_tokens=["数据看板统计图表功能", "dashboard"],
        results=[
            RetrievalResult(
                file_path=Path("DashboardController.java"),
                start_line=1,
                end_line=10,
                content="class DashboardController {}",
                score=0.9,
                score_parts={
                    "planner_semantic": 0.84,
                    "effective_semantic": 0.714,
                },
                reasons=["planner semantic match"],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.84)],
            )
        ],
        followup_keywords=[],
        query_variants=[
            QueryVariant("original", "数据看板统计图表功能", "original"),
            QueryVariant("planner:0", "dashboard statistics chart", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    payload = json.loads(format_json(bundle))

    assert payload["query_variants"] == [
        {
            "variant_id": "original",
            "text": "数据看板统计图表功能",
            "source": "original",
        },
        {
            "variant_id": "planner:0",
            "text": "dashboard statistics chart",
            "source": "planner",
        },
    ]
    assert payload["variant_retrieval_status"] == "hybrid"
    assert payload["results"][0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.84}
    ]


def test_markdown_does_not_add_per_result_semantic_provenance_table() -> None:
    base_bundle = sample_bundle()
    anchor = EvidenceAnchor(
        file_path=Path("README.md"),
        start_line=1,
        end_line=2,
        content="Audit documentation",
        score=0.4,
        score_parts={"lexical": 0.4},
        reasons=["documentation match"],
        anchor_kind="document",
    )
    base_bundle = replace(base_bundle, evidence_anchors=[anchor])
    provenance_bundle = replace(
        base_bundle,
        results=[
            replace(
                base_bundle.results[0],
                semantic_matches=[SemanticMatch("planner:0", 0.75)],
            )
        ],
        evidence_anchors=[
            replace(
                anchor,
                semantic_matches=[SemanticMatch("planner:0", 0.4)],
            )
        ],
        query_variants=[
            QueryVariant("original", base_bundle.query, "original"),
            QueryVariant("planner:0", "apply audit workflow", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    assert format_markdown(provenance_bundle) == format_markdown(base_bundle)
~~~

Import dataclasses.replace for this exact compatibility comparison. Nonempty
result and evidence-anchor provenance must not change the pre-provenance
Markdown output.

In tests/test_mcp_tools.py, import QueryVariant and SemanticMatch and add:

~~~python
def test_mcp_query_payload_exposes_variant_and_anchor_provenance() -> None:
    bundle = QueryBundle(
        query="query",
        expanded_tokens=["query"],
        results=[
            RetrievalResult(
                file_path=Path("App.java"),
                start_line=1,
                end_line=2,
                content="class App {}",
                score=0.8,
                score_parts={"planner_semantic": 0.8},
                reasons=["planner semantic match"],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.8)],
            )
        ],
        followup_keywords=[],
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("README.md"),
                start_line=1,
                end_line=2,
                content="App docs",
                score=0.4,
                score_parts={"planner_semantic": 0.4},
                reasons=["planner semantic match"],
                anchor_kind="document",
                semantic_matches=[SemanticMatch("planner:0", 0.4)],
            )
        ],
        query_variants=[
            QueryVariant("original", "query", "original"),
            QueryVariant("planner:0", "application entrypoint", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    payload = mcp_tools._query_payload(bundle)

    assert payload["variant_retrieval_status"] == "hybrid"
    assert payload["query_variants"][1]["variant_id"] == "planner:0"
    assert payload["results"][0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.8}
    ]
    assert payload["evidence_anchors"][0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.4}
    ]


def test_mcp_feedback_hashes_variants_without_storing_rewrite_text(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".context-search").mkdir()
    private_rewrite = "private planner rewrite"
    rewritten_query_sentinel = "private rewritten query sentinel"
    grep_keyword_sentinel = "private grep keyword sentinel"
    symbol_hint_sentinel = "PrivatePlannerSymbolHintSentinel"
    payload = {
        "ok": True,
        "results": [],
        "summary": {},
        "followup_keywords": [],
        "planner": {
            "status": "ok",
            "rewritten_queries": [rewritten_query_sentinel],
            "grep_keywords": [grep_keyword_sentinel],
            "symbol_hints": [symbol_hint_sentinel],
        },
        "variant_retrieval_status": "hybrid",
        "query_variants": [
            {
                "variant_id": "original",
                "source": "original",
                "text": "original secret query",
            },
            {
                "variant_id": "planner:0",
                "source": "planner",
                "text": private_rewrite,
            },
        ],
    }

    mcp_tools._append_query_feedback(
        repo,
        query="original secret query",
        payload=payload,
        context_lines=None,
        full_file=False,
        final_top_k=None,
    )
    event = json.loads(
        (repo / ".context-search" / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(event)
    expected_hash = hashlib.sha256(private_rewrite.encode("utf-8")).hexdigest()[:12]

    assert event["query"] == "original secret query"
    assert event["variant_retrieval"]["status"] == "hybrid"
    assert event["variant_retrieval"]["count"] == 2
    assert event["variant_retrieval"]["variants"][1] == {
        "variant_id": "planner:0",
        "source": "planner",
        "position": 1,
        "text_hash": expected_hash,
    }
    for field in ("rewritten_queries", "grep_keywords", "symbol_hints"):
        assert field not in event["planner"]
    for sensitive_text in (
        private_rewrite,
        rewritten_query_sentinel,
        grep_keyword_sentinel,
        symbol_hint_sentinel,
    ):
        assert sensitive_text not in serialized
~~~

Import hashlib in the test so the persisted hash contract is checked
independently of the production helper. Also add regressions for an error
payload (original_only, zero variants), all three allowed statuses, and
malformed status/variant_id/source values containing sentinel rewrite text.
Malformed metadata must be omitted or defaulted so none of those sentinels can
reach the serialized event.

- [ ] **Step 2: Run and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_formatters.py::test_json_formatter_exposes_query_variants_and_semantic_matches \
  tests/test_formatters.py::test_markdown_does_not_add_per_result_semantic_provenance_table \
  tests/test_mcp_tools.py::test_mcp_query_payload_exposes_variant_and_anchor_provenance \
  tests/test_mcp_tools.py::test_mcp_feedback_hashes_variants_without_storing_rewrite_text \
  -q
~~~

Expected: FAIL because the additive payload fields and bounded feedback metadata are absent.

- [ ] **Step 3: Add explicit serializer helpers**

In both src/context_search_tool/formatters.py and src/context_search_tool/mcp_tools.py, import QueryVariant and SemanticMatch and add:

~~~python
def _query_variant_payload(variant: QueryVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "text": variant.text,
        "source": variant.source,
    }


def _semantic_match_payload(match: SemanticMatch) -> dict[str, Any]:
    return {
        "variant_id": match.variant_id,
        "score": match.score,
    }
~~~

In format_json and _query_payload add:

~~~python
"query_variants": [
    _query_variant_payload(variant) for variant in bundle.query_variants
],
"variant_retrieval_status": bundle.variant_retrieval_status,
~~~

Add semantic_matches to every result and evidence-anchor payload:

~~~python
"semantic_matches": [
    _semantic_match_payload(match) for match in result.semantic_matches
],
~~~

Use anchor.semantic_matches in the anchor helper.

Do not change format_markdown. Its existing concise planner line and score-parts section remain the Markdown contract.

- [ ] **Step 4: Add bounded variant metadata to raw MCP feedback**

Add:

~~~python
def _feedback_variant_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("variant_retrieval_status", "original_only")
    if status not in ("original_only", "hybrid", "embedding_fallback"):
        status = "original_only"
    variants = payload.get("query_variants", [])
    if not isinstance(variants, list):
        variants = []
    bounded = []
    for position, item in enumerate(variants):
        if not isinstance(item, dict):
            continue
        variant_id = item.get("variant_id")
        source = item.get("source")
        is_original = source == "original" and variant_id == "original"
        is_planner = False
        if source == "planner" and isinstance(variant_id, str):
            prefix, separator, raw_index = variant_id.partition(":")
            is_planner = (
                prefix == "planner"
                and separator == ":"
                and raw_index.isascii()
                and raw_index.isdecimal()
                and (raw_index == "0" or not raw_index.startswith("0"))
            )
        if not (is_original or is_planner):
            continue
        text = item.get("text", "")
        bounded.append(
            {
                "variant_id": variant_id,
                "source": source,
                "position": position,
                "text_hash": _short_hash(text if isinstance(text, str) else ""),
            }
        )
    return {
        "status": status,
        "count": len(bounded),
        "variants": bounded,
    }
~~~

This is a persisted privacy boundary: accept only canonical original/original
and planner:N/planner identity pairs, preserve their original list positions,
and fail closed on malformed metadata. Do not copy arbitrary status, ID, or
source objects into the feedback event.

Add this event field in _append_query_feedback:

~~~python
"variant_retrieval": _feedback_variant_payload(payload),
~~~

Do not add query variant text to the event or to _feedback_planner_payload. The existing feedback summary remains unchanged and therefore continues hiding terms/examples unless its explicit flags are used.

- [ ] **Step 5: Run formatter, MCP, and feedback tests**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_formatters.py \
  tests/test_mcp_tools.py \
  tests/test_quality_feedback.py \
  -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add \
  src/context_search_tool/formatters.py \
  src/context_search_tool/mcp_tools.py \
  tests/test_formatters.py \
  tests/test_mcp_tools.py
git commit -m "feat: expose semantic variant provenance safely"
~~~

### Task 7: Add typed profile expectations and exact Phase 1 profile validation

**Files:**

- Modify: src/context_search_tool/quality/cases.py
- Modify: tests/test_quality_cases.py

- [ ] **Step 1: Write failing expectation-parser tests**

Import ProfileExpectation in tests/test_quality_cases.py and add:

~~~python
def test_case_parses_profile_specific_runtime_expectations(
    tmp_path: Path,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {
            "p1_vector_bge": {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "p1_hybrid_bge": {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {
                    "enabled": True,
                    "provider": "ollama",
                    "model": "qwen3.5:4b-mlx",
                },
            },
        },
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["p1_vector_bge", "p1_hybrid_bge"],
                "queries": [
                    {
                        "id": "cross-language",
                        "query": "数据看板",
                        "profiles": ["p1_vector_bge", "p1_hybrid_bge"],
                        "profile_expectations": {
                            "p1_vector_bge": {
                                "planner_status": "disabled",
                                "variant_retrieval_status": "original_only",
                            },
                            "p1_hybrid_bge": {
                                "planner_status": "ok",
                                "variant_retrieval_status": "hybrid",
                                "top_result_planner_semantic_match": True,
                            },
                        },
                    }
                ],
            }
        ],
    }

    case = load_quality_fixture(_write_fixture(tmp_path, data)).repos[0].queries[0]

    assert case.profile_expectations == {
        "p1_vector_bge": ProfileExpectation(
            planner_status="disabled",
            variant_retrieval_status="original_only",
        ),
        "p1_hybrid_bge": ProfileExpectation(
            planner_status="ok",
            variant_retrieval_status="hybrid",
            top_result_planner_semantic_match=True,
        ),
    }
~~~

Add strict invalid-value coverage:

~~~python
@pytest.mark.parametrize(
    "expectation,message",
    [
        ({"unknown": True}, "unknown profile expectation field"),
        ({"planner_status": "maybe"}, "invalid planner_status"),
        (
            {"variant_retrieval_status": "fallback"},
            "invalid variant_retrieval_status",
        ),
        (
            {"top_result_planner_semantic_match": 1},
            "top_result_planner_semantic_match must be a bool",
        ),
    ],
)
def test_profile_expectations_reject_unknown_or_invalid_values(
    tmp_path: Path,
    expectation: dict,
    message: str,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {"custom": {}},
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["custom"],
                "queries": [
                    {
                        "id": "case",
                        "query": "query",
                        "profile_expectations": {"custom": expectation},
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match=message):
        load_quality_fixture(_write_fixture(tmp_path, data))
~~~

Also parameterize both status fields over JSON-like non-string values (`[]`,
`{}`, `true`, and a number) and require the same documented `ValueError`
messages. This locks the explicit type guards and prevents unhashable inputs
from leaking `TypeError`.

Add a case where an expectation key is configured globally but is not selected by that case; expect ValueError matching profile expectation uses unselected profile.

- [ ] **Step 2: Write failing exact profile-invariant tests**

Extend the canonical profile parameterization with:

~~~python
(
    "p1_vector_bge",
    ToolConfig(
        embedding=EmbeddingConfig(
            provider="hash",
            model="bge-m3",
            dimensions=1024,
        ),
        query_planner=QueryPlannerConfig(enabled=False),
    ),
    "p1_vector_bge profile requires BGE M3 at 1024 dimensions",
),
(
    "p1_vector_bge",
    ToolConfig(
        embedding=replace(_VALID_BGE_EMBEDDING, model="other"),
    ),
    "p1_vector_bge profile requires BGE M3 at 1024 dimensions",
),
(
    "p1_vector_bge",
    ToolConfig(
        embedding=replace(_VALID_BGE_EMBEDDING, dimensions=384),
    ),
    "p1_vector_bge profile requires BGE M3 at 1024 dimensions",
),
(
    "p1_vector_bge",
    ToolConfig(
        embedding=_VALID_BGE_EMBEDDING,
        query_planner=QueryPlannerConfig(enabled=True),
    ),
    "p1_vector_bge profile requires the query planner disabled",
),
(
    "p1_hybrid_bge",
    ToolConfig(
        embedding=_VALID_BGE_EMBEDDING,
        query_planner=QueryPlannerConfig(enabled=False),
    ),
    "p1_hybrid_bge profile requires the query planner enabled",
),
(
    "p1_hybrid_bge",
    ToolConfig(
        embedding=_VALID_BGE_EMBEDDING,
        query_planner=QueryPlannerConfig(
            enabled=True,
            provider="remote",
            model="qwen3.5:4b-mlx",
        ),
    ),
    "p1_hybrid_bge profile requires the Ollama planner",
),
(
    "p1_hybrid_bge",
    ToolConfig(
        embedding=_VALID_BGE_EMBEDDING,
        query_planner=QueryPlannerConfig(
            enabled=True,
            provider="ollama",
            model="other",
        ),
    ),
    "p1_hybrid_bge profile requires qwen3.5:4b-mlx",
),
~~~

- [ ] **Step 3: Run and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py::test_case_parses_profile_specific_runtime_expectations \
  tests/test_quality_cases.py::test_profile_expectations_reject_unknown_or_invalid_values \
  tests/test_quality_cases.py::test_canonical_profile_invariants_reject_each_invalid_property \
  -q
~~~

Expected: FAIL because ProfileExpectation and Phase 1 profile invariants do not exist.

- [ ] **Step 4: Add the typed expectation model and parser**

In src/context_search_tool/quality/cases.py add:

~~~python
_PLANNER_STATUSES = {"disabled", "ok", "fallback"}
_VARIANT_RETRIEVAL_STATUSES = {
    "original_only",
    "hybrid",
    "embedding_fallback",
}


@dataclass(frozen=True)
class ProfileExpectation:
    planner_status: str | None = None
    variant_retrieval_status: str | None = None
    top_result_planner_semantic_match: bool | None = None
~~~

Add this final field to QualityCase:

~~~python
profile_expectations: dict[str, ProfileExpectation] = field(default_factory=dict)
~~~

Add:

~~~python
def _parse_profile_expectations(
    raw: Any,
) -> dict[str, ProfileExpectation]:
    values = _require_dict(raw, "profile_expectations")
    parsed: dict[str, ProfileExpectation] = {}
    allowed = {
        "planner_status",
        "variant_retrieval_status",
        "top_result_planner_semantic_match",
    }
    for raw_profile, raw_expectation in values.items():
        profile = _require_non_empty_str(raw_profile, "profile expectation name")
        expectation = _require_dict(
            raw_expectation,
            f"profile_expectations.{profile}",
        )
        unknown = set(expectation) - allowed
        if unknown:
            raise ValueError(
                f"unknown profile expectation field: {sorted(unknown)[0]}"
            )

        planner_status = expectation.get("planner_status")
        if (
            planner_status is not None
            and planner_status not in _PLANNER_STATUSES
        ):
            raise ValueError("invalid planner_status")
        variant_status = expectation.get("variant_retrieval_status")
        if (
            variant_status is not None
            and variant_status not in _VARIANT_RETRIEVAL_STATUSES
        ):
            raise ValueError("invalid variant_retrieval_status")
        planner_match = expectation.get(
            "top_result_planner_semantic_match"
        )
        if planner_match is not None and type(planner_match) is not bool:
            raise ValueError(
                "top_result_planner_semantic_match must be a bool"
            )
        parsed[profile] = ProfileExpectation(
            planner_status=planner_status,
            variant_retrieval_status=variant_status,
            top_result_planner_semantic_match=planner_match,
        )
    return parsed
~~~

Call it in _parse_case:

~~~python
profile_expectations=_parse_profile_expectations(
    raw.get("profile_expectations", {})
),
~~~

In _validate_fixture_profiles, after case profile validation, require each expectation profile to be in case.profiles or, when case.profiles is empty, repo.profiles:

~~~python
selected_profiles = case.profiles or repo.profiles
for expectation_profile in case.profile_expectations:
    if expectation_profile not in selected_profiles:
        raise ValueError(
            "profile expectation uses unselected profile: "
            f"{expectation_profile}"
        )
~~~

- [ ] **Step 5: Enforce canonical Phase 1 profile names exactly**

In validate_profile_compatible, before the existing calibration/AB BGE branch, add:

~~~python
if profile in {"p1_vector_bge", "p1_hybrid_bge"}:
    if (
        config.embedding.provider != "bge"
        or config.embedding.model != "bge-m3"
        or config.embedding.dimensions != 1024
    ):
        raise ValueError(
            f"{profile} profile requires BGE M3 at 1024 dimensions"
        )
    if profile == "p1_vector_bge":
        if config.query_planner.enabled:
            raise ValueError(
                "p1_vector_bge profile requires the query planner disabled"
            )
        return
    if not config.query_planner.enabled:
        raise ValueError(
            "p1_hybrid_bge profile requires the query planner enabled"
        )
    if config.query_planner.provider != "ollama":
        raise ValueError(
            "p1_hybrid_bge profile requires the Ollama planner"
        )
    if config.query_planner.model != "qwen3.5:4b-mlx":
        raise ValueError(
            "p1_hybrid_bge profile requires qwen3.5:4b-mlx"
        )
    return
~~~

- [ ] **Step 6: Run quality case tests**

Run:

~~~bash
conda run -n base python -m pytest tests/test_quality_cases.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Commit**

~~~bash
git add \
  src/context_search_tool/quality/cases.py \
  tests/test_quality_cases.py
git commit -m "feat: define phase one quality expectations"
~~~

### Task 8: Make runtime expectations gating and reports inspectable

**Files:**

- Modify: src/context_search_tool/quality/metrics.py
- Modify: src/context_search_tool/quality/runner.py
- Modify: tests/test_quality_metrics.py
- Modify: tests/test_quality_runner.py

- [ ] **Step 1: Write failing semantic-match report tests**

In tests/test_quality_metrics.py, import SemanticMatch and replace the existing
_result helper with:

~~~python
def _result(
    path: str,
    score: float = 1.0,
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
    *,
    semantic_matches: list[SemanticMatch] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=10,
        content="content",
        score=score,
        score_parts=score_parts or {},
        reasons=reasons or [],
        followup_keywords=[],
        semantic_matches=list(semantic_matches or []),
    )
~~~

Then add:

~~~python
def test_normalized_top_results_preserve_semantic_matches() -> None:
    evaluation = evaluate_case(
        QualityCase(
            case_id="semantic",
            query="query",
            expected_top_k=(_expected("src/App.java", 1),),
        ),
        [
            _result(
                "src/App.java",
                semantic_matches=[SemanticMatch("planner:0", 0.84)],
            )
        ],
        latency_ms=10,
    )

    assert evaluation.top_results[0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.84}
    ]
~~~

Extend the existing normalization mutation and duplicate-path tests so they
also prove semantic_matches is copied rather than aliased and that the first
normalized result retains its provenance when a later duplicate path carries a
different planner match.

- [ ] **Step 2: Write failing runtime-gate tests**

In tests/test_quality_runner.py, import SemanticMatch, QueryVariant, RetrievalResult, CaseEvaluation, Gate, ProfileExpectation, and QualityCase. Add:

~~~python
def _passing_evaluation() -> CaseEvaluation:
    return CaseEvaluation(
        case_id="case",
        status="pass",
        metrics={},
        failures=[],
        top_results=[],
    )


def test_profile_expectations_fail_case_when_hybrid_did_not_execute() -> None:
    case = QualityCase(
        case_id="case",
        query="query",
        gate=Gate.REQUIRED,
        profile_expectations={
            "p1_hybrid_bge": ProfileExpectation(
                planner_status="ok",
                variant_retrieval_status="hybrid",
                top_result_planner_semantic_match=True,
            )
        },
    )
    bundle = QueryBundle(
        query="query",
        expanded_tokens=[],
        results=[],
        followup_keywords=[],
        planner=QueryPlan("query", status="fallback"),
        query_variants=[QueryVariant("original", "query", "original")],
        variant_retrieval_status="original_only",
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "p1_hybrid_bge",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == [
        "planner_status expected ok, got fallback",
        "variant_retrieval_status expected hybrid, got original_only",
        "top_result_planner_semantic_match expected true, got false",
    ]


def test_profile_expectations_pass_with_actual_planner_semantic_top_result() -> None:
    case = QualityCase(
        case_id="case",
        query="query",
        gate=Gate.REQUIRED,
        profile_expectations={
            "p1_hybrid_bge": ProfileExpectation(
                planner_status="ok",
                variant_retrieval_status="hybrid",
                top_result_planner_semantic_match=True,
            )
        },
    )
    bundle = QueryBundle(
        query="query",
        expanded_tokens=[],
        results=[
            RetrievalResult(
                file_path=Path("App.java"),
                start_line=1,
                end_line=1,
                content="class App {}",
                score=1.0,
                score_parts={},
                reasons=[],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.9)],
            )
        ],
        followup_keywords=[],
        planner=QueryPlan("query", status="ok"),
        query_variants=[
            QueryVariant("original", "query", "original"),
            QueryVariant("planner:0", "app", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "p1_hybrid_bge",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == "pass"
    assert evaluation.failures == []
~~~

Add a _case_record assertion:

~~~python
def test_case_record_serializes_executed_variant_provenance() -> None:
    record = quality_runner._case_record(
        "repo",
        QualityCase(case_id="case", query="query"),
        _passing_evaluation(),
        QueryBundle(
            query="query",
            expanded_tokens=[],
            results=[],
            followup_keywords=[],
            query_variants=[
                QueryVariant("original", "query", "original"),
                QueryVariant("planner:0", "app", "planner"),
            ],
            variant_retrieval_status="hybrid",
        ),
    )

    assert record["query_variants"] == [
        {"variant_id": "original", "text": "query", "source": "original"},
        {"variant_id": "planner:0", "text": "app", "source": "planner"},
    ]
    assert record["variant_retrieval_status"] == "hybrid"
~~~

Add focused boundary coverage for the expectation helper:

- a false top-result expectation is meaningful for both actual true and false;
- a planner match on rank 2 does not satisfy the Top 1 expectation;
- pre-existing evaluation failures remain and keep a required case failed;
- absent and wrong-profile expectations are identity no-ops;
- known-gap and informational statuses are preserved while failures append;
- all-None expectations are ignored.

Add one parsed-fixture `run_quality_fixture` integration test whose fake bundle
misses all three runtime expectations and require the exact three failures in
the emitted required case record. This test must fail if the call immediately
after evaluate_case is removed. Also assert that skipped and error records omit
query_variants and variant_retrieval_status while successful records retain
those execution-only fields.

- [ ] **Step 3: Run and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_quality_metrics.py::test_normalized_top_results_preserve_semantic_matches \
  tests/test_quality_runner.py::test_profile_expectations_fail_case_when_hybrid_did_not_execute \
  tests/test_quality_runner.py::test_profile_expectations_pass_with_actual_planner_semantic_top_result \
  tests/test_quality_runner.py::test_case_record_serializes_executed_variant_provenance \
  -q
~~~

Expected: FAIL because quality normalization drops matches and the runner does not evaluate profile expectations.

- [ ] **Step 4: Preserve semantic matches in quality top results**

In src/context_search_tool/quality/metrics.py:

- import SemanticMatch;
- add semantic_matches: list[SemanticMatch] to NormalizedResult;
- copy result.semantic_matches in normalize_results;
- add semantic_matches to _result_payload.

Use:

~~~python
"semantic_matches": [
    {
        "variant_id": match.variant_id,
        "score": match.score,
    }
    for match in result.semantic_matches
],
~~~

- [ ] **Step 5: Gate the case on the selected profile expectation**

In src/context_search_tool/quality/runner.py, import Gate and add:

~~~python
def _apply_profile_expectations(
    case: QualityCase,
    profile: str,
    bundle: QueryBundle,
    evaluation: CaseEvaluation,
) -> CaseEvaluation:
    expectation = case.profile_expectations.get(profile)
    if expectation is None:
        return evaluation

    failures = list(evaluation.failures)
    if (
        expectation.planner_status is not None
        and bundle.planner.status != expectation.planner_status
    ):
        failures.append(
            "planner_status expected "
            f"{expectation.planner_status}, got {bundle.planner.status}"
        )
    if (
        expectation.variant_retrieval_status is not None
        and bundle.variant_retrieval_status
        != expectation.variant_retrieval_status
    ):
        failures.append(
            "variant_retrieval_status expected "
            f"{expectation.variant_retrieval_status}, got "
            f"{bundle.variant_retrieval_status}"
        )

    actual_planner_match = bool(
        bundle.results
        and any(
            match.variant_id.startswith("planner:")
            for match in bundle.results[0].semantic_matches
        )
    )
    expected_planner_match = (
        expectation.top_result_planner_semantic_match
    )
    if (
        expected_planner_match is not None
        and actual_planner_match != expected_planner_match
    ):
        failures.append(
            "top_result_planner_semantic_match expected "
            f"{str(expected_planner_match).lower()}, got "
            f"{str(actual_planner_match).lower()}"
        )

    status = evaluation.status
    if case.gate is Gate.REQUIRED:
        status = "fail" if failures else "pass"
    return replace(
        evaluation,
        status=status,
        failures=failures,
    )
~~~

Immediately after evaluate_case in run_quality_fixture:

~~~python
evaluation = _apply_profile_expectations(
    case,
    profile,
    bundle,
    evaluation,
)
~~~

Known-gap and informational status semantics remain unchanged; the Phase 1 cases are required gates.

- [ ] **Step 6: Serialize executed variants and status**

In _case_record add:

~~~python
"query_variants": [
    {
        "variant_id": variant.variant_id,
        "text": variant.text,
        "source": variant.source,
    }
    for variant in bundle.query_variants
],
"variant_retrieval_status": bundle.variant_retrieval_status,
~~~

Keep skipped/error records without these execution-only fields. They already carry explicit status and failure reason.

- [ ] **Step 7: Run quality metrics and runner suites**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  -q
~~~

Expected: PASS.

- [ ] **Step 8: Commit**

~~~bash
git add \
  src/context_search_tool/quality/metrics.py \
  src/context_search_tool/quality/runner.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py
git commit -m "feat: gate quality cases on hybrid execution"
~~~

### Task 9: Add the identical committed-snapshot Phase 1 case set

**Files:**

- Modify: src/context_search_tool/quality/runner.py
- Modify: tests/test_quality_runner.py
- Modify: tests/fixtures/retrieval_quality/queries.json
- Modify: tests/test_quality_catalog.py

- [ ] **Step 1: Write the expected Phase 1 catalog manifest first**

In tests/test_quality_catalog.py, add p1_vector_bge and p1_hybrid_bge to EXPECTED_PROFILE_CONFIGS:

~~~python
"p1_vector_bge": {
    "embedding": {
        "provider": "bge",
        "model": "bge-m3",
        "dimensions": 1024,
    },
    "query_planner": {"enabled": False},
},
"p1_hybrid_bge": {
    "embedding": {
        "provider": "bge",
        "model": "bge-m3",
        "dimensions": 1024,
    },
    "query_planner": {
        "enabled": True,
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "timeout_seconds": 30,
    },
},
~~~

Update EXPECTED_REPO_WIRING:

~~~python
(
    "java_spring_mini",
    ("ci", "p1_vector_bge", "p1_hybrid_bge"),
    "",
    "",
    "tests/fixtures/java-spring-mini",
    {},
),
(
    "cross_language_dashboard",
    ("planner", "p1_vector_bge", "p1_hybrid_bge"),
    "",
    "",
    "tests/fixtures/real_projects/cross_language_dashboard",
    {},
),
(
    "embedding_ab",
    ("ab_hash", "ab_bge", "p1_vector_bge", "p1_hybrid_bge"),
    "CST_QUALITY_AB_REPO",
    "embedding-ab",
    "tests/fixtures/real_projects/embedding_ab",
    {},
),
~~~

Add profile_expectations to _quality_case_manifest:

~~~python
"profile_expectations": {
    profile: {
        key: value
        for key, value in {
            "planner_status": expectation.planner_status,
            "variant_retrieval_status": (
                expectation.variant_retrieval_status
            ),
            "top_result_planner_semantic_match": (
                expectation.top_result_planner_semantic_match
            ),
        }.items()
        if value is not None
    }
    for profile, expectation in case.profile_expectations.items()
},
~~~

Add profile_expectations: {} to EXPECTED_NEW_CASE_DEFAULTS, then define manifest entries for the five new cases and update the existing dashboard and apply-audit entries. The selected Phase 1 case keys must be exactly:

~~~python
EXPECTED_P1_CASE_KEYS = {
    "java_spring_mini/apply-audit-endpoint",
    "java_spring_mini/audit-status-literal",
    "cross_language_dashboard/dashboard-cross-language",
    "cross_language_dashboard/dashboard-controller-path",
    "embedding_ab/access-validation-cross-language",
    "embedding_ab/blacklist-management-cross-language",
    "embedding_ab/order-service-symbol",
}
~~~

Add:

~~~python
def test_phase_one_profiles_select_identical_required_committed_cases() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    selected = {}
    for profile in ("p1_vector_bge", "p1_hybrid_bge"):
        selected[profile] = {
            f"{repo.repo_key}/{case.case_id}"
            for repo in fixture.repos
            for case in repo.queries
            if profile in repo.profiles
            and (not case.profiles or profile in case.profiles)
        }

    assert selected["p1_vector_bge"] == EXPECTED_P1_CASE_KEYS
    assert selected["p1_hybrid_bge"] == EXPECTED_P1_CASE_KEYS
    cases = _catalog_cases()
    assert all(cases[key].gate is Gate.REQUIRED for key in EXPECTED_P1_CASE_KEYS)
    assert sum(
        "cross_language" in cases[key].tags
        for key in EXPECTED_P1_CASE_KEYS
    ) == 3
~~~

Update the total catalog count from 39 to 44.

- [ ] **Step 2: Run the manifest tests and verify failure**

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_quality_catalog.py::test_catalog_profile_registry_and_inventory \
  tests/test_quality_catalog.py::test_catalog_repo_wiring_matches_approved_inventory \
  tests/test_quality_catalog.py::test_phase_one_profiles_select_identical_required_committed_cases \
  -q
~~~

Expected: FAIL because the two profiles and five new cases are not in the fixture.

- [ ] **Step 3: Add the two exact profile configs**

In tests/fixtures/retrieval_quality/queries.json, add:

~~~json
"p1_vector_bge": {
  "embedding": {
    "provider": "bge",
    "model": "bge-m3",
    "dimensions": 1024
  },
  "query_planner": {
    "enabled": false
  }
},
"p1_hybrid_bge": {
  "embedding": {
    "provider": "bge",
    "model": "bge-m3",
    "dimensions": 1024
  },
  "query_planner": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen3.5:4b-mlx",
    "timeout_seconds": 30
  }
}
~~~

Do not change ci, planner, calibration_bge, ab_hash, or ab_bge.

- [ ] **Step 4: Wire exact endpoint and literal cases to both profiles**

Change java_spring_mini profiles to:

~~~json
[
  "ci",
  "p1_vector_bge",
  "p1_hybrid_bge"
]
~~~

Give apply-audit-endpoint explicit profiles and expectations:

~~~json
"profiles": [
  "ci",
  "p1_vector_bge",
  "p1_hybrid_bge"
],
"profile_expectations": {
  "p1_vector_bge": {
    "planner_status": "disabled",
    "variant_retrieval_status": "original_only"
  },
  "p1_hybrid_bge": {
    "planner_status": "ok"
  }
}
~~~

Give workbench-audit-localized-cjk profiles ["ci"] so it does not enter Phase 1 accidentally.

Add:

~~~json
{
  "id": "audit-status-literal",
  "query": "INVOLVED_BY_ME",
  "profiles": [
    "p1_vector_bge",
    "p1_hybrid_bge"
  ],
  "tags": [
    "java_spring",
    "exact_literal"
  ],
  "gate": "required",
  "expected_top_k": [
    {
      "path": "src/main/java/com/example/audit/AuditStatus.java",
      "top_k": 3
    }
  ],
  "profile_expectations": {
    "p1_vector_bge": {
      "planner_status": "disabled",
      "variant_retrieval_status": "original_only"
    },
    "p1_hybrid_bge": {
      "planner_status": "ok"
    }
  }
}
~~~

- [ ] **Step 5: Wire the dashboard cross-language and exact-path cases**

Change cross_language_dashboard repo profiles to planner plus both Phase 1 profiles. Change dashboard-cross-language profiles to the same three and add:

~~~json
"profile_expectations": {
  "p1_vector_bge": {
    "planner_status": "disabled",
    "variant_retrieval_status": "original_only"
  },
  "p1_hybrid_bge": {
    "planner_status": "ok",
    "variant_retrieval_status": "hybrid",
    "top_result_planner_semantic_match": true
  }
}
~~~

Add:

~~~json
{
  "id": "dashboard-controller-path",
  "query": "src/main/java/com/example/dashboard/DashboardController.java",
  "profiles": [
    "p1_vector_bge",
    "p1_hybrid_bge"
  ],
  "tags": [
    "java_spring",
    "exact_path",
    "entrypoint"
  ],
  "gate": "required",
  "expected_top_k": [
    {
      "path": "src/main/java/com/example/dashboard/DashboardController.java",
      "top_k": 1
    }
  ],
  "preferred_rank": [
    {
      "path": "src/main/java/com/example/dashboard/DashboardController.java",
      "top_k": 1,
      "max_rank": 1,
      "role": "entrypoint"
    }
  ],
  "profile_expectations": {
    "p1_vector_bge": {
      "planner_status": "disabled",
      "variant_retrieval_status": "original_only"
    },
    "p1_hybrid_bge": {
      "planner_status": "ok"
    }
  }
}
~~~

- [ ] **Step 6: Add two cross-language cases and one exact-symbol case**

Add both Phase 1 profiles to the embedding_ab repo profile list, but leave its three existing informational A/B case profile lists unchanged.

Add these three required cases:

~~~json
{
  "id": "access-validation-cross-language",
  "query": "开门校验场景",
  "profiles": [
    "p1_vector_bge",
    "p1_hybrid_bge"
  ],
  "tags": [
    "java",
    "cross_language"
  ],
  "gate": "required",
  "expected_top_k": [
    {
      "path": "src/access/WhitelistValidation.java",
      "top_k": 5
    }
  ],
  "profile_expectations": {
    "p1_vector_bge": {
      "planner_status": "disabled",
      "variant_retrieval_status": "original_only"
    },
    "p1_hybrid_bge": {
      "planner_status": "ok",
      "variant_retrieval_status": "hybrid"
    }
  }
},
{
  "id": "blacklist-management-cross-language",
  "query": "黑白名单管理",
  "profiles": [
    "p1_vector_bge",
    "p1_hybrid_bge"
  ],
  "tags": [
    "java",
    "cross_language"
  ],
  "gate": "required",
  "expected_top_k": [
    {
      "path": "src/access/BlacklistManager.java",
      "top_k": 5
    }
  ],
  "profile_expectations": {
    "p1_vector_bge": {
      "planner_status": "disabled",
      "variant_retrieval_status": "original_only"
    },
    "p1_hybrid_bge": {
      "planner_status": "ok",
      "variant_retrieval_status": "hybrid"
    }
  }
},
{
  "id": "order-service-symbol",
  "query": "OrderService cancel method",
  "profiles": [
    "p1_vector_bge",
    "p1_hybrid_bge"
  ],
  "tags": [
    "java",
    "exact_symbol"
  ],
  "gate": "required",
  "expected_top_k": [
    {
      "path": "src/order/OrderService.java",
      "top_k": 1
    }
  ],
  "profile_expectations": {
    "p1_vector_bge": {
      "planner_status": "disabled",
      "variant_retrieval_status": "original_only"
    },
    "p1_hybrid_bge": {
      "planner_status": "ok"
    }
  }
}
~~~

- [ ] **Step 7: Complete the approved manifest entries and run offline catalog tests**

Update EXPECTED_NEW_CASES with the exact paths, ranks, profiles, tags, and
profile expectations above. Update
test_catalog_case_profiles_match_approved_selection to assert all profile
changes made in this task:

- java_spring_mini/apply-audit-endpoint has ci, p1_vector_bge, and
  p1_hybrid_bge;
- java_spring_mini/workbench-audit-localized-cjk remains ci-only;
- cross_language_dashboard/dashboard-cross-language has planner,
  p1_vector_bge, and p1_hybrid_bge;
- the five new P1 case keys have exactly the profiles specified in Steps 4–6.

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_catalog.py \
  tests/test_quality_planner.py -m "not integration" \
  -q
~~~

Expected: PASS. The snapshot SHA256 test remains unchanged because no committed source snapshot content changes.

- [ ] **Step 7A: Force both Phase 1 profiles onto committed snapshots**

The embedding_ab repo intentionally retains path_env and repo_dir_name for the
existing ab_hash and ab_bge workflows. The two Phase 1 profiles must ignore
those external candidates and use snapshot_path so all seven comparison cases
come from committed sources.

First add a hostile-environment regression in tests/test_quality_runner.py. Use
a QualityRepo with a valid snapshot_path plus valid path_env and smoke-root
directories, set both environment sources, and parameterize over
p1_vector_bge and p1_hybrid_bge. Require _resolve_repo_source to return the
snapshot_path ResolvedSource for both profiles. The test must fail against the
current non-CI precedence, which chooses path_env. Lock every canonical
non-snapshot profile—smoke, planner, calibration_bge, ab_hash, and ab_bge—to
the existing external-source precedence, including when a committed snapshot
is also available. A mutation that adds calibration_bge to the snapshot-only
set must fail this test.

Then make the smallest runner change: treat exactly ci, p1_vector_bge, and
p1_hybrid_bge as snapshot-only profiles in _resolve_repo_source. Reuse the
existing CI snapshot validation and safe locator behavior, with the selected
profile name in missing-path errors. Do not change path_env/smoke-root
precedence for smoke, planner, calibration, ab_hash, or ab_bge.

Run:

~~~bash
conda run -n base python -m pytest \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  -m "not integration" \
  -q
~~~

Expected: PASS. With CST_QUALITY_AB_REPO set to a valid hostile directory, an
independent resolver probe must still report snapshot_path for both Phase 1
profiles and path_env for ab_hash/ab_bge.

- [ ] **Step 8: Commit**

~~~bash
git add \
  tests/fixtures/retrieval_quality/queries.json \
  tests/test_quality_catalog.py
git commit -m "test: add phase one vector and hybrid gates"

git add \
  src/context_search_tool/quality/runner.py \
  tests/test_quality_runner.py
git commit -m "fix: pin phase one profiles to snapshots"

git add tests/test_quality_runner.py
git commit -m "test: preserve non-p1 source precedence"
~~~

### Task 10: Add the model-backed pair gate, document operation, verify, and close Phase 1 conditionally

**Files:**

- Create: tests/test_quality_p1.py
- Modify: docs/retrieval-quality.md
- Modify after successful model-backed acceptance: roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md

- [ ] **Step 1: Write the guarded focused acceptance test**

Create tests/test_quality_p1.py:

~~~python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from context_search_tool.quality.runner import run_quality_fixture


CATALOG = (
    Path(__file__).parent
    / "fixtures"
    / "retrieval_quality"
    / "queries.json"
)
P1_PROFILES = ("p1_vector_bge", "p1_hybrid_bge")
RUN_P1_ACCEPTANCE = os.environ.get("CST_RUN_P1_ACCEPTANCE") == "1"


def _case_index(report: dict) -> dict[tuple[str, str], dict]:
    return {
        (case["repo_key"], case["case_id"]): case
        for case in report["cases"]
    }


def _metric(report: dict, name: str, field: str) -> float:
    value = report["aggregate"]["metrics"]["overall"][name][field]
    assert isinstance(value, int | float)
    return float(value)


@pytest.fixture(scope="module")
def p1_reports() -> dict[str, dict]:
    if not RUN_P1_ACCEPTANCE:
        pytest.skip("set CST_RUN_P1_ACCEPTANCE=1 to run local model acceptance")
    return {
        profile: run_quality_fixture(CATALOG, profile, None, None)
        for profile in P1_PROFILES
    }


@pytest.mark.slow
@pytest.mark.integration
def test_phase_one_vector_and_hybrid_profiles_close_together(
    p1_reports: dict[str, dict],
) -> None:
    vector = p1_reports["p1_vector_bge"]
    hybrid = p1_reports["p1_hybrid_bge"]
    vector_cases = _case_index(vector)
    hybrid_cases = _case_index(hybrid)

    assert set(vector_cases) == set(hybrid_cases)
    assert {
        key: case["gate"] for key, case in vector_cases.items()
    } == {
        key: case["gate"] for key, case in hybrid_cases.items()
    }
    assert len(vector_cases) == 7
    assert all(case["gate"] == "required" for case in vector_cases.values())
    assert all(case["status"] == "pass" for case in vector_cases.values())
    assert all(case["status"] == "pass" for case in hybrid_cases.values())

    for case in vector_cases.values():
        assert case["planner"]["status"] == "disabled"
        assert case["variant_retrieval_status"] == "original_only"
        assert case["query_variants"][0]["variant_id"] == "original"

    assert all(
        case["variant_retrieval_status"] != "embedding_fallback"
        for case in hybrid_cases.values()
    )

    cross_language = [
        case
        for case in hybrid_cases.values()
        if "cross_language" in case["tags"]
    ]
    assert len(cross_language) == 3
    assert all(case["planner"]["status"] == "ok" for case in cross_language)
    assert all(
        case["variant_retrieval_status"] == "hybrid"
        for case in cross_language
    )
    dashboard = hybrid_cases[
        ("cross_language_dashboard", "dashboard-cross-language")
    ]
    assert dashboard["top_results"]
    assert any(
        match["variant_id"].startswith("planner:")
        for match in dashboard["top_results"][0]["semantic_matches"]
    )

    assert _metric(hybrid, "mrr", "mean") >= _metric(
        vector,
        "mrr",
        "mean",
    )
    assert _metric(hybrid, "recall_at_5", "mean") >= _metric(
        vector,
        "recall_at_5",
        "mean",
    )
    assert _metric(hybrid, "entrypoint_top3", "rate") >= _metric(
        vector,
        "entrypoint_top3",
        "rate",
    )
~~~

The explicit environment switch keeps ordinary offline pytest runs model-independent. When the switch is enabled, missing BGE/Qwen causes profile errors or failed case assertions; it cannot be mistaken for closure.

Factor the core report assertions into a private helper used by the guarded
integration test. Add an unguarded deterministic regression with an otherwise
valid seven-case pair report whose non-cross-language hybrid case reports
embedding_fallback; the shared helper must reject it. This keeps the
no-fallback closure rule mutation-tested without invoking either model.

- [ ] **Step 2: Run the test without the switch**

Run:

~~~bash
conda run -n base python -m pytest tests/test_quality_p1.py -q
~~~

Expected: the deterministic fallback regression passes and the guarded model
test skips with the explicit CST_RUN_P1_ACCEPTANCE instruction.

- [ ] **Step 3: Document both Phase 1 profile commands and dependency semantics**

In docs/retrieval-quality.md:

- add p1_vector_bge and p1_hybrid_bge to the profile table;
- state that both use the identical seven required committed-snapshot cases;
- add commands:

~~~bash
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_vector_bge \
  --output .quality/p1-vector-bge.json \
  --markdown .quality/p1-vector-bge.md

conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_hybrid_bge \
  --output .quality/p1-hybrid-bge.json \
  --markdown .quality/p1-hybrid-bge.md

CST_RUN_P1_ACCEPTANCE=1 \
conda run -n base python -m pytest \
  tests/test_quality_p1.py \
  -m integration \
  -q
~~~

Document these interpretation rules:

- p1_vector_bge requires local bge-m3.
- p1_hybrid_bge requires local bge-m3 and qwen3.5:4b-mlx.
- missing service/model means unverified_dependency;
- skipped, error, fallback, or zero-executed runs cannot close Phase 1;
- the focused pair test, not the general comparison command alone, enforces the Phase 1 aggregate delta gate;
- both reports record latency mean, p50, and p95 under aggregate.metrics.overall.latency_ms.
- the documented `cst` commands assume the executable imports the current
  checkout. For editable installs or multiple worktrees, document an import
  path preflight and the `PYTHONPATH="$PWD/src"` prefix. State that
  `tool.git_commit` alone does not prove Python import provenance.

- [ ] **Step 4: Run all offline verification**

Run:

~~~bash
conda run -n base python -m pytest tests/test_query_planner.py -q
conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py \
  tests/test_rerank_soft_sorting.py \
  tests/test_formatters.py \
  tests/test_mcp_tools.py \
  -q
conda run -n base python -m pytest tests/test_quality_*.py -m "not integration" -q
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/ci-p1-check.json \
  --markdown .quality/ci-p1-check.md
conda run -n base python -m pytest -q
~~~

Expected:

- all focused suites pass;
- ci selects and passes its existing eight required cases;
- the full suite passes, with only explicitly guarded integration tests skipped.

- [ ] **Step 5: Run required model-backed acceptance**

Confirm the local service contains both required models, then run:

~~~bash
ollama list
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_vector_bge \
  --output .quality/p1-vector-bge.json \
  --markdown .quality/p1-vector-bge.md
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_hybrid_bge \
  --output .quality/p1-hybrid-bge.json \
  --markdown .quality/p1-hybrid-bge.md
CST_RUN_P1_ACCEPTANCE=1 \
conda run -n base python -m pytest \
  tests/test_quality_p1.py \
  -m integration \
  -q
~~~

Expected:

- both profiles select, execute, and pass seven of seven required cases;
- every cross-language hybrid case records planner status ok and variant status hybrid;
- dashboard-cross-language Top 1 contains a planner semantic match;
- MRR mean, Recall@5 mean, and entrypoint Top3 rate do not decline from vector to hybrid;
- both reports contain latency mean, p50, and p95.

If ollama list lacks either model, the service is unavailable, a report has skipped/error cases, or the focused test fails, record the missing/failing dependency as unverified_dependency and stop before the roadmap edit. Do not change the 0.85 weight or the case gates silently; return to the design/plan checkpoint with both reports.

- [ ] **Step 6: Mark Phase 1 complete only after Step 5 passes**

In roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md:

- add Status: Complete (2026-07-13) below the Phase 1 heading;
- add the design and operational-guide paths;
- list p1_vector_bge and p1_hybrid_bge as verified;
- replace the outdated static-lexicon bullet with the implemented bounded multi-query vector recall and semantic provenance;
- state that exact path, symbol, endpoint, and literal cases remained required gates;
- state that missing model dependencies remain unverified_dependency and never count as completion.

Do not alter Phase 2, Phase 3, or Phase 4 scope.

- [ ] **Step 7: Run final artifact and diff checks**

Run:

~~~bash
rg -n \
  "p1_vector_bge|p1_hybrid_bge|variant_retrieval_status|semantic_matches|Phase 1" \
  docs/retrieval-quality.md \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md \
  tests/fixtures/retrieval_quality/queries.json
git diff --check
git status --short
~~~

Expected:

- both profiles and provenance fields appear in the intended docs/fixture;
- git diff --check prints nothing;
- only files named in this plan are modified or created.

- [ ] **Step 8: Commit the acceptance gate and documentation**

If Step 5 passed and the roadmap was updated:

~~~bash
git add \
  tests/test_quality_p1.py \
  docs/retrieval-quality.md \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
git commit -m "docs: close phase one query understanding"
~~~

If Step 5 was unverified_dependency, omit the roadmap from the commit:

~~~bash
git add tests/test_quality_p1.py docs/retrieval-quality.md
git commit -m "test: add phase one model acceptance gate"
~~~

## Final Verification Matrix

| Requirement | Deterministic verification | Model-backed verification |
| --- | --- | --- |
| Variant order, bounds, dedupe, stable IDs | tests/test_query_planner.py | report query_variants |
| One retrieval-layer batch + 1 + N searches | controlled provider/store tests | p1_hybrid_bge runtime report |
| Original-only fallback | retrieval unit/integration tests | failed batch cannot report hybrid |
| Max blend and negative-score preservation | tests/test_rerank_soft_sorting.py | pair aggregate gate |
| Exact evidence protection | endpoint/path/symbol/literal fixture gates | both P1 profiles |
| Semantic provenance through merged output | retrieval merge tests | top-result semantic_matches |
| JSON/MCP additive contract | formatter and MCP tests | quality report inspection |
| Feedback privacy | MCP feedback hash test | no rewrite text in raw log |
| Same required case/gate set | catalog and acceptance tests | seven cases in each report |
| No MRR/Recall@5/entrypoint Top3 decline | focused acceptance helper logic | CST_RUN_P1_ACCEPTANCE=1 |
| Latency recorded | aggregate unit coverage | both P1 reports |
| Roadmap closure gate | conditional roadmap step | only after both profiles pass |

## Stop Point

This plan ends after Phase 1 verification and the conditional roadmap update. Do not begin ContextPack, RetrievalTrace/core decomposition, multi-round exploration, or any Phase 2–4 work in the same execution.
