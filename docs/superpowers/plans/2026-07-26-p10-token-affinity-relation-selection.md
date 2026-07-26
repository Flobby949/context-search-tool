# P10 Token-Affinity Relation Selection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Draft for review; implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `3b10645` (main; quota machinery present, inert)
Design:
`docs/superpowers/specs/2026-07-26-p10-token-affinity-relation-selection-design.md`

**Goal:** One pre-committed experiment: token-only affinity gating on the
existing (currently inert) relation quota, with the direct+graph channel
co-occurrence specified and fixture-reproduced first.

**Architecture:** Three deltas over the shipped inert machinery: (1) a RED
co-occurrence test that forces relation expansion to merge graph score
parts onto an already-direct candidate in a synthetic fixture, with the
minimal merge fix if it fails; (2) `_DIRECT_AFFINITY_KEYS` narrowed to
token channels; (3) `RELATION_SLOTS_ENABLED = True` on the candidate
branch only. One paired A/B, one disposition, no post-comparison edits.

**Tech Stack:** Python 3.11+, existing retrieval core and P8/P9 harness.

## Global Constraints

- Supported runtime: `.quality/p5-runtime/bin/python`; tests via
  `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`.
- Pre-committed and frozen at review time (design §Pre-Committed Rules):
  the affinity key list `("lexical", "path_symbol", "direct_text",
  "planner_lexical", "planner_path_symbol")`, `RELATION_FINAL_SLOTS = 2`,
  `RELATION_SLOT_SCAN_DEPTH = 50`, the nine P9 ship gates with gate 2 at
  >= 2 credited required items. After the single comparison, no
  predicate/constant/gold edit; disposition only.
- If gate 2 fails, the record declares the selection-quota mechanism
  family exhausted (next class: overflow reranking); no further
  membership-rule variants.
- Product surface: `retrieval_core/selection.py`,
  `retrieval_core/relation_policy.py`, and — only if the Task 1 RED test
  fails — the minimal merge fix in `retrieval_core/expansion.py` and/or
  `retrieval_core/evidence_merge.py` (and `retrieval_core/candidates.py`
  only if the merge point proves to live there). Nothing else.
- Ledger constraint: in `tests/test_retrieval_pipeline.py` use bare,
  already-imported facade names only.
- Characterization: the zero-activity structural invariant must continue
  to hold (no protected fixture case fires the quota). A firing fixture
  case is a STOP, not a repin.
- Do not commit/push beyond the working branch unless the user asks; p6
  measurement-worker failures on this machine are environmental.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/retrieval_core/selection.py` | narrow `_DIRECT_AFFINITY_KEYS` |
| modify | `src/context_search_tool/retrieval_core/relation_policy.py` | `RELATION_SLOTS_ENABLED = True` (candidate branch) |
| modify if RED fails | `retrieval_core/expansion.py` / `evidence_merge.py` / `candidates.py` | direct+graph merge on one candidate |
| modify | `tests/test_retrieval_core_primitives.py` | affinity-key exactness + gate unit updates |
| modify | `tests/test_retrieval_pipeline.py` | co-occurrence RED, active-quota e2e repin |
| evidence | `$P9_RUN_ROOT` (existing) | reuse baseline.json; new candidate capture |

---

### Task 0: Verify The Standing Baseline

- [ ] **Step 0.1:** Clean tree at `3b10645`+ on a new branch
  `feat/p10-token-affinity`; full suite green (expected 2965 passed,
  p6 env failures aside).
- [ ] **Step 0.2:** Reuse `$P9_RUN_ROOT/baseline.json` (read the root
  from `.quality/p9-run-root.txt`). Verify it is still the behavior
  baseline: run one fresh capture of the CURRENT inert tree to
  `$P9_RUN_ROOT/inert-check.json` and assert selected membership per
  case equals `baseline.json` (a 10-line python comparison, ignoring
  `timing`/`implementation`). Never overwrite `baseline.json`.
- [ ] **Step 0.3:** `generate_p8_python_graph_manifest.py --check`
  passes; gold frozen, no edits.

### Task 1: RED/GREEN Channel Co-Occurrence

**Files:** `tests/test_retrieval_pipeline.py`; product only if RED fails.

- [ ] **Step 1.1: Write the RED co-occurrence test** (bare facade names):
  in the `_p9_quota_workflow` fixture (wire.py already carries the weak
  "entry"-token content), query `"handle_order api entry"` and assert on
  the QueryBundle result or — since wire may not be selected — assert at
  the seam `split_results_and_anchors` receives: monkeypatch
  `selection._apply_relation_slots` with a recorder (the P9a debugging
  pattern) and assert the overflow entry for `app/wire.py` carries BOTH
  a positive `lexical` part AND `resolved_relation` +
  `graph_imports_match`. Per the P9a record this currently FAILS (direct
  acquisition owns the candidate without graph parts).
- [ ] **Step 1.2: Diagnose the merge point.** Read
  `retrieval_core/expansion.py` `_resolved_relation_candidates` (its
  return path builds `RetrievalCandidate`s) and the candidate merge in
  `retrieval_core/candidates.py` / `retrieval.py`
  (`_merge_candidates`-style logic feeding ranking): determine why a
  chunk acquired directly does not receive the relation candidate's
  graph score parts. Record the finding in the implementation record
  BEFORE fixing.
- [ ] **Step 1.3: Implement the minimal merge** so the relation
  candidate's `graph_*`/`resolved_relation`/seed parts merge onto the
  existing direct candidate for the same chunk (existing
  `evidence_merge.merge_score_parts` semantics; no score VALUE changes to
  direct channels, no new keys). GREEN the co-occurrence test.
- [ ] **Step 1.4: Blast-radius check:** full suite. Expected effects and
  their handling:
  - characterization: score-part merging may change reasons/hashes; ANY
    delta here beyond none must be inspected — membership/order changes
    on fixtures are a STOP; added graph keys on already-selected direct
    results change internal-bundle projections → if hashes move, follow
    the P7/P9 overlay precedent with a structural assertion that ONLY
    score-part key additions occurred (no membership/order/score-value
    drift).
  - `test_p5_protected_direct.py` and `test_resolved_graph_expansion.py`
    protect direct-candidate objects: verify the merge preserves
    protected-direct object equality where pinned; if a pin forbids the
    merge on protected chunks, exclude `protected_chunk_ids` from the
    merge exactly as the expansion already does for candidate creation.
- [ ] **Step 1.5:** Commit
  `fix: merge graph provenance onto direct candidates (P10 Task 1)`.

### Task 2: Token-Only Affinity Keys

- [ ] **Step 2.1: RED:** extend `test_relation_policy_values_are_exact`
  with the exact tuple assertion:

```python
    assert selection._DIRECT_AFFINITY_KEYS == (
        "lexical",
        "path_symbol",
        "direct_text",
        "planner_lexical",
        "planner_path_symbol",
    )
