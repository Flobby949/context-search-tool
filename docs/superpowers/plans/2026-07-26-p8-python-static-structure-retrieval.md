# P8 Python Static Structure Retrieval v1 Implementation Plan

Date: 2026-07-26
Status: Ready for review; implementation not authorized or started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `75cc65ed627dd5982460a4d4a10d28f10e7151b8`
Design:
`docs/superpowers/specs/2026-07-26-p8-python-static-structure-retrieval-design.md`
Predecessor:
`docs/superpowers/plans/2026-07-26-p7-final-path-diverse-evidence-selection.md`

## Objective

Implement one attributable Python structural-retrieval slice:

```text
stdlib Python AST
  -> declarations
  -> static repository-local module imports
  -> existing schema-v5 resolver
  -> existing exact test association
  -> existing relation expansion/ranking
  -> unchanged P7 path-diverse final selection
```

The implementation is successful only when:

- the structural contract is exact, deterministic, bounded, lifecycle-safe, and
  non-executing;
- both pinned Python repositories show the reviewed retrieval benefit;
- every claimed improvement is backed by a persisted exact import relation;
- no relation weight, generic ranking rule, result budget, query plan, or P7
  selector is changed;
- all protected P5/P6/P7 and full-suite gates pass;
- implementation stops before Python call edges or file-level reranking.

## Authorization And Git Boundary

This plan is a design artifact. Do not begin Task 0 product/fixture work until
the user explicitly authorizes implementation.

Even after implementation is authorized:

- do not stage, commit, amend, push, create a branch, or open a pull request
  unless the user separately asks;
- use detached temporary worktrees/snapshots for baseline comparison;
- do not modify or index the user's original RedInk or
  `daily_stock_analysis` directories;
- preserve unrelated working-tree changes;
- do not edit P6 benchmark policy to make a transient benchmark pass.

## Fixed Assumptions

1. Behavior comparison remains anchored to
   `75cc65ed627dd5982460a4d4a10d28f10e7151b8` even if these Markdown files are
   later committed separately.
2. The supported local acceptance runtime is:

   ```text
   .quality/p5-runtime/bin/python
   Python 3.13.12
   SQLite 3.51.2
   ```

3. Every Python command explicitly sets `PYTHONPATH="$PWD/src"` or points
   `PYTHONPATH` at the detached implementation root under test.
4. Hash embeddings and planner-off execution are the deterministic real-profile
   baseline.
5. Schema-v5 fields and relation kind `imports` are sufficient. P8 does not
   create schema 6.
6. Existing `test_association.py` should work without a product edit. The one
   reviewed generic resolver edit is the module-candidate ambiguity guard for
   active paths without core signals; no Python-specific lookup path is added.
7. The current P6 group has 81 tests. A previously observed resident benchmark
   node failed transiently once and passed in isolated, group, and full-suite
   reruns. Treat a recurrence as a benchmark investigation, not P8 scope.
8. The current accepted full suite is 2,900 passed and 9 established skips.

## Non-Negotiable Scope

### Product Work Allowed

- new `PythonGraphProducer`;
- Python declaration symbols/signals;
- static module import relations;
- one generic module-candidate ambiguity guard for active paths without core
  signals;
- one internal graph producer-contract metadata version;
- one language-neutral import reason;
- tests, synthetic fixtures, pinned benchmark inputs/evidence;
- completion docs after acceptance.

### Product Work Forbidden

- Python call, inheritance, decorator, framework, type, data-flow, or runtime
  import relations;
- rank/penalty/weight tuning;
- new query rewrite, route, model, or planner logic;
- new retrieval stage, recursive traversal, result/ContextPack/trace schema;
- candidate/result/context/exploration budget changes;
- P7 selection changes;
- executing or importing target repository code;
- copying target repository source into tracked fixtures.

If a RED test cannot be made green without forbidden work, stop and revise the
design rather than broadening the implementation.

## Success Criteria

The implementation loop uses these verifiable goals:

1. **Structure:** exact fixture projection for declarations/import selectors.
2. **Lifecycle:** a pre-P8 ready-v5 index reparses once, reaches ready, and then
   no-ops; future producer versions never downgrade.
3. **Resolution:** only exact/unique same-unit Python imports traverse.
4. **Association:** explicit Python test imports create exact existing `tests`
   relations and remain intent-gated.
5. **Retrieval:** imported relevant modules gain existing relation provenance
   without score-policy changes.
6. **Real value:** all design ship gates pass on RedInk and the daily core
   slice.
7. **Compatibility:** protected tests, P6, P7, quality, and full suite pass.
8. **Auditability:** final diff and tracked artifacts match the reviewed
   allowlist and contain no local/private source material.

## Command Convention

At implementation start:

```bash
export P8_REPO_ROOT="$PWD"
export P8_RUNTIME="$PWD/.quality/p5-runtime/bin/python"
export P8_BEHAVIOR_BASELINE="75cc65ed627dd5982460a4d4a10d28f10e7151b8"
test "$(git rev-parse --show-toplevel)" = "$P8_REPO_ROOT"
test -x "$P8_RUNTIME"
```

Run tests through:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q
```

Do not use an installed stale copy of `context_search_tool`.

For a detached baseline worktree:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_BASELINE_WORKTREE/src" \
  "$P8_RUNTIME" -m context_search_tool.cli --help
```

All real-repository paths are prepared under a task-specific `.quality` or
`mktemp -d` directory. No command targets either user-supplied local source
directory for indexing or writing.

## Planned File Map

### Product

| action | path | purpose |
| --- | --- | --- |
| create | `src/context_search_tool/python_graph.py` | AST facts, declaration projections, import selectors/relations |
| modify | `src/context_search_tool/plugins.py` | default producer registration |
| modify | `src/context_search_tool/graph_contract.py` | `MAX_PYTHON_IMPORTS_PER_FILE` |
| modify | `src/context_search_tool/graph_lifecycle.py` | graph producer metadata/version/read rules |
| modify | `src/context_search_tool/sqlite_store.py` | producer version initialization/final-ready persistence |
| modify | `src/context_search_tool/indexer.py` | producer-contract stale reason/activation plumbing |
| modify | `src/context_search_tool/graph_resolution.py` | preserve multi-path module ambiguity when an active candidate has no core signal |
| modify | `src/context_search_tool/retrieval_core/relation_policy.py` | language-neutral import reason |

### Focused Tests

| action | path | purpose |
| --- | --- | --- |
| create | `tests/test_python_graph.py` | parser, declarations, selectors, materialization |
| modify | `tests/test_graph_lifecycle.py` | missing/current/invalid/future producer versions |
| modify if required | `tests/test_graph_store.py` | initialization and both ready-publication metadata paths |
| modify if required | `tests/test_index_health.py` | stale/current/future health projection |
| modify if required | `tests/test_indexer_manifest.py` | producer-contract stale activation |
| modify | `tests/test_graph_resolution.py` | Python exact/ambiguous/external module rows |
| modify | `tests/test_incremental_refresh.py` | activation/no-op/change/delete/recovery |
| modify | `tests/test_test_association.py` | Python import-derived exact association |
| modify | `tests/test_resolved_graph_expansion.py` | existing import traversal and protected behavior |
| modify | `tests/test_retrieval_pipeline.py` | end-to-end Python relation retrieval/P7 selection |
| modify | `tests/test_p5_explain.py` | Python explain projection if existing coverage does not reach it |
| modify if required | `tests/test_exploration_p7.py` | one Python end-to-end P7 witness |
| create | `tests/test_p8_graph_contract.py` | deterministic structural fixture projection |

### Synthetic And Real Quality

