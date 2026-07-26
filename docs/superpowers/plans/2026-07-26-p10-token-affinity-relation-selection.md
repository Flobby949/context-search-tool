# P10 Token-Affinity Relation Selection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Revised after adversarial review (r2); implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `3b10645` (main; quota machinery present, inert)
Design:
`docs/superpowers/specs/2026-07-26-p10-token-affinity-relation-selection-design.md`

**Goal:** One pre-committed experiment: six-key token affinity on the
existing inert relation quota. No acquisition, merge, or scoring change.

**Architecture:** Two product deltas only: `_DIRECT_AFFINITY_KEYS`
narrowed to the frozen six keys (including `token_coverage`), and
`RELATION_SLOTS_ENABLED = True` on the candidate branch. The channel
co-occurrence question is settled by a fixture-shape test (the merge
already exists for non-protected direct chunks); any product change to
force co-occurrence is forbidden. One paired A/B, one disposition.

**Tech Stack:** Python 3.11+, existing retrieval core and P8/P9 harness.

## Global Constraints

- Supported runtime: `.quality/p5-runtime/bin/python`; tests via
  `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`.
- Frozen at review time: the six-key affinity list, both quota
  constants, and gate 2 = the runner's implemented
  `credited_gain / 57 >= 0.05` (≥ 3 credited items). The runner is NOT
  edited; the disposition is read from its eleven-gate report.
- Product surface: `retrieval_core/selection.py` (key list) and
  `retrieval_core/relation_policy.py` (flag) ONLY. Expansion,
  evidence_merge, candidates, ranking, retrieval, formatters: untouched.
- With no acquisition change, characterization must not move at all:
  any characterization failure at any task is a STOP, never a repin.
  Same for the quality suites (`test_quality_p3.py`, `test_quality_p5.py`)
  and the literal `("relation_slot_selected", 0)` pins at
  `tests/test_formatters.py:130`, `tests/test_retrieval_pipeline.py:8950,9026`,
  `tests/test_retrieval_trace_pipeline.py:468,549,974` — these fire only
  on fixture-behavior drift, which this plan must not produce (fixture
  zero-activity is expected to survive activation; a firing fixture is a
  STOP).
- Ledger constraint: in `tests/test_retrieval_pipeline.py` use bare,
  already-imported names; `relation_policy` is NOT imported there —
  reach it as `selection.relation_policy` when monkeypatching.
- Do not commit/push beyond the working branch unless the user asks; p6
  measurement-worker failures on this machine are environmental.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/retrieval_core/selection.py` | six-key `_DIRECT_AFFINITY_KEYS` |
| modify | `src/context_search_tool/retrieval_core/relation_policy.py` | `RELATION_SLOTS_ENABLED = True` (candidate branch) |
| modify | `tests/test_retrieval_core_primitives.py` | key-list exactness, helper `parts` override, token_coverage scenarios, flag expectation flip |
| modify | `tests/test_retrieval_pipeline.py` | co-occurrence fixture-shape test; three e2e repins |
| evidence | `$P9_RUN_ROOT` (existing) | reuse baseline.json; new candidate capture |

---

### Task 0: Verify The Standing Baseline

- [ ] **Step 0.1:** Clean tree on branch `feat/p10-token-affinity` from
  main (`3b10645`+); full suite green (2965+ passed, p6 env aside).
- [ ] **Step 0.2:** `P9=$(cat .quality/p9-run-root.txt)` must contain
  `baseline.json`; `R=$(cat .quality/p8-baseline-root.txt)` must contain
  the `RedInk` and `daily_stock_analysis` checkouts (if `/private/tmp`
  was wiped, re-clone per the P9 plan Task 0 Step 0.4 commands and
  validate via `p8_python_graph_identity.validate_protected_source`).
  Then verify the standing baseline:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  capture "$PWD" "$R" "$P9/inert-check.json" 1
```

  and assert per-case selected path lists in `inert-check.json` equal
  `baseline.json` (10-line python; ignore `timing`/`implementation`).
  Never overwrite `baseline.json`.
- [ ] **Step 0.3:** `generate_p8_python_graph_manifest.py --check`
  passes; gold frozen.

### Task 1: Fixture-Shape Co-Occurrence Proof (no product change)

**Files:** `tests/test_retrieval_pipeline.py` only.

