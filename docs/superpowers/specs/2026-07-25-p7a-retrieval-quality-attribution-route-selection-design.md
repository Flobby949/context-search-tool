# P7A Retrieval Quality Attribution And Route Selection Design

Date: 2026-07-25
Status: Reviewed; fixed-payload agent review PASS; awaiting user approval
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Roadmap phase: Phase 7A
Behavior baseline: `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`
Predecessor: `docs/superpowers/specs/2026-07-18-p6-freshness-performance-large-repositories-design.md`
Preserved prior proposal: `docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md`

## Executive Decision

P7A will diagnose retrieval loss and select the next experiment. It will not
implement exact-injection, file-level reranking, wider context pools, protected
pack reservation, RetrievalTrace v2, a new parser, a reranker, or a controller.

This is a deliberate correction to the earlier route. The preserved P7
proposal tried to do three jobs at once:

1. build a stage-attribution system;
2. model several possible future mechanisms; and
3. activate exact acquisition, file projection, context-boundary, and pack
   changes as one production bundle.

That proposal remains intact as historical design evidence; P7A neither edits
nor silently replaces it. P7A is the narrower operative proposal because the
earlier design could only explain the result after several hypotheses had
already been implemented together. That made causal attribution weak and
risked repeating the current pattern of adding retrieval mechanisms before
proving where evidence was lost.

The revised phase boundary is:

```text
P7A
  freeze public target-bearing benchmark and selection provenance
  -> add behavior-neutral, source-free observation
  -> run one reproducible baseline twice
  -> attribute every required unit through the real surface DAG
  -> run label-assisted file/span/pack upper-bound diagnostics
  -> publish one reviewed route decision
  -> STOP

P7B or P8
  write a new design for exactly one selected mechanism
  -> implement one mechanism
  -> run paired A/B
  -> retain, revise, or reject it
```

P7A is complete when the reviewed route record exists. It is not incomplete
merely because no retrieval behavior changed. Conversely, a route record is not
authorization to implement its recommendation; a separately reviewed design,
plan, and explicit user instruction are required.

## Why This Split Is Necessary

The current engine already has lexical, semantic, path/symbol, direct-text,
signal, graph, planner, controlled exploration, ContextPack, and trace
mechanisms. Aggregate recall cannot distinguish whether a required evidence
unit:

1. never entered the candidate population;
2. came from the right file but the target span never entered;
3. entered but was lost during ranking or context materialization;
4. survived until the output pool but lost a result slot;
5. reached a ContextPack candidate set but lost pack selection; or
6. reached a pack item but was cropped from excerpts.

Without that distinction, “improve ranking” and “improve pack selection” are
not plans; they are guesses.

The P7A route record therefore answers only:

> On this frozen, explicitly limited benchmark, which stage is the strongest
> supported bottleneck, and what single experiment should be designed next?

It does not claim the benchmark represents the production query distribution,
and it does not claim parity with fast-context.

## Phase Outcomes

`P7ARouteDecision v1` has exactly one outcome:

- `benchmark_path_acquisition_dominant`
- `benchmark_target_span_acquisition_dominant`
- `benchmark_span_materialization_dominant`
- `benchmark_selection_dominant`
- `benchmark_pack_excerpt_dominant`
- `benchmark_mixed_expand`
- `no_proven_gap`

The matching next action is closed:

| outcome | next action |
| --- | --- |
| `benchmark_path_acquisition_dominant` | design one path-acquisition/controller experiment |
| `benchmark_target_span_acquisition_dominant` | design one target-span acquisition experiment |
| `benchmark_span_materialization_dominant` | design one span materialization/ranking experiment |
| `benchmark_selection_dominant` | design one file/set-selection experiment |
| `benchmark_pack_excerpt_dominant` | design one ContextPack/excerpt experiment |
| `benchmark_mixed_expand` | expand or correct the benchmark; do not alter retrieval |
| `no_proven_gap` | stop until a new measurable failure definition exists |

The `benchmark_` prefix is normative. It prevents a curated public benchmark
from being described as the real-world request distribution.

## Goals

1. Freeze a target-bearing public quality profile before reading its controlled
   baseline output.
2. Record how public cases were selected and which cases motivated the design.
3. Attribute path and target-span survival through the actual query, context,
   and explore execution DAG.
4. Keep observer-disabled product output, work, and public schemas unchanged.
5. Keep the audit source-free and bounded.
6. Separate path acquisition, target-span acquisition, span
   materialization/ranking, surface selection, and pack/excerpt loss.
7. Use case-macro and unit-micro evidence so one large case cannot select a
   route.
8. Require support from two independent external repositories.
9. Reject a case before baseline execution unless at least one complete
   coherent evidence variant fits the real surface capacities and budgets.
10. Use file, span/ranking, and pack oracles only as label-assisted upper
    bounds.
11. Produce a reproducible, agent-reviewed route record and stop.

## Non-Goals

P7A does not:

- inject or protect exact identifiers;
- change candidate acquisition, scoring, ranking, cohort policy, result
  membership, or result order;
- deduplicate result paths or introduce a file projection;
- change QueryBundle, ContextPack, RetrievalTrace, or ExplorationTrace schemas;
- widen default context candidate limits;
- add ContextPack reservation or excerpt policy;
- add Python/Java/frontend parsing or graph rules;
- add a learned, model, remote, or heuristic reranker;
- make exploration automatic;
- change P4 probe/fusion behavior;
- run private repositories as decision evidence;
- make fast-context availability a gate;
- implement the route chosen by the decision record;
- complete P6's deferred scale, stress, churn, cross-platform, or service work.

## Baseline And Compatibility Boundary

The behavior baseline is the clean P6 merge:

```text
74aae0abe3dff685282fbcc785f7a9b3532cbbe6
```

The plan-time local evidence on 2026-07-25 was:

```text
Python: 3.13.12
SQLite: 3.51.2
pytest: 2896 passed, 9 skipped, 0 failed, 0 errors, 0 xfailed
warnings: 16
duration: 54.58 seconds
tracked source/test diff: empty
```

Task 0 must reproduce this from the reviewed documentation entry commit,
including exact skip node IDs and optional-environment presence. This is
plan-time evidence, not a substitute for execution-time evidence.

That documentation entry also preserves the prior P7 spec and plan byte for
byte. Their recovery identities are:

```text
P7 spec  sha256 04bc5c52179cf63e29a7a6145e43416ab6e21d61de5e2bc2528b62ac12ca64e8
P7 plan  sha256 06f80aeda5c70afe315d1b30d2bf88b910b28c340f1fc252cc7d889c18b8c4a2
```

P7A references those files as history; it does not amend their payloads.

P7A permits only this production compatibility delta:

- internal, ContextVar-scoped audit hooks at already existing stage boundaries;
- private source-free audit value types;
- a separate evaluator worker/driver protocol;
- quality fixture/schema/report additions.

With no audit observer installed:

- query, context, trace, and explore public bytes are unchanged;
- store connections, scans, source reads, embedding calls, planner calls, and
  exploration calls are unchanged;
- no audit ledger, candidate snapshot, gold value, or cross-request state is
  retained;
- existing P0-P6 protected fixtures remain byte-identical.

P7A does not migrate RetrievalTrace. Public trace remains version 1.

## Architecture

### Process Boundary

The baseline harness has two processes:

```text
evaluator process
  owns fixtures, gold, variants, finalizers, metrics, oracles, and decision
  -> sends only ordinary façade inputs to product worker

product worker
  imports one explicit product root
  -> runs query/context/explore through supported façades
  -> captures source-free audit leaves through the observer
  -> returns one transient framed public output, work counters, and leaves

evaluator process
  validates and hashes the transient frame in memory
  -> persists only source-free projections, hashes, work, and leaves

after all six role artifacts are sealed
  evaluator process joins source-free leaves/projections to gold
  -> finalizes variants and terminal reasons
  -> aggregates metrics and route decision
```

The product worker receives the ordinary query, public options, prepared
repository/index, and observer sink. It does not receive target paths, target
ranges, evidence variants, route thresholds, case gate, profile name, or gold
hashes.

The import boundary is process-scoped and executable, not conventional:

- the production observer lives in
  `context_search_tool.retrieval_core.audit_observer`, whose package
  `__init__` is side-effect free and whose module imports only the standard
  library;
- the framed product worker and its stdlib-only bootstrap/frame validator live
  outside `context_search_tool.quality`;
- the evaluator launches that worker as
  `python -I -B /absolute/instrumentation/src/context_search_tool/_p7a_worker.py`
  with a sterile working directory and one explicit product
  `src` root; before importing a façade the bootstrap removes its own script
  directory, empty/cwd entry, `PYTHONPATH`, ambient repository paths, and other
  CST roots from `sys.path`, inserts the resolved product root, preserves only
  runtime-identity-bound stdlib/site-packages roots, and verifies every loaded
  `context_search_tool` module is below the selected root and every third-party
  module below a frozen dependency root; `-B` plus an in-process assertion
  keeps both prepared trees bytecode-write-free even though `-I` ignores
  `PYTHONDONTWRITEBYTECODE`;
- a closed transient `P7AWorkerRequest v1` carries the selected absolute
  `product_src_root`, expected product commit/tree, opaque invocation ID,
  surface, ordinary façade inputs, source/index identity, and audit mode; the
  absolute root never appears in a frame, log, or persisted artifact, and the
  worker rejects a role/root/commit/tree mismatch before product import;
- ordinary product import, ordinary query, and worker startup must leave
  `context_search_tool.quality` and every case/finalizer/oracle/decision module
  absent from `sys.modules`;
- the worker process never imports `quality`; the separate evaluator process
  may import `quality` before launch because its modules and gold do not cross
  the process boundary or enter the worker frame; and
- P7A does not edit `quality/__init__.py` to make this isolation test pass.

This boundary is necessary because importing a `quality.*` child executes the
existing `quality/__init__.py` and eagerly imports case/aggregate code.

`P7AWorkerRequest v1` and `P7AWorkerFrame v1` are separate, closed in-memory
protocols. A successful frame may contain the ordinary public output, including
source excerpts, only for that role invocation. The evaluator validates it,
hashes the canonical public bytes, derives the target-independent content
commitments below, and destroys the frame before returning from role mode.
Neither transient protocol is written to a run directory, log, exception, or
tracked artifact, and role mode never parses gold.

The persisted `role_run` artifact contains only public output/error SHA-256 and
byte length, source-free public path/range/order/content-commitment projections,
work counters, import-closure evidence, and source-free audit leaves. The two
transient schemas and persisted-artifact schema are independently frozen in the
evaluator closure.

The evaluator starts each worker in a new process group with bounded stdin,
stdout frame, and stderr capture. On cancellation, declared timeout, malformed
or oversized frame, or parent error it closes stdin, sends group termination,
waits one frozen monotonic grace interval, sends group kill if necessary, and
always `wait()`s/reaps before inspecting evidence. Raw stderr is validated and
hashed in memory, never persisted. Only after reap may the runner seal partial
byte hashes, verify prepared repository/index identities and clean product
worktrees, or write an attempt disposition. A live/unreaped child, surviving
descendant, changing partial file, or post-reap repository mismatch is an
implementation-invalid run, never an immutable failure record.
A worker that exceeds the frozen declared deadline is reaped by this path and
receives the non-retryable `declared_timeout` disposition; it is never relabeled
as an external host failure.

### Materialized Content Commitments

Reported line ranges alone cannot prove delivery. Query full-file caps and
ContextPack excerpt allocation can crop inside a UTF-8 line while retaining the
same `start_line` and `end_line`. Whole-output hashes prove repeat equality but
cannot later prove which target bytes survived.

Before discarding a transient frame, the evaluator creates one
`MaterializedContentCommitment v1` for every public result, evidence anchor,
and ContextPack excerpt that contains content. `ContextItem` has no public
content field, so there is no item-content commitment. Each commitment is
target-independent and contains only:

- canonical public repository-relative path, surface/kind, output/item/excerpt
  ordinals, reported inclusive range, public `truncated` state where present,
  exact emitted-content UTF-8 byte length, and SHA-256;