| action | path | purpose |
| --- | --- | --- |
| create | `tests/fixtures/p8-python-graphs/` | authored positive/negative Python project |
| create | `tests/fixtures/p8_python_graphs/input_manifest.json` | protected sources, inventories, queries, roles, hashes |
| create | `tests/fixtures/retrieval_quality/p8_python_graphs.json` | standard quality catalog |
| create | `tests/p8_python_graph_identity.py` | constants and protected-input validation |
| create | `tests/generate_p8_python_graph_manifest.py` | deterministic manifest/projection generation |
| create | `tests/p8_real_python_graphs_acceptance.py` | paired stage trajectory and ship-gate evaluation |
| create | `tests/test_p8_real_python_graphs_acceptance.py` | runner identity, privacy, comparison, and negative gate tests |

### Completion Documentation

Update only after candidate acceptance:

- `README.md`;
- `docs/retrieval-quality.md`;
- `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`;
- this plan's implementation record.

Do not edit the historical P5/P7/P7A design/plan documents.

## Task 0: Freeze Entry State, Source Identity, Gold, And Baseline

**Goal:** Make candidate-independent evidence immutable before product code.

**Product changes:** none.

### Step 0.1: Audit The Worktree

Run:

```bash
git status --short --branch
git rev-parse HEAD
git diff --check
```

Expected at plan entry:

```text
HEAD = 75cc65ed627dd5982460a4d4a10d28f10e7151b8
```

The two P8 Markdown files may be untracked/modified if they have not yet been
committed. Record them explicitly. Any other path is user-owned until proven
otherwise.

### Step 0.2: Verify Runtime And Accepted Gates

Run:

```bash
"$P8_RUNTIME" -VV
"$P8_RUNTIME" -c 'import sqlite3; print(sqlite3.sqlite_version)'
```

Run the focused current graph/P7 entry gate:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_graph_lifecycle.py \
  tests/test_graph_resolution.py \
  tests/test_test_association.py \
  tests/test_resolved_graph_expansion.py \
  tests/test_incremental_refresh.py \
  tests/test_retrieval_pipeline.py \
  tests/test_exploration_p7.py
```

Record pass count and duration. Do not redefine the accepted full-suite
baseline from a partial run.

### Step 0.3: Create A Detached Behavior Baseline

Use a new explicit temporary directory:

```bash
export P8_BASELINE_ROOT="$(mktemp -d /private/tmp/cst-p8-baseline.XXXXXX)"
export P8_BASELINE_WORKTREE="$P8_BASELINE_ROOT/context-search-tool"
git worktree add --detach \
  "$P8_BASELINE_WORKTREE" \
  "$P8_BEHAVIOR_BASELINE"
test "$(git -C "$P8_BASELINE_WORKTREE" rev-parse HEAD)" = \
  "$P8_BEHAVIOR_BASELINE"
```

Do not add a branch. Do not remove an existing path or reuse a prior evidence
directory.

### Step 0.4: Verify Pinned External Sources

Freeze:

```text
RedInk
  URL: https://github.com/HisMax/RedInk.git
  commit: 4d48722344594cf00e0498f0e1ed3df9cd4fd6be
  include: backend/**/*.py, tests/**/*.py, pyproject.toml

daily_stock_analysis
  URL: https://github.com/ZhuLinsen/daily_stock_analysis.git
  commit: 487e49e565ffd1b96a7cf4d855f99cee3c981eaa
  include: data_provider/**/*.py, src/**/*.py,
           tests/test_data_fetcher_prefetch_stock_names.py
```

Use the existing quality repository preparer or detached clones under
`$P8_BASELINE_ROOT`. Verify:

- exact `HEAD`;
- exact HTTPS origin;
- no local modifications;
- RedInk selected inventory is 28 files;
- daily selected inventory is 203 files;
- selected source content hash and sorted inventory hash;
- no `.env`, local provider YAML, history, images, database, log, or
  `.context-search` path is selected.

Do not derive a source identity from the user's local dirty directories.

### Step 0.5: Freeze Gold Before Candidate Output Exists

Create the data-only inputs:

- `tests/fixtures/p8_python_graphs/input_manifest.json`;
- `tests/fixtures/retrieval_quality/p8_python_graphs.json`;
- `tests/p8_python_graph_identity.py`;
- `tests/generate_p8_python_graph_manifest.py`.

The manifest must contain:

- schema version;
- CST behavior baseline;
- both source URLs/commits/include patterns;
- selected source inventory hash;
- all 18 exact query strings;
- every required/contextual path;
- role and necessity;
- exact expansion of every prose contextual category;
- the closed-world rule that every selected ordinary path outside the frozen
  required/contextual set is noise;
- gold-review note;
- manifest hash.

The catalog uses only existing quality-case fields and projects all 18 cases as
`mode="results"` with `gate="informational"`. Custom role/trajectory metadata,
ship gates, and ContextPack/exploration witnesses stay in the P8 input manifest
and acceptance script.

Run manifest validation before any candidate index exists:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" tests/generate_p8_python_graph_manifest.py \
  --check
```

If source inspection changes a proposed gold:

1. record the correction and reason;
2. update it now;
3. rerun `--check`;
4. freeze the new manifest hash.

After the first candidate run, gold changes are forbidden without an explicit
review reset.

### Step 0.6: Capture The P7 Baseline Projection

Before adding the P8 runner, use existing public query/trace APIs or an ignored
temporary diagnostic to capture:

- stage acquisition/rank for all gold paths;
- selected path order;
- score parts/reasons;
- relation-expansion count;
- unique paths;
- ContextPack/exploration witnesses named by the design;
- structural counts from the ready graph.

Minimum verified baseline:

```text
RedInk: 28 files, 87 chunks, 0 symbols, 25 core modules, 0 relations
daily: 203 files, 1,596 chunks, 0 symbols, 201 core modules, 0 relations
```

For the frozen daily continuity query verify:

```text
12 selected results
12 unique selected paths
src/core/pipeline.py present
data_provider/base.py present
relation expansion count = 0
```

Store raw baseline outputs only under the task evidence root, not tracked docs.
Tracked artifacts contain normalized hashes/projections, not source bodies.

### Step 0.7: Task 0 Gate

Task 0 is complete only when:

- source and gold hashes are frozen;
- no product file changed;
- candidate output has not influenced gold;
- both user originals remain byte/metadata untouched by CST;
- baseline rank trajectories are reproducible twice;
- `git diff --check` passes.

If any source identity cannot be reproduced, stop before AST work.

## Task 1: RED/GREEN Pure Python AST Facts

**Goal:** Parse Python bytes into bounded, deterministic facts without
materializing graph rows.

**Files:**

- create `src/context_search_tool/python_graph.py`;
- create `tests/test_python_graph.py`;
- create the initial `tests/fixtures/p8-python-graphs/` files.

### Step 1.1: Author The Synthetic Fixture

Use only original minimal code. Include:

```text
pyproject.toml
__init__.py
app/__init__.py
app/api.py
app/service.py
app/clients/__init__.py
app/clients/text.py
app/dupe.py
app/dupe/__init__.py
app/dynamic.py
app/broken.py
src/payments/__init__.py
src/payments/engine.py
tests/test_service.py
nested/pyproject.toml
nested/pkg/__init__.py
nested/pkg/consumer.py
nested/pkg/target.py
lonely.py
```

Facts represented by the fixture:

- module-level class, sync function, async function;
- direct class methods and a nested class method;
- conditional module/class-scope declarations and excluded function-scope
  declarations;
- nested function/class inside a function, which must be excluded;
- top-level, aliased, multi-name, relative, star-source, and function-local
  imports;
