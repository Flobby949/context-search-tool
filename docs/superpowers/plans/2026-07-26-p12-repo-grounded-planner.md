# P12 Repo-Grounded Planner Translation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Draft for adversarial review; implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `04e11fe` (main)
Design:
`docs/superpowers/specs/2026-07-26-p12-repo-grounded-planner-design.md`

**Goal:** One pre-committed experiment: filter planner hints against the
full indexed lexicon instead of the 2.5KB profile sample, enrich the
profile the model sees, pin sampling, and measure on the frozen P12
gold (bge + planner on, both sides).

**Architecture:** `sqlite_store.planner_support_lexicon()` supplies the
support set; `clean_planner_payload` filters against it when provided
(legacy profile-vocabulary path preserved when it is not);
`repo_profile` grows caps and a basename-symbol fallback; retrieval
threads the lexicon only when the planner is enabled. Planner remains
default-off; hash/planner-off behavior is structurally unreachable.

## Global Constraints

- Runtime/tests: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src"
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider`.
  Known-environmental: `tests/test_p6_measurement_worker.py` failures.
- Every Python process that talks to Ollama sets
  `NO_PROXY=localhost,127.0.0.1` (planner session already sets
  `trust_env=False`; the constraint covers curl probes and the runner).
- Frozen at review: lexicon definition (`chunk_tokens` active ∪
  tokenized `symbols.name` ∪ tokenized `source_files.path`,
  lowercased), profile caps `files 32 / symbols 96 / tokens 64 / chars
  6000`, basename-symbol fallback, `options {"temperature": 0, "seed":
  0}`, prompt text and `PROMPT_VERSION` unchanged, gates G1–G5, gold =
  the 21 queries / 53 required items exactly as captured in
  `tests/fixtures/p12_planner/gold.json`. No post-comparison edits.
- Eval projects: the pinned copies under
  `$(cat .quality/p12-eval-root.txt)` (`backend-template`,
  `Investment-Assistant`, `git-course`). Their content-inventory sha256
  is frozen in Task 5; drift at capture time is a STOP, never a re-pin.
  Never touch the user's originals under `/Users/flobby/vibe_coding/`.
- Captures never contain source bodies or absolute paths (projects are
  keyed by name; paths are repo-relative).
- The A/B is BLOCKED without local Ollama serving BOTH `bge-m3` and
  `qwen3.5:4b-mlx` (digests recorded); never simulated.
- Run root: `P12=$(mktemp -d /private/tmp/cst-p12-run.XXXXXX); echo
  "$P12" > .quality/p12-run-root.txt`.
- No commit/push beyond the working branch unless the user asks.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/sqlite_store.py` | `planner_support_lexicon()` |
| modify | `src/context_search_tool/query_planner.py` | `support_lexicon` filtering, pinned options |
| modify | `src/context_search_tool/repo_profile.py` | caps, basename-symbol fallback |
| modify | `src/context_search_tool/retrieval.py` | build + thread the lexicon |
| modify | `tests/test_query_planner.py` | filter matrix flip + options pin |
| modify | `tests/test_repo_profile.py` | caps + fallback matrix |
| modify | `tests/test_retrieval_pipeline.py` | e2e lexicon threading + planner-off pin |
| create | `tests/p12_planner_acceptance.py` | capture / compare / check runner |
| create | `tests/fixtures/p12_planner/gold.json` | frozen 21-query gold |
| create | `tests/fixtures/p12_planner/sources_manifest.json` | pinned-copy inventory shas |
| evidence | `$(cat .quality/p12-run-root.txt)` | baseline/candidate captures, comparison |

---

### Task 0: Gates Only

- [ ] **Step 0.1:** Branch `feat/p12-repo-grounded-planner` from main;
  full suite green (2983±, p6 env aside). Create and persist `$P12`.
- [ ] **Step 0.2:** Ollama precondition:
  `curl -s --noproxy '*' localhost:11434/api/tags` must list `bge-m3`
  AND `qwen3.5:4b-mlx`; record both digests into the record. One chat
  warmup (`/api/chat` with the pinned options) and one embed warmup.
- [ ] **Step 0.3:** Eval copies present under
  `$(cat .quality/p12-eval-root.txt)` with `.context-search` intact
  (bge indexes from the exploratory run are NOT reused for captures —
  Task 6 reindexes deterministically).

### Task 1: RED/GREEN `planner_support_lexicon`

- [ ] **Step 1.1: RED** in `tests/test_retrieval_pipeline.py` (store
  APIs are tested there alongside the other store surface): index a
  tmp workspace containing `alpha_service.py` (content mentioning
  `trading day cron`), a symbol-bearing file if cheap, and one file
  whose only signal is its path (`tools/sync_log_helper.py` with
  trivial body). Assert:
  - `store.planner_support_lexicon()` contains `"trading"`, `"cron"`,
    `"sync"`, `"log"`, `"helper"` (path-derived), `"alpha"`;
  - all entries are lowercase;
  - deleting the file (re-index without it) removes its unique tokens
    (active-chunks-only clause).
  Expected RED: `AttributeError: planner_support_lexicon`.
