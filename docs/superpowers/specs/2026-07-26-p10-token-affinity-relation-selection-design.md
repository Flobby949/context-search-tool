# P10 Token-Affinity Relation Selection v1 Design

Date: 2026-07-26
Status: Revised after adversarial review (r2)
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `3b10645` (main; relation quota present but inert)
Predecessor evidence: P9 plan implementation record (both A/B rounds,
P9a ablation, and the safety patch), P8 implementation record.

Review r2 note: the first draft specified a direct+graph merge change
and claimed token-level noise discrimination. Code review showed (a) the
merge already happens for non-protected direct chunks — the suppression
is the deliberate protected-skip in expansion — and any merge change
would NOT be score-neutral (graph keys feed `_combined_score` and global
normalization), and (b) named noise files DO share query tokens. Both
claims are corrected below; the merge change is deleted and explicitly
forbidden.

## Pre-Committed Rules (fixed before any comparison is run)

1. **Affinity definition (token-only, six keys):** a candidate has query
   affinity iff `score_parts` contains a positive value for at least one
   of `lexical`, `path_symbol`, `direct_text`, `planner_lexical`,
   `planner_path_symbol`, `token_coverage`. Rationale: the first five
   are acquisition-channel evidence but top-k gated (a rank-20-40 gold
   target may carry none); `token_coverage` is the pipeline's faithful
   content-vs-query token measure, computed for every ranked candidate,
   and the fast-context evidence ("shares a query token with its own
   path or content") supports exactly it. The near-universal
   hash-semantic channels (`semantic`, `planner_semantic`) and `signal`
   are excluded — P9a showed they gate almost nothing.
   Subset-safety: under P9a's ten-key predicate (which included the
   near-universal `semantic`), protected fixtures showed zero quota
   activity; the six-key predicate is strictly narrower in practice, so
   the zero-activity invariant is expected to hold — and remains a STOP
   condition, not an assumption.
2. **Channel co-occurrence is a fixture-shape task, not a product
   change.** The pipeline already merges relation score parts onto
   direct candidates for the same chunk via `merge_candidates` →
   `evidence_merge.merge_score_parts`; co-occurrence is suppressed only
   for protected direct chunks (`expansion.py` resolved path skips
   `protected_chunk_ids`, sourced from
   `ranking.protected_direct_chunk_ids`) and by the legacy path's
   seed-score condition. The synthetic co-occurrence test must therefore
   shape its fixture so the graph target is a NON-protected direct
   candidate (weak/planner-channel direct evidence). Any change to
   expansion/merge/scoring to force co-occurrence is FORBIDDEN in P10:
   merging graph keys onto protected direct candidates changes
   `_combined_score`, global max-normalization, `has_relation_support`,
   evidence classes, and reasons — a scoring experiment, not this one.
3. **Activation:** the quota reuses the inert P9 machinery;
   `RELATION_SLOTS_ENABLED` flips to True only inside P10's candidate
   tree during the A/B; main stays inert until a `ship` disposition.
4. **One comparison, one disposition.** Eligibility, constants
   (`RELATION_FINAL_SLOTS = 2`, `RELATION_SLOT_SCAN_DEPTH = 50`), and
   the six-key list are frozen at review time. No post-comparison edits.
5. **Pre-committed regression check:** the P9 loss triple —
   `daily-portfolio-risk src/services/decision_signal_service.py`,
   `daily-prefetch-tests tests/test_data_fetcher_prefetch_stock_names.py`,
   `redink-image-flow backend/utils/image_compressor.py` — must remain
   selected in the candidate capture (they are baseline top-12 members;
   losing any is a gate-3 failure and is called out by name in the
   record).

## Evidence Chain (restated honestly)

- P8: import edges resolve; relation candidates stall below final
  selection.
- P9: unconditional quota — 36 firings, 0 required gains, 3 losses,
  −0.053. Rank order within relation-supported overflow does not
  correlate with gold at the margin.
- P9a: any-direct-evidence gate — hash-semantic near-universal, −0.035.
- Token analysis of the frozen gold: all four recurring gold misses
  share query tokens with their own path/content (registry↔"registry",
  profile↔"profile", action↔"action", stock_code_utils↔"code"). BUT so
  does some co-imported noise (`portfolio_alerts.py`↔"portfolio" in
  daily-portfolio-risk; `market_light_service.py`↔"market","service" in
  daily-alert-worker). Token affinity is therefore a *hypothesis about
  net effect*, not an established discriminator: the bet is that
  token-affine gold outranks token-affine noise within the
  relation-supported overflow often enough to clear the gates.

Hypothesis (falsifiable, one shot): with the six-key affinity gate,
combined required Recall@12 improves by at least 3 credited items
(3/57 ≥ 0.05, the unchanged runner's gate-2 arithmetic) with no
required fallout.

## Mechanism Delta vs Shipped State (complete list)

1. `_DIRECT_AFFINITY_KEYS` becomes exactly
   `("lexical", "path_symbol", "direct_text", "planner_lexical",
   "planner_path_symbol", "token_coverage")`.
2. `RELATION_SLOTS_ENABLED = True` (candidate tree only until ship).
3. Nothing else: no expansion/merge/scoring/eviction change; counter,
   schema v2, credit rule, characterization pins reused verbatim. With
   no acquisition change, characterization hashes must not move at all —
   any characterization delta is a STOP.

## Ship Gates

The v2 runner's eleven gates, evaluated unchanged. Gate 2 as
implemented: `credited_gain / 57 >= 0.05`, i.e. **≥ 3 credited required
items** (the design's earlier "≥ 2" was inconsistent with the runner and
is corrected here, before any capture). If gate 2 fails, the
selection-quota mechanism family is exhausted: the record must state
that the next mechanism class is overflow reranking (reading candidate
content), and no further membership-rule variants may be proposed.

## Change Surface

| file | responsibility |
| --- | --- |
| `retrieval_core/selection.py` | `_DIRECT_AFFINITY_KEYS` = the frozen six keys |
| `retrieval_core/relation_policy.py` | `RELATION_SLOTS_ENABLED = True` (candidate tree only until ship) |
| tests per plan | co-occurrence fixture-shape proof, unit updates, e2e repin, A/B |

Expansion, evidence_merge, candidates, ranking, retrieval, formatters,
ContextPack, exploration: untouched.
