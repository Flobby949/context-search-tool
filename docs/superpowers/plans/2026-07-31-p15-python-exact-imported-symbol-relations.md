# P15 Python Exact Imported-Symbol Relations v1 Implementation Plan

> **For agentic workers:** Execute tasks in order. Task 0 is a hard,
> product-free oracle gate. Do not touch product code unless the oracle passes
> every frozen causal and safety gate. Stop instead of tuning after capture.

Date: 2026-07-31
Status: Reviewed on 2026-07-31; implementation not authorized or started
Repository: `context-search-tool`
Behavior baseline: `5f56de2e1b57ed7f1ec0ee9a513b508461d78233`
Design:
`docs/superpowers/specs/2026-07-31-p15-python-exact-imported-symbol-relations-design.md`

The design is the normative behavior contract. This plan is its execution
checklist; any conflict stops work and requires document review. No task below,
including Task 0 harness/fixture work, is authorized until the user separately
approves implementation.

## Goal

Test, then implement only if justified, one narrow Python graph refinement:

```text
from package.module import Name as LocalName
  -> preserve the existing module-target imports relation
  -> resolve one exact same-unit Python declaration signal
  -> add one imports relation to that type/function declaration
  -> reuse existing expansion, weight, reason, and max evidence merge
```

The intended benefit is to retrieve the imported declaration chunk instead of
letting every import of a module support only that module's broad first chunk.
The implementation succeeds only if the product-free oracle proves enough
headroom and the candidate reproduces that benefit without required loss,
noise growth, protected-winner drift, budget growth, or policy changes.

## Frozen Product Contract

- Existing Python module-target `imports` relations remain present and keep
  their current identity, confidence, ordering, occurrence accounting, and
  256-row cap.
- A separate syntax fact is emitted only for a static `ast.ImportFrom` with:
  - a named module;
  - a non-star imported simple identifier.
- That fact materializes an exact-symbol relation only when the existing module
  selector resolves one target file in the same project unit. Fact extraction
  itself does not consult the index or suppress external/unresolved syntax.
- Alias text affects only bounded provenance metadata such as `local_names`.
  It never changes the target qualified name, relation score, or query.
- Import usage analysis is not part of P15. The `ImportFrom` statement itself
  is the static dependency witness.
- The target must be the unique active signal in the exact target file with:
  - producer `python_ast`;
  - language `python`;
  - kind `type` or `function`;
  - the exact module-level qualified name formed from the imported name.
- Zero matches remain unresolved. More than one allowed match is ambiguous.
  Never pick the first match and never use capitalization to guess a kind.
- Re-exports are not followed.
- The relation keeps kind `imports`, producer `python_ast`, existing producer
  confidence, existing weight `0.85`, graph decay `0.8`, score part
  `graph_imports_match`, and reason `static module dependency`.
- Module and exact-symbol edges that reach the same result merge the graph
  score by `max`; they never add two boosts.
- Exact-symbol relations have their own deterministic 256-row cap, applied
  after relation-identity deduplication. It must not consume or reorder the
  existing module relation cap.
- `TARGET_GRAPH_PRODUCER_VERSION` changes from `1` to `2`. A ready schema-v5
  index stamped with producer v1 becomes stale once, rebuilds authoritatively,
  reaches ready v2, and then no-ops. Future versions fail closed.
- No signal, relation, trace, result, ContextPack, manifest, vector, or SQLite
  schema version changes.

## Frozen and Blocking Decisions

R1 is frozen by the 2026-07-31 document review. R2's arithmetic is frozen
below; Task 0 must fill and seal its concrete source/gold denominators and
hashes before the first capture. No oracle capture may start while that
manifest work remains open.

### R1 — Union Target Selector

Use exactly this internal representation:

```text
target_kind = "python_declaration"
metadata.target_signal_kinds = ["type", "function"]
metadata.target_file_path = <exact repository-relative target path>
```

The resolver and SQLite lookup may recognize this closed internal selector
only for `python_ast` imported-symbol `imports` rows. On resolution, integrity
must bind the row to an actual `type` or `function` target signal without
weakening generic relation checks. Relation identity and the persisted
`target_kind` retain the stable pseudo-kind `python_declaration`; the joined
target signal retains its actual kind. The resolution lookup and graph
integrity special case both require the exact producer, language, file,
qualified name, project unit, resolution basis, and closed kind tuple.

