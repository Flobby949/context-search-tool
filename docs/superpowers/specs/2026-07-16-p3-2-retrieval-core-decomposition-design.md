# P3.2 Retrieval Core Decomposition Design

Date: 2026-07-16
Status: Implemented and verified (2026-07-16)
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor: `docs/superpowers/specs/2026-07-16-p3-1-retrieval-trace-v1-design.md`
Baseline implementation: `34c5b5bd2189fbba4ead3902342706266c399b41`
Implementation plan: `docs/superpowers/plans/2026-07-16-p3-2-retrieval-core-decomposition.md`

## Summary

P3.2 decomposes the 5,035-line `retrieval.py` into stage-owned internal modules
without changing retrieval behavior. The existing `query_repository()` function
remains the explicit orchestration owner for the canonical fifteen P3.1 stages;
candidate collection, expansion, ranking, context expansion, final selection,
and trace observation move behind typed module boundaries.

This is a structural refactor only. P3.2 does not change scores, sort keys,
candidate limits, query planning, ContextPack output, RetrievalTrace schema v1,
CLI/MCP contracts, or feedback behavior. It does not fix the independent Phase 1
quality gap and does not begin controlled multi-round exploration.

The design deliberately avoids a generic stage framework. The pipeline remains
ordinary, readable Python with explicit calls and explicit P3.1 timing points.
The decomposition succeeds when developers can change one stage implementation
without editing unrelated stages, while exact pre-refactor JSON, Markdown,
ContextPack, trace-envelope, internal-result, and representative stage-ledger
fingerprints remain unchanged.

## Baseline And Roadmap Reconciliation

The design is prepared from `6e4eef4c61ecfdaaa6721e5d81a40832b90a4281`,
whose retrieval implementation is `34c5b5bd2189fbba4ead3902342706266c399b41`.
The verified baseline is:

- `retrieval.py`: 5,035 lines;
- full suite: 1,884 passed and 9 skipped;
- focused P3.1 suite: 125 passed;
- committed P3.1 Java, frontend, and documentation cases: TraceCoverage 1.0;
- `p2_context_pack`: selected/executed/passed 5/5/5;
- raw `ci`: selected/executed/passed 8/8/8;
- Phase 1 model acceptance: independently pending at 6/7.

At that reviewed baseline, P3.1 was complete and supplied the protected
observable stage contract, while Phase 3 as a whole remained open. P3.2 could
begin because its acceptance was structural and behavior-preserving; it did not
depend on closing the Phase 1 ranking gap.

## Motivation

`retrieval.py` currently owns several distinct responsibilities:

- the public `QueryBundle` and `TracedQueryBundle` contracts;
- repository preflight, query planning, and single-pass orchestration;
- semantic, lexical, path/symbol, direct-text, signal, and planner-hint recall;
- direct merge, anchor expansion, relation expansion, and candidate merge;
- score-part normalization, evidence classification, ranking, and cohort rerank;
- route, Spring, Java-context, frontend, identifier, project-scope, and artifact
  ranking policies;
- file context expansion, overlap merging, span normalization, and byte caps;
- result/evidence-anchor selection, summaries, reasons, and follow-up keywords;
- conversion of live values into RetrievalTrace observations.

The problem is not only file length. These responsibilities share private
functions and constants through file scope, so ownership is implicit. A change
to relation expansion, for example, is reviewed in the same physical unit as
route ranking, content capping, and final selection. Tests reinforce that
coupling: many directly access `retrieval._rank_chunks`, `_ExpandedResult`,
`_relation_expansion_candidates`, and other private names.

P3.1 now makes the logical pipeline observable. P3.2 can therefore move a stage
implementation while checking not just final results but raw source counts,
intermediate order, final-selection provenance, and normalized trace structure.

## Goals

1. Give each existing retrieval stage a clear internal module owner.
2. Keep `query_repository()` as the single explicit orchestration path.
3. Preserve the supported public retrieval façade, including the two bundle
   classes, four callable entry points/helpers, and the two expansion-limit
   constants defined below.
4. Preserve exact ordinary JSON and Markdown, ContextPack, normalized trace
   envelope, internal result diagnostics, and representative full-stage ledgers
   on committed deterministic fixtures.
5. Preserve P3.1 stage names, order, source-count semantics, preview bounds,
   timing boundaries, and feedback privacy.
6. Establish an acyclic dependency graph that prevents stage modules from
   reaching back into the public façade.
7. Move tests to the module that owns the behavior they exercise.
8. Remove temporary private compatibility aliases before P3.2 completion.
9. Make future stage-specific changes smaller and easier to review.

## Non-Goals

P3.2 does not:

- change score weights, thresholds, boosts, penalties, ceilings, or sort keys;
- change semantic, lexical, path/symbol, signal, anchor, or relation limits;
- change query planner prompts, variants, fallback, or token expansion;
- fix `audit-status-literal` or claim Phase 1 completion;
- add new relations, AST analysis, call graphs, import graphs, or framework rules;
- execute ContextPack `next_queries` or add multi-round retrieval;
- change ContextPack grouping, budgets, confidence, or byte serialization;
- change RetrievalTrace schema version 1 or add trace fields;
- add a stage registry, plugin interface, event bus, or dependency-injection
  framework;
- add configuration for internal module selection;
- persist trace or pipeline state;
- optimize SQLite, vector search, or file I/O while code is being moved;
- split ranking policy into a second hierarchy of micro-modules;
- preserve unsupported imports of private `retrieval._name` symbols or
  incidental imported dependencies as a public compatibility promise.

## Design Principles

### Behavior Before Structure

Each extraction moves existing code with the smallest possible import and name
changes. No extraction commit also tunes retrieval behavior. A useful cleanup
that changes score computation, ordering, or I/O is deferred to a separately
reviewed change.

### The Canonical Pipeline Stays Explicit

The fifteen P3.1 stages remain visible in `query_repository()` in canonical
order. P3.2 does not replace them with a loop over stage objects, a registry, or
callbacks. Explicit orchestration keeps early returns, data flow, and timing
boundaries reviewable.

### Modules Own Cohesive Stage Behavior

Module boundaries follow retrieval responsibilities, not arbitrary line counts.
A module owns its stage entry points, private helpers, and constants. Shared
pure primitives are extracted only when two or more stage modules genuinely use
them.

### Public Contracts Stay In Place

`QueryBundle`, `TracedQueryBundle`, `query_repository()`, `trace_repository()`,
`evidence_anchor_top_k()`, `normalize_score()`, `MAX_EXPANSION_DEPTH`, and
`MAX_EXPANSION_CANDIDATES` remain importable from
`context_search_tool.retrieval`. Both bundle classes remain defined there so
their field order, defaults, frozen behavior, equality, representation, and
module-qualified identity do not change.

The supported façade is normative:

