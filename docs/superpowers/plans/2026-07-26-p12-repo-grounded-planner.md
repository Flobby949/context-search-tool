# P12 Repo-Grounded Planner Translation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Revised after adversarial review (r2); execution authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `04e11fe` (main)
Design: `docs/superpowers/specs/2026-07-26-p12-repo-grounded-planner-design.md` (r2)

**Goal:** One-lever experiment: planner hint filtering grounded in the
full indexed lexicon, measured on the frozen P12 gold with a planner-off
reference and a sealed held-out set.

## Global Constraints

- Runtime/tests: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src"
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`
  (p6 worker failures are environmental).
- Ollama processes: `NO_PROXY=localhost,127.0.0.1`; curl: `--noproxy '*'`.
- Frozen: everything in design rules 1–10. No post-comparison edits.
- Never touch originals under `/Users/flobby/vibe_coding/`; pinned
  copies live in gitignored `.quality/p12-eval-sources/`.
- Runner reuses the P8 runner by IMPORT
  (`import p8_real_python_graphs_acceptance as p8`): `_embedding_config`,
  `_install_bge_truncation`, `implementation_identity`.
- `retrieval.py`: inline edits only — no new top-level defs/assignments.
- New tests in `tests/test_retrieval_pipeline.py` /
  `tests/test_retrieval_trace_pipeline.py` reuse the modules' existing
  imports; planner stubs are monkeypatched via object injection
  (`planner=`) or string targets only.
- Run root: `P12=$(mktemp -d /private/tmp/cst-p12-run.XXXXXX); echo
  "$P12" > .quality/p12-run-root.txt`.

## File Map

Per the design's Change Surface table (r2), plus
`tests/test_p12_planner_acceptance.py` and `.quality/p12-eval-sources/`
(durable pinned copies + full manifest, gitignored).

---

### Task 0: Gates, Durable Pinning, Sealed Held-Out

- [ ] **0.1** Branch `feat/p12-repo-grounded-planner` from main; full
  suite green; create `$P12`.
- [ ] **0.2** Ollama: tags list `bge-m3` AND `qwen3.5:4b-mlx`; record
  digests. Cross-process pinned-chat probe: run the SAME
  `/api/chat` request (model qwen3.5:4b-mlx, `format:"json"`,
  `think:false`, `options {"temperature":0,"seed":0,"top_k":1}`, fixed messages)
  in TWO separate python processes; byte-equal `message.content`
  required, else BLOCKED. Note: no other Ollama clients during captures.
- [ ] **0.3** Durable pinning: `rsync` the three copies from
  `$(cat .quality/p12-eval-root.txt)` into `.quality/p12-eval-sources/`
  (excluding `.context-search`); verify `.quality/` is gitignored;
  write the FULL per-file sha256 manifest to
  `.quality/p12-eval-sources/manifest.json` + aggregate sha per
  project; copy `gold_p12.json` alongside. Record aggregate shas.
- [ ] **0.4** Held-out seal: launch a fresh agent (no failure-analysis
  context; prompt = the same authoring rules used for the gold: intent
  phrasing, no filename echo, verified required paths) to produce 8
  queries across the three pinned copies. Save to
  `.quality/p12-eval-sources/heldout.json`; record its sha256 in this
  plan's record BEFORE Task 1's first commit. Evaluated once, in
  Task 5 only.

### Task 1: Lexicon API + Guard Allowlists (one commit)

- [ ] **1.1 RED** in `tests/test_retrieval_pipeline.py` (reusing its
  existing imports): index a tmp workspace with
  `alpha_service.py` (body mentions `trading day cron`) and
  `tools/sync_log_helper.py` (trivial body); assert
  `SQLiteStore(...).planner_support_lexicon()` contains
  `trading/cron/sync/log/helper/alpha`, all-lowercase, and that
  re-indexing without a file removes its unique tokens. RED:
  `AttributeError`.
- [ ] **1.2 GREEN** in `sqlite_store.py`: top-level
  `from context_search_tool.tokenizer import tokenize_query` (verified
  cycle-free) + the design rule-1 SQL (three queries; `source_files`
  path column is `path`; ≥2-char filter).
- [ ] **1.3** Same commit: `tests/test_retrieval_core_boundaries.py`
  gains `P12_PLANNER_PRODUCTION_CHANGES =
  {"src/context_search_tool/query_planner.py"}` OR'd into BOTH
  protected-diff assertions (committed + dirty), and
  `_is_p4_public_facade_reference` admits
  `tests/p12_planner_acceptance.py` and the `tests/test_p12_` prefix.
  Full suite; commit `feat: full-index planner support lexicon (P12 Task 1)`.

### Task 2: Lexicon Filtering + Product Options Pin

- [ ] **2.1 RED** in `tests/test_query_planner.py`:
  - `clean_planner_payload(..., support_lexicon=frozenset({"is",
    "trading", "day", ...}))` keeps a hint outside
    `profile_vocabulary` but inside the lexicon; drops `LaunchGuard`
    (token outside) into `discarded_hints`; rewritten-query ≥2-token
    rule uses lexicon ∪ original tokens.
  - legacy pin: `support_lexicon=None` + profile ⇒ byte-identical
    behavior (existing tests at ~430-462 untouched and green).
  - request pin: monkeypatched session asserts body contains
    `"options": {"temperature": 0, "seed": 0, "top_k": 1}` and that
    `plan(query, repo_profile=..., support_lexicon=...)` forwards the
    lexicon. RED: unexpected kwarg.
- [ ] **2.2 GREEN** in `query_planner.py`: `support_lexicon` kwarg on
  the Protocol, `DisabledQueryPlanner.plan`, `OllamaQueryPlanner.plan`,
  `clean_planner_payload` (filter base = lexicon when not None, else
  legacy); `options` added to the request body.
- [ ] **2.3** Full suite; commit
  `feat: lexicon-grounded planner filtering (P12 Task 2)`.

### Task 3: Retrieval Threading + Stub Updates

- [ ] **3.1 RED** in `tests/test_retrieval_pipeline.py`: with
  `query_planner.enabled=True` config and an injected recording stub
  planner, assert the stub received a non-empty `frozenset` containing
  an indexed token. Planner-off pin (NOT RED): with DEFAULT_CONFIG,
  a counting wrapper on `SQLiteStore.planner_support_lexicon`
  (class-attribute patch, ledger-safe) records ZERO calls and results
  match the existing fixture expectations.
- [ ] **3.2 GREEN** in `retrieval.py` (inline, at :311-316): build
  `support_lexicon = store.planner_support_lexicon() if
  config.query_planner.enabled else None`; pass to `.plan(...,
  support_lexicon=support_lexicon)`.
- [ ] **3.3** Stub signature sweep (same commit): add
  `support_lexicon=None` (accept, ignore) to `FakePlanner`,
  `CapturingPlanner`, `RecordingDisabledPlanner`
  (test_retrieval_pipeline.py), `FixedPlanner`, `FailingPlanner`
  (test_retrieval_trace_pipeline.py), and `PlannerProxy`
  (tests/retrieval_core_characterization.py — accept and do NOT
  record, keeping frozen baselines intact).
- [ ] **3.4** Full suite; characterization green (STOP otherwise).
  Commit `feat: thread the support lexicon into the planner (P12 Task 3)`.

### Task 4: Frozen Gold Fixture + Runner

- [ ] **4.1** `tests/fixtures/p12_planner/gold.json`: the 21 queries +
  required paths keyed by project name + per-project aggregate sha +
  file count (NO per-file inventory). Generated from the durable
  `.quality` copies; a unit test asserts fixture aggregate shas match
  the durable manifest.
- [ ] **4.2 RED/GREEN** `tests/p12_planner_acceptance.py`:
  - `capture <impl_root> <sources_root> <out> [--planner off]`:
    validate manifest (drift STOP / missing BLOCKED); wipe+reindex each
    copy with `p8._embedding_config("bge")` + `p8._install_bge_truncation()`;
    install the OPTIONS PIN on the loaded tree (monkeypatch
    `OllamaQueryPlanner.plan`'s session post — or wrap `plan` — to
    inject the frozen options identically for any tree); run all 21
    queries TWICE in-process with planner on (or off for the
    reference); enforce pass-equality of required-rank maps and
    planner status "ok" everywhere (planner-on only); record the
    design's evidence schema (statuses, latencies both passes,
    ranks, selected paths, kept/discarded counts, surviving hints,
    identities incl. qwen digest + injected options).
  - `compare <baseline> <candidate> <reference> <heldout-eval...> <out>`:
    gates G1/G2/G3/G4/G6 per design rule 8 (G4 = mean over all queries
    of both passes); disposition ship iff all true.
  - `check`: schema, canonical render, no absolute paths, no
    content/snippet, 21 cases.
  - Unit tests (`tests/test_p12_planner_acceptance.py`): every gate
    polarity on synthetic captures; drift raise; leak raise.
- [ ] **4.3** Full suite; commit
  `test: frozen P12 planner gold and paired runner (P12 Task 4)`.

### Task 5: Captures And The Single A/B

- [ ] **5.1** Warmups (chat+embed) immediately before EVERY capture.
  Planner-OFF reference: one capture from the baseline tree
  (`git worktree add --detach "$P12/baseline-tree" 04e11fe`),
  `--planner off`.
- [ ] **5.2** BASELINE ×2 (separate processes, planner on, baseline
  tree); byte-identical modulo timing/implementation (STOP otherwise).
- [ ] **5.3** CANDIDATE ×2 from the working tree; same rule.
- [ ] **5.4** Held-out one-shot: evaluate `heldout.json` (sha must
  match the sealed record) on the baseline and candidate captures'
  workspaces via one dedicated runner invocation; report delta
  verbatim.
- [ ] **5.5** `compare`; evaluate G1–G4, G6 from the report; G5 = full
  suite + boundaries guards green. ONE comparison, one disposition per
  design rule 10. Non-ship: the branch does not merge (no inert switch
  needed); record; write the applicable rule-10 statement.

### Task 6: Record

- [ ] Digests, aggregate shas, held-out sha + delta, all gate values,
  per-project deltas, determinism confirmations (all passes + both
  capture pairs + Task 0 probe), latency arithmetic, surviving-hint
  evidence for moved queries, disposition, rule-10 statement,
  gold-as-diagnostic disclosure, `test_quality_planner.py`
  environment-gated meaning-change note.

## Stop Conditions

Missing models / cross-process probe failure (BLOCKED); manifest drift
(STOP) vs copies lost (BLOCKED); any pass or capture-pair divergence;
any planner status ≠ ok; characterization/boundaries drift; any
post-comparison edit.

## Implementation Record

Status: Not started. Record only observed, verified results.
