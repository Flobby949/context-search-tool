# P9 Relation-Aware Final Selection v1 Design

Date: 2026-07-26
Status: Draft for review
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
candidates that would otherwise not be selected — without touching any
score, weight, decay, budget, or acquisition stage.

## Plan-Time Evidence

Three independent measurements converge on the same boundary:

1. **P8 paired A/B** (18 frozen gold cases, RedInk + daily): resolved
   imports exist (RedInk 35, daily 696 resolved-exact edges), relation
   candidates are acquired, yet zero credited required-item gains; the
   trajectory state is `acquired_below_limit` / `acquired_not_selected`.
2. **P8 ablation**: with the double-counting lexical channel removed,
   combined required recall is +0.0175 with two residual required
   `support` losses; in the graph-only configuration the
   `daily-runtime-scheduler` case shows five graph-origin candidates
   entering ranks 7-12 while the weakly-matched required `src/config.py`
   drops out — selection pressure, not acquisition failure.
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

`final_top_k` selection (P7) is path-diverse over one globally ranked
list. Rank order is dominated by direct evidence (lexical, path/symbol,
direct text). A file whose relevance is primarily structural — imported
by the file the query is about, but sharing few query tokens — ranks
below directly-matched sibling files and misses selection even when its
resolved relation evidence is exact.