| symbol | P3.2 ownership and compatibility rule |
| --- | --- |
| `QueryBundle` | remains defined in `retrieval.py`; exact dataclass contract is frozen |
| `TracedQueryBundle` | remains defined in `retrieval.py`; exact dataclass contract is frozen |
| `query_repository` | remains defined in `retrieval.py`; signature and behavior are frozen |
| `trace_repository` | remains defined in `retrieval.py`; signature and behavior are frozen |
| `evidence_anchor_top_k` | remains a public helper in `retrieval.py`; signature and values are frozen |
| `normalize_score` | remains a thin function defined in `retrieval.py` and delegates to `ranking.normalize_score`; signature, `__module__`, and values are frozen |
| `MAX_EXPANSION_DEPTH` | remains a value-preserving alias to `relation_policy.MAX_EXPANSION_DEPTH` |
| `MAX_EXPANSION_CANDIDATES` | remains a value-preserving alias to `relation_policy.MAX_EXPANSION_CANDIDATES` |

There is no new `__all__` in P3.2. Imported implementation dependencies that
happen to be visible today—including `tokenize_query`, `expand_lines`,
`NumpyVectorStore`, `SQLiteStore`, `provider_from_config`, and
`RetrievalTraceCollector`—are not supported façade symbols. Repository tests
that use those names as white-box seams move atomically to their owning modules.
Removing either the three supported compatibility exports or any supported
façade symbol requires a separate approved breaking-change design.

### Trace Is An Observer

Trace code reads stage outputs only after the live operation stops. It never
feeds data back into candidate selection or ranking. Ordinary queries do not
construct trace models, candidate previews, or rank history.

### No Permanent Compatibility Façade For Private Names

Temporary aliases may keep intermediate extraction commits runnable, but final
tests import internal behavior from its owning module. Leaving every private
name re-exported from `retrieval.py` would preserve the original coupling and
defeat the decomposition. The explicit `normalize_score` wrapper and two public
constant aliases above are permanent supported exports, not private migration
aliases.

## Approaches Considered

### Selected: Stage-Owned Modules With An Explicit Orchestrator

`retrieval.py` keeps public contracts and the canonical pipeline. Stage bodies
move into a private `retrieval_core` package. The orchestrator calls concrete
module functions and retains P3.1 start/stop points.

Advantages:

- preserves `QueryBundle` construction and trace total-duration placement;
- avoids an import cycle between a pipeline module and `retrieval.py`;
- avoids a second intermediate result object on ordinary queries;
- keeps the fifteen-stage contract visible in one place;
- moves the large, change-prone implementations out of the public module.

### Rejected: Move The Entire Pipeline Behind A Thin Façade

A new `retrieval_core.pipeline` could return a second bundle-shaped object or
require moving `QueryBundle`. The former adds an ordinary-query allocation and
duplicate contract; the latter changes class ownership and increases public
compatibility risk. A bundle factory callback avoids both but makes the core
depend on an awkward inversion solely for construction.

P3.2 does not need that complexity. The explicit orchestrator is itself the
protected stage map, while stage implementations are the part that needs
physical decomposition.

### Rejected: Generic Stage Interface And Registry

A `Stage` protocol with generic input/output dictionaries would reduce repeated
calls, but it would obscure concrete types, encourage free-form payloads, and
make early-return and timing semantics harder to audit. There is only one fixed
pipeline; a registry solves no current requirement.

### Rejected: Split By File Size Alone

Moving every 500 lines into a new file would create accidental dependencies and
utility dumping grounds. Responsibility and data ownership, not a line target,
determine the modules.

### Rejected: Rewrite Ranking While Moving It

Ranking contains the densest policy coupling and the largest test surface.
Changing its abstractions during extraction would make parity failures difficult
to attribute. P3.2 moves ranking as one cohesive responsibility. Any later
ranking-policy decomposition or redesign needs its own evidence and review.

## Target Architecture

```text
src/context_search_tool/
  retrieval.py                       public contracts + explicit orchestration
  retrieval_core/
    __init__.py                      package marker; no broad re-exports
    types.py                         _RankedChunk and _ExpandedResult
    ordering.py                      two stable dedupers + shared sort precision
    evidence_merge.py                pure score/evidence merge primitives
    relation_policy.py               shared relation limits and confidence floor
    file_roles.py                    existing generic file-role policy values
    candidates.py                    direct candidate sources and merging
    expansion.py                     anchor and relation expansion
    ranking.py                       ranking policy and cohort rerank
    context_expansion.py             file windows, overlap merge, caps, spans
    selection.py                     result/anchor selection and summaries
    tracing.py                       P3.1 observation adapters and finalization
  retrieval_trace/                  unchanged public trace-v1 package
```

The target does not add `retrieval_core.pipeline.py`. `retrieval.py` is the
pipeline owner by design.

### `retrieval.py`

The final module owns only:

- `QueryBundle`;
- `TracedQueryBundle`;
- `trace_repository()`;
- `query_repository()` and its explicit fifteen-stage orchestration;
- `evidence_anchor_top_k()`;
- the supported `normalize_score()` forwarding function and two expansion-limit
  aliases from the normative façade table;
- imports of the concrete internal modules used by the orchestrator.

It does not define candidate, expansion, ranking, context, selection, or trace
conversion helpers. The orchestrator uses module-qualified calls such as
`candidates.semantic_candidates(...)` rather than importing dozens of private
functions into file scope.

### `retrieval_core/types.py`

This module owns the internal values that cross stage boundaries:

- `_RankedChunk`, preserving every current field and default;
- `_ExpandedResult`, preserving every current field and
  private context-content behavior.

The leading underscores and class `__name__` values remain unchanged to avoid a
gratuitous rename. Their `__module__` values intentionally change from
`context_search_tool.retrieval` to `context_search_tool.retrieval_core.types`;
they are internal, and tests migrate to that owner. Public bundle `__module__`
values do not change.

Types used by only one module remain with that module:

- `RelationSeed` stays in `expansion.py`;
- `ChunkRole` and `SpringPathImplementor` stay in `ranking.py`;
- `FinalTraceInput` and `FinalTraceDecisions` stay in `selection.py`.

This avoids turning `types.py` into a dumping ground.

### `retrieval_core/ordering.py`

This module has an intentionally closed surface:

- `dedupe_lowered()`, preserving current `_dedupe()` lowercased output;
- `ordered_unique_preserving_case()`, preserving current `_ordered_unique()`
  first-value casing;
- `RERANK_SORT_DECIMALS`, preserving the one sort precision shared by ranking
  and expanded-result ordering.

It owns no policy weights, stage limits, or generic collection helpers. Adding
another primitive requires proving at least two named consumers and updating the
allowed-edge table.

### `retrieval_core/evidence_merge.py`

This module contains only shared, pure operations used across stage owners:

- score bounding;
- score-part dictionary merging;
- semantic-match merge and existing semantic-match ordering.

