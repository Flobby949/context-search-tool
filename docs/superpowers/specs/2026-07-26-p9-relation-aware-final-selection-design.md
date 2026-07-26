# P9 Relation-Aware Final Selection v1 Design

Date: 2026-07-26
Status: Revised after adversarial review (r2)
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `b9fa965` (main with P8 producer merged)
Predecessor evidence:
`docs/superpowers/plans/2026-07-26-p8-python-static-structure-retrieval.md`
(implementation record, both A/B rounds and the ablation)

## Summary

P8 proved that resolved static import edges are acquired correctly and
cheaply, but stall below the final evidence line: relation-supported
candidates carry lower scores than direct lexical clusters and lose the
final `final_top_k` slots. P9 adds one bounded, deterministic selection
rule — a small reserved quota of final slots for relation-supported
results that would otherwise not be selected — without touching any
score, weight, decay, budget, or acquisition stage.

Review r2 note: the first draft assumed relation IDs were reachable at
selection time; code review showed expansion drops them (score parts are
float-only). This revision moves credit provenance to the acceptance
harness and keeps the product change strictly at membership + reason.

## Plan-Time Evidence

Three independent measurements converge on the same boundary:

1. **P8 paired A/B** (18 frozen gold cases, RedInk + daily): resolved
   imports exist (RedInk 35, daily 696 resolved-exact edges), relation
   candidates are acquired, yet zero credited required-item gains; the
   trajectory state is `acquired_below_limit` / `acquired_not_selected`.
2. **P8 ablation**: with the double-counting lexical channel removed,
   combined required recall is +0.0175 with two residual required
   `support` losses. In the graph-only ablation capture (session
   evidence directory `cst-p8-baseline.*/evidence/candidate-graphonly.json`,
   unversioned), the `daily-runtime-scheduler` selected list shows five
   graph-origin entries at ranks 7-12 while the weakly-matched required
   `src/config.py` drops out — selection pressure, not acquisition
   failure.
3. **fast-context comparison on the same frozen gold** (6-case subset):
   fast-context 20/21 vs CST 17/21 required Recall@12. Every CST miss —
   `src/services/stock_code_utils.py`, `src/agent/tools/registry.py`,
   `src/schemas/decision_profile.py`, `src/schemas/decision_action.py` —
   is a `support`-role file with an existing resolved-exact import edge
   from an already-selected result.

The failure boundary is precisely: *final selection has no channel for
relation-supported evidence; weak-direct support files lose slots to
same-cluster direct noise.*

## Problem Statement

`final_top_k` selection (P7, implemented in
`selection.split_results_and_anchors`) is path-diverse over one globally
ranked list. Rank order is dominated by direct evidence. A file whose
relevance is primarily structural — imported by the file the query is
about, but sharing few query tokens — ranks below directly-matched
sibling files and misses selection even when its resolved relation
evidence is exact.

