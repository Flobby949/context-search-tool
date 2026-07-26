# P9 Relation-Aware Final Selection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Revised after adversarial review (r2); implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `b9fa965` (main with P8 merged)
Design:
`docs/superpowers/specs/2026-07-26-p9-relation-aware-final-selection-design.md`

**Goal:** Let relation-supported results enter final selection through a
bounded reserved quota, credited by the acceptance harness, without changing
any score.

**Architecture:** One post-pass inside `split_results_and_anchors`
(`retrieval_core/selection.py`): scan the path-deduplicated ranked list to
overall rank 50 for relation-supported, non-anchor, path-distinct items,
take at most 2 in ranked order, evict only non-protected
(`evidence_priority != 0`) lowest ranks, append takes at the end, add the
reason `"relation slot"`, and count `relation_slot_selected`.

**Tech Stack:** Python 3.11+, existing retrieval core; no new dependencies.

## Global Constraints

- Supported acceptance runtime: `.quality/p5-runtime/bin/python`
  (Python 3.13.12, SQLite 3.51.2); run tests with
  `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`.
- Product files touched: `retrieval_core/relation_policy.py` and
  `retrieval_core/selection.py` only. The harness file
  `tests/p8_real_python_graphs_acceptance.py` is extended (capture schema
  v2). No score/weight/decay/budget/acquisition change; `tracing.py`,
  `retrieval.py`, expansion, ranking, formatters stay untouched.
- `RELATION_FINAL_SLOTS = 2`, `RELATION_SLOT_SCAN_DEPTH = 50`; do not tune
  either after seeing the first A/B comparison (design stop rule).
- Characterization: pin new hashes for ALL 13 fixture cases (the counter is
  visible in every trace); baseline.json is never edited.
- Reuse the P8 gold manifest and pinned sources unchanged; capture a fresh
  v2 baseline at `b9fa965` before any candidate exists and never overwrite
  it.
- In `tests/test_retrieval_pipeline.py` use bare, already-imported facade
  names (`query_repository`, `index_repository`) — the migration ledger
  pins attribute-reference counts.
- Do not commit/push beyond the working branch unless the user asks.
- Known environment failures (p6 measurement workers on this machine) are
  out of scope; the dirty-tree p6 gates clear on each commit.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/retrieval_core/relation_policy.py` | quota constants |
| modify | `src/context_search_tool/retrieval_core/selection.py` | quota post-pass, reason, `_FINAL_TRACE_DECISION_KEYS` entry, counting |
| modify | `tests/p8_real_python_graphs_acceptance.py` | capture schema v2, `relation_slot` flag, credit rule |
| modify | `tests/test_retrieval_core_primitives.py` | policy constants + selector unit tests |
| modify | `tests/test_retrieval_pipeline.py` | end-to-end quota behavior; pinned decision tuples at 8942-8949, 9020; monkeypatch guard 8965 |
| modify | `tests/test_retrieval_trace_pipeline.py` | pinned tuples at ~461-468, 544, 968 and the sum-invariant assertion at ~469 |
| modify | `tests/test_formatters.py` | pinned decision rendering at ~126 |
| modify | `tests/test_retrieval_core_characterization.py` | `EXPECTED_P9_FINAL_TRACE_HASHES` overlay (all 13 cases) |
| modify | `tests/test_p8_real_python_graphs_acceptance.py` | v2 schema + credit-rule tests |
| create | evidence under `$P9_RUN_ROOT` (mktemp) | captures, comparison |

---

### Task 0: Freeze The P9 Baseline

**Files:** `tests/p8_real_python_graphs_acceptance.py` (schema v2 first),
`tests/test_p8_real_python_graphs_acceptance.py`; then evidence only.

- [ ] **Step 0.1:** Verify entry: clean tree on main at `b9fa965` (or its
  ff-descendant with no product diffs), full suite green (expected 2960
  passed on the supported runtime).
- [ ] **Step 0.2: RED for capture v2.** In
  `tests/test_p8_real_python_graphs_acceptance.py` extend the synthetic
  capture builder so every selected entry carries
  `"relation_slot": False`, set the expected `schema_version` to 2, and
  assert `check` rejects a v1 payload. Run
  `pytest -q tests/test_p8_real_python_graphs_acceptance.py` — RED.
- [ ] **Step 0.3: Implement v2** in `p8_real_python_graphs_acceptance.py`:
  `CAPTURE_SCHEMA_VERSION = 2`; in the capture loop set
  `entry["relation_slot"] = "relation slot" in result.reasons`; `check`
  accepts only version 2. GREEN; commit
  `test: bump P9 acceptance capture schema to v2`.
- [ ] **Step 0.4: Prepare pinned sources.** If the P8 clone root is gone:

```bash
export P9_RUN_ROOT="$(mktemp -d /private/tmp/cst-p9-run.XXXXXX)"
git clone https://github.com/HisMax/RedInk.git "$P9_RUN_ROOT/RedInk"
git -C "$P9_RUN_ROOT/RedInk" checkout 4d48722344594cf00e0498f0e1ed3df9cd4fd6be
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git "$P9_RUN_ROOT/daily_stock_analysis"
git -C "$P9_RUN_ROOT/daily_stock_analysis" checkout 487e49e565ffd1b96a7cf4d855f99cee3c981eaa
```

  Then validate via `p8_python_graph_identity.validate_protected_source`
  for both repos (counts 28/203 and both hash pairs).
- [ ] **Step 0.5: Baseline capture (twice):**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  capture "$PWD" "$P9_RUN_ROOT" "$P9_RUN_ROOT/baseline.json" 2
```

  and a second run to `baseline-repeat.json`. The two captures must be
  byte-identical after deleting the top-level `timing` and
  `implementation` keys (compare with a 5-line python snippet). All
  baseline entries must have `relation_slot: false`. Never overwrite
  `baseline.json` afterwards.
