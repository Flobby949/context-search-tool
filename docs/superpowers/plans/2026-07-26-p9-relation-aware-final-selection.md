# P9 Relation-Aware Final Selection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Ready for review; implementation not authorized or started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `b9fa965` (main with P8 merged)
Design:
`docs/superpowers/specs/2026-07-26-p9-relation-aware-final-selection-design.md`

**Goal:** Let relation-supported candidates enter final selection through a
bounded reserved quota, credited mechanically, without changing any score.

**Architecture:** One selection-stage rule inside the P7 selector: scan the
ranked list to depth 50 for path-distinct relation-supported candidates,
take at most 2, evict only non-relation-supported, non-protected lowest
ranks, and record relation provenance as the credit witness.

**Tech Stack:** Python 3.11+, existing retrieval core; no new dependencies.

## Global Constraints

- Supported acceptance runtime: `.quality/p5-runtime/bin/python`
  (Python 3.13.12, SQLite 3.51.2); run tests with
  `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" <runtime> -m pytest -q`.
- No score, weight, decay, budget, acquisition, or schema change; the only
  product files touched are the three in the design change surface.
- `RELATION_FINAL_SLOTS = 2`, `RELATION_SLOT_SCAN_DEPTH = 50`; do not tune
  either after seeing the first A/B comparison (design stop rule).
- Characterization handling follows the P7 overlay precedent; baseline.json
  is never edited.
- Reuse the P8 gold manifest, pinned sources, and paired runner unchanged;
  capture a fresh baseline at `b9fa965` before any candidate exists and
  never overwrite it.
- Do not commit/push beyond the working branch unless the user asks.
- Known environment failures (p6 measurement workers on this machine) are
  out of scope; the dirty-tree p6 gates clear on each commit.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/retrieval_core/relation_policy.py` | quota constants |
| modify | `src/context_search_tool/retrieval_core/selection.py` | quota scan/eviction/provenance |
| modify | `src/context_search_tool/retrieval_core/tracing.py` | `relation_slot_selected` final-stage counter |
| modify | `tests/test_retrieval_core_primitives.py` | policy constants exactness |
| modify | `tests/test_retrieval_pipeline.py` | end-to-end quota behavior (ledger-safe: bare facade names only) |
| modify | `tests/test_exploration_p7.py` or `tests/test_retrieval_trace.py` | trace counter |
| modify | `tests/test_retrieval_core_characterization.py` | `EXPECTED_P9_FINAL_TRACE_HASHES` overlay |
| create | evidence under a task `mktemp -d` root | baseline/candidate captures, comparison |

---

### Task 0: Freeze The P9 Baseline

**Files:** evidence only; no product changes.

- [ ] **Step 0.1:** Verify entry state: `git rev-parse HEAD` = `b9fa965`
  ancestor tip of main, clean tree, full suite green
  (expected: 2960 passed).
- [ ] **Step 0.2:** Create `P9_RUN_ROOT="$(mktemp -d /private/tmp/cst-p9-run.XXXXXX)"`.
  Reuse the existing pinned clones (re-clone via
  `tests/p8_python_graph_identity.py` validation if the P8 root is gone).
- [ ] **Step 0.3:** Capture the baseline with the P8 runner against the
  CURRENT tree (which is the baseline for P9):
  `p8_real_python_graphs_acceptance.py capture <repo-root> <repos-dir>
  $P9_RUN_ROOT/baseline.json 2`. Run twice; normalized projections must be
  byte-identical. Record structural counts.
- [ ] **Step 0.4:** Validate gold via
  `generate_p8_python_graph_manifest.py --check` and record the manifest
  hash. Gold is frozen; no edits in P9.

### Task 1: RED/GREEN Quota Constants And Selector Unit

**Files:**
- Modify: `src/context_search_tool/retrieval_core/relation_policy.py`
- Modify: `src/context_search_tool/retrieval_core/selection.py`
- Test: `tests/test_retrieval_core_primitives.py`, `tests/test_retrieval_pipeline.py`

**Interfaces:**
- Produces: `relation_policy.RELATION_FINAL_SLOTS == 2`,
  `relation_policy.RELATION_SLOT_SCAN_DEPTH == 50`, and a pure helper in
  `selection.py`:

```python
def apply_relation_slots(
    ordered: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    protected_chunk_ids: set[str],
) -> tuple[list[core_types._ExpandedResult], int]:
    """Return the final selection with up to RELATION_FINAL_SLOTS quota
    swaps applied, plus the relation_slot_selected count."""
```

  A result is relation-supported when its `score_parts` contain any key in
  `relation_policy.GRAPH_SCORE_KEYS` and its metadata-carried provenance
  names a persisted relation ID (already available on expansion results;
  thread it through `_ExpandedResult` score_parts — no new dataclass
  field).

- [ ] **Step 1.1: Write the failing policy test** in
  `tests/test_retrieval_core_primitives.py`, extending
  `test_relation_policy_values_are_exact`:

```python
    assert relation_policy.RELATION_FINAL_SLOTS == 2
    assert relation_policy.RELATION_SLOT_SCAN_DEPTH == 50
