# P4 Controlled Multi-Round Exploration Implementation Plan

Date: 2026-07-16
Status: Agent-reviewed; implementation not started
Repository: /Users/flobby/vibe_coding/context-search-tool
Design: docs/superpowers/specs/2026-07-16-p4-controlled-multi-round-exploration-design.md
Protected P0-P3 implementation baseline: b827707325d0ee4e9c6b2bcb3dee39955c263822

> **For agentic workers:** Execute one task at a time. Every task uses checkbox
> tracking, starts with a failing or protective test where practical, ends with
> explicit verification, and creates the listed focused commit. Stop on any
> single-pass fingerprint, trace-v1, ContextPack-v2, privacy, call-count, input
> identity, or skip/xfail mismatch. Do not refresh a protected baseline to make
> P4 pass.

**Goal:** Add one explicit, deterministic exploration operation that performs
one traced initial retrieval and at most two sequential, planner-off follow-up
retrievals, then returns one unchanged ContextPack v2 plus a compact
ExplorationTrace v2. Existing query, context, trace, library, retrieval-core,
and P0-P3 quality behavior must remain unchanged.

**Architecture:** Add a one-way orchestration package under
src/context_search_tool/exploration. It consumes the supported retrieval façade,
ContextPack internals already approved by the design, SQLite metadata, and a
separate ExplorationTrace-v2 model. It freezes goals after the initial pack,
plans only grounded probes, fuses evidence by repository-relative path without
cross-query score arithmetic, and exposes the behavior only through cst explore,
context_search_explore, and explore_repository.

**Tech Stack:** Python 3.11-compatible source, frozen dataclasses, Typer,
FastMCP, SQLite, current Java/frontend parsers, offline hash-v1 embeddings,
pytest, AST dependency checks, canonical JSON with allow_nan=False, and the
existing quality runner/report schema.

---

## Source Of Truth And Execution Constraints

The reviewed source of truth is:

- docs/superpowers/specs/2026-07-16-p4-controlled-multi-round-exploration-design.md

The protected implementation and evidence baseline is:

- P0-P3 implementation commit:
  b827707325d0ee4e9c6b2bcb3dee39955c263822;
- full suite: 1,938 passed, 9 skipped, 0 xfailed;
- focused P3.2 characterization: all 13 cases and four full-stage ledgers;
- immutable P3.2 baseline blob:
  a0011178b2671af25cb0853260c8fdcf586acee0;
- P2 context profile: 5/5;
- raw CI profile: 8/8;
- P3 TraceCoverage: 1.0;
- Phase 1: independently pending at 6/7.

The P0-P3 quality catalog is itself a protected P3.2 characterization input:

- path: tests/fixtures/retrieval_quality/queries.json;
- Git blob:
  8bbe4d560fec1499aa1f436af929b8a6bb6f3eac;
- SHA-256:
  ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5.

P4 therefore uses a separate catalog:

- tests/fixtures/retrieval_quality/p4_exploration.json.

This is not optional organization. Editing the P0-P3 catalog would invalidate
the immutable P3.2 input-identity test even if all retrieval outputs happened
to remain equal.

Execution constraints:

1. This document plans future implementation; it does not authorize starting
   Task 0. Begin implementation only after a later explicit user instruction,
   from reviewed main after the P4 design and this plan are merged.
   Documentation-only commits after b827707 are allowed; production source and
   protected P0-P3 fixtures must still match b827707 at Task 0.
2. Task 1 assays current single-pass behavior, then freezes all new
   deterministic P4 inputs before production code is added. Later tasks must
   not edit those inputs or their identity manifest.
3. The P3.2 baseline, its generator/projection semantics, the main quality
   catalog, and all existing committed fixture trees remain immutable.
4. Production additions are limited to the new exploration package and the
   distinct retrieval_trace/exploration.py model. Existing adapters and quality
   modules may receive only the additive changes listed in the file map.
5. Do not modify retrieval.py, retrieval_core, ContextPack models, ContextPack
   builder policy, RetrievalTrace-v1 models/serialization, index schema,
   scanner, chunker, indexer, embedding storage, or manifest format.
6. Existing cst query/context/trace, MCP query/context/trace, query_repository,
   and trace_repository requests must never import or call the exploration
   runner during request execution.
7. Follow-up retrievals use the same embedding provider, an explicitly disabled
   planner config and DisabledQueryPlanner instance, final_top_k=6, and the
   caller's context-line/full-file policy.
8. No task may add a round/probe/threshold configuration surface. All P4-v1
   limits are schema constants.
9. No task may compare or combine scores from different retrieval calls.
10. No task may persist original/generated queries, goal IDs, seed/final paths,
    source counts, content, or exception text through explore feedback.
11. Every production task begins with focused failing tests and ends with the
    P3.2 characterization gate. Do not weaken existing assertions.
12. Every task stages exact paths and creates one focused commit. Do not use
    git add -A in a dirty worktree.
13. The opt-in PetClinic acceptance file is deliberately not named test_*.py,
    so the default full suite retains the reviewed nine-skip identity.
14. The fast-context comparison is qualitative evidence only. It cannot define
    a P4 schema, expected path, gate, or service dependency.
15. Do not begin Phase 5 graph work, persistent exploration state, model-driven
    probe generation, concurrent probes, or Phase 1 reclassification.

## Definition Of Done

P4 implementation is complete only when:

- cst explore, context_search_explore, and explore_repository exist as additive
  surfaces;
- resolve_explore_pack_options is a supported companion and direct-library
  invalid inputs fail before retrieval;
- the library returns an ExploredContext containing the initial bundle/pack,
  fused bundle/final pack, and ExplorationTrace v2;
- public CLI/MCP output has exactly the reviewed success-envelope keys;
- fresh ordinary CLI/MCP/quality/library imports do not load exploration.runner;
- exactly one initial call and at most two sequential follow-up calls execute;
- frozen goals follow the complete six-class ordering and eight-goal cap;
- every retained/omitted/satisfied count is self-consistent;
- explicit-role gaps use only classifier-producible ContextPack roles;
- structural goals use the closed eligible-entrypoint predicate;
- exact_satisfied executes exactly one retrieval even with a recommended gap;
- probes use only approved bounded seed sources and the fixed priority/fairness
  algorithm;
- stale candidates are skipped dynamically and unexecuted text is not exposed;
- fusion is path-based, result-first, monotonic in frozen-goal coverage, and
  never replaces protected initial evidence;
- follow-up semantic matches are cleared and evidence priority is downgraded;
- the final pack uses a 32-candidate explore-only ceiling and remains canonical;
- ExplorationTrace v2 validates exact fields, key order, matrices, count
  equations, provenance, limits, and privacy;
- all normally returned v1 traces have zero final-selection omission;
- handled follow-up failure returns the best pack with partial sanitized trace;
- unexpected assembly failure returns only the stable explore_failed error;
- dedicated feedback contains exactly the aggregate projection in the design;
- the P4 deterministic profile passes all four required cases;
- non-timing P2/raw-CI quality projections remain byte-identical, not merely
  passing by count;
- every non-empty P4 case has ExplorationTraceCoverage 1.0;
- pinned PetClinic evidence and its normalized acceptance projection pass;
- P3.2 characterization, P3 trace, P2 5/5, raw CI 8/8, and the full suite pass
  without unreviewed skip/xfail drift;
- the P0-P3 quality catalog remains byte-identical;
- docs record exact commits, counts, hashes, reports, and qualitative comparison
  before the roadmap marks Phase 4 complete;
- Phase 1 remains 6/7.

## File Responsibility Map