- an ordered logical-line array whose entries contain only
  `source_line_number`, `utf8_byte_length`, and SHA-256 of that emitted logical
  line payload; and
- the closed normalization ID
  `python313-utf8-replace-universal-newline-splitlines-v1`.

The normalization exactly matches the behavior-baseline source/range contract:
decode Git/source bytes as UTF-8 with replacement, apply text-I/O universal
newline translation (`CRLF -> LF`, bare `CR -> LF`), then use Python 3.13
`str.splitlines(keepends=True)`. Its closed boundary set is LF, VT, FF, FS, GS,
RS, NEL, U+2028, and U+2029 after CR translation. Hash each logical-line
payload without its recognized terminator. Preserve actual empty logical lines,
perform no Unicode normalization, and do not synthesize an extra numbered line
for a final terminator. Target resolution, feasible-cover construction,
transient commitment creation, and pinned-blob replay use this one helper and
normalization ID; an unrecognized runtime/helper blob invalidates the closure.

Transient public content is normalized by the same algorithm and assigned
consecutive source-line numbers beginning at its reported start. The projection
rejects a line count inconsistent with the reported range, except that closed
empty-content forms have no line commitments. Gold preflight rejects every
target whose normalized target-line payloads have aggregate UTF-8 byte length
zero, so such a form can never be used to prove a declared target. The
projection stores no content, prefix, suffix, literal, target marker, or
absolute byte offset.

After all six role artifacts are sealed, the finalizer reads the pinned public
Git blobs and independently recomputes canonical full-line hashes. A single
materialized segment covers a target only when it contains a consecutive entry
for every target line and every entry's length and hash equals that canonical
full source line. A range match without this exact commitment match is never
coverage. Therefore a mid-line first/last-line crop, including a single-line
crop that retains a target literal, is a materialization/excerpt miss; a full
target match also proves every already-validated frozen literal remains
present. Extra committed context lines are allowed.

Commitment count and bytes are bounded by the already emitted public segments,
lines, and bytes. They are source-free and public-repository-only. This is the
only legal post-frame proof of terminal target/literal delivery.

This separation is a causality and accidental-leak boundary, not a security
sandbox. P7A evaluates trusted repository code and makes no claim that it can
contain an adversarial product implementation with arbitrary filesystem access.
That threat model is acceptable because P7A has no post-gold candidate
implementation. A future candidate benchmark must specify a real sandbox or
explicitly retain the same trusted-code limitation.

### Observer Contract

The observer is:

- installed through a private `ContextVar`;
- non-nestable;
- reset in `finally` after success, error, cancellation, and early return;
- request-local;
- source-free;
- bounded by existing candidate/result/excerpt limits;
- ignored by serializers, feedback, formatters, CLI, and MCP output.

The hook helper returns immediately when no observer is installed. It may copy
only already-computed scalar facts. It cannot trigger a store query, source
read, embedding, planner request, graph traversal, or extra retrieval.

The product-side implementation is one stdlib-only observer module plus hooks
at the smallest orchestration points that already hold the needed values:
`retrieval.py`, `context_pack/builder.py`, `exploration/runner.py`, and
`exploration/fusion.py`. P7A does not add observer calls to acquisition,
ranking, or expansion helpers merely to mirror their internal steps.

The audit may contain:

- stable run/case/surface IDs;
- canonical public repository-relative paths;
- chunk IDs and one-based inclusive line ranges;
- source/lane and stage membership;
- canonical rank and output position;
- work counters;
- pack item paths and excerpt ranges;
- stable selector membership, closed omission decisions, and errors;
- opaque hashes and counts.

It may not contain:

- source, snippet, excerpt, or prompt text;
- private or absolute paths;
- local usernames;
- environment values;
- exception tracebacks containing source content;
- arbitrary diagnostics.

### Actual Surface DAG

The audit models a DAG, not one linear funnel:

```text
common retrieval prefix
  ordinary candidate acquisition
  -> final merged chunk population
  -> chunk ranking/cohort rerank
  -> context expansion carrier lineage
  -> actual final result/anchor selection

query
  selected result/anchor
  -> public raw materialization

context
  selected QueryBundle
  -> ContextPack selection
  -> item content
  -> excerpt allocation

explore
  initial common prefix
  -> zero or more follow-up common prefixes
  -> path fusion
  -> final ContextPack selection
  -> final excerpt allocation
```

`context` does not depend on the public raw query serialization. `explore`
records one retrieval ledger per actual call and one fusion/pack branch.

The product audit records generic candidate/path/chunk/range/order, actual
selection-membership, and already-computed pack-omission ledgers with no target
marker. It does not call `collect_trace`; only after all role artifacts are
sealed does the evaluator join resolved gold, replay the frozen final selector,
and derive, for each alternative:

1. path present in the final merged candidate population;
2. target carrier present after context expansion;
3. carrier seed chunk IDs and best carrier rank, or null;
4. every carrier's final-selection ordinal and closed selector decision;
5. target carrier present in actual final selected results/anchors;
6. selected output positions and partitions, or empty.

A `target carrier` is an actual expanded result whose range fully covers the
canonical target and whose `chunk_ids` backlink to one or more chunks in the
actual merged candidate population on the same path. The seed chunk range need
not itself cover the target: an adjacent chunk may legally create target
coverage through the existing expansion window. Candidate-target coverage is
therefore diagnostic side data, never a predecessor leaf. A delivered target
without carrier lineage is contradictory, but
`seed chunk does not cover target -> expanded carrier covers target` is valid.

Surface leaves then record:

- query: at least one public result/anchor on the canonical target path has one
  materialized-content commitment that exactly covers every canonical target
  line;
- context: pack item exists and one excerpt covers the target;
- explore: target carrier selected into a QueryBundle by any probe, fused path
  selected, final pack item exists, and one final excerpt covers target.

Every context/explore excerpt-coverage leaf uses the same full-line commitment
test. A reported range is routing metadata only and cannot make a terminal leaf
true.

Every applicable leaf is boolean, integer, closed enum, or null. Null is legal
only when the field is structurally not applicable. A missing applicable leaf,
unknown selector/omission decision, duplicate leaf key, terminal coverage
without carrier lineage, or another contradictory transition invalidates the
run instead of becoming a retrieval miss.

Quality comparison uses the existing deterministic `clock_ns` seam for every
explore call. The worker installs a closed monotonic tick sequence derived only
from retrieval-call ordinal, so public `duration_ms` bytes compare exactly
across all six quality roles. No timing field is removed or normalized.
Real-time latency uses the default clock in the separate audit-disabled P6
paired performance run and never enters quality equality.

## Public Benchmark Contract

### Source Manifest

Every source entry declares:

```text
source_id
origin
pinned_commit_or_subtree_object
source_tree_hash
language_family
independence_class
license_status
prepare_options_hash
```

Closed values:

- `language_family = java | python | frontend_generic`
- `independence_class = independent_external | in_project_fixture`

The initial profile uses:

1. Spring PetClinic at
   `51045d1648dad955df586150c1a1a6e22ef400c2`
   (`independent_external`, Java);
2. `ZhuLinsen/daily_stock_analysis` at
   `487e49e565ffd1b96a7cf4d855f99cee3c981eaa`
   (`independent_external`, Python);
3. CST commit `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`,
   subtree `tests/fixtures/real_projects/program_tool`, object
   `a8c0ace36cf82e2c743f06726944f20ce740000f`
   (`in_project_fixture`, frontend/generic).

The CST fixture contributes metrics and coverage but never satisfies the
two-independent-source dominance minimum.

### Case Selection Provenance

`CaseSelectionProvenance v1` freezes before baseline execution:

- the source task universe available for each repository;
- the deterministic inclusion/exclusion rule;
- source task/origin and authoring UTC for every case;
- whether a case directly motivated any P7A category or threshold;
- the confirmatory-cohort membership;
- author and independent label-review identities;
- complete case/profile/source manifest hashes.

At least six cases form a confirmatory cohort that did not motivate the
attribution categories or dominance thresholds. At least three confirmatory
cases come from each independent external repository. Their gold is authored
from source and task meaning before the controlled baseline is run.

This reduces selection bias but cannot prove population representativeness.
Reports therefore use `benchmark_*` terminology and include the selection
provenance hash.

### Profile Quotas

The first `p7a_route` profile contains exactly:

- three source identities;
- eighteen cases;
- at least forty-eight required evidence units;
- six cases per source;
- at least six `exact_identifier` and six
  `exploratory_cross_module` cases;
- at least four query, eight context, and four explore cases;
- at least five Java and five Python cases;
- at least twelve required Java units and twelve required Python units.

Each independent external source must contribute:

- at least two cases and four required units to each intent cohort; and
- at least one case and two required units to each surface.

Quota validation uses closed fields, not free-form tags. Missing cross-source
coverage blocks route classification.

### Case Schema V2

Conceptual shape:

```json
{
  "schema_version": 2,
  "id": "authorization-flow",
  "source_id": "petclinic",
  "surface": "context",
  "intent_cohort": "exploratory_cross_module",
  "gate": "required",
  "confirmatory": true,
  "query": "How does authorization reach the owner update operation?",
  "options": {},
  "evidence_units": [
    {
      "id": "authorization-entry",
      "required": true,
      "role": "entrypoint",
      "alternatives": [
        {
          "path": "src/main/java/example/AuthorizationInterceptor.java",
          "target": {
            "symbol": "preHandle",
            "line_range": [30, 48],
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

Closed case fields:

- `surface = query | context | explore`;
- `intent_cohort = exact_identifier | exploratory_cross_module`;
- `gate = required | known_gap | informational`;
- `confirmatory` is boolean and must agree with selection provenance.

Gate semantics:

- `required`: execution/audit completeness is mandatory and the case votes;
- `known_gap`: execution/audit completeness is mandatory and the case votes,
  but a retrieval miss is expected evidence rather than a test failure;
- `informational`: execution is reported but units and cases never enter
  dominance denominators, support counts, or route selection.

`required` on an evidence unit means the unit participates in coherent case
coverage. It does not assert that the current baseline must retrieve it.
P7A has no candidate pass threshold and therefore no ambiguous “absolute
expectation” field.

Intent validation:

- `exact_identifier` normalizes the original query to NFC, takes maximal runs
  of Unicode letter/decimal characters plus `_`, `$`, `.`, `/`, `\`, `:`, and
  `-`, strips leading/trailing `.`, `/`, `\`, `:`, and `-`, and retains a run
  only when its first remaining character is a Unicode letter, `_`, or `$`;
- retained tokens match case-sensitively and in full against an indexed
  qualified symbol, unqualified symbol, canonical path basename, or basename
  with one final extension removed; substring, stemming, case-folding, and
  planner-derived matches are forbidden;
- `exact_identifier` requires at least one retained token to resolve to a
  declared target symbol/path, freezes every token-to-path/symbol match, and
  requires every declared coherent variant to include a required choice
  whose path is in that exact match set;
- `exploratory_cross_module` requires every declared coherent variant to
  cover at least two canonical paths and two evidence roles or project units;
- a mixed request has one reviewed primary intent and counts once.

Evidence-unit rules:

- one to sixteen units per case;
- safe unique unit IDs;
- `required` boolean;
- closed role:
  `entrypoint | implementation | downstream | type | test | config | supporting`;
- one to four alternatives;
- exact canonical repository-relative path;
- exact symbol and/or one-based inclusive line range;
- zero to three NFC, case-sensitive, control-free literals;
- canonical target range of one to eighty lines;
- target must resolve in pinned source and be fully covered by an active indexed
  chunk;
- the normalized target-line payloads must have aggregate UTF-8 byte length
  greater than zero; an empty-only range is not evidence and is rejected before
  feasible-cover construction;
- symbol and line range must overlap when both exist;
- literals must occur inside the canonical target range;
- one window/excerpt must cover the complete target and all literals; unions of
  partial excerpts do not satisfy it.
- required units must have distinct resolved semantic targets; expressing the
  same resolved path/range through different symbols or literals is a
  duplicate and is rejected;
- within one coherent variant, chosen required ranges on the same path must be
  pairwise non-overlapping under inclusive line semantics; alternatives that
  are never co-selected may overlap.

Coherent-variant rules:

- one to sixty-four variants;
- each variant selects exactly one alternative for every required unit;
- duplicate semantic choice sets are rejected;
- every alternative of every required unit occurs in at least one variant;
- validation and finalization use semantic choices, never variant IDs or
  declared order;
- optional units are diagnostic and never fail or vote.

There is no separate or implicit `score-eligible` state. Every declared variant
that selects exactly one alternative for each required unit is a complete
variant and is validated, witnessed, and finalized. Case gate controls only
whether its finalized required units vote; `informational` variants still must
be structurally valid.

### Joint Feasibility Before Baseline

`FeasibleCoverWitness v1` prevents an impossible gold set from being counted as
a retrieval miss. It is computed and independently reviewed before any
controlled baseline output exists.

The frozen source/target-only helper uses only pinned source/index structure,
resolved targets, case options, and the behavior baseline's public capacities.
It never invokes CST retrieval, a comparator, a model, an oracle, or a future
candidate. For every coherent variant it:

1. resolves each chosen target to the active indexed chunks and all legal
   materialized windows that fully cover it;
2. groups targets by canonical path and enumerates legal result/excerpt cover
   atoms under the exact line and UTF-8 byte rules;
3. computes the minimum simultaneous cover by lexicographically minimizing
   `(result_slots, item_count, excerpt_count, serialized_utf8_bytes,
   semantic_cover_key)`;
4. checks the real surface limits: query result/anchor partitions and result
   range bounds; or context/explore QueryBundle/fusion capacity plus
   every frozen `ContextPackOptions` field:
   `max_items`, `max_excerpts_per_item`, `max_excerpt_bytes`,
   `max_item_content_bytes`, `max_total_content_bytes`, `max_pack_bytes`,
   `context_before_lines`, and `context_after_lines`; and
5. emits only semantic choices, canonical paths/ranges, selected chunk/window
   IDs, partition assignments, item/excerpt/byte counts, limit values, and
   hashes—never source text.

Every declared complete variant must have one complete simultaneous witness,
and each case must therefore have at least one. A per-unit union of separately
feasible choices is not a witness. A case or variant without a witness is an
invalid benchmark input and is rejected before baseline execution; it is never
reported as a miss. A required target that fits aggregate item/total/pack
budgets but exceeds `max_excerpt_bytes` is specifically infeasible.

The witness manifest binds the helper Git blob, options hash, source/index
identity, case/variant semantic keys, and per-variant witness hash. The
independent label reviewer verifies the witness against the pinned source and
budgets. Gold freeze and evaluator closure both bind the accepted manifest.

### Gold Freeze

Gold authoring reads only pinned source, task meaning, and declared surface
budgets. It must not read the controlled P7A baseline, an external comparator,
or future implementation output.

`GoldFreezeInputs v1` binds:

- behavior baseline commit;
- source and case-selection manifests;
- fixture/profile hashes;
- coherent-variant manifest;
- exact-identifier token/match report;
- feasible-cover witness manifest and helper/options hashes;
- case author and distinct reviewer;
- target-resolution report;
- evaluator contract version;
- progress-vector, terminal-reason, metric, oracle, and route-decision contract
  hashes;
- freeze UTC.

After those bytes are committed, `GoldProvenanceSeal v1` binds their Git blobs
and `P7A_GOLD_FREEZE_COMMIT`. Runtime commands accept only the resolved join of
the two states. Any query, target, variant, profile, source pin, quota, metric,
oracle, finalizer, reason map, metric, threshold, or decision correction
requires a reviewed benchmark-contract amendment, a new gold freeze, and a
disclosed old/new baseline-effect report. It is never classified as an
instrumentation retry, and files are never edited in place to make a result
look better.

## Variant Finalization Without Frankenstein Evidence

Every declared coherent variant is evaluated independently. Evidence choices
from different variants are never combined.

Each surface freezes an ordered applicable leaf chain from acquisition at
depth 1 to terminal delivery at depth `D`. For required unit `u` in complete
variant `v`, `reached(v,u)` is the greatest depth whose leaf and every
predecessor leaf are true. The exact progress vector is:

```text
progress(v) = (
  count(reached(v,u) >= D     for required u),
  count(reached(v,u) >= D - 1 for required u),
  ...
  count(reached(v,u) >= 1     for required u)
)
```

Vectors are compared lexicographically from the deepest count to the
acquisition count. Counts, dimension order, and direction are therefore closed;
implementations cannot substitute summed depths, average recall, or an
ID/path-based tie-break.

For a case:

1. evaluate every complete feasible variant and assign exactly one
   `diagnostic_terminal_reason` to each `(variant, required unit)` pair;
2. if any variant terminally satisfies every required unit, retain all fully
   satisfied variants and mark the case satisfied;
3. otherwise retain every variant tied for the lexicographically maximal
   progress vector;
4. retain the minimum semantic choice key only as a reproducible diagnostic
   backlink; it cannot affect metrics or votes;
5. for each required unit, publish every tied variant's alternative semantic
   key and `diagnostic_terminal_reason`;
6. derive a separate unit vote state by exactly three branches:
   - if every retained reason is one of `satisfied`, `satisfied_initially`, or
     `satisfied_by_followup`, emit `unit_satisfied` and exclude the unit from
     the miss denominator;
   - if every retained reason is non-satisfied and maps to the same route group,
     emit that group; or
   - otherwise emit `unit_mixed`, including every satisfied/non-satisfied mix;
7. `unit_mixed` stays in the miss denominator but contributes to no route-group
   numerator; it is voting ambiguity, never a fabricated terminal reason; and
8. a failed case casts a route-group vote only when one group is its unique
   largest unambiguous unit group, otherwise it casts `case_mixed`.

Variant IDs, array order, canonical path lexicography, or alternative indices
cannot decide a reason-group vote. Permuting unit/variant IDs and order while
preserving semantic choices leaves metrics and route selection unchanged.

## Terminal Attribution

Each `(complete variant, required unit)` receives exactly one diagnostic
terminal reason on its surface. There is deliberately no invented single
reason for a unit whose tied variants disagree.

Closed reasons:

| stage group | terminal reasons |
| --- | --- |
| path acquisition | `path_not_acquired`, `path_not_acquired_after_all_probes` |
| target-span acquisition | `target_span_not_acquired`, `target_span_not_acquired_after_all_probes` |
| span materialization/ranking | `target_below_rank_cutoff`, `target_below_rank_cutoff_after_all_probes`, `query_bundle_target_span_missing`, `raw_target_not_materialized` |
| surface selection | `raw_selection`, `raw_selection_after_all_probes`, `fused_selection` |
| pack/excerpt | `pack_selection`, `pack_budget_or_policy`, `excerpt_allocation_or_cropping`, `final_pack_selection`, `final_pack_budget_or_policy`, `final_excerpt_allocation_or_cropping` |
| satisfied | `satisfied`, `satisfied_initially`, `satisfied_by_followup` |

Every non-satisfied reason maps to exactly one route group. Unknown reasons
invalidate the report.

The first false applicable leaf selects the reason. Later leaves cannot
override it.

For `query`, the exact chain is:

```text
candidate-merge path present
  -> expansion-created target carrier present
  -> at least one carrier is not excluded solely by partition rank capacity
  -> target carrier selected into result/anchor partition
  -> any one public result/anchor content commitment exactly covers target
```

The first failures map respectively to `path_not_acquired`,
`target_span_not_acquired`, `target_below_rank_cutoff`, `raw_selection`, and
`raw_target_not_materialized`.

For the last transition, a matching path/range with a missing or mismatched
target-line commitment is false. It does not borrow content from another output
position.

The “final-selection input cut” is not a newly materialized product list. From
the enabled audit's already-existing expanded-order scalars, the frozen
evaluator replays the exact behavior-baseline partition classification,
eligibility, deduplication key, and capacity rule and assigns a one-based
pre-limit ordinal separately for results and evidence anchors. Each carrier has
one closed decision:
`selected_result | selected_anchor | result_limit | anchor_limit |
duplicate_anchor`. If every target carrier is excluded only by
`result_limit`/`anchor_limit`, the reason is `target_below_rank_cutoff`. If at
least one carrier has `duplicate_anchor`, but no target carrier is selected,
the reason is `raw_selection`. These conditions are
mutually exclusive. Synthetic conformance tests require the evaluator
projection to reproduce `split_results_and_anchors`; audit-disabled product
execution does not request `collect_trace` or allocate this projection.

For `context`, the query carrier and exact final-selector decision nodes run
first, followed by:

```text
candidate-merge path present
  -> expansion-created target carrier present
  -> at least one carrier is not excluded solely by partition rank capacity
  -> target carrier selected into QueryBundle
  -> QueryBundle target-range membership
  -> final stable ContextPack selector membership
  -> item emitted
  -> one excerpt content commitment exactly covers the complete target
```

The first three failures use `path_not_acquired`,
`target_span_not_acquired`, and `target_below_rank_cutoff`. A carrier excluded
by a non-rank final-selector decision is `raw_selection`, not a rank miss. If a
target carrier is selected but the QueryBundle path exists without the target
range, the reason is `query_bundle_target_span_missing`. A QueryBundle target
omitted by the final stable pack selector is `pack_selection`. A
stable-selected target with no emitted item is `pack_budget_or_policy`, and the
observer must record one of the closed omission decisions
`item_budget | item_bytes | pack_bytes | policy`. An emitted item without one
covering excerpt is `excerpt_allocation_or_cropping`.

For `explore`, the chain aggregates the same carrier and final-selector nodes
across actual probes without combining alternatives:

```text
path acquired by any probe
  -> expansion-created target carrier present in any probe
  -> a target carrier is not excluded solely by rank capacity in any probe
  -> target carrier selected into a probe QueryBundle
  -> target range enters a probe QueryBundle/fusion input
  -> target survives fusion
  -> final stable pack selector membership
  -> final item emitted
  -> one final excerpt content commitment exactly covers the complete target
```

The first failures map to `path_not_acquired_after_all_probes`,
`target_span_not_acquired_after_all_probes`,
`target_below_rank_cutoff_after_all_probes`,
`raw_selection_after_all_probes`, `query_bundle_target_span_missing`,
`fused_selection`,
`final_pack_selection`, `final_pack_budget_or_policy`, and
`final_excerpt_allocation_or_cropping`. The rank reason applies only when every
probe carrier is excluded solely by partition capacity; any applicable
non-rank exclusion with no selected target uses the raw-selection reason.
Satisfaction records whether the covering evidence was present initially or
first appeared in a follow-up.

Query cannot emit pack/excerpt reasons, context never uses public query
serialization as a prerequisite, an acquired seed chunk may become successful
through adjacent expansion, and a path hit without a target carrier is not span
success. Null is allowed only for a leaf excluded by the surface DAG; a missing
applicable leaf or missing final/stable selector/omission decision invalidates
the entire role run.

## Metrics

Metrics are computed only after six-role equality is proved, from the canonical
`instrumentation-enabled-a` role. The equal roles are evidence, not six samples.

For case `c` and required unit `u`, let `A(c,u)` be the nonempty set of distinct
alternative semantic keys chosen for `u` by the retained complete variants.
The set removes duplicate appearances of the same alternative in different
variants. A `metric_unit` is the single stable `(case_id, unit_id)` pair, not a
`(variant, unit)` occurrence. Adding or recombining variants without changing
any `A(c,u)` therefore cannot change a metric. Optional units are excluded.

For an applicable boolean stage `S`:

```text
unit_hit(c, u, S) =
  1 iff every distinct alternative in A(c,u) satisfies S, else 0

unit_micro(S, slice) =
  sum(unit_hit) / count(applicable metric_unit)

case_macro(S, slice) =
  exact mean over cases with a nonempty denominator of
  sum(unit_hit in case) / count(applicable metric_unit in case)