Forbidden R1 substitutes:

- emit one speculative type edge and one speculative function edge;
- infer kind from identifier case;
- wildcard across producers, languages, files, or project units;
- accept the first of multiple rows;
- relax generic integrity for unrelated relation producers.

### R2 — Numeric Acceptance Floor

The 2026-07-31 review freezes the exact arithmetic and values below. Task 0
copies them verbatim into the tracked P15 manifest and fills only the sealed
source identities and exact denominators that the rules require. R2 has two
phases and cannot be changed in response to output.

The Task 0 development-oracle floor is:

- combined micro required Recall@12 gain at least `0.05` absolute;
- at least `3` newly selected required items across `3` distinct cases;
- at least one exact-symbol-credited gain in each development repository;
- zero previously selected required-item loss, per repo and combined;
- zero selected closed-world noise increase, per case, per repo, and combined;
- zero protected-winner drift and no unapproved selected-membership drift
  outside oracle-eligible cases;
- deterministic normalized hash projections across canonical/reversed input
  order and two separate-process repeats, plus deterministic online stable
  projections across two separate-process repeats;
- zero privacy, source-identity, request-accounting, or integrity failure.

The final candidate floor additionally requires:

- production recovers every development gain credited by the oracle;
- the sealed held-out gains at least `2` required items across `2` cases;
- gains therefore occur in both development repositories and the held-out;
- `daily_stock_analysis` index wall-time regression no more than `25%`;
- query latency regression no more than `10%` when absolute increase is at
  least `5 ms`;
- no increase to any existing graph work cap or retrieval budget;
- every remaining hash, online, regression, privacy, and integrity gate passes.

The held-out denominator is not instantiated until the independent reviewer
seals the corpus. The frozen admissibility rule is at least `12` held-out
required items across at least `4` cases. Task 0 records the resulting exact
integer before the first oracle capture; this fills a sealed input, not a new
R2 choice. Neither denominator nor floor may change afterward.

## Non-Goals

- general Python call graph, inheritance, data flow, or type inference;
- runtime import execution, `sys.path` emulation, or dynamic imports;
- assignment, constant, enum-like value, or type-alias declarations;
- closing `analysis_metadata.py` constant ownership gaps;
- nested declarations, methods, or nested qualified-name lookup;
- `import module as alias; alias.attribute` relations;
- star imports, unnamed-module imports, or re-export traversal;
- LSP, tree-sitter, or a new parser dependency;
- a new store table, column, index schema, or public schema field;
- planner, query, route, ranking-weight, graph-decay, or reason changes;
- P9-P11 quota, membership, affinity, listwise, or overflow tuning;
- candidate, result, context, exploration, edge, or signal budget expansion;
- P6/product-surface work unrelated to measured regression protection.

## Planned File Surface

Product changes are limited to:

| path | purpose |
| --- | --- |
| `src/context_search_tool/python_graph.py` | imported-name facts, aliases, exact module selector, symbol relation projection |
| `src/context_search_tool/graph_resolution.py` | closed R1 selector classification and cardinality |
| `src/context_search_tool/sqlite_store.py` | exact-file/type-or-function lookup and unchanged integrity guarantees |
| `src/context_search_tool/graph_lifecycle.py` | producer contract version 2 |

Expected focused tests:

| path | purpose |
| --- | --- |
| `tests/test_python_graph.py` | facts, selector matrix, cap, materialized rows |
| `tests/test_graph_resolution.py` | zero/one/many target classification and same-unit closure |
| `tests/test_graph_store.py` | R1 lookup/integrity behavior |
| `tests/test_graph_lifecycle.py` | producer v1-to-v2 lifecycle |
| `tests/test_incremental_refresh.py` | rebuild/no-op/change/revert convergence |
| `tests/test_resolved_graph_expansion.py` | exact target expansion and max merge |
| `tests/test_retrieval_pipeline.py` | rank/membership compatibility |
| `tests/test_retrieval_trace_pipeline.py` | existing score part and reason |
| `tests/test_p8_graph_contract.py` | protected Python graph projection |

Tracked P15 evidence tooling:

