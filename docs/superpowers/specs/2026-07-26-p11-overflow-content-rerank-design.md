# P11 Overflow Content Rerank v1 Design

Date: 2026-07-26
Status: Draft for review
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `4467978` (main; quota machinery inert, co-occurrence
proven, six-key affinity landed but gated off)
Predecessors: P8/P9/P10 implementation records. The P10 record's
exhaustion declaration names this mechanism class: *read the content of
relation-supported overflow candidates against the query*.

## Why A Model, Stated Plainly

Three controlled experiments exhausted shallow per-candidate predicates:
rank order (P9), any-channel evidence (P9a), and token overlap (P10) all
order co-imported noise above gold support files inside
relation-supported overflow. The fast-context comparison showed the
missing discriminator is semantic reading of candidate content. The
project principle "Local First, Model Optional" permits exactly this:
model-backed improvement that degrades to today's behavior when no model
is configured. P9a additionally proved HASH-semantic is not that signal
(near-universal, uninformative) — so the rerank activates only under a
REAL embedding provider (`bge` via Ollama or `openai-compatible`), never
under `hash`.

## Pre-Committed Rules (fixed before any comparison)

1. **Activation condition:** the relation quota
   (`RELATION_SLOTS_ENABLED`) becomes provider-conditional: active iff
   the repository's configured embedding provider is not `hash`. Under
   `hash` the entire mechanism is byte-identical to today (inert).
2. **Rerank scope (bounded):** only candidates that pass the existing
   six-key `_relation_slot_supported` predicate, inside the existing
   `RELATION_SLOT_SCAN_DEPTH = 50`, capped at the first
   `RERANK_OVERFLOW_CAP = 16` such candidates in ranked order.
3. **Signal:** query-to-content cosine similarity from the configured
   real embedding provider, computed at query time over each candidate's
   selected chunk content (first `RERANK_TEXT_BYTES = 2048` UTF-8 bytes)
   and the bottom `RELATION_FINAL_SLOTS = 2` non-protected members of
   the ordinary selection, in ONE batch request (≤ 19 texts including
   the query).
4. **Admission rule (relative, not threshold):** a candidate is admitted
   (up to 2, best similarity first, path-diverse, deterministic
   tie-break by ranked order) only if its similarity strictly exceeds
   the similarity of the member it would evict. Eviction order and
   protections are exactly the shipped `_apply_relation_slots` rules.
5. **The pre-committed P9/P10 regression triple** (decision_signal_
   service.py / test_data_fetcher_prefetch_stock_names.py /
   image_compressor.py) must remain selected; each is called out by name
   in the record.
6. **One comparison, one disposition.** All constants above, the model
   identity (`bge-m3` via Ollama for the A/B), and the eleven-gate
   arithmetic (gate 2 = credited_gain/57 >= 0.05, i.e. >= 3) are frozen
   at review time. If gate 2 fails, the record must state that
   local-deterministic AND local-model selection mechanisms are both
   exhausted, and the remaining options are (a) accepting the gap or
   (b) LLM-based reranking — a product-direction decision for the user,
   not another experiment variant.

## Evidence Chain

- P9/P9a/P10: three rejects; consistent failure shape — shallow signals
  cannot order gold above co-imported noise in overflow (P10: 34
  token-affine noise admissions, zero gold).
- P9a specifically: hash-semantic near-universal ⇒ excluded here.
- fast-context 20/21 vs CST 17/21 on frozen gold: the discriminator is
  content reading. bge-m3 is the strongest local reading proxy already
  integrated in the codebase (embedding provider + quality profiles
  `calibration_bge`/`ab_bge` exist).

Hypothesis (falsifiable, one shot): real-model similarity orders gold
support files above co-imported noise within relation-supported
overflow often enough that ≥ 3 required items are admitted (credited)
with no required fallout.

## Architecture

### Selected: Provider-Conditional Similarity Gate Inside The Quota

`_apply_relation_slots` gains an optional `similarity` argument: a
mapping `chunk_id -> float` computed by the caller
(`split_results_and_anchors` receives it from `retrieval.py`, which owns
the embedding provider). When `similarity` is `None` (hash provider, or
provider failure), the quota is inert. When present:

1. eligible overflow (six-key predicate, cap 16) and the bottom-2
   non-protected selected members get similarities;
2. admission per pre-committed rule 4;
3. reason `"relation slot"` and the `relation_slot_selected` counter as
   shipped.

Provider failure at query time (timeout/error) degrades to inert for
that query and records the existing provider-failure handling; it never
fails the query.

### Rejected: LLM listwise rerank

Cost, nondeterminism, and a new dependency class; reserved as the
explicit next decision if this experiment fails (rule 6).

### Rejected: threshold-based admission

Absolute thresholds are corpus-dependent; the relative
beats-the-victim rule is scale-free and needs no tuning knob.

### Rejected: reranking the whole overflow / all results

Unbounded model cost per query; the evidence localizes the failure to
relation-supported overflow only.

## Compatibility

- `hash` provider (default, all fixtures, characterization, quality
  suites, CI): byte-identical behavior; every existing pin must remain
  untouched — any drift is a STOP.
- Latency: one batch embedding call only on graph-bearing repos under a
  real provider; pre-committed gate: paired query-latency mean
  regression <= 15% on the bge-configured A/B (the call is real work; 5%
  is unrealistic for a network hop to Ollama, and the baseline for this
  comparison also runs bge — see Benchmark).
- Determinism: fixed model + fixed inputs ⇒ fixed scores; the capture
  records provider/model/dimensions and the Ollama model digest.

## Benchmark Design

Both sides of the A/B run with the SAME bge-m3 configuration (the
variable isolated is the rerank, not the embedding provider):

- baseline: current main, `[embedding] provider = "bge"` config on the
  prepared repos, quota inert (flag semantics: provider-conditional
  activation is the CANDIDATE change; the baseline tree predates it).
- candidate: this design's tree, same config.
- gold, runner (v2 captures, credit rule, eleven gates), pinned repos:
  reused unchanged. New capture fields: provider identity + model
  digest.
- Environment precondition (checked at Task 0): local Ollama serving
  `bge-m3`; if unavailable, the experiment is BLOCKED, not simulated
  with hash.

## Change Surface

| file | responsibility |
| --- | --- |
| `retrieval_core/relation_policy.py` | `RERANK_OVERFLOW_CAP = 16`, `RERANK_TEXT_BYTES = 2048`; `RELATION_SLOTS_ENABLED` replaced by provider-conditional activation |
| `retrieval_core/selection.py` | `similarity` parameter, relative admission |
| `retrieval.py` | compute the batch similarities under a real provider; pass through |
| `tests/p8_real_python_graphs_acceptance.py` | provider/model identity in captures |
| tests per plan | unit, provider-conditional gating, hash-inertness, A/B |

Expansion, ranking, evidence_merge, formatters, trace schema: untouched.