| file | final responsibility |
| --- | --- |
| src/context_search_tool/exploration/__init__.py | Narrow public exports of explore_repository, ExploredContext, and resolve_explore_pack_options |
| src/context_search_tool/exploration/models.py | Fixed limits, internal immutable goals/probes/origins/fusion state, ExploredContext, bounded exploration error |
| src/context_search_tool/exploration/options.py | Explore-only strict request/config validation, initial cap, follow-up config, and 32-candidate pack resolver |
| src/context_search_tool/exploration/goals.py | Candidate-goal derivation, exact six-class freeze order, classifier-backed matching, exact_satisfied |
| src/context_search_tool/exploration/probes.py | Approved seed extraction, SQLite/header reads, candidate dedupe, priority, fairness, and stale predicates |
| src/context_search_tool/exploration/fusion.py | Result/anchor path fusion, representative replacement, provenance, caps, and synthetic QueryBundle |
| src/context_search_tool/exploration/runner.py | Explicit initial/follow-up orchestration, pack rebuilds, stop precedence, failure projection, and trace assembly |
| src/context_search_tool/retrieval_trace/exploration.py | Independent ExplorationTrace-v2 dataclasses, validation, payload, and canonical bytes |
| src/context_search_tool/retrieval_trace/__init__.py | Narrow exports for the new v2 types/serializer; no v1 relaxation |
| src/context_search_tool/formatters.py | Exact explore envelope plus JSON/Markdown validation/rendering |
| src/context_search_tool/cli.py | cst explore adapter and stable CLI errors only |
| src/context_search_tool/mcp_tools.py | context_search_explore_tool, strict boundary, sanitized errors, dedicated aggregate feedback |
| src/context_search_tool/mcp_server.py | Exact MCP registration/signature forwarding |
| src/context_search_tool/quality/cases.py | Exploration mode/profile and closed fixture-field validation |
| src/context_search_tool/quality/runner.py | Same-run initial/final artifact ownership and exploration evaluation path |
| src/context_search_tool/quality/metrics.py | Exact P4 metric formulas and gates |
| src/context_search_tool/quality/aggregate.py | Null-safe exploration metric aggregation |
| src/context_search_tool/quality/reports.py | P4 diagnostic/report rows without schema drift |
| src/context_search_tool/quality/compare.py | P4 metric type/bounds/direction rules; latency remains neutral |
| tests/p4_exploration_identity.py | Test-only P4 input hashing, P0-P3 quality projection, and JUnit identity checks |
| tests/generate_p4_exploration_manifest.py | One-shot, pre-production P4 input-manifest generator |
| tests/test_exploration_inputs.py | Frozen P4 input identity and four-case inventory |
| tests/test_exploration_boundaries.py | AST dependency, protected-file, no-import/no-call, and compatibility gates |
| tests/test_exploration_options.py | Strict request/config/capacity validation |
| tests/test_exploration_goals.py | Goal ordering, role production, matching, cap, and exact predicate |
| tests/test_exploration_probes.py | Grounding, bounds, priority, fairness, I/O caps, and unsafe-seed rejection |
| tests/test_exploration_fusion.py | Monotonic path fusion, provenance adaptation, ordering, and caps |
| tests/test_exploration_trace.py | Exact v2 schema, matrices, equations, serialization, and privacy |
| tests/test_exploration_runner.py | Fake-call ordering, stop precedence, failures, timing, and call ceilings |
| tests/test_exploration_contracts.py | CLI/MCP/formatter/feedback public contract tests |
| tests/test_quality_p4.py | Fixture validation, metrics, deterministic profile, failure seam, and acceptance projection tests |
| tests/p4_real_exploration_acceptance.py | Explicitly invoked PetClinic repeatability check; not default-collected |
| tests/fixtures/p4-exploration-java | New deterministic Java controller/entity/test/form snapshot |
| tests/fixtures/p4-exploration-duplicate | New deterministic duplicate/no-gain snapshot |
| tests/fixtures/p4_exploration/input_manifest.json | Immutable P4 input hashes and protected baseline identities |
| tests/fixtures/p4_exploration/p0_p3_p2_quality.json | Stable non-timing P2 report projection from b827707 |
| tests/fixtures/p4_exploration/p0_p3_ci_quality.json | Stable non-timing raw-CI report projection from b827707 |
| tests/fixtures/p4_exploration/petclinic-owner-registration.json | Normalized pinned real-project acceptance projection |
| tests/fixtures/retrieval_quality/p4_exploration.json | Separate four-case deterministic and one-case real P4 catalog |
| README.md | Explore usage after acceptance |
| docs/retrieval-quality.md | P4 metrics, reports, compatibility, PetClinic, and comparison evidence |
| P4 design, this plan, and roadmap | Conditional implementation status and exact acceptance record |

## Final Import Adjacency

The AST boundary test treats an edge as importer -> imported. Standard-library
and existing domain imports remain allowed; the P4-specific adjacency is:

| importer | allowed P4 dependencies |
| --- | --- |
| exploration/__init__.py | exploration.models, exploration.options, exploration.runner |
| exploration/models.py | public model types and TYPE_CHECKING-only trace/retrieval references |
| exploration/options.py | config, context_pack models/errors |
| exploration/goals.py | exploration.models, context_pack models/roles/needs, shared query/identifier intent |
| exploration/probes.py | exploration.models/goals, retrieval_trace v1 models, sqlite_store, frontend_roles, paths |
| exploration/fusion.py | exploration.models/goals, public retrieval/models, context_pack roles/needs |
| exploration/runner.py | exploration models/options/goals/probes/fusion, public retrieval façade, context_pack, query_planner, retrieval_trace v1/v2 |
| retrieval_trace/exploration.py | no exploration package import; only public constants/models needed for validation |
| formatters.py | retrieval_trace-v2 runtime types; exploration types only under TYPE_CHECKING |
| cli.py | explore-command-local imports of the public entry point/resolver only |
| mcp_tools.py | explore-tool-local imports of the public entry point/resolver only |
| quality runner | exploration-mode-branch-local imports of the public entry point/types only |

Forbidden edges:

- retrieval.py -> exploration;
- any retrieval_core module -> exploration;
- any context_pack module -> exploration;
- retrieval_trace/exploration.py -> exploration;
- exploration low-level modules -> CLI, MCP, formatters, or quality;
- ordinary single-pass execution -> exploration.runner.

Because importing any exploration submodule first executes
exploration/__init__.py, cli.py, mcp_tools.py, formatters.py, and
quality/runner.py must not have a module-scope runtime import from
context_search_tool.exploration or any of its submodules. CLI/MCP imports occur
inside only their explore functions; the quality import occurs inside only the
exploration-mode branch; formatter annotations use TYPE_CHECKING. A fresh-process
gate verifies that importing these consumers and executing ordinary operations
does not place context_search_tool.exploration.runner in sys.modules.

retrieval_trace/__init__.py may export the independent v2 trace model, but
RetrievalTrace v1 remains hard-coded to schema_version=1 and unchanged.

## Supported Public Surface

| surface | exact rule |
| --- | --- |
| exploration.explore_repository | Signature exactly matches the reviewed design |
| exploration.ExploredContext | Initial bundle/pack and fused bundle/final pack/trace fields; frozen |
| exploration.resolve_explore_pack_options | Supported companion that constructs the required 32-candidate ContextPackOptions |
| cst explore | Context options plus planner/no-planner for initial round; no final-top-k flag |
| context_search_explore | Exact reviewed MCP signature including optional final_top_k |
| explore success envelope | Exact keys: ok, repo, query, retrieval, context_pack, trace |
| retrieval summary | Exact eight reviewed fields; requested_final_top_k is MCP explicit value or null |
| ExplorationTrace | Separate schema version 2 and mode exploration |

The following are internal and must not become broad root exports:

- goal/probe/fusion state classes;
- request/config/follow-up option helpers other than the supported
  resolve_explore_pack_options companion;
- trace builder helpers;
- per-probe QueryBundles or RetrievalTrace-v1 objects;
- feedback projection helpers.

## Task And Commit Order

| task | design slice | required focused commit |
| ---: | --- | --- |
| 0 | Preflight | none |
| 1 | Frozen inputs and compatibility boundary | test: lock p4 exploration inputs |
| 2 | Options, models, and frozen goals | feat: add bounded exploration goals |
| 3 | Grounded deterministic probes | feat: add grounded exploration probes |
| 4 | Monotonic path fusion | feat: add exploration evidence fusion |
| 5 | ExplorationTrace schema v2 | feat: add exploration trace v2 |
| 6 | Explicit two-round runner | feat: add controlled exploration runner |
| 7 | CLI, MCP, formatters, feedback | feat: expose controlled exploration |
| 8 | Quality mode, metrics, deterministic profile | test: add p4 exploration quality gates |
| 9 | Pinned PetClinic acceptance baseline | test: lock p4 real exploration acceptance |
| 10 | Full acceptance and docs | docs: verify controlled exploration |

Do not squash Task 1: its commit is the immutable P4 input identity. Do not
rewrite Task 9's pinned acceptance projection after final acceptance except
through a separately reviewed design change.

## Shared Verification Commands

Every default test/quality command runs with optional external acceptance
variables unset. A fresh shell must include this prelude, or use equivalent
env -u entries inline:

~~~bash
unset \
  CST_RUN_P1_ACCEPTANCE \
  CST_P2_REAL_CONTEXT_REPOS_DIR \
  CST_P4_REAL_EXPLORATION_REPOS_DIR \
  CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
  CST_SMOKE_REPOS_DIR \
  CST_PLANNER_REQUESTS_REPO
test -z "$(env | rg '^(CST_RUN_P1_ACCEPTANCE|CST_P2_REAL_CONTEXT_REPOS_DIR|CST_P4_REAL_EXPLORATION_REPOS_DIR|CST_SMOKE_INVESTMENT_ASSISTANT_REPO|CST_SMOKE_REPOS_DIR|CST_PLANNER_REQUESTS_REPO)=' || true)"
~~~

Use these gates consistently:

~~~bash
# P4 pure/core gate
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
  tests/test_exploration_options.py \
  tests/test_exploration_goals.py \
  tests/test_exploration_probes.py \
  tests/test_exploration_fusion.py \
  tests/test_exploration_trace.py \
  tests/test_exploration_runner.py

# P4 adapter/quality gate
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
  tests/test_exploration_inputs.py \
  tests/test_exploration_boundaries.py \
  tests/test_exploration_contracts.py \
  tests/test_quality_p4.py

# Protected P0-P3 compatibility gate
PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_quality_p3.py \
  tests/test_context_pack.py

# Full suite
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
~~~

Omit a not-yet-created P4 test file until its task creates it. Every production
task runs its focused test, the input/boundary tests, and the P3.2
characterization test before commit.

### Task 0: Establish A Clean, Reproducible Start

**Files:** none

- [ ] **Step 1: Create the implementation branch from reviewed main**

  ~~~bash
  git switch main
  git status --short
  git switch -c codex/p4-controlled-exploration
  ~~~

  Expected: main contains the reviewed design and plan; the new branch is clean.

- [ ] **Step 2: Prove the protected production baseline**

  ~~~bash
  git diff --exit-code \
    b827707325d0ee4e9c6b2bcb3dee39955c263822 -- \
    src/context_search_tool
  wc -l src/context_search_tool/retrieval.py
  ~~~

  Expected: no source diff and retrieval.py remains 529 lines. Documentation
  commits after b827707 do not authorize source drift.

- [ ] **Step 3: Prove the immutable P3.2 inputs**

  ~~~bash
  test "$(git hash-object tests/fixtures/retrieval_core_decomposition/baseline.json)" = \
    a0011178b2671af25cb0853260c8fdcf586acee0
  test "$(git hash-object tests/fixtures/retrieval_quality/queries.json)" = \
    8bbe4d560fec1499aa1f436af929b8a6bb6f3eac
  git diff --exit-code \
    b827707325d0ee4e9c6b2bcb3dee39955c263822 -- \
    tests/fixtures/retrieval_quality/queries.json \
    tests/fixtures/real_projects/program_tool \
    tests/fixtures/context-pack-java \
    tests/fixtures/context-pack-docs \
    tests/fixtures/java-spring-mini \
    tests/fixtures/retrieval_core_decomposition
  ~~~

  Expected: all commands are silent and successful.

