# P4 Controlled Multi-Round Exploration v1 Design

Date: 2026-07-16
Status: Agent-reviewed; implementation not started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor: `docs/superpowers/specs/2026-07-16-p3-2-retrieval-core-decomposition-design.md`
Baseline: `b827707325d0ee4e9c6b2bcb3dee39955c263822`

## Summary

P4 adds one explicit, bounded exploration operation that can run a second local
retrieval round when the first ContextPack leaves a grounded evidence goal
unsatisfied. The selected public surfaces are `cst explore` and
`context_search_explore`. Existing `query`, `context`, and `trace` operations
remain single-pass and byte-compatible.

Version 1 has exactly two logical rounds:

1. one initial retrieval using the existing query configuration;
2. at most one follow-up round containing at most two deterministic probes.

The operation therefore executes at most three calls to the existing retrieval
pipeline. Follow-up probes are generated only from the original query, the
initial ContextPack, repository-relative paths, indexed symbols/signals and
relations, and bounded imports from initially selected indexed files. Follow-up
calls always disable the model query planner, execute sequentially, and use the
same indexed embedding provider as the initial call.

The initial ContextPack freezes a bounded set of evidence goals. Those goals,
rather than newly discovered terms, control probe priority and stopping. Results
are fused by repository-relative file path without comparing scores from
different queries. The final output is a normal ContextPack schema version 2
plus a compact, source-content-free ExplorationTrace schema version 2 that
records goals, rounds, probes, gain, stop, and final-evidence provenance.

P4 v1 deliberately does not add a recursive agent loop, a model-driven probe
planner, a language graph, or automatic exploration to ordinary queries. It is
the smallest implementation that can improve a controller-to-supporting-code
reading set while preserving deterministic budgets and the P0-P3 contracts.

## Baseline And Fresh Evidence

The reviewed baseline is commit
`b827707325d0ee4e9c6b2bcb3dee39955c263822`:

- Phase 3 is complete;
- full suite: `1,938` passed and the established `9` optional skips;
- focused P3.1/P3.2 gate: `76` passed;
- P2 ContextPack profile: selected/executed/passed `5/5/5`;
- raw CI profile: selected/executed/passed `8/8/8`;
- P3 TraceCoverage: `1.0`;
- Phase 1 model acceptance remains independently pending at `6/7`.

A 2026-07-16 validation used the pinned Spring PetClinic commit
`51045d1648dad955df586150c1a1a6e22ef400c2`. CST indexed 94 files into 250
chunks. For `owner registration form validation flow`, the current single pass:

- returned `OwnerController.java` at rank 1;
- built the same `ready/medium` 40,748-byte ContextPack recorded before P3;
- included `Owner.java` and `OwnerRepository.java`;
- reported missing recommended owner tests and suggested `owner test`;
- did not include `createOrUpdateOwnerForm.html`;
- retained CSS and message-file noise;
- produced a complete fifteen-stage trace with 14/14 selections covered.

A fresh fast-context run on the same public pin returned twelve files. Its first
four were `OwnerController.java`, `Owner.java`, `Person.java`, and
`createOrUpdateOwnerForm.html`; it also found `PetValidator.java`, but did not
find `OwnerControllerTests.java`. The comparison is qualitative and is not an
acceptance gate.

Focused local probes demonstrate that a bounded second pass is viable without a
new index or graph:

- `OwnerController test` returns `OwnerControllerTests.java` at rank 1;
- `createOrUpdateOwnerForm` returns the owner form template and the controller;
- `owner test` is too broad and does not return `OwnerControllerTests.java` in
  the first twelve results.

The design therefore must improve grounded probe specificity, not merely execute
every current `next_queries` string verbatim.

## Problem Statement

The current retrieval pass already performs semantic, lexical, path/symbol,
direct-text, signal, anchor, and relation recall. It then ranks once and selects
a bounded result set. ContextPack can identify missing evidence and suggest a
safe next query, but it never executes that suggestion.

This produces three practical gaps:

1. A broad first query can find the correct entrypoint but spend most of its
   result budget on nearby domain files before a test, template, store, type, or
   configuration appears.
2. Existing relation expansion is bounded by relations attached to the first
   candidate set. A high-value symbol or view name discovered only after ranking
   cannot trigger another targeted lookup.
3. Agents receive a useful `next_queries` hint but must implement their own loop,
   budget, deduplication, and stop policy. Different callers therefore obtain
   inconsistent latency and context completeness.

P4 should close this gap without turning every query into an open-ended agentic
search or redesigning the single-pass ranking engine.

## Goals

1. Add an explicit exploration operation that can improve a task-oriented
   ContextPack through one bounded follow-up round.
2. Keep ordinary query, context, and trace operations single-pass and unchanged.
3. Generate follow-up probes only from repository-grounded evidence and fixed
   category suffixes.
4. Prefer existing indexed relations, symbols, endpoints, routes, and imports
   before generic path or lexical probes.
5. Freeze the initial evidence goals so follow-up results cannot create an
   unbounded moving target.
6. Stop deterministically on satisfaction, no grounded probe, marginal gain,
   duplicate coverage, partial failure, or the fixed probe budget.
7. Preserve initial original-direct evidence and avoid comparing scores produced
   for different query strings.
8. Record each round and final evidence origin in a bounded ExplorationTrace v2.
9. Return a normal ContextPack v2 so existing agent-side pack consumption remains
   reusable.
10. Add deterministic quality cases that prove difficult Java and frontend flows
    gain supporting evidence while exact-query behavior remains protected.
11. Keep feedback metadata bounded and never persist generated probe text, paths,
    excerpts, or need subjects.

## Non-Goals

P4 v1 does not:

- change the default behavior, signatures, or payloads of `query_repository()`,
  `trace_repository()`, `cst query`, `cst context`, `cst trace`, or their MCP
  equivalents;
- change current score weights, ranking sort keys, relation confidence, candidate
  limits, or ContextPack selection policy for single-pass calls;
- fix the independent Phase 1 `audit-status-literal` model-quality gap or claim
  Phase 1 completion;
- use an LLM to generate follow-up probes;
- enable the configured query planner on follow-up probes;
- run more than one follow-up round or more than two follow-up probes;
- add a generic loop/agent framework, stage registry, scheduler, work queue, or
  parallel probe executor;
- build or persist a call graph, import graph, route graph, test graph, or new
  index schema;
- add Java AST parsing, framework-specific test association, or frontend graph
  indexing reserved for Phase 5;
- execute arbitrary ContextPack `next_queries` recursively;
- change ContextPack schema version 2 or embed exploration provenance in its
  public item schema;
- replace RetrievalTrace v1 for existing single-pass trace calls;
- add exploration configuration to `config.toml` or expose round/probe-count
  tuning flags in v1;
- use wall-clock time as an output-changing stop condition;
- persist exploration state, traces, probes, or results between requests;
- refresh a stale index or add service/watch behavior;
- update the roadmap to mark Phase 4 complete before implementation acceptance.

## Approaches Considered

### Selected: Explicit Explore Surface With One Follow-Up Round

`explore` composes existing traced retrieval and ContextPack building. It runs the
original query, freezes goals, executes at most two deterministic follow-up
queries, fuses evidence, and builds one final ContextPack.

Advantages:

- ordinary operations pay no new allocation, I/O, embedding, or planner cost;
- each retrieval call remains the already-tested fifteen-stage pipeline;
- P3 trace data supplies safe origin chunk IDs for grounded probe generation;
- ContextPack v2 remains the final reading-set contract;
- the call-count budget is trivial to audit;
- failures can return the best completed pack without persisting state.

### Rejected: Make `context` Multi-Round By Default

Changing `context` would slow existing users, invalidate P2 byte and call-count
contracts, and make exact queries unexpectedly invoke more embeddings. An opt-in
flag on `context` would also overload one operation with two execution models.
The additive `explore` surface keeps intent and compatibility explicit.

### Rejected: Recursively Execute Every `next_queries` Entry

ContextPack emits up to three safe suggestions, but they are user-facing hints,
not an execution plan. The PetClinic `owner test` example is too broad. Recursive
execution would amplify broad hints, create moving goals, and make latency depend
on new results. P4 instead specializes grounded seeds and uses a fixed global
probe budget.

### Rejected: Model-Driven Probe Planning

The optional planner can improve initial cross-language recall, but using it
again after every result would introduce network/model latency, hallucinated
symbols, provider-specific loops, and difficult deterministic tests. Follow-up
planning is local and typed. The initial round may still use the configured
planner exactly as it does today.

### Rejected: Reopen The Candidate Pipeline For Incremental Injection