Raising relation scores would reshuffle ranking corpus-wide (the exact
failure mode P8's ablation exposed for the lexical channel). The fix
must therefore live in selection, not scoring.

## Goals

1. A required/support path acquired through resolved relation expansion
   can enter the final selection through a bounded, attributable
   channel.
2. The mechanism is deterministic, path-diverse, explainable, and
   changes no score, no rank value, and no candidate acquisition.
3. Quota selections are mechanically identifiable (reason string +
   trace counter), and the acceptance harness independently verifies a
   persisted resolved relation witness for each credited gain (fixing
   the P8 gate-2 attribution gap without threading relation IDs through
   the retrieval core).
4. The paired A/B harness, frozen gold, and pinned repositories from P8
   are reused; the capture schema is extended (v2) to record the quota
   flag.

## Non-Goals

- No relation weight, decay, confidence, or ranking change.
- No new acquisition stage, no expansion-budget change.
- No result/ContextPack schema change; RetrievalTrace stays schema
  version 1 (one additional informational decision counter, following
  the P7 `duplicate_result_path` precedent).
- No exploration/probe changes.
- No gold or metric redefinition beyond the credit rule below.
- No cross-encoder/model reranking.

## Causal Hypothesis

If the final selection reserves a small number of slots for the
highest-ranked not-yet-selected relation-supported results, then the
observed misses (support files with exact import edges) enter the final
set at the cost of the lowest-ranked non-protected direct selections —
which, in the frozen gold, were predominantly reviewer-labeled noise
(same-cluster sibling services). Combined required Recall@12 should rise
on the same frozen cases without new noise categories.

## Architecture Decision

### Selected: A Reserved Relation Quota Inside `split_results_and_anchors`

The quota is a post-pass inside `split_results_and_anchors`
(`retrieval_core/selection.py`), which owns the ranked `expanded` list,
the path-diverse cut, and the final-stage decision counting. No other
call site changes.

Definitions (per merged `_ExpandedResult`):

- **relation-supported**: `"resolved_relation"` is present in
  `score_parts` together with at least one
  `relation_policy.GRAPH_SCORE_KEYS` key. The resolved expansion pathway
  only reads edges with resolution `resolved_exact`/`resolved_unique`
  (`GraphReadSession` filters at the SQL level), so this predicate is
  already backed by persisted resolved rows; no per-candidate re-check
  is performed. Note: through score-part merging, results that ALSO have
  direct evidence may carry these keys; that is acceptable for the
  take-side predicate (the file did receive resolved-graph support).
- **protected**: `evidence_priority == 0` (the existing per-result
  protected-direct definition already used by this function). Protection
  is not derived from `protected_chunk_ids`, which is not in scope here.
- **anchor-kind**: `_evidence_anchor_kind(...) != ""`; such items are
  never eligible for the quota (they belong to the anchors channel).

Algorithm, after the ordinary path-diverse selection `S` (size
`final_top_k`) is determined and before results are finalized:

1. Scan the ranked, path-deduplicated list beyond the cut, up to
   overall rank `RELATION_SLOT_SCAN_DEPTH`, for items that are
   relation-supported, not anchor-kind, and whose path is not in `S`.
2. Take up to `RELATION_FINAL_SLOTS` such items in ranked order.
3. For each taken item, evict the lowest-ranked member of `S` that is
   not protected. If every remaining member is protected, stop taking.
4. Append taken items to the end of the final selection in ranked
   order (they do not splice into the middle; reading order keeps the
   ordinary ranking prefix stable).
5. Append the reason `"relation slot"` to each taken item through the
   existing reasons channel, and count the swaps as
   `relation_slot_selected`.

Constants (in `relation_policy.py`, covered by the existing exactness
test):

```text
RELATION_FINAL_SLOTS = 2
RELATION_SLOT_SCAN_DEPTH = 50
```

Acknowledged residual risk: eviction cannot see which selected path
seeded a taken item (provenance is not threaded through the core), so a
swap could in principle evict the importer of the file it admits. The
bottom-of-list eviction makes this unlikely (seeds are high-ranked), and
ship gate 3 (no required fallout) plus gate 1 are the empirical
backstop; if the A/B shows importer eviction, that is a recorded failure
boundary, not a tuning invitation.

### Rejected: Score Boost For Relation Support

Weight tuning reshuffles the global order; the P8 ablation showed a
single redundant channel moved RedInk required recall from 1.0 to 0.941.

### Rejected: Threading Relation IDs Through The Retrieval Core

Would require widening `RetrievalCandidate`/`_ExpandedResult` beyond
float score parts and touching expansion, merge, and retrieval plumbing
— a large change surface for provenance the harness can obtain from the
index directly.

### Rejected: Separate "Related Files" Response Section

Changes the public results contract for every consumer.

### Rejected: Larger `final_top_k`

Dilutes precision for every query; noise gates would fail.

## Selection Contract Details

- Language-neutral: any producer whose relations resolve
  (Java, frontend, MyBatis, Python, test associations) feeds the same
  predicate.
- Determinism: items are considered strictly in existing ranked order;
  eviction picks the strictly lowest-ranked non-protected member;
  appended order is ranked order. Repeated runs and fresh/reverse
  registration-order indexes must produce byte-identical final path
  lists.
- Trace: `relation_slot_selected` (0..RELATION_FINAL_SLOTS) joins the
  final-selection decision counts emitted by this function. Because a
  swap removes one selected item and adds one, the existing bucket
  arithmetic is unchanged; `relation_slot_selected` is an informational
  counter and is excluded from the
  `selected + duplicate_result_path + result_limit == input_count`
  invariant. It appears (value 0 included) in every trace, so every
  characterization trace hash changes — see Compatibility.
- Evidence anchors are unaffected.
- ContextPack/exploration consume the same QueryBundle and inherit the
  membership change; a quota-selected result flows through pack
  classification like any non-protected result (smoke-tested in the
  plan).
- When the graph is stale/legacy or no eligible item exists, final
  membership and order are byte-identical to today (the trace differs
  only by the new zero-valued counter).

## Compatibility And Protected Behavior

- Characterization: the counter is present in every final-selection
  trace, so ALL 13 fixture case hashes change. Handling follows the P7
  precedent exactly: pin `EXPECTED_P9_FINAL_TRACE_HASHES` for all
  cases; the P9 normalizer asserts each actual hash equals its P9 pin,
  strips the `relation_slot_selected` entry from both decision-count
  lists (before the P7 normalizer pops its own entry, preserving that
  code's index arithmetic), and then delegates to the existing P7/
  followup normalizer chain against the immutable baseline. The
  zero-activity invariant is structural, not hash-based: any case whose
  `relation_slot_selected == 0` must show final membership and order
  identical to its P7-era selection.
- Protected direct results (`evidence_priority == 0`) are never
  evicted; a dedicated test pins this.
- P5/P6 suites, quality ci profile, and the full suite stay green aside
  from the reviewed characterization overlay and the pinned
  decision-count tuples that existing trace/pipeline/formatter tests
  assert (enumerated in the plan).

## Benchmark Design

Reuse: pinned RedInk/daily commits and hashes, the 18-case frozen gold
manifest, closed-world noise rule, and the paired runner flow. The
runner's capture schema is extended to version 2: each selected entry
additionally records `relation_slot: bool` (true iff the result's
reasons contain `"relation slot"`). A fresh baseline capture against
`b9fa965` is taken with the v2 runner before any candidate exists
(baseline entries all record `relation_slot: false`).

### Credit Rule (fixes the P8 gate-2 attribution gap)

A required-item gain is credited to P9 when:

1. the candidate capture's selected entry for that path has
   `relation_slot == true`; and
2. the capture's existing witness lookup finds a persisted resolved
   (`resolved_exact` or `resolved_unique`) relation row whose target is
   that path and whose source file path is among the same case's
   selected paths; when several rows qualify, the witness is the row
   with the lexicographically smallest `(source_path, relation_id)`.

Gains without both conditions remain reported but uncredited.

### Ship Gates

1. Per-repository required-role Recall@12 non-decreasing vs the new
   baseline.
2. Combined required Recall@12 improves by at least 2 required items,
   and every counted improvement is quota-credited.
3. No required path present in the baseline top 12 falls out.
4. At least 3 cases gain a quota-credited required path, including at
   least 2 in daily.
5. Reviewer-labeled aggregate noise ratio does not increase by more than
   0.02 and no case gains more than one new noise path.
6. The frozen daily continuity query retains 12 unique paths and both
   required paths.
7. Protected direct winners are unchanged in every case.
8. Deterministic repeated captures are byte-identical after removing
   the `timing` and `implementation` sections.
9. Query latency mean regression <= 5% (the quota adds one bounded
   in-memory scan per query; witness lookups are harness-side only).

If gate 2 fails, P9 is reported as insufficient without adjusting
`RELATION_FINAL_SLOTS` or `RELATION_SLOT_SCAN_DEPTH`; the failure
boundary chooses the next mechanism.

## Determinism

Final path order, quota decisions, eviction choices, and the counter
must be independent of insertion, registration, SQLite row, and
dictionary order. Fresh/reverse fixture runs and repeated captures must
agree byte-for-byte (captures: after removing timing/implementation).

## Change Surface

| file | responsibility |
| --- | --- |
| `src/context_search_tool/retrieval_core/relation_policy.py` | the two quota constants |
| `src/context_search_tool/retrieval_core/selection.py` | quota scan, eviction, reason, `relation_slot_selected` in `_FINAL_TRACE_DECISION_KEYS` and `split_results_and_anchors` |
| `tests/p8_real_python_graphs_acceptance.py` | capture schema v2 (`relation_slot` per entry), credit rule in compare |
| tests per plan | unit, pinned-tuple updates, characterization overlay, A/B rerun |

`tracing.py` needs no change (it passes decision counts through).
Explicitly out of scope: expansion, ranking, retrieval.py, formatters
(the reason string flows through the existing channel), ContextPack,
exploration, MCP schemas.
