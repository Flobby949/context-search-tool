# P3.2 Retrieval Core Decomposition Implementation Plan

Date: 2026-07-16
Status: Agent-reviewed; implementation pending
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Design: `docs/superpowers/specs/2026-07-16-p3-2-retrieval-core-decomposition-design.md`
Implementation baseline: `34c5b5bd2189fbba4ead3902342706266c399b41`

> **For agentic workers:** Execute one task at a time. Every task uses checkbox
> (`- [ ]`) tracking, ends with explicit verification, and creates the listed
> focused commit. Stop immediately on any fingerprint, ordering, timing, privacy,
> or public-contract mismatch; do not update expected values to make a refactor
> pass.

**Goal:** Decompose the 5,035-line `retrieval.py` into the reviewed
`retrieval_core` modules while preserving every supported façade contract,
ordinary-query result, ContextPack byte, RetrievalTrace-v1 observation, early
return, operation count, and feedback/privacy boundary.

**Architecture:** Keep `QueryBundle`, `TracedQueryBundle`,
`query_repository()`, and `trace_repository()` in `retrieval.py`. Keep the
fifteen canonical P3.1 stages explicit there. Move only stage implementations
and narrow shared primitives into an acyclic private package. Do not introduce a
pipeline object, stage registry, callback framework, or second bundle-shaped
result.

**Tech Stack:** Python 3.11, frozen dataclasses, SQLite-backed retrieval,
offline hash-v1 embeddings, pytest, AST boundary checks, SHA-256
characterization fixtures, Typer/FastMCP compatibility tests.

---

## Source Of Truth And Execution Constraints

The approved source of truth is:

- `docs/superpowers/specs/2026-07-16-p3-2-retrieval-core-decomposition-design.md`

The protected implementation baseline is:

- retrieval implementation: `34c5b5bd2189fbba4ead3902342706266c399b41`;
- documentation baseline containing verified P3.1 evidence:
  `6e4eef4c61ecfdaaa6721e5d81a40832b90a4281`;
- full suite: 1,884 passed and 9 skipped;
- focused P3.1 suite: 125 passed;
- `p2_context_pack`: 5/5;
- raw `ci`: 8/8;
- Phase 1: independently pending at 6/7.

Execution constraints:

1. Start from a clean branch created from `main` after the reviewed P3.2 design
   and this plan are merged.
2. Before generating characterization data, prove that production source is
   unchanged relative to `34c5b5b`:

   ```bash
   git diff --exit-code \
     34c5b5bd2189fbba4ead3902342706266c399b41 -- \
     src/context_search_tool
   ```

   Also require a completely clean source worktree, including untracked files:

   ```bash
   test -z "$(git status --porcelain=v1 --untracked-files=all -- \
     src/context_search_tool)"
   ```

3. Freeze characterization inputs relative to the reviewed documentation
   baseline `6e4eef4c61ecfdaaa6721e5d81a40832b90a4281`. Before generation, require
   no tracked, staged, unstaged, or untracked difference in:

   - `tests/fixtures/retrieval_quality/queries.json`;
   - `tests/fixtures/real_projects/program_tool/`;
   - `tests/fixtures/java-spring-mini/`;
   - `tests/fixtures/context-pack-java/`;
   - `tests/fixtures/context-pack-docs/`.

   The manifest records the catalog blob OID, each resolved snapshot tree OID,
   and a working-tree content hash. The generator rejects any mismatch, and the
   committed characterization verifier rechecks the same identity on every
   later run; input drift is never accepted merely because `baseline.json`
   remains unchanged.

4. Slice 1 is tests and fixtures only. Its baseline manifest is committed before
   any production extraction.
5. After Slice 1, never edit
   `tests/fixtures/retrieval_core_decomposition/baseline.json` during P3.2.
6. Production changes are limited to
   `src/context_search_tool/retrieval.py` and new files under
   `src/context_search_tool/retrieval_core/`.
7. Do not edit `retrieval_trace/`, `context_pack/`, `quality/`, public
   `models.py`, `cli.py`, `formatters.py`, `mcp_server.py`, or `mcp_tools.py`.
   `scripts/profile_retrieval.py` is the one allowed non-production consumer
   update; it must migrate with the private functions it profiles.
8. Do not change scores, constants, limits, sort keys, collection shapes, query
   planning, error handling, ContextPack options, trace schema, or public output.
9. Do not delete the pre-existing uncalled helpers `_candidate_base_score()` or
   `_is_readme_document()`; move them unchanged to their reviewed owners.
10. A temporary private alias may exist only inside the task that removes it. It
   may not be used to forward monkeypatches across an owner boundary.
11. Move the production call site, direct test import, monkeypatch target,
    profiling target, and
    migration-ledger row atomically.
12. Preserve all existing test assertions. Import-only edits are allowed;
    weakening, deleting, or replacing exact assertions is not.
13. Run the characterization verifier after every production edit. A mismatch
    is a stop condition, not permission to regenerate the fixture.
14. Every task ends with a focused commit. Stage exact paths; do not use
    `git add -A` in a dirty worktree.
15. Do not begin ranking redesign, P4 exploration, multi-round retrieval, graph
    features, trace persistence, or Phase 1 closure.

## Definition Of Done

P3.2 implementation is complete only when:

- `retrieval.py` contains the normative façade and explicit fifteen-stage
  orchestration, but no stage implementation body;
- the reviewed import-adjacency table is exact, acyclic, and AST-enforced;
- all 13 public/output/internal fingerprints, all four full-stage ledgers, and
  both complete 13-case operation ledgers match the immutable baseline;
- the catalog blob OID, four snapshot tree OIDs, working-tree content hashes,
  and clean tracked/staged/unstaged/untracked state still match the frozen
  characterization inputs;
- public bundle identity, supported imports, timing, early returns, operation
  counts, privacy, feedback isolation, and error contracts remain exact;
- no migrated private façade reference or temporary alias remains;
- the full suite, P3.1, P2, and raw-CI gates pass with the recorded skip/xfail
  set;
- the protected-source diff gate is clean;
- verification evidence and exact commits are documented before the roadmap
  marks P3.2 implementation complete.

## File Responsibility Map

| file | final responsibility |
| --- | --- |
| `src/context_search_tool/retrieval.py` | Supported façade and explicit fifteen-stage orchestration |
| `src/context_search_tool/retrieval_core/__init__.py` | Package marker only; no broad re-exports |
| `src/context_search_tool/retrieval_core/types.py` | `_RankedChunk` and `_ExpandedResult` |
| `src/context_search_tool/retrieval_core/ordering.py` | Two stable dedupers and shared rerank sort precision |
| `src/context_search_tool/retrieval_core/evidence_merge.py` | Pure score bounding, score-part merge, semantic-match merge/order |
| `src/context_search_tool/retrieval_core/relation_policy.py` | Shared expansion depth/cap and relation confidence floor |
| `src/context_search_tool/retrieval_core/file_roles.py` | Existing generic file-role value, constants, and predicates |
| `src/context_search_tool/retrieval_core/candidates.py` | Recall stages, direct probes, candidate merge, source normalization |
| `src/context_search_tool/retrieval_core/expansion.py` | Anchor/relation expansion and compatibility logger |
| `src/context_search_tool/retrieval_core/ranking.py` | Ranking, route/Spring/Java/frontend policy, cohort rerank, score normalization |
| `src/context_search_tool/retrieval_core/context_expansion.py` | File reads, windows, caps, overlap merge, spans |
| `src/context_search_tool/retrieval_core/selection.py` | Timed selection and post-stop output assembly |
| `src/context_search_tool/retrieval_core/tracing.py` | Trace-v1 adapters, explicit stop/finish helpers, finalization |
| `tests/retrieval_core_characterization.py` | Stable test-only projections, hashing, case runner, full-stage ledger |
| `tests/generate_retrieval_core_baseline.py` | One-shot pre-refactor manifest generator |
| `tests/test_retrieval_core_characterization.py` | Immutable baseline verification and operation ledgers |
| `tests/test_retrieval_core_boundaries.py` | Façade, AST adjacency, privacy, alias, and protected-diff gates |
| `tests/test_retrieval_core_primitives.py` | Shared primitive and internal dataclass parity tests |
| `tests/test_profile_retrieval.py` | Profiling target existence and wrapper-hit regression tests |
| `tests/fixtures/retrieval_core_decomposition/baseline.json` | Immutable 13-case fingerprints, four full-stage ledgers, and ordinary/traced operation ledgers |
| `tests/fixtures/retrieval_core_decomposition/migration_ledger.json` | Original private references and per-slice resolution state |
| `scripts/profile_retrieval.py` | Owner-qualified profiling targets that follow stage extraction |
| Existing retrieval/rerank/quality/trace tests | Same assertions, imports and patch targets migrated to owners |
| `docs/retrieval-quality.md` | Final P3.2 acceptance evidence |
| P3.2 design, this plan, and roadmap | Conditional implementation status and exact commit evidence |

## Final Internal Import Adjacency

The AST test treats an edge as `importer -> imported` and permits only:

| importer | allowed retrieval-core dependencies |
| --- | --- |
| `retrieval.py` | `candidates`, `expansion`, `ranking`, `context_expansion`, `selection`, `tracing`, `ordering`, `relation_policy`, plus public `retrieval_trace` |
| `types` | none |
| `ordering` | none |
| `evidence_merge` | none |
| `relation_policy` | none |
| `file_roles` | none |
| `candidates` | `ordering`, `evidence_merge` |
| `expansion` | `evidence_merge`, `file_roles`, `relation_policy` |
| `ranking` | `types`, `ordering`, `evidence_merge`, `file_roles`, `relation_policy` |
| `context_expansion` | `types`, `ordering`, `evidence_merge` |
| `selection` | `types`, `ordering` |
| `tracing` | `types`, `ordering`, `selection`, plus public `retrieval_trace` |

All standard-library and existing non-retrieval domain imports remain allowed.
No `retrieval_core` module imports `retrieval.py`; no stage owner imports another
stage owner; `tracing -> selection` is the single reviewed stage-related edge.

## Supported Retrieval Façade

The final façade allowlist is exact:

| symbol | implementation rule |
| --- | --- |
| `QueryBundle` | Remains defined in `retrieval.py` with exact dataclass identity |
| `TracedQueryBundle` | Remains defined in `retrieval.py` with exact dataclass identity |
| `query_repository` | Same signature; explicit fifteen-stage orchestrator |
| `trace_repository` | Same signature; only collector constructor |
| `evidence_anchor_top_k` | Remains defined in `retrieval.py` |
| `normalize_score` | Thin function defined in `retrieval.py`, delegating to `ranking.normalize_score` |
| `MAX_EXPANSION_DEPTH` | Value alias to `relation_policy.MAX_EXPANSION_DEPTH` |
| `MAX_EXPANSION_CANDIDATES` | Value alias to `relation_policy.MAX_EXPANSION_CANDIDATES` |

Do not add `__all__`. Incidental names such as `tokenize_query`, `expand_lines`,
`NumpyVectorStore`, `SQLiteStore`, `provider_from_config`, and
`RetrievalTraceCollector` are not supported façade contracts; tests using them
move to their canonical or new owner.

## Task And Commit Order

| task | design slice | required focused commit |
| ---: | --- | --- |
| 0 | Preflight | none |
| 1 | Slice 1 | `test: lock retrieval core decomposition baseline` |
| 2 | Slice 2 | `refactor: extract retrieval core primitives` |
| 3 | Slice 3a | `refactor: extract retrieval candidate stages` |
| 4 | Slice 3b | `refactor: extract retrieval expansion stages` |
| 5 | Slice 4 | `refactor: extract retrieval ranking core` |
| 6 | Slice 5a | `refactor: extract retrieval context expansion` |
| 7 | Slice 5b | `refactor: extract retrieval selection` |
| 8 | Slice 6 | `refactor: extract retrieval trace adapters` |
| 9 | Slice 6 closure | `test: close retrieval core decomposition boundaries` |
| 10 | Slice 7 | `docs: verify retrieval core decomposition` |

Do not squash the Slice 1 commit: its commit ID and the Git blob OID of
`baseline.json` are final acceptance evidence.

## Shared Verification Commands

Use these names consistently throughout the plan:

Every suite and quality command runs with the five environment variables listed
in Task 1 unset. Do not rely on state from an earlier shell invocation. In the
same shell invocation as each command block below, first execute this mandatory
prelude (blocks already showing `env -u ...` are the equivalent inline form):

```bash
unset \
  CST_RUN_P1_ACCEPTANCE \
  CST_P2_REAL_CONTEXT_REPOS_DIR \
  CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
  CST_SMOKE_REPOS_DIR \
  CST_PLANNER_REQUESTS_REPO
test -z "$(env | rg '^(CST_RUN_P1_ACCEPTANCE|CST_P2_REAL_CONTEXT_REPOS_DIR|CST_SMOKE_INVESTMENT_ASSISTANT_REPO|CST_SMOKE_REPOS_DIR|CST_PLANNER_REQUESTS_REPO)=' || true)"
```

An execution agent using a fresh shell for each tool call must prepend this
block to each such call; an unprefixed fresh-shell test run is invalid evidence.

```bash
# Fast structural/focused gate
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
  tests/test_retrieval_core_primitives.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_core_characterization.py

# Existing retrieval and trace behavior
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
  tests/test_retrieval_pipeline.py \
  tests/test_rerank_soft_sorting.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p3.py

# Full suite
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
```

The first command is introduced incrementally; omit a not-yet-created test file
until its task creates it. Every production task runs the characterization test
and full suite before commit.

### Task 0: Establish A Clean, Reproducible Start

**Files:** none

- [ ] **Step 1: Create the implementation branch from reviewed `main`**

  ```bash
  git switch main
  git status --short
  git switch -c codex/p3-2-retrieval-core-decomposition
  ```

  Expected: `main` contains the reviewed design and plan; the new branch starts
  clean.

- [ ] **Step 2: Prove the production baseline**

  ```bash
  git diff --exit-code \
    34c5b5bd2189fbba4ead3902342706266c399b41 -- \
    src/context_search_tool
  wc -l src/context_search_tool/retrieval.py
  ```

  Expected: no production diff and exactly 5,035 lines.

- [ ] **Step 3: Prove the characterization-input baseline**

  ```bash
  git diff --exit-code \
    6e4eef4c61ecfdaaa6721e5d81a40832b90a4281 -- \
    tests/fixtures/retrieval_quality/queries.json \
    tests/fixtures/real_projects/program_tool \
    tests/fixtures/java-spring-mini \
    tests/fixtures/context-pack-java \
    tests/fixtures/context-pack-docs
  test -z "$(git status --porcelain=v1 --untracked-files=all -- \
    tests/fixtures/retrieval_quality/queries.json \
    tests/fixtures/real_projects/program_tool \
    tests/fixtures/java-spring-mini \
    tests/fixtures/context-pack-java \
    tests/fixtures/context-pack-docs)"
  ```

  Expected: no output. Capture the baseline catalog blob and four snapshot tree
  OIDs with `git rev-parse 6e4eef4:<path>`; Task 1 writes and verifies them.

- [ ] **Step 4: Record the current façade-reference inventory**

  ```bash
  rg -n 'retrieval\._[A-Za-z0-9_]+|from context_search_tool\.retrieval import' \
    tests scripts --stats || true
  rg -n 'monkeypatch\.setattr\(retrieval|patch\.object\(retrieval' tests || true
  ```

  The commands are informational only; multiline patches and dynamic
  `getattr/setattr` targets are not reliably covered by line regexes. Task 1
  builds the normative inventory with AST plus explicit dynamic-target parsing.
  Store exact symbol/file/kind/disposition rows; do not use an aggregate count
  as the migration gate.

- [ ] **Step 5: Run the pre-refactor verification baseline**

  ```bash
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q -rs \
    --junitxml=/tmp/cst-p3-2-baseline.xml
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_p3.py
  ```

  Expected: 1,884 passed, 9 skipped; focused P3.1 total remains 125 passed.
  Preserve `/tmp/cst-p3-2-baseline.xml` for Task 1 so the manifest can record
  exact skip/xfail node IDs and reasons. Stop if the reviewed baseline cannot be
  reproduced.

### Task 1: Lock Characterization, Façade, And Migration Boundaries

**Files:**

- Create: `tests/retrieval_core_characterization.py`
- Create: `tests/generate_retrieval_core_baseline.py`
- Create: `tests/test_retrieval_core_characterization.py`
- Create: `tests/test_retrieval_core_boundaries.py`
- Create: `tests/test_profile_retrieval.py`
- Create: `tests/fixtures/retrieval_core_decomposition/baseline.json`
- Create: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`
- Modify: `tests/test_retrieval_trace_pipeline.py`

- [ ] **Step 1: Write the failing immutable-manifest test**

  Add a test that loads `baseline.json`, requires `schema_version == 1`, checks
  the exact 13 `(profile, repo_key, case_id)` entries, and verifies these four
  full-ledger keys:

  - `context_pack_java/workspace-page-flow`;
  - `context_pack_frontend/qrcode-feature-context`;
  - `context_pack_docs/program-tool-developer-docs`;
  - `java_spring_mini/apply-audit-endpoint`.

  Also require the exact baseline skip/xfail node IDs and reasons parsed from
  Task 0's JUnit XML. Define
  `test_characterization_inputs_match_frozen_identity` to recompute the catalog
  blob OID, four snapshot tree OIDs, working-tree content hashes, and clean
  tracked/staged/unstaged/untracked state on every verifier run.

  Run it before creating the fixture:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py
  ```

  Expected: FAIL because `baseline.json` does not exist.