An internal candidate-state API could inject second-round candidates before the
existing ranking stage. That would require extracting a new public/private
pipeline result from `query_repository()`, coupling P4 to private ranking types,
and changing P3.2's explicit orchestrator. Result-level composition is less
elegant but far smaller and preserves the protected single-pass implementation.

### Rejected: Full Nested RetrievalTrace v1 Payload Per Probe

Three complete v1 traces can make an explore response several times larger than
the final ContextPack. ExplorationTrace v2 therefore records compact round/probe
summaries and final evidence provenance. It includes each executed probe string,
so a developer can run the existing `trace` operation for that individual query
when stage-level detail is needed.

## Design Principles

### Explicit Cost

Only the new explore surface can execute follow-up retrieval. No heuristic can
silently turn an ordinary query into exploration.

### Goals Before Probes

The initial pack defines what evidence is missing. Probe generation cannot add a
new goal from its own output, so the request always converges within the fixed
budget.

### Grounded, Not Generative

Every non-original probe token must come from a typed index field, a
repository-relative path component, an existing safe `next_queries` suffix, or
an already-retrieved static import. Arbitrary source prose and model output are
not probe seeds.

### Rank Within A Query, Never Scores Across Queries

Scores from `owner registration flow` and `OwnerController test` are not
calibrated against each other. Fusion uses goal coverage, round/probe priority,
and per-probe rank. It never applies cross-query score arithmetic.

### Original Direct Evidence Remains Protected

Only initial-round evidence may retain ContextPack's protected-original-direct
classification. A direct match to a generated follow-up query is useful but is
not direct evidence for the user's original query.

### Deterministic Structural Budgets

Call counts, candidates, probe text, merged evidence, and trace previews have
fixed limits. Timings are recorded as neutral diagnostics, but real elapsed time
never changes which deterministic result is returned.

### Trace Is Still An Observer

Exploration uses v1 traces to obtain completed retrieval observations. Trace
serialization does not feed scores or preview order back into retrieval. Probe
generation uses the selected origin chunk IDs, not the five-item stage previews.

## Public Operations

### Existing Operations

The following remain byte- and behavior-compatible:

- `cst query` / `context_search_query`;
- `cst context` / `context_search_context`;
- `cst trace` / `context_search_trace`;
- `query_repository()` and `trace_repository()`;
- QueryBundle, ContextPack v2, and RetrievalTrace v1 serialization.

The implementation must prove that none of these paths imports or calls the
exploration runner during request execution.

### CLI

Add:

```bash
cst explore /path/to/repo "owner registration form validation flow"
cst explore /path/to/repo "owner registration form validation flow" --json
cst explore /path/to/repo "数据看板统计图表功能" --planner
```

`explore` reuses the `context` options:

- `--json`;
- `--context-lines`;
- `--full-file`;
- `--max-items`;
- `--max-context-bytes`;
- `--planner` and `--no-planner` for the initial round only.

It adds no round, probe, threshold, or trace-preview flags in v1. Markdown is the
default and renders the compact exploration trace before the final ContextPack.

### MCP

Add:

```python
context_search_explore(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
    max_items: int | None = None,
    max_context_bytes: int | None = None,
) -> dict[str, Any]
```

Explore has its own strict boundary validator; it does not tighten or reuse the
permissive parts of the existing query helper. `final_top_k` must be `None` or
an integer other than `bool` greater than zero, then is capped to the
exploration v1 limit. `context_lines` must be `None` or a non-negative
integer other than `bool`; `full_file` must be a real boolean; `max_items`
must be `None` or a positive integer other than `bool`; and
`max_context_bytes` must be `None` or an integer other than `bool` of at
least 4,096. Invalid `final_top_k` returns `query_failed`; invalid ContextPack
options return `invalid_context_options`. All fail before retrieval.

After applying an optional override, explore also validates the merged
`config.retrieval.final_top_k` as an integer other than `bool` greater than
zero before taking the cap. An invalid persisted/configured value returns
`query_failed` before retrieval. When `context_lines` is `None`, the
configured `context_before_lines` and `context_after_lines` must each be an
integer other than `bool` greater than or equal to zero; otherwise explore
returns `invalid_context_options` before retrieval. These checks belong only
to explore and do not tighten existing operations.

The effective initial limit is `min(merged_config.retrieval.final_top_k, 12)`.
In the success envelope,
`requested_final_top_k` is the caller's explicit MCP value or `null`; CLI has
no such flag and therefore reports `null`. The effective cap is always
reported. The MCP operation has no planner override because current MCP
configuration remains repository-owned.

### Library

Add the supported pack-options companion required by the library entry point:

    resolve_explore_pack_options(
        config: ToolConfig,
        *,
        context_lines: int | None,
        max_items: int | None = None,
        max_pack_bytes: int | None = None,
    ) -> ContextPackOptions

Add one supported entry point:

```python
explore_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    pack_options: ContextPackOptions,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
    *,
    clock_ns=None,
) -> ExploredContext
```

`pack_options` must come from the explore-only option resolver described below,
not from the single-pass resolver using the initial retrieval cap.
`ExploredContext` contains the initial QueryBundle and initial ContextPack
snapshot, final internal fused QueryBundle, final ContextPack v2, and a distinct
`ExplorationTrace` v2 model. The initial snapshot exists so quality evaluation
can prove gain within the same execution; CLI and MCP do not serialize it.
Per-probe QueryBundles and v1 traces are request-local implementation details and
are not public fields.

The supported library entry point repeats its own strict preflight before the
first retrieval call; CLI/MCP validation is not its only guard. It validates the
merged retrieval limit, context_lines, full_file, configured context-line
limits, and the complete ContextPackOptions structure/caps. A direct library
option with max_items=0 remains valid for the context_budget_zero stop.
Invalid retrieval limits raise ValueError; invalid context/full-file/pack
options raise ContextPackError with code invalid_context_options. Tests require
zero retrieval calls for every invalid direct-library input.

## Fixed V1 Limits

P4 v1 has no configurable exploration section. These values are schema and
behavior constants:

| limit | value | behavior |
| --- | ---: | --- |
| logical rounds | 2 | one initial round plus at most one follow-up round |
| follow-up probes | 2 | execute in deterministic priority order |
| total retrieval calls | 3 | initial plus two probes |
| frozen goals | 8 | exact ordered truncation after candidate derivation |
| planned probe candidates | 8 | retain first eight after deduplication |
| probe text | 160 Unicode code points | trim at a token boundary when possible |
| seed paths per probe | 3 | repository-relative paths only |
| frontend import header | 16,384 bytes | only for up to three selected indexed frontend paths |
| effective initial result limit | 12 | lower user/config limits remain lower |
| result limit per follow-up probe | 6 | same for every probe |
| fused result paths | 24 | initial paths first, then novel probe paths |
| fused evidence-anchor paths | 8 | initial anchors first, then novel anchors |
| final trace evidence preview | 20 | report full count and omitted count |
| duplicate stop ratio | 0.80 | applies only when the probe satisfies no new goal |

The explore-only validator above owns public option behavior. A configured or
requested `final_top_k` above 12 is not an error for explore; it is capped to 12
and the requested/effective values are both reported. Existing operations do
not inherit this cap or the stricter validation.

The explore-only ContextPack resolver validates the same configured context
limits as the current resolver but computes its raw-candidate ceiling from
`max_fused_results + max_fused_anchors = 32`, not from the effective initial
`final_top_k`. It then applies the configured `context.max_items` and explicit
`max_items`/byte ceilings normally. This prevents an initial
`final_top_k=1` from silently limiting the final explored pack to two items.
It does not change the existing single-pass resolver.

## Runtime Architecture

```text
CLI explore / MCP context_search_explore
  -> validate request and resolve initial config plus explore-only pack options
  -> exploration.runner.explore_repository(...)
       -> trace_repository(original query, effective initial config)
       -> build_context_pack(initial bundle)
       -> goals.freeze_goals(original query, initial pack)
       -> evaluate initial empty/partial/budget/exact/satisfaction stops
       -> only if exploration remains eligible:
            -> probes.plan_probes(initial bundle, v1 trace, initial pack, goals)
            -> stop no_grounded_probe if planning yields nothing
       -> for at most two selected probes, sequentially:
            -> trace_repository(probe, planner disabled, top_k=6)
            -> fusion.add_probe_evidence(...)
            -> build_context_pack(fused bundle)
            -> evaluate deterministic stop conditions
       -> exploration_trace.finish(...)
       -> ExploredContext(initial snapshot, fused bundle, final pack, trace_v2)
  -> shared explore JSON or Markdown formatter
  -> bounded MCP feedback metadata
```

Proposed ownership:

