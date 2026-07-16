# Fast-Context-Like Retrieval Roadmap

Date: 2026-07-08
Status: Long-term roadmap
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Next-stage review: Phase 4 controlled multi-round exploration design review

## Summary

Context Search Tool should grow from a local hybrid code search tool into a fast-context-like code context retrieval engine.

The target is not to clone fast-context or RagCode feature by feature. The target is to keep CST's current strengths - local indexing, speed, precise lexical and symbol matching, explainable scores, and MCP integration - while closing the quality gaps that make fast-context stronger during exploratory coding work:

- natural-language query understanding, especially Chinese business terms mapped to English code concepts;
- multi-round, controlled exploration instead of a single fixed retrieval pass;
- coherent context packs that tell an agent what to read, why it matters, what is missing, and what to search next;
- stronger file-role, relation, and framework-aware ranking;
- measurable quality improvements against real repositories.

This roadmap is intentionally long-term. Concrete implementation plans should be derived from it one milestone at a time.

## Product Direction

CST should answer a coding agent's retrieval question:

> "Given this vague or precise request, what code should I read first, what supporting evidence matters, and is the retrieved context sufficient for the next development step?"

That means CST should remain a retrieval tool, not become a full autonomous coding platform. Its core job is to find, rank, group, and explain code context better than grep and faster or more locally than an AI-only search loop.

Fast-context is the main quality reference because it is strong at exploratory search. RagCode is a useful architectural reference for verified context packaging, freshness, and agent-facing contracts, but CST should only borrow the parts that improve retrieval quality and agent usability.

## Current Strengths

CST already has a solid base:

- Local per-repository index stored under `.context-search/`.
- Hybrid retrieval across SQLite FTS, vector search, path and symbol signals, token coverage, code signals, and relation expansion.
- Strong exact-match behavior for endpoints, class names, method names, constants, and business keywords already present in code.
- Java/Spring signal extraction and relation hints.
- Generic language baseline across common source suffixes.
- Frontend role/cohort reranking work in progress through design docs and fixtures.
- MCP tools for indexing, querying, stats, and explain.
- Real test coverage and real-project quality fixtures.

The long-term strategy should preserve these advantages instead of replacing them with a model-only search flow.

## Current Gaps

The main gaps compared with fast-context-like behavior are:

- Cross-language understanding: Chinese queries such as `数据看板统计图表功能` need to surface English code such as `DashboardController`, `StatisticsService`, and chart-related implementation.
- Exploration: the retrieval flow is mostly a single pass. It does not yet run bounded follow-up searches from the first result set.
- Context grouping: results are ranked snippets, but not yet packaged as a task-oriented reading set with entrypoints, implementations, types, tests, configs, and missing evidence.
- Traceability: score parts exist, but there is no complete retrieval trace showing candidate sources, stage counts, rerank decisions, and why a result survived.
- Architecture pressure: `retrieval.py` has accumulated candidate collection, relation expansion, ranking, formatting support, and explanation logic in one large module.
- Evaluation fragmentation: metrics, real-project fixtures, calibration, A/B comparisons, and MCP feedback logs exist, but they are not yet one product-quality loop.
- Large-repository operation: index status, freshness, vector coverage, and incremental behavior can become more explicit before adding service or watch modes.

## Design Principles

### Local First, Model Optional

CST should work offline with hash embeddings and deterministic retrieval. Local or remote models can improve query planning, semantic retrieval, or reranking, but model failure must not break basic search.

### Exact Evidence Must Stay Strong

Fast-context-like exploration should not weaken CST's current advantage on exact code clues. Endpoint strings, symbols, file paths, constants, and direct business keywords should still rank reliably.

### Explore Under Budget

Multi-round retrieval should be bounded. Each round needs a clear purpose, such as finding entrypoints, expanding relations, finding tests, or validating supporting types. The system should prefer a compact, useful context pack over a large dump.

### Explainable By Default

Every result should preserve provenance: which query variant found it, which retrieval source contributed it, which relation expanded it, and which rerank rule changed its score.

### Generic Core Before Plugin Depth