```

  and add a unit scenario: an overflow item with ONLY
  `{"semantic": 0.4, "resolved_relation": 1.0, "graph_imports_match":
  0.3}` is NOT eligible; the same item plus `"lexical": 0.2` IS.
- [ ] **Step 2.2: GREEN:** narrow `_DIRECT_AFFINITY_KEYS` in
  `selection.py`; run the primitives + pipeline suites. Commit
  `feat: token-only affinity gate (P10 Task 2)`.

### Task 3: Activate On The Candidate Branch

- [ ] **Step 3.1: RED:** flip the policy exactness expectation to
  `RELATION_SLOTS_ENABLED is True`; repin the two P9a-inert e2e tests to
  ACTIVE expectations: `app/wire.py` (token-affine, graph-merged after
  Task 1) is selected with reasons `"relation slot"` and
  `"static module dependency"`; repeated and reverse-registration runs
  identical; ContextPack smoke includes `app/wire.py`.
- [ ] **Step 3.2: GREEN:** set `RELATION_SLOTS_ENABLED = True`. Full
  suite; characterization zero-activity invariant must hold (STOP
  otherwise). Commit `feat: activate token-affinity relation slots
  (P10 Task 3)`.

### Task 4: The Single Paired A/B

- [ ] **Step 4.1:** Candidate capture twice (deterministic modulo
  `timing`/`implementation`), then one compare against the standing
  `baseline.json`:

```bash
P9=$(cat .quality/p9-run-root.txt); R=$(cat .quality/p8-baseline-root.txt)
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  capture "$PWD" "$R" "$P9/candidate-p10.json" 2
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  compare "$P9/baseline.json" "$P9/candidate-p10.json" "$P9/comparison-p10.json"
```

- [ ] **Step 4.2:** Apply the fixed disposition from the gates. `ship` →
  merge with `RELATION_SLOTS_ENABLED = True`; anything else → revert the
  flag to False on the branch (keeping Tasks 1-2, which are
  independently reviewed), record, and declare the mechanism family
  exhausted per the design.

### Task 5: Record

- [ ] **Step 5.1:** Implementation record: co-occurrence diagnosis, all
  gate values, quota admission list (which paths took slots), and the
  disposition. On non-ship: the exhaustion declaration.
- [ ] **Step 5.2:** On `ship` only: README/retrieval-quality/roadmap
  notes in a separate docs commit.

## Stop Conditions

- Characterization fixture membership/order drift at Task 1, or any
  fixture case with `relation_slot_selected > 0` at Task 3.
- Gate 2 failure → mechanism family exhausted; no variant proposals.
- Any post-comparison predicate/constant edit.

## Implementation Record

Status: Not started. Record only observed, verified results.