It does not own evidence policy, weights, reasons, or rerank decisions. Those
remain in `ranking.py`. Candidate-source interpretation and the current
`_normalized_score_parts()` behavior move to `candidates.py`, where they have a
single consumer, rather than being mislabeled as a shared primitive.

### `retrieval_core/relation_policy.py`

This module owns the immutable values shared by relation expansion and Spring
path ranking: `MAX_EXPANSION_DEPTH`, `MAX_EXPANSION_CANDIDATES`, and the existing
minimum relation-confidence threshold. It owns no traversal code. Relation
score decay remains expansion-only; Spring path depth remains ranking-only.

### `retrieval_core/file_roles.py`

Anchor expansion currently needs the same generic file-role policy used by
ranking to suppress generated schema and penalized template neighbors. The
existing `_GenericFileRole` value, its current numeric `source_boost`, `penalty`,
and `penalty_key` fields, classification constants, and predicates such as test,
generated-schema, lockfile-query, and generic-role classification move here
unchanged so expansion does not import the ranking engine.

`file_roles.py` therefore owns the existing classification result, including
its numeric fields. `ranking.py` owns how that result becomes signed score-part
entries and all other ranking policy. P3.2 does not redesign this boundary or
recalculate any value.

### `retrieval_core/candidates.py`

This module owns direct candidate production and direct merge:

- semantic recall and embedding fallback;
- lexical recall;
- path/symbol recall wrapper;
- direct-text probe generation and recall;
- signal recall and signal scoring;
- planner-hint recall;
- deterministic candidate merge;
- candidate-source normalization currently performed by
  `_normalized_score_parts()`;
- candidate-source constants used only by these operations.

The orchestrator calls each canonical recall stage separately. P3.2 removes the
current `_initial_candidates()` convenience aggregator because it hides four
protected stages behind one private function. Candidate order remains semantic,
lexical, path/symbol, then direct text, exactly as today.

Direct-text probes have an explicit seam: the orchestrator calls
`candidates.direct_text_probes(query, original_tokens)` once before starting the
`direct_text_recall` timer, then passes that list to
`candidates.direct_text_candidates(store, probes, config)`. The latter never
recomputes probes. This is the module form of today's orchestrator, which also
computes probes once before the timer and sends that list directly to the store;
it does not reuse the legacy private helper signature that accepts query and
tokens and would compute probes inside the timed call. Production allocation and
store-call counts, candidate values, and candidate order remain unchanged.

### `retrieval_core/expansion.py`

This module owns:

- anchor expansion and its same-file/directory helpers;
- relation expansion, depth/candidate limits, and relation-seed policy;
- expansion-only constants and limit logging.

It accepts and returns existing `RetrievalCandidate` collections. It does not
rank chunks, read source content, construct results, or emit trace models.

Direct merge and final candidate merge continue to use
`candidates.merge_candidates()` so one deterministic merge implementation owns
source, score-part, and semantic-match combination.

The moved expansion logger is constructed with the compatibility name
`context_search_tool.retrieval`; warning level, text, arguments, and count remain
unchanged. Logger identity may change only in a later separately reviewed
observability change.

### `retrieval_core/ranking.py`

This module moves ranking as one cohesive policy unit:

- chunk materialization and first-pass score-part construction;
- score normalization, evidence classification, priority, and rank tiers;
- rerank score calculation and ceiling behavior;
- route, Spring path, Java context, frontend, identifier, query-intent,
  project-scope, and artifact-role adjustments;
- final ranked sort key;
- frontend import cohort rerank.

Although this remains the largest internal module, P3.2 intentionally does not
split the tightly coupled score-part policy while moving it. It has two stage
entry points and one façade compatibility helper:

```python
rank_chunks(store, candidates, tokens, query) -> list[_RankedChunk]
apply_frontend_import_cohort_rerank(repo, ranked, query) -> list[_RankedChunk]
normalize_score(scores) -> list[float]  # delegated by retrieval.normalize_score
```

All other names are module-private. A later policy redesign must be separately
reviewed rather than hidden inside this structural refactor.

### `retrieval_core/context_expansion.py`

This module owns conversion from ranked chunks to file-backed expanded results:

- context-line and full-file expansion;
- content-byte caps;
- overlapping-result merge and deterministic sort;
- source-context joining;
- retrieval-span source classification and normalization.

This is retrieval result expansion, not ContextPack v2. The existing
`context_search_tool.context_pack` package remains unchanged and continues to
consume the final `QueryBundle`.

### `retrieval_core/selection.py`

This module owns:

- timed splitting of expanded items into code results and evidence anchors;
- duplicate-anchor, result-limit, and anchor-limit decisions;
- stop-after-selection conversion to `EvidenceAnchor` and `RetrievalResult`;
- stop-after-selection retrieval summary construction and per-result reasons;
- stop-after-selection follow-up keyword collection;
- `FinalTraceInput` and `FinalTraceDecisions`, created only when trace collection
  is explicitly active.

The API boundary is explicit:

```python
split_results_and_anchors(...)  # the only timed final_selection operation
assemble_query_output(...)      # summary/results/follow-ups after stage stop
```

The ordinary path retains the current two-value split return and does not
allocate trace decision lists or counters. The internal decision types use
selection-owned `Literal` aliases with kind values `result` and
`evidence_anchor`, and reason values `selected_within_result_limit` and
`selected_within_anchor_limit`. `selection.py` does not import
`retrieval_trace`; `tracing.py` converts those values into the schema-v1 trace
models after the stage has stopped.

### `retrieval_core/tracing.py`

This module owns adapters from internal live values to the existing P3.1 trace
contract:

- trace query metadata conversion;
- stage start/stop helpers;
- candidate, ranked, and expanded previews;
- source counts and rank-position observation;
- bounded adjustments and final selections;
- collector finalization.

It imports `retrieval_trace` models and collector types. No other stage module
imports `retrieval_trace`. The public `retrieval_trace` package remains unchanged
and does not import `retrieval_core`.

### Existing Uncalled Helpers

P3.2 does not use a refactor as dead-code cleanup. The currently uncalled
`_candidate_base_score()` moves unchanged to `ranking.py`, and the currently
uncalled `_is_readme_document()` moves unchanged to `file_roles.py`. Focused
zero-caller evidence records that neither becomes a new production dependency.
Their deletion, if desired, is a separate cleanup.

## Dependency Direction

The AST boundary test uses this exact internal adjacency allowlist. An entry
lists the only `retrieval_core` or `retrieval_trace` packages that the row may
import; standard-library and existing non-retrieval domain imports are checked
separately but omitted here for readability.

