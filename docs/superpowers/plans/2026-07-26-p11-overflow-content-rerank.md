# P11 Overflow Content Rerank v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Draft for review; implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `4467978` (main; quota inert)
Design:
`docs/superpowers/specs/2026-07-26-p11-overflow-content-rerank-design.md`

**Goal:** One pre-committed experiment: real-model similarity admission
for the relation quota, provider-conditional, hash = byte-identical.

**Architecture:** `retrieval.py` computes one batch of query/content
similarities under a non-hash embedding provider and passes a
`chunk_id -> float` mapping into `split_results_and_anchors`;
`_apply_relation_slots` admits an eligible overflow candidate only when
its similarity strictly beats its eviction victim's. `hash` provider or
provider failure ⇒ mapping is `None` ⇒ inert.

## Global Constraints

- Runtime/tests: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src"
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`.
- Frozen at review: `RERANK_OVERFLOW_CAP = 16`,
  `RERANK_TEXT_BYTES = 2048`, the relative admission rule, bge-m3 as the
  A/B model, gate 2 >= 3 credited, latency gate <= 15% on the
  bge-vs-bge comparison. No post-comparison edits.
- Under `hash` everything must be byte-identical: characterization,
  quality suites, counter pins, and the standing hash baseline
  membership are STOP conditions, never repins.
- The A/B is BLOCKED (not simulated) if local Ollama with `bge-m3` is
  unavailable at Task 0.
- Ledger: bare imported names in `tests/test_retrieval_pipeline.py`;
  reach policy flags via `selection.relation_policy`.
- No commit/push beyond the working branch unless the user asks; p6
  worker failures are environmental.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `retrieval_core/relation_policy.py` | two new constants; activation semantics |
| modify | `retrieval_core/selection.py` | `similarity` param + relative admission |
| modify | `src/context_search_tool/retrieval.py` | batch similarity computation + pass-through |
| modify | `tests/test_retrieval_core_primitives.py` | admission unit matrix |
| modify | `tests/test_retrieval_pipeline.py` | hash-inertness e2e; provider-conditional e2e with a stub provider |
| modify | `tests/p8_real_python_graphs_acceptance.py` | provider/model identity fields (capture schema v3) |
| modify | `tests/test_p8_real_python_graphs_acceptance.py` | v3 + gating tests |
| evidence | new `$P11_RUN_ROOT` (mktemp) | bge baseline + candidate captures |

---

### Task 0: Environment And Baseline Gate

- [ ] **Step 0.1:** Branch `feat/p11-overflow-rerank` from main; full
  suite green (2972+, p6 env aside).
- [ ] **Step 0.2:** Ollama precondition:
  `curl -s localhost:11434/api/tags | grep bge-m3` — on failure, STOP
  and report BLOCKED. Record the model digest from the tags payload.
- [ ] **Step 0.3:** Pinned repos present under
  `$(cat .quality/p8-baseline-root.txt)` (re-clone per P9 plan Task 0 if
  wiped; validate via `validate_protected_source`).
- [ ] **Step 0.4: bge BASELINE capture (the hash baseline is not
  reusable — the provider is part of the variable isolation):** write
  `[embedding] provider="bge" model="bge-m3" dimensions=1024` into each
  prepared repo's `.context-search/config.toml`, `cst clean` + `cst
  index` both repos with MAIN's code, then capture twice into
  `$P11_RUN_ROOT/baseline-bge.json` (+`-repeat`), identical modulo
  timing/implementation. Record index wall times.
- [ ] **Step 0.5:** Manifest `--check`; gold frozen.

### Task 1: RED/GREEN Relative Admission Unit

- [ ] **Step 1.1: RED** in `test_retrieval_core_primitives.py`:
  `_apply_relation_slots(selected, overflow, similarity=...)` matrix:
  - candidate sim 0.8 vs victim sim 0.5 → admitted (count 1, reason
    handling unchanged);
  - candidate 0.5 vs victim 0.5 → NOT admitted (strict inequality);
  - candidate missing from the mapping → not admitted;
  - `similarity=None` → identical to today's inert path (no admission
    even for eligible candidates);
  - two candidates both beating both bottom victims → best-similarity
    first, two admissions, deterministic order on equal sims by ranked
    position;
  - eviction protections (rank-1, relation-supported) unchanged.
- [ ] **Step 1.2: GREEN:** add the keyword-only `similarity` parameter
  (default `None`) and the relative rule inside
  `_apply_relation_slots`; add the two policy constants + exactness
  assertions. `RELATION_SLOTS_ENABLED` is DELETED in favor of
  `similarity is not None` (update the policy exactness test and the
  flag references; the P10 co-occurrence test patches are updated to
  pass a stub mapping instead of flipping a flag). Commit.

### Task 2: RED/GREEN Provider Wiring

- [ ] **Step 2.1: RED e2e (stub provider)** in
  `test_retrieval_pipeline.py`: monkeypatch the provider seam that
  `retrieval.py` will expose (a module-level function
  `relation_slot_similarities(provider, query, texts) -> list[float]`
  or equivalent named in the implementation) so the fixture's wire.py
  gets sim 0.9 and the victim 0.1; assert wire selected with
  `"relation slot"` reason under the diluted query. Second scenario:
  stub returns victim-beating sims for a noise-shaped file only → that
  file admitted (the mechanism is signal-agnostic; quality lives in the
  model, which the A/B judges).
- [ ] **Step 2.2: RED hash-inertness e2e:** with DEFAULT_CONFIG (hash),
  assert no result carries `"relation slot"` and membership equals the
  pre-change expectation (reuse the P10 inert assertions).
- [ ] **Step 2.3: GREEN:** implement in `retrieval.py`: when the
  configured provider is non-hash and the graph session is ready,
  collect eligible overflow (cap 16) + bottom-2 victims after ranking,
  embed `[query] + [first 2048 bytes of each chunk content]` in one
  provider batch, cosine per candidate, build the mapping; failures →
  `None`. Pass into `split_results_and_anchors`. Full suite: everything
  hash-mode must be untouched (STOP otherwise). Commit.

### Task 3: Capture Schema v3

- [ ] **Step 3.1: RED** in the runner tests: captures carry
  `embedding_identity` (provider/model/dimensions/digest-if-known);
  `check` rejects v2. **GREEN:** bump `CAPTURE_SCHEMA_VERSION = 3`,
  record identity from the workspace config + Ollama tags when
  provider=bge. Re-capture the Task 0 baseline files with v3 (they were
  captured before the bump — regenerate BOTH, still with main's
  retrieval code via the baseline worktree pattern: use a detached
  worktree at `4467978` with PYTHONPATH pointing at it, the P8 Task 8
  technique). Commit.

### Task 4: The Single Paired A/B (bge vs bge)

- [ ] **Step 4.1:** Candidate captures twice on the prepared bge-config
  repos; deterministic modulo timing/implementation/digest.
- [ ] **Step 4.2:** `compare baseline-bge.json candidate-p11.json` →
  eleven gates + the named P9/P10 regression triple + latency <= 15%.
  Disposition per the frozen rule; on non-ship revert the provider
  wiring activation (keep Tasks 1 unit machinery), record, and write
  the design's rule-6 exhaustion statement (local mechanisms exhausted;
  LLM rerank or accept-the-gap is a user decision).
- [ ] **Step 4.3:** On ship additionally: hash-mode full suite green,
  README/retrieval-quality docs in a separate commit.

### Task 5: Record

- [ ] Implementation record: model digest, all gate values, admission
  list with per-admission sims vs victim sims, the regression triple,
  latency, disposition.

## Stop Conditions

- Ollama/bge-m3 unavailable at Task 0 (BLOCKED, no hash simulation).
- Any hash-mode pin drift at any task.
- Gate 2 failure → rule-6 exhaustion statement; no variants.
- Any post-comparison edit.

## Implementation Record

Status: Not started. Record only observed, verified results.