| path | purpose |
| --- | --- |
| `tests/fixtures/p15_python_import_symbols/input_manifest.json` | development query/gold plus held-out public identity, denominator, thresholds, and sealed-payload digest |
| `tests/p15_python_import_symbol_acceptance.py` | oracle/capture/compare/check CLI |
| `tests/test_p15_python_import_symbol_acceptance.py` | schema, arithmetic, gate, privacy, determinism tests |

Do not add a production file or change another product path without design
review. Documentation updates are conditional on final disposition.

## Command Convention

Run from the checkout root and derive local paths instead of tracking them:

```bash
P15_ROOT=$(git rev-parse --show-toplevel)
P15_PYTHON="$P15_ROOT/.quality/p5-runtime/bin/python"
P15_BASELINE=5f56de2e1b57ed7f1ec0ee9a513b508461d78233
P15_MANIFEST=tests/fixtures/p15_python_import_symbols/input_manifest.json
P15_ACCEPTANCE=tests/p15_python_import_symbol_acceptance.py
P15_ATTEMPT_ID=p15-v1-attempt-001
P15_RUN_ROOT="$P15_ROOT/.quality/p15-runs/$P15_ATTEMPT_ID"
P15_FOCUSED_TESTS=(
  tests/test_p15_python_import_symbol_acceptance.py
  tests/test_python_graph.py tests/test_graph_resolution.py
  tests/test_graph_store.py tests/test_graph_lifecycle.py
  tests/test_incremental_refresh.py tests/test_resolved_graph_expansion.py
  tests/test_retrieval_trace_pipeline.py
)
P15_PROTECTED_TESTS=(
  tests/test_quality_p2.py tests/test_quality_p3.py tests/test_quality_p4.py
  tests/test_quality_p5.py tests/test_p5_protected_direct.py
  tests/test_p6_benchmark.py tests/test_exploration_p7.py
  tests/test_p8_graph_contract.py tests/test_p13_bge_provider_measurement.py
  tests/test_p14_definition_owner_acceptance.py
  tests/test_retrieval_core_boundaries.py tests/test_exploration_boundaries.py
)

test "$PWD" = "$P15_ROOT"
test "$(git rev-parse "$P15_BASELINE^{commit}")" = "$P15_BASELINE"
test "$(git rev-parse HEAD)" = "$P15_BASELINE"
test -x "$P15_PYTHON"
```

Each task gives its concrete pytest or acceptance command. Every task ends
with tracked and untracked whitespace/diff checks:

```bash
git status --short --untracked-files=all
git ls-files --others --exclude-standard
git diff --check
P15_UNTRACKED_CHECK=$(
  while IFS= read -r P15_PATH; do
    git diff --no-index --check /dev/null "$P15_PATH" 2>&1 || test $? -eq 1
  done < <(git ls-files --others --exclude-standard)
)
test -z "$P15_UNTRACKED_CHECK"
P15_UNTRACKED_PRODUCT=$(git ls-files --others --exclude-standard -- \
  src/context_search_tool)
test -z "$P15_UNTRACKED_PRODUCT"
```

Do not stage, commit, push, or publish while executing this plan. Never modify
the three pinned external source corpora. Current-checkout product edits are
allowed only after Task 0 returns `proceed`, and only in the listed files.

---

### Task 0: Isolate, Freeze, and Run the Product-Free Oracle

**Files:** P15 manifest, acceptance script, acceptance tests, ignored evidence
root only. No `src/context_search_tool/**` edit is allowed.

#### RED — Freeze the harness contract

1. Record baseline SHA, branch, dirty state, runtime, module origins, and the
   reviewed R1/R2 text hash.
2. Seal three independent public inputs:
   - RedInk at the already pinned P8 URL/commit/include projection;
   - `daily_stock_analysis` at the already pinned P8 URL/commit/include
     projection;
   - one independent public Python held-out repository chosen and held by an
     independent reviewer before development-oracle output exists. The
     implementation team receives its identity/hash contract but cannot open
     its queries, gold, or retrieval outcomes until Task 6.
3. For every source, freeze URL, commit, license, include/exclude rules,
   selected inventory, inventory SHA-256, content SHA-256, and repository role.