| importer | allowed internal dependencies |
| --- | --- |
| `retrieval.py` | `retrieval_core.candidates`, `expansion`, `ranking`, `context_expansion`, `selection`, `tracing`, `ordering`, `relation_policy`; `retrieval_trace` |
| `retrieval_core.types` | none |
| `retrieval_core.ordering` | none |
| `retrieval_core.evidence_merge` | none |
| `retrieval_core.relation_policy` | none |
| `retrieval_core.file_roles` | none |
| `retrieval_core.candidates` | `ordering`, `evidence_merge` |
| `retrieval_core.expansion` | `evidence_merge`, `file_roles`, `relation_policy` |
| `retrieval_core.ranking` | `types`, `ordering`, `evidence_merge`, `file_roles`, `relation_policy` |
| `retrieval_core.context_expansion` | `types`, `ordering`, `evidence_merge` |
| `retrieval_core.selection` | `types`, `ordering` |
| `retrieval_core.tracing` | `types`, `ordering`, `selection`; `retrieval_trace` |
| `retrieval_trace.*` | none from `retrieval.py` or `retrieval_core` |
| `context_pack.*` | `retrieval.QueryBundle` only; none from `retrieval_core` |

The enforceable rules are:

1. No `retrieval_core` module imports `context_search_tool.retrieval`.
2. No stage-owner module imports another stage-owner module. The sole
   stage-related edge is `tracing -> selection`, used only for internal final
   decision values after selection has stopped.
3. Within `retrieval_core`, only `tracing.py` imports `retrieval_trace`.
   `retrieval.py` may import the collector and public trace type for its two
   public bundle/orchestration functions; existing formatter, CLI, and MCP trace
   imports remain unchanged.
4. `retrieval_trace` imports neither `retrieval.py` nor `retrieval_core`.
5. `context_pack` consumes `QueryBundle` and never imports `retrieval_core`.
6. `retrieval.py` uses module-qualified stage calls and does not re-export their
   private functions at P3.2 completion.
7. Low-level modules may not grow unlisted core dependencies. In particular,
   neither `types.py` nor `ordering.py` becomes a generic utility owner.

The allowlist defines dependency direction as `importer -> imported`. The
focused AST test rejects every unlisted edge, import cycle, star import,
package-level broad re-export, and aliased private re-export. Slice 1 starts
with a checked transitional allowlist containing the current façade ownership;
each slice removes named edges, and the list may only shrink toward this table.

## Protected Stage Mapping

| order | P3.1 stage | P3.2 operation owner | live output |
| ---: | --- | --- | --- |
| 1 | `query_understanding` | `retrieval.py` using existing planner modules | tokens, plan, variants, hints |
| 2 | `semantic_recall` | `candidates.semantic_candidates` | candidates, executed variants, status |
| 3 | `lexical_recall` | `candidates.lexical_candidates` | lexical candidates |
| 4 | `path_symbol_recall` | `candidates.path_symbol_candidates` | path/symbol candidates |
| 5 | `direct_text_recall` | `candidates.direct_text_candidates` | direct-text candidates |
| 6 | `signal_recall` | `candidates.signal_candidates` | signal candidates |
| 7 | `planner_hint_recall` | `candidates.planner_hint_candidates` | planner candidates |
| 8 | `direct_merge` | `candidates.merge_candidates` | ordered unique direct map |
| 9 | `anchor_expansion` | `expansion.anchor_candidates` | anchor candidates |
| 10 | `relation_expansion` | `expansion.relation_candidates` | relation candidates |
| 11 | `candidate_merge` | `candidates.merge_candidates` | ordered unique candidate map |
| 12 | `ranking` | `ranking.rank_chunks` | ranked chunks |
| 13 | `cohort_rerank` | `ranking.apply_frontend_import_cohort_rerank` | reranked chunks |
| 14 | `context_expansion` | `context_expansion.expand_ranked_chunks` | expanded results |
| 15 | `final_selection` | `selection.split_results_and_anchors` | visible results, anchors, optional trace decisions |

Stage names, source keys, decision keys, input/output/unique count semantics, and
preview order remain exactly those of RetrievalTrace schema v1.

## Execution Semantics

### Ordinary Query

`query_repository()` performs the same sequence as today:

1. resolve the repository and tokenize the original query;
2. return the same empty bundle when the index is missing;
3. validate the manifest and read deleted chunk IDs;
4. plan and expand the query;
5. call each candidate source in canonical order;
6. merge, expand, rank, rerank, and expand context;
7. select code results and evidence anchors;
8. build the same summary, results, follow-ups, and `QueryBundle`.

With `trace_collector=None`, no trace query, preview, decision ledger, rank map,
or clock read is created. Moving helpers does not add a second bundle, pipeline
state object, or candidate copy.

### Traced Query

`trace_repository()` remains the only collector constructor. It calls the same
`query_repository()` once. The orchestrator retains explicit stage start/stop
calls and delegates observation conversion to `retrieval_core.tracing` only
after each live operation has stopped.

Every observed stage follows one mechanically testable event sequence:

```python
token = tracing.start_stage(collector, stage_name, input_count=...)
live_output = owner.live_operation(...)
stopped = tracing.stop_stage(collector, token)
observations = tracing.observe_after_stop(collector, stopped, live_output, ...)
tracing.finish_stage(collector, stopped, observations, ...)
```

The control helpers may receive `collector=None` as they do today, but no
observation adapter executes in that case. The event-ledger test asserts that
the live operation returns before the stop clock read and that every preview,
rank-history update, trace selection conversion, and observation-only store
lookup occurs after that read. `direct_text_probes()` remains before the direct
text start event. `split_results_and_anchors()` is the complete timed
`final_selection` live operation; trace conversion, summary store reads,
`RetrievalResult` construction, follow-up collection, and `QueryBundle`
construction all occur after its stop event.

Collector finalization remains after `QueryBundle` construction, so total trace
duration retains its current boundary. Stage durations continue to exclude
preview conversion and store lookups used only for observations, while those
operations and output assembly remain included in total duration.

### Early Returns

The current outcome and stage-prefix rules remain:

| condition | outcome | termination | stages |
| --- | --- | --- | --- |
| missing index | `empty` | `missing_index` | none |
| handled deleted-ID store error | `partial` | `store_read_error` | none |
| no merged candidates | `empty` | `no_candidates` | stages 1-11 |
| successful execution | `complete` | `completed` | all 15 |

P3.2 does not add new handled exceptions or reinterpret an existing exception.
Focused tests freeze each branch beyond the short table:

- missing index: exact complete `QueryBundle`, JSON, and Markdown parity; no
  stage, planner, store construction, vector, or source-file stat/read beyond
  the existing repository/index resolution and index-exists preflight;
- deleted-ID `sqlite3.Error`: exact plain/traced bundle parity, no stage or
  planner/candidate work, and no broader exception class is caught;
- no candidates: exact bundle/JSON/Markdown parity, stages 1-11 with exact
  counts, and no ranking, context-expansion, summary, or source-file I/O;
- manifest incompatibility and planner/provider failures: the same exception
  type/message propagates, and CLI/MCP expose the same stable error contract
  without a partial public trace.

## Data And Ordering Contracts

