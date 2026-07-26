# P7 Retrieval Quality Attribution And Evidence-Set Selection Design

Date: 2026-07-25
Status: Approved direction, revised for plan-review findings; implementation requires a separately reviewed plan
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Roadmap phase: Phase 7
Baseline: `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`
Predecessor: `docs/superpowers/specs/2026-07-18-p6-freshness-performance-large-repositories-design.md`

## Summary

P7 changes how Context Search Tool improves retrieval quality.

The current engine has accumulated capable retrieval primitives: lexical,
semantic, path, symbol, direct-text, signal, graph, planner, controlled
exploration, ContextPack, and trace support. Its remaining quality gap is not
well described by a single aggregate `Recall@K` number, however. The engine
cannot currently answer whether a required evidence span:

1. came from a file that never entered the candidate population;
2. belonged to a candidate file but its target method/type/span never entered;
3. entered as a chunk but ranked below the retained display windows;
4. survived span ranking but its file fell below the surface-pool cutoff;
5. reached a surface pool but was omitted by that surface's selector; or
6. reached a ContextPack item but was cropped or omitted from its excerpts.

Without that attribution, adding another graph, parser, score bonus, planner
prompt, or reranker is guesswork.

P7 therefore has three mandatory deliverables:

1. **Retrieval quality attribution:** an evaluation-only audit records both
   path- and target-span survival through a common retrieval prefix and separate
   `query`, `context`, and `explore` branches. It does not publish source
   content.
2. **A measured route checkpoint:** the frozen baseline compares actual
   terminal attrition with policy-shadow plus file/span-oracle headroom. A
   source-free `BaselineOpportunityRecord` must show cross-repository
   post-acquisition recoverable evidence before file-level selection work may
   proceed. Otherwise P7 stops and redirects to acquisition/controller design
   or benchmark expansion.
3. **An evidence-backed next-step decision:** after the mandatory behavior is
   measured—and, only when separately authorized at the checkpoint, after the
   structural selection candidate is evaluated—a committed decision record
   classifies the remaining gap as acquisition, span/file ordering, visibility
   policy, set selection, pack or excerpt materialization, or no proven
   retrieval gap. That record, rather than the existing phase numbering,
   determines the next implementation spec.

P7 does not attempt to make a one-pass heuristic ranker imitate an open-ended
agent. It also does not add a Python AST, replace the embedding model, introduce
a learned reranker, or make exploration automatic. Existing P4 exploration is
preserved and measured against the same evidence units. If acquisition remains
the dominant failure after P7, the decision record must recommend an
evidence-directed exploration/controller phase instead of more ranking weights.

This document does not authorize implementation. A reviewed implementation
plan is required after this design is approved.

## Decision

Replace the roadmap's former Phase 7 "Optional Product Surfaces" placeholder
with **Retrieval Quality Attribution And Evidence-Set Selection**. Product
surfaces are deferred until the retrieval core can demonstrate where it loses
required evidence.

The conditionally selected product approach, authorized only after the baseline
opportunity checkpoint, is:

- keep chunk-level recall and relevance scoring;
- resolve original exact identifiers in the path/signal acquisition scopes
  (including the declared metadata-only disabled-lane edge) and inject one
  canonical declaration/file chunk for each unique resolution before
  direct-candidate merge;
- introduce an internal, unique-path `FileEvidencePopulation` in the explicit
  RetrievalTrace-v2 `file_projection` stage after context expansion, then let
  `final_selection` construct each bounded `SurfaceFilePool`;
- reserve uniquely resolved original-query identifiers structurally instead of
  competing through another large numeric boost;
- select files lexicographically by explicit evidence, unmet required needs,
  unmet recommended needs, existing evidence order, and stable path;
- introduce RetrievalTrace v2 with one explicit `file_projection` stage because
  v1 cannot truthfully account for multiple expanded chunks becoming one file;
- keep ContextPack v2 and ExplorationTrace v2 field semantics unchanged;
- add an evaluation-only stage audit plus separate file- and span-oracle
  diagnostics;
- forbid general score retuning until the first audit baseline is frozen;
- decide later controller or reranker work from measured stage attrition.

The observation/baseline slice is unconditional once P7 implementation begins.
The product slice is not. A reviewed
`BaselineOpportunityRecord=full_bundle_supported` is necessary but not
sufficient: the repository owner must explicitly authorize continuation after
seeing it. `acquisition_redirect` or `mixed_insufficient` terminates this
implementation plan before any Task-7 product preparation.

The following alternatives are rejected:

- **Continue adding ranking bonuses.** Existing scoring already combines many
  heterogeneous signals. Another bonus can fix one case while changing
  unrelated cohorts, and it cannot recover a file removed before ContextPack.
- **Add Python AST next.** The observed Python gaps do not yet prove that the
  required files were absent from the candidate pool. AST work is justified
  only by acquisition-stage evidence.
- **Install a model reranker immediately.** A reranker cannot fix missing
  candidates, duplicate file-slot consumption, or an under-supplied pack
  candidate universe.
- **Rewrite retrieval around an autonomous model loop.** CST's local,
  deterministic primitives remain valuable. A controller may be the next
  phase, but only after the attribution profile proves an acquisition gap and
  defines the evidence it must acquire.
- **Hide file projection inside RetrievalTrace v1 final selection.** V1's closed
  decision set cannot account for same-path result consolidation. P7 bumps the
  retrieval trace to v2, adds an explicit stage after `context_expansion`, and
  groups context expansion by path for one transient read without moving source
  materialization.
- **Feed hidden pool-only files into ContextPack v2.** Every result-backed
  ContextPack v2 item needs a valid `retrieval_rank` from its own QueryBundle.
  The `context` surface instead builds one wider unique-path QueryBundle when
  the caller does not explicitly constrain `final_top_k`.
- **Treat fast-context overlap as the release gate.** The external service is a
  useful qualitative reference but is not stable, inspectable, or consistently
  available enough to define CST correctness.

## Roadmap Reconciliation

P7 changes the long-term roadmap in one material way: retrieval quality remains
unfinished, so optional dashboards, project memory, and review helpers no
longer precede another quality milestone.

Phase statuses remain independent:

- Phase 1 remains pending at its existing model-quality gate.
- P4 remains the implemented bounded exploration contract.
- P5 remains the implemented language/framework graph contract.
- P6 remains basic-implementation-complete with full release-grade acceptance
  pending.
- P7 may design and implement ranking/selection behavior without claiming P6's
  deferred scale matrix or service/watch decision.

P7 must preserve protected P0-P6 contracts except for this closed set of
reviewed changes:

- the schema-versioned RetrievalTrace v1-to-v2 migration;
- query result path uniqueness/order/membership plus the explicitly disclosed
  file-ordering-score versus display-window association and first-segment
  `spans` projection;
- omitted-budget `context` candidate-boundary behavior, private exact
  reservation, and a possible second existing-schema excerpt.

All public field shapes other than RetrievalTrace remain unchanged. No other
protected contract changes, and fixtures must not be silently refreshed merely
to make the listed changes pass.

## Baseline And Current Evidence

The implementation baseline is clean commit
`74aae0abe3dff685282fbcc785f7a9b3532cbbe6`, the merge of the P6 basic
implementation.

### Existing Pipeline Facts

The current ordinary query pipeline:

1. collects semantic, lexical, path/symbol, direct-text, signal, and planner
   candidates;
2. expands same-file/directory anchors;
3. expands graph and relation candidates;
4. merges by chunk ID;
5. ranks chunks;
6. performs cohort reranking;
7. expands every ranked chunk into source context;
8. takes the first `final_top_k` non-anchor expanded results;
9. builds a ContextPack from that already truncated result list.

The following are code facts, not hypotheses:

- `retrieval_core.selection.split_results_and_anchors` deduplicates evidence
  anchors but appends normal code results until `final_top_k`; it has no
  path-level result deduplication.
- `retrieval_core.expansion._add_same_file_anchor_candidates` can add every
  chunk in an anchor file with `anchor_score * 0.80`.
- those same-file anchor candidates are also relation-expansion seeds;
- `context_pack.roles.normalize_candidates` deduplicates by path only after the
  raw result budget has been spent;
- when duplicate path candidates are merged for ContextPack, reasons are merged
  but independent spans and content windows are not generally preserved;
- the quality evaluator normalizes result paths before computing metrics, so it
  can hide the fact that duplicate chunks consumed public result slots;
- original identifier intent contributes a bounded numeric boost, while
  project/cohort policy can still demote a cross-unit exact file;
- P4 exploration fuses by unique path, but each probe can contribute only files
  that survived that probe's ordinary final selection;
- P4 freezes goals from the initial ContextPack, which itself sees only the
  truncated initial results;
- RetrievalTrace v1 exposes five candidate previews per stage and omitted
  counts. That is appropriate for public diagnostics but insufficient to
  evaluate required-file survival across a 24-64 file audit pool.

### External Comparison Evidence

Two local comparisons motivated this design:

- A public Python-heavy repository at commit
  `487e49e565ffd1b96a7cf4d855f99cee3c981eaa` showed that CST could find
  plausible local matches but often returned an incomplete cross-module
  reading set.
- A private Java multi-module repository showed stronger exact and graph
  behavior, but repeated chunks from one large implementation file and
  cross-unit cohort behavior displaced explicitly named supporting files. Its
  snapshot identity remains only in an uncommitted local report.

The private repository, its query text, source, paths, and raw reports must not
be committed. Only aggregate stage metrics and sanitized case identifiers may
appear in an acceptance decision record.

The comparisons support two hypotheses:

1. some current failures are selection failures because relevant file hints
   appear in planner or trace evidence but not in the final pack;
2. some broad natural-language failures may still be acquisition failures.

P7 must measure both. It must not treat either hypothesis as already proven for
the complete quality catalog.

## Problem Statement

### Chunk Relevance And Evidence-Set Utility Are Different Objectives

A chunk ranker answers:

> Which local span looks most relevant to this query?

An agent-facing context retriever must answer:

> Which bounded set of files and excerpts jointly supplies the evidence needed
> to understand or change the requested behavior?

The best five chunks can all come from one large service implementation. That
may be valid chunk ranking while being a poor reading set. Conversely, a
repository, request interceptor, route, or configuration file can have a lower
standalone score while adding the missing link that makes the set useful.

P7 must keep these objectives separate.

### The Current Quality Loop Observes Too Late

Current metrics are strongest at final results and ContextPack output. They do
not measure the path-level candidate universe before final selection. When
`Recall@10` fails, the project cannot choose rationally among:

- more recall;
- another graph;
- a different score formula;
- a reranker;
- file diversity;
- a wider ContextPack pool;
- better excerpts; or
- a multi-round controller.

P7 must make that choice measurable.

### Exact User Evidence Is Soft When It Should Be Structural

An exact class, method, filename, endpoint, or path written in the original
query is qualitatively different from a planner-generated synonym. It should
not require a sufficiently large additive bonus to survive unrelated soft
policies.

Protection must still be bounded. Common or ambiguous names cannot reserve every
matching file, and generic split tokens such as `Service`, `Impl`, `Manager`, or
`util` are not exact evidence by themselves.

### ContextPack Has The Right Selector But The Wrong Candidate Boundary

ContextPack v2 already reserves candidates that cover required and recommended
evidence needs. The more fundamental issue is that its input is normally the
raw `final_top_k` result list after duplicate chunks may have consumed slots.

P7 should widen and normalize the internal file candidate boundary rather than
create a second unrelated pack-selection algorithm.

## Goals

1. Attribute every labeled required evidence unit at both path and target-span
   granularity through the common retrieval prefix and its applicable
   surface-specific branch.
2. Make public raw results unique by normalized repository-relative file path.
3. Ensure additional non-ordering chunks from one file cannot aggregate into a
   better file selection score.
4. Preserve each uniquely resolved original-query path when its output
   partition can contain it, and prioritize its exact declaration window within
   the separate two-window-per-file capacity.
5. Prevent candidates supported only by traversal-only same-file anchors from
   occupying visible results.
6. Let `context`, when its caller omits `final_top_k`, build its one QueryBundle
   with a wider unique-file candidate limit than ordinary `query`, while keeping
   every ContextPack v2 `retrieval_rank` valid.
7. Reuse ContextPack's evidence-need matching and greedy coverage behavior from
   that surface's QueryBundle.
8. Preserve bounded multiple span evidence for a selected file where the
   existing ContextPack excerpt contract can materialize it safely.
9. Keep `query`, `context`, and `explore` public schemas unchanged and make the
   trace change explicit as RetrievalTrace v2.
10. Keep ordinary exact queries deterministic, local, and within an explicit
    performance regression budget.
11. Add deterministic failure-shaped fixtures and pinned public-repository
    cases for Java, Python, cross-unit exact identifiers, large-file duplicate
    chunks, and excerpt coverage.
12. Produce a versioned P7 decision record that selects the next quality
    mechanism from observed stage attrition.

## Non-Goals

P7 does not:

- add a Python, Go, or Rust AST/plugin;
- change Java/frontend graph schema v5;
- add a new embedding provider or change the default embedding model;
- add a learned, cross-encoder, LLM, or remote reranker;
- add general recursive exploration or a model-driven search controller;
- make P4 exploration automatic for ordinary `query` or `context`;
- compare numeric scores produced by different exploration probes;
- feed files absent from a ContextPack v2 source QueryBundle into that pack;
- widen or redesign P4 fusion in P7;
- move source materialization before ranking or after file selection;
- rewrite the current chunk scoring formula;
- guarantee that every explicit identifier fits when the user requests more
  unique files than the result or pack capacity;
- protect ambiguous identifier matches as if they were unique declarations;
- turn quality evaluation into an LLM-as-judge workflow;
- add a dashboard, daemon, watch mode, project memory, or review-diff helper;
- close P6's deferred large/scale/stress/churn matrix;
- commit private repository source, queries, paths, excerpts, or raw reports;
- claim fast-context parity from a small benchmark.

## Design Principles

### Diagnose Before Optimizing

The first P7 implementation slice adds observation only. Its normal and audited
query projections must be byte-identical. The first stage-attribution baseline
is frozen before ranking or selection behavior changes. That freeze ends at a
mandatory human checkpoint; later product tasks do not run merely because they
were prewritten in a plan.

### Original Query Evidence Is Sovereign

Only evidence literally present in the original query can receive structural
exact protection. Planner rewrites, grep hints, symbol hints, exploration
probes, and discovered relation names remain recall/ranking hints.

A planner may add candidates. It may not remove or downgrade original-query
exact evidence.

### Hard Constraints Before Soft Weights

Unique-path budgets and uniquely resolved explicit identifiers are selection
constraints, not larger score bonuses. Soft score remains useful within the
eligible file population.

### Rank Spans, Select Files, Pack Evidence

Chunks remain the unit for locating relevant spans. Files become the unit for
spending result and ContextPack item budgets. The final pack remains a set of
evidence with one item per path and one or more bounded excerpts.

### No Length Or Chunk-Count Advantage

A file's primary order is inherited from its best chunk under the existing
canonical rank order. Scores from multiple chunks in the same file are never
summed or averaged into a higher file score.

Additional chunks may contribute span coverage and provenance only.

### One Evidence Policy

Runtime required/recommended needs must continue to use the ContextPack
`EvidenceNeed` and `candidate_matches_need` semantics. Retrieval selection must
not invent a second role taxonomy that can disagree with ContextPack.

### Public Trace Is Not The Quality Audit

RetrievalTrace remains a compact, source-free public explanation. P7 explicitly
versions the unavoidable file-projection change as v2. Its evaluation audit is
an internal observer with separate models and artifacts and is not folded into
that public trace.

### Bounded And Local

P7 adds no network call. Exact resolution uses indexed metadata during existing
bounded path/signal acquisition. The file population cannot exceed the bounded
expanded input, and each surface pool retains its existing capacity. Source
reads remain inside the existing `context_expansion` stage; ranked origins are
grouped by normalized path so one transient file body serves that path and is
released before the next path.

### Determinism Is A Correctness Property

Query occurrence order, canonical chunk order, exact-resolution order,
file-population order, surface-pool order, selection order, omission order,
audit metrics, and decision records must be deterministic.

## Terminology

### Evidence Unit

A labeled evaluation requirement representing one piece of information a useful
answer needs, such as an entrypoint, implementation, downstream integration,
type, test, or configuration.

An evidence unit defines one or more exact repository-relative path
alternatives and a target symbol, line range, or bounded literal set. Path
presence and target-span presence are measured separately. Alternatives from
different units are not independently interchangeable: each decision-profile
case also declares the complete coherent evidence-cover variants that are legal
for that case.

Evidence units are evaluation data. They are not injected into production
queries.

### Evidence Cover Variant

A source-authored, frozen assignment from every required evidence-unit ID in
one case to exactly one of that unit's alternative indices. It represents one
coherent way to answer the whole case. Every required alternative used for
scoring must belong to at least one declared variant.

The evaluator may accept any complete declared variant, but it may never form a
new answer by mixing the best independently observed alternative of each unit.
Optional units remain informational and do not participate in the coherent
cover assignment.

### Chunk Candidate

The existing indexed chunk plus accumulated recall and ranking evidence.

### File Evidence Candidate

An internal, unique-path projection of one or more ranked chunks:

```text
file_path
primary_chunk
primary_order
evidence_class
evidence_priority
source_keys
span_refs
role/group classification
project_unit_key
protected_identifier_ids
visibility
```

The type is private to the retrieval core. It is not serialized by CLI or MCP.

### File Evidence Population

The complete ordered set of visible, unique-path `FileEvidenceCandidate`
values emitted by `file_projection`. It is finite because it projects the
already bounded expanded input, but `file_projection` does not truncate it to a
surface capacity.

### Surface File Pool

The protected-first, capacity-bounded subset created by `final_selection` for a
specific result or evidence-anchor partition. Only `final_selection` owns
`final_top_k`, `evidence_anchor_top_k(final_top_k)`, and their omission
decisions.

### Protected Identifier Resolution

A unique indexed declaration or unique exact file/path match derived from an
identifier literal in the original query.

The private resolution record contains:

```text
literal
occurrence_order
state                  unique | ambiguous | missing
match_kind
file_path
declaration_state       unique | ambiguous | missing
declaration_chunk_id
project_unit_key
```

Only path-state `unique` records have `file_path` and `project_unit_key`.
`declaration_chunk_id` exists only when exactly one matching declaration range
remains inside that path. Multiple overloads/declarations in one unique path
protect the path but set `declaration_state=ambiguous`; P7 does not pretend the
first overload is the named span.

### Protected Path Requirement

A private reservation binding a unique original-query resolution to one exact
path and declaration/display chunk. It is not a ContextPack `EvidenceNeed` and
is never serialized as one.

### Evidence Set

The unique paths selected for a raw result list or ContextPack.

### Retrieval Quality Audit

An evaluation-only observer that records counts and evidence-unit hit status at
named stages. It records no source content and is not returned from ordinary
library, CLI, or MCP calls.

### File Oracle

A label-assisted diagnostic that fixes only the minimal acceptable gold path
set and then lets production span retention and ContextPack behavior operate.

### Span Oracle

A stronger label-assisted diagnostic that fixes both the minimal gold path set
and its target spans. It tests excerpt allocation, cropping, byte budgets, and
serialization only. Neither oracle is a production result.

## Target Architecture

```text
Original Query
  -> Query Understanding
       -> original exact identifier literals
       -> planner/query variants as untrusted hints
  -> Multi-Source Chunk Acquisition
       -> semantic / lexical / path / symbol / direct / signal
       -> exact resolution in path/signal acquisition scopes
       -> canonical exact declaration/file chunk injection
       -> traversal anchors
       -> relation expansion
  -> Chunk Merge And Rank
       -> existing score/evidence policy
       -> existing cohort rerank
  -> Context Expansion
       -> existing source-materialization boundary
       -> one transient workspace read per normalized path
       -> restore original ranked-input order after grouped materialization
  -> File Evidence Projection
       -> explicit RetrievalTrace-v2 stage
       -> unique normalized path
       -> best chunk defines order
       -> exact declaration origin prioritizes its expanded window
       -> at most two bounded display windows
       -> exact unique resolution protection
       -> traversal-only visibility filter
  -> File Evidence Population
       -> every visible unique path, no surface-capacity truncation
  -> Final Selection / Surface File Pools
       -> protected paths first when capacity permits
       -> remaining paths by canonical file order
  -> Output-Specific Selection
       -> raw query: unique top-K files
       -> context: wider QueryBundle, then ContextPack-v2 need selection
       -> explore: existing P4 QueryBundle/path fusion, unchanged limits
  -> Public Output
       -> existing QueryBundle / RetrievalTrace v2
       -> existing ContextPack v2 / ExplorationTrace v2

Evaluation-only side channel:

  product leaf protocol (IDs/ranks/booleans/counts only)
       -> frozen Task-6 evaluator closure
       -> frozen gold/variant resolution
       -> query/context/explore finalization
       -> per-surface terminal attrition and metrics
       -> file and span oracle diagnostics
       -> comparison and P7 decision record
```

