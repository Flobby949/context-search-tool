# P6 Freshness, Performance, And Large Repositories Implementation Plan

Date: 2026-07-18
Status: Reviewed — ready for user approval; implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Design: `docs/superpowers/specs/2026-07-18-p6-freshness-performance-large-repositories-design.md`
Current source HEAD at plan time: `bf39182f44238819df4aab7c8e42181bcef28b6b`
Required P6 entry commit: pending isolated P5 path-inventory fix
Authorization: planning and agent review only; P6 implementation is not yet authorized

> **For agentic workers:** Execute one task at a time and keep every task green.
> Begin behavior changes with a failing or protective test, run the task's exact
> gates, stage only paths listed by that task, and create the focused commit
> shown below. Stop on a P5 baseline, schema-first preflight, inventory
> completeness, observation fence, ready-generation binding, reader lifetime,
> remote-egress disclosure, exact-result, benchmark-validity, privacy,
> skip/xfail, or performance-budget mismatch. Never refresh a protected output
> or relax a budget merely to make a gate pass.

**Goal:** Make CST dependable for repeated agent use on large repositories by
adding truthful read-only index health, an explicit metadata-guided incremental
refresh, bounded lifecycle maintenance, and reproducible performance evidence
without changing protected retrieval semantics.

**Architecture:** One schema-first capability probe runs before configuration or
provider work. A two-phase workspace observer separates metadata discovery from
safe body reads. `status` inspects committed state without mutation; `index`
performs authoritative full-content verification; `refresh` prepares every
direct and dependent artifact under opening observations, completes a closing
inventory fence, then enters the existing stale-to-ready publication protocol
using frozen facts only. Manifest v2, operational schema v1, and vector
descriptor v2 are bound together by the final SQLite ready transaction. Exact
profiling and work counters select surgical optimizations; ANN and service/watch
remain separately gated decisions.

**Tech Stack:** Python 3.11-3.14, SQLite rollback-journal transactions, NumPy
immutable vector generations, frozen dataclasses, Typer, FastMCP, existing P5
parser/graph plugins, local hash-v1 acceptance embeddings, pytest, deterministic
generated repositories, canonical JSON with `allow_nan=False`, subprocess RSS
measurement, and `sqlite3.Connection.set_progress_handler` in test-only work
proofs.

---

## Source Of Truth And Execution Constraints

The reviewed design is normative:

- `docs/superpowers/specs/2026-07-18-p6-freshness-performance-large-repositories-design.md`

If this plan and the design disagree, stop, amend both documents as needed, and
repeat agent review. Do not silently choose the easier implementation.

The source worktree is intentionally not a P6 entry baseline yet. It contains
the reviewed P5 correctness fix in:

- `src/context_search_tool/indexer.py`;
- `src/context_search_tool/sqlite_store.py`;
- `tests/test_indexer_manifest.py`.

That fix re-materializes unchanged `imports` and `routes_to` sources when the
active path inventory changes. The P6 design and plan are also untracked at plan
time. Before Task 0, the P5 fix must be committed alone and pass its focused/full
gates. The independently reviewed design and plan must then be committed in one
documentation-only review commit. Record that commit as `P6_REVIEW_COMMIT`; it
must contain no production/test behavior and must not be mixed into the P5
correction. The resulting clean documentation commit is the initial
`P6_ENTRY_COMMIT` and replaces the pending placeholder above.

Execution constraints:

1. This document authorizes no branch creation, staging, commit, benchmark run
   that mutates tracked artifacts, or production implementation. Start Task 0
   only after a new explicit implementation instruction.
2. Task 0 must start from a clean commit containing the exact reviewed P5
   path-inventory fix. The candidate evidence is 2,625 passed with the established
   9 optional skips and 0 xfails on Python 3.13.12/SQLite 3.51.2; Task 0 must
   reproduce it rather than treating this plan-time result as the baseline.
3. The exact Task-0 commit becomes `P6_ENTRY_COMMIT`; its parent lineage must
   contain an isolated P5-fix commit followed only by the reviewed design/plan
   commit. Every later protected source/output comparison and baseline
   performance report records the entry commit and production-tree hash.
4. P5 deterministic language graphs remain 12/12; pinned-real P5 remains 2/2
   twice; P4 remains 4/4; P2 remains 5/5; raw CI remains 8/8; protected trace
   coverage, ContextPack v2, RetrievalTrace v1, ExplorationTrace v2,
   protected-direct, and no-legal-edge projections remain exact.
5. Task 1 freezes P6 contract fixtures, generator identity, workload/query
   manifests, metric units, privacy rules, and unoptimized baseline reports
   before any production P6 behavior changes.
6. Manifest v1/signal schema v5 stays queryable under exact P5 rules. P6 adds
   manifest v2 and operational schema v1; it does not bump the graph signal
   schema or reinterpret a future schema.
7. Raw index existence, raw manifest version, raw operational version, and raw
   graph version are inspected before `load_config()`, `read_config()`, provider
   construction, feedback, repository profiling, scanning, or unknown-row
   access. Missing/future tests monkeypatch all forbidden work to fail.
8. `status` and `stats` create or modify no file, directory, lock, SQLite row,
   access timestamp, feedback entry, or metric. They instantiate no embedding
   or planner provider and make no network call.
9. Quick inspection never reads eligible source bodies or vector payload/ID
   files. Verified inspection may stream source bodies and vector files once
   with bounded buffers; neither path parses or embeds source.
10. An incomplete inventory, control-file error, or closing-fence drift never
    infers deletion, never marks stale, and never commits ready/fresh. All prior
    rows and the prior ready snapshot remain intact.
11. Both `index` and `refresh` finish every workspace-derived safe read, hash,
    parse, relation materialization, embedding input, and returned vector before
    the closing fence. Only after the fence passes may they commit stale. From
    `stale_committed` through ready, repository source, `.gitignore`, current
    config, and topology-control reads are forbidden by an instrumented test.
12. Keep SQLite rollback-journal mode. Do not enable WAL. `GraphReadSession`
    owns its read transaction through descriptor selection, payload/ID load or
    mmap, vector search, and every use of the mapping. A vector handle, mmap, or
    view may not escape the session.
13. A graph-only refresh reuses the current immutable vector generation. A new
    generation is published only when the ordered `(embedding_id, vector)` set
    changes. Cleanup occurs only after the final ready commit while the writer
    lock remains held and must fail closed under unsupported journal modes.
14. A no-op quick refresh with no retryable skip performs zero eligible source
    reads/hashes/parses/embeddings, zero SQLite replacements, zero vector
    generation writes, and zero ready-state rewrite. Work counters are part of
    the contract, not debug-only prose.
15. A remote provider may receive only new/content-changed chunk embedding
    inputs. Dependency-only graph work sends no source. Every refresh failure
    returns `network_egress_outcome=not_attempted|possible|performed` without
    endpoint, credential, response body, environment value, or source text.
16. Existing query/context/trace/explore/explain success and error envelopes do
    not gain health siblings. Existing stats top-level `embedding` keeps its
    indexed meaning. New status/refresh envelopes follow the exact reviewed v1
    contracts.
17. Exact search optimization precedes approximation. Every rewrite must match
    frozen ordered candidate IDs/scores and protected final outputs. If the ANN
    trigger is crossed, stop for a reviewed design/plan amendment; do not install
    or ship ANN from this baseline plan.
18. P6 ships no service or watcher. Task 11 records only `deferred` or
    `eligible_for_separate_design`. Eligibility does not authorize a prototype.
19. Performance acceptance uses the deterministic generator, hash embeddings,
    planner-off cases, the same recorded host, calibrated baseline/final
    sessions, exact cold/warm definitions, and both stopwatch and work proofs.
20. Generated source repositories and `.quality/p6-*` work directories remain
    untracked. Only privacy-audited manifests, schemas, raw sample reports, and
    summaries listed by this plan may be committed under `docs/benchmarks/p6/`.
21. Each task's `Files` list is its complete **tracked commit boundary**. A task
    may write only its explicitly named ignored evidence/work roots under
    `.quality/`; those paths are never staged. New tracked paths or ignored
    roots require a reviewed plan amendment. Do not refactor adjacent code,
    change parser or ranking policy, add a configuration flag, or use
    `git add -A`.
22. Each task ends with `git diff --cached --check` and an exact staged-name
    review before its focused commit. Preserve unrelated user work.
23. Documentation and roadmap completion updates occur only in Task 11 after
    all correctness, quality, performance, privacy, and lifecycle gates pass.

## Definition Of Done

P6 implementation is complete only when:

- the clean `P6_ENTRY_COMMIT` contains the isolated P5 path-inventory fix and
  all protected P5/quality/full-suite evidence is reproduced;
- schema-first raw capability probing returns missing/future outcomes before
  config/provider/feedback/profile/scan/mutation on every public operation;
- `IndexHealthReport v1`, `StatusEnvelope v1`, and `RefreshEnvelope v1` match
  their golden required-key/order/enum/null contracts;
- quick/verified health correctly distinguishes missing, incompatible, corrupt,
  stale, degraded, metadata-fresh, and verified-fresh states under every
  writer/generation/inventory/coverage combination;
- status/stats are mechanically read-only, local, bounded, sanitized, and agree
  on one inspection result;
- manifest v1 remains queryable/degraded and authoritative index safely upgrades
  it to bound manifest v2/operational v1/descriptor v2 state;
- opening/closing fences prevent false freshness and all post-stale persistence
  consumes frozen facts only;
- quick refresh proves zero-work no-op, direct/dependent invalidation, retryable
  skip fairness, coverage recovery, truthful remote egress, and safe rejection
  of reasons requiring authoritative index;
- final ready atomically binds observation/config/content fingerprints, manifest
  identity, descriptor identity/sizes, exact SQLite counts/IDs, graph state, and
  work summary;
- immutable generation cleanup, rollback-journal reader lifetime, bounded
  tombstone purge, crash recovery, and 100-step churn reach the designed steady
  state;
- the deterministic smoke/large/scale/stress harness records valid workload,
  environment, cold/warm, RSS, disk, row/byte/pass, and raw sample evidence;
- mandatory `RepositoryPathIndex`, planner-off profile skip, exact SQLite work,
  and exact vector top-k changes meet budgets without protected output drift;
- ANN is either not triggered or has a separately reviewed amendment; exact
  search remains the shipped fallback;
- service/watch has only an evidence-backed defer/eligibility record and no
  shipped daemon behavior;
- P5 12/12, pinned-real P5 2/2 twice, P4 4/4, P2 5/5, raw CI 8/8, protected
  projections, privacy/no-fetch, supported runtime matrix, and full suite pass
  with the exact established optional skips and zero xfails;
- committed P6 acceptance artifacts pass privacy/schema validation, and docs/
  roadmap are updated only after every gate above passes.

## File Responsibility Map

| area | production/artifact owner | focused tests |
| --- | --- | --- |
| health values, canonical envelopes, raw preflight, inspector | new `src/context_search_tool/index_health.py` | new `tests/test_index_health.py` |
| two-phase inventory, metadata tokens, safe reads, skips | `src/context_search_tool/scanner.py` | `tests/test_tokenizer_scanner.py`, `tests/test_index_health.py` |
| manifest v1/v2 and embedding/config fingerprints | `src/context_search_tool/manifest.py` | new `tests/test_manifest_v2.py` |
| operational schema, observations, ready bindings, purge/work counters | `src/context_search_tool/sqlite_store.py`, `src/context_search_tool/graph_lifecycle.py` | `tests/test_graph_store.py`, `tests/test_graph_lifecycle.py`, new `tests/test_p6_operational_store.py` |
| descriptor v1/v2, mmap/normalized exact top-k, cleanup | `src/context_search_tool/vector_store.py` | `tests/test_embeddings_vector_store.py` |
| authoritative index and quick refresh orchestration | `src/context_search_tool/indexer.py` | `tests/test_indexer_manifest.py`, new `tests/test_incremental_refresh.py` |
| shared path/unit context and measured dependent work | `src/context_search_tool/graph_plugins.py`, `src/context_search_tool/frontend_graph.py`, `src/context_search_tool/test_association.py` only if their owning task requires it | existing focused P5 graph tests plus performance work proofs |
| exact retrieval/store hot paths | `src/context_search_tool/retrieval.py`, `src/context_search_tool/repo_profile.py`, `src/context_search_tool/retrieval_core/candidates.py`, `src/context_search_tool/sqlite_store.py` | `tests/test_repo_profile.py`, `tests/test_sqlite_store.py`, protected retrieval tests |
| CLI/MCP status, stats, refresh | `src/context_search_tool/cli.py`, `src/context_search_tool/mcp_tools.py`, `src/context_search_tool/mcp_server.py` | `tests/test_cli_commands.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` |
| benchmark generator, runner, schemas, privacy | new `scripts/p6_benchmark.py`, new `tests/test_p6_benchmark.py`, `tests/fixtures/p6_performance/**`, `docs/benchmarks/p6/**` | `tests/test_p6_benchmark.py` |
| protected source-change allowlist/import boundaries | `tests/test_retrieval_core_boundaries.py` | same file |
| accepted documentation | `README.md`, `docs/retrieval-quality.md`, reviewed design/plan, roadmap | final artifact and link checks |

`index_health.py` owns operational inspection and serialization only. It may
depend on `paths`, non-creating config reads, manifest raw/versioned readers,
scanner inventory values, graph lifecycle values, SQLite read sessions, and
vector descriptor readers. Scanner, manifest, store, and vector modules must not
import CLI/MCP. Retrieval must not import status/refresh public adapters. The
benchmark script may call production entry points and test-only instrumentation;
production code must not import `scripts` or benchmark fixtures.

## Public And Persistent Surface

| surface | P6 contract and activation task |
| --- | --- |
| `cst status [repo] [--json] [--verify] [--require ...]` | Task 4 replaces legacy filename checks with read-only `StatusEnvelope v1`/human health |
| `cst stats [repo] [--json] [--verify]` | Task 4 preserves current human fields and adds nested health; existing missing/future errors remain errors |
| `cst index [repo]` | Task 5 retains command/authoritative meaning, adds schema-first loading, verified observations, v2 publication, and additive work summary |
| `cst refresh [repo] [--json]` | Task 7 activates explicit metadata-guided mutation and `RefreshEnvelope v1` |
| `context_search_status(repo, verify=False)` | Task 4 adds dedicated reportable missing/incompatible/corrupt status |
| `context_search_stats(repo, verify=False)` | Task 4 preserves existing top-level success/error shape and indexed `embedding`, adds `index_health` |
| `context_search_refresh(repo)` | Task 7 adds explicit mutation with exact error/egress contract |
| query/context/trace/explore/explain | no success-schema additions; Task 4 only shares future-schema preflight and Task 9/10 preserve exact results |
| manifest | readers accept v1/v2; Task 3 adds writer-v2 structure, Task 5 first publishes it |
| SQLite graph schema | remains v5; Task 3 adds independent operational v1 DDL/metadata, authoritative only at final ready |
| vector descriptor | readers accept v1/v2; Task 3 adds v2 sizes/bindings, Task 5 first publishes it |
| ANN/service/watch | no public or persistent surface in this plan |

## Task And Commit Order

| task | purpose | focused commit |
| ---: | --- | --- |
| 0 | Reproduce clean P5/P6 entry and quality/performance environment | no commit |
| 1 | Freeze P6 API/workload/metric/privacy contracts and unoptimized baseline | `test: lock p6 contracts and benchmark baseline` |
| 2 | Add pure inventory, report, raw capability, and inspection primitives | `feat: add p6 health inspection core` |
| 3 | Add internal manifest v2, operational v1, and descriptor v2 persistence | `feat: add p6 snapshot metadata` |
| 4 | Activate read-only CLI/MCP status and additive stats | `feat: expose p6 index health` |
| 5 | Make authoritative index observation-safe and publish verified v2 | `feat: make authoritative index observation safe` |
| 6 | Build the complete internal quick-refresh path and work proofs | `feat: add p6 incremental refresh core` |
| 7 | Add bounded maintenance/recovery and activate public refresh | `feat: activate p6 incremental refresh` |
| 8 | Remove measured indexing/path-context amplification | `perf: optimize p6 indexing paths` |
| 9 | Optimize measured exact SQLite/repository query paths | `perf: optimize p6 exact recall` |
| 10 | Optimize exact vector load/search and record ANN decision | `perf: optimize p6 exact vector search` |
| 11 | Run final quality/performance/privacy acceptance and record P6 | `docs: record p6 acceptance` |

Tasks 2-3 add directly tested internal primitives without changing public
status/stats/index behavior. Task 4 activates read-only health against missing,
legacy, and synthetic v2 states; no production writer can create v2 yet. Task 5
is the sole authoritative v2-writer activation. Task 6 builds a complete
refresh entry point invoked only by direct tests. Task 7 adds all cleanup,
failure, egress, and reader-lifetime gates before exposing CLI/MCP refresh. Tasks
8-10 optimize only measured contributors and must preserve exact projections.

## Shared Verification Commands

Use the accepted P5 runtime unless Task 0 records a reviewed replacement:

```bash
unset \
  CST_RUN_P1_ACCEPTANCE \
  CST_P2_REAL_CONTEXT_REPOS_DIR \
  CST_P4_REAL_EXPLORATION_REPOS_DIR \
  CST_P5_REAL_LANGUAGE_GRAPHS_REPOS_DIR \
  CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
  CST_SMOKE_REPOS_DIR \
  CST_PLANNER_REQUESTS_REPO
export P6_RUNTIME="$PWD/.quality/p5-runtime/bin/python"
test -x "$P6_RUNTIME"
"$P6_RUNTIME" -c \
  'import sqlite3, sys; assert sys.version_info[:2] == (3, 13); assert sqlite3.sqlite_version_info[:2] == (3, 51)'
```

Focused groups, omitting not-yet-created files until their owning task:

```bash
# P6 health, persistence, and public contracts
PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
  tests/test_index_health.py \
  tests/test_manifest_v2.py \
  tests/test_p6_operational_store.py \
  tests/test_tokenizer_scanner.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py

# P6 index/refresh/vector lifecycle
PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
  tests/test_incremental_refresh.py \
  tests/test_indexer_manifest.py \
  tests/test_graph_lifecycle.py \
  tests/test_graph_store.py \
  tests/test_embeddings_vector_store.py

# P6 performance correctness and work proofs
PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
  tests/test_p6_benchmark.py \
  tests/test_sqlite_store.py \
  tests/test_repo_profile.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py

# Protected P0-P5 contracts
PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
  tests/test_p5_inputs.py \
  tests/test_p5_graph_contract.py \
  tests/test_quality_p5.py \
  tests/test_p5_protected_direct.py \
  tests/test_resolved_graph_expansion.py \
  tests/test_p5_explain.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_context_pack.py \
  tests/test_exploration_boundaries.py \
  tests/test_exploration_contracts.py \
  tests/test_exploration_runner.py \
  tests/test_quality_p3.py \
  tests/test_quality_p4.py

# Full suite
PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
```

Every production task runs its focused group plus protected P0-P5 contracts.
Tasks 5-11 also run the full suite. No task introduces a default skip or xfail.
Before every commit:

```bash
git diff --cached --check
git diff --cached --name-only
```

The staged-name output must be a subset of that task's explicit `Files` list and
must contain every changed path intended for that focused commit.

### Mandatory TDD Evidence Protocol

Tasks 1-10 are test-first checkpoints, not descriptions to validate only after
implementation. Before each production behavior named by a later step, add the
smallest focused test nodes for that behavior and run them against the unchanged
production tree through Task 1's `tdd-red`; after implementation, `tdd-green`
reruns the exact arguments with byte-identical tests and emits
`.quality/p6-artifacts/tdd-task-N.json`. Task 1 uses the reviewed bootstrap path.
The first mandatory RED payload is written in each task below; repeat the same
sequence for later fault, concurrency, egress, work-counter, and platform cases
before their production step. A missing module/symbol is tested through a
capability assertion inside the test body, never a top-level import failure.
Syntax/import/collection/fixture failures never count as RED. If a new test
unexpectedly passes, prove it is already covered or correct the test before
changing production.

For optimization tasks, first run the frozen correctness projection green,
then add a deterministic row/byte/pass/allocation assertion that fails on the
old work while correctness stays green. After implementation, rerun the exact
RED nodes green, the task-focused group, protected contracts, and any required
full suite. After the exact `git add`, every task invokes `tdd-green` (Task 1
uses `tdd-bootstrap`) with `--staged-tree "$(git write-tree)"`, then validates
the record against the same tree. Thus the recorded GREEN production/test
hashes and candidate tree are the final staged state. A task cannot commit
without this schema-valid RED-to-GREEN proof. TDD records remain ignored local
evidence; Task 11 publishes only their privacy-safe aggregate.

### Task 0: Establish The Clean P6 Entry Baseline

**Tracked files:** none

**Allowed ignored evidence roots:** `.quality/p6-artifacts/` and the existing
`.quality/p5-repos/`. Task 0 must not write any other tracked or untracked path.

- [ ] **Step 1: Start only after explicit implementation authorization**

  Confirm the user has authorized implementation, the P5 correction is an
  isolated commit, the reviewed design/plan are tracked by the immediately
  following documentation-only `P6_REVIEW_COMMIT`, and the worktree contains no
  unrelated tracked or untracked changes. Then create the implementation
  branch:

  ```bash
  git status --short
  git log -4 --oneline
  git switch -c codex/p6-freshness-performance
  export P6_ENTRY_COMMIT="$(git rev-parse HEAD)"
  export P6_REVIEW_COMMIT="$P6_ENTRY_COMMIT"
  git show --stat --oneline "$P6_ENTRY_COMMIT"
  git diff --name-only "$P6_ENTRY_COMMIT^" "$P6_ENTRY_COMMIT"
  ```

  The review commit may contain only the two reviewed P6 documentation files;
  its parent lineage contains the exact isolated path-inventory correction and
  no P6 production code. If either commit is missing, mixed, or differs from the
  reviewed document hashes, stop before creating the branch.

- [ ] **Step 2: Prove the P5 correction and source boundary**

  Inspect the entry diff from `bf39182f44238819df4aab7c8e42181bcef28b6b`
  and require the only source/test delta to be the reviewed P5 correction:

  ```bash
  git diff --name-only \
    bf39182f44238819df4aab7c8e42181bcef28b6b \
    "$P6_ENTRY_COMMIT" -- src/context_search_tool tests
  git diff --check \
    bf39182f44238819df4aab7c8e42181bcef28b6b \
    "$P6_ENTRY_COMMIT"
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_indexer_manifest.py::test_incremental_path_change_rematerializes_frontend_selectors \
    tests/test_indexer_manifest.py::test_internal_v5_deletion_regenerates_unchanged_test_associations \
    tests/test_graph_store.py
  ```

  Review the full diff semantically: additions/deletions may re-materialize
  active `imports`/`routes_to` sources, while a body-only no-op and unrelated
  relations remain unchanged.

- [ ] **Step 3: Freeze runtime, host, and dependency evidence**

  ```bash
  mkdir -p .quality/p6-artifacts
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -c \
    'import json, platform, sqlite3, sys; print(json.dumps({"python": sys.version, "sqlite": sqlite3.sqlite_version, "platform": platform.platform(), "machine": platform.machine()}, sort_keys=True))' \
    > .quality/p6-artifacts/entry-runtime.json
  "$P6_RUNTIME" -m pip freeze \
    > .quality/p6-artifacts/entry-dependencies.txt
  ```

  These raw runtime/dependency files are the only Task-0 environment inputs.
  Task 1's structured benchmark runner records CPU count, physical memory,
  local-disk class, power/governor state, swap before/after, background CPU, and
  calibration under the frozen environment schema. The acceptance host must
  have at least 8 logical CPUs, 16 GiB RAM, local SSD, no swap growth, and
  background CPU below 20%. No producer may retain usernames, absolute home
  paths, serial numbers, environment values, or process command lines.

- [ ] **Step 4: Reproduce the full and protected baseline**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs \
    --junitxml=.quality/p6-artifacts/entry-full.xml

  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    --profile p5_language_graphs \
    --output .quality/p6-artifacts/entry-p5.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output .quality/p6-artifacts/entry-p4.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output .quality/p6-artifacts/entry-p2.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output .quality/p6-artifacts/entry-ci.json
  ```

  Required full result: exactly 2,625 passed, the same 9 optional skip node IDs,
  and 0 xfails/errors. Required quality aggregates are 12/12, 4/4, 5/5, and 8/8
  with protected trace coverage 1.0. Re-run the committed protected-direct,
  no-legal-edge, P5 structural projection, ContextPack, trace, and exploration
  identity tests; do not initialize or rewrite any expected file.

- [ ] **Step 5: Reproduce pinned-real P5 twice**

  Use the existing pinned preparation and non-default acceptance script. The
  only network-capable step is the explicit `prepare`; if network access was not
  separately authorized or the checkout is already valid, omit it and validate
  the existing prepared repository. Never fetch during either measured run.

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality prepare \
    tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos
  test "$(git -C .quality/p5-repos/spring-petclinic rev-parse HEAD)" = \
    51045d1648dad955df586150c1a1a6e22ef400c2
  test -z "$(git -C .quality/p5-repos/spring-petclinic status --porcelain)"

  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output .quality/p6-artifacts/entry-real-a.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output .quality/p6-artifacts/entry-real-b.json
  cmp -s \
    .quality/p6-artifacts/entry-real-a.json \
    .quality/p6-artifacts/entry-real-b.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate .quality/p6-artifacts/entry-real-a.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate .quality/p6-artifacts/entry-real-b.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  ```

  Both candidates must be byte-identical, exactly 2/2, and equal to the
  committed normalized projection. Pin drift, a dirty prepared checkout, output
  drift, or any fetch during the runs blocks P6.

- [ ] **Step 6: Record the immutable entry facts**

  Produce only deterministic raw inputs here; Task 1's reviewed adapters create
  and validate the typed entry record:

  ```bash
  git rev-parse HEAD > .quality/p6-artifacts/entry-commit.txt
  shasum -a 256 \
    .quality/p6-artifacts/entry-full.xml \
    .quality/p6-artifacts/entry-p5.json \
    .quality/p6-artifacts/entry-p4.json \
    .quality/p6-artifacts/entry-p2.json \
    .quality/p6-artifacts/entry-ci.json \
    .quality/p6-artifacts/entry-real-a.json \
    .quality/p6-artifacts/entry-real-b.json \
    .quality/p6-artifacts/entry-runtime.json \
    .quality/p6-artifacts/entry-dependencies.txt \
    > .quality/p6-artifacts/entry-evidence-hashes.txt
  ```

  The raw JUnit owns counts/skip node IDs; quality and real JSON own their exact
  aggregates/projection; hash text only binds bytes and may not substitute for
  parsing them. Task 0 changes no tracked file and creates no commit.

**Stop:** any dirty source, P5-fix mismatch, runtime/fixture drift, quality
failure, real-repository drift, new skip/xfail, or full-suite mismatch blocks
Task 1.

### Task 1: Freeze P6 Contracts, Workloads, And The Unoptimized Baseline

**Files:**

- Create: `.github/workflows/p6-functional-matrix.yml`
- Create: `scripts/p6_benchmark.py`
- Create: `tests/test_p6_benchmark.py`
- Create: `tests/fixtures/p6_contracts/index_health_v1.json`
- Create: `tests/fixtures/p6_contracts/status_envelopes_v1.json`
- Create: `tests/fixtures/p6_contracts/refresh_envelopes_v1.json`
- Create: `tests/fixtures/p6_contracts/operation_outcomes_v1.json`
- Create: `tests/fixtures/p6_performance/workload_manifest.json`
- Create: `tests/fixtures/p6_performance/query_cases.json`
- Create: `tests/fixtures/p6_performance/exact_candidate_baseline.json`
- Create: `docs/benchmarks/p6/README.md`
- Create: `docs/benchmarks/p6/schemas/benchmark-report-v1.json`
- Create: `docs/benchmarks/p6/schemas/decision-record-v1.json`
- Create: `docs/benchmarks/p6/schemas/matrix-summary-v1.json`
- Create: `docs/benchmarks/p6/schemas/entry-record-v1.json`
- Create: `docs/benchmarks/p6/schemas/environment-report-v1.json`
- Create: `docs/benchmarks/p6/schemas/quality-report-v1.json`
- Create: `docs/benchmarks/p6/schemas/tdd-record-v1.json`
- Create: `docs/benchmarks/p6/baseline/entry-environment.json`
- Create: `docs/benchmarks/p6/baseline/entry-smoke.json`
- Create: `docs/benchmarks/p6/baseline/entry-large.json`
- Create: `docs/benchmarks/p6/baseline/entry-scale-5k.json`
- Create: `docs/benchmarks/p6/baseline/entry-scale-10k.json`
- Create: `docs/benchmarks/p6/baseline/entry-performance.json`
- Modify: `tests/test_retrieval_core_characterization.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write benchmark-schema and privacy tests first**

  Freeze one canonical benchmark report schema with required environment,
  implementation/harness identity, workload identity, operation/case, cold/warm
  state, calibration, raw samples, stage timings, work counters, RSS, disk,
  summary statistics, and validity fields. Reject unknown units, missing raw
  samples, mixed query cases, NaN/Inf, absolute temporary roots, environment
  dumps, source bodies, vector floats, secrets, unapproved real query text, or a
  dirty production-source marker. Implementation identity contains both the
  commit and `src/context_search_tool` tree object; an asserted commit string
  without the matching tree is invalid.

  Freeze decision records for exact/ANN and service/watch as
  `retained|prototype_requires_amendment` and
  `deferred|eligible_for_separate_design`. A decision schema must not encode
  implementation authorization.

  Freeze a matrix-summary schema keyed by implementation commit/tree, workflow
  file hash, OS, architecture, Python version, dependency-lock hash, exact test/
  skip/xfail counts, JUnit digest, run identity, and conclusion. It contains no
  raw environment values or credentials.

  Freeze four more closed schemas: Task-0 entry identity/evidence hashes,
  privacy-safe environment/calibration summary, protected-quality/full-suite
  summary, and `TddRecordV1`. The TDD record binds task, pre-change commit/tree,
  production/test file hashes, exact pytest node IDs/arguments, RED exit and
  assertion summaries, GREEN exit/results, final staged tree, timestamps, and
  producer version. RED and GREEN must use byte-identical test files; a
  collection/import/syntax/fixture error is invalid.

  Add negative tests proving each final churn threshold independently fails
  final-mode validation/comparison: disk/page ratio, tombstone threshold, query
  p95 drift, and generation count. Baseline-mode reports may omit churn; a
  final-mode performance report may not.

- [ ] **Step 2: Freeze the reviewed API golden values before implementation**

  Materialize the complete required-key `IndexHealthReport v1` examples for at
  least missing, future manifest, future operational, future graph, legacy v1,
  healthy metadata, healthy verified, stale, writer/generation interrupted,
  degraded coverage, and stable corruption. Freeze Status/Refresh success and
  every operation-specific error allowlist, including required refresh-error
  egress outcome.

  Golden tests validate canonical field order, enums, null vs empty collection
  rules, bounded samples, fail-closed embedding egress, and the complete
  operation matrix. At this task the production serializers do not exist;
  fixture/schema validation is the failing/protective source of truth for Tasks
  2-7.

- [ ] **Step 3: Run the benchmark-contract RED phase**

  New-module and new-command checks perform capability lookup inside the test
  body and fail an explicit assertion; they do not import an absent module at
  collection time. After writing only the new tests, schemas, and golden
  fixtures, capture the bootstrap RED evidence before the harness exists:

  ```bash
  shasum -a 256 \
    tests/test_p6_benchmark.py \
    tests/fixtures/p6_contracts/index_health_v1.json \
    tests/fixtures/p6_contracts/status_envelopes_v1.json \
    tests/fixtures/p6_contracts/refresh_envelopes_v1.json \
    tests/fixtures/p6_contracts/operation_outcomes_v1.json \
    tests/fixtures/p6_performance/workload_manifest.json \
    tests/fixtures/p6_performance/query_cases.json \
    tests/fixtures/p6_performance/exact_candidate_baseline.json \
    docs/benchmarks/p6/schemas/benchmark-report-v1.json \
    docs/benchmarks/p6/schemas/decision-record-v1.json \
    docs/benchmarks/p6/schemas/matrix-summary-v1.json \
    docs/benchmarks/p6/schemas/entry-record-v1.json \
    docs/benchmarks/p6/schemas/environment-report-v1.json \
    docs/benchmarks/p6/schemas/quality-report-v1.json \
    docs/benchmarks/p6/schemas/tdd-record-v1.json \
    > .quality/p6-artifacts/tdd-task-1-test-input-hashes.txt
  set +e
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_p6_benchmark.py \
    > .quality/p6-artifacts/tdd-task-1-red.log 2>&1
  export P6_TASK1_RED_EXIT="$?"
  set -e
  test "$P6_TASK1_RED_EXIT" -eq 1
  printf '%s\n' "$P6_TASK1_RED_EXIT" \
    > .quality/p6-artifacts/tdd-task-1-red-exit.txt
  ```

  Record the exact failing node IDs. RED must be caused by the absent harness
  subcommands/schema enforcement and matrix contract—not collection, syntax, or
  fixture-parse errors. Fix the test itself before proceeding if the failure is
  not the intended missing behavior. Do not edit `test_p6_benchmark.py` after
  this point; if it must change, discard the raw record and repeat RED from the
  unchanged production tree.

- [ ] **Step 4: Implement a deterministic generated-repository harness**

  Add `generate`, `run`, `assemble`, `paired`, `decide`, `tdd-bootstrap`,
  `tdd-red`, `tdd-green`, `validate`, `compare`, and `publish` subcommands to
  `scripts/p6_benchmark.py`. Generation uses a versioned seed and writes only a
  requested external work directory. It creates exact smoke, large, scale-5k,
  scale-10k, and stress manifests from the design, including file/source/chunk
  bytes, paths/depth, language/project markers, token/symbol/signal/relation
  density, selectivity families, skip/control failures, and the 100-step churn
  schedule. It never copies real repository source.

  `assemble` requires schema-valid JSON inputs. Its only non-JSON inputs use
  closed, tested adapters for JUnit XML, normalized `pip freeze`, one lowercase
  Git SHA, a lowercase SHA-256 manifest over allowlisted relative evidence
  paths, and exact `<commit> <subject>` lineage text; each adapter validates
  grammar, hashes raw bytes, extracts an allowlisted projection, and rejects
  unknown/private data.
  Adapter positive/negative tests include `name @ file://...` and direct-VCS/
  URL freeze entries: resolve installed distribution metadata to
  `normalized-name==version`, retain only the raw-file digest, and never publish
  the URL, credential, local path, revision locator, or fragment.
  Raw XML/text is evidence input, not falsely described as JSON-schema-valid.
  `paired` alternates baseline/final subprocesses by pair ID using one external
  harness and two explicit clean implementation roots; `decide` emits only the
  two closed decision schemas; and `publish` validates privacy, canonicalizes,
  and refuses overwrite while copying a local report to an explicit committed
  path. Every command is unit-tested for missing/duplicate/mixed identity inputs.

  `tdd-red` runs the passed pytest node list, requires ordinary assertion
  failures and no collection/import/syntax/fixture error, and writes a pending
  record. `tdd-green` requires byte-identical tests, reruns the exact arguments,
  requires all nodes green, and emits `TddRecordV1`; `tdd-bootstrap` converts
  Task 1's pre-harness raw RED log/exit/test hashes plus its later identical
  GREEN run. `validate` refuses a TDD record missing either phase or whose test
  identity changed.

  The committed workload manifest stores the generator version/hash, seed,
  cardinalities, byte distributions, query identities, edit schedule, and
  expected content fingerprints—not generated bodies. It also freezes the
  complete `protected_small_entry_comparable` operation/case IDs used by the
  <=10% paired gate. Two independent smoke generations must have equal
  canonical fingerprints.

