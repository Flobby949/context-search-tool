# P7 Retrieval Quality Attribution And Evidence-Set Selection Implementation Plan

Date: 2026-07-25
Status: Detailed review candidate; implementation is not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Design: `docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md`
Behavior baseline: `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`
Current source HEAD at plan time: `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`
Required reviewed-document entry commit: pending
Authorization: planning and review only; implementation is not authorized

> **For agentic workers:** Execute one task at a time and keep every task
> green. Begin each behavior change with a focused failing test, preserve the
> exact frozen baseline and gold identities, stage only the paths listed by the
> task, and create the focused commit named by that task. Stop on a design
> mismatch, behavior-neutrality failure, gold-feasibility failure, unreviewed
> schema change, extra scan/connection, P4 semantic drift, privacy leak,
> protected-profile regression, or performance-budget failure. Never refresh a
> baseline, witness, expected output, or threshold merely to make a candidate
> pass.

**Goal:** Implement the reviewed P7 design as a measured retrieval-quality
phase: first freeze truthful stage attribution and feasible target-bearing
gold, then stop at a mechanism-specific baseline opportunity checkpoint. Only
if all four structural mechanisms have independent cross-repository support and
the user separately authorizes continuation may the plan activate exact
original-query evidence, unique-file projection, a wider default-context
boundary, and protected ContextPack reservation. Finally, use measured
remaining attrition to select exactly one justified next phase.

**Architecture:** Existing recall and ranking continue to operate on chunks.
Original-query exact literals are resolved inside the existing path/symbol and
signal read scopes. A canonical exact chunk may be injected before direct
merge. Existing ranking and context expansion run before a new pure
`file_projection` stage groups visible expanded candidates by canonical path,
retains at most two bounded display segments for normal results, and preserves
the ordering chunk separately from display origins. `final_selection` alone
applies independent result and anchor capacities with protected-first
reservation. ContextPack v2 receives one real QueryBundle, reserves private
protected paths, and allocates excerpts independently per retained segment.
This complete product bundle is conditional; no individual subset is inferred
from a different mechanism's oracle.
An evaluation-only ContextVar observer emits source-free leaves for the common
retrieval prefix and separate query/context/explore DAG without changing public
output. The complete Task-6 evaluator closure—gold/variant resolver,
finalizers, metrics, schemas, comparison, reports, oracles, and decision
algorithm—is then frozen before activation. Later candidate code is only the
product/leaf-execution target and cannot judge its own output.

**Tech Stack:** Python 3.11-3.14, frozen dataclasses, SQLite rollback-journal
read sessions, existing hash-v1 deterministic embeddings, existing P5 graph
schema v5, ContextVar-scoped observation, Typer/FastMCP adapters, ContextPack
v2, RetrievalTrace v2, ExplorationTrace v2, pytest, deterministic fixture
repositories, pinned public Git repositories, canonical JSON with
`allow_nan=False`, and the existing P6 paired latency/RSS measurement
conventions.

---

## Source Of Truth And Execution Constraints

The reviewed design is normative:

- `docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md`

If this plan and the design disagree, stop, amend both documents, and repeat
independent review. Do not silently choose the easier implementation.

The plan-time source baseline is the clean P6 basic-implementation merge
`74aae0abe3dff685282fbcc785f7a9b3532cbbe6`. On 2026-07-25 the plan author
reproduced the following local candidate baseline with optional external
acceptance variables absent:

```text
runtime: Python 3.13.12
SQLite: 3.51.2
command: python -m pytest -q -p no:cacheprovider
result: 2896 passed, 9 skipped, 0 xfailed, 16 warnings
duration: 54.58 seconds
tracked source/test diff after run: empty
```

This is plan-time evidence only. Task 0 must reproduce the baseline from the
reviewed documentation entry commit and record exact skip node IDs. A count
match without the same skip identities, runtime, dependency freeze, source
tree, and optional-environment state is not a valid entry.

Execution constraints:

1. This document authorizes no production edit, branch creation, staging,
   commit, public-repository preparation, private-overlay run, external
   comparator request, or roadmap update. Begin only after a new explicit user
   instruction to implement P7.
2. After this plan passes review, commit only the reviewed design and plan in a
   documentation-only commit whose parent is exactly `74aae0a...`. Record that
   commit with exact subject `docs: add reviewed p7 design and plan` as
   `P7_REVIEW_COMMIT` and initial `P7_ENTRY_COMMIT`. If another source, test,
   fixture, dependency, or roadmap change intervenes, stop and amend the
   baseline rather than rebasing the evidence implicitly.
3. P6's basic implementation is the dependency baseline. P7 neither claims nor
   completes P6's deferred large/scale/stress/churn, cross-platform, ANN, or
   service/watch acceptance.
4. Task 0 reproduces P0-P6 behavior. Tasks 1-6 are the complete observation and
   baseline-freeze slice. No production ranking, membership, display-window,
   trace-version, context-candidate-limit, pack-reservation, or P4 behavior may
   change before Task 6 commits the frozen baseline.
5. The behavior baseline remains `74aae0a...`. Task 6 first creates
   `P7_AUDIT_INSTRUMENTATION_COMMIT`, then runs the baseline and creates a
   separate artifact-only `P7_BASELINE_FREEZE_COMMIT` that names it. Reports
   record all identities; they must never claim that audit code executed in the
   behavior-baseline commit or try to embed a commit's own ID in itself.
6. Gold authoring uses pinned source and task meaning, not baseline, candidate,
   oracle, or comparator output. Public decision gold requires distinct author
   and read-only reviewer identities before `P7_GOLD_FREEZE_COMMIT`. Required
   alternatives are legal only through source-authored
   `evidence_cover_variants`; evaluation cannot mix choices across variants.
7. Task 5 freezes the reference feasibility/oracle helper and all gold input
   bytes. Its focused commit is `P7_GOLD_FREEZE_COMMIT`. Because a Git commit
   cannot contain its own object ID, Task 6 writes the source-free provenance
   seal that names that already-created commit; the runtime resolver joins
   `GoldFreezeInputs` and `GoldProvenanceSeal` into the only runnable
   `ResolvedGoldProvenance`. After the gold
   freeze, later tasks may call but may not edit the helper, fixture labels,
   witnesses, thresholds, profile membership, query text, source pins, or
   effective options. A correction requires a new independently reviewed gold
   freeze and paired reruns on the old baseline and current candidate.
8. Existing quality schema-v1 fixtures remain readable. Only schema-v2 cases
   with target-bearing evidence units participate in P7 attribution or
   classification.
9. The quality observer is evaluation-only, source-free, ContextVar-scoped,
   non-nestable, and reset in `finally`. Normal query, trace, context, and
   explore calls allocate no audit ledger and retain no observer state. Every
   accepted baseline/candidate derived field is recomputed by the Task-6 frozen
   evaluator closure. Its product-worker shim, supported-façade call
   orchestration, observer capture, and leaf serializer are frozen too;
   candidate-resident adapters, gold, finalizers, metrics, schemas, normalizers,
   pass booleans, and decision code are never trusted.
10. Audit-enabled and audit-disabled public projections must be byte-identical
    after normalizing only documented timing fields. Shadow policy data never
    replaces actual baseline output and never votes in regressions or the phase
    decision.
11. Exact extraction resolves at most sixteen distinct eligible literals in
    original occurrence order. Only literal original-query evidence can create
    protection. Planner variants, planner hints, exploration probes, relation
    discoveries, split identifier components, content-only occurrences, and
    ambiguous paths cannot.
12. Enabled path/symbol and signal lanes add no connection or scan. The
    `lexical_top_k == 0` eligible-exact edge adds exactly one shared
    metadata-only path/symbol connection/pass for the request; the no-exact
    edge adds none. No per-literal or second signal pass is legal.
13. Exact resolution and injection must occur before direct merge. Canonical
    fallback selection compares only original-query lane/source precedence,
    lane return rank, range, and chunk ID. It never compares cross-lane scores
    or admits planner/anchor/relation/probe candidates.
14. Chunk relevance scoring and cohort reranking stay numerically unchanged.
    Non-ordering chunks never sum, average, or otherwise improve file order.
    General score retuning is outside P7.
15. Source materialization stays in `context_expansion`. Grouped I/O performs at
    most one `stat` and one `read_text` per expanded canonical path, restores
    original ranked positions, and preserves each unreadable origin's own
    indexed fallback. Its explicit acquire/release seam must report
    `peak_additional_transient_source_read_buffers <= 1`; already-retained
    bounded downstream windows are counted separately as
    `retained_output_bytes` and remain subject to candidate/window caps and RSS.
16. `file_projection` occurs after context expansion, emits the complete visible
    unique normal-file population plus every anchor passthrough, and owns no
    surface capacity. Only `final_selection` applies result and anchor limits
    and anchor deduplication.
17. RetrievalTrace moves atomically from v1 to v2 in the same task that
    activates `file_projection`. There is no committed production state in
    which the new projection is described as v1 or v2 is emitted without the
    new stage.
18. QueryBundle fields and the supported `query_repository`,
    `trace_repository`, and `build_context_pack` signatures remain exact.
    Private constructor-compatible fields use defaults, `repr=False`, and
    `compare=False`; serializers, feedback, and formatters ignore them except
    for the reviewed RetrievalTrace-v2 fields.
19. ContextPack v2 never consumes a result-backed path absent from its source
    QueryBundle. Omitted-budget `context` creates one wider request-local
    QueryBundle before one builder call; explicit `final_top_k` remains
    authoritative.
20. P4 initial evidence may retain original-query protection. Every follow-up
    call runs under the non-nestable protection-disable guard, adds no
    metadata-only exact scan, and defensively clears a private marker.
    ExplorationTrace v2, call ceilings, fusion capacities, frozen goals,
    probe-local ranks, score-domain isolation, and legacy origin seed semantics
    remain unchanged.
21. File/span oracles are evaluation-only and force the reviewed feasible-cover
    witness's one declared coherent variant. They do not mutate production
    candidates, public traces, fixture alternatives, or ordinary terminal
    scoring.
22. Fixed-profile classification uses only enforced-candidate
    `actual_terminal_reason` values. Deterministic mechanics, baseline shadow
    reasons, comparator output, and undersized private overlays do not vote.
23. Public benchmark artifacts may contain public repository-relative paths but
    no source excerpts. Private query text, paths, identifiers, origin, planner
    text, raw report, fixture location, username, and absolute path remain
    uncommitted. Private summaries are built from an allowlist, never by
    redacting a full report.
24. A private overlay is always diagnostic and non-voting. Task 6 commits
    `private_prefreeze_state=paired_frozen | unavailable` plus the design's
    domain-separated salted continuity commitment; the random salt and exact
    local seals remain ignored. Task 12 must verify that commitment before the
    matching candidate side. A missing/drifted paired record or salt becomes a
    closed `failed` status, never unavailable or late. A later-selected overlay
    uses a distinct attempt-bound `late_informational` seal. Raw private input
    and secret scanner-needle hashes stay local and never enter tracked decision
    provenance.
25. P7 adds no parser, graph schema, embedding provider, learned/remote
    reranker, controller, automatic exploration, daemon, watcher, dashboard,
    memory, or product surface.
26. Every task's `Files` list is its complete tracked commit boundary. New
    tracked paths require a reviewed plan amendment. Generated repositories,
    temporary worktrees, RED/GREEN logs, raw private evidence, and comparator
    responses live only under the task's named ignored `.quality/p7-*` roots.
27. Each production task starts with a focused failing test, ends with its
    focused gate, the protected contract gate, `git diff --cached --check`, and
    exact staged-name review. Preserve unrelated user work and never use
    `git add -A`.
28. Task 12 is the only task allowed to write final candidate/comparison/
    decision artifacts or update README, roadmap, benchmark documentation, or
    plan completion status. The fixed-payload-reviewed design bytes and status
    remain immutable. A failed gate cannot be converted into completion prose.
29. A structured-signal exact contribution remains provisional until graph
    health is final. Direct/anchor trace and audit membership/provenance commit
    atomically from the selected `ready` or `graph_fault` batch projection;
    abandoned signal-exact contribution IDs, ranks, winners, and protection may
    not reach either accepted surface.
30. The public paraphrase/robustness cohort is visible, not a hidden holdout.
    Frozen metamorphic companions and a production-source anti-special-casing
    sentinel are mandatory; neither may be described as unseen evidence.
31. Task 6 is a mandatory stop. Its frozen `BaselineOpportunityRecord` computes
    four independent support bits—exact acquisition, file projection, omitted-
    budget context boundary, and pack reservation—from isolated
    counterfactuals. Tasks 7-12 require all four bits, the closed
    `full_bundle_supported` recommendation, and a later explicit user
    authorization. Any other recommendation stops this plan and requires a new
    focused design; no subset of the prewritten bundle runs opportunistically.

## Definition Of Done

The unconditional P7 observation slice is complete only when the baseline
freeze, exhaustive target manifest, and tracked `BaselineOpportunityRecord v1`
are reproducible. If that record is anything except
`full_bundle_supported`, this plan ends at Task 6 and success means handing off
the required focused redesign rather than claiming product-selection
completion.

If and only if the user later authorizes the conditional product bundle, P7
implementation is complete only when:

- the clean reviewed-document entry and the exact `74aae0a...` behavior
  baseline are reproducible with recorded runtime, dependency, source-tree,
  full-suite, skip, protected-profile, and public-projection identities;
- schema-v2 cases enforce exact canonical target ranges, literals, coherent
  evidence-cover variants, anti-duplication rules, source pins, author/reviewer
  separation, and frozen feasible-cover witnesses;
- the audit observer is behavior-neutral, lifecycle-safe, source-free, and
  complete for the common prefix plus the applicable query/context/explore
  branch;
- the Task-6 evaluator closure owns every accepted gold join, coherent-variant
  choice, final reason, metric, normalization, comparison, schema check, report,
  and decision for both baseline and candidate;
- every required unit receives exactly one actual terminal reason, every
  behavior-baseline unit receives one separate non-voting shadow reason, and
  no applicable field is silently null;
- each of the four opportunity bits is supported by its own single-mechanism
  counterfactual across both independent external sources, the combined shadow
  has no required-unit regression, and the tracked recommendation is
  `full_bundle_supported`;
- exact literal extraction, resolution priority, clause-local narrowing,
  declaration policy, canonical injection, protection overflow, and
  enabled/disabled-lane work counts match the design;
- same-file traversal-only candidates remain usable as relation seeds but
  cannot become visible without independent evidence;
- context expansion groups workspace reads by path, keeps at most one additional
  transient source-read buffer at the measured seam, separately bounds retained
  output bytes, preserves original order/fallback semantics, and carries
  winner-consistent origin provenance;
- file projection emits all visible unique normal paths without capacity
  truncation, uses the ordering chunk alone for file order, retains at most two
  bounded normal display segments, preserves one anchor window, and handles a
  transitive bridge atomically;
- final selection independently reserves protected result/anchor paths,
  deduplicates anchors only there, fills eligible capacities, and emits one raw
  result per canonical path;
- RetrievalTrace v2 has sixteen canonical stages, closed projection decisions,
  empty composite previews, contiguous interleaved ranks, winner-first
  canonical provenance, exact public omission counts, and a separate private
  legacy P4 origin tuple;
- legacy direct ContextPack construction synthesizes exactly one source view,
  while P7-produced candidates use segment-local matching/excerpts without
  concatenating disjoint content;
- ContextPack private protected reservation participates in the existing
  blocked-match, excerpt, byte-fitting, compaction, relinking, omission, and
  retry pipeline without changing unprotected relative order or public schema;
- omitted-budget context uses the reviewed wider QueryBundle formula, explicit
  budgets stay exact, and every result item has a valid zero-based retrieval
  rank in that same bundle;
- P4 follow-ups cannot create or transport protection and all protected P4
  projections, counts, origins, goals, limits, and score-domain rules pass;
- all eight deterministic mechanics shapes pass, the fixed public profile meets
  minimum cohort size and frozen gates, any private diagnostics are source-safe
  and non-voting, and comparator availability remains non-gating;
- the visible paraphrase/robustness and frozen metamorphic cohorts pass, and the
  production anti-special-casing sentinel finds no frozen case/query/path/hash
  table;
- query/context latency, the explore retrieval-call ceiling, RSS, source-read,
  planner/embedding request, audit-lifecycle, deterministic ordering, and P0-P6
  protected gates pass;
- `P7DecisionRecord v1` validates, selects exactly one legal classification or
  `mixed_inconclusive`, maps it to exactly one legal next action, records
  rejected actions and privacy evidence, and does not overclaim fast-context
  parity;
- README, roadmap, plan, and benchmark documentation are updated only after all
  required evidence exists; the fixed reviewed design remains byte-identical.

## Dependency And Activation Order

The implementation has one hard activation barrier:

```text
Tasks 0-6: observe and freeze
  Task 1 contracts
    -> Task 2 pure exact/file policy
    -> Task 3 observation-only acquisition facts
    -> Task 4 target-bearing case schema
    -> Task 5 frozen feasibility/oracle/decision reference and gold inputs
    -> Task 6 audit runner + provenance seal + behavior-neutral baseline freeze
      -> tracked BaselineOpportunityRecord
      -> MANDATORY STOP AND USER REVIEW

Only full_bundle_supported + a later explicit user instruction continues:

Tasks 7-9: prepare compatible consumers and provenance
  Task 7 ContextPack private segment/reservation support
    -> Task 8 exact injection transport + P4 guard (not activated)
    -> Task 9 grouped materialization + RetrievalTrace-v2 readiness

Task 10: atomic common retrieval/pack-metadata activation
  exact injection + traversal visibility + file projection
  + protected final selection + private pack transport + RetrievalTrace v2

Task 11: omitted-budget context surface boundary and integration verification

Task 12: candidate acceptance, decision, documentation

focused_redesign | acquisition_redirect | mixed_insufficient:
  stop; write the recommendation-specific design; do not execute Tasks 7-12
```

Tasks 7-9 may add private fields and dormant/internal helpers, but their public
normalized outputs must remain baseline-identical. Task 10 is the one atomic
common retrieval, trace, and P7-produced ContextPack metadata/reservation
activation. Task 11 is the only intentional omitted-budget
context-candidate-limit activation.

## File Responsibility Map

| area | production/artifact owner | focused tests |
| --- | --- | --- |
| occurrence-preserving literal extraction and protectable filename policy | `src/context_search_tool/identifier_intent.py`, new `src/context_search_tool/retrieval_core/exact_intent.py`, `src/context_search_tool/scanner.py` | new `tests/test_p7_exact_intent.py`, existing `tests/test_identifier_intent.py`, `tests/test_tokenizer_scanner.py` |
| exact path/symbol/signal metadata pass and measured work | `src/context_search_tool/sqlite_store.py`, `src/context_search_tool/retrieval_core/candidates.py` | new `tests/test_p7_exact_acquisition.py`, existing `tests/test_sqlite_store_query_work.py`, `tests/test_retrieval_pipeline.py` |
| private exact/traversal/ranked/expanded/file value types | `src/context_search_tool/models.py`, `src/context_search_tool/retrieval_core/types.py` | new P7 exact, file-evidence, context, and trace tests |
| traversal-only marking and independent-display evidence | `src/context_search_tool/retrieval_core/expansion.py`, `src/context_search_tool/retrieval_core/candidates.py` | new `tests/test_p7_file_evidence.py`, existing `tests/test_resolved_graph_expansion.py` |
| pure file projection, segment choice, protected partition pools | new `src/context_search_tool/retrieval_core/file_evidence.py` | new `tests/test_p7_file_evidence.py` |
| path-grouped materialization, winner, source fallback | `src/context_search_tool/retrieval_core/context_expansion.py` | new `tests/test_p7_context_expansion.py`, existing retrieval pipeline tests |
| exact identity transport without numeric retuning | `src/context_search_tool/retrieval_core/ranking.py` | new `tests/test_p7_pipeline.py`, existing rerank and protected-direct tests |
| projection/final selection and raw result materialization | `src/context_search_tool/retrieval_core/selection.py` | new `tests/test_p7_pipeline.py`, `tests/test_retrieval_pipeline.py` |
| retrieval orchestration, graph-fault contribution batch, and no-signature audit hooks | `src/context_search_tool/retrieval.py` | new `tests/test_p7_audit.py`, `tests/test_p7_pipeline.py`, existing boundary/characterization tests |
| evaluation-only runtime observer, deferred leaf batch, and frozen finalizers | new `src/context_search_tool/retrieval_core/audit.py`, new `src/context_search_tool/quality/audit.py` | new `tests/test_p7_audit.py` |
| RetrievalTrace v2 model, collector, serialization, formatter | `src/context_search_tool/retrieval_trace/models.py`, `collector.py`, `serialization.py`, `src/context_search_tool/retrieval_core/tracing.py`, `src/context_search_tool/retrieval_trace/__init__.py`, `src/context_search_tool/formatters.py` | new `tests/test_p7_trace_v2.py`, existing trace/formatter tests |
| private ContextPack segments/protection and selection | `src/context_search_tool/context_pack/models.py`, `roles.py`, `needs.py`, `builder.py`, `excerpts.py` | new `tests/test_p7_context_pack.py`, existing ContextPack/excerpt/need tests |
| shared context request-local candidate limit | new `src/context_search_tool/context_pack/surface.py`, `src/context_search_tool/cli.py`, `src/context_search_tool/mcp_tools.py` | new `tests/test_p7_surfaces.py`, existing CLI/MCP tests |
| P4 protection guard, origin compatibility, marker handling | `src/context_search_tool/retrieval_core/exact_intent.py`, `src/context_search_tool/exploration/runner.py`, `probes.py`, `fusion.py` | new `tests/test_p7_exploration.py`, existing P4 tests |
| schema-v2 evidence units, coherent variants, and source/two-state gold provenance | `src/context_search_tool/quality/cases.py` | new `tests/test_p7_quality_cases.py`, existing quality case/catalog tests |
| frozen feasibility witness, file/span oracle, closed decision | new `src/context_search_tool/quality/oracle.py`, new `src/context_search_tool/quality/p7_decision.py` | new `tests/test_p7_oracle.py`, `tests/test_p7_decision.py` |
| Task-6-frozen evaluator, worker shim, call orchestration, leaf serialization, metrics, reports, comparison, CLI; no later mutation | `src/context_search_tool/quality/runner.py`, `metrics.py`, `aggregate.py`, `compare.py`, `reports.py`, `__main__.py` | new `tests/test_p7_quality_runner.py`, existing quality tests |
| deterministic mechanics, fixed public profile, paraphrase/metamorphic transforms, source manifest | `tests/fixtures/p7-retrieval-quality/**`, `tests/fixtures/p7_retrieval_quality/**` | all new P7 quality tests |
| context latency/RSS/source-read measurement | `scripts/p6_benchmark.py` | `tests/test_p6_benchmark.py`, `tests/test_p6_measurement_worker.py`, new P7 performance assertions |
| schemas, baseline, candidate, comparison, decision | `docs/benchmarks/p7/**` | artifact validators in new P7 quality tests |
| accepted user documentation and roadmap | `README.md`, `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`, reviewed design and this plan | Task-12 link/status/claim checks |

The preferred import direction is:

```text
identifier_intent/scanner constants
  -> retrieval_core.exact_intent
  -> retrieval_core.candidates/ranking

retrieval_core.types
  -> retrieval_core.context_expansion
  -> retrieval_core.file_evidence
  -> retrieval_core.selection/tracing
  -> retrieval orchestration

retrieval_core.audit
  <- retrieval, ContextPack builder, exploration runner
  -> product source-free leaf protocol
  -> Task-6 frozen quality.audit finalization

models private segment fields
  -> context_pack.roles/models/excerpts/builder
  -> context_pack.surface
  -> CLI/MCP
```

`quality` may depend on production retrieval and ContextPack. Production
retrieval, ContextPack, and exploration may import only the source-free no-op
observer seam from `retrieval_core.audit`; they must not import quality cases,
oracles, fixtures, reports, or decision code. `scripts/p6_benchmark.py` may
measure public/library entry points; production code must not import scripts or
benchmark artifacts.

## Public And Persistent Surface

| surface | P7 contract and activation task |
| --- | --- |
| `query_repository()` / `QueryBundle` | signature and fields unchanged; Task 10 intentionally changes result uniqueness/order/membership and private segment/protection metadata |
| `trace_repository()` | signature unchanged; Task 10 emits RetrievalTrace v2 with `file_projection` and ordering/display provenance |
| CLI/MCP `query` | response shape unchanged; Task 10 emits unique paths and first display windows |
| CLI/MCP `trace` | existing error envelope unchanged; success trace moves from schema v1 to v2 in Task 10 |
| CLI `context` | has no `final_top_k` option and is therefore the omitted-budget branch; Task 11 uses the wider request-local QueryBundle |
| MCP `context_search_context` | null `final_top_k` uses the wider formula; an explicit positive value remains exact; response stays ContextPack v2 |
| `build_context_pack(bundle, options)` | signature unchanged; Task 7 adds dormant support and Task 10 begins supplying private segment/protection metadata on P7-produced bundles |
| `ContextPackOptions` / ContextPack v2 | public fields/schema unchanged; Task 11 resolves options against the same request-local config used for retrieval |
| `explore_repository()` / ExplorationTrace v2 | public signatures/schema, limits, fusion, goals, counts, and stop rules unchanged; Tasks 8-11 preserve initial markers and disable follow-up protection |
| retrieval feedback | no audit/protection/segment data persisted; existing request/output fields unchanged |
| quality fixture schema | v1 remains readable; v2 is new and required for P7 attribution |
| quality audit / decision | new benchmark-only schemas under `docs/benchmarks/p7/schemas/`; never returned from CLI/MCP retrieval |
| graph/index schemas | manifest v2, operational v1, graph v5, and vector descriptor v2 remain unchanged |

## Tracked And Ignored Artifact Boundaries

Committed source-independent P7 evidence may include:

```text
docs/benchmarks/p7/README.md
docs/benchmarks/p7/schemas/*.json
docs/benchmarks/p7/baseline/public-audit.json
docs/benchmarks/p7/baseline/public-projection-identity.json
docs/benchmarks/p7/final/public-audit.json
docs/benchmarks/p7/final/public-comparison.json
docs/benchmarks/p7/final/performance-summary.json
docs/benchmarks/p7/final/robustness-summary.json
docs/benchmarks/p7/final/p7-decision.json
docs/benchmarks/p7/final/p7-decision.md
tests/fixtures/p7_retrieval_quality/*.json
tests/fixtures/p7-retrieval-quality/**
```

Ignored/local-only roots:

```text
.quality/p7-artifacts/
.quality/p7-repos/
.quality/p7-worktrees/
.quality/p7-private/
.quality/p7-comparator/
.quality/p7-performance/
.quality/p7-attempts/
```

Raw public source checkouts, indexes, source excerpts, complete trace dumps,
timing samples, and comparator responses remain ignored. Committed public audit
artifacts contain IDs, booleans, counts, reasons, hashes, safe public relative
paths where the schema allows them, and normalized summaries only. Raw or
private-input-bearing artifacts never leave `.quality/p7-private/`; the
sanitized `private-summary-v1` remains there too. Only that summary's validated
hash, closed mode/eligibility/pass status, and derived private classification
can enter the tracked decision; its private aggregate metrics cannot.

## Task And Commit Order

| task | purpose | focused commit |
| ---: | --- | --- |
| 0 | Reproduce the clean reviewed entry and protected P0-P6 baseline | no commit |
| 1 | Freeze public compatibility projections and P7 artifact schemas | `test: lock p7 contracts and artifact schemas` |
| 2 | Add pure exact-intent and file-evidence policy primitives | `feat: add p7 evidence policy core` |
| 3 | Collect exact metadata and traversal facts without changing output | `feat: observe p7 exact acquisition facts` |
| 4 | Add target-bearing quality schema v2 and gold validation | `feat: add p7 evidence unit contracts` |
| 5 | Add and freeze feasibility, oracle, profile, and decision references | `test: freeze p7 gold and decision references` |
| 6 | Add the behavior-neutral audit DAG, then freeze the baseline | `feat: add p7 retrieval quality audit`; `test: freeze p7 behavior baseline` |
| 7 | Add dormant private ContextPack reservation and segment support | `feat: add p7 context evidence transport` |
| 8 | Prepare exact injection transport and P4 protection isolation | `feat: prepare p7 exact evidence activation` |
| 9 | Group materialization and make RetrievalTrace v2 consumers ready | `feat: add p7 materialization provenance` |
| 10 | Atomically activate exact evidence, file projection, selection, private pack transport, and trace v2 | `feat: activate p7 file evidence selection` |
| 11 | Activate the omitted-budget context boundary and verify surface/P4 integration | `feat: activate p7 context evidence boundary` |
| 12 | Run acceptance, publish the decision record, and update documentation | `docs: record p7 acceptance and decision` |

Task 5's focused commit is `P7_GOLD_FREEZE_COMMIT`. Task 6's first focused
commit is `P7_AUDIT_INSTRUMENTATION_COMMIT`; it seals the already-known gold
commit ID. Its second, artifact-only commit is `P7_BASELINE_FREEZE_COMMIT`;
that commit publishes the behavior-neutral baseline and is the behavior-change
gate.
Tasks 7-9 remain public-projection-neutral despite adding private capabilities.
Task 10 is one atomic common retrieval/trace/private-pack behavior migration.
Task 11 is one atomic omitted-budget context-default migration. Task 12
contains no new retrieval policy.

## Shared Verification Commands

Every `bash` block in this plan is normative Bash, not ambient zsh/sh. Execute
each task in a fresh Bash process with this preamble before any displayed
command; nested `(...)` blocks inherit the options:

```bash
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
```

An optional probe must be inside an explicit `if` whose unavailable branch
writes the named schema-valid unavailable artifact. Do not use an unguarded
failing command followed by later commands, and do not append `|| true` except
for a displayed read-only emptiness probe whose result is asserted immediately.

Because tasks use fresh shells, no later task may rely on a prior `export`.
Reconstruct roots/runtime each time, and resolve every already-completed named
commit as the unique exact subject on the coordination branch's first-parent
history:

```bash
export P7_REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$P7_REPO_ROOT"
export P7_RUNTIME="$P7_REPO_ROOT/.quality/p5-runtime/bin/python"
test -x "$P7_RUNTIME"

p7_commit_by_subject() {
  local expected_subject="$1"
  local matches
  matches="$(
    git log --first-parent --format='%H%x09%s' HEAD |
      awk -F '\t' -v wanted="$expected_subject" '$2 == wanted { print $1 }'
  )"
  test -n "$matches"
  test "$(printf '%s\n' "$matches" | wc -l | tr -d ' ')" -eq 1
  git merge-base --is-ancestor "$matches" HEAD
  printf '%s\n' "$matches"
}

export P7_REVIEW_COMMIT="$(
  p7_commit_by_subject 'docs: add reviewed p7 design and plan'
)"
# Resolve only commits whose owning task is already complete:
# P7_GOLD_FREEZE_COMMIT:
#   test: freeze p7 gold and decision references
# P7_AUDIT_INSTRUMENTATION_COMMIT:
#   feat: add p7 retrieval quality audit
# P7_BASELINE_FREEZE_COMMIT:
#   test: freeze p7 behavior baseline
```