- [ ] **Step 0.6:** `generate_p8_python_graph_manifest.py --check` passes;
  record the manifest hash. Gold is frozen; no edits in P9.

### Task 1: RED/GREEN Quota Constants And Selector Unit

**Files:**
- Modify: `src/context_search_tool/retrieval_core/relation_policy.py`
- Modify: `src/context_search_tool/retrieval_core/selection.py`
- Test: `tests/test_retrieval_core_primitives.py`

**Interfaces:**
- Produces: `relation_policy.RELATION_FINAL_SLOTS == 2`,
  `relation_policy.RELATION_SLOT_SCAN_DEPTH == 50`, and inside
  `selection.py` a pure helper the post-pass and tests share:

```python
def _apply_relation_slots(
    selected: list[core_types._ExpandedResult],
    overflow: list[core_types._ExpandedResult],
) -> tuple[
    list[core_types._ExpandedResult],
    list[core_types._ExpandedResult],
    int,
]:
    """Return (final_selection, swapped_out, relation_slot_selected).

    `selected` is the ordinary path-diverse selection in ranked order;
    `overflow` is the remaining path-deduplicated ranked tail, already
    truncated so that len(selected) + len(overflow) <=
    RELATION_SLOT_SCAN_DEPTH and stripped of anchor-kind items by the
    caller. Eligibility: "resolved_relation" in score_parts and any
    GRAPH_SCORE_KEYS key present. Protection: evidence_priority == 0
    members of `selected` are never evicted. Takes append in ranked
    order; each take evicts the lowest-ranked non-protected member.
    """
```

- [ ] **Step 1.1: Failing policy test** — extend
  `test_relation_policy_values_are_exact`
  (`tests/test_retrieval_core_primitives.py:331`):

```python
    assert relation_policy.RELATION_FINAL_SLOTS == 2
    assert relation_policy.RELATION_SLOT_SCAN_DEPTH == 50
```

- [ ] **Step 1.2: Failing selector unit tests** (same file), building
  `_ExpandedResult` items with the existing test constructors. Scenarios:
  - takes at overflow ranks 1-2 (score_parts
    `{"graph_imports_match": 0.3, "resolved_relation": 1.0}`) enter; the
    two lowest-ranked `selected` members with `evidence_priority=2` are
    evicted; count == 2; final order = surviving selected order + takes
    appended in ranked order;
  - a `selected` tail member with `evidence_priority == 0` is never
    evicted (construct a selection whose last two members are protected;
    only one take happens against the single non-protected member);
  - an overflow item without `resolved_relation` (bare
    `graph_imports_match` only) is not eligible;
  - zero eligible overflow items → returned selection equals input list
    contents, swapped_out empty, count 0;
  - determinism: calling twice on copies yields identical outputs.