4. Freeze exact query strings, `TopK=12`, required/contextual paths, necessity,
   protected winners, eligible membership-change cases, and the closed-world
   noise rule.
5. The independent reviewer fills the exact held-out denominator and seals the
   hidden query/gold payload; the checker verifies the manifest copies the
   already-frozen R2 values. Hash the public manifest and sealed-payload digest.
   Any later gold edit requires discarding all captures and a new explicit
   review, not a waiver.
6. Write negative tests for wrong source/implementation/gold/threshold hashes,
   denominator changes, missing roles, invalid absolute paths, source bodies,
   oracle rows without exact witnesses, repeat/input-order drift, and every
   reject gate.

Run:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_p15_python_import_symbol_acceptance.py
```

Expected RED: missing harness/manifest or unimplemented validation. Record
only observed node names and failure reasons.

#### GREEN — Build an independent oracle

The oracle is test-only and must not import candidate P15 code. It runs only on
the two development repositories. On fresh baseline indexes it:

1. parses `ImportFrom` statements independently with stdlib AST;
2. retains only frozen P15-eligible selectors;
3. starts from an existing resolved-exact module relation;
4. looks in that exact target file and same project unit for active
   `python_ast` Python `type`/`function` signals with the exact qualified name;
5. accepts exactly one match, classifies zero/many closed, and overlays one
   already-resolved test-only relation using the target's actual `type` or
   `function` kind on a copied index while preserving every original relation;
6. reruns the existing retrieval pipeline without candidate R1 plumbing and
   without changing product code, rank policy, weights, budgets, query,
   planner, or gold;
7. assigns every frozen residual exactly one terminal state:
   `not_representable`, `no_exact_signal`, `ambiguous_signal`,
   `resolved_not_traversed`, `acquired_below_ranking`, `ranked_not_selected`,
   `selected_wrong_chunk`, or `selected_exact_declaration_chunk`;
8. emits only those states, hashes, relative paths, bounded metadata, relation
   IDs, target signal/chunk IDs, stage/rank trajectory, work counters, and
   timing.

For canonical and reversed input order, capture baseline and oracle in two
separate processes with deterministic hash embeddings and planner off. Compare
all normalized projections byte-for-byte.

The GREEN harness must make this command sequence executable:

```bash
"$P15_PYTHON" "$P15_ACCEPTANCE" validate \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT"
for P15_REPEAT in 1 2; do
  for P15_VARIANT in baseline oracle; do
    for P15_ORDER in canonical reverse; do
      "$P15_PYTHON" "$P15_ACCEPTANCE" capture \
        --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
        --phase oracle --corpora development --profile hash \
        --variant "$P15_VARIANT" --repeat "$P15_REPEAT" \
        --input-order "$P15_ORDER"
    done
  done
done
"$P15_PYTHON" "$P15_ACCEPTANCE" compare \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
  --phase oracle --corpora development --profile hash
```

The primary causal credit for a newly selected required item requires all of:

- exact frozen importer/imported-name fact;
- preserved exact module relation;
- added exact symbol relation;
- unique allowed target signal in the exact target file;
- target chunk equals the gained result chunk;
- `graph_imports_match` and resolved-relation provenance on the gained result;
- no unrelated direct, planner, query, weight, budget, or gold difference.

The P8 `relation_slot` rule is forbidden as either terminal-state or gain
credit. The checker rejects a missing, duplicate, or non-terminal residual
classification.

Apply the development-oracle half of R2 mechanically. If it fails one gate,
disposition is `reject`: stop before Task 1 and do not touch product code.

#### Confirmatory online safety definition

Before any online call, freeze the stable projection for planner-off provider
`openai-compatible`, model `Pro/BAAI/bge-m3`, 1024 dimensions, endpoint
`https://api.siliconflow.cn/v1`. The hashed manifest must also freeze P14's
approved pacing before the first request: a 240,000-token sliding-minute
budget, 80,000-token per-request budget, two-second minimum interval, and the
bounded-greedy batch implementation/configuration identity. The checker fails
closed if any field is absent or changes. The stable projection contains:

- provider/model/dimensions and request counts;
- selected required/contextual/noise path membership and order;
- required-item ranks and graph score-key presence;
- protected winners;
- exact relation/target/chunk credit witnesses, relation/target identities, and
  structural counts;