```

The mean is stored as a reduced rational plus contributing-case count. Every
view stores its raw hit/total counts. A zero denominator produces null, never
zero, and cannot be silently dropped from an applicable case. A raw audit leaf
that is legitimately downstream of an earlier false leaf may be null, but its
unconditional later-stage `unit_hit` is false; a missing leaf that should have
been observed still invalidates the role.

The six recall metrics are closed as follows:

| metric | applicable surfaces | one alternative satisfies when |
| --- | --- | --- |
| path acquisition recall | query, context, explore | its canonical path is in the actual final merged seed population; explore uses any actual probe |
| seed target-span acquisition recall | query, context, explore | one actual merged seed chunk on that path fully covers its canonical target range |
| expansion-carrier recall | query, context, explore | one actual expanded result satisfies the frozen target-carrier lineage definition |
| surface terminal recall | query, context, explore | query has an exact covering public result/anchor commitment, or context/explore has an exact covering final excerpt commitment |
| ContextPack item recall | context, explore only | the actual final pack emits an item carrying that target lineage; any earlier-stage miss is false |
| excerpt recall | context, explore only | one actual final excerpt commitment exactly covers the complete target; any earlier-stage miss is false |

Query serializes null item/excerpt metrics and is excluded from their
denominators by surface declaration. The seed metric is diagnostic side data,
not a route predecessor: an adjacent seed may make expansion-carrier recall true
while seed target-span recall is false.

The remaining diagnostics have separate, closed aggregation contracts:

- `best_target_carrier_rank` uses each distinct
  `(case_id, unit_id, alternative_semantic_key)` in `A(c,u)` once. Rank is the
  minimum one-based ordinal in the actual final merged expanded carrier order
  before partition limits. For explore, the evaluator constructs one canonical
  fusion-input stream by concatenating the initial call first and then
  follow-up probes in ascending recorded `probe_ordinal`; within each call it
  preserves that call's actual final merged expanded-carrier order. The
  one-based ordinal is the position in this pre-fusion, pre-deduplication
  flattened stream, and a target present in more than one call uses its minimum
  global ordinal. It is neither a per-probe local rank nor the final fused
  output ordinal. No carrier is represented by null and counted in
  `missing_rank_count`, never discarded.
  Each case and aggregate slice store atom count, present count, missing count,
  sorted present ranks, min/max, and nearest-rank p50/p90
  (`sorted[ceil(p*n)-1]`); numeric fields are null when present count is zero.
  It has no invented unit-micro or case-macro scalar.
- `unique_public_result_path_ratio` uses the canonical final public result
  partition for each case, after fusion for explore and excluding evidence
  anchors. Per case it is `unique_canonical_path_count / result_slot_count`,
  null when there are zero result slots. Its pooled view is
  `sum(unique_canonical_path_count) / sum(result_slot_count)` and its case-macro
  view is the exact mean of non-null case ratios.
- `duplicate_result_slot_count` for a case is
  `result_slot_count - unique_canonical_path_count`. Aggregate slices store the
  integer sum and exact mean over every applicable case, including zero counts.
- `terminal_reason_counts` count each distinct semantic-choice atom in
  `A(c,u)` once. The same semantic choice producing different actual reasons in
  two retained variants invalidates finalization. `unit_mixed_count` counts each
  finalized required unit once; `case_mixed_count` counts each failed case once.
  None is normalized by variant count.

Every metric is emitted for `all_profile` and recomputed independently for the
closed source, surface, primary-intent, language, confirmatory, and gate slices.
An atom belongs to the strata of its case; slices never duplicate an atom
inside one result. Recall slices use the exact unit-micro/case-macro rules above;
rank slices use the rank distribution contract; result-population slices use
their pooled/case rules; count slices use integer sums and stated case means.
Only the decision-eligible gate slice can support route diagnostics.

Metrics are computed only by the frozen evaluator from raw leaves and resolved
gold. Product code cannot provide aggregate counts, pass booleans, terminal
reasons, or route classifications.

## Label-Assisted Oracle Diagnostics

Oracles are evaluation-only upper bounds. They may use gold after actual
retrieval leaves exist, but they cannot mutate the actual run or authorize a
production mechanism.

### File Oracle

Within the actual acquired, expanded, surface-selector input population and
actual surface capacity, perform a gold-assisted carrier/set selection while
preserving result/anchor or fusion partition rules. For each actual
deduplication key, including `(anchor_kind, canonical path)`, it may retain at
most one actual representative and may prefer an already-existing target
carrier over a non-target representative with that same key. It may then order
the retained keys/paths for the coherent variant ahead of other actual keys.
For explore it applies the same rule independently to each actual probe
population and to actual fusion representatives. It answers:

> If the current carrier population had ideal file/set/representative
> selection, how many additional required units could reach the surface?

It cannot add a path absent from actual acquisition, create or alter a carrier,
change a deduplication key, exceed a partition/capacity, combine representatives
from different alternatives, or intervene at a downstream pack/excerpt node.
The oracle stops after the exact failed surface-selection or fusion leaf
becomes true; it neither replays nor assumes any downstream pack/excerpt leaf.
It may recover only `raw_selection`, `raw_selection_after_all_probes`, or
`fused_selection`.
Query/context duplicate-anchor cases, explore duplicate-carrier cases, and
fusion representative replacement are mandatory conformance tests.

### Span Oracle

Within actual acquired seed chunks and their legal expansion-carrier windows,
force target carriers through the existing ranking/materialization boundary
while preserving actual path population, surface capacity, partitions,
source/window bounds, and output budgets. It answers:

> If the current path population had ideal span choice/materialization, how
> many additional required units could cross their failed span/materialization
> boundary?

It cannot add a path or seed chunk, enlarge the frozen expansion window, create
a carrier that no actual seed can legally materialize, or select a path that an
ideal carrier ordering/materialization still leaves outside the surface
boundary. It may recover only `target_below_rank_cutoff*`,
`query_bundle_target_span_missing`, or `raw_target_not_materialized`.
The span oracle stops after the exact false leaf named by that reason becomes
true. It does not replay or assume a later selection, fusion, pack, or excerpt
decision.

### Pack Oracle

Within the actual QueryBundle and actual ContextPack item/excerpt/byte budgets,
force the coherent required paths and target ranges through the existing pack
shape. It answers:

> If the same input bundle had ideal pack/excerpt allocation, how much
> additional evidence could be delivered?

It cannot add a candidate file or target span, alter QueryBundle/fusion, or
exceed actual budgets. It may recover only `pack_selection`,
`pack_budget_or_policy`, `excerpt_allocation_or_cropping`, or their `final_*`
forms. Only recovery of an excerpt-allocation leaf, which is terminal in the
surface DAG, may also make the unit terminally satisfied; an earlier pack-group
boundary remains stage-local.

Each oracle evaluates every complete coherent variant separately against that
same variant's immutable actual leaves. Each non-noop certificate performs
exactly one typed intervention at its mapped first-false leaf; one canonical
no-op certificate is always legal and changes no leaf. All actual leaves remain
unchanged; downstream counterfactual leaves are `not_evaluated`, never copied,
replayed, idealized, or filled from a feasible-cover witness. Every oracle
therefore proves stage-local headroom. A certificate may additionally report
new terminal satisfaction only when the mapped first-false leaf is itself the
terminal leaf of that surface DAG: query `raw_target_not_materialized` for the
span oracle, or `excerpt_allocation_or_cropping` /
`final_excerpt_allocation_or_cropping` for the pack oracle. Recovering
`pack_selection`, `pack_budget_or_policy`, or any other nonterminal leaf cannot
assume its later leaves. For variant `v`:

```text
certificate_lift(v, c) = (
  newly_mapped_boundary_recovered_required_count
)

