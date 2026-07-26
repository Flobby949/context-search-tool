# P12 Repo-Grounded Planner Translation v1 Design

Date: 2026-07-26
Status: Draft for adversarial review; implementation not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: current main (`04e11fe`)
Predecessors: P11 implementation record (reject; rule-7 statement names
LLM-based mechanisms as the remaining class), P12 exploratory eval
(2026-07-26, three pinned projects, 21 intent-phrased queries).

## Problem, Stated From Evidence

The P12 exploratory eval (21 intent-phrased queries, 53 required files,
three projects of 82/271/287 files) measured the ladder:

| config | recall@12 |
| --- | --- |
| hash (default) | 16/53 (30%) |
| bge-m3 index | 18/53 (34%) |
| bge + planner on | 20/53 (38%) |
| fast-context (agentic, remote LLM) | 36/53 (68%) |

The dominant failure is missing intent→identifier translation. The
planner was built to be exactly that translator, and probing it shows
the translation IS produced and then destroyed in post-processing:

- For `ia-cron-jobs` (a 0/2 query), qwen3.5:4b returned raw hints
  `isTradingDay` (a real method in the gold file's call chain), `cron`,
  `schedule`, `non-trading day`, `sync`/`result record`. Every one was
  discarded by `_filter_identifier_hints` / `_filter_rewritten_queries`
  because the support vocabulary is built from the same 2.5KB
  `RepoProfile` sample the model saw — 130 distinct tokens for a repo
  whose index holds 41,513 distinct `chunk_tokens` rows. All six probe
  tokens (`trading`, `day`, `cron`, `schedule`, `sync`, `log`) exist in
  the full lexicon.
- For pure-Go `git-course`, `symbols` is empty (no Go symbol producer),
  the profile carries 82 vocabulary tokens against a 21,281-token
  lexicon, and the filter reduced the planner's rewritten queries to
  `"go tui orchestrator"` / `"go error"` / `"go app"`.
- The anti-hallucination *intent* of the filter is sound: for
  `gc-env-check` qwen also invented `LaunchGuard`, `PreStartValidators`
  — names that exist nowhere and should be dropped.

Diagnosis: the filter's support set is a starved sample, so it has a
catastrophic false-negative rate on correct translations, while the
model's input profile is too thin to ground it (and blind for languages
without a symbol producer). The mechanism class (LLM reads and
translates the query) is the one P11's exhaustion statement left open;
this is its cheapest instantiation — one local LLM call that already
ships behind `query_planner.enabled = False`.

## Pre-Committed Rules (fixed before any comparison)

1. **Support = the full indexed lexicon.** A new store API (frozen
   name: `planner_support_lexicon`) returns the lowercased token set
   `distinct chunk_tokens.token (active chunks) ∪
   tokenize_query(symbols.name) ∪ tokenize_query(source_files.path)`.
   `clean_planner_payload` filters against THIS set instead of
   `profile_vocabulary(repo_profile)`. Filter semantics are otherwise
   byte-preserved: same term granularity, same all-tokens-supported
   rule for hints, same ≥2-supported-tokens rule for rewritten queries
   (support = lexicon ∪ original-query tokens), same caps, same
   `discarded_hints` recording.
2. **Profile enrichment (model input only).** `RepoProfileLimits`
   becomes `max_files 32, max_symbols 96, max_tokens 64, max_chars
   6000` (languages unchanged). When the symbols table is empty, the
   profile's `symbols` list is filled with file-basename identifiers
   (deterministic: stem of each `source_files` path, most-chunks-first,
   deduped, same 96 cap). The profile remains model input and telemetry
   only; it no longer defines the filter.
3. **Reproducibility.** The Ollama chat request gains
   `"options": {"temperature": 0, "seed": 0}`. `PROMPT_VERSION` and the
   system prompt text are unchanged in P12 (prompt engineering is a
   separate lever; one lever per experiment).
4. **Activation and privacy unchanged.** Planner stays default-off,
   provider-gated to `ollama`. The enriched profile is the same
   category of metadata (paths, symbol names, tokens — never file
   bodies) flowing to the same user-configured local endpoint.