After resolving a commit, verify its expected parent/ancestor order, exact
task-owned path set, and the staged-tree/TDD record from its owning task before
using it. `P7_CANDIDATE_COMMIT` is `git rev-parse HEAD` only after Task 11 (or
the final reviewed fix chain) and must descend from all four frozen commits.
Reconstruct all `.quality/p7-{worktrees,repos,artifacts,performance,private,
comparator}` paths from `P7_REPO_ROOT`; never persist or trust an absolute path
from another shell. A missing/duplicate subject or ancestry/path mismatch is a
stop, not a reason to pick the newest commit.

Run default/protected gates with optional external variables absent, but scope
that sanitization to the individual command. Never erase caller-supplied public,
private, or comparator configuration from the task shell before the explicit
preparation/evaluation steps:

```bash
p7_run_default() {
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_P4_REAL_EXPLORATION_REPOS_DIR \
    -u CST_P5_REAL_LANGUAGE_GRAPHS_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    -u CST_P7_PUBLIC_REPOS_DIR \
    -u CST_P7_PRIVATE_FIXTURE \
    -u CST_P7_PRIVATE_REPO \
    -u CST_P7_PRIVATE_REVIEW_ID \
    -u CST_P7_FAST_CONTEXT_COMMAND \
    "$@"
}
export P7_RUNTIME="$PWD/.quality/p5-runtime/bin/python"
test -x "$P7_RUNTIME"
p7_run_default "$P7_RUNTIME" -c \
  'import sqlite3, sys; assert sys.version_info[:2] == (3, 13); assert sqlite3.sqlite_version_info[:2] == (3, 51)'
```

Every later command described as a default or protected gate runs through
`p7_run_default` (for example,
`PYTHONPATH=... p7_run_default "$P7_RUNTIME" -m pytest ...`). Commands that
explicitly prepare pinned public repositories, a pre-frozen private overlay, or
the optional comparator do not use the wrapper and validate their own closed
environment allowlist.

Focused groups, omitting not-yet-created files until their owning task:

```bash
# P7 exact acquisition and file policy
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
  tests/test_p7_exact_intent.py \
  tests/test_p7_exact_acquisition.py \
  tests/test_p7_file_evidence.py \
  tests/test_identifier_intent.py \
  tests/test_sqlite_store_query_work.py \
  tests/test_resolved_graph_expansion.py

# P7 audit, target-bearing quality, oracle, and decision
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
  tests/test_p7_contracts.py \
  tests/test_p7_quality_cases.py \
  tests/test_p7_oracle.py \
  tests/test_p7_audit.py \
  tests/test_p7_quality_runner.py \
  tests/test_p7_decision.py \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py

# P7 ContextPack, trace, surfaces, and P4 compatibility
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
  tests/test_p7_context_pack.py \
  tests/test_p7_context_expansion.py \
  tests/test_p7_trace_v2.py \
  tests/test_p7_pipeline.py \
  tests/test_p7_surfaces.py \
  tests/test_p7_exploration.py \
  tests/test_context_pack.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_exploration_probes.py \
  tests/test_exploration_fusion.py \
  tests/test_exploration_runner.py

# Protected P0-P6 contracts
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_core_primitives.py \
  tests/test_retrieval_pipeline.py \
  tests/test_direct_text_evidence.py \
  tests/test_rerank_soft_sorting.py \
  tests/test_p5_protected_direct.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_context_pack.py \
  tests/test_context_excerpts.py \
  tests/test_exploration_boundaries.py \
  tests/test_exploration_contracts.py \
  tests/test_exploration_runner.py \
  tests/test_quality_p3.py \
  tests/test_quality_p4.py \
  tests/test_quality_p5.py \
  tests/test_p6_benchmark.py \
  tests/test_p6_measurement_worker.py

# Full suite
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P7_RUNTIME" -m pytest -q -rsxX -p no:cacheprovider
```

Every production task runs its focused group and the protected contract group.
Tasks 6 and 9-12 additionally run the full suite. No task introduces a default
skip or xfail.

Deterministic quality commands after their owning fixtures exist:

```bash
PYTHONPATH="$PWD/src" "$P7_RUNTIME" -m context_search_tool.quality run \
  tests/fixtures/p7_retrieval_quality/p7_mechanics.json \
  --profile p7_mechanics \
  --repos-dir .quality/p7-repos/mechanics \
  --output .quality/p7-artifacts/mechanics.json

PYTHONPATH="$PWD/src" "$P7_RUNTIME" -m context_search_tool.quality run \
  tests/fixtures/p7_retrieval_quality/p7_decision.json \
  --profile p7_decision \
  --repos-dir .quality/p7-repos/public \
  --output .quality/p7-artifacts/public-audit.json
```

Before every commit:

```bash
git diff --check
git diff --cached --check
git diff --cached --name-only
```

The staged-name output must be a subset of the task's exact `Files` list and
must include every intended tracked change. No ignored evidence path may be
staged.

### Isolated Worktree Setup And Validation

Baseline, instrumentation, candidate, and repeat evidence never runs from the
mutable implementation worktree. Use this exact ignored root and stop if a
target already exists:

```bash
export P7_REPO_ROOT="$(pwd -P)"
export P7_GIT_ROOT="$(git rev-parse --show-toplevel)"
export P7_WORKTREE_ROOT="$P7_REPO_ROOT/.quality/p7-worktrees"
test "$P7_REPO_ROOT" = "$(cd "$P7_GIT_ROOT" && pwd -P)"
test "$P7_WORKTREE_ROOT" = "$P7_REPO_ROOT/.quality/p7-worktrees"
mkdir -p "$P7_WORKTREE_ROOT"

export P7_BEHAVIOR_WORKTREE="$P7_WORKTREE_ROOT/behavior-baseline"
export P7_AUDIT_WORKTREE="$P7_WORKTREE_ROOT/audit-instrumentation"
test ! -e "$P7_BEHAVIOR_WORKTREE"
test ! -e "$P7_AUDIT_WORKTREE"
git worktree add --detach "$P7_BEHAVIOR_WORKTREE" \
  74aae0abe3dff685282fbcc785f7a9b3532cbbe6
git worktree add --detach "$P7_AUDIT_WORKTREE" \
  "$P7_AUDIT_INSTRUMENTATION_COMMIT"
test "$(git -C "$P7_BEHAVIOR_WORKTREE" rev-parse HEAD)" = \
  "74aae0abe3dff685282fbcc785f7a9b3532cbbe6"
test "$(git -C "$P7_AUDIT_WORKTREE" rev-parse HEAD)" = \
  "$P7_AUDIT_INSTRUMENTATION_COMMIT"
test -z "$(git -C "$P7_BEHAVIOR_WORKTREE" status --porcelain)"
test -z "$(git -C "$P7_AUDIT_WORKTREE" status --porcelain)"
```

After Task 11 creates `P7_CANDIDATE_COMMIT`, Task 12 opens one immutable
acceptance attempt and creates candidate/repeat worktrees inside it. The
operator must choose the next unused explicit two-digit ordinal; a retry after
a partial/transient failure uses a new attempt even when the commit is
unchanged:

```bash
export P7_ATTEMPT_ID="c-$(printf '%s' "$P7_CANDIDATE_COMMIT" | cut -c1-12)-a01"
printf '%s\n' "$P7_ATTEMPT_ID" |
  rg -q '^c-[0-9a-f]{12}-a(0[1-9]|[1-9][0-9])$'
export P7_ATTEMPT_ROOT="$P7_REPO_ROOT/.quality/p7-attempts/$P7_ATTEMPT_ID"
test ! -e "$P7_ATTEMPT_ROOT"
mkdir -p "$P7_REPO_ROOT/.quality/p7-attempts"
(
  cd "$P7_AUDIT_WORKTREE"
  PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
    -m context_search_tool.quality p7-open-attempt \
    --coordination-root "$P7_REPO_ROOT" \
    --expected-coordination-commit "$P7_CANDIDATE_COMMIT" \
    --evidence-root "$P7_REPO_ROOT/.quality" \
    --evaluator-closure \
    "$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold/evaluator-closure.json" \
    --candidate-commit "$P7_CANDIDATE_COMMIT" \
    --gold-freeze-commit "$P7_GOLD_FREEZE_COMMIT" \
    --audit-instrumentation-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
    --baseline-freeze-commit "$P7_BASELINE_FREEZE_COMMIT" \
    --baseline-projection-identity \
    "$P7_REPO_ROOT/docs/benchmarks/p7/baseline/public-projection-identity.json" \
    --attempt-id "$P7_ATTEMPT_ID" \
    --attempt-root "$P7_ATTEMPT_ROOT" \
    --output "$P7_ATTEMPT_ROOT/attempt-identity.json"
)

export P7_CANDIDATE_WORKTREE="$P7_ATTEMPT_ROOT/worktrees/candidate"
export P7_REPEAT_A_WORKTREE="$P7_ATTEMPT_ROOT/worktrees/repeat-a"
export P7_REPEAT_B_WORKTREE="$P7_ATTEMPT_ROOT/worktrees/repeat-b"
mkdir -p "$P7_ATTEMPT_ROOT/worktrees"
git worktree add --detach "$P7_CANDIDATE_WORKTREE" "$P7_CANDIDATE_COMMIT"
git worktree add --detach "$P7_REPEAT_A_WORKTREE" "$P7_CANDIDATE_COMMIT"
git worktree add --detach "$P7_REPEAT_B_WORKTREE" "$P7_CANDIDATE_COMMIT"
test "$(git -C "$P7_CANDIDATE_WORKTREE" rev-parse HEAD)" = \
  "$P7_CANDIDATE_COMMIT"
test "$(git -C "$P7_REPEAT_A_WORKTREE" rev-parse HEAD)" = \
  "$P7_CANDIDATE_COMMIT"
test "$(git -C "$P7_REPEAT_B_WORKTREE" rev-parse HEAD)" = \
  "$P7_CANDIDATE_COMMIT"
test -z "$(git -C "$P7_CANDIDATE_WORKTREE" status --porcelain)"
test -z "$(git -C "$P7_REPEAT_A_WORKTREE" status --porcelain)"
test -z "$(git -C "$P7_REPEAT_B_WORKTREE" status --porcelain)"
```

Prepared public/private source copies and indexes live only under their
attempt's separate `repos`, `private`, `comparator`, and `performance`
subdirectories. They are never nested in a Git worktree. Every candidate
artifact binds `attempt-identity.json`, and one final decision may consume
files from exactly one attempt. Failed attempts remain intact. Before and after
every evidence run, recheck worktree commit and clean status plus source/index
hashes.

Cleanup is not an acceptance step. Leave worktrees intact for review. If the
user later authorizes cleanup, first revalidate each exact path and clean
status, then use `git worktree remove <exact-path>` separately; never recursively
delete the worktree root.

### Mandatory TDD Evidence Protocol

Tasks 2-11 are ten test-first checkpoints. Reuse the existing validated P6
`tdd-record-v1` producer without changing its closed `task: 1..10` schema.
The schema task field is a P7 checkpoint ordinal, not the plan task number:

| plan task | checkpoint | canonical RED selectors |
| ---: | ---: | --- |
| 2 | 1 | `tests/test_p7_exact_intent.py`, `tests/test_p7_file_evidence.py` |
| 3 | 2 | `tests/test_p7_exact_acquisition.py` |
| 4 | 3 | `tests/test_p7_quality_cases.py` |
| 5 | 4 | `tests/test_p7_oracle.py`, `tests/test_p7_decision.py`, `tests/test_p7_quality_profile.py` |
| 6 | 5 | `tests/test_p7_audit.py`, `tests/test_p7_quality_runner.py`, `tests/test_p7_performance_contract.py` |
| 7 | 6 | `tests/test_p7_context_pack.py` |
| 8 | 7 | `tests/test_p7_exact_injection.py`, `tests/test_p7_exploration.py` |
| 9 | 8 | `tests/test_p7_context_expansion.py`, `tests/test_p7_trace_v2.py` |
| 10 | 9 | `tests/test_p7_pipeline.py` |
| 11 | 10 | `tests/test_p7_surfaces.py` |

For each task, add these smallest focused tests without a top-level missing
import/collection failure, set the matching checkpoint and selector array, and
capture RED against the unchanged committed production tree. Use the existing
`tdd-bootstrap` path, not `tdd-red`: the current `tdd-red` implementation does
not preserve its raw log and does not by itself prove that every failed node is
an ordinary assertion rather than an environmental/runtime failure.

```bash
mkdir -p .quality/p7-artifacts/tdd
export P7_TDD_PRE_CHANGE_COMMIT="$(git rev-parse HEAD)"
# Set the exact ordinal and selector array from the table, for example Task 2:
export P7_TDD_CHECKPOINT="1"
P7_TDD_SELECTORS=(
  tests/test_p7_exact_intent.py
  tests/test_p7_file_evidence.py
)
export P7_TDD_RED_LOG="$PWD/.quality/p7-artifacts/tdd/checkpoint-$P7_TDD_CHECKPOINT.red.log"
export P7_TDD_RED_EXIT="$PWD/.quality/p7-artifacts/tdd/checkpoint-$P7_TDD_CHECKPOINT.red.exit"
export P7_TDD_TEST_HASHES="$PWD/.quality/p7-artifacts/tdd/checkpoint-$P7_TDD_CHECKPOINT.tests.sha256"
test "$(git rev-parse HEAD)" = "$P7_TDD_PRE_CHANGE_COMMIT"
test -z "$(git status --porcelain --untracked-files=all -- src)"
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" - \
  "${P7_TDD_SELECTORS[@]}" <<'PY'
import os
from pathlib import Path
import subprocess
import sys

completed = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", *sys.argv[1:]],
    cwd=os.getcwd(),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    check=False,
    timeout=120,
)
Path(os.environ["P7_TDD_RED_LOG"]).write_text(completed.stdout, encoding="utf-8")
Path(os.environ["P7_TDD_RED_EXIT"]).write_text(
    f"{completed.returncode}\n",
    encoding="utf-8",
)
PY
shasum -a 256 "${P7_TDD_SELECTORS[@]}" > "$P7_TDD_TEST_HASHES"

P7_TDD_SELECTORS_JOINED="${P7_TDD_SELECTORS[*]}"
export P7_TDD_SELECTORS_JOINED
"$P7_RUNTIME" - <<'PY'
import os
from pathlib import Path
import re

log = Path(os.environ["P7_TDD_RED_LOG"]).read_text(encoding="utf-8")
exit_code = Path(os.environ["P7_TDD_RED_EXIT"]).read_text(
    encoding="utf-8"
).strip()
if exit_code != "1":
    raise SystemExit("RED did not exit exactly 1")
for marker in (
    "ERROR collecting",
    "ERROR at setup",
    "ERROR at teardown",
    "SyntaxError",
    "ImportError",
    "FixtureLookupError",
    "TimeoutExpired",
    "ConnectionError",
    "FileNotFoundError",
):
    if marker.lower() in log.lower():
        raise SystemExit(f"non-assertion RED marker: {marker}")
match = re.search(
    r"(?m)^(?:=+ )?(\d+) failed(?:, .*?)? in [^\n]+(?: =+)?$",
    log,
)
failed = int(match.group(1)) if match else 0
summaries = re.findall(r"(?m)^FAILED (tests/[^\n]+)$", log)
if failed < 1 or len(summaries) != failed:
    raise SystemExit("RED failure count and exact failed nodes disagree")
if any(" - AssertionError" not in summary for summary in summaries):
    raise SystemExit("every RED node must end in an explicit AssertionError")
selectors = os.environ["P7_TDD_SELECTORS_JOINED"].split()
if not selectors or any(not value.startswith("tests/test_") for value in selectors):
    raise SystemExit("RED selectors are not the reviewed focused test files")
PY
```

Every RED test uses only committed repository inputs plus task-local temporary
fixtures, denies network access, and makes its first failing capability check
inside the test body with an explicit `AssertionError` message naming the P7
contract. The capture has a hard 120-second timeout; a timeout produces no
acceptable exit record. The post-capture validator rejects mixed runtime,
collection, setup/teardown, missing-file, connection, and timeout failures and
requires every reported failed node to end in an explicit assertion. Preserve
the raw log, exit file, and test hash manifest. Implement only the named
behavior, then run the task-focused/protected/full gates required by that task.

After the task's exact `git add`, require no unstaged task changes, create the
staged tree, and let `tdd-bootstrap` revalidate the preserved RED evidence and
run GREEN against the same test bytes. Then validate the closed record:

```bash
test -z "$(git diff --name-only)"
test -z "$(git ls-files --others --exclude-standard)"
export P7_TDD_STAGED_TREE="$(git write-tree)"
P7_TDD_NODE_ARGS=()
for P7_TDD_SELECTOR in "${P7_TDD_SELECTORS[@]}"; do
  P7_TDD_NODE_ARGS+=(--pytest-node "$P7_TDD_SELECTOR")
done
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" \
  scripts/p6_benchmark.py tdd-bootstrap \
  --task "$P7_TDD_CHECKPOINT" \
  --pre-change-commit "$P7_TDD_PRE_CHANGE_COMMIT" \
  "${P7_TDD_NODE_ARGS[@]}" \
  --red-log "$P7_TDD_RED_LOG" \
  --red-exit-file "$P7_TDD_RED_EXIT" \
  --test-input-hashes "$P7_TDD_TEST_HASHES" \
  --staged-tree "$P7_TDD_STAGED_TREE" \
  --output ".quality/p7-artifacts/tdd/checkpoint-$P7_TDD_CHECKPOINT.json"
PYTHONPATH="$PWD/src" "$P7_RUNTIME" scripts/p6_benchmark.py validate \
  --report ".quality/p7-artifacts/tdd/checkpoint-$P7_TDD_CHECKPOINT.json" \
  --schema tdd-record-v1.json \
  --staged-tree "$P7_TDD_STAGED_TREE"
```

The bootstrap/GREEN producer verifies exact collected nodes, identical test
hashes, exact failed-node membership, assertion evidence, and the final staged
tree. Task 6 may extend benchmark operations but must leave this producer and
schema backward-compatible; its checkpoint proves that invariant.
Immediately after each focused commit, require:

```bash
test "$(git rev-parse 'HEAD^{tree}')" = "$P7_TDD_STAGED_TREE"
test "$(git rev-parse 'HEAD^')" = "$P7_TDD_PRE_CHANGE_COMMIT"
```

The acceptance aggregator later resolves exactly one candidate-ancestor commit
for each record whose parent is `pre_change_commit` and whose tree is
`final_staged_tree`; an absent, duplicate, reordered, or non-ancestor match
invalidates the checkpoint.
Characterization-only Task 1 runs ordinary GREEN tests and does not fabricate a
RED. Task 12 consumes the fixed task-to-checkpoint map and publishes only plan
task, checkpoint, pre-change commit, test identity, RED assertion IDs, GREEN
counts, and staged-tree hash. Pending/final records and raw pytest output remain
ignored.

If a test unexpectedly passes before implementation, either the behavior
already exists and the plan must be corrected, or the test does not exercise
the contract. Do not weaken it to manufacture RED. A later fix for the same
task preserves the canonical record and creates
`checkpoint-N-fix-01.json`, then contiguous two-digit suffixes. A fix starts
from the current clean implementation HEAD, not by rewriting history back to
the earlier task commit. Its `pre_change_commit` is that current HEAD and its
focused fix commit is the immediate child; it records the previous record hash
as `supersedes_record_hash`, keeps the same checkpoint and reviewed selector
set plus only a named regression selector when necessary, requires the
superseded focused commit to be an ancestor, and repeats RED/GREEN/tree binding.
Task 12's frozen TDD indexer orders actual candidate-ancestor commits and uses
the latest valid record for each checkpoint. It rejects a missing canonical
record, suffix gap, missing/wrong supersedes hash, changed selector without the
named regression extension, non-ancestor prior record, invalid immediate
pre-change edge, or unused later record. Every downstream gate affected by a
late fix is rerun; no branch rewrite or destructive reset is implied.

### Task 0: Establish The Clean Reviewed P7 Entry

**Purpose:** Prove that implementation starts from the reviewed documents on
the exact protected behavior baseline, not from the current untracked planning
tree or a later moving target.

**Files:**

- `docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md`
- `docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md`

**Preconditions:**

- this plan's final review result is PASS with no blocker or major finding;
- the user has explicitly authorized implementation;
- the only documentation handoff commit contains the reviewed P7 design and
  plan;
- its parent is exactly `74aae0a...`;
- no production, test, fixture, benchmark, README, or roadmap path differs from
  that parent.

- [ ] **Step 1: Create and verify the documentation-only entry**

  Stage exactly:

  ```bash
  git add \
    docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md \
    docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md
  git diff --cached --check
  test "$(git diff --cached --name-only | wc -l | tr -d ' ')" = "2"
  git commit -m "docs: add reviewed p7 design and plan"
  export P7_REVIEW_COMMIT="$(git rev-parse HEAD)"
  export P7_ENTRY_COMMIT="$P7_REVIEW_COMMIT"
  test "$(git rev-parse "$P7_ENTRY_COMMIT^")" = \
    "74aae0abe3dff685282fbcc785f7a9b3532cbbe6"
  test -z "$(git status --porcelain)"
  ```

  If the user asks for an implementation workflow without commits, stop and
  amend this commit-oriented plan rather than silently dropping its evidence
  lineage.

- [ ] **Step 2: Freeze runtime and dependency identity**

  ```bash
  mkdir -p .quality/p7-artifacts/entry
  "$P7_RUNTIME" -VV > .quality/p7-artifacts/entry/python.txt
  "$P7_RUNTIME" - <<'PY' \
    > .quality/p7-artifacts/entry/runtime.json
  import json
  import platform
  import sqlite3
  import sys
  print(json.dumps({
      "executable_name": sys.executable.rsplit("/", 1)[-1],
      "python": platform.python_version(),
      "implementation": platform.python_implementation(),
      "sqlite": sqlite3.sqlite_version,
      "platform": platform.platform(),
  }, sort_keys=True, separators=(",", ":")))
  PY
  "$P7_RUNTIME" -m pip freeze --all \
    | LC_ALL=C sort \
    > .quality/p7-artifacts/entry/dependencies.txt
  shasum -a 256 \
    .quality/p7-artifacts/entry/runtime.json \
    .quality/p7-artifacts/entry/dependencies.txt \
    > .quality/p7-artifacts/entry/environment.sha256
  ```

  The committed summary later records hashes and safe version fields, not the
  absolute interpreter path or unrelated environment values.

- [ ] **Step 3: Reproduce the complete suite and exact skip set**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
    "$P7_RUNTIME" -m pytest -q -rsxX -p no:cacheprovider \
    --junitxml .quality/p7-artifacts/entry/full-suite.xml \
    > .quality/p7-artifacts/entry/full-suite.log 2>&1
  P7_FULL_SUITE_STATUS="$?"
  test "$P7_FULL_SUITE_STATUS" = "0"
  test -z "$(git status --porcelain)"
  ```

  Parse JUnit with the existing P6-safe parser. Require `2896 passed`,
  `9 skipped`, `0 failed`, `0 errors`, and `0 xfailed`, plus the exact nine
  node IDs recorded by the XML/log. A future harmless warning-count difference
  is informational; a test/skip/xfail identity difference requires review.

- [ ] **Step 4: Reproduce protected deterministic quality**

  Run the existing CI, P2, P4, and P5 deterministic profiles into new ignored
  outputs. Reuse prepared public repositories only after their commit and clean
  status are validated; never fetch as part of this step.

  ```bash
  PYTHONPATH="$PWD/src" "$P7_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --repos-dir .quality/repos \
    --output .quality/p7-artifacts/entry/p0-ci.json

  PYTHONPATH="$PWD/src" "$P7_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --repos-dir .quality/repos \
    --output .quality/p7-artifacts/entry/p2-context.json

  PYTHONPATH="$PWD/src" "$P7_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --repos-dir .quality/p4-repos \
    --output .quality/p7-artifacts/entry/p4-exploration.json

  PYTHONPATH="$PWD/src" "$P7_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    --profile p5_language_graphs \
    --repos-dir .quality/p5-repos \
    --output .quality/p7-artifacts/entry/p5-language-graphs.json
  ```

  Require the established P0 raw CI 8/8, P2 5/5, P4 4/4, and P5 12/12
  identities. If existing fixture membership has legitimately changed after
  plan review, stop because the entry parent is no longer the reviewed
  baseline.

- [ ] **Step 5: Record source and protected projection hashes**

  Record:

  ```text
  P7_ENTRY_COMMIT
  parent commit
  clean source tree hash
  Python/SQLite/dependency hashes
  full-suite counts and exact skip IDs
  deterministic profile fixture/config/output hashes
  RetrievalTrace-v1 fixture/projection hash
  ContextPack-v2 projection hash
  ExplorationTrace-v2 projection hash
  P4 origin/probe projection hash
  P5 graph projection hash
  ```

  Store the record under `.quality/p7-artifacts/entry/entry-record.json`.
  Task 1's schema validator will validate it after that validator exists.

**Verification:**

```bash
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$P7_ENTRY_COMMIT"
PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_context_pack.py \
  tests/test_exploration_contracts.py \
  tests/test_quality_p4.py \
  tests/test_quality_p5.py