- [ ] **Step 2: Implement the stable test-only projection library**

  `tests/retrieval_core_characterization.py` must provide narrow helpers for:

  - loading `tests/fixtures/retrieval_quality/queries.json` with
    `load_quality_fixture()`;
  - resolving a `ToolConfig` from `DEFAULT_CONFIG` and the selected profile;
  - copying each `snapshot_path` to a temporary workspace and indexing it;
  - running `query_repository()` and `trace_repository()` exactly once per
    requested projection;
  - resolving P2 `ContextPackOptions` through the production resolver;
  - hashing exact production bytes;
  - building a fixed-order internal bundle diagnostic;
  - capturing the four full-stage ledgers with test wrappers;
  - recursively rejecting absolute temp paths, source text, prompts, headers,
    environment values, and secrets from the manifest.

  The helper also defines the one clean verification environment by rejecting
  these variables when generating or comparing JUnit evidence:

  - `CST_RUN_P1_ACCEPTANCE`;
  - `CST_P2_REAL_CONTEXT_REPOS_DIR`;
  - `CST_SMOKE_INVESTMENT_ASSISTANT_REPO`;
  - `CST_SMOKE_REPOS_DIR`;
  - `CST_PLANNER_REQUESTS_REPO`.

  Record and later require the same Python major/minor, `sys.platform`,
  `os.name`, and SQLite version so platform-conditional skips cannot drift
  silently.

  Keep this code under `tests/`; production retrieval must never import it.

- [ ] **Step 3: Define exact public byte hashes**

  For every one of the 13 cases, compute SHA-256 of:

  ```python
  format_json(bundle).encode("utf-8")
  format_markdown(bundle).encode("utf-8")
  format_trace_json(normalized_trace_envelope).encode("utf-8")
  ```

  Build the trace envelope with `trace_payload(repo, query, trace)`. Normalize
  only:

  - envelope `repo` to the fixture identifier;
  - trace `duration_ms` to integer `0`;
  - every stage `duration_ms` to integer `0`.

  Do not sort, remove, or rebuild trace keys. For the five P2 cases, also hash:

  ```python
  canonical_context_pack_bytes(build_context_pack(bundle, resolved_options))
  ```

  Store the complete resolved options beside the P2 hash and compare them before
  building the pack.

- [ ] **Step 4: Define the internal bundle diagnostic**

  Use explicit fixed-order dictionaries and ordered arrays. Include:

  - query, expanded tokens, planner, variants, status, summary, and follow-ups;
  - every result's non-content fields, complete spans, semantic matches,
    `sha256(content)`, and `sha256(_context_content)` when present;
  - every evidence anchor's non-content fields, `sha256(content)`, and
    `sha256(_context_content)` when present.

  Serialize with UTF-8, `ensure_ascii=True`, compact separators,
  `sort_keys=False`, and `allow_nan=False`. Never write source content into the
  fixture.

- [ ] **Step 5: Define the full-stage ledger schema**

  The stable ledger schema is an ordered list of all fifteen stages. Record all
  live outputs, not trace top-five previews:

  - candidate stages: chunk ID, score, source, score parts, semantic matches;
  - ranking/cohort: chunk/path/span, scores, tier, evidence class/priority,
    clamp state, reasons, semantic matches;
  - context expansion: origin IDs, path/span, scores, complete retrieval spans,
    content/context-content hashes;
  - selection: selected origins, kind, reason, and exact decision counts;
  - query understanding: tokens, variants, plan status, and hints;
  - ordered planner, embedding, vector, SQLite, observation-only store, and file
    operations with safe normalized arguments.

  Independently record **two complete operation ledgers for every one of the 13
  cases**, not only the four stage-ledger cases:

  - `ordinary_operations`: a plain `query_repository()` run;
  - `traced_operations`: a separate `trace_repository()` run.

  Reset spies between run boundaries and label every entry with
  `run=ordinary|traced` and `phase=live|observation`. The ordinary ledger locks
  every planner, embedding, vector, SQLite, index-exists/source-file stat/read,
  and fallback operation with safe normalized arguments. The traced ledger
  separately identifies observation-only store calls. Never infer ordinary
  behavior from wrappers that execute only on the traced path.

  Capture with test wrappers around existing orchestration seams. Freeze the
  ledger schema/projection tests now; later tasks may change only the wrapper
  target path when ownership moves.

  The initial adapters must be explicit rather than heuristic:

  - wrap `_finish_candidate_stage` and use its `StageToken.name` for stages
    2-11, recording the full candidate list before preview truncation;
  - wrap `_trace_ranked_observations` for ranking/cohort full lists;
  - wrap `_trace_expanded_observations` for the full context list;
  - wrap `_trace_final_selections` plus the selection input/decision values;
  - wrap planner/token/hint functions for query-understanding outputs;
  - spy on provider/vector/store/path methods for operation order.

  When ownership moves, only these wrapper target imports change; ledger field
  construction and serialization stay byte-identical and are guarded by unit
  tests.

- [ ] **Step 6: Generate the baseline exactly once**

  `tests/generate_retrieval_core_baseline.py` must refuse to run unless:

  - `git diff 34c5b5b -- src/context_search_tool` is empty;
  - `git status --porcelain=v1 --untracked-files=all -- src/context_search_tool`
    is empty;
  - the catalog and all resolved snapshot inputs exactly match
    `6e4eef4c61ecfdaaa6721e5d81a40832b90a4281`, including clean tracked/staged/
    untracked state, expected Git OIDs, and working-tree content hashes;
  - the catalog exposes exactly 8 `ci` and 5 `p2_context_pack` cases;
  - all snapshot paths resolve inside the repository fixtures;
  - no output contains a temporary absolute path or unhashed content;
  - all five clean-environment variables are absent;
  - the supplied JUnit XML records the expected 1,884 passes and 9 skips on the
    recorded platform/runtime.

  Run:

  ```bash
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/generate_retrieval_core_baseline.py \
    --junitxml /tmp/cst-p3-2-baseline.xml
  ```

  Review the generated manifest. It must name implementation commit
  `34c5b5bd2189fbba4ead3902342706266c399b41` and contain no wall-clock value.
  The committed verifier must independently recompute and compare every input
  OID/hash and clean-state condition on every subsequent characterization run;
  this logic is not generator-only.

- [ ] **Step 7: Add façade and dataclass identity gates**

  In `tests/test_retrieval_core_boundaries.py`, freeze:

  - both public classes' `__name__`, `__module__`, frozen setting, fields,
    defaults, repr, and equality;
  - signatures of `query_repository`, `trace_repository`,
    `evidence_anchor_top_k`, and `normalize_score`;
  - `normalize_score` values and `__module__`;
  - values of `MAX_EXPANSION_DEPTH` and `MAX_EXPANSION_CANDIDATES`;
  - the absence of a new retrieval `__all__` requirement.

- [ ] **Step 8: Add transitional AST inventory machinery**

  Implement the ledger generator with AST visitors for `ImportFrom`,
  `retrieval.<attr>`, `monkeypatch.setattr`, and `patch.object`, plus explicit
  parsing of dynamic `getattr/setattr` names in `scripts/profile_retrieval.py`.
  This must find multiline patches that the Task 0 regex misses. Add explicit
  `--write-migration-ledger` and `--check-migration-ledger` modes to
  `tests/generate_retrieval_core_baseline.py`; ordinary baseline generation must
  not implicitly freeze a provisional ledger.

  Classify every reference as either:

  - `supported_facade`: remains on `retrieval` and must keep its original
    reference count/contract;
  - `migrate`: private or incidental and must reach zero at its assigned owner
    task.

  Each row records:

  - old symbol;
  - final owner;
  - design slice/task;
  - direct-reference files/count;
  - monkeypatch files/count;
  - production call sites;
  - syntax kind and `disposition`;
  - `remaining` count;
  - `resolved_task`, initially `null`.

  Add an AST test with the final adjacency table plus an explicit transitional
  allowlist. The transitional list may only shrink. Reject cycles, star imports,
  package-level broad re-exports, aliased private re-exports, and every
  unsupported incidental façade attribute. A provisional scan may exercise the
  generator here, but do not write or freeze `migration_ledger.json` yet: Steps
  9-10 add test references that belong in the Slice 1 inventory.

- [ ] **Step 9: Lock the profiling consumer**

  Add `tests/test_profile_retrieval.py` to prove that every configured profiling
  `(display_name, owner_module, attribute_name)` target exists and that the
  wrapper is actually hit. At the Slice 1 baseline it may adapt the current
  string list into that test shape without modifying the script. Tasks 3-7 must
  migrate each target tuple with its production owner; silent `getattr(...,
  None)` skips are forbidden.

- [ ] **Step 10: Strengthen early-return, timing, operation, and privacy tests**

  Add focused tests that freeze:

  - missing index: full bundle/JSON/Markdown, no stage/planner/store/vector or
    source-file stat/read beyond the existing resolve/index-exists preflight;
  - deleted-ID `sqlite3.Error`: full plain/traced bundle parity, no stage, and no
    broader caught exception;
  - no candidates: exact stages 1-11 and no ranking/context/summary/file work;
  - manifest/planner/provider propagation and CLI/MCP no-partial-trace behavior;
  - operation -> stop-clock -> observation order for every stage;
  - final selection stop before trace conversion and output assembly;
  - bundle construction before collector total finish;
  - one primary embedding batch plus only the existing fallback retry;
  - exactly one direct-text probe computation before its timer;
  - no trace adapter/decision construction for ordinary queries;
  - tracing does not read `.content` or `._context_content`;
  - both `_try_append_query_feedback` and `_append_query_feedback` remain
    forbidden for trace success, early-return, and error paths.