```text
src/context_search_tool/
  exploration/
    __init__.py       narrow public exports: runner, result, pack resolver
    models.py         goals, probes, provenance, fixed limits, runtime bundle
    options.py        strict boundary validation and explore-only pack capacity
    goals.py          freeze and match initial evidence goals
    probes.py         grounded probe generation and deterministic priority
    fusion.py         path-level representative selection and fused QueryBundle
    runner.py         explicit two-round orchestration and stop policy
  retrieval_trace/
    exploration.py    distinct ExplorationTrace v2 models/serialization adapters
  formatters.py       explore JSON/Markdown envelope formatting
  cli.py              `explore` adapter only
  mcp_tools.py        `context_search_explore_tool` and bounded feedback adapter
  mcp_server.py       MCP registration only
```

`exploration` may import the public retrieval facade, ContextPack builder/models,
query/identifier intent helpers, `SQLiteStore`, and existing parser helpers. The
retrieval facade and every `retrieval_core` module must not import exploration.
`context_pack` must not import exploration. This keeps the dependency direction
acyclic:

```text
CLI/MCP -> exploration -> retrieval facade -> retrieval_core
                      -> context_pack
                      -> retrieval_trace v1/v2
```

The implementation plan must add an AST import-adjacency test for these edges.

## Exploration Goals

### Frozen Goal Contract

An internal immutable goal has:

```text
id
kind                  need | role_gap
category              one ContextPack group
accepted_roles        bounded closed role tuple
subject_terms         bounded normalized terms
required              bool
provenance            context_need | explicit_query_role | structural_cluster
initially_satisfied   bool
```

All candidate goals are derived before truncation. At most eight are retained in
this exact order:

1. unmatched required ContextPack evidence needs;
2. unmatched required explicit-role gaps;
3. initially satisfied required ContextPack evidence needs;
4. unmatched recommended ContextPack evidence needs;
5. unmatched recommended structural-cluster gaps;
6. initially satisfied recommended ContextPack evidence needs.

Within each class, preserve initial pack/intent order. Probe planning ignores
initially satisfied goals, but those retained goals remain in coverage
denominators. The trace records the initial EvidenceNeed count, candidate goal
count, retained count, and omitted count, so an input with more than eight needs
cannot silently change the denominator. Goal IDs are deterministic from the
class, category/role, and initial ordinal; they do not hash source content.

### ContextPack Need Goals

Every initial `EvidenceNeed` becomes a candidate goal before the ordered
eight-goal cap is applied. The goal copies only its bounded ID, category, subject
terms, requiredness, and matched state. Retained matched needs remain in the
frozen set for denominator and trace accounting but do not generate probes.

### Explicit Query Role Gaps

The original query may require a more specific role than a ContextPack group can
express. A fixed explicit-token table, evaluated against the original query,
adds a required role goal only when no initial selected item has an accepted
role:

| explicit token class | nominal category | accepted ContextPack item roles |
| --- | --- | --- |
| form/page/view | `entrypoints` | `view`, `view_page`, `layout_component` |
| component | `supporting` | `component`, `shared_component`, `layout_component` |
| store/state | `implementations` | `state_store`, `store` |
| test | `tests` | `test` |
| config | `configs_docs` | `deployment_config`, `config_example`, `runtime_config`, `config`, `pom` |
| doc | `configs_docs` | `doc` |
| route/controller/entrypoint | `entrypoints` | `entrypoint`, `router`, `command`, `handler`, `route_config` |
| implementation/service/repository | `implementations` | `service_impl`, `executor`, `engine`, `middleware`, `storage`, `service`, `repository`, `source_adapter`, `state_store`, `composable`, `scheduler`, `utility`, `store`, `shared_component` |

The mapping is the intersection of roles already accepted by ContextPack v2
serialization and roles producible by the current ContextPack classifier stack:
path roles, frontend roles, and anchor-kind fallback. Parameterized tests must
construct `normalize_candidates()` examples for every listed role, including a
`pom` anchor-fallback fixture; P4 does not invent framework-specific role
strings.

### Structural Cluster Gaps

Add recommended goals only from an eligible initial entrypoint. The predicate is
closed: a selected item must have group `entrypoints`, use one of the
current roles `entrypoint`, `router`, `command`, `handler`, `view`,
`route_config`, `view_page`, or `layout_component`, and its normalized
initial candidate must either be protected-original-direct or match an initially
required entrypoint need. No numeric retrieval score or pack-level confidence
threshold participates in this predicate.

For each eligible entrypoint:

- any entrypoint may recommend implementation and test evidence;
- a frontend entrypoint may additionally recommend one route/view counterpart
  and one supporting service/store/utility/type role;
- a Java/Spring controller may recommend related type evidence;
- template/config/doc goals are not inferred unless the original query requests
  them.

ContextPack need goals win on duplicate category/subject/role coverage. No goal is
added from a follow-up result.

An independent `exact_satisfied` predicate protects exact exploration calls. It
is true only when identifier intent contains a file hint or identifier, a
protected initial candidate matches that hint in its repository-relative path or
file stem, and every retained required goal is initially satisfied. It permits
an immediate one-call stop even when a recommended structural goal remains.
Queries such as `OwnerController test` do not qualify when their required test
goal is missing.

## Grounded Probe Planning

### Allowed Seed Sources

Probe seeds may come only from:

1. the original query and initial ContextPack `next_queries`;
2. subject terms from frozen goals;
3. file stems from initial selected items;
4. symbols on origin chunks named by initial RetrievalTrace final selections;
   for an indexed single-line Java `static final String` constant whose name
   contains a closed view/form/page/template token, the repository-relative
   literal basename from that exact declaration may also be used;
5. indexed endpoint, route, usage, and relation target names attached to those
   origin chunks;
6. Java imports from the origin chunk's repository-relative path via
   `SourceFile.metadata["plugin"]["imports"]`;
7. relative static imports parsed first with the existing frontend parser from
   already-returned content, or, when the retrieval window omits the file
   header, from at most the first 16,384 bytes of up to three selected indexed
   frontend files; a P4-local lexical guard may additionally recognize only
   multiline named-import declarations that the existing line parser omits;
8. fixed category/role suffixes.

The Java lookup resolves origin chunk IDs to their indexed file paths, then uses
`SQLiteStore.source_file_for_path()`; imports are not read from chunk metadata.
The bounded frontend header fallback accepts only an already-indexed,
repository-relative selected path whose resolved regular file remains under the
repository root. It does not scan other files or follow a newly discovered
import recursively.

Arbitrary comments, string literals, full source lines, planner discarded hints,
environment values, absolute paths, and exception text are forbidden seed
sources. The view-constant exception is declaration-bound: symbol kind, name,
line, Java type/modifiers, and a safe relative literal must all match. P4 does
not scan arbitrary literals for guessed filenames.

### Probe Sources

Each candidate records one closed source:

- `next_query`;
- `relation_target`;
- `indexed_symbol`;
- `endpoint_or_route`;
- `static_import`;
- `path_stem`.

It also records the goal IDs, purpose, and up to three seed paths that justify
it. Generated text is normalized to one line, bounded to 160 code points, and
deduplicated case-insensitively. Deduplication preserves the first candidate's
source/purpose and ordered-unions its goal IDs and seed paths within their caps.

### Fixed Suffixes

P4 reuses ContextPack's closed category suffix intent but may specialize it by
role:

| goal | suffix examples |
| --- | --- |
| tests | `test` |
| implementation | `service implementation` |
| related type | `DTO type entity model` |
| UI/form | `form template view` |
| route | `route controller endpoint` |
| config | `config properties yaml` |
| docs | `documentation readme` |

The implementation uses fixed strings, not locale/model generation. A seed such
as `OwnerController` plus the test suffix yields `OwnerController test`; the
PetClinic index's actual `VIEWS_OWNER_CREATE_OR_UPDATE_FORM` declaration safely
grounds the higher-signal `createOrUpdateOwnerForm` basename without broadening
to unrelated literals.

When at least two retained required goals are initially unsatisfied, planning
also creates exactly one composite candidate from the already-allowed original
query plus the ordered unique fixed suffixes for those goals. Its `goal_ids`
name every represented required goal. It introduces no new seed source and is
still subject to the normal 160-code-point bound.

When exactly one retained required UI/form goal remains, an indexed-symbol seed
that supports it may also combine that required suffix with the ordered suffixes
of supported unsatisfied recommended goals. This lets one bounded, grounded
probe cover the form and its requested test evidence before the required-goal
stop condition fires.

### Deterministic Priority

Candidate priority is the tuple:

```text
requiredness,
goal order,
descending represented-goal count,
seed-source priority,
initial source rank,
normalized probe text
```

Seed-source priority is relation target, indexed symbol, endpoint/route, static
import, path stem, then unchanged `next_query`. This intentionally prefers a
specific `OwnerController test` probe over broad `owner test`.

