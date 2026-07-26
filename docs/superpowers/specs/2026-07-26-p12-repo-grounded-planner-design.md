# P12 Repo-Grounded Planner Translation v1 Design

Date: 2026-07-26
Status: Revised after adversarial review (r2); implementation authorized by the user conditional on this revision
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `04e11fe` (main)
Predecessors: P11 record (rule-7 names LLM mechanisms as the remaining
class), P12 exploratory eval (21 intent queries / 53 required files,
three pinned projects).

Review r2 note: the draft bundled three levers (lexicon filter, profile
enrichment, sampling pinning) and pinned sampling inside the candidate
source, which made the baseline capture structurally unable to satisfy
its own determinism STOP. r2 narrows the treatment to ONE lever (the
filter), reclassifies sampling pinning as runner infrastructure applied
identically to both trees, defers profile enrichment to a successor
experiment, and adds the held-out set, the planner-off reference, and
the guard-allowlist edits both reviewers demanded.

## Problem (evidence unchanged from r1)

Ladder on the frozen-able gold: hash 16/53 → bge 18/53 → bge+planner
20/53 → fast-context 36/53. Probe evidence: for `ia-cron-jobs` (0/2)
qwen's RAW output contained `isTradingDay`, `cron`, `schedule`,
`non-trading day` — all real lexicon members (verified in
`chunk_tokens`) — and ALL were discarded because the support vocabulary
is the 2.5KB profile sample (130 tokens vs 41,513 in the index).
Hallucinations (`LaunchGuard`) were also present, so the filter must
stay — grounded against the true lexicon. Disclosure: this diagnosis
was derived from the same 21 queries that form the gold; the probe
touched `ia-cron-jobs` and `gc-env-check` token-by-token. The held-out
protocol below exists because of that contamination.

## The Single Treatment Lever