- [ ] **Step 11: Generate and freeze the final Slice 1 migration ledger**

  Only after Steps 9-10 have created all Slice 1 tests, run the AST/dynamic-target
  generator over the completed `tests/` tree and `scripts/profile_retrieval.py`
  and write `migration_ledger.json`. Exclude the generated ledger file itself
  from source-reference scanning. Then immediately run the generator in compare
  mode and require byte-identical reference rows, counts, syntax kinds, and
  dispositions. Any later Slice 1 test edit requires regeneration and another
  exact compare before the Slice 1 commit; after that commit, rows may only be
  resolved by their assigned Tasks 2-8.

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/generate_retrieval_core_baseline.py --write-migration-ledger
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python \
    tests/generate_retrieval_core_baseline.py --check-migration-ledger
  ```

- [ ] **Step 12: Run Slice 1 verification**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_trace_pipeline.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  git diff --check
  ```

  Expected: immutable characterization passes; the pre-existing skip/xfail node
  IDs and reasons remain exact, and every newly added test passes. The total
  passed count increases, so do not compare the post-Slice-1 pass-node set to the
  1,884-test pre-Slice-1 set. Inspect the manifest rather than trusting only test
  status.

- [ ] **Step 13: Commit the immutable baseline slice**

  ```bash
  git add \
    tests/retrieval_core_characterization.py \
    tests/generate_retrieval_core_baseline.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/fixtures/retrieval_core_decomposition/baseline.json \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "test: lock retrieval core decomposition baseline"
  git rev-parse HEAD
  git hash-object \
    tests/fixtures/retrieval_core_decomposition/baseline.json
  ```

  Save both IDs for Task 10. From this point onward, the baseline blob OID must
  never change.

### Task 2: Extract Shared Types And Narrow Primitives

**Files:**

- Create: `src/context_search_tool/retrieval_core/__init__.py`
- Create: `src/context_search_tool/retrieval_core/types.py`
- Create: `src/context_search_tool/retrieval_core/ordering.py`
- Create: `src/context_search_tool/retrieval_core/evidence_merge.py`
- Create: `src/context_search_tool/retrieval_core/relation_policy.py`
- Create: `src/context_search_tool/retrieval_core/file_roles.py`
- Create: `tests/test_retrieval_core_primitives.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_rerank_soft_sorting.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`
- Modify: `tests/test_quality_catalog.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Write failing owner and parity tests**

  Add exact tests for:

  - `_RankedChunk` and `_ExpandedResult` field order/defaults/equality/repr;
  - their unchanged `__name__` and intentional new `__module__`;
  - case-insensitive `dedupe_lowered()` output;
  - first-value-casing `ordered_unique_preserving_case()` output;
  - `RERANK_SORT_DECIMALS == 3`;
  - score bounding, score-part merge, and semantic-match merge/order;
  - relation depth/cap/confidence values;
  - generic file-role classification, numeric fields, and predicates;
  - `_is_readme_document()` remains present and uncalled.

  Import the not-yet-created owners and run:

  ```bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_primitives.py
  ```

  Expected: FAIL on missing `retrieval_core` modules.

- [ ] **Step 2: Create the package marker and internal dataclasses**

  `retrieval_core/__init__.py` contains only a package docstring. It must not
  import or re-export submodule symbols.

  Move these classes to `types.py` without changing their class names, field
  order, defaults, decorators, repr, or equality behavior:

  - `_RankedChunk`;
  - `_ExpandedResult`.

  Change production annotations/constructors and tests to
  `core_types._RankedChunk` and `core_types._ExpandedResult`. Do not leave
  aliases in `retrieval.py`.

- [ ] **Step 3: Move the two distinct ordering semantics**

  Move and rename only:

  - `_dedupe()` -> `ordering.dedupe_lowered()`;
  - `_ordered_unique()` ->
    `ordering.ordered_unique_preserving_case()`;
  - `_RERANK_SORT_DECIMALS` -> `ordering.RERANK_SORT_DECIMALS`.

  Replace every production call explicitly. Do not combine the two dedupers;
  one lowercases its output and the other preserves the first spelling.

- [ ] **Step 4: Move shared evidence merge primitives**

  Move without policy changes:

  - `_bounded_score()` -> `evidence_merge.bounded_score()`;
  - `_merge_score_parts()` -> `evidence_merge.merge_score_parts()`;
  - `_merge_semantic_matches()` ->
    `evidence_merge.merge_semantic_matches()`;
  - `_semantic_match_sort_key()` as a private helper of `evidence_merge.py`.

  Candidate-source interpretation in `_normalized_score_parts()` does **not**
  move here; it remains for Task 3.

- [ ] **Step 5: Move shared relation policy values**

  Move exactly:

  - `MAX_EXPANSION_DEPTH`;
  - `MAX_EXPANSION_CANDIDATES`;
  - `_MIN_RELATION_CONFIDENCE`.

  In `retrieval.py`, define the two supported aliases by value:

  ```python
  MAX_EXPANSION_DEPTH = relation_policy.MAX_EXPANSION_DEPTH
  MAX_EXPANSION_CANDIDATES = relation_policy.MAX_EXPANSION_CANDIDATES
  ```

  Do not move `_RELATION_SCORE_DECAY` or `_SPRING_PATH_MAX_DEPTH`; they remain
  owned by their single future stage modules.

- [ ] **Step 6: Move the existing file-role value and predicates**

  Move bodies unchanged:

  - `_GenericFileRole`;
  - `_SOURCE_SUFFIXES`, `_TEMPLATE_SUFFIXES`, `_DOC_SUFFIXES`,
    `_CONFIG_SUFFIXES`, `_INDEXED_LOCKFILE_NAMES`, `_LOCKFILE_QUERY_TOKENS`;
  - `_looks_implementation_query()`;
  - `_has_explicit_lockfile_query()`;
  - `_is_generated_schema_path()`;
  - `_generic_file_role()`;
  - `_is_test_path()`;
  - the uncalled `_is_readme_document()`.

  Keep `source_boost`, `penalty`, and `penalty_key` values inside the
  classification result. Ranking conversion to signed score parts remains in
  `retrieval.py` until Task 5.

- [ ] **Step 7: Migrate tests and update the ledger atomically**

  Change existing direct private references to their new owners in the same
  edit as each production call. Update only imports/qualified names; preserve
  assertions and fixtures. Mark the types/ordering/evidence/file-role rows in
  `migration_ledger.json` with `remaining: 0` and `resolved_task: 2`.

  In the same task, remove independent test coupling to canonical incidental
  façade names:

  - use `context_search_tool.tokenizer.tokenize_query` instead of
    `retrieval.tokenize_query` in `test_retrieval_pipeline.py` and
    `test_quality_catalog.py`;
  - use `context_search_tool.chunker.expand_lines` instead of
    `retrieval.expand_lines`;
  - patch `context_search_tool.sqlite_store.SQLiteStore` instead of
    `retrieval.SQLiteStore` where the class object is the intended seam.

  Mark those incidental ledger rows resolved in Task 2. Supported façade rows
  remain `supported_facade` and are not required to reach zero.

  Verify no removed definition or alias remains:

  ```bash
  if rg -n '^def (_dedupe|_ordered_unique|_bounded_score|_merge_score_parts|_merge_semantic_matches)\b|^class (_RankedChunk|_ExpandedResult|_GenericFileRole)\b' \
      src/context_search_tool/retrieval.py; then
    exit 1
  fi
  ```

  Expected: no matches.

- [ ] **Step 8: Run Slice 2 gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_catalog.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  git diff --check
  ```

  Confirm
  `git hash-object tests/fixtures/retrieval_core_decomposition/baseline.json`
  still equals the Task 1 blob OID.

- [ ] **Step 9: Commit Slice 2**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/__init__.py \
    src/context_search_tool/retrieval_core/types.py \
    src/context_search_tool/retrieval_core/ordering.py \
    src/context_search_tool/retrieval_core/evidence_merge.py \
    src/context_search_tool/retrieval_core/relation_policy.py \
    src/context_search_tool/retrieval_core/file_roles.py \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_catalog.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval core primitives"
  ```

### Task 3: Extract Candidate Recall And Merge Stages

**Files:**

- Create: `src/context_search_tool/retrieval_core/candidates.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_quality_catalog.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`
- Modify: `tests/test_rerank_soft_sorting.py`
- Modify: `scripts/profile_retrieval.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Redirect candidate tests first and prove they fail**

  Change candidate-focused tests to import/patch
  `context_search_tool.retrieval_core.candidates`, including semantic provider
  and vector-store seams. Keep expected values unchanged.

  ```bash
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_quality_catalog.py
  ```

  Expected: collection/import failures until `candidates.py` exists.