```

**Commit:** None.

### Task 1: Freeze Public Compatibility And P7 Artifact Contracts

**Purpose:** Make the reviewed compatibility delta and benchmark artifact shapes
executable before adding any P7 behavior.

**Files:**

- `tests/test_p7_contracts.py`
- `tests/fixtures/p7_retrieval_quality/contracts.json`
- `tests/fixtures/p7_retrieval_quality/retrieval_trace_v1_projection.json`
- `tests/fixtures/retrieval_core_decomposition/p7_allowed_migration.json`
- `docs/benchmarks/p7/README.md`
- `docs/benchmarks/p7/schemas/entry-record-v1.json`
- `docs/benchmarks/p7/schemas/baseline-attempt-v1.json`
- `docs/benchmarks/p7/schemas/acceptance-attempt-v1.json`
- `docs/benchmarks/p7/schemas/evaluator-closure-v1.json`
- `docs/benchmarks/p7/schemas/audit-report-v1.json`
- `docs/benchmarks/p7/schemas/public-projection-identity-v1.json`
- `docs/benchmarks/p7/schemas/baseline-neutrality-proof-v1.json`
- `docs/benchmarks/p7/schemas/audit-neutrality-proof-v1.json`
- `docs/benchmarks/p7/schemas/feasible-cover-manifest-v1.json`
- `docs/benchmarks/p7/schemas/comparison-report-v1.json`
- `docs/benchmarks/p7/schemas/performance-summary-v1.json`
- `docs/benchmarks/p7/schemas/mechanics-summary-v1.json`
- `docs/benchmarks/p7/schemas/robustness-summary-v1.json`
- `docs/benchmarks/p7/schemas/comparator-summary-v1.json`
- `docs/benchmarks/p7/schemas/protected-summary-v1.json`
- `docs/benchmarks/p7/schemas/tdd-index-v1.json`
- `docs/benchmarks/p7/schemas/private-gold-seal-v1.json`
- `docs/benchmarks/p7/schemas/private-baseline-summary-v1.json`
- `docs/benchmarks/p7/schemas/private-freeze-record-v1.json`
- `docs/benchmarks/p7/schemas/private-summary-v1.json`
- `docs/benchmarks/p7/schemas/baseline-target-manifest-v1.json`
- `docs/benchmarks/p7/schemas/baseline-opportunity-record-v1.json`
- `docs/benchmarks/p7/schemas/decision-record-v1.json`

- [ ] **Step 1: Freeze façade and dataclass projections**

  Add characterization assertions for:

  ```text
  inspect.signature(query_repository)
  inspect.signature(trace_repository)
  inspect.signature(build_context_pack)
  dataclasses.fields(QueryBundle)
  dataclasses.fields(ContextPackOptions)
  public RetrievalResult/EvidenceAnchor constructor parameters
  CLI query/context/trace option names
  MCP query/context/trace parameter names and null behavior
  ```

  The fixture records public fields, order, defaults, and serialized keys. It
  explicitly permits later private `_context_segments` and
  `_protected_path_order` constructor-compatible fields only when they remain
  `repr=False`, `compare=False`, and absent from public serializers. It does not
  permit a QueryBundle field or façade parameter.

- [ ] **Step 2: Freeze the v1-to-v2 compatibility ledger**

  Capture representative RetrievalTrace-v1 payloads for:

  - one normal result;
  - one overlap-merged result whose accumulated first origin is not its score
    winner;
  - one evidence anchor;
  - interleaved result/anchor selection;
  - more than eight origins;
  - missing index, no candidates, and store-read error.

  Store source-free payloads in
  `retrieval_trace_v1_projection.json`. The contract test defines the only
  allowed migration deltas:

  ```text
  schema_version 1 -> 2
  one file_projection stage after context_expansion
  five-stage rank history
  ordering_chunk_id
  display_origin_chunk_ids
  origin_chunk_omitted_count
  winner-first public origin projection
  file-level result membership/order
  ```

  Existing source-count keys, limits, error envelopes, timing units, and
  privacy rules remain exact.

  Also hash-protect the existing
  `retrieval_core_decomposition/{baseline,migration_ledger}.json` bytes and add
  `p7_allowed_migration.json`. That closed ledger permits only:

  - Task-3 outcome-wrapper operation names normalized to the same existing
    store operation, with side data excluded from public characterization, plus
    the exact eligible-literal/`lexical_top_k == 0` metadata-only path/symbol
    edge: one request-scoped connection/pass instead of zero, zero broad
    candidates, and no change for an ineligible/no-literal request;
  - Task-8 P4 follow-up-only inverse under `protection_disabled`: remove exactly
    that metadata-only connection/pass when an eligible exact literal is
    present; initial retrieval, ordinary enabled lanes, candidate bytes,
    network work, and every no-literal case remain unchanged;
  - Task-9 repeated same-path stat/read reductions and private winner data;
  - Task-10 one-result-per-path membership/order/display changes, the explicit
    file-projection stage, trace-v2 provenance, and Task-10 private pack
    transport;
  - Task-10 numeric normalization changes only when exact injection changes the
    candidate domain/max and the frozen helper deterministically recomputes the
    value; the ledger requires the injected-population witness and exact
    before/after domain hashes for each such delta.

  It forbids wildcard paths, arbitrary ignored keys, score-part keys, weights,
  bonuses, helper/source/AST/formula changes, unattributed numeric deltas,
  unlisted store/network operations, and mutation of the two old fixtures.

- [ ] **Step 3: Define closed artifact schemas**

  Schemas require exact top-level keys, schema version, finite numbers,
  canonical relative public paths, lowercase safe IDs, canonical enums, hash
  prefixes, UTC timestamps, and explicit nullability. They reject unknown
  fields, NaN/Infinity, source content, raw queries in private summaries,
  absolute paths, and unbounded diagnostics.

  `baseline-attempt-v1` binds one explicit
  `b-<audit-commit[0:12]>-aNN` ID to behavior/audit commits and trees,
  evaluator/gold/runtime/dependency/environment identities, creation UTC, and
  one ignored baseline attempt root. Every baseline repository copy, raw
  artifact, private freeze input, repeat proof, target manifest, opportunity
  record, and publication receipt repeats its identity hash. A complete
  baseline freeze selects exactly one attempt; partial attempts remain
  immutable and cannot be mixed or reused.

  `acceptance-attempt-v1` binds one explicit safe attempt ID to the candidate
  commit/tree, freeze identities, evaluator closure, runtime/dependency,
  environment-presence projection, creation UTC, and exact attempt root. Every
  candidate-side proof/summary/report repeats its identity hash. Cross-attempt
  input mixing is invalid even when candidate commits are equal.

  Every candidate-side mechanics, robustness, comparison, neutrality,
  performance, protected, private, comparator, and decision schema requires
  that exact attempt ID/hash and a causally nested run interval. Baseline-only
  schemas reject attempt fields.

  `audit-report-v1` distinguishes:

  ```text
  behavior_baseline_commit
  audit_instrumentation_commit
  candidate_commit
  exact_injection_mode
  exact_injection_applied
  graph_state
  signal_exact_revoked_count
  file_projection_mode
  actual_terminal_reason
  policy_shadow_terminal_reason
  ```

  `exact_injection_mode` is the report/ledger policy state
  (`shadow` or `enforced`). `exact_injection_applied` is a per-retrieval event:
  true only when at least one injected candidate survives the final graph state
  into direct merge. `graph_state` is one closed lifecycle value and
  `signal_exact_revoked_count` is zero except for the Task-10 ready-to-fault
  rollback. Baseline and non-fault candidate reports require zero; a positive
  count requires `graph_state=faulted`, final signal-free provenance, and exact
  contribution-lineage/count consistency. Revocation is a non-terminal
  diagnostic; it does not add a terminal reason.

  `evaluator-closure-v1` is a sorted exact path-to-blob-hash manifest for the
  frozen Task-6 driver, case/provenance resolver, oracle, audit finalizer,
  metrics, aggregation, projection normalization, compare/decision code,
  canonical serialization, schemas, fixture/profile inputs, coherent-variant
  selection, metamorphic-transform validation, and the production
  anti-special-casing scanner. It excludes its own bytes, contains no
  candidate-derived hash, and has one canonical domain-separated closure
  digest.

  `performance-summary-v1` requires the frozen workload-manifest hash,
  baseline/candidate/environment identities, fixed warmup and sample counts,
  per-operation p50/p95 and ratio values for exact query, exploratory query, and
  context, RSS ratio, store/source/network work counters, the separate explore
  retrieval-call ceiling/count, every reviewed threshold, and one pass/fail per
  threshold. Explore-latency keys are forbidden rather than nullable because P7
  defines no explore-latency sample contract. It contains normalized summaries
  only, never raw timing samples or command lines.

  `audit-neutrality-proof-v1` binds the separately validated identity/control
  and timing envelopes for one audit-enabled and one audit-disabled run of the
  same product/profile/input identity. It requires exact equality of the
  schema-defined public output/error/work-counter behavioral payload, confirms
  zero observer/ledger state in the disabled worker after return, and stores no
  source content. Product commits, audit modes, run roles/IDs/timestamps, and
  audit-output presence remain bound proof inputs outside the equality payload;
  no unequal identity is normalized away.

  `baseline-neutrality-proof-v1` is the six-role counterpart for the complete
  `p7_decision` profile: two behavior-root audit-disabled runs, two
  instrumentation-root audit-disabled runs, and two instrumentation-root
  audit-enabled runs plus both enabled audit reports. It binds every
  role-specific identity/control/timing envelope, requires within-role repeats,
  cross-root behavioral-payload equality, instrumentation enabled/disabled
  equality, enabled audit-leaf repeat equality, and exact prepared-copy
  identity. It is distinct from the one-pair candidate
  `audit-neutrality-proof-v1`.

  `comparison-report-v1` binds the exact baseline audit and freeze/projection
  identity, candidate audit and repeat proof, candidate public
  audit-neutrality proof, resolved-gold validation, source/index/config/runtime
  identity, and all per-case regression/improvement facts. It cannot validate
  when any bound proof fails or belongs to another candidate attempt.

  `mechanics-summary-v1` requires the two enforced candidate
  audit/projection hashes, their profile-repeat proof, all eight exact case IDs,
  every mandatory absolute invariant/result, frozen
  evaluator/candidate/source identities, the candidate mechanics
  audit-neutrality-proof hash/pass, and one aggregate pass. A baseline audit
  cannot satisfy this candidate-only schema.

  `robustness-summary-v1` requires the frozen transform/profile/source/index
  identities, at least three exact companion IDs, base/transformed coherent
  terminal-result hashes modulo each rename map, per-companion pass/fail, the
  candidate production-tree hash, anti-special-casing scanner/rule/forbidden
  manifest hashes, zero forbidden production matches, and one aggregate pass.
  It contains no query/source content and is mandatory decision input.

  `comparator-summary-v1` permits only `unavailable`, `complete`, `partial`, or
  `failed`, a safe run/config/version hash when exposed, case/response/retry/
  failure/truncation counts, aggregate path/span recall when computable,
  descriptive overlap and normalized latency, and zero raw queries, result
  paths, snippets, responses, commands, or local paths. It is non-gating but its
  validated hash/status is mandatory decision provenance.

  `private-summary-v1` permits only `paired_frozen`, `late_informational`, or
  `unavailable`, an exact vote-eligibility boolean, aggregate pass/privacy
  status, and the design's source-free sufficient statistics: case/required
  unit/terminal-miss counts, stage recall, unit-miss counts by reason group,
  case-vote counts including `case_mixed`, distinct supporting-case counts,
  unique-path ratio, latency, invariant outcomes, computed classification, and
  classification-proof hash. Only `paired_frozen` may be vote-eligible, and
  frozen decision code recomputes the thresholds/dominance/ties from those
  counts and requires the classification to match. It contains no raw-audit,
  fixture, repository, source/index,
  freeze-input, review-identity, query, identifier, path, origin, or local-user
  hash/value. Those bindings remain in ignored local validation evidence; the
  decision records only this sanitized summary's own hash.

  `private-gold-seal-v1`, `private-baseline-summary-v1`, and
  `private-freeze-record-v1` are ignored-artifact schemas frozen in the
  evaluator closure. Before any private baseline call, the first binds exact
  fixture/profile/targets/coherent variants, a private feasible-cover witness,
  prepared source/index/options, thresholds, and distinct label-author/reviewer
  identities. The second is the allowlisted pre-candidate baseline aggregate.
  The third binds both prior artifacts to evaluator/public-gold, freeze-UTC,
  owner-review, and run identities. All forbid source content and raw
  query/path values; unlike `private-summary-v1`, their sensitive identity
  hashes remain local and are forbidden from publication or decision
  embedding.

  `protected-summary-v1` requires exact full-suite pass/skip/error identities,
  immutable P3 v1 hashes, mandatory P0/P2/P4/P5 profile hashes/outcomes, P4
  call ceilings, P6 work-contract results, the exact checkpoint 1-10 TDD map
  with resolved focused-commit ancestry/tree identity, and explicit validated
  availability for each optional pinned-real profile.

  `tdd-index-v1` requires checkpoint ordinals 1-10 exactly once, a canonical
  record plus contiguous `fix-01`, `fix-02`, ... records per ordinal when
  present, identical reviewed selector identity within each logical chain,
  exact `supersedes_record_hash`, each record's own
  pre-change/focused-commit immediate parent/tree edge, ancestry of every
  superseded focused commit, candidate commit order, and the latest valid
  record selected for acceptance.

  `public-projection-identity-v1` requires both behavior/audit implementation
  commits and trees, all six run/source/index/config/environment hashes,
  within-mode repeat equality, same-instrumentation-root audit-on/off equality,
  behavior-versus-instrumentation-disabled equality after the closed timing
  normalization, the separately validated expected A/B run-ID/UTC identity
  projection, enabled-run audit availability, the two-run complete
  `p7_decision` projection/audit equality proof, the selected canonical-run
  hashes, and zero unreviewed normalized field.

  `decision-record-v1` permits only the eleven reviewed classifications and one
  matching next-phase mapping. It requires exact validated baseline audit,
  baseline-freeze commit and public-projection-identity, candidate audit,
  public comparison, resolved-gold provenance, candidate public
  audit-neutrality proof, and
  mechanics/robustness/protected/performance/private/comparator summary hashes.
  It requires mechanics, robustness, protected, performance, comparison, gold,
  and candidate-neutrality aggregate pass; records private and comparator
  status even when unavailable; and rejects mismatched environment,
  candidate-attempt, run-role, or causal timestamp identities.

- [ ] **Step 4: Validate the Task-0 entry record**

  Add a reusable schema loader/validator and make default pytest validate only
  committed synthetic examples with safe paths and IDs. Validate the real
  `.quality/p7-artifacts/entry/entry-record.json` through an explicit
  task-local validator invocation in this step; no committed/default test may
  require an ignored artifact, network, prepared public checkout, or private
  environment. Plan-time local absolute paths are not copied into fixtures.

- [ ] **Step 5: Run characterization and protected gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_contracts.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_context_pack.py \
    tests/test_exploration_contracts.py
  ```

- [ ] **Step 6: Commit the frozen contracts**

  ```bash
  git add \
    tests/test_p7_contracts.py \
    tests/fixtures/p7_retrieval_quality/contracts.json \
    tests/fixtures/p7_retrieval_quality/retrieval_trace_v1_projection.json \
    tests/fixtures/retrieval_core_decomposition/p7_allowed_migration.json \
    docs/benchmarks/p7/README.md \
    docs/benchmarks/p7/schemas/entry-record-v1.json \
    docs/benchmarks/p7/schemas/acceptance-attempt-v1.json \
    docs/benchmarks/p7/schemas/evaluator-closure-v1.json \
    docs/benchmarks/p7/schemas/audit-report-v1.json \
    docs/benchmarks/p7/schemas/public-projection-identity-v1.json \
    docs/benchmarks/p7/schemas/baseline-neutrality-proof-v1.json \
    docs/benchmarks/p7/schemas/audit-neutrality-proof-v1.json \
    docs/benchmarks/p7/schemas/feasible-cover-manifest-v1.json \
    docs/benchmarks/p7/schemas/comparison-report-v1.json \
    docs/benchmarks/p7/schemas/performance-summary-v1.json \
    docs/benchmarks/p7/schemas/mechanics-summary-v1.json \
    docs/benchmarks/p7/schemas/robustness-summary-v1.json \
    docs/benchmarks/p7/schemas/comparator-summary-v1.json \
    docs/benchmarks/p7/schemas/protected-summary-v1.json \
    docs/benchmarks/p7/schemas/tdd-index-v1.json \
    docs/benchmarks/p7/schemas/private-gold-seal-v1.json \
    docs/benchmarks/p7/schemas/private-baseline-summary-v1.json \
    docs/benchmarks/p7/schemas/private-freeze-record-v1.json \
    docs/benchmarks/p7/schemas/private-summary-v1.json \
    docs/benchmarks/p7/schemas/decision-record-v1.json
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "test: lock p7 contracts and artifact schemas"
  ```

**Commit:** `test: lock p7 contracts and artifact schemas`

### Task 2: Add Pure Exact-Intent And File-Evidence Policy Primitives

**Purpose:** Implement the deterministic rules that both Slice-0 shadow
observation and later production enforcement will call, without touching the
retrieval pipeline.

**Files:**

- `src/context_search_tool/identifier_intent.py`
- `src/context_search_tool/scanner.py`
- `src/context_search_tool/retrieval_core/types.py`
- `src/context_search_tool/retrieval_core/exact_intent.py`
- `src/context_search_tool/retrieval_core/file_evidence.py`
- `tests/test_identifier_intent.py`
- `tests/test_tokenizer_scanner.py`
- `tests/test_p7_exact_intent.py`
- `tests/test_p7_file_evidence.py`
- `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write RED exact-literal tests**

  Cover:

  - NFC normalization and first-occurrence ordering;
  - deduplication without alphabetic sorting;
  - maximum sixteen distinct literals plus occurrence-ordered
    `budget_omitted`;
  - full paths, two-component suffixes, qualified names, Pascal/camel/snake
    identifiers;
  - generic-token, split-component, substring, absolute, `..`, wildcard, and
    invalid suffix rejection;
  - path-separator normalization without host case folding;
  - exact protectable filename positives and negatives from the design;
  - compound name, final-suffix, dotfile, and case-preserved resolution rules;
  - opaque literal spans and the closed punctuation/conjunction clause split;
  - same-clause path/unit narrowing, cross-clause isolation, conflicts, and
    priority-level non-fallthrough.

  The first RED assertion must call a capability seam inside the test body; a
  missing-module collection error is invalid.

- [ ] **Step 2: Expose the scanner suffix set without widening it**

  Keep `_LANGUAGES_BY_SUFFIX` as the scanner's one map and expose an immutable
  suffix-key view. `is_protectable_filename` consumes that view plus exactly the
  reviewed full-name allowlist. Add a test that compares the exported set to the
  scanner map so future scanner language changes are explicit review events.

- [ ] **Step 3: Add private frozen exact-intent models**

  `retrieval_core.exact_intent` owns:

  ```text
  ExactLiteral
  ActivePathFact
  DeclarationFact
  ExactResolution
  ProtectedPathRequirement
  OriginalLaneChunk
  ```

  Validate canonical paths, occurrence indexes, closed states/kinds/origins,
  declaration ranges, and optional-field consistency. These are private and
  never serialized by public retrieval.

- [ ] **Step 4: Implement the pure resolution algorithm**

  Given pre-collected active path/declaration facts, resolve each literal in
  this exact priority: full path, component-boundary suffix, filename, file
  stem, qualified declaration, simple declaration, then content-only ordinary
  recall. Apply same-clause constraints only to the first non-empty level,
  deduplicate declarations by
  `(path,start_line,end_line)`, prefer active-symbol provenance on an identical
  range, and compute path and declaration states separately.

  Content-level facts may create ordinary recall metadata but must return
  structural state `missing`.

- [ ] **Step 5: Implement the canonical injection key**

  Add a pure chooser over original-query lane returns:

  ```text
  path_symbol < signal < direct_text < lexical < semantic
  then one-based lane return rank
  then start_line, end_line, chunk_id
  ```

  Declaration-unique wins before this chooser; the first active file chunk is
  the final fallback. Planner, anchor, relation, and probe inputs are rejected
  by type/source validation rather than merely sorted later.

- [ ] **Step 6: Write RED file-evidence policy tests**

  With synthetic expanded inputs, cover:

  - explicit independent-display versus same-file-traversal-only visibility;
  - derived non-sticky visibility after evidence merge;
  - ordering chunk chosen only by canonical expanded order;
  - no score aggregation from later chunks;
  - protected declaration windows before ordering and remaining windows;
  - maximum two normal segments and one anchor window;
  - overlap/adjacent coalescing;
  - successful transitive bridge coalescing both segments and freeing one slot;
  - successful bridge input receiving `coalesced_same_file_span` while both
    prior inputs retain their original trace decisions;
  - failed bridge leaving both segments byte-identical and receiving
    `same_file_span_limit`;
  - eight-origin focus cap and deterministic omission;
  - every anchor input passthrough, including duplicates;
  - complete normal-file population without a capacity argument;
  - independent protected-first result/anchor capacity selection;
  - occurrence-order overflow, canonical/effective ranks, fill, and omission
    reasons.

- [ ] **Step 7: Implement the pure file policy**

  `file_evidence.py` owns anchor classification shared by projection/selection,
  visibility derivation, its own frozen source-independent input/segment/file
  values, display-segment choice, `FileEvidencePopulation`, and pure partition
  selection. It accepts primitive projections of already materialized expanded
  inputs and does not import mutable retrieval candidate/result models;
  orchestration adapters live outside this frozen module. It never reads the
  store, repository, config file, source file, planner, or network.

  Keep `final_top_k` and anchor capacity out of projection APIs. Only the
  partition-selection API accepts capacities.

- [ ] **Step 8: Protect import boundaries and run gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_exact_intent.py \
    tests/test_p7_file_evidence.py \
    tests/test_identifier_intent.py \
    tests/test_tokenizer_scanner.py \
    tests/test_retrieval_core_boundaries.py
  ```

  Verify no production caller invokes the new projection/resolution helpers yet
  and normalized public behavior remains identical.

- [ ] **Step 9: Commit**

  ```bash
  git add \
    src/context_search_tool/identifier_intent.py \
    src/context_search_tool/scanner.py \
    src/context_search_tool/retrieval_core/types.py \
    src/context_search_tool/retrieval_core/exact_intent.py \
    src/context_search_tool/retrieval_core/file_evidence.py \
    tests/test_identifier_intent.py \
    tests/test_tokenizer_scanner.py \
    tests/test_p7_exact_intent.py \
    tests/test_p7_file_evidence.py \
    tests/test_retrieval_core_boundaries.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p7 evidence policy core"
  ```

**Commit:** `feat: add p7 evidence policy core`

### Task 3: Collect Exact Acquisition And Traversal Facts Without Changing Output

**Purpose:** Obtain all future exact-resolution and visibility facts inside the
existing read scopes and prove the work contract before any injection or
selection behavior changes.

**Files:**

- `src/context_search_tool/models.py`
- `src/context_search_tool/sqlite_store.py`
- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/retrieval_core/candidates.py`
- `src/context_search_tool/retrieval_core/exact_intent.py`
- `src/context_search_tool/retrieval_core/expansion.py`
- `src/context_search_tool/retrieval_core/types.py`
- `tests/test_p7_exact_acquisition.py`
- `tests/test_sqlite_store_query_work.py`
- `tests/test_retrieval_pipeline.py`
- `tests/test_resolved_graph_expansion.py`
- `tests/test_retrieval_core_characterization.py`
- `tests/test_retrieval_core_boundaries.py`
- `tests/retrieval_core_characterization.py`

- [ ] **Step 1: Write RED work-identity tests**

  Instrument connection opens, SQL statement classes, row visits, candidate
  helper calls, and graph session identity. Compare exact-literal and
  no-literal requests with identical planner/config state:

  - enabled path/symbol lane: same connection/pass/statement count;
  - enabled signal lane: same graph session and signal search call count;
  - `lexical_top_k == 0` plus eligible exact literal: exactly one metadata-only
    path/symbol connection/pass for all literals and zero broad candidates;
  - disabled lane plus no eligible literal: zero connection/pass;
  - no per-literal query, second path pass, or extra signal search;
  - planner-token calls retain their existing counts and cannot contribute
    original exact facts.

  Row/VM counts are diagnostic ceilings derived from fixture size; the hard
  contract is statement/pass/connection identity and bounded one-pass rows, not
  an unstable wall-clock assertion.

  Extend the characterization operation recorder to observe the new internal
  outcome seam as the same existing path/symbol or signal store operation,
  while recording exact side-data work only in focused P7 tests. Do not let a
  renamed wrapper disappear from the protected operation ledger.

- [ ] **Step 2: Add a one-pass path/symbol outcome**

  Preserve `path_symbol_candidates(...) -> list[RetrievalCandidate]` as a
  compatibility wrapper. Add one internal outcome-producing method that, in the
  same connection and existing path/token/symbol row passes, returns:

  ```text
  ordinary bounded candidates
  per-literal/per-clause saturated path and unit-constraint states
  at most two canonical witnesses per state
  selected unique-path declaration/first-chunk candidates
  bounded original-literal lane-rank facts
  measured work counters for tests/audit
  ```

  Broaden selected columns or decode existing chunk metadata inside those same
  rows; do not add another table scan. A zero-limit metadata-only call emits
  side data but no ordinary candidates. Do not return or retain repository-wide
  path, chunk, project-unit, or symbol fact collections. Accumulate
  unconstrained and each exact same-clause intersection independently as rows
  pass, saturating counts at `0 | 1 | >=2`; never derive a constrained state
  from an already capped unconstrained witness list. Retain a first
  chunk/declaration only after a unique path is selected, and cap rank facts by
  the ordinary candidate/literal contract.

- [ ] **Step 3: Derive structured declaration facts from the existing signal result**

  `signal_candidates` already uses `GraphReadSession.signal_search`, whose
  public result is truncated to its ordinary limit. Add an internal
  same-session outcome that computes exact declaration state from the complete
  pre-limit matching set inside that one existing SQL/search pass, then returns
  the unchanged ordinary `matches[:limit]` candidates/order. It extracts only
  ready, recallable `java_ast` type/method/field/endpoint declarations.

  For each of the at-most-sixteen literals, distinct path/declaration counts
  saturate at two and retain at most two canonical witness keys, which is enough
  to prove missing/unique/ambiguous without unbounded side state. When a literal
  has clause-local path/unit constraints already collected by the path pass,
  compute both unconstrained and exact-intersection saturated states inside the
  same traversal; the witness cap must not discard a third path that is the
  sole constrained survivor. Never infer uniqueness from the truncated
  candidate list. Add RED cases where the first same-name declaration is inside
  the candidate limit and the second is outside it, and where narrowing selects
  a later canonical path; both states must be correct. Legacy/stale paths supply
  no structured declaration proof.

  Do not call `signals_for_chunk`, `find_signals`, or a second signal search for
  exact intent.

  Mirror the constrained-third-path case for path/symbol facts: two earlier
  unconstrained paths saturate the witness list, a later third path is the sole
  project-unit survivor, and both unconstrained ambiguity and constrained
  uniqueness must remain correct. Add a large-index fixture/assertion showing
  retained exact side-data cardinality is bounded by literals, declared
  constraints, ordinary candidate limits, and two witnesses—not repository
  path/symbol count—and include it in the P7 RSS/work gate.

- [ ] **Step 4: Add original-lane rank side data**

  Preserve lane return order before merge for path/symbol, signal, direct text,
  lexical, and semantic original-query calls. Record only chunk IDs, lane rank,
  source, and indexed range/path facts. Planner variants/candidates use separate
  wrappers and never enter the canonical exact domain.

- [ ] **Step 5: Carry explicit traversal evidence**

  Add constructor-compatible private evidence flags to candidate/internal value
  types. Same-file anchor expansion sets only
  `same_file_traversal_evidence`. Ordinary recall, resolved relations,
  protection, and current-policy display-eligible directory evidence set
  `independent_display_evidence`. Merge recomputes visibility from the complete
  evidence instead of OR-ing a sticky `traversal_only` boolean.

  These fields do not change score parts, source strings, trace counts, ranking,
  or selection yet.

- [ ] **Step 6: Observe resolutions locally but do not inject**

  In `_query_repository_impl`, extract exact literals during query
  understanding, combine the path/symbol and structured-signal facts after the
  existing signal stage, and construct request-local `ExactResolution` values.
  Do not append a canonical candidate, set a result marker, call file
  projection, or alter final selection.

  A test monkeypatches the future injection helper to fail if called.

- [ ] **Step 7: Prove byte-identical existing behavior**

  For missing/legacy/ready/stale graph modes, planner disabled/enabled/fallback,
  zero/nonzero lexical limits, and exact/no-exact queries, compare:

  ```text
  QueryBundle public projection
  RetrievalTrace-v1 payload with timing normalized
  ContextPack-v2 canonical bytes
  P4 probe/fusion projection
  source counts and candidate counts
  ```

- [ ] **Step 8: Run gates and commit**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_exact_acquisition.py \
    tests/test_sqlite_store_query_work.py \
    tests/test_retrieval_pipeline.py \
    tests/test_resolved_graph_expansion.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py

  git add \
    src/context_search_tool/models.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/candidates.py \
    src/context_search_tool/retrieval_core/exact_intent.py \
    src/context_search_tool/retrieval_core/expansion.py \
    src/context_search_tool/retrieval_core/types.py \
    tests/test_p7_exact_acquisition.py \
    tests/test_sqlite_store_query_work.py \
    tests/test_retrieval_pipeline.py \
    tests/test_resolved_graph_expansion.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/retrieval_core_characterization.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: observe p7 exact acquisition facts"
  ```

**Commit:** `feat: observe p7 exact acquisition facts`

### Task 4: Add Target-Bearing Quality Schema V2 And Gold Validation

**Purpose:** Make every P7 attribution case identify the exact required span,
not merely a path that could hide a wrong-chunk result.

**Files:**

- `src/context_search_tool/quality/cases.py`
- `tests/test_p7_quality_cases.py`
- `tests/test_quality_cases.py`
- `tests/test_quality_catalog.py`
- `tests/fixtures/p7_retrieval_quality/schema_examples.json`

- [ ] **Step 1: Write RED schema-v2 parsing tests**

  Add frozen dataclasses for:

  ```text
  EvidenceTarget
  EvidenceAlternative
  EvidenceUnit
  EvidenceCoverChoice
  EvidenceCoverVariant
  IdentifierExpectation
  GoldFreezeInputs
  GoldProvenanceSeal
  ResolvedGoldProvenance
  ```

  Test exact key sets, closed enums, ID syntax, case surface, limits, canonical
  paths, required boolean, roles, alternatives, symbol/range/literal selectors,
  `protected_by` references, and one-to-64 coherent cover variants. Include
  Unicode positive/negative cases proving every `IdentifierExpectation.literal`
  appears literally in the NFC-normalized original query after the literal is
  NFC-normalized; canonically equivalent text passes and absent text fails.

- [ ] **Step 2: Preserve schema-v1 read behavior**

  Existing v1 fixture objects and every current profile must parse to the same
  values. V1 cannot silently receive empty evidence units and cannot enter a
  P7 profile. Add explicit profile validation that rejects a v1 case in
  `p7_mechanics`, `p7_decision`, or `p7_private`.

- [ ] **Step 3: Resolve targets against pinned indexed source**

  Add preflight functions, separate from JSON parsing, that:

  - verify the source checkout commit/content identity;
  - require each exact path to exist in the isolated pinned workspace;
  - resolve a symbol to one active declaration in that path;
  - require line ranges to be one-based, inclusive, in-file, and 1-80 lines;
  - require symbol/range overlap when both exist;
  - require at least one active indexed chunk to fully cover the canonical
    target range;
  - require every literal to be NFC-normalized, case-sensitive, 4-160 code
    points, control-free, and inside the target range;
  - require each normalized identifier-expectation literal to occur as an exact
    case-sensitive substring of the NFC-normalized original query;
  - record the continuous canonical target range without source content.

- [ ] **Step 4: Enforce anti-gaming rules**

  Reject:

  - duplicate required units with the same canonical alternatives/targets;
  - overlapping required ranges on one path;
  - path-only required units;
  - globs/contains matchers in evidence alternatives;
  - overloaded symbols without a line range;
  - more than 16 units, 4 alternatives, or 3 literals per alternative;
  - duplicate identifier expectation literals;
  - unique identifier expectations without path/declaration state;
  - non-unique expectations with an expected path;
  - `protected_by` references whose path is absent from the unit alternatives;
  - a missing/partial/duplicate cover variant, unknown or repeated required-unit
    choice, invalid alternative index, non-canonical unit order, duplicate
    variant tuple, or required alternative not represented by any variant.

  Each variant maps every required evidence unit exactly once to one alternative
  index. Optional units do not enter the map. Terminal scoring and attribution
  may accept one complete declared variant but may never synthesize a cover from
  choices belonging to different variants.

- [ ] **Step 5: Validate the two-state gold provenance lifecycle**

  `GoldFreezeInputs` is the only pre-seal authoring/preflight type. It has the
  exact source/profile/fixture/helper/options/witness/threshold/label fields
  reviewed by the design and deliberately no `gold_freeze_commit`. It may be
  used to validate labels and feasible cover in Task 5, but it is rejected by
  run, compare, publish, and decide APIs.

  `GoldProvenanceSeal` contains the later immutable gold commit plus exact
  hashes of the frozen inputs and every referenced blob. The resolver reads
  the two exact filenames from one explicit provenance root, verifies both
  against the named Git object, rejects duplicate fields, conflicts, unknown
  keys, missing blobs, or current-worktree substitution, and constructs one
  in-memory `ResolvedGoldProvenance`. Its canonical bytes/hash are the
  domain-separated canonical JSON of:

  ```text
  "p7-resolved-gold-provenance-v1\n" || freeze_inputs || seal
  ```

  Only the resolved type is accepted by evaluation/comparison/decision code.
  Author and reviewer IDs must differ. At this task all three types use
  synthetic identities; fixed decision gold is not frozen until Tasks 5-6.