After case-insensitive deduplication, planning performs one fairness sweep over
unsatisfied goals in goal order, taking the best candidate for each goal not
already represented by a selected candidate's merged goal IDs. It then appends
remaining candidates in the priority order above and retains at most eight.
The represented-goal count lets the single bounded composite candidate address
multiple required gaps before a narrower single-goal candidate. This prevents
two probes for one goal from starving a second required goal.
Before each execution, the runner skips any planned candidate whose
`goal_ids` are all already satisfied and chooses the next retained candidate.
At most two probes execute. The trace records stale-skip and unexecuted counts;
unexecuted candidate text is never serialized.

### Follow-Up Query Configuration

Every executed follow-up:

- uses `final_top_k=6`;
- uses the initial embedding provider and index compatibility checks;
- receives an explicitly disabled planner instance and config;
- creates only an `original` query variant for the generated probe;
- uses the request's context-line/full-file policy;
- runs sequentially;
- on a normal return, produces an ordinary QueryBundle and a valid
  RetrievalTrace v1 internally.

Planner disablement is a tested invariant even when the initial round used a
model planner. A provider or validation exception produces no synthetic v1
trace; the outer ExplorationTrace failure contract below applies instead.

## Evidence Fusion

### Why Fusion Is Path-Based

ContextPack v2 ultimately emits one item per repository-relative file path.
Exploration therefore deduplicates at the same path boundary. It does not try to
compare raw chunk IDs or scores from different probe queries as a global rank.

### Internal Fused QueryBundle

The fused QueryBundle is an adapter used only to call the unchanged ContextPack
builder. It retains these initial-round fields exactly:

- original `query`;
- `expanded_tokens`;
- planner and query variants;
- variant retrieval status;
- summary;
- top-level follow-up keywords.

Only `results` and `evidence_anchors` are path-fused. Explore never exposes this
synthetic bundle through the raw query API.

### Representative Selection

Results and anchors are first fused within their own kind. When the same path
appears as both a result and an anchor, the result wins, matching current
ContextPack normalization; an anchor is retained only when no result represents
that path.

For every path, choose one representative with this priority:

1. number of newly satisfied required frozen goals, descending;
2. number of newly satisfied recommended frozen goals, descending;
3. initial round before follow-up rounds;
4. earlier probe;
5. lower rank within that probe;
6. repository-relative path.

Same-path replacement is stricter than that ordering alone. Let
`old_goal_set` and `new_goal_set` be the frozen goals satisfied by the
existing and proposed representatives when classified independently. A
follow-up may replace an initial representative only when:

1. the initial representative is not protected-original-direct;
2. `old_goal_set` is a proper subset of `new_goal_set`; and
3. rebuilding the candidate preserves every previously satisfied frozen goal.

Otherwise the initial result remains byte-identical. This makes goal coverage
monotonic and prevents a new span that finds goal B from losing goal A or the
initial protected-direct confidence claim. P4 v1 does not merge arbitrary
same-file source spans to manufacture a superset.

The winning path keeps its slot in the initial order when that path was initially
present. Novel paths append in probe/rank order. Retain at most 24 result paths
and eight anchor paths.

### Follow-Up Provenance Adaptation

A follow-up representative is copied into the synthetic bundle with:

- a bounded reason identifying its probe ID and goal class;
- `semantic_matches` cleared so probe semantics are not attributed to the
  original query;
- `evidence_priority` forced to at least 1, so it is not treated as protected
  original-direct evidence;
- its original finite score retained only as per-item display and
  candidate-local excerpt-window information, never as a fusion priority;
- its round, probe, and per-probe rank stored in request-local provenance used by
  ExplorationTrace v2.

Initial results and anchors are not mutated. Reasons and score parts from
different queries are not numerically merged or compared across paths.

### Goal Satisfaction

Goal matching reuses ContextPack candidate classification and subject matching.
A `need` goal requires its category and subjects exactly as ContextPack does.
A `role_gap` goal requires an accepted role and its subjects; its nominal
category controls ordering and suffix choice but does not reject an accepted role
that current ContextPack places in another group, such as
`shared_component`. Satisfaction is recomputed after each fused pack. Stop
decisions use only the frozen goal set. The final ContextPack is free to
recompute its normal v2 evidence needs; any newly materialized need is reported
in the pack but does not start another exploration round.

## Deterministic Stop Policy

The runner evaluates conditions in this exact order.

### After Initial Round

1. `initial_missing_index`: library use receives v1
   `empty/missing_index`; CLI and MCP preflight instead return the existing
   public `missing_index` error before exploration;
2. `initial_empty`: v1 is `empty/no_candidates`, or a completed initial
   bundle contains no result or anchor;
3. `initial_retrieval_incomplete`: v1 outcome is exactly `partial`, never
   merely “not complete”;
4. `context_budget_zero`: a direct library caller supplied a valid
   ContextPack option with `max_items=0`;
5. `exact_satisfied`: the exact predicate above is true and all retained
   required goals are satisfied; recommended gaps do not trigger a probe;
6. `initial_satisfied`: every retained frozen required/recommended goal is
   satisfied;
7. `no_grounded_probe`: origin provenance is incomplete or no valid probe
   candidate exists;
8. otherwise enter the follow-up round.

### After Each Follow-Up Probe

1. `followup_query_failed`: the probe raised a handled retrieval/provider
   error, returned v1 `partial`, or returned `empty/missing_index`;
2. `satisfied`: every frozen goal is satisfied, or the frozen set contains at
   least one required goal and every required goal is satisfied;
3. `no_marginal_gain`: the probe satisfies no new goal and either contributes no
   novel path or has duplicate-path ratio at least 0.80;
4. skip planned probes whose goals are all satisfied, then execute the next
   remaining selected probe if one exists;
5. `probe_budget_exhausted`: the two-probe limit is reached with goals remaining.

The 2026-07-17 deterministic-fixture acceptance amendment makes this follow-up
stop independent of normal ContextPack confidence. Recommended gaps continue to
affect ContextPack confidence and trace coverage, but do not force an otherwise
complete required-goal flow into a duplicate probe. The same amendment permits
the P4-local guarded multiline named-import fallback and the bounded
multi-required-goal composite candidate above without changing the shared
frontend parser or retrieval-core behavior.

Duplicate-path ratio is:

```text
unique returned paths already present before the probe
divided by unique returned paths
```

Result and anchor occurrences of the same path count once in both numerator and
denominator. An empty denominator serializes as `null`; the separate
zero-novel-path condition still stops the run. All counts are computed before
trace preview truncation. No elapsed-time threshold changes output. Existing
embedding/planner HTTP timeouts may still raise handled errors.

## ExplorationTrace Schema Version 2

### Versioning And Type Rule

Multi-round execution is a materially different stage model, so P3.1's rule
requires a new schema version. Existing `RetrievalTrace`, `cst trace`, and
`context_search_trace` remain hard-coded to schema version 1. Explore uses a
separate Python root type named `ExplorationTrace`, separate serializer and
validator, schema version 2, and `mode: "exploration"`. The v1 model is never
relaxed to accept version 2.

### Exact Top-Level Contract

Canonical JSON preserves the following exact key order. Fields are never
omitted and have no implicit nullability:

```text
schema_version                    int, exactly 2
mode                              string, exactly "exploration"
outcome                           complete | empty | partial
termination_reason                closed by the matrix below
duration_ms                       non-negative int
limits                            exact ExplorationLimits object
initial_evidence_need_count       non-negative int
candidate_goal_count              non-negative int
retained_goal_count               int in [0, 8]
omitted_goal_count                non-negative int
initial_satisfied_goal_count      non-negative int
final_satisfied_goal_count        non-negative int
planned_probe_count               int in [0, 8], follow-ups only
executed_probe_count              int in [0, 2], follow-ups only
stale_skipped_probe_count         non-negative int
unexecuted_probe_count            non-negative int
retrieval_call_count              int in [1, 3]
goals                             ordered ExplorationGoal[]
rounds                            ordered ExplorationRound[]
final_evidence_count              non-negative int
final_evidence_omitted_count      non-negative int
final_evidence                    ordered FinalEvidence[], at most 20
```

`ExplorationLimits` has exactly these ordered non-negative integer keys:

```text
max_rounds                        2
max_followup_probes               2
max_retrieval_calls               3
max_planned_probes                8
max_goals                         8
max_probe_code_points             160
max_seed_paths                    3
max_frontend_import_header_bytes  16384
max_frontend_import_paths         3
effective_initial_top_k           1..12
followup_top_k                    6
max_fused_results                 24
max_fused_anchors                 8
final_evidence_top_k              20
```