Raising relation scores would reshuffle ranking corpus-wide (the exact
failure mode P8's ablation exposed for the lexical channel). The fix
must therefore live in selection, not scoring.

## Goals

1. A required/support path with an exact resolved relation from a
   selected result can enter the final selection through a bounded,
   attributable channel.
2. The mechanism is deterministic, path-diverse, explainable, and
   changes no score, no rank, and no candidate acquisition.
3. Every quota selection carries provenance naming the persisted
   relation and its already-selected source path, so gains are credited
   mechanically (fixing the P8 gate-2 attribution gap).
4. The paired A/B harness, frozen gold, and pinned repositories from P8
   are reused unchanged.

## Non-Goals

- No relation weight, decay, confidence, or ranking change.
- No new acquisition stage, no expansion-budget change.
- No result/ContextPack/trace schema change (`results` shape is
  unchanged; the quota manifests as which results are selected plus one
  existing-style reason string).
- No exploration/probe changes.
- No gold or metric redefinition beyond the credit rule fix below.
- No cross-encoder/model reranking.

## Causal Hypothesis

If the final selection reserves a small number of slots for the
highest-ranked not-yet-selected relation-supported candidates, then the
observed misses (support files with exact import edges) enter the final
set at the cost of the lowest-ranked direct selections — which, in the
frozen gold, were predominantly reviewer-labeled noise (same-cluster
sibling services). Combined required Recall@12 should rise on the same
frozen cases without new noise categories.

## Architecture Decision

### Selected: A Reserved Relation Quota Inside The P7 Selector

After the existing P7 path-diverse scan produces the ordinary selection
order, and before results are materialized:

1. Identify the would-be selected set `S` of size `final_top_k`.
2. Scan the ranked list up to `RELATION_SLOT_SCAN_DEPTH` for candidates
   that are:
   - not in `S` by path (path-diverse like every P7 decision);
   - relation-supported: their score parts contain at least one
     `graph_*_match` key whose provenance seed chunk belongs to a path
     already in `S` (the capture/selection layer resolves this from the
     existing expansion score parts and seed bookkeeping);
   - backed by a persisted relation row whose resolution is
     `resolved_exact` or `resolved_unique`.
3. Take up to `RELATION_FINAL_SLOTS` such candidates in ranked order.
4. For each taken candidate, evict the lowest-ranked member of `S` that
   is **not itself relation-supported and not a protected direct
   winner** (the existing protected-direct set). If no evictable member
   exists, stop taking.
5. Record for each quota selection: the relation ID, source path, and
   the reason `relation slot` in the existing reasons channel.

Constants:

```text
RELATION_FINAL_SLOTS = 2
RELATION_SLOT_SCAN_DEPTH = 50
```

Both are selection-stage constants in `relation_policy.py`, subject to
the same exactness tests as the existing policy values. No configuration
knob is added in v1.

### Rejected: Score Boost For Relation Support

Weight tuning reshuffles the global order; the P8 ablation showed a
single redundant channel moved RedInk required recall from 1.0 to 0.941.
Also explicitly forbidden by the P8 stop rule's spirit: evidence must
not be manufactured by re-scoring.

### Rejected: Separate "Related Files" Response Section

Changes the public results contract for every consumer; the evidence
only asks for membership, not a new surface.

### Rejected: Larger `final_top_k`

Dilutes precision for every query to fix a structural miss; noise ratio
gates would fail.

## Selection Contract Details

- The quota runs identically for every language and relation kind that
  produces `graph_*_match` score parts (Java, frontend, MyBatis, Python,
  test associations). It is language-neutral by construction.
- Determinism: candidates are considered strictly in existing ranked
  order; ties inside the ranked list are already deterministic; repeated
  runs must produce byte-identical final path lists.
- `duplicate_result_path` accounting (P7 trace) is unchanged; a new
  bounded counter `relation_slot_selected` (0..RELATION_FINAL_SLOTS) is
  added to the final-selection trace stage only. RetrievalTrace schema
  version stays 1; the counter joins the existing decision-count list
  the same way `duplicate_result_path` did in P7.
- Evidence anchors are unaffected.
- ContextPack/exploration consume the same QueryBundle and inherit the
  membership change without contract edits.
- When the graph is stale/legacy or has no relation-supported
  candidates, selection is byte-identical to today.

## Compatibility And Protected Behavior

- Characterization: this deliberately changes final selection for
  fixture cases with active graphs. Handling follows the P7 precedent
  exactly: pin new expected final-trace hashes in an overlay
  (`EXPECTED_P9_FINAL_TRACE_HASHES`), assert the delta structurally
  (only membership/order inside final selection, plus the new counter),
  and substitute frozen values back for the remaining immutable-baseline
  comparison. The baseline JSON itself is not edited.
- Protected direct winners (explicit path/symbol/direct top results)
  are never evicted; a dedicated test pins this.
- P5/P6 suites, quality ci profile, and the full suite must stay green
  aside from the reviewed characterization overlay.

## Benchmark Design

Reuse without modification:

- pinned RedInk/daily commits, include patterns, inventory/content
  hashes;
- the 18-case frozen gold manifest and closed-world noise rule;
- the paired runner (`capture` / `compare` / `check`);
- baseline captures against `b9fa965` (new baseline capture required
  since P8 merged).

### Revised Credit Rule (fixes the P8 gate-2 attribution gap)

A required-item gain is credited to P9 when the item's selected entry
carries the `relation slot` provenance (quota-selected with relation ID
and source path). Gains through rank drift remain reported but
uncredited, as in P8.

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
8. Deterministic repeated captures are byte-identical.
9. Query latency mean regression <= 5% (the quota adds one bounded scan
   and at most `RELATION_FINAL_SLOTS` relation-row lookups per query).

If gate 2 fails, P9 is reported as insufficient without adjusting
`RELATION_FINAL_SLOTS` upward to manufacture a pass; the failure
boundary chooses the next mechanism.

## Determinism

Final path order, quota decisions, eviction choices, and the
`relation_slot_selected` counter must be independent of insertion,
registration, SQLite row, and dictionary order. Fresh/reverse fixture
runs and repeated captures must agree byte-for-byte.

## Change Surface

| file | responsibility |
| --- | --- |
| `src/context_search_tool/retrieval_core/relation_policy.py` | the two quota constants |
| `src/context_search_tool/retrieval_core/selection.py` | quota scan, eviction, provenance reason |
| `src/context_search_tool/retrieval_core/tracing.py` | `relation_slot_selected` counter in the final stage |
| tests per plan | unit, characterization overlay, A/B rerun |

Nothing else changes. Explicitly out of scope: expansion, ranking,
formatters (the reason string flows through the existing channel),
ContextPack, exploration, MCP schemas.