The candidate product is an execution target, not its own judge. Task 6 freezes
the evaluator closure before behavior activation. Every later baseline or
candidate report is rebuilt by that closure from source-free product leaves;
candidate-resident fixtures, gold resolvers, finalizers, aggregators,
normalizers, schemas, pass booleans, and decision code are never trusted.

## Surface Candidate Boundary

P7 does not add a hidden pool to public `QueryBundle`, and ContextPack v2 never
selects a result-backed file absent from `bundle.results`.

- `query_repository` and `trace_repository` keep their public return types.
- `query` uses the caller/config `final_top_k` as its unique-file output limit.
- `context` still executes retrieval exactly once and calls
  `build_context_pack(bundle, options)` exactly once.
- when a `context` caller explicitly supplies `final_top_k`, that value remains
  its QueryBundle candidate limit;
- before retrieval, the surface resolves
  `requested_max_items = min(config.context.max_items, max_items or
  config.context.max_items)`;
- when a `context` caller omits `final_top_k`, its effective candidate limit is:

```text
max(
  config.retrieval.final_top_k,
  min(64, 4 * requested_max_items)
)
```

- the surface creates one request-local config copy with that limit and then
  resolves existing ContextPack options against the same copy; this keeps the
  effective `max_items` within the result/anchor capacity derived from the
  actual QueryBundle limit;
- CLI `context` is an omitted-`final_top_k` request; MCP retains the distinction
  between a null argument and an explicit positive value;
- every ContextPack v2 result item therefore keeps the existing zero-based
  `retrieval_rank` meaning;
- direct callers of `build_context_pack(bundle, options)` retain existing
  deterministic behavior for the candidates in their supplied bundle;
- `explore` retains P4's existing effective initial/follow-up limits and fusion
  model. It benefits from unique-path results but does not receive a hidden
  wider pool in P7.

This is an intentional default-quality change only for `context` requests that
omit `final_top_k`. Explicit caller budgets remain authoritative.

The resolver is one shared CLI/MCP helper and executes in this non-circular
order:

1. validate the request and compute `requested_max_items` without applying the
   old result/anchor cap;
2. choose explicit `final_top_k` unchanged, or compute the omitted-request
   formula above;
3. create the request-local retrieval config;
4. derive the anchor capacity from that chosen candidate limit;
5. call the existing ContextPack option resolver once against the request-local
   config.

A configured `final_top_k > 64` is never reduced. Tests cover omitted,
explicitly equal-to-default, explicit smaller/larger, configured-above-64, and
invalid request cases.

### Private Protection Transport

P7 does not add a field to the frozen `QueryBundle` dataclass, change the
`query_repository()` signature, or add a parameter to
`build_context_pack(bundle, options)`.

Protection travels through the existing private retrieval-result metadata
convention:

1. internal chunk/file candidates carry `ProtectedPathRequirement` records;
2. the selected `RetrievalResult` or `EvidenceAnchor` stores only the path's
   first protected identifier occurrence as
   `_protected_path_order: int | None = field(default=None, repr=False,
   compare=False)`, a non-serialized constructor-compatible field;
3. `normalize_candidates(bundle)` maps either marker into private
   `ContextCandidate` reservation metadata;
4. the builder reserves those candidates before its existing need-coverage
   loop.

When result and anchor inputs share a canonical path, duplicate normalization
keeps the existing winning content/rank/segment candidate but merges protection
as `min(all non-null _protected_path_order)` across every duplicate. A losing
protected duplicate therefore cannot silently unprotect the winning path.
Normalization never concatenates text or changes the existing content winner.

Raw formatters, trace adapters, equality/representation characterization, and
feedback must ignore the marker, as they already ignore private context content
and role-hint fields. `replace` and `deepcopy` preserve it. P4 fusion treats a
marked initial result or anchor as protected, while its follow-up adapter
defensively clears any such marker. A direct caller that constructs a
QueryBundle has no marker and therefore retains existing behavior.

## Original-Query Identifier Resolution

### Extraction

Identifier extraction must preserve first occurrence order. It must not sort
the final identifier tuple alphabetically.

Eligible literal forms are:

- complete repository-relative paths;
- path suffixes containing at least two exact path components whose final
  component is not a generic directory token;
- filenames accepted by the closed `is_protectable_filename` predicate below;
- qualified identifiers such as `package.Type`, `Type.method`, or
  `module::symbol`;
- PascalCase or camelCase identifiers;
- snake_case identifiers with at least one underscore.

The extractor may reuse the current identifier-intent tokenization but must
retain the original literal and occurrence position. It resolves at most
sixteen distinct eligible literals in first-occurrence order. Later literals
remain ordinary query text but are recorded as `budget_omitted` and cannot
create protection.

The following are not independently protectable:

- a single generic role token such as `service`, `impl`, `manager`,
  `controller`, `repository`, `util`, `helper`, `config`, or `test`;
- a CamelCase component produced only by splitting a larger literal;
- planner-generated text;
- a substring match against an unrelated longer identifier.

All matching is Unicode NFC-normalized. Identifier and path-component case is
preserved. Repository path canonicalization:

- converts separators to `/`;
- removes `.` components and duplicate separators;
- rejects absolute paths and every `..` component;
- does not case-fold according to the host filesystem.

P7 introduces one shared `is_protectable_filename` predicate used by
identifier extraction and tests. A basename is eligible when its case-folded
final suffix is in the exact suffix-key set currently owned by
`scanner._LANGUAGES_BY_SUFFIX`, moved to a shared constant without adding
members, or when its case-folded full name is in:

```text
cargo.lock
dockerfile
go.mod
go.sum
makefile
package-lock.json
pnpm-lock.yaml
pnpm-lock.yml
yarn.lock
pom.xml
build.gradle
build.gradle.kts
settings.gradle
settings.gradle.kts
package.json
pyproject.toml
requirements.txt
cargo.toml
.env
.gitignore
```

No other role classifier implicitly enlarges this set. Eligibility case-folds
only to recognize the suffix/name class; resolution still requires the
case-preserved exact repository filename. Compound names are tested as one full
basename (`package-lock.json`), only the final suffix is considered
(`Foo.java.bak` is ineligible), and a dotfile is eligible only through the
explicit full-name allowlist.

For suffix matching, the normalized literal is split on `/` and compared only
to the same number of trailing components in each active canonical repository
path. Every component must be equal with preserved case; substring, partial
component, wildcard, and host-filesystem case-folded matches are forbidden. A
suffix has at least two components, and its final component must not be one of
the generic directory tokens `src`, `main`, `test`, `tests`, `app`, `lib`,
`java`, `kotlin`, `python`, `javascript`, or `typescript`. Thus
`service/Foo.java` is eligible and can resolve only if that exact
component-boundary suffix identifies one active path, while `src/main` is not.

### Resolution Priority

Each literal resolves in this order:

1. exact normalized repository-relative path;
2. exact component-boundary path suffix satisfying the extraction rule;
3. exact filename including suffix;
4. exact file stem;
5. exact indexed qualified symbol declaration;
6. exact indexed symbol declaration;
7. exact full-literal content occurrence as an unprotected recall fallback.

Declaration signals outrank references. A content occurrence alone never
creates structural protection.

The first priority level with at least one active matching path determines the
resolution set; lower-priority levels neither disambiguate nor make that set
ambiguous. Full-path and suffix matching enumerate active canonical paths
before the existing clause-local project-unit narrowing is applied, so suffix
uniqueness is computed as zero, one, or more-than-one paths rather than as the
first scan hit. The final content level contributes ordinary recall only and
always leaves structural resolution `missing`.

Structural declaration matches use this closed evidence policy:

- active `symbols` rows attached to active chunks are declaration evidence;
- ready structured graph signals are eligible only when `recallable=true`,
  `producer="java_ast"`, and `kind` is `type`, `method`, `field`, or
  `endpoint`;
- `comment`, `usage`, `local`, `parameter`, relation-source occurrences,
  `module`, `route`, and `mybatis_statement` signals never establish unique
  declaration protection;
- legacy/stale/unavailable graph modes may use active `symbols` plus exact
  path/filename/stem matches, but not legacy signal rows as declaration proof;
- uniqueness/ambiguity is computed across all matching active declaration paths
  seen before candidate truncation and stops only after proving zero, one, or at
  least two distinct paths.

Declaration candidates deduplicate by canonical
`(path, start_line, end_line)`. When an active-symbol row and an eligible
structured signal identify the same declaration range, the active-symbol fact
wins the provenance tie; different ranges remain distinct and can make
`declaration_state=ambiguous` within an otherwise unique path. Every retained
declaration carries `resolution_origin=active_symbol` or
`resolution_origin=structured_signal`.

This policy is deliberately conservative. Languages without declaration symbols
can still receive exact path/filename protection and ordinary content recall;
P7 does not pretend a reference occurrence is a declaration.

Resolution is path-based:

- multiple signals in one file count as one resolved path;
- one resolved path is `unique`;
- zero resolved paths is `missing`;
- more than one resolved path is `ambiguous`, unless an explicit path or
  project-unit fragment in the same query narrows it to one path.

Narrowing is clause-local: a path/project-unit fragment can narrow an
identifier only when both occur in the same punctuation- or conjunction-bounded
query clause. A globally mentioned module name cannot silently disambiguate
every identifier in a multi-module query.

#### Clause-Local Narrowing Algorithm

This is a new exact-resolution parser, not a reuse of global
`infer_query_scope`.

1. Extract eligible path, filename, qualified-identifier, identifier, and exact
   active project-unit-fragment spans first. Their character intervals are
   opaque while clauses are split, so `/`, `.`, `::`, `_`, and `-` inside a
   recognized literal are never separators.
2. Outside opaque spans, split on the closed punctuation set newline, `,`, `;`,
   `:`, `.`, `!`, `?`, `，`, `；`, `：`, `。`, `！`, `？`, or on a
   case-folded whole-word conjunction in `and`, `or`, `but`, `then`, `以及`,
   `并且`, `同时`, `或者`, `但是`, `然后`. Whitespace alone does not split a
   clause.
3. A project-unit fragment is recognized only when its NFC text is an exact
   case-preserved active `project_name`, an exact canonical `project_root`, or a
   component-boundary path prefix beginning with that root. Unit kind,
   language, marker, business-role token, and fuzzy/substring matches are never
   narrowing evidence.
4. Each recognized same-clause full/suffix path fragment contributes its exact
   active matching-path set. Each recognized unit fragment contributes the set
   of active paths whose current chunk metadata has that exact
   `(project_root, project_name)`.
5. Intersect every recognized same-clause constraint set with that literal's
   active resolution-path set from its first non-empty priority level. For a
   filename or stem this is the filename/stem path set; only a
   qualified/simple symbol level uses declaration paths. Lower priority levels
   never participate in narrowing. Exactly one surviving path narrows the path
   state; zero survivors, more than one survivor, or conflicting path/unit
   fragments leave the original zero/ambiguous state unchanged. After a unique
   path is chosen, `declaration_state` is computed separately among declaration
   ranges inside that path. Fragment order never breaks a tie.

Active `(path, project_root, project_name)` facts are consumed inside the same
path/symbol metadata pass and connection described below. The outcome does not
retain or return the repository-wide fact table. For each of the at-most-sixteen
eligible literals and each recognized same-clause constraint, it retains only a
saturated `missing | unique | ambiguous` state, at most two canonical
witnesses, and the first active chunk/declaration candidate for a selected
unique path. Unconstrained and each exact-intersection state are accumulated
independently during the pass, so two earlier unconstrained witnesses cannot
hide a later third path that is the sole same-clause survivor. These facts do
not come from the globally inferred query scope and add no separate
project-unit scan. Clause and literal traversal follows original character
occurrence order, then canonical path order.

### Acquisition Injection

Resolution is part of the existing path/symbol and signal acquisition, not a
post-ranking lookup.

For every `unique` resolution, acquisition injects exactly one canonical chunk
before direct-candidate merge:

1. the exact declaration chunk when `declaration_state=unique`;
2. otherwise the first original-query recalled chunk for that path under the
   closed key below;
3. otherwise the first active indexed chunk in that file by
   `(start_line, end_line, chunk_id)`.

Step 2 never compares cross-lane numeric scores. Its domain excludes every
planner rewrite/hint, exploration probe, traversal anchor, and relation
candidate. For each distinct chunk recalled by the literal original-query
calls, retain its best key:

```text
(
  source_precedence,   # path_symbol, signal, direct_text, lexical, semantic
  one_based_lane_return_rank,
  start_line,
  end_line,
  chunk_id,
)
```

The lexicographic minimum wins. Duplicate appearances of one chunk use its
minimum key. `planner_path_symbol`, `planner_signal`, `planner_lexical`, and
`planner_semantic` are not aliases for an allowed source. Therefore planner
availability, text, or score cannot change the canonical injected chunk.

The injected candidate uses an existing trace source:

- exact path/suffix/filename/file-stem resolution uses `path_symbol`;
- an `active_symbol` declaration uses the `path_symbol` candidate and score-part
  semantics from the existing path/symbol scan;
- only a `structured_signal` declaration uses the `signal` candidate and
  score-part semantics from its current graph session.

Protection is carried by the private `ExactResolution` /
`ProtectedPathRequirement`. The injected candidate uses the existing
`path_symbol` or `signal` score-part semantics; P7 adds no public score key and
does not implement protection as a larger relevance score. It never relabels a
symbols-only match as `signal`, and the same declaration range is injected only
once after the precedence rule above.

The audit records acquisition both before and after exact injection so an exact
rescue cannot be mistaken for ordinary semantic/lexical recall.

Structured-signal proof is conditional on the final health of the graph read
session. The exact helper is called once and returns an immutable
`ExactInjectionBatch` with two closed projections:

```text
ready:
  path/symbol exact contributions + structured-signal exact contributions

graph_fault:
  the same pre-merge exact-contribution/fallback facts with every
  structured-signal exact contribution removed
```

Each provisional direct candidate, independently seeded anchor contribution,
and merged winner keeps bounded contribution lineage identifying ordinary
baseline, non-signal exact, and structured-signal exact support. P7 does not
widen the existing anchor-seed policy: `seed_ids` are derived only from
ordinary `direct_text` seeds; a path/symbol or structured-signal exact
contribution never enters that seed set or creates a new anchor by itself. A
structured-signal exact contribution may nevertheless temporarily win the
later merge for a chunk also produced as an anchor from an independent
ordinary direct-text seed.

If relation expansion activates the existing graph-fault fallback,
orchestration selects `graph_fault` and recomputes downstream merge/anchor
winners from the retained surviving lineage. The independently seeded anchor
membership remains, while any signal-exact winning content/provenance is
replaced by the surviving ordinary contribution. The pre-merge helper does not
claim to select winners that do not yet exist.
Orchestration does not rerun resolution, reopen a store/session, repeat anchor
expansion, or perform a second source read. Ordinary baseline signal behavior
that existed before P7 is preserved by its own contribution; only P7
structured-signal exact proof is revoked.

Direct-merge and anchor-expansion trace facts and audit leaf facts are held in
one request-local deferred batch until graph health is final. Timing and work
counters may be observed immediately, but membership, ranks, protected
occurrence order, and provenance are committed atomically from the selected
projection. An abandoned provisional contribution may not appear in either the
public trace or the accepted audit ledger.

Every retrieval ledger records:

```text
exact_injection_mode        shadow | enforced
exact_injection_applied     boolean event
graph_state                 not_applicable | ready | faulted
signal_exact_revoked_count  non-negative integer
```

`exact_injection_mode` is policy state. `exact_injection_applied` is true only
when at least one P7-injected candidate survives the selected final graph
projection into direct merge. Thus an enforced request with no eligible unique
literal, or with only structured-signal exact contributions revoked by a graph
fault, has `mode=enforced` and `applied=false`. A positive revoked count requires
`graph_state=faulted`, no surviving structured-signal exact provenance, and
exact contribution-lineage consistency; it is diagnostic and does not invent a
new terminal attrition reason.

### Snapshot And Work Contract

Exact resolution executes inside the database read scope already used by the
corresponding acquisition stage:

- path/suffix/filename/stem and active-symbol declaration facts are collected
  by the path/symbol metadata pass and use its connection;
- only eligible ready `java_ast` structured-signal declaration facts are
  collected inside the existing `GraphReadSession.signal_search` snapshot;
- legacy signal search retains its ordinary candidate behavior but supplies no
  declaration proof to exact resolution.

When `lexical_top_k > 0`, the path/symbol metadata facts must piggyback on the
already executed pass with zero incremental connection or scan. The existing
configuration also permits `lexical_top_k == 0`, which currently skips that
pass before opening a connection. If such a request contains at least one of
the first sixteen eligible exact literals, P7 intentionally performs exactly
one metadata-only path/symbol pass and one connection for the whole request;
it emits no broad path/symbol recall candidates and returns only resolution
side data plus any canonical exact injection. With no eligible exact literal,
the disabled lane remains fully skipped. This edge is an explicit measured work
change, not a false zero-increment claim.

No configuration may perform a per-literal scan, a second path/symbol pass, or
an extra signal pass. P7 does not claim a new cross-stage transaction boundary
that the baseline query does not have.

The preferred implementation returns bounded exact-resolution side data from
the existing path/symbol and signal candidate helpers alongside their ordinary
bounded candidates. It must not duplicate the active path, chunk, symbol, or
signal tables in memory. During the existing passes it retains only
per-literal/per-clause saturated states, at most two canonical witnesses per
state, selected unique-path first-chunk/declaration candidates, bounded
original-lane rank facts, and measured counters. Constrained states are updated
directly from every matching row rather than derived from a witness list that
may already have saturated. If that cannot satisfy the contract without an
additional schema/index, implementation stops for a reviewed
operational-schema amendment; P7 does not silently add an unmeasured lookup
table.

Focused work-count tests must prove:

- enabled path/symbol and signal lanes add zero scans or connections relative
  to the same baseline query with the same planner state;
- the `lexical_top_k == 0` exact-literal edge adds exactly one shared
  metadata-only path/symbol pass/connection, while the no-exact edge adds zero;
- original-query exact facts come only from the original-token acquisition
  calls, while existing planner-token calls retain their current count and
  source attribution;
- signal resolution shares the graph session and generation identity when the
  query has one;
- path resolution is produced before the existing path-symbol connection
  closes;
- returned-result bounds are not used as a substitute for measured scan work;
- a third matching path/declaration outside the first two witnesses still
  changes an unconstrained state to `ambiguous` and can independently become
  the sole survivor of an exact same-clause path/unit constraint; and
- retained exact side data stays bounded by literals, declared constraints,
  ordinary candidate limits, and the two-witness cap rather than repository
  size.

### Protection Capacity

Let:

```text
R_result = ordered unique protected paths classified as normal results
C_result = final_top_k
R_anchor = ordered unique protected paths classified by the existing
           evidence-anchor policy
C_anchor = evidence_anchor_top_k(final_top_k)
```

Result and anchor protection are applied independently so P7 does not turn a
README/POM/config anchor into a normal code result merely to protect it.

If `len(R_result) <= C_result`, every result path survives. If
`len(R_anchor) <= C_anchor`, every anchor path survives. An over-capacity
partition keeps the first paths by original identifier occurrence order and
records the rest as budget omissions. ContextPack then applies one global
protected reservation over both kinds up to `options.max_items`.

Budget omissions appear as missing evidence/omission diagnostics where the
public schema already permits them. P7 does not expand QueryBundle or
ContextPack schemas solely for this overflow.

Multiple identifiers resolving to one path consume one slot.

### Interaction With Soft Ranking

A protected file:

- is present because its canonical chunk was injected before merge;
- is reserved before non-protected files by the surface's unique-result selector
  and by ContextPack's private protected-path reservation;
- does not receive a project/cohort mismatch penalty that can remove the
  protected path;
- retains its existing numeric score for explanation and ordering among
  non-capacity decisions.

Protection does not propagate automatically to every same-module or related
file. Related files still require their own recall, relation, or evidence-need
support.

## Traversal Anchor Visibility

P7 separates traversal eligibility from display eligibility.

A candidate explicitly marked `traversal_only=True` by same-file anchor
expansion

may seed relation expansion but is not eligible for the visible file evidence
pool.

It becomes display-eligible only if the merged candidate also has at least one
independent source:

- original/planner lexical or semantic recall;
- path/symbol or direct-text recall;
- indexed signal recall;
- resolved relation evidence;
- protected original identifier resolution.

Visibility is based on explicit metadata, not source-name inference:

| candidate evidence | traversal eligible | display eligible |
| --- | --- | --- |
| same-file anchor only | yes | no |
| same-file anchor plus independent evidence | yes | yes |
| resolved relation candidate reached from an anchor | yes | yes |
| current directory anchor | current policy | current policy |
| public evidence anchor | separate anchor policy | separate anchor policy |

Directory/documentation evidence anchors retain their current behavior. The
shared `anchored_relation` string is not sufficient to classify visibility.

`traversal_only` is derived after every evidence merge; it is not a sticky
boolean combined with logical OR. Merge metadata separately records
`same_file_traversal_evidence` and `independent_display_evidence`. Any listed
independent source, or any directory-anchor evidence that is display-eligible
under current policy, sets the latter and makes the merged normal candidate
display-eligible. Only a candidate whose merged evidence remains exclusively
same-file traversal evidence is filtered.

The trace's existing source counts remain truthful. Detailed visibility reasons
belong to the internal P7 audit, not a silent reinterpretation of an existing
public trace reason.

## File Evidence Projection

### Grouping

After existing chunk ranking, cohort reranking, and `context_expansion`,
visible expanded candidates are grouped by canonical repository-relative
`file_path` in the new RetrievalTrace-v2 `file_projection` stage.

The ordering chunk is the first chunk under the existing canonical ranked-chunk
ordering. The file inherits:

- ordering-chunk rerank score;
- ordering-chunk evidence class and priority;
- ordering-chunk score explanation;
- ordering-chunk project unit;
- canonical primary rank.

The file does not add, average, multiply, or otherwise aggregate chunk scores.

### Ordering And Display Windows

File order and displayed evidence are deliberately separate.

Every expanded candidate has two different ranges:

```text
origin_chunk_range    # indexed chunk/declaration provenance
materialized_window   # existing start/end/content after context expansion
```

File projection selects origin candidates but retains their already materialized
windows. It never shrinks a window back to the raw chunk range. It visits every
display-eligible origin in this priority:

1. windows whose origin chunk contains a uniquely resolved exact protected
   declaration, in original-query occurrence order;
2. the ordering chunk's window;
3. all remaining origins in canonical ranked order.

For each origin, an overlapping or adjacent window first coalesces with a
retained segment when the existing bounded context-expansion rule permits it.
A distinct window is added only while fewer than two segments exist. After two
segments, later origins are still visited: they may coalesce without consuming
a slot, otherwise they receive `same_file_span_limit`. Additional omitted
origins cannot improve file order. Thus an exact named method is not displaced
by an unrelated higher-scoring chunk in the same file, while evidence recovered
only through an expanded window remains representable.

Coalescing is transitive. If one new window touches both retained segments, the
implementation first computes their complete union and applies the existing
byte/range bound once. On success, both segments become one, the new input is
`coalesced_same_file_span`, and prior inputs keep their original decisions. On
failure, no partial mutation occurs and the new input is
`same_file_span_limit`. A successful bridge frees one segment slot for a later
distinct window.

Existing materialization semantics are preserved:

- normal requests retain the current `context_lines`-expanded windows;
- `full_file=True` on a source within `max_full_file_bytes` produces one
  coalesced full-file window and therefore preserves the full-file raw result;
- oversized `full_file=True` requests retain the existing byte-capped expanded
  window behavior;
- an unreadable path uses each origin chunk's own indexed fallback window, never
  another chunk's fallback.

For public raw query results, the first materialized window supplies
`start_line`, `end_line`, and `content`. For ContextPack, both retained windows
may produce existing-schema excerpts when its per-item/excerpt/total/pack
budgets permit them.

`RetrievalResult` and `EvidenceAnchor` add one private, non-serialized,
constructor-compatible field:

```text
_context_segments: tuple[RetrievalContextSegment, ...] = field(
  default=(),
  repr=False,
  compare=False,
)
# () is the legacy sentinel; P7-produced values have length 1..2

RetrievalContextSegment:
  start_line
  end_line
  content
  origin_spans: tuple[RetrievalSpan, ...]  # normal: 1..8; anchor: 0..8
```

Each segment is the already materialized context window belonging to one
retained/coalesced display window. Segments are ordered like display windows,
non-overlapping after coalescing, individually byte-bounded, and validated
against its line range. Every `origin_span` is finite, has non-empty existing
sources, and is fully contained in that segment. When more than eight origins
compete, retention chooses protected-identifier occurrence order, then the
ordering chunk, then canonical ranked-chunk order, deduplicated by exact range.
The retained spans are then stored through the current
`(start_line, end_line, -score, sources)` normalization so direct Python
line-order semantics do not become priority order. At most eight spans per
segment survive; further focus spans are counted by the audit and do not alter
file order. Any bounded content union was already determined by display-window
coalescing and is not undone merely because a focus span is omitted.

The public-shaped `RetrievalResult.start_line`, `end_line`, `content`, and
`spans` remain the first segment and that segment's retained origin spans.
Existing `_context_content` remains the first segment's content for
compatibility. `normalize_candidates` copies both segments into equally private
`ContextCandidate` state while leaving its ordinary fields as the first
segment.

An empty tuple is accepted only as a legacy/direct-construction sentinel.
Normalization synthesizes exactly one segment from the existing public
start/end, `_context_content or content`, and spans. A legacy normal result with
no spans receives the same synthetic full-range `legacy_result` span that the
current builder creates; a legacy evidence anchor keeps an empty span tuple and
the current anchor-window path. `ContextCandidate` adds the same default-empty
private field, so existing constructors and direct
`build_context_pack(bundle, options)` callers remain source-compatible and
produce their pre-P7 single-view behavior. A non-empty tuple is authoritative;
invalid mixed or partially populated segment state fails with the existing
bounded ContextPack error.

ContextPack never concatenates disjoint segment text. Full need matching calls
the existing `candidate_matches_need` semantics once per segment with that
segment's content; a need is covered when one complete segment matches, and
tokens on opposite sides of a gap cannot form a synthetic match. Excerpt
windowing likewise constructs a separate source view from each segment and
uses only that segment's `origin_spans`. Window merge is segment-local; the
resulting windows are globally ordered by the existing window rank before
existing excerpt/item/pack limits and cropping apply. Every emitted excerpt is
contained in exactly one segment, so a secondary target cannot be focused or
cropped using the first segment's spans. The builder remains I/O-free.

Raw formatters expose only the first display window and ignore the private
tuple.

Materialization failure exposes no raw exception. Excess exact declarations and
bounded-window failures are recorded as target-span
retention/materialization attrition.

This uses ContextPack v2's existing multiple-excerpt contract. It does not add
multiple raw `RetrievalResult` objects for one path.

### Surface Pool Capacity

`file_projection` emits every display-eligible unique normal file from its
bounded expanded input and performs no capacity truncation. `final_selection`
is the sole owner of capacity and constructs the normal-result surface file
pool for one retrieval execution from that population. Its capacity is the
execution's effective `final_top_k`:

- `query` and `trace` use their existing effective value;
- explicit `context final_top_k` is respected exactly;
- default `context` uses the wider candidate value from
  `Surface Candidate Boundary`;
- `explore` uses P4's existing effective limits.

There is no second hidden pool behind the QueryBundle and no earlier projection
cutoff that can pre-empt `final_selection`. Protected paths are reserved first
up to capacity; remaining files follow canonical file order. Evidence anchors
remain outside the normal-file population and use the existing
`evidence_anchor_top_k(final_top_k)` partition, with the same protected-first
rule inside that partition. Both bounded surface pools then appear in the one
QueryBundle that ContextPack normalizes.

The audit distinguishes order from hard policy:

- a protected result/anchor beyond its partition capacity in occurrence order is
  `protected_capacity_overflow`;
- an unprotected normal result with `canonical_file_rank > capacity` is
  `canonical_file_rank_below_cutoff`;
- an unprotected anchor with `canonical_anchor_rank > anchor_capacity` is
  `anchor_rank_below_cutoff`;
- an unprotected normal result with `canonical_file_rank <= capacity` and
  `effective_file_pool_rank > capacity`, or an unprotected anchor with
  `canonical_anchor_rank <= anchor_capacity` and
  `effective_anchor_pool_rank > anchor_capacity`, is
  `protected_reservation_displacement`.

These conditions are mutually exclusive and evaluated in that order. Both
canonical and effective partition ranks are retained; a reservation
displacement or anchor cutoff is not reported as a chunk-reranking failure.

### Materialization Order

RetrievalTrace-v2 stage order is:

```text
ranking
  -> cohort_rerank
  -> context_expansion
  -> file_projection
  -> final_selection
```

`context_expansion` first records every ranked input's original zero-based
position and groups input references by canonical path in first-position order.
For one path at a time it performs at most one `stat` and one `read_text`,
materializes every ranked origin for that path from the same observation, and
then releases the full file body before processing the next path. Materialized
bounded windows are placed back into their original input positions before the
existing overlap merge, so grouping I/O does not change ranking, winner,
coalescing, or trace order.

The transient per-path state is exactly:

```text
Readable(path) -> file_size, full_text  # released after this path's origins
Unreadable(path) -> failure sentinel    # retained only as small status metadata
```

`stat` success followed by `read_text` failure becomes `Unreadable`. The
sentinel suppresses repeated workspace I/O but is never a substitute full-file
body: every origin in that path group falls back to its own indexed chunk
content. The request never retains a dictionary of all source-file bodies.
The measured gate is
`peak_additional_transient_source_read_buffers <= 1`. It increments at the
grouped-read seam when one full source body is acquired and decrements when
that path is released; it is not inferred from garbage collection or process
RSS. Already-retained bounded expanded windows are downstream result bytes, not
transient full-source read buffers, and are measured separately as
`retained_output_bytes` under existing candidate/window limits and the paired
RSS gate. File projection still occurs afterwards, and `final_selection`
spends surface capacity over file candidates plus existing evidence anchors.
P7 does not claim selection-before-materialization performance.

## RetrievalTrace v2 Migration

File-level projection cannot be represented honestly by RetrievalTrace v1's
closed final-selection decisions. P7 therefore changes only the retrieval trace
schema to version 2.

V2 inserts `file_projection` after `context_expansion`. For every expanded input
it records exactly one closed decision:

```text
ordering_and_display
ordering_only
additional_display_span
coalesced_same_file_span
same_file_span_limit
traversal_only_filtered
evidence_anchor_passthrough
```

The decisions are mutually exclusive in this order:

| decision | exact meaning for one expanded input |
| --- | --- |
| `evidence_anchor_passthrough` | input has the existing public evidence-anchor classification and passes unchanged to the anchor population |
| `traversal_only_filtered` | normal input has traversal-only evidence and no independent display evidence |
| `ordering_and_display` | first canonical display-eligible input for a normal path; it defines file order and contributes to a retained display segment |
| `ordering_only` | first canonical display-eligible input for a normal path; it defines file order but two higher-priority exact windows exclude its materialized window |
| `additional_display_span` | later same-path input contributes any separately retained display segment, whether it becomes first or second under display-priority order |
| `coalesced_same_file_span` | later same-path input contributes origin/content to a retained segment under the existing bounded coalescing rule |
| `same_file_span_limit` | every other display-eligible same-path input after the ordering input; its window cannot be retained or coalesced within the two-segment/origin bounds |

The first matching row is recorded. A normal file contributes exactly one
`ordering_and_display` or `ordering_only` input. Therefore
`output_count == ordering_and_display + ordering_only +
evidence_anchor_passthrough`; the other decisions explain consumed inputs but
do not add outputs.

The decision counts sum to that stage's `input_count`. Its `output_count` is the
number of unique normal file candidates plus passed-through evidence anchors.
Its `top_candidates` tuple is always empty: a v1-shaped `TraceCandidate` cannot
truthfully combine an ordering chunk's ID/score with a different first display
range. Counts and decisions explain the whole stage, while selected composite
provenance is carried only by v2 `TraceSelection`. Evidence anchors retain their
existing separate policy. This stage emits all unique normal files from its
input plus every passed-through anchor; it never applies `final_top_k` or the
anchor limit.

Every anchor input is a passthrough output at this stage, including anchors that
the existing final selector later recognizes as duplicate
`(anchor_kind, path)` values. Consequently `output_count` is unique
display-eligible normal paths plus `evidence_anchor_passthrough` inputs. Anchor
deduplication and its `duplicate_anchor` decision remain exclusively in
`final_selection`; `file_projection` never claims a unique-across-all-kinds
count.

The stage has one global output order, not separate normal/anchor rank spaces.
Each visible normal file is positioned at its first display-eligible expanded
input; each passthrough anchor is positioned at its own input. Sorting by that
one-based input position, then selection kind and canonical path as defensive
ties, produces contiguous one-based `file_projection` ranks.
Later same-file inputs contribute decisions/provenance but no second output.
Partition-local canonical/effective file and anchor ranks exist only in the
quality audit.

`final_selection` receives that complete population and the passthrough
anchors, reserves protected paths, constructs the two bounded surface pools,
and applies the result/anchor limits. Because normal file candidates are
already unique, its selection and limit decisions remain truthful; same-path
chunk consolidation is never misreported as `result_limit`.

The result and anchor pools keep their own QueryBundle list order, but
`TraceSelection.rank` remains one contiguous global order. Final trace order is
a deterministic two-way head merge:

1. take the current head of the selected result list and selected anchor list;
2. emit the head with the lower
   `(file_projection_rank, kind_tiebreak, file_path)`, where result sorts before
   anchor only on a defensive tie;
3. advance only that list and repeat.

This preserves the exact relative order of `bundle.results` and
`bundle.evidence_anchors` as trace subsequences while defining one unambiguous
global final rank. When neither partition was reordered by protection, it
reconstructs the existing interleaved projection order. P4 continues to use
this global final rank as its probe-local source rank; partition-local
canonical/effective ranks remain audit-only.

V2 adds these required `TraceSelection` fields for both selection kinds:

```text
ordering_chunk_id: str
display_origin_chunk_ids: tuple[str, ...]
origin_chunk_omitted_count: int
```

The in-memory model also carries:

```text
_canonical_origin_chunk_ids: tuple[str, ...] = field(
  default=(),
  repr=False,
  compare=False,
)
_legacy_probe_origin_chunk_ids: tuple[str, ...] = field(
  default=(),
  repr=False,
  compare=False,
)
```

Neither tuple is serialized. P7's trace producer fills
`_canonical_origin_chunk_ids` with the full winner-first selection provenance
before the public eight-origin projection. It fills
`_legacy_probe_origin_chunk_ids` with exactly the pre-P7 accumulated
`chunk_ids` order of the selected ordering expanded item only. The legacy tuple
does not add secondary file-projection display origins.

Internal P4 origin loading uses `_legacy_probe_origin_chunk_ids` when present
and falls back to public `origin_chunk_ids` for legacy/directly constructed
traces. Every P4 loop that loads chunks, symbols, signals, relations, or source
paths uses that same legacy tuple. Thus a given selected ordering expanded item
retains its pre-P7 probe seed membership and order even when canonical v2
provenance is winner-first or publicly truncated. P4 must not use
`_canonical_origin_chunk_ids`, display origins, or the omitted count to create
seeds.

An empty `_canonical_origin_chunk_ids` is a valid direct-construction sentinel
only when `origin_chunk_omitted_count == 0`; validation then treats public
`origin_chunk_ids` as the complete canonical tuple. A positive omitted count
requires non-empty private canonical provenance and exact recomputation or the
v2 trace is rejected.

Context expansion also carries a private, non-serialized
`winner_chunk_id`. A single expanded chunk initializes it to its own ID; an
overlap merge copies it from the same `_expanded_result_sort_key` winner that
supplies rerank score, score parts, reasons, and adjustments. It must occur in
the merged origin-ID set. Neither merge order nor the first accumulated
`chunk_ids` entry may substitute for this winner.

The complete origin order is the stable distinct union of the ordering origin
followed by the origins contributing display windows, ordered by retained
segment and then canonical chunk rank. `origin_chunk_ids` exposes the first
eight IDs in that complete order. `display_origin_chunk_ids` exposes, in
display order, only contributing IDs that remain in that disclosed eight.
`origin_chunk_omitted_count` is exactly the complete distinct origin count
minus `len(origin_chunk_ids)`. The count is never inferred from preview
truncation, both origin-ID tuples are non-empty and contain no duplicate, and
`origin_chunk_ids[0] == ordering_chunk_id`.

For a selected normal result:

- `start_line`, `end_line`, and raw public content refer to the first display
  span;
- `score`, adjustments, file order, and every rank before final selection
  refer only to the ordering chunk;
- `ordering_chunk_id` is that expanded ordering candidate's
  `winner_chunk_id`;
- display origins are the ranked chunks retained in either display segment;
- rank history is
  `ranking -> cohort_rerank -> context_expansion -> file_projection ->
  final_selection`.

For a selected `EvidenceAnchor`, file projection is a one-input/one-output
passthrough:

- `start_line`, `end_line`, score, adjustments, selection reason, and public
  materialization retain their existing v1 anchor meanings;
- `ordering_chunk_id` is the anchor expanded candidate's
  `winner_chunk_id`, whose existing score and adjustments the anchor exposes;
  v2 deliberately moves that winner to `origin_chunk_ids[0]` even when v1's
  accumulated merge-origin order began with another chunk;
- display origins are the existing canonical origins that contribute that
  anchor's materialized window;
- the `file_projection` rank is its position in the single interleaved global
  stage output defined above, and rank history contains the same five canonical
  stages as a normal result;
- it is never grouped into the normal-file population or deduplicated against a
  normal result during `file_projection`; existing anchor handling remains in
  `final_selection`.

For both kinds, sources, variants, and reasons are the stable bounded union over
the disclosed `origin_chunk_ids` only, so an omitted same-file origin cannot
silently alter the explanation. Validation recomputes the disclosed order and
omitted count from `_canonical_origin_chunk_ids` before serialization.

V2 keeps the five-candidate preview limit for every preview-bearing stage,
twenty final selections, twenty-four adjustments, total duration semantics, and
source-free/privacy rules. `file_projection` is the one explicitly
non-preview-bearing composite stage. The existing sixteen-stage ceiling already
fits the new total of sixteen stages.

P3's v1 fixtures remain immutable migration inputs. New tests compare v1
baseline and v2 projections field by field and approve only the version,
`file_projection`, winner-consistent rank-history, and provenance deltas listed
above. Consumers must branch on `schema_version`; P7 does not serialize both
versions from one request.

## Evidence-Set Selection

### Need Derivation

ContextPack continues to derive `EvidenceNeed` from its QueryBundle exactly
once. P7 does not add a path constraint to public `EvidenceNeed` and does not
pretend its category/subject matching can express an exact file requirement.

Unique original identifiers instead create private
`ProtectedPathRequirement` values. ContextPack reserves matching protected
`ContextCandidate` paths by `_protected_path_order`, then source order and
canonical path, before normal required/recommended need coverage. Existing
explicit-role and structural needs retain their current semantics.

The new `_protected_path_order` is independent of the existing
`protected_direct` flag derived from `evidence_priority == 0`; P7 does not
reinterpret or overwrite that score-part contract. Exact-path reservations run
first, and the existing protected-direct/need behavior then runs unchanged for
remaining capacity.

### Selection Order

Raw query selection is intentionally simple:

1. reserve protected exact paths in query occurrence order;
2. fill remaining slots by canonical file order;
3. emit one first-display-window result per path.