oracle_lift(v) = max(certificate_lift(v, c) for legal certificate c)
```

There is deliberately no secondary cross-reason or downstream tie-breaker. A
unit is boundary-recovered only when its actual reason belongs to that oracle's
exact group and the oracle changes that reason's first-false leaf from false to
true using a legal in-population intervention. The no-op has lift zero and is
the maximal certificate only when no legal typed intervention has positive
lift.

For each `(oracle, variant)`, let `C*` be the complete mathematical set of legal
certificates tied at that variant's maximal lift.
`variant_supported_units = intersection(recovered_units(c) for c in C*)`;
choosing the first enumerated certificate is forbidden. The implementation need
not serialize an exponentially large `C*`. It deterministically proves the same
intersection by recording one semantic-min maximal witness and, for every
candidate unit `u`, the constrained optimum when `u` is not recovered plus its
semantic-min countercertificate. Unit `u` is universally supported only when
that constrained optimum is strictly below the maximal lift; equality excludes
it. Synthetic exhaustive enumeration must match this bounded proof.

The evaluator then retains every variant tied at the case's maximal lift and
computes `case_supported_units` as the intersection of
`variant_supported_units` across those tied variants. Per-unit maxima from
different certificates or variants are forbidden. Tied variant keys, actual
reasons, bounded maximality/countercertificates, both intersection levels, and
recovered-boundary certificates remain in the diagnostic report. Permuting
carriers, certificates, variants, or their IDs cannot change support.

The exact route-to-oracle map is:

| route group | required diagnostic |
| --- | --- |
| path acquisition | none; an oracle may not add a missing path |
| target-span acquisition | none; an oracle may not add a missing legal target carrier |
| span materialization/ranking | span oracle |
| surface selection | file oracle |
| pack/excerpt | pack oracle |

Oracle headroom for a different group, a `unit_mixed` unit, or an unrelated
unit cannot support the route.

Oracle results report feasible stage-local lift, not terminal product lift or
expected product lift. No upstream oracle may claim that a downstream pack
would accept its counterfactual input. A later mechanism design must identify
product-visible signals and prove its own end-to-end A/B.

## Route Decision Algorithm

Only `required` and `known_gap` cases vote. Informational cases, deterministic
mechanics, private data, comparator data, oracles, and audit-disabled runs never
vote.

1. Validate gold, source pins, case-selection provenance, profile quotas,
   worker/evaluator identity, audit completeness, and repeat/neutrality proofs.
   Failure produces no route decision.
2. Finalize per-variant diagnostic reasons and derive each unit's separate
   vote group through the variant rules.
3. Remove only units whose derived state is `unit_satisfied`; a
   satisfied/non-satisfied variant mix remains `unit_mixed`.
4. If no decision-eligible misses remain, select `no_proven_gap`.
5. Map misses to the five route groups.
6. Compute unit counts, `unit_mixed`, case votes, and `case_mixed`.
7. A group is dominant only if it is the unique top group in both unit counts
   and case votes and all conditions hold:
   - at least six grouped unit misses;
   - at least three failed cases;
   - at least three unit misses for the group;
   - at least three case votes for the group;
   - supporting case votes from two distinct `independent_external` source IDs;
   - at least one supporting confirmatory case vote from each independent
     external source;
   - unit share at least `0.50`;
   - unit lead at least `0.15`;
   - case-vote share at least `0.50`;
   - case-vote lead at least `0.15`.
8. Exact formulas are:

   ```text
   M = all decision-eligible misses, including unit_mixed
   U1 = top group unit count
   U2 = max(other group counts, unit_mixed)
   unit_share = U1 / M
   unit_lead = (U1 - U2) / M

   F = all failed decision-eligible cases, including case_mixed
   C1 = top group case votes
   C2 = max(other group case votes, case_mixed)
   case_share = C1 / F
   case_lead = (C1 - C2) / F
   ```

   Boundaries use integer cross-products, not rounded floats.
9. Compute the same dominance result for each closed intent cohort and surface
   only when its misses include three cases and both independent external
   sources. Language/source strata remain descriptive.
10. Independently reconcile the decision-eligible confirmatory-only slice. For
    the globally dominant group `G`, `G` must be the unique top value in both
    confirmatory unit counts and confirmatory case votes, with `unit_mixed` and
    `case_mixed` participating as competitors. It must retain at least one
    supporting case vote from each independent external source, and its
    confirmatory unit share, unit lead, case-vote share, and case-vote lead must
    satisfy the same `0.50`, `0.15`, `0.50`, and `0.15` boundaries using only
    confirmatory denominators. Here `Mc`, `Fc`, `UGc`, `U2c`, `CGc`, and `C2c`
    are exactly `M`, `F`, `U1`, `U2`, `C1`, and `C2` from step 8 restricted to
    confirmatory cases and evaluated for `G`. A missing denominator, tie,
    different top group, lost cross-source support, or threshold miss is closed
    as `confirmatory_inconclusive_or_conflicting`; it is not silently ignored.
    This slice is intentionally a direction check rather than a second
    independent dominance election: when the global absolute minima already
    pass, exactly two confirmatory failed cases/two supporting units, one from
    each external source, may support `G` if all four confirmatory ratios are
    `1.0`.
11. If global dominance is absent, select `benchmark_mixed_expand`; cohort or
    confirmatory dominance cannot upgrade it.
12. If any eligible intent/surface cohort has a dominant group different from
    the global group, two eligible cohorts disagree, or confirmatory
    reconciliation does not support the global group, select
    `benchmark_mixed_expand`.
13. Otherwise map path acquisition to
    `benchmark_path_acquisition_dominant`, target-span acquisition to
    `benchmark_target_span_acquisition_dominant`, and the remaining groups to
    their matching `benchmark_*_dominant` outcomes.
14. Path- and target-span-acquisition outcomes require no oracle because the
    allowed oracles cannot add the missing population.
15. For span materialization/ranking, surface selection, and pack/excerpt
    outcomes, count only units in each case's `case_supported_units` from the
    two-level certificate/variant intersection. Require the exactly mapped
    oracle to recover the mapped first-false boundary for at least two
    matching-group units in two cases with one case from each independent
    external source. If it does not, select `benchmark_mixed_expand`. Oracle
    support demonstrates stage-local headroom only; the next phase still starts
    with a product-visible-signal design.

The route record lists every threshold numerator/denominator, confirmatory
support key, confirmatory-only counts/shares/leads/reconciliation state, cohort
result, oracle headroom, rejected route, and open risk.

## Baseline Neutrality

The instrumentation commit is distinct from the behavior baseline. The harness
runs the complete profile in six roles from byte-identical prepared copies:

```text
behavior baseline, audit disabled, run A
behavior baseline, audit disabled, run B
instrumentation tree, audit disabled, run A
instrumentation tree, audit disabled, run B
instrumentation tree, audit enabled, run A
instrumentation tree, audit enabled, run B
```

The proof binds role-specific commit/tree, source/index, configuration,
runtime/dependency, environment-presence, run ID, and UTC envelopes. It then
requires:

- repeat equality within behavior-disabled roles;
- repeat equality within instrumentation-disabled roles;
- repeat equality of instrumentation-enabled public-output hashes/projections
  and audit leaves;
- behavior-disabled versus instrumentation-disabled public-output
  hashes/projections and work equality;
- instrumentation-disabled versus instrumentation-enabled public-output
  hashes/projections and work equality;
- byte equality includes every public timing field because all six quality
  roles use the same frozen deterministic clock protocol before the transient
  public bytes are hashed;
- each single-case worker's actual product-module closure is a subset of the
  frozen allowlist for its exact `(product-tree role class, case ID, surface)`
  key, contains the key's required roots, and excludes `quality` and evaluator
  modules;
- A/B repeats have exact closure equality for the same key; neither closures
  from different cases/surfaces nor behavior and instrumentation closures are
  required to equal one another because their legitimate imports differ; and
- zero observer state after every run.

Audit reports exist only for enabled roles. The document never claims audit
code executed at the behavior baseline commit.

## Evaluator Closure Before First Run

Before the first controlled `p7a_route` profile execution, the instrumentation
commit and a sorted `path -> Git blob OID` manifest are frozen. The manifest
covers the complete transitive P7A evaluation boundary:

- the top-level worker shim, request/frame validators, observer value/enums,
  content-commitment builder, and hook projection helpers;
- artifact schema and canonical JSON implementation;
- case, source, target, exact-identifier, gold, and feasible-cover resolvers;
- surface chains, selection projection, progress vector, finalizer, terminal
  reason map, metrics, oracles, thresholds, and route decision;
- attempt/review-round allocator and validator,
  disposition/lineage/definition-effect/finding-scope builders,
  review-candidate/evidence projection, final-tree verifier, and publisher; and
- fixed profile, source, selection-provenance, gold, label-review, and
  feasible-cover inputs.

The closure command verifies each path is tracked at the instrumentation or
gold-freeze commit, recomputes every blob OID without importing the product
worker, records the evaluator import closure plus a closed worker allowlist for
every `(behavior-disabled | instrumentation-disabled |
instrumentation-enabled, case ID, surface)` key, and emits one
domain-separated digest at a create-only content-addressed path. Each allowlist
is a statically resolved permitted superset, not an assertion that query,
context, and explore load the same modules. The sealed attempt manifest, every
role run, baseline identity, route decision, publish receipt, and evidence
review bind that digest.

For a newly reserved attempt, its controlled role directory must be absent
until that attempt's closure and sealed manifest exist. Older immutable
attempts may predate a replacement closure; they remain disclosed and are
linked by their own closure hashes, but they do not violate the new
attempt-scoped guard.

The closure embeds two disjoint, closed path-to-blob maps. The
`contract_governed_blobs` map contains the reviewed design/plan payload
identities; `p7a_contracts.py`, `p7a_evaluator.py`, the artifact schema,
`tests/test_p7a_contracts.py`,
`tests/fixtures/p7a_retrieval_quality/contracts.json`, the Task 1
`docs/benchmarks/p7a/README.md` marker template, and schema examples; all
Task 2 case/gold/profile/finalizer/oracle/decision tests; and every Task 3
selection-provenance, case/profile, source-pin, gold, label-review, and
feasible-cover input. The
`corrective_implementation_paths` map contains only the behavior-neutral product
hooks and their compatibility tests, the isolated worker, CLI wiring,
runner/lifecycle/publisher implementations, and their
runner/attempt/publication tests. A path cannot appear in both maps, and a
semantic path outside both maps invalidates successor construction.

A reviewed amendment returns to every owning **code** TDD checkpoint touched by
its governed delta: Task 1 for schema/registry/contracts and their exact
test/fixture/benchmark-README marker template, and Task 2 for evaluator,
profile-validation, gold-validation, finalizer, oracle, metric, and decision
semantics plus their exact tests. The successor proof binds each resulting
contiguous checkpoint fix chain; changing a checkpoint-owned contract without
its owning test, or changing such a test outside amendment mode, rejects.

Task 3 is governed benchmark data, not a fifth code checkpoint. A data-only
selection/profile/source/gold amendment leaves every Task 2 selected test blob
and the existing four-checkpoint TDD manifest unchanged, and instead must
rebuild the deterministic selection provenance, independent label review,
simultaneous feasible-cover witness, `GoldFreezeInputs`, post-commit
`GoldProvenanceSeal`, evaluator closure, definition-effect report, and
successor attempt. The successor verifier proves that all checkpoint-owned
code/schema/test blobs are unchanged from the bound manifest. If the amendment
also changes a validator or governed test, it additionally extends checkpoint
1 or 2, as applicable, before rebuilding the data lineage. Missing either the
required data lineage or the required code-checkpoint fix rejects.

A finalizer, reason, oracle, metric, threshold, decision, feasible-cover,
schema, governed test, gold, or reviewed-payload change therefore requires a
reviewed benchmark-contract amendment, new gold freeze, new
content-addressed closure, a new attempt, and an old/new baseline-effect
report. Calling it “instrumentation-only” does not make it corrective.

## Immutable Baseline Attempts

Every baseline attempt has:

```text
b-<instrumentation-commit-first-12-hex>-aNN
```

Attempt creation has two immutable states:

1. a content-addressed lineage-successor proof may be prepared, but does not
   consume a disposition; an atomic create-only allocator takes the ledger
   lock, revalidates that proof, and commits the lowest unused root plus
   `reservation.json`, binding ordinal, behavior/instrumentation commits,
   gold/closure/TDD hashes, the proof/root, creation UTC, and root; then
2. repository preparation performs no retrieval and
   `attempt.json` is created exactly once before any role run.

The sealed `attempt.json` identity binds:

- behavior and instrumentation commits/trees;
- gold, evaluator closure, and the frozen P7A TDD manifest;
- runtime/dependency and sanitized environment presence;
- prepared source/index identities;
- reservation hash/UTC, lineage root, and ignored attempt root.

All attempt-local raw runs, copies, proofs, summaries, review inputs, and
publication receipts remain below that create-only root and repeat the sealed
attempt hash. The already-created content-addressed lineage candidate remains
in its seal root and is referenced by hash from the reservation. A reservation
is not a baseline attempt eligible for finalization until `attempt.json` exists.

Every abandoned or invalidated root receives exactly one create-only
`attempt-disposition.json`. It binds the latest available predecessor
(`reservation.json`, `attempt.json`, or `complete.json`), last completed
step/case, all existing partial-byte hashes, UTC, and one closed reason.
External reasons additionally require independent host evidence and set
`retry_authorized=true`. All other reasons set `retry_authorized=false`, bind
the required successor kind, and, when applicable, bind the review candidate
and all three reviewer-record hashes:

```text
external:
  runner_startup_external | host_signal_external |
  storage_failure_external | host_resource_exhaustion_external

non-retryable:
  implementation_invalid | contract_invalid | provenance_invalid |
  repeat_invalid | neutrality_invalid | audit_invalid | quality_invalid |
  decision_invalid | review_rejected | manual_cancelled |
  declared_timeout | undeclared_timeout

required successor:
  corrective_commit | reviewed_contract_amendment | abandon_phase