- required losses, noise delta, work caps, and error/fallback/skip counts.

Continuous scores and timing are not causal evidence. After the development
hash oracle passes, capture the same oracle overlay twice online before Task 1.
Provider failure is `blocked`; any stable-projection safety failure is
`reject`. No after-the-fact waiver is permitted.

```bash
for P15_REPEAT in 1 2; do
  for P15_VARIANT in baseline oracle; do
    "$P15_PYTHON" "$P15_ACCEPTANCE" capture \
      --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
      --phase oracle --corpora development --profile online-bge \
      --variant "$P15_VARIANT" --repeat "$P15_REPEAT" \
      --input-order canonical
  done
done
"$P15_PYTHON" "$P15_ACCEPTANCE" compare \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
  --phase oracle --corpora development --profile online-bge
"$P15_PYTHON" "$P15_ACCEPTANCE" check \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" --gate task0
git diff --exit-code "$P15_BASELINE" -- src/context_search_tool
```

**Task 0 gate:** manifest immutable, R1/R2 closed, held-out sealed but unopened,
development oracle hash and online projections each pass twice, every Task 0
R2 gate passes, privacy checks pass, and product diff is empty.

---

### Task 1: RED/GREEN Imported-Name and Alias AST Facts

**Files:** `tests/test_python_graph.py`,
`src/context_search_tool/python_graph.py`.

Write RED tests for one independent fact per named `ImportFrom` alias:

- exact `module`, relative level, imported name, local alias, and range;
- multi-name and repeated statements have canonical ordering;
- `from m import n` and `from m import n as local` retain the same target name;
- star, unnamed-module, `import m as x`, and dynamic imports are ineligible;
- parse failures preserve the existing fail-closed behavior;
- existing `PythonImportFact` tuples and module relation projection are
  unchanged;
- repeated parsing and equivalent source ordering are deterministic;
- facts remain syntax-complete within the existing scanner input bound.

Run the file and record the new fact nodes as RED. Implement only the frozen
fact and collector, then run the same command twice and require GREEN:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider tests/test_python_graph.py
```

**Stop:** any solution that needs runtime imports, usage analysis, re-export
walking, or changes existing module facts returns to design review.

---

### Task 2: RED/GREEN Exact Symbol Selector and Resolution

**Files:** `tests/test_python_graph.py`, `tests/test_graph_resolution.py`,
`tests/test_graph_store.py`, `src/context_search_tool/python_graph.py`,
`src/context_search_tool/graph_resolution.py`,
`src/context_search_tool/sqlite_store.py`.

Write RED matrices for:

- absolute and relative named-module imports resolving to one same-unit file;
- root and `src` layouts and package `__init__.py` projection;
- external, unresolved, escaping, cross-unit, and multi-path modules;
- unique top-level `type` and `function` targets both resolve while the
  relation keeps persisted `target_kind=python_declaration`;
- zero target, duplicate definitions, and same-name type/function ambiguity;
- method/nested declaration, any kind outside the frozen two-kind set, other
  producer, other language, other file, stale, deleted, and re-export rows
  excluded;
- R1 selector cannot affect any non-Python or non-import relation;
- lookup is exact-file bounded and deterministically ordered;
- integrity accepts actual target kind `type` and `function` only for the
  closed P15 selector and still rejects every target unit/kind/name mismatch.

Run this command once before implementation and record the new matrix nodes as
RED. Then implement the smallest R1 branch and SQLite lookup, keep generic
resolution byte-for-byte outside the closed selector, and run it twice GREEN:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_python_graph.py tests/test_graph_resolution.py \
  tests/test_graph_store.py
```

**Stop:** wildcard queries, first-match selection, speculative dual edges, or
generic integrity weakening are reject conditions.

---

### Task 3: RED/GREEN Materialization and Producer Lifecycle

**Files:** `tests/test_python_graph.py`, `tests/test_graph_lifecycle.py`,
`tests/test_incremental_refresh.py`, `src/context_search_tool/python_graph.py`,
`src/context_search_tool/graph_lifecycle.py`.

Write RED tests proving:

- every eligible fact preserves its module edge and adds at most one exact
  declaration edge;
- relation ID, producer, target name/file/unit, selector metadata, first
  position, aliases, and occurrence count are deterministic;