- [ ] **Step 6: Run gates and commit**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_quality_cases.py \
    tests/test_quality_cases.py \
    tests/test_quality_catalog.py

  git add \
    src/context_search_tool/quality/cases.py \
    tests/test_p7_quality_cases.py \
    tests/test_quality_cases.py \
    tests/test_quality_catalog.py \
    tests/fixtures/p7_retrieval_quality/schema_examples.json
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p7 evidence unit contracts"
  ```

**Commit:** `feat: add p7 evidence unit contracts`

### Task 5: Freeze Feasibility, Oracle, Profile, And Decision References

**Purpose:** Establish target-bearing gold, prove that every required evidence
set can fit its declared surface budgets, and freeze the reference algorithms
before either the behavior baseline or the candidate can influence them.

**Files:**

- `src/context_search_tool/quality/oracle.py`
- `src/context_search_tool/quality/p7_decision.py`
- `tests/test_p7_oracle.py`
- `tests/test_p7_decision.py`
- `tests/test_p7_quality_profile.py`
- `tests/fixtures/p7_retrieval_quality/p7_mechanics.json`
- `tests/fixtures/p7_retrieval_quality/p7_decision.json`
- `tests/fixtures/p7_retrieval_quality/p7_profile.json`
- `tests/fixtures/p7_retrieval_quality/metamorphic_transforms.json`
- `tests/fixtures/p7_retrieval_quality/public_source_manifest.json`
- `tests/fixtures/p7-retrieval-quality`
- `docs/benchmarks/p7/gold/gold-freeze-inputs.json`
- `docs/benchmarks/p7/gold/feasible-cover-manifest.json`
- `docs/benchmarks/p7/gold/label-review.json`

- [ ] **Step 1: Write RED feasibility-search tests**

  Add small synthetic cases that exercise:

  - rejection above 64 source-authored coherent cover variants;
  - canonical required-unit order, valid alternative indices, duplicate-tuple
    rejection, and exact declared variant order;
  - proof that alternatives from two different variants can never form a
    feasible or terminal “Frankenstein” cover;
  - the lexicographic objective: path count, non-overlapping range count,
    canonical pack bytes, canonical path tuple, then the order/ID-independent
    semantic choice key over partition/role/path/range/literal hashes;
  - overlap/adjacency coalescing and the same transitive bridge semantics as the
    frozen file policy;
  - `query` one-public-window feasibility, including the rule that a private
    second segment cannot rescue raw output;
  - `context` and `explore` two normal windows but one evidence-anchor window;
  - result/anchor partition capacities, `max_items`, excerpt count/bytes,
    per-item bytes, total-content bytes, and canonical final-pack bytes;
  - one complete target and all literals in one window/excerpt, never a union
    across partial excerpts;
  - source, resolved-options, helper, and witness mismatch failures;
  - an infeasible case failing setup before any retrieval callback runs.
  - a joint permutation property: reorder variants/units/alternatives and
    rename variant/unit IDs without changing semantic choices; the witness
    semantic hash, file/span oracle output, finalizer result, and gates remain
    identical, while source-backlink diagnostic indices may change.

  The RED nodes call stable seams in existing `quality.cases` and
  `retrieval_core.file_evidence`; a missing-module collection failure is not
  acceptable TDD evidence.

- [ ] **Step 2: Implement the frozen reference helper**

  `quality.oracle` owns immutable, evaluation-only values:

  ```text
  FEASIBILITY_CONTRACT_VERSION = 1
  FeasibleCoverChoice
  FeasibleCoverWitness
  FeasibilityOptions
  OraclePathForce
  OracleSpanForce
  ReferenceContextPackProjection
  ReferenceExploreFusionProjection
  MetamorphicTransform
  apply_metamorphic_transform
  validate_metamorphic_identity
  ```

  The helper consumes resolved target metadata and source observations from
  preflight. It stores no source content. Its canonical hash covers:

  - `quality/oracle.py`;
  - the complete allowlisted transitive local source closure of the Task-2 pure
    visibility/projection/range helpers it calls, intentionally limited to the
    frozen `file_evidence.py` policy values rather than later mutable retrieval
    models;
  - the exact canonical-JSON encoder;
  - the versioned options projection.

  Later production slices call the Task-2 policy helper; they do not copy it.
  The two reference surface projections are benchmark-only frozen models of
  the reviewed protected reservation, segment-local excerpt, blocked retry,
  and existing P4 path-fusion rules. They make baseline shadow attribution
  possible before production transport is activated; they never return a
  public product object or run retrieval. Reference code may import only the
  standard library and the explicitly hashed frozen policy closure; it must not
  call the mutable production ContextPack builder. An import-closure test fails
  if a new un-hashed local dependency appears.
  Neither `quality/oracle.py` nor the hashed policy helper may change after
  this task without a new gold freeze. An import-only refactor is still a hash
  change and therefore a correction event.

  The pure transform helper accepts only the closed rename/replacement grammar
  and returns transformed relative-path/byte mappings plus their canonical tree
  hash; it performs no retrieval and does not inspect candidate output. During
  Task 5 preflight, apply it in a temporary copy of each pinned source, run the
  manifest's closed offline validator and the current frozen indexing entry
  point with exact options, and record the expected transformed source-tree and
  index-semantic hashes before `P7_GOLD_FREEZE_COMMIT`. A distinct label reviewer
  verifies the transform, renamed targets, and hashes. Task 6's later
  `p7-prepare-metamorphic` is only a closure-hashed filesystem/index adapter
  around this already frozen helper; it cannot choose or refresh expected
  output.

- [ ] **Step 3: Implement witness generation and validation**

  For each case:

  1. resolve all alternatives against the pinned, clean indexed source;
  2. validate every declared coherent variant and the 64-variant cap;
  3. visit complete variants only, in declared order;
  4. validate each surface's complete partition, window, excerpt, and byte
     contract;
  5. select the one lexicographically minimal feasible assignment using the
     semantic key, never declared order or IDs;
  6. serialize canonical semantic choices plus canonical public paths, ranges,
     literal hashes, partitions, byte counts, effective limits, and hashes;
     retain declared variant ID/index, unit IDs, and alternative indices only
     as full-file-hashed source backlinks excluded from the semantic witness
     hash.

  A later run validates the selected witness; it never selects a new variant.
  Ordinary terminal scoring accepts any frozen complete declared variant.
  File/span oracles alone force the witness variant.

- [ ] **Step 4: Write RED file-oracle and span-oracle tests**

  Prove that:

  - the file oracle forces only the witness path set through the existing
    result/anchor partition;
  - acquired chunks retain production order and remaining active chunks append
    at the fixed floor in `(start_line, end_line, chunk_id)` order;
  - target labels do not influence chunk order;
  - the span oracle forces witness ranges in semantic canonical
    `(partition,path,start,end,literal hashes,role)` order without widening the
    anchor contract; unit/variant IDs do not affect materialization priority;
  - both oracles reuse production visibility, projection, materialization,
    ContextPack, excerpt, and byte policies after their declared idealization;
  - oracle metadata never reaches QueryBundle, RetrievalTrace, ContextPack, or
    ExplorationTrace serialization;
  - a span-oracle failure after valid preflight is reported as a candidate
    packing/serialization defect, not invalid gold.

- [ ] **Step 5: Write RED decision-algorithm tests**

  Freeze the complete terminal-reason-to-classification table and test:

  - every non-satisfied reason maps exactly once;
  - unknown, satisfied, shadow, or non-applicable reasons cannot vote;
  - one unit vote per required executed surface and one largest-group case vote;
  - tied case groups produce `case_mixed`;
  - inclusive unit/case/repository/share/lead boundaries;
  - unique-top agreement across unit counts and case votes;
  - exact/exploratory/query/context/explore cohort minimums and contradictory
    cohort dominance;
  - Java/Python/frontend tags remaining descriptive and non-voting because
    language is confounded with repository identity in this profile;
  - the private six-case/twelve-unit/six-miss/three-case threshold and its
    one-repository waiver;
  - private contradiction changing only the owner-facing selection;
  - all-satisfied selection of `no_proven_retrieval_bottleneck`;
  - every insufficient or tied distribution selecting `mixed_inconclusive`;
  - the exact one-to-one next-phase mapping and rejected-action list;
  - invalid provenance/profile/audit inputs producing no classification.

- [ ] **Step 6: Implement the closed decision reference**

  `quality.p7_decision` is a pure consumer of validated aggregate facts. It
  accepts no callbacks into retrieval and no arbitrary weights. Keep the
  eleven legal classifications, nine miss groups, inclusive thresholds, cohort
  rules, private override, and next-phase mapping as closed constants validated
  for exhaustiveness at import/test time. No output may authorize Python AST or
  another language-specific retrieval mechanism; that requires a later
  repository-balanced design with at least two independent repositories per
  compared language.

- [ ] **Step 7: Build the deterministic mechanics profile**

  Under `tests/fixtures/p7-retrieval-quality/`, add eight minimal repositories
  representing exactly the reviewed failure shapes:

  1. large multi-chunk implementation plus entrypoint/downstream files;
  2. five exact identifiers across two project units;
  3. ambiguous common class name;
  4. rejected planner hint plus valid original-query literal;
  5. generic Python route/handler/sender without Python AST;
  6. required method in the bounded secondary file span;
  7. uncorroborated same-file traversal-only anchor;
  8. more unique exact identifiers than partition capacity.

  Use deterministic hash embeddings, no model planner, no network, and explicit
  per-case designed attrition expectations. These cases gate mechanics and are
  excluded from phase voting.

- [ ] **Step 8: Build and quota-check the fixed public profile**

  `p7_decision.json` contains exactly eighteen cases at the first freeze:

  | source identity | cases | minimum required units |
  | --- | ---: | ---: |
  | Spring PetClinic `51045d1648dad955df586150c1a1a6e22ef400c2`, with existing P5 prepared-source tree/content identity | 6 | 16 |
  | `ZhuLinsen/daily_stock_analysis@487e49e565ffd1b96a7cf4d855f99cee3c981eaa` | 6 | 16 |
  | `https://github.com/Flobby949/context-search-tool@74aae0abe3dff685282fbcc785f7a9b3532cbbe6:tests/fixtures/real_projects/program_tool`, subtree object `a8c0ace36cf82e2c743f06726944f20ce740000f` | 6 | 16 |

  Quota validation, not prose, enforces:

  - at least three source identities, eighteen cases, and forty-eight required
    units;
  - at least five Java and five Python cases, with at least twelve required
    units from each language;
  - at least six exact and six exploratory/cross-module cases;
  - at least four query, eight context, and four explore cases;
  - at least six visible predeclared paraphrase/robustness cases marked before
    candidate execution, with no hidden-holdout claim;
  - at least three frozen metamorphic companions with a deterministic query
    paraphrase and non-protected path/import rename map;
  - fixed effective result, anchor, pack, excerpt, and byte options;
  - explicit `Gate.REQUIRED`, `Gate.KNOWN_GAP`, or `Gate.INFORMATIONAL`.

  The frontend source is a public CST subtree, not a third independent external
  repository. Its manifest must record the URL, CST commit, path, exact subtree
  object, `license_status=not_declared`, and that no copy beyond the already
  tracked fixture is created. Cross-repository decision support still requires
  the two independent external sources.

- [ ] **Step 9: Author and independently review gold**

  Gold authoring must use only pinned clean source and task meaning. It may not
  inspect baseline/candidate retrieval output, policy-shadow results, oracle
  rankings, or fast-context output. A distinct read-only reviewer checks:

  ```text
  query intent
  every required/optional evidence unit
  each alternative path and canonical target
  literal containment
  identifier expected state/path/declaration state
  surface and gate tag
  paraphrase/robustness designation and explicit non-hidden status
  coherent evidence-cover variants
  metamorphic companion transform/rename map where applicable
  selected feasible-cover witness and budget proof
  ```

  Write stable author/reviewer IDs and the review result to
  `label-review.json`. Any blocker or unresolved label dispute prevents the
  freeze.

- [ ] **Step 10: Validate source and profile identity**

  Public workspaces must already exist under an explicitly supplied
  `CST_P7_PUBLIC_REPOS_DIR`. The task may copy them into isolated ignored
  worktrees, but it does not fetch or mutate the user's repositories. Verify
  exact commit/tree identity, clean status, submodule state, index/source
  identity, and normalized options before resolving targets.

  The tracked frontend source identity is exactly CST commit
  `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`, path
  `tests/fixtures/real_projects/program_tool`, and subtree object
  `a8c0ace36cf82e2c743f06726944f20ce740000f`, publicly rooted at
  `https://github.com/Flobby949/context-search-tool`. Record
  `license_status=not_declared`; do not infer a license from public access. The
  runner must resolve the object from the named commit and must not read
  untracked fixture files.

- [ ] **Step 11: Generate the source-free gold inputs**

  `gold-freeze-inputs.json` records:

  ```text
  schema_version
  label_author_id
  label_reviewer_id
  label_review_hash
  gold_freeze_utc
  behavior_baseline_commit
  source_identity_manifest_hash
  fixture_manifest_hash
  profile_config_hash
  coherent_variant_manifest_hash
  metamorphic_transform_manifest_hash
  feasibility_contract_version
  feasibility_helper_closure_hash
  feasibility_options_hash
  feasible_cover_manifest_hash
  acceptance_and_decision_contract_hash
  ```

  It deliberately does not contain `gold_freeze_commit`: that object ID does
  not exist until the commit is created. Task 6's provenance seal adds the
  commit ID and lets the closed resolver construct
  `ResolvedGoldProvenance` without a self-referential Git object. Task 5
  commands accept only `GoldFreezeInputs`; attempting to run, compare, publish,
  or decide with this pre-seal state must fail.

- [ ] **Step 12: Run gates and freeze**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_quality_cases.py \
    tests/test_p7_oracle.py \
    tests/test_p7_decision.py \
    tests/test_p7_quality_profile.py \
    tests/test_p7_file_evidence.py

  git add \
    src/context_search_tool/quality/oracle.py \
    src/context_search_tool/quality/p7_decision.py \
    tests/test_p7_oracle.py \
    tests/test_p7_decision.py \
    tests/test_p7_quality_profile.py \
    tests/fixtures/p7_retrieval_quality/p7_mechanics.json \
    tests/fixtures/p7_retrieval_quality/p7_decision.json \
    tests/fixtures/p7_retrieval_quality/p7_profile.json \
    tests/fixtures/p7_retrieval_quality/metamorphic_transforms.json \
    tests/fixtures/p7_retrieval_quality/public_source_manifest.json \
    tests/fixtures/p7-retrieval-quality \
    docs/benchmarks/p7/gold/gold-freeze-inputs.json \
    docs/benchmarks/p7/gold/feasible-cover-manifest.json \
    docs/benchmarks/p7/gold/label-review.json
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "test: freeze p7 gold and decision references"
  export P7_GOLD_FREEZE_COMMIT="$(git rev-parse HEAD)"
  ```

  Immediately recompute all tracked hashes from
  `P7_GOLD_FREEZE_COMMIT^{tree}`. A mismatch, dirty source, or unreviewed label
  invalidates the freeze. Task 6 records the new commit ID; do not amend this
  commit to insert its own SHA.

**Commit:** `test: freeze p7 gold and decision references`

### Task 6: Add The Behavior-Neutral Audit DAG And Freeze The Baseline

**Purpose:** Observe the real retrieval loss chain on baseline behavior,
separate actual output from future-policy shadow output, prove the observer is
neutral, and publish the only valid pre-activation baseline.

**Files:**

- `src/context_search_tool/retrieval_core/audit.py`
- `src/context_search_tool/quality/audit.py`
- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/context_pack/builder.py`
- `src/context_search_tool/exploration/runner.py`
- `src/context_search_tool/quality/runner.py`
- `src/context_search_tool/quality/metrics.py`
- `src/context_search_tool/quality/aggregate.py`
- `src/context_search_tool/quality/compare.py`
- `src/context_search_tool/quality/reports.py`
- `src/context_search_tool/quality/__main__.py`
- `scripts/p6_benchmark.py`
- `tests/fixtures/p6_performance/workload_manifest.json`
- `tests/test_p7_audit.py`
- `tests/test_p7_quality_runner.py`
- `tests/test_p7_quality_profile.py`
- `tests/test_p7_performance_contract.py`
- `tests/test_p6_benchmark.py`
- `tests/test_p6_case_registry.py`
- `tests/test_p6_measurement_worker.py`
- `docs/benchmarks/p7/gold/gold-provenance-seal.json`
- `docs/benchmarks/p7/gold/evaluator-closure.json`
- `docs/benchmarks/p7/baseline/public-audit.json`
- `docs/benchmarks/p7/baseline/public-projection-identity.json`

- [ ] **Step 1: Write RED observer-lifecycle tests**

  Cover unset no-op behavior, one capture scope, nested-capture rejection,
  concurrent task isolation, one unfinished ledger per retrieval, exact reset
  after success/early return/exception/cancellation, and destruction of all
  ledgers/observer references after finalization. Audit-disabled calls must
  allocate no ledger and leave the ContextVar unset after return.

- [ ] **Step 2: Add the source-free production observer seam**

  `retrieval_core.audit` may know only immutable IDs, ranks, booleans, counts,
  enums, and bounded timings. It provides:

  ```text
  capture(observer)
  current_observer()
  begin_retrieval(...)
  observe_stage(...)
  begin_deferred_stage_batch(stage_ids)
  observe_deferred_stage(batch, ...)
  commit_deferred_stage_batch(batch, selected_projection)
  abandon_deferred_stage_batch(batch)
  finish_retrieval(...)
  abandon_retrieval(...)
  ```

  Every function becomes an immediate no-op when unset. Production retrieval,
  ContextPack, and exploration may import this seam but must not import
  `quality`, case definitions, targets, or report code. Deferred batches contain
  source-free contribution IDs/ranks/counts/provenance only, are request-local
  and single-commit, and expose no leaf until a closed projection is committed.
  Task 6 exercises them with the legacy projection only; graph-fault selection
  remains dormant until Task 10.

- [ ] **Step 3: Write RED common-prefix attribution tests**

  For each alternative, assert the fourteen reviewed acquisition, expansion,
  visibility, projection, rank, and pool facts. Require complete canonical
  range coverage; a path hit or partial overlap is insufficient. Verify
  target-recovered-by-expansion provenance and separate result versus anchor
  rank spaces.

  On the behavior baseline:

  ```text
  exact_injection_mode = shadow
  exact_injection_applied = false
  file_projection_mode = shadow
  after_exact facts equal ordinary direct facts
  policy_* facts come from the frozen Task-2 helper
  actual_* facts inspect only actual legacy outputs
  ```

- [ ] **Step 4: Implement actual and shadow lanes without mutation**

  `quality.audit` joins frozen case targets to immutable ledgers. It constructs
  an isolated shadow file projection and protected-first pool with the Task-2
  helper and, when applicable, calls the frozen Task-5 reference pack/fusion
  projection. It does not call the current production builder to pretend that
  pre-P7 behavior already supports private segments/reservation. It never
  replaces, appends to, reorders, or annotates the returned production object.

  Each lane evaluates complete declared cover variants independently. A case is
  satisfied only when all required choices of one variant are satisfied. For
  attribution, select one variant by greatest terminally satisfied required
  choice count, greatest minimum reached depth, greatest depth sum, greatest
  reached-depth tuple after sorting depths descending and comparing
  lexicographically, then smallest semantic key over sorted canonical
  `(role, path, target range, literal hashes)` choices. IDs and declaration
  order are excluded from that key. That one variant supplies exactly one
  alternative and reason for every required unit. If variants tied before the
  semantic-key step have different reason-group multisets, raw diagnostics use
  the semantic-key winner but the case classification vote is `case_mixed`.
  Per-alternative facts are bounded, non-voting diagnostics only. Shadow and
  actual lanes select independently; fields never cross lanes.

  Optional units remain outside variants and independently choose their one
  bounded diagnostic alternative by greatest reached depth, then the smallest
  order/ID-independent semantic `(role,path,target range,literal hashes)` key.
  They never enter required denominators, votes, gates, or classification.

- [ ] **Step 5: Write RED per-surface DAG tests**

  Query tests cover raw selection/materialization. Context tests cover pack
  selection, final stable item selection after blocked retry, budget/policy,
  and one-excerpt target satisfaction. Explore tests cover initial versus each
  follow-up ledger, any-probe acquisition, fusion, final pack, final excerpt,
  and `satisfied_initially` versus `satisfied_by_followup`.

  Require one closed terminal reason per required unit per executed surface,
  `null` only for declared non-applicability, and ledger count exactly equal to
  actual retrieval-call count. Include a case whose independently
  furthest-reaching alternatives belong to different variants and prove they
  cannot combine into terminal satisfaction or voting metrics. Property tests
  legally permute unit declaration order and rename safe unit/variant IDs; the
  semantic winner, reason multiset, and classification must remain unchanged.
  A separate optional-unit property test reorders/renames optional units and
  alternatives and requires the same one non-voting diagnostic choice.

- [ ] **Step 6: Integrate no-signature stage hooks**

  Hook query understanding, direct lanes/merge, anchors, relations, ranking,
  cohort rerank, context expansion, legacy selection, ContextPack final
  selection/excerpts, and P4 retrieval/fusion/final pack. Use the Task-3 facts
  and Task-2 pure helpers. Do not invoke exact injection, change visibility,
  emit file candidates, reserve a protected pack item, or switch trace version.

  Direct-merge and anchor-expansion membership/provenance hooks use the dormant
  deferred-stage batch. Under baseline behavior they commit the one legacy
  projection after relation health is known, producing byte-identical leaves.
  Tests prove abandon/exception paths emit neither partial membership nor stale
  references.

  A focused test installs an observer that raises at each seam and verifies the
  error is contained by the quality run while ordinary public error behavior
  remains unchanged.

- [ ] **Step 7: Add P7 metrics and source-free reports**

  Extend quality aggregation with hits/totals plus micro/macro recall,
  identifier metrics, raw duplicate/fill metrics, canonical/effective ranks,
  actual and shadow attrition distributions, and file/span-oracle diagnostics.
  Applicable-stage `null` invalidates a report. Empty denominators alone become
  `null`.

  Public reports may use public case IDs, evidence-unit IDs, safe public
  relative paths where the schema permits them, booleans, counts, reasons,
  hashes, and normalized timing. Private reports use the stricter allowlist and
  never nest the ordinary quality report.

  Keep the existing `quality run` and `quality compare` commands compatible,
  extending them only when the selected profile/report is schema v2. Add one
  benchmark-only `quality p7-decide` command that accepts validated baseline,
  baseline-freeze/projection identity, candidate, comparison, resolved-gold
  validation, candidate audit-neutrality, performance, protected-profile,
  mechanics, robustness, private, and comparator-summary paths. Every input is
  mandatory; private and comparator use schema-valid explicit unavailable
  artifacts when absent. It performs no retrieval and writes one schema-valid
  decision JSON plus optional Markdown.

  Freeze the product-worker shim, supported-façade call orchestration, observer
  capture, leaf serializer, and a versioned product-leaf envelope containing
  only request/case opaque IDs, ranks, ranges, booleans, counts, closed enums,
  bounded timings, content-free public structure, domain-separated hashes of
  canonical public bytes, and commit/source/index handshakes. The request may
  carry the frozen query into the product process, but the response leaf binds
  it only by opaque ID/hash and never echoes query/source/snippet/content bytes.
  The shim is loaded from the verified driver closure while its
  only product import root is `<product-root>/src`; the candidate cannot replace
  it. The envelope may not contain gold alternatives, selected cover variants,
  terminal reasons, aggregate metrics, thresholds, schemas, or pass booleans
  supplied by the product. The frozen evaluator joins targets, chooses one
  coherent attribution variant per lane/surface, finalizes every reason, and
  recomputes all aggregates.

  Freeze both robustness checks here:

  - the metamorphic validator applies only the Task-5 recorded paraphrase and
    rename maps, compares coherent terminal results modulo that map, and never
    asks the product for an oracle answer;
  - the anti-special-casing scanner tokenizes all candidate production modules
    with no mutable-code exemption and rejects frozen case IDs, full query
    strings, target-path tables, and fixture/profile hashes. Its closed decoder
    checks Python string/bytes literals, JSON constants, and base64 or hex
    constants of at most 4 KiB with one decode layer; concatenated adjacent
    constants are folded once. It performs no heuristic/deobfuscation search.
    This is a deterministic sentinel, not proof against arbitrary obfuscation.
    The frozen worker shim is verified by closure hash rather than exempting
    candidate code. Scanner grammar and the exact forbidden-hash manifest are
    part of the evaluator closure.

  Add a hermetic `p7-evaluate` subcommand to `scripts/p6_benchmark.py` for the
  cross-version runs in Steps 12-13 and Task 12. Its reviewed interface is:

  ```text
  p7-evaluate
    --driver-root PATH
    --product-root PATH
    --expected-driver-commit SHA
    --expected-product-commit SHA
    --coordination-root PATH
    --expected-coordination-commit SHA
    --evidence-root PATH
    --evaluator-closure PATH
    --fixture PATH
    --profile {p7_projection,p7_mechanics,p7_decision,p7_private}
    --repos-dir PATH
    --gold-provenance-root PATH
    [--private-gold-seal PATH]
    --behavior-contract {baseline-shadow,p7-enforced}
    --audit {enabled,disabled}
    --run-id SAFE_ID
    --public-projection-output NEW_PATH
    [--audit-output NEW_PATH]
  ```

  `--private-gold-seal` is required exactly when `--profile p7_private` and its
  local seal must match the fixture/prepared identity; every other profile
  rejects the flag. `--gold-provenance-root` still binds the frozen
  evaluator/public-gold closure and never substitutes for private label
  provenance.

  The driver root must be the Git root containing the invoked script. It parses
  the frozen P7 fixture and spawns the closure-hashed Task-6 worker shim with
  `shell=False`, cwd at one prepared public repository, and an allowlisted
  environment whose only product import root is `<product-root>/src`. The shim
  handshakes the product's exact Git
  commit/tree, imported `context_search_tool.__file__`, runtime/dependency
  hash, fixture/profile/options hash, source/index identity, and audit protocol
  availability before a case runs. `audit=enabled` is legal only when the
  product has the Task-6 observer protocol; `74aae0a...` runs projection-only
  with audit disabled. The driver rejects an import from its own source tree,
  except when the verified product root is exactly the driver root. In all
  cases the imported package path must equal `<product-root>/src`; when roots
  differ, any import from `<driver-root>/src` is rejected. It also rejects a
  dirty root, mismatched handshake, reused output, source/index mutation,
  subprocess nesting by the product, or any unreviewed optional environment
  key.

  For the `context` surface the frozen shim never calls MCP or CLI because those
  append feedback beside the index. It computes the already reviewed boundary
  itself from the frozen profile and explicit `behavior-contract`, then calls
  `query_repository()` exactly once and `build_context_pack()` exactly once.
  `baseline-shadow` uses the legacy actual candidate limit while preserving the
  separate future-policy shadow projection; `p7-enforced` uses the reviewed
  omitted/explicit P7 formula. The evaluator rejects baseline commits in
  enforced mode and enforced candidate reports in baseline mode. Task 11 tests
  CLI and MCP output against this mutation-free reference call for the same
  request, while preserving their existing feedback side effects in isolated
  test indexes. No hidden “disable feedback” product flag is added.

  Add companion closed commands:

  ```text
  p7-prepare-repos     copy/validate already-pinned sources and indexes;
                       never fetch; create named byte-identical run copies
  quality p7-open-attempt
                       create one immutable candidate-attempt identity/root;
                       reject reused IDs/paths and bind every later artifact
  p7-prepare-metamorphic
                       create fresh transformed source/index copies from the
                       frozen manifest; never mutate a base run copy
  p7-prepare-private   copy one explicitly configured private source/index into
                       named isolated run copies and emit a secret local identity
  quality p7-private-gold-seal
                       validate/freeze local private labels, coherent variants,
                       feasible witness, source/index/options, thresholds, and
                       distinct author/reviewer identities before baseline
  quality p7-private-freeze
                       seal pre-candidate private fixture/profile/source/index,
                       owner-review, threshold, evaluator/gold, and sanitized
                       baseline-summary identities into ignored local evidence
  p7-protected-evaluate
                       run one frozen P0/P2/P4/P5 case/profile definition
                       against an explicit product-root worker and emit leaves
  quality p7-validate-gold
                       validate the frozen profile, feasible-cover witness,
                       source/index identities, and provenance seal
  quality p7-compare-projections
                       validate/bind closed identity-control/timing envelopes
                       and compare only the schema-defined behavioral payload
  quality p7-seal-baseline
                       bind neutrality plus full public-profile repeat proof to
                       one canonical baseline audit
  quality p7-compare   compare two schema-v2 public audit reports
  quality p7-assert-mechanics
                       gate enforced candidate mechanics from two repeat proofs;
                       baseline mechanics remain diagnostic
  quality p7-robustness
                       run frozen companions, compare coherent results modulo
                       rename maps, scan the candidate tree, and emit one summary
  quality p7-private-summary
                       emit an allowlisted paired-frozen, late-informational, or
                       explicit unavailable private-summary-v1 artifact
  p7-comparator-run    invoke configured bounded argv into an ignored raw file
                       with shell disabled, timeout, and output caps
  quality p7-comparator-summary
                       sanitize raw comparator evidence or emit explicit
                       unavailable status as comparator-summary-v1
  quality p7-protected-summary
                       validate and aggregate the exact P0-P6/JUnit inputs
  quality p7-index-tdd
                       close checkpoint 1-10 canonical/fix chains against the
                       candidate Git ancestry
  quality p7-publish-batch
                       preflight and recoverably publish the exact two-file
                       baseline or six-file final set without overwrite
  ```

  `p7-compare-projections` has exactly three mutually exclusive modes.
  `baseline-neutrality` requires the six named behavior-disabled,
  instrumentation-disabled, and instrumentation-enabled projections plus the
  prepared-repository identity and emits an ignored neutrality proof.
  `profile-repeat` requires exactly two projections, their two audit leaf
  reports, a closed profile ID, and the prepared identity; it emits a
  repeatability proof only. `candidate-neutrality` requires one audit-enabled
  projection and audit report plus one fresh audit-disabled projection for the
  same candidate/profile/input identity; it emits
  `audit-neutrality-proof-v1` only after public output, public errors, and work
  counters are byte-identical and the disabled worker reports no retained
  observer/ledger. `p7-seal-baseline` accepts exactly one neutrality
  proof, one `p7_decision` repeat proof, and the selected canonical audit and
  emits `public-projection-identity-v1`. Supplying a flag from the
  other mode, omitting one input, or using one file in two roles fails closed.

  `p7-open-attempt` accepts an explicit safe ID
  `c-<12 lowercase commit hex>-a<two positive digits>`, the exact candidate,
  freeze/evaluator/runtime/environment identities, and an absent canonical root
  under `.quality/p7-attempts/`. It atomically creates that root and one
  `acceptance-attempt-v1` identity before any candidate worktree, prepared copy,
  or output exists. It never chooses/reuses an ID. Every later candidate command
  requires that identity through common args and writes only below the same
  root.

  `p7-prepare-metamorphic` accepts only the Task-5 transform manifest, a verified
  base public-repository root, a new destination, and a new identity output. A
  transform is a closed sequence of canonical non-protected path renames and
  exact before-hash/after-hash text replacements for import/path references;
  it may not rename a protected identifier, target symbol, target literal,
  repository root, symlink, or case-only path. Each companion declares one
  closed offline validator class (`python_compile_import_graph`,
  `java_index_signal_graph`, or `frontend_static_import_graph`), expected
  transformed source-tree hash, fresh index options/hash, and resolved renamed
  gold-path map. The command creates one new source and index per companion,
  validates syntax/import resolution plus target/literal preservation, and
  rejects an existing destination, in-place rewrite, undeclared byte change,
  hash mismatch, or index reuse.

  `p7-robustness` invokes the same frozen worker shim for at least three declared
  companions under `p7-enforced`, compares each with its already validated base
  case, and requires the same complete coherent variant and terminal evidence
  after applying the exact rename map. It then applies the closed
  anti-special-casing scanner to the complete candidate production tree and
  emits `robustness-summary-v1`. Missing companion/base evidence, a transformed
  index/source drift, a scanner match, or any failed required companion makes
  the aggregate fail. `p7-assert-mechanics` similarly separates schema-valid
  baseline diagnostics from enforced candidate acceptance.

  `p7-prepare-private` accepts all three explicit private configuration values
  (fixture, repository, and owner review ID), requires a clean readable
  source/index identity, creates new isolated named copies, and writes only a
  secret local identity under `.quality/p7-private`. In frozen mode it also
  accepts the Task-6 freeze record, baseline repo identity and sanitized
  baseline summary, profile/options and threshold contract, and evaluator/gold
  identity; it validates every one before creating a candidate run copy. It
  never writes the origin, query, identifiers, paths, or source hashes into a
  public artifact and never mutates the supplied repository.

  `p7-private-summary` has exactly four local execution modes.
  `baseline-freeze` consumes one frozen-evaluator raw baseline audit and writes
  an ignored allowlisted `private-baseline-summary-v1`. `paired-frozen` consumes that
  already sealed baseline summary, its matching `private-freeze-record`, and
  one candidate raw private audit; it never accepts or reruns a baseline raw
  audit. `late-informational` consumes only a post-freeze candidate raw audit
  and is always non-voting. `unavailable` accepts only a closed absence reason
  derived from all three explicit environment-variable presence bits. The
  command builds the design's allowlist directly and runs every private
  query/identifier/path/origin/username/secret sentinel before writing a new
  output. Raw-input, fixture/repository, prepared identity, review-identity,
  and freeze-input hashes remain only under `.quality/p7-private`; they are
  validated locally but are forbidden in the final `private-summary-v1`.
  `baseline-freeze` output is never a decision input. No redaction of a general
  report is accepted.

  `p7-private-freeze` runs only in Task 6 after `baseline-freeze`. It requires
  all three of `CST_P7_PRIVATE_FIXTURE`, `CST_P7_PRIVATE_REPO`, and
  `CST_P7_PRIVATE_REVIEW_ID`; exact fixture/profile/options, prepared
  source/index, evaluator/gold, threshold-contract, sanitized baseline-summary,
  owner-review, and freeze-UTC identities; and a new ignored output. A
  configured baseline failure creates no record and blocks the baseline freeze.
  Task 12 validates current configuration and prepared-copy identity against
  this record before candidate execution. If the record exists, missing or
  drifting inputs block; if no record exists, a later complete configuration
  can produce only `late-informational` evidence.

  `p7-private-gold-seal` runs after private preparation but before the first
  private baseline product call. It resolves every private target against the
  prepared identity, validates coherent variants and a private feasible-cover
  witness with the frozen Task-5 helper, verifies that the fixture's label
  author differs from `CST_P7_PRIVATE_REVIEW_ID`, and binds exact
  profile/options/threshold/evaluator identities. It emits a local-only
  `private-gold-seal-v1` with no source/query/path bytes. Every `p7_private`
  baseline or candidate evaluation requires `--private-gold-seal`; the public
  `--gold-provenance-root` alone is insufficient.

  `p7-comparator-run` is the only owned remote-comparator wrapper. It parses the
  explicitly configured value as bounded argv, uses `shell=False`, a prepared
  public cwd, allowlisted environment, per-case timeout, response/count/byte
  caps, and a new raw output under `.quality/p7-comparator`. The frozen
  `p7-comparator-summary` parser either validates that raw envelope or, when the
  command is absent, emits the exact `unavailable/not_configured` artifact. It
  rejects raw paths/snippets/queries/commands from the summary and records only
  the non-gating safe aggregates allowed by its schema.

  Equality uses one closed envelope schema rather than ad-hoc pointer deletion.
  Each input has (a) an identity/control envelope with run ID/role/UTC,
  product commit/tree, source/index/config/environment identity,
  behavior-contract, audit mode, and audit-output presence; (b) a separate
  non-voting timing envelope; and (c) a content-free behavioral payload with
  public output/error and work counters. The command validates and binds the
  role-specific identity/control and timing envelopes, including gold-freeze
  and causal ordering, but compares only the schema-defined behavioral payload.
  It therefore neither asks unequal baseline/instrumentation identities to be
  equal nor normalizes those identities away. No result/error/counter field is
  excluded. Request, case, ledger, and leaf IDs in repeatable facts are
  deterministic functions of profile case ID, surface, and retrieval ordinal;
  random/process-local IDs are rejected.

  Every cross-worktree command takes the same explicit coordination/evidence
  arguments. `coordination-root` must be the original implementation worktree,
  have the expected HEAD, and share the exact Git common-dir with driver and
  product roots. `evidence-root` must resolve to its ignored `.quality`
  directory; every ignored output must be a new descendant of that root.
  Publication additionally requires
  `--publication-root <coordination-root>/docs/benchmarks/p7` and uses an exact
  mode-specific in-progress allowlist: Task 6 permits only its two
  `baseline/{public-audit,public-projection-identity}.json` outputs, and Task 12
  permits only its six declared `final/` outputs before the later documentation
  edit. `p7-publish-batch` has only `baseline` and `final` modes with closed
  named input flags. It validates every input, schema, privacy scan, normalized
  output hash, destination, and the whole target-root allowlist before its first
  write, stages normalized bytes in the ignored evidence root, and publishes
  each file by no-replace atomic rename. A retry after an interrupted partial
  publish accepts an existing destination only when its bytes exactly equal the
  preflighted normalized bytes, then creates only missing outputs; a differing
  existing byte is a blocker and is never overwritten. Completion writes one
  ignored batch receipt binding the entire set. It rejects every other
  target-root change. Every command records input hashes and refuses an
  unresolved/symlink escape or ambient alternative root. Tests exercise all
  commands from a different cwd to prove that no implicit `$PWD`,
  `PYTHONPATH`, or environment variable selects a product/evidence/publication
  root.

  Freeze the complete evaluator closure in
  `docs/benchmarks/p7/gold/evaluator-closure.json`. Its exact entries cover the
  driver/product-worker protocol, case and resolved-gold parsers, Task-5
  reference oracle/feasibility/decision code, audit finalization and terminal
  reason mapping, metrics/aggregation/comparison/report projection, canonical
  JSON/private scanners, every P7 artifact schema, profile fixture, and the
  frozen file-policy helper. The manifest is generated before the
  instrumentation commit, excludes itself from its digest, and is verified
  from `P7_AUDIT_INSTRUMENTATION_COMMIT^{tree}` after commit.

  The closure contains an `immutable_product_audit_protocol` submanifest for
  `retrieval_core/audit.py` and every ledger/leaf enum, envelope model, and
  validator it owns. Those candidate Git blobs must remain byte-identical to
  Task 6 in every later handshake. Retrieval/ContextPack/exploration hook call
  sites may evolve only in their planned owning tasks and are checked through
  exact decision accounting, public-output/work-counter cross-checks, and
  focused tests. A change to an immutable protocol blob, even with the same
  version string, requires a new reviewed baseline.

  Every later baseline or candidate evaluation command is launched from this
  audit-instrumentation worktree and takes
  `--evaluator-closure evaluator-closure.json`. It recomputes the closure from
  the named driver commit before reading any product facts. The candidate is
  only a `--product-root` worker: candidate-resident quality cases, aggregators,
  normalizers, compare/decision code, schemas, and pass booleans are never
  trusted. The worker-shim blob and its call/serialization projection must equal
  the closure manifest; the candidate tree has no adapter role. The frozen
  evaluator recomputes every derived field from leaf facts and cross-checks
  product protocol invariants.

  The frozen driver is also a future trace consumer. Before live v2 exists,
  synthetic tests feed it exact complete RetrievalTrace-v1 and reviewed-v2
  payloads. It must dispatch to the exact fifteen- or sixteen-stage contract
  and reject unknown versions, missing/extra stages, prefixes, and private
  field leakage. Task 9 later verifies this already-frozen consumer with live
  model fixtures but may not edit the driver.

