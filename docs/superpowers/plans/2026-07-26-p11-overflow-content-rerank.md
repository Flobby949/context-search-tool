# P11 Overflow Content Rerank v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Executed 2026-07-26; disposition reject (see Implementation Record)
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `4467978` (main; quota inert)
Design:
`docs/superpowers/specs/2026-07-26-p11-overflow-content-rerank-design.md`

**Goal:** One pre-committed experiment: indexed-vector similarity
admission for the relation quota, provider-conditional, hash =
byte-identical, with a bge-vs-hash control dispositioned first.

**Architecture:** candidates.py surfaces the query vector it already
computes; retrieval.py builds a similarity resolver over the vector
snapshot (frozen name `relation_slot_similarities`); selection resolves
similarities for exactly the candidates/victims it considers and admits
only strict victim-beaters (6-decimal rounding). No provider calls at
query time beyond today's query embedding.

## Global Constraints

- Runtime/tests: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src"
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`.
- Frozen at review: `RERANK_OVERFLOW_CAP = 16`, the relative admission
  rule with 6-decimal rounding, MAX-over-chunk_ids for merged results,
  bge-m3 as the A/B model, gate 2 >= 3 credited, latency formula
  `candidate.timing.query_latency_mean_seconds /
  baseline.timing.query_latency_mean_seconds - 1 <= 0.15` (computed
  manually from capture fields into the record), one Ollama warmup call
  (`curl -s localhost:11434/api/embed -d '{"model":"bge-m3","input":"warmup"}'`)
  before every capture. No post-comparison edits.
- Hash mode must stay byte-identical at every task: characterization,
  quality suites, counter pins, and the standing hash `baseline.json`
  membership are STOPs, never repins.
- The A/B is BLOCKED (not simulated) without local Ollama + bge-m3.
- Ledger constraints: bare imported names in
  `tests/test_retrieval_pipeline.py`; the resolver seam is
  monkeypatched ONLY via the string-target form
  `monkeypatch.setattr("context_search_tool.retrieval.relation_slot_similarities", stub)`
  (the ledger scanner does not match string targets; never import the
  seam in tests).
- Run root: create once and persist —
  `P11=$(mktemp -d /private/tmp/cst-p11-run.XXXXXX); echo "$P11" > .quality/p11-run-root.txt`;
  later tasks read `$(cat .quality/p11-run-root.txt)`.
- No commit/push beyond the working branch unless the user asks; p6
  worker failures are environmental.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `retrieval_core/relation_policy.py` | `RERANK_OVERFLOW_CAP = 16`; delete `RELATION_SLOTS_ENABLED` |
| modify | `retrieval_core/selection.py` | `similarity_resolver` kwarg, relative admission, unconditional call |
| modify | `retrieval_core/candidates.py` | return the existing original-variant query vector |
| modify | `src/context_search_tool/retrieval.py` | `relation_slot_similarities(query_vector, vector_snapshot) -> Callable[[list[str]], dict[str, float]] | None` |
| modify | `tests/test_retrieval_core_boundaries.py` | add `relation_slot_similarities` to `EXPECTED_LOCAL_DEFINITIONS` |
| modify | `tests/test_retrieval_core_primitives.py` | admission unit matrix flip (all six existing tests + new resolver matrix) |
| modify | `tests/test_retrieval_pipeline.py` | P10 recorder signature update; hash-inertness regression pin; stub-resolver e2e |
| modify | `tests/p8_real_python_graphs_acceptance.py` | `--embedding` plumbing, schema v3, identity assertion |
| modify | `tests/test_p8_real_python_graphs_acceptance.py` | v3 + embedding-identity tests |
| evidence | `$(cat .quality/p11-run-root.txt)` | bge baseline + candidate captures, control comparison |

---

### Task 0: Gates Only

- [x] **Step 0.1:** Branch `feat/p11-overflow-rerank` from main; full
  suite green (2972+, p6 env aside). Create and persist `$P11` (see
  Global Constraints).
- [x] **Step 0.2:** Ollama precondition:
  `curl -s localhost:11434/api/tags | grep -q bge-m3` — on failure STOP
  (BLOCKED). Record the bge-m3 digest from the tags payload into the
  record.
- [x] **Step 0.3:** Pinned sources present at
  `R=$(cat .quality/p8-baseline-root.txt)`: `$R/RedInk`,
  `$R/daily_stock_analysis` (the runner consumes THESE, never
  `prepared/`); re-clone per P9 plan Task 0 Step 0.4 if wiped, validate
  via `validate_protected_source`. Manifest `--check` passes.

### Task 1: RED/GREEN Resolver Admission Unit (inertness moves inside)

- [x] **Step 1.1: RED** in `tests/test_retrieval_core_primitives.py`.
  New matrix for `_apply_relation_slots(selected, overflow, *,
  similarity_resolver=None)`:
  - resolver returning {candidate: 0.8, victim: 0.5} → admitted;
  - {candidate: 0.5, victim: 0.5} → NOT admitted (strict, after
    6-decimal rounding — also assert 0.5000004 vs 0.5 is NOT admitted);
  - candidate absent from the resolver's dict → not admitted;
  - `similarity_resolver=None` → NO admissions even for eligible
    candidates (this INVERTS the six existing admission tests
    `test_relation_slots_*` at
    tests/test_retrieval_core_primitives.py:~546-685, which currently
    call with two args and expect admissions: update every one to pass
    a stub resolver granting the admitted candidates victim-beating
    sims; keep their eviction/protection/determinism assertions);
  - two candidates both beating victims → best-sim first, equal sims
    broken by ranked position;
  - resolver called with exactly the eligible candidate ids + current
    victim ids (assert on the recorded query list).
  Also: policy exactness — `RERANK_OVERFLOW_CAP == 16` added,
  `RELATION_SLOTS_ENABLED` assertion DELETED.
- [x] **Step 1.2: GREEN:** implement in `selection.py` (unconditional
  call from `split_results_and_anchors`; delete the flag guard and the
  flag itself in `relation_policy.py`). Update the P10 co-occurrence
  test: recorder signature becomes
  `def recorder(selected, overflow, *, similarity_resolver=None):` and
  forwards to the original with its own stub where the test needs
  admissions; its flag monkeypatch line is deleted (the call is now
  unconditional, so the recorder fires under hash too).
- [x] **Step 1.3:** Full suite; hash-mode pins all green (STOP
  otherwise). Commit
  `feat: resolver-based relation slot admission (P11 Task 1)`.

### Task 2: RED/GREEN Provider Wiring

- [x] **Step 2.1: RED (seam absent).** In
  `tests/test_retrieval_pipeline.py`, two tests:
  - stub-resolver e2e: monkeypatch the STRING target
    `"context_search_tool.retrieval.relation_slot_similarities"` with a
    function returning a resolver granting `app/wire.py` 0.9 and every
    victim 0.1; under the diluted query assert wire selected with
    `"relation slot"` reason. Expected RED reason: `AttributeError`
    (the seam does not exist yet).
  - regression pin (NOT RED — expected to pass before and after; any
    failure is a STOP): with DEFAULT_CONFIG (hash) no result carries
    `"relation slot"` and membership matches the current inert
    expectations.
- [x] **Step 2.2: GREEN:** implement `relation_slot_similarities` in
  `retrieval.py` (returns `None` for hash provider / missing snapshot /
  missing query vector; otherwise a resolver doing MAX-over-chunk_ids
  dot products against snapshot vectors, values rounded to 6 decimals);
  surface the query vector from
  `candidates._semantic_candidates_with_store` (returned alongside the
  candidates; hash path may keep returning it — the provider check
  lives in the resolver builder); wire the resolver through both
  `split_results_and_anchors` call sites. Add
  `relation_slot_similarities` to `EXPECTED_LOCAL_DEFINITIONS` in
  `tests/test_retrieval_core_boundaries.py`.
- [x] **Step 2.3:** Full suite; hash pins green (STOP otherwise).
  Commit `feat: indexed-vector relation slot similarities (P11 Task 2)`.

### Task 3: Runner Embedding Plumbing + Schema v3

- [x] **Step 3.1: RED** in the runner tests: `capture` accepts an
  embedding argument; a bge capture must carry
  `embedding_identity == {"provider": "bge", "model": "bge-m3",
  "dimensions": 1024, "digest": <recorded>}` and FAIL (raise) if the
  workspace's indexed identity disagrees; a hash capture carries
  provider "hash"; `check` rejects schema v2.
- [x] **Step 3.2: GREEN:** `CAPTURE_SCHEMA_VERSION = 3`; CLI
  `capture <impl_root> <repos_dir> <out> [reps] [embedding]` where
  `embedding=bge` builds the bge `ToolConfig` and passes it to BOTH
  `index_repository` and `query_repository`; identity recorded from
  that config + Ollama tags digest. Commit
  `test: bge-capable capture schema v3 (P11 Task 3)`.

### Task 3.5: Captures And The Pre-Committed Control

- [x] **Step 3.5.1:** Warmup call, then bge BASELINE twice via the
  detached-worktree technique (behavior-baseline code, candidate
  runner):

```bash
P11=$(cat .quality/p11-run-root.txt); R=$(cat .quality/p8-baseline-root.txt)
git worktree add --detach "$P11/baseline-tree" 4467978
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$P11/baseline-tree/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p8_real_python_graphs_acceptance.py \
  capture "$P11/baseline-tree" "$R" "$P11/baseline-bge.json" 2 bge