- alias variants merge by target identity without changing score;
- after deduplication, the exact-symbol projection has its own 256-row cap and
  `graph_omitted_imported_symbols`; module rows are never displaced;
- missing, `0`, and v1 ready metadata become stale with
  `producer_contract_changed` and require one authoritative rebuild;
- refresh resolves associations before one atomic ready-v2 publication;
- a second v2 refresh parses zero files and reuses vector rows/embedding IDs;
- change/revert and delete/restore converge;
- malformed, negative, and future producer versions fail closed.

Run the command once before implementation and record the new lifecycle and
materialization nodes as RED. Then implement exact rows, change only the
producer version constant from 1 to 2, and run the command twice GREEN:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_python_graph.py tests/test_graph_lifecycle.py \
  tests/test_incremental_refresh.py tests/test_index_health.py
```

**Stop:** do not raise schema versions, caps, or force unrelated re-embedding.

---

### Task 4: Verify Expansion, Max Merge, Trace, and Compatibility

**Files:** `tests/test_resolved_graph_expansion.py`,
`tests/test_retrieval_pipeline.py`, `tests/test_retrieval_trace_pipeline.py`,
`tests/test_p8_graph_contract.py`; product edits only if a frozen contract is
missing, followed by review.

Add focused tests showing:

- a seed importer reaches the exact declaration chunk through the symbol edge;
- existing module expansion remains available;
- both edges use imports weight `0.85`, decay `0.8`,
  `graph_imports_match`, and the existing reason;
- duplicate module/symbol support merges by max, never sum;
- same-chunk merge and different-chunk winners in both directions preserve one
  final path;
- direct evidence dominance plus winner-consistent trace/reason behavior remain
  intact for the selected chunk;
- unresolved/ambiguous/stale rows add no candidate or reason;
- P9-P11 quotas, membership logic, overflow, and work caps are unchanged;
- non-Python and protected P8 fixtures remain byte-stable where P15 is
  ineligible.

Run this command once before any Task 4 product correction and record each new
node's actual RED/GREEN result. Existing expansion may make a node GREEN; do
not manufacture a failure or edit working code. Only an observed RED authorizes
the minimum correction allowed by the spec. Do not edit relation policy,
ranking weights, selection, planner, or budgets. End with two GREEN runs:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_resolved_graph_expansion.py tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py tests/test_p8_graph_contract.py
```

---

### Task 5: Tracked Acceptance Checker and Protected Regression

**Files:** `tests/p15_python_import_symbol_acceptance.py`,
`tests/test_p15_python_import_symbol_acceptance.py`,
`tests/fixtures/p15_python_import_symbols/input_manifest.json`, and the exact
protected test paths in the commands below.

Extend the Task 0 checker for candidate captures. RED/GREEN coverage must
reject:

- non-baseline or dirty implementation identity not fully hashed;
- changed source/query/gold/role/threshold/held-out identities;
- a gain without exact relation, target signal, and target chunk witnesses;
- required loss, noise increase, protected-winner drift, or unapproved
  membership drift;
- altered relation policy, budgets, caps, schema, planner, or query;
- nondeterministic normalized captures across either repeat or canonical versus
  reversed input order;
- absolute paths, source bodies, credentials, or unredacted provider errors;
- performance or work-cap failure;
- online stable-projection failure or missing request accounting;
- missing raw-CI report or anything other than selected/executed/passed
  `8/8/8` with zero failures/errors.