- [ ] **Step 2: Move candidate-only constants and helpers**

  Move:

  - `_CJK_SEQUENCE_RE`, `_DIRECT_FRAGMENT_RE`,
    `_DIRECT_TEXT_TOP_K_MULTIPLIER`;
  - `_semantic_candidates()` -> `semantic_candidates()`;
  - `_lexical_candidates()` -> `lexical_candidates()`;
  - current path/symbol store call behind `path_symbol_candidates()`;
  - `_direct_text_probes()` -> `direct_text_probes()`;
  - `_signal_candidates()` -> `signal_candidates()`;
  - `_signal_score()` and `_metadata_text()` as private candidate helpers;
  - `_planner_hint_candidates()` -> `planner_hint_candidates()`;
  - `_merge_candidates()` -> `merge_candidates()`;
  - `_normalized_score_parts()` as a private candidate helper.

  Keep semantic fallback behavior, vector filtering, deleted-ID behavior,
  concrete list/dict shapes, and first-seen merge order byte-for-byte equivalent.

- [ ] **Step 3: Define the direct-text seam exactly**

  The new signatures are:

  ```python
  direct_text_probes(query, original_tokens) -> list[str]
  direct_text_candidates(store, probes, config) -> list[RetrievalCandidate]
  ```

  In `query_repository()`:

  1. compute probes once;
  2. start `direct_text_recall` with `input_count=len(probes)`;
  3. pass the existing list to `direct_text_candidates()`;
  4. stop the stage;
  5. observe only after stop.

  Do not retain the legacy helper signature that accepts query/tokens and
  recomputes probes inside the timed operation.

- [ ] **Step 4: Expand the four hidden initial stages in the orchestrator**

  Remove `_initial_candidates()`. Keep the following calls explicit and in this
  exact order:

  1. `semantic_candidates`;
  2. `lexical_candidates`;
  3. `path_symbol_candidates`;
  4. `direct_text_candidates`.

  Preserve executed variants, fallback status, timer input counts, source-count
  keys, and concatenation order.

- [ ] **Step 5: Use module-qualified calls for the remaining candidate stages**

  Change `signal_recall`, `planner_hint_recall`, `direct_merge`, and
  `candidate_merge` to call `candidates.<operation>()`. The orchestrator remains
  the only owner of stage start/stop and early-return branching.

- [ ] **Step 6: Atomically migrate direct calls and monkeypatch targets**

  In the same edit:

  - patch `candidates.provider_from_config` and `candidates.NumpyVectorStore`;
  - patch `candidates.semantic_candidates` and `candidates.merge_candidates`;
  - replace direct calls to old candidate helpers;
  - migrate the three `_direct_text_probes` calls in
    `test_rerank_soft_sorting.py`;
  - rewrite the hand-built `_initial_candidates()` flows in
    `test_retrieval_pipeline.py` and `test_quality_catalog.py` as the same four
    explicit recall calls;
  - update the candidate ledger rows to `remaining: 0`, `resolved_task: 3`.

  Do not leave a retrieval alias: a value alias would not forward a patch after
  the orchestrator changes owner.

  Convert the profiler's string-only target list into explicit
  `(display_name, owner_module, attribute_name)` tuples. Point the five candidate
  targets to `candidates` and their new names; leave later-stage tuples on their
  current owner until Tasks 4-7. Remove silent `getattr(..., None)` skipping:
  every configured target must exist, and `tests/test_profile_retrieval.py`
  proves its wrapper is hit.

- [ ] **Step 7: Run candidate and behavior gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_quality_catalog.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  if rg -n '_initial_candidates|retrieval\._(semantic_candidates|lexical_candidates|direct_text_probes|signal_candidates|planner_hint_candidates|merge_candidates)' \
      src tests; then
    exit 1
  fi
  git diff --check
  ```

  Expected: no old owner references; all fingerprints and the operation ledger
  remain exact.

- [ ] **Step 8: Commit candidate extraction**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/candidates.py \
    tests/test_retrieval_pipeline.py \
    tests/test_quality_catalog.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    scripts/profile_retrieval.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval candidate stages"
  ```

### Task 4: Extract Anchor And Relation Expansion

**Files:**

- Create: `src/context_search_tool/retrieval_core/expansion.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_quality_catalog.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`
- Modify: `scripts/profile_retrieval.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Redirect expansion tests and prove the owner is missing**

  Point anchor/relation tests at `retrieval_core.expansion`; preserve all exact
  score, order, cap, depth, store-call, and warning assertions. Run the focused
  tests and observe the expected missing-module failure.

- [ ] **Step 2: Move anchor expansion as one body-preserving unit**

  Move to `expansion.py`:

  - `anchor_candidates()` from `_anchor_expansion_candidates()`;
  - same-file and directory helper functions;
  - `_put_anchor_candidate()`;
  - `_is_document_or_config_anchor()`.

  Use `evidence_merge.bounded_score()` and
  `file_roles._generic_file_role()` through the reviewed low-level edges. Do not
  read source files, construct public results, or import ranking/candidates.

- [ ] **Step 3: Move relation expansion as one body-preserving unit**

  Move:

  - `_RelationSeed`;
  - `relation_candidates()` from `_relation_expansion_candidates()`;
  - relation-seed source priority and seed calculation;
  - `_RELATION_SCORE_DECAY`;
  - expansion-limit logging.

  Consume depth/cap/confidence from `relation_policy`. Preserve frontier order,
  store call batches, cap returns, score decay, exception behavior, and final
  `(-score, chunk_id)` ordering.

- [ ] **Step 4: Preserve logger identity exactly**

  Define:

  ```python
  logger = logging.getLogger("context_search_tool.retrieval")
  ```

  Keep warning level, template, argument, and count exact. Migrate the test
  logger target only if needed; do not change the externally observed logger
  name during P3.2.

- [ ] **Step 5: Change only stage operation calls in the orchestrator**

  Use:

  ```python
  expansion.anchor_candidates(...)
  expansion.relation_candidates(...)
  ```

  Keep `direct_merge`/`candidate_merge` in `candidates`, and keep all timer,
  trace-observation, and early-return code in `retrieval.py`.

- [ ] **Step 6: Migrate tests and close expansion ledger rows**

  Move every direct call and monkeypatch target in the same edit. Update
  `migration_ledger.json` to `remaining: 0`, `resolved_task: 4` for expansion
  names. Leave the uncalled `_candidate_base_score()` in `retrieval.py` for
  Task 5 and leave `_evidence_anchor_kind()` for Task 7.

  Point the profiler's anchor/relation tuples to `expansion.anchor_candidates`
  and `expansion.relation_candidates`. Replace the caplog dependency on
  `retrieval.__name__` with the preserved `expansion.logger.name`; mark that
  incidental row resolved. Run `test_profile_retrieval.py` to prove both targets
  exist and are wrapped.

- [ ] **Step 7: Run the complete Slice 3 gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_pipeline.py \
    tests/test_quality_catalog.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  if rg -n 'retrieval\._(anchor_expansion_candidates|relation_expansion_candidates)' tests; then
    exit 1
  fi
  git diff --check
  ```

  Expected: no old expansion references; exact fingerprints, full ledgers,
  warning tests, P3.1 stages, and full suite pass.

- [ ] **Step 8: Commit expansion extraction**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/expansion.py \
    tests/test_retrieval_pipeline.py \
    tests/test_quality_catalog.py \
    tests/test_retrieval_trace_pipeline.py \
    scripts/profile_retrieval.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval expansion stages"
  ```

### Task 5: Move Ranking As One Cohesive Policy Unit

**Files:**

- Create: `src/context_search_tool/retrieval_core/ranking.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_rerank_soft_sorting.py`
- Modify: `tests/test_quality_catalog.py`
- Modify: `scripts/profile_retrieval.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Redirect ranking imports without changing assertions**

  Migrate ranking-focused tests to `retrieval_core.ranking` and internal value
  construction to `retrieval_core.types`. This includes all 54 `_rank_chunks`
  references and every ranking constant/helper reference. Run the focused tests
  and confirm failure because `ranking.py` does not yet exist.

- [ ] **Step 2: Move the ranking entry points and local types**

  Move as one policy unit:

  - `_rank_chunks()` -> `rank_chunks()`;
  - `_ranked_chunk_sort_key()`;
  - `_apply_frontend_import_cohort_rerank()` ->
    `apply_frontend_import_cohort_rerank()`;
  - `_read_frontend_import_anchor()`;
  - `_ChunkRole` and `_SpringPathImplementor` with their existing private class
    names and unchanged fields.

  Construct and return `core_types._RankedChunk`. Do not add a score ledger,
  policy object, strategy registry, or new dataclass.