- [ ] **Step 5: Implement measurement semantics without product changes**

  The runner launches fresh subprocesses, records nearest-rank p95, expensive
  operation median/max, population CV, `ru_maxrss` normalized by platform, empty
  harness subtraction, disk component sizes, and stage/call/row/byte/pass
  counters. It supports:

  - `cli_process_cold` after one page-cache warmup;
  - `mcp_resident_warm` after three production-process warmups;
  - informational `filesystem_cold_diagnostic` only;
  - full build, authoritative no-op, current status/stats, ordinary query,
    bounded explore, one-file edit, scale, and churn cases;
  - explicit `unsupported` for pre-P6 quick/verified status and refresh rather
    than fabricating a baseline.

  Use wrappers and test-only SQLite progress handlers for unoptimized work
  attribution. Do not add benchmark counters to RetrievalTrace or mutate
  production behavior in this task.

  Add `.github/workflows/p6-functional-matrix.yml` as a functional-only matrix
  over `ubuntu-latest|macos-latest|windows-latest` and Python 3.11-3.14. It runs
  the P6 health/refresh/vector/lifecycle tests plus protected contracts, audits
  every skip/xfail node, and uploads JUnit plus one schema-valid matrix summary
  per cell. It triggers only on tags matching `p6-acceptance-*`; Tasks 1-10 do
  not push such a tag, so they remain green before later tests exist. Every cell
  binds `github.ref_name` as the unique evidence ID, `github.sha`, workflow hash,
  run ID, and run attempt; workflow `run-name` is exactly
  `P6 evidence <github.ref_name>`. Pushing the final evidence tag still requires
  the user's separate publication/CI authorization. Tests pin the exact trigger,
  run-name, matrix, evidence binding, and commands so a partial or unrelated run
  cannot be reported as full.

- [ ] **Step 6: Verify the pre-RED exact query candidate projections**

  Step 2 materialized `exact_candidate_baseline.json` before Task-1 RED and its
  hash is part of the bootstrap identity. Compute ordered candidate IDs, finite
  scores, source/score parts, and final result fingerprints for high-hit,
  low-hit, zero-hit, ambiguity, CJK/ASCII direct text, path/symbol, lexical,
  signal, semantic, planner-off ordinary query, and one P4 explore family from
  two generated snapshots; require both local candidates to be byte-equal to
  the frozen fixture. Never rewrite it after RED. If either differs because the
  fixture/test was wrong, discard the Task-1 RED evidence, fix the fixture, and
  repeat Step 3 from the unchanged product tree. Protected real outputs remain
  separate and immutable.

- [ ] **Step 7: Capture the unoptimized entry performance**

  With production source equal to `P6_ENTRY_COMMIT`, generate smoke and large
  repositories outside the worktree, run the reference-host calibrations, then
  record all currently supported baseline cases. First prove the production
  tree is byte-for-byte the recorded entry tree:

  ```bash
  git diff --exit-code "$P6_ENTRY_COMMIT" -- src/context_search_tool
  export P6_ENTRY_PRODUCTION_TREE="$(git rev-parse \
    "$P6_ENTRY_COMMIT:src/context_search_tool")"
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier smoke --output .quality/p6-smoke
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier large --output .quality/p6-large
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier scale-5k --output .quality/p6-scale-5k
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier scale-10k --output .quality/p6-scale-10k
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-smoke \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --output .quality/p6-artifacts/entry-smoke.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-large \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --output .quality/p6-artifacts/entry-large.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-scale-5k \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --output .quality/p6-artifacts/entry-scale-5k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-scale-10k \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --output .quality/p6-artifacts/entry-scale-10k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind performance \
    --mode baseline \
    --input .quality/p6-artifacts/entry-smoke.json \
    --input .quality/p6-artifacts/entry-large.json \
    --input .quality/p6-artifacts/entry-scale-5k.json \
    --input .quality/p6-artifacts/entry-scale-10k.json \
    --output .quality/p6-artifacts/entry-performance.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind entry \
    --input .quality/p6-artifacts/entry-commit.txt \
    --input .quality/p6-artifacts/entry-evidence-hashes.txt \
    --input .quality/p6-artifacts/entry-full.xml \
    --input .quality/p6-artifacts/entry-p5.json \
    --input .quality/p6-artifacts/entry-p4.json \
    --input .quality/p6-artifacts/entry-p2.json \
    --input .quality/p6-artifacts/entry-ci.json \
    --input .quality/p6-artifacts/entry-real-a.json \
    --input .quality/p6-artifacts/entry-real-b.json \
    --input .quality/p6-artifacts/entry-runtime.json \
    --input .quality/p6-artifacts/entry-dependencies.txt \
    --output .quality/p6-artifacts/entry-record.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/entry-record.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind environment \
    --input .quality/p6-artifacts/entry-record.json \
    --input .quality/p6-artifacts/entry-performance.json \
    --output .quality/p6-artifacts/entry-environment.json
  ```

  The report records `implementation_commit=P6_ENTRY_COMMIT` and a separate
  hash of the uncommitted benchmark harness/fixtures. Require zero dirty paths
  under `src/context_search_tool`; harness/report files may be dirty and are
  explicitly listed. Every report records `P6_ENTRY_PRODUCTION_TREE` and the
  runner verifies it against the implementation root. Copy the privacy-safe
  Task-0 host/runtime/dependency,
  calibration, suite-count, skip-node, protected-report, and pinned-real facts
  into `docs/benchmarks/p6/baseline/entry-environment.json`; no raw environment
  dump or absolute path may enter it. Sanitize/validate the combined raw report
  before publishing it. Use `publish` separately for the environment, four raw
  tier reports, and combined performance report; each destination is the exact
  corresponding `docs/benchmarks/p6/baseline/entry-*.json` path listed above.

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/entry-environment.json \
    --output docs/benchmarks/p6/baseline/entry-environment.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/entry-smoke.json \
    --output docs/benchmarks/p6/baseline/entry-smoke.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/entry-large.json \
    --output docs/benchmarks/p6/baseline/entry-large.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/entry-scale-5k.json \
    --output docs/benchmarks/p6/baseline/entry-scale-5k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/entry-scale-10k.json \
    --output docs/benchmarks/p6/baseline/entry-scale-10k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/entry-performance.json \
    --output docs/benchmarks/p6/baseline/entry-performance.json
  ```

- [ ] **Step 8: Verify the harness and frozen contracts**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_p6_benchmark.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report docs/benchmarks/p6/baseline/entry-performance.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report docs/benchmarks/p6/baseline/entry-environment.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report docs/benchmarks/p6/baseline/entry-scale-5k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report docs/benchmarks/p6/baseline/entry-scale-10k.json
  git diff --check
  ```

  The baseline does not need to meet final P6 budgets; it must be reproducible,
  calibrated, complete for supported cases, explicit about unsupported cases,
  and privacy-clean.

- [ ] **Step 9: Commit the frozen evidence**

  ```bash
  git add \
    .github/workflows/p6-functional-matrix.yml \
    scripts/p6_benchmark.py \
    tests/test_p6_benchmark.py \
    tests/fixtures/p6_contracts/index_health_v1.json \
    tests/fixtures/p6_contracts/status_envelopes_v1.json \
    tests/fixtures/p6_contracts/refresh_envelopes_v1.json \
    tests/fixtures/p6_contracts/operation_outcomes_v1.json \
    tests/fixtures/p6_performance/workload_manifest.json \
    tests/fixtures/p6_performance/query_cases.json \
    tests/fixtures/p6_performance/exact_candidate_baseline.json \
    docs/benchmarks/p6/README.md \
    docs/benchmarks/p6/schemas/benchmark-report-v1.json \
    docs/benchmarks/p6/schemas/decision-record-v1.json \
    docs/benchmarks/p6/schemas/matrix-summary-v1.json \
    docs/benchmarks/p6/schemas/entry-record-v1.json \
    docs/benchmarks/p6/schemas/environment-report-v1.json \
    docs/benchmarks/p6/schemas/quality-report-v1.json \
    docs/benchmarks/p6/schemas/tdd-record-v1.json \
    docs/benchmarks/p6/baseline/entry-environment.json \
    docs/benchmarks/p6/baseline/entry-smoke.json \
    docs/benchmarks/p6/baseline/entry-large.json \
    docs/benchmarks/p6/baseline/entry-scale-5k.json \
    docs/benchmarks/p6/baseline/entry-scale-10k.json \
    docs/benchmarks/p6/baseline/entry-performance.json \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-bootstrap \
    --task 1 \
    --pre-change-commit "$P6_ENTRY_COMMIT" \
    --red-log .quality/p6-artifacts/tdd-task-1-red.log \
    --red-exit-file .quality/p6-artifacts/tdd-task-1-red-exit.txt \
    --test-input-hashes .quality/p6-artifacts/tdd-task-1-test-input-hashes.txt \
    --pytest-node tests/test_p6_benchmark.py \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-1.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-1.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "test: lock p6 contracts and benchmark baseline"
  ```

### Task 2: Add Pure Inventory, Report, And Raw Inspection Primitives

**Files:**

- Create: `src/context_search_tool/index_health.py`
- Modify: `src/context_search_tool/scanner.py`
- Modify: `src/context_search_tool/manifest.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/graph_lifecycle.py`
- Create: `tests/test_index_health.py`
- Modify: `tests/test_tokenizer_scanner.py`
- Modify: `tests/test_graph_store.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write pure report-model and total-derivation tests first**

  Implement tests from the Task-1 golden values before production classes.
  Cover every health-priority and total-combination row: missing/incompatible/
  stable-corrupt priority; graph stale/unfinished; inventory incomplete;
  workspace delta; ready plus writer/drift; stale plus writer/drift; writer
  unknown; coverage degraded; quick/verified healthy. Require exact
  `queryable`, evidence, refresh kind/reasons/action, canonical sorting, bounded
  samples, and fail-closed embedding fields.

  Before creating `index_health.py` or modifying production, run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 2 \
    --pending .quality/p6-artifacts/tdd-task-2.pending.json \
    -- \
    tests/test_index_health.py \
    tests/test_tokenizer_scanner.py \
    tests/test_graph_store.py
  ```

  Record the exact failing nodes and assertions. Expected RED reasons are the
  absent report types/serializer and missing inventory/error semantics. Import,
  collection, syntax, or malformed-fixture failures do not count as RED.

- [ ] **Step 2: Implement report values and split metadata observation from body reading**

  Add frozen dataclasses/enums and one canonical serializer in
  `index_health.py`. All required keys are emitted. Unknown evidence uses the
  reviewed null rules; consumers never infer evidence from missing keys.

  Refactor the v5 scanner into `observe_workspace()` and
  `read_observed_file()`. Preserve existing include/exclude/gitignore/default-
  directory/language/symlink/root rules. `WorkspaceInventory` owns canonical
  eligible observations, coverage skips, exclusions, `complete`, unscannable
  subtrees, control-file errors, change-token kind, and diagnostics.

  Use `os.walk(..., followlinks=False, onerror=...)`; never silently drop a
  subtree. Treat `.gitignore` and scanner-affecting config as bounded control
  inputs whose read errors make the inventory incomplete. Excluded/pruned/
  unsupported paths contribute only bounded display counts, never the
  freshness fingerprint.

- [ ] **Step 3: Implement stable metadata and safe streaming reads**

  Persist/compare path, regular type, size, `mtime_ns`, best-effort `ctime_ns` or
  platform token, and token kind. The body reader validates path identity and
  metadata before/after the bounded no-follow read, streams SHA-256, and returns
  normalized binary/encoding/oversize/unreadable/changed-during-read outcomes.
  It retains at most one bounded body. Inject mtime-only and platform-specific
  observers for tests; no code claims a metadata tuple proves content.

  Keep compatibility adapters for current `ScannedFile` callers until Task 5.
  Existing scanner tests remain exact while new tests cover traversal errors,
  control errors, lower-bound counts, no inferred deletions, transient skips,
  stable skips, and recovery.

- [ ] **Step 4: Add a mutation-free raw capability probe**

  Before interpreting versioned rows, inspect:

  1. repository root and index existence;
  2. raw manifest JSON schema version through a bounded regular-file read;
  3. raw SQLite operational and graph versions through `mode=ro` URI and only
     `sqlite_master`/known metadata keys;
  4. stable error classes/codes for future/malformed values.

  The probe creates no SQLite file, journal, config, directory, or lock and does
  not read unknown-version tables/columns. Tests monkeypatch `load_config`,
  `read_config`, provider construction, feedback, profile, scanner, and normal
  store APIs to raise, then prove missing and each future schema return first.

- [ ] **Step 5: Add injected quick/verified inspector orchestration**

  Implement the observation algorithm against injected read adapters so Task 2
  can test missing/legacy/future and synthetic current-state snapshots without
  making v2 writable. Quick mode uses two complete metadata inventories, hashes
  only small manifest/descriptor files, performs two short SQLite snapshots,
  and never reads source/vector payloads. Verified mode streams every eligible
  source and exact vector tuple once, runs `PRAGMA quick_check`, and returns
  `verification_interrupted` on drift rather than corruption.

  A stable bound mismatch may derive corrupt; writer activity, generation drift,
  incomplete inventory, or interrupted reads derive unchecked/degraded or stale
  exactly as the design table. Unsupported lock probing yields
  `writer.active=null`, never false idle.

- [ ] **Step 6: Prove read-only and bounded behavior directly**

  Snapshot the complete repository/index tree metadata and bytes before/after
  quick and verified inspection. Monkeypatch every mutator/provider/network
  entry. Require zero changes, no feedback/metric writes, no eligible body read
  in quick mode, one bounded buffer in verified mode, two inventory passes, and
  stable sanitized relative-path diagnostics.

- [ ] **Step 7: Run focused/protected gates and commit**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_index_health.py \
    tests/test_tokenizer_scanner.py \
    tests/test_graph_store.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  ```bash
  git add \
    src/context_search_tool/index_health.py \
    src/context_search_tool/scanner.py \
    src/context_search_tool/manifest.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/graph_lifecycle.py \
    tests/test_index_health.py \
    tests/test_tokenizer_scanner.py \
    tests/test_graph_store.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-2.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-2.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-2.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p6 health inspection core"
  ```

  Public CLI/MCP behavior and all writer versions remain unchanged in Task 2.

### Task 3: Add Internal Manifest V2, Operational V1, And Descriptor V2

**Files:**

- Modify: `src/context_search_tool/index_health.py`
- Modify: `src/context_search_tool/manifest.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/graph_lifecycle.py`
- Modify: `src/context_search_tool/vector_store.py`
- Create: `tests/test_manifest_v2.py`
- Create: `tests/test_p6_operational_store.py`
- Modify: `tests/test_index_health.py`
- Modify: `tests/test_graph_store.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write literal v1/v2/future/corrupt fixture tests first**

  Construct files/databases independently of current constructors. Cover no
  index, manifest v1, valid manifest v2/operational v1/descriptor v2, DDL-only
  interrupted migration, graph stale, future manifest, future operational,
  future graph, malformed versions, missing bindings, wrong digest/size/
  generation, truncated files, symlinks, non-regular files, wrong owner/mode
  where supported, and exact-ID mismatch. Future refusal precedes config and
  unknown-row reads; stable supported-state mismatches are corruption only when
  both SQLite snapshots prove the same bound generation.

  Before modifying production, run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 3 \
    --pending .quality/p6-artifacts/tdd-task-3.pending.json \
    -- \
    tests/test_manifest_v2.py \
    tests/test_p6_operational_store.py \
    tests/test_index_health.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py
  ```

  Record exact RED nodes whose assertions fail because v2 readers/writers,
  operational bindings, or final-ready semantics are absent. Collection/import
  errors and failures of pre-existing v1 cases are not an acceptable RED phase.

- [ ] **Step 2: Implement manifest v1/v2 readers and canonical v2 writer**

  Replace one global schema constant with
  `READABLE_MANIFEST_VERSIONS={1,2}` and `WRITE_MANIFEST_VERSION=2`. Preserve the
  exact v1 adapter/embedding meaning. Manifest v2 includes reviewed config,
  content/observation fingerprints, observation/manifest generations, bound
  descriptor fields, timestamps, operation mode, bounded work metrics, counts,
  and embedding identity. Canonical UTF-8 JSON and its digest are computed
  before publication; no secret-bearing config value is serialized.

  Add closed `IncompatibleManifestSchemaError` and stable corruption errors.
  Reading never downgrades or rewrites. The production indexer still writes v1
  until Task 5.

- [ ] **Step 3: Add additive operational schema v1 primitives**

  Add only the reviewed operational state:

  - source observation change-token/kind/generation columns while reusing
    existing canonical path/language/size/mtime/hash columns;
  - `scan_skips` keyed by path with closed reason, optional metadata, retryable
    flag, first/last observation generation, and last retry generation;
  - operational version and ready metadata for config/content/observation
    fingerprints, observation generation, operation/work summary;
  - exact expected manifest version/generation/digest and descriptor
    schema/generation/digest/vector+ID byte sizes.

  Add typed snapshot reads, deterministic replacement, oldest-first retry
  selection, and bounded physical purge APIs. DDL is additive and not
  authoritative until the final ready transaction binds operational version 1.
  A v1-ready reader ignores unbound new DDL. No method uses `SELECT *` against a
  future operational version.

- [ ] **Step 4: Add descriptor v1/v2 readers and immutable v2 preparation**

  Descriptor v2 retains generation, filenames, SHA-256, row count, dimensions,
  and embedding identity, and adds exact payload/ID byte sizes plus a closed
  normalization invariant (`none|l2`). Readers preserve v1 behavior. Writers
  emit v2 only through new internal preparation methods; the public P5 indexer
  remains on its existing descriptor path until Task 5.

  Quick validation hashes only the small descriptor and checks referenced path,
  regular/non-symlink/owner safety, generation names, and sizes. Verified load
  hashes payload/IDs, validates exact shapes/IDs, and honors the normalization
  invariant. Never infer v2 from filenames alone.

- [ ] **Step 5: Implement one final-ready binding transaction**

  Add a store method that, inside the same final transaction as graph ready:

  - validates supported graph/operational schemas and no unfinished file marker;
  - validates source/skip observation generation and fingerprints;
  - validates active source/chunk/vector counts and exact embedding IDs;
  - invokes the external small-file validator;
  - writes manifest and descriptor bindings, work summary, indexed time, and
    operational version 1;
  - clears stale/full flags and sets ready last.

  The method accepts already-computed frozen values; it performs no workspace
  read. Failure rolls back every ready binding. DDL presence without this commit
  cannot produce a v2-fresh report.

- [ ] **Step 6: Prove migration and crash capability matrices**

  Fault before additive DDL commit leaves exact v1. Fault after DDL but before
  stale leaves the bound v1 snapshot queryable/degraded. Fault after stale
  leaves recoverable stale v2 work. A future schema is never overwritten. A
  synthetic successful final bind produces one reportable valid v2 tuple and a
  second identical inspection. Reader/writer interleavings use rollback journal
  and two SQLite snapshots; generation drift is unchecked, not corrupt.