Run both commands once before extending the checker and record every new
acceptance node as RED. Then implement only the checker/protection changes and
run each command twice GREEN:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  "${P15_FOCUSED_TESTS[@]}"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  "${P15_PROTECTED_TESTS[@]}"
```

A test expectation may change only when it directly represents an eligible P15
exact relation; document every such overlay. Before Task 6, run independent
Standards and Spec reviews over the complete candidate diff. Resolve findings
with RED tests now, rerun both commands, and freeze the reviewed implementation
hash. No finding may be deferred into the immutable capture attempt.

---

### Task 6: Paired Real-Corpus Hash and Online Gates

**Files:** ignored immutable evidence under one durable `.quality/p15-runs/`
root. Freeze the reviewed candidate hash before capture; no product edit is
allowed afterward within that attempt.

1. Freeze the candidate implementation and manifest hashes.
2. On the two development corpora only, capture baseline and candidate in two
   separate processes for canonical and reversed input order on fresh indexes
   using hash embeddings/planner off; require normalized equality across both
   repeat and order axes.
3. Verify every development gain manually against the persisted relation,
   target signal, target chunk, score part, and stage trajectory.
4. Only after the candidate is immutable and development hash gates pass, let
   the independent reviewer open the held-out payload and verify its sealed
   digest. Opening it here starts final acceptance, not a development loop.
5. Capture held-out baseline and candidate on fresh indexes with the same
   two-repeat/two-order matrix, then apply final R2 to RedInk, daily, held-out,
   and combined micro totals.
6. If every hash gate passes, capture baseline/candidate twice on all three
   corpora with the fixed planner-off online BGE identity and check only the
   pre-frozen stable projection.
7. Run the exact Task 5 protected commands, raw CI `8/8/8`, and the full suite.
8. Bind commands, module origins, implementation/source/manifest/report
   hashes, timing, work counters, and outcomes in
   `.quality/p15-runs/$P15_ATTEMPT_ID/final/evidence-manifest.json`.

The acceptance CLI contract is:

```bash
"$P15_PYTHON" "$P15_ACCEPTANCE" freeze-candidate \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT"
for P15_REPEAT in 1 2; do
  for P15_VARIANT in baseline candidate; do
    for P15_ORDER in canonical reverse; do
      "$P15_PYTHON" "$P15_ACCEPTANCE" capture \
        --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
        --phase candidate --corpora development --profile hash \
        --variant "$P15_VARIANT" --repeat "$P15_REPEAT" \
        --input-order "$P15_ORDER"
    done
  done
done
"$P15_PYTHON" "$P15_ACCEPTANCE" compare \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
  --phase candidate --corpora development --profile hash

test -n "${P15_HELDOUT_PAYLOAD:-}"
"$P15_PYTHON" "$P15_ACCEPTANCE" open-heldout \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
  --sealed-payload "$P15_HELDOUT_PAYLOAD"
for P15_REPEAT in 1 2; do
  for P15_VARIANT in baseline candidate; do
    for P15_ORDER in canonical reverse; do
      "$P15_PYTHON" "$P15_ACCEPTANCE" capture \
        --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
        --phase candidate --corpora heldout --profile hash \
        --variant "$P15_VARIANT" --repeat "$P15_REPEAT" \
        --input-order "$P15_ORDER"
    done
  done
done
"$P15_PYTHON" "$P15_ACCEPTANCE" compare \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
  --phase candidate --corpora all --profile hash

for P15_REPEAT in 1 2; do
  for P15_VARIANT in baseline candidate; do
    "$P15_PYTHON" "$P15_ACCEPTANCE" capture \
      --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
      --phase candidate --corpora all --profile online-bge \
      --variant "$P15_VARIANT" --repeat "$P15_REPEAT" \
      --input-order canonical
  done
done
"$P15_PYTHON" "$P15_ACCEPTANCE" compare \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" \
  --phase candidate --corpora all --profile online-bge
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  --junitxml="$P15_RUN_ROOT/final/protected.junit.xml" \
  "${P15_PROTECTED_TESTS[@]}"
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P15_PYTHON" -m pytest -q -p no:cacheprovider \
  --junitxml="$P15_RUN_ROOT/final/full-suite.junit.xml"
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P15_PYTHON" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json --profile ci \
  --output "$P15_RUN_ROOT/final/raw-ci.json" \
  --markdown "$P15_RUN_ROOT/final/raw-ci.md"
"$P15_PYTHON" "$P15_ACCEPTANCE" check \
  --manifest "$P15_MANIFEST" --run-root "$P15_RUN_ROOT" --gate final \
  --protected-junit "$P15_RUN_ROOT/final/protected.junit.xml" \
  --full-suite-junit "$P15_RUN_ROOT/final/full-suite.junit.xml" \
  --raw-ci "$P15_RUN_ROOT/final/raw-ci.json" \
  --write-evidence-manifest \
  "$P15_RUN_ROOT/final/evidence-manifest.json"