- [ ] **Step 1.2: GREEN:** implement in `sqlite_store.py`:

```python
def planner_support_lexicon(self) -> frozenset[str]:
    with self._connect() as connection:
        token_rows = connection.execute(
            """
            SELECT DISTINCT chunk_tokens.token
            FROM chunk_tokens
            JOIN chunks ON chunks.chunk_ref = chunk_tokens.chunk_ref
            WHERE chunks.deleted_at IS NULL
            """
        ).fetchall()
        symbol_rows = connection.execute(
            "SELECT DISTINCT name FROM symbols"
        ).fetchall()
        path_rows = connection.execute(
            "SELECT path FROM source_files"
        ).fetchall()
    tokens: set[str] = {
        str(row["token"]).lower() for row in token_rows
    }
    for row in symbol_rows:
        tokens.update(
            token.lower() for token in tokenize_query(str(row["name"]))
        )
    for row in path_rows:
        tokens.update(
            token.lower() for token in tokenize_query(str(row["path"]))
        )
    return frozenset(token for token in tokens if len(token) >= 2)
```

  (adjust the `source_files` column name to the actual schema at
  implementation time; `tokenize_query` is already imported by the
  store or imported locally to avoid cycles).
- [ ] **Step 1.3:** Full suite; commit
  `feat: full-index planner support lexicon (P12 Task 1)`.

### Task 2: RED/GREEN Lexicon-Based Filtering + Pinned Options

- [ ] **Step 2.1: RED** in `tests/test_query_planner.py`:
  - `clean_planner_payload(..., repo_profile=profile,
    support_lexicon=frozenset({...}))` keeps a hint whose tokens are in
    the lexicon but NOT in `profile_vocabulary(profile)` (the
    `isTradingDay` shape: lexicon ⊇ {is, trading, day}), and still
    drops a hint with any token outside the lexicon (`LaunchGuard`
    shape); dropped hints appear in `discarded_hints`.
  - rewritten-query rule unchanged in shape: ≥2 tokens supported by
    lexicon ∪ original-query tokens survive as the cleaned string.
  - legacy path pin (NOT RED): with `support_lexicon=None` and a
    profile, behavior is byte-identical to today (existing tests at
    tests/test_query_planner.py:~430-460 stay green unmodified).
  - `OllamaQueryPlanner` request pin: monkeypatch the session's
    `post`; assert the JSON body contains
    `"options": {"temperature": 0, "seed": 0}` and that `plan(query,
    repo_profile=..., support_lexicon=...)` forwards the lexicon to
    `clean_planner_payload`.
  Expected RED: unexpected-keyword `support_lexicon`.
- [ ] **Step 2.2: GREEN:** implement in `query_planner.py`:
  - `clean_planner_payload(..., support_lexicon: frozenset[str] | None
    = None)`; filter base = `support_lexicon` when it is not None, else
    the existing `profile_vocabulary(repo_profile)` path; both feed the
    SAME `_filter_identifier_hints` / `_filter_rewritten_queries`
    helpers (their signatures already take a vocabulary set — no logic
    change inside them).
  - `OllamaQueryPlanner.plan(query, repo_profile=None,
    support_lexicon=None)`; `DisabledQueryPlanner` and the `QueryPlanner`
    Protocol gain the same keyword (ignored).
  - request body gains the frozen `options` object.
- [ ] **Step 2.3:** Full suite; commit
  `feat: lexicon-grounded planner filtering (P12 Task 2)`.

### Task 3: RED/GREEN Profile Enrichment

- [ ] **Step 3.1: RED** in `tests/test_repo_profile.py`:
  - `RepoProfileLimits()` exactness: `max_files == 32`,
    `max_symbols == 96`, `max_tokens == 64`, `max_chars == 6000`.
  - basename fallback: a store stub whose `symbol_names_for_profile`
    returns `[]` and whose `source_files_for_profile` returns
    `[Path("internal/app/orchestrator.go"), Path("cmd/main.go")]`
    yields `profile.symbols == ["orchestrator", "main"]` (stem order =
    file order, deduped, capped at `max_symbols`).
  - non-empty symbols: fallback NOT applied.
- [ ] **Step 3.2: GREEN:** implement in `repo_profile.py`
  (`build_repo_profile` computes `symbols = store.symbol_names…` then
  `if not symbols: symbols = [Path(f).stem for f in files-order]`,
  dedup, cap). Full suite (`_fit_budget` and vocabulary tests may need
  cap-driven updates — pin the NEW values, never loosen assertions).
  Commit `feat: enriched planner repo profile (P12 Task 3)`.

### Task 4: RED/GREEN Retrieval Threading + Planner-Off Pin