- [ ] **Step 4: Capture the baseline suite with machine-readable evidence**

  ~~~bash
  mkdir -p .quality/p4-artifacts
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_P4_REAL_EXPLORATION_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q -rs \
    --junitxml=.quality/p4-artifacts/baseline.xml
  ~~~

  Required: 1,938 passed, exact 9 skips, 0 xfails, no errors. The .quality
  directory is gitignored and persists across the implementation commits.

- [ ] **Step 5: Reproduce protected quality gates**

  ~~~bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_quality_p3.py

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output .quality/p4-artifacts/baseline-p2.json

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output .quality/p4-artifacts/baseline-ci.json
  ~~~

  Required: characterization exact; P3 TraceCoverage 1.0; P2 5/5; raw CI 8/8.
  Stop if any reviewed baseline cannot be reproduced. Task 1 converts these two
  reports into committed non-timing compatibility projections; later quality
  changes must compare against those projections, not only pass counts.

### Task 1: Freeze P4 Inputs And Compatibility Boundaries

**Files:**

- Create: tests/fixtures/p4-exploration-java/src/main/java/com/example/owner/OwnerController.java
- Create: tests/fixtures/p4-exploration-java/src/main/java/com/example/owner/Owner.java
- Create: tests/fixtures/p4-exploration-java/src/main/java/com/example/owner/OwnerService.java
- Create: tests/fixtures/p4-exploration-java/src/test/java/com/example/owner/OwnerControllerTests.java
- Create: tests/fixtures/p4-exploration-java/src/main/resources/templates/owners/createOrUpdateOwnerForm.html
- Create: tests/fixtures/p4-exploration-duplicate/src/main/java/com/example/solo/SoloController.java
- Create: tests/fixtures/retrieval_quality/p4_exploration.json
- Create: tests/fixtures/p4_exploration/input_manifest.json
- Create: tests/fixtures/p4_exploration/p0_p3_p2_quality.json
- Create: tests/fixtures/p4_exploration/p0_p3_ci_quality.json
- Create: tests/p4_exploration_identity.py
- Create: tests/generate_p4_exploration_manifest.py
- Create: tests/test_exploration_inputs.py
- Create: tests/test_exploration_boundaries.py

- [ ] **Step 1: Write the protected-input tests first**

  Task 1 deliberately cannot use production load_quality_fixture because
  production exploration schema support does not exist until Task 8. Use a
  narrow test-only raw-JSON validator in p4_exploration_identity.py. Add tests
  that require:

  - the protected baseline commit and P3.2 baseline blob above;
  - exact blob/SHA identity for queries.json;
  - no tracked, staged, unstaged, or untracked drift under the protected P0-P3
    catalog/snapshot paths;
  - P4 catalog schema version 1 with only p4_exploration and
    p4_real_exploration profiles;
  - exactly four deterministic p4_exploration cases and one pinned
    p4_real_exploration case;
  - exact source commit
    51045d1648dad955df586150c1a1a6e22ef400c2 for PetClinic;
  - no network/planner requirement in the deterministic profile.

  Run before the new inputs exist:

  ~~~bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_exploration_inputs.py
  ~~~

  Expected: FAIL because the P4 catalog and manifest do not exist.

- [ ] **Step 2: Build the deterministic Java flow snapshot**

  Keep the snapshot minimal and semantically explicit:

  - OwnerController is the protected entrypoint and exposes the
    VIEWS_OWNER_CREATE_OR_UPDATE_FORM symbol;
  - Owner is the related type;
  - OwnerService is supporting implementation evidence;
  - OwnerControllerTests is the exact test target;
  - the Spring template path is classified as role view;
  - no generated, lockfile, unrelated test, or noise file is present.

  The Java-flow profile uses a low initial result cap so the initial pack lacks
  the exact test and form while grounded symbol/path probes can recover both.
  Do not tune production scoring or add a new parser to make the fixture pass.

- [ ] **Step 3: Build the duplicate/no-gain snapshot**

  SoloController is the only indexed path. It contains at least two safe indexed
  symbols capable of producing distinct planned probes for the same missing test
  goal, but contains no test file. The first follow-up must return only the
  already-fused controller path, yield zero goal gain, and leave a second
  planned candidate unexecuted.

- [ ] **Step 4: Define the separate P4 catalog exactly**

  Add four deterministic cases:

  1. Java query OwnerController owner registration form validation test with
     final_top_k=1, making form and test explicit required role gaps;
  2. frontend query QRCode page route service type with final_top_k=1, using the
     existing immutable program_tool snapshot;
  3. exact query OwnerController with a recommended gap and one retrieval call;
  4. duplicate query SoloController test with two planned candidates but one
     follow-up call.

  Add the one pinned PetClinic owner-registration case under
  p4_real_exploration. Use only the closed exploration fields from the design.
  Do not add P4 profiles or cases to queries.json.

- [ ] **Step 5: Run the pre-freeze single-pass assay**

  Before hashing any P4 input, use only existing b827707 indexing,
  trace_repository, and ContextPack APIs in temporary workspaces. Assert:

  - Java initial top-1/pack selects OwnerController and omits the exact test and
    form; VIEWS_OWNER_CREATE_OR_UPDATE_FORM form template view finds the form in
    follow-up top-6; OwnerController test finds OwnerControllerTests in top-6;
  - frontend initial top-1/pack selects QRCodeTool.vue and omits at least the
    declared route/implementation supports; QRCodeTool route controller
    endpoint and qrcodeUtils service implementation each recover their declared
    target within top-6;
  - exact OwnerController produces a protected exact controller candidate while
    at least one structural recommendation remains possible;
  - duplicate initial retrieval and both distinct assay probes return only the
    already-present SoloController path;
  - Java query tokens imply required form and test role gaps in that exact order,
    and frontend query tokens imply the two executable missing role goals.

  Store only query/config, ordered repository-relative result/anchor paths,
  initial pack item paths/status, and expected required goal classes in the
  manifest. Do not store source, scores, timings, or absolute temp paths.
  Task 2 must prove its production goal derivation matches the frozen goal-class
  assay. If any current single-pass precondition fails, adjust the not-yet-frozen
  fixture/query now or stop for design review; never defer discovery to Task 8.

- [ ] **Step 6: Add the one-shot identity generator**

  tests/generate_p4_exploration_manifest.py must refuse to run unless:

  - production source matches b827707;
  - P3.2 baseline blob and queries.json blob/SHA match;
  - all protected P0-P3 input paths are clean;
  - no exploration production package exists yet;
  - the new catalog has the exact five-case inventory;
  - every pre-freeze single-pass assay above passes;
  - .quality/p4-artifacts/baseline-p2.json and baseline-ci.json are valid b827707
    reports;
  - every P4 snapshot path is repository-relative, regular, and under
    tests/fixtures.

  The manifest records fixed-order SHA-256 content identities for:

  - p4_exploration.json;
  - p4-exploration-java;
  - p4-exploration-duplicate;
  - the reused program_tool tree;
  - the protected catalog and P3.2 baseline blob identities.

  p4_exploration_identity.py also defines one exact P0-P3 quality compatibility
  projection. It retains schema/profile/config/repo/case identities, status,
  failures, every non-timing metric, and non-timing aggregate values; it removes
  only generated timestamps, tool commit, absolute fixture/workspace paths, and
  timing leaves. The generator writes the Task 0 P2/CI projections to the two
  committed p0_p3_*_quality.json files and records their SHA-256 values.

  The same test-only utility provides verify-junit. It loads the immutable P3.2
  skip ledger, requires the exact nine node IDs/reasons and zero xfails, counts
  default P4 tests only from the reviewed test_exploration_*.py and
  test_quality_p4.py files, rejects any skipped P4 test, and requires final
  passed = baseline-passed + collected default P4 tests.

  It never stores source content or absolute paths.

- [ ] **Step 7: Add the initial AST boundary test**

  Assert that retrieval.py, every retrieval_core module, and every context_pack
  module have no import edge to context_search_tool.exploration. Assert that the
  only allowed future production change roots are:

  - src/context_search_tool/exploration;
  - src/context_search_tool/retrieval_trace/exploration.py;
  - the reviewed adapter/quality files listed in the file map plus
    retrieval_trace/__init__.py.

  The protected modules remain exact. Task 7 extends this file with runtime
  no-call sentinels.

- [ ] **Step 8: Generate once and verify**

  ~~~bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/generate_p4_exploration_manifest.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py \
    tests/test_retrieval_core_characterization.py
  git diff --check
  ~~~

  Required: all pass; queries.json remains the exact protected blob.

- [ ] **Step 9: Commit the frozen inputs**

  ~~~bash
  git add \
    tests/fixtures/p4-exploration-java \
    tests/fixtures/p4-exploration-duplicate \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    tests/fixtures/p4_exploration/input_manifest.json \
    tests/fixtures/p4_exploration/p0_p3_p2_quality.json \
    tests/fixtures/p4_exploration/p0_p3_ci_quality.json \
    tests/p4_exploration_identity.py \
    tests/generate_p4_exploration_manifest.py \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py
  git commit -m "test: lock p4 exploration inputs"
  ~~~

  After this commit, no later task edits the P4 catalog, deterministic snapshots,
  input_manifest.json, or P0-P3 quality projections. Task 9's PetClinic output
  projection is explicitly outside the input-manifest scope. Any frozen-input
  mismatch is a design/fixture blocker.

### Task 2: Add Strict Options, Internal Models, And Frozen Goals

**Files:**

- Create: src/context_search_tool/exploration/models.py
- Create: src/context_search_tool/exploration/options.py
- Create: src/context_search_tool/exploration/goals.py
- Create: tests/test_exploration_options.py
- Create: tests/test_exploration_goals.py