- [ ] **Step 8: Extend the P6 harness for paired context measurement**

  Add a new `p7_retrieval_context_paired` operation set instead of reusing the
  current hard-coded `protected_small_entry_comparable` set. It contains warm
  exact query, exploratory query, and context operations; context performs one
  real retrieval plus one ContextPack build. Fix five unmeasured warmups and
  thirty measured samples per gated query/context case. It has no explore
  latency operation or sample key; explore is checked separately through its
  existing retrieval-call ceiling.

  The existing one-shot paired CLI worker is cold-process evidence and is not
  valid for these gates. Add a persistent JSON-lines measurement worker for
  each side:

  - launch the frozen Task-6 driver from the audit instrumentation root;
  - bind product imports explicitly to
    `<implementation_root>/src` for either `74aae0a...` or the candidate;
  - handshake with implementation commit/tree, imported module path,
    runtime/dependency hash, repo/index hash, operation set, and options;
  - warm both workers, then measure alternating AB/BA blocks without restart;
  - reject a worker restart, cold sample, import from the driver root, mixed
    module roots, mutable-index delta, or environment mismatch;
  - use separate read-only workspace/index copies with byte-identical initial
    hashes so one side cannot warm or mutate the other's state;
  - measure process RSS with the existing P6 unit/normalization and record each
    side's peak over the same lifecycle.

  Produce paired baseline/candidate ratios from the two sample arrays only;
  never compare candidate-resident warm data to a baseline cold subprocess.
  Also record:

  ```text
  workspace stat/read_text calls per unique expanded path
  maximum concurrently retained full source bodies
  embedding/planner request counts
  exploration retrieval-call count
  audit ledger retention after return
  ```

  Extend the paired CLI only for this named operation set with required
  `--baseline-root`, `--candidate-root`, `--baseline-repo`,
  `--candidate-repo`, `--raw-output`, and `--summary-output` arguments plus a
  `p7-prepare-paired-workspaces` command. Preparation takes the tracked
  workload manifest and a new master root, creates two non-existing
  source/index copies, and emits their byte/semantic identity; it never
  measures. The manifest's closed `master_generation` object freezes the tier
  ID, generator version and source-blob hash, seed, input-spec hash, file/byte
  shape, indexing options hash, and expected source-tree/index-semantic hashes.
  Preparation must generate the master once with the frozen Task-6 generator
  and match those hashes before copying; an existing/caller-populated master,
  alternate tier, seed, source input, or index is rejected. The paired command
  refuses legacy `--final-root`, shared `--repo`, and `--output` for the P7 set,
  validates both roots before and after measurement, and retains the old P6
  paired interface (`--baseline-root --final-root --repo --output`) and case
  matrix byte-for-byte for every old operation set while rejecting all P7-only
  flags there. Parser/help/backward-compatibility tests cover both exact,
  mutually exclusive flag sets and missing/mixed arguments.

  Extend the tracked P6 workload manifest with the versioned operation set,
  persistent-worker state, fixed cases/warmup/sample counts, paired ordering,
  prepared-index identity, and expected measurement keys. Bump its registry
  version, preserve the entire old P6 registry/case matrix as an exact named
  sub-projection, and assert the new P7 operation set independently. Update
  `test_p6_case_registry.py`; do not replace its old exact-set assertion with a
  subset or open-ended membership check. Freeze a
  source projection of the existing `tdd-red`, `tdd-green`, `tdd-bootstrap`,
  validation, and schema-selection functions and require it byte-identical
  before/after this task; P7 benchmark work must not mutate its own evidence
  producer. The manifest hash is recorded in both baseline and candidate
  performance summaries; the candidate cannot supply a different workload
  registry.

  Raw handshakes, samples, and worker logs stay in
  `.quality/p7-performance/`. The tracked performance schema stores only
  counts, normalized percentiles/ratios, identities, counters, and gates.

  No test or default command fetches a repository or makes a model request.

- [ ] **Step 9: Prove audited/non-audited identity**

  For deterministic mechanics and representative P0-P6 cases, run the same
  inputs both ways and compare:

  ```text
  QueryBundle public projection
  RetrievalTrace-v1 with only documented timing normalized
  ContextPack-v2 canonical bytes
  ExplorationTrace-v2 canonical bytes
  public errors and exit status
  store/network/work counters
  ```

  The projections must be byte-identical. Audit is allowed observer-local CPU
  and memory only; it may not trigger another retrieval, source read, planner
  request, embedding request, or store scan.

- [ ] **Step 10: Create the non-self-referential gold provenance seal**

  After verifying `P7_GOLD_FREEZE_COMMIT` is the exact Task-5 commit and an
  ancestor of the current tree, write `gold-provenance-seal.json` containing
  that commit ID and the recomputed fixture, manifest, helper, options, witness,
  threshold, and label-review hashes. Resolve the exact two-file
  `GoldFreezeInputs` + `GoldProvenanceSeal` join and record its canonical
  `ResolvedGoldProvenance` hash in every baseline artifact.

  A test checks that every hashed file exists in the named commit with the
  recorded bytes. It also proves that the current candidate cannot substitute
  its own helper, options, or witness.

- [ ] **Step 11: Run gates and commit the instrumentation**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_audit.py \
    tests/test_p7_quality_runner.py \
    tests/test_p7_quality_profile.py \
    tests/test_p7_performance_contract.py \
    tests/test_p7_oracle.py \
    tests/test_p7_decision.py \
    tests/test_p6_benchmark.py \
    tests/test_p6_case_registry.py \
    tests/test_p6_measurement_worker.py \
    tests/test_retrieval_pipeline.py \
    tests/test_context_pack.py \
    tests/test_quality_p4.py

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
    "$P7_RUNTIME" -m pytest -q -rsxX -p no:cacheprovider

  git add \
    src/context_search_tool/retrieval_core/audit.py \
    src/context_search_tool/quality/audit.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/context_pack/builder.py \
    src/context_search_tool/exploration/runner.py \
    src/context_search_tool/quality/runner.py \
    src/context_search_tool/quality/metrics.py \
    src/context_search_tool/quality/aggregate.py \
    src/context_search_tool/quality/compare.py \
    src/context_search_tool/quality/reports.py \
    src/context_search_tool/quality/__main__.py \
    scripts/p6_benchmark.py \
    tests/fixtures/p6_performance/workload_manifest.json \
    tests/test_p7_audit.py \
    tests/test_p7_quality_runner.py \
    tests/test_p7_quality_profile.py \
    tests/test_p7_performance_contract.py \
    tests/test_p6_benchmark.py \
    tests/test_p6_case_registry.py \
    tests/test_p6_measurement_worker.py \
    docs/benchmarks/p7/gold/gold-provenance-seal.json \
    docs/benchmarks/p7/gold/evaluator-closure.json
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p7 retrieval quality audit"
  export P7_AUDIT_INSTRUMENTATION_COMMIT="$(git rev-parse HEAD)"
  ```

  Verify the committed tree against the GREEN staged-tree record and rerun the
  gold seal plus evaluator-closure validators at this exact commit. Recompute
  every closure blob from
  `P7_AUDIT_INSTRUMENTATION_COMMIT^{tree}` and require its domain-separated
  digest to equal the manifest. No baseline artifact is staged in this first
  commit.

- [ ] **Step 12: Run the behavior baseline twice**

  Use:

  - a clean worktree at `74aae0a...` for public output projection;
  - a clean worktree at `P7_AUDIT_INSTRUMENTATION_COMMIT`, whose production
    behavior is still equivalent, for audit facts and shadow policy.

  Inputs, clean source copies, index identities, config, environment, and
  optional variables must match. Compare the normalized public projection of
  both trees byte-for-byte. Record:

  ```text
  behavior_baseline_commit = 74aae0a...
  audit_instrumentation_commit = P7_AUDIT_INSTRUMENTATION_COMMIT
  gold_freeze_commit = P7_GOLD_FREEZE_COMMIT
  exact_injection_applied = false
  file_projection_mode = shadow
  behavior/source/config/environment hashes
  ```

  Both IDs are now known and must be literal 40-character object IDs. No
  placeholder or "current commit" alias is permitted in the report.

  Run from the clean audit-instrumentation worktree with the Task-6 driver and
  write only to the original repository's ignored evidence root:

  ```bash
  export P7_BASELINE_ARTIFACT_ROOT="$P7_REPO_ROOT/.quality/p7-artifacts/baseline"
  export P7_BASELINE_REPO_ROOT="$P7_REPO_ROOT/.quality/p7-repos/baseline"
  export P7_DRIVER="$P7_AUDIT_WORKTREE/scripts/p6_benchmark.py"
  export P7_EVIDENCE_ROOT="$P7_REPO_ROOT/.quality"
  export P7_EVALUATOR_CLOSURE="$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold/evaluator-closure.json"
  export P7_GOLD_PROVENANCE_ROOT="$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold"
  export P7_MECHANICS_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_mechanics.json"
  export P7_DECISION_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_decision.json"
  P7_BASELINE_COMMON_ARGS=(
    --coordination-root "$P7_REPO_ROOT"
    --expected-coordination-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT"
    --evidence-root "$P7_EVIDENCE_ROOT"
    --evaluator-closure "$P7_EVALUATOR_CLOSURE"
  )
  mkdir -p "$P7_BASELINE_ARTIFACT_ROOT" "$P7_BASELINE_REPO_ROOT"
  test "$(git -C "$P7_BEHAVIOR_WORKTREE" rev-parse HEAD)" = \
    "74aae0abe3dff685282fbcc785f7a9b3532cbbe6"
  test "$(git -C "$P7_AUDIT_WORKTREE" rev-parse HEAD)" = \
    "$P7_AUDIT_INSTRUMENTATION_COMMIT"
  test -z "$(git -C "$P7_BEHAVIOR_WORKTREE" status --porcelain)"
  test -z "$(git -C "$P7_AUDIT_WORKTREE" status --porcelain)"
  test -d "$CST_P7_PUBLIC_REPOS_DIR"

  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" \
      p7-prepare-repos \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_BEHAVIOR_WORKTREE" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit \
      74aae0abe3dff685282fbcc785f7a9b3532cbbe6 \
      --source-manifest \
      "$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/public_source_manifest.json" \
      --source-repos-dir "$CST_P7_PUBLIC_REPOS_DIR" \
      --destination "$P7_BASELINE_REPO_ROOT/master" \
      --clone-destination "$P7_BASELINE_REPO_ROOT/behavior-a" \
      --clone-destination "$P7_BASELINE_REPO_ROOT/behavior-b" \
      --clone-destination "$P7_BASELINE_REPO_ROOT/instrumented-disabled-a" \
      --clone-destination "$P7_BASELINE_REPO_ROOT/instrumented-disabled-b" \
      --clone-destination "$P7_BASELINE_REPO_ROOT/instrumented-enabled-a" \
      --clone-destination "$P7_BASELINE_REPO_ROOT/instrumented-enabled-b" \
      --identity-output "$P7_BASELINE_ARTIFACT_ROOT/repos-identity.json"
  )
  ```

  `p7-prepare-repos` refuses an existing destination, verifies the pinned
  source commits/subtree hashes and compatible prepared indexes, makes no
  network call, and proves the six run copies have identical normalized
  source/index hashes. Then execute the complete eighteen-case `p7_decision`
  profile in all six fixed roles; the smaller mechanics profile is not a
  substitute for baseline neutrality:

  ```bash
  P7_BASELINE_PUBLICATION_ARGS=(
    "${P7_BASELINE_COMMON_ARGS[@]}"
    --publication-root "$P7_REPO_ROOT/docs/benchmarks/p7"
  )
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_BEHAVIOR_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit 74aae0abe3dff685282fbcc785f7a9b3532cbbe6 \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/behavior-a" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit disabled \
      --run-id behavior-a \
      --public-projection-output "$P7_BASELINE_ARTIFACT_ROOT/behavior-a.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_BEHAVIOR_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit 74aae0abe3dff685282fbcc785f7a9b3532cbbe6 \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/behavior-b" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit disabled \
      --run-id behavior-b \
      --public-projection-output "$P7_BASELINE_ARTIFACT_ROOT/behavior-b.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-disabled-a" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit disabled \
      --run-id instrumented-disabled-a \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-disabled-a.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-disabled-b" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit disabled \
      --run-id instrumented-disabled-b \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-disabled-b.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-enabled-a" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit enabled \
      --run-id instrumented-enabled-a \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-a.json" \
      --audit-output \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-a-audit.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-enabled-b" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit enabled \
      --run-id instrumented-enabled-b \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-b.json" \
      --audit-output \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-b-audit.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare-projections \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --mode baseline-neutrality \
      --behavior-disabled-a "$P7_BASELINE_ARTIFACT_ROOT/behavior-a.json" \
      --behavior-disabled-b "$P7_BASELINE_ARTIFACT_ROOT/behavior-b.json" \
      --instrumented-disabled-a \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-disabled-a.json" \
      --instrumented-disabled-b \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-disabled-b.json" \
      --instrumented-enabled-a \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-a.json" \
      --instrumented-enabled-b \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-b.json" \
      --instrumented-enabled-a-audit \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-a-audit.json" \
      --instrumented-enabled-b-audit \
      "$P7_BASELINE_ARTIFACT_ROOT/instrumented-enabled-b-audit.json" \
      --repos-identity "$P7_BASELINE_ARTIFACT_ROOT/repos-identity.json" \
      --output \
      "$P7_BASELINE_ARTIFACT_ROOT/baseline-neutrality.json"
  )
  ```

  `baseline-neutrality` requires full `p7_decision`
  behavior-disabled repeat equality, instrumentation-disabled repeat equality,
  instrumentation-enabled behavioral and audit-leaf repeat equality,
  enabled/disabled equality on the instrumentation tree, and
  behavior-versus-instrumentation-disabled equality under the closed envelope
  contract above. Audit reports exist only for enabled runs and are explicit
  proof inputs. Every differing identity/control/timing envelope is separately
  validated and bound; only the schema-defined behavioral payload is compared.
  Recheck both worktree HEAD/clean states and all six source/index hashes after
  the commands; a mismatch invalidates the run.

- [ ] **Step 13: Run mechanics, public, and available private baseline**

  Run feasibility witness validation first, then deterministic mechanics and
  the complete fixed public decision profile. If the explicitly configured
  private overlay meets its own schema, run it into `.quality/p7-private/`;
  otherwise record `unavailable` without inventing a pass.

  Do not run the candidate or external comparator. Gold/profile correction at
  this point creates a new Task-5-style freeze and repeats this baseline; it is
  never amended in place after seeing candidate output.

  Execute the frozen witness check and both public profiles explicitly:

  ```bash
  export P7_DECISION_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_decision.json"
  export P7_PROFILE_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_profile.json"
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-validate-gold \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --profile "$P7_PROFILE_FIXTURE" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --feasible-cover \
      "$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold/feasible-cover-manifest.json" \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-enabled-a" \
      --output "$P7_BASELINE_ARTIFACT_ROOT/gold-validation.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_MECHANICS_FIXTURE" --profile p7_mechanics \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-enabled-a" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit enabled \
      --run-id mechanics-baseline \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/mechanics-projection.json" \
      --audit-output "$P7_BASELINE_ARTIFACT_ROOT/mechanics-audit.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-enabled-a" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit enabled \
      --run-id public-baseline-a \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/public-a-projection.json" \
      --audit-output "$P7_BASELINE_ARTIFACT_ROOT/public-a-audit.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --fixture "$P7_DECISION_FIXTURE" --profile p7_decision \
      --repos-dir "$P7_BASELINE_REPO_ROOT/instrumented-enabled-b" \
      --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
      --behavior-contract baseline-shadow --audit enabled \
      --run-id public-baseline-b \
      --public-projection-output \
      "$P7_BASELINE_ARTIFACT_ROOT/public-b-projection.json" \
      --audit-output "$P7_BASELINE_ARTIFACT_ROOT/public-b-audit.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare-projections \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --mode profile-repeat --profile-id p7_decision \
      --run-a "$P7_BASELINE_ARTIFACT_ROOT/public-a-projection.json" \
      --run-b "$P7_BASELINE_ARTIFACT_ROOT/public-b-projection.json" \
      --audit-a "$P7_BASELINE_ARTIFACT_ROOT/public-a-audit.json" \
      --audit-b "$P7_BASELINE_ARTIFACT_ROOT/public-b-audit.json" \
      --repos-identity "$P7_BASELINE_ARTIFACT_ROOT/repos-identity.json" \
      --output "$P7_BASELINE_ARTIFACT_ROOT/public-repeat.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-seal-baseline \
      "${P7_BASELINE_COMMON_ARGS[@]}" \
      --neutrality "$P7_BASELINE_ARTIFACT_ROOT/baseline-neutrality.json" \
      --public-repeat "$P7_BASELINE_ARTIFACT_ROOT/public-repeat.json" \
      --canonical-audit "$P7_BASELINE_ARTIFACT_ROOT/public-a-audit.json" \
      --canonical-projection \
      "$P7_BASELINE_ARTIFACT_ROOT/public-a-projection.json" \
      --output \
      "$P7_BASELINE_ARTIFACT_ROOT/public-projection-identity.json"
  )
  ```

  Resolve the private overlay once, before any candidate behavior task. A
  configured overlay creates one sealed local baseline summary and one
  pre-candidate freeze record; complete absence creates only an unavailable
  local summary:

  ```bash
  export P7_PRIVATE_BASELINE_ROOT="$P7_REPO_ROOT/.quality/p7-private/baseline"
  export P7_PRIVATE_GOLD_SEAL="$P7_PRIVATE_BASELINE_ROOT/private-gold-seal.json"
  export P7_PRIVATE_FREEZE_RECORD="$P7_PRIVATE_BASELINE_ROOT/private-freeze-record.json"
  mkdir -p "$P7_PRIVATE_BASELINE_ROOT"
  if [[ -n "${CST_P7_PRIVATE_FIXTURE:-}" &&
        -n "${CST_P7_PRIVATE_REPO:-}" &&
        -n "${CST_P7_PRIVATE_REVIEW_ID:-}" ]]; then
    (
      cd "$P7_AUDIT_WORKTREE"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" \
        p7-prepare-private \
        --driver-root "$P7_AUDIT_WORKTREE" \
        --product-root "$P7_AUDIT_WORKTREE" \
        --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        "${P7_BASELINE_COMMON_ARGS[@]}" \
        --source-repo "$CST_P7_PRIVATE_REPO" \
        --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
        --private-review-id "$CST_P7_PRIVATE_REVIEW_ID" \
        --destination "$P7_PRIVATE_BASELINE_ROOT/master" \
        --clone-destination "$P7_PRIVATE_BASELINE_ROOT/baseline-repo" \
        --identity-output "$P7_PRIVATE_BASELINE_ROOT/repo-identity.json"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-private-gold-seal \
        "${P7_BASELINE_COMMON_ARGS[@]}" \
        --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
        --private-review-id "$CST_P7_PRIVATE_REVIEW_ID" \
        --profile p7_private \
        --repos-dir "$P7_PRIVATE_BASELINE_ROOT/baseline-repo" \
        --repo-identity "$P7_PRIVATE_BASELINE_ROOT/repo-identity.json" \
        --threshold-contract \
        "$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_profile.json" \
        --feasibility-helper \
        "$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold/feasible-cover-manifest.json" \
        --output "$P7_PRIVATE_GOLD_SEAL"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_DRIVER" \
        p7-evaluate \
        --driver-root "$P7_AUDIT_WORKTREE" \
        --product-root "$P7_AUDIT_WORKTREE" \
        --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        --expected-product-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        "${P7_BASELINE_COMMON_ARGS[@]}" \
        --fixture "$CST_P7_PRIVATE_FIXTURE" --profile p7_private \
        --repos-dir "$P7_PRIVATE_BASELINE_ROOT/baseline-repo" \
        --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
        --private-gold-seal "$P7_PRIVATE_GOLD_SEAL" \
        --behavior-contract baseline-shadow --audit enabled \
        --run-id private-baseline \
        --public-projection-output \
        "$P7_PRIVATE_BASELINE_ROOT/raw-projection.json" \
        --audit-output "$P7_PRIVATE_BASELINE_ROOT/raw-audit.json"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-private-summary \
        "${P7_BASELINE_COMMON_ARGS[@]}" \
        --mode baseline-freeze \
        --raw-audit "$P7_PRIVATE_BASELINE_ROOT/raw-audit.json" \
        --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
        --private-repo "$CST_P7_PRIVATE_REPO" \
        --repo-identity "$P7_PRIVATE_BASELINE_ROOT/repo-identity.json" \
        --output "$P7_PRIVATE_BASELINE_ROOT/summary.json"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-private-freeze \
        "${P7_BASELINE_COMMON_ARGS[@]}" \
        --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
        --private-repo "$CST_P7_PRIVATE_REPO" \
        --private-review-id "$CST_P7_PRIVATE_REVIEW_ID" \
        --profile p7_private \
        --repo-identity "$P7_PRIVATE_BASELINE_ROOT/repo-identity.json" \
        --private-gold-seal "$P7_PRIVATE_GOLD_SEAL" \
        --baseline-summary "$P7_PRIVATE_BASELINE_ROOT/summary.json" \
        --gold-provenance-root "$P7_GOLD_PROVENANCE_ROOT" \
        --threshold-contract \
        "$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_profile.json" \
        --output "$P7_PRIVATE_FREEZE_RECORD"
    )
  elif [[ -z "${CST_P7_PRIVATE_FIXTURE:-}" &&
          -z "${CST_P7_PRIVATE_REPO:-}" &&
          -z "${CST_P7_PRIVATE_REVIEW_ID:-}" ]]; then
    test ! -e "$P7_PRIVATE_FREEZE_RECORD"
    (
      cd "$P7_AUDIT_WORKTREE"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-private-summary \
        "${P7_BASELINE_COMMON_ARGS[@]}" \
        --mode unavailable --reason not_configured \
        --fixture-present false --repo-present false \
        --review-id-present false \
        --output "$P7_PRIVATE_BASELINE_ROOT/summary.json"
    )
  else
    echo "CST_P7_PRIVATE_FIXTURE, CST_P7_PRIVATE_REPO, and CST_P7_PRIVATE_REVIEW_ID must be all present or all absent" >&2
    exit 1
  fi
  ```

  The baseline summary is allowlisted and sentinel-scanned. Its raw projection,
  audit, prepared identity, freeze record, review identity, query, and paths
  remain ignored. The freeze record binds their hashes locally, including the
  freeze UTC and exact threshold/evaluator/gold identities; neither it nor any
  raw private-input hash is copied into a tracked artifact. A configured
  private run that fails creates no valid freeze record and cannot be rewritten
  as unavailable.

- [ ] **Step 14: Validate and commit the artifact-only baseline freeze**

  ```bash
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-publish-batch \
      "${P7_BASELINE_PUBLICATION_ARGS[@]}" \
      --mode baseline \
      --public-audit-input "$P7_BASELINE_ARTIFACT_ROOT/public-a-audit.json" \
      --projection-identity-input \
      "$P7_BASELINE_ARTIFACT_ROOT/public-projection-identity.json" \
      --receipt-output "$P7_BASELINE_ARTIFACT_ROOT/publication-receipt.json"
  )

  cd "$P7_REPO_ROOT"
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_audit.py \
    tests/test_p7_quality_runner.py \
    tests/test_p7_oracle.py \
    tests/test_p7_decision.py \
    tests/test_p7_quality_profile.py

  git add \
    docs/benchmarks/p7/baseline/public-audit.json \
    docs/benchmarks/p7/baseline/public-projection-identity.json
  git diff --cached --check
  git diff --cached --name-only
  test "$(git diff --cached --name-only | wc -l | tr -d ' ')" = "2"
  git commit -m "test: freeze p7 behavior baseline"
  export P7_BASELINE_FREEZE_COMMIT="$(git rev-parse HEAD)"
  ```

  Require `P7_GOLD_FREEZE_COMMIT`,
  `P7_AUDIT_INSTRUMENTATION_COMMIT`, and `P7_BASELINE_FREEZE_COMMIT` to be
  ancestors of every later candidate. The second commit contains no production,
  test, fixture, threshold, or gold change.

**Commits:**

1. `feat: add p7 retrieval quality audit`
2. `test: freeze p7 behavior baseline`

### Task 7: Add Dormant ContextPack Segment And Reservation Support

**Purpose:** Teach ContextPack to consume bounded same-file evidence segments
and protected-path metadata while keeping every legacy and current production
bundle byte-identical until later tasks emit that private state.

**Files:**

- `src/context_search_tool/models.py`
- `src/context_search_tool/context_pack/models.py`
- `src/context_search_tool/context_pack/roles.py`
- `src/context_search_tool/context_pack/needs.py`
- `src/context_search_tool/context_pack/excerpts.py`
- `src/context_search_tool/context_pack/builder.py`
- `tests/test_p7_context_pack.py`
- `tests/test_context_pack.py`
- `tests/test_context_excerpts.py`
- `tests/test_context_needs.py`

- [ ] **Step 1: Write RED private-model and sentinel tests**

  Add direct-construction tests for:

  ```text
  RetrievalContextSegment
  RetrievalResult._context_segments
  EvidenceAnchor._context_segments
  RetrievalResult._protected_path_order
  EvidenceAnchor._protected_path_order
  ContextCandidate._context_segments
  ContextCandidate._protected_path_order
  ```

  Require private fields to be constructor-compatible defaults, `repr=False`,
  `compare=False`, absent from public serializers, and absent from ContextPack
  JSON. Validate one-to-two non-overlapping normal segments, exactly one anchor
  segment, per-segment contained finite origin spans, and the eight-origin
  bound. Add duplicate-path matrices for an unprotected result plus protected
  anchor, protected result plus duplicate anchor, and two protected duplicates
  with different occurrence orders.

- [ ] **Step 2: Implement the exact legacy sentinel**

  `()` means a legacy/directly constructed value only:

  - synthesize one segment from public range, `_context_content or content`,
    and spans;
  - synthesize the current full-range `legacy_result` span only for a normal
    legacy result with no spans;
  - keep an anchor's current empty-span path;
  - keep all existing direct `build_context_pack(bundle, options)` behavior.

  A non-empty segment tuple is authoritative. Mixed, overlapping, partially
  populated, out-of-range, or segment/content-inconsistent state fails through
  the existing bounded ContextPack error mechanism.

- [ ] **Step 3: Normalize private transport without changing public values**

  `normalize_candidates` copies private segments and path order into
  `ContextCandidate`; its ordinary path, content, range, rank, score, sources,
  anchor metadata, and role inputs continue to reflect the first segment.
  Duplicate-path normalization retains the winning candidate under the existing
  policy and never concatenates segment text. Its merge helper independently
  retains `min(all non-null _protected_path_order)` across result and anchor
  duplicates, even when the protected duplicate loses the content/rank
  decision; every other private/public field remains winner-derived.

- [ ] **Step 4: Write RED segment-local need tests**

  Prove that:

  - `candidate_matches_need` runs unchanged matching semantics independently
    against each segment;
  - a complete need match in one segment succeeds;
  - tokens split across a gap do not create a synthetic match;
  - matching one segment does not change need derivation or public need IDs;
  - explicit role and structural need precedence are unchanged.

- [ ] **Step 5: Make excerpt construction segment-local**

  Build one source view per segment, use only that segment's origin spans, and
  merge windows only inside that segment. Then globally order the resulting
  windows by the existing window rank before applying current excerpt, item,
  total-content, cropping, and pack limits. Every emitted excerpt must be fully
  contained in one authoritative segment.

- [ ] **Step 6: Write RED protected-reservation tests**

  Cover:

  - protected order, then source order/path tie-break;
  - reservation up to `max_items`, including more protected paths than space;
  - independent behavior from existing `protected_direct`;
  - filtered coverage under each blocked-match retry iteration;
  - removal of covered required and recommended needs before ordinary greedy
    selection;
  - reserved candidates becoming ordinary `_SelectedCandidate` values and
    participating in excerpt fitting, reselection, omission, item linking, and
    byte budgets;
  - a reserved item rejected by content/byte policy re-entering the existing
    blocked/retry path rather than bypassing it;
  - exact relative order of every pair of unprotected candidates remaining
    unchanged;
  - one item per path and current stable reading/omission order.

- [ ] **Step 7: Implement reservation inside the existing retry loop**

  At each selector iteration:

  1. recompute reserved candidates against current blocked matches;
  2. create normal selected values with priority
     `(0, protected_path_order, source_order, file_path)`;
  3. remove their filtered need coverage;
  4. run the unchanged greedy suffix for remaining capacity with priority
     `(1, *existing_rank_tuple)`;
  5. execute the existing excerpt/byte fitting and blocked retry.

  Do not add another build, candidate list, greedy algorithm, role, need type,
  or public omission reason.

- [ ] **Step 8: Prove dormant public compatibility**

  Production QueryBundles still have the legacy empty tuple and no protected
  path order at this task. Compare representative P0/P2/P4 bundle-to-pack
  outputs byte-for-byte, including omission order and next queries. Direct P7
  test objects exercise new behavior without activating retrieval transport.
  For the complete bounded synthetic matrix, production builder output must
  also equal the frozen Task-5 reference projection; a mismatch is fixed here,
  never by editing the frozen reference.

- [ ] **Step 9: Run gates and commit**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_context_pack.py \
    tests/test_context_pack.py \
    tests/test_context_excerpts.py \
    tests/test_context_needs.py \
    tests/test_quality_p2.py \
    tests/test_quality_p4.py

  git add \
    src/context_search_tool/models.py \
    src/context_search_tool/context_pack/models.py \
    src/context_search_tool/context_pack/roles.py \
    src/context_search_tool/context_pack/needs.py \
    src/context_search_tool/context_pack/excerpts.py \
    src/context_search_tool/context_pack/builder.py \
    tests/test_p7_context_pack.py \
    tests/test_context_pack.py \
    tests/test_context_excerpts.py \
    tests/test_context_needs.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p7 context evidence transport"
  ```