```

For a non-draft `review_rejected`, the disposition builder derives the successor
from strict finding scopes; callers cannot supply it. Any blocker/major touching
a governed path, both maps, an unlisted path, gold, reviewed payload, schema,
reason/oracle/metric/threshold/decision, feasible-cover rule, or reviewed
semantics selects `reviewed_contract_amendment`. Only a set confined wholly to
the corrective map with unchanged reviewed semantics may select
`corrective_commit`.

No successor may satisfy that enum by assertion alone. Before allocation, a
create-only content-addressed `P7ALineageSuccessorProof v1` proposes every
still-unconsumed predecessor disposition in deterministic order and produces
one domain-separated lineage-root hash. The proof alone is non-consuming.
Only the allocator's committed `reservation.json`, created while holding the
ledger lock after a fresh scan, consumes those dispositions. Concurrent or
orphan candidate proofs have no ledger effect:

- `genesis` has no predecessor and is legal only for the first attempt;
- `external_retry` accepts only `retry_authorized=true` dispositions, keeps
  behavior/instrumentation commit, gold seal, evaluator closure, TDD manifest,
  and review payload hashes identical, and binds host evidence;
- `corrective_commit` requires the new instrumentation commit to descend from
  the failed commit, byte-identical reviewed payloads/gold and every
  `contract_governed_blobs` entry, a nonempty delta wholly inside
  `corrective_implementation_paths`, a new contiguous TDD fix-chain tip, and a
  changed evaluator-closure digest; governed, docs-only, mixed-set, or unrelated
  deltas reject; and
- `reviewed_contract_amendment` binds newly PASS-reviewed design/plan payloads,
  the amended semantic blob set, new gold seal and closure, the new TDD
  manifest where code changed, and a strict old/new definition-effect report
  recomputed only from the predecessor's already sealed role artifacts. The
  report's closed status is:
  - `computed` only when all six old roles exist and the new definition can
    mechanically replay them;
  - `unavailable_no_complete_role_set` when any old role is absent; or
  - `unavailable_incompatible_old_evidence` when all six exist but a closed
    incompatibility (`missing_required_old_field`, `case_or_unit_domain_change`,
    `observation_domain_change`, or `normalization_or_schema_change`) prevents
    replay.
  Both unavailable forms bind every old role/partial hash, the exact old/new
  required-field and case/unit-domain manifests, and make no effect claim. The
  builder must compute compatibility and rejects a caller-selected unavailable
  status when replay is possible. It cannot read a new controlled baseline
  before reservation.

The ledger verifier rejects an unconsumed required predecessor, a disposition
bound by two reservations, a proof whose mode disagrees with
`required_successor`, or a semantic identity/delta mismatch. A candidate proof
not bound by a reservation is ignored for consumption and may never authorize
a role. Reservation commit is a single atomic directory publication under the
ledger lock; a crash before publication leaves only an ignored temporary root,
while a crash after publication leaves a complete reservation. Reservation,
sealed attempt, complete attempt, baseline identity, review candidate, agent
reviews, evidence review, route, and publication receipts all bind the same
lineage root. This is the executable proof that a non-retryable failure was not
evaded with a docs-only commit or unchanged evaluator/product bytes.
`required_successor=abandon_phase` has no legal successor proof and permanently
stops allocation for that lineage.

Retry and disposition rules prevent cherry-picking:

- one atomic create-only allocator scans the ledger and creates the lowest
  unused legal ordinal; callers never hard-code `a01` or choose an ordinal;
- if `a01` through `a99` are occupied, allocation fails closed and requires a
  reviewed lineage amendment; it never wraps or reuses an ordinal;
- before `complete.json`, a same-commit retry is allowed after a
  machine-verifiable external infrastructure failure: externally failed runner startup,
  storage I/O failure, host resource exhaustion, or a process signal/host
  termination that is independently recorded by the host;
- worker exception, traceback, nonzero exit, abort, or unexplained crash is an
  implementation failure and is not retryable as external termination;
- the failed attempt remains immutable and its disposition is sealed before a
  fresh ordinal is allocated; a pre-seal failure binds the reservation hash, a
  post-seal failure binds the sealed attempt hash, and a post-completion review
  rejection binds the complete attempt plus review evidence;
- a retry creates new prepared repositories and consumes no run, leaf, proof,
  summary, or publication byte from the failed attempt;
- gold joining, variant finalization, oracle execution, and route aggregation
  are forbidden until all six strict role-run files are complete and sealed;
- manual cancellation, declared or undeclared timeout, assertion, schema, provenance,
  repeat, neutrality, audit completeness, quality, decision, or review failure
  is not an infrastructure failure;
- schema, provenance, repeat, neutrality, audit completeness, quality,
  decision, or review failure is not retryable with unchanged implementation
  bytes; its disposition requires a corrective commit or reviewed contract
  amendment and a new closure/attempt lineage;
- a `complete.json` with `review_rejected` disposition is ineligible even
  though its route bytes remain immutable;
- a draft-only rejected review round does not create an attempt disposition or
  rerun the baseline; it must be closed by its own immutable round disposition
  and superseded by the next create-only review round;
- the publisher selects the lowest ordinal complete eligible attempt in its
  lineage and verifies every earlier root has exactly one closed disposition;
  the final ledger also discloses predecessor lineages replaced by a corrective
  commit or contract amendment;
- after `complete.json`, infrastructure interruption never allocates a new
  attempt: review input creation and create-only publication resume only from
  byte-identical inputs in the same attempt;
- after promote begins, a signal/storage crash must use same-receipt
  continuation; a receipt/destination mismatch fails closed with
  `contract_invalid` disposition and requires a reviewed amendment rather than
  a new ordinal on the same bytes.

Attempts are never deleted, overwritten, or mixed.

## Publication And Evidence Review

One committed `p7a-artifacts-v1` schema uses a closed `artifact_kind`
discriminator for entry, P7A TDD record/manifest, selection provenance, gold
inputs/seal, label review, feasible-cover witness, audit report, role run,
neutrality proof, evaluator closure, prepared-repository set, attempt,
attempt disposition, lineage-successor proof, definition-effect report,
paired-performance proof, baseline identity,
stage/oracle/route summaries, review round, review-round disposition,
review-draft manifest, review-draft revision manifest, agent review, review
candidate, evidence review, publish receipt, and final-tree projection receipt.
Every named persisted JSON
validates against exactly one branch with unknown keys rejected; hashing an
otherwise arbitrary JSON object is never sufficient. The transient
`P7AWorkerRequest v1` and source-bearing `P7AWorkerFrame v1` have their own
closed in-memory schemas and are not artifact branches.

`P7A_PUBLICATION_REGION_REGISTRY_V1` is a literal closed constant in
`p7a_contracts.py`, bound by the Task 1 TDD record, evaluator closure, attempt,
and every review candidate. Its ordered table is:

| destination | `publication_region_id` | exact opening marker | exact closing marker |
| --- | --- | --- | --- |
| `docs/benchmarks/p7a/README.md` | `p7a_benchmark_readme` | `<!-- P7A:BEGIN p7a_benchmark_readme -->` | `<!-- P7A:END p7a_benchmark_readme -->` |
| `README.md` | `p7a_root_readme` | `<!-- P7A:BEGIN p7a_root_readme -->` | `<!-- P7A:END p7a_root_readme -->` |
| `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` | `p7a_roadmap` | `<!-- P7A:BEGIN p7a_roadmap -->` | `<!-- P7A:END p7a_roadmap -->` |
| `docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md` | `p7a_plan_implementation_record` | `<!-- P7A:BEGIN p7a_plan_implementation_record -->` | `<!-- P7A:END p7a_plan_implementation_record -->` |

Each literal marker is one complete ASCII line terminated by LF. In its
registered destination, the opening and closing line must each occur exactly
once, in that order; the region is the byte interval after the opening LF and
before the closing marker's first byte. The four documents permit exactly one
region each. A missing, duplicate, reversed, nested, CRLF-mutated, or
unregistered complete marker line beginning `<!-- P7A:BEGIN ` or
`<!-- P7A:END ` fails bundle validation before `r01` publishes. Inline code or
table text is not a marker. The first round performs exact complete-line table
lookup, never heuristic discovery. Later rounds require the same marker bytes
and IDs in the outside-region projection. The plan markers occur inside the
excluded Implementation Record, so its headings, review ledger, and Stop Point
remain outside the mutable region. Any registry change is governed contract
work.

Before the first controlled role, a create-only `P7ATddManifest v1` orders all
four base checkpoint records and every contiguous fix record. It binds each
record hash, `supersedes_sha256`, exact selector identity, producer/schema
blobs, pre-change parent, and resulting task commit/tree. Missing checkpoints,
forked or skipped fix ordinals, tree mismatches, and unbound TDD files reject.
RED and GREEN share one exact semantic test argv but use distinct create-only
phase evidence sinks. Every GREEN is executed from a sterile materialization of
the bound staged Git tree, with loaded blobs verified against that tree. Every
selected test blob must have the exact SHA-256 captured at RED, and every RED
failing node ID must appear in GREEN JUnit as passed; deleting, renaming, or
rewriting a RED assertion invalidates the record. Running from ambient
working-tree bytes is invalid.
The attempt, baseline identity, review candidate, three agent reviews, evidence
review, and final projection receipt all bind this one manifest digest.

The selected attempt prepares, but does not yet publish, this canonical tracked
set:

```text
docs/benchmarks/p7a/baseline/baseline-identity.json
docs/benchmarks/p7a/baseline/stage-summary.json
docs/benchmarks/p7a/baseline/oracle-summary.json
docs/benchmarks/p7a/baseline/route-decision.json
```

The frozen publisher validates all four files against their exact discriminated
branches in the single `p7a-artifacts-v1` schema, plus privacy rules,
identities, and cross-hashes, then writes an attempt-local publish-set receipt.
It performs zero tracked writes in prepare mode.

Three independent agents review the same fixed implementation commit, document
payload hashes, gold/label-review/feasible-cover hashes, publication-region
registry hash, evaluator closure hash,
TDD manifest, lineage root/successor proof and consumed dispositions, attempt
identity, strict role-run set, four artifact hashes, neutrality and
paired-performance proofs, source diff, exact documentation drafts, and a
pre-review final-tree manifest:

1. architecture/contract compatibility;
2. IR/evaluation/gold validity;
3. implementation/TDD/operability.

Review input is published only as one complete create-only
`review-rounds/rNN` bundle at the lowest unused ordinal. Under one ledger lock,
the builder constructs the round record, snapshots, draft manifest, revision
manifest, and candidate in an unnumbered same-filesystem candidate directory,
validates the entire bundle, rescans the predecessor chain, and atomically
renames that directory to the absent `rNN` destination after durably flushing
its files/directories, then durably flushes the rounds parent. Validation
failure or a pre-rename crash publishes no numbered round, so corrected draft bytes may
retry the same lowest ordinal without deleting evidence. A post-rename crash
leaves the complete candidate bundle. On restart, the builder first validates
and returns the highest complete open bundle instead of allocating another
ordinal, but only when its attempt/TDD/lineage/receipt bindings equal the
request; a mismatch fails closed. Reviewer dispatch therefore resumes from its
snapshots even if mutable draft bytes have since changed. Orphan unnumbered
candidate directories are not ledger entries and cannot influence ordinal
selection or finalization.
All persisted intra-bundle paths are relative to the bundle root; the temporary
candidate-directory name enters no artifact or hash domain.

Within the unpublished bundle, a strict round record binds the complete
attempt, ordinal, and nullable preceding round-disposition hash. Every
documentation draft is copied byte-for-byte below that candidate root. A
strict draft manifest binds only the round and ordered
`(repository-relative destination, byte length, SHA-256, bundle-relative
snapshot path)` tuples
plus a domain-separated `draft_set_id`. That ID is computed only from ordered
`(repository-relative destination, byte length, SHA-256)` content tuples; it
excludes the round, snapshot path, and candidate so relocating identical bytes
cannot manufacture a revision. It never binds a future candidate.

After the draft manifest, a strict `review_draft_revision_manifest` is created.
For `r01`, its closed `revision_kind=initial` binds the current manifest and
content-only `draft_set_id` and forbids predecessor/delta fields. For a later
round, `revision_kind=draft_revision` binds the immediately preceding
draft-only round disposition and candidate, previous/current draft manifests
and content-set IDs, a nonempty normalized region-delta digest, and one
resolution entry for every failed draft-only canonical finding identity. The
normalized delta is the frozen byte-diff algorithm's ordered, non-overlapping
replacement hunks;
each hunk binds destination/region ID, previous/current region-relative
intervals, and before/after length and SHA-256. Among minimum-unit-cost
insert/delete byte scripts, the algorithm chooses the lexicographically least
full operation sequence by `(previous offset, current offset, operation kind,
unsigned byte)`, with delete ordered before insert, then coalesces adjacent
operations. Applying all hunks must reproduce the current region exactly. The
manifest requires distinct previous/current
content-set IDs, byte-identical content outside the prior candidate's permitted
regions, at least one changed permitted region, and a finding-to-hunk mapping.
The mapped prior interval must overlap the finding reference; a zero-width
insertion point must lie inside or on that reference's boundary.

The later review candidate inside the same unpublished bundle binds the draft
and revision manifests, `draft_set_id`, and prepare receipt, preserving an
acyclic hash direction. It resolves each registry-defined
`publication_region_id` by exact literal lookup and binds the registry
version/hash, marker pair, current `[start,end)` byte interval, length, and
SHA-256 in the frozen snapshot. Marker bytes and IDs must survive a draft-only
revision unchanged; the plan exposes only the marked interior of its excluded
Implementation Record. Reviewers read snapshots, not mutable working-tree
paths.

A rejected candidate, its snapshots, reviewer records, and round disposition
remain immutable. Corrective or contract-amendment work begins only in a new
clean worktree on a persistent successor branch at the rejected implementation
commit, with the shared evidence ledger supplied read-only; the dirty drafting
tree is never used for a TDD GREEN gate. A successor attempt creates a new
candidate and new snapshots rather than replacing the rejected ones.

Every reviewer must return zero blocker and zero major findings. Their
hash-bound verdicts use pairwise-distinct reviewer invocation IDs and are
combined into:

```text
docs/benchmarks/p7a/baseline/evidence-review.json
```

Every finding has a `local_finding_id` that is unique within its reviewer
record and a nonempty closed target union:

- `publication_region_ref` binds the reviewed candidate and draft-set hashes,
  destination, `publication_region_id`, and a nonempty region-relative
  `[start,end)` byte interval plus the referenced slice SHA-256;
- `corrective_path_ref` binds one exact path in
  `corrective_implementation_paths`;
- `governed_path_ref` binds one exact path in `contract_governed_blobs`; or
- `conceptual_contract_key` binds one closed conceptual key.

A sealed finding's canonical identity is derived only after the reviewer record
exists as the domain-separated digest of
`(review_role, agent_review_sha256, local_finding_id)`. It is never stored as a
self-referential digest inside that record. Round dispositions, revision
resolution mappings, and final replay bind this canonical identity; equal local
IDs in different reviewer records remain distinct, while a duplicate local ID
inside one record rejects.

A bare documentation path is not a publication-region reference. Each
blocker/major also states whether reviewed semantics must change. The evidence
builder validates every schema-valid target against the candidate/maps and
derives exactly one scope:

- `review_draft_only` only when every target is a valid
  `publication_region_ref` inside the candidate's closed P7A publication
  regions, no evidence/artifact/implementation target is present, and reviewed
  semantics remain unchanged;
- `corrective_only` only when every target is a valid `corrective_path_ref` and
  reviewed semantics remain unchanged; or
- `governed_or_mixed` for every other case, including a governed path, mixed
  target kinds, an unlisted/bare path, a conceptual contract key, an invalid or
  cross-boundary region reference, or a semantic change.

An unknown target discriminator, malformed hash, or otherwise structurally
invalid reviewer object is rejected before it becomes a sealed review record.
Once a record is structurally valid, however, a stale candidate binding,
unknown region ID, out-of-bounds interval, wrong slice hash, or cross-boundary
reference is evidence of `governed_or_mixed`; the failure sealer must create the
`reviewed_contract_amendment` attempt disposition rather than reject the
already completed review round. Free-form prose or reviewer-selected scope
cannot downgrade a finding. If every
blocker/major in a failed round is `review_draft_only`, a create-only
`review_round_disposition` closes that round without invalidating the complete
attempt. The disposition binds every failed canonical finding identity and its
allowed publication-region references. The next round must bind it, keep
implementation/gold/closure/TDD/route/artifact hashes identical, and provide
the strict revision manifest proving a nonempty content change only in those
regions plus a resolution mapping for every bound canonical finding identity.
If any finding is not draft-only, the attempt receives `review_rejected`:
`governed_or_mixed` takes precedence and requires amendment; otherwise the
set contains at least one `corrective_only` finding and requires a corrective
commit; accompanying draft-only findings are fixed in the successor attempt's
new drafts. A final PASS round is legal only when every earlier round is closed
exactly once. Evidence review and publication require that PASS round to be the
highest allocated round and reject an open, skipped, or multiply closed
predecessor. It also revalidates the entire draft-revision chain and rejects
equal adjacent content-set IDs, an empty/relocated-only delta, an uncovered
finding, a registry hash/marker mismatch, an out-of-region byte change, or a
stale predecessor even when the highest round itself is PASS.

The evaluator closure also freezes one deterministic post-review projection.
It accepts only three strict reviewer records over the reviewed manifest and
may produce only:

- `evidence-review.json`;
- the exact excluded Implementation Record fields for those reviewer hashes,
  verdict/counts, and evidence-review hash; and
- a `final_tree_projection_receipt` that binds every final tracked path/hash to
  the reviewed pre-review manifest plus those generated bytes and derives the
  expected full Git tree OID against the exact instrumentation parent.

No prose, result, threshold, artifact, README, roadmap, or covered plan byte may
change after review. The final staged-tree verifier requires the exact
projection receipt and rejects extra tracked, unstaged, or untracked paths. It
records the exact reviewed staged Git tree OID. After commit, the final verifier
must recompute from the commit object, require `HEAD^{tree}` to equal that saved
OID, and revalidate the projection receipt in commit mode. Exact parent/ancestry
without exact commit-tree equality is insufficient because a hook could rewrite
the index after staged verification.

Only then may promote mode perform recoverable create-only creation of the five
previously absent baseline/review files from the reviewed receipt. It validates
the whole set before writing, creates destinations in a frozen order with
exclusive creation, and refuses replacement. A crash can leave a partial set;
replaying the byte-identical receipt continues the same attempt after verifying
every existing byte. This continuation is not an infrastructure retry and
never allocates a new attempt.

README, roadmap, and plan implementation status are updated in the same final
documentation/artifact commit. Immediately before that commit, the persistent
publication branch HEAD must equal the instrumentation commit accepted by the
final PASS attempt; the documentation/artifact commit has that commit as its
exact parent and the saved reviewed staged tree as its exact tree. A detached
corrective commit cannot be published from an older branch. The route record is
the P7A terminal artifact.

## Performance And Lifecycle Gates

Audit-disabled instrumentation must satisfy:

- exact public output/error bytes;
- exact store connection/operation counts;
- exact source `stat/read_text` counts;
- exact embedding/planner/network request counts;
- exact exploration retrieval/pack call counts;
- no retained audit object after return;
- the unmodified P6 `protected_small_entry_comparable` paired harness, real
  default clocks, alternating pairs, calibration, and existing validator;
- query and bounded-explore median ratios no more than `1.03x` the behavior
  baseline;
- for every protected `query_*` and `explore_p4_bounded` operation, let each
  side's peak be the maximum `rss.extra_peak_bytes` across its supported raw
  paired samples; the baseline maximum must be positive and the exact integer
  gate is
  `100 * final_max_extra_peak_bytes <= 102 * baseline_max_extra_peak_bytes`.

The existing P6 paired harness does not provide a standalone context operation
or p95 summary. P7A therefore makes no context-latency or p95 claim. ContextPack
is protected by exact audit-disabled public bytes, candidate/item/excerpt
counts, serialized byte counts, and zero additional I/O/work. P7A does not add
a new performance harness merely to manufacture a stronger percentile.

For every bound sample the proof also verifies
`extra_peak_bytes = max(0, peak_bytes - empty_harness_peak_bytes)`. Zero
baseline denominator, missing side, unsupported protected retrieval operation,
or non-finite/invalid measurement invalidates the proof rather than becoming
not applicable. The strict paired-performance proof records the unchanged P6
harness blob, operation set, raw report hash, every sorted
`(operation_id, pair_id, side, order_index, case_id)` sample identity, median
calculation, per-operation RSS maxima and integer comparison, calibration
result, and context byte/work equality.

Hash edges always point backward in creation order: the reservation binds the
already-created lineage-successor proof/root; the sealed attempt binds that
reservation; the performance proof binds the sealed attempt; baseline identity
binds the lineage root, performance/neutrality proofs, and canonical summaries;
the prepare receipt binds baseline identity and the four prepared artifacts;
each review-round record binds only the complete attempt and preceding closed
round, its draft manifest binds create-only snapshots, its revision manifest
binds the current manifest and, only for `draft_revision`, the immediately
preceding candidate/disposition and prior manifest; `initial` binds no
candidate/disposition. The review candidate binds the current manifests and
receipt; evidence review
binds the final PASS candidate, all preceding round dispositions/revision
manifests, lineage root, TDD manifest, and reviewer records; and the final
projection receipt binds the
evidence review plus generated plan. No early proof references a future
artifact. The Implementation Record never records its own hash, the final
projection-receipt hash, or the final commit hash.

Audit-enabled evidence collection:

- stores no source content;
- is bounded by existing candidate/result/excerpt counts;
- has deterministic canonical serialization;
- runs only in explicit quality commands;
- is not used for the product latency comparison.

The full suite, exact skip identity, P0/P2/P3/P4/P5 protected profiles, and P6
focused lifecycle/work tests must pass.

## Privacy And External Comparisons

P7A route classification uses only pinned public repositories.

Private overlays are out of scope. If the owner runs a private repository
manually, its output is local, descriptive, non-voting, and absent from tracked
P7A artifacts.

Fast-context comparison is also out of scope for acceptance. A separate manual
comparison may reuse the frozen public cases after P7A, but it cannot alter gold,
route counts, or the decision. Remote availability and proprietary behavior
cannot define CST correctness.

Tracked artifacts may contain public repository-relative paths, ranges, IDs,
counts, and hashes. They may not contain source excerpts, absolute paths,
commands with local paths, environment values, local usernames, private
origins, or raw exception traces.

## Test Strategy

### Contract Tests

- public façade and serialized output projections remain unchanged;
- observer fields remain private and source-free;
- invalid enums, hashes, paths, ranges, NaN/Infinity, unknown keys, and absolute
  paths are rejected;
- the exact four-entry publication-region registry/hash is frozen; first-round
  literal resolution accepts one ordered LF marker pair per destination and
  rejects missing, duplicate, reversed, nested, CRLF-mutated, or unregistered
  markers;
- every named artifact, including label review, feasible-cover witness,
  role-run, P7A TDD record/manifest, attempt disposition,
  paired-performance proof, baseline identity, review round,
  review-round disposition, review-draft manifest, review-draft revision
  manifest, review candidate, and final-tree projection receipt validates
  against exactly one closed
  `p7a-artifacts-v1` branch;
- transient worker requests/frames and persisted source-free role runs have
  distinct closed schemas, and no public source text or absolute product root
  reaches disk;
- materialized-content commitments are bounded, target-independent, and reject
  malformed range/line-count/hash combinations;
- audit-disabled work counters remain exact;
- worker receives no gold/target/profile metadata;
- absolute-path isolated `-I -B` worker startup validates the transient
  role/root/commit/tree tuple, writes no bytecode, loads the selected product
  root, and imports no `quality`/evaluator module.

### Case And Gold Tests

- schema-v1 fixtures remain readable but cannot enter `p7a_route`;
- exact target paths, symbols, ranges, literals, and coherent variants validate;
- an empty-only normalized target range rejects before feasible-cover;
- partial/duplicate/overlapping-target/Frankenstein variants reject;
- every declared complete variant has a source-reviewed simultaneous
  feasible-cover witness under all real `ContextPackOptions` fields;
- aggregate pack budgets cannot hide a `max_excerpt_bytes` violation;
- intent, gate, source-independence, confirmatory, and cross-source quotas are
  enforced;
- `informational` cases never vote;
- exact-identifier NFC token boundaries/matches are closed and its variants
  cannot select only non-named-path alternatives;
- case-selection provenance is complete and author/reviewer identities differ.

### Finalizer And Decision Tests

- every reason maps exactly once;
- query/context/explore carrier-lineage DAG applicability is exact;
- an adjacent seed chunk may expand into target coverage without contradiction;
- query succeeds when any one public same-path content commitment covers the
  target;
- identical reported ranges with a single-line mid-byte crop, first/last-line
  crop, missing literal bytes, CJK multibyte boundary, CRLF/bare-CR/LF,
  VT/FF/FS/GS/RS/NEL/U+2028/U+2029, or no-final-newline case never pass without
  exact canonical full-line commitments; full targets with extra context do
  pass;
- seed target-span acquisition and expansion-carrier metric numerators and
  denominators follow their distinct definitions, including adjacent-seed
  expansion;
- context/explore distinguish rank capacity from every closed non-rank final
  selector decision;
- progress vectors use the closed deepest-to-shallowest count formula;
- every tied variant/unit retains its diagnostic reason while vote ambiguity is
  represented only by `unit_mixed`;
- all-satisfied ties yield `unit_satisfied`; satisfied/miss ties yield
  `unit_mixed`;
- tied best variants with different reason groups produce `unit_mixed` and
  `case_mixed`, independent of semantic-key ordering;
- unit and case thresholds use inclusive integer cross-products;
- two independent external sources and confirmatory support are mandatory;
- global mixed cannot be upgraded by a cohort;
- global A/intent-or-surface cohort B is mixed; global A/matching cohorts
  remains A;
- global A/confirmatory-only B is mixed; global A/confirmatory-only A remains
  A; a tied, threshold-ineligible, missing-denominator, or one-source-only
  confirmatory slice is mixed;
- the intentional minimum confirmatory direction check
  `Mc=2, Fc=2, U_G=2, C_G=2`, with one supporting case from each external
  source and all four ratios equal to `1.0`, supports the globally qualified
  group;
- language/source strata never vote;
- no misses selects `no_proven_gap`;
- path and target-span acquisition require no impossible oracle;
- insufficient matching oracle headroom downgrades a
  span/materialization, selection, or pack route to
  `benchmark_mixed_expand`;
- every outcome maps to exactly one next action.

### Metric Tests

- metrics read only the canonical role after six-role equality;
- a semantic choice repeated or recombined across extra legal variants is
  counted once and cannot change any output when each unit's distinct retained
  choice set is unchanged;
- all six recall metrics enforce their exact surface applicability,
  predecessor-false, missing-leaf, raw-count, unit-micro, case-macro, and null
  rules;
- unequal case denominators exercise the exact reduced-rational macro formula;
- rank tests cover missing carriers, no present ranks, nearest-rank p50/p90,
  query/context merged order, and explore's initial-then-probe flattened
  pre-fusion order, including one target present in the initial call and
  multiple follow-up probes;
- result-population tests cover zero slots, duplicate paths, excluded anchors,
  pooled versus case-macro ratios, and explore post-fusion results;
- terminal reasons are deduplicated by semantic-choice atom and inconsistent
  reasons for the same atom invalidate finalization;
- mixed counts use one finalized unit or case, never variant occurrences; and
- every source/surface/intent/language/confirmatory/gate slice uses its declared
  aggregation, including empty and informational slices.

### Oracle Tests

- file oracle cannot add an unacquired path or carrier, exceed capacity, or
  select more than one representative per actual deduplication key;
- file oracle covers `raw_selection`, `raw_selection_after_all_probes`, and
  `fused_selection`, including query/context duplicate anchors, explore
  duplicate carriers, and fusion representative replacement;
- file/span oracles recover only their mapped first-false boundary, mark every
  downstream counterfactual leaf `not_evaluated`, and never assume or replay
  fusion/pack/excerpt success;
- terminal satisfaction is reported only when the recovered mapped leaf is
  terminal: query `raw_target_not_materialized` for span, or the final excerpt
  leaf for pack; earlier pack leaves and every file-oracle leaf remain
  stage-local;
- span oracle cannot add a path/seed or a carrier unavailable from the actual
  acquired seeds under frozen expansion bounds;
- pack oracle cannot add a file absent from the actual QueryBundle or exceed
  item/excerpt/byte budgets;
- each oracle evaluates every complete coherent variant, defines the full
  maximal-lift certificate set, proves its intersection with bounded
  per-unit constrained optima/countercertificates, and then intersects across
  every maximal-lift variant;
- bounded intersection proofs match exhaustive enumeration on synthetic
  populations;
- tied interventions that recover different units, duplicate-carrier choices,
  and carrier/certificate/variant permutations cannot change case support;
- oracle support units have the oracle's exactly mapped actual route group;
- oracle output never mutates actual leaves or product output;
- oracle lift cannot cast route votes.

### Lifecycle And Reproducibility Tests

- observer reset on success/error/cancellation;
- deterministic-clock six-role public-hash/projection neutrality and repeat
  matrix over transient raw bytes;
- prepared-copy identity before and after every run;
- reservation-before-preparation, sealed attempt identity, closed
  retry/non-retry disposition taxonomy, post-completion review rejection, no
  partial-byte reuse, and lowest-eligible-ordinal rule;
- genesis/external/corrective/contract-amendment candidate proofs become
  consuming only in an atomically published reservation; concurrent/orphan
  proofs cannot double-consume or authorize a run;
- corrective successors preserve every governed blob and change only the closed
  corrective implementation set; governed or mixed deltas require amendment;
- registry/schema/evaluator/profile-test amendments include their exact Task
  1/2 governed tests/fixtures and contiguous owning-checkpoint fixes; omitting
  or classifying those test paths as corrective rejects;
- data-only selection/profile/source/gold amendments keep the four-checkpoint
  TDD manifest and its selected test blobs unchanged, rebuild selection,
  label-review, feasible-cover, gold-seal, closure, definition-effect, and
  successor-attempt lineage, and reject any missing or stale link; a coupled
  validator/test change also requires its Task 1/2 checkpoint fix;
- definition-effect tests cover `computed`, incomplete-role unavailable, and
  complete-but-incompatible-old-evidence unavailable without a fabricated
  effect claim;
- declared worker timeout maps deterministically to non-retryable
  `declared_timeout`;
- worker cancellation/protocol failure reaps the entire process group before
  partial hashes, repository verification, or disposition;
- all four base TDD records and contiguous fix chains validate through one
  frozen manifest bound into the attempt/review/final evidence chain;
- RED/GREEN semantic argv identity permits only distinct create-only evidence
  sinks, every selected test hash is identical, every RED failing node exists
  and passes in GREEN, and every GREEN loaded blob comes from the recorded
  staged tree;
- recoverable create-only prepare/review/promote publication;
- review input is invisible until the complete round/snapshot/draft-manifest/
  revision-manifest/candidate bundle atomically publishes; same-byte,
  out-of-region, stale-predecessor, missing-marker, invalid-placeholder, and
  injected pre-rename failures consume no `rNN`, while a post-rename crash
  resumes from one complete bundle;
- rejected review candidates retain create-only documentation snapshots;
  draft-only rounds use candidate-bound region locators, distinct content-only
  draft-set IDs, nonempty normalized deltas, and complete finding-resolution
  mappings on the same complete attempt, while mixed/governed findings take
  amendment precedence;
- structurally valid stale/unknown/out-of-bounds/wrong-slice/cross-boundary
  publication references close the failed round through governed amendment;
  only structurally invalid review objects fail before sealing;
- corrective TDD runs only from a fresh clean persistent successor branch, and
  the final publication commit has the reviewed instrumentation commit as its
  exact parent and the reviewed staged tree as its exact commit tree;
- a synthetic pre-commit index rewrite is detected by post-commit tree equality
  and commit-mode projection verification;
- end-to-end draft-reject/revise/PASS and
  reject/correct/new-attempt/PASS/publish transitions;
- changed-byte replacement rejection and same-receipt interrupted continuation;
- exact attempt-scoped pre-first-run evaluator closure and per-case/role
  Git-blob/import allowlist plus A/B closure verification;
- unchanged P6 paired median/per-operation RSS proof and exact context byte/work
  proof;
- reviewed-manifest plus deterministic post-review projection exactly equals
  the final staged tree.
- three agent-review role records bind one candidate/lineage and have
  pairwise-distinct reviewer invocation IDs; duplicate local finding IDs inside
  one record reject, while the same local ID in two reviewer records produces
  two distinct canonical finding identities and resolution obligations.

## Acceptance Checklist

P7A is complete only when:

1. the behavior baseline and reviewed-document entry are clean and reproducible;
2. case-selection provenance, public profile, gold, variants, feasible-cover
   witnesses, and source pins are frozen before controlled baseline execution;
3. all joint-feasibility, profile, and cross-source quotas pass;
4. the observer is source-free, bounded, lifecycle-safe, work-neutral, and
   import-isolated from `quality`;
5. the evaluator closure exists before the first controlled run and binds every
   semantic evaluator/worker/publisher blob;
6. six-role transient public-byte hash/content-commitment projection and work
   neutrality plus repeat equality pass under the deterministic clock, and
   target coverage is proved only from full-line commitments;
7. every decision-eligible `(complete variant, required unit)` has one
   diagnostic terminal reason and every unit has a separate vote group;
8. tied variant ambiguity cannot be resolved by IDs, order, or path
   lexicography for voting;
9. every metric uses its closed semantic-choice/unit/population atom,
   applicability, aggregation, null, and stratum contract and is invariant to
   variant recombination that preserves semantic choice sets;
10. file/span/pack oracle results obey their upper-bound and complete-variant
   aggregation contracts;
11. route dominance has two-external-source support and matching
    confirmatory-only direction/threshold evidence or selects mixed/no-gap;
12. the selected attempt satisfies the anti-cherry-pick rule, every abandoned
    predecessor has one closed disposition proposed by a valid successor proof
    and consumed by exactly one atomic reservation, and the lineage root plus
    four-checkpoint TDD manifest are bound through final review;
13. full suite, protected profiles, P6 paired median/RSS, exact context
    byte/work, and lifecycle gates pass;
14. three fixed-evidence implementation reviewers report zero blocker and zero
    major findings;
15. the five tracked baseline/review artifacts are promoted by the reviewed
    recoverable create-only receipt and the final staged tree equals its
    projection receipt;
16. README, roadmap, benchmark README, and plan record state that P7A stops at
    route selection;
17. no P7B/P8 product mechanism is implemented or implied as authorized.

## Plan-Alignment Review Record

This section is excluded from the stable design review payload. The stable
`design_review_payload_sha256` is computed by:

1. removing the single `Status:` line; and
2. removing bytes from `## Plan-Alignment Review Record` up to, but not
   including, `## Stop Point`.