- [ ] **Step 1: Write failing strict-option tests**

  Cover every request field with None, boundary values, bool impostors, negative
  values, floats, and strings. Require:

  - final_top_k invalidity -> ValueError/query_failed ownership;
  - context_lines, full_file, max_items, max_context_bytes invalidity ->
    ContextPackError/invalid_context_options ownership;
  - invalid persisted final_top_k fails before cap;
  - invalid configured context-before/after fails only when no request override;
  - effective initial top-k is min(valid merged value, 12);
  - requested value remains distinct from effective value;
  - final pack max_items uses raw ceiling 32, not initial top-k plus anchors;
  - request max_items remains positive, while a direct library-created valid
    ContextPackOptions(max_items=0, ...) remains usable for the
    context_budget_zero stop;
  - library validation accepts only structurally valid ContextPackOptions,
    preserves max_items=0, rejects bool impostors, and enforces max_items <= 32;
  - existing resolve_context_pack_options behavior remains unchanged.

- [ ] **Step 2: Implement the minimum option API**

  In options.py provide narrow helpers with one owner each:

  - validate_explore_request_options;
  - validate_library_explore_options;
  - resolve_explore_config;
  - resolve_explore_pack_options;
  - followup_config.

  resolve_explore_pack_options is the one supported companion exported from
  exploration/__init__.py in Task 6; the other helpers remain internal.
  resolve_explore_config returns a copied ToolConfig with the capped initial
  retrieval limit; it never mutates the caller config. resolve_explore_pack_options
  repeats the current configured ContextPack limit validation but uses the fixed
  24+8 candidate ceiling. Do not call the single-pass resolver and patch its
  result.

- [ ] **Step 3: Write failing model and goal tests**

  Require fixed dataclass field order and frozen instances for:

  - ExplorationGoal;
  - FrozenGoals;
  - ProbeCandidate;
  - EvidenceOrigin;
  - FusedEvidenceState;
  - ExploredContext;
  - ExplorationError.

  Task 2 defines the final field schema for all of these models. Tasks 3, 4, and
  6 consume them without changing models.py or its field-order tests.

  Goal tests must cover:

  - all ContextPack needs become candidates before truncation;
  - exact six-class ordering and stable order within each class;
  - candidate = retained + omitted and retained <= 8;
  - deterministic IDs independent of source content;
  - initially satisfied goals remain in denominators but do not request probes;
  - duplicate need/structural goals collapse in favor of ContextPack needs;
  - no API accepts a follow-up bundle to expand the goal set.
  - the exact Java/frontend queries in the frozen Task 1 assay derive the
    recorded required role-goal classes and order.

- [ ] **Step 4: Implement the classifier-backed role table**

  Use the exact reviewed explicit-token mapping. Parameterized tests must pass
  real QueryBundle examples through context_pack.roles.normalize_candidates and
  produce every accepted role, including:

  - view, view_page, layout_component;
  - component, shared_component;
  - state_store, store;
  - test;
  - deployment/config/doc roles;
  - entrypoint/router/command/handler/route_config;
  - every listed implementation role;
  - pom through the anchor-kind fallback.

  Do not add a role to ContextPack serialization or classifier code.

- [ ] **Step 5: Implement structural and exact predicates**

  The eligible structural-entrypoint predicate is exact: selected entrypoints
  group, one of the eight reviewed roles, and either protected initial direct
  evidence or a match to an initially required entrypoint need.

  exact_satisfied requires:

  - a file hint or identifier from current identifier intent;
  - a protected initial candidate matching path or stem;
  - every retained required goal initially satisfied.

  Tests must prove OwnerController stops exactly while OwnerController test does
  not when the test role is missing.

- [ ] **Step 6: Implement goal matching**

  Need goals reuse ContextPack category/subject semantics. Role gaps require
  accepted role plus subjects and may match across their nominal group. Keep
  subject terms internal; the later trace ledger must not serialize them.

- [ ] **Step 7: Verify and commit**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_options.py \
    tests/test_exploration_goals.py \
    tests/test_context_pack.py \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py
  git diff --check
  git add \
    src/context_search_tool/exploration/models.py \
    src/context_search_tool/exploration/options.py \
    src/context_search_tool/exploration/goals.py \
    tests/test_exploration_options.py \
    tests/test_exploration_goals.py
  git commit -m "feat: add bounded exploration goals"
  ~~~

### Task 3: Add Grounded Deterministic Probe Planning

**Files:**

- Create: src/context_search_tool/exploration/probes.py
- Create: tests/test_exploration_probes.py

- [ ] **Step 1: Write failing seed-provenance tests**

  Construct controlled bundles, packs, v1 traces, SQLite stores, and repository
  files. Accept seeds only from:

  - original query/initial next_queries;
  - frozen subject terms;
  - initial selected path stems;
  - symbols on origin chunks in initial v1 final selections;
  - indexed endpoint/route/usage/relation targets attached to those origins;
  - SourceFile.metadata["plugin"]["imports"] for Java;
  - extract_static_imports/resolve_frontend_import for returned frontend content
    or bounded selected-file headers;
  - fixed suffixes.

  Mutation/sentinel cases reject comments, arbitrary literals, full lines,
  discarded planner hints, environment values, absolute paths, exception text,
  control characters, and repo escapes.

- [ ] **Step 2: Implement bounded origin lookup**

  Resolve origin chunk IDs only from complete v1 final selections. Use:

  - SQLiteStore.chunk_for_id or chunks_for_ids;
  - signals_for_chunks;
  - relations_for_sources;
  - source_file_for_path for Java plugin imports.

  Fail planning closed when initial final_selection_omitted_count is nonzero or
  origin provenance cannot cover the selected evidence required by the design.
  Do not fabricate missing origins.

- [ ] **Step 3: Implement bounded frontend fallback**

  First parse already-returned candidate content. Only when its window omits the
  import header may P4 read:

  - at most three selected, already-indexed frontend paths;
  - at most the first 16,384 bytes per path;
  - regular files resolving under the repository root;
  - no symlink/repository escape;
  - no recursively discovered file.

  Reuse extract_static_imports and resolve_frontend_import. Tests count every
  stat/read and prove count/byte ceilings exactly.

- [ ] **Step 4: Implement text construction and deduplication**

  Every ProbeCandidate records source, purpose, goal IDs, and at most three seed
  paths. Normalize to one line, remove unsafe controls, trim to 160 Unicode code
  points at a token boundary when possible, and casefold-dedupe.

  A duplicate retains the first source/purpose and ordered-unions goal IDs and
  seed paths within caps. Planned candidates are capped at eight.

- [ ] **Step 5: Implement priority and fairness**

  Sort by:

  1. requiredness;
  2. frozen goal order;
  3. relation, symbol, endpoint/route, static import, path stem, next_query;
  4. initial source rank;
  5. normalized text.

  Perform one goal-order fairness sweep, then append remaining priority order.
  Tests prove one goal cannot consume both executable slots before another
  unsatisfied goal is represented. Provide a pure
  probe_candidate_is_stale(candidate, satisfied_goal_ids) predicate for runner
  use.

- [ ] **Step 6: Verify and commit**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_goals.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py
  git diff --check
  git add \
    src/context_search_tool/exploration/probes.py \
    tests/test_exploration_probes.py
  git commit -m "feat: add grounded exploration probes"
  ~~~

### Task 4: Add Monotonic Path-Level Evidence Fusion

**Files:**

- Create: src/context_search_tool/exploration/fusion.py
- Create: tests/test_exploration_fusion.py

- [ ] **Step 1: Write failing initial-state and ordering tests**

  Require:

  - initial results and anchors remain byte/value-identical;
  - results and anchors dedupe within kind by repository-relative path;
  - result wins a result/anchor path collision;
  - initial paths keep their slots;
  - novel paths append by probe then within-probe rank;
  - result and anchor caps are exactly 24 and 8.

- [ ] **Step 2: Write failing replacement tests**

  For one same-path proposed follow-up, cover every condition independently:

  - protected initial -> never replace;
  - equal goal set -> never replace;
  - disjoint/non-superset goal set -> never replace;
  - proper superset but global prior coverage loss -> never replace;
  - unprotected proper superset preserving global coverage -> replace.

  P4 must not merge arbitrary spans to manufacture a superset.

- [ ] **Step 3: Implement provenance adaptation**

  Copy a winning follow-up representative with:

  - one bounded reason carrying probe ID and goal class;
  - semantic_matches=empty;
  - evidence_priority at least 1;
  - finite item-local score preserved without cross-query comparison;
  - request-local round/probe/rank/selection-reason origin.

  Never mutate an input bundle or merge numeric score parts between calls.

- [ ] **Step 4: Build the synthetic QueryBundle**

  Preserve the initial query, tokens, planner, variants, variant status,
  summary, and top-level follow-up keywords exactly. Replace only results and
  evidence_anchors with the fused representatives.

  Build a ContextPack with the explore-only options in tests and require
  canonical bytes, valid groups/needs, and all configured byte/item limits.

- [ ] **Step 5: Recompute frozen goal satisfaction**

  Re-normalize fused candidates and use goal matching after every accepted
  probe. New ContextPack needs may appear in the final pack but never enter the
  FrozenGoals object. Assert monotonic frozen-goal coverage.

- [ ] **Step 6: Verify and commit**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_goals.py \
    tests/test_exploration_fusion.py \
    tests/test_context_pack.py \
    tests/test_exploration_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py
  git diff --check
  git add \
    src/context_search_tool/exploration/fusion.py \
    tests/test_exploration_fusion.py
  git commit -m "feat: add exploration evidence fusion"
  ~~~

### Task 5: Add ExplorationTrace Schema Version 2

**Files:**

- Create: src/context_search_tool/retrieval_trace/exploration.py
- Modify: src/context_search_tool/retrieval_trace/__init__.py
- Create: tests/test_exploration_trace.py