**Commit:** `feat: add p7 context evidence transport`

### Task 8: Prepare Exact Injection Transport And P4 Protection Isolation

**Purpose:** Complete the private exact-evidence path and exploration guard so
that Task 10 can activate it atomically, without yet injecting or reserving
anything in normal production retrieval.

**Files:**

- `src/context_search_tool/models.py`
- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/retrieval_core/types.py`
- `src/context_search_tool/retrieval_core/candidates.py`
- `src/context_search_tool/retrieval_core/expansion.py`
- `src/context_search_tool/retrieval_core/ranking.py`
- `src/context_search_tool/retrieval_core/exact_intent.py`
- `src/context_search_tool/exploration/runner.py`
- `src/context_search_tool/exploration/probes.py`
- `src/context_search_tool/exploration/fusion.py`
- `tests/test_p7_exact_injection.py`
- `tests/test_p7_exploration.py`
- `tests/test_p5_protected_direct.py`
- `tests/test_exploration_runner.py`
- `tests/test_exploration_probes.py`
- `tests/test_exploration_fusion.py`
- `tests/test_quality_p4.py`

- [ ] **Step 1: Write RED canonical-injection tests**

  Exercise a private helper with Task-3 lane/fact inputs:

  - a unique structured declaration selects the covering declaration chunk;
  - otherwise original lanes use fixed precedence
    `path_symbol, signal, direct_text, lexical, semantic`;
  - lane return rank, start/end, and chunk ID break ties;
  - otherwise the first active indexed chunk for the unique path wins;
  - planner, probe, anchor, relation, and non-original inputs are rejected;
  - content-only structural state never injects;
  - ambiguous/missing/budget-omitted literals never inject;
  - several literals resolving to one path produce one candidate with the
    earliest protected occurrence order and all bounded declaration focus
    metadata;
  - injection happens before a direct-merge fixture and does not alter numeric
    score parts, cohort keys, or unrelated candidate order.
  - one batch built from ready structured-signal plus non-signal facts contains
    both a healthy projection and a signal-free fault projection; selecting the
    latter requires no helper re-entry or store/graph read;
  - an injected signal seed that creates or wins an anchor contribution is
    distinguishable from an anchor with independent baseline/non-signal seed
    lineage, including when both merge to the same candidate ID.

- [ ] **Step 2: Add private protection transport**

  Carry a distinct exact-path marker and occurrence order through candidate,
  ranked, expanded, result, and anchor private values. Do not reinterpret
  `evidence_priority == 0` or the existing `protected_direct` score part.
  Copy/replace/merge helpers must preserve the earliest exact occurrence and
  bounded declaration origins.

  The injection helper returns ordinary candidate input plus immutable audit
  facts. Path/suffix/filename/stem and active-symbol resolutions reuse the
  existing `path_symbol` candidate/source/score-part semantics; only a
  structured-signal declaration reuses `signal`. Identical declaration ranges
  inject once under active-symbol provenance precedence. The helper has no
  store, source, planner, or network access.

  Have that one helper call return an immutable request-local
  `ExactInjectionBatch` with two closed projections:

  ```text
  ready              all finally eligible exact resolutions
  graph_fault        the same facts with structured-signal proof removed and
                     path/symbol fallback recomputed in memory
  ```

  Preserve the pre-injection ordinary direct/planner inputs. Until the graph
  session finishes relation expansion, propagate private contribution lineage
  through direct merge and anchor expansion. For every affected candidate key,
  retain the independently existing baseline contribution, non-signal injected
  contribution, and signal-injected contribution separately enough to reselect
  the same merge winner after one class is revoked; do not retain source text or
  an unbounded candidate history. The existing per-stage candidate ceilings
  plus at most sixteen exact literals bound this request-local state. This
  metadata is dormant, compare/repr false, absent from serializers, and erased
  after the graph state commits.

- [ ] **Step 3: Write RED ContextVar guard tests**

  `protection_disabled()` must:

  - be non-nestable;
  - isolate concurrent tasks;
  - reset its token in `finally` after normal return, early return, exception,
    and cancellation;
  - suppress exact-resolution side data and the `lexical_top_k == 0`
    metadata-only pass;
  - leave enabled ordinary recall lanes and their existing candidates intact;
  - add no public parameter or config field.

- [ ] **Step 4: Guard every P4 follow-up retrieval**

  Initial retrieval runs normally. Wrap each actual follow-up query call in the
  guard, and defensively strip any private protection marker returned by an
  adapter/test double before fusion. Probe text, planner text, and discovered
  identifiers may still contribute through ordinary recall, never structural
  protection.

- [ ] **Step 5: Preserve initial protection through fusion**

  Ensure `replace`, `deepcopy`, trace-to-probe conversion, and path fusion keep
  initial result/anchor private markers. Extend P4's protected predicate to
  recognize the marker in addition to current behavior. Numeric scores across
  probes remain incomparable; source rank, path ceilings, goals, call limits,
  and pack-build counts remain exact.

- [ ] **Step 6: Add the legacy P4 origin accessor**

  Centralize origin loading behind:

  ```text
  selection._legacy_probe_origin_chunk_ids
  else selection.origin_chunk_ids
  ```

  Use it for every P4 loop that loads chunks, symbols, signals, relations, or
  source paths. Do not use future canonical/display origins or omitted counts
  as probe seeds. At this task direct selections use the fallback; Task 9 adds
  the private tuple.

- [ ] **Step 7: Keep activation dormant**

  `_query_repository_impl` may construct the prepared injection input but must
  not call the injection helper or emit the marker. Add a test that patches the
  helper to raise during ordinary query/trace/context/explore and proves it was
  not invoked. The audit remains:

  ```text
  exact_injection_applied = false
  file_projection_mode = shadow
  ```

- [ ] **Step 8: Prove P4 and public parity**

  Compare initial/follow-up count, probe text IDs, source rank, legacy origin
  order, fused path order, goals, stop reason, pack build count, QueryBundle,
  ContextPack, and ExplorationTrace bytes on all deterministic P4 cases.
  Ordinary follow-up work may be lower only for the forbidden exact metadata
  edge; returned public candidates remain identical because injection is still
  dormant.

- [ ] **Step 9: Run gates and commit**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_exact_injection.py \
    tests/test_p7_exploration.py \
    tests/test_p5_protected_direct.py \
    tests/test_exploration_runner.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_quality_p4.py \
    tests/test_p7_exact_acquisition.py

  git add \
    src/context_search_tool/models.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/types.py \
    src/context_search_tool/retrieval_core/candidates.py \
    src/context_search_tool/retrieval_core/expansion.py \
    src/context_search_tool/retrieval_core/ranking.py \
    src/context_search_tool/retrieval_core/exact_intent.py \
    src/context_search_tool/exploration/runner.py \
    src/context_search_tool/exploration/probes.py \
    src/context_search_tool/exploration/fusion.py \
    tests/test_p7_exact_injection.py \
    tests/test_p7_exploration.py \
    tests/test_p5_protected_direct.py \
    tests/test_exploration_runner.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_quality_p4.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: prepare p7 exact evidence activation"
  ```

**Commit:** `feat: prepare p7 exact evidence activation`

### Task 9: Group Materialization And Make RetrievalTrace V2 Consumers Ready

**Purpose:** Remove repeated same-path workspace reads, preserve a score-winner
identity through expansion, and make every trace model/consumer able to handle
v2 before the producer switches versions.

**Files:**

- `src/context_search_tool/retrieval_core/types.py`
- `src/context_search_tool/retrieval_core/context_expansion.py`
- `src/context_search_tool/retrieval_core/tracing.py`
- `src/context_search_tool/retrieval_trace/models.py`
- `src/context_search_tool/retrieval_trace/collector.py`
- `src/context_search_tool/retrieval_trace/serialization.py`
- `src/context_search_tool/retrieval_trace/__init__.py`
- `src/context_search_tool/formatters.py`
- `src/context_search_tool/exploration/probes.py`
- `tests/test_p7_context_expansion.py`
- `tests/test_p7_trace_v2.py`
- `tests/test_retrieval_pipeline.py`
- `tests/test_retrieval_trace.py`
- `tests/test_retrieval_trace_pipeline.py`
- `tests/test_formatters.py`
- `tests/test_exploration_probes.py`
- `tests/test_exploration_boundaries.py`
- `tests/test_p6_measurement_worker.py`
- `tests/test_cli_commands.py`
- `tests/test_mcp_tools.py`
- `tests/test_retrieval_core_characterization.py`
- `tests/retrieval_core_characterization.py`

- [ ] **Step 1: Write RED grouped-I/O tests**

  With interleaved ranked inputs from repeated paths, assert:

  - grouping in each path's first-position order;
  - at most one `stat` and one `read_text` per unique expanded path;
  - one full source body resident at a time;
  - output restored to original input positions before overlap merge;
  - exact existing ranges/content/order for readable, full-file, oversized,
    empty, and missing paths;
  - `stat` success plus `read_text` failure creates one small unreadable
    sentinel;
  - each unreadable origin falls back to its own indexed content/range;
  - no dictionary of all full source bodies remains after return.

- [ ] **Step 2: Implement path-grouped materialization**

  Record original zero-based positions, materialize every origin for one path
  from one observation, release the body, place bounded values back into their
  original slots, then run the existing overlap merge. Do not move file
  projection or selection before materialization.

- [ ] **Step 3: Add and verify `winner_chunk_id`**

  A single expanded candidate initializes it to its own chunk ID. An overlap
  merge copies it from the same `_expanded_result_sort_key` winner that supplies
  rerank score, parts, reasons, and adjustments. Require it in the merged
  origin set. Accumulated origin order must never substitute for this winner.

- [ ] **Step 4: Write RED v1/v2 model-validation tests**

  Preserve frozen v1 fixtures byte-for-byte. Add direct v2 values covering:

  - schema version exactly 2;
  - sixteen closed ordered stages with `file_projection` after expansion;
  - the seven closed file-projection decisions;
  - decision counts summing to input and the composite output equation;
  - `output_count == ordering_and_display + ordering_only +
    evidence_anchor_passthrough`, including duplicate anchor passthroughs;
  - file-projection `top_candidates == ()`;
  - five-stage rank history;
  - contiguous global ranks with result and anchor subsequences preserved;
  - `ordering_chunk_id`, display origins, and omitted count invariants;
  - positive omitted count requiring complete private canonical provenance;
  - private canonical and legacy P4 origins absent from serialization;
  - twenty selection, twenty-four adjustment, preview, timing, source, and
    privacy bounds unchanged.

- [ ] **Step 5: Implement version-branching trace models and serialization**

  Consumers branch on `schema_version`; no request emits both shapes. V1
  validation/serialization remains immutable. V2 adds only the reviewed stage
  and selection provenance fields. Do not loosen enums or accept unknown
  versions for forward compatibility.

- [ ] **Step 6: Prepare v2 collector and tracing helpers**

  Add dormant helpers for:

  - file-projection stage decisions/counts with no preview;
  - global interleaved projection ranks;
  - two-way selected-head final rank merge;
  - complete stable provenance, winner-first public eight-origin disclosure,
    display-origin intersection, and exact omitted count;
  - sources/variants/reasons bounded over disclosed origins only;
  - `_legacy_probe_origin_chunk_ids` from the pre-P7 accumulated origins of the
    selected ordering expanded item.
  - one request-local graph-batch trace buffer for `direct_merge` and
    `anchor_expansion`: it records timing/work immediately but commits their
    candidate counts/provenance only after `relation_expansion` declares the
    graph state healthy or faulted. A fault selects the Task-8 signal-free
    contribution projection; no public trace contains an abandoned provisional
    injection.

  The production retrieval orchestration still asks the collector for v1 in
  this task and never emits `file_projection`. With injection dormant, the
  buffer commits exactly the old v1 stage payload and bytes.

- [ ] **Step 7: Update all trace consumers before producer activation**

  Update formatters, quality projection, P4 probe conversion, and package
  exports to handle either exact schema. P4 must use only the Task-8 legacy
  accessor, never canonical/display origins. Add a fixture where the score
  winner differs from the first accumulated origin to prove v2 correctness and
  v1 probe compatibility simultaneously.

  Make the characterization recorder schema-version-aware before producer
  activation: retain the exact fifteen-stage v1 path, add a dedicated composite
  file-projection recorder for v2, and never project a file candidate through
  the old `_ExpandedResult` shape. Keep the old baseline/migration fixtures
  byte-identical.

  Remove hidden v1-only assumptions from the live CLI, MCP, lazy-import
  boundary, and P6 attribution tests before activation. Each becomes a closed
  two-entry dispatch:

  ```text
  schema/stage shape 1 -> exact frozen fifteen-stage order
  schema/stage shape 2 -> exact reviewed sixteen-stage order
  anything else       -> fail
  ```

  CLI/MCP/lazy-boundary tests dispatch from the serialized schema version and
  still validate the exact response keys, privacy, one-pass behavior, and
  absence of eager exploration imports. The P6 worker attribution does not
  serialize a schema version, so its test accepts only one of the two complete
  exact stage tuples; it does not accept a prefix, arbitrary list, or unknown
  stage. Task-10 P7 pipeline/trace tests independently require that every live
  producer is v2, so this compatibility dispatch cannot hide a failed
  activation. Do not change the P6 measurement producer or artifact shape.
  The CLI help text continues to describe the currently emitted v1 producer in
  this neutral task; Task 10 changes that public sentence in the same atomic
  commit that activates v2.

  Add one cross-root integration test that constructs and serializes
  RetrievalTrace-v2 with the live Task-9 models, then passes those bytes through
  the Task-6 frozen driver's trace-consumer entry point at
  `P7_AUDIT_INSTRUMENTATION_COMMIT`. Require exact v2 acceptance and derived
  leaf projection, then reject an extra/missing/reordered stage and unknown
  version. Verify the driver and evaluator-closure blob hashes before and after;
  Task 9 may test but may not edit either frozen file.

- [ ] **Step 8: Prove public projection neutrality**

  Current producer output remains RetrievalTrace v1. Grouped materialization
  must preserve QueryBundle, trace-v1, ContextPack, and P4 projections while
  lowering only repeated source-read counts allowed by the frozen P7 migration
  ledger. Audit-enabled and disabled output identity remains exact.

- [ ] **Step 9: Run gates and commit**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_context_expansion.py \
    tests/test_p7_trace_v2.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_formatters.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_boundaries.py \
    tests/test_p6_measurement_worker.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_p7_audit.py

  git add \
    src/context_search_tool/retrieval_core/types.py \
    src/context_search_tool/retrieval_core/context_expansion.py \
    src/context_search_tool/retrieval_core/tracing.py \
    src/context_search_tool/retrieval_trace/models.py \
    src/context_search_tool/retrieval_trace/collector.py \
    src/context_search_tool/retrieval_trace/serialization.py \
    src/context_search_tool/retrieval_trace/__init__.py \
    src/context_search_tool/formatters.py \
    src/context_search_tool/exploration/probes.py \
    tests/test_p7_context_expansion.py \
    tests/test_p7_trace_v2.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_formatters.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_boundaries.py \
    tests/test_p6_measurement_worker.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_retrieval_core_characterization.py \
    tests/retrieval_core_characterization.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p7 materialization provenance"
  ```

**Commit:** `feat: add p7 materialization provenance`

### Task 10: Atomically Activate Exact Evidence, File Projection, Pack Transport, And Trace V2

**Purpose:** Make the common retrieval behavior migration: enforce the
already-frozen exact and file policy, emit one result per normal path, begin
supplying the private ContextPack segment/protection metadata prepared in Task
7, and switch the retrieval trace producer to v2 in one indivisible commit.

**Files:**

- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/cli.py`
- `src/context_search_tool/models.py`
- `src/context_search_tool/retrieval_core/types.py`
- `src/context_search_tool/retrieval_core/ranking.py`
- `src/context_search_tool/retrieval_core/context_expansion.py`
- `src/context_search_tool/retrieval_core/selection.py`
- `src/context_search_tool/retrieval_core/tracing.py`
- `src/context_search_tool/retrieval_trace/collector.py`
- `tests/test_p7_pipeline.py`
- `tests/test_p7_file_evidence.py`
- `tests/test_p7_exact_injection.py`
- `tests/test_p7_trace_v2.py`
- `tests/test_p7_context_pack.py`
- `tests/test_p7_exploration.py`
- `tests/test_retrieval_pipeline.py`
- `tests/test_retrieval_core_characterization.py`
- `tests/test_retrieval_core_boundaries.py`
- `tests/retrieval_core_characterization.py`
- `tests/fixtures/retrieval_core_decomposition/p7_expected.json`
- `tests/fixtures/retrieval_core_decomposition/p7_allowed_migration.json`
  (read-only closed contract)
- `tests/fixtures/retrieval_core_decomposition/baseline.json`
  (read-only protected fixture)
- `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`
  (read-only protected fixture)
- `tests/test_retrieval_trace.py`
- `tests/test_retrieval_trace_pipeline.py`
- `tests/test_p5_protected_direct.py`
- `tests/test_quality_p4.py`
- `tests/test_p7_audit.py`
- `tests/test_cli_commands.py`

- [ ] **Step 1: Write the atomic RED pipeline matrix**

  Before changing production orchestration, add end-to-end cases for:

  - unique exact path with a unique declaration window;
  - unique path with ambiguous/missing declaration and canonical lane fallback;
  - path and symbol literals in one clause versus independent clauses;
  - ambiguous, missing, budget-omitted, planner-only, and content-only literals;
  - enabled path/symbol/signal lanes and both zero/nonzero lexical limits;
  - one file with multiple ranked chunks, two disjoint useful spans, and a
    transitive bridge;
  - traversal-only same-file anchor filtered until independent evidence exists;
  - normal and anchor protection overflow in separate partitions;
  - anchor duplicates retained through projection and deduplicated only by
    final selection;
  - duplicate protected anchors consuming one unique-path protection/capacity
    slot while retaining complete duplicate trace accounting;
  - result fill after same-path consolidation;
  - interleaved result/anchor trace ordering and more than eight origins.
  - a structured signal that is initially ready/unique followed by a dangling
    relation or integrity failure that sets the existing graph-session fault:
    the signal-origin exact injection, exact marker, and its protection must be
    revoked, while an independently acquired active path/symbol fallback
    remains eligible and the public graph-fault fallback stays byte-compatible;
    include one case where the provisional injected signal creates an anchor
    and one where it temporarily wins a merged anchor also supported by an
    ordinary seed, proving lineage rollback and winner reselection. Inspect both
    the final public trace and the Task-6-frozen evaluator's accepted audit:
    neither may contain an abandoned contribution ID/rank/provenance/protection,
    both must agree on final membership/winner, and the audit must contain only
    the fault state plus exact revocation count/lineage consistency.

  RED assertions must fail on public membership/provenance/invariant behavior,
  not merely because the trace version is still one.

- [ ] **Step 2: Activate canonical exact injection before direct merge**

  After collecting all original-query lane facts and structured declarations,
  call the Task-8 helper once for all resolutions. Add at most one canonical
  candidate per uniquely resolved path, carrying its earliest occurrence order
  and bounded protected declaration origins, before the existing direct merge.

  Do not:

  - compare cross-lane numeric scores;
  - change any score part, evidence priority, rerank key, or cohort policy;
  - admit planner/anchor/relation/probe candidates into fallback selection;
  - run another path/symbol/signal pass;
  - inject for non-unique or content-only structural states.

  Do not commit `exact_injection_applied` merely because the ready projection
  entered a provisional direct merge. Derive and emit it only after graph health
  selects the final batch projection.

  Exact resolution remains conditional on the final health of the same graph
  session. Call the Task-8 batch helper exactly once. Use its `ready` projection
  provisionally before direct merge. If relation expansion activates the
  existing graph-fault fallback, select the already-computed `graph_fault`
  projection and rebuild the effective direct/anchor merge from the retained
  contribution lineage:

  - restore the existing pre-injection non-signal direct fallback;
  - preserve ordinary baseline anchor contributions, including the legacy
    behavior of an independently produced ordinary signal anchor;
  - retain non-signal exact contributions;
  - remove signal-exact candidates and every anchor/merge winner whose only
    added lineage came from them;
  - discard relation candidates under the existing fault rule.

  Reselect any merged winner from its surviving contribution snapshots, then
  commit the buffered direct/anchor trace stages and the Task-6 dormant
  deferred audit-stage batch together with final surviving counts/provenance.
  The abandoned provisional batch is absent from public trace membership and
  candidate audit; source-free audit records only the graph state and the
  number of signal-exact contributions revoked. Derive the
  final `exact_injection_applied` marker and protected occurrence order from the
  selected projection: in `ready`, it is true when any non-signal or
  structured-signal exact candidate survives into direct merge; in
  `graph_fault`, all structured-signal exact contributions are revoked, so it
  is true only when a non-signal exact candidate remains. Otherwise it is
  false. The state transition performs no helper re-entry, second
  store/graph/source read, or second anchor expansion.

- [ ] **Step 3: Enforce derived traversal visibility**

  Recompute display visibility from the complete candidate evidence at merge
  boundaries. A same-file traversal carrier with no independent display
  evidence remains available for relation traversal but cannot enter the
  visible normal-file population. Later independent evidence makes it visible;
  visibility is derived, not a sticky OR flag.

- [ ] **Step 4: Project the complete file evidence population**

  Immediately after context expansion, call the frozen Task-2 helper over all
  expanded inputs:

  - every anchor is a passthrough input, including duplicates;
  - every visible normal path produces exactly one file candidate;
  - first canonical expanded input defines ordering and inherited score data;
  - exact declaration windows, ordering window, and remaining origins are
    visited in reviewed priority;
  - at most two bounded/coalesced normal segments and one anchor segment are
    retained;
  - transitive coalescing is all-or-nothing;
  - first display segment supplies public raw range/content;
  - all retained segments and protection order travel only through private
    fields;
  - no result or anchor capacity is accepted by projection.

  Do not edit the frozen Task-2 policy helper in this task. If its enforced
  behavior differs from the same helper's shadow projection, stop and diagnose
  the activation wiring. Fix Task 10 and rerun under the same frozen gold; do
  not patch around the helper or absorb a candidate defect into gold. Only
  independently proven source/label/witness error may use the separate reviewed
  gold-correction flow, which creates a new freeze and reruns both baseline and
  candidate.

- [ ] **Step 5: Make final selection the sole capacity owner**

  Replace chunk-level result limiting with independent file/anchor partition
  selection:

  1. reserve protected normal paths in occurrence order up to
     `final_top_k`;
  2. fill remaining normal slots by canonical file order;
  3. apply the existing first-canonical `(anchor_kind, path)` duplicate rule to
     the complete anchor passthrough stream, recording every removed input as
     `duplicate_anchor`; protection is path metadata applied before this step,
     so the retained canonical representative keeps the earliest occurrence
     without taking content/score from a later duplicate;
  4. reserve the remaining protected anchors in occurrence order up to
     `evidence_anchor_top_k(final_top_k)`;
  5. fill remaining anchor slots by
     canonical anchor order.

  Record canonical and effective ranks and one closed omission reason in the
  audit. Duplicate anchors never consume capacity and every input is still
  accounted for by final-selection trace decisions. `file_projection` emits
  the complete population; no earlier hidden cutoff, over-fetch pool, or
  post-hoc normalization may redefine the eligible denominator.

- [ ] **Step 6: Materialize one public item per selected path**

  Construct `RetrievalResult` and `EvidenceAnchor` from selected file values.
  Public result range/content/spans use segment one; private segments contain
  the authoritative one-to-two windows. Preserve source, project unit, score,
  reason, variant, adjustment, and private context conventions within the
  reviewed winner/display split.

  Raw `QueryBundle.results` must already be unique. Existing
  `normalize_results` may remain a defensive public compatibility layer, but
  P7 metrics inspect the pre-normalization output and must observe zero
  duplicate slots plus full eligible fill.

  This is the deliberate activation point for Task-7's previously dormant
  builder support: a direct caller that builds a ContextPack from this
  P7-produced QueryBundle may now receive protected reservation and a secondary
  excerpt. Task 11 widens only omitted-budget context retrieval; it is not
  allowed to repair or complete this private transport.