### Candidate Collections

Stage functions return the same concrete list or insertion-ordered dictionary
shapes used today. Extraction must not replace them with sets, sorted snapshots,
generators, or generic stage-result objects.

The following order is protected:

- semantic candidates by executed variant and vector-store result order;
- direct candidates by semantic, lexical, path/symbol, direct text, signal, then
  planner hint contribution order;
- merge dictionaries by first-seen chunk ID;
- relation candidates by the existing score/chunk-ID sort;
- ranked and expanded values by their existing sort keys.

### Score Parts

Score-part names and numeric meanings remain unchanged. `evidence_merge.py`
moves only the pure shared merge primitives and must not centralize policy
constants or rename keys. Trace adjustment extraction continues to identify
existing non-zero keys by the schema-v1 suffix policy.

### Internal Dataclasses

`_RankedChunk` and `_ExpandedResult` retain exact class names, field order,
defaults, equality, and private `_context_content` behavior. Their expected
`__module__` change and test-import migration are the only identity changes.

### Public Bundles

`QueryBundle` and `TracedQueryBundle` remain unchanged in `retrieval.py`. Their
class names, `__module__`, frozen setting, field order/defaults, equality, and
representation are frozen. Raw query JSON/Markdown, ContextPack v2 canonical
bytes, MCP payloads, and quality-runner inputs do not gain core-module metadata.

## Characterization Baseline

Existing tests compare traced and untraced execution after the same code has
already changed. P3.2 additionally needs a pre-refactor baseline that cannot
drift together with the implementation.

Before moving code, Slice 1 adds a committed manifest generated from
implementation commit `34c5b5bd2189fbba4ead3902342706266c399b41`:

```text
tests/fixtures/retrieval_core_decomposition/baseline.json
```

The baseline commit is a standalone Slice 1 commit with no production changes.
Final evidence records that commit ID and the Git blob OID of `baseline.json`.
Every later slice verifies that the blob is identical; changing it stops P3.2
and requires a separate behavior-change review.

### Input Identity

Generation is valid only while the quality catalog and its four resolved
snapshot trees are identical to documentation baseline
`6e4eef4c61ecfdaaa6721e5d81a40832b90a4281`. Slice 1 rejects tracked, staged,
unstaged, and untracked drift; the manifest records the catalog blob OID, each
snapshot tree OID, and a working-tree content hash. The committed verifier
recomputes these identities and cleanliness conditions on every later
characterization run and in final acceptance. This prevents a fixture change
from being mistaken for retrieval parity.

### Case Universe

Fingerprints cover every current deterministic acceptance entry, not only a
representative subset:

| profile | exact case keys |
| --- | --- |
| `ci` | `program_tool/watermark-remover`, `program_tool/mqtt-tool`, `program_tool/qrcode-tool`, `program_tool/json-to-entity`, `program_tool/app-layout-theme`, `program_tool/ai-chat`, `java_spring_mini/apply-audit-endpoint`, `java_spring_mini/workbench-audit-localized-cjk` |
| `p2_context_pack` | `context_pack_java/workspace-page-flow`, `context_pack_java/workspace-test-file`, `context_pack_java/workspace-service-symbol`, `context_pack_frontend/qrcode-feature-context`, `context_pack_docs/program-tool-developer-docs` |

Each manifest entry stores the case key, exact query, snapshot identifier,
profile name, and the complete effective `ToolConfig` projection that affects
retrieval. The `ci` and `p2_context_pack` configurations come from the matching
`profile_configs` entries in
`tests/fixtures/retrieval_quality/queries.json`; ad hoc defaults are forbidden.
For all five P2 cases, the manifest also stores the complete resolved
`ContextPackOptions` returned by `resolve_context_pack_options(config,
context_lines=None, max_evidence_anchors=evidence_anchor_top_k(final_top_k))`.
The verifier compares that options object before building the pack. The quality
case ceilings remain `maximum_pack_bytes=65536` and
`maximum_truncated_items=4`.

### Public Byte Fingerprints

For all thirteen cases, record SHA-256 over the exact UTF-8 bytes returned by:

- `format_json(bundle).encode("utf-8")`;
- `format_markdown(bundle).encode("utf-8")`;
- the normalized trace-envelope procedure below.

For the five P2 cases, also record SHA-256 over
`canonical_context_pack_bytes(build_context_pack(bundle, resolved_options))`.
These are the production serialization functions; the verifier does not replace
their indentation, escaping, key order, separators, or `ensure_ascii` behavior
with a custom sorted representation.

The trace fingerprint is unambiguously the four-key formatter envelope, not the
bare `RetrievalTrace` payload:

1. call `trace_payload(repo, query, trace)`;
2. replace only envelope `repo` with the fixture identifier;
3. replace trace `duration_ms` and every stage `duration_ms` with integer `0`;
4. call `format_trace_json(normalized_envelope).encode("utf-8")`;
5. hash those bytes.

No key is removed or reordered. In particular, schema-v1 source-count and
decision-count insertion order stays observable because
`format_trace_json()` uses `ensure_ascii=True`, two-space indentation,
`sort_keys=False`, and `allow_nan=False`.

### Internal Bundle Diagnostic

The public raw payload intentionally omits some internal retrieval fields. All
thirteen cases therefore also hash a test-only, fixed-order diagnostic
projection containing:

- query, expanded tokens, planner, variants, status, summary, and follow-ups;
- every result in order with path, lines, scores, score parts, reasons,
  semantic matches, and complete `RetrievalSpan` values;
- SHA-256 of each result's `content` and optional `_context_content`, never the
  source text itself;
- every evidence anchor in order with all non-content public fields, plus
  SHA-256 of its `content` and optional `_context_content`; neither source string
  is stored.

The diagnostic serializer uses explicitly constructed fixed-order dictionaries,
ordered arrays, UTF-8, `ensure_ascii=True`, compact separators,
`sort_keys=False`, and `allow_nan=False`. It is test-only and is not imported by
production retrieval or trace code.

### Representative Full-Stage Ledger

Because RetrievalTrace intentionally bounds previews at five, four diverse
cases additionally receive a test-only full-stage ledger:

- `context_pack_java/workspace-page-flow`;
- `context_pack_frontend/qrcode-feature-context`;
- `context_pack_docs/program-tool-developer-docs`;
- `java_spring_mini/apply-audit-endpoint`.

The ledger records every item, in live order, at each of the fifteen stage
seams. Candidate stages include chunk ID, score, source, score parts, and every
semantic match; ranked stages add path/span, rank tier, evidence class/priority,
rerank/pre-ceiling scores, clamp state, reasons, and score parts; expanded and
selection stages add origin chunk IDs, complete spans, decisions, and hashes of
content/context content. The ledger also records executed variants and
operation-call order. It is captured by test wrappers at the existing
orchestrator seams, never by widening production RetrievalTrace or adding an
ordinary-path pipeline object.