- [ ] **Step 1: Write failing exact-field and key-order tests**

  Define expected dataclass field tuples and serialized key tuples for:

  - ExplorationLimits;
  - ExplorationGoalRecord;
  - ExplorationProbe;
  - ExplorationRound;
  - FinalEvidence;
  - ExplorationTrace.

  Require all fixed values and exact top-level order from the design. No field is
  implicitly optional or omitted.

- [ ] **Step 2: Implement a separate v2 model**

  Add ExplorationTraceError and the v2 dataclasses in exploration.py. Do not
  subclass or widen RetrievalTrace v1. retrieval_trace/__init__.py exports only
  the reviewed v2 public types and serializer beside unchanged v1 exports.

- [ ] **Step 3: Implement closed validation**

  Validate:

  - top-level outcome/termination matrix;
  - probe outcome/termination matrix;
  - exact limits and bounds;
  - retained goal references and uniqueness;
  - contiguous rounds/probe IDs;
  - canonical source-count keys/order;
  - repository-relative POSIX paths;
  - finite numeric values and non-negative non-bool integers;
  - all count equations;
  - final evidence count/provenance coverage.

  Failed thrown probes use zero canonical counts and no fake v1 trace.

- [ ] **Step 4: Implement payload and canonical bytes**

  exploration_trace_payload preserves insertion order exactly.
  canonical_exploration_trace_bytes serializes UTF-8 with fixed separators,
  sort_keys=False, and allow_nan=False. Tests reject NaN/Infinity and verify that
  only timing fields can be normalized by the quality acceptance helper.

- [ ] **Step 5: Add privacy and omission-invariant tests**

  Validate privacy by field and provenance, not by rejecting arbitrary string
  values. The trace intentionally retains r0p0.query, every executed follow-up
  query, repository-relative seed paths, and final-evidence paths. Require:

  - no source/content/_context_content or score-parts field anywhere;
  - no subject_terms field in the public goal ledger, while subject text is
    allowed when it legitimately appears inside an executed probe query;
  - path validation only on structured seed_paths/file_path fields, so an
    original user query is not misclassified merely because it contains
    path-like text;
  - source-isolation sentinels injected as planner prompts, environment values,
    headers, secrets, and exception text never reach the trace through those
    internal sources.

  Require normally returned initial/follow-up v1 traces to have
  final_selection_omitted_count=0 under 16/8 maximum selections. Test the
  fail-closed projections for violations.

- [ ] **Step 6: Prove v1 is unchanged**

  ~~~bash
  git diff --exit-code \
    b827707325d0ee4e9c6b2bcb3dee39955c263822 -- \
    src/context_search_tool/retrieval_trace/models.py \
    src/context_search_tool/retrieval_trace/serialization.py \
    src/context_search_tool/retrieval_trace/collector.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_exploration_trace.py
  ~~~

- [ ] **Step 7: Verify and commit**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_trace.py \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py
  git diff --check
  git add \
    src/context_search_tool/retrieval_trace/exploration.py \
    src/context_search_tool/retrieval_trace/__init__.py \
    tests/test_exploration_trace.py
  git commit -m "feat: add exploration trace v2"
  ~~~

### Task 6: Add The Explicit Two-Round Runner

**Files:**

- Create: src/context_search_tool/exploration/runner.py
- Create: src/context_search_tool/exploration/__init__.py
- Create: tests/test_exploration_runner.py

- [ ] **Step 1: Write one fake-driven test per initial stop**

  With injected clock and monkeypatched runner seams, prove exact order/count for:

  - initial_missing_index;
  - initial_empty;
  - initial_retrieval_incomplete;
  - context_budget_zero;
  - exact_satisfied;
  - initial_satisfied;
  - no_grounded_probe;
  - initial v1 final-selection omission -> no_grounded_probe with zero
    follow-up calls.

  Assert the exact precedence, especially empty before partial, partial only for
  v1 outcome partial, budget-zero before exact, and planning only after earlier
  stops are false.

- [ ] **Step 2: Write one fake-driven test per follow-up stop**

  Cover:

  - followup_query_failed from v1 partial/store_read_error;
  - followup_query_failed from empty/missing_index;
  - failed/query_error from ValueError without fake v1;
  - failed/provider_error from HTTP error without fake v1;
  - follow-up v1 final-selection omission -> discard all probe evidence and
    partial/followup_query_failed;
  - satisfied;
  - no_marginal_gain from zero novel path;
  - no_marginal_gain from duplicate ratio exactly 0.80;
  - stale skip followed by next candidate;
  - probe_budget_exhausted.

  Duplicate tests count the result/anchor union once and serialize null only for
  an empty denominator.

- [ ] **Step 3: Implement the initial round**

  explore_repository has the exact reviewed signature. It:

  1. before any retrieval, validates config final_top_k, context_lines,
     full_file, configured context lines, and the complete ContextPackOptions
     structure through validate_library_explore_options;
  2. preserves valid direct-library max_items=0 but rejects a bool, negative,
     malformed byte ordering, or max_items above the fused ceiling with
     ContextPackError(invalid_context_options);
  3. resolves/caps an initial config without mutating input;
  4. calls trace_repository once;
  5. requires complete v1 provenance or follows the closed stop;
  6. builds initial_pack from the supplied explore-only pack options;
  7. freezes goals once;
  8. evaluates initial stops in exact order;
  9. plans probes only if eligible.

  Direct-library sentinel tests pass every invalid raw parameter/config/options
  case and require zero retrieval calls. Invalid retrieval final_top_k raises
  ValueError; invalid context/full-file/pack options raise
  ContextPackError(invalid_context_options). CLI/MCP retain their own earlier
  boundary validation, but cannot bypass this supported library boundary.

  The returned ExploredContext always retains the initial snapshot. CLI/MCP
  serialization later omits it.

- [ ] **Step 4: Implement sequential follow-ups**

  Before each candidate, recompute stale status. For at most two executed probes:

  - copy config with planner disabled and final_top_k=6;
  - pass DisabledQueryPlanner explicitly;
  - reuse context_lines/full_file;
  - call trace_repository synchronously;
  - validate zero v1 selection omission;
  - discard failed/invalid probe evidence;
  - otherwise fuse, rebuild pack, recompute frozen goals, and evaluate stops.

  Tests use an active-call counter to fail if probes overlap and a call ledger to
  fail if they reorder.

- [ ] **Step 5: Assemble v2 trace and ExploredContext**

  Count planned = executed + stale skipped + unexecuted, calls = 1 + executed,
  rounds contiguous, and final provenance covers every final item. Initial and
  final bundle/pack fields are distinct, non-mutated value snapshots. Their
  mutable list/dict containers must not share references across the initial and
  final snapshots.

- [ ] **Step 6: Bound errors**

  Initial ValueError/HTTP/provider errors propagate for adapter mapping to
  query_failed. Handled follow-up failures return a partial ExploredContext
  without exception text. Unexpected goal/fusion/pack/trace assembly raises only
  ExplorationError with stable public message; KeyboardInterrupt/SystemExit are
  not caught.

- [ ] **Step 7: Run mutation-oriented call gates**

  Add tests that fail if:

  - a third follow-up executes;
  - planner is enabled on any follow-up;
  - goals are recomputed/expanded from follow-up output;
  - initial/final bundle or pack containers alias each other;
  - exact_satisfied probes;
  - a failed follow-up drops the initial pack;
  - final_top_k=1 reduces final ContextPack max_items to two;
  - timing changes a stop;
  - ordinary retrieval constructs ExploredContext/ExplorationTrace.

  Also import exploration from its supported package and assert that
  explore_repository, ExploredContext, and resolve_explore_pack_options are the
  only reviewed public exports.

- [ ] **Step 8: Verify and commit**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_options.py \
    tests/test_exploration_goals.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_exploration_trace.py \
    tests/test_exploration_runner.py \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py
  git diff --check
  git add \
    src/context_search_tool/exploration/__init__.py \
    src/context_search_tool/exploration/runner.py \
    tests/test_exploration_runner.py
  git commit -m "feat: add controlled exploration runner"
  ~~~

### Task 7: Expose CLI, MCP, Formatters, And Private Feedback

**Files:**

- Modify: src/context_search_tool/formatters.py
- Modify: src/context_search_tool/cli.py
- Modify: src/context_search_tool/mcp_tools.py
- Modify: src/context_search_tool/mcp_server.py
- Create: tests/test_exploration_contracts.py
- Modify: tests/test_exploration_boundaries.py

- [ ] **Step 1: Write failing envelope/formatter tests**

  Define exact functions:

  - explore_payload;
  - format_explore_json;
  - format_explore_markdown.

  Require exact top-level key order and exact eight-field retrieval object.
  JSON uses ensure_ascii=True, sort_keys=False, allow_nan=False. The envelope
  includes only final ContextPack and compact v2 trace, never initial pack,
  fused bundle, per-probe bundle, or v1 trace.

  Markdown renders outcome/termination/calls/duration, one row per attempted
  probe, gain/provenance, partial warning when applicable, and the normal final
  ContextPack sections.

  formatters.py may reference ExploredContext only under TYPE_CHECKING, or accept
  already materialized fields. It must not perform a module-scope runtime import
  from the exploration package.

- [ ] **Step 2: Add cst explore**

  Reuse the context command's repo/question resolution and the exact reviewed
  options. CLI has no final-top-k option and reports requested_final_top_k null.
  Planner/no-planner affects only the initial call. Strict option/config
  resolution occurs before explore_repository. Import the public exploration
  resolver/runner inside only the explore command body; importing cli.py or
  executing any other command must not load exploration.runner.

  Stable failures:

  - current repo/missing-index behavior;
  - invalid options with the reviewed code/message;
  - initial query errors through existing error handling;
  - unexpected ExplorationError as Controlled exploration failed and exit 1.

