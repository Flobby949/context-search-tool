# P10 Token-Affinity Relation Selection v1 Design

Date: 2026-07-26
Status: Draft for review
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `3b10645` (main; relation quota present but inert)
Predecessor evidence: P9 plan implementation record (both A/B rounds,
P9a ablation, and the safety patch), P8 implementation record.

## Pre-Committed Rules (fixed before any comparison is run)

The P9/P9a stop-rule lesson is procedural: predicates must be frozen
before evidence is seen. P10 therefore pre-commits, in this document,
before any capture:

1. **Affinity definition (token-only):** a candidate has query affinity
   iff `score_parts` contains a positive value for at least one of
   `lexical`, `path_symbol`, `direct_text`, `planner_lexical`,
   `planner_path_symbol`. The near-universal hash-semantic channels
   (`semantic`, `planner_semantic`) and `signal` are excluded — P9a
   showed they gate almost nothing on real repositories.
2. **Channel co-occurrence semantics:** the P9a fixture finding — direct
   and graph acquisition do not co-occur on one candidate in synthetic
   fixtures while they do on real repositories — must be resolved by
   specification, not accident. P10 specifies: relation expansion MUST
   merge its score parts onto an existing direct candidate for the same
   chunk (the evidence_merge path), and a synthetic fixture MUST
   reproduce a merged direct+graph candidate; if the current pipeline
   cannot produce one, that is a P10 implementation task with its own
   RED test, not a fixture accommodation.
3. **Activation:** the quota reuses the inert P9 machinery
   (`RELATION_SLOTS_ENABLED` flips to True only inside P10's candidate
   tree during the A/B; main stays inert until a `ship` disposition).
4. **No tuning after first comparison:** eligibility, constants
   (`RELATION_FINAL_SLOTS = 2`, `RELATION_SLOT_SCAN_DEPTH = 50`), and
   the affinity key list are frozen at review time. One comparison, one
   disposition.

## Evidence Chain (why this exact mechanism)

- P8: import edges resolve correctly; relation candidates acquired but
  stall below final selection (`acquired_below_limit`).
- P9: unconditional quota — 36 firings, 0 required gains, 3 losses,
  combined recall −0.053. Falsified: rank order within
  relation-supported overflow does not correlate with gold at the
  margin.
- P9a: any-direct-evidence gate — hash-semantic scores are near
  universal, gate inert-in-fixtures/ineffective-in-reality, −0.035.
- fast-context comparison: every CST gold miss (`registry.py`,
  `decision_profile.py`, `decision_action.py`, `stock_code_utils.py`)
  shares a **query token with its own path or content**
  (registry↔"registry", profile↔"profile", action↔"action",
  code↔"code"). Token-level affinity discriminates exactly where
  hash-semantic affinity cannot: co-imported noise modules
  (`market_light_service`, `portfolio_alerts`, …) share no query token.

Hypothesis (falsifiable, one shot): with token-only affinity, quota
admissions on the frozen gold are predominantly gold support files, and
combined required Recall@12 improves by ≥ 2 credited items with no
required fallout.

## Mechanism Delta vs P9a (complete list)

1. `_DIRECT_AFFINITY_KEYS` loses `semantic`, `planner_semantic`,
   `signal`, `planner_hint`, `planner_signal`.
2. Relation-expansion merge onto direct candidates is specified and
   fixture-reproduced (new RED test; possible small change in
   `expansion.py`/`evidence_merge.py` merge path — this is the one new
   product surface, reviewed here).
3. Eviction additionally never removes an item with token affinity for
   the query AND a `support`-shaped path role? — NO. Rejected: role
   inference at selection time is new policy; eviction stays as shipped
   (rank-1 + relation-supported protected). Gate 3 remains the backstop.
4. Everything else (counter, schema v2, credit rule, characterization
   overlay, ship gates 1–9 from the P9 design) is reused verbatim.

## Ship Gates

Identical to the P9 design's nine gates, evaluated by the unchanged v2
runner. Gate 2 threshold: ≥ 2 credited required items. If it fails, the
selection-quota family is exhausted: the record must state that the next
mechanism class is overflow reranking (reading candidate content), and
no further membership-rule variants may be proposed.

## Change Surface

| file | responsibility |
| --- | --- |
| `retrieval_core/selection.py` | `_DIRECT_AFFINITY_KEYS` narrowing |
| `retrieval_core/relation_policy.py` | `RELATION_SLOTS_ENABLED = True` (candidate tree only until ship) |
| `retrieval_core/expansion.py` and/or `evidence_merge.py` | specified direct+graph merge (only if the RED co-occurrence test fails) |
| tests per plan | unit updates, co-occurrence RED, A/B |