Each case also records canonical stage names, exact source/decision counts,
final-selection count, and TraceCoverage. This makes top-five trace previews and
all later candidates independently observable.

### Ordinary And Traced Operation Ledgers

Every one of the thirteen cases also has two independent complete operation
ledgers: one from a plain `query_repository()` run and one from a separate
`trace_repository()` run. Spies reset between runs and label each entry with its
run and `live`/`observation` phase. Both ledgers freeze normalized planner,
embedding/fallback, vector, SQLite, index-existence, source-file stat/read, and
other store calls with their order and safe arguments. Observation-only work is
identified explicitly; ordinary behavior is never inferred from traced-path
wrappers.

Missing-index, store-error, no-candidate, planner-variant, ceiling, cohort,
anchor, and relation edge behavior remains covered by focused unit/integration
tests rather than hash-only cases.

The baseline manifest is immutable during P3.2. If a value needs to change, stop
and open a separately reviewed behavior change; do not update the baseline in
the same decomposition.

## Test Ownership Migration

The current test suite has extensive direct access to private names in
`retrieval.py`, including dozens of calls to `_rank_chunks` and constructions of
`_ExpandedResult`. P3.2 migrates those imports as functions move:

| behavior | final test owner/import |
| --- | --- |
| candidate recall and merge | `retrieval_core.candidates` |
| anchor and relation expansion | `retrieval_core.expansion` |
| ranking policy and cohort | `retrieval_core.ranking` |
| ranked/expanded types | `retrieval_core.types` |
| context expansion and overlap | `retrieval_core.context_expansion` |
| final selection and summary | `retrieval_core.selection` |
| trace conversion | `retrieval_core.tracing` |
| end-to-end public behavior | `context_search_tool.retrieval` |

Temporary aliases in `retrieval.py` are allowed only within an extraction slice
to keep intermediate commits green. The final boundary test fails if known
stage-private names remain defined or re-exported by `retrieval.py`.

Slice 1 creates a migration ledger from every existing test reference to
`retrieval.<name>` and every dynamic target in `scripts/profile_retrieval.py`.
AST visitors cover direct imports, qualified attributes, and multiline
monkeypatch/`patch.object` calls; the profiler target list is parsed explicitly.
Each row records the old symbol, new owner, direct imports, production call
sites, monkeypatch and profiler targets, migration slice, disposition, and
alias-removal commit. Supported façade rows retain their contract/count;
private/incidental `migrate` rows must reach zero. A slice is atomic across all
five kinds of reference:

1. move the definition;
2. change the production call to the module-qualified owner;
3. migrate direct unit-test imports;
4. migrate monkeypatch targets to the same owner.
5. migrate profiler targets to the same owner.

A value alias cannot preserve monkeypatch semantics once the orchestrator calls
the new owner, so aliases are never presented as monkeypatch forwarding layers.
They may serve only as short-lived direct-call compatibility inside the same
slice. Tests that patch `_semantic_candidates`, `_merge_candidates`,
`provider_from_config`, `NumpyVectorStore`, or trace adapters move their patch to
`retrieval_core.candidates` or `retrieval_core.tracing` in the same commit as the
production call-site change.

Tests are split into two explicit categories:

- black-box public tests import only the normative retrieval façade;
- white-box orchestration-seam and owner-unit tests may import/patch a named
  `retrieval_core` owner because they verify internal sequencing or policy.

The hand-built `_initial_candidates()` flows in `test_retrieval_pipeline.py` and
`test_quality_catalog.py` migrate in Slice 3 to the same four explicit recall
calls used by the orchestrator. Final AST verification scans all tests and the
profiler, permits only the eight normative façade symbols, and requires zero
private/incidental or stale dynamic targets.

## Migration Strategy

P3.2 is implemented in reviewable, behavior-preserving slices. Each slice ends
with its focused tests, the characterization baseline, and the full suite green.

### Slice 1: Lock Characterization And Import Rules

- add the immutable thirteen-case baseline manifest and verifier in a standalone
  commit, then record its commit ID and blob OID;
- freeze catalog/snapshot Git OIDs, content hashes, and the clean execution
  environment before generation;
- add exact dataclass identity tests for both public bundles and supported
  façade tests for `normalize_score` and the two limit constants;
- generate the AST-based reference/monkeypatch/profiler migration ledger;
- add profiler target-existence and wrapper-hit regression tests;
- add the AST import-boundary test with an explicit transitional allowlist that
  may only shrink;
- record the baseline test/quality counts;
- make no production move yet.

### Slice 2: Move Shared Internal Types And Pure Primitives

- create `retrieval_core/types.py`, `ordering.py`, `evidence_merge.py`,
  `relation_policy.py`, and `file_roles.py`;
- move types and pure helpers without changing bodies;
- add temporary aliases only where needed by unmigrated code/tests;
- migrate focused type/score/file-role tests to the new owners.

### Slice 3: Move Candidate Sources And Expansion

- create `candidates.py` and `expansion.py`;
- expose each recall stage separately to the orchestrator;
- preserve the compute-probes-before-start, pass-probes-once direct-text seam;
- remove `_initial_candidates()` after parity is established;
- preserve merge insertion order and expansion limits;
- atomically migrate candidate/expansion production calls, direct tests,
  monkeypatch targets, and both hand-built `_initial_candidates()` flows;
- remove candidate/expansion aliases from `retrieval.py`.

### Slice 4: Move Ranking As One Policy Unit

- create `ranking.py`;
- move ranking constants, policy helpers, `rank_chunks`, and cohort rerank;
- change only imports and module-qualified calls;
- migrate ranking and soft-sorting tests;
- retain the supported `retrieval.normalize_score()` forwarding function;
- run exact raw/ContextPack/trace fingerprints before removing aliases.

No scoring cleanup or submodule split is allowed in this slice.

### Slice 5: Move Context Expansion And Selection

- create `context_expansion.py` and `selection.py`;
- move file reads, caps, overlap/spans, anchor selection, summaries, and
  follow-ups;
- preserve the ordinary two-value selection path and trace-only decision path;
- keep only split/decision work inside `final_selection`; assemble summary,
  results, follow-ups, and bundle after the stop event;
- migrate their focused tests and remove aliases.

### Slice 6: Move Trace Adapters And Clean The Orchestrator

- create `tracing.py`;
- move all trace conversion helpers while leaving start/stop call sites explicit;
- keep collector finalization after bundle construction;
- enforce the operation -> stop -> observation event sequence;
- remove every temporary private compatibility alias;
- enable strict import-boundary and façade-symbol tests.

### Slice 7: Final Compatibility And Documentation

- run full, P3.1, P2, raw CI, and characterization gates;
- inspect skips and generated artifacts;
- document the final dependency graph and module ownership;
- update the P3.2 design status and roadmap only after all gates pass;
- stop before any ranking or multi-round implementation work.