- [ ] **Step 3: Add context_search_explore_tool and registration**

  Add the exact MCP signature and forwarding order in mcp_server.py. Preflight:

  1. resolve repo or repo_not_found;
  2. require index or missing_index;
  3. strict request/config/options resolution;
  4. call explore_repository;
  5. build/strictly validate envelope;
  6. project feedback;
  7. return.

  Invalid final_top_k/config final_top_k returns query_failed. Other invalid
  context options return invalid_context_options. Initial failure has no partial
  payload; handled follow-up failure remains ok true; unexpected assembly
  returns only explore_failed.

  context_search_explore_tool performs its exploration imports inside only that
  function. mcp_tools.py and mcp_server.py module import must not load the
  exploration runner.

- [ ] **Step 4: Add dedicated aggregate-only feedback**

  Implement exact signatures:

  - _try_append_explore_feedback(repo, projection);
  - _append_explore_feedback(repo, projection).

  A separate projector first validates the canonical envelope/pack/trace, then
  constructs the exact top-level and nested keys from the design. Append helpers
  do not accept query, probe, seed/final path, IDs, content, source counts, or
  exception values.

  Tests:

  - monkeypatch both existing query feedback helpers to raise if called;
  - inspect.signature rejects forbidden parameters;
  - pre-existing feedback file gains exactly one canonical event;
  - success and error projection keys are always present;
  - recursive sentinels find no query/probe/path/content/ID/error detail;
  - append/projection OSError, RuntimeError, or any other ordinary Exception
    does not change response;
  - KeyboardInterrupt and SystemExit are not swallowed;
  - CLI/library write nothing.

- [ ] **Step 5: Add exact CLI/MCP contract tests**

  Prove:

  - one prebuilt ExploredContext yields identical CLI JSON/MCP envelope;
  - separate live runs match after normalizing only top/round/probe durations;
  - invalid request and persisted config fail before a retrieval sentinel;
  - strict explore validation does not change existing permissive operations;
  - partial follow-up has valid pack and sanitized trace;
  - MCP registration and optional forwarding are exact.

- [ ] **Step 6: Extend runtime isolation gates**

  For cst query/context/trace, context_search_query/context/trace, direct
  query_repository, and direct trace_repository, patch the exploration runner
  constructor/call to raise. Each existing operation must still return its
  exact fingerprint and the sentinel call count stays zero.

  Add a fresh Python subprocess test that imports formatters, cli, mcp_tools,
  mcp_server, and quality.runner, then executes representative ordinary
  CLI/MCP/library query/context/trace paths. Assert
  context_search_tool.exploration.runner is absent from sys.modules before and
  after. The AST test rejects every module-scope exploration import in those
  consumer modules and permits local imports only inside the explore command,
  explore MCP tool, or exploration-mode quality branch.

  AST checks also require the reviewed adjacency and forbid imports in protected
  core/context modules.

- [ ] **Step 7: Verify and commit**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_contracts.py \
    tests/test_exploration_boundaries.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_mcp_server.py \
    tests/test_formatters.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py
  git diff --check
  git add \
    src/context_search_tool/formatters.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/mcp_tools.py \
    src/context_search_tool/mcp_server.py \
    tests/test_exploration_contracts.py \
    tests/test_exploration_boundaries.py
  git commit -m "feat: expose controlled exploration"
  ~~~

### Task 8: Add The P4 Quality Mode, Metrics, And Deterministic Profile

**Files:**

- Modify: src/context_search_tool/quality/cases.py
- Modify: src/context_search_tool/quality/runner.py
- Modify: src/context_search_tool/quality/metrics.py
- Modify: src/context_search_tool/quality/aggregate.py
- Modify: src/context_search_tool/quality/reports.py
- Modify: src/context_search_tool/quality/compare.py
- Create: tests/test_quality_p4.py
- Create: tests/p4_real_exploration_acceptance.py

- [ ] **Step 1: Write failing closed-schema tests**

  Add mode exploration and validate only the ten reviewed exploration fields.
  Reject:

  - unknown fields;
  - exploration-only fields on results/context_pack modes;
  - duplicate matchers;
  - negative counts;
  - exact/max calls outside 1..3;
  - exact calls above maximum;
  - final_at_least min_matches above unique matchers;
  - unknown termination reasons.

  p4_exploration requires hash-v1, 384 dimensions, planner disabled, and no
  remote embedding settings. p4_real_exploration has the same retrieval
  determinism but requires the pinned remote-source contract.

  Load the frozen P4 catalog once through the Task 1 raw-JSON validator and once
  through production load_quality_fixture. Compare an exact fixture projection
  so production parsing matches every frozen profile/repo/case/field and does
  not silently default or discard an exploration field.

- [ ] **Step 2: Add same-run runner ownership**

  For exploration cases, quality.runner performs its exploration import only
  inside the exploration-mode branch, calls explore_repository exactly once,
  and consumes:

  - initial_bundle for existing raw hit/MRR metrics;
  - initial_pack for initial_absent and initial coverage;
  - final_pack for existing ContextPack expectations and final matchers;
  - final fused bundle only for path-union metrics;
  - trace for calls/probes/gain/provenance/timing.

  A sentinel must fail if the runner re-executes the original query to synthesize
  a baseline. Existing legacy latency_ms is exactly the duration of the round-0
  original probe; total multi-round elapsed time appears only as
  exploration_latency_ms. A clock-controlled test proves the two fields have
  distinct owners and values.

- [ ] **Step 3: Implement exact metrics**

  Add the twelve reviewed metrics with exact zero-denominator null behavior:

  - exploration_goal_coverage_initial;
  - exploration_goal_coverage_final;
  - exploration_goal_gain;
  - novel_path_count;
  - duplicate_path_ratio;
  - executed_probe_count;
  - probe_efficiency;
  - retrieval_call_count;
  - exploration_trace_coverage;
  - final_pack_noise_count;
  - final_pack_noise_ratio;
  - exploration_latency_ms.

  Count result/anchor path unions once. Assert calls = 1 + probes. Compute trace
  coverage from the complete internal valid-origin count, require it to equal
  trace.final_evidence_count, and divide by final pack item count; do not use the
  at-most-20 final_evidence preview length when items were omitted from preview.

- [ ] **Step 4: Add fixture gates**

  Apply initial_absent to initial pack, all final matchers to final pack, and the
  exact/max/gain/noise/termination gates to trace/metrics. The injected
  follow-up-only failure test succeeds initially, raises on first follow-up, and
  requires ok-quality ownership of the best pack with partial sanitized trace.
  It is not added as a real hash-profile case.

- [ ] **Step 5: Extend aggregation/report comparison conservatively**

  Keep quality report schema unchanged. Validate types/bounds and aggregate
  nullable ratios safely.

  The exploration fixture expectations and resulting pass/fail status are the
  only new hard gates. Do not add P4 metrics to the existing required
  pass-to-pass regression heuristic. Treat all twelve P4 metric deltas as
  neutral diagnostics in report comparison: novelty can be noise, a lower
  duplicate ratio can come from unrelated paths, and the reviewed probe
  efficiency formula counts novel-path-only probes. Fixture minimum gain,
  declared supports/noise, exact/max calls, termination, and trace coverage
  enforce quality instead.

  For per-case warnings, prefer exploration_latency_ms when it exists and fall
  back to legacy latency_ms for non-exploration cases. A greater-than-50-percent
  increase remains a warning, never a gating classification or aggregate p95
  gate.

  Reports show calls, gain, trace coverage, noise, and latency without exposing
  probes or source paths beyond the explicit quality case output contract.

- [ ] **Step 6: Define the real acceptance projection helper**

  tests/p4_real_exploration_acceptance.py is an executable test utility with
  exact subcommands run, initialize, and verify. The run subcommand accepts
  --fixture, --profile, --repos-dir, --repo-key, --case-id, and --output. It:

  1. loads the frozen production fixture/profile/case;
  2. validates the prepared checkout and pinned commit;
  3. uses the same quality config/index/workspace helpers as quality.runner;
  4. calls explore_repository once and production exploration evaluation once;
  5. builds the exact ten-key projection from that same ExploredContext;
  6. normalizes only trace/round/probe durations, excludes
     exploration_latency_ms from non_timing_metrics, and writes canonical JSON
  with sort_keys=False and allow_nan=False.

  The utility does not read a quality report as a source for pack hashes/trace.
  A parity test runs the utility path and quality.runner path through the same
  fake artifacts and requires identical non-timing metrics/failures. initialize
  accepts --fixture, --candidate-a, --candidate-b, and --output; it refuses an
  existing baseline, byte-compares both candidates itself, and verifies their
  exact fixture pin/keys before writing. verify performs byte comparison against
  the committed baseline.

  Do not name this file test_*.py and do not add a default skip.

- [ ] **Step 7: Run the deterministic four-case profile**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output /tmp/cst-p4-exploration.json \
    --markdown /tmp/cst-p4-exploration.md
  ~~~

  Required:

  - selected/executed/passed = 4/4/4;
  - Java gain >= 2 within <= 3 calls;
  - frontend gain >= 2, at least two declared supports, zero declared noise;
  - exact case exact_satisfied with one call and zero gain;
  - duplicate case no_marginal_gain with two calls, zero gain, second planned
    candidate unexecuted;
  - ExplorationTraceCoverage 1.0 for every non-empty case.

  Do not edit the frozen P4 catalog/snapshots if a case fails. Fix only behavior
  that violates the reviewed contract; stop for fixture/design ambiguity.