- root and `src` import roots;
- project-unit-root and nested package `__init__.py` behavior;
- `.py` versus package-`__init__` ambiguity;
- external and escaping imports;
- dynamic `importlib` / `__import__`, which emit no import fact;
- malformed syntax;
- nested project-unit boundary;
- explicit Python test import.

Use inline byte strings, not a tracked non-UTF-8 file, for encoding-cookie tests.

### Step 1.2: Write RED Parser Tests

Test a pure seam such as:

```python
extract_python_facts(file_path: str, content: bytes) -> PythonFactSet
```

Required RED assertions:

- only declared inclusion-boundary classes/functions/methods appear;
- async state and owner qualified name are exact;
- undecorated and earliest-decorator start ranges, declaration ends, and UTF-8
  byte columns are exact;
- every supported import form produces the reviewed raw fact;
- nested/static imports are collected with their source range;
- dynamic imports produce no fact;
- source order is canonical;
- syntax/encoding/recursion failures return bounded diagnostics;
- exception text/source lines are absent from metadata;
- 4,096 ordered declarations retain the canonical first 4,095 and record one
  omission before symbols reach chunking;
- repeated runs return equal frozen facts.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  -k 'facts or parse or declaration or import_syntax or malformed or encoding'
```

Expected: failures because the module/seam does not exist.

Save the RED test node names and concise failure reasons in the implementation
record.

### Step 1.3: Implement The Minimum Fact Extractor

In `python_graph.py`:

- use `compile(..., ast.PyCF_ONLY_AST | ast.PyCF_TYPE_COMMENTS, ...)`;
- convert AST nodes immediately to frozen facts;
- do not retain AST nodes;
- use an explicit ownership walk that excludes function-local declarations but
  still observes static imports anywhere;
- catch only reviewed per-file failures;
- sort facts explicitly;
- emit bounded diagnostic code/count.

Do not import CST store, retrieval, CLI, MCP, quality, or external parser
modules.

### Step 1.4: GREEN And Determinism

Run the RED selection twice:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  -k 'facts or parse or declaration or import_syntax or malformed or encoding'
```

Then:

```bash
git diff --check
```

Task 1 stops at facts. Do not register the producer or emit graph relations yet.

## Task 2: RED/GREEN Declaration Symbols And Signals

**Goal:** Project reviewed declarations into existing `SymbolRef` and
schema-v5 `CodeSignal` objects with no import relations yet.

**Files:**

- modify `src/context_search_tool/python_graph.py`;
- extend `tests/test_python_graph.py`;
- modify `src/context_search_tool/graph_contract.py` only when adding the
  import cap in Task 3, not preemptively.

### Step 2.1: Write RED Materialization Tests

Construct `PluginContext`, generic chunks, and a core module signal using
existing test helpers.

Assert:

- `supports()` accepts `.py` and `.pyw` by suffix even with a scanner-language
  mismatch, and rejects `.pyi`, `.PY`, and other suffixes even if labeled
  `python`;
- class -> `type`, top-level function -> `function`, class member -> `method`;
- every signal has producer `python_ast`, language `python`,
  `recallable=True`, `signature=""`, `arity=None`;
- declaration qualified names always use the project-unit-root projection,
  while root/`src` alternate spellings resolve to the same module path;
- `__init__.py` declaration names use the containing package;
- project-unit-root `__init__.py` uses the stable declaration identity
  `__init__` and resolves only closed sibling-relative imports;
- symbol kinds/names/ranges match the design;
- signal IDs equal direct `generate_v5_signal_id()` results;
- signals attach to the containing start-line chunk;
- missing chunk attachment fails the producer closed for that file;
- at most 4,095 declaration symbols/signals survive, reserving the existing
  4,096th signal slot for the core module;
- forward/reverse fact input produces identical sorted signals.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  -k 'supports or symbol or signal or qualified or chunk or signal_cap'
```

Expected: RED for missing projection/materialization.

### Step 2.2: Implement Declaration Projection

Add:

- `PythonGraphProducer`;
- `parse()` returning symbols, evidenced lexical tokens, and parse metadata;
- declaration materialization through the existing v5 identity helper;
- explicit signal ordering;
- closed missing-chunk metadata behavior.

Do not register it in `default_plugins()` yet. Direct tests instantiate it.

### Step 2.3: Verify Chunking Impact

Add an integration test that runs `_prepare_v5_file()` or the smallest existing
public test seam with only `PythonGraphProducer`.

Prove:

- declaration symbols turn the intended chunks into symbol chunks;
- lexical tokens remain source-evidenced;
- core module remains exactly one per non-empty path;
- no duplicate signal IDs exist;
- empty files still have no module/signal;
- non-Python chunk projections are unchanged.

### Step 2.4: GREEN

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py
```

Then:

```bash
git diff --check
```

Do not add arity/signature inference to satisfy future call-graph ideas.

## Task 3: RED/GREEN Static Module Selectors And Import Relations

**Goal:** Materialize only active, same-unit, closed Python module selectors and
schema-v5 `imports` relations.

**Files:**

- modify `src/context_search_tool/python_graph.py`;
- modify `src/context_search_tool/graph_contract.py`;
- extend `tests/test_python_graph.py`;
- extend `tests/test_graph_resolution.py`.

### Step 3.1: Add The Reviewed Budget

Write a contract test for:

```python
MAX_PYTHON_IMPORTS_PER_FILE == 256
```

Add the constant in `graph_contract.py`. Do not alter any existing graph limit.

### Step 3.2: Write RED Selector Matrix

Parameterize exact expected states for:

- `import app.service`;
- `import app.service as service`;
- `import app.service, app.clients.text`;
- `from app.service import Service`;
- `from app.service import *`;
- `from .service import Service`;
- `from ..clients import text`;
- `from . import service`;
- `from . import *`;
- root import layout;
- conventional `src` layout;
- `.pyw`;
- package `__init__.py`;
- module/package and root/`src` ties;
- missing absolute/external;
- relative escape/unresolved;
- cross-project-unit target;
- dynamic imports.

Assert exact ordered candidate paths and no filesystem access beyond
`RepositoryPathIndex`.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  -k 'selector or relative or root_layout or src_layout or ambiguous or external or dynamic'
```

Expected: RED.

### Step 3.3: Implement Closed Candidate Resolution

Implement pure candidate helpers inside `python_graph.py`:

- normalize unit root and optional `src` root;
- derive source package context;
- perform relative-level arithmetic;
- generate `.py`, `.pyw`, and package `__init__.py` candidates;
- retain only active same-unit paths;
- classify exact/candidates/external/unresolved;
- never parse packaging configuration or inspect host `sys.path`.

For `from package import Name`, target only `package`.
For `from . import sibling`, target the explicit relative sibling when active.

### Step 3.4: Write RED Relation Projection Tests

Assert exact `CodeRelation` fields:

- source is the current core module signal;
- kind `imports`;
- target kind `module`;
- producer `python_ast`;
- producer confidence 1.0;
- unresolved target before global resolution;
- exact v5 relation ID;
- metadata source location/form/level/candidates;
- repeated imports merge earliest location and occurrence count;
- semantically distinct targets do not merge;
- aliases/imported attribute names are not persisted;
- 257 distinct imports retain exactly the canonical first 256 and record one
  omission;
- malformed files emit no relation.

### Step 3.5: Implement Relation Projection

Use existing:

- `generate_v5_relation_id()`;
- core module signal;
- `MaterializedGraph`;
- centralized per-file relation cap after producer materialization.

Keep Python's own 256 cap earlier than the general 8,192 cap. Do not create a
new relation kind or graph score key.

### Step 3.6: Prove Existing Global Resolution

Extend `tests/test_graph_resolution.py` with persisted Python-produced rows.
Assert:

- single active path -> `resolved_exact`, confidence 1.0;
- a single exact active but empty/signal-less path remains unresolved;
- multiple matches -> `ambiguous`, empty target ID;
- multiple distinct active candidate paths remain ambiguous when one lacks a
  core module signal;
- external -> `external`, empty target ID;
- relative unresolved -> `unresolved`, empty target ID;
- target in another project unit is not selected;
- resolved target is the existing `core_module` signal;
- insertion order cannot change state or target.

Add the minimum generic module-candidate guard in `graph_resolution.py`: when
`selector_state="candidates"` names more than one distinct active candidate,
the row stays ambiguous regardless of how many core signals exist. Keep
single-candidate no-match unresolved. Do not add Python-specific lookup SQL or
change non-module signal resolution. Add one frontend-shaped characterization
row proving the same fail-closed generic behavior.

### Step 3.7: GREEN

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  tests/test_graph_resolution.py
```