Any other byte change requires a new complete fixed-payload review.

### Fixed-Payload Review: PASS (Round 11)

The final candidate identities reviewed from line 1 through EOF were:

- design full SHA-256
  `7c6c37a3938a8fbeb8171e3987266489c6429039e46f43000d8874389825b42a`,
  stable payload SHA-256
  `0ca18e89be73fbb0019e90bef24a3c956dfff9a47b4755aa06764b0c6fd89a02`,
  2,146 lines, 108,973 bytes; and
- plan full SHA-256
  `c24e2d88a5b8e183a8c137314d7cac0a6e857a6b0c27a38918f45e705ac68072`,
  stable payload SHA-256
  `c2fa3c40d61be75b8814ffabdd96287451c1a841fc51fe1dd3b299fd5511afc5`,
  3,005 lines, 135,303 bytes.

| review role | reviewer | verdict | blocker | major | minor |
| --- | --- | --- | ---: | ---: | ---: |
| architecture/contract | Poincare (`/root/p7_architecture_review`) | PASS | 0 | 0 | 0 |
| IR/evaluation/gold | Peirce (`/root/p7_ir_evaluation_review`) | PASS | 0 | 0 | 0 |
| implementation/TDD/operability | Kierkegaard (`/root/p7_feasibility_review`) | PASS | 0 | 0 | 0 |