- [ ] **Step 3: Move ranking constants and all tightly coupled helpers**

  Move the existing route, Spring path, Java context, frontend cohort,
  identifier-intent, query-intent, project-scope, evidence, ceiling, and
  artifact-role constants and functions together. This includes:

  - chunk role, effective semantic, combined score, evidence class/priority;
  - strong/weak/direct/planner evidence predicates;
  - rerank score, rank tier, reasons, and sort keys;
  - route parsing/matching and route score parts;
  - Spring path traversal and role score parts;
  - Java context and route-tail score parts;
  - frontend import cohort scan/support behavior;
  - identifier/query-intent/project-scope adjustments;
  - generic noise score-part conversion and legacy generated/test penalty;
  - the pre-existing uncalled `_candidate_base_score()`.

  Preserve and test zero production callers for `_candidate_base_score()`; do
  not make the dead helper part of live ranking while moving it.

  Use only the reviewed low-level dependencies. In particular:

  - `ordering.RERANK_SORT_DECIMALS` owns shared rounding precision;
  - `evidence_merge` owns bounding and merge primitives;
  - `file_roles` owns generic role values/predicates;
  - `relation_policy` owns shared relation confidence/cap;
  - no ranking helper moves to a new micro-module.

- [ ] **Step 4: Preserve the supported score-normalization façade**

  Move the current `normalize_score()` implementation to
  `ranking.normalize_score()`. Define a real wrapper in `retrieval.py`:

  ```python
  def normalize_score(scores: list[float]) -> list[float]:
      return ranking.normalize_score(scores)
  ```

  Do not use `normalize_score = ranking.normalize_score`; the wrapper preserves
  `context_search_tool.retrieval` as `__module__` and keeps the supported
  signature explicit.

- [ ] **Step 5: Change only ranking and cohort operation calls**

  In the explicit orchestrator, call:

  ```python
  ranking.rank_chunks(...)
  ranking.apply_frontend_import_cohort_rerank(...)
  ```

  Do not move timers, observation, selection, bundle construction, or early
  returns into `ranking.py`.

- [ ] **Step 6: Review the extraction as a move, not a rewrite**

  Use:

  ```bash
  git diff --color-moved=dimmed-zebra -- \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/ranking.py
  ```

  Every non-import/non-qualification change requires a direct explanation. Reject
  cleanup, renamed score keys, reformatted policy tables, altered constants, or
  new exception handling.

- [ ] **Step 7: Migrate tests and close ranking ledger rows**

  Point direct imports to `ranking` or `core_types` and preserve every exact
  score/order assertion. Update ranking rows in `migration_ledger.json` to
  `remaining: 0`, `resolved_task: 5`. No private ranking alias remains in
  `retrieval.py`.

  Point the profiler's rank tuple to `ranking.rank_chunks` while preserving its
  display name. Run `test_profile_retrieval.py` to prove the wrapper is hit.

- [ ] **Step 8: Run the high-risk ranking gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_rerank_soft_sorting.py \
    tests/test_retrieval_pipeline.py \
    tests/test_quality_catalog.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_p3.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  git diff --check
  ```

  Confirm all four full-stage ledgers and every public byte hash remain exact.
  Any score or ordering mismatch blocks the task.

- [ ] **Step 9: Commit ranking extraction**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/ranking.py \
    tests/test_retrieval_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_quality_catalog.py \
    scripts/profile_retrieval.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval ranking core"
  ```

### Task 6: Extract Context Expansion And Span Handling

**Files:**

- Create: `src/context_search_tool/retrieval_core/context_expansion.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_rerank_soft_sorting.py`
- Modify: `scripts/profile_retrieval.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Redirect context-expansion tests and observe failure**

  Point tests for `_expand_ranked_chunks`, overlap merge, byte caps, line joins,
  sort keys, span sources, and span normalization to
  `retrieval_core.context_expansion`. Point `_ExpandedResult` construction to
  `retrieval_core.types`. Keep all exact expected content, line ranges, score
  parts, spans, and exceptions unchanged.

- [ ] **Step 2: Move context expansion and its constants**

  Move:

  - `_expand_ranked_chunks()` -> `expand_ranked_chunks()`;
  - `_SPAN_SOURCE_KEYS` and `_SPAN_SOURCE_SCORE_KEYS`;
  - content byte cap and expanded-result cap;
  - end-line calculation;
  - overlap grouping and merge;
  - expanded-result sort key;
  - exact context-line extraction/joining;
  - span source classification and normalization;
  - `_context_window()`.

  Use `core_types._RankedChunk` and `_ExpandedResult`,
  `ordering.RERANK_SORT_DECIMALS`, and shared evidence merge primitives. Do not
  import ranking, selection, tracing, the façade, or ContextPack.

- [ ] **Step 3: Preserve file and allocation behavior**

  Keep exact:

  - source `stat()` then `read_text()` order;
  - `OSError` fallback to indexed chunk content;
  - full-file byte-cap conditions;
  - `expand_lines()` arguments;
  - `_context_content` creation and trimming;
  - overlap winner choice and insertion/order semantics;
  - one resulting list and no generic stage-result wrapper.

  The operation ledger must prove the same file calls and arguments.

- [ ] **Step 4: Change only the context stage operation call**

  In `query_repository()`, replace the live operation with
  `context_expansion.expand_ranked_chunks(...)`. Keep start, stop, observation,
  rank-history, and final-selection code in place.

- [ ] **Step 5: Close context-expansion ledger rows**

  Update all direct imports and the migration ledger atomically. Require
  `remaining: 0`, `resolved_task: 6`. Do not leave old aliases in the façade.

  This includes the context-expansion imports/calls in
  `test_rerank_soft_sorting.py`. Point the profiler's expansion tuple to
  `context_expansion.expand_ranked_chunks`, preserve its display name, and prove
  it is hit with `test_profile_retrieval.py`.

- [ ] **Step 6: Run Slice 5a gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_trace_pipeline.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  if rg -n 'retrieval\._(expand_ranked_chunks|merge_overlapping_results|merge_expanded_result|span_sources)' tests; then
    exit 1
  fi
  git diff --check
  ```

- [ ] **Step 7: Commit context extraction**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/context_expansion.py \
    tests/test_retrieval_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    scripts/profile_retrieval.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval context expansion"
  ```

### Task 7: Extract Timed Selection And Post-Stop Output Assembly

**Files:**

- Create: `src/context_search_tool/retrieval_core/selection.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`
- Modify: `scripts/profile_retrieval.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Add failing tests for the two selection APIs**

  Test these separate responsibilities:

  ```python
  split_results_and_anchors(...)  # timed live selection only
  assemble_query_output(...)      # summary/results/follow-ups after stop
  ```

  Preserve the ordinary two-value overload and traced three-value overload.
  Assert that ordinary selection allocates no decision tuple/counter.

- [ ] **Step 2: Move final-selection types and exact literals**

  Move `_FinalTraceInput`, `_FinalTraceDecisions`, and decision-count keys to
  `selection.py`. Define selection-local literal aliases with exactly:

  - kinds: `"result"`, `"evidence_anchor"`;
  - reasons: `"selected_within_result_limit"`,
    `"selected_within_anchor_limit"`.

  Do not import `retrieval_trace`; Task 8 performs conversion after stage stop.

- [ ] **Step 3: Move timed split behavior unchanged**

  Move `_split_code_results_and_evidence_anchors()` to
  `split_results_and_anchors()`, including:

  - result and anchor limits;
  - duplicate anchor decisions;
  - exact decision counts/order;
  - `_evidence_anchor_from_expanded()`;
  - `_evidence_anchor_kind()`.

  This function is the complete `final_selection` timed live operation. It may
  convert selected anchors because current selection already does so; it may not
  summarize, construct `RetrievalResult`, or read summary data from the store.

- [ ] **Step 4: Move summary and result assembly after the timer**

  Move summary, per-result reason, signal/relation support, name classification,
  result conversion, and follow-up collection into `selection.py`. Include:

  - `_summarize_results()`, `_summarize_chunk()`, `_reasons_for_chunk()`;
  - `_chunk_has_relation_support()`;
  - primary/controller/implementation/related-type name helpers;
  - `_followup_keywords()`;
  - current inline `RetrievalResult` construction.

  Implement:

  ```python
  assemble_query_output(store, visible_results)
      -> tuple[RetrievalSummary, list[RetrievalResult], list[str]]
  ```

  Do not introduce an assembly dataclass. Preserve result order, reasons,
  `score_parts`, spans, content, `_context_content`, summary, and follow-ups.

- [ ] **Step 5: Keep `QueryBundle` construction in the façade**

  The orchestrator sequence must be:

  1. start `final_selection`;
  2. call `selection.split_results_and_anchors()`;
  3. stop the stage;
  4. convert/finish trace selection after stop when traced;
  5. call `selection.assemble_query_output()`;
  6. construct `QueryBundle` in `retrieval.py`;
  7. finish total trace after bundle construction.

  Task 8 supplies the final trace calls, but this ordering must already be
  visible and covered by the event test.