- [ ] **Step 1.3:** Run
  `pytest -q tests/test_retrieval_core_primitives.py -k relation` —
  expected RED (missing constants and helper).
- [ ] **Step 1.4: Implement** the constants and `_apply_relation_slots`,
  and wire the post-pass into `split_results_and_anchors`
  (selection.py:80-164): after the ordinary path-diverse selection is
  determined and before trace decisions are finalized, build `overflow`
  from the remaining path-deduplicated ranked, non-anchor items up to
  overall rank `RELATION_SLOT_SCAN_DEPTH`, apply the helper, append the
  reason `"relation slot"` to takes via the existing reasons list, and
  keep evicted items out of `results` (they are counted per Step 2.2).
- [ ] **Step 1.5:** GREEN twice; `git diff --check`; commit
  `feat: reserve relation-supported final slots (P9 Task 1)`.

### Task 2: RED/GREEN Trace Counter, Pinned Tuples, End-To-End

**Files:**
- Modify: `src/context_search_tool/retrieval_core/selection.py`
- Test: `tests/test_retrieval_pipeline.py`,
  `tests/test_retrieval_trace_pipeline.py`, `tests/test_formatters.py`

- [ ] **Step 2.1: Failing counter contract.** Add to
  `_FINAL_TRACE_DECISION_KEYS` (selection.py:46-53) the new literal
  `"relation_slot_selected"`, TEST-FIRST by updating the pinned
  decision-count expectations to include `["relation_slot_selected", N]`:
  - `tests/test_retrieval_trace_pipeline.py:461-468` (exact tuple) and
    the invariant at line ~469, which becomes: the sum of all decision
    counts EXCLUDING `relation_slot_selected` equals
    `final_stage.input_count` (a swap moves one item out and one in, so
    the selected/limit buckets stay balanced; the new counter is
    informational);
  - the further exact tuples at `test_retrieval_trace_pipeline.py:544`
    and `:968`;
  - `tests/test_retrieval_pipeline.py:8942-8949` and `:9020`, and the
    `_FINAL_TRACE_DECISION_KEYS` monkeypatch guard at `:8965`;
  - `tests/test_formatters.py:126` rendering expectation.
  Run those suites — RED with the old tuples.
- [ ] **Step 2.2: Implement counting** in `split_results_and_anchors`
  (same style as `duplicate_result_path` at selection.py:133-135):
  swapped-out items increment `result_limit` (they were cut by policy),
  takes count toward `selected`, and `relation_slot_selected` records
  the number of swaps. GREEN.
- [ ] **Step 2.3: Failing end-to-end test** in
  `tests/test_retrieval_pipeline.py` (bare facade names): extend the
  P8 mini workflow (`_p8_mini_workflow`, :12024) with 12+ direct-matching
  sibling files sharing the query tokens so `app/wire.py` (no query
  token) ranks below the ordinary cut; assert:
  - `app/wire.py` is selected and its reasons contain
    `"relation slot"` and `"static module dependency"`;
  - final paths unique; two repeated calls identical;
  - the rank-1 direct winner is the same as in the unmodified mini
    workflow (protected-winner witness);
  - a reverse-registration variant (index with plugins reversed via
    `build_v5_index_snapshot(..., graph_plugins=list(reversed(...)))`)
    returns the identical final path list.
- [ ] **Step 2.4: ContextPack smoke** (same test file): build the context
  pack via the bare `build_context_pack`-equivalent public path already
  used in the file, assert the quota-selected `app/wire.py` appears as a
  pack item without error. GREEN twice; commit
  `feat: trace and prove relation slot selections (P9 Task 2)`.

### Task 3: Characterization Overlay

**Files:** `tests/test_retrieval_core_characterization.py`

- [ ] **Step 3.1:** Run the characterization suite; ALL 13 cases fail on
  `trace_json_sha256` (the counter is present in every trace). Collect
  each case's actual hash.