ContextPack first reserves private protected paths by
`(_protected_path_order, source_order, file_path)` up to `max_items` inside each
invocation of the existing blocked-match retry loop. Coverage for a reserved
candidate is its segment-aware `full_matches` minus the loop's current
`blocked_matches`. Before ordinary greedy selection, those covered IDs are
removed from both `unmatched_required` and `unmatched_recommended`; the
unreserved candidates therefore cannot spend another slot merely to cover a
need already satisfied by a reservation.

Every reserved candidate becomes an ordinary `_SelectedCandidate`: it carries
that filtered `matched_need_ids`, participates in preferred-excerpt building,
byte fitting, blocked-match retry, final item linking, and omission accounting,
and receives a stable priority with a protected prefix:

```text
protected:   (0, protected_path_order, source_order, file_path)
unprotected: (1, *existing_rank_tuple)
```

The unreserved candidates and remaining capacity then pass through the existing
v2 selector without changing the relative ranking of any two unprotected
candidates. At each existing greedy step that suffix rank tuple remains:

1. count of currently uncovered required needs;
2. count of currently uncovered recommended needs;
3. the existing static promoted-group position;
4. result evidence before evidence-anchor fallback;
5. existing retrieval rank or anchor source order;
6. normalized path.

Required need gain still outranks any number of recommended need gains. P7 does
not introduce dynamic group/role novelty or change default-noise filtering,
blocked-match retry, reading order, omission order, or excerpt retry semantics.
After a candidate is selected, the existing selector removes every need it
covers from the uncovered sets. A path is never selected twice.

### Cross-Probe Evidence

P4 exploration continues to fuse by path. Numeric scores from different query
strings are not compared.

The initial P4 query enables original-query exact resolution. Every follow-up
retrieval call executes inside an internal
`retrieval_core.exact_intent.protection_disabled()` context manager; probe text,
planner text, and discovered identifiers may retain ordinary recall behavior but
cannot create a new `ProtectedPathRequirement`.

The guard uses a `ContextVar`, rejects nesting, and resets its token in `finally`
for success, early return, cancellation, and exception paths. It changes no
public retrieval/trace signature. The follow-up adapter also strips any private
protection marker defensively. Initial protected results and anchors keep their
marker through `replace`, `deepcopy`, and P4 fusion, and the fusion
protected-result/anchor predicate recognizes it.

While the guard is active, exact-resolution side-data collection and the
`lexical_top_k == 0` metadata-only edge are both disabled. Existing enabled
ordinary recall lanes still run with their current candidate behavior, but a
follow-up never incurs work solely to create protection that it is forbidden to
use.

P4 otherwise keeps its current QueryBundle fusion, frozen goals, per-probe
source rank, origin model, path limits, and one-pack-build-per accepted
candidate behavior in P7. Optimizing or widening that fusion is a separately
trace-versioned controller phase.

### Missing Evidence

ContextPack continues to report `missing_evidence`, `next_queries`, confidence,
and omissions under schema version 2.

P7 must distinguish internally:

- a required target path absent from chunk acquisition;
- a target path present but its required span absent;
- a target span acquired but not retained for display;
- a visible file below the surface candidate cutoff;
- a context candidate omitted by pack policy or capacity;
- a packed file whose required excerpt was cropped or omitted.

Only meanings already representable by ContextPack v2 are exposed publicly.
The complete distinction is recorded by the evaluation audit.

## Retrieval Quality Audit

### Boundary

The audit is enabled only by the frozen Task-6 evaluation driver and focused
tests. Product code exposes a read-only leaf observer consulted by private
retrieval-stage seams; it does not own gold interpretation, terminal
finalization, metrics, comparison, or acceptance.

Normal query, trace, context, and explore calls do not construct or retain audit
path ledgers.

Audited and non-audited executions with the same inputs must produce
byte-identical behavioral payloads. Each evaluation envelope separates:

- a validated identity/control envelope containing run role/ID/timestamps,
  product commit/tree, source/index/config identity, behavior contract, audit
  mode, and audit-output presence;
- a non-voting timing envelope; and
- a content-free behavioral payload containing public output/error and work
  counters.

Identity/control and timing values are bound into the proof but are never
pretended to be equal across roles. Equality compares only the schema-defined
behavioral payload; it does not delete arbitrary JSON pointers or normalize
away product identity. Request, case, ledger, and leaf IDs inside repeatable
facts are deterministic functions of profile case ID, surface, and retrieval
ordinal rather than process-local UUIDs.

The frozen `query_repository()`/`trace_repository()` signatures and
`QueryBundle` return contract do not change. Instead, an internal
`retrieval_core.audit.capture(observer)` context manager installs a
`contextvars.ContextVar` observer for the dynamic extent of one quality-runner
surface call:

- stage hooks are no-ops when the context variable is unset;
- each retrieval call appends one unfinished `RetrievalAuditLedger`;
- tokens are reset in `finally`, including early-return and exception paths;
- thread/task concurrency is isolated by `ContextVar`, and one observer cannot
  be nested inside another;
- the observer receives immutable IDs, ranks, booleans, and counts, never source
  content.

The product worker returns a closed, source-free leaf protocol according to the
surface:

```text
query:
  capture one retrieval ledger
  -> emit content-free query leaves plus canonical-public-byte hashes

context:
  capture one retrieval ledger
  -> emit retrieval and final stable pack/excerpt IDs/ranges/structure

explore:
  capture one ledger per actual P4 retrieval call
  -> emit content-free initial/follow-up/fusion/final-pack/final-excerpt leaves
```

The frozen request may carry the gold-frozen query into the product process,
but the response binds it only by opaque ID/hash and never echoes query, source,
snippet, or excerpt-content bytes.

The frozen evaluator closure at the Task-6 audit-instrumentation commit owns:

- the case parser and two-state gold-provenance resolver;
- coherent evidence-cover-variant selection and witness validation;
- query/context/explore finalization and the closed terminal-reason mapping;
- metrics, aggregation, normalization, schemas, privacy scanners, reports,
  comparisons, and the P7 decision algorithm.

The evaluator verifies the product commit/tree/import root and leaf-protocol
version before a case runs, checks ledger count against actual retrieval count,
and recomputes every derived field. The product worker shim, surface-call
orchestration, observer capture, and leaf serializer are themselves frozen
inside the Task-6 closure. The shim imports the explicit product root and calls
only the already supported façade under test; the candidate does not supply or
modify an evaluation adapter. Later behavior may populate only protocol fields
that Task 6 already declared through production observer hooks, and the frozen
shim cross-checks those leaves against public output and work counters.

The frozen closure contains a separate immutable-product-protocol manifest for
the observer seam and every ledger/leaf enum, envelope model, and validator.
Their candidate Git blobs must equal the Task-6 instrumentation blobs; a
same-version semantic edit requires a new baseline. Planned retrieval,
ContextPack, and exploration hook call sites remain product behavior under test
and are checked by exact decision accounting plus public-output/work-counter
cross-checks.

Every later baseline/candidate evaluation, comparison, publication, and
decision command executes from that exact frozen closure. The candidate
supplies only the product implementation under test; it cannot supply
evaluation orchestration, leaf serialization, policy, or pass/fail claims.

Every unfinished product ledger and observer reference is destroyed after leaf
emission. `not_applicable` leaves serialize as `null`; the frozen evaluator
never treats them as misses.

### Common Retrieval Prefix

For every evidence alternative, the audit records:

1. `path_acquired_before_exact`: an ordinary pre-injection direct candidate has
   its exact gold path;
2. `target_span_acquired_before_exact`: such a candidate span fully covers the
   canonical gold target range;
3. `path_acquired_after_exact`: the path exists after exact injection and direct
   merge;
4. `target_span_acquired_after_exact`: a direct candidate chunk fully covers the
   target after injection;
5. `path_acquired`: the path exists in the final merged chunk population after
   anchor and relation acquisition;
6. `target_span_acquired`: a final merged candidate chunk fully covers the
   target;
7. `best_target_chunk_rank`: the one-based canonical ranked-chunk rank, or
   `null`;
8. `target_span_present_after_context_expansion`: at least one expanded
   candidate window fully covers the target, regardless of visibility;
9. `file_visible`: at least one display-eligible expanded candidate exists for
   the path;
10. `target_span_display_eligible`: at least one display-eligible expanded
    candidate window fully covers the target;
11. `target_span_retained`: a retained display window fully covers the target;
12. `candidate_kind`: `result` or `evidence_anchor` under the existing anchor
    classification;
13. for a result, `canonical_file_rank` over the complete file population and
    `effective_file_pool_rank` inside the protected-first surface pool; for an
    anchor, `canonical_anchor_rank` and `effective_anchor_pool_rank`; the
    non-applicable pair is `null`;
14. `surface_candidate_pooled`: the path survives its result or anchor
    partition's effective candidate limit, with one closed omission reason when
    false.

Target location is evaluated against the fixture's resolved canonical range;
declared literals are additionally required at the materialized surface. Path
presence or partial range overlap never satisfies a target.

`target_recovered_by_context_expansion` is true when stage 6 is false and stage
8 is true. This recovery is provenance, not a miss.

In the serialized ledger, fields 9-14 and
`target_recovered_by_context_expansion` use the `policy_` prefix. They are
computed by the shared P7 visibility/projection/selection policy described
below. Actual emitted-result, pack, excerpt, and terminal-satisfaction fields
use the `actual_` prefix. This prevents a counterfactual baseline policy rank
from being mistaken for an output that baseline code actually emitted.

### Behavior-Baseline Shadow Semantics

Slice 0 implements the future pure visibility, two-window projection, and
protected-first capacity helpers behind an audit-only seam before freezing the
baseline. It also collects read-only exact-resolution side data under the
declared enabled/disabled-lane work contract and derives the future
traversal-only boolean without mutating a production candidate. Slice 1/2 must
call these exact same helpers to enforce behavior; they may not reimplement the
shadow algorithm.

Slice 0 attributes the old selector without applying those helpers to public
behavior. Its audit therefore records:

```text
exact_injection_mode = shadow
exact_injection_applied = false
file_projection_mode = shadow
```

On that baseline:

- `*_after_exact` equals the ordinary direct-acquisition state; resolution may
  be observed, but no chunk is injected;
- every `policy_*` visibility, display-window, file-rank, and surface-pool field
  is computed read-only from the actual expanded sequence by the frozen shared
  helper, including exact-window priority and protected reservation;
- every `actual_*` raw/pack/explore selection, materialization, and terminal
  field inspects the actual baseline output;
- file and span oracles use the same frozen policy helper, but never replace the
  actual baseline terminal result.

A file eligible in the shadow projection but absent from the actual
chunk-budgeted baseline output is consequently attributed to that surface's
selection stage in the shadow lane only. The runner constructs an isolated
shadow QueryBundle and, for `context`/`explore`, an isolated shadow pack/fusion
  projection without replacing or mutating actual outputs. Candidate runs set
  `exact_injection_mode=enforced` and `file_projection_mode=enforced`;
  `exact_injection_applied` remains the per-retrieval surviving-injection event
  defined above and may legitimately be false. Reports never claim that the
  shadow policy executed in commit `74aae0a...`.

Every baseline unit therefore has two non-interchangeable reason fields:

```text
actual_terminal_reason
policy_shadow_terminal_reason
```

`actual_terminal_reason` is finalized solely from acquisition/expansion facts
and the actual legacy QueryBundle/pack/exploration output.
`policy_shadow_terminal_reason` is finalized solely from the isolated future
policy projection. If baseline actually selected a path that shadow policy
would filter or displace, the former can report actual
materialization/pack/excerpt loss while the latter reports
visibility/reservation loss; neither overwrites the other. Enforced candidate
runs set `policy_shadow_terminal_reason=null` and use the complete policy chain
for `actual_terminal_reason`.

Acceptance cohorts, baseline/candidate paired comparisons, regressions, and
decision votes use only `actual_terminal_reason` and actual terminal
satisfaction. Shadow reasons are diagnostic and may motivate a case tag but
never vote. Policy-stage fields are compared only as shadow-helper
characterization when the helper identity/hash matches. The helper hash and
both mode fields are frozen with the baseline.

### Surface DAG

The common prefix then branches:

```text
common:
  ordinary -> exact -> final path/span acquisition
    -> chunk rank
    -> expanded target presence
    -> target/file visibility
    -> display-window retention
    -> canonical/effective file order and pool

query:
  result_file_pooled | anchor_pooled
    -> raw_selected
    -> raw_target_materialized

context:
  result_file_pooled | anchor_pooled
    -> pack_selected
    -> pack_item
    -> excerpt_satisfied

explore:
  initial common prefix
    -> zero or more follow-up common prefixes
    -> target_acquired_by_any_probe
    -> fused_selected
    -> final_pack_item
    -> final_excerpt_satisfied
```

`context` does not depend on `raw_selected`. `explore` reports initial survival,
any-follow-up survival, and final fusion survival separately.

`pack_selected` and `final_pack_item` refer only to the builder's final stable
selection after any blocked-match retry/reselection loop. A candidate selected
in an abandoned intermediate iteration is not counted as selected.

The audit also records:

- total chunk candidates;
- total unique acquired paths;
- visible/invisible path counts;
- same-file traversal-only path count;
- complete file-population size plus final surface-pool size, cutoff rank, and
  omitted count;
- raw result count, pre-normalization unique path count, and duplicate slot
  count;
- pack item and excerpt counts;
- protected identifier states: `unique`, `ambiguous`, `missing`, `budget_omitted`;
- exact-injection rescue count;
- stage duration from existing timing observers where available.

### Per-Surface Terminal Attrition

Each required evidence unit receives exactly one `actual_terminal_reason` for
each executed surface, never one reason shared across surfaces. A behavior
baseline additionally receives one separate `policy_shadow_terminal_reason`;
an enforced candidate does not.

The finalizer checks terminal surface satisfaction first. A final result that
fully contains the canonical range/literals is `satisfied` even if the target
arrived only through a context-expansion window; its recovery provenance remains
visible in the stage record.

For a case with alternatives, each lane's frozen finalizer evaluates its own
full ordered condition chain for every declared coherent evidence-cover
variant. It never reads a field from the other lane and never combines
alternative choices from two variants.

A case is terminally satisfied only when every required choice in at least one
complete declared variant is satisfied. For attribution, the finalizer selects
one variant lexicographically by:

1. greatest number of terminally satisfied required choices;
2. greatest minimum reached-condition depth across required choices;
3. greatest sum of reached-condition depths;
4. greatest reached-depth tuple after sorting depths descending and comparing
   the tuples lexicographically; and
5. smallest semantic variant key, computed from the sorted canonical
   `(role, alternative path, target range, literal hashes)` choices without
   evidence-unit IDs, variant IDs, or declaration order.

The chosen variant supplies exactly one alternative and one terminal reason for
each required unit. The first failed condition of that chosen alternative
determines its reason. Unit metrics, case votes, and classification all use this
one coherent attribution variant; per-alternative observations may be retained
only as bounded non-voting diagnostics. If variants tied through criterion 4
have different terminal reason-group multisets, raw unit diagnostics use the
semantic-key winner but that case's classification vote is `case_mixed`.
Shadow and actual lanes choose independently. Property tests permute unit
declaration order and rename safe unit/variant IDs and require the same semantic
winner, reason multiset, and classification. Counts therefore remain mutually
exclusive without letting order, naming, a weak alternative, a cross-variant
“Frankenstein” cover, or a shadow fact mask an actual failure.

Optional units never enter a cover variant, required denominator, case vote,
gate, or classification. For bounded diagnostic metrics only, each optional
unit evaluates its alternatives independently, chooses greatest
reached-condition depth, then the smallest order/ID-independent semantic
`(role, path, target range, literal hashes)` key, and records that one
non-voting result. Alternative/unit IDs and declaration order cannot select it.

| first failed condition | query reason | context reason |
| --- | --- | --- |
| gold path absent after acquisition | `path_not_acquired` | `path_not_acquired` |
| path present, target absent from acquisition and expansion | `target_span_not_acquired` | `target_span_not_acquired` |
| acquired target is lost while materializing/merging/cropping context windows | `target_span_lost_during_context_expansion` | `target_span_lost_during_context_expansion` |
| expanded target has no display-eligible carrier | `target_span_visibility_filtered` | `target_span_visibility_filtered` |
| display-eligible target falls outside retained spans | `target_span_lost_in_file_projection` | `target_span_lost_in_file_projection` |
| protected result/anchor exceeds its partition capacity in occurrence order | `protected_capacity_overflow` | `protected_capacity_overflow` |
| unprotected normal result has canonical rank beyond its partition capacity | `canonical_file_rank_below_cutoff` | `canonical_file_rank_below_cutoff` |
| unprotected evidence anchor has canonical rank beyond its anchor-partition capacity | `anchor_rank_below_cutoff` | `anchor_rank_below_cutoff` |
| unprotected result/anchor is canonically within capacity but displaced by protected reservations in its partition | `protected_reservation_displacement` | `protected_reservation_displacement` |
| pooled file not emitted/selected | `raw_selection` | `pack_selection` |
| emitted/selected but no item | `raw_materialization` | `pack_budget_or_policy` |
| item exists but no single excerpt fully covers the canonical range and all literals | not applicable | `excerpt_allocation_or_cropping` |
| terminal target is present | `satisfied` | `satisfied` |

The table above is the enforced-policy chain and the baseline shadow chain. The
baseline actual chain omits the future-only visibility, file-projection,
canonical/effective pool-rank, reservation, and protected-capacity rows. After
actual context expansion it examines only the actual surface:

- absent actual raw output is `raw_selection`; a raw item whose public window
  lacks the target is `raw_materialization`;
- absent actual ContextPack item is `pack_selection` when the actual bundle
  lacks the path, otherwise `pack_budget_or_policy`; a present item without a
  satisfying excerpt is `excerpt_allocation_or_cropping`;
- explore analogously uses its actual all-probes acquisition, fusion,
  final-pack, and final-excerpt reasons.

Thus a baseline path that shadow would have rejected can never receive a shadow
visibility/capacity reason in `actual_terminal_reason`.

Explore uses the same common reasons with these additional terminal reasons:

- `path_not_acquired_after_all_probes`;
- `target_span_not_acquired_after_all_probes`;
- `fused_selection`;
- `final_pack_budget_or_policy`;
- `final_excerpt_allocation_or_cropping`;
- `satisfied_initially`;
- `satisfied_by_followup`.

`final_excerpt_allocation_or_cropping` likewise means that no single final
excerpt fully contains the canonical range and all literals; unions of partial
excerpts never satisfy or bypass the terminal chain.

`target_span_lost_during_context_expansion` is a source-window
materialization/merge/cropping loss; ranking is not blamed because every ranked
chunk enters the current expansion stage. `target_span_lost_in_file_projection`
is the bounded display-window selection policy. Target-level visibility is
never inferred from another visible chunk in the same file.

### Privacy

The committed audit report contains:

- repository case ID;
- evidence-unit ID;
- boolean stage survival;
- first attrition reason;
- aggregate counts and ratios;
- configuration and commit identities;
- normalized timing statistics.

It does not contain:

- source content or excerpts;
- private query text;
- private repository paths or filenames;
- planner prompts or responses;
- generated probes;
- local absolute paths.

Public fixture reports may include public repository-relative result paths in
the existing quality-report section. Private overlay reports remain
uncommitted; only aggregate metrics may be copied into the decision record.

## Quality Case Contract

P7 introduces quality fixture schema version 2 while retaining a read path for
existing schema-v1 fixtures. Only v2 cases can participate in P7 stage
attribution.

Conceptual case shape:

```json
{
  "id": "authorization-flow",
  "surface": "context",
  "intent_cohort": "exact_identifier",
  "identifier_expectations": [
    {
      "id": "authorization-interceptor",
      "literal": "AuthorizationInterceptor",
      "occurrence_index": 18,
      "expected_state": "unique",
      "expected_declaration_state": "unique",
      "expected_path": "src/main/java/example/AuthorizationInterceptor.java"
    }
  ],
  "evidence_units": [
    {
      "id": "authorization-entry",
      "required": true,
      "role": "entrypoint",
      "protected_by": "authorization-interceptor",
      "alternatives": [
        {
          "path": "src/main/java/example/AuthorizationInterceptor.java",
          "target": {
            "symbol": "preHandle",
            "literals": ["boolean preHandle"]
          }
        }
      ]
    }
  ],
  "evidence_cover_variants": [
    {
      "id": "interceptor-flow",
      "choices": [
        {
          "evidence_unit_id": "authorization-entry",
          "alternative_index": 0
        }
      ]
    }
  ]
}
```