- [ ] **Step 6: Migrate tests and close selection ledger rows**

  Move direct imports/constructions to `selection` and `core_types`, preserve
  every assertion, and set selection rows to `remaining: 0`,
  `resolved_task: 7`. No selection helper alias remains in `retrieval.py`.

  Point the profiler's split and summary tuples to
  `selection.split_results_and_anchors` and selection's body-preserved private
  summary helper. Keep their existing display names and prove both wrappers are
  hit. Do not broaden summary timing to the whole output assembly.

- [ ] **Step 7: Run complete Slice 5 gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_profile_retrieval.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_quality_p2.py \
    tests/test_quality_p3.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  git diff --check
  ```

  Explicitly inspect the event ledger: summary store reads and result/bundle
  construction must occur after final-stage stop and before total trace finish.

- [ ] **Step 8: Commit selection extraction**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/selection.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_trace_pipeline.py \
    scripts/profile_retrieval.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval selection"
  ```

### Task 8: Extract Trace Adapters And Make Timing Order Explicit

**Files:**

- Create: `src/context_search_tool/retrieval_core/tracing.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/retrieval_core_characterization.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Redirect trace-adapter tests and observe failure**

  Point trace conversion/unit patches to `retrieval_core.tracing`; keep public
  end-to-end tests on `retrieval.trace_repository()`. Run the trace tests and
  confirm the new module is missing.

- [ ] **Step 2: Move trace-only conversion helpers**

  Move into `tracing.py`:

  - query metadata conversion;
  - candidate source parsing/counts;
  - candidate, ranked, and expanded observations;
  - rank-position generation;
  - adjustment extraction/bounds;
  - final-selection/rank-history conversion;
  - trace query recording and collector finalization.

  `tracing.py` may import `core_types`, `ordering`, `selection`, and
  `retrieval_trace`. It must not import the façade or any live stage owner.

- [ ] **Step 3: Expose narrow orchestrator-facing trace control functions**

  Implement the smallest concrete surface needed by `retrieval.py`:

  ```python
  start_stage(collector, name, input_count) -> StageToken | None
  stop_stage(collector, token) -> StoppedStage | None
  finish_count_stage(collector, stopped, output_count, unique_output_count)
  finish_candidate_stage(collector, stopped, store, candidates, source_keys=())
  finish_ranked_stage(collector, stopped, ranked, candidates)
  finish_expanded_stage(collector, stopped, expanded, candidates)
  finish_selection_stage(collector, stopped, decisions, candidates)
      -> tuple[TraceSelection, ...]
  finish_trace(collector, query metadata..., outcome, termination, selections=())
  ```

  These are internal package functions, not public user API. Keep conversion
  helpers private. Do not create generic event dictionaries or callbacks.

- [ ] **Step 4: Separate stop from every observation**

  Every stage in `query_repository()` must visibly follow:

  ```python
  token = tracing.start_stage(...)
  output = owner.operation(...)
  stopped = tracing.stop_stage(trace_collector, token)
  tracing.finish_<shape>_stage(trace_collector, stopped, output, ...)
  ```

  `finish_*` must never call `stop_stage`. Candidate preview store lookups,
  ranked/expanded projection, rank history, and final-selection conversion all
  occur after `stop_stage` returns. With `collector=None`, control functions may
  return immediately, but no observation adapter executes.

- [ ] **Step 5: Preserve early-return and total-duration placement**

  Keep exact outcomes and prefixes:

  - missing index -> `empty` / `missing_index` / no stages;
  - deleted-ID store error -> `partial` / `store_read_error` / no stages;
  - no candidates -> `empty` / `no_candidates` / stages 1-11;
  - success -> `complete` / `completed` / all 15 stages.

  On every successful/handled return, construct the exact `QueryBundle` first,
  then call `tracing.finish_trace()`. `trace_repository()` remains the only
  collector constructor and calls `query_repository()` exactly once.

- [ ] **Step 6: Enforce trace privacy structurally**

  `tracing.py` may use paths, line ranges, scores, reasons, sources, variants,
  and internal decision values. It must never access `.content` or
  `._context_content`. Run AST and sentinel tests for complete, missing-index,
  store-error, no-candidate, and propagated-error paths. Keep both feedback
  writers forbidden.

- [ ] **Step 7: Remove trace imports and helpers from the façade**

  `retrieval.py` retains only the public trace type annotation/collector
  construction needed by `TracedQueryBundle` and `trace_repository()`. Move all
  trace adapters and trace-only constants. Use module-qualified calls; leave no
  `_trace_*` function or `_FinalTrace*` class in the façade.

- [ ] **Step 8: Migrate patches and close trace ledger rows**

  Patch `tracing` owners or the canonical `retrieval_trace` module, never a stale
  façade value. Update every trace row to `remaining: 0`, `resolved_task: 8`.

  Update `tests/retrieval_core_characterization.py` so its existing trace-wrapper
  targets point to `retrieval_core.tracing`. A focused test must prove this task
  changes only the owner-target mapping: ledger field construction,
  serialization order, projection schema/version, normalization, and baseline
  hash remain byte-identical.

  Migrate any test patch of incidental `retrieval.RetrievalTraceCollector` to
  the canonical `retrieval_trace` owner and make `trace_repository()` construct
  through the same module-qualified seam.

- [ ] **Step 9: Run Slice 6 high-risk gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_quality_p3.py
  PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
  if rg -n '^def _trace_|^class _FinalTrace' \
      src/context_search_tool/retrieval.py; then
    exit 1
  fi
  git diff --check
  ```

  Expected: no old trace definitions; exact trace-envelope bytes, timing event
  order, early-return prefixes, privacy, feedback isolation, and full suite pass.

- [ ] **Step 10: Commit trace extraction**

  ```bash
  git add \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/tracing.py \
    tests/retrieval_core_characterization.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_retrieval_pipeline.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "refactor: extract retrieval trace adapters"
  ```

### Task 9: Close Strict Boundaries And Compatibility Gates

**Files:**

- Modify: `tests/test_retrieval_core_boundaries.py`
- Modify: `tests/test_retrieval_core_characterization.py`
- Modify: `tests/fixtures/retrieval_core_decomposition/migration_ledger.json`

- [ ] **Step 1: Enable the final AST adjacency allowlist**

  Remove the transitional allowlist. Assert the exact final table from this
  plan, no cycles, no star imports, no `retrieval_core -> retrieval`, no broad
  package re-export, and no core `retrieval_trace` import except `tracing.py`.

- [ ] **Step 2: Enforce the exact façade definition set**

  Parse `retrieval.py` and permit only these top-level definitions:

  - `QueryBundle`;
  - `TracedQueryBundle`;
  - `query_repository`;
  - `trace_repository`;
  - `evidence_anchor_top_k`;
  - `normalize_score`.

  Permit the two supported `MAX_EXPANSION_*` assignments. Reject every other
  local stage helper/class, any private re-export alias, and any aliased import
  that recreates an old private name. This task is a gate, not a cleanup slice:
  any failure means the responsible Task 2-8 slice is incomplete and must be
  corrected and re-verified there before continuing.

- [ ] **Step 3: Require the migration ledger to be fully closed**

  Every `migrate` row must have `remaining: 0` and a non-null `resolved_task`.
  Every `supported_facade` row must still resolve to the same façade symbol and
  retain its contract; it is not expected to reach zero.

  Re-run the same AST inventory over `tests/` and `scripts/profile_retrieval.py`
  rather than trusting ledger fields. Permit `retrieval.<attr>` and
  `from ...retrieval import ...` only for the eight supported façade symbols;
  reject private names, incidental names such as `tokenize_query`, `expand_lines`,
  `SQLiteStore`, `NumpyVectorStore`, `provider_from_config`, and
  `RetrievalTraceCollector`, and stale dynamic profiler names.

  The quick private scan remains a supplemental diagnostic:

  ```bash
  if rg --pcre2 -n 'retrieval\._(?!_)' tests; then
    exit 1
  fi
  ```

  Expected: no matches. The AST test separately rejects unsupported
  `from context_search_tool.retrieval import ...` names.

- [ ] **Step 4: Prove the protected-source boundary**

  ```bash
  if git diff --name-only \
      34c5b5bd2189fbba4ead3902342706266c399b41 -- \
      src/context_search_tool | \
      rg -qv '^src/context_search_tool/(retrieval\.py|retrieval_core/)'; then
    git diff --name-only \
      34c5b5bd2189fbba4ead3902342706266c399b41 -- \
      src/context_search_tool | \
      rg -v '^src/context_search_tool/(retrieval\.py|retrieval_core/)'
    exit 1
  fi

  test -z "$(git status --porcelain=v1 --untracked-files=all -- \
    src/context_search_tool)"

  git diff --exit-code \
    34c5b5bd2189fbba4ead3902342706266c399b41 -- \
    src/context_search_tool/retrieval_trace \
    src/context_search_tool/context_pack \
    src/context_search_tool/quality \
    src/context_search_tool/models.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/formatters.py \
    src/context_search_tool/mcp_server.py \
    src/context_search_tool/mcp_tools.py
  ```

  The conditional block must not enter, the clean-status assertion must pass,
  and the final protected-path diff must exit zero.

  The clean-status assertion is essential: `git diff` cannot see an untracked
  file under a protected package. At this point Tasks 2-8 are committed, so no
  source worktree change is expected.