- [ ] **Step 3.2:** Add `EXPECTED_P9_FINAL_TRACE_HASHES` (all 13 keys) and
  `_normalize_p9_final_trace_delta(actual, expected)` chained BEFORE the
  existing P7 normalizer inside
  `test_characterization_matches_immutable_baseline`:
  - assert each actual hash equals its P9 pin;
  - substitute the P7-pinned hash (`EXPECTED_P7_FINAL_TRACE_HASHES`)
    for each case so the untouched P7 normalizer still validates its own
    pin and the baseline substitution chain;
  - in `full_stage_ledgers`, assert the final stage contains the entry
    `["relation_slot_selected", 0]` for the fixture cases (zero-activity
    structural invariant: fixture repos must not trigger the quota) and
    pop that entry before the P7 normalizer pops its
    `duplicate_result_path` entry, preserving the existing index
    arithmetic at characterization.py:262-263.
  If any fixture case shows `relation_slot_selected > 0`, STOP: that is
  an unreviewed behavior change on protected fixtures.
- [ ] **Step 3.3:** Full suite on the supported runtime — target: green on
  a clean tree except known worker failures. Commit
  `test: pin P9 final-selection characterization overlay (P9 Task 3)`.

### Task 4: Paired A/B, Credit Rule, Ship Gates

**Files:** `tests/p8_real_python_graphs_acceptance.py` (compare/credit),
`tests/test_p8_real_python_graphs_acceptance.py`; evidence.

- [ ] **Step 4.1: RED credit-rule tests** in the runner test file:
  synthetic captures where (a) a gained required path has
  `relation_slot: true` + a witness → credited; (b) gained with
  `relation_slot: false` → uncredited; (c) `relation_slot: true` but no
  witness row → uncredited and gate 2 unsatisfied. RED, then implement in
  `compare`: credit requires `relation_slot` AND `relation_witness`
  (already looked up at capture time; when several rows qualify the
  capture records the lexicographically smallest
  `(source_path, relation_id)`). GREEN; commit
  `test: credit quota-selected gains in the paired comparison (P9 Task 4a)`.
- [ ] **Step 4.2: Candidate capture (twice):** same command as Step 0.5
  with output `candidate.json` / `candidate-repeat.json`; identical after
  removing `timing`/`implementation`.
- [ ] **Step 4.3: Compare and evaluate the design's nine gates:**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  compare "$P9_RUN_ROOT/baseline.json" "$P9_RUN_ROOT/candidate.json" \
  "$P9_RUN_ROOT/comparison.json"
```

  Apply the fixed disposition. If gate 2 fails, stop and record; do not
  raise the constants.
- [ ] **Step 4.4: On `ship`:** run the standard p8_python quality profile
  (18/18, zero errors) and re-score the six-case fast-context subset;
  record all numbers.

### Task 5: Record And Docs

- [ ] **Step 5.1:** Fill this plan's Implementation Record with observed
  values only (either disposition; a non-ship result records the boundary
  and stops).
- [ ] **Step 5.2:** On `ship` only: README selection note,
  `docs/retrieval-quality.md` gate description, roadmap status line;
  separate docs commit.

## Stop Conditions

- Any protected-direct winner change in unit/e2e tests.
- Any characterization fixture case with `relation_slot_selected > 0`.
- Gate 2 failure (insufficient credited gains) — report, do not tune.
- Query latency mean regression > 5% in the paired comparison.

## Implementation Record

Status: Tasks 0-4 executed 2026-07-26; disposition **reject** (stop rule
applied); Task 5 ship docs intentionally not written; branch left
unmerged.

```text
entry: main b9fa965, clean tree, full suite 2960 passed.
baseline capture (v2 runner): deterministic twice; all relation_slot
  false; gold manifest verified.

implementation (branch feat/p9-relation-final-selection):
  capture schema v2 (relation_slot per selected entry);
  RELATION_FINAL_SLOTS=2 / RELATION_SLOT_SCAN_DEPTH=50;
  _apply_relation_slots post-pass in split_results_and_anchors;
  relation_slot_selected decision counter (informational, excluded from
  the bucket-sum invariant); reason "relation slot"; internal trace
  reason mapped to the frozen schema-v1 vocabulary at the tracing
  boundary (retrieval_trace/models.py is P4-frozen and untouched).