- [ ] **Step 8: Run quality and compatibility tests**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_quality_cases.py \
    tests/test_quality_runner.py \
    tests/test_quality_metrics.py \
    tests/test_quality_aggregate.py \
    tests/test_quality_reports.py \
    tests/test_quality_compare.py \
    tests/test_quality_p4.py \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_quality_p3.py

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output /tmp/cst-p4-task8-p2.json
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output /tmp/cst-p4-task8-ci.json
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_exploration_identity.py quality-projection \
    --input /tmp/cst-p4-task8-p2.json \
    --output /tmp/cst-p4-task8-p2-projection.json
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_exploration_identity.py quality-projection \
    --input /tmp/cst-p4-task8-ci.json \
    --output /tmp/cst-p4-task8-ci-projection.json
  cmp -s \
    tests/fixtures/p4_exploration/p0_p3_p2_quality.json \
    /tmp/cst-p4-task8-p2-projection.json
  cmp -s \
    tests/fixtures/p4_exploration/p0_p3_ci_quality.json \
    /tmp/cst-p4-task8-ci-projection.json

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality compare \
    --baseline .quality/p4-artifacts/baseline-p2.json \
    --candidate /tmp/cst-p4-task8-p2.json \
    --output /tmp/cst-p4-task8-p2-compare.json
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality compare \
    --baseline .quality/p4-artifacts/baseline-ci.json \
    --candidate /tmp/cst-p4-task8-ci.json \
    --output /tmp/cst-p4-task8-ci-compare.json
  git diff --check
  ~~~

  Required: both stable projections are byte-identical and both comparisons
  report zero gating regressions. A 5/5 or 8/8 pass count alone is insufficient.

- [ ] **Step 9: Commit quality support**

  ~~~bash
  git add \
    src/context_search_tool/quality/cases.py \
    src/context_search_tool/quality/runner.py \
    src/context_search_tool/quality/metrics.py \
    src/context_search_tool/quality/aggregate.py \
    src/context_search_tool/quality/reports.py \
    src/context_search_tool/quality/compare.py \
    tests/test_quality_p4.py \
    tests/p4_real_exploration_acceptance.py
  git commit -m "test: add p4 exploration quality gates"
  ~~~

### Task 9: Run And Lock Pinned PetClinic Acceptance

**Files:**

- Create: tests/fixtures/p4_exploration/petclinic-owner-registration.json

- [ ] **Step 1: Prepare the exact pinned checkout**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality prepare \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_real_exploration \
    --repos-dir .quality/p4-repos
  ~~~

  Verify checkout commit is exactly
  51045d1648dad955df586150c1a1a6e22ef400c2 and the prepared tree is clean before
  indexing. Network approval may be required; do not substitute another commit.

- [ ] **Step 2: Run the real profile twice**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_real_exploration \
    --repos-dir .quality/p4-repos \
    --output /tmp/cst-p4-real-a.json

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_real_exploration \
    --repos-dir .quality/p4-repos \
    --output /tmp/cst-p4-real-b.json
  ~~~

  Required:

  - initial Top-1 OwnerController.java;
  - final pack includes OwnerController.java, Owner.java,
    OwnerControllerTests.java, and createOrUpdateOwnerForm.html;
  - final canonical pack <= 65,536 bytes;
  - <= 2 follow-up probes and <= 3 retrieval calls;
  - ExplorationTraceCoverage 1.0;
  - no failed case/error.

  These two reports prove the production quality path, but they are not inputs
  to the canonical pack/trace projection below.

- [ ] **Step 3: Build and compare exact case projections**

  ~~~bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_real_exploration_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_real_exploration \
    --repos-dir .quality/p4-repos \
    --repo-key spring_petclinic \
    --case-id owner-registration-validation-flow \
    --output /tmp/cst-p4-owner-projection-a.json

  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_real_exploration_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_real_exploration \
    --repos-dir .quality/p4-repos \
    --repo-key spring_petclinic \
    --case-id owner-registration-validation-flow \
    --output /tmp/cst-p4-owner-projection-b.json

  cmp -s \
    /tmp/cst-p4-owner-projection-a.json \
    /tmp/cst-p4-owner-projection-b.json
  test ! -e tests/fixtures/p4_exploration/petclinic-owner-registration.json

  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_real_exploration_acceptance.py initialize \
    --fixture tests/fixtures/retrieval_quality/p4_exploration.json \
    --candidate-a /tmp/cst-p4-owner-projection-a.json \
    --candidate-b /tmp/cst-p4-owner-projection-b.json \
    --output tests/fixtures/p4_exploration/petclinic-owner-registration.json

  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_real_exploration_acceptance.py verify \
    --candidate /tmp/cst-p4-owner-projection-b.json \
    --expected tests/fixtures/p4_exploration/petclinic-owner-registration.json
  ~~~

  initialize must refuse overwrite, internally byte-compare A/B, verify the
  exact pinned fixture/profile/repo/case identity, and write only after every
  check passes. The preceding standalone cmp remains a transparent command-line
  gate rather than initialize's only equality proof. Do not hash or compare the
  complete quality reports.

- [ ] **Step 4: Run the qualitative fast-context comparison**

  When the configured fast-context service is available and authorized, run one
  balanced semantic query against the same pinned PetClinic checkout and the
  owner-registration intent. Record only:

  - returned file/range suggestions;
  - overlap/differences with CST initial/final paths;
  - qualitative observations about specificity and coverage.

  Do not copy source excerpts into acceptance fixtures, and do not convert this
  comparison into a gate. If the service is unavailable, record that fact
  honestly; PetClinic CST acceptance remains mandatory.

- [ ] **Step 5: Re-run deterministic and protected gates**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output /tmp/cst-p4-after-real.json
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_exploration_inputs.py \
    tests/test_quality_p4.py
  git diff --check
  ~~~

- [ ] **Step 6: Commit the pinned projection**

  ~~~bash
  git add tests/fixtures/p4_exploration/petclinic-owner-registration.json
  git commit -m "test: lock p4 real exploration acceptance"
  ~~~

### Task 10: Run Full Acceptance And Record Evidence

**Files:**

- Modify: README.md
- Modify: docs/retrieval-quality.md
- Modify: docs/superpowers/specs/2026-07-16-p4-controlled-multi-round-exploration-design.md
- Modify: docs/superpowers/plans/2026-07-16-p4-controlled-multi-round-exploration.md
- Modify: roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md

- [ ] **Step 1: Run all P4 focused gates**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_inputs.py \
    tests/test_exploration_boundaries.py \
    tests/test_exploration_options.py \
    tests/test_exploration_goals.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_exploration_trace.py \
    tests/test_exploration_runner.py \
    tests/test_exploration_contracts.py \
    tests/test_quality_p4.py
  ~~~

  Record exact passed count. No test may be skipped or xfailed in this focused
  deterministic command.

- [ ] **Step 2: Run protected P0-P3 acceptance**

  ~~~bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_p3.py \
    tests/test_context_pack.py
  ~~~

  Required: all 13 characterization cases and four full-stage ledgers exact;
  RetrievalTrace v1 exact; P3 TraceCoverage 1.0; ContextPack v2 tests exact.

- [ ] **Step 3: Run all three deterministic profiles**

  ~~~bash
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output /tmp/cst-p4-final.json \
    --markdown /tmp/cst-p4-final.md

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output /tmp/cst-p4-final-p2.json \
    --markdown /tmp/cst-p4-final-p2.md

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output /tmp/cst-p4-final-ci.json \
    --markdown /tmp/cst-p4-final-ci.md

  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_exploration_identity.py quality-projection \
    --input /tmp/cst-p4-final-p2.json \
    --output /tmp/cst-p4-final-p2-projection.json
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_exploration_identity.py quality-projection \
    --input /tmp/cst-p4-final-ci.json \
    --output /tmp/cst-p4-final-ci-projection.json
  cmp -s \
    tests/fixtures/p4_exploration/p0_p3_p2_quality.json \
    /tmp/cst-p4-final-p2-projection.json
  cmp -s \
    tests/fixtures/p4_exploration/p0_p3_ci_quality.json \
    /tmp/cst-p4-final-ci-projection.json

  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality compare \
    --baseline .quality/p4-artifacts/baseline-p2.json \
    --candidate /tmp/cst-p4-final-p2.json \
    --output /tmp/cst-p4-final-p2-compare.json
  PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality compare \
    --baseline .quality/p4-artifacts/baseline-ci.json \
    --candidate /tmp/cst-p4-final-ci.json \
    --output /tmp/cst-p4-final-ci-compare.json
  ~~~

  Required: P4 4/4; P2 5/5; raw CI 8/8; no errors; all P4 non-empty trace
  coverage values 1.0; both P0-P3 stable projections byte-identical; both
  quality comparisons report zero gating regressions.

- [ ] **Step 4: Run the full suite with JUnit evidence**

  ~~~bash
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_P4_REAL_EXPLORATION_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q -rs \
    --junitxml=.quality/p4-artifacts/final.xml

  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/p4_exploration_identity.py verify-junit \
    --candidate .quality/p4-artifacts/final.xml \
    --baseline-passed 1938
  ~~~

  Required:

  - no failure/error;
  - exact same nine skip node IDs/reasons as the immutable P3.2 skip ledger;
  - zero xfails;
  - no baseline pass removed;
  - final pass total equals 1,938 plus the exact number of newly collected
    default P4 tests.

  Record both the absolute count and P4 delta. The explicitly invoked real
  acceptance file must not add a default skip.

- [ ] **Step 5: Run protected-file and privacy gates**

  ~~~bash
  test "$(git hash-object tests/fixtures/retrieval_quality/queries.json)" = \
    8bbe4d560fec1499aa1f436af929b8a6bb6f3eac
  test "$(git hash-object tests/fixtures/retrieval_core_decomposition/baseline.json)" = \
    a0011178b2671af25cb0853260c8fdcf586acee0
  git diff --exit-code \
    b827707325d0ee4e9c6b2bcb3dee39955c263822 -- \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core \
    src/context_search_tool/context_pack \
    src/context_search_tool/retrieval_trace/models.py \
    src/context_search_tool/retrieval_trace/serialization.py \
    src/context_search_tool/retrieval_trace/collector.py \
    src/context_search_tool/indexer.py \
    src/context_search_tool/scanner.py \
    src/context_search_tool/chunker.py \
    src/context_search_tool/manifest.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_exploration_boundaries.py \
    tests/test_exploration_trace.py \
    tests/test_exploration_contracts.py
  git diff --check
  git status --short
  ~~~

  Review every remaining changed production file against the allowed map.