```

The final checker requires raw CI aggregate
`selected/executed/passed=8/8/8`, `failed=0`, and `errors=0`; the evidence
manifest binds the JSON hash. A Markdown summary alone is not gate evidence.

Disposition is exactly one of:

- `ship`: every hash, online, regression, privacy, performance, and work gate
  passes;
- `blocked`: required online service or independently sealed source is
  unavailable without substitution;
- `reject`: any causal, quality, compatibility, determinism, privacy,
  performance, or work gate fails.

Do not tune or recapture after a valid failing comparison. A harness defect
requires preserving the failed evidence, independent review, a new attempt ID,
and identical frozen product/gold/threshold inputs.

---

### Task 7: Final Evidence Audit, Documentation, and Disposition

**Files:** this plan, companion design, conditional `README.md`, conditional
`docs/retrieval-quality.md`, conditional
`roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`, and
`.quality/p15-runs/$P15_ATTEMPT_ID/final/evidence-manifest.json`.

Request two independent reviews:

1. **Standards review:** repository rules, scope, lifecycle, determinism,
   bounded work, privacy, test quality, and diff allowlist.
2. **Spec review:** R1/R2, exact eligibility, module preservation, cardinality,
   scoring reuse, oracle attribution, held-out seal, and every gate.

Confirm first that the captured candidate hash equals the implementation hash
reviewed before Task 6. Reviewers must inspect raw strict reports as well as
normalized projections; normalized output cannot conceal a strict failure.
Any actionable product/spec finding now makes this attempt `reject`; preserve
the evidence and start a separately identified attempt from the applicable RED
task. Do not edit the captured product and recapture in place.

Only a `ship` disposition permits bounded user documentation stating that
exact imported type/function declarations add an additional Python import
relation. `reject` or `blocked` documentation records evidence and residual
limitations without claiming shipped behavior.

## Global Stop and Rollback Rules

Stop immediately when:

- R1 or R2 remains open;
- held-out identity, denominator, or gold is not sealed before oracle;
- oracle misses any R2 floor;
- implementation needs a forbidden mechanism or product path;
- module relations disappear, reorder, or lose cap capacity;
- target cardinality is guessed or integrity is weakened;
- relation evidence adds instead of max-merging;
- required loss, noise growth, winner drift, or unauthorized membership drift
  appears;
- planner/query/ranking/weight/quota/budget edits seem necessary;
- determinism, privacy, performance, work-cap, or protected regression fails;
- online stable-projection confirmation fails.

Rollback is surgical and evidence-preserving:

1. stop new captures and retain all raw evidence;
2. retain the exact candidate diff and list the P15-owned paths; do not mutate
   or discard the user's working tree automatically;
3. keep reviewed spec/plan, frozen manifest, harness, and reject record;
4. use a fresh baseline checkout/index to confirm the producer-v1 projection;
5. do not downgrade a user index in place;
6. report the failed gate and the smallest next design question. Any later fix
   requires explicit authorization and a new attempt ID.

No stop condition authorizes call graphs, constants, reranking, quotas, budget
growth, or a waiver.

## Implementation Record

Status: Not started. Document review complete; implementation not authorized.

```text
review:
  R1 decision/hash:
  R2 decision/hash:
  held-out denominator:

entry:
  behavior baseline:
  candidate identity:
  Python/SQLite:

frozen inputs:
  RedInk commit/inventory/content hash:
  daily commit/inventory/content hash:
  held-out URL/commit/license/inventory/content hash:
  manifest hash:

oracle:
  RED nodes/failures:
  hash repeats:
  required gain/items/cases/repos:
  losses/noise/winners/membership:
  relation attribution:
  performance/work/privacy:
  disposition:

implementation TDD:
  Task 1 RED/GREEN:
  Task 2 RED/GREEN:
  Task 3 RED/GREEN:
  Task 4 actual RED/GREEN and verification:
  Task 5 RED/GREEN:

paired candidate:
  hash baseline/candidate:
  online baseline/candidate:
  stable projection:
  performance/work:

regression:
  focused:
  full suite:
  diff/privacy audit:

review:
  Standards:
  Spec:

final disposition:
  ship | blocked | reject
  evidence manifest hash:
  residual limitations:
```

Do not fill this record with expected values. Record only commands actually
run and results actually observed.