- [ ] **Step 7: Switch the trace producer to v2**

  Emit the sixteen-stage order with `file_projection`, its complete decision
  accounting, empty preview, global stage output rank, and v2 selected
  provenance. Use the score winner for `ordering_chunk_id`, winner-first
  canonical origins, disclosed display-origin intersection, exact omitted
  count, and the two-way selected-head global final rank.

  Results and anchors retain their own QueryBundle subsequence order. P4
  receives only `_legacy_probe_origin_chunk_ids`.

  In this same commit, change the CLI trace help/docstring from its v1-only
  claim to the exact v2 producer contract and lock the rendered help text.
  Task-9 CLI/MCP consumer tests still use closed v1/v2 dispatch; the P7
  activation tests require live CLI and MCP trace outputs to be v2.

- [ ] **Step 8: Switch the audit from shadow to enforced**

  Candidate ledgers record:

  ```text
  exact_injection_mode = enforced
  exact_injection_applied = true only when a surviving candidate was injected
  file_projection_mode = enforced
  policy_shadow_terminal_reason = null
  ```

  All actual visibility, retention, rank, pool, raw, pack, and terminal facts
  now follow the enforced common prefix. No baseline shadow result is used in a
  regression or decision vote.
  Requests with no eligible/unique exact literal, or a signal-only injection
  revoked by graph fault, remain `mode=enforced, applied=false`; this is normal
  evidence, not a shadow fallback.

- [ ] **Step 9: Run structural invariant gates**

  Require:

  ```text
  unique_path_ratio == 1.0
  raw_duplicate_slot_count == 0
  result_fill_ratio == 1.0 on deterministic capacity cases
  one file_projection decision per expanded input
  one normal output per visible canonical path
  all anchor inputs passed to final selection
  protected survival when its partition has capacity
  no planner-only or ambiguous reservation
  deterministic output across two clean executions
  exact connection/scan work contract unchanged
  ```

  Extend the existing full-stage characterization rather than merely changing
  its expected stage count:

  - record the v2 `file_projection` live composite output/decisions with its own
    projection;
  - instrument every new store outcome seam under the corresponding existing
    operation identity;
  - keep
    `retrieval_core_decomposition/{baseline,migration_ledger}.json`
    byte-identical;
  - validate the complete old-to-P7 normalized diff against
    `p7_allowed_migration.json`;
  - write a versioned exact `p7_expected.json` for the reviewed deterministic
    cases and reject generic ignored keys/wildcards;
  - hash-protect the numeric scoring/rerank helper source/AST projection and
    every score-part key, weight, and bonus; where the candidate normalization
    domain/max is unchanged, compare ordering-chunk numeric scores/parts
    exactly to the old baseline; where exact injection changes that domain,
    allow only a mechanically recomputed normalization delta attributable to
    the injected population, with no new key, weight, bonus, or formula;
  - bind the candidate characterization to the staged tree instead of
    weakening the old protected-baseline identity guard.

- [ ] **Step 10: Run protected and full gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_pipeline.py \
    tests/test_p7_file_evidence.py \
    tests/test_p7_exact_injection.py \
    tests/test_p7_trace_v2.py \
    tests/test_p7_context_pack.py \
    tests/test_p7_exploration.py \
    tests/test_p7_audit.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_p5_protected_direct.py \
    tests/test_quality_p4.py \
    tests/test_cli_commands.py

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
    "$P7_RUNTIME" -m pytest -q -rsxX -p no:cacheprovider
  ```

  The full suite must have no failures/errors/xfails and the exact audited skip
  identity unless a separately reviewed environment record explains an
  optional skip. Do not commit a partial activation that relies on Task 11 to
  make query/trace tests pass.

- [ ] **Step 11: Commit as one activation unit**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/models.py \
    src/context_search_tool/retrieval_core/types.py \
    src/context_search_tool/retrieval_core/ranking.py \
    src/context_search_tool/retrieval_core/context_expansion.py \
    src/context_search_tool/retrieval_core/selection.py \
    src/context_search_tool/retrieval_core/tracing.py \
    src/context_search_tool/retrieval_trace/collector.py \
    tests/test_p7_pipeline.py \
    tests/test_p7_file_evidence.py \
    tests/test_p7_exact_injection.py \
    tests/test_p7_trace_v2.py \
    tests/test_p7_context_pack.py \
    tests/test_p7_exploration.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/retrieval_core_characterization.py \
    tests/fixtures/retrieval_core_decomposition/p7_expected.json \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_p5_protected_direct.py \
    tests/test_quality_p4.py \
    tests/test_p7_audit.py \
    tests/test_cli_commands.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: activate p7 file evidence selection"
  ```

  If a post-commit protected gate reveals an activation defect, revert this
  whole focused commit or fix it with a new test-first commit before Task 11.
  Never leave exact injection, projection, selection, and trace-version
  activation at different commits or behind an undocumented local flag.

**Commit:** `feat: activate p7 file evidence selection`

### Task 11: Activate The Omitted-Budget Context Boundary And Verify Integration

**Purpose:** Give omitted-budget context requests one honest wider QueryBundle,
then complete CLI, MCP, feedback, frozen-worker, and audit surface verification
without widening explicit caller budgets or changing P4 production code.

**Files:**

- `src/context_search_tool/context_pack/surface.py`
- `src/context_search_tool/context_pack/__init__.py`
- `src/context_search_tool/cli.py`
- `src/context_search_tool/mcp_tools.py`
- `tests/test_p7_surfaces.py`
- `tests/test_cli_commands.py`
- `tests/test_mcp_tools.py`
- `tests/test_p7_quality_runner.py`

- [ ] **Step 1: Write RED shared-boundary tests**

  Freeze this exact non-circular order:

  1. validate request values;
  2. compute
     `requested_max_items = min(config.context.max_items,
     explicit_max_items or config.context.max_items)` without the old
     result/anchor cap;
  3. keep an explicit positive `final_top_k` exact, otherwise compute
     `max(config.retrieval.final_top_k, min(64, 4 * requested_max_items))`;
  4. create one request-local config copy;
  5. derive anchor capacity from that selected limit;
  6. resolve ContextPack options once against that same config.

  Cover omitted, null, explicit equal-to-default, explicit smaller/larger,
  configured `final_top_k > 64`, small/large/invalid `max_items`, and invalid
  `final_top_k`. Invalid requests perform zero retrievals and zero builds.

- [ ] **Step 2: Implement one shared pure surface resolver**

  `context_pack.surface` returns the request-local config, resolved options,
  requested/effective values, and anchor capacity. It performs no retrieval or
  build. CLI and MCP call it. The frozen Task-6 shim independently applies its
  closure-frozen reference boundary and calls `query_repository` plus
  `build_context_pack`; it does not import this resolver. Task-11 parity tests
  require both paths to produce the same request-local config/options and public
  output. No product surface maintains a formula copy.

  Do not add `final_top_k` to the CLI context command, QueryBundle,
  ContextPackOptions, or `build_context_pack`.

- [ ] **Step 3: Wire CLI context**

  CLI context is always the omitted-`final_top_k` branch. It performs exactly
  one retrieval using the request-local config and exactly one
  `build_context_pack` with the already-resolved options. Existing output,
  validation error, exit code, and feedback envelope shapes remain unchanged.

- [ ] **Step 4: Wire MCP context**

  Preserve the semantic distinction:

  ```text
  final_top_k = null     -> omitted formula
  final_top_k = positive -> authoritative exact candidate limit
  ```

  Use one request-local config for retrieval and option resolution. Keep
  request/response schema, tool name, error envelope, feedback fields, and
  direct query/trace tool behavior unchanged.

- [ ] **Step 5: Verify the frozen product-worker shim**

  The unchanged Task-6 worker shim applies its closure-frozen boundary to
  explicit request values and calls `query_repository` plus
  `build_context_pack` exactly once each. Candidate CLI/MCP internals use the
  shared product resolver and one retrieval/build pair; parity tests compare
  their config/options/public output with the shim while using isolated indexes
  for existing feedback side effects. The shim serializes only the
  closed Task-6 raw protocol: request/effective limits, immutable ledger
  IDs/counts, selected IDs/ranks, raw pack/excerpt IDs/ranges/structure, work
  counters, and public product hashes. Target-relative “survival” is not a
  product leaf; the frozen evaluator derives it after joining gold.

  Recompute the Task-6 evaluator closure and require the worker shim,
  call-orchestration, leaf serializer, coherent-variant selection, terminal
  mapping, metrics, and reports to be blob-identical. Candidate
  `quality/runner.py` is untouched. Any closure/protocol change requires a new
  reviewed baseline rather than a Task-11 fix. No audit or oracle path may call
  retrieval a second time.

- [ ] **Step 6: Verify the already-complete P4 activation**

  Tasks 8-10 must already guarantee:

  - initial exact protection survives trace conversion, replacement, deep copy,
    path fusion, and final ContextPack normalization;
  - every follow-up runs under the non-nestable guard and returns no marker;
  - every origin-dependent loop uses the legacy tuple;
  - probe-local source rank remains the trace's global final rank;
  - numeric scores across queries are never compared;
  - initial/follow-up/fusion path ceilings, goals, stop rules, call count, and
    one-build-per-accepted-candidate rules remain exact; the executed call count
    remains bounded by those rules but may fall/rise within the existing ceiling
    only as a consequence of changed P7 evidence satisfying or exposing frozen
    goals;
  - ExplorationTrace remains schema version 2 with no new public fields.

  This step is verification-only. If any invariant fails, fix the owning Task
  8, 9, or 10 contract with a new test-first commit before proceeding. Do not
  modify exploration production code in this context-boundary commit.

- [ ] **Step 7: Emit context/explore leaf audit facts**

  Through the frozen shim, candidate context emits exactly one enforced
  retrieval ledger plus raw IDs/ranks/ranges for the final stable builder
  selection after blocked retry. Explore emits exactly the actual P4 retrieval
  count plus raw initial, follow-up, fused, final-pack, and final-excerpt
  identities/ranges. Audit-disabled calls retain no ledger or marker side state.
  Only the frozen Task-6 evaluator may join these leaves to targets, derive
  survival, finalize reasons, aggregate metrics, or serialize the accepted
  audit report.

- [ ] **Step 8: Run real P4 compatibility before acceptance**

  Run the pinned deterministic P4 profile and, when the prepared clean
  PetClinic checkout is explicitly available, its existing real acceptance
  profile. Compare call ceiling, origins, goals, fused paths, pack bytes, stop
  decisions, and trace public projection to the reviewed allowed migration.
  Every per-case call-count delta must be mechanically attributable to changed
  initial/follow-up evidence under the unchanged stop rules; no new call site,
  round, probe source, or hidden oracle retrieval is accepted.

- [ ] **Step 9: Run surface and protected gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_surfaces.py \
    tests/test_p7_exploration.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_exploration_runner.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_quality_p4.py \
    tests/test_p7_quality_runner.py \
    tests/test_p7_context_pack.py \
    tests/test_p7_pipeline.py

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
    "$P7_RUNTIME" -m pytest -q -rsxX -p no:cacheprovider
  ```

- [ ] **Step 10: Commit the context-default activation**

  ```bash
  git add \
    src/context_search_tool/context_pack/surface.py \
    src/context_search_tool/context_pack/__init__.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/mcp_tools.py \
    tests/test_p7_surfaces.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_p7_quality_runner.py
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: activate p7 context evidence boundary"
  export P7_CANDIDATE_COMMIT="$(git rev-parse HEAD)"
  ```

  The only newly wider retrieval is an omitted-budget context request. Query,
  trace, explicit-budget context, and explore keep their declared limits.

**Commit:** `feat: activate p7 context evidence boundary`

### Task 12: Run Acceptance, Publish The Decision, And Update Documentation

**Purpose:** Prove the candidate against frozen gold and protected history,
select the next engineering phase through the closed decision algorithm, and
publish only privacy-safe reproducible evidence.

**Files:**

- `docs/benchmarks/p7/final/public-audit.json`
- `docs/benchmarks/p7/final/public-comparison.json`
- `docs/benchmarks/p7/final/performance-summary.json`
- `docs/benchmarks/p7/final/robustness-summary.json`
- `docs/benchmarks/p7/final/p7-decision.json`
- `docs/benchmarks/p7/final/p7-decision.md`
- `docs/benchmarks/p7/README.md`
- `README.md`
- `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
- `docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md`

- [ ] **Step 1: Seal candidate and environment identity**

  Require a clean tree at `P7_CANDIDATE_COMMIT`, and verify:

  ```text
  behavior baseline = 74aae0a...
  P7_REVIEW_COMMIT is an ancestor
  P7_GOLD_FREEZE_COMMIT is an ancestor
  P7_AUDIT_INSTRUMENTATION_COMMIT is an ancestor
  P7_BASELINE_FREEZE_COMMIT is an ancestor
  P7_CANDIDATE_COMMIT is the Task-11/final fix commit
  gold provenance seal resolves every frozen blob from the gold commit
  public source commits/subtree hashes and indexes are exact and clean
  runtime/dependency/config identity matches the paired baseline
  optional external variables are recorded by presence, never copied raw
  acceptance-attempt identity is new, immutable, and commit-matched
  ```

  Acceptance never runs from dirty local source. Use isolated worktrees and
  prepared source copies; do not point the runner at either user's development
  worktree from the original comparison.

  Prepare three isolated, identical public source/index copies before any
  candidate run. First execute the attempt-scoped candidate worktree block in
  `Isolated Worktree Setup And Validation`; then rehydrate only these
  attempt-local roots:

  ```bash
  test -n "${P7_ATTEMPT_ID:-}"
  export P7_ATTEMPT_ROOT="$P7_REPO_ROOT/.quality/p7-attempts/$P7_ATTEMPT_ID"
  export P7_ATTEMPT_IDENTITY="$P7_ATTEMPT_ROOT/attempt-identity.json"
  test -f "$P7_ATTEMPT_IDENTITY"
  export P7_CANDIDATE_ARTIFACT_ROOT="$P7_ATTEMPT_ROOT/artifacts"
  export P7_CANDIDATE_REPO_ROOT="$P7_ATTEMPT_ROOT/repos"
  export P7_FROZEN_EVALUATOR_ROOT="$P7_AUDIT_WORKTREE"
  export P7_FROZEN_DRIVER="$P7_AUDIT_WORKTREE/scripts/p6_benchmark.py"
  export P7_CANDIDATE_GOLD_ROOT="$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold"
  export P7_EVALUATOR_CLOSURE="$P7_CANDIDATE_GOLD_ROOT/evaluator-closure.json"
  export P7_EVIDENCE_ROOT="$P7_REPO_ROOT/.quality"
  P7_CANDIDATE_COMMON_ARGS=(
    --coordination-root "$P7_REPO_ROOT"
    --expected-coordination-commit "$P7_CANDIDATE_COMMIT"
    --evidence-root "$P7_EVIDENCE_ROOT"
    --evaluator-closure "$P7_EVALUATOR_CLOSURE"
    --attempt-identity "$P7_ATTEMPT_IDENTITY"
  )
  mkdir -p "$P7_CANDIDATE_ARTIFACT_ROOT" "$P7_CANDIDATE_REPO_ROOT"
  test "$(git -C "$P7_CANDIDATE_WORKTREE" rev-parse HEAD)" = \
    "$P7_CANDIDATE_COMMIT"
  test "$(git -C "$P7_REPEAT_A_WORKTREE" rev-parse HEAD)" = \
    "$P7_CANDIDATE_COMMIT"
  test "$(git -C "$P7_REPEAT_B_WORKTREE" rev-parse HEAD)" = \
    "$P7_CANDIDATE_COMMIT"
  test -z "$(git -C "$P7_CANDIDATE_WORKTREE" status --porcelain)"
  test -z "$(git -C "$P7_REPEAT_A_WORKTREE" status --porcelain)"
  test -z "$(git -C "$P7_REPEAT_B_WORKTREE" status --porcelain)"

  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-prepare-repos \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --source-manifest \
      "$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/public_source_manifest.json" \
      --source-repos-dir "$CST_P7_PUBLIC_REPOS_DIR" \
      --destination "$P7_CANDIDATE_REPO_ROOT/master" \
      --clone-destination "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --clone-destination "$P7_CANDIDATE_REPO_ROOT/repeat-a" \
      --clone-destination "$P7_CANDIDATE_REPO_ROOT/repeat-b" \
      --identity-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/repos-identity.json"
  )
  ```

  The resulting identity must match Task 6's pinned source/index/config
  identities. Revalidate all three copies before and after every later step;
  no acceptance command may refresh an index in place.

- [ ] **Step 2: Re-run the complete protected history**

  Run the full suite with exact skip/xfail accounting, then P0 raw CI, P2
  ContextPack, P3 trace migration/fixtures, P4 deterministic plus available
  pinned real exploration, P5 graph profiles, and P6 focused
  query/performance/lifecycle gates. No protected fixture, limit, expectation,
  or negative matcher may be weakened to accommodate P7.

  Require:

  ```text
  failures = 0
  errors = 0
  xfails = 0
  skip IDs = reviewed environment set
  P4 retrieval-call ceiling unchanged
  P3 v1 fixtures byte-identical
  allowed v2 migration exact
  ```

  Run the closed protected set from the candidate worktree:

  ```bash
  export P7_PROTECTED_ROOT="$P7_CANDIDATE_ARTIFACT_ROOT/protected"
  mkdir -p "$P7_PROTECTED_ROOT"
  (
    cd "$P7_CANDIDATE_WORKTREE"
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$P7_CANDIDATE_WORKTREE/src" \
      "$P7_RUNTIME" -m pytest -q -rsxX -p no:cacheprovider \
      --junitxml "$P7_PROTECTED_ROOT/full-suite.xml" \
      > "$P7_PROTECTED_ROOT/full-suite.log" 2>&1

    PYTHONPATH="$P7_CANDIDATE_WORKTREE/src:$P7_CANDIDATE_WORKTREE/tests" \
      "$P7_RUNTIME" -m pytest -q \
      tests/test_quality_p3.py \
      tests/test_retrieval_trace.py \
      tests/test_retrieval_trace_pipeline.py \
      tests/test_exploration_inputs.py \
      tests/test_quality_p4.py \
      tests/test_p5_inputs.py \
      tests/test_quality_p5.py \
      tests/test_p6_benchmark.py \
      tests/test_p6_case_registry.py \
      tests/test_p6_measurement_worker.py

  )
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-protected-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture \
      "$P7_AUDIT_WORKTREE/tests/fixtures/retrieval_quality/queries.json" \
      --profile ci --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --output "$P7_PROTECTED_ROOT/p0-ci.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-protected-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture \
      "$P7_AUDIT_WORKTREE/tests/fixtures/retrieval_quality/queries.json" \
      --profile p2_context_pack \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --output "$P7_PROTECTED_ROOT/p2-context.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-protected-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture \
      "$P7_AUDIT_WORKTREE/tests/fixtures/retrieval_quality/p4_exploration.json" \
      --profile p4_exploration \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --output "$P7_PROTECTED_ROOT/p4-exploration.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-protected-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture \
      "$P7_AUDIT_WORKTREE/tests/fixtures/retrieval_quality/p5_language_graphs.json" \
      --profile p5_language_graphs \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --output "$P7_PROTECTED_ROOT/p5-language-graphs.json"
  )
  ```

  Parse `full-suite.xml` with the frozen safe parser and require the exact
  reviewed skip IDs. If the prepared pinned-real roots are present, run
  `p4_real_exploration` against the same
  `tests/fixtures/retrieval_quality/p4_exploration.json` and
  `p5_real_language_graphs` against
  `tests/fixtures/retrieval_quality/p5_real_language_graphs.json`, each into a
  new file under `P7_PROTECTED_ROOT`; absence is recorded with the reviewed
  optional identity, never replaced by a deterministic fixture.

  Finally run the Task-6 closed aggregator with the full JUnit, four mandatory
  reports, exact frozen P3 fixture hashes, and any present pinned-real reports:

  ```bash
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-index-tdd \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --records-root "$P7_REPO_ROOT/.quality/p7-artifacts/tdd" \
      --candidate-commit "$P7_CANDIDATE_COMMIT" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/tdd-index.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-protected-summary \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --full-suite "$P7_PROTECTED_ROOT/full-suite.xml" \
      --p0 "$P7_PROTECTED_ROOT/p0-ci.json" \
      --p2 "$P7_PROTECTED_ROOT/p2-context.json" \
      --p4 "$P7_PROTECTED_ROOT/p4-exploration.json" \
      --p5 "$P7_PROTECTED_ROOT/p5-language-graphs.json" \
      --tdd-index "$P7_CANDIDATE_ARTIFACT_ROOT/tdd-index.json" \
      --candidate-commit "$P7_CANDIDATE_COMMIT" \
      --baseline-freeze-commit "$P7_BASELINE_FREEZE_COMMIT" \
      --baseline-projection-identity \
      "$P7_CANDIDATE_WORKTREE/docs/benchmarks/p7/baseline/public-projection-identity.json" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/protected-summary.json"
  )
  ```

  Optional report flags are appended only for files that exist and have passed
  their own identity validator. The aggregator rejects an unaudited omission,
  unknown skip, changed P3 v1 hash, or weakened protected expectation.

- [ ] **Step 3: Run deterministic mechanics twice**

  Execute all eight mechanics cases in two clean candidate worktrees with hash
  embeddings and no planner. Require exact repeatability after timing
  normalization and, for every case:

  ```text
  identifier extraction/state/path expectation exact
  conditional protected-path survival = 1.0
  unique_path_ratio = 1.0
  raw_duplicate_slot_count = 0
  result_fill_ratio = 1.0
  applicable terminal recall = 1.0
  context/explore required excerpt recall = 1.0
  designed attrition reason exact
  file/span oracle expectation exact
  ```

  ```bash
  export P7_CANDIDATE_MECHANICS_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_mechanics.json"
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_REPEAT_A_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture "$P7_CANDIDATE_MECHANICS_FIXTURE" \
      --profile p7_mechanics \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/repeat-a" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --behavior-contract p7-enforced --audit enabled --run-id mechanics-a \
      --public-projection-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-projection.json" \
      --audit-output "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-audit.json"
  )
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_REPEAT_B_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture "$P7_CANDIDATE_MECHANICS_FIXTURE" \
      --profile p7_mechanics \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/repeat-b" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --behavior-contract p7-enforced --audit enabled --run-id mechanics-b \
      --public-projection-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-b-projection.json" \
      --audit-output "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-b-audit.json"
  )
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture "$P7_CANDIDATE_MECHANICS_FIXTURE" \
      --profile p7_mechanics \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --behavior-contract p7-enforced --audit disabled \
      --run-id mechanics-audit-disabled \
      --public-projection-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-disabled-projection.json"
  )
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare-projections \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --mode profile-repeat --profile-id p7_mechanics \
      --run-a \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-projection.json" \
      --run-b \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-b-projection.json" \
      --audit-a \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-audit.json" \
      --audit-b \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-b-audit.json" \
      --repos-identity "$P7_CANDIDATE_ARTIFACT_ROOT/repos-identity.json" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-repeat.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare-projections \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --mode candidate-neutrality --profile-id p7_mechanics \
      --enabled-run \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-projection.json" \
      --enabled-audit \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-audit.json" \
      --disabled-run \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-disabled-projection.json" \
      --repos-identity "$P7_CANDIDATE_ARTIFACT_ROOT/repos-identity.json" \
      --output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-audit-neutrality.json"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-assert-mechanics \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --audit-a "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-audit.json" \
      --audit-b "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-b-audit.json" \
      --projection-a \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-a-projection.json" \
      --projection-b \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-b-projection.json" \
      --repeat-proof "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-repeat.json" \
      --audit-neutrality-proof \
      "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-audit-neutrality.json" \
      --candidate-commit "$P7_CANDIDATE_COMMIT" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-summary.json"
  )
  ```

  `p7-evaluate` always emits a schema-valid mechanics report, including for the
  expected failing behavior baseline. The candidate-only
  `p7-assert-mechanics` command fails closed on every absolute expectation above
  and binds its result to both enabled runs, the repeat proof, and the fresh
  audit-disabled neutrality proof. The repeat comparison validates and binds
  the separate identity/control and timing envelopes, then requires exact
  behavioral-payload and audit-leaf equality. The neutrality comparison
  requires exact public output/error/work-counter equality and no retained
  disabled-run observer state. Recheck all three worktrees and run-copy
  identities after execution.

- [ ] **Step 4: Run the fixed public candidate profile**

  Validate the frozen witness rather than searching again, then run exactly the
  eighteen frozen cases and their declared query/context/explore surfaces. Each
  audited surface performs its production call count only; oracle runs are
  separate diagnostics and never modify production candidates.

  Generate candidate audit and compare it with the Task-6 baseline using only
  `actual_terminal_reason` for regression/improvement/decision data.
  `policy_shadow_terminal_reason` remains baseline characterization and never
  votes.

  ```bash
  export P7_CANDIDATE_DECISION_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_decision.json"
  export P7_CANDIDATE_PROFILE_FIXTURE="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_profile.json"
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-validate-gold \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --profile "$P7_CANDIDATE_PROFILE_FIXTURE" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --feasible-cover \
      "$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold/feasible-cover-manifest.json" \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/gold-validation.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_REPEAT_A_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture "$P7_CANDIDATE_DECISION_FIXTURE" \
      --profile p7_decision \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/repeat-a" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --behavior-contract p7-enforced --audit enabled \
      --run-id public-candidate-a \
      --public-projection-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-projection.json" \
      --audit-output "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_REPEAT_B_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture "$P7_CANDIDATE_DECISION_FIXTURE" \
      --profile p7_decision \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/repeat-b" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --behavior-contract p7-enforced --audit enabled \
      --run-id public-candidate-b \
      --public-projection-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-b-projection.json" \
      --audit-output "$P7_CANDIDATE_ARTIFACT_ROOT/public-b-audit.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-evaluate \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --fixture "$P7_CANDIDATE_DECISION_FIXTURE" \
      --profile p7_decision \
      --repos-dir "$P7_CANDIDATE_REPO_ROOT/candidate" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --behavior-contract p7-enforced --audit disabled \
      --run-id public-candidate-audit-disabled \
      --public-projection-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-disabled-projection.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare-projections \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --mode profile-repeat --profile-id p7_decision \
      --run-a "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-projection.json" \
      --run-b "$P7_CANDIDATE_ARTIFACT_ROOT/public-b-projection.json" \
      --audit-a "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json" \
      --audit-b "$P7_CANDIDATE_ARTIFACT_ROOT/public-b-audit.json" \
      --repos-identity "$P7_CANDIDATE_ARTIFACT_ROOT/repos-identity.json" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/public-repeat.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare-projections \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --mode candidate-neutrality --profile-id p7_decision \
      --enabled-run "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-projection.json" \
      --enabled-audit "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json" \
      --disabled-run \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-disabled-projection.json" \
      --repos-identity "$P7_CANDIDATE_ARTIFACT_ROOT/repos-identity.json" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/public-audit-neutrality.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-compare \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --baseline \
      "$P7_CANDIDATE_WORKTREE/docs/benchmarks/p7/baseline/public-audit.json" \
      --baseline-freeze-commit "$P7_BASELINE_FREEZE_COMMIT" \
      --baseline-projection-identity \
      "$P7_CANDIDATE_WORKTREE/docs/benchmarks/p7/baseline/public-projection-identity.json" \
      --candidate "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json" \
      --candidate-repeat-proof \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-repeat.json" \
      --candidate-neutrality-proof \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-audit-neutrality.json" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --resolved-gold-validation \
      "$P7_CANDIDATE_ARTIFACT_ROOT/gold-validation.json" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/public-comparison.json"
  )
  ```

  Driver, fixture, provenance resolver, normalization, and comparison all
  resolve from the frozen evaluator closure; only the product worker resolves
  from `P7_CANDIDATE_COMMIT`. The compare command verifies and records the
  Task-6 baseline-neutrality artifact before accepting the baseline audit and
  the final-candidate audit-neutrality proof before accepting candidate audit
  leaves. It rejects policy-shadow fields as voting inputs and records their
  hash only as baseline diagnosis. Baseline files are read from the
  candidate/coordination tree because the detached evaluator commit predates
  the artifact-only freeze; the frozen evaluator verifies their exact blobs at
  `P7_BASELINE_FREEZE_COMMIT` before use.

- [ ] **Step 5: Run frozen metamorphic and anti-special-casing gates**

  Create fresh transformed source/index copies; never edit candidate,
  repeat-a/repeat-b, master, or ordinary public run roots:

  ```bash
  export P7_TRANSFORM_MANIFEST="$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/metamorphic_transforms.json"
  export P7_METAMORPHIC_ROOT="$P7_CANDIDATE_REPO_ROOT/metamorphic"
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_FROZEN_DRIVER" p7-prepare-metamorphic \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_CANDIDATE_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --transform-manifest "$P7_TRANSFORM_MANIFEST" \
      --base-repos-dir "$P7_CANDIDATE_REPO_ROOT/master" \
      --destination "$P7_METAMORPHIC_ROOT" \
      --identity-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/metamorphic-identity.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-robustness \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --product-root "$P7_REPEAT_A_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      --expected-product-commit "$P7_CANDIDATE_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --behavior-contract p7-enforced \
      --fixture "$P7_CANDIDATE_DECISION_FIXTURE" \
      --transform-manifest "$P7_TRANSFORM_MANIFEST" \
      --base-audit "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json" \
      --repos-dir "$P7_METAMORPHIC_ROOT" \
      --metamorphic-identity \
      "$P7_CANDIDATE_ARTIFACT_ROOT/metamorphic-identity.json" \
      --candidate-production-root \
      "$P7_CANDIDATE_WORKTREE/src/context_search_tool" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/robustness-summary.json"
  )
  ```

  Require at least three exact companion IDs; exact transformed source/index
  hashes before and after; offline syntax/import and renamed-target validation;
  full required coherent terminal satisfaction equal to its base result modulo
  the rename map; and zero anti-special-casing matches. The command writes no
  query, source, snippet, transformed path, or scanner needle to the summary.
  Any missing/failed companion or source/index/product drift blocks P7.

- [ ] **Step 6: Enforce pinned-public quality gates**

  Across required cases:

  - path and target-span acquisition do not regress;
  - context-expansion survival, terminal, pack, and excerpt recall do not
    regress;
  - every targeted baseline attrition cohort improves actual terminal
    satisfaction, not only an intermediate or shadow stage;
  - exact-query Hit@1 and MRR do not regress;
  - configured noise-in-pack does not increase;
  - every `Gate.REQUIRED` absolute expectation passes;
  - known-gap/informational cases execute with complete audits but cannot fail
    P7 merely for preserving the declared gap;
  - no aggregate gain hides an individual required-case regression.

  A failure produces no accepted decision. Fix the owning task with a new RED,
  update `P7_CANDIDATE_COMMIT`, and repeat all affected paired runs. Gold,
  thresholds, baseline, and reference helpers remain frozen.