The immediately preceding fixed candidate, Round 10, had design full/payload
SHA-256 `e8edda7a79c194190fcc63fe9c28d9e2a1dcc36cb6eea7e720f8d610781ffbab` /
`9e053ac9d3ace34347e03576b6ce0d9a747f69554eb0696c6e10b96bfb8d76c4`
and plan full/payload SHA-256
`cf08c2c7b73405bce36812cdfb76c4a824d277f19713c48cbd0cce468918543a` /
`7e2fd9fd90bd9cec644e0a2e834577ed9b2f84166a67272d3f6a0e75c22c1dfa`.
All three roles returned FAIL with 0 blocker, 1 major, and 0 minor because Task
3 data amendments were assigned to a nonexistent TDD checkpoint. Round 11
closed that issue by assigning the profile validator test to checkpoint 2 from
its initial RED and making Task 3 data-only with its own complete governed-data
lineage. Each reviewer confirmed the fix and reran their full regression scope
without modifying the files.

This PASS records review only. User approval and separate explicit
implementation authorization remain required.

## Stop Point

This document ends at design.

Do not implement P7A, modify roadmap status, prepare public repositories, author
controlled gold, run a private overlay, or start a retrieval mechanism until:

1. fixed-payload independent review has zero blocker and zero major findings;
2. review results are recorded without changing the payload;
3. the user approves this revised P7A boundary; and
4. the separate implementation plan is approved and the user explicitly
   authorizes implementation.

After P7A implementation later publishes its route decision, stop again. The
selected P7B/P8 mechanism requires its own design, review, plan, and explicit
authorization.