The only legal top-level outcome/termination pairs are:

| outcome | termination reasons |
| --- | --- |
| `complete` | `context_budget_zero`, `exact_satisfied`, `initial_satisfied`, `no_grounded_probe`, `satisfied`, `no_marginal_gain`, `probe_budget_exhausted` |
| `empty` | `initial_missing_index`, `initial_empty` |
| `partial` | `initial_retrieval_incomplete`, `followup_query_failed` |

### Goal Ledger Contract

`goals` is the complete retained frozen-goal ledger, capped at eight. Each
entry has exactly these ordered fields:

```text
id                    non-empty string
kind                  need | role_gap
category              one ContextPack group
accepted_roles        ordered unique closed role strings
required              bool
provenance            context_need | explicit_query_role | structural_cluster
initially_satisfied   bool
finally_satisfied     bool
```

Subject terms are deliberately absent from the public trace. All goal IDs used
by rounds, probes, or final evidence must resolve in this ledger.

### Round Contract

Each round has exactly these ordered fields:

```text
round_index                    non-negative int
kind                           initial | followup
duration_ms                    non-negative int
input_path_count               non-negative int
output_path_count              non-negative int
novel_path_count               non-negative int
duplicate_path_count           non-negative int
newly_satisfied_goal_ids       ordered unique goal IDs
probes                         ordered ExplorationProbe[]
```

Round 0 has index 0, kind `initial`, and one probe representing the original
query. Round 1, when present, has index 1, kind `followup`, and one or two
attempted probes. There is no empty follow-up round.

### Probe Contract

Each attempted probe has exactly these ordered fields:

```text
id                              non-empty string
query                           bounded public query string
purpose                         non-empty closed-purpose string
source                          original | next_query | relation_target |
                                indexed_symbol | endpoint_or_route |
                                static_import | path_stem
goal_ids                        ordered unique retained goal IDs
seed_paths                      0..3 repository-relative POSIX paths
retrieval_outcome               complete | empty | partial | failed
retrieval_termination_reason    closed by the matrix below
duration_ms                     non-negative int
result_count                    non-negative int
evidence_anchor_count           non-negative int
unique_path_count               non-negative int
duplicate_path_count            non-negative int
novel_path_count                non-negative int
newly_satisfied_goal_ids        ordered unique retained goal IDs
source_counts                   exact canonical source-count object
final_selection_count           non-negative int
```

The exact legal probe pairs are:

| retrieval outcome | retrieval termination reasons |
| --- | --- |
| `complete` | `completed` |
| `empty` | `no_candidates`, `missing_index` |
| `partial` | `store_read_error` |
| `failed` | `query_error`, `provider_error` |

The original query uses `id="r0p0"`, `purpose="original_query"`,
`source="original"`, empty `goal_ids`, and empty `seed_paths`. Attempted
follow-ups receive stable execution-order IDs `r1p0` and `r1p1`; skipped
stale candidates receive no ID and are represented only by the top-level count.
Every follow-up purpose is exactly
`find_missing_{required|recommended}_{category}`, where `category` is one of
the six ContextPack group strings; no free-form purpose is allowed.

`source_counts` has exactly the v1 canonical ordered keys `semantic`,
`planner_semantic`, `lexical`, `path_symbol`, `direct_text`, `signal`,
`planner_lexical`, `planner_path_symbol`, `planner_signal`,
`anchor_expansion`, and `relation`, each with a non-negative integer value.
For a provider or validation exception, no v1 trace is fabricated: the failed
probe records outer elapsed time, zero result/anchor/path/selection counts, the
canonical all-zero source-count object, and zero gain.

### Final Evidence Provenance

Each previewed final ContextPack item has exactly these ordered fields:

```text
item_id             non-empty ContextPack item ID
file_path           repository-relative POSIX path
source_round        0 | 1
probe_id            r0p0 | r1p0 | r1p1
probe_rank          positive within-probe rank
goal_ids            ordered unique retained goal IDs
selection_reason    retained_initial_evidence |
                    replaced_by_goal_covering_probe |
                    added_novel_probe_evidence |
                    selected_evidence_anchor
```

Every final pack item has one origin. The preview is capped at 20 and reports
the omitted count. `selected_evidence_anchor` applies to any winning anchor;
otherwise an initial result is `retained_initial_evidence`, a same-path
follow-up winner is `replaced_by_goal_covering_probe`, and a novel follow-up
result is `added_novel_probe_evidence`.

### Count Equations And Invariants

- `candidate_goal_count == retained_goal_count + omitted_goal_count`;
- `retained_goal_count == len(goals)`;
- initial/final satisfied counts equal the corresponding true flags in
  `goals` and never exceed the retained count;
- `planned_probe_count == executed_probe_count +
  stale_skipped_probe_count + unexecuted_probe_count`;
- `retrieval_call_count == 1 + executed_probe_count`;
- round indexes are contiguous from zero and match round kind;
- round input/output counts use the fused result/anchor path union immediately
  before/after the round; round 0 input is zero, round novel count is
  `|output - input|`, and duplicate count sums probe duplicate counts;
- probe IDs are unique and ordered, and the number of follow-up probe records
  equals `executed_probe_count`;
- probe result/anchor counts are their returned list lengths; unique paths are
  their union, novel/duplicate partition that union against the pre-probe fused
  union, and a normally returned probe's final selection count equals its v1
  count;
- all paths are repository-relative POSIX paths and all counts/timings are
  non-negative integers;
- source-count keys use the exact order above;
- final evidence count equals final ContextPack item count and equals
  `len(final_evidence) + final_evidence_omitted_count`;
- probe and final evidence records contain no source excerpts, score parts,
  environment values, prompts, headers, or exception text;
- JSON uses `allow_nan=False`;
- ordinary single-pass retrieval constructs no v2 models.

Explore's limits guarantee complete v1 final-selection provenance:
`12 + evidence_anchor_top_k(12) = 16 <= 20` initially and
`6 + evidence_anchor_top_k(6) = 8 <= 20` per follow-up. Every normally
returned v1 trace must therefore have
`final_selection_omitted_count == 0`. If the initial trace violates this
invariant, execute no follow-up and stop `no_grounded_probe`; if a follow-up
violates it, discard that probe's evidence and stop `followup_query_failed`.

ExplorationTraceCoverage is:

```text
final ContextPack items with a valid round, probe, rank, and selection reason
divided by all final ContextPack items
```

Every non-empty P4 acceptance case requires `ExplorationTraceCoverage == 1.0`.

## Explore Success Envelope

Successful CLI JSON and MCP output have exactly these top-level keys:

```text
ok, repo, query, retrieval, context_pack, trace
```

`ok` is exactly `true`; `repo` is the resolved absolute repository string
already used by current MCP envelopes; and `query` is the original string.

`retrieval` has exactly:

```text
initial_result_count
initial_evidence_anchor_count
fused_result_count
fused_evidence_anchor_count
planner_status
planner_intent
requested_final_top_k
effective_initial_top_k
```

The four counts are non-negative integers; planner status/intent are closed
strings copied from the initial plan; `requested_final_top_k` is `null` or a
positive integer; and `effective_initial_top_k` is an integer in [1, 12].

`context_pack` is the unchanged schema version 2 payload. `trace` is the compact
ExplorationTrace version 2 payload. The envelope does not include raw per-probe
results, v1 traces, or the internal fused QueryBundle.

Markdown renders:

1. outcome, termination, call/probe counts, and duration;
2. one compact row per executed probe;
3. goal gain and final-evidence provenance;
4. the normal final ContextPack rendering.

## Errors And Partial Results

### Preflight And Initial Retrieval

Repository, missing-index, invalid option, manifest, planner, embedding, and
initial retrieval failures preserve existing public error codes where possible:

- `repo_not_found`;
- `missing_index`;
- `invalid_context_options`;
- `query_failed`.

No partial explore payload is returned when the original query raises before
producing a valid initial bundle and pack. If `trace_repository()` normally
returns a valid bundle and pack with v1 `partial/store_read_error`, explore
returns that pack with ExplorationTrace `partial/initial_retrieval_incomplete`
and executes no follow-up.

### Follow-Up Retrieval Failure

A handled `ValueError`, SQLite read error represented by an incomplete v1 trace,
or provider HTTP failure after a valid initial pack produces `ok: true` with:

- the best successfully built pack so far;
- trace outcome `partial`;
- termination `followup_query_failed`;
- no internal exception text.

This is a successful degraded result because the response contains a valid
bounded ContextPack. A v1 `partial/store_read_error` is projected into the
probe's closed `partial` pair. A thrown `ValueError` or provider HTTP error
has no v1 trace and is projected to `failed/query_error` or
`failed/provider_error` with the all-zero count contract above. Neither path
exposes exception text.