Run twice. Compare pass counts and, where asserted, projection hashes.

## Task 4: RED/GREEN Producer-Contract Activation

**Goal:** Make unchanged pre-P8 ready-v5 indexes rebuild graph facts exactly
once without signal schema 6.

**Files:**

- modify `src/context_search_tool/graph_lifecycle.py`;
- modify `src/context_search_tool/sqlite_store.py`;
- modify `src/context_search_tool/indexer.py`;
- modify `src/context_search_tool/plugins.py` only after RED lifecycle coverage;
- extend `tests/test_graph_lifecycle.py`;
- extend `tests/test_incremental_refresh.py`;
- extend storage/index-health tests only where existing metadata projections
  require it.

### Step 4.1: Write RED Metadata Read Tests

Cover signal schema 5 with:

- missing `graph_producer_version`;
- `"0"`;
- `"1"`;
- `"-1"`;
- non-integer;
- `"2"` future.

Expected:

| stored value | result |
| --- | --- |
| missing/0 | stale, reason `producer_contract_changed`, no ready evidence |
| 1 | normal current readiness |
| negative/non-integer | existing `IncompatibleSignalSchemaError` channel |
| >1 | existing `IncompatibleSignalSchemaError` channel; no downgrade |

Using the existing error channel avoids a new CLI/MCP/public error schema.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_graph_lifecycle.py \
  -k 'producer'
```

Expected: RED.

### Step 4.2: Add Metadata Contract

In `graph_lifecycle.py` add:

```text
TARGET_GRAPH_PRODUCER_VERSION = 1
GRAPH_PRODUCER_VERSION_KEY = "graph_producer_version"
```

Include the key in graph metadata ownership. Validate it only for current
schema-v5 structured state.

Do not increment:

- `TARGET_SIGNAL_SCHEMA_VERSION`;
- `TARGET_GRAPH_RESOLUTION_VERSION`;
- manifest/operational/vector schema versions.

### Step 4.3: Write RED Initialization/Ready Tests

Assert:

- fresh `initialize_v5()` and legacy-to-v5 `migrate_signal_schema_v5()` write
  producer version 1 with stale state;
- calling `initialize_v5()` on a pre-P8 current-v5 store does not paper over a
  missing producer version; capability remains stale until authoritative
  rebuild;
- both `mark_graph_ready()` and `commit_operational_ready_v1()` write/retain
  version 1 atomically with ready;
- failed validation never writes ready;
- missing version on a previously ready fixture becomes stale before evidence;
- future version causes index/query preflight failure without changing DB
  metadata or source files.

### Step 4.4: Implement Store And Index Plumbing

Update store initialization/finalization metadata writes.

In the index preparation path:

- preserve the computed `producer_contract_changed` stale reason when no
  stronger integrity/topology/file reason exists;
- reuse the existing stale-on-entry rebuild of active non-empty files;
- rely on existing chunk-ID comparison to rebuild vectors only for paths whose
  declaration-driven chunking changes;
- preserve source-hash-last, resolver, association, validation, and publication
  ordering.

Cover both ready-publication implementations. A quiet
`graph_snapshot_unchanged=True` publication may retain version 1 only after a
current producer snapshot exists; it must never bless a missing/zero producer
version as ready.

Do not create a producer-only unsafe partial-ready path.

### Step 4.5: Register The Producer

Only after lifecycle RED tests exist, add `PythonGraphProducer()` to
`default_plugins()`.

Verify `ordered_graph_plugins()` remains deterministic and every default plugin
instance is unique.

### Step 4.6: Write RED Upgrade/No-Op/Recovery Integration

Construct a pre-P8 ready-v5 index by:

1. indexing the synthetic fixture with the old producer set or deleting the
   producer-version metadata in a test-only store;
2. confirming no Python facts;
3. running the new authoritative index.

Assert:

- entry graph becomes stale before file replacement;
- all active non-empty files are parsed;
- Python declarations/imports appear;
- changed Python chunk IDs rebuild their vectors;
- unaffected non-Python vector IDs/bytes are reused;
- producer/import/test resolution finishes before ready;
- final producer version is 1;
- the next authoritative run parses zero files and preserves graph/vector
  projection;
- a Python source change reparses only the required path plus existing
  relation/path-inventory dependencies;
- deletion removes source signals/relations/test associations;
- failures after stale, file, relation, association, vector, and final
  validation stages never expose ready partial evidence;
- rerun converges to the fresh expected graph.

Use existing fault hooks. Do not invent a second transaction manager.

### Step 4.7: GREEN

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_graph_lifecycle.py \
  tests/test_graph_store.py \
  tests/test_incremental_refresh.py \
  tests/test_indexer_manifest.py \
  tests/test_index_health.py
```

Then:

```bash
git diff --check
```

Any need for schema 6 is a design blocker, not an implementation convenience.

## Task 5: RED/GREEN Full Graph Projection And Python Test Association

**Goal:** Prove end-to-end index ordering, exact import resolution, and reuse of
the existing test-association pass.

**Files:**

- create `tests/test_p8_graph_contract.py`;
- extend `tests/test_test_association.py`;
- extend `tests/fixtures/p8-python-graphs/`;
- modify `tests/generate_p8_python_graph_manifest.py`;
- do not modify `test_association.py` unless RED reveals a generic contract
  defect.

### Step 5.1: Define The Structural Projection

The canonical JSON projection contains:

- source paths/languages/test flags;
- Python symbols and declaration signals;
- module signals;
- Python import relations with selector/resolution/confidence/occurrences;
- exact test associations;
- counts by signal/relation kind/producer/resolution;
- omitted counts;
- project units/topology fingerprint;
- graph readiness including producer version;
- deterministic IDs but no source content.

### Step 5.2: Write RED Fresh/Reverse Tests

Index the fixture twice with forward and reversed scanner order.

Assert:

- projections are byte-identical;
- every non-empty active file has exactly one core module;
- expected Python declarations/imports are exact;
- ambiguous/external/unresolved relations have no target;
- no cross-unit relation resolves;
- no dynamic import relation exists;
- malformed source retains generic/core evidence only;
- caps/omissions are exact.

### Step 5.3: Write RED Test-Association Proof

Use `tests/test_service.py` importing production modules.

Assert ordering:

```text
python producer imports persisted
  -> producer imports resolved
  -> test associations regenerated
  -> test associations resolved
  -> graph ready
```

Assert association fields:

- source recognized by canonical Python test path rules;
- target is same-unit, non-test, non-generated core module;
- basis `exact_test_import`;
- provenance relation ID points to the Python import;
- producer `test_association`;
- confidence/resolution 1.0 exact;
- cap eight after target dedupe;
- no test-to-test/generated/cross-unit relation.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_test_association.py \
  tests/test_p8_graph_contract.py
```

Expected: RED before projection/fixture completion.

### Step 5.4: Make The Existing Pipeline Green

Prefer fixture/test changes and producer correctness. `build_test_associations`
already consumes resolved `imports`; no Python-specific branch should be added.

If a product edit is truly required, first document:

- the generic invariant violated;
- why frontend/Java imports are unaffected;
- the new focused negative tests.

### Step 5.5: Add Incremental Convergence

Project and compare:

- fresh index;
- authoritative no-op;
- one importer change;
- imported target deletion;
- target restoration;
- project-unit marker/topology change;
- fault recovery.

All paths ending in the same source state must have the same active structural
projection.

### Step 5.6: GREEN

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  tests/test_graph_resolution.py \
  tests/test_test_association.py \
  tests/test_graph_lifecycle.py \
  tests/test_incremental_refresh.py \
  tests/test_p8_graph_contract.py
```

Run the structural projection generation/check twice:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" tests/generate_p8_python_graph_manifest.py \
  --check-structural
```

Outputs must be byte-identical.

## Task 6: RED/GREEN Retrieval, Explain, Reason, And P7 Compatibility

**Goal:** Let resolved Python imports use existing retrieval behavior without
changing score policy or final selection.

**Files:**

- modify `src/context_search_tool/retrieval_core/relation_policy.py`;
- extend `tests/test_resolved_graph_expansion.py`;
- extend `tests/test_retrieval_pipeline.py`;
- extend `tests/test_p5_explain.py` if necessary;
- extend `tests/test_exploration_p7.py` only for a Python end-to-end witness.

### Step 6.1: Write RED Existing-Policy Tests

Create a deterministic indexed Python mini-workflow:

```text
api.py -> service.py -> client.py
api.py -> schema.py
tests/test_api.py -> api.py
```

Assert:

- a seed in `api.py` acquires `service.py`/`schema.py`;
- a seed matching a later declaration chunk in `api.py` still receives the
  existing same-file core-module seed and traverses its imports;
- a seed in `service.py` acquires `client.py`;
- imports remain outgoing-only;
- test reverse/forward behavior stays gated by explicit test intent;
- `graph_imports_match` uses existing confidence, weight 0.85, and decay 0.8;
- protected direct candidates are object/value unchanged by graph merge;
- ambiguous/external/unresolved rows add no candidate;
- work caps terminate deterministic high-degree/cyclic fixtures;
- trace source remains `relation`;
- query, trace, ContextPack, and exploration consume the same QueryBundle.

Do not assert a new score amount that implies weight tuning.

### Step 6.2: Write RED Reason Test

Assert the selected graph-supported import reason is:

```text
static module dependency
```

Update only characterization snapshots/reasons that previously expected
`frontend import dependency`. Membership, ordering, numeric score parts, and
schemas must remain exact.

### Step 6.3: Write RED P7 Interaction Test

Use repeated chunks from the importer plus relation targets.

Assert:

- final ordinary paths are unique;
- first ranked chunk per path wins;
- relation targets may occupy new distinct-path slots;
- anchors stay independent;
- `selected + duplicate_result_path + result_limit` equals stage input;
- no result/candidate/context limit changes;
- two repeated calls return identical path order.

### Step 6.4: Make Retrieval Green

Expected product change is only the reason string. Existing relation expansion
should already traverse a resolved `imports` row.

If a failing test suggests a ranking/expansion product edit:

1. inspect whether the producer relation fields violate the existing contract;
2. fix the producer first;
3. do not alter relation weight, direction, candidate priority, or ranking;
4. stop for design review if existing generic import traversal truly cannot
   support Python without a policy change.

### Step 6.5: Explain Projection

Verify existing `explain` shows:

- Python declaration signal kind/name/qualified name/producer/range;
- outgoing `imports` relation;
- resolution/confidence;
- target path and signal ID;
- bounded signal/outgoing/incoming counts.

No new explain schema or command option is added.

### Step 6.6: GREEN

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_resolved_graph_expansion.py \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_p5_explain.py \
  tests/test_exploration_p7.py \
  tests/test_formatters.py
```

Then the retrieval-core boundaries:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_core_characterization.py
```

Any non-reason characterization delta is investigated before proceeding.

## Task 7: Build The Pinned Paired Acceptance Runner

**Goal:** Recreate baseline and candidate evidence through one candidate-owned
runner while importing the selected implementation root explicitly.

**Files:**

- create `tests/p8_real_python_graphs_acceptance.py`;
- finalize `tests/fixtures/p8_python_graphs/input_manifest.json`;
- finalize `tests/fixtures/retrieval_quality/p8_python_graphs.json`;
- finalize `tests/p8_python_graph_identity.py`;
- extend P8 manifest generator tests.

### Step 7.1: Runner Contract

The script exposes:

```text
capture
compare
check
```

`capture` inputs:

- implementation root/identity;
- prepared repositories directory;
- frozen input manifest;
- output JSON path;
- optional timing repetition count.

`capture` must:

- import `context_search_tool` from the requested implementation root;
- verify its Git identity or reviewed dirty candidate tree identity;
- for a dirty candidate, record the base commit, tracked binary-diff hash, and
  a canonical path/content digest for every non-ignored untracked file under
  `src/` and `tests/`; a tracked-only diff hash is insufficient;
- prepare/validate exact remote commits;
- copy only through existing safe quality workspace handling;
- use hash embedding/planner off;
- create a fresh index per implementation/source pairing;
- capture structural counts and all 18 case trajectories;
- capture graph-origin target chunk path/range and fixed-witness ContextPack
  role coverage so path acquisition is not confused with best-chunk reranking;
- capture selected results without source content;
- run the ContextPack/exploration witnesses;
- normalize nondeterministic timestamps/durations separately;
- write canonical JSON.

The candidate-owned runner may call only baseline APIs present at the behavior
baseline when capturing that baseline. New P8 internals may be used for
candidate-only structural validation, but not to reinterpret baseline output.

`compare` takes baseline/candidate captures and writes:

- per-case rank/role deltas;
- non-relation producer versus graph-origin import effects;
- structural deltas;
- gained/lost required roles;
- noise deltas;
- relation witness validation;
- P7 continuity;
- timing/resource deltas;
- each design ship-gate result;
- final disposition `ship`, `ranking_followup`, `call_followup`, or `reject`.

Metric arithmetic follows the design exactly: distinct required paths sharing
one broad role remain distinct required items; repository and combined recall
are micro averages; unselected rank delta uses sentinel 13; aggregate noise is
weighted by selected path count.

`check` validates schema, hashes, source provenance, no source bodies/absolute
paths, and deterministic rerender.

### Step 7.2: RED Runner Tests

Test with tiny local synthetic repositories before remote execution:

- wrong implementation identity rejected;
- dirty identity changes when either a tracked or untracked implementation/test
  file changes;
- wrong source commit/content/inventory rejected;
- manifest/gold hash mismatch rejected;
- output refuses source body and absolute source path;
- `not_acquired` differs from `acquired_below_limit`;
- relation witness requires exact persisted relation ID/target;
- gold cannot change between baseline and candidate;
- canonical rerender is byte-identical;
- every ship gate is exercised by a negative fixture.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_p8_graph_contract.py \
  tests/test_quality_cases.py \
  tests/test_quality_runner.py
```