- [ ] **Step 7: Run focused/protected/full gates and commit**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_manifest_v2.py \
    tests/test_p6_operational_store.py \
    tests/test_index_health.py \
    tests/test_graph_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  ```bash
  git add \
    src/context_search_tool/index_health.py \
    src/context_search_tool/manifest.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/graph_lifecycle.py \
    src/context_search_tool/vector_store.py \
    tests/test_manifest_v2.py \
    tests/test_p6_operational_store.py \
    tests/test_index_health.py \
    tests/test_graph_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-3.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-3.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-3.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p6 snapshot metadata"
  ```

  No public writer emits manifest/operational/descriptor v2 in Task 3.

### Task 4: Activate Read-Only Status And Additive Stats

**Files:**

- Modify: `src/context_search_tool/index_health.py`
- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/cli.py`
- Modify: `src/context_search_tool/mcp_tools.py`
- Modify: `src/context_search_tool/mcp_server.py`
- Modify: `tests/test_index_health.py`
- Modify: `tests/test_cli_commands.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write exact CLI/MCP envelope tests first**

  Use the frozen Task-1 fixtures to require exact success/error fields, order,
  enum/null rules, and messages for:

  - valid root plus missing, manifest v1, v2 ready/stale, future manifest,
    future operational, future graph, stable corrupt, writer/drift, incomplete
    inventory, degraded coverage, metadata healthy, and verified healthy;
  - `StatusEnvelope v1` success for every valid-root index state and only
    `repo_not_found|status_failed` errors;
  - stats' unchanged top-level `ok`, `repo`, `stats`, and indexed `embedding`
    plus one `index_health` sibling on readable success;
  - exact stats errors for missing/future/corrupt/failure;
  - human status exit zero for reportable states and exact nonzero
    `--require verified|metadata|queryable` failures;
  - CLI JSON and MCP status value equality for the same injected snapshot.

  Before modifying production adapters, run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 4 \
    --pending .quality/p6-artifacts/tdd-task-4.pending.json \
    -- \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_mcp_server.py \
    tests/test_index_health.py
  ```

  Record exact RED nodes caused by the absent status surface/shared preflight
  and additive stats fields. Pre-existing CLI/MCP cases must remain green;
  import, collection, and fixture-format failures do not count.

- [ ] **Step 2: Route every public operation through shared raw preflight**

  Add one public-operation capability helper in `index_health.py`. CLI/MCP
  index, query, trace, context, explore, stats, explain, and new status call it
  before config/provider/feedback/profile/scan/work. Existing query-family error
  envelopes remain exact. Only status converts missing/incompatible/corrupt into
  successful reports.

  Refactor `index_repository()` to run the same preflight before using an
  injected config and to load config internally only when no config was passed.
  CLI/MCP index stop calling `load_config()` first. Preserve optional config
  injection for focused tests, but preflight always precedes its use.

  For every missing/future branch, monkeypatch config readers, provider/planner
  factories, feedback, repository profile, scanner, normal SQLite reads, and
  mutators to fail. Snapshot repository/index bytes and require equality.

- [ ] **Step 3: Replace legacy CLI status with the inspector**

  Add `--json`, `--verify`, and closed `--require` options. Human output is a
  concise rendering of the same report and includes health, freshness evidence,
  coverage, graph/integrity, vector coverage evidence, indexed/configured
  embeddings and match, writer state, reasons/action, bounded path samples, and
  metadata limitation. Remove the obsolete checks for `vectors.npy` and
  `vector_ids.json`; generation-qualified v5/v2 state is descriptor-driven.

  JSON emits `StatusEnvelope v1`, not a human-derived second implementation.
  Status resolves a valid root without creating `.context-search`, config,
  `.gitignore`, lock, metrics, or feedback.

- [ ] **Step 4: Make CLI stats additive and inspection-consistent**

  Keep every existing human count/embedding/disk line and meaning. Add
  `--json`/`--verify`; readable JSON retains current count semantics and indexed
  top-level embedding, then adds index schemas, disk components, last-work
  summary, and the exact nested health report. Call the inspector once and
  derive both human/additive stats from its opening committed snapshot where
  possible; do not run a second independent freshness computation.

  Missing/future/corrupt stats remain errors according to the operation matrix,
  not successful status-like responses.

- [ ] **Step 5: Add MCP status and extend MCP stats compatibly**

  Add:

  ```text
  context_search_status(repo: str, verify: bool = false)
  context_search_stats(repo: str, verify: bool = false)
  ```

  Keep existing stats calls valid because `verify` defaults false. Register
  status in `mcp_server.py` with a read-only/no-provider description. Do not add
  health to query/context/trace/explore/explain. Exact server signature/import
  tests and tool-call tests prove one inspection, no mutation, and no source
  content or absolute sampled path in responses.

- [ ] **Step 6: Prove two-snapshot and lock-probe interleavings**

  Pause status after its opening SQLite snapshot, commit a writer, then continue.
  Require the second snapshot to detect generation drift and emit the fixed
  unchecked/degraded or stale result—not healthy/corrupt. Pause with a committed
  stale marker, an unfinished file marker, lock active, and unsupported lock
  probe; compare every axis/action to the total table. Status uses bounded busy
  handling and never waits indefinitely.

- [ ] **Step 7: Run public/protected/full gates and commit**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_index_health.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_mcp_server.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_context_pack.py \
    tests/test_exploration_contracts.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  ```bash
  git add \
    src/context_search_tool/index_health.py \
    src/context_search_tool/indexer.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/mcp_tools.py \
    src/context_search_tool/mcp_server.py \
    tests/test_index_health.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_mcp_server.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-4.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-4.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-4.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: expose p6 index health"
  ```

  Task 4 changes only read-only/public preflight behavior. Public index still
  produces P5 manifest/descriptor v1 and no refresh surface exists.

### Task 5: Make Authoritative Index Observation-Safe And Publish V2

**Files:**

- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/scanner.py`
- Modify: `src/context_search_tool/index_health.py`
- Modify: `src/context_search_tool/manifest.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/graph_lifecycle.py`
- Modify: `src/context_search_tool/vector_store.py`
- Modify: `src/context_search_tool/paths.py`
- Modify: `tests/test_indexer_manifest.py`
- Create: `tests/test_incremental_refresh.py`
- Modify: `tests/test_index_health.py`
- Modify: `tests/test_manifest_v2.py`
- Modify: `tests/test_p6_operational_store.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_config_paths.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write authoritative observation/fence tests first**

  Tests must fail against stale-before-prepare and prove this exact ordering:

  1. acquire the exclusive writer lock and complete schema/reason legality;
  2. capture a complete opening metadata inventory;
  3. stream/hash every eligible source, derive direct/dependent work, and finish
     every required safe read/parse/relation materialization/embedding result;
  4. capture a complete closing metadata inventory and compare all eligible/
     control observations;
  5. record `completed_at` immediately after the passing fence;
  6. only then commit stale and persist frozen facts through final ready.

  A missing config may be initialized only while holding the writer lock and
  before the opening inventory. Freeze the effective scanner/embedding config
  object and its safe hash as part of preparation. Instrument repository source,
  `.gitignore`, current config, and topology controls so any read after
  `stale_committed` raises. Edit an early-observed file later, add a path after
  the scan cursor, alter a control file, inject an unreadable subtree, and
  preserve size/mtime for a content edit. Drift or incomplete inventory must
  leave the prior ready snapshot unchanged; the authoritative hash path must
  detect the adversarial content edit.

  Before modifying production, run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 5 \
    --pending .quality/p6-artifacts/tdd-task-5.pending.json \
    -- \
    tests/test_incremental_refresh.py \
    tests/test_indexer_manifest.py \
    tests/test_manifest_v2.py \
    tests/test_graph_lifecycle.py
  ```

  Record the exact fence/migration nodes that fail because current code marks
  stale before preparation or cannot publish the bound v2 tuple. A failure from
  collection, syntax, or a broken pre-existing P5 assertion is not RED.

- [ ] **Step 2: Refactor preparation before mutation**

  Replace the current scan-and-stale sequence with explicit immutable
  `PreparedIndexSnapshot` data owned by the indexer. It contains canonical
  inventory observations, source/skip replacements, prepared direct/dependent
  file facts, frozen embedding results, project topology, expected vector set,
  fingerprints, the frozen effective config and safe config hash, external
  payload bytes/digests, work counters, and observation interval. It contains no
  open repository file handle and exposes no mutable scanner collection.

  Reuse current parser/chunker/plugin methods. Do not introduce a second graph
  pipeline or refactor parser/ranking code. Current path-inventory, topology,
  stale-on-entry, integrity, and test-association invalidation rules remain
  exact.

- [ ] **Step 3: Make authoritative no-op verified and work-accounted**

  Every authoritative invocation hashes all eligible files and validates the
  exact vector tuple. Equal content with changed metadata updates observations
  without parsing/embedding. A v2 ready/content-equal result may return without
  stale/ready rewrite only after verified integrity and both fences pass. Report
  all source bytes hashed, zero parse/embed for no-op, vector verification work,
  and `freshness=verified_fresh` against the existing ready generation.

- [ ] **Step 4: Implement v1-to-v2 authoritative migration**

  A manifest-v1/graph-v5 index remains queryable until this locked operation.
  Hash all eligible sources, validate/reuse unchanged chunks/graph/embeddings,
  and fully validate the current vector generation. If the ordered vector set is
  unchanged, publish descriptor v2 around the same immutable payload/ID pair;
  do not resend unchanged source or manufacture a new matrix. Use full rebuild
  only for existing P5 schema/config/integrity reasons.

  Additive operational DDL does not become authoritative before stale. A fault
  before stale leaves prior v1 ready. A fault after stale leaves recoverable v2
  work. Future schemas refuse before config/provider/scan/mutation and are never
  overwritten.

- [ ] **Step 5: Publish and bind the exact v2 tuple**

  While stale, persist frozen file/deletion/skip facts and run producer
  resolution, complete test association regeneration, and association
  resolution. Publish/reuse the immutable descriptor, atomically publish only
  manifest v2, reread/validate the manifest/descriptor small identities and
  exact vector tuple, then call the Task-3 final-ready transaction with the same
  frozen observation generation, fingerprints, and config hash. Never publish,
  overwrite, or reread current `config.toml` after the closing fence.

  Add a race that edits config after the closing fence: the writer must not
  overwrite the edit; the completed snapshot remains bound to the frozen hash,
  and the next status reports configuration mismatch. After ready, no code may
  replace or modify the current bound manifest/descriptor/payload/ID artifacts;
  Task 7 may only delete a generation proven unreferenced. The ready transaction
  binds exact manifest generation/digest and descriptor schema/generation/
  digest/sizes, counts, IDs, graph generations, work summary, and indexed time.
  A returned success health report is inspected against that committed
  generation and must be `healthy_verified`.

- [ ] **Step 6: Add complete fault/recovery seams**

  Extend existing P5 fault injection across opening inventory, each safe read,
  dirty/dependent preparation, embedding, closing fence, operational DDL,
  source/skip persistence, vector/manifest v2 preparation/publication, external
  validation, binding, before/after ready commit. Pre-stale failure preserves
  prior ready; post-stale failure is recoverable; acknowledged ready is complete;
  unknown commit result resolves to only complete stale or complete ready.

  Remote-provider tests prove only changed chunks are sent, and exceptions are
  sanitized. Index retains its existing user-facing error shape; no raw endpoint,
  credentials, response body, source, or absolute path escapes.

- [ ] **Step 7: Run lifecycle/protected/full gates and commit**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_indexer_manifest.py \
    tests/test_incremental_refresh.py \
    tests/test_index_health.py \
    tests/test_manifest_v2.py \
    tests/test_p6_operational_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_config_paths.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_p5_protected_direct.py \
    tests/test_retrieval_core_characterization.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  ```bash
  git add \
    src/context_search_tool/indexer.py \
    src/context_search_tool/scanner.py \
    src/context_search_tool/index_health.py \
    src/context_search_tool/manifest.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/graph_lifecycle.py \
    src/context_search_tool/vector_store.py \
    src/context_search_tool/paths.py \
    tests/test_indexer_manifest.py \
    tests/test_incremental_refresh.py \
    tests/test_index_health.py \
    tests/test_manifest_v2.py \
    tests/test_p6_operational_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_config_paths.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-5.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-5.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-5.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: make authoritative index observation safe"
  ```

### Task 6: Build The Complete Internal Quick-Refresh Path

**Files:**

- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/index_health.py`
- Modify: `src/context_search_tool/scanner.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/vector_store.py`
- Modify: `tests/test_incremental_refresh.py`
- Modify: `tests/test_indexer_manifest.py`
- Modify: `tests/test_index_health.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write internal refresh legality and zero-work tests first**

  Invoke one internal `refresh_repository()` seam directly; no CLI/MCP imports
  it yet. Cover missing index, manifest v1, incomplete migration, three future
  schemas, stable corruption, busy writer, embedding identity change, scanner
  config change, retrieval-only config change, topology change, path inventory
  change, stale-on-entry reasons, and valid v2 ready/stale states. Every outcome
  must match the reviewed reason/config matrix.

  A complete no-op with no due retryable skip proves zero body reads/hashes/
  parses/embeddings, zero SQLite replacements, zero vector prepare/publish, zero
  ready rewrite, two metadata inventories, and exact nonzero metadata/SQLite
  counters only.

  Before modifying production, run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 6 \
    --pending .quality/p6-artifacts/tdd-task-6.pending.json \
    -- \
    tests/test_incremental_refresh.py \
    tests/test_indexer_manifest.py \
    tests/test_index_health.py
  ```

  Record exact RED nodes caused by the absent internal refresh entry, legality
  matrix, and zero-work contract. Collection/import failures and unrelated P5
  regressions are invalid RED evidence.

- [ ] **Step 2: Implement direct metadata diff and bounded skip retry**

  Diff opening observations from the last ready generation into added, deleted,
  metadata candidate, coverage change, config change, topology change, and path
  inventory change. Hash only direct dirty candidates and at most 32 oldest-first
  retryable `unreadable|changed_during_read` skips. Equal hashes become
  metadata-only observation updates; stable binary/oversize/unsafe skips remain
  coverage evidence without repeated body reads.

  An incomplete opening/closing inventory returns `inventory_incomplete` or
  `workspace_changed` before stale and preserves every row. No path under an
  unscannable subtree is classified deleted.

- [ ] **Step 3: Compute exact dependent rebuilds**

  Starting from persisted P5 facts, compute:

  - unchanged active `imports|routes_to` sources affected by any path addition/
    deletion, preserving the committed P5 fix transitions;
  - graph-safe full/affected rebuilds for project-unit topology changes;
  - test associations from persisted imports after producer resolution;
  - stale/integrity reasons that must use authoritative index instead of quick
    repair.

  Every rebuilt path has one closed reason. Reverse insertion and filesystem
  order must yield the same canonical set and summary.

- [ ] **Step 4: Freeze all direct/dependent work before the fence**

  Safely read/hash every required direct/dependent path; parse/chunk/materialize
  graph facts; freeze embedding inputs and returned vectors; build the complete
  expected ordered vector set and path/unit context; then run the closing full
  inventory. Provider calls occur before the fence so no workspace-derived work
  remains afterward. A post-provider drift returns `workspace_changed` with
  truthful `network_egress_outcome` and leaves prior ready intact.

  Instrument all workspace/control reads to fail after stale. Persistence and
  resolver/test-association work may consume only SQLite plus the frozen
  snapshot.

- [ ] **Step 5: Reuse the authoritative publication protocol**

  Do not implement a second ready path. Apply the Task-5 stale/persist/resolve/
  external-bind/ready helper with quick evidence and work counts. Dependency-
  only/metadata-only work reuses unchanged embeddings; a new vector generation
  is prepared only when the ordered vector set changes. A successful report is
  `metadata_fresh`, never verified fresh.

- [ ] **Step 6: Freeze `RefreshSummaryV1` work accounting**

  Populate every required files/chunks/inventory/source/path-index/graph/vector/
  maintenance field. Enforce:

  - `payload_passes = prior_payload_passes + prepared_payload_passes`;
  - vector hash bytes are a subset of logical read bytes;
  - `generations_before/after` count payload+ID pairs, not files;
  - embedded chunk count equals refresh embedding disclosure;
  - dependency reason counts sum to dependent rebuild total;
  - no negative/NaN/unbounded diagnostic values.

  Return typed internal success/failure values; public envelopes belong to Task
  7. Provider exceptions carry only sanitized code and egress outcome.

- [ ] **Step 7: Add refresh crash/interleaving tests**

  Inject faults at every direct/dependent read, embedding, closing fence, stale,
  file/skip replacement, resolver, vector/manifest publication, ready binding,
  and post-commit seam. Pause an old reader across stale/ready and prove exact
  old/new committed behavior. Quick retry after any failure must recover or
  return authoritative requirement without manual file deletion.

- [ ] **Step 8: Run focused/protected/full gates and commit**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_incremental_refresh.py \
    tests/test_indexer_manifest.py \
    tests/test_index_health.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_p5_protected_direct.py \
    tests/test_retrieval_core_characterization.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  ```bash
  git add \
    src/context_search_tool/indexer.py \
    src/context_search_tool/index_health.py \
    src/context_search_tool/scanner.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/vector_store.py \
    tests/test_incremental_refresh.py \
    tests/test_indexer_manifest.py \
    tests/test_index_health.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-6.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-6.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-6.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: add p6 incremental refresh core"
  ```

  Public CLI/MCP/query operations cannot invoke refresh in Task 6.

### Task 7: Add Bounded Maintenance And Activate Public Refresh

**Files:**

- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/index_health.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/graph_lifecycle.py`
- Modify: `src/context_search_tool/vector_store.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `src/context_search_tool/cli.py`
- Modify: `src/context_search_tool/mcp_tools.py`
- Modify: `src/context_search_tool/mcp_server.py`
- Modify: `tests/test_incremental_refresh.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_graph_store.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_cli_commands.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write generation cleanup and reader-lifetime tests first**

  Permit cleanup only for the closed rollback-journal set
  `DELETE|TRUNCATE|PERSIST`; `WAL|MEMORY|OFF|unknown` fails closed before any
  unlink. Hold a
  `GraphReadSession` across descriptor selection, payload/ID load or mmap,
  vector search, and result materialization; start a writer and prove the final
  ready commit acts as the barrier. No descriptor, file handle, mmap, ndarray
  view, or store backed by it may escape the session.

  After acknowledged ready and while holding the writer lock, retain exactly
  the descriptor-referenced generation and remove only closed-pattern, regular,
  non-symlink, current-owner unreferenced generation files. Unknown names,
  symlinks, foreign owner/mode, and possibly reader-visible files remain.
  Cleanup failure records bounded diagnostics and ready remains valid. Every
  subsequent writer must, after acquiring the lock and before preparing any new
  generation or committing stale, retry cleanup of already-confirmed orphans.
  If that retry fails, the writer stops before preparation; it may not add a
  third generation.

  Add the exact sequence `G2 ready -> G1 cleanup failure -> next writer starts ->
  retry failure/success -> injected pre/post-prepare fault`. Prove no path can
  leave G1+G2+G3, and cover a v1 migration directory containing multiple
  historical P5 generations. The closed-name, owner/mode, symlink, journal, and
  reader-visibility rules apply to the retry exactly as to first cleanup.

  Before modifying production, run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 7 \
    --pending .quality/p6-artifacts/tdd-task-7.pending.json \
    -- \
    tests/test_incremental_refresh.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py
  ```

  Record exact RED nodes caused by missing cleanup/barrier/public-refresh
  behavior. Existing query and lifecycle protection must stay green; import,
  collection, or malformed-golden failures do not count.

- [ ] **Step 2: Add bounded tombstone maintenance**

  Count active/deleted chunks, signals, relations, orphan symbols/associations,
  pages, and freelist. In the final ready transaction—after the active vector
  identity is known—purge deterministic bounded batches when a table exceeds
  `max(5_000, 5% of active rows)`. Keep FTS/search payloads exact. Reuse pages;
  never run automatic full `VACUUM` on refresh.

  Fault injection leaves ready valid or the operation stale according to commit
  position. The next writer resumes. A 100-step smoke churn ends below thresholds,
  with one generation after success and at most current+one orphan after a
  fault.

- [ ] **Step 3: Freeze public refresh success/error adapters**

  Add `cst refresh [repo] [--json]` and
  `context_search_refresh(repo: str)`. Human output and JSON derive from one
  internal result. Success emits exact `RefreshEnvelope v1`, including indexed
  before/configured embedding identities, actual network egress performed,
  complete work summary, and resulting health.

  Map only the reviewed errors:
  `repo_not_found|missing_index|incompatible_manifest_schema|
  incompatible_operational_schema|incompatible_signal_schema|index_busy|
  authoritative_index_required|inventory_incomplete|workspace_changed|
  refresh_failed`. Every error has required fail-closed egress outcome and no
  partial summary/health sibling.

- [ ] **Step 4: Prove explicit mutation and remote disclosure**

  CLI help, MCP description, and tests state refresh mutates repository index
  and may send only new/content-changed chunk text to a configured remote
  provider. Unknown provider/config is egress-capable. Dependency-only and
  metadata-only refresh send nothing. Simulate not-attempted transport failure,
  possible send, received response followed by fence drift, and later
  persistence failure; require exact egress outcome and sanitized message.

  Query/context/trace/explore never call refresh, even for stale/missing health.
  Add call-count tests and preserve every existing envelope.

- [ ] **Step 5: Run 100-step functional churn and recovery**

  Use the smoke generator's fixed schedule to modify/delete/restore paths,
  trigger retryable coverage, cross maintenance thresholds in a scaled focused
  store, inject one cleanup failure, and sample status/query every ten steps.
  Assert exact freshness transitions, no false deletion, vector IDs, graph
  integrity, bounded tombstones/generations, and unchanged ordered protected
  query results. This is a correctness/work test; Task 11 owns large-tier timing.

- [ ] **Step 6: Run public/lifecycle/protected/full gates and commit**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q \
    tests/test_incremental_refresh.py \
    tests/test_graph_lifecycle.py \
    tests/test_graph_store.py \
    tests/test_embeddings_vector_store.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_mcp_server.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_p5_protected_direct.py \
    tests/test_context_pack.py \
    tests/test_exploration_contracts.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  ```bash
  git add \
    src/context_search_tool/indexer.py \
    src/context_search_tool/index_health.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/graph_lifecycle.py \
    src/context_search_tool/vector_store.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/mcp_tools.py \
    src/context_search_tool/mcp_server.py \
    tests/test_incremental_refresh.py \
    tests/test_graph_lifecycle.py \
    tests/test_graph_store.py \
    tests/test_embeddings_vector_store.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_mcp_server.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-7.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-7.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-7.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "feat: activate p6 incremental refresh"
  ```

### Task 8: Remove Measured Indexing And Path-Context Amplification

**Files:**

- Modify: `src/context_search_tool/graph_plugins.py`
- Modify: `src/context_search_tool/frontend_graph.py`
- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/java_plugin.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/test_association.py`
- Modify: `src/context_search_tool/vector_store.py`
- Modify: `scripts/p6_benchmark.py`
- Modify: `tests/test_incremental_refresh.py`
- Modify: `tests/test_indexer_manifest.py`
- Modify: `tests/test_java_ast.py`
- Modify: `tests/test_frontend_graph.py`
- Modify: `tests/test_test_association.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_p6_benchmark.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Capture post-correctness indexing profiles before optimization**

  Run smoke/large full build, authoritative no-op, no-op refresh, and one-file
  vector/graph edits from observation-consistent ready snapshots. Record
  preparation queue/text/vector peaks, parser/embed batches, inventory work,
  path canonicalization/copy counts, relation resolution, association inputs/
  writes, active/deleted ID work, vector passes, SQLite pages/tombstones, RSS,
  and wall time. Compare to Task-1 entry reports without claiming equivalence for
  previously unsupported status/refresh cases.

  The mandatory known hotspot is per-file repository path/unit reconstruction.
  Any additional optimization in this task must be one of the measured stages
  listed in `Files`, must exceed its budget or dominate the profile, and must
  have an exact before projection. Otherwise record it as retained exact work;
  do not optimize speculatively.

  Run the profile from the clean Task-7 commit and validate it before using a
  measurement to authorize any conditional branch:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-large \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations full-build,authoritative-noop,refresh-noop,refresh-one-file \
    --output .quality/p6-artifacts/task8-before.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/task8-before.json
  ```

  Only a report with valid calibration, sample counts, applicable CV, cold/warm
  state, RSS/work units, clean implementation identity, and privacy may drive
  Step 4/5. One complete rerun is allowed; a second invalid result stops.

  **Measured amendment (2026-07-21):** after removing the mandatory path-index
  amplification, an isolated scale-5k full build remained CPU-bound for
  608.99 s before interruption while peak RSS stayed at 243,924,992 bytes. A
  stack sample and seven-run single-file projection isolated the retained P5
  Java extraction pass: 555.37 ms for one 24,576-byte/320-line generated file,
  versus 0.84 ms for AST graph parsing and 0.59 ms for chunking. The excess is
  `_METHOD_RE`/`_FIELD_RE` backtracking on generated whitespace-only padding.
  This measured budget failure authorizes one exact `java_plugin.py` fast path:
  skip scrubbed lines containing no non-whitespace characters before declaration
  regexes. Freeze equal extraction/graph/index projections with and without the
  padding; no other Java parsing behavior or file is authorized by this amendment.

  The corrected scale-5k build then completed in 256.38 s with 891,879,424-byte
  peak RSS. Its remaining sampled hotspot was an FTS5 full scan caused by
  `replace_chunks()` deleting incoming chunk IDs that were absent from the
  `chunks` primary-key table; a pristine one-chunk trace reproduced one such
  invalid `DELETE FROM chunks_fts`. This measured amplification authorizes one
  `sqlite_store.py` existence filter before incoming search-payload deletion.
  Existing active IDs must still be cleaned exactly once, changed-file FTS/token/
  symbol projections must remain exact, and no transaction/batching redesign is
  authorized unless this filter fails the next scale projection.

  With both measured fixes applied, clean isolated builds completed in 96.11 s
  for scale-5k and 242.52 s for scale-10k, a 2.523x projection ratio within the
  2.7x budget. Maximum RSS was 899,776,512 bytes and 1,663,025,152 bytes,
  respectively, so the 2 GiB batching trigger was not reached.

- [ ] **Step 2: Write shared repository-path-index work proofs first**

  First run existing correctness projections green. Then add only the named work
  assertions and run their RED nodes before modifying production:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_frontend_graph.py \
    tests/test_test_association.py \
    tests/test_p5_graph_contract.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 8 \
    --pending .quality/p6-artifacts/tdd-task-8.pending.json \
    -- \
    tests/test_incremental_refresh.py::test_repository_path_index_built_once_per_operation \
    tests/test_frontend_graph.py::test_frontend_path_context_reuses_one_repository_index \
    tests/test_p6_benchmark.py::test_path_context_work_scales_linearly
  ```

  The second command must fail only on old repeated build/copy/work counts;
  output projections remain green. Collection/import errors or a correctness
  failure do not count as RED.

  Require one canonicalization/build per index/refresh operation regardless of
  rebuilt-file count. Reversed input order produces equal paths, membership, and
  unit lookup. Every `PluginContext` in the operation shares the same immutable
  index identity. Existing positional/direct `PluginContext` constructors and
  P5 parser facts remain compatible.

  Frontend materialization performs zero per-relation full active-path set or
  unit-map construction. Doubling scale-5k to scale-10k keeps context-build
  work/time/RSS ratios within the reviewed 2.4/2.7 boundaries.

- [ ] **Step 3: Implement one immutable `RepositoryPathIndex`**

  Add a frozen object in `graph_plugins.py` containing canonical path tuple,
  membership set, path-to-unit mapping, and deterministic lookup. Build it once
  after the opening inventory and pass it by reference through frozen prepared
  work. `PluginContext` accepts it through a backward-compatible optional field;
  when present, existing `active_paths`, `active_path_project_units`, and
  `project_unit_for_path()` views reuse the precomputed data without re-sorting/
  copying. Direct constructors used by parser tests retain exact behavior.

  Update frontend selector materialization to use membership/unit lookup
  directly. Do not change ambiguity, extension/index ties, target IDs,
  project-unit boundaries, relation metadata, or canonical order.

- [ ] **Step 4: Bound full-build preparation memory only if the profile requires it**

  If full-build RSS exceeds 2 GiB or queued prepared text/vectors are the proven
  dominant allocation, add deterministic **in-memory** bounded parse/embed/
  vector-preparation batches in `indexer.py`/`vector_store.py` while preserving
  prepare-before-fence. Freeze and test maximum queued source bytes, embedding
  text bytes, vector bytes, batch count, and configured batch size; no batch may
  publish or commit graph/source state before the closing fence.

  This plan authorizes no disk spill or new prepared-file class. If bounded
  in-memory batching cannot meet RSS, stop and amend the design/plan with a
  reviewed spill ownership, naming, no-follow, crash-recovery, cleanup, and disk
  contract before writing it. If the profile is within budget, implement no
  batching abstraction and record the measured retained path in Task 11.

- [ ] **Step 5: Optimize resolver/association work only behind exact selectors**

  If full relation resolution or all-file test association is a measured budget
  failure, derive affected selectors/units solely from persisted relation/import
  facts and frozen path/topology deltas. Compare the complete final graph and
  test-association projection to full regeneration under additions, deletions,
  ambiguity transitions, topology changes, stale recovery, and reversed order.
  Any case without a proven complete affected set keeps the current full pass.

  If those stages meet budgets, make no behavioral change; retain their one-pass
  counters and exact full algorithm.

- [ ] **Step 6: Stage, measure from a clean candidate tree, and re-run gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_incremental_refresh.py \
    tests/test_indexer_manifest.py \
    tests/test_frontend_graph.py \
    tests/test_test_association.py \
    tests/test_p6_benchmark.py \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  Stage only explicit Task-8 paths, review them, and create an unreachable
  candidate commit/worktree whose tree exactly equals the staged tree. Run host
  evidence from that clean candidate, never the dirty primary worktree. Execute
  this block and Step 7 in one shell so the all-exit cleanup trap remains armed:

  ```bash
  git add \
    src/context_search_tool/graph_plugins.py \
    src/context_search_tool/frontend_graph.py \
    src/context_search_tool/indexer.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/test_association.py \
    src/context_search_tool/vector_store.py \
    scripts/p6_benchmark.py \
    tests/test_incremental_refresh.py \
    tests/test_indexer_manifest.py \
    tests/test_frontend_graph.py \
    tests/test_test_association.py \
    tests/test_embeddings_vector_store.py \
    tests/test_p6_benchmark.py \
    tests/test_retrieval_core_boundaries.py
  git diff --exit-code -- $(git diff --cached --name-only)
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-8.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-8.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-8.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  export P6_TASK8_TREE="$(git write-tree)"
  export P6_TASK8_CANDIDATE="$(printf '%s\n' 'P6 Task 8 candidate' | \
    git commit-tree "$P6_TASK8_TREE" -p HEAD)"
  export P6_TASK8_TMP="$(mktemp -d "${TMPDIR:-/tmp}/cst-p6-task8.XXXXXX")"
  export P6_TASK8_WORKTREE="$P6_TASK8_TMP/worktree"
  p6_task8_cleanup() {
    if test -e "$P6_TASK8_WORKTREE/.git"; then
      git worktree remove "$P6_TASK8_WORKTREE"
    fi
    if test -d "$P6_TASK8_TMP"; then
      rmdir "$P6_TASK8_TMP"
    fi
  }
  trap p6_task8_cleanup EXIT INT TERM
  git worktree add --detach "$P6_TASK8_WORKTREE" "$P6_TASK8_CANDIDATE"
  test -z "$(git -C "$P6_TASK8_WORKTREE" status --porcelain)"
  test "$(git -C "$P6_TASK8_WORKTREE" rev-parse HEAD^{tree})" = "$P6_TASK8_TREE"
  PYTHONPATH="$P6_TASK8_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK8_WORKTREE/scripts/p6_benchmark.py" run \
    --repo "$PWD/.quality/p6-scale-5k" \
    --manifest "$P6_TASK8_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
    --operations full-build,authoritative-noop,refresh-noop,refresh-one-file \
    --output "$PWD/.quality/p6-artifacts/task8-scale-5k.json"
  PYTHONPATH="$P6_TASK8_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK8_WORKTREE/scripts/p6_benchmark.py" run \
    --repo "$PWD/.quality/p6-scale-10k" \
    --manifest "$P6_TASK8_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
    --operations full-build,authoritative-noop,refresh-noop,refresh-one-file \
    --output "$PWD/.quality/p6-artifacts/task8-scale-10k.json"
  PYTHONPATH="$P6_TASK8_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK8_WORKTREE/scripts/p6_benchmark.py" validate \
    --report "$PWD/.quality/p6-artifacts/task8-scale-5k.json"
  PYTHONPATH="$P6_TASK8_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK8_WORKTREE/scripts/p6_benchmark.py" validate \
    --report "$PWD/.quality/p6-artifacts/task8-scale-10k.json"
  ```

  Both reports must meet calibration/sample/CV/state/RSS/work/privacy validity
  and bind `P6_TASK8_CANDIDATE` plus `P6_TASK8_TREE`. One complete rerun is
  allowed; a second invalid session stops. Exact P5 graph projections, embedding
  inputs, vector IDs, and refresh equations must match before/after; a changing
  optimization is reverted, not baselined.

- [ ] **Step 7: Commit the already-staged measured tree**

  ```bash
  git commit -m "perf: optimize p6 indexing paths"
  test "$(git rev-parse HEAD^{tree})" = "$P6_TASK8_TREE"
  test -z "$(git status --porcelain -- $(git show --pretty='' --name-only HEAD))"
  p6_task8_cleanup
  trap - EXIT INT TERM
  ```

  Omit unchanged optional paths from staging. The commit must at least contain
  the measured `RepositoryPathIndex` change and its work/correctness tests.

### Task 9: Optimize Measured Exact SQLite And Repository Query Paths

**Files:**

- Modify: `src/context_search_tool/retrieval.py`
- Modify: `src/context_search_tool/repo_profile.py`
- Modify: `src/context_search_tool/retrieval_core/candidates.py`
- Modify: `src/context_search_tool/path_roles.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `scripts/p6_benchmark.py`
- Modify: `tests/test_repo_profile.py`
- Modify: `tests/test_sqlite_store.py`
- Modify: `tests/test_direct_text_evidence.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_retrieval_core_characterization.py`
- Modify: `tests/test_p6_benchmark.py`
- Modify: `tests/test_p6_measurement_worker.py`
- Modify: `tests/test_path_roles.py`
- Modify: `tests/test_retrieval_core_boundaries.py`
- Modify: `tests/test_exploration_boundaries.py`
- Create: `tests/test_sqlite_store_query_work.py`