```

- [ ] **Step 1.2: Write the failing selector unit test** (same file):
  construct ~15 synthetic `_ExpandedResult` items over distinct paths where
  items at ranks 13 and 14 carry `graph_imports_match` in score_parts and
  ranks 11-12 do not; assert:
  - returned selection contains the rank-13/14 paths;
  - the evicted items are exactly the previous ranks 11-12;
  - a protected item at rank 12 (chunk_id in `protected_chunk_ids`) is
    never evicted (construct a second scenario);
  - an already relation-supported member of the selection is never
    evicted;
  - count returned equals the number of swaps;
  - no relation-supported candidate below `RELATION_SLOT_SCAN_DEPTH` is
    considered (place one at rank 51 and assert it stays out);
  - with zero relation-supported candidates the output is the identical
    list object contents and count 0.
- [ ] **Step 1.3:** Run
  `pytest -q tests/test_retrieval_core_primitives.py -k relation` —
  expected RED (missing constants/helper).
- [ ] **Step 1.4: Implement** the constants and `apply_relation_slots`;
  wire it into `assemble_query_output` immediately after the existing P7
  path-diverse cut, before `RetrievalResult` construction; append reason
  `"relation slot"` to swapped-in items via the existing reasons channel.
- [ ] **Step 1.5:** Run the same selection twice; assert list equality in
  the unit test (determinism). GREEN, twice; `git diff --check`; commit
  `feat: reserve relation-supported final slots (P9 Task 1)`.

### Task 2: RED/GREEN End-To-End And Trace Counter

**Files:**
- Modify: `src/context_search_tool/retrieval_core/tracing.py`
- Test: `tests/test_retrieval_pipeline.py`, `tests/test_retrieval_trace.py`

- [ ] **Step 2.1: Failing end-to-end test** in `test_retrieval_pipeline.py`
  (bare `query_repository`/`index_repository` names only — the migration
  ledger pins attribute-reference counts): extend the existing P8 mini
  workflow so one imported target (`app/wire.py`) shares no query token,
  add 12+ direct-matching sibling files so `wire.py` ranks below the
  final cut, and assert:
  - `app/wire.py` is selected;
  - its reasons contain `"relation slot"` and `"static module dependency"`;
  - final paths are unique and two repeated calls return identical order;
  - the top direct winner is unchanged versus the same query with the
    sibling set reduced (protected-winner witness).
- [ ] **Step 2.2: Failing trace test**: the final-selection stage decision
  counts include `["relation_slot_selected", N]` with the exact N from the
  pipeline fixture, following the `duplicate_result_path` precedent.
- [ ] **Step 2.3:** Implement the counter in `tracing.py` (same insertion
  style as `duplicate_result_path`); GREEN both tests twice; commit
  `feat: trace relation slot selections (P9 Task 2)`.

### Task 3: Characterization Overlay

**Files:**
- Modify: `tests/test_retrieval_core_characterization.py`

- [ ] **Step 3.1:** Run the characterization suite; collect the failing
  cases' actual final trace hashes (these are the P9 deltas).
- [ ] **Step 3.2:** Add `EXPECTED_P9_FINAL_TRACE_HASHES` and
  `_normalize_p9_final_trace_delta(actual, expected)` following the P7
  normalizer shape exactly: assert actual == P9 pinned hash, assert it
  differs from the P7 pinned value only for cases whose final stage shows
  `relation_slot_selected > 0` (a case with zero quota activity must keep
  its P7 hash), strip/restore the new counter like P7 did for
  `duplicate_result_path`, and chain it inside
  `test_characterization_matches_immutable_baseline` before the P7
  normalizer.
- [ ] **Step 3.3:** Full suite on the supported runtime — target: only the
  known p6 worker environment failures on a clean tree. Commit
  `test: pin P9 final-selection characterization overlay (P9 Task 3)`.

### Task 4: Paired A/B And Ship Gates

**Files:** evidence only.

- [ ] **Step 4.1:** Candidate capture (twice, deterministic-identical)
  into `$P9_RUN_ROOT/candidate.json`.
- [ ] **Step 4.2:** Extend the P8 `compare` gates in a P9 wrapper script
  under `tests/` only if gate arithmetic differs; otherwise reuse
  `compare` and evaluate the design's nine P9 gates from the report plus
  the quota-credit rule (a gain is credited only when the selected entry
  carries the `relation slot` reason and relation provenance).
- [ ] **Step 4.3:** Apply the fixed disposition. If gate 2 fails, stop:
  record the failure boundary; do not raise `RELATION_FINAL_SLOTS`.
- [ ] **Step 4.4:** On `ship`: run the standard p8_python quality profile
  (18/18, zero errors) and the fast-context comparison scoring script on
  the six-case subset; record all numbers.

### Task 5: Record And Docs

- [ ] **Step 5.1:** Fill this plan's Implementation Record with observed
  values only (both dispositions possible; a non-ship result records the
  boundary and stops, per the P8 precedent).
- [ ] **Step 5.2:** On `ship` only: README selection note +
  `docs/retrieval-quality.md` gate description + roadmap status line.
  Commit docs separately.

## Stop Conditions

- Any protected-direct winner change in unit/e2e tests.
- Characterization delta in a case with `relation_slot_selected == 0`.
- Gate 2 failure (insufficient credited gains) — report, do not tune.
- Latency regression > 5% on the paired mean.

## Implementation Record

Status: Not started. Record only observed, verified results.