- [ ] **Step 6: Capture commit and artifact evidence**

  Record:

  - Task 1 frozen-input commit and manifest SHA;
  - Tasks 2-9 commit IDs;
  - P4 catalog SHA and unchanged P0-P3 catalog blob/SHA;
  - deterministic and PetClinic report/projection SHA values;
  - focused/full pass and skip/xfail counts;
  - P4/P2/CI profile counts;
  - P3 characterization and TraceCoverage results;
  - protected-file/import/privacy results;
  - retrieval-call/gain/noise/trace-coverage metrics per P4 case;
  - fast-context qualitative comparison or honest availability note;
  - Phase 1 still 6/7.

- [ ] **Step 7: Update docs conditionally**

  Only after all gates pass:

  - add cst explore and MCP usage to README;
  - document P4 limits, privacy, quality metrics, deterministic cases, and
    PetClinic evidence in docs/retrieval-quality.md;
  - change design and plan status to implemented/verified;
  - fill the implementation record below with exact Tasks 1-9 commits;
  - mark only Phase 4 complete in the roadmap;
  - name Phase 5 design review as the next phase without starting it;
  - preserve Phase 1 at 6/7;
  - do not embed the Task 10 documentation commit ID inside its own content.

  If any hard gate fails, leave Phase 4 open and document the blocker instead.

- [ ] **Step 8: Commit verification evidence**

  ~~~bash
  git add \
    README.md \
    docs/retrieval-quality.md \
    docs/superpowers/specs/2026-07-16-p4-controlled-multi-round-exploration-design.md \
    docs/superpowers/plans/2026-07-16-p4-controlled-multi-round-exploration.md \
    roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
  git commit -m "docs: verify controlled exploration"
  ~~~

## Implementation And Acceptance Record

Implementation has not started. Populate this table only after each focused
commit exists:

| task | commit |
| --- | --- |
| Task 1 | pending |
| Task 2 | pending |
| Task 3 | pending |
| Task 4 | pending |
| Task 5 | pending |
| Task 6 | pending |
| Task 7 | pending |
| Task 8 | pending |
| Task 9 | pending |

Final evidence is pending. The Task 10 documentation commit is intentionally
reported after creation in the handoff, not self-recorded here.

## Stop Conditions

Stop implementation and request design review if any of these occurs:

- a protected P0-P3 catalog/snapshot or P3.2 baseline must change;
- retrieval.py, retrieval_core, ContextPack policy/schema, RetrievalTrace-v1
  model/serialization, index schema, scanner, chunker, indexer, embeddings, or
  manifest appears necessary to edit;
- an existing query/context/trace/library fingerprint changes;
- ordinary execution imports/calls the exploration runner or constructs v2
  runtime state;
- a goal requires a role the current ContextPack classifier stack cannot
  produce;
- follow-up evidence is needed to add a new goal;
- an allowed probe seed cannot be traced to approved provenance;
- a new parser, arbitrary literal/comment scan, recursive import walk, absolute
  path, or environment value appears necessary;
- a probe requires a model/planner, concurrency, more than two follow-ups, or
  more than three retrieval calls;
- cross-query score arithmetic appears necessary;
- same-path replacement cannot preserve every prior frozen goal;
- protected initial evidence would need replacement or mutation;
- a final ContextPack needs more than the reviewed 24+8 fused candidates;
- a normal v1 trace omits final selections under reviewed caps;
- v2 trace equations, key order, matrices, provenance, or privacy cannot validate
  without relaxing the design;
- a handled follow-up failure cannot preserve the best valid pack;
- feedback needs a forbidden query/probe/path/content/ID/error value;
- a deterministic P4 case requires editing its frozen fixture or tuning
  single-pass ranking;
- the pinned PetClinic commit cannot meet required evidence within fixed limits;
- a new default skip/xfail appears;
- P2, raw CI, P3 characterization/TraceCoverage, or full suite regresses;
- fast-context output is treated as normative acceptance;
- work begins Phase 5 or changes Phase 1 status.

These are boundary failures, not permission to improvise a broader P4.

## Final Review Checklist

Before requesting implementation review, verify:

- [ ] every design acceptance criterion maps to a task/test/gate;
- [ ] P4 catalog is separate and queries.json remains exact;
- [ ] Task 1 assays initial/probe retrieval behavior before freezing all
  deterministic inputs;
- [ ] every new module has one responsibility and allowed imports only;
- [ ] exploration dependency direction is acyclic;
- [ ] public signatures/envelopes are exact and additive;
- [ ] the supported pack resolver is exported and direct-library invalid inputs
  make zero retrieval calls;
- [ ] strict explore validation does not alter existing operations;
- [ ] fresh ordinary imports/execution leave exploration.runner unloaded;
- [ ] initial cap, follow-up cap, fused caps, goal/probe/call caps are exact;
- [ ] goal ordering includes all six reviewed classes;
- [ ] role tables are classifier-producible, including pom fallback;
- [ ] structural and exact predicates are closed;
- [ ] every seed is approved, bounded, and provenance-backed;
- [ ] Java/frontend metadata reads use exact current APIs and I/O caps;
- [ ] probe fairness, dedupe, priority, and stale skip are deterministic;
- [ ] fusion never uses cross-query score comparison;
- [ ] protected evidence and global goal coverage are monotonic;
- [ ] v2 trace is separate from unchanged v1 and self-validating;
- [ ] failure pairs and zero-count projections are exact;
- [ ] final provenance covers every final item;
- [ ] feedback signatures/projection exclude all forbidden values;
- [ ] quality uses same-run initial snapshot and no second baseline query;
- [ ] all metric formulas and null denominators are exact;
- [ ] legacy latency belongs to round 0, exploration latency belongs to total
  duration, latency is neutral, and call counts are hard gates;
- [ ] P2/raw-CI non-timing report projections remain byte-identical;
- [ ] deterministic four-case profile proves gain/exact/no-gain behavior;
- [ ] PetClinic projection utility has executable run/initialize/verify commands
  and normalizes only allowed timings;
- [ ] real acceptance does not add a default skipped test;
- [ ] full suite skip identities, P2, raw CI, P3, and Phase 1 status remain exact;
- [ ] docs/roadmap update only after acceptance.

## Plan Review Rubric

Independent plan reviewers must check:

1. whether each task can end green without temporary compatibility aliases or
   weakening an existing assertion;
2. whether the separate P4 catalog fully resolves the immutable P3.2 catalog
   identity conflict;
3. whether input identity is frozen before production and cannot drift later;
4. whether module ownership and import adjacency are acyclic and implementable;
5. whether option ownership yields the exact public error codes before retrieval;
6. whether all goal classes, role production, structural eligibility, and
   exact_satisfied semantics are executable with current APIs;
7. whether probe seed extraction uses real SQLite/parser methods with complete
   byte/path/count bounds;
8. whether fairness/dedupe/stale behavior and planned/executed equations are
   unambiguous;
9. whether fusion is monotonic and avoids every cross-query score trap;
10. whether v2 trace validation can prove all state/count/privacy invariants
    without changing v1;
11. whether runner stop precedence and partial failure behavior are exhaustive;
12. whether CLI/MCP envelope/error/feedback contracts are exact and share one
    implementation;
13. whether quality fixtures and formulas prove gain within the same run;
14. whether deterministic and pinned-real acceptance are reproducible without
    making fast-context normative;
15. whether commit boundaries, protected gates, and stop conditions prevent
    Phase 5 or single-pass scope creep.

Any unresolved blocker or major finding keeps this plan in draft status.

## Agent Review Record

Three independent read-only reviewers inspected the first complete plan from
architecture/dependency/task-order, public-contract/privacy/trace, and
implementation-feasibility/fixtures/quality/verification perspectives.

The first pass reported 1 Blocker, 11 Major, and 6 Minor findings across the
three reports. The material issues were:

- a stale authorization stop point and eager exploration imports on ordinary
  paths;
- freezing fixtures before proving that current P0-P3 behavior can realize the
  required omissions, follow-up hits, duplicates, and goal classes;
- conflict with the immutable P3.2 quality catalog, plus incomplete direct-
  library preflight and missing public pack-option resolution;
- privacy tests that could reject legitimate user queries, incomplete v1
  omission/follow-up failure coverage, and feedback exception gaps;
- weak P2/CI baseline identity, ambiguous latency ownership, metrics that could
  reward noise, and an under-specified PetClinic projection workflow;
- volatile JUnit/report evidence and raw-fixture/production-parser parity gaps.

This revision resolves them by using a separate frozen P4 catalog, adding a
pre-freeze behavior assay, enforcing explore-only local imports and fresh-
process no-import gates, specifying zero-call direct-library validation and a
supported pack resolver, making privacy source-aware, freezing stable P2/CI
projections, keeping all new metrics neutral in report comparison, defining
round-0 versus total latency ownership, and making PetClinic A/B projection
comparison internal to the non-overwriting initializer as well as externally
visible.

Each reviewer then performed targeted rereviews. Their terminal results are:

- architecture/dependency/task order: PASS;
- public contract/privacy/trace: PASS;
- implementation feasibility/fixtures/quality/verification: PASS.

The final minor corrections were also rechecked: initial/final mutable
containers cannot alias, legitimate original-query echo is distinguished from
internal secret leakage, direct-library error semantics are present in the
design, and PetClinic initialize independently compares both candidates before
writing. No unresolved finding remains. This review approves the plan only;
Task 0 and implementation have not started.