- [ ] **Step 1.1: Write the co-occurrence test.** Bare names; patch the
  flag and record the seam:

```python
def test_direct_and_graph_evidence_co_occur_for_unprotected_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _p9_quota_workflow(tmp_path)
    monkeypatch.setattr(
        selection.relation_policy, "RELATION_SLOTS_ENABLED", True
    )
    seen: dict[str, dict[str, float]] = {}
    original = selection._apply_relation_slots

    def recorder(selected, overflow):
        for item in overflow:
            seen[str(item.file_path)] = dict(item.score_parts)
        return original(selected, overflow)

    monkeypatch.setattr(selection, "_apply_relation_slots", recorder)
    query_repository(repo, "handle_order api entry", DEFAULT_CONFIG)

    wire = seen.get("app/wire.py")
    assert wire is not None
    assert wire.get("token_coverage", 0.0) > 0.0
    assert "resolved_relation" in wire and "graph_imports_match" in wire
```

  Expected first run: the token_coverage/graph assertions reveal the
  actual fixture state. If `app/wire.py` lacks graph keys because its
  direct acquisition is PROTECTED (evidence-priority-0 original_direct —
  the mechanism at `expansion.py` resolved-path skip), reshape the
  FIXTURE, not the product: weaken wire's direct evidence (e.g. remove
  the literal "entry" from its content so it matches only via
  `token_coverage`-relevant tokens after ranking, or add stronger
  competing files) until wire is acquired weakly/unprotected AND carries
  merged graph keys. Record the final fixture shape and the observed
  parts in the implementation record. Product edits are FORBIDDEN here;
  if no fixture shape can produce co-occurrence, that is a STOP with the
  diagnosis recorded (it would falsify the design's premise that real
  repos' co-occurrence is reproducible synthetically).
- [ ] **Step 1.2:** Commit
  `test: prove direct+graph co-occurrence on unprotected targets (P10 Task 1)`.

### Task 2: Six-Key Affinity List

- [ ] **Step 2.1: RED.** In `tests/test_retrieval_core_primitives.py`:
  - extend `_slot_item` with an optional `parts` override:

```python
def _slot_item(path, *, priority=2, graph=False, resolved=False,
               score=0.5, parts=None):
    if parts is None:
        parts = {"lexical": score} if score else {}
        ...
```

  - extend `test_relation_policy_values_are_exact` with

```python
    assert selection._DIRECT_AFFINITY_KEYS == (
        "lexical",
        "path_symbol",
        "direct_text",
        "planner_lexical",
        "planner_path_symbol",
        "token_coverage",
    )
```

  - add two scenarios: overflow item with
    `parts={"semantic": 0.4, "resolved_relation": 1.0,
    "graph_imports_match": 0.3}` is NOT eligible; the same plus
    `"token_coverage": 0.1` IS eligible.
  Run `-k relation` — RED (tuple mismatch; semantic currently counts).
- [ ] **Step 2.2: GREEN.** Set `_DIRECT_AFFINITY_KEYS` to the six keys in
  `selection.py`. No existing unit test relies on removed keys (they all
  use `lexical`). Full primitives + pipeline suites. Commit
  `feat: token-only affinity keys (P10 Task 2)`.

### Task 3: Activate On The Candidate Branch

- [ ] **Step 3.1: RED.** Flip the pin in
  `test_relation_policy_values_are_exact` to
  `RELATION_SLOTS_ENABLED is True`, and repin all THREE e2e tests:
  - `test_relation_slot_recovers_graph_only_target_end_to_end`
    (test_retrieval_pipeline.py:~12134): replace the inert-invariant
    block (`"relation slot" not in result.reasons`) with active
    expectations — `app/wire.py` selected, reasons contain
    `"relation slot"` and `"static module dependency"`, `paths[0] ==
    "app/api.py"`, repeat-call identical (uses the Task 1 fixture
    shape);
  - `test_relation_slot_selection_is_registration_order_independent`
    (:~12162): forward == reverse path lists (assert wire present in
    both);
  - `test_relation_slot_result_flows_into_context_pack` (:~12195): add
    `assert "app/wire.py" in item_paths`.
- [ ] **Step 3.2: GREEN.** `RELATION_SLOTS_ENABLED = True` in
  `relation_policy.py`. Full suite: characterization, quality suites,
  and every `("relation_slot_selected", 0)` pin must be untouched (STOP
  on any of them). Commit
  `feat: activate token-affinity relation slots (P10 Task 3)`.

### Task 4: The Single Paired A/B

- [ ] **Step 4.1:** Candidate capture twice (deterministic modulo
  `timing`/`implementation`) and one compare:

```bash
P9=$(cat .quality/p9-run-root.txt); R=$(cat .quality/p8-baseline-root.txt)
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  capture "$PWD" "$R" "$P9/candidate-p10.json" 2
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  compare "$P9/baseline.json" "$P9/candidate-p10.json" "$P9/comparison-p10.json"
```

- [ ] **Step 4.2:** Read the eleven-gate report; gate 2 passes only at
  ≥ 3 credited items. Verify the pre-committed P9-loss-triple regression
  check (all three paths still selected). Disposition: `ship` → merge
  with the flag True; anything else → revert the flag to False on the
  branch (keeping Tasks 1-2), record, declare the mechanism family
  exhausted.

### Task 5: Record

- [ ] **Step 5.1:** Implementation record: co-occurrence fixture shape
  and observed parts, all gate values, the quota admission list, the
  P9-triple check, disposition. On non-ship: the exhaustion declaration
  naming overflow reranking as the next mechanism class.
- [ ] **Step 5.2:** On `ship` only: README/retrieval-quality/roadmap
  notes in a separate docs commit.

## Stop Conditions

- Any characterization, quality-suite, or `relation_slot_selected` pin
  failure at any task (no repins in P10).
- Task 1 unable to produce co-occurrence by fixture shape alone.
- Gate 2 failure → mechanism family exhausted; no variant proposals.
- Any post-comparison predicate/constant edit.

## Implementation Record

Status: Tasks 0-4 executed 2026-07-26; disposition **reject**;
activation reverted (Tasks 1-2 retained); mechanism family declared
EXHAUSTED per the pre-committed rule.

```text
entry: main 8886af7, clean, 2965 passed; inert membership verified
  equal to baseline.json; gold manifest verified.

Task 1 (fixture-shape co-occurrence): PROVEN with zero product change.
  Mechanism: lengthening the query dilutes wire.py's token coverage
  below the strong-original-direct threshold (0.2 corroboration bound,
  ranking._has_strong_original_direct_evidence), leaving it an
  unprotected weak-direct candidate; the existing merge_candidates path
  then combines token_coverage with resolved_relation/
  graph_imports_match on one candidate. Confirms the design premise and
  the protected-skip diagnosis.

Task 2: six-key _DIRECT_AFFINITY_KEYS landed with unit coverage
  (semantic-only ineligible; +token_coverage eligible).

Task 3: activation with the six-key gate left every protected fixture
  at zero quota activity - characterization, quality suites, and all
  counter pins green on the full suite. STOP conditions never fired.

Task 4 (the single A/B, captures deterministic twice):
  quota admissions: 34, listed in the capture; ZERO gold targets among
  them - admissions are token-affine co-imported noise exactly of the
  shape the r2 review predicted (market_light_service via
  "market"/"service", stock_repo via "stock", decision_signal_summary
  via "decision", text/genai clients via path tokens).
  newly satisfied: none; credited: none.
  lost required (the pre-committed P9 triple, by name):
    daily-portfolio-risk src/services/decision_signal_service.py,
    daily-prefetch-tests tests/test_data_fetcher_prefetch_stock_names.py,
    redink-image-flow backend/utils/image_compressor.py.
  combined recall 0.860 -> 0.807 (-0.053). Gates 1-5 FAIL, 6-11 pass.
  disposition: reject. No post-comparison edits were made; the flag
  revert restores the inert machinery (full suite 2972 passed).

EXHAUSTION DECLARATION (per design ship-gate rule): the
selection-quota mechanism family - membership rules over the ranked
overflow keyed on relation support plus per-candidate evidence
predicates - is exhausted after three controlled failures (P9
unconditional, P9a any-direct-evidence, P10 token-affinity). The
consistent failure shape across all three: within relation-supported
overflow, rank and shallow per-candidate signals order co-imported
noise ABOVE gold support files, and the displaced bottom ranks
disproportionately contain weakly-matched required files. No further
membership-rule variants may be proposed. The next mechanism class is
overflow reranking: reading the content of relation-supported overflow
candidates against the query (the capability the fast-context
comparison showed is the actual discriminator).
```