### Assembly And Serialization Failure

Unexpected goal, fusion, ExplorationTrace, ContextPack, or serialization failure
returns:

```json
{
  "ok": false,
  "error": {
    "code": "explore_failed",
    "message": "Controlled exploration failed"
  }
}
```

No partial pack or trace accompanies this error. CLI prints the same stable
message and exits nonzero. `KeyboardInterrupt` and `SystemExit` are not caught.

## Privacy And Persistence

The explicit explore response may contain:

- the original query and executed generated probe text;
- repository-relative seed and final-evidence paths;
- goal IDs/categories/roles without source excerpts;
- source counts, timings, ranks, and stop reasons;
- normal ContextPack excerpts requested by the caller.

The original query is echoed exactly by public contract and executed probe
queries may legitimately contain subject text or path-like text. The
prompt/API-key/environment/header/exception prohibitions below apply to leakage
from internal sources; they are not a value-based filter that rewrites or
rejects the caller's original query. Structured seed/final path fields still
must be repository-relative.

ExplorationTrace v2 must not contain:

- source content or `_context_content`;
- arbitrary string literals/comments used as speculative seeds;
- planner prompts, API keys, environment values, headers, or proxy settings;
- absolute paths;
- internal exception strings.

Explore does not persist probes, goals, traces, or fused results. MCP adds
dedicated `_try_append_explore_feedback(repo, projection)` and
`_append_explore_feedback(repo, projection)` functions. They must not call or
forward to the existing query feedback helpers, and neither signature accepts
the original query, a generated probe, a seed path, or a final evidence path.
The resolved repo argument is used only to locate the existing log and derive
the existing `repo_hash`.

Every stored explore event has exactly these top-level keys:

```text
timestamp, tool, ok, error_code, repo_hash, request,
exploration, context_pack, embedding
```

`tool` is exactly `context_search_explore`; `timestamp` is a non-negative
integer; `ok` is boolean; `error_code` is a string or `null`; and
`repo_hash` is the existing bounded hash. The exact nested projections are:

```text
request:
  context_lines, full_file, requested_final_top_k,
  effective_initial_top_k, max_items, max_context_bytes
exploration:
  schema_version, outcome, termination_reason, round_count,
  planned_probe_count, executed_probe_count, stale_skipped_probe_count,
  retrieval_call_count, initial_satisfied_goal_count,
  final_satisfied_goal_count
context_pack:
  schema_version, status, confidence, included_items, content_bytes,
  pack_bytes, budget_exhausted
embedding:
  provider, model, dimensions, config_hash
```

Request values are only booleans, bounded integers, or `null`. On an error
before an artifact exists, artifact strings/hashes are `null` and counts are
zero; keys are still present. The adapter first strictly validates the canonical
success/error envelope, ContextPack, and ExplorationTrace, then constructs this
aggregate projection. Feedback projection or append failures are swallowed
without changing the explore response; `KeyboardInterrupt` and `SystemExit`
remain uncaught.

Feedback must not store original or generated probe text, seed/final paths,
excerpts, item IDs, goal IDs/subjects, need IDs, per-probe source counts, or
exception text. Sentinel tests monkeypatch the two existing query feedback
helpers to fail if explore calls them, verify the new helper signatures do not
accept forbidden values, and verify that a pre-existing feedback file changes
only through the exact projection above. CLI/library calls write nothing.

## Performance Semantics

The operation is structurally bounded by at most three retrieval calls. Initial
and follow-up calls run sequentially to avoid provider bursts and ordering races.
P4 does not add threads or async execution.

The acceptance report records:

- initial, each probe, and total latency;
- retrieval call count;
- candidate/planned/executed probe counts;
- duplicate and novel path counts;
- peak fused path counts;
- ContextPack bytes.

Wall-clock time is not a deterministic stop input or a hard deterministic gate.
The current comparison code emits a warning for a greater-than-50% per-case
latency increase; it does not gate aggregate p95. P4 keeps that behavior honest:
raw-CI p50/p95 and explore p50/p95 are reported as neutral diagnostics, while
retrieval call ceilings are hard gates. Exact-query protection is proved
structurally by the no-import/no-call sentinels for existing operations and by
the `exact_satisfied` explore case requiring exactly one retrieval call.

## Quality Model

### New Quality Mode And Profile

Extend the quality fixture schema with mode `exploration` and deterministic hash
profile `p4_exploration`. P4 cases live in the separate committed catalog
`tests/fixtures/retrieval_quality/p4_exploration.json`; the P0-P3 catalog
`queries.json` remains byte-identical because the immutable P3.2
characterization manifest records its Git object ID and content hash. The
runner calls only the new explore operation for P4 cases. Existing modes,
profiles, and their catalog remain unchanged.

Every P4 case records both the initial and final pack so improvement is proven
within one run rather than against an editable external baseline. The quality
runner consumes `ExploredContext.initial_pack`; it never re-executes the
initial query to synthesize a baseline.

Existing ContextPack expectation fields apply to the final pack. Exploration
mode adds these closed fixture fields:

| field | type and meaning |
| --- | --- |
| `initial_absent` | matcher list; every path must be absent from the initial pack |
| `final_present` | matcher list; every path must be present in the final pack |
| `final_at_least` | one object with unique matcher list and non-negative `min_matches` |
| `final_forbidden` | matcher list; every path must be absent from the final pack |
| `final_noise_matchers` | matcher list used only for the final-pack noise metric |
| `expected_termination_reason` | one closed ExplorationTrace termination string |
| `expected_retrieval_call_count` | optional exact integer in [1, 3] |
| `maximum_retrieval_call_count` | optional integer ceiling in [1, 3] |
| `minimum_goal_gain` | non-negative integer |
| `maximum_final_noise_items` | non-negative integer |

Unknown fields, duplicate matchers, an impossible `min_matches`, or specifying
both an exact call count above its maximum are fixture validation errors.

### Metrics

Add the following exact metrics:

- `exploration_goal_coverage_initial = initially_satisfied retained goals /
  retained_goal_count`;
- `exploration_goal_coverage_final = finally_satisfied retained goals /
  retained_goal_count`;
- `exploration_goal_gain = final_satisfied_goal_count -
  initial_satisfied_goal_count`;
- `novel_path_count = |final fused result/anchor path union - initial
  result/anchor path union|`;
- `duplicate_path_ratio = sum(per-probe duplicate unique-path counts) /
  sum(per-probe returned unique-path counts)`;
- `executed_probe_count`, copied from the trace;
- `probe_efficiency = executed probes with positive novel-path or goal gain /
  executed_probe_count`;
- `retrieval_call_count`, copied from the trace and required to equal
  `1 + executed_probe_count`;
- `exploration_trace_coverage`, using the formula above;
- `final_pack_noise_count`, the number of distinct final item paths matching
  any declared `final_noise_matchers`;
- `final_pack_noise_ratio = final_pack_noise_count / final item count`;
- `exploration_latency_ms`, copied from trace duration.

Each result/anchor path is counted once even if it occurs in both kinds. Coverage,
duplicate ratio, probe efficiency, and noise ratio serialize as `null` when
their denominator is zero; integer counts remain zero. Existing raw result
hit/MRR metrics are computed against the initial QueryBundle only. Existing
ContextPack completeness, need completeness, bytes, status, and confidence
metrics are computed against the final pack.

### Deterministic Committed Cases

The P4 profile must include at least:

1. Java controller flow: `initial_absent` names a specific test and requested
   form, `final_present` requires both, `minimum_goal_gain=2`, and
   `maximum_retrieval_call_count=3`.
2. Frontend feature flow: the initial pack contains the view/entrypoint,
   `final_at_least` requires at least two of declared route/service/store/
   utility/type matchers, `minimum_goal_gain=2`, and lockfile/generated paths
   are `final_forbidden` with zero allowed final noise.
3. Exact path/identifier case: a protected exact item is present while at least
   one recommended goal remains missing, yet termination is
   `exact_satisfied`, `expected_retrieval_call_count=1`, and goal gain is
   zero.
4. Duplicate/no-gain case: termination is `no_marginal_gain`,
   `expected_retrieval_call_count=2`, goal gain is zero, and the planned
   second probe is not executed.

Deterministic gates use committed snapshots and hash embeddings with planner off.
No network, Ollama, or external checkout is required.

The handled follow-up failure scenario is not a committed hash-profile case:
the real hash provider offers no deterministic way for only the second call to
fail. It is a required runner test using an injected retrieval seam that
succeeds initially and raises on the first follow-up.

### Pinned Real-Project Evidence