- [ ] **Step 1: Profile every exact candidate source independently**

  For every frozen query case, record end-to-end and separate repo-profile,
  active/deleted-ID, lexical FTS, exact token, path/symbol, direct-text, signal,
  planner-hint, and graph-expansion stage timings plus SQL VM steps, calls,
  decoded rows/bytes, and output rows. Instrumented and uninstrumented runs must
  return identical ordered candidates/scores.

  Keep per-case samples separate. `EXPLAIN QUERY PLAN` is supporting evidence,
  not a visited-row proof. Baseline the current full scans visibly before each
  change.

  Run and validate the clean Task-8 commit before changing tests or production:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-large \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations query-cold,query-warm,explore-warm \
    --output .quality/p6-artifacts/task9-before.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/task9-before.json
  ```

  Only valid calibration/sample/CV/state/RSS/work/privacy evidence may identify
  a source for optimization. One complete rerun is allowed; a second invalid
  profile stops instead of authorizing a rewrite.

  **Measured amendment (2026-07-21):** isolated smoke-tier attribution on the
  clean Task-8 commit measured ordinary query wall times of 1.94--2.20 s. A
  representative query spent 129 ms in query understanding while the disabled
  planner's unused repository profile performed 1,349,996 SQLite VM steps and
  decoded 321 rows. Path/symbol recall decoded 92,000 rows (about 80,000 from an
  unconditional `chunk_tokens` scan), direct text made one 4,000-row/
  25,537,824-byte active-content pass, and signal recall decoded 11,000 legal
  recallable rows. This authorizes only the mandatory disabled-profile skip and
  an indexed equality seek for the exact-token component of path/symbol recall;
  the already-bounded direct-text and recallable-signal scans remain unchanged.

  Three cases also exposed a measurement-only identity bug: the product logger's
  host-dependent `direct_text_search slow: <elapsed>ms` line was included in the
  timing/attribution output digest. Two ordinary runs produced different hashes
  while attribution was stable. Task 9 therefore also authorizes canonicalizing
  only that diagnostic duration in `_measurement_output_bytes`; probe/chunk
  counts and all product output remain hashed. Freeze this repair separately in
  `tests/test_p6_measurement_worker.py` before changing the harness.

  Post-change stage profiling then isolated the retained dominant query cost:
  92 Java path-role classifications spent about 0.9 s in normal execution (and
  6.7 s under call profiling) performing roughly 33 million `isspace()` calls
  across generated whitespace padding. `_JAVA_DECLARATION_BOUNDARY_RE` treated
  every whitespace-only line as a declaration candidate, so each candidate
  rescanned the remaining padding. This authorizes one lookahead requiring an
  annotation/identifier start at a boundary. Freeze identical compact/padded
  role projections and linear skipped-character work; no role precedence or
  declaration grammar change is authorized.

  A subsequent 10k-file ready-snapshot query measured 10.64 s end to end:
  signal recall took 1.95 s, ranking 2.15 s, and relation expansion 2.13 s.
  Inspection showed that every decoded result chunk independently queried the
  unindexed `chunk_tokens.chunk_id` column, repeatedly scanning the full token
  table, while signal recall decoded every legal row before matching. Java role
  classification also masked the full body even when no record, enum, or data
  annotation marker existed. This authorizes one non-persistent batched payload
  read per chunk set, a conservative ASCII SQL prefilter with an exact fallback
  for unsafe tokens/rows, and a marker-absence fast path before Java masking.
  Ordered chunks, tokens, symbols, signal scores/ties, Unicode behavior, and all
  protected output projections remain byte-identical. On the same 10k snapshot,
  the resulting query measured 1.78 s end to end: signal recall was 0.14 s,
  ranking 0.09 s, and relation expansion 0.08 s.

- [ ] **Step 2: Skip unused repository profiles with a protective test**

  Run current candidate/output projections green, add only the new work tests,
  then run these RED nodes before production changes:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_repo_profile.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 9 \
    --pending .quality/p6-artifacts/tdd-task-9.pending.json \
    -- \
    tests/test_retrieval_pipeline.py::test_planner_disabled_skips_repository_profile \
    tests/test_sqlite_store.py::test_exact_candidate_sources_meet_work_contracts \
    tests/test_p6_benchmark.py::test_query_work_contract_rejects_full_scan_amplification
  ```

  The RED command must fail on old profile/query counts only; ordered candidates
  and protected outputs stay green. Collection/import or unrelated correctness
  failure is not valid RED evidence.

  When no planner is injected and configured planner is disabled, call the
  disabled planner with `repo_profile=None` and perform zero language/file/
  symbol/token profile queries. When planner is enabled or injected, preserve
  the exact current profile, prompt payload, sanitization, hashes, variants, and
  traces. This is mandatory even if current latency meets budget because the
  work is provably unused.

- [ ] **Step 3: Enforce the allowed exact scan contracts**

  Implement only profile-justified changes:

  - lexical FTS remains indexed and bounded;
  - exact token uses equality seeks and decodes only matches;
  - path/symbol substring scans at most normalized active path/symbol columns,
    never token tables or chunk bodies;
  - direct text performs at most one active text-byte pass per distinct
    normalized probe set and reuses planner overlap;
  - signal scans only recallable normalized fields/metadata and excludes
    non-recallable rows in SQL;
  - planner hints reuse overlapping normalized source results;
  - active/deleted ID work is generation-bound and cannot grow with purged
    tombstones.

  Feature-detected FTS trigram or another SQLite extension must retain an exact
  fallback and cannot become required across supported builds. No source may
  add a new persistent search surface or disk artifact in this task. If the
  reviewed exact scans cannot meet budgets, stop for a measured design/plan
  amendment with its own portability and disk budget; the ANN-only 1.5x
  allowance does not apply to SQLite.

- [ ] **Step 4: Preserve exact CJK, substring, score, and tie behavior**

  Compare every candidate source to the Task-1 baseline across high/low/zero
  selectivity, CJK sequences, case, path separators, symbol/member names,
  metadata, deleted rows, duplicates, planner overlap, and deterministic ties.
  Final result, reason, follow-up keyword, ContextPack, trace, and exploration
  projections remain exact. Any unavoidable numeric change requires a reviewed
  tolerance amendment; this task assumes none.

- [ ] **Step 5: Replace the host-sensitive direct-text unit assertion**

  Keep deterministic row/byte/pass/correctness assertions in normal CI. Move
  the current 100-ms host assertion into the P6 benchmark profile or remove only
  that wall-clock condition after the acceptance harness owns it. Do not weaken
  direct-text evidence tests.

- [ ] **Step 6: Stage, measure the clean candidate, and run protected gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_repo_profile.py \
    tests/test_sqlite_store.py \
    tests/test_direct_text_evidence.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_p6_benchmark.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_context_pack.py \
    tests/test_exploration_contracts.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  Stage exactly the Task-9 boundary and measure an unreachable clean candidate
  with the same tree as the staging area. Execute this block and Step 7 in one
  shell so the all-exit cleanup trap remains armed:

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/repo_profile.py \
    src/context_search_tool/retrieval_core/candidates.py \
    src/context_search_tool/sqlite_store.py \
    scripts/p6_benchmark.py \
    tests/test_repo_profile.py \
    tests/test_sqlite_store.py \
    tests/test_direct_text_evidence.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_p6_benchmark.py \
    tests/test_retrieval_core_boundaries.py
  git diff --exit-code -- $(git diff --cached --name-only)
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-9.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-9.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-9.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  export P6_TASK9_TREE="$(git write-tree)"
  export P6_TASK9_CANDIDATE="$(printf '%s\n' 'P6 Task 9 candidate' | \
    git commit-tree "$P6_TASK9_TREE" -p HEAD)"
  export P6_TASK9_TMP="$(mktemp -d "${TMPDIR:-/tmp}/cst-p6-task9.XXXXXX")"
  export P6_TASK9_WORKTREE="$P6_TASK9_TMP/worktree"
  p6_task9_cleanup() {
    if test -e "$P6_TASK9_WORKTREE/.git"; then
      git worktree remove "$P6_TASK9_WORKTREE"
    fi
    if test -d "$P6_TASK9_TMP"; then
      rmdir "$P6_TASK9_TMP"
    fi
  }
  trap p6_task9_cleanup EXIT INT TERM
  git worktree add --detach "$P6_TASK9_WORKTREE" "$P6_TASK9_CANDIDATE"
  test -z "$(git -C "$P6_TASK9_WORKTREE" status --porcelain)"
  test "$(git -C "$P6_TASK9_WORKTREE" rev-parse HEAD^{tree})" = "$P6_TASK9_TREE"
  PYTHONPATH="$P6_TASK9_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK9_WORKTREE/scripts/p6_benchmark.py" run \
    --repo "$PWD/.quality/p6-large" \
    --manifest "$P6_TASK9_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
    --operations query-cold,query-warm,explore-warm \
    --output "$PWD/.quality/p6-artifacts/task9-query.json"
  PYTHONPATH="$P6_TASK9_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK9_WORKTREE/scripts/p6_benchmark.py" validate \
    --report "$PWD/.quality/p6-artifacts/task9-query.json"
  ```

  The valid report binds `P6_TASK9_CANDIDATE`/`P6_TASK9_TREE`, required samples,
  calibration, CV, states, RSS, work, and privacy. One rerun is allowed. Require
  every frozen query case to pass work and output gates; family averages cannot
  hide a failing case.

- [ ] **Step 7: Commit the already-staged exact measured tree**

  ```bash
  git commit -m "perf: optimize p6 exact recall"
  test "$(git rev-parse HEAD^{tree})" = "$P6_TASK9_TREE"
  test -z "$(git status --porcelain -- $(git show --pretty='' --name-only HEAD))"
  p6_task9_cleanup
  trap - EXIT INT TERM
  ```

  Omit any unchanged optional source from staging. If exact SQLite paths cannot
  meet budgets within the reviewed scan contracts, stop and amend the plan with
  the measured new search surface; do not improvise one here.

### Task 10: Optimize Exact Vector Load/Search And Record The ANN Decision

**Files:**

- Modify: `src/context_search_tool/vector_store.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `src/context_search_tool/retrieval_core/candidates.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/graph_lifecycle.py`
- Modify: `scripts/p6_benchmark.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_retrieval_core_characterization.py`
- Modify: `tests/test_p6_benchmark.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Freeze exhaustive exact-vector reference cases first**

  Cover empty, one row, random matrices, multiple variants, deleted IDs,
  duplicate/equal scores, ties spanning `top_k`, all-zero rows/query, NaN/Inf
  sanitization, v1 non-normalized and v2 normalized descriptors, wrong
  dimensions/counts/sizes/IDs, descriptor drift, and every supported platform
  load path. The reference result is exact full-score sort by
  `(-finite_score, chunk_id)`; optimized output and float values must match.

  First profile and validate the clean Task-9 commit, then run all existing
  vector/output references green. After adding only the new invariant/work
  assertions, run the named RED nodes before production changes:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-large \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations query-cold,query-warm,explore-warm \
    --output .quality/p6-artifacts/task10-before.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/task10-before.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_embeddings_vector_store.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-red \
    --task 10 \
    --pending .quality/p6-artifacts/tdd-task-10.pending.json \
    -- \
    tests/test_embeddings_vector_store.py::test_exact_top_k_avoids_full_score_sort \
    tests/test_embeddings_vector_store.py::test_ready_query_uses_bound_small_identity \
    tests/test_p6_benchmark.py::test_vector_work_contract_requires_one_score_pass
  ```

  The profile must satisfy calibration/sample/CV/state/RSS/work/privacy
  validity; one rerun is allowed and a second invalid result stops. RED nodes
  fail only on old payload-hash/normalization/full-sort work; all output
  references remain green. Collection/import or correctness failure is invalid
  RED evidence.

- [ ] **Step 2: Replace repeated payload hashing with the reviewed ready invariant**

  A ready query reads the expected descriptor generation/digest/sizes from its
  `GraphReadSession`, hashes the small descriptor, validates regular immutable
  generation names/files/sizes, and uses only a generation whose full hashes and
  exact IDs were verified before the bound ready commit. Cache only the
  generation's verified small identity/stat facts when safe; no file handle,
  mmap, ndarray view, or SQLite snapshot escapes a read session. Verified
  status/authoritative index still stream cryptographic payload hashes.

  Internal writers never modify a generation in place, descriptor publication
  is atomic, and cleanup cannot remove the session-visible generation. Any load,
  shape, descriptor, or SQLite binding mismatch fails closed according to
  ready/stale rules. Same-size adversarial payload tampering remains explicitly
  a quick-evidence limitation detected by verified inspection; no stronger claim
  is made.

- [ ] **Step 3: Publish normalized v2 vectors and use bounded mmap loads**

  Normalize finite vectors once during v2 preparation and record
  `normalization=l2`. Query sanitizes/normalizes only the query vector. Use
  `mmap_mode="r"` when platform/lifecycle tests prove safe; v1/`none` retains the
  exact fallback. Keep mapping lifetime inside `GraphReadSession` and report
  logical payload passes independent of page-cache behavior.

- [ ] **Step 4: Implement deterministic partial top-k**

  Score one matrix pass, apply deleted mask before selection, find the kth finite
  score threshold without sorting all rows, keep all rows above it, choose the
  lexicographically smallest chunk IDs among boundary-equal rows to fill the
  remainder, and sort only the final set by `(-score, chunk_id)`. CI counters
  require one score pass, one normalization invariant check, and zero full-score
  sort.

  Multiple query variants may reuse the loaded/normalized generation inside one
  session but still score once per variant. Do not cache query vectors or change
  semantic candidate merge/ranking.

- [ ] **Step 5: Measure exact-vector final performance and apply the ANN trigger**

  Run at least 30 same-case resident-warm samples and record semantic stage,
  end-to-end, RSS, load/hash/pass, scored/sorted rows, and calibration. ANN is
  considered only if semantic p95 remains above 300 ms or RSS exceeds budget,
  and paired median `semantic_stage_ms/end_to_end_ms >= 40%` or vectors dominate
  excess RSS.

  If not crossed, write a local validated decision `exact search retained`. If
  crossed, stop P6 implementation and request a design/plan amendment for an ANN
  prototype. Do not add a dependency, index format, migration, or approximate
  code in this task.

- [ ] **Step 6: Stage and measure the clean vector candidate**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_embeddings_vector_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_p6_benchmark.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_context_pack.py \
    tests/test_exploration_contracts.py
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  Stage exactly the Task-10 boundary, create an unreachable clean candidate with
  the identical tree, and run the performance/decision evidence there. Execute
  this block and Step 7 in one shell so the all-exit cleanup trap remains armed:

  ```bash
  git add \
    src/context_search_tool/vector_store.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/candidates.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/graph_lifecycle.py \
    scripts/p6_benchmark.py \
    tests/test_embeddings_vector_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_p6_benchmark.py \
    tests/test_retrieval_core_boundaries.py
  git diff --exit-code -- $(git diff --cached --name-only)
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py tdd-green \
    --pending .quality/p6-artifacts/tdd-task-10.pending.json \
    --staged-tree "$(git write-tree)" \
    --output .quality/p6-artifacts/tdd-task-10.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/tdd-task-10.json \
    --staged-tree "$(git write-tree)"
  git diff --cached --check
  git diff --cached --name-only
  export P6_TASK10_TREE="$(git write-tree)"
  export P6_TASK10_CANDIDATE="$(printf '%s\n' 'P6 Task 10 candidate' | \
    git commit-tree "$P6_TASK10_TREE" -p HEAD)"
  export P6_TASK10_TMP="$(mktemp -d "${TMPDIR:-/tmp}/cst-p6-task10.XXXXXX")"
  export P6_TASK10_WORKTREE="$P6_TASK10_TMP/worktree"
  p6_task10_cleanup() {
    if test -e "$P6_TASK10_WORKTREE/.git"; then
      git worktree remove "$P6_TASK10_WORKTREE"
    fi
    if test -d "$P6_TASK10_TMP"; then
      rmdir "$P6_TASK10_TMP"
    fi
  }
  trap p6_task10_cleanup EXIT INT TERM
  git worktree add --detach "$P6_TASK10_WORKTREE" "$P6_TASK10_CANDIDATE"
  test -z "$(git -C "$P6_TASK10_WORKTREE" status --porcelain)"
  test "$(git -C "$P6_TASK10_WORKTREE" rev-parse HEAD^{tree})" = "$P6_TASK10_TREE"
  PYTHONPATH="$P6_TASK10_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK10_WORKTREE/scripts/p6_benchmark.py" run \
    --repo "$PWD/.quality/p6-large" \
    --manifest "$P6_TASK10_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
    --operations query-cold,query-warm,explore-warm \
    --output "$PWD/.quality/p6-artifacts/task10-vector.json"
  PYTHONPATH="$P6_TASK10_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK10_WORKTREE/scripts/p6_benchmark.py" validate \
    --report "$PWD/.quality/p6-artifacts/task10-vector.json"
  PYTHONPATH="$P6_TASK10_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK10_WORKTREE/scripts/p6_benchmark.py" decide \
    --kind ann \
    --report "$PWD/.quality/p6-artifacts/task10-vector.json" \
    --output "$PWD/.quality/p6-artifacts/task10-ann.json"
  PYTHONPATH="$P6_TASK10_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_TASK10_WORKTREE/scripts/p6_benchmark.py" validate \
    --report "$PWD/.quality/p6-artifacts/task10-ann.json"
  ```

  Both reports bind `P6_TASK10_CANDIDATE`/`P6_TASK10_TREE` and pass required
  sample, calibration, CV, state, RSS/work, and privacy rules. One rerun is
  allowed. `exact search retained` permits Step 7; a crossed ANN trigger stops
  without committing this candidate and requires a reviewed amendment.

- [ ] **Step 7: Commit the already-staged exact vector tree only**

  ```bash
  git commit -m "perf: optimize p6 exact vector search"
  test "$(git rev-parse HEAD^{tree})" = "$P6_TASK10_TREE"
  test -z "$(git status --porcelain -- $(git show --pretty='' --name-only HEAD))"
  p6_task10_cleanup
  trap - EXIT INT TERM
  ```

### Task 11: Run Final Acceptance And Record P6 Completion

**Files:**

- Create: `docs/benchmarks/p6/final/final-environment.json`
- Create: `docs/benchmarks/p6/final/final-matrix.json`
- Create: `docs/benchmarks/p6/final/final-smoke.json`
- Create: `docs/benchmarks/p6/final/final-large.json`
- Create: `docs/benchmarks/p6/final/final-scale-5k.json`
- Create: `docs/benchmarks/p6/final/final-scale-10k.json`
- Create: `docs/benchmarks/p6/final/final-stress.json`
- Create: `docs/benchmarks/p6/final/final-performance.json`
- Create: `docs/benchmarks/p6/final/churn.json`
- Create: `docs/benchmarks/p6/final/quality.json`
- Create: `docs/benchmarks/p6/decisions/ann.json`
- Create: `docs/benchmarks/p6/decisions/service-watch.json`
- Modify: `docs/benchmarks/p6/README.md`
- Modify: `README.md`
- Modify: `docs/retrieval-quality.md`
- Modify: `docs/superpowers/specs/2026-07-18-p6-freshness-performance-large-repositories-design.md`
- Modify: this plan
- Modify: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