Evidence-unit contract:

- a case contains at most 16 evidence units;
- a case declares exactly one surface: `query`, `context`, or `explore`;
- a case declares exactly one closed `intent_cohort`:
  `exact_identifier` or `exploratory_cross_module`; free-form intent tags are
  forbidden for P7 voting;
- `exact_identifier` requires at least one extractor-valid
  `IdentifierExpectation` and at least one required unit protected by it;
  `exploratory_cross_module` requires every score-eligible coherent variant to
  cover at least two canonical paths and two evidence roles or project units;
- a mixed natural-language request still declares one reviewed primary intent
  plus a source-authored rationale and counts once; it cannot enter both intent
  quotas or cast duplicate cohort votes;
- `id` is 1-64 lowercase ASCII letters, digits, hyphen, or underscore and is
  unique within the case;
- `required` is boolean;
- `role` is one of `entrypoint`, `implementation`, `downstream`, `type`,
  `test`, `config`, or `supporting`;
- `alternatives` contains one to four alternatives;
- every alternative uses one exact canonical repository-relative `path`, not a
  `glob` or `contains` matcher;
- each alternative has a `target` containing at least one location selector:
  - exact indexed `symbol`;
  - one-based inclusive `line_range`;
  and may additionally contain one to three exact `literals`;
- `symbol` must resolve to one active declaration in that exact path; an
  overloaded/duplicate symbol requires `line_range` to disambiguate;
- `line_range` must be inside the pinned source file; when both location
  selectors exist, the declaration range must overlap it;
- preflight resolves every alternative to exactly one continuous
  `canonical_target_range`: the declared line range when present, otherwise the
  unique symbol declaration range;
- the canonical range contains 1-80 lines and at least one active indexed chunk
  fully covers it; for `query` its source slice must fit one permitted raw
  materialized window, while for `context`/`explore` it must fit one configured
  excerpt; a broader requirement must be split into separate evidence units;
- path/span acquisition and retention require one candidate/materialized window to
  fully cover the canonical range, not merely touch some other part of the same
  file;
- literals are NFC-normalized, case-sensitive, 4-160 Unicode code points, have
  no control characters, must all occur inside the canonical target range, and
  are ANDed;
- terminal raw/pack/excerpt satisfaction requires complete canonical-range
  coverage plus every declared literal; literals are content checks, not
  substitutes for a target location;
- raw satisfaction requires the first public window to contain them; context or
  explore satisfaction requires one excerpt in the matching item to contain
  the complete range and all literals, not a union of partial excerpts;
- multiple distant required ranges in one file are separate units. Their joint
  feasibility is validated against surface and partition rules: a normal
  `context`/`explore` result may use two display windows, while raw results and
  evidence anchors retain only one final materialized window;
- a case declares one to 64 `evidence_cover_variants`; each has a unique safe
  ID and maps every required unit exactly once to a valid zero-based alternative
  index, in canonical evidence-unit order;
- that declared mapping order is canonical serialization/backlink structure
  only; feasibility, attribution, oracle materialization, and gates compare
  order/ID-independent semantic choice keys;
- duplicate variant choice tuples are rejected, and every alternative that is
  eligible for required-unit scoring appears in at least one variant;
- a required unit is attributed only through the one coherent variant selected
  by the frozen finalizer; complete case satisfaction requires all required
  choices of one declared variant;
- optional units contribute metrics but do not fail a required gate.

Identifier expectation contract:

- `identifier_expectations` contains zero to 16 entries independently of
  evidence units, so ambiguous and missing literals do not need a fake gold
  target path;
- expectation IDs follow the evidence-unit ID syntax and are unique in a case;
- `literal` and zero-based Unicode-code-point `occurrence_index` must match
  exactly one output of the frozen P7 extractor when run over the NFC-normalized
  original query: the same complete literal at the same occurrence, among the
  first sixteen distinct eligible outputs in occurrence order;
- preflight invokes that extractor and rejects expectations that are merely a
  substring of a longer identifier, split CamelCase components, generic tokens,
  excluded filename forms, duplicates, outputs beyond the first-sixteen cap, or
  literals absent at the declared occurrence;
- duplicate `(literal, occurrence_index)` expectations are rejected;
- `expected_state` is `unique`, `ambiguous`, or `missing`;
- `expected_path` is required only for `unique`, must be a canonical active
  repository-relative path, and is forbidden otherwise;
- `expected_declaration_state` is required for `unique` and is `unique`,
  `ambiguous`, or `missing`; it is forbidden for non-unique path states;
- an evidence unit's optional `protected_by` references one `unique`
  expectation whose expected path occurs in that unit's alternatives;
- evaluation gates extraction, resolution state, unique resolved path, and
  post-resolution survival separately.

Negative extraction assertions are not `IdentifierExpectation` values.
Deterministic mechanics may use a separate closed
`IdentifierExclusionExpectation(literal, occurrence_index, exclusion_reason)`
schema; it is forbidden from the public decision profile and never contributes
recall or classification.

Anti-gaming validation:

- reject duplicate required units with the same canonical
  `(alternatives, targets)` projection;
- reject missing, partial, duplicate, unknown-unit, out-of-range, or
  non-canonical evidence-cover variants;
- canonical target ranges of multiple required units on one path must be
  non-overlapping; overlapping requirements are one unit and cannot be split
  into several literal variants to increase vote weight;
- preflight verifies every exact path exists at the pinned source commit;
- preflight verifies each target resolves to at least one indexed/source span;
- the gold-feasibility preflight below must find at least one declared coherent
  variant that fits item, display-window, excerpt, content, and pack-byte
  budgets; otherwise the case is invalid rather than an expected miss.

Gold provenance has two immutable on-disk states and one runtime join.
`GoldFreezeInputs` is written before its commit exists and contains:

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
targeted_improvement_eligibility_contract_hash
anti_special_casing_forbidden_manifest_hash
metamorphic_transform_manifest_hash
feasibility_contract_version
feasibility_helper_closure_hash
feasibility_options_hash
feasible_cover_manifest_hash
acceptance_and_decision_contract_hash
```

After that exact input file and all referenced blobs are committed,
`GoldProvenanceSeal` records exactly its schema version,
`gold_freeze_commit`, the `GoldFreezeInputs` Git blob hash, and a closed sorted
path-to-Git-blob-hash map for every source manifest, fixture/profile/config,
variant, transform, label review, helper closure, options, witness, threshold,
and decision-contract input named above.
The frozen resolver reads both exact files from one explicit provenance root,
verifies them against the named Git objects, rejects unknown/duplicate/conflict
fields and current-worktree substitution, and constructs the only runnable
`ResolvedGoldProvenance`. Its canonical hash is domain-separated over both
states. Pre-seal inputs are accepted only by authoring/preflight; run, compare,
publish, and decide APIs accept only the resolved type.

The author and reviewer must be distinct. Mechanical deterministic fixtures may
use repository-owned test identities; public decision cases require an
independent read-only label review.

The frozen manifest contains one `FeasibleCoverWitness` per case:

```text
surface
declared_variant_id
declared_variant_index
ordered (evidence_unit_id, chosen_alternative_index)
canonical (path, target_start, target_end, literal_hashes)
result_or_anchor_partition
coalesced_display_ranges
query_first_public_range | context_excerpt_ranges
per_excerpt_utf8_bytes
per_item_content_bytes
total_content_bytes
canonical_pack_bytes
effective_result_anchor_item_excerpt_limits
```

The witness stores hashes, ranges, counts, and indices, never source content.
`feasible_cover_hash` covers its canonical serialization.

The decision runner verifies that `gold_freeze_commit` contains the recorded
fixture, manifest, helper, options, and witness hashes and is an ancestor of the
candidate commit. Comparator records include run identity and UTC time later
than the freeze. A correction creates a new freeze commit and reviewer
approval, then reports its separate effect on the old baseline and current
candidate; booleans that merely assert "labeled before" are insufficient.

## Metrics

Let `E` be required evidence units for a case. For applicable stage `S`:

```text
RequiredEvidenceRecall(S) =
  required choices from the frozen finalizer's coherent attribution variant
  satisfying S / len(E)
```

Each report stores raw `(hits, total)`, unit-micro recall, and case-macro recall.
It also records the selected coherent variant ID for each actual/shadow lane and
surface. A report is invalid if any contributing unit came from a different
variant.
Stage applicability is declared by surface before execution. Non-applicable
stages serialize as `null` and are excluded by that declaration; a `null` in an
applicable stage invalidates the report rather than silently shrinking a
phase-decision denominator.

P7 records:

- path recall before and after exact injection;
- target-span recall before and after exact injection;
- final merged target-span acquisition and context-expansion recovery recall;
- target-span display-eligibility recall;
- target-span retention recall;
- pooled-result and pooled-anchor recall;
- surface terminal recall for query/context/explore;
- pack-item and excerpt recall for applicable surfaces;
- `best_target_chunk_rank`, canonical/effective result-file rank, and
  canonical/effective anchor-rank distributions;
- identifier extraction recall;
- identifier resolution-state accuracy;
- unique-path declaration-state accuracy;
- unique-resolution path accuracy;
- conditional protected-path survival;
- exact budget-omission count;
- raw result duplication/fill metrics;
- file- and span-oracle recall;
- existing latency, MRR, Recall@K, noise, goal-gain, and trace metrics.

Raw result metrics are computed before `normalize_results`:

```text
raw_duplicate_slot_count =
  raw_result_count - raw_unique_path_count

unique_path_ratio =
  raw_unique_path_count / raw_result_count

result_fill_ratio =
  raw_unique_path_count /
  min(output_capacity, eligible_unique_file_count)
```

`eligible_unique_file_count` is the normal-file
`FileEvidencePopulation` count after chunk ranking, context expansion, and
target-independent display-visibility filtering, but before
`final_selection`, protected reservation, or the surface-pool cutoff. It never
includes evidence anchors. A selector cannot improve this metric by redefining
the eligible population after seeing its output.

An empty denominator serializes as `null`. `unique_path_ratio == 1.0` is valid
only together with the required `result_fill_ratio` gate.

The old proposed `evidence_set_precision` name is rejected because gold evidence
labels are not an exhaustive relevance judgment. P7 may report
`labeled_evidence_path_ratio` as informational only. Noise remains gated by
explicit negative matchers.

Aggregate reports separate:

- required vs optional evidence;
- query vs context vs explore surface;
- the closed exact-identifier vs exploratory-cross-module intent cohort;
- the source manifest's closed Java vs Python vs frontend/generic language
  family;
- deterministic mechanics vs fixed public decision vs predeclared public
  paraphrase/robustness cohort vs private local overlay.

## File And Span Oracle Diagnostics

### Gold-Feasibility Preflight

Before gold freeze, a label-assisted preflight chooses one declared coherent
evidence-cover variant and verifies that the whole variant can fit the case's
pinned surface configuration and budgets. It uses the versioned Slice-0 reference
visibility/materialization/packing helper, not whatever helper happens to exist
in a later candidate checkout. Its canonical code hash and resolved options
hash are part of gold provenance.

For each declared variant, it:

1. groups canonical target ranges by path;
2. coalesces only overlapping/adjacent ranges under the frozen P7 range rule;
3. classifies each path through the frozen result/evidence-anchor policy;
4. applies the exact surface-specific feasibility contract below;
5. uses the frozen reference materialization, UTF-8 cropping, and, where
   applicable, canonical JSON byte accounting;
6. requires every canonical range and literal to survive one complete terminal
   item/window/excerpt rather than a union of partial fragments.

Surface-specific feasibility is closed:

- `query` applies its pinned normal-result and evidence-anchor partition
  capacities. Each selected path has one public first window, so every required
  unit assigned to the same path must fit that same first reference-shaped
  materialized window; the private second window cannot make raw gold feasible.
- `context` applies its effective QueryBundle result/anchor capacities, then
  `max_items`; a normal result path may use at most two display windows, but an
  evidence-anchor path retains its current single selected materialized window.
  It then applies `max_excerpts_per_item`, excerpt bytes, item-content bytes,
  total-content bytes, and final pack bytes.
- `explore` applies P4's pinned initial/follow-up/fusion result and anchor path
  ceilings without adding oracle retrieval calls, then applies the same
  normal-two-window/anchor-one-window final ContextPack, item, excerpt, and byte
  limits.

Consequently, two distant raw-query targets in one file invalidate that
assignment unless one permitted first materialized window contains both. The
same targets may be feasible for `context` or `explore` only on a normal-result
path whose two segments and excerpts fit all applicable budgets. On an
evidence-anchor path, all assigned targets must fit its one current-policy
materialized window.

The chosen feasible cover minimizes, in order:

1. path count;
2. non-overlapping range count;
3. canonical pack bytes;
4. ordered canonical path tuple;
5. an order/ID-independent semantic variant key over sorted
   `(partition, role, canonical path, target range, sorted literal hashes)`
   choices.

Declared variant IDs/indices, unit IDs, and alternative indices are retained
only as source-backlink diagnostics and are covered by the full witness-file
hash. They never break a feasibility tie, determine materialization priority,
or enter the semantic witness hash used by oracles and gates. Semantically
duplicate variants therefore produce the same semantic choices even if fixture
variant/unit order changes or IDs are renamed.

The validator does not manufacture the Cartesian product of independent unit
alternatives. It validates at most `max_declared_cover_variants = 64` exact
source-authored variants in declared order, with no branch-and-bound or
candidate-dependent search. Crossing the cap is an invalid fixture; truncation
or a partial cover is forbidden. If no declared variant is feasible, benchmark
setup fails before baseline or candidate execution. This is the only
oracle-related condition that invalidates gold for capacity.

The selected semantic assignment and its full bounded budget proof are
serialized as the `FeasibleCoverWitness`, with declared variant ID/index and
alternative indices as diagnostic backlinks, and reviewed before freeze. Its
separate semantic hash excludes those backlinks. Baseline, candidate, and
external-comparator runs never rerun feasibility-cover search. They validate
the witness with the frozen reference helper/hash; file/span oracles force its
exact chosen alternatives. Ordinary production and comparator terminal scoring
still accepts any frozen complete declared variant under the evidence-unit
contract and does not confuse that with choosing a new capacity witness. A source,
options, or witness mismatch invalidates that run; it does not authorize the
candidate to replace the witness. If candidate production materialization or
packing cannot satisfy a still-valid span-oracle witness, that oracle result is
a candidate defect, not invalid gold.

### File Oracle

The file oracle forces only the chosen feasible path set through the relevant
result/anchor pool; it does not reveal canonical target ranges to chunk/span
ordering.

For each forced normal file:

- already acquired production chunks retain their production order;
- every other active indexed chunk is appended at a fixed oracle floor in
  `(start_line, end_line, chunk_id)` order;
- target labels and literal locations do not affect that order;
- the path is forced selected independently of file rank, because this oracle
  idealizes path acquisition/set membership;
- production visibility and two-span projection run; `query` then evaluates its
  first public window, while `context` and `explore` run their production final
  ContextPack selection, excerpt allocation, cropping, and byte budgets.

Forced evidence anchors retain their existing anchor classification and use
canonical path order. Oracle-only source/force metadata is evaluation state and
never enters a public trace or production candidate.

It diagnoses span selection and packing after path selection is idealized.

### Span Oracle

The span oracle forces the same feasible paths, treats each chosen canonical
gold range as a mandatory origin, and materializes its display window through
the same `context_lines`/`full_file`/byte-cap rules in semantic canonical order
`(partition, canonical path, start, end, sorted literal hashes, role)`. Unit and
variant IDs are backlink labels only and cannot affect window/excerpt priority.
A `query` case then exposes only the production first public window. `context`
and `explore` cases run production ContextPack selection, excerpt allocation,
cropping, byte budgets, and serialization.

Mandatory origins do not widen an anchor contract. A normal result may
materialize up to the two witness windows; an evidence anchor must place every
assigned target in its single witness/materialized window. A second distant
anchor target is rejected by preflight rather than fabricated by the oracle.

It idealizes path and span acquisition, then diagnoses the production
ContextPack selector, excerpt allocator, budgets, and serialization. The
surface audit distinguishes those terminal causes. It is explicitly
label-assisted.

Interpretation:

- low production path recall with high file-oracle recall indicates acquisition
  or file/set-selection loss;
- high file-oracle path recall with low file-oracle excerpt recall indicates
  target-span ranking/retention or pack behavior;
- high file-oracle failure with successful span oracle isolates target-span
  selection;
- span-oracle failure after a successful feasibility preflight is a real
  pack/excerpt allocation or serialization defect, not an invalid fixture;
- only gold-feasibility failure blocks benchmark setup.

Oracle results are diagnostics, never production candidates and never input to
automatic tuning.

## Benchmark Matrix

### Deterministic Committed Fixtures

P7 adds failure-shaped repositories for:

1. one large implementation file producing many independently ranked chunks,
   plus a lower-ranked entrypoint and downstream file;
2. five exact identifiers distributed across two project units;
3. an ambiguous common class name that must not reserve multiple files;
4. a planner hint rejected by repo-profile filtering while the same literal in
   the original query still resolves;
5. a generic Python route-to-handler-to-sender flow without a Python AST;
6. a selected file whose required method is outside the ordering chunk but
   inside the bounded secondary span;
7. a same-file anchor that is useful for relation traversal but has no
   independent display evidence;
8. more unique exact identifiers than the output capacity, proving deterministic
   occurrence-order overflow.

These fixtures are small enough for deterministic hash embeddings and no model
planner. They gate mechanics only and are excluded from phase-bottleneck
classification.

### Pinned Public Repositories

Required non-CI or scheduled acceptance profiles include:

- Spring PetClinic pinned to
  `51045d1648dad955df586150c1a1a6e22ef400c2`, retaining the existing P5
  prepared-source tree/content identity checks;
- the public `ZhuLinsen/daily_stock_analysis` repository pinned to
  `487e49e565ffd1b96a7cf4d855f99cee3c981eaa`;
- the already tracked frontend snapshot at
  `https://github.com/Flobby949/context-search-tool`, CST commit
  `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`, subtree
  `tests/fixtures/real_projects/program_tool`, Git object
  `a8c0ace36cf82e2c743f06726944f20ce740000f`.

Every source-manifest entry has the closed field
`independence_class=independent_external | in_project_fixture`. PetClinic and
daily_stock_analysis are `independent_external`; the third identity is public
and reproducible but is a CST subtree and therefore `in_project_fixture`. Its
source manifest also records `license_status=not_declared`: the CST tree at the
pinned commit has no license file, so P7 makes no licensing claim and does not
copy material beyond the already tracked evaluation fixture. CST cases count
toward case/unit/profile quotas, but neither global nor cohort dominance may
use them to satisfy the two-repository support minimum. Every dominant
classification must have supporting case votes from two distinct
`independent_external` source IDs.

Every public case declares evidence units and a clean source commit. The runner
must clone/copy into an isolated workspace; it must not use dirty local working
tree content as acceptance evidence.

The fixed `p7_decision` profile must contain at least:

- three public repositories;
- eighteen cases and forty-eight required evidence units;
- five Java and five Python cases, each language contributing at least twelve
  required units;
- six exact-identifier and six exploratory/cross-module cases;
- four query, eight context, and four exploration cases.

Those intent quotas are computed only from the closed case-level
`intent_cohort`, and language quotas are computed only from the source
manifest's closed `language_family`. Open tags cannot satisfy either quota or
enter a voting cohort.

At least six cases form a predeclared paraphrase/robustness cohort that did not
motivate the mandatory P7 rules. It is visible in the repository and therefore
must never be described as hidden holdout evidence. Gold labels are written
from pinned source and task meaning, reviewed, and frozen before running either
the P7 candidate implementation or the external comparator.