review-driven contract refinements recorded during RED/GREEN:
  1. eviction protects the rank-1 winner and relation-supported
     selections; the design's evidence_priority==0 proxy marked every
     original-direct result, so the quota could never fire;
  2. eligibility narrowed to resolved import support and excludes
     ranker-penalized generated artifacts: on the protected P5 quality
     fixtures the broad GRAPH_SCORE_KEYS predicate admitted
     generated/test artifacts through tests/routes edges
     (generic-test-conventions regression caught by the quality gate).

verification state before A/B: unit + e2e + registration-order
  determinism + ContextPack smoke green; characterization overlay pins
  all 13 case hashes with a structural zero-activity invariant (quota
  fires on no protected fixture); full suite 2963 passed, 0 non-env
  failures.

paired A/B (baseline b9fa965 vs candidate, both captures deterministic):
  quota fired 36 times across the 18 gold cases;
  newly satisfied required items: ZERO;
  lost required (gate 3 FAIL): daily-portfolio-risk
    src/services/decision_signal_service.py (support),
    daily-prefetch-tests tests/test_data_fetcher_prefetch_stock_names.py
    (test), redink-image-flow backend/utils/image_compressor.py
    (support);
  recall: RedInk 1.0 -> 0.941, daily 0.8 -> 0.75,
    combined 0.860 -> 0.807 (delta -0.053);
  gates 1/2/3/4/5 FAIL; 6-11 pass; latency unchanged (0.503s).
  disposition: reject. No constant was tuned after the comparison.

falsified hypothesis, precisely: "highest-ranked not-yet-selected
  relation-supported overflow ~= the missing gold support files" is
  false on the pinned repositories. The overflow's top relation-
  supported entries are OTHER imported modules of the seeds (noise per
  the closed world), ranked 13-14 by residual direct evidence, while
  the gold support targets (registry.py, decision_profile.py,
  decision_action.py) sit at ranks ~20-40. Rank order within the
  relation-supported set does not correlate with gold relevance at the
  margin; eviction additionally removed required files that happened to
  carry no resolved import support in that query's expansion.

P9a follow-up round (same session, user-directed):
  mechanism: eligibility additionally requires nonzero direct evidence
  on the candidate itself (the record's "target-affinity gate").
  fixture finding: direct and graph acquisition do not co-occur on one
  candidate in the synthetic fixture (direct acquisition owns the
  candidate without graph parts), so the gated quota is inert there;
  the e2e tests pin that safe behavior.
  real A/B: quota still fired 30 times (hash-embedding semantic scores
  are near-universal, so "any direct evidence" gates almost nothing);
  combined recall 0.860 -> 0.825 (-0.035), two required support losses.
  disposition: reject. Iteration stopped here deliberately: narrowing
  the affinity predicate further after two seen comparisons would be
  fitting the gate to the gold.

safety patch (same day): RELATION_SLOTS_ENABLED = False gates the
  post-pass off at the call site; helper logic and unit tests stay for
  the successor; counter remains present (value 0), so the v2 captures,
  characterization pins, and schema hold. Verified: zero quota firings
  and selected membership identical to the b9fa965 baseline on the
  pinned repositories.

next-phase boundary (evidence for the successor design):
  membership rules keyed on relation support alone cannot discriminate
  gold from co-imported noise; the missing signal is query affinity of
  the relation TARGET itself (semantic/lexical match of the candidate's
  own content), i.e. the discriminator fast-context obtains by reading
  candidates. A bounded target-affinity gate on quota admission (e.g.
  requiring nonzero direct token/semantic evidence on the candidate) or
  a lightweight rerank of the relation-supported overflow are the two
  smallest reviewed mechanisms consistent with this record.
  P9a adds: the affinity definition must exclude the near-universal
  hash-semantic channel BEFORE the next comparison is run (token-level
  evidence only), and the direct/graph channel co-occurrence semantics
  in candidate merging must be specified explicitly, because the two
  channels currently meet only on real repositories, not in synthetic
  fixtures.
```