`clean_planner_payload` filters hints and rewritten queries against the
full indexed lexicon instead of `profile_vocabulary(repo_profile)`.
Nothing else about planner behavior changes in this experiment.
Deferred to a successor (NOT in this A/B): profile cap enrichment and
the basename-symbol fallback for symbol-less languages (the successor
will use the plan's simpler files-order stem definition), prompt text
changes, planner-on-by-default.

## Pre-Committed Rules (fixed at this revision)

1. **Support = full indexed lexicon.** Store API (frozen name)
   `planner_support_lexicon() -> frozenset[str]`: lowercased
   `distinct chunk_tokens.token` over active chunks ∪
   `tokenize_query(symbols.name)` ∪ `tokenize_query(source_files.path)`,
   dropping tokens shorter than 2. Filter helpers, term granularity,
   all-tokens-supported rule, ≥2-supported-tokens rewritten-query rule,
   caps, and `discarded_hints` recording are byte-preserved; only the
   vocabulary set changes. Legacy path: with `support_lexicon=None` the
   existing `profile_vocabulary` behavior is untouched.
2. **Lexicon gating:** built in `retrieval.py` iff
   `config.query_planner.enabled` is true (measured build cost on the
   pinned copies: 15.0 / 32.8 / 88.6 ms). Injected test planners with
   planner-disabled config receive `support_lexicon=None`; exploration
   follow-up probes (DisabledQueryPlanner injections) never pay the
   cost. Planner-off retrieval remains structurally unchanged.
3. **Sampling pinning is runner infrastructure, not treatment.** The
   P12 acceptance runner monkeypatches the planner request of WHICHEVER
   tree PYTHONPATH selects to inject
   `"options": {"temperature": 0, "seed": 0, "top_k": 1}` (precedent:
   `_install_bge_truncation`). The candidate source ALSO ships the same
   options as product behavior; because the runner injects identically
   on both sides, this cannot differ between sides and is not a lever
   in the A/B.
4. **Privacy:** the repo gains NO per-file inventory of the user's
   projects. Committed fixture carries queries + required paths +
   aggregate sha256 + file count per project only; the full per-file
   manifest lives in gitignored `.quality/`. Planner egress posture
   unchanged (metadata to the user-configured local endpoint only).
5. **Gold, storage, drift.** The 21 queries / 53 required items are
   frozen exactly as archived; the three project copies move at Task 0
   into durable gitignored `.quality/p12-eval-sources/` and are pinned
   by the aggregate manifest then. At capture time: content drift =
   STOP (never re-pin); copies lost = BLOCKED (restore from the durable
   root only).
6. **Held-out set.** At Task 0 a FRESH agent with no access to the
   failure analysis authors 8 intent-phrased queries with required
   files over the same three pinned copies; the set is sealed
   (sha256 recorded in the plan record) before any implementation
   commit, evaluated EXACTLY once, at comparison time, on both
   baseline and candidate captures. Pre-committed interpretation: the
   held-out delta is reported verbatim in the record; if the gold
   gates pass but the held-out delta is ≤ 0, the disposition is still
   governed by the gates, and the record MUST carry a named
   "benchmark-fit risk" caveat; no re-runs, no query edits.
7. **Captures and determinism.**
   - Config frozen: ToolConfig defaults except
     `embedding = bge/bge-m3/1024` and `query_planner.enabled = true`
     (every other planner field at its default; `final_top_k = 12`).
   - "Hit" := the required path appears among the 12 selected results.
   - Each capture runs the 21 queries TWICE in one process; per-query
     required-rank maps must match between passes (STOP otherwise) —
     valid on both trees because the runner injects the options pin.
   - Each SIDE is captured twice in separate processes; the two
     captures must be byte-identical modulo timing/implementation
     (P11 discipline; catches reindex and cross-process drift).
   - Task 0 probes cross-process chat stability: the same pinned chat
     request in two processes must return byte-equal content
     (precondition; failure = BLOCKED).
   - No other Ollama clients may run during captures.
   - Per-query planner `status` is recorded; any status ≠ "ok" in any
     pass of any capture = STOP (silent-fallback guard).
8. **Reference and gates.** Captures: planner-OFF reference (bge, one
   capture, double-pass rule applies without planner), baseline
   (main tree, planner on), candidate (working tree, planner on).
   - G1: candidate hits ≥ baseline hits + 5.
   - G2: no project subtotal decreases (candidate vs baseline).
   - G3: no query falls from ≥1 (baseline) to 0 (candidate).
   - G4: mean latency over ALL queries of BOTH passes:
     candidate ≤ 1.5 × baseline.
   - G5: hash-default regression — full suite green including the
     boundaries guards (extended by the pre-declared allowlists
     below); any characterization drift = STOP.
   - G6: candidate hits ≥ planner-off reference hits + 3 (shipping a
     planner worse than no planner is forbidden).
   One comparison, one disposition, no post-comparison edits.
9. **Guard allowlists are part of the reviewed change.** 
   `test_retrieval_core_boundaries.py` gains
   `P12_PLANNER_PRODUCTION_CHANGES = {"src/context_search_tool/query_planner.py"}`
   OR'd into the protected-diff assertions, and
   `_is_p4_public_facade_reference` admits
   `tests/p12_planner_acceptance.py` + the `tests/test_p12_` prefix.
   New pipeline tests reuse existing imports (ledger reference counts
   pinned); stub planners updated per plan (characterization proxy
   accepts and does NOT record the new kwarg, so frozen baselines are
   untouched). `retrieval.py` gains no new top-level defs or module
   assignments (EXPECTED_LOCAL_DEFINITIONS stays).
10. **Disposition statements (pre-committed).**
    - G1 fails: "full-lexicon grounding of the shipped planner did not
      reach +5 on the gold (measured delta: X). Remaining levers:
      profile enrichment, prompt v3, multi-turn retrieval, listwise
      rerank — a product decision." (No claim about model size or the
      class beyond the measured lever.)
    - Reject caused only by G2/G3: "grounding helps in aggregate but
      regresses named queries: [ids]; per-query loss analysis attached."
    - Reject caused only by G4: "latency regression: numbers; mechanism
      effect otherwise as measured."
    - G6 fails: "the planner (grounded or not) underperforms
      planner-off on this gold; enabling it is not recommended."

## Capture Evidence Schema (rule for the runner)

Per query, per pass: planner status, latency, required-rank map,
selected relative paths, kept/discarded hint COUNTS, and the surviving
grep keywords / symbol hints / rewritten queries (identifier strings —
same privacy category as selected paths; `check` still rejects
`content`/`snippet`). Capture header: implementation identity,
embedding identity + digest, planner identity (provider, model, digest,
PROMPT_VERSION, prompt_hash, injected options), config fingerprint.

## Change Surface

| file | responsibility |
| --- | --- |
| `sqlite_store.py` | `planner_support_lexicon` (top-level cycle-free `tokenize_query` import) |
| `query_planner.py` | `support_lexicon` kwarg through Protocol/planners/clean; options in request (product) |
| `retrieval.py` | inline lexicon build (gated) + threading; no new top-level defs |
| `tests/test_retrieval_core_boundaries.py` | P12 allowlists (rule 9) |
| `tests/test_query_planner.py` | lexicon filter matrix, options pin |
| `tests/test_retrieval_pipeline.py` | threading e2e, planner-off pin, stub signature updates |
| `tests/test_retrieval_trace_pipeline.py` | stub signature updates |
| `tests/retrieval_core_characterization.py` | proxy accepts+ignores kwarg |
| `tests/p12_planner_acceptance.py` (+unit test file) | runner per rules 3/7/8 + evidence schema |
| `tests/fixtures/p12_planner/gold.json` | queries + required + aggregate shas only |

Untouched: `repo_profile.py` (enrichment deferred), selection/ranking/
expansion/candidates, `retrieval_trace/models.py` (P4-frozen), relation
machinery, prompt text, `PROMPT_VERSION`.