## Verification Strategy

### Focused Module Tests

Each new module receives tests for the behavior it owns. Existing assertions are
moved rather than weakened. Tests use the same stores, fixtures, and exact
expected scores/order.

### Public Compatibility

Tests assert:

- `QueryBundle` and `TracedQueryBundle` names, `__module__`, frozen setting,
  fields/defaults, repr, and equality remain unchanged;
- `query_repository()` and `trace_repository()` signatures remain unchanged;
- every normative façade symbol remains importable with exact values/signature;
- raw query payloads and Markdown remain exact;
- ContextPack v2 canonical bytes remain exact;
- CLI and MCP success/error contracts remain exact;
- feedback logs remain unchanged by trace requests.

### P3.1 Trace Compatibility

Tests assert:

- schema version 1 and exact serialized keys;
- the canonical fifteen stages and source-count keys;
- normalized trace fingerprint equality to the pre-refactor manifest;
- early-return stage prefixes and outcomes;
- final-selection provenance, rank history, adjustments, and decisions;
- stage/final/adjustment bounds;
- the full operation -> stop -> observation event ledger with an injected clock;
- summary/result/bundle assembly before total finish but after final-stage stop;
- ordinary query does not call trace query/preview/rank-history/final-selection
  adapters or construct trace-only decisions.

### Dependency And Façade Tests

An AST-based test verifies the import rules and that `retrieval.py` defines only
the normative public contracts/orchestrators/wrappers. It rejects direct and
aliased private re-exports, star imports, unlisted core edges, and cycles. A
separate repository scan detects stale test references, dynamic profiler
targets, and temporary aliases that must not survive the final slice. Profiling
targets move atomically to their new owner modules and are covered by a wrapper-
hit regression test; silent missing-target skips are forbidden.

### Protected-Source Diff Gate

Relative to `34c5b5bd2189fbba4ead3902342706266c399b41`, P3.2 production changes are
limited to `retrieval.py` and the new `retrieval_core/` package. The final gate
rejects changes under `retrieval_trace/`, `context_pack/`, `quality/`, and public
`models.py`, plus `cli.py`, `formatters.py`, `mcp_server.py`, and `mcp_tools.py`.
Tests, the immutable characterization fixture, `scripts/profile_retrieval.py`,
design/plan documents, and the roadmap may change. The profiler is the only
allowed non-production consumer edit and may change only to follow extracted
owner modules. Any need to edit a protected production surface stops the
refactor for separate review.

### Quality Gates

The final acceptance reruns these commands under the implementation plan's one
explicit clean environment (all five optional acceptance/repository variables
unset):

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output /tmp/cst-p3-2-p2.json \
  --markdown /tmp/cst-p3-2-p2.md

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p3-2-ci.json \
  --markdown /tmp/cst-p3-2-ci.md