- [ ] **Step 1: Freeze the final implementation identity and clean host session**

  Before editing documentation/artifacts, require a clean production/test/
  scripts/workflow tree and freeze the Task-10 commit as
  `P6_FINAL_IMPLEMENTATION_COMMIT`. Record its production tree, ordered Task
  1-10 lineage, dependency lock/freeze, Python/SQLite/NumPy versions, OS/CPU/RAM/
  disk/power state, and no swap growth/background overload:

  ```bash
  test -z "$(git status --porcelain -- \
    src tests scripts .github/workflows/p6-functional-matrix.yml)"
  export P6_FINAL_IMPLEMENTATION_COMMIT="$(git rev-parse HEAD)"
  export P6_FINAL_PRODUCTION_TREE="$(git rev-parse \
    "$P6_FINAL_IMPLEMENTATION_COMMIT:src/context_search_tool")"
  git log --reverse --format='%H %s' \
    "$P6_ENTRY_COMMIT..$P6_FINAL_IMPLEMENTATION_COMMIT" \
    > .quality/p6-artifacts/final-lineage.txt
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -c \
    'import json, platform, sqlite3, sys; print(json.dumps({"python": sys.version, "sqlite": sqlite3.sqlite_version, "platform": platform.platform(), "machine": platform.machine()}, sort_keys=True))' \
    > .quality/p6-artifacts/final-runtime.json
  "$P6_RUNTIME" -m pip freeze \
    > .quality/p6-artifacts/final-dependencies.txt
  ```

  Run the 512-MiB SHA-256, fixed 80k-by-384 NumPy dot, and fixed SQLite
  calibration; each must be within 10% of Task-1 baseline or the session is
  invalid.

  The Python/OS functional matrix is executable evidence, not prose. After
  separate user authorization for remote tag publication/CI, push one unique
  acceptance tag pointing at the exact final implementation commit. The Task-1
  tag-push workflow exists in that commit, so it does not depend on prior
  default-branch installation:

  ```bash
  export P6_EVIDENCE_ID="p6-acceptance-$P6_FINAL_IMPLEMENTATION_COMMIT"
  test -z "$(git tag --list "$P6_EVIDENCE_ID")"
  test -z "$(git ls-remote --tags origin "refs/tags/$P6_EVIDENCE_ID")"
  git tag "$P6_EVIDENCE_ID" "$P6_FINAL_IMPLEMENTATION_COMMIT"
  git push origin "refs/tags/$P6_EVIDENCE_ID:refs/tags/$P6_EVIDENCE_ID"

  p6_matrix_attempt=0
  P6_MATRIX_MATCHES=
  P6_MATRIX_MATCH_COUNT=0
  while test "$p6_matrix_attempt" -lt 12; do
    p6_matrix_attempt=$((p6_matrix_attempt + 1))
    P6_MATRIX_MATCHES="$(gh run list \
      --workflow p6-functional-matrix.yml \
      --commit "$P6_FINAL_IMPLEMENTATION_COMMIT" \
      --event push \
      --limit 20 \
      --json databaseId,displayTitle,headSha,event \
      --jq ".[] | select(.displayTitle == \"P6 evidence $P6_EVIDENCE_ID\" and .headSha == \"$P6_FINAL_IMPLEMENTATION_COMMIT\" and .event == \"push\") | .databaseId")"
    P6_MATRIX_MATCH_COUNT="$(printf '%s\n' "$P6_MATRIX_MATCHES" | \
      sed '/^$/d' | wc -l | tr -d ' ')"
    if test "$P6_MATRIX_MATCH_COUNT" -eq 1; then
      break
    fi
    if test "$P6_MATRIX_MATCH_COUNT" -gt 1; then
      exit 1
    fi
    sleep 5
  done
  test "$P6_MATRIX_MATCH_COUNT" -eq 1
  export P6_MATRIX_RUN_ID="$(printf '%s\n' "$P6_MATRIX_MATCHES" | \
    sed '/^$/d')"
  gh run watch "$P6_MATRIX_RUN_ID" --exit-status
  test "$(gh run view "$P6_MATRIX_RUN_ID" --json headSha --jq .headSha)" = \
    "$P6_FINAL_IMPLEMENTATION_COMMIT"
  test "$(gh run view "$P6_MATRIX_RUN_ID" --json displayTitle --jq .displayTitle)" = \
    "P6 evidence $P6_EVIDENCE_ID"
  test "$(gh run view "$P6_MATRIX_RUN_ID" --json event --jq .event)" = push
  gh run download "$P6_MATRIX_RUN_ID" \
    --dir .quality/p6-artifacts/final-matrix-cells
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind matrix \
    --evidence-id "$P6_EVIDENCE_ID" \
    --input-dir .quality/p6-artifacts/final-matrix-cells \
    --output .quality/p6-artifacts/final-matrix.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-matrix.json
  ```

  The matrix must contain exactly 12 successful cells:
  Ubuntu/macOS/Windows crossed with Python 3.11-3.14, with exact workflow/hash/
  dependency/test/skip/xfail/JUnit identities, and the same unique evidence ID.
  If tag publication/CI is not authorized, the tag already exists, the run
  identity is ambiguous, or any supported cell is unavailable/fails, stop Task
  11; do not claim the matrix from the local Python 3.13 run.

- [ ] **Step 2: Produce all final smoke/large/scale/stress/churn reports**

  Generate observation-consistent repositories from the exact frozen manifest.
  For one-file samples, restore or rebuild a ready baseline against each clone's
  current metadata outside the timed interval; byte-identical copying alone is
  insufficient. Produce every raw input and the combined report explicitly:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier smoke --output .quality/p6-final-smoke
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier smoke --output .quality/p6-final-small-paired
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier large --output .quality/p6-final-large
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier scale-5k --output .quality/p6-final-scale-5k
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier scale-10k --output .quality/p6-final-scale-10k
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py generate \
    --tier stress --output .quality/p6-final-stress

  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-final-smoke \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations all-smoke \
    --output .quality/p6-artifacts/final-smoke.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-final-large \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations all-large \
    --output .quality/p6-artifacts/final-large.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-final-scale-5k \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations all-scale \
    --output .quality/p6-artifacts/final-scale-5k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-final-scale-10k \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations all-scale \
    --output .quality/p6-artifacts/final-scale-10k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-final-stress \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations capacity-informational \
    --output .quality/p6-artifacts/final-stress.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py run \
    --repo .quality/p6-final-smoke \
    --manifest tests/fixtures/p6_performance/workload_manifest.json \
    --operations churn-100 \
    --output .quality/p6-artifacts/final-churn.json
  ```

  Produce the protected <=10% comparison in one host session with one final
  harness and two clean implementation worktrees. The entry side is never
  measured with its historical Task-1 harness:

  ```bash
  export P6_COMPARE_TMP="$(mktemp -d \
    "${TMPDIR:-/tmp}/cst-p6-final-compare.XXXXXX")"
  export P6_ENTRY_WORKTREE="$P6_COMPARE_TMP/entry"
  export P6_FINAL_WORKTREE="$P6_COMPARE_TMP/final"
  p6_final_pair_cleanup() {
    if test -e "$P6_ENTRY_WORKTREE/.git"; then
      git worktree remove "$P6_ENTRY_WORKTREE"
    fi
    if test -e "$P6_FINAL_WORKTREE/.git"; then
      git worktree remove "$P6_FINAL_WORKTREE"
    fi
    if test -d "$P6_COMPARE_TMP"; then
      rmdir "$P6_COMPARE_TMP"
    fi
  }
  trap p6_final_pair_cleanup EXIT INT TERM
  git worktree add --detach "$P6_ENTRY_WORKTREE" "$P6_ENTRY_COMMIT"
  git worktree add --detach \
    "$P6_FINAL_WORKTREE" "$P6_FINAL_IMPLEMENTATION_COMMIT"
  test -z "$(git -C "$P6_ENTRY_WORKTREE" status --porcelain)"
  test -z "$(git -C "$P6_FINAL_WORKTREE" status --porcelain)"
  PYTHONPATH="$P6_FINAL_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_FINAL_WORKTREE/scripts/p6_benchmark.py" paired \
    --baseline-root "$P6_ENTRY_WORKTREE" \
    --final-root "$P6_FINAL_WORKTREE" \
    --repo "$PWD/.quality/p6-final-small-paired" \
    --manifest "$P6_FINAL_WORKTREE/tests/fixtures/p6_performance/workload_manifest.json" \
    --operation-set protected_small_entry_comparable \
    --pairs 30 \
    --output "$PWD/.quality/p6-artifacts/final-small-paired.json"
  PYTHONPATH="$P6_FINAL_WORKTREE/src" "$P6_RUNTIME" \
    "$P6_FINAL_WORKTREE/scripts/p6_benchmark.py" validate \
    --report "$PWD/.quality/p6-artifacts/final-small-paired.json"
  p6_final_pair_cleanup
  trap - EXIT INT TERM
  ```

  The paired report records pair IDs, alternating execution order, identical
  pristine repository fingerprint equal to the frozen workload manifest,
  entry/final commits and production trees, one harness hash, both calibrations,
  raw samples, and exact protected operation/case IDs. For every pair, the
  harness makes two independent clones from that pristine root and builds each
  clone's observation-consistent ready index outside the timed interval; no
  mutation or ready state carries between pairs. Validation checks the frozen
  fingerprint, not merely equality between the two sides. Assemble and validate
  all raw inputs:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind performance \
    --mode final \
    --input .quality/p6-artifacts/final-smoke.json \
    --input .quality/p6-artifacts/final-large.json \
    --input .quality/p6-artifacts/final-scale-5k.json \
    --input .quality/p6-artifacts/final-scale-10k.json \
    --input .quality/p6-artifacts/final-stress.json \
    --input .quality/p6-artifacts/final-small-paired.json \
    --input .quality/p6-artifacts/final-churn.json \
    --output .quality/p6-artifacts/final-performance.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-smoke.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-large.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-scale-5k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-scale-10k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-stress.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-churn.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-performance.json
  ```

  Run all required samples and enforce:

  | operation | required final gate |
  | --- | --- |
  | initial large authoritative build | 5 samples, median <=300 s, max <=420 s, peak RSS <=2 GiB, ready disk <=2.5 GiB |
  | authoritative no-op | 5 samples, median <=15 s, max <=25 s, extra RSS <=512 MiB, all 512 MiB hashed, zero parse/embed |
  | quick status | 20 samples, p95 <=2.0 s, extra RSS <=256 MiB, zero eligible body/vector payload bytes |
  | verified status | 5 samples, source hash median >=75 MiB/s, max <=12 s, extra RSS <=256 MiB |
  | no-op refresh | 20 samples, p95 <=2.5 s, all zero-work counters exact |
  | one-file refresh | 20 paired samples, p95 <=5.0 s, declared fan-out, extra RSS <= vector payload x2.2 +256 MiB, vector read/write <=1.10x generation, prior passes <=1 |
  | MCP warm ordinary query | 30 samples per case, each p95 <=750 ms, semantic p95 <=300 ms |
  | CLI cold ordinary query | 30 samples per case, each p95 <=2.0 s |
  | MCP warm bounded explore | 30 samples per case, each p95 <=2.5 s and <=3 retrieval calls |
  | query RSS | vector payload x1.35 +256 MiB maximum |
  | vector publish disk | <=2.10x current generation high water, exactly one generation after success |
  | 100-step churn | final disk/pages <=1.25x compacted live baseline, tombstones below threshold, query p95 drift <=10%, <=2 generations after fault |
  | 5k to 10k scale | design ratios: full build <=2.7; no-op/status/refresh/one-file work/time/RSS <=2.4 as applicable |
  | protected small-repository regression | >=30 alternating paired baseline/final samples per protected operation; median paired latency regression <=10% when both population CVs <=8% |

  P95 uses nearest rank; expensive five-sample operations gate median/max. Apply
  the one-rerun and CV validity rules exactly. If either protected-small CV is
  above 8%, the comparison is invalid and the environment/baseline must be
  re-established; it is not a waiver. Absolute, scaling, work, disk,
  correctness, small-repository regression, and calibration gates are
  conjunctive.

- [ ] **Step 3: Validate exact outputs and ANN/service decisions**

  Compare final per-source candidates and final outputs to Task-1/protected
  projections. Regenerate the ANN decision against the final clean commit and
  combined report; a Task-10 candidate decision cannot be copied as final:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py decide \
    --kind ann \
    --report .quality/p6-artifacts/final-performance.json \
    --output .quality/p6-artifacts/final-ann.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-ann.json
  ```

  Step 5 computes the service/watch decision only after all other P6 gates:

  - use paired per-sample
    `immutable_state_load_ms/end_to_end_ms` median, never p95 division;
  - require the reviewed 40% and counterfactual 2x/750-ms/RSS conditions;
  - record only `deferred` or `eligible_for_separate_design`;
  - include no service/watcher implementation or authorization.

- [ ] **Step 4: Run every protected quality gate and pinned-real P5 twice**

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    --profile p5_language_graphs \
    --output .quality/p6-artifacts/final-p5.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output .quality/p6-artifacts/final-p4.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output .quality/p6-artifacts/final-p2.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output .quality/p6-artifacts/final-ci.json
  ```

  Validate the existing prepared pin and run the deliberately non-default real
  acceptance twice; the full pytest suite does not collect this script:

  ```bash
  test "$(git -C .quality/p5-repos/spring-petclinic rev-parse HEAD)" = \
    51045d1648dad955df586150c1a1a6e22ef400c2
  test -z "$(git -C .quality/p5-repos/spring-petclinic status --porcelain)"
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output .quality/p6-artifacts/final-real-a.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output .quality/p6-artifacts/final-real-b.json
  cmp -s \
    .quality/p6-artifacts/final-real-a.json \
    .quality/p6-artifacts/final-real-b.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate .quality/p6-artifacts/final-real-a.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate .quality/p6-artifacts/final-real-b.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  ```

  Require exact 12/12, 4/4, 5/5, and 8/8 with trace coverage 1.0. Require both
  pinned-real candidates to be byte-identical exact 2/2 and equal the committed
  normalized projection, with no fetch during either run.
  Re-run protected-direct/no-edge, ContextPack v2, RetrievalTrace v1,
  ExplorationTrace v2, P4 call/item/byte, structural graph, and input identity
  tests. P6 operational envelope fields are the only reviewed additive outputs;
  ranking/reasons/context bytes do not change.

- [ ] **Step 5: Run security/privacy/runtime/full acceptance**

  Run schema-first forbidden-work tests, no-fetch parser/scanner/status tests,
  symlink/path-race tests, remote payload/egress/error sanitization, lock/journal/
  reader cleanup interleavings, every fault seam, and benchmark privacy. Require
  the already-downloaded 12-cell Python 3.11-3.14/OS matrix from Step 1; the
  following local Python 3.13 suite supplements rather than substitutes for it:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" -m pytest -q -rs \
    --junitxml=.quality/p6-artifacts/final-full.xml
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-performance.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py compare \
    --baseline docs/benchmarks/p6/baseline/entry-performance.json \
    --final .quality/p6-artifacts/final-performance.json \
    --paired .quality/p6-artifacts/final-small-paired.json \
    --churn .quality/p6-artifacts/final-churn.json \
    --require-churn \
    --require-scale-5k-10k
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind environment \
    --input .quality/p6-artifacts/final-runtime.json \
    --input .quality/p6-artifacts/final-dependencies.txt \
    --input .quality/p6-artifacts/final-lineage.txt \
    --input .quality/p6-artifacts/final-matrix.json \
    --input .quality/p6-artifacts/final-performance.json \
    --output .quality/p6-artifacts/final-environment.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py assemble \
    --kind quality \
    --input .quality/p6-artifacts/final-p5.json \
    --input .quality/p6-artifacts/final-p4.json \
    --input .quality/p6-artifacts/final-p2.json \
    --input .quality/p6-artifacts/final-ci.json \
    --input .quality/p6-artifacts/final-real-a.json \
    --input .quality/p6-artifacts/final-real-b.json \
    --input .quality/p6-artifacts/final-full.xml \
    --input .quality/p6-artifacts/tdd-task-1.json \
    --input .quality/p6-artifacts/tdd-task-2.json \
    --input .quality/p6-artifacts/tdd-task-3.json \
    --input .quality/p6-artifacts/tdd-task-4.json \
    --input .quality/p6-artifacts/tdd-task-5.json \
    --input .quality/p6-artifacts/tdd-task-6.json \
    --input .quality/p6-artifacts/tdd-task-7.json \
    --input .quality/p6-artifacts/tdd-task-8.json \
    --input .quality/p6-artifacts/tdd-task-9.json \
    --input .quality/p6-artifacts/tdd-task-10.json \
    --output .quality/p6-artifacts/final-quality.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py decide \
    --kind service-watch \
    --report .quality/p6-artifacts/final-performance.json \
    --output .quality/p6-artifacts/final-service-watch.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-environment.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-quality.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py validate \
    --report .quality/p6-artifacts/final-service-watch.json
  ```

  `decide --kind service-watch` runs only here, after functional matrix, all
  performance/correctness comparisons, protected profiles, real acceptance,
  security/privacy tests, and full suite have passed. Audit exact skip node IDs
  and zero xfails. Privacy validation must precede copying raw reports into
  `docs/benchmarks/p6/final/`. The committed quality summary contains only TDD
  task/checkpoint counts, test/tree hashes, RED/GREEN outcomes, and producer
  identity—never raw failure logs, commands with absolute roots, or source text.

- [ ] **Step 6: Commit privacy-audited acceptance artifacts**

  Copy only canonical validated reports with source bodies, vector floats,
  secrets, environment values, absolute temporary paths, and unapproved real
  query text removed. Record generator/report hashes, raw sample counts,
  environment/calibration, stage/work/RSS/disk summaries, churn, quality, ANN,
  and service decisions. `docs/benchmarks/p6/README.md` links each artifact and
  states which host-dependent gates it proves.

  Use the sole privacy/canonical copy path for every committed artifact:

  ```bash
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-environment.json \
    --output docs/benchmarks/p6/final/final-environment.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-matrix.json \
    --output docs/benchmarks/p6/final/final-matrix.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-smoke.json \
    --output docs/benchmarks/p6/final/final-smoke.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-large.json \
    --output docs/benchmarks/p6/final/final-large.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-scale-5k.json \
    --output docs/benchmarks/p6/final/final-scale-5k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-scale-10k.json \
    --output docs/benchmarks/p6/final/final-scale-10k.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-stress.json \
    --output docs/benchmarks/p6/final/final-stress.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-performance.json \
    --output docs/benchmarks/p6/final/final-performance.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-churn.json \
    --output docs/benchmarks/p6/final/churn.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-quality.json \
    --output docs/benchmarks/p6/final/quality.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-ann.json \
    --output docs/benchmarks/p6/decisions/ann.json
  PYTHONPATH="$PWD/src" "$P6_RUNTIME" scripts/p6_benchmark.py publish \
    --input .quality/p6-artifacts/final-service-watch.json \
    --output docs/benchmarks/p6/decisions/service-watch.json
  ```

- [ ] **Step 7: Update user documentation and roadmap only now**

  Document:

  - metadata vs verified freshness and observation-interval limitation;
  - status/stats read-only behavior and exact CLI/MCP examples;
  - explicit refresh mutation, dependent fan-out, authoritative-index cases,
    and remote embedding disclosure;
  - v1 degraded migration, future schema refusal, failure recovery, generation/
    tombstone maintenance;
  - measured large-repository budgets and exact/ANN decision;
  - service/watch decision as non-shipped future design only.

  Mark design/plan/roadmap P6 complete only if every prior step passed. Preserve
  Phase 1's independent status and do not advance Phase 7.

- [ ] **Step 8: Final docs/artifact verification and commit**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P6_RUNTIME" -m pytest -q \
    tests/test_p6_benchmark.py \
    tests/test_index_health.py \
    tests/test_incremental_refresh.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_p5_inputs.py \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_retrieval_core_characterization.py
  git diff --check
  ```

  ```bash
  git add \
    docs/benchmarks/p6/final/final-environment.json \
    docs/benchmarks/p6/final/final-matrix.json \
    docs/benchmarks/p6/final/final-smoke.json \
    docs/benchmarks/p6/final/final-large.json \
    docs/benchmarks/p6/final/final-scale-5k.json \
    docs/benchmarks/p6/final/final-scale-10k.json \
    docs/benchmarks/p6/final/final-stress.json \
    docs/benchmarks/p6/final/final-performance.json \
    docs/benchmarks/p6/final/churn.json \
    docs/benchmarks/p6/final/quality.json \
    docs/benchmarks/p6/decisions/ann.json \
    docs/benchmarks/p6/decisions/service-watch.json \
    docs/benchmarks/p6/README.md \
    README.md \
    docs/retrieval-quality.md \
    docs/superpowers/specs/2026-07-18-p6-freshness-performance-large-repositories-design.md \
    docs/superpowers/plans/2026-07-18-p6-freshness-performance-large-repositories.md \
    roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
  git diff --cached --check
  git diff --cached --name-only
  git commit -m "docs: record p6 acceptance"
  ```

  Report the documentation commit in the handoff; this document cannot
  self-record the hash of the commit that contains its final edit.