At least three of those cases have a frozen metamorphic companion generated
before candidate execution. The transform preserves task meaning while changing
non-semantic query wording and deterministically renaming non-protected source
paths/import references in an isolated copy. The frozen evaluator requires the
same coherent terminal evidence result modulo the recorded rename map. A static
anti-special-casing sentinel also rejects decision-case IDs, full query strings,
canonical target paths, target symbols, every
`IdentifierExpectation.literal`, reviewed high-information target literals,
identifier-to-path maps, or fixture/profile hashes embedded anywhere in the
complete candidate production tree. A frozen explicit allowlist may exempt
only independently reviewed generic CST vocabulary and is part of the
forbidden-manifest hash; it cannot exempt a case-specific tuple or mapping.
There is no mutable candidate adapter exemption; only the Task-6 frozen
worker/closure is outside that tree and is protected by exact blob identity.
These checks reduce direct benchmark special-casing; they do not turn a public
benchmark into an unseen test set.

Each transform is an exact manifest of canonical non-protected path renames and
before/after-hashed import/path-reference edits. It cannot rename a protected
identifier, target symbol/literal, root, symlink, or case-only path. A fresh
source and index copy is created per companion, checked by one closed offline
language-family syntax/import validator, target/literal re-resolution, expected
source-tree hash, and expected index/options hash. Base run copies are never
rewritten in place.

The Task-6-frozen robustness runner evaluates at least three required companions
through the frozen worker shim, compares their complete coherent variant and
terminal evidence to the already validated base result modulo the rename map,
and scans the complete candidate production tree with a closed literal/JSON/
single-layer base64-or-hex sentinel grammar. Scanner tests include at least one
plain identifier dispatch, one identifier-to-path map, and one
`(symbol,literal,path)` tuple. The resulting source-free
`RobustnessSummary v1` and aggregate pass are mandatory decision inputs. The
sentinel reduces obvious special-casing; it is not a proof against arbitrary
obfuscation.

Decision reports provide both unit-micro and case-macro metrics. Phase
classification uses this fixed profile, never deterministic fixtures.

### Private Local Overlay

A local-only profile may point to a private repository through environment
variables and an uncommitted fixture overlay. It is an optional diagnostic,
never a portable or owner-facing acceptance gate, never votes, and never
changes `public_classification`, `selected_classification`, or
`selected_next_phase`. P7 reports this limitation instead of treating one
private repository as cross-repository evidence.

A configured pre-candidate overlay has two local-only seals. Before its
diagnostic baseline runs, `private-gold-seal` in
`pre_candidate_baseline` mode binds the exact fixture/profile/targets/coherent
variants, private feasible-cover witness, prepared source/index/options,
threshold contract, a secret anti-special-casing needle manifest, and distinct
label-author/reviewer identities. This mode forbids a candidate attempt
identity and is the only mode that may enter a `private-freeze-record`. The
private evaluator accepts that resolved local seal, not an unsealed fixture plus
the public provenance root. After the baseline, the ignored freeze record binds
the private-gold seal, frozen evaluator/public-gold identities, owner review
identity, freeze time, and sanitized baseline summary.

The committed public baseline projection identity records the closed
`private_prefreeze_state=paired_frozen | unavailable`, a closed commitment
scheme ID, and a nullable commitment. For `paired_frozen`, the commitment is:

```text
SHA-256(
  "p7-private-prefreeze-v1\0" ||
  random_256_bit_local_salt ||
  canonical_private_gold_seal ||
  canonical_private_freeze_record ||
  baseline_attempt_identity_hash
)
```

The salt and both private bytes remain local; the public commitment is a
one-way continuity proof rather than a raw private-input hash. `unavailable`
requires a null commitment. `paired_frozen` is legal only when both local seals
and a successful baseline diagnostic existed before candidate behavior work.
`unavailable` is legal only when all private configuration was absent. Partial
configuration or an execution, provenance, schema, privacy, or neutrality
failure makes that baseline attempt incomplete; an expected retrieval miss or
low recall does not. The selected state and commitment are immutable after
baseline promotion.

Task-12 reads the committed state before inspecting local files. For
`paired_frozen`, it must match both seals byte-for-byte, consume the sealed
baseline summary, verify the local salt/bytes against the committed
domain-separated commitment, and run only the candidate side. A missing
record/salt or commitment mismatch cannot be downgraded to `unavailable` or
`late_informational`; it yields the safe status `failed_missing_record` or
`failed_commitment_mismatch`. Configuration drift or a candidate diagnostic
failure yields another closed `failed` reason. These failures are reported but
do not change the public decision.

A newly supplied overlay after an `unavailable` freeze requires a distinct
`private-gold-seal` `late_informational` mode. That mode requires and binds the
current candidate-attempt identity, is created no earlier than the attempt,
cannot enter a freeze record or baseline comparison, and authorizes only the
same attempt's late diagnostic/summary.

Private execution uses a separate allowlist summarizer. The full quality report
must not be nested, copied, or written inside the repository. Raw audit,
fixture, repository, seal, secret-needle, and match evidence stay only below
the selected ignored baseline/candidate attempt roots. The tracked decision
binds only the sanitized summary hash and its closed status:

```text
paired_frozen | late_informational | unavailable | failed
```

For a completed diagnostic, the source-free summary may contain case/unit/miss
counts, aggregate stage recall, reason-group counts, case-vote counts,
supporting-case counts, unique-path ratio, normalized latency, invariant
outcomes, and a descriptive classification/proof hash. For `unavailable` or
`failed`, metric fields are absent rather than fabricated. No
eligibility-to-vote field exists; all modes are non-voting.

Two independent local scans are mandatory whenever a paired or late overlay is
evaluated:

- the sanitized-output privacy scanner rejects private query, identifier,
  relative/absolute path, symbol, high-information literal, planner hint,
  repository origin, local username, and fixture-path leakage;
- the same Task-6-frozen production-tree scanner uses the private gold seal's
  secret case IDs, full queries, identifiers, target paths, target symbols, and
  high-information target literals. Raw needles and matches remain local; the
  summary exposes only scanner-rule hash, candidate-tree hash, zero-match
  boolean/count, and privacy pass.

A production-tree private-needle match blocks P7 acceptance as benchmark
special-casing. A privacy-scan failure blocks publication until the frozen
summarizer can emit a safe `failed` summary without sensitive content. These
integrity/privacy gates do not make private retrieval results vote-capable.

### External Comparator

When available, fast-context may be run on the same public commits and queries.
Gold remains frozen before this run. Both tools are evaluated at the same
per-case `K` frozen in the gold/profile contract. The wrapper normalizes
repository-relative paths with the same canonicalizer, keeps first occurrence,
deduplicates, truncates over-return to the first `K`, and separately counts
short-return, over-return, malformed, and duplicate entries. The raw local
envelope and sanitized summary both bind the exact per-case K manifest hash.

The external command never receives a shared candidate repository as writable
state. The wrapper creates a comparator-only source copy below the current
attempt, supplies dedicated `HOME`/XDG/temp/cache/index roots, binds the source
commit/tree plus the closed attempt-owned path manifest before invocation, and
revalidates source bytes, commit, clean state, and known non-cache attempt paths
after every case and at completion. A detected source or closed-path mutation
fails comparator provenance. P7 does not claim this wrapper confines arbitrary
absolute writes without a separately named OS-sandbox backend; comparator
failure remains non-gating to CST quality. The report may record:

- returned path count;
- `path_evidence_recall_at_k`;
- `span_evidence_recall_at_k` when ranges/snippets are available;
- overlap/Jaccard with CST's final pack;
- wall-clock latency with retry disclosure;
- truncation, failures, malformed responses, service version/config when
  exposed, and retry count.

The comparator parser maps each bounded returned canonical path/range to gold
leaves and runs the same frozen coherent-variant selector used for CST. A
path-only response has `span=null`; path recall must not combine one variant's
path with another variant's span. Comparator output is qualitative and
non-gating. CST acceptance cannot depend on remote availability or unpublished
implementation behavior. Jaccard is descriptive only because different
coherent evidence variants can both satisfy the gold units.

## Baseline Freeze

Before any P7 behavior change, one immutable baseline attempt must:

1. implement the source-free audit leaf protocol, evidence-unit/variant parsing,
   two-state gold resolver, and complete evaluator;
2. freeze an exact path-to-Git-blob evaluator-closure manifest covering the
   driver, worker protocol, gold/case resolver, oracle, finalizer, metrics,
   aggregation, normalization, schemas, privacy scanner, comparison, report,
   and decision code;
3. prove audited/non-audited public projection identity;
4. run every P7 deterministic, pinned public, and configured private overlay
   case with behavior equivalent to baseline commit `74aae0a...`;
5. publish or locally preserve the privacy-appropriate baseline report;
6. record all stage metrics and attrition reasons;
7. validate declared coherent variants once and independently review every selected
   `FeasibleCoverWitness`;
8. run the complete public `p7_decision` profile twice from isolated,
   byte-identical source/index copies and freeze its repeat proof;
9. freeze case definitions, evidence units, coherent variants, metamorphic
   transforms, witnesses, reference-helper/options hashes, profile
   configuration, targeted-improvement manifest, anti-special-casing forbidden
   manifest, and acceptance thresholds;
10. compute the closed `BaselineOpportunityRecord` below before any product
    task is authorized.

Baseline artifacts record three separate identities:

```text
behavior_baseline_commit = 74aae0a...
audit_instrumentation_commit = Slice-0 commit
baseline_attempt_id_and_hash
evaluator_closure_hash
feasibility_helper_hash
feasible_cover_manifest_hash
source_tree_hash
source_tree_clean = true
baseline_neutrality_proof_hash
public_profile_repeat_proof_hash
canonical_baseline_audit_hash
private_prefreeze_state
baseline_opportunity_record_hash
```

Slice 0 runs two isolated copies each for clean behavior-baseline audit-disabled,
instrumentation-root audit-disabled, and instrumentation-root audit-enabled
modes. The proof validates and binds each role-specific identity/control and
timing envelope, then requires the schema-defined behavioral payload to agree
within and across applicable modes. Unequal product commits, run roles, audit
modes, timestamps, and audit-output presence therefore remain truthful inputs
to the proof rather than impossible equality operands. The complete public
profile likewise runs twice and freezes both behavioral-payload and audit-leaf
equality plus one canonical audit. The document never claims that code absent
from `74aae0a...` executed at that commit.

After behavior activation, acceptance repeats the same audit-neutrality proof
on the final candidate. The complete public decision profile runs once with
audit disabled against a fresh prepared copy and is compared with the canonical
audit-enabled run; deterministic mechanics receives the same enabled/disabled
check. Candidate neutrality proofs are mandatory inputs to mechanics,
baseline/candidate comparison, and the final decision. Thus accepted
attribution cannot depend on observer presence or measure behavior unavailable
to an ordinary product call.

Baseline runs are create-only and attempt-scoped. An operator chooses the next
unused ID `b-<audit-instrumentation-commit[0:12]>-aNN`; its repositories,
public/private raw artifacts, repeat runs, performance inputs, and publication
preflight live below one ignored attempt root and bind
`baseline-attempt-identity-v1`. Any partial, transient, schema, provenance,
privacy, or neutrality failure leaves that attempt intact and opens a new
ordinal; outputs are never deleted, overwritten, or mixed. Expected retrieval
misses and low recall are measured facts, not attempt failures.

Only one complete attempt may be selected. The frozen publisher first prepares
and validates a canonical baseline publish set plus receipt inside that attempt,
then atomically promotes the reviewed bytes to previously absent tracked
baseline paths. `P7_BASELINE_FREEZE_COMMIT` binds the attempt ID/hash, receipt,
public projection identity, canonical audit, private prefreeze state, and
opportunity record. No fixed baseline output root is reused across attempts.

### Mandatory Baseline Opportunity Checkpoint

`BaselineOpportunityRecord v1` is produced entirely by the frozen evaluator
from a repeated, source-free `MechanismOpportunityMatrix v1`, the canonical
baseline actual audit, descriptive file/span-oracle diagnostics, source
independence classes, and gold/profile identities. It records exact unit keys
and aggregate counts but no source or query content.

The matrix is frozen in Tasks 5-6 before behavior activation. Each lane uses
only product-visible facts and a target-blind helper; gold is joined afterwards
only to score the already-produced leaves through the same coherent finalizer.
Each lane runs twice from byte-identical prepared copies and requires exact
leaf/output/work-counter repeat equality:

```text
actual_legacy
  ordinary baseline product execution

exact_acquisition_only
  fork after original-lane exact facts; apply only the frozen canonical
  exact-injection reference, then the legacy downstream projection

file_projection_only
  fork from actual expanded candidates; apply only unique-file/display-span
  projection and legacy-size final selection; exact, wider boundary, and pack
  reservation remain disabled

context_boundary_only
  on fresh copies, call the legacy context surface with the one frozen explicit
  wider final_top_k; exact/file projection/pack reservation remain disabled

pack_reservation_only
  fork from the same actual legacy QueryBundle; apply only the frozen
  protected-reservation/excerpt reference without adding a candidate file

combined_future_policy
  apply all four reviewed mechanisms in production order
```

The evaluator closure freezes each lane's input seam, helper/import hash,
disabled-mechanism assertions, terminal finalizer, output schema, work budget,
and repeat proof. `context_boundary_only` is a distinct supported-façade
baseline call, not a fabricated projection of files absent from the legacy
bundle. The exact reference may use bounded exact lane facts and canonical
indexed chunks already captured by the source-free audit protocol, but never a
gold target. Interaction-only lift in `combined_future_policy` is reported and
cannot support a single-mechanism bit. File/span oracles remain label-assisted
capacity/headroom diagnostics and cannot support any production bit.

A mechanism-specific support bit is true only when no baseline-satisfied
`Gate.REQUIRED` unit regresses under that mechanism's isolated lane and at least
two terminally missed required units in at least two cases—one supporting case
from each of the two distinct `independent_external` source IDs—become
terminally satisfied. The four bits map one-to-one to the four isolated lanes.
The baseline freeze stores each bit's exact `mechanism_target_cohort`, its
counterfactual recovered count, and
`minimum_candidate_recovered_count=max(1, ceil(counterfactual_count / 2))`.
Candidate acceptance must meet that minimum separately for every authorized
mechanism; an aggregate +1 cannot substitute for a mechanism cohort.

One unit may support more than one bit only when separate isolated lanes each
recover it. Deterministic mechanics prove correctness but cannot satisfy
opportunity thresholds.

The record first computes the baseline classification through the same closed
global/cohort reconciliation used for the final decision. It then selects
exactly one recommendation in this order:

- `acquisition_redirect` when the reconciled baseline classification is
  `path_acquisition_dominant` or `target_span_acquisition_dominant`, regardless
  of smaller post-acquisition opportunities;
- `full_bundle_supported` only when the baseline is neither acquisition-
  dominant nor mixed, all four mechanism bits are true, the combined lane has
  zero required-unit regression, and the exhaustive baseline target manifest
  is non-empty;
- `focused_redesign` when the baseline is not acquisition-dominant and at least
  one but not all mechanism bits are true, or when only label-assisted oracle
  headroom exists;
- `mixed_insufficient` otherwise.

The record reports each bit's exact supporting unit/case/source keys,
single-mechanism and combined deltas, interaction-only lift, descriptive oracle
headroom, duplicate-slot/fill invariants, exact-identifier survival, and
rejected recommendations. It cannot infer support from `Gate.KNOWN_GAP`,
`Gate.INFORMATIONAL`, private data, comparator output, the in-project CST
fixture, a different mechanism's oracle, or a label-assisted oracle.

Task 6 ends after this record and baseline freeze. Even
`full_bundle_supported` requires the repository owner to inspect the record and
explicitly authorize Tasks 7-12 in a later instruction. `focused_redesign`
stops this plan and requires a smaller mechanism-specific design rather than
executing a subset of the prewritten bundle. `acquisition_redirect` requires a
new acquisition/controller spec; `mixed_insufficient` requires benchmark
correction/expansion. This checkpoint is not satisfiable by deterministic
mechanics alone.

After the freeze:

- changing a required evidence unit, matcher, query, mode, threshold, feasible
  cover, or reference helper/options contract requires an explicit benchmark
  correction record;
- a behavior change cannot refresh its own baseline;
- known fixture mistakes require an independently reviewed, versioned new
  freeze and paired reruns on both baseline and candidate commits; the current
  plan must stop rather than overwrite or ad-hoc supersede a freeze.

### Immutable Acceptance Attempts

Every post-activation acceptance run belongs to one explicit immutable attempt
identity bound to candidate commit/tree, frozen evaluator/gold/baseline,
runtime/dependencies, and the optional-environment presence projection.
Candidate/repeat worktrees, prepared public/private copies, raw artifacts,
performance samples, comparator evidence, and summaries all live below that
attempt's ignored root and repeat its identity hash. A decision may consume
exactly one complete attempt.

A product fix always opens a new attempt. A same-commit retry after a partial or
transient failure also opens a new attempt; existing outputs are never erased,
overwritten, or mixed. Failed attempts remain reviewable. This isolation is
separate from the pre-candidate private freeze, which is shared read-only only
when its committed baseline control says it existed.

## Mandatory Acceptance Gates

### Structural Invariants

1. raw `query` results have `unique_path_ratio == 1.0`;
2. adding or removing non-ordering chunks cannot change a file's canonical
   order; a genuinely higher-ranked chunk may become its ordering chunk;
3. an uncorroborated traversal-only same-file anchor never appears in visible
   results;
4. every uniquely resolved original-query path survives when its result or
   anchor partition has sufficient capacity, while declaration-window survival
   is measured against the independent two-window bound;
5. ambiguous identifiers do not reserve multiple files;
6. planner-only identifiers receive no structural protection;
7. ContextPack contains at most one item per path;
8. P4 never compares numeric scores from different probes;
9. audited and non-audited public projections are identical;
10. RetrievalTrace-v2 `file_projection` decisions sum to stage input and every
    selected result separates ordering-chunk from display-window provenance;
11. supported retrieval/builder façade signatures and frozen QueryBundle fields
    are exact;
12. all ordering is deterministic across two clean runs.

### Deterministic Quality

All eight new failure-shaped cases pass:

- identifier extraction and expected resolution state/path are exact;
- conditional protected-path survival is `1.0`;
- `unique_path_ratio == 1.0`;
- `raw_duplicate_slot_count == 0`;
- `result_fill_ratio == 1.0`;
- applicable surface terminal recall is `1.0`;
- required context/explore excerpt recall is `1.0`;
- per-surface attrition reasons match the fixture's designed stage;
- file- and span-oracle expectations pass.

### Existing Protected Profiles

- P0 raw CI passes;
- P2 ContextPack passes;
- P3 RetrievalTrace v1 fixtures remain immutable and the reviewed v2 migration
  delta/coverage passes;
- P4 deterministic exploration passes within its current three-call ceiling;
- P5 graph profiles pass;
- P6 focused query/performance/lifecycle regressions pass;
- the full suite preserves the audited optional skip identities and introduces
  no xfails.

No protected fixture may be weakened solely because public result paths become
unique.

### Pinned Public Quality

Across the frozen P7 public profile:

- path and target-span acquisition do not regress from baseline;
- actual context-expansion survival, surface-terminal, pack, and excerpt recall
  do not regress; shadow visibility/projection/pool fields are reported as
  characterization and are not paired with enforced actual fields;
- the exhaustive frozen baseline target manifest must strictly improve actual
  terminal satisfaction under the exact rule below, not merely move one
  intermediate or shadow stage;
- exact-query Hit@1 and MRR do not regress;
- configured noise-in-pack does not increase;
- every `Gate.REQUIRED` case passes its frozen absolute expectations.

Gold freezes only the closed targeted-improvement eligibility predicate and
reason set, not a hand-picked unit list. After the canonical baseline audit is
sealed and before any candidate behavior work, the frozen evaluator derives
`BaselineTargetManifest v1` exhaustively: include every required unit in every
`Gate.REQUIRED` case whose actual baseline terminal state is unsatisfied with
one of:

```text
path_not_acquired
target_span_not_acquired
target_span_lost_during_context_expansion
path_not_acquired_after_all_probes
target_span_not_acquired_after_all_probes
raw_selection
raw_materialization
pack_selection
pack_budget_or_policy
excerpt_allocation_or_cropping
fused_selection
final_pack_budget_or_policy
final_excerpt_allocation_or_cropping
```

The manifest contains the complete canonical ordered unit-key set plus the
baseline attempt/report, predicate, profile, and gold hashes. It records every
included key and a count for every excluded gate/reason category, so neither an
author nor the evaluator may cherry-pick after seeing the baseline. It is
sealed and promoted with `P7_BASELINE_FREEZE_COMMIT`.