```

Required results remain P2 5/5 and raw CI 8/8. Phase 1 remains independently
pending unless a separate reviewed change genuinely closes its 7/7 gate.

## Error And Early-Return Compatibility

P3.2 introduces no new public error code or fallback. The following remain
unchanged:

- missing-index empty bundle and MCP `missing_index` preflight;
- handled deleted-chunk store error and partial trace outcome;
- manifest incompatibility behavior;
- planner/provider `ValueError` and HTTP error handling;
- CLI trace stable `Retrieval trace failed` message;
- MCP `trace_failed`, `query_failed`, and `repo_not_found` semantics;
- no partial public trace on trace assembly failure.

Internal modules do not catch broader exceptions than the current owner. Moving
a function must not silently turn an error into an empty candidate list.

## Performance And Allocation Constraints

The structural refactor must preserve operation counts and the ordinary
zero-trace path:

- one query-planner call;
- one primary semantic embedding batch and only the existing single
  original-query fallback retry when that batch fails or returns the wrong
  count;
- the same vector/store/file calls, arguments, and order;
- exactly one direct-text probe computation before its stage timer;
- no second candidate pipeline or bundle construction;
- no generic stage-result allocations;
- no collector, trace query, candidate/ranked/expanded preview, rank history,
  trace-final-selection adapter, or trace decision value for ordinary queries;
- no added sorting or collection conversion on live values.

Latency remains informational because wall-clock values vary. Focused spy tests
record an exact ordered ledger of planner, embedding, vector, SQLite, and source
file operations, including arguments and fallback branch. Ordinary-path tests
replace every trace observation/conversion adapter and trace-decision
constructor with a forbidden sentinel; only the existing no-op control-helper
calls with `collector=None` are permitted.

## Privacy And Persistence

The decomposition does not broaden the data surface:

- trace still contains no source content or absolute candidate paths;
- ordinary query and ContextPack output remain unchanged;
- `context_search_trace_tool()` still never writes feedback;
- no internal pipeline state is serialized or persisted;
- baseline files store hashes and fixture-relative identifiers, not absolute
  repository paths, environment values, prompts, headers, or secrets.

Verification adds structural privacy gates:

- AST inspection rejects `.content` and `._context_content` reads in
  `retrieval_core/tracing.py`;
- recursive sentinel tests reject source text, prompts, environment values,
  headers, secrets, and absolute paths in success and early-return trace trees;
- both feedback-writing functions are monkeypatched to forbidden sentinels for
  all trace success/error/early-return paths;
- the baseline verifier rejects absolute temporary paths, unhashed source
  content, and unexpected environment-derived fields recursively.

## Risks And Mitigations

### Hidden File-Scope Dependencies Break During Moves

Risk: a moved function relies on a constant or helper whose ownership was
implicit in `retrieval.py`.

Mitigation: move one responsibility slice at a time, keep function bodies
unchanged, use module-qualified imports, and run focused plus fingerprint tests
before deleting aliases.

### Import Cycles Replace File Coupling

Risk: expansion imports ranking for file roles, tracing imports the façade for
internal types, or stage modules import the orchestrator.

Mitigation: shared types, ordering, evidence merge, relation policy, and file-role
policy have narrow explicit owners; the exact adjacency allowlist rejects
forbidden edges and cycles.

### Private Compatibility Aliases Become Permanent

Risk: leaving all old `_name` imports in `retrieval.py` makes tests pass while
the physical coupling remains.

Mitigation: aliases are tracked per migration slice; the final façade-symbol
test and direct-owner test imports make their removal an acceptance gate. A
production call, direct test, and monkeypatch target move atomically because a
plain value alias cannot forward a monkeypatch.

### Candidate Ordering Changes Accidentally

Risk: replacing dict/list flow or moving a sort changes first-seen order and
therefore final ranking or trace previews.

Mitigation: preserve concrete collection shapes, lock pre-refactor fingerprints,
and compare stage previews and final selections after normalizing timing only.

### Trace Timing Boundaries Drift

Risk: a stage wrapper includes observation conversion or finalization moves
before bundle construction.

Mitigation: start/stop remains explicit in `query_repository()`, observation
stays after stop, and collector clock tests assert call order.

### Ranking Extraction Turns Into A Rewrite

Risk: the largest move invites cleanup, new policy objects, or score-ledger
changes.

Mitigation: ranking moves as one unit with no numeric or structural policy
changes. Follow-up ranking redesign requires a separate design.

### Tests Are Weakened To Fit New Modules

Risk: broad end-to-end assertions replace exact private behavior tests during
import migration.

Mitigation: move existing assertions to new owners, add baseline fingerprints,
and reject deletions or relaxed thresholds not directly required by ownership.

## Acceptance Criteria

P3.2 is complete only when all of the following are true:

1. `retrieval.py` defines the normative façade, its three explicit compatibility
   exports, and the canonical fifteen-stage orchestration—no stage bodies.
2. Every stage behavior and shared primitive has exactly one documented owner.
3. The exact import adjacency table is acyclic and passes the strict AST gate.
4. No temporary private alias, stale test reference, or stale profiler target to
   a migrated façade name remains.
5. Every supported retrieval import/signature/value and both public dataclass
   identities remain exact.
6. Exact JSON, Markdown, and normalized trace-envelope bytes match for all 13
   cases; ContextPack canonical bytes/options match for all five P2 cases.
7. Internal bundle diagnostics match all 13 cases, and complete stage ledgers
   match the four representative cases.
8. RetrievalTrace remains schema version 1 with the same fifteen stages, counts,
   order, provenance, bounds, privacy, and key order.
9. The event ledger proves live operation -> stop -> observation for every stage,
   final output assembly after final-stage stop, and total finish after bundle
   construction.
10. Missing-index, store-error, no-candidate, and propagated-error branches meet
    their exact bundle, call, stage-prefix, exception, CLI, and MCP contracts.
11. Separate ordinary and traced runs for all 13 cases match their exact planner,
    embedding/fallback, vector, store, direct-probe, index-existence, and source-
    file operation ledgers; ordinary queries construct no trace-only values.
12. Structural and sentinel privacy gates pass on success and every early/error
    path; feedback writers are never called by tracing.
13. Existing focused assertions remain exact under new owners; no test is deleted
    or weakened to fit the decomposition.
14. The full suite passes, and baseline skip/xfail node IDs and reasons match the
    Slice 1 manifest exactly.
15. P3.1 TraceCoverage remains 1.0 on every committed non-empty case.
16. `p2_context_pack` remains 5/5 and raw `ci` remains 8/8.
17. Phase 1 remains recorded independently at 6/7 unless separately closed.
18. The protected-source diff gate is clean; catalog/snapshot OIDs and content
    hashes still match the frozen inputs; and the Slice 1 baseline commit/blob
    OIDs remain unchanged.
19. No ranking change, P4 exploration, graph feature, trace persistence, or new
    configuration/API surface is included.
20. Documentation records exact commits and verification evidence before the
    roadmap marks P3.2 implementation complete.

## Implementation Verification Record

All acceptance criteria passed on 2026-07-16 at Task 9 commit
`b21f0a350b3f132f8befebf87f5e211092fe7ad1`. The full suite passed
`1,938` tests with the exact baseline set of `9` skips and no xfails; the
six-file focused gate passed `76` tests; all 13 cases and four full-stage
ledgers matched; TraceCoverage remained `1.0`; and P2/raw-CI passed `5/5` and
`8/8`. Frozen-input identity, protected-source, exact ownership, and acyclic
import-adjacency gates were clean. Detailed OIDs, content hashes, and report
paths are recorded in `docs/retrieval-quality.md`.

The reviewed implementation and closure commits are:

| task | commit |
| --- | --- |
| Task 1 | `680b252b5c863fce9b236771b1a54c28e3f9839e` |
| Task 2 | `fafea37b89190bdeed0a7baea972d01889570b46` |
| Task 3 | `70d41a745b0c1c5f65f8516d8b6f2c4ad1f87db9` |
| Task 4 | `c1fad40c631eefec84a2057ff18a800c2c3cc6cf` |
| Task 5 | `2dba63e52d20a2afa3dc347df8b21217448fd7a1` |
| Task 6 | `17ca0a527864630c5420de1ed7237fa5c0f12ee6` |
| Task 7 | `fd2340ac91e21099b44d82fbd7ee62b797bc4d09` |
| Task 8 | `d0a65a5af560e8eeff46000be0cf88490e6c4bca` |
| Task 9 | `b21f0a350b3f132f8befebf87f5e211092fe7ad1` |

The Task 10 documentation commit is reported in the implementation handoff and
is intentionally not embedded in that same commit. Phase 1 remains pending at
its independent `6/7` gate, and Phase 4 work has not begun.

## Agent Review Rubric

The design review must independently check:

- whether every major current `retrieval.py` responsibility has one owner;
- whether the proposed dependency graph can be implemented without a cycle;
- whether keeping orchestration in `retrieval.py` preserves P3.1 timing and
  public bundle semantics better than moving it;
- whether shared modules are minimal rather than utility dumping grounds;
- whether ranking remains sufficiently isolated without being redesigned;
- whether characterization fingerprints can detect coupled drift;
- whether test migration removes, rather than hides, private-module coupling;
- whether any scope accidentally begins P4 or changes retrieval quality.

Any unresolved ownership, compatibility, or verification blocker keeps the
status at draft.

## Agent Review Record

Three independent read-only reviewers examined the completed first draft from
architecture, contract-preservation, and migration-feasibility perspectives.
The first round agreed that the explicit orchestrator and stage-owned split were
sound, but found two common blockers: the façade omitted supported
`normalize_score`/limit exports, and shared ordering/relation values had no
acyclic owner. They also identified baseline, timing, monkeypatch, logger, and
dead-helper ambiguities.

The design was revised to add the normative façade table, narrow shared owners,
exact adjacency allowlist, atomic test/patch migration, thirteen-case byte and
diagnostic fingerprints, four complete stage ledgers, executable timing and
early-return gates, protected-source boundaries, and privacy sentinels.

All three reviewers then performed a targeted second pass:

- architecture: PASS, with no missing dependency edge or cycle;
- contract preservation: PASS after adding hashed `EvidenceAnchor.content` and
  `_context_content` plus integer trace-duration normalization;
- migration feasibility: PASS, with all seven slices capable of remaining green.

No blocker or major finding remains. This review approved the design boundary.
The separate implementation plan passed its own three-agent, two-round review,
and the implementation and acceptance evidence above now verify that boundary.

## Stop Point

P3.2 ends after stage implementations are moved behind the documented internal
modules, private test imports are migrated, all compatibility/fingerprint gates
pass, and documentation is updated with exact evidence.

It does not change ranking behavior, close Phase 1, split ranking policy into a
new abstraction hierarchy, execute follow-up queries, add multi-round
exploration, add graph features, persist traces, or implement the next roadmap
phase.