- [ ] **Step 7: Run paired performance and work-contract acceptance**

  On the same P6 environment/prepared indexes and fixed warmups/samples, require:

  ```text
  warm exact-query p95 <= 1.10x baseline
  warm exploratory query p95 <= 1.15x baseline
  warm context p95 <= 1.15x baseline
  peak RSS <= 1.10x baseline
  exploration retrieval-call ceiling unchanged
  embedding/planner request delta = 0
  source stat/read_text <= one pair per expanded unique path
  peak full-source-body residency <= one
  audit-disabled retained-ledger count = 0
  ```

  Drive both persistent workers with the frozen Task-6 harness:

  ```bash
  export P7_PERFORMANCE_ROOT="$P7_ATTEMPT_ROOT/performance"
  mkdir -p "$P7_PERFORMANCE_ROOT"
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_AUDIT_WORKTREE/scripts/p6_benchmark.py" \
      p7-prepare-paired-workspaces \
      --driver-root "$P7_AUDIT_WORKTREE" \
      --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --manifest \
      "$P7_AUDIT_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
      --master-root "$P7_PERFORMANCE_ROOT/master" \
      --baseline-repo "$P7_PERFORMANCE_ROOT/baseline-repo" \
      --candidate-repo "$P7_PERFORMANCE_ROOT/candidate-repo" \
      --identity-output "$P7_PERFORMANCE_ROOT/workspace-identity.json"

    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      "$P7_AUDIT_WORKTREE/scripts/p6_benchmark.py" paired \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --operation-set p7_retrieval_context_paired \
      --baseline-root "$P7_BEHAVIOR_WORKTREE" \
      --candidate-root "$P7_CANDIDATE_WORKTREE" \
      --baseline-repo "$P7_PERFORMANCE_ROOT/baseline-repo" \
      --candidate-repo "$P7_PERFORMANCE_ROOT/candidate-repo" \
      --manifest \
      "$P7_AUDIT_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
      --workspace-identity "$P7_PERFORMANCE_ROOT/workspace-identity.json" \
      --pairs 30 \
      --raw-output "$P7_PERFORMANCE_ROOT/paired-raw.json" \
      --summary-output "$P7_PERFORMANCE_ROOT/paired-summary.json"
  )
  ```

  The command must validate the implementation-root handshakes, five warmups,
  thirty gated samples, alternating AB/BA order, and identical prepared
  workspace/index hashes before reporting ratios. It also verifies the driver
  source projection still equals Task 6, runs both workers under the same
  runtime/dependency hash, and rejects any worker restart or source/index drift.

  Publish normalized ratios, sample counts, environment hash, and threshold
  outcomes. Raw samples, absolute local paths, process command lines, and source
  bodies remain under `.quality/p7-performance/`.

- [ ] **Step 8: Run and sanitize the private overlay when authorized**

  Always create exactly one candidate private-summary artifact. Determine
  eligibility from the Task-6 freeze record before reading candidate output:

  ```bash
  export P7_PRIVATE_CANDIDATE_ROOT="$P7_ATTEMPT_ROOT/private"
  export P7_PRIVATE_BASELINE_ROOT="$P7_REPO_ROOT/.quality/p7-private/baseline"
  export P7_PRIVATE_GOLD_SEAL="$P7_PRIVATE_BASELINE_ROOT/private-gold-seal.json"
  export P7_PRIVATE_FREEZE_RECORD="$P7_PRIVATE_BASELINE_ROOT/private-freeze-record.json"
  mkdir -p "$P7_PRIVATE_CANDIDATE_ROOT"

  P7_PRIVATE_CONFIG_COMPLETE=false
  if [[ -n "${CST_P7_PRIVATE_FIXTURE:-}" &&
        -n "${CST_P7_PRIVATE_REPO:-}" &&
        -n "${CST_P7_PRIVATE_REVIEW_ID:-}" ]]; then
    P7_PRIVATE_CONFIG_COMPLETE=true
  elif [[ -n "${CST_P7_PRIVATE_FIXTURE:-}" ||
          -n "${CST_P7_PRIVATE_REPO:-}" ||
          -n "${CST_P7_PRIVATE_REVIEW_ID:-}" ]]; then
    echo "Private fixture, repo, and review ID must be all present or all absent" >&2
    exit 1
  fi

  P7_PRIVATE_PREPARE_FREEZE_ARGS=()
  P7_PRIVATE_SUMMARY_FREEZE_ARGS=()
  if [[ -e "$P7_PRIVATE_FREEZE_RECORD" ]]; then
    test "$P7_PRIVATE_CONFIG_COMPLETE" = true
    P7_PRIVATE_SUMMARY_MODE=paired-frozen
    P7_PRIVATE_ACTIVE_GOLD_SEAL="$P7_PRIVATE_GOLD_SEAL"
    P7_PRIVATE_PREPARE_FREEZE_ARGS=(
      --freeze-record "$P7_PRIVATE_FREEZE_RECORD"
      --expected-baseline-repo-identity \
      "$P7_PRIVATE_BASELINE_ROOT/repo-identity.json"
      --profile p7_private
      --threshold-contract \
      "$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_profile.json"
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT"
      --private-gold-seal "$P7_PRIVATE_GOLD_SEAL"
      --baseline-summary "$P7_PRIVATE_BASELINE_ROOT/summary.json"
    )
    P7_PRIVATE_SUMMARY_FREEZE_ARGS=(
      --freeze-record "$P7_PRIVATE_FREEZE_RECORD"
      --baseline-summary "$P7_PRIVATE_BASELINE_ROOT/summary.json"
    )
  elif [[ "$P7_PRIVATE_CONFIG_COMPLETE" = true ]]; then
    P7_PRIVATE_SUMMARY_MODE=late-informational
    P7_PRIVATE_ACTIVE_GOLD_SEAL="$P7_PRIVATE_CANDIDATE_ROOT/late-private-gold-seal.json"
  else
    (
      cd "$P7_AUDIT_WORKTREE"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-private-summary \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --mode unavailable --reason not_configured_before_candidate \
        --fixture-present false --repo-present false \
        --review-id-present false \
        --output "$P7_PRIVATE_CANDIDATE_ROOT/summary.json"
    )
  fi

  if [[ "$P7_PRIVATE_CONFIG_COMPLETE" = true ]]; then
    (
      cd "$P7_AUDIT_WORKTREE"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_FROZEN_DRIVER" \
        p7-prepare-private \
        --driver-root "$P7_AUDIT_WORKTREE" \
        --product-root "$P7_CANDIDATE_WORKTREE" \
        --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        --expected-product-commit "$P7_CANDIDATE_COMMIT" \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --source-repo "$CST_P7_PRIVATE_REPO" \
        --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
        --private-review-id "$CST_P7_PRIVATE_REVIEW_ID" \
        --destination "$P7_PRIVATE_CANDIDATE_ROOT/master" \
        --clone-destination "$P7_PRIVATE_CANDIDATE_ROOT/candidate-repo" \
        --identity-output "$P7_PRIVATE_CANDIDATE_ROOT/repos-identity.json" \
        "${P7_PRIVATE_PREPARE_FREEZE_ARGS[@]}"
      if [[ "$P7_PRIVATE_SUMMARY_MODE" = late-informational ]]; then
        PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
          -m context_search_tool.quality p7-private-gold-seal \
          "${P7_CANDIDATE_COMMON_ARGS[@]}" \
          --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
          --private-review-id "$CST_P7_PRIVATE_REVIEW_ID" \
          --profile p7_private \
          --repos-dir "$P7_PRIVATE_CANDIDATE_ROOT/candidate-repo" \
          --repo-identity "$P7_PRIVATE_CANDIDATE_ROOT/repos-identity.json" \
          --threshold-contract \
          "$P7_AUDIT_WORKTREE/tests/fixtures/p7_retrieval_quality/p7_profile.json" \
          --feasibility-helper \
          "$P7_AUDIT_WORKTREE/docs/benchmarks/p7/gold/feasible-cover-manifest.json" \
          --output "$P7_PRIVATE_ACTIVE_GOLD_SEAL"
      fi
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_FROZEN_DRIVER" \
        p7-evaluate \
        --driver-root "$P7_AUDIT_WORKTREE" \
        --product-root "$P7_CANDIDATE_WORKTREE" \
        --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        --expected-product-commit "$P7_CANDIDATE_COMMIT" \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --fixture "$CST_P7_PRIVATE_FIXTURE" --profile p7_private \
        --repos-dir "$P7_PRIVATE_CANDIDATE_ROOT/candidate-repo" \
        --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
        --private-gold-seal "$P7_PRIVATE_ACTIVE_GOLD_SEAL" \
        --behavior-contract p7-enforced --audit enabled \
        --run-id private-candidate \
        --public-projection-output \
        "$P7_PRIVATE_CANDIDATE_ROOT/candidate-raw-projection.json" \
        --audit-output "$P7_PRIVATE_CANDIDATE_ROOT/candidate-raw-audit.json"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-private-summary \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --mode "$P7_PRIVATE_SUMMARY_MODE" \
        --candidate-raw-audit \
        "$P7_PRIVATE_CANDIDATE_ROOT/candidate-raw-audit.json" \
        --private-fixture "$CST_P7_PRIVATE_FIXTURE" \
        --private-repo "$CST_P7_PRIVATE_REPO" \
        --private-review-id "$CST_P7_PRIVATE_REVIEW_ID" \
        --repos-identity "$P7_PRIVATE_CANDIDATE_ROOT/repos-identity.json" \
        --private-gold-seal "$P7_PRIVATE_ACTIVE_GOLD_SEAL" \
        "${P7_PRIVATE_SUMMARY_FREEZE_ARGS[@]}" \
        --output "$P7_PRIVATE_CANDIDATE_ROOT/summary.json"
    )
  fi
  ```

  `paired-frozen` verifies the current fixture, repo/index, owner-review,
  profile/options, thresholds, evaluator/gold, and sanitized baseline-summary
  identities against Task 6 before candidate execution; it runs no baseline
  product. Only that mode can influence the owner-facing result, and only after
  six cases, twelve units, six misses, and three supporting cases.
  `late-informational` is permanently non-voting. Scan the final summary bytes
  for every private query, identifier, relative/absolute path, planner hint,
  origin, username, fixture/review path or identity, raw-input hash, and secret
  pattern. A frozen overlay that is missing, drifts, fails, or leaks blocks
  acceptance; it cannot be relabeled unavailable.

- [ ] **Step 9: Optionally run fast-context as a non-gating comparator**

  Always create one closed comparator summary:

  ```bash
  export P7_COMPARATOR_ROOT="$P7_ATTEMPT_ROOT/comparator"
  mkdir -p "$P7_COMPARATOR_ROOT"
  if [[ -n "${CST_P7_FAST_CONTEXT_COMMAND:-}" ]]; then
    (
      cd "$P7_AUDIT_WORKTREE"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" "$P7_FROZEN_DRIVER" \
        p7-comparator-run \
        --driver-root "$P7_AUDIT_WORKTREE" \
        --expected-driver-commit "$P7_AUDIT_INSTRUMENTATION_COMMIT" \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --bounded-command "$CST_P7_FAST_CONTEXT_COMMAND" \
        --fixture "$P7_CANDIDATE_DECISION_FIXTURE" \
        --repos-dir "$P7_CANDIDATE_REPO_ROOT/master" \
        --raw-output "$P7_COMPARATOR_ROOT/raw.json"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-comparator-summary \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --mode observed --raw "$P7_COMPARATOR_ROOT/raw.json" \
        --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
        --output "$P7_CANDIDATE_ARTIFACT_ROOT/comparator-summary.json"
    )
  else
    (
      cd "$P7_AUDIT_WORKTREE"
      PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
        -m context_search_tool.quality p7-comparator-summary \
        "${P7_CANDIDATE_COMMON_ARGS[@]}" \
        --mode unavailable --reason not_configured \
        --command-present false \
        --output "$P7_CANDIDATE_ARTIFACT_ROOT/comparator-summary.json"
    )
  fi
  ```

  The wrapper parses bounded argv, uses `shell=False`, a fixed public cwd,
  explicit timeout/response caps, and an allowlisted environment. A remote
  failure is a valid `failed` comparator status and remains non-gating; a
  wrapper/provenance/privacy/schema failure blocks the summary. Raw commands,
  responses, paths, snippets, and queries remain ignored. Comparator evidence
  never changes gold, witnesses, thresholds, classification, or candidate
  behavior, and cannot support a general fast-context parity claim.

- [ ] **Step 10: Generate and validate `P7DecisionRecord v1`**

  Feed only the fixed public candidate's enforced actual terminal reasons into
  `quality.p7_decision`. Validate profile/cohort minimums, complete applicable
  audits, provenance, oracle witness, source/config identity, structural and
  protected gates, performance, and privacy before classification.

  Select exactly one of the eleven legal classifications and exactly one legal
  next-phase mapping. Include:

  ```text
  all commit/tree/config/fixture/helper/witness identities
  case and required-unit counts by cohort
  stage hit/total and micro/macro recall
  actual attrition counts
  baseline shadow counts separately
  exact-resolution/survival and raw duplicate/fill metrics
  file/span oracle diagnostics
  latency/RSS/work summaries
  protected profile outcomes
  comparator availability only
  public and private classifications
  owner-facing selected classification
  selected next phase
  rejected actions and open risks
  privacy proof
  ```

  `mixed_inconclusive` authorizes only benchmark expansion/correction.
  `no_proven_retrieval_bottleneck` forbids another retrieval mechanism without
  a new measurable failure. No result pre-authorizes AST, a reranker, controller
  redesign, or score retuning.

  The final decision command is:

  ```bash
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-decide \
      "${P7_CANDIDATE_COMMON_ARGS[@]}" \
      --baseline \
      "$P7_CANDIDATE_WORKTREE/docs/benchmarks/p7/baseline/public-audit.json" \
      --baseline-freeze-commit "$P7_BASELINE_FREEZE_COMMIT" \
      --baseline-projection-identity \
      "$P7_CANDIDATE_WORKTREE/docs/benchmarks/p7/baseline/public-projection-identity.json" \
      --candidate "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json" \
      --comparison "$P7_CANDIDATE_ARTIFACT_ROOT/public-comparison.json" \
      --candidate-neutrality-proof \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-audit-neutrality.json" \
      --mechanics "$P7_CANDIDATE_ARTIFACT_ROOT/mechanics-summary.json" \
      --robustness "$P7_CANDIDATE_ARTIFACT_ROOT/robustness-summary.json" \
      --performance "$P7_PERFORMANCE_ROOT/paired-summary.json" \
      --protected "$P7_CANDIDATE_ARTIFACT_ROOT/protected-summary.json" \
      --private-summary "$P7_PRIVATE_CANDIDATE_ROOT/summary.json" \
      --comparator-summary \
      "$P7_CANDIDATE_ARTIFACT_ROOT/comparator-summary.json" \
      --gold-provenance-root "$P7_CANDIDATE_GOLD_ROOT" \
      --resolved-gold-validation \
      "$P7_CANDIDATE_ARTIFACT_ROOT/gold-validation.json" \
      --output "$P7_CANDIDATE_ARTIFACT_ROOT/p7-decision.json" \
      --markdown "$P7_CANDIDATE_ARTIFACT_ROOT/p7-decision.md"
  )
  ```

  All listed inputs are mandatory. Private and comparator commands always emit
  schema-valid explicit unavailable artifacts when not configured; absence is
  never represented by omitting a flag. `p7-decide` revalidates every input
  hash, candidate attempt/environment identity, run role, and causal timestamp.
  A configured frozen-private failure blocks; a remote comparator's validated
  `failed` status remains non-gating.

- [ ] **Step 11: Publish only schema-valid source-independent artifacts**

  Copy normalized public audit/comparison/performance/decision artifacts into
  `docs/benchmarks/p7/final/`. Re-run exact-key schemas and forbidden-content
  scanners. Confirm no raw report, source excerpt, full trace dump, query from a
  private overlay, checkout/index, timing sample, comparator response, or local
  environment path is staged.

  Use the closed publisher rather than a filesystem copy:

  ```bash
  P7_FINAL_PUBLICATION_ARGS=(
    "${P7_CANDIDATE_COMMON_ARGS[@]}"
    --publication-root "$P7_REPO_ROOT/docs/benchmarks/p7"
  )
  (
    cd "$P7_AUDIT_WORKTREE"
    PYTHONPATH="$P7_AUDIT_WORKTREE/src" "$P7_RUNTIME" \
      -m context_search_tool.quality p7-publish-batch \
      "${P7_FINAL_PUBLICATION_ARGS[@]}" \
      --mode final \
      --public-audit-input \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-a-audit.json" \
      --comparison-input \
      "$P7_CANDIDATE_ARTIFACT_ROOT/public-comparison.json" \
      --performance-input "$P7_PERFORMANCE_ROOT/paired-summary.json" \
      --robustness-input \
      "$P7_CANDIDATE_ARTIFACT_ROOT/robustness-summary.json" \
      --decision-input "$P7_CANDIDATE_ARTIFACT_ROOT/p7-decision.json" \
      --decision-markdown-input \
      "$P7_CANDIDATE_ARTIFACT_ROOT/p7-decision.md" \
      --receipt-output \
      "$P7_CANDIDATE_ARTIFACT_ROOT/publication-receipt.json"
  )
  ```

  Every output is no-overwrite/create-only with exact-identical interrupted
  resume semantics. The Markdown projection permits only fields already present
  in the validated decision JSON and records that JSON's hash; it cannot
  introduce raw queries, paths, samples, or free-form comparator content.

- [ ] **Step 12: Update documentation only after all gates pass**

  Update:

  - README with the accepted public behavior and trace-v2 compatibility note;
  - roadmap P7 status and the selected next phase, explicitly retaining P8/P9
    as evidence-dependent rather than implied commitments;
  - leave the reviewed design bytes/status unchanged; record implementation and
    acceptance links in README, roadmap, and this plan so the reviewed design
    identity remains valid;
  - plan status and Implementation Record with every already-known ancestor
    commit, commands, hashes, counts, deviations/corrections, and agent/human
    reviews;
  - benchmark README with reproduction, privacy, comparator, and interpretation
    limits.

  If any mandatory gate fails, leave plan status unaccepted, leave the reviewed
  design untouched, and do not publish a success narrative.

- [ ] **Step 13: Validate the final documentation-only diff**

  ```bash
  cd "$P7_REPO_ROOT"
  PYTHONPATH="$PWD/src:$PWD/tests" "$P7_RUNTIME" -m pytest -q \
    tests/test_p7_contracts.py \
    tests/test_p7_quality_cases.py \
    tests/test_p7_oracle.py \
    tests/test_p7_decision.py \
    tests/test_p7_quality_profile.py \
    tests/test_p7_quality_runner.py \
    tests/test_p7_performance_contract.py

  git diff --check
  git status --short
  ```

  Verify the final diff is limited to the Task-12 `Files` list and that every
  linked artifact exists, validates, and refers to the actual ancestor commit.

- [ ] **Step 14: Run fixed-payload post-implementation review**

  After the Implementation Record and every final documentation/artifact byte
  are complete, freeze:

  ```text
  full design SHA-256 and line count
  design_review_payload_sha256
  full plan SHA-256 and line count
  review_payload_sha256
  P7_CANDIDATE_COMMIT and complete candidate diff/tree
  all baseline/final artifact hashes and schema results
  ```

  Three independent read-only agents—architecture/contract,
  IR/evaluation/gold, and implementation/TDD/operability—must reread the
  complete fixed documents and inspect the implementation diff plus declared
  evidence. Each reports the fixed hashes, `PASS|FAIL`, blocker/major/minor
  counts, exact findings, and residual risks. Acceptance requires zero blocker,
  zero major, and every minor either corrected with all affected gates/reviews
  repeated or explicitly accepted with rationale.

  Record results only in the excluded `Independent Plan Review Record` and
  update the excluded `Status:` line. Recompute both payload hashes and require
  them unchanged from the values the agents reviewed. A correction to the
  Implementation Record, Stop Point, command, contract, artifact, or any other
  covered byte creates a new payload and restarts all three reviews. The design
  remains byte-identical.

- [ ] **Step 15: Commit the accepted record**

  ```bash
  git add \
    docs/benchmarks/p7/final/public-audit.json \
    docs/benchmarks/p7/final/public-comparison.json \
    docs/benchmarks/p7/final/performance-summary.json \
    docs/benchmarks/p7/final/robustness-summary.json \
    docs/benchmarks/p7/final/p7-decision.json \
    docs/benchmarks/p7/final/p7-decision.md \
    docs/benchmarks/p7/README.md \
    README.md \
    roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md \
    docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "docs: record p7 acceptance and decision"
  ```

**Commit:** `docs: record p7 acceptance and decision`

## Design-To-Task Traceability

| reviewed design contract | implementation task(s) | decisive verification |
| --- | --- | --- |
| Audit before optimization; actual/shadow separation | 2-6 | audited/non-audited byte identity; one actual and optional shadow reason |
| Schema-v2 target-bearing evidence units | 4 | source-resolved canonical target and anti-gaming tests |
| Frozen feasible cover and provenance | 5-6 | exhaustive equivalence, witness hash, gold commit seal |
| Closed file/span oracles | 5, 12 | idealization boundary tests and accepted oracle diagnostics |
| Fixed public/private benchmark matrix | 5, 6, 12 | quota/source identity/privacy validators |
| Closed classification and next-phase mapping | 5, 12 | boundary/contradiction tests and one valid decision |
| Occurrence-preserving exact extraction/resolution | 2-3 | literal/clause/priority/work-contract matrix |
| Canonical exact injection before direct merge | 8, 10 | lane precedence and end-to-end rescue tests |
| No general score retuning | 1, 8, 10 | frozen score/rerank projections |
| Traversal-only visibility | 2-3, 10 | derived-evidence and pipeline visibility tests |
| Grouped one-body source materialization | 9, 12 | read/stat/residency counters and output parity |
| Complete file population; two normal spans | 2, 10 | pure projection plus end-to-end population accounting |
| Final selection sole capacity owner | 2, 10 | independent protected pools and fill denominator |
| Private segments and pack reservation | 7, 10-11 | sentinel, no-gap matching, retry/reservation tests |
| Omitted-budget context boundary | 11 | exact formula/null/explicit/one-call matrix |
| RetrievalTrace v2 and P4 legacy origins | 1, 8-10 | v1 ledger, v2 provenance, unchanged P4 seed tests |
| P4 follow-up protection disabled | 8, 11 | ContextVar lifecycle and real/deterministic P4 compatibility |
| P0-P6 and performance protection | 0, 6, 10-12 | full suite, protected profiles, paired ratios |
| Privacy and comparator limits | 1, 6, 12 | exact artifact schemas and private sentinel scan |

## Commit, Correction, And Rollback Policy

- Each task's focused commit contains only its declared files and passes its
  focused gates. A review/fix commit may be separate only when it names the
  originating task and repeats that task's tests.
- Tasks 1-6 must not change normalized public behavior. A detected delta is a
  blocker, not an allowlist candidate.
- Task 5 gold and the Task-6 evaluator/instrumentation/baseline series are
  immutable within this reviewed execution. Discovering a legitimate defect in
  any of them stops P7 and requires a separately reviewed plan amendment that
  defines new versioned freeze subjects/artifact paths and paired baseline/
  candidate reruns. The current unique-subject resolver must never select a
  second ad-hoc freeze, and the generic late-fix chain cannot supersede Tasks
  5-6.
- Task 10 is the indivisible query/trace activation. Roll it back as a unit; do
  not disable only exact injection, projection, selection, or trace v2.
- Task 11 is the indivisible omitted-budget context activation. Reverting it
  restores the old context candidate boundary without reverting Task 10.
- Acceptance failures return to the smallest owning task with a new valid RED.
  Threshold/gold/evaluator/baseline edits are not product fixes and trigger the
  stop above.
- No `git reset --hard`, broad checkout, or deletion of user work is part of
  this plan. Isolated worktrees and ignored artifacts may be removed only after
  exact-path validation and explicit implementation authorization.

## Implementation Record

Fill this section during implementation; `pending` is intentional until then.

| evidence | required value |
| --- | --- |
| `P7_REVIEW_COMMIT` | pending |
| `P7_ENTRY_COMMIT` | pending |
| `P7_GOLD_FREEZE_COMMIT` | pending |
| `P7_AUDIT_INSTRUMENTATION_COMMIT` | pending |
| `P7_BASELINE_FREEZE_COMMIT` | pending |
| Task 10 activation commit | pending |
| `P7_CANDIDATE_COMMIT` | pending |
| Task-12 acceptance evidence parent | pending (`P7_CANDIDATE_COMMIT`) |
| runtime/dependency/environment hash | pending |
| full-suite entry/final counts and skip IDs | pending |
| protected profile outputs | pending |
| fixture/profile/helper/options/witness hashes | pending |
| baseline/candidate public audit hashes | pending |
| performance paired-run hash and outcomes | pending |
| private overlay availability/privacy scan | pending |
| comparator availability and disclosure | pending |
| selected classification/next phase | pending |
| deviations and correction records | pending |

The final documentation commit cannot contain its own Git object ID. Its SHA is
derived from Git after Step 15 and reported in the implementation handoff, not
embedded back into this plan or any artifact whose bytes determine that commit.

## Mandatory Stop Conditions

Stop implementation and request review when any of these occurs:

1. source/test/fixture baseline is no longer the reviewed entry parent;
2. a normative design requirement conflicts with this plan or current code;
3. public gold lacks an independent reviewer or is influenced by retrieval
   output;
4. source identity, helper/options hash, witness, or gold seal does not match;
5. feasibility product/state limits are exceeded or no feasible assignment
   exists;
6. Tasks 1-9 change an unapproved public projection;
7. exact resolution requires a second enabled-lane scan/connection or a
   per-literal query;
8. frozen policy/oracle code would need editing after gold freeze;
9. frozen gold, evaluator/instrumentation, or baseline evidence is found
   defective; this plan defines no in-place or same-subject refreeze;
10. Task 10 cannot activate exact/projection/selection/trace together;
11. a façade signature, QueryBundle field, ContextPack schema, ExplorationTrace
    schema, index/graph schema, P4 call limit, or numeric scoring contract would
    need changing;
12. a mandatory quality, protected, deterministic, performance, or privacy gate
    fails;
13. a private/comparator artifact cannot be sanitized with the closed
    allowlist;
14. a classification cannot be selected without changing frozen thresholds;
15. implementation would require a new production retrieval AST (including a
    Python AST retrieval feature), a learned reranker, acquisition controller
    redesign, or another non-goal. Existing Java AST behavior and
    evaluation-only offline syntax/import validation remain allowed.

## Final Verification Checklist

Before Task 12 can mark P7 accepted:

- [ ] reviewed documentation entry and every implementation commit are clean,
      ordered, and recorded;
- [ ] gold predates candidate behavior and its seal resolves immutable blobs;
- [ ] every task has valid RED/GREEN/staged-tree evidence where required;
- [ ] audited and non-audited projections are identical;
- [ ] baseline actual and policy-shadow reasons are never conflated;
- [ ] exact resolution/injection/work limits match the closed contract;
- [ ] raw normal results are unique, filled, and protected within capacity;
- [ ] file projection accounts for every input and retains bounded segments;
- [ ] trace v2 provenance is winner/display correct and P4 uses legacy origins;
- [ ] context omitted/explicit budgets and one-call behavior are exact;
- [ ] P0-P6, full suite, deterministic mechanics, public quality, oracle,
      performance, and privacy gates pass;
- [ ] raw/private-input-bearing data and comparator responses are absent from
      tracked artifacts; only validated safe summary hashes, closed
      status/eligibility/pass fields, derived private classification, and
      comparator availability enter the decision;
- [ ] one legal classification and next phase are mechanically selected;
- [ ] documentation makes no unsupported general or fast-context parity claim.

## Independent Plan Review Rubric

Each reviewer must read the complete plan and normative design at fixed hashes,
make no edits, and return:

```text
reviewer/task
plan SHA-256 and line count read
plan review_payload_sha256
design SHA-256 and line count read
design_review_payload_sha256
PASS or FAIL
blocker count
major count
minor count
numbered findings with exact section/line
residual risks
```

The full plan hash used for a review round is reported externally, because
adding that round's result to this file changes the full-file hash. The stable
`review_payload_sha256` used in the embedded record is computed from this plan
after:

1. removing the single `Status:` line; and
2. removing bytes from `## Independent Plan Review Record` up to, but not
   including, `## Stop Point`.

Everything normative, including the Stop Point, remains covered. A reviewer
must report both the full-file hash/line count it read and this payload hash.
Review-result/status edits may change the full file without changing the
payload; any other edit changes the payload and requires complete re-review.
The final full-file hash is reported in the user handoff rather than embedded
self-referentially.

The design payload uses the exact companion algorithm declared in
`## Plan-Alignment Amendment Review` of the design. Reviewers report both full
file identities and both stable payload hashes. The initial review of this
execution plan legitimately covers a `pending` Implementation Record. Filling
that covered record during implementation changes the plan payload by design;
Task 12 Step 14 therefore requires a second full fixed-payload three-agent
review before acceptance. The initial planning review cannot substitute for
that post-implementation review.

Review dimensions:

1. architecture and dependency order;
2. fidelity to every normative design invariant and non-goal;
3. public/backward compatibility and atomic activation;
4. TDD validity, test isolation, commit/file ownership, and rollback;
5. exact-resolution, projection, ContextPack, trace, and P4 edge cases;
6. target/gold provenance, feasibility, oracle, metric, and decision validity;
7. baseline/candidate comparability, performance, privacy, and comparator
   claims;
8. implementability from the actual repository rather than a hypothetical
   architecture.

A review passes only with zero blocker and zero major findings. Minor findings
must be resolved or explicitly accepted with rationale before the final hash.

## Independent Plan Review Record

### Round 1: Pending

The plan will be sent independently to:

- architecture/contract reviewer;
- IR/evaluation/gold reviewer;
- implementation/TDD/operability reviewer.

Their findings and the corresponding corrections will be recorded here.

### Final Review: Pending

Record the final plan/design hashes, reviewer results, resolved finding count,
and any explicitly accepted minor residual risk here. Do not change the plan
after the final reviewed hash without repeating review.

## Stop Point

This document is a reviewed execution plan only. It does not authorize P7
implementation, repository preparation, private data access, comparator calls,
staging, commits, or roadmap/status changes. Wait for explicit user
authorization after the independent plan review passes.