- [ ] **Step 5: Verify input identity, baseline immutability, and exact skip/xfail state**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_characterization.py::test_characterization_inputs_match_frozen_identity
  git hash-object \
    tests/fixtures/retrieval_core_decomposition/baseline.json
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q -rs \
    --junitxml=/tmp/cst-p3-2-final.xml
  ```

  The first test recomputes the catalog/snapshot Git OIDs, working-tree content
  hashes, and tracked/staged/unstaged/untracked cleanliness recorded in Task 1.
  Compare the blob OID to Task 1. Parse the JUnit file with the test helper and
  compare exact skip/xfail node IDs and reasons to the Slice 1 manifest. Any
  input-identity, count, or reason change is a failure even if the suite is green.

- [ ] **Step 6: Run the complete structural and behavioral gate**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_pipeline.py \
    tests/test_rerank_soft_sorting.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_catalog.py \
    tests/test_quality_p2.py \
    tests/test_quality_p3.py
  git diff --check
  ```

- [ ] **Step 7: Commit strict boundary closure**

  ```bash
  git add \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py \
    tests/fixtures/retrieval_core_decomposition/migration_ledger.json
  git commit -m "test: close retrieval core decomposition boundaries"
  ```

### Task 10: Run Final Acceptance And Record Evidence

**Files:**

- Modify: `docs/retrieval-quality.md`
- Modify: `docs/superpowers/specs/2026-07-16-p3-2-retrieval-core-decomposition-design.md`
- Modify: `docs/superpowers/plans/2026-07-16-p3-2-retrieval-core-decomposition.md`
- Modify: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

- [ ] **Step 1: Run the full suite with machine-readable skip evidence**

  ```bash
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q -rs \
    --junitxml=/tmp/cst-p3-2-final.xml
  ```

  Record passed/skipped/xfail totals and exact skip/xfail comparison. Do not
  silently accept a new skip.

- [ ] **Step 2: Run focused P3.1/P3.2 acceptance**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_quality_p3.py \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_retrieval_core_characterization.py
  ```

  Record TraceCoverage 1.0 for every committed non-empty case and exact
  thirteen-case/four-ledger parity.

- [ ] **Step 3: Run P2 and raw-CI quality profiles**

  ```bash
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output /tmp/cst-p3-2-p2.json \
    --markdown /tmp/cst-p3-2-p2.md

  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output /tmp/cst-p3-2-ci.json \
    --markdown /tmp/cst-p3-2-ci.md
  ```

  Required: P2 selected/executed/passed 5/5/5; raw CI 8/8/8; no failed case or
  error. Phase 1 remains documented at 6/7; this task does not reclassify it.

- [ ] **Step 4: Capture exact commit and fixture evidence**

  ```bash
  git log --oneline --decorate \
    --grep='retrieval core\|retrieval candidate\|retrieval expansion\|retrieval ranking\|retrieval context\|retrieval selection\|retrieval trace adapters'
  git hash-object \
    tests/fixtures/retrieval_core_decomposition/baseline.json
  git diff --check
  git status --short
  ```

  Record:

  - Slice 1 baseline commit and blob OID;
  - catalog blob OID, four snapshot tree OIDs, content hashes, and final clean
    input-identity result;
  - Tasks 2-9 commit IDs;
  - full/focused/quality counts;
  - protected-source diff result;
  - final module ownership and import adjacency result;
  - Phase 1 still 6/7.

- [ ] **Step 5: Update documentation conditionally**

  Only after all gates pass:

  - append a P3.2 acceptance section to `docs/retrieval-quality.md`;
  - change the design and plan status to implemented/verified;
  - record the exact Slice 1 and Tasks 2-9 implementation/verification commits;
  - do not try to embed the Task 10 documentation commit ID inside that same
    commit; report it after commit in the hand-off evidence;
  - mark only P3.2 and Phase 3 complete in the roadmap;
  - set the next-stage review to Phase 4 controlled multi-round exploration
    design review;
  - preserve Phase 1 at 6/7 and retain Phase 4+ scope unchanged.

  If any gate fails, document the blocker in the implementation branch and leave
  P3.2/Phase 3 open.

- [ ] **Step 6: Commit verification evidence**

  ```bash
  git add \
    docs/retrieval-quality.md \
    docs/superpowers/specs/2026-07-16-p3-2-retrieval-core-decomposition-design.md \
    docs/superpowers/plans/2026-07-16-p3-2-retrieval-core-decomposition.md \
    roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
  git commit -m "docs: verify retrieval core decomposition"
  ```

## Stop Conditions

Stop the implementation and request review if any of these occurs:

- the immutable baseline must change;
- a score, ordering, count, byte hash, stage ledger, or operation ledger differs;
- a protected production file appears necessary to edit;
- a stage owner needs an unlisted core dependency;
- a monkeypatch can only be preserved with a forwarding alias;
- ordinary queries construct a trace-only value or add an operation;
- observation must occur before stage stop;
- output assembly must move inside `final_selection` timing;
- source content or absolute paths appear in trace/baseline data;
- a new skip/xfail appears or an existing reason changes;
- ranking redesign, P4 behavior, or a new API/config surface appears necessary.

These are design-boundary failures, not opportunities for an implementation
agent to improvise a broader solution.

## Final Review Checklist

Before requesting implementation review, verify:

- [ ] every design acceptance criterion maps to a concrete task and test;
- [ ] every new production module has one owner and only allowed imports;
- [ ] all fifteen stages remain explicit and in canonical order;
- [ ] direct-text probes are computed once before the timer;
- [ ] every stage shows operation -> stop -> observation;
- [ ] final output assembly is after final-stage stop and before total finish;
- [ ] all 13 cases, four full ledgers, and both 13-case operation ledgers use the
  immutable baseline;
- [ ] catalog/snapshot OIDs, content hashes, and clean input state still match
  the immutable manifest;
- [ ] both result and evidence-anchor hidden content are hashed, never stored;
- [ ] public bundle identity and all eight supported façade symbols remain exact;
- [ ] all private direct imports and monkeypatch targets have an atomic owner move;
- [ ] no temporary alias or stale façade reference remains;
- [ ] full suite skip/xfail node IDs and reasons match Slice 1;
- [ ] P2 is 5/5, raw CI is 8/8, TraceCoverage is 1.0;
- [ ] Phase 1 remains 6/7;
- [ ] protected source is unchanged outside `retrieval.py`/`retrieval_core/`;
- [ ] baseline commit/blob and all implementation commits are recorded;
- [ ] Phase 4+ work has not begun.

## Plan Review Rubric

Independent plan review must check:

1. whether the task order can keep every focused commit green;
2. whether Slice 1 can produce and later verify the immutable manifest without
   production instrumentation;
3. whether every current retrieval helper/constant has exactly one final owner;
4. whether the adjacency table is implementable without a cycle;
5. whether monkeypatch and direct-import migrations are atomic and complete;
6. whether ranking moves as one policy unit without disguised redesign;
7. whether context selection/tracing timing is executable as written;
8. whether public bytes, hidden content, full candidates, operation order,
   early returns, privacy, and feedback isolation have independent gates;
9. whether commit boundaries and stop conditions prevent expected-value drift;
10. whether any task accidentally begins P4, closes Phase 1, or edits a protected
    production surface.

Any unresolved blocker or major finding keeps this plan in draft status.

## Agent Review Record

Three independent read-only reviewers examined the first complete plan from
architecture, contract-preservation, and migration-feasibility perspectives.
The first round did not pass. It found missing test consumers in Tasks 2, 3,
and 6; an untracked dynamic profiling consumer; incomplete input and operation
ledger freezing; a characterization-wrapper staging omission; regex-only
reference discovery; ambiguous supported-versus-migrated closure; environment
drift; shell gates that treated `rg`'s correct empty result as failure; and a
Task 10 commit self-reference.

The plan and design were revised to:

- inventory tests and profiler targets with AST plus explicit dynamic-target
  parsing, then freeze the final Slice 1 ledger only after all Slice 1 tests;
- migrate every owner, production call, direct test, monkeypatch, profiler
  target, and ledger row atomically;
- freeze catalog/snapshot Git identities and content hashes and recheck them on
  every characterization run;
- record independent ordinary and traced operation ledgers for all 13 cases;
- preserve characterization projection bytes while moving only wrapper targets;
- enforce a per-shell clean environment, exact skip/xfail identity, protected
  tracked/untracked source boundaries, and executable empty-result shell gates;
- make Task 9 a pure closure gate and report the Task 10 commit only after it is
  created.

All three reviewers then performed targeted second passes against the current
design, plan, roadmap, implementation baseline, tests, and profiler:

- architecture: PASS; blocker/major/minor: none;
- contract preservation: PASS; blocker/major/minor: none;
- migration feasibility: PASS; blocker/major/minor: none.

This review approves the implementation plan and its task/commit boundaries. It
does not claim that P3.2 implementation or acceptance has begun.