- [ ] **Step 4.1: RED** in `tests/test_retrieval_pipeline.py`:
  - e2e: index a small workspace; inject a stub planner (the existing
    `planner=` parameter of the query path) that RECORDS the
    `support_lexicon` kwarg it receives and returns a fixed plan whose
    grep keyword exists in the index but not in the profile sample;
    assert the lexicon was a non-empty frozenset and the keyword's
    tokens appear in `bundle.expanded_tokens` (i.e. survived into the
    planner channels).
  - planner-off pin (NOT RED): with DEFAULT_CONFIG,
    `store.planner_support_lexicon` is never called (monkeypatch a
    counting wrapper) and results are byte-identical to a pre-change
    capture of the same fixture (reuse an existing pipeline
    fixture's assertions).
- [ ] **Step 4.2: GREEN:** in `retrieval.py`, extend the existing
  conditional profile block (retrieval.py:311-316): build
  `support_lexicon = store.planner_support_lexicon()` under the SAME
  condition that builds the profile; call
  `planner_instance.plan(query, repo_profile=repo_profile,
  support_lexicon=support_lexicon)`.
- [ ] **Step 4.3:** Full suite; hash-default characterization all green
  (STOP otherwise). Commit
  `feat: thread the support lexicon into the planner (P12 Task 4)`.

### Task 5: Freeze Gold + Runner

- [ ] **Step 5.1:** Write `tests/fixtures/p12_planner/gold.json` — the
  21 queries / 53 required paths exactly as archived at
  `$(cat .quality/p12-eval-root.txt)/gold_p12.json`, with project roots
  replaced by symbolic keys (`backend-template`, `investment-assistant`,
  `git-course`). Write `sources_manifest.json`: per project, sorted
  repo-relative file list + per-file sha256 + aggregate sha of the
  pinned copies (excluding `.context-search`).
- [ ] **Step 5.2: RED/GREEN runner** `tests/p12_planner_acceptance.py`:
  - `capture <impl_root> <eval_root> <out.json>`: validates the
    sources manifest (drift = raise), wipes and reindexes each project
    copy with the bge config (reusing the P8 runner's `_embedding_config`
    pattern and its 4000-char BGE truncation guard), runs the 21
    queries with planner enabled TWICE in-process, asserts pass-1 ==
    pass-2 required-rank maps (determinism STOP), records: schema
    version 1, implementation identity (P8 runner's helper), embedding
    identity + digest, planner identity (provider, model, digest,
    `PROMPT_VERSION`, `prompt_hash()`, options), per-query required
    ranks + selected relative paths, per-pass mean latency. Canonical
    render; `check` validates schema, canonical render, no absolute
    paths, no `content`/`snippet` keys, 21 cases.
  - `compare <baseline> <candidate> <out>`: gates G1 (hits ≥ base+5),
    G2 (per-project subtotals non-decreasing), G3 (no ≥1→0 query), G4
    (`candidate.mean_latency / baseline.mean_latency ≤ 1.5`), plus the
    determinism flags from both captures; disposition `ship` iff all
    gates true else `reject` (no middle disposition — G5 lives in the
    suite, not the runner).
  - Unit tests in `tests/test_p12_planner_acceptance.py`: synthetic
    captures exercise every gate polarity; manifest drift raises;
    absolute-path leak raises.
- [ ] **Step 5.3:** Full suite; commit
  `test: frozen P12 planner gold and paired runner (P12 Task 5)`.

### Task 6: Captures And The Single A/B

- [ ] **Step 6.1:** Warmups (chat + embed). BASELINE via detached
  worktree:

```bash
P12=$(cat .quality/p12-run-root.txt); EVAL=$(cat .quality/p12-eval-root.txt)
git worktree add --detach "$P12/baseline-tree" 04e11fe
env PYTHONDONTWRITEBYTECODE=1 NO_PROXY=localhost,127.0.0.1 \
  PYTHONPATH="$P12/baseline-tree/src:$PWD/tests" \
  .quality/p5-runtime/bin/python tests/p12_planner_acceptance.py \
  capture "$P12/baseline-tree" "$EVAL" "$P12/baseline.json"
```

- [ ] **Step 6.2:** CANDIDATE from the working tree (`capture "$PWD"
  ...` with `PYTHONPATH="$PWD/src:$PWD/tests"`).
- [ ] **Step 6.3:** `compare "$P12/baseline.json"
  "$P12/candidate.json" "$P12/comparison.json"`; evaluate G1–G4 from
  the report and G5 via the full suite + the standing P8 hash baseline
  invariants. ONE comparison, one disposition.
- [ ] **Step 6.4:** Disposition. Ship: merge path per user
  instruction, planner stays default-off, README planner section
  reviewed. Reject: revert Tasks 2–4's behavior by reverting the
  branch commits (machinery has no inert switch — the branch simply
  does not merge), record, and write the design's rule-7 statement.

### Task 7: Record

- [ ] Implementation record in this plan: digests (bge, qwen), gate
  values, per-project deltas, determinism confirmation for all four
  passes, latency arithmetic, newly-hit and newly-missed queries by
  id, disposition, and — on G1 failure — the rule-7 statement naming
  the remaining levers.

## Stop Conditions

- Ollama missing either model (BLOCKED; never simulated).
- Sources-manifest drift at any capture (STOP, never re-pin).
- In-capture pass-1 ≠ pass-2 required ranks (determinism STOP).
- Any hash-default characterization drift (G5 STOP).
- Any post-comparison edit.

## Implementation Record

Status: Not started. Record only observed, verified results.