Framework plugins should deepen quality for important ecosystems, but new repositories should be useful before a plugin exists. Generic file roles, path signals, symbol signals, and noise policies remain part of the core.

### Quality Gates Before Big Rewrites

Major ranking or architecture changes should be protected by real-project fixtures and A/B comparisons. The project should not swap embedding models, add a reranker, or refactor the retrieval core without measurable safety checks.

## Target Architecture

The long-term retrieval flow should evolve toward this shape:

```text
User Query
  -> Query Understanding
       -> normalized terms
       -> translated/domain terms
       -> rewritten query variants
       -> likely symbols and paths
       -> intent hints
  -> Multi-Source Recall
       -> exact/path/symbol recall
       -> lexical/FTS recall
       -> semantic recall
       -> plugin signal recall
  -> Controlled Exploration
       -> entrypoint expansion
       -> import/call/type relation expansion
       -> test/config/doc evidence expansion
       -> bounded follow-up searches
  -> Ranking And Grouping
       -> direct evidence
       -> semantic relevance
       -> file role and noise policy
       -> relation proximity
       -> feature cohort coherence
  -> Context Packing
       -> entrypoints
       -> implementations
       -> related types
       -> tests
       -> configs/docs
       -> missing evidence
       -> next queries
  -> Trace And Feedback
       -> retrieval trace
       -> score breakdown
       -> quality metrics
       -> MCP feedback log
```

## Roadmap Phases

### Phase 0: Quality Control Loop

Status: Complete (2026-07-11)

Operational guide: `docs/retrieval-quality.md`
Canonical catalog: `tests/fixtures/retrieval_quality/queries.json`
Required verified profiles: `ci`, `smoke`, `ab_hash`

Profile status:

| profile | status |
| --- | --- |
| ci | verified |
| smoke | verified |
| planner | verified |
| calibration_bge | verified |
| ab_hash | verified |
| ab_bge | verified |

Goal: make retrieval quality measurable before deeper changes.

Work:

- Unify existing real-project fixtures, calibration tests, A/B comparisons, and MCP feedback logs into one quality workflow.
- Track metrics such as Recall@K, MRR, entrypoint Top1/Top3, noise-in-top-K, cross-language success, and latency.
- Keep fixtures for Java/Spring, generic language baseline, frontend workflows, and Chinese-query-to-English-code cases.
- Add a standard command or test profile for comparing the current branch against a baseline branch.

Success signal:

- A ranking change can be judged by quality deltas instead of manual result inspection alone.
- Known fast-context comparison gaps become repeatable tests or documented benchmark cases.

### Phase 1: Query Understanding

Status: Implementation complete; model acceptance pending

Latest acceptance check (2026-07-16): both required model profiles selected and
executed seven cases but passed 6/7. `audit-status-literal` still misses
`AuditStatus.java` within Top-3, so the focused pair gate and Phase 1 roadmap
closure remain pending.

Goal: reduce the gap on natural-language and cross-language queries while preserving exact search.

Work:

- Stabilize the existing optional query planner around bounded structured output.
- Add a lightweight domain lexicon for common Chinese business terms and English code terms.
- Build a repository profile from indexed symbols, paths, languages, and common framework terms.
- Use query variants as recall hints with clear provenance, not as hard facts.
- Tune dynamic source weights so semantic and planner hints can matter when the original query is vague or cross-language, without drowning direct exact matches.

Success signal:

- Queries like `数据看板统计图表功能` can surface dashboard/statistics/chart code without requiring the user to know English class names.
- Planner failure or timeout falls back to normal retrieval cleanly.

### Phase 2: Context Pack Output

Status: Complete (2026-07-16)

Acceptance evidence at `be03fa73437cd897d112377d80dda5c83370def5`:

- full suite: 1,832 passed and 9 skipped;
- focused P2/P2.1 deterministic suite: 1,278 passed and 6 skipped;
- deterministic ContextPack v2 profile: 5/5 passed;
- raw-result CI profile: 8/8 passed;
- pinned real-project ContextPack v2 profile: 4/4 passed.

Phase statuses are recorded independently: the open Phase 1 model-quality gate
remains pending and is not weakened or reclassified by Phase 2 completion.