When the set is non-empty, the frozen comparison recomputes
`terminal_satisfied_count(candidate) >=
terminal_satisfied_count(baseline) + 1` over that exact exhaustive set. It also
requires no individual `Gate.REQUIRED` unit that was terminally satisfied at
baseline to become unsatisfied. An empty set records
`targeted_improvement_status=not_applicable` and cannot support
`full_bundle_supported`; it is not silently replaced with a hand-selected
cohort. The comparison schema binds the exact baseline-target-manifest hash,
enumerates every member and before/after terminal state, and rejects a list
derived by candidate-side code.

Exploratory cases intentionally retained to classify a remaining acquisition
gap use existing `Gate.KNOWN_GAP` or `Gate.INFORMATIONAL`. They must execute and
produce complete audits but do not prevent P7 from ending with an
`path_acquisition_dominant` or `target_span_acquisition_dominant` decision and
never enter the targeted-improvement gate.

Aggregate improvement alone cannot hide an individual required-case regression.
Fixture corrections require a separate correction record and paired reruns of
baseline and candidate.

The frozen robustness summary is also mandatory: at least three transformed
companions must use fresh verified source/index copies, preserve their complete
required coherent terminal evidence modulo the exact rename map, and pass the
production-tree anti-special-casing sentinel with zero matches. Missing
robustness evidence blocks classification.

### Performance

On the same P6 environment and prepared indexes:

- warm exact-query p95 is at most `1.10x` baseline;
- warm exploratory query/context p95 is at most `1.15x` baseline;
- explore remains within its existing retrieval-call ceiling; the P7 performance
  summary has no explore-latency sample/ratio field and does not invent a new
  latency gate for that multi-call surface;
- peak RSS is at most `1.10x` baseline for the same workload;
- no additional embedding or planner network request is introduced;
- context expansion performs at most one workspace `stat/read_text` pair per
  expanded unique path and
  `peak_additional_transient_source_read_buffers <= 1`; the counter is taken at
  the grouped-read acquire/release seam and excludes already-retained bounded
  downstream windows;
- `retained_output_bytes` is reported separately and remains bounded by the
  reviewed candidate/window caps plus the paired RSS gate;
- audit-disabled execution retains no audit stage ledger after return.

The P6 benchmark harness is extended to include `context` with fixed warmup,
sample count, paired baseline/candidate ratios, and the existing RSS-unit
definition. This design does not infer context performance from query timing.

If a threshold fails, P7 remains unaccepted until the regression is removed or
a separately reviewed budget amendment explains measured user value.

## Quality Decision Tree

After mandatory fixes, classification uses only the fixed public
`p7_decision` profile and the enforced candidate's per-surface
`actual_terminal_reason`. Baseline reasons and policy-shadow reasons do not
vote. Deterministic fixtures and private overlay diagnostics do not vote.

### Exhaustive Classification Algorithm

1. Validate profile minimums, gold provenance, source commits, capacities,
   audit completeness, and oracle preflight. Any failure blocks P7 and produces
   no classification.
2. Count one enforced-candidate `actual_terminal_reason` for every required
   evidence unit on every executed surface.
3. Remove `satisfied`, `satisfied_initially`, and `satisfied_by_followup`.
4. If no misses remain and every required cohort is complete, select
   `no_proven_retrieval_bottleneck`.
5. Otherwise, group every miss through the closed mapping below and compute raw
   unit counts.
6. Give every failed case exactly one case vote: its unique largest reason group
   wins; a tie votes `case_mixed`. Raw unit metrics remain unchanged.
7. A public group is dominant only when it is the unique top group in both unit
   counts and case votes and all of these inclusive conditions hold:
   - at least six grouped unit misses;
   - at least three failed cases;
   - the group has at least three unit misses;
   - the group receives at least three case votes from at least two distinct
     `independent_external` source IDs;
   - unit share is at least `0.50`;
   - unit lead over the second group is at least `0.15`;
   - case-vote share across all failed cases, including `case_mixed`, is at
     least `0.50`; and
   - case-vote lead over the second group or `case_mixed` is at least `0.15`.
8. With `M` total grouped unit misses, `U1` the top unit count, and `U2` the
   largest remaining group count (zero when none),
   `unit_share=U1/M` and `unit_lead=(U1-U2)/M`. With `F` failed cases, `C1`
   the top group's case votes, and `C2` the largest of every other group's case
   votes and `case_mixed` (zero when none),
   `case_vote_share=C1/F` and `case_vote_lead=(C1-C2)/F`.
   `case_mixed` contributes to `F` and may be runner-up but can never be
   dominant. Exact rational cross-products, not rounded decimals, decide every
   boundary.
9. The global result is the qualifying dominant group, or
   `mixed_inconclusive` when no group qualifies.
10. Independently compute dominant classifications for the closed
    `intent_cohort` values and the `query`, `context`, and `explore` surfaces
    only when the restricted cohort has at least six misses, three failed
    cases, and supporting votes from two distinct `independent_external`
    source IDs. Apply the same counts, shares, leads, and formulas. An eligible
    cohort with no dominant group remains descriptive and does not upgrade a
    global `mixed_inconclusive` result.
11. Reconcile without priority ordering: a global `mixed_inconclusive` remains
    mixed. Otherwise, if any eligible cohort has a dominant classification
    different from the global class, or two eligible cohorts have different
    dominant classes, select `mixed_inconclusive`; if every eligible dominant
    cohort matches the global class, keep the global result. Thus global A plus
    sole eligible cohort B is mixed, while global A plus cohort A remains A.
    Java, Python, and frontend/source tags are descriptive only and cannot vote
    or justify a language-specific mechanism.

Boundary comparisons are inclusive exactly as written. There is no
priority-ordered overlap because terminal reasons map to exactly one group and
dominance must agree at both unit and case levels. A single high-unit case
cannot select the next phase.

### Terminal-Reason Mapping

| classification | terminal reasons |
| --- | --- |
| `path_acquisition_dominant` | `path_not_acquired`, `path_not_acquired_after_all_probes` |
| `target_span_acquisition_dominant` | `target_span_not_acquired`, `target_span_not_acquired_after_all_probes` |
| `materialization_dominant` | `target_span_lost_during_context_expansion`, `raw_materialization` |
| `span_ranking_dominant` | `target_span_lost_in_file_projection` |
| `visibility_policy_dominant` | `target_span_visibility_filtered` |
| `file_pool_order_dominant` | `canonical_file_rank_below_cutoff` |
| `set_selection_dominant` | `protected_reservation_displacement`, `protected_capacity_overflow`, `anchor_rank_below_cutoff`, `raw_selection`, `pack_selection`, `fused_selection` |
| `pack_dominant` | `pack_budget_or_policy`, `final_pack_budget_or_policy` |
| `excerpt_dominant` | `excerpt_allocation_or_cropping`, `final_excerpt_allocation_or_cropping` |

Every non-satisfied terminal reason appears exactly once in this table.

### Next-Phase Mapping

- path/target-span acquisition dominance selects evidence-directed
  acquisition/controller work. P7 does not authorize Python AST or any
  language-specific retrieval mechanism because its fixed profile cannot
  separate language from repository effects. Such a proposal first requires a
  separate phase/spec with at least two independent repositories per compared
  language and repository-balanced evidence.
- materialization dominance selects focused source-window generation,
  overlap-merge, byte-cropping, or raw-projection work; it does not authorize a
  reranker.
- span-ranking or file-pool-order dominance selects an offline bounded ranking
  experiment over the frozen candidate population. It issues no retrieval calls
  and cannot see files outside that population.
- visibility-policy dominance selects a focused visibility-policy correction;
  it does not authorize score retuning or broader acquisition.
- set-selection dominance selects deterministic evidence-need/set-policy work
  before any learned reranker.
- pack dominance selects ContextPack role, need, or byte-budget work.
- excerpt dominance selects display-window/excerpt allocation work.
- no proven bottleneck forbids more retrieval changes until a new measurable
  failure definition exists.
- mixed/inconclusive authorizes only benchmark expansion or correction.

Any later reranker adoption requires its own spec, zero exact-invariant
regressions, paired terminal-recall improvement, and explicit latency/privacy
budgets. P7 does not pre-authorize it with an arbitrary aggregate delta.

These thresholds select an engineering mechanism; they are not claims of
fast-context parity.

## P7 Decision Record

P7 produces `P7DecisionRecord v1` with:

```text
schema_version
behavior_baseline_commit
audit_instrumentation_commit
candidate_commit
source_tree_hashes
fixture_hashes
profile_config_hashes
feasibility_helper_and_options_hashes
feasible_cover_witness_hashes
environment_identity
case_counts_by_cohort
stage_hits_totals_and_recall_by_cohort
actual_surface_attrition_reason_counts
baseline_policy_shadow_attrition_reason_counts
identifier_extraction_resolution_survival
raw_duplicate_and_fill_metrics
file_and_span_oracle_metrics
latency_and_rss_summary
protected_profile_results
mechanics_summary_hash_and_result
robustness_summary_hash_and_result
private_summary_hash_and_status
comparator_summary_hash_and_status
external_comparator_availability
public_classification
private_diagnostic_classification
selected_classification
selected_next_phase
rejected_next_actions
open_risks
privacy_audit
```

`selected_classification` must equal `public_classification` byte-for-byte.
`private_diagnostic_classification` is nullable descriptive metadata and cannot
alter the selected class or next phase.

Legal `selected_classification` values are:

- `path_acquisition_dominant`;
- `target_span_acquisition_dominant`;
- `materialization_dominant`;
- `span_ranking_dominant`;
- `visibility_policy_dominant`;
- `file_pool_order_dominant`;
- `set_selection_dominant`;
- `pack_dominant`;
- `excerpt_dominant`;
- `no_proven_retrieval_bottleneck`;
- `mixed_inconclusive`.

`mixed_inconclusive` is not permission to implement all branches. It requires a
larger or corrected benchmark before another quality mechanism is selected.

## Public Compatibility

### QueryBundle And Query JSON

Field names, types, serialization, numeric score construction, and error
envelopes remain unchanged. The score-to-display relationship changes exactly
as disclosed below.

Intentional behavior change:

- normal code results are unique by path;
- result order and membership may change under the P7 selection rules;
- one path exposes its first display window as the raw excerpt;
- `score`, `score_parts`, and ordinary result reasons explain the file's
  ordering expanded candidate, not necessarily the first display window. When
  two exact windows make that candidate `ordering_only`, public
  `start_line`/`end_line`/`content` can contain none of its lines. This is an
  intentional unversioned result-semantic change under the existing JSON shape;
  RetrievalTrace v2 is the authoritative ordering/display provenance split.
- direct Python `RetrievalResult.spans` remains in the current normalized
  line-range order, but contains only the capped origins of the first retained
  display segment; `_context_segments` carries the private second segment.

### RetrievalTrace v2

Retrieval trace intentionally moves from schema version 1 to 2. The exact
`file_projection` decisions, rank history, and ordering/display provenance are
defined in `RetrievalTrace v2 Migration`. Other preview limits, source-count
keys, timing semantics, error envelopes, and source-free behavior remain
unchanged.

P7 does not serialize the quality audit into RetrievalTrace v2.
ExplorationTrace v2 may consume retrieval-v2 counts internally but does not
embed or expose the retrieval trace schema.

### ContextPack v2

Schema version, groups, evidence needs, missing evidence, next queries,
confidence, omissions, budgets, and excerpt shape remain unchanged.

Intentional behavior change:

- a `context` request that omits `final_top_k` builds one wider unique-result
  QueryBundle before its single v2 builder invocation;
- every result item still has a valid rank in that QueryBundle;
- explicit protected paths are privately reserved before normal EvidenceNeed
  selection without changing the public need schema;
- one selected item may use a second existing-schema excerpt when a retained
  span justifies it.

### ExplorationTrace v2

Round/probe limits, stop reasons, goal ledger, final evidence origin, and schema
version remain unchanged.

P7 may improve unique-path initial/follow-up results and the final pack, but it
does not widen P4's pool, add a round/probe/goal source, or change origin/count
semantics. Follow-up probes disable new exact protection through the private
context-local guard. A future evidence-directed controller is materially
different and requires a new exploration design and trace version.

### Quality Artifacts

P7 quality-audit and decision artifacts are new internal benchmark schemas.
They do not alter MCP or CLI retrieval responses.

## Likely Change Surface

Expected production files:

- `src/context_search_tool/models.py`
  - private, non-serialized protected-identifier occurrence metadata on
    `RetrievalResult` and `EvidenceAnchor`, following existing private context
    fields, plus bounded `RetrievalContextSegment` transport;
- `src/context_search_tool/identifier_intent.py`
  - occurrence-preserving original literal extraction and exact-resolution
    input;
- `src/context_search_tool/scanner.py`
  - expose the existing language-suffix keys to the shared closed
    protectable-filename predicate without enlarging scanner support;
- `src/context_search_tool/sqlite_store.py`
  - expose exact path/declaration matches collected by the existing bounded
    path/symbol and signal scans in the current read session;
- `src/context_search_tool/retrieval_core/expansion.py`
  - traversal-only same-file anchor marking;
- `src/context_search_tool/retrieval_core/candidates.py`
  - exact-resolution side-data transport and the measured
    `lexical_top_k == 0` metadata-only edge;
- `src/context_search_tool/retrieval_core/context_expansion.py`
  - path-grouped one-read materialization, original-rank restoration,
    `winner_chunk_id`, and private retained-range metadata;
- `src/context_search_tool/retrieval_core/ranking.py`
  - preserve private protected-resolution identity without changing numeric
    score policy;
- `src/context_search_tool/retrieval_core/selection.py`
  - post-expansion file evidence projection, protected reservation, visibility
    filtering, one-result-per-path projection, and partitioned result/anchor
    final selection;
- `src/context_search_tool/retrieval_core/types.py`
  - private exact-resolution, protected-path, file-candidate, and span-reference
    models;
- `src/context_search_tool/retrieval.py`
  - exact-resolution injection, request-local deferred trace/audit contribution
    batch, graph-fault projection selection, explicit file-projection trace
    orchestration, and no-op audit-stage hooks without changing its supported
    façade;
- `src/context_search_tool/retrieval_core/tracing.py`
  - winner-consistent v2 rank history, separate canonical/legacy probe origins,
    and public provenance projection;
- `src/context_search_tool/retrieval_trace/models.py`,
  `collector.py`, and `serialization.py`
  - schema-v2 stage decisions, ordering/display provenance, validation, and
    canonical payload;
- `src/context_search_tool/formatters.py`
  - accept and render RetrievalTrace v2 while preserving trace error envelopes;
- `src/context_search_tool/mcp_tools.py` and
  `src/context_search_tool/cli.py`
  - request-local default `context` candidate-limit resolution before the one
    retrieval/build pair;
- `src/context_search_tool/context_pack/builder.py`
  - private protected-path reservation before existing need-aware selection;
- `src/context_search_tool/context_pack/roles.py`
  - bounded same-path reason/retained-span preservation and private protection
    marker normalization;
- `src/context_search_tool/context_pack/models.py`
  - internal `_protected_path_order` and context segments on
    `ContextCandidate`;
- `src/context_search_tool/context_pack/excerpts.py`
  - validate and allocate at most two retained ranges without changing v2
    serialization;
- `src/context_search_tool/exploration/runner.py`
  - run follow-ups under the protection-disable guard while preserving P4 call
    and fusion limits;
- `src/context_search_tool/exploration/probes.py`
  - consume only private legacy ordering-item origins when available so
    winner-first/display provenance and the public v2 cap do not change probe
    seeding;
- `src/context_search_tool/exploration/fusion.py`
  - preserve protected initial result/anchor markers and strip follow-up
    markers defensively;
- `src/context_search_tool/quality/cases.py`
  - schema-v2 evidence-unit parsing, canonical-path validation, target
    validation, and gold provenance;
- `src/context_search_tool/quality/metrics.py`
  - raw duplicate/fill, path/span stage, surface, and oracle metrics;
- `src/context_search_tool/quality/runner.py`
  - Task-6 frozen cross-root evaluation orchestration, product-worker shim,
    supported-surface calls, observer capture, and leaf serialization; its
    closure blob must remain exact for every later accepted run;
- Task-6-frozen `quality/audit.py`, `metrics.py`, `aggregate.py`, `compare.py`,
  `reports.py`, and `p7_decision.py`
  - coherent-variant finalization, oracle workflows, metrics, comparisons,
    schema/privacy validation, and decision ownership for every later run;
- `scripts/p6_benchmark.py`
  - paired warm `context` coverage using the existing environment/RSS
    conventions.

Expected new internal modules may include:

- `retrieval_core/file_evidence.py`;
- `retrieval_core/exact_intent.py`;
- `retrieval_core/audit.py`;
- `quality/audit.py`;
- `quality/oracle.py`.

The implementation plan may choose fewer files. It must not introduce a generic
plugin/registry abstraction solely for P7.

## Delivery Decomposition

### Slice 0: Audit And Baseline Only

- add schema-v2 evidence-unit parsing, target validation, and gold provenance;
- add the context-local evaluation observer and source-free retrieval leaf
  ledger without changing a supported façade;
- freeze the complete evaluator closure, including the two-state gold resolver,
  coherent-variant finalizers, metrics, comparison, and decision code;
- collect read-only exact-resolution facts under the declared scan contract and
  implement the shared pure traversal-visibility, two-window file-projection,
  and protected-capacity helpers in shadow mode;
- add file- and span-oracle diagnostics;
- add deterministic mechanics cases and the fixed public decision profile;
- prove audited/non-audited public projection identity;
- prove complete public-profile repeat identity;
- record behavior-baseline, instrumentation-commit, clean-tree, fixture, and
  profile identities;
- freeze baseline reports, gold labels, and thresholds.

No production ranking or selection behavior changes in this slice.

### Slice 1: Original Exact Evidence

- preserve identifier occurrence order;
- promote Slice-0's bounded exact declaration/file side data from audit-only
  observation to production use without adding another scan or connection;
- classify unique/ambiguous/missing;
- inject one canonical declaration/file chunk before direct merge;
- add private protected-path selection metadata;
- add the context-local protection-disable guard and use it for every P4
  follow-up before any protected behavior can merge;
- prove planner hints cannot create or remove protection;
- add cross-unit, clause-local narrowing, work-count, and capacity-overflow
  tests.

### Slice 2: Post-Expansion File Projection

- mark traversal-only same-file anchors;
- group context expansion by path for one transient read, restore original
  ranked order, and do not move the source-materialization boundary;
- group expanded ranked chunks by canonical repository-relative path inside
  the new `file_projection` stage;
- migrate RetrievalTrace v1 to v2 with closed projection decisions and explicit
  ordering/display provenance;
- preserve primary order without score aggregation;
- retain protected declaration, ordering, and at most one additional bounded
  display window;
- apply visibility in `file_projection`, then apply protected reservation and
  both result/anchor capacities only in `final_selection`;
- project unique raw results;
- extend path/span/rank/pool audit survival.

### Slice 3: Context Candidate Boundary And Pack Reservation

- resolve the wider default `context` QueryBundle limit only when
  `final_top_k` is omitted;
- keep one retrieval call, one QueryBundle, and one ContextPack build;
- carry reservation order through private `RetrievalResult` /
  `ContextCandidate` metadata and reserve protected paths before unchanged
  public `EvidenceNeed` coverage;
- allocate at most two retained excerpts from the already materialized segment
  views;
- preserve ContextPack v2;
- emit pack-item and excerpt leaves consumed by the frozen Task-6 finalizer;
- prove every result-backed item has a valid rank in the source QueryBundle.
- prove `QueryBundle`, retrieval, and builder public signatures/dataclass
  contracts remain exact.

### Slice 4: P4 Compatibility Guard

- verify every follow-up runs under the Slice-1 protection-disable guard and
  defensively clears private markers;
- preserve P4's current initial/follow-up limits, fusion, origin/count fields,
  frozen goals, and score-domain isolation;
- emit initial, follow-up, fusion, final-pack, and final-excerpt audit leaves for
  the frozen Task-6 finalizer without changing ExplorationTrace v2;
- rerun all P4 deterministic and pinned-real gates.

This slice does not widen the exploration candidate pool or redesign fusion.