Keep runner-specific tests in the planned
`tests/test_p8_real_python_graphs_acceptance.py`; keep structural projection
assertions in `tests/test_p8_graph_contract.py`.

### Step 7.3: Reuse Existing Quality Infrastructure

Use `QualityRepo`, safe remote preparation, config merging, workspace copy, and
query evaluation where their contracts fit.

Do not fork the general quality framework merely to add role trajectory. Keep
P8-specific role/edge comparison in the acceptance runner.

The standard P8 catalog contains only the results-mode projection of the 18
queries. Existing quality parsing already accepts an arbitrary results profile
name, so do not modify `quality/cases.py`. ContextPack/exploration witnesses
remain in the P8-specific paired runner rather than widening the existing
closed exploration-profile policy.

### Step 7.4: Standard Quality Profile

Validate:

```bash
export P8_STANDARD_ROOT="$(mktemp -d /private/tmp/cst-p8-standard.XXXXXX)"
export P8_REPOS_DIR="$P8_STANDARD_ROOT/repos"
export P8_PROFILE_OUTPUT="$P8_STANDARD_ROOT/profile.json"
mkdir -p "$P8_REPOS_DIR"

env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m context_search_tool.quality prepare \
  tests/fixtures/retrieval_quality/p8_python_graphs.json \
  --profile p8_python_graphs \
  --repos-dir "$P8_REPOS_DIR"
```

Then:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p8_python_graphs.json \
  --profile p8_python_graphs \
  --repos-dir "$P8_REPOS_DIR" \
  --output "$P8_PROFILE_OUTPUT"
```

The standard profile is a compatibility/quality view. The custom paired runner
remains authoritative for roles, stage trajectories, and ship disposition.
Require 18 selected/executed cases and zero runner errors; do not reinterpret
the informational quality aggregate as the P8 ship decision.

### Step 7.5: GREEN Local Runner Contract

Run all runner/manifest tests twice and compare canonical output hashes.

Do not run a candidate-vs-baseline comparison until the frozen gold hash is
validated.

## Task 8: Run Baseline/Candidate A/B And Enforce The Stop Rule

**Goal:** Decide P8 using pinned, paired evidence without tuning.

**Files:** evidence outputs under the task-specific `P8_RUN_ROOT`; no product
edits while interpreting the first comparison.

### Step 8.1: Prepare Evidence Roots

```bash
export P8_RUN_ROOT="$(mktemp -d /private/tmp/cst-p8-run.XXXXXX)"
export P8_REPOS_DIR="$P8_RUN_ROOT/repos"
export P8_BASELINE_CAPTURE="$P8_RUN_ROOT/baseline.json"
export P8_CANDIDATE_CAPTURE="$P8_RUN_ROOT/candidate.json"
export P8_COMPARISON="$P8_RUN_ROOT/comparison.json"
mkdir -p "$P8_REPOS_DIR"
```

Keep baseline and candidate outputs in separate files. Never overwrite the
first valid baseline capture.

### Step 8.2: Capture The Detached Baseline

Run the candidate-owned script with baseline package import:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_BASELINE_WORKTREE/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" \
  "$P8_REPO_ROOT/tests/p8_real_python_graphs_acceptance.py" \
  capture \
  --implementation-root "$P8_BASELINE_WORKTREE" \
  --manifest "$P8_REPO_ROOT/tests/fixtures/p8_python_graphs/input_manifest.json" \
  --repos-dir "$P8_REPOS_DIR" \
  --output "$P8_BASELINE_CAPTURE"
```

Verify:

- implementation identity is exactly the behavior baseline;
- structural counts match Task 0;
- shared rank/path fields match the pre-run Task 0 projection;
- two deterministic repeats are identical.

Any mismatch is a harness/baseline blocker.

### Step 8.3: Capture The Candidate

Record the visible candidate state before capture:

```bash
git rev-parse HEAD
git status --short
```

The capture runner computes the reviewed dirty-tree identity described in Task
7, including new untracked implementation/test files, and writes only hashes
and repository-relative paths. Do not persist a raw candidate patch merely to
identify the tree.

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" \
  "$P8_REPO_ROOT/tests/p8_real_python_graphs_acceptance.py" \
  capture \
  --implementation-root "$P8_REPO_ROOT" \
  --manifest "$P8_REPO_ROOT/tests/fixtures/p8_python_graphs/input_manifest.json" \
  --repos-dir "$P8_REPOS_DIR" \
  --output "$P8_CANDIDATE_CAPTURE"
```

Run it a second time to a distinct path and require deterministic projection
equality.

### Step 8.4: Compare Without Editing Product Code

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" \
  "$P8_REPO_ROOT/tests/p8_real_python_graphs_acceptance.py" \
  compare \
  --manifest "$P8_REPO_ROOT/tests/fixtures/p8_python_graphs/input_manifest.json" \
  --baseline "$P8_BASELINE_CAPTURE" \
  --candidate "$P8_CANDIDATE_CAPTURE" \
  --output "$P8_COMPARISON"
```

Then:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" \
  "$P8_REPO_ROOT/tests/p8_real_python_graphs_acceptance.py" \
  check \
  --manifest "$P8_REPO_ROOT/tests/fixtures/p8_python_graphs/input_manifest.json" \
  --capture "$P8_BASELINE_CAPTURE" \
  --capture "$P8_CANDIDATE_CAPTURE" \
  --comparison "$P8_COMPARISON"
```

### Step 8.5: Validate Every Relation Claim

For every improved required path:

- identify the importer seed path/rank;
- verify the improved selected representative is graph-origin rather than a
  non-relation producer/direct-only shift;
- identify source core module signal;
- identify relation ID;
- verify producer `python_ast`;
- verify kind `imports`;
- verify `resolved_exact`;
- verify target core module/path;
- verify source/target project-unit equality;
- verify candidate selected reason/score part;
- verify no direct-protected mutation.

A rank/recall improvement without graph origin and this exact witness is
reported but is not credited to the P8 import ship gates.

### Step 8.6: Apply The Fixed Disposition

Use the design outcomes:

- `ship`: all acceptance/ship gates pass;
- `ranking_followup`: exact relation evidence is acquired/expanded but remains
  below final evidence;
- `call_followup`: reviewed missing targets have no import path from admitted
  seeds;
- `reject`: noise, cost, lifecycle, compatibility, privacy, or determinism
  fails.

Do not edit:

- relation weight;
- graph decay;
- query text;
- gold;
- required/contextual labels;
- candidate/result limits;
- generic ranking penalties

after seeing the first candidate comparison.

If disposition is not `ship`, stop product implementation and report the
evidence. Do not continue to Task 9 completion docs as though P8 were accepted.

## Task 9: Protected Regression, Performance, Full Suite, And Completion Docs

**Goal:** Prove that an accepted candidate is safe outside the P8 profile and
record only the bounded claim.

### Step 9.1: Focused P8 Group

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_python_graph.py \
  tests/test_p8_graph_contract.py \
  tests/test_graph_lifecycle.py \
  tests/test_graph_resolution.py \
  tests/test_graph_store.py \
  tests/test_incremental_refresh.py \
  tests/test_test_association.py \
  tests/test_resolved_graph_expansion.py \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_p5_explain.py \
  tests/test_exploration_p7.py
```

Expected: all pass, no xfail, only established warnings.

### Step 9.2: P5 Structural/Quality Protection

Run the focused P5 graph group:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src:$P8_REPO_ROOT/tests" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_p5_graph_contract.py \
  tests/test_frontend_graph.py \
  tests/test_java_ast.py \
  tests/test_chunker_java_plugin.py \
  tests/test_mybatis_xml.py \
  tests/test_test_association.py \
  tests/test_resolved_graph_expansion.py