Goal: return a reading set, not only a ranked list.

Work:

- Introduce a `ContextPack` contract for CLI JSON and MCP output.
- Group results into entrypoints, implementations, related types, tests, configs/docs, and evidence anchors.
- Include `missing_evidence`, `next_queries`, `confidence`, and budget information.
- Keep the existing `results` list for compatibility while adding a richer pack for agents.
- Start with deterministic grouping from current retrieval results; do not require a new graph engine first.

Success signal:

- An agent can use one CST response to decide what to read first and what follow-up query to run next.
- The output explains when the retrieved context is incomplete instead of pretending every search is sufficient.

### Phase 3: Retrieval Trace And Core Decomposition

Status: Complete (2026-07-16)

- P3.1 RetrievalTrace v1: complete (2026-07-16).
  Design: `docs/superpowers/specs/2026-07-16-p3-1-retrieval-trace-v1-design.md`.
  Plan: `docs/superpowers/plans/2026-07-16-p3-1-retrieval-trace-v1.md`.
  Implementation commit: `34c5b5bd2189fbba4ead3902342706266c399b41`.
  Verification evidence:

  - full suite: 1,884 passed and 9 skipped;
  - focused P3.1 suite: 125 passed;
  - three committed Java, frontend, and documentation cases: TraceCoverage 1.0;
  - `cst-p3-1-p2.json`: `p2_context_pack` selected/executed/passed 5/5/5,
    failed 0, errors 0;
  - `cst-p3-1-ci.json`: raw `ci` selected/executed/passed 8/8/8,
    failed 0, errors 0.

  Phase 1 remains pending at its independent 6/7 baseline; P3.1 does not weaken
  or reclassify that gate.
- P3.2 retrieval-core decomposition: complete (2026-07-16).
  Design: `docs/superpowers/specs/2026-07-16-p3-2-retrieval-core-decomposition-design.md`.
  Plan: `docs/superpowers/plans/2026-07-16-p3-2-retrieval-core-decomposition.md`.
  Acceptance: full suite `1,938` passed with the exact baseline `9` skips and
  no xfails; focused P3.1/P3.2 gate `76` passed; 13 cases and four full-stage
  ledgers matched; TraceCoverage `1.0`; P2 `5/5`; raw CI `8/8`.

Goal: make the retrieval engine easier to improve.

Work:

- Add `RetrievalTrace` with source counts, query variants, candidate provenance, stage top-N, rerank adjustments, and final selection reasons.
- Split the retrieval core into smaller modules:
  - candidate source collection;
  - relation and cohort expansion;
  - ranking policy;
  - context packing;
  - explanations and trace formatting.
- Preserve behavior through tests before changing ranking logic.

Success signal:

- Developers can inspect why a result ranked high or low without reading the whole retrieval module.
- Future features can be added to one stage without touching every part of the retrieval pipeline.

### Phase 4: Controlled Multi-Round Exploration

Goal: approximate fast-context's exploratory strength in a deterministic, bounded local engine.

Work:

- Run an initial recall pass to find likely entrypoints and high-confidence symbols.
- Generate bounded follow-up probes from top results, such as related symbol names, imports, endpoint paths, route names, DTO names, and test names.
- Expand from entrypoints to implementation, types, tests, configs, and docs using existing relations first, then fallback path and lexical probes.
- Stop based on budget, marginal gain, duplicate coverage, and confidence.
- Record each exploration round in `RetrievalTrace`.

Success signal:

- Flow-style queries return controller/service/interface/DTO/test clusters rather than isolated snippets.
- Frontend feature queries return route/view/service/store/utility/type clusters with reduced noise.
- Multi-round mode improves difficult exploratory queries without slowing exact queries unnecessarily.

### Phase 5: Language And Framework Graphs

Goal: make relation expansion more precise for high-value ecosystems.

Work:

- Deepen Java/Spring support with AST-backed symbols, method calls, controller-service relations, annotations, MyBatis XML, and test linkage.
- Add frontend route/import graph support for Vue/React/TypeScript projects.
- Add generic test association heuristics across Java, Go, Rust, Python, and TypeScript.
- Consider later plugins for Go, Rust, and Python only after generic retrieval metrics show the need.