## Design-To-Task Acceptance Map

| reviewed design contract | owning task(s) |
| --- | --- |
| clean P5 path-inventory entry and protected baseline | 0 |
| canonical health/envelope/workload schemas and immutable evidence | 1 |
| five health axes, total derivation, queryability evidence, bounded samples | 1-2, 4 |
| schema-first missing/v1/v2/future/corrupt capability matrix | 2-5, 7 |
| complete/incomplete inventory, control errors, stable observations, safe reads | 2, 5-7 |
| quick/verified inspection, two SQLite snapshots, read-only status/stats | 2-4 |
| indexed/configured embedding identity and fail-closed egress | 1-4, 7 |
| manifest v2, operational v1, descriptor v2 and final ready bindings | 3, 5 |
| v1 queryability and verified v1-to-v2 migration/recovery | 3-5 |
| authoritative prepare/fence/stale ordering and verified freshness | 5 |
| quick refresh legality, zero no-op, direct/dependent/retry work | 6 |
| refresh public envelopes, egress failures, explicit non-query mutation | 7 |
| immutable generation cleanup, reader barrier, tombstones, churn | 7, 11 |
| deterministic generator, cold/warm/RSS/work/disk/statistical methodology | 1, 8-11 |
| shared repository path index and measured indexing hot paths | 8 |
| exact SQLite/profile/ID/full-scan optimization and work contracts | 9 |
| exact vector load/normalization/partial top-k and ANN trigger | 10 |
| latency/RSS/disk/scaling/steady-state budgets | 8-11 |
| service/watch defer-or-eligibility only | 11 |
| privacy, no-fetch, sanitization, network disclosure | every task; final 11 |
| protected P0-P5 outputs, quality profiles, full suite/runtime matrix | 0, every production task, 11 |
| acceptance artifacts and docs/roadmap after all gates | 11 |

No row is satisfied by prose alone. Every contract has a focused test, canonical
fixture, validated report, or protected executable gate in its owning task.

## Implementation And Acceptance Record

Pending. Task 11 replaces this paragraph only after implementation passes all
reviewed gates. The record must include the `P6_ENTRY_COMMIT`, complete Task
1-10 lineage, runtime/dependency/host/calibration identities, full-suite counts
and exact skip node IDs/xfails, protected profile/projection hashes, benchmark
generator/report hashes, raw sample counts, all absolute/work/scaling/disk/RSS/
churn results, remote-egress/privacy results, ANN decision, service/watch
decision, and final documentation commit handoff.

## Stop Conditions

Stop implementation and request design/plan review if any of these occurs:

- the isolated P5 fix is absent/mixed, the entry worktree is dirty, or the exact
  2,625/9/0 candidate baseline and protected P5/real/quality evidence cannot be
  reproduced;
- implementation would need to start from a different runtime/dependency/source
  lineage without amending Task 0 and regenerating the baseline;
- a missing/future schema branch reaches config/provider/feedback/profile/scan,
  opens SQLite read-write, creates a journal/config/directory/lock, or interprets
  unknown rows/columns;
- manifest v1 cannot remain queryable/degraded until explicit authoritative
  migration, or future manifest/operational/graph state would be overwritten;
- DDL presence alone can become operational-authoritative, or manifest/
  descriptor identity cannot be bound in the same final ready transaction;
- quick status needs an eligible source body or vector payload read, verified
  status needs parsing/embedding, or status/stats cannot be proven mutation- and
  network-free;
- one report state has ambiguous health/queryability/action, omits a required
  key, guesses configured/indexed identity, or uses an unreviewed enum/error;
- an incomplete inventory/control error can infer deletion, lower-bound counts
  can be presented as complete, or a retryable skip can starve indefinitely;
- any workspace-derived source/control read, parser call, or embedding request
  occurs after the closing fence or after `stale_committed`;
- a closing-fence drift/incomplete pass can mark stale/ready or destroy the prior
  ready snapshot;
- quick refresh cannot prove zero body/hash/parse/embed/replace/publish/rewrite
  work for a complete no-op;
- a path addition/deletion can change an unchanged import/route/test/topology
  result without that source being in the declared dependent set;
- refresh would repair an embedding identity, future schema, stable corruption,
  or incomplete operational baseline that the legality matrix assigns to
  authoritative index;
- remote source scope exceeds new/content-changed embedding inputs, a dependency-
  only refresh sends source, egress outcome cannot be fail-closed, or an error
  can leak endpoint/credential/response/source/environment data;
- vector publication must mutate a generation in place, publish an unverified
  pair, or create a ready SQLite/manifest/descriptor/config mismatch;
- cleanup needs WAL, cannot prove a rollback-journal reader barrier, removes a
  referenced/unknown/symlink/foreign/possibly-reader-visible file, or allows a
  mmap/view to escape `GraphReadSession`;
- tombstone maintenance requires automatic refresh-path `VACUUM`, changes live
  search/graph rows, or cannot recover after a bounded fault;
- a benchmark mixes query cases/cold states, lacks raw samples/units/calibration,
  uses generated state inconsistent with its ready observations, counts hash
  work outside read/pass totals, or contains prohibited private data;
- a host-sensitive timing assertion remains in deterministic CI without a work
  proof, or a final performance claim violates CV/rerun/reference-host rules;
- `RepositoryPathIndex`, SQLite, or vector optimization changes ordered
  candidates, finite scores, reasons, follow-ups, ContextPack/trace/exploration
  bytes, P4 budgets, P5 graph projections, or protected direct/no-edge behavior;
- an exact scan exceeds its reviewed row/byte/pass contract or a new search
  surface/dependency is needed but not named in this plan;
- exact vector optimization cannot preserve boundary ties/float outputs, cannot
  keep mapping lifetime inside the read transaction, or weakens verified
  integrity without the reviewed replacement invariant;
- the ANN trigger is crossed, an ANN dependency/index/migration is proposed, or
  approximate behavior would ship without a reviewed amendment;
- service/watch eligibility is treated as implementation authority, or any
  daemon/watcher/cache lifecycle behavior is added by this plan;
- large latency/RSS/disk/churn/scaling or work-count gates fail after the one
  allowed valid rerun;
- a new default skip/xfail appears, a frozen fixture/expected output is refreshed
  to hide a regression, or a protected quality/real case falls below its exact
  gate;
- docs/roadmap are marked complete, acceptance artifacts are committed, or
  Phase 7 is advanced before every P6 gate passes.

These conditions are contract failures, not permission to broaden scope.

## Final Implementation Review Checklist

Before requesting implementation review, verify:

- [ ] clean `P6_ENTRY_COMMIT`, exact runtime/dependencies, P5 fix, 2,625/9/0,
  protected profiles, and pinned-real projection reproduced;
- [ ] Task-1 contract/workload/query fixtures and entry reports are immutable,
  deterministic, calibrated, schema-valid, and privacy-clean;
- [ ] raw capability probe is read-only/schema-first for every public operation;
- [ ] manifest v1/v2, operational absent/v1, graph v5/future, missing/corrupt
  capability matrix and exact error codes pass;
- [ ] health priority/total table, queryability evidence, nullable collections,
  samples/reasons/diagnostics, and embedding identities match golden v1;
- [ ] quick/verified inspectors use two inventories/two SQLite snapshots and
  classify drift/incomplete as interrupted rather than corrupt;
- [ ] status/stats mutate nothing, call no provider/network, expose no secret or
  absolute sampled path, and share one inspection result;
- [ ] existing stats top-level fields/embedding and query-family envelopes remain
  exact; new status/refresh envelopes are canonical;
- [ ] additive operational DDL is non-authoritative until final ready and future
  schemas never downgrade;
- [ ] manifest/descriptor canonical payloads, generations, digests, sizes,
  config/content/observation fingerprints, and work summary bind atomically;
- [ ] authoritative index hashes all eligible sources and detects preserved-
  metadata edits while parsing/embedding only declared work;
- [ ] direct/dependent workspace work and embedding results freeze before the
  closing fence; post-stale instrumentation proves zero workspace/control reads;
- [ ] incomplete/drift paths preserve the prior ready snapshot and infer no
  deletion;
- [ ] v1-to-v2 migration reuses valid chunks/graph/embeddings/generation and
  recovers at every fault seam;
- [ ] quick refresh no-op counters are exactly zero and successful evidence is
  metadata, never verified;
- [ ] direct edits, equal touches, add/delete/rename, skip recovery, topology,
  test association, and all path-resolution ambiguity transitions pass;
- [ ] reason/config legality refuses every authoritative-only condition before
  mutation/provider work;
- [ ] remote provider receives only allowed changed chunks; error egress outcome
  and sanitized disclosure pass every seam;
- [ ] graph-only refresh reuses descriptor/generation and exact active vector IDs
  bind at ready;
- [ ] rollback journal, reader lifetime, mmap/handle containment, cleanup safety,
  orphan retry, and unsupported-mode fail-closed tests pass;
- [ ] tombstone thresholds/batches, FTS/graph correctness, pages/freelist, one-
  generation success, two-generation fault bound, and churn recovery pass;
- [ ] one immutable `RepositoryPathIndex` is built per operation and exact P5
  plugin/materialization outputs are unchanged;
- [ ] planner-disabled queries build no repo profile; enabled/injected planner
  behavior remains exact;
- [ ] every exact SQLite source meets its SQL VM/row/byte/pass contract and every
  frozen candidate projection is identical;
- [ ] vector v2 normalization/mmap/partial top-k matches exhaustive full-sort
  references, including boundary ties and non-finite values;
- [ ] query payload hashing relaxation is backed by immutable bound ready facts,
  verified paths still hash, and evidence limitations are explicit;
- [ ] ANN decision is schema-valid and no ANN code/dependency ships without an
  amendment;
- [ ] smoke/large/scale/stress/churn reports satisfy sample/CV/calibration,
  latency/RSS/disk/work/scaling/privacy gates;
- [ ] service/watch decision uses paired ratios and contains no prototype;
- [ ] P5 12/12, pinned-real 2/2 twice, P4 4/4, P2 5/5, CI 8/8, traces,
  ContextPack, protected direct/no-edge, full suite, skips/xfails, and runtime
  matrix pass;
- [ ] committed artifacts contain no source/vector/secrets/environment/absolute
  temp paths and every documented claim links to validated evidence;
- [ ] README, quality docs, design, plan, and roadmap update only after all gates.

## Plan Review Rubric

Independent plan reviewers must check:

1. whether the pending P5 fix/clean-entry boundary is executable and no P6 work
   can begin from the current dirty worktree;
2. whether every task can end green with one focused commit, exact write paths,
   tests first, protected gates, and no hidden intermediate public state;
3. whether Task 1 freezes valid schemas/workloads/query projections and can
   capture an unoptimized product baseline without benchmark code contaminating
   production identity;
4. whether raw missing/v1/v2/future/corrupt probing precedes every forbidden
   config/provider/feedback/profile/scan/unknown-row action;
5. whether the report model, null/enum/sample/error contracts, embedding split,
   and total health/writer/generation derivation are mechanically testable;
6. whether inventory completeness/control errors/stable reads/two fences make
   false deletion/freshness impossible under traversal failure and concurrent
   edits;
7. whether manifest v2/operational v1/descriptor v2 migration and final-ready
   binding preserve P5 v1 queryability and recover from every crash phase;
8. whether authoritative and quick pipelines finish all direct/dependent source,
   parser, relation, embedding, and topology inputs before stale and reuse one
   persistence protocol;
9. whether refresh legality, zero-work no-op, retry fairness, dependency fan-out,
   vector reuse, work equations, remote payload, and error egress are complete;
10. whether rollback-journal reader barriers, `GraphReadSession` vector lifetime,
    generation cleanup, tombstone purge, disk bounds, and churn recovery are
    safe on POSIX/Windows and fail closed otherwise;
11. whether the performance harness has realistic bytes/density/selectivity,
    observation-consistent mutations, valid cold/warm/RSS/calibration/statistics,
    work counters, privacy, and committed evidence;
12. whether Tasks 8-9 optimize only proven costs, include mandatory path-index/
    planner-off fixes, preserve exact source/final projections, and stop for an
    unnamed new search surface;
13. whether Task 10's small-identity/immutable-generation replacement for
    repeated payload hashing and normalized mmap/partial top-k are lifecycle-safe
    and exact, with a sufficient ANN stop gate;
14. whether protected P0-P5/real/full/runtime/privacy gates and final absolute/
    work/scaling/disk/churn budgets are executable from the listed commands;
15. whether service/watch, ANN, new ranking/parser/language/product surfaces,
    Phase 1, and Phase 7 remain outside authorization.

Any unresolved blocker or major correctness, lifecycle, compatibility, privacy,
freshness-truth, benchmark-validity, task-order, exactness, or acceptance finding
keeps this plan in draft status.

## Agent Review Record

Round 1 reviewed the complete 2,205-line draft at SHA-256
`568b75303e4b4c9a523c472696134b0981a927e2d287225f5d265ce2bb99c9ee`.
All reviewers confirmed a read-only full-document pass:

- architecture/lifecycle: FAIL, 0 blocker / 3 major / 2 minor;
- performance/executability: FAIL, 0 blocker / 4 major / 2 minor;
- adversarial testing/acceptance: FAIL, 0 blocker / 6 major / 2 minor.

Round 2 reviewed the complete 3,026-line revision at SHA-256
`26f117b0ccf738fdcb5e2e9af60394cd6f3945261149fe2ec334bd8d83598d95`.
All reviewers again confirmed the hash and read-only full-document pass:

- architecture/lifecycle: PASS, 0 blocker / 0 major / 1 minor;
- performance/executability: FAIL, 0 blocker / 2 major / 2 minor;
- adversarial testing/acceptance: FAIL, 0 blocker / 3 major / 1 minor.

Round 2 confirmed every Round-1 major closed, then found five new executable-
evidence gaps. This revision adds closed entry/environment/quality/TDD schemas,
bootstrap plus per-task `tdd-red`/`tdd-green` producers bound to the staged tree,
closed adapters for raw JUnit/dependency/lineage/hash evidence, and a deterministic
Task-0-to-Task-1 entry producer. It replaces impossible first-time dispatch with
a unique final `p6-acceptance-*` tag-push workflow/run-name/evidence binding,
feeds churn into final-mode assembly and mandatory comparison with four negative
budget tests, gives paired sampling its own pristine generated root and per-pair
clones, proves no unstaged candidate-path changes, and arms all-exit cleanup for
Tasks 8-10 temporary worktrees.

Round 3 reviewed the complete 3,316-line revision at SHA-256
`999be7e53b4e903af11406da85f0b4500e78612ab91926b773afe86fc3f78f9b`:

- architecture/lifecycle: PASS, 0 blocker / 0 major / 1 minor;
- performance/executability: PASS, 0 blocker / 0 major / 3 minor;
- adversarial testing/acceptance: PASS, 0 blocker / 0 major / 2 minor.

The six minor findings were all incorporated: bounded unique CI-run polling,
paired all-exit cleanup, local/direct-URL dependency sanitization, immutable
pre-RED candidate fixtures, and the related cleanup/evidence clarifications.

Round 4 reviewed only those closures in the complete 3,350-line revision at
SHA-256
`d4c16adf02d81ec5160a9112998c425f2784b58780520fd4570e8a4eecdf269f`.
Architecture/lifecycle, performance/executability, and adversarial testing/
acceptance each returned PASS with 0 blocker / 0 major / 0 minor and confirmed
the file hash plus read-only worktree state.

Result: this plan is independently reviewed and ready for user approval. It
does not authorize implementation; Task 0 still requires a new explicit user
instruction and the clean P5-fix/documentation entry sequence above.

## Stop Point

Planning and agent review are authorized. P6 implementation, branch creation,
staging, commits, large benchmark execution, remote publication, ANN work, and
service/watch work are not authorized by this document. After review, wait for
an explicit user instruction before Task 0.
