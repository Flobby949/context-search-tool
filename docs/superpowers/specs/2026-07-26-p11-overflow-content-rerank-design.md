# P11 Overflow Content Rerank v1 Design

Date: 2026-07-26
Status: Revised after adversarial review (r2)
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `4467978` (main; quota machinery inert)
Predecessors: P8/P9/P10 implementation records; the P10 exhaustion
declaration names this mechanism class.

Review r2 note: the first draft re-embedded candidate content at query
time. Review showed the published index already holds every chunk's
vector under the configured provider (`vectors.npy`, l2-normalized for
v2 generations), retrievable by chunk_id with zero provider calls —
deterministic, zero new egress, full-content signal, no latency hit.
That is now the selected architecture. The draft's re-embedding is the
rejected alternative. The review also exposed that the A/B harness
hardcodes the hash config and that the experiment lacked a bge-vs-hash
control; both are now pre-committed below.

## Why A Model Signal, Stated Plainly

P9/P9a/P10 exhausted shallow per-candidate predicates: rank order,
any-channel evidence, and token overlap all order co-imported noise
above gold support files inside relation-supported overflow. The
missing discriminator is semantic content reading. P9a proved
HASH-semantic is not that signal, so the mechanism activates only when
the repository is indexed under a real provider (`bge` via Ollama or
`openai-compatible`); under `hash` it is byte-identical to today.

## Pre-Committed Rules (fixed before any comparison)

1. **Signal = indexed vectors.** Similarity is the dot product of the
   query vector (already computed by the semantic stage under the
   configured provider, currently discarded — it will be surfaced, not
   recomputed) with the candidate's INDEXED chunk vector from the
   published vector snapshot. For a merged result with several
   `chunk_ids`, the similarity is the MAX over its chunks' vectors.
   No content is embedded or transmitted at query time.
2. **Activation:** the quota is active iff the indexed embedding
   provider is not `hash` AND the vector snapshot is available at the
   call site. `RELATION_SLOTS_ENABLED` is deleted; inertness is
   `similarity_resolver is None` inside `_apply_relation_slots` (the
   call from `split_results_and_anchors` becomes unconditional).
3. **Rerank scope:** eligible overflow per the shipped six-key
   `_relation_slot_supported` predicate, inside
   `RELATION_SLOT_SCAN_DEPTH = 50`, capped at the first
   `RERANK_OVERFLOW_CAP = 16` eligible items in ranked order.
4. **Admission rule (relative):** a candidate is admitted (up to
   `RELATION_FINAL_SLOTS = 2`, best similarity first, ties broken by
   ranked order) only if its similarity strictly exceeds that of the
   member it would evict, both similarities rounded to 6 decimals
   before comparison (pre-committed tolerance; a capture-twice
   membership difference is a STOP). Eviction order and protections are
   exactly the shipped rules.
5. **Control comparison first:** before the quota A/B, the record must
   contain `compare(hash-baseline, bge-baseline)` on the frozen gold —
   both sides on the behavior-baseline code. Pre-committed branches:
   - if the bge baseline alone credits >= 3 previously-missed required
     items, the experiment is re-scoped: the record documents "configure
     a real provider" as the finding and the quota A/B is not run;
   - if the bge baseline loses required items vs hash, any later `ship`
     is recorded as conditional on provider choice;
   - otherwise proceed to the quota A/B.
6. **The P9/P10 regression triple** (decision_signal_service.py /
   test_data_fetcher_prefetch_stock_names.py / image_compressor.py)
   must remain selected in the candidate capture; each is named in the
   record.
7. **One quota comparison, one disposition.** All constants, the
   admission rule, the model identity (bge-m3, digest recorded), the
   eleven runner gates (gate 2 = credited_gain/57 >= 0.05, i.e. >= 3),
   and the latency rule
   `candidate.timing.query_latency_mean_seconds /
   baseline.timing.query_latency_mean_seconds - 1 <= 0.15` (computed
   from the capture fields, recorded manually in the record; one
   Ollama warmup call precedes EVERY capture) are frozen at review
   time. If gate 2 fails, the record states: membership-rule and
   indexed-vector-similarity selection mechanisms are exhausted; the
   remaining options — accept the gap, or LLM-based reranking — are a
   product-direction decision for the user. The provider-choice
   question is dispositioned separately by rule 5's control.