```

Run deterministic P5 quality if its prepared inputs are available:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p5_language_graphs.json \
  --profile p5_language_graphs \
  --output "$P8_RUN_ROOT/p5-language-graphs.json"
```

Expected: 12/12. The established real P5 profile remains 2/2 when its prepared
remote inputs are available.

Audit every P5 projection change. Allowed causes are only:

- producer-version readiness metadata;
- actual Python signals/imports/associations in a Python-containing fixture;
- `static module dependency` reason wording.

### Step 9.3: P7 Protection

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_exploration_p7.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_formatters.py
```

Recheck the frozen daily continuity query in the candidate capture:

```text
12 results
12 unique paths
pipeline present
base present
first-ranked representative per path preserved
duplicate decision accounting exact
```

### Step 9.4: P6 Protection

Run the full P6 group while the machine is otherwise idle:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q \
  tests/test_p6_benchmark.py \
  tests/test_p6_case_registry.py \
  tests/test_p6_entry_publish.py \
  tests/test_p6_measurement_worker.py \
  tests/test_p6_operational_store.py \
  tests/test_p6_paired.py
```

Expected accepted baseline: 81 passed.

If one resident/calibration node fails:

1. record the exact node and full output;
2. rerun only that node in a clean process;
3. rerun the entire 81-test group while idle;
4. do not change P6 code/policy unless a repeatable P8-caused regression is
   proven.

### Step 9.5: Raw CI Quality

Run:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output "$P8_RUN_ROOT/ci.json"
```

Expected:

```text
selected/executed/passed = 8/8/8
failed/errors = 0/0
```

### Step 9.6: Full Suite

Run serially:

```bash
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$P8_REPO_ROOT/src" \
  "$P8_RUNTIME" -m pytest -q
```

Acceptance:

- zero failures;
- established skips are exactly audited;
- no new xfail;
- any pass-count increase is traceable to new P8 tests.

Do not declare success from focused tests if the full suite fails.

### Step 9.7: Performance Review

From the paired capture and P6 output, report:

- RedInk/daily index wall time;
- query latency distribution;
- SQLite/index/vector size;
- parsed files/chunks embedded/vector bytes reused;
- signals/relations/test associations;
- graph work counts.

If either reviewed cost threshold is exceeded, stop for review even when
functional tests pass.

### Step 9.8: Completion Documentation

Only with `ship` disposition:

1. update README with the bounded Python declaration/static-import claim;
2. update retrieval-quality docs with source commits, role metrics, and exact
   commands;
3. update roadmap from planned to accepted;
4. record full focused/P5/P6/P7/quality/full-suite and real-profile results in
   this plan;
5. state explicit residuals:
   - no Python call graph;
   - no runtime import resolution;
   - no arbitrary packaging mapping;
   - no fast-context parity;
   - next phase chosen only from the A/B disposition.

Do not publish raw source bodies, local absolute source paths, dirty-worktree
patches, or secrets.

### Step 9.9: Final Diff Audit

Run:

```bash
git status --short
git diff --stat
git diff --check
git diff --name-only "$P8_BEHAVIOR_BASELINE"
```

Audit every changed/untracked path against the planned file map.

Search tracked candidate content for forbidden local/source material:

```bash
rg -n \
  '/Users/[^/]+/(openSource|opensource)|\\.env|api[_-]?key|BEGIN (RSA|OPENSSH) PRIVATE KEY' \
  README.md \
  docs \
  roadmap \
  src \
  tests
```

Review matches manually; repository documentation may contain historical local
paths, so the command is a review aid, not a blind failure by itself. New P8
artifacts must contain no local source locator or secret.

Do not stage or commit unless the user asks.

## Required Test Matrix

| behavior | primary test owner |
| --- | --- |
| AST-only parse and diagnostics | `test_python_graph.py` |
| declaration boundary/ranges/identity | `test_python_graph.py` |
| root/`src`/relative/module selector | `test_python_graph.py` |
| exact/ambiguous/external resolution | `test_graph_resolution.py` |
| producer-version read/upgrade/future | `test_graph_lifecycle.py` |
| vector/chunk/incremental/recovery | `test_incremental_refresh.py` |
| producer -> association ordering | `test_test_association.py`, `test_p8_graph_contract.py` |
| outgoing imports/weight/protection/caps | `test_resolved_graph_expansion.py` |
| reason/explain/public surfaces | `test_p5_explain.py`, retrieval tests |
| P7 path diversity/accounting | `test_retrieval_pipeline.py`, `test_exploration_p7.py` |
| deterministic structural projection | `test_p8_graph_contract.py` |
| source/gold/privacy/paired gates | P8 identity/generator/acceptance tests |
| existing Java/frontend/MyBatis | P5 focused/projection tests |
| performance/freshness | P6 81-test group |
| generic quality | CI 8/8 |
| repository-wide compatibility | full pytest suite |

## Acceptance Checklist

### Inputs And Causality

- [ ] behavior baseline exact;
- [ ] RedInk source commit/inventory exact;
- [ ] daily source commit/203-file inventory exact;
- [ ] original user repositories untouched;
- [ ] all 18 queries/roles/gold frozen before candidate output;
- [ ] baseline stage trajectories captured twice;
- [ ] candidate uses identical sources/config/budgets.

### Parser And Facts

- [ ] AST-only compile on bytes;
- [ ] no target execution/import/network/environment access;
- [ ] declaration inclusion/exclusion exact;
- [ ] source ranges and byte columns exact;
- [ ] declaration/symbol cap retains 4,095 and records exact omissions;
- [ ] malformed/encoded/runtime-newer syntax fails softly;
- [ ] bounded diagnostic metadata contains no source/exception text;
- [ ] fact order deterministic.

### Signals And Imports

- [ ] symbols/signals use reviewed kinds/qualified names/IDs;
- [ ] signature empty and arity null;
- [ ] only root and `src` import roots;
- [ ] same-unit active paths only;
- [ ] all import syntax-table positives/negatives pass;
- [ ] `from package import name` does not invent a submodule;
- [ ] repeated import merge exact;
- [ ] Python import cap 256;
- [ ] existing signal/relation caps unchanged.

### Lifecycle And Resolution

- [ ] schema remains 5;
- [ ] producer version key/target is 1;
- [ ] missing/0 stale and reparses once;
- [ ] current no-ops;
- [ ] invalid/future fails without downgrade;
- [ ] only changed vectors rebuild;
- [ ] fault recovery never exposes partial ready;
- [ ] exact/unique resolves;
- [ ] ambiguous/external/unresolved never traverses;
- [ ] deletion/topology/incremental paths converge.

### Test Association And Retrieval

- [ ] producer resolution precedes association regeneration;
- [ ] Python test association is exact, same-unit, non-test, non-generated;
- [ ] test intent gate unchanged;
- [ ] imports remain outgoing-only;
- [ ] weight/decay/score part unchanged;
- [ ] language-neutral reason exact;
- [ ] protected direct candidates unchanged;
- [ ] trace/ContextPack/exploration schemas/budgets unchanged;
- [ ] P7 unique paths/winner/accounting unchanged.

### Real Value

- [ ] per-repository required-role Recall@12 non-decreasing;
- [ ] graph-origin exact imports newly satisfy at least 0.05 of the combined
  required-item denominator and total combined Recall improves accordingly;
- [ ] no baseline top-12 required path is lost;
- [ ] at least four relation-attributable qualifying cases improve;
- [ ] at least three qualifying improvements occur in daily;
- [ ] RedInk is treated as a precision/provenance guard, not forced rank gain;
- [ ] relation-supported selected evidence appears in at least six cases;
- [ ] relation witness minimum is met for each repository;
- [ ] every witness is a persisted exact import;
- [ ] noise gates pass;
- [ ] P7 continuity query passes;
- [ ] deterministic repeated projections match.

### Regression And Delivery

- [ ] focused P8 tests pass;
- [ ] P5 focused/projections and 12/12 quality pass;
- [ ] P7 focused/characterization pass;
- [ ] P6 81/81 passes or any transient is fully audited and clears;
- [ ] raw CI 8/8 passes;
- [ ] full suite passes with established skips audited;
- [ ] timing/resource review passes;
- [ ] completion docs make only bounded claims;
- [ ] no local/private/source-body evidence tracked;
- [ ] final diff matches allowlist and `git diff --check`;
- [ ] no calls/reranking added;
- [ ] no Git publication action taken without user request.

## Stop Conditions

Stop immediately and report evidence when:

- source/gold identity changes after candidate observation;
- exact source preparation is unavailable;
- AST parsing requires executing target code;
- import resolution requires arbitrary runtime `sys.path` reproduction;
- existing schema fields cannot express the relation safely;
- a future producer version would be downgraded;
- ambiguity is resolved by "pick first";
- a protected direct result changes due to graph merge;
- a score/weight/ranking edit appears necessary;
- P7 path diversity/accounting regresses;
- a repeatable P6/full-suite regression remains;
- privacy/source-body checks fail;
- the paired disposition is not `ship`.

The stop condition does not authorize adding the next mechanism. A
`ranking_followup` or `call_followup` disposition becomes a new design task.

## Implementation Record

Status: Tasks 0-8 executed 2026-07-26; disposition **reject** (stop rule
applied); Task 9 completion docs intentionally not written.

Observed record:

```text
entry:
  behavior baseline: 117f46bdd9f067d50ce66b553cd85d7488649eed
    (re-anchored from the plan's 75cc65e: post-plan main merged storage
     layout v2 [retrieval-neutral] and followup-keyword filtering
     [rendered-output change]; anchoring to the last pre-P8 commit keeps
     the A/B a pure P8 delta; original anchor retained in
     tests/p8_python_graph_identity.py)
  implementation tree: feat/p8-python-static-structure (commits a2fd260,
    df3330b, 264d828, 671731a, 67d3e49, + Tasks 4-7 commits)
  Python: 3.13.12 (.quality/p5-runtime)
  SQLite: 3.51.2