Add a separate opt-in `p4_real_exploration` PetClinic profile at commit
`51045d1648dad955df586150c1a1a6e22ef400c2`. For the owner registration flow,
acceptance requires:

- initial Top-1 remains `OwnerController.java`;
- final pack contains `OwnerController.java`, `Owner.java`,
  `OwnerControllerTests.java`, and `createOrUpdateOwnerForm.html`;
- final pack stays within 65,536 canonical bytes;
- at most two follow-up probes and three total retrieval calls execute;
- ExplorationTraceCoverage is 1.0;
- repeated case-level exploration acceptance projections are byte-identical.

The comparison does not hash the complete quality report, whose
`generated_at`, fixture/workspace paths, tool commit, and aggregate latency
summaries legitimately vary. The acceptance projection has exactly these keys:

```text
schema_version                 exactly 1
repo_key                       stable fixture key
case_id                        stable case key
query                          original query
initial_result_paths           ordered repository-relative paths
initial_context_pack_sha256    SHA-256 of canonical ContextPack v2 bytes
final_context_pack_sha256      SHA-256 of canonical ContextPack v2 bytes
trace                          canonical ExplorationTrace v2
non_timing_metrics             exact metric object
failures                       ordered quality failure strings
```

Before canonical serialization, only `trace.duration_ms`, every
`trace.rounds[*].duration_ms`, and every
`trace.rounds[*].probes[*].duration_ms` are set to zero.
`non_timing_metrics` has exactly the exploration metrics defined above except
`exploration_latency_ms`; it contains no current raw/context latency,
generated timestamp, absolute path, workspace, fixture path, git commit, or
aggregate value. ContextPack hashes use the existing canonical serializer.

The profile does not change the P2 profile selection set. The fresh fast-context
result remains qualitative context only. It is not a required service dependency
and does not define CST's schema or ranking.

## Testing Strategy

### Goal And Probe Unit Tests

Prove:

- exact goal ordering, deduplication, cap, IDs, and requiredness;
- a ContextPack with more than eight needs reports candidate/retained/omitted
  counts and follows the complete truncation order;
- explicit form/test/config/doc roles create only the closed role gaps;
- every accepted role is produced by a current ContextPack classifier-stack
  fixture, including anchor fallback;
- follow-up outputs cannot add goals;
- every seed source is grounded and bounded;
- Java imports come from source-file plugin metadata and frontend header reads
  obey path/count/byte limits;
- specific symbol/relation probes outrank broad `next_query` probes;
- the first fairness sweep selects one candidate per unsatisfied goal and stale
  candidates are skipped after gain;
- unsafe/absolute/control-character seeds are rejected;
- candidate and text bounds are exact;
- follow-up planner state is disabled.

### Fusion Unit Tests

Prove:

- initial order and initial representatives remain unchanged without new goal
  coverage;
- a same-path follow-up replaces only on a proper goal-set superset, never loses
  a previously satisfied goal, and never replaces protected initial evidence;
- result/anchor collisions follow result-first ContextPack normalization;
- novel paths append deterministically;
- result/anchor caps and path deduplication are exact;
- no cross-query score arithmetic occurs;
- follow-up semantic matches are cleared and protected evidence is downgraded;
- final ContextPack remains canonical and bounded.

### Runner And Stop Tests

Use controlled fakes to assert exact retrieval call order and count for every
termination reason. Inject the clock for timing. Mutation tests must fail if:

- a third follow-up probe executes;
- probes run in parallel or reorder;
- the planner is enabled on a follow-up;
- goals are recomputed from follow-up evidence;
- an exact protected hit with required goals satisfied but a recommended gap
  executes a follow-up;
- duplicate threshold or stop precedence changes;
- a failed follow-up discards the valid initial pack;
- `final_top_k=1` limits the explore-only final pack capacity to two items;
- ordinary query/context/trace constructs exploration state.

### ExplorationTrace V2 Tests

Prove exact dataclass fields, serialized keys/order, goal ledger references,
top-level and probe outcome/termination matrices, bounds, path validation, count
equations, finite values, source-count order, final evidence provenance, timing
normalization, no source content, `allow_nan=False`, and the required zero v1
final-selection omission invariant.

RetrievalTrace v1 tests and schema remain unchanged.

### CLI And MCP Contract Tests

Prove:

- CLI JSON and MCP envelopes are identical for one prebuilt result;
- separate live runs match after normalizing only documented timing fields;
- Markdown includes rounds, probes, stop reason, gain, provenance, and final pack;
- invalid options fail before retrieval;
- invalid persisted `final_top_k` and configured context-line limits fail
  before retrieval on both CLI and MCP explore paths;
- explore's strict validator does not alter the existing permissive option
  behavior;
- initial errors preserve existing codes;
- partial follow-up failure is `ok: true` with a valid pack;
- unexpected failures expose only `explore_failed`;
- MCP registration/signature forwarding is exact;
- feedback contains only approved bounded aggregate metadata and never calls the
  existing query feedback helpers.

### Quality Schema And Evaluation Tests

Prove exact exploration-only fixture fields and unknown-field rejection, every
metric formula and zero-denominator `null`, initial-vs-final artifact ownership,
exact/max call gates, final-pack path/noise matchers, timing normalization
allowlist, exact case-level acceptance-projection keys, exclusion of
report/workspace/git/aggregate volatility, and the injected follow-up-only
failure seam.

### Compatibility Gates

Before and after P4 implementation, compare:

- complete raw query JSON and Markdown fingerprints;
- ContextPack v2 canonical bytes for all P2 cases;
- normalized RetrievalTrace v1 envelopes and stage ledgers;
- the P3.2 13-case characterization baseline and import boundaries;
- the byte-identical P0-P3 quality catalog at
  `tests/fixtures/retrieval_quality/queries.json`;
- full suite skip/xfail identities;
- raw CI and P2 profile reports.

The P3.2 immutable baseline is not rewritten. P4 adds a separate baseline and
profile. Any unexpected single-pass fingerprint drift is a regression, not an
occasion to refresh fixtures.

## Likely Change Surface

Expected new files:

- `src/context_search_tool/exploration/__init__.py`;
- `src/context_search_tool/exploration/models.py`;
- `src/context_search_tool/exploration/options.py`;
- `src/context_search_tool/exploration/goals.py`;
- `src/context_search_tool/exploration/probes.py`;
- `src/context_search_tool/exploration/fusion.py`;
- `src/context_search_tool/exploration/runner.py`;
- `src/context_search_tool/retrieval_trace/exploration.py`;
- `tests/fixtures/retrieval_quality/p4_exploration.json`;
- focused exploration/trace/quality tests and committed fixtures.

Expected modifications:

- `src/context_search_tool/formatters.py`;
- `src/context_search_tool/cli.py`;
- `src/context_search_tool/mcp_tools.py`;
- `src/context_search_tool/mcp_server.py`;
- narrow `retrieval_trace/__init__.py` exports;
- quality cases, runner, metrics, aggregate, reports, and compare validation;
- README, retrieval-quality guide, and roadmap after acceptance.

No change is expected to:

- index schema, scanner, chunker, indexer, embedding storage, or manifest format;
- current retrieval-core ranking/selection implementation;
- ContextPack schema or builder policy;
- RetrievalTrace v1 models/serialization;
- current raw query/context/trace public payloads.

If implementation requires one of those protected changes, stop and amend this
design before continuing.

## Delivery Decomposition

A later implementation plan should preserve green checkpoints in this order:

1. freeze P4 input identity and P0-P3 compatibility evidence;
2. add goal/probe models and deterministic unit tests;
3. add path-level fusion and goal-matching tests;
4. add ExplorationTrace v2 models/serialization and privacy tests;
5. add the two-round runner with fake-call stop tests;
6. add CLI/MCP/formatting surfaces and feedback projection;
7. add deterministic quality mode/profile and committed Java/frontend cases;
8. run pinned PetClinic evidence and qualitative fast-context comparison;
9. run full compatibility/quality acceptance;
10. update operational docs and mark Phase 4 complete only if every gate passes.

No slice combines a protected single-pass behavior change with exploration work.

## Risks And Mitigations

### Broad Probes Add More Noise

Risk: executing `owner test` adds unrelated test files.

Mitigation: prefer indexed class/symbol/relation seeds, bind probes to frozen
goals, cap per-probe results, and stop on duplicate/no-goal gain.

### Follow-Up Direct Matches Masquerade As Original Evidence

Risk: ContextPack could treat a direct match to a generated probe as proof that
the original query directly named the result.

Mitigation: force follow-up evidence priority above the protected tier, clear
probe semantic matches in the synthetic bundle, and retain round/probe provenance
only in ExplorationTrace v2.

### Scores From Different Queries Are Mixed

Risk: numerically combining independent rerank scores produces unstable order.