```

  (+`-repeat`; identical modulo timing/implementation/digest — a
  difference is the rule-4 STOP).
- [x] **Step 3.5.2: The control:** `compare $P9_hash_baseline
  $P11/baseline-bge.json $P11/control.json` (hash baseline path from
  `$(cat .quality/p9-run-root.txt)/baseline.json`). Apply the design's
  rule-5 branches BEFORE any candidate capture; record the outcome. If
  re-scoped, stop here and report.
- [x] **Step 3.5.3:** Warmup, then bge CANDIDATE twice from the working
  tree (`capture "$PWD" ...`), deterministic per rule 4.

### Task 4: The Single Quota A/B

- [x] **Step 4.1:** `compare $P11/baseline-bge.json
  $P11/candidate-p11.json $P11/comparison-p11.json`; evaluate the
  eleven gates, the named regression triple, and the latency formula.
- [x] **Step 4.2:** Disposition per the frozen rules. Non-ship: revert
  the resolver wiring activation is NOT possible by flag anymore —
  instead `relation_slot_similarities` returns `None` unconditionally
  (one-line inerting, keeping Tasks 1-2 machinery and tests that use
  stubs), record, and write the design's rule-7 exhaustion statement.
  Ship: hash-mode full suite green + docs commit.

### Task 5: Record

- [x] Implementation record: digest, control outcome and branch taken,
  all gate values, admission list with per-admission sims vs victim
  sims, the regression triple, latency arithmetic, disposition.

## Stop Conditions

- Ollama/bge-m3 unavailable (BLOCKED; no hash simulation).
- Any hash-mode pin drift at any task.
- Capture-twice membership difference (rule-4 determinism STOP).
- Rule-5 control re-scope (documented stop, not a failure).
- Gate 2 failure → rule-7 exhaustion statement; no variants.
- Any post-comparison edit.

## Implementation Record

Status: COMPLETE. Disposition: **reject** (frozen rules applied
verbatim; no post-comparison edits).

### Environment and identities

- Model: bge-m3 via local Ollama, digest
  `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`,
  1024 dimensions; one warmup embed call preceded every capture.
- Baseline capture: detached worktree at `4467978`, clean
  (`dirty: false`), candidate runner. Candidate capture: working tree at
  `a711b13`, clean. Both captures schema v3 with
  `embedding_identity.provider == "bge"` and the indexed-identity
  assertion passing (the `--embedding` plumbing worked; nothing fell
  back to hash).
- Capture infrastructure fix (pre-capture, commit `a711b13`): Ollama
  rejects a single text whose tokenization exceeds bge-m3's 8192-token
  context (a 6,924-char dense-CJK chunk in daily_stock_analysis
  reproduced `400: input length exceeds the context length`;
  server-side `truncate`/`num_ctx` options do not help). The runner
  installs a deterministic per-text truncation at 4,000 chars on the
  BGE provider of whichever tree PYTHONPATH selects — identical for
  baseline and candidate, no source-tree edits, unit-tested. Noted as a
  separate product defect in `embeddings_bge.py` (out of P11 scope).
- Determinism (rule 4): baseline captured twice and candidate captured
  twice; each pair byte-identical modulo `timing`/`implementation`. No
  STOP.

### Rule-5 control: compare(hash-baseline, bge-baseline)

`control.json` (hash baseline = P9 standing `baseline.json`, both sides
behavior-baseline code):

- Combined required Recall@12: hash 0.8596 → bge 0.8772 (+0.0175);
  redink 1.0 → 1.0, daily 0.80 → 0.825.
- Newly satisfied required: 1 (`daily-portfolio-risk
  src/services/portfolio_service.py`, uncredited by construction).
  Lost required: none. Noise ratio 0.7130 → 0.7083.
- Branch taken: 1 < 3 newly-credited → NOT re-scoped; no required lost
  → no provider-conditional clause; **proceed to the quota A/B**.

### The single quota A/B (bge-baseline vs bge-candidate)

`comparison-p11.json`, eleven gates:

| gate | value |
| --- | --- |
| 1 recall non-decreasing | **false** (daily fell) |
| 2 credited gain ≥ 5% (≥3 items) | **false** (0 credited) |
| 3 no required falls out | **false** |
| 4 ≥4 credited case improvements | false (0) |
| 5 ≥3 daily qualifying | false (0) |
| 6 relation-supported spread | true |
| 7 witnesses persisted | true |
| 8 noise bounded | true (+0.0093) |
| 9 P7 continuity | true |
| 10 protected winners stable | true |
| 11 deterministic render | true |

- Combined recall 0.8772 → 0.8596 (−0.0175).
- Admissions (10, across 7 cases; per-admission similarity values are
  not persisted by schema v3 — membership and ranks only):
  daily-backtest → stock_index_remote_service.py@12;
  daily-portfolio-risk → market_strategy.py@11,
  daily_market_context_guardrail.py@12;
  daily-runtime-scheduler → llm/__init__.py@12;
  redink-app-wiring → text_client.py@11, genai_client.py@12;
  redink-history-flow → text_client.py@12;
  redink-outline-flow → generators/factory.py@12;
  redink-provider-config → image_routes.py@11, generators/base.py@12.
  **Zero** admissions were previously-missed required items.
- Lost required: `daily-portfolio-risk
  src/services/decision_signal_service.py` (evicted by the case's two
  admissions) — a named member of the P9/P10 regression triple, so
  rule 6 is violated by name. The other two triple members
  (`test_data_fetcher_prefetch_stock_names.py`, `image_compressor.py`)
  remained selected.
- Latency formula: 0.6947 / 0.68957 − 1 = **+0.74%** ≤ 15% (pass;
  immaterial to the disposition).

### Disposition and reversion

Reject. Reversion per plan Task 4.2: `relation_slot_similarities`
returns `None` unconditionally (commit `2664e7e`); the resolver-based
admission machinery, its unit matrix, and the stub-resolver e2e remain.
Hash mode was byte-identical throughout (every characterization and
quality pin green at every task; full suite 2972+ passing with only the
known environmental p6 worker failures).

### Rule-7 exhaustion statement

Membership-rule selection (P9, P9a, P10) and indexed-vector-similarity
selection (P11) are both exhausted for the relation quota: real
bge-m3 content vectors, like every shallower signal, rank co-imported
noise above the gold support files inside relation-supported overflow
(10 admissions, 0 gold, 1 required eviction). The remaining options —
accepting the recall gap, or LLM-based listwise reranking of overflow —
are a product-direction decision for the user. Separately, the rule-5
control measured the first quantitative provider effect on the frozen
gold: switching indexing from hash to bge-m3 alone is +0.0175 combined
required recall with no losses and slightly less noise, at the cost of
Ollama-dependent indexing; configuring a real provider is a plausible
product improvement independent of any quota mechanism.