## Evidence Chain

- P9/P9a/P10: three rejects; shallow signals cannot order gold above
  co-imported noise (P10: 34 token-affine noise admissions, zero gold).
- fast-context 20/21 vs CST 17/21: content reading is the
  discriminator; bge-m3 vectors are the strongest local proxy already
  integrated (provider abstraction + `calibration_bge`/`ab_bge`
  profiles; the only recorded bge evidence is qualitative PetClinic
  data, hence rule 5's control).

Hypothesis (falsifiable, one shot): real-provider indexed-vector
similarity orders gold support files above co-imported noise within
relation-supported overflow well enough to admit >= 3 credited required
items with no required fallout.

## Architecture

### Selected: Indexed-Vector Similarity Resolver

- `retrieval_core/candidates.py`: the semantic stage additionally
  returns the original-variant query vector it already computes.
- `src/context_search_tool/retrieval.py`: one new module-level function
  (name frozen: `relation_slot_similarities`) builds a resolver
  `Callable[[list[str]], dict[str, float]]` closing over the query
  vector and the vector snapshot; it is `None` when the indexed
  provider is `hash`, the snapshot is unavailable, or the query vector
  is missing. Passed into `split_results_and_anchors`.
- `retrieval_core/selection.py`: `_apply_relation_slots` gains
  keyword-only `similarity_resolver=None`; it resolves similarities for
  exactly the eligible candidates and current eviction victims it
  considers (no partition logic leaves selection.py), applies rule 4,
  and stays inert when the resolver is `None`.

### Rejected: query-time content re-embedding (draft v1)

Nondeterministic under Ollama batching/float order, new per-query
source-content egress under remote providers, ~7 sequential HTTP calls
per query under the BGE provider's 8-text/6000-char batching — and
strictly less signal (2048-byte truncation vs the indexed full chunk).

### Rejected: LLM listwise rerank

Reserved as the explicit user decision if this experiment fails.

### Rejected: threshold admission

Corpus-dependent; the relative beats-the-victim rule is scale-free.

## Compatibility

- `hash` provider (default, all fixtures, characterization, quality
  suites): resolver is `None` ⇒ byte-identical; every existing pin is a
  STOP, never a repin.
- Determinism: stored vectors + one query embed per query; the only
  float risk is the query embedding itself, absorbed by the 6-decimal
  rounding rule and the capture-twice STOP.
- No new egress: nothing beyond today's query-text embedding leaves the
  machine; README privacy text is unchanged.

## Benchmark Design

- The runner gains an explicit embedding argument
  (`capture ... --embedding bge|hash`) threaded to BOTH
  `index_repository` and `query_repository`; a bge capture asserts its
  recorded `embedding_identity.provider == "bge"` (fail, not just
  record). Capture schema v3 adds `embedding_identity`
  (provider/model/dimensions + Ollama digest when applicable).
- Captures: hash-baseline (standing `baseline.json`, already valid),
  bge-baseline (behavior-baseline code via detached worktree at
  `4467978`, candidate runner script), bge-candidate. Rule 5's control
  compares the first two; the quota A/B compares the last two.
- Environment precondition: local Ollama serving bge-m3; BLOCKED
  otherwise, never simulated with hash.

## Change Surface

| file | responsibility |
| --- | --- |
| `retrieval_core/relation_policy.py` | `RERANK_OVERFLOW_CAP = 16`; delete `RELATION_SLOTS_ENABLED` |
| `retrieval_core/selection.py` | `similarity_resolver` param, relative admission, unconditional call |
| `retrieval_core/candidates.py` | surface the existing query vector |
| `src/context_search_tool/retrieval.py` | `relation_slot_similarities` resolver builder |
| `tests/test_retrieval_core_boundaries.py` | add the new def to `EXPECTED_LOCAL_DEFINITIONS` |
| `tests/p8_real_python_graphs_acceptance.py` | `--embedding` plumbing, schema v3, identity assertion |
| tests per plan | unit matrix flip (six admission tests), P10 recorder signature, hash-inertness pins, A/B |

Ranking, expansion, evidence_merge, formatters, trace schema: untouched.