5. **The A/B.** Frozen gold: the 21 P12 queries with their 53 required
   paths, checked into the repo as a fixture; the three project copies
   pinned by a content-inventory sha256 manifest (drift = STOP, never
   re-pin). Both sides run bge-m3 index + planner on, captured by the
   candidate runner: baseline = detached worktree at main, candidate =
   working tree. One comparison, one disposition.
6. **Determinism rule.** Every capture runs its query set twice in one
   process; the per-query required-rank maps must be identical between
   the two passes (temperature 0 + seed 0). Divergence is a STOP, not
   an averaging opportunity.
7. **Gates.**
   - G1: candidate required hits ≥ baseline required hits + 5 (on the
     measured baseline capture, not the exploratory 20/53).
   - G2: no project's hit subtotal decreases.
   - G3: no query falls from ≥1 hit (baseline) to 0 (candidate).
   - G4: candidate mean query latency ≤ 1.5 × baseline mean (planner
     path measured like-for-like; formula recorded in the record).
   - G5: hash-default regression — the standing P8 harness hash
     baseline (planner off) plus the full test suite stay green;
     planner-off retrieval is structurally unreachable by this change
     (`DisabledQueryPlanner` short-circuits), and any characterization
     drift is a STOP.
   If G1 fails, the record must state: query-side LLM grounding is
   insufficient at this model size; the remaining levers are prompt
   engineering (v3), multi-turn retrieval, or result-side listwise
   rerank — a product decision, no same-family variants without a new
   review.
8. **No post-comparison edits** to any constant, filter rule, prompt,
   or gold definition.

## Architecture

### Selected: full-lexicon support + enriched profile

- `sqlite_store.py`: `planner_support_lexicon() -> frozenset[str]` —
  one query over `chunk_tokens` (active chunks) plus tokenized symbol
  names and file paths, built per retrieval call (~tens of ms at 40k
  tokens; `chunk_tokens.token` is indexed).
- `query_planner.py`: `clean_planner_payload` accepts
  `support_lexicon: frozenset[str] | None`; when provided it replaces
  `profile_vocabulary` as the filter base. `OllamaQueryPlanner.plan`
  gains the same optional parameter, threaded from retrieval. Request
  gains pinned `options`.
- `repo_profile.py`: cap changes; basename-symbol fallback.
- `src/context_search_tool/retrieval.py`: builds the lexicon alongside
  the existing `build_repo_profile(store)` call and passes both.
- Runner: `tests/p12_planner_acceptance.py` (capture/compare/check),
  gold + inventory manifest under `tests/fixtures/p12_planner/`.

### Rejected: directory tree in the prompt

The probe shows correct translations already emerge from the starved
profile (`isTradingDay` was produced without any tree). Tree injection
grows the payload and the hallucination surface before the cheap fix is
measured. Deferred, not forbidden.

### Rejected: dropping the filter entirely

`LaunchGuard` / `PreStartValidators` demonstrate real hallucinations.
Unfiltered hints feed `planner_lexical` / `planner_path_symbol`
scoring; the P10 record shows what ungrounded token affinity does.

### Rejected: result-side LLM rerank first

Strictly more expensive per query (candidate content through an LLM vs
one query-text call), and P12's evidence localizes the loss at query
understanding, not candidate ordering.

## Change Surface

| file | responsibility |
| --- | --- |
| `sqlite_store.py` | `planner_support_lexicon` |
| `query_planner.py` | lexicon-based filtering, pinned options |
| `repo_profile.py` | caps, basename-symbol fallback |
| `retrieval.py` | thread lexicon into the planner call |
| `tests/p12_planner_acceptance.py` | frozen gold runner |
| tests per plan | unit matrix, e2e planner pins, A/B captures |

Untouched: selection/ranking/expansion/candidates scoring,
`retrieval_trace/models.py` (P4-frozen), relation machinery, README
privacy posture (planner section reviewed, not weakened).