frozen inputs:
  RedInk 4d487223: 28 files, inventory 0da08ce1..., content 53644c92...
  daily 487e49e5: 203 files, inventory 76cca5c6..., content 0b77bceb...
  gold manifest hash: 459e6a56c0f7c3b033e34dafeba623b15e221d19ff59244d7fa29a47621f7767

RED: every task followed RED->GREEN with double GREEN runs; notable
  reviewed corrections during RED: same-statement imports order by
  semantic target; .service/app.service merge (same target module);
  compile() maps bad source encoding to syntax_error; explain relation
  rows carry no producer field.

changed product files: python_graph.py (new), plugins.py,
  graph_contract.py (MAX_PYTHON_IMPORTS_PER_FILE), graph_lifecycle.py
  (graph_producer_version read rules), sqlite_store.py (producer version
  stamping at v5 init/migrate/both ready publications),
  graph_resolution.py (generic multi-candidate ambiguity guard),
  retrieval_core/relation_policy.py (reason -> "static module dependency").
  No weight/decay/budget/query/planner/P7 edits.

structural projection: forward/reverse byte-identical; 19 files,
  14 modules, 25 declarations, imports {ambiguous 1, external 5,
  resolved_exact 7, unresolved 5}, 1 exact test association;
  incremental change/revert and delete/restore converge (active
  structure; tombstone + resolution-generation counters normalized).

real paired profile (evidence: $P8_BASELINE_ROOT/evidence/*.json):
  RedInk: recall@12 1.0 -> 0.941 (image_compressor.py displaced)
  daily: recall@12 0.775 -> 0.800
  combined: 0.842 -> 0.842 (delta 0.0)
  candidate graph: daily 696 resolved-exact imports + 3 test assoc,
    RedInk 35 resolved-exact imports; witnesses map to persisted r5: ids
  newly satisfied: 3 daily required paths, all credited=False
    (declaration-chunking/direct effects, not graph-origin selection)
  lost required (gate 3 FAIL): daily-agent-execution
    src/agent/tools/registry.py, daily-runtime-scheduler src/config.py,
    redink-image-flow backend/utils/image_compressor.py
  relation-supported cases: 3 (need >=6 across both repos)
  noise: 0.713 -> 0.713 (delta 0.0, gate 8 PASS)
  P7 continuity: 12 unique paths, both required present (gate 9 PASS)
  determinism: second candidate capture byte-identical after
    timing/identity normalization (gate 11 PASS)
  disposition: reject

performance (REJECT trigger): daily index 1.28s -> 2.60s (+102%,
  gate: <=25%); query latency mean 0.374s -> 4.349s (~12x; gate: <=10%
  and <5ms absolute). Profile attribution: expansion._resolved_edge ->
  chunk_for_id loads chunks one edge at a time (1,231 edge visits,
  8,713 SQL executes, 5.9s of 6.7s in one profiled query). Existing
  N+1 in relation expansion, first exposed by import-graph edge density;
  P5 work caps themselves held.

P5/P6/P7: focused suites all green (411-entry gate at Task 0; 400
  protected graph/P7 tests green after Task 3; 187 lifecycle/store/
  refresh/manifest/health after Task 4; 327 retrieval/trace/explain/
  exploration/formatters after Task 6).

CI quality: standard p8_python profile prepare (remote pinned clones)
  + run: selected=18 executed=18 errors=0 (informational).

full suite: 2954 passed, 0 failed, 5 skipped (supported runtime).

privacy/diff audit: captures contain repository-relative paths and
  hashes only; check rejects absolute paths/source bodies; no user
  directory was indexed or modified.

residual limitations: reject evidence, not shipped behavior. The
  producer/lifecycle/graph code is inert for retrieval quality claims
  until a follow-up passes the gates.

next-phase decision (from the observed failure boundary, in order):
  1. batch chunk materialization in relation expansion
     (_resolved_relation_candidates) - performance fix, not weight
     tuning; rerun this A/B unchanged;
  2. then re-examine gate 3 fallout: graph-origin candidates displacing
     required support paths through P7 slots is a selection-pressure
     interaction, only meaningful to judge at sane latency;
  3. gate 2/4/5 (credited gains) were not met: observed daily gains came
     from declaration chunking, suggesting the next quality lever may be
     declaration-signal recall rather than import-edge expansion.
```

Original template (unfilled) follows for reference:

```text
entry:
  behavior baseline:
  implementation tree:
  Python:
  SQLite:

frozen inputs:
  RedInk commit/inventory/content hash:
  daily commit/inventory/content hash:
  gold manifest hash:

RED:
  Task 1 nodes/failures:
  Task 2 nodes/failures:
  Task 3 nodes/failures:
  Task 4 nodes/failures:
  Task 5 nodes/failures:
  Task 6 nodes/failures:
  Task 7 nodes/failures:

changed product files:

focused:

structural projection:

real paired profile:
  RedInk:
  daily:
  combined:
  relation witnesses:
  noise:
  P7 continuity:
  disposition:

performance:

P5:

P6:

P7:

CI quality:

full suite:

privacy/diff audit:

residual limitations:

next-phase decision:
```

Do not fill the record with expected values. Record only observed, verified
results.