Mitigation: fusion never compares scores across probes; it uses goal coverage,
round/probe priority, and within-probe rank.

### Goal Set Expands Forever

Risk: every new result suggests another missing role or symbol.

Mitigation: freeze at most eight goals after the initial pack. Final pack needs
remain informative but cannot trigger another round in v1.

### Same-Path Dedup Hides A Better Span

Risk: a follow-up finds the right test/form span in a file already selected from
an irrelevant location.

Mitigation: forbid replacement of protected initial evidence and require the
follow-up representative's goal set to be a proper superset of the old set; keep
the original path slot and record the replacement reason.

### Trace Payload Grows With Nested Traces

Risk: serializing three complete v1 traces dwarfs the final pack.

Mitigation: v2 stores compact per-probe summaries and final provenance, with
fixed previews. The recorded probe can be sent to the existing trace operation
for deep diagnostics.

### Partial Failure Is Mistaken For Full Success

Risk: a valid initial pack hides a failed second round.

Mitigation: keep `ok: true` only because the pack is usable, but require trace
outcome `partial`, closed termination `followup_query_failed`, zero gain for the
failed probe, and explicit Markdown warning.

### Exact Queries Become Slower

Risk: exploration work leaks into ordinary paths or runs after a satisfied exact
query.

Mitigation: additive surface, import/call sentinels, the closed
`exact_satisfied` predicate, hard retrieval-call gates, and an exact fixture
that deliberately retains a recommended gap.

### P4 Quietly Becomes P5

Risk: probe specificity invites new parsers and graph persistence.

Mitigation: use only existing symbols, signals, relations, metadata, and static
import parser output. Any new indexing relation belongs to a separate Phase 5
design.

### Feedback Persists Sensitive Derived Queries

Risk: generated probes reveal private symbol/path combinations.

Mitigation: never persist original/generated probe text, paths, goal IDs/subjects,
or source counts; log only bounded aggregate counts and hashes already approved.

## Acceptance Criteria

P4 v1 is complete only when all of the following are true:

1. `cst explore` and `context_search_explore` are additive and share one exact
   success envelope.
2. Existing query/context/trace/library contracts and P0-P3 fingerprints remain
   unchanged.
3. Explore performs one initial retrieval and at most two sequential follow-up
   retrievals.
4. Follow-up probes are local, deterministic, grounded, bounded, and planner-off.
5. Candidate goals follow the exact truncation order, the retained set is frozen
   and bounded to eight, omitted counts are visible, and follow-up output cannot
   expand it.
6. Probe priority prefers specific relation/symbol/route/import evidence over a
   broad next-query fallback, gives unsatisfied goals a fair first sweep, and
   skips stale candidates.
7. Fusion never compares scores across queries; same-path replacement requires a
   proper goal-set superset and cannot replace protected initial evidence.
8. Only initial evidence can retain protected original-direct status.
9. Final output is a valid ContextPack schema version 2 within existing item and
   byte budgets, using the fused-candidate ceiling rather than the initial
   retrieval limit.
10. ExplorationTrace schema version 2 has an exact goal ledger, state matrices,
    counts, rounds, probes, gains, stops, limits, and final evidence provenance
    without source content.
11. RetrievalTrace v1 remains unchanged for existing trace operations.
12. Every non-empty deterministic P4 case has ExplorationTraceCoverage 1.0.
13. Java and frontend flow cases gain declared supporting evidence within two
    probes and do not add declared noise.
14. An exact protected hit with all required goals satisfied executes one
    retrieval call even when a recommended gap remains.
15. Duplicate/no-gain cases stop before an unnecessary second probe.
16. Follow-up handled failure returns the best valid pack with a partial,
    sanitized trace; unexpected assembly failures return only `explore_failed`.
17. Dedicated explore feedback contains exactly the approved aggregate
    projection, never calls existing query feedback helpers, and contains no
    query/probe text, source paths/content, item/need/goal identifiers, or
    private error details.
18. The deterministic `p4_exploration` profile passes every selected case.
19. P2 remains `5/5`, raw CI remains `8/8`, P3 TraceCoverage remains 1.0, and
    the complete suite passes with no unreviewed skip/xfail drift.
20. The pinned PetClinic owner-flow case finds controller, entity, test, and form
    within three total retrieval calls and 65,536 final pack bytes.
21. Phase 1 remains documented at `6/7` unless a separate reviewed change closes
    it.
22. Roadmap and operational docs record exact acceptance evidence before Phase 4
    is marked complete.
23. Quality evaluation consumes the same-run initial pack snapshot, validates
    the exploration-only fixture schema/formulas, and uses an injected seam for
    follow-up-only failure.

## Agent Review Rubric

Independent reviewers must check:

- whether an additive explore surface is the smallest safe compatibility choice;
- whether two rounds/two probes can satisfy the roadmap without premature
  recursive infrastructure;
- whether goals and probes are fully grounded and bounded;
- whether every accepted role is produced by the current ContextPack classifier
  stack and goal
  truncation is complete;
- whether the probe priority is implementable with current index/parser data;
- whether probe fairness and `exact_satisfied` make call counts deterministic;
- whether result-level fusion can build a correct ContextPack without misleading
  cross-query scores or provenance;
- whether same-path replacement has a deterministic, testable rule;
- whether the dependency graph is acyclic and P3.2 boundaries stay intact;
- whether trace versioning is correct and the compact v2 schema is sufficient;
- whether the goal ledger, state matrices, and count equations are self-validating;
- whether partial-error, privacy, and feedback semantics fail closed;
- whether deterministic fixtures and metrics can prove real gain rather than
  merely more results;
- whether any requirement silently begins Phase 5 or alters Phase 1 status.

Any unresolved architecture, contract, privacy, determinism, or acceptance
blocker keeps the status at draft.

## Agent Review Record

Three independent read-only reviewers examined the first draft from
architecture, public-contract/privacy, and quality/testing perspectives. The
first round found one shared blocker: the hand-written accepted-role table used
values the current classifiers cannot produce, so the required PetClinic form
goal could remain unsatisfied even when the form was selected.

Across the reports, the material findings also covered non-monotonic same-path
replacement, initial-top-k leaking into final pack capacity, the missing
same-run initial snapshot, an undefined structural-entrypoint predicate,
empty/partial stop precedence, a missing trace goal ledger and failure state
matrix, reuse of query feedback that stores raw queries, permissive existing
option validation, exact-query follow-ups despite only recommended gaps,
incomplete goal truncation, probe starvation, an underspecified quality schema
and formulas, a falsely claimed p95 gate, an impossible real-provider failure
fixture, and incorrect Java/frontend import assumptions.

This revision resolves those findings with classifier-backed roles, monotonic
protected fusion, explore-only option/pack resolution, a closed
`exact_satisfied` rule, complete goal ordering and goal-fair probe selection,
an exact self-validating ExplorationTrace schema, a dedicated aggregate-only
feedback adapter, same-run quality snapshots and fixture formulas, an injected
failure seam, honest latency semantics, and bounded source-file/header import
reads.

All three reviewers then performed targeted second passes:

- architecture: PASS; its two non-blocking wording notes were also incorporated
  by naming the full ContextPack classifier stack, adding a `pom` anchor
  fixture, and validating merged persisted retrieval limits;
- public contract/privacy: one remaining major on invalid persisted
  `final_top_k` was fixed with explore-only merged-config validation, followed
  by final PASS;
- quality/testing: one remaining major on volatile full-report comparison was
  fixed by defining the closed case-level acceptance projection, followed by
  final PASS.

No blocker or major finding remains. The three-agent review approves this design
boundary; implementation has not started.

Implementation-plan review exposed three cross-document consistency issues,
which are now incorporated here: P3.2's immutable catalog remains byte-exact
while P4 owns a separate `p4_exploration.json` catalog; the pack-option resolver
and direct-library zero-retrieval preflight are supported contracts; and the
stop point records the later authorization for plan writing/review without
authorizing implementation. The architecture, contract/privacy, and
quality/testing reviewers rechecked the affected boundaries and each returned
PASS. These were documentation corrections only; no P4 implementation began.

## Stop Point

This design ends after the explicit explore surface, frozen goals, deterministic
probe planner, bounded second round, path-level fusion, ExplorationTrace v2,
ContextPack v2 output, privacy rules, and acceptance gates are specified and
agent-reviewed.

The subsequent 2026-07-16 user instruction explicitly authorizes writing and
agent-reviewing the P4 implementation plan. That plan work does not itself
authorize implementation. This design still does not authorize score tuning,
single-pass behavior changes, model-driven exploration, persistent graphs,
language/framework graph work, Phase 1 reclassification, or Phase 5 work.