### Slice 5: Acceptance And Decision

- run deterministic, protected, pinned public, and local overlay profiles;
- run paired latency/RSS checks;
- optionally run the external comparator;
- generate privacy-audited P7 reports;
- write the P7 decision record;
- update roadmap status only after all gates and review pass.

Each slice is independently reviewable and reverts cleanly. General ranking
retuning, controller work, reranker experiments, AST plugins, and product
surfaces are excluded from the implementation plan.

## Testing Strategy

### Unit Tests

- identifier literal extraction and occurrence order;
- protectable filename positives cover source/template/config/doc
  (`Foo.java`, `View.vue`, `app.json`, `README.md`), compound and dotfile names;
  negatives cover `notes.bin`, `.secret`, and `Foo.java.bak`, with
  case-preserved resolution;
- exact filename/stem/qualified-symbol/symbol resolution;
- active-symbol versus structured-signal declaration deduplication, provenance,
  and legacy symbols-only `path_symbol` source counts;
- ambiguity, clause-local project-unit narrowing, and canonical-path rejection;
- clause splitting keeps path `/` and qualified literals opaque and covers
  same-clause unit narrowing, cross-conjunction isolation,
  `module-a/Foo` plus `module-b/Bar`, conflicting fragments, and duplicate
  filename/stem paths narrowed within but never across clauses;
- exact-injection precedence and path/signal source attribution;
- same-path multi-lane canonical injection follows the fixed source/lane-rank
  key and is unchanged by adding a higher-scoring planner candidate;
- enabled-lane read-scope identity and zero incremental path/signal work;
- `lexical_top_k == 0` performs exactly one shared metadata-only path/symbol
  pass/connection with an eligible exact literal and zero without one;
- protection capacity and overflow;
- private protection metadata normalization and formatter/trace/feedback
  exclusion;
- private metadata `replace`/`deepcopy`, initial-fusion preservation, and
  follow-up stripping;
- duplicate result/anchor normalization preserves the minimum non-null
  protected occurrence order while leaving the existing content/rank winner
  unchanged;
- traversal/display visibility;
- same-file traversal evidence merged with a current-policy display-eligible
  directory anchor becomes visible rather than inheriting a sticky filter;
- file grouping and no score aggregation;
- protected-declaration, ordering, and secondary display-window selection;
- one later bridge window transitively merges two retained segments or leaves
  both unchanged on bound failure, with the specified trace decision;
- complete file-population ordering and final surface-pool capacity;
- ContextPack protected reservation followed by existing need coverage;
- per-surface terminal attrition and `not_applicable` handling;
- baseline actual/shadow terminal lanes remain isolated in both directions and
  only enforced actual reasons enter cohorts, regressions, and votes;
- evidence-unit v2, gold-provenance, feasibility-cover, and anti-gaming
  validation;
- two distant targets in one README/POM evidence anchor are infeasible unless
  its one materialized window contains both;
- frozen feasible-cover witness alternatives/ranges/budget counts and
  helper/options/hash mismatch rejection without candidate reselection;
- file-oracle and span-oracle alternative/excerpt selection;
- private-summary allowlist, leakage sentinels, private production-tree secret
  needle scan, and non-voting status invariants.

### Pipeline Tests

- duplicate chunks from one path produce one raw result;
- lower-ranked supporting files regain result/pack capacity;
- exact cross-unit declaration chunks enter before merge and survive the bounded
  selector;
- planner-only hints remain soft;
- protected original evidence survives planner failure;
- uncorroborated same-file anchors remain traversal-only;
- `context` performs exactly one retrieval and one pack build;
- explicit `context final_top_k` remains authoritative;
- omitted `context final_top_k` produces the specified wider QueryBundle and
  valid v2 `retrieval_rank` values;
- the same request executed as ordinary `query` can have a smaller result
  universe without creating a hidden ContextPack pool;
- an `ordering_only` raw result exposes exact-window content while its
  score/score-parts/reasons remain ordering evidence and trace v2 separates
  both origins;
- pack emits two excerpts without duplicate items when a secondary span is
  required;
- oversized-file fallback remains bounded;
- repeated expanded chunks cause at most one `stat/read_text` pair per canonical
  path;
- many large unique paths keep
  `peak_additional_transient_source_read_buffers <= 1`, report separately
  bounded `retained_output_bytes`, and satisfy the RSS gate;
- unreadable-path status preserves each chunk's own indexed fallback;
- P4 follow-up text cannot create protected exact intent;
- protection-disabled follow-ups never trigger the metadata-only zero-lane
  exact scan;
- P4 path fusion, score-domain isolation, call ceilings, origin counts, and
  frozen-goal monotonicity remain valid.

### Characterization And Compatibility

- normalized public query projection before/after audit is identical;
- supported `QueryBundle`, `query_repository`, `trace_repository`, and
  `build_context_pack` contracts remain exact;
- legacy direct construction with `_context_segments=()` synthesizes the
  pre-P7 single source view for normal results and anchors;
- context-local audit capture resets after success, early return, exception,
  and concurrent task execution;
- the protection-disable guard resets after success, early return, cancellation,
  exception, and concurrent task execution;
- immutable RetrievalTrace-v1 fixtures compare to v2 with only the reviewed
  migration delta;
- RetrievalTrace v2 keeps truthful stage decision sums and the canonical
  `ranking -> cohort_rerank -> context_expansion -> file_projection ->
  final_selection` rank history;
- duplicate anchors remain separate projection passthrough outputs and are
  deduplicated only by `final_selection`;
- composite `file_projection` has empty `top_candidates` instead of mixing an
  ordering chunk's identity/score with another window's range;
- final trace two-way merge is contiguous and preserves result-list and
  anchor-list order as exact subsequences, including protected reordering;
- overlap-merged normal results and anchors use their score/adjustment winner
  for `ordering_chunk_id` even when accumulated origin order differs;
- selections with more than eight canonical origins expose the exact public
  omitted count, while P4 reads only the selected ordering item's private v1
  accumulated origins; secondary display origins never become new probes;
- trace formatter/MCP/CLI outputs accept schema v2 and reject malformed v2
  provenance;
- ContextPack v2 canonical fixtures remain valid;
- ExplorationTrace v2 canonical fixtures remain valid;
- ordinary error and missing-index paths remain unchanged;
- exact evidence-anchor separation remains unchanged;
- feedback persistence receives no audit path ledger or source data.

### Quality And Performance

- run new P7 deterministic profile on every change;
- run P0/P2/P3/P4/P5 protected profiles before each slice merges;
- run pinned public P7 profile before acceptance;
- run private local overlay only in the owner's environment;
- compare instrumented baseline/candidate audit reports and separately prove
  clean-baseline/instrumented public projection identity;
- run paired warm exact-query/exploratory-query/context timing and RSS under P6
  methods, plus the separate existing explore retrieval-call ceiling.

## Security And Privacy

- exact resolution reads indexed metadata and local source only;
- P7 introduces no new network path;
- remote planner/embedding disclosure remains governed by existing config;
- quality audit does not store source content;
- private overlay query text, paths, identifiers, excerpts, and reports remain
  outside version control;
- private aggregation starts from an explicit field allowlist; it never
  serializes a full report and then attempts to redact it;
- committed public reports identify only public repositories and safe fixture
  data; tracked decision provenance contains only the sanitized private-summary
  hash, closed non-voting mode/pass status, and nullable descriptive private
  classification, never the private aggregate metrics themselves;
- leakage sentinels include original/private query text, identifier literals,
  repository-relative and absolute paths, repository origin, planner hints,
  fixture path, and local username;
- absolute local paths are removed from canonical artifacts;
- exception messages do not include source content;
- audit collectors are discarded at execution end and are never appended to MCP
  feedback.

## Risks And Mitigations

### File Deduplication Hides A Second Important Method

Risk: one result per file could preserve the wrong span.

Mitigation: ordering-chunk order remains canonical, up to two bounded
non-overlapping display windows can feed ContextPack, and target-range evidence
units test the chosen windows.

### Exact Protection Crowds The Set

Risk: common names or many literals consume every slot.

Mitigation: only unique declaration/file resolutions are protected, generic
split terms are excluded, multiple literals resolving to one path share a file
slot, and result/anchor overflow follows query occurrence order. More than two
distant protected declarations in one file remain subject to the explicit
display-window bound and are reported as span-retention loss rather than hidden
as successful protection.

### Quality Audit Changes Execution

Risk: collecting full candidate identities changes allocation, ordering, or
timing enough to alter results.

Mitigation: audit is a read-only observer, audited/non-audited projections are
characterized as identical, and performance gates use audit-disabled production
execution.

### The Benchmark Overfits Two Repositories

Risk: P7 becomes a collection of fixes for one Python and one Java project.

Mitigation: separate mechanical deterministic fixtures, pinned public
repositories, existing generic/frontend profiles, and a non-published private
overlay. The visible paraphrase/robustness cohort, frozen metamorphic companions,
and static anti-special-casing sentinel test transfer without claiming a hidden
holdout. Aggregate metrics are reported by cohort and cannot hide individual
required cases.

### Wider Pool Increases Source Reads

Risk: giving ContextPack more candidates causes every candidate file to be read.

Mitigation: only default `context` widens its actual QueryBundle, the automatic
`4 * requested_max_items` component is capped at 64 without reducing a larger
configured limit, and `context_expansion` groups origins by path while allowing
only one transient full-source read buffer at the explicit acquire/release seam.
A many-large-unique-path fixture measures that counter, retained output bytes,
RSS, and read counts separately. The design explicitly budgets and benchmarks
the extra expanded unique files; it does not claim
selection-before-materialization.

### Retrieval Trace Migration Breaks An Unversioned Consumer

Risk: a consumer assumes schema version 1 or four-stage final rank history
without checking `schema_version`.

Mitigation: RetrievalTrace moves explicitly to v2, formatters and tool payload
tests cover it, v1 fixtures remain immutable migration inputs, and the reviewed
delta is limited to file projection and its provenance.

### P4 Semantics Drift

Risk: a better initial pool accidentally changes call limits, goal monotonicity,
or cross-query score behavior.

Mitigation: P7 does not widen P4. It preserves ExplorationTrace v2 and current
limits, disables exact protection on follow-ups, keeps probe-local rank, and
reruns all P4 deterministic and pinned-real gates.

### Exact Resolution Adds Hidden Scan Cost

Risk: declaration protection triggers another repository-wide symbol or path
scan for each identifier.

Mitigation: enabled lanes collect resolution inside their existing
original-token path/symbol and signal read scopes with no incremental work.
When the path/symbol lane is disabled, the first sixteen eligible literals
share exactly one intentional metadata-only pass/connection; no eligible
literal adds none. Work-count tests reject every per-literal scan, second pass,
or extra signal connection and performance gates measure the declared edge.

### Path Recall Masks A Wrong Excerpt

Risk: a report marks the right file as success while the requested method never
entered or survived.

Mitigation: every decision-profile unit includes an exact target, and the audit
separately gates target-span acquisition, retained display windows, pack items,
and excerpt satisfaction. Path-only metrics cannot satisfy a target-span gate.

### Quality Gold Is Retrofitted To The Candidate

Risk: evidence alternatives are loosened after seeing CST or comparator output.

Mitigation: exact targets, source commit, author/reviewer identities, fixture
hash, and freeze timestamps are validated before candidate or comparator runs.
Corrections require a paired baseline/candidate correction record.

### Decision Thresholds Are Used As Product Claims

Risk: `0.90` stage recall is presented as fast-context parity.

Mitigation: thresholds select the next engineering mechanism only. External
quality claims require broader, separately reviewed evidence.

## Definition Of Done

P7 is complete only when:

1. behavior-baseline, audit-instrumentation, frozen-evaluator-closure,
   clean-tree, fixture, and profile identities are recorded separately;
2. fixed public gold is target-bearing, coherent-variant-constrained,
   independently reviewed, sealed through the two-state provenance join, frozen
   before candidate/comparator runs, and meets the profile minimums;
3. audit observation is proven behavior-neutral against the clean baseline and
   the full public profile has a frozen two-run projection/audit repeat proof;
4. every required unit receives complete applicable path/span stage survival
   and exactly one `actual_terminal_reason` per executed surface, while the
   behavior baseline separately records one non-voting shadow reason;
5. the baseline opportunity record selects exactly one closed recommendation,
   and no product task begins without both `full_bundle_supported` and a
   later explicit user authorization;
6. when that continuation is authorized, raw result paths are unique,
   duplicate-slot count is zero, and eligible
   result capacity is filled;
7. non-ordering chunks cannot aggregate into a better file order;
8. traversal-only anchors cannot occupy display slots without corroboration;
9. uniquely resolved original-query paths are injected and satisfy their
   result/anchor capacity contract with the declared enabled/disabled-lane work
   counts, while exact declaration windows obey and report the separate
   two-window bound; graph-fault rollback commits trace and audit membership
   atomically from the signal-free projection;
10. omitted-budget `context` uses the specified wider source QueryBundle, while
   explicit budgets and every v2 `retrieval_rank` remain valid;
11. ContextPack v2 can reserve protected paths and preserve the required bounded
    secondary excerpt without a hidden candidate pool;
12. P4 follow-ups cannot create exact protection and all P4 limits, fusion,
    origin/count, frozen-goal, and score-domain contracts remain unchanged;
13. deterministic mechanics cases and all protected P0-P6 gates pass;
14. pinned public cases meet frozen non-regression and absolute gates;
    the public paraphrase/robustness and metamorphic cohorts pass without being
    represented as hidden holdout evidence;
15. any evaluated private local overlay passes the allowlist, leakage, and
    private production-tree anti-special-casing scans and remains non-voting;
16. query/context performance, explore call ceilings, RSS, network,
    source-read, and audit-lifecycle
    budgets pass;
17. public query, ContextPack v2, ExplorationTrace v2, error schemas, and the
    explicit RetrievalTrace v2 migration remain valid;
18. the privacy-audited P7 decision record selects exactly one legal next-phase
    classification or explicitly records `mixed_inconclusive`;
19. the roadmap status is updated only after the evidence above exists.

P7 may finish with `path_acquisition_dominant` or
`target_span_acquisition_dominant`. That is not a claim that retrieval quality
is solved; it is evidence that the next phase should change acquisition rather
than continue unmeasured ranking work.

## Agent Review Rubric

Independent reviewers must verify:

- the diagnosis boundary distinguishes path acquisition, target-span
  acquisition, span retention, complete file-population order, final
  surface-pool order, each surface selector, pack, and excerpt loss with only
  the explicit RetrievalTrace-v2 migration;
- query, context, and explore are modeled as separate branches rather than one
  fictitious linear funnel;
- the file evidence population cannot aggregate score from file length or
  additional non-ordering chunks, and only `final_selection` owns capacity;
- exact identifier protection is bounded, unambiguous, occurrence-ordered, and
  planner-independent, and its canonical chunk is acquired before merge with
  exactly the declared enabled/disabled-lane scan work;
- ContextPack reserves private protected paths without changing public
  `EvidenceNeed` semantics or consuming files outside its QueryBundle;
- every result-backed ContextPack item keeps a valid `retrieval_rank`;
- P4 follow-ups cannot create exact protection, never compare cross-query
  scores, and retain v2 limits/origin/count semantics;
- the Task-6-frozen evaluator, rather than candidate code, owns gold resolution,
  finalization, metrics, comparison, schemas, and decision;
- evidence-unit and oracle metrics cannot be trivially gamed by duplicate
  paths, cross-variant alternative mixing, weak alternatives, path-only labels,
  production special-casing, or labels written after candidate output;
- thresholds lead to one justified next action rather than authorizing every
  mechanism;
- implementation slices are feasible without a broad retrieval rewrite;
- unchanged public schemas, the reviewed trace migration, privacy,
  deterministic behavior, and P6 performance contracts remain protected;
- private comparison evidence cannot leak into committed artifacts.

## Agent Review Record

### Round 1: 2026-07-25

Three independent agents reviewed the initial draft from architecture,
IR/evaluation, and implementation-feasibility perspectives. All three returned
`FAIL`.

| review | result | blocker | major | minor |
| --- | --- | ---: | ---: | ---: |
| architecture and contract compatibility | FAIL | 2 | 6 | 5 |
| information retrieval and evaluation validity | FAIL | 2 | 5 | 3 |
| implementation feasibility and scope | FAIL | 2 | 6 | 4 |

The shared blocking findings were:

1. path-only survival could declare success for the wrong chunk in the right
   file;
2. query, context, and explore were modeled as one linear funnel even though
   their output paths form a DAG;
3. a hidden wider pool would make ContextPack v2 `retrieval_rank` invalid;
4. moving file selection before source materialization would silently change
   RetrievalTrace v1 stage semantics.

Revisions 2 and 3 close those findings by requiring target-bearing evidence
units, per-surface actual/shadow audit finalizers, an actual wider QueryBundle
only for omitted-budget `context`, and a new post-expansion
`file_projection` stage before capacity-owning `final_selection`.

They also incorporate the major findings by:

- injecting a canonical exact declaration/file chunk before merge;
- closing exact extraction, priority-level narrowing, evidence-source,
  disabled-lane scan work, and planner-independent injection order;
- using private `ProtectedPathRequirement` values instead of overloading public
  `EvidenceNeed`;
- disabling exact protection on P4 follow-up probes;
- separating file and span oracles and freezing a reviewed feasible-cover
  witness before candidate execution;
- defining raw duplicate/fill metrics before normalization;
- freezing target labels and comparator-independent gold provenance;
- defining mutually exclusive actual terminal reasons, non-voting shadow
  reasons, and a dominance algorithm;
- separating behavior-baseline and audit-instrumentation identities;
- versioning RetrievalTrace with winner/display provenance while keeping
  separate legacy P4 probe origins;
- bounding scan work, source reads, segment focus state, and full-body
  residency; and
- sanitizing private overlays through an allowlist plus leakage sentinels.

### Final Review: 2026-07-25

The same three independent perspectives re-reviewed revision 3:

| review | result | blocker | major | minor reported |
| --- | --- | ---: | ---: | ---: |
| architecture and contract compatibility | PASS | 0 | 0 | 1 |
| information retrieval and evaluation validity | PASS | 0 | 0 | 0 |
| implementation feasibility and scope | PASS | 0 | 0 | 2 |

The architecture minor was this stale review-record description. The two
feasibility minors requested an exact duplicate-anchor projection count and
transitive bridge-window merge rule. This final editorial pass fixes all three:
every anchor input is a projection passthrough until final-selection
deduplication, and a bridge window atomically coalesces both touched segments or
is rejected without partial mutation.

No reviewer reports a remaining blocker or major finding. Agent review approves
the design direction; it does not authorize implementation.

## Plan-Alignment Amendment Review

This section is a non-normative review-result ledger. Plan authoring exposed
additional contracts for coherent cover variants, frozen evaluator ownership,
metamorphic robustness, private-overlay pre-freezing, bounded exact side data,
and atomic graph-fault publication; the normative design above has been amended
to state them explicitly.

The stable `design_review_payload_sha256` is computed after:

1. removing the single `Status:` line; and
2. removing bytes from `## Plan-Alignment Amendment Review` up to, but not
   including, `## Stop Point`.

Everything else, including this document's original review history and Stop
Point, remains covered. Review-result/status edits may change the full-file hash
without changing the payload. Any other edit requires another complete
fixed-payload review.

### Fixed-Payload Review: Pending

The architecture/contract, IR/evaluation/gold, and
implementation/TDD/operability reviewers must each read the complete amended
design and detailed plan at their fixed payload hashes. Results are recorded
here only after all three report zero blocker and zero major findings.

## Stop Point

This document ends at design.

Do not implement P7, change roadmap status, refresh quality expectations, add a
reranker/controller/parser, or claim retrieval-quality closure until:

1. independent agent review has no blocker or major finding;
2. this design is revised with the review record;
3. the user approves the revised direction; and
4. a separate implementation plan is written and reviewed.

Conditions 1-4 remain pending for this amended direction until the fixed-payload
review below is complete and the user has inspected the result. The amendment
is part of this design's normative payload; only its review-result ledger and
`Status:` line are excluded by the declared hash procedure. Even after document
review and user approval, implementation requires a new explicit instruction.
If implementation later reaches the baseline opportunity checkpoint, Tasks
7-12 require a second explicit user authorization.