Success signal:

- CST can follow common business flows across framework boundaries instead of relying mostly on textual co-occurrence.
- Plugins improve depth but are not required for baseline usefulness.

### Phase 6: Freshness, Performance, And Large Repositories

Goal: make CST dependable on larger repositories and repeated agent use.

Work:

- Expand `status` and `stats` to include freshness, stale files, skipped files, vector coverage, embedding config, and index health.
- Profile full-scan paths in SQLite search and vector search.
- Improve vector search performance or introduce an approximate index only after profiling shows a real need.
- Add lazy refresh for files touched since the last index.
- Consider optional service/watch mode after status semantics and incremental refresh are reliable.

Success signal:

- Agents can tell whether the index is fresh enough for a query.
- Large repository queries stay within clear latency and memory budgets.
- Incremental workflows are reliable before any daemon-style experience is introduced.

### Phase 7: Optional Product Surfaces

Goal: improve usability after the retrieval core is strong.

Possible work:

- Quality reports that show benchmark changes between branches.
- A small local dashboard for inspecting index health and retrieval traces.
- Review-diff helpers that call the retrieval engine for changed files.
- Project memory only if it clearly improves retrieval and can be kept separate from source indexing.

Success signal:

- Product surfaces make the retrieval engine easier to trust, not broader for its own sake.

## API Direction

The MCP and CLI should evolve without breaking current users.

Existing behavior:

- `context_search_query` returns ranked results, score parts, reasons, and follow-up keywords.

Potential additions:

- `context_search_context`: returns a `ContextPack` optimized for coding agents.
- `context_search_trace`: exposes retrieval diagnostics for debugging and evaluation.
- Enhanced `context_search_stats`: reports freshness and vector/index health.

The current query output should remain available. Richer outputs should be additive, versioned, and easy for agents to consume.

## Quality Metrics

The roadmap should be judged by these metrics:

- `Recall@K`: expected files appear in top K.
- `MRR`: important files move earlier.
- `EntryPointTopK`: user-facing entrypoint appears near the top for feature queries.
- `NoiseTopK`: lockfiles, generated files, broad config, and scratch files do not crowd top results.
- `CrossLanguageSuccess`: Chinese business query finds English code concepts.
- `ContextCompleteness`: pack includes entrypoint, implementation, types, and tests when available.
- `Latency`: exact queries remain fast; exploratory mode has a separate budget.
- `TraceCoverage`: final results have explainable provenance.

## Risks And Mitigations

### Planner Hallucination

Risk: a model planner may invent terms or symbols.

Mitigation: treat planner output as hints, cap list sizes, preserve provenance, and never filter only because a planner said so.

### Semantic Search Overpowers Exact Evidence

Risk: vague semantic matches may outrank direct code clues.

Mitigation: keep exact/path/symbol recall as protected signals and evaluate exact-query regressions separately.

### Multi-Round Search Becomes Slow

Risk: exploration improves quality but makes normal queries feel heavy.

Mitigation: keep exact mode fast, add budgets, stop early, and expose trace timings.

### Plugin Sprawl

Risk: every framework becomes a special case.

Mitigation: improve the generic core first, then add plugins only for repeated structures with measurable quality wins.

### Context Packs Hide Important Details

Risk: grouping may make output look cleaner while omitting needed code.

Mitigation: keep raw ranked results available, include missing evidence and next queries, and test context completeness.

## Recommended Next Milestones

The next implementation work should be split into separate specs and plans:

1. Quality loop consolidation: define benchmark commands and metrics from existing fixtures, A/B tests, and MCP feedback.
2. ContextPack v1: add an additive CLI JSON and MCP response shape using current retrieval results.
3. RetrievalTrace v1: expose candidate source counts, query variants, score changes, and final provenance.
4. Retrieval core decomposition: split the large retrieval module after trace and tests protect behavior.
5. Controlled exploration v1: add a budgeted second pass for entrypoint-to-supporting-code expansion.

This order keeps the project grounded: measure first, expose better context and
traceability second, decompose the protected retrieval core third, and only then
add multi-round exploration.
