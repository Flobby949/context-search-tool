# P14 Exact-Identifier Definition-Owner Ranking v1 Implementation Plan

> **For agentic workers:** Execute one task at a time. Keep the
> production delta to the three reviewed files, use tests before code,
> and stop at the declared gates rather than tuning after evaluation.

Date: 2026-07-30
Status: Rebased r2; implementation authorized and in progress
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `501cf852ad54181eb823994747d2dc8555edc418`
Design:
`docs/superpowers/specs/2026-07-30-p14-exact-identifier-definition-owner-ranking-design.md`

**Goal:** For a query whose complete trimmed text is one code
identifier, give an already-recalled declaration owner a bounded
advantage over content references, closing both P1 profiles without
changing recall or non-exact query behavior.

**Architecture:** `IdentifierIntent` identifies the frozen
full-query-only SCREAMING_SNAKE grammar and exposes
`exact_identifier`. The ranker proves ownership from an exact,
case-sensitive `SymbolRef` whose declaration start lies in the chunk,
then adds the frozen
`identifier_definition_owner_boost = 0.50` only in `_rerank_score`.
Existing normalization, evidence classes, planner ceilings, cohort
logic, and selection remain authoritative. Context expansion keeps the
new score part winner-scoped.

**Tech stack:** Python 3.13 fixed repository runtime, pytest, existing
SQLite-backed retrieval pipeline, RetrievalTrace v1, P1 quality runner,
and the P8/P13 real-project capture infrastructure.

## Global Constraints

- The original shared checkout is the coordination root; it owns the
  ignored runtime and durable evidence even when implementation runs in
  separate worktrees:

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider
```

  `$PWD` in task commands is always the isolated candidate worktree.
  Never create the evidence root inside a disposable worktree.

- The committed behavior baseline is
  `501cf852ad54181eb823994747d2dc8555edc418`. It includes the
  OpenAI-compatible embedding/planner implementation and layered user
  configuration.
- P14 uses the dedicated online worktrees and pointers
  `.quality/p14-online-baseline-tree.txt` and
  `.quality/p14-online-candidate-tree.txt`. The old local-Ollama P14
  worktrees and evidence remain historical and must not be mixed into
  this run.
- No commit, branch, push, PR, model start/pull, or external publication
  without user authorization. Commit messages below are optional
  checkpoints only.
- Frozen product scope:
  `identifier_intent.py`, `retrieval_core/ranking.py`, and
  `retrieval_core/context_expansion.py`. No other production path.
- No new candidate source, store-query/file-read primitive, network
  call, index schema, provider branch, graph edge, planner hint,
  selection quota, or public schema. Eligible exact-query ordering may
  change which files the existing capped frontend and context-expansion
  passes read.
- The value `0.50`, owner predicate, grammar, gold, catalog, expected
  path, Top-K, and acceptance thresholds are frozen before the first
  candidate capture.
- `INVOLVED_BY_ME`, `AuditStatus.java`, `enum_value`, Java paths, and
  P1 case IDs may appear in tests/evidence but never in production.
- Live semantic captures use SiliconFlow `BAAI/bge-m3`; hybrid captures
  additionally use SiliconFlow `Qwen/Qwen2.5-7B-Instruct`. A
  live-service failure is `BLOCKED`. Do not substitute local Ollama,
  hash, mocks, cached reports, or skipped tests for online acceptance.
- The capture harness reads the API key only from the user-level config,
  injects it into the runtime config in memory, redacts it from errors,
  and never serializes it into catalogs, reports, or command lines.
- Every checkpoint audits both tracked and untracked files:

```bash
git status --short --untracked-files=all
git ls-files --others --exclude-standard
git diff --check
```

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/identifier_intent.py` | add exact identifier representation and full-query SCREAMING_SNAKE grammar |
| modify | `src/context_search_tool/retrieval_core/ranking.py` | declaration witness, fixed `0.50` rerank feature, reason |
| modify | `src/context_search_tool/retrieval_core/context_expansion.py` | retain winner-consistent owner score part |
| modify | `tests/test_identifier_intent.py` | grammar/exactness RED/GREEN |
| modify | `tests/test_retrieval_pipeline.py` | owner/reference ranking and merge matrix |
| modify | `tests/test_retrieval_trace_pipeline.py` | reason/adjustment propagation |
| modify | `tests/test_retrieval_core_boundaries.py` | exact P14 production overlay |
| modify | `tests/test_exploration_boundaries.py` | exact P14 production overlay |
| conditional modify | `tests/test_retrieval_core_characterization.py` | selective overlay for Task-0 inventoried exact queries |
| modify | `tests/test_quality_p5.py` | explicit eligible protected-direct owner overlay |
| modify | `tests/test_p5_protected_direct.py` | explicit eligible protected-direct owner overlay |
| modify | `tests/test_p6_benchmark.py` | explicit eligible exact-query snapshot overlay |
| add | `tests/p14_definition_owner_acceptance.py` | reproducible P1/P8 gate-input checker |
| add | `tests/test_p14_definition_owner_acceptance.py` | checker schema/arithmetic/outcome tests |
| conditional | `README.md` | user-facing exact-query behavior after acceptance |
| conditional | `docs/retrieval-quality.md` | P1 evidence/disposition after acceptance |
| conditional | `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` | close P1 only after ship |
| evidence | `$P14_RUN_ROOT` | immutable baseline/candidate reports; never source code |

---

### Task 0: Isolate Entry and Freeze Evidence

- [x] **Step 0.1: isolate P14.** The online provider baseline commit and
  detached worktrees were explicitly authorized. Record:

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

git -C "$P14_COORD_ROOT" rev-parse HEAD
git -C "$P14_COORD_ROOT" status --short --untracked-files=all
git -C "$P14_COORD_ROOT" ls-files --others --exclude-standard
```

  The coordination checkout is the authorized online-provider branch
  plus the two untracked P14 documents. It is not a capture tree.

  Create two clean detached worktrees at the behavior baseline: one
  immutable baseline capture tree and one candidate implementation tree.
  Store both validated absolute paths in the coordination root. After
  worktree creation is authorized, run:

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_BASELINE_SHA=501cf852ad54181eb823994747d2dc8555edc418
P14_BASELINE_TREE=/Users/flobby/vibe_coding/context-search-tool-p14-online-baseline-v2
P14_CANDIDATE_TREE=/Users/flobby/vibe_coding/context-search-tool-p14-online-candidate-v2
P14_BASELINE_POINTER="$P14_COORD_ROOT/.quality/p14-online-baseline-tree.txt"
P14_CANDIDATE_POINTER="$P14_COORD_ROOT/.quality/p14-online-candidate-tree.txt"

if [ -e "$P14_BASELINE_TREE" ] || [ -e "$P14_CANDIDATE_TREE" ]; then
  echo "P14 worktree target already exists; validate it manually" >&2
  exit 1
fi
git -C "$P14_COORD_ROOT" worktree add --detach \
  "$P14_BASELINE_TREE" "$P14_BASELINE_SHA"
git -C "$P14_COORD_ROOT" worktree add --detach \
  "$P14_CANDIDATE_TREE" "$P14_BASELINE_SHA"
test "$(git -C "$P14_BASELINE_TREE" rev-parse HEAD)" = "$P14_BASELINE_SHA"
test "$(git -C "$P14_CANDIDATE_TREE" rev-parse HEAD)" = "$P14_BASELINE_SHA"
test -z "$(git -C "$P14_BASELINE_TREE" status --porcelain --untracked-files=all)"
test -z "$(git -C "$P14_CANDIDATE_TREE" status --porcelain --untracked-files=all)"

if [ -e "$P14_BASELINE_POINTER" ]; then
  test "$(cat "$P14_BASELINE_POINTER")" = "$P14_BASELINE_TREE"
else
  (set -o noclobber; printf '%s\n' "$P14_BASELINE_TREE" > "$P14_BASELINE_POINTER")
fi
if [ -e "$P14_CANDIDATE_POINTER" ]; then
  test "$(cat "$P14_CANDIDATE_POINTER")" = "$P14_CANDIDATE_TREE"
else
  (set -o noclobber; printf '%s\n' "$P14_CANDIDATE_TREE" > "$P14_CANDIDATE_POINTER")
fi

BASELINE_TREE=$(cat "$P14_COORD_ROOT/.quality/p14-online-baseline-tree.txt")
CANDIDATE_TREE=$(cat "$P14_COORD_ROOT/.quality/p14-online-candidate-tree.txt")
cd "$CANDIDATE_TREE"
```

  Using `apply_patch`, materialize the two reviewed P14 documents from
  the coordination checkout into the candidate tree, then require their
  SHA-256 values to match. Do not copy any other uncommitted file. At
  this entry point, candidate `git status` may list only those two
  documents; the baseline tree remains clean forever. Re-run
  `rev-parse`, `status --short --untracked-files=all`, and
  `ls-files --others --exclude-standard` from the candidate, and use
  that output—not the coordination audit—as the implementation entry
  gate.

  `$PWD` for every later implementation command must equal the
  candidate pointer, never the coordination checkout or baseline tree.

- [x] **Step 0.2: fixed environment.** Record:

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

"$P14_PYTHON" -VV
"$P14_PYTHON" -c \
  'import sqlite3,numpy,pytest; print(sqlite3.sqlite_version,numpy.__version__,pytest.__version__)'
```

- [x] **Step 0.3: create one durable evidence root.**

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_RUN_ROOT="$P14_COORD_ROOT/.quality/p14-runs/20260731T032623Z-online-task0"
mkdir -p "$P14_RUN_ROOT"
printf '%s\n' "$P14_RUN_ROOT" > \
  "$P14_COORD_ROOT/.quality/p14-online-run-root.txt"
```

  Record baseline SHA, module origins, dirty state, environment,
  quality catalog SHA-256, and frozen P8/P13 source manifest
  identities. The pointer and evidence are gitignored. Do not use a
  temporary-only directory: P13 showed that a vanished `/tmp` root
  leaves hashes that cannot be independently inspected.

- [x] **Step 0.4: baseline focused and protected suites.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_identifier_intent.py \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_exploration_boundaries.py
```

  Then run the same full offline expression used for the candidate:

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  -m "not slow and not integration"
```

  Apply the Task-5.5 P6-only `sysctl` rule if needed. Any other failure
  is a STOP. Record exact pass/skip/deselect accounting rather than
  copying an old suite count.

- [x] **Step 0.5: freeze eligible-query inventory.** Before product
  edits, scan every committed retrieval characterization and quality
  query with the design's exact grammar. For each match, record query
  ID/text, identifier family, and whether any baseline candidate has a
  case-sensitive declaration-start witness without project-scope
  mismatch. Write the canonical inventory and its SHA-256 to
  `$P14_RUN_ROOT/eligible-queries.json`.

  Mark every full-query SCREAMING_SNAKE query eligible because that
  family enters the ranking-local reference model. Mark an exact
  camel/Pascal/lower-snake query eligible only if the applicable owner
  witness exists. Non-exact queries and existing-family exact queries
  without an applicable owner are immutable. The checker derives this
  allowlist from baseline facts before candidate comparison; a
  candidate delta can never make itself eligible.

- [x] **Step 0.6: build the pre-production acceptance harness.** Add
  `tests/p14_definition_owner_acceptance.py` and
  `tests/test_p14_definition_owner_acceptance.py` before changing any
  production file. The harness has two boundaries:
  - `capture-p8` and `capture-p1` orchestrate fresh child processes but
    never import production modules in the parent. They run the P8
    script or quality module from the requested implementation root
    with
    `PYTHONPATH=<implementation>/src:<implementation>/tests`, assert
    that `identifier_intent`, `ranking`, and `context_expansion` resolve
    beneath that root, and validate the output implementation identity.
    Both capture commands require `--attempt-id`, `--side`
    (`baseline|candidate`), and `--repeat` (`1|2`); those values are
    stored in an immutable envelope, and output creation fails if the
    path already exists;
  - comparison modes read JSON only and never execute a query.

  The P14 `capture-p8` envelope extends the legacy P8 projection without
  changing the general P8/P9 runner: for every selected result it
  records rank, path, numeric score, canonical sorted score parts, and
  ordered reasons in addition to the existing structural fields. That
  P14-only observable projection is required for complete non-eligible
  parity.

  The online capture layer is external to the implementation roots.
  It reads the user config, validates the exact SiliconFlow base URL,
  `BAAI/bge-m3` embedding identity, 1024 response dimensions, and
  `Qwen/Qwen2.5-7B-Instruct` planner identity, then injects only those
  runtime provider sections in memory. It never mutates the frozen
  catalog and never serializes the API key. Any Ollama identity,
  missing key, planner fallback, or unexpected model is rejected.

  Freeze two comparison CLIs:
  - `compare-p8` requires eight named captures:
    baseline/candidate × repeat 1/2 × hash/online, plus
    `--eligible-inventory` and `--output`;
  - `compare-p1` requires eight named captures:
    baseline/candidate × repeat 1/2 × vector/hybrid, plus `--catalog`
    and `--output`.

  Every named input is mandatory and unique. The parser rejects a path
  reused in two slots, provider/profile/side/repeat mismatches,
  cross-attempt mixing, missing repeats, output/input aliasing, and any
  schema or implementation-identity mismatch. Identity equality is
  side-local: all four baseline captures must identify the same
  immutable baseline tree, and all four candidate captures must
  identify the same candidate tree/state. Baseline and candidate
  identities are intentionally different and are never required equal.
  Both compare commands require `--attempt-id`, and all eight capture
  envelopes must equal it.
  Base attempt IDs are exactly `p8-initial`, `p1-initial`, `p8-final`,
  and `p1-final`. An allowed retry uses exactly `p8-retry-1` or
  `p1-retry-1`, a new directory, and eight newly captured inputs;
  initial/final files are never overwritten or mixed into the retry.

  Unit-test wrong-root/module-origin rejection, strict schemas,
  identity/catalog mismatches, selected/executed/pass counts, required
  rank extraction, fallback rejection, P8 required/noise arithmetic,
  eligible-query allowlists, complete non-eligible ranking-output
  parity, repeat canonicalization, and `ship/reject/blocked` outcomes.
  Non-eligible parity covers every captured ranking field after removing
  only declared envelope/timing fields, including membership, order,
  score, score parts, and reasons. The checker writes canonical gate
  JSON with every numerator, denominator, threshold, source filename,
  and SHA-256.

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_p14_definition_owner_acceptance.py
```

- [x] **Step 0.7: baseline live P1 capture.** If the configured
  SiliconFlow embedding and planner are available, capture each
  baseline P1 profile twice from the isolated baseline tree with module
  origins asserted. Require the known `6/7` result
  with `AuditStatus.java` recalled in Top-12 but outside Top-3 in both;
  record fresh ranks rather than requiring the stale diagnostic 5/6.
  If the target is already Top-3, or is no longer recalled in Top-12,
  the ranking-only diagnosis is false and P14 stops for redesign.
  Vector non-timing fields and hybrid case status, required ranks,
  planner status, and fallback state are the repeatability gate inputs.
  Use the pre-production wrapper, not a module imported from the
  candidate implementation:

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")
BASELINE_TREE=$(cat "$P14_COORD_ROOT/.quality/p14-online-baseline-tree.txt")
P14_P1_ATTEMPT_ID=p1-initial
P14_P1_ATTEMPT_ROOT="$P14_RUN_ROOT/$P14_P1_ATTEMPT_ID"
mkdir -p "$P14_P1_ATTEMPT_ROOT"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py capture-p1 \
  --attempt-id "$P14_P1_ATTEMPT_ID" \
  --side baseline \
  --repeat 1 \
  --implementation-root "$BASELINE_TREE" \
  --catalog "$BASELINE_TREE/tests/fixtures/retrieval_quality/queries.json" \
  --profile p1_vector_bge \
  --output "$P14_P1_ATTEMPT_ROOT/vector-baseline-r1.json" \
  --markdown "$P14_P1_ATTEMPT_ROOT/vector-baseline-r1.md"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py capture-p1 \
  --attempt-id "$P14_P1_ATTEMPT_ID" \
  --side baseline \
  --repeat 1 \
  --implementation-root "$BASELINE_TREE" \
  --catalog "$BASELINE_TREE/tests/fixtures/retrieval_quality/queries.json" \
  --profile p1_hybrid_bge \
  --output "$P14_P1_ATTEMPT_ROOT/hybrid-baseline-r1.json" \
  --markdown "$P14_P1_ATTEMPT_ROOT/hybrid-baseline-r1.md"
```

  Repeat both commands with `--repeat 2` and `-r2` paths under the same
  attempt root. Vector non-timing gate-input drift is a `STOP` for
  diagnosis, not a retry. If the hybrid gate inputs drift, retain both
  attempts and mark the live comparison pending; Task 6 may perform
  exactly one complete baseline/candidate-pair rerun under
  `p1-retry-1`. Raw planner text drift alone is disclosed but is not a
  failure. If services are unavailable, record `BLOCKED` and continue
  offline through Task 5.

  Online Task-0 result: vector reproduced `6/7` twice with
  `AuditStatus.java` at rank 5. Hybrid returned `4/7` and `2/7`; its
  fallback sets and owner ranks (`5`, `6`) drifted. The immutable
  reports and `baseline-status.json` therefore record `pending_retry`
  with the one global `p1-retry-1` attempt reserved. No Ollama fallback
  was used.

**Verify Task 0:** isolated tree; clean baseline tests; environment,
catalog, source, and eligible-query inventory pinned; acceptance
harness proves implementation-root isolation; baseline P1 is exactly
one of reproduced, `pending_retry` with `p1-retry-1` reserved, or
explicitly `BLOCKED`.

---

### Task 1: RED/GREEN — Exact-Identifier Intent

**Files:** `tests/test_identifier_intent.py`,
`src/context_search_tool/identifier_intent.py`.

- [x] **Step 1.1: write RED grammar tests.** Add table-driven cases for:
  - `INVOLVED_BY_ME`, `HTTP_2_MODE`, and surrounding whitespace;
  - lowercase snake, camelCase, PascalCase, and acronym-prefixed Pascal;
  - plain `REST`, leading/trailing underscores, doubled underscores,
    mixed-lowercase screaming forms, and punctuation boundaries;
  - uniqueness and the existing lexical sort.

- [x] **Step 1.2: write RED exactness tests.** Assert:

```text
INVOLVED_BY_ME                  -> exact_identifier set
 AuditStatus                    -> exact_identifier set
apply_dev                       -> exact_identifier set
find INVOLVED_BY_ME             -> exact_identifier None
`INVOLVED_BY_ME`                -> exact_identifier None
/apply/audit/pageEs INVOLVED... -> exact_identifier None
REST                            -> exact_identifier None
```

  For pure `INVOLVED_BY_ME`, assert `identifiers == ()`: the new family
  populates only `exact_identifier`. Wrapped/prose variants also keep
  `identifiers == ()`. The mixed route case preserves the baseline
  `identifiers == ("pageEs",)` while `exact_identifier is None`; only
  the uppercase constant is not added. Also cover two identifiers,
  `Owner.MEMBER`, quotes, and trailing punctuation. Existing
  camel/Pascal and lowercase-snake extraction, file hints, suffix hints,
  and role hints retain their current values.

- [x] **Step 1.3: run RED.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_identifier_intent.py
```

  Confirm failures are only the missing field/grammar.

- [x] **Step 1.4: implement GREEN.** Add the frozen SCREAMING_SNAKE
  regex using `fullmatch(query.strip())` only, plus
  `exact_identifier: str | None = None`. SCREAMING_SNAKE sets only that
  field; it never enters `identifiers`. Compute whole-query exactness
  for all three supported identifier families; do not strip
  punctuation or add a general parser.

- [x] **Step 1.5: run GREEN plus existing identifier ranking tests.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_identifier_intent.py \
  tests/test_retrieval_pipeline.py -k 'identifier_intent'
```

- [x] **Step 1.6:** audit the diff. Optional authorized checkpoint:
  `feat: recognize exact screaming-snake identifiers (P14 Task 1)`.

---

### Task 2: RED — Freeze Definition-Owner Ranking

**Files:** `tests/test_retrieval_pipeline.py`.

Use explicit `SymbolRef` declarations in every owner fixture. Content
alone is not proof of ownership.

- [x] **Step 2.1: main owner/reference case.** Build one enum/constant
  declaration and at least three higher-scoring references
  (controller, service/executor, and test). Query exactly
  `INVOLVED_BY_ME`. Assert:
  - the owner receives exactly
    `identifier_definition_owner_boost == 0.50`;
  - references receive no owner boost;
  - versus a paired control with the same identifier intent but the
    owner feature disabled, the owner's rerank score increases by
    exactly `0.50`;
  - the fixture places the owner within Top-3, without asserting Top-1;
  - references keep their relative order;
  - combined score, normalization of all candidates, evidence class,
    evidence priority, and rank tier are unchanged.

- [x] **Step 2.2: owner-witness matrix.** Assert no owner boost for:
  - matching content with no `SymbolRef`;
  - matching path/stem with no declaration;
  - `symbol.name="involved_by_me"` case mismatch;
  - an identifier substring rather than exact symbol name;
  - a `SymbolRef` whose `start_line` lies outside the chunk;
  - query `find INVOLVED_BY_ME`;
  - backtick-wrapped query;
  - plain acronym query `REST`.

  For an exact SCREAMING_SNAKE query, content-only and path/symbol
  references receive only the existing `0.20`/`0.30` identifier scores.
  Mixed, wrapped, and acronym queries preserve their exact pre-P14 order
  and score parts.

- [x] **Step 2.3: declaration-line boundary.** Create one class/type
  symbol spanning more than one 80-line chunk. Only the chunk
  containing `symbol.start_line` gets the boost. Also assert that a
  one-line Java-style enum value qualifies.

- [x] **Step 2.4: existing safeguards.** A planner-only or graph-only
  owner may carry the `0.50` feature but does not become
  original-direct/protected and remains planner-ceiling-clamped when
  the existing contract requires. When an owner participates in the
  minimum strong-direct ceiling anchor, assert that
  `pre_ceiling_rerank_score` includes exactly `0.50` and that the
  unchanged ceiling algorithm consumes that score. Do not require the
  numeric ceiling to equal a feature-disabled control. Test/generated/
  artifact penalties and project-scope mismatch behavior remain
  effective; a scope mismatch has no owner score part, reason, or trace
  adjustment.

  Add a multi-project fixture where the owner changes the existing
  cohort anchor and therefore changes non-owner penalties. Freeze that
  cascade as deterministic output under reversed candidate
  registration; do not add an owner-specific anchor rule. Add a
  frontend-cohort boundary fixture where the owner crosses the existing
  Top-10 scan boundary, and prove the existing Top-10, three-file, and
  50,000-byte-per-file caps plus the deterministic read set remain
  enforced.

- [x] **Step 2.5: duplicate declarations and determinism.** Two
  same-name owners both qualify. Reverse candidate insertion order and
  require byte-equal ordered chunk IDs, rerank scores, score parts, and
  reasons. Existing score/path tie-breakers decide their order. Include
  a manually constructed Python `SymbolRef` to prove the policy is
  retrieval-core behavior, not Java-specific.

- [x] **Step 2.6: run RED.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_retrieval_pipeline.py \
  -k 'exact_identifier or definition_owner'
```

  No production edit belongs in Task 2.

---

### Task 3: GREEN — Add the Bounded Owner Feature

**Files:** `src/context_search_tool/retrieval_core/ranking.py`.

- [x] **Step 3.1: add one score helper.** It accepts a chunk and
  `IdentifierIntent`, then:
  - returns immediately when `exact_identifier is None`;
  - finds an exact case-sensitive `symbol.name`;
  - requires `chunk.start_line <= symbol.start_line <= chunk.end_line`;
  - returns exactly `0.50` or `0.0`;
  - performs no store, source-file, parser, or graph access.

- [x] **Step 3.2: write the score part once.** Add
  `identifier_definition_owner_boost` in
  `_identifier_intent_score_parts`, passing the already-computed
  project-scope mismatch state into that helper. Write the boost only
  when the exact declaration witness is present and scope does not
  mismatch; otherwise omit the key. Make
  `_identifier_exact_match_score` evaluate the ordered unique union of
  `intent.identifiers` and `intent.exact_identifier`, local to ranking;
  do not mutate `IdentifierIntent.identifiers`. `_combined_score` must
  continue to ignore both identifier score parts, proving global
  normalized scores do not move.

- [x] **Step 3.3: add it only to soft reranking.** In `_rerank_score`,
  add the present part beside `identifier_exact_match_boost` before the
  existing second-pass ceiling. Leave the existing planner-ceiling,
  project-cohort, frontend-cohort, and final-selection algorithms
  unchanged. They consume the new normal rerank score, so their numeric
  results or in-cap membership may change for an eligible exact query.
  Do not add a parallel counterfactual score.

  Pin the resulting ceiling/cohort/frontend cascades in the focused
  tests from Task 2. Do not change `_evidence_class`,
  `_evidence_priority`, protected chunk IDs, rank tier, either sort key,
  or any existing work cap.

- [x] **Step 3.4: add the reason.** `_reasons` emits exactly
  `exact identifier definition owner` when the applied score part is
  positive. A scope-mismatched declaration has no owner boost, reason,
  or trace adjustment; add that negative test.

- [x] **Step 3.5: run GREEN and broad ranking regressions.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_identifier_intent.py \
  tests/test_retrieval_pipeline.py
```

- [x] **Step 3.6:** inspect every changed score part and result tuple.
  Optional authorized checkpoint:
  `feat: prefer exact identifier definition owners (P14 Task 3)`.

---

### Task 4: RED/GREEN — Preserve Expansion and Trace Semantics

**Files:** `tests/test_retrieval_pipeline.py`,
`tests/test_retrieval_trace_pipeline.py`,
`src/context_search_tool/retrieval_core/context_expansion.py`.

- [x] **Step 4.1: expansion RED.** Create overlapping chunks from the
  same file where the definition owner wins. Assert the expanded
  result's `rerank_score`, reason, and owner boost all come from that
  winner. Add the inverse fixture needed to prove a losing item's
  owner boost is not max-merged onto an unrelated winner.

- [x] **Step 4.2: trace RED.** Run a traced query through final
  selection. Assert:
  - schema version and stage sequence are unchanged;
  - rank history carries the normal final rerank score;
  - reasons contain `exact identifier definition owner`;
  - adjustments contain
    `identifier_definition_owner_boost == 0.50`;
  - a ceiling-clamped owner also reports the existing clamp adjustment;
  - no source content or absolute path enters the trace.

- [x] **Step 4.3: GREEN.** Add the new score-part name to the existing
  winner-scoped tuple in `_merge_expanded_result`. No other expansion,
  span, or trace code changes.

- [x] **Step 4.4: run focused suites.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py
```

- [x] **Step 4.5:** optional authorized checkpoint:
  `test: preserve P14 expansion and trace attribution (P14 Task 4)`.

---

### Task 5: Acceptance Checker, Boundaries, and Protected Regression

**Files:** `tests/test_retrieval_core_boundaries.py`,
`tests/test_exploration_boundaries.py`,
`tests/p14_definition_owner_acceptance.py`,
`tests/test_p14_definition_owner_acceptance.py`; existing protected
suites.

- [x] **Step 5.1: exact production overlays.** Add:

```python
P14_DEFINITION_OWNER_REVIEWED_PRODUCTION_CHANGES = {
    "src/context_search_tool/identifier_intent.py",
    "src/context_search_tool/retrieval_core/context_expansion.py",
    "src/context_search_tool/retrieval_core/ranking.py",
}
```

  OR it into each existing reviewed set and add an exact-set test.
  Preserve all entries committed at the declared baseline. Do not copy
  or recreate the coordination checkout's unrelated uncommitted
  overlay edits. If those edits land first, update the P14 baseline and
  documents before composing them.

- [x] **Step 5.2: revalidate the tracked acceptance checker.** Rerun the
  Task-0 harness tests after product edits and audit that capture modes
  still spawn the requested implementation while comparison modes
  remain JSON-only. Vector repeat comparison removes only timing and
  implementation fields. Hybrid repeat comparison freezes case status,
  required ranks, planner status, and fallback state while reporting
  raw planner text drift.

- [x] **Step 5.3: boundary and characterization gates.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_retrieval_core_boundaries.py \
  tests/test_exploration_boundaries.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_p14_definition_owner_acceptance.py
```

  Compare any output delta with Task 0's eligible-query inventory.
  The expected exact camel/Pascal inventory may include
  `WorkspaceServiceImpl`; if it has the applicable baseline owner
  witness, add only its predeclared P14 overlay. Do not overwrite the
  immutable base hashes or P9 pins. Any non-eligible drift is a STOP.

- [x] **Step 5.4: protected P2/P3/P4/P5/P7 gates.** Run the concrete
  protected module group:

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_context_pack.py \
  tests/test_quality_p2.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_quality_p3.py \
  tests/test_exploration_contracts.py \
  tests/test_exploration_fusion.py \
  tests/test_exploration_goals.py \
  tests/test_exploration_inputs.py \
  tests/test_exploration_options.py \
  tests/test_exploration_probes.py \
  tests/test_exploration_runner.py \
  tests/test_exploration_trace.py \
  tests/test_quality_p4.py \
  tests/test_p5_graph_contract.py \
  tests/test_frontend_graph.py \
  tests/test_java_ast.py \
  tests/test_chunker_java_plugin.py \
  tests/test_mybatis_xml.py \
  tests/test_test_association.py \
  tests/test_resolved_graph_expansion.py \
  tests/test_quality_p5.py \
  tests/test_exploration_p7.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_formatters.py
```

  Then run the deterministic P2, P4, P5, and raw-CI profiles:

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output "$P14_RUN_ROOT/p2-context-pack.json"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p4_exploration.json \
  --profile p4_exploration \
  --output "$P14_RUN_ROOT/p4-exploration.json"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p5_language_graphs.json \
  --profile p5_language_graphs \
  --output "$P14_RUN_ROOT/p5-language-graphs.json"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output "$P14_RUN_ROOT/ci.json" \
  --markdown "$P14_RUN_ROOT/ci.md"
```

  Require P2 `5/5`, P4 `4/4`, P5 `12/12`, and raw CI `8/8`.
  All pass counts, catalog hashes, schema hashes, protected-direct
  winners, and no-legal-edge projections must remain valid.

- [x] **Step 5.5: explicit P6 protection.** Run the established six-file
  group while the machine is otherwise idle:

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_p6_benchmark.py \
  tests/test_p6_case_registry.py \
  tests/test_p6_entry_publish.py \
  tests/test_p6_measurement_worker.py \
  tests/test_p6_operational_store.py \
  tests/test_p6_paired.py
```

  If a known P6 worker node fails only because the restricted macOS
  process denies `sysctl`, retain that output, rerun exactly the failing
  node IDs in an unrestricted process, then rerun the complete six-file
  group while idle. Any other or repeatable product failure is a STOP;
  do not change P6 policy.

- [x] **Step 5.6: full offline suite.**

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  -m "not slow and not integration"
```

  Apply the same recorded P6-only `sysctl` exception. Any product
  failure is a STOP.

- [x] **Step 5.7: scope audit.** Require exactly the planned production
  paths and planned tests/docs. Optional authorized checkpoint:
  `test: protect P14 exact-identifier boundary (P14 Task 5)`.

---

### Task 6: Real-Project A/B and P1 Closure

Run this task only with the required real services and frozen source
copies. Absence is `BLOCKED`; it does not invalidate completed offline
work.

- [x] **Step 6.1: restore and revalidate evidence.** At design time,
  `$P14_COORD_ROOT/.quality/p8-baseline-root.txt` points to the deleted
  `/private/tmp/cst-p8-baseline.HWrpIy`; real-corpus capture is therefore
  currently `BLOCKED`. Do not guess a replacement or reuse an
  unvalidated checkout.

  After explicit network authorization, restore RedInk and
  `daily_stock_analysis` under the durable
  `$P14_COORD_ROOT/.quality/p14-sources/` root using:

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_SOURCE_ROOT="$P14_COORD_ROOT/.quality/p14-sources"
P14_SOURCE_POINTER="$P14_COORD_ROOT/.quality/p14-sources-root.txt"
REDINK_ROOT="$P14_SOURCE_ROOT/RedInk"
DAILY_ROOT="$P14_SOURCE_ROOT/daily_stock_analysis"

mkdir -p "$P14_SOURCE_ROOT"
if [ ! -e "$REDINK_ROOT" ]; then
  git clone https://github.com/HisMax/RedInk.git "$REDINK_ROOT"
  git -C "$REDINK_ROOT" checkout --detach \
    4d48722344594cf00e0498f0e1ed3df9cd4fd6be
fi
if [ ! -e "$DAILY_ROOT" ]; then
  git clone https://github.com/ZhuLinsen/daily_stock_analysis.git "$DAILY_ROOT"
  git -C "$DAILY_ROOT" checkout --detach \
    487e49e565ffd1b96a7cf4d855f99cee3c981eaa
fi

test "$(git -C "$REDINK_ROOT" rev-parse HEAD)" = \
  4d48722344594cf00e0498f0e1ed3df9cd4fd6be
test "$(git -C "$DAILY_ROOT" rev-parse HEAD)" = \
  487e49e565ffd1b96a7cf4d855f99cee3c981eaa

env P14_SOURCE_ROOT="$P14_SOURCE_ROOT" \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/tests" \
  "$P14_PYTHON" - <<'PY'
import os
from pathlib import Path

from p8_python_graph_identity import (
    DAILY_CONTENT_SHA256,
    DAILY_INCLUDE,
    DAILY_INVENTORY_SHA256,
    DAILY_SELECTED_COUNT,
    REDINK_CONTENT_SHA256,
    REDINK_INCLUDE,
    REDINK_INVENTORY_SHA256,
    REDINK_SELECTED_COUNT,
    validate_protected_source,
)

root = Path(os.environ["P14_SOURCE_ROOT"])
validate_protected_source(
    root / "RedInk",
    patterns=REDINK_INCLUDE,
    expected_count=REDINK_SELECTED_COUNT,
    expected_inventory_sha256=REDINK_INVENTORY_SHA256,
    expected_content_sha256=REDINK_CONTENT_SHA256,
)
validate_protected_source(
    root / "daily_stock_analysis",
    patterns=DAILY_INCLUDE,
    expected_count=DAILY_SELECTED_COUNT,
    expected_inventory_sha256=DAILY_INVENTORY_SHA256,
    expected_content_sha256=DAILY_CONTENT_SHA256,
)
PY

if [ -e "$P14_SOURCE_POINTER" ]; then
  test "$(cat "$P14_SOURCE_POINTER")" = "$P14_SOURCE_ROOT"
else
  (set -o noclobber; printf '%s\n' "$P14_SOURCE_ROOT" > "$P14_SOURCE_POINTER")
fi
```

  This is the exact P9 source-preparation identity flow, anchored by:

  - RedInk commit
    `4d48722344594cf00e0498f0e1ed3df9cd4fd6be`;
  - daily commit
    `487e49e565ffd1b96a7cf4d855f99cee3c981eaa`;
  - the committed include patterns, selected counts `28` and `203`, and
    both inventory/content SHA-256 pairs from
    `tests/p8_python_graph_identity.py`.

  The historical stale P8 pointer is not overwritten. Only after both
  validations pass may P14 write its new pointer. If an existing target
  is not already the exact commit and content, the commands fail closed
  rather than changing it. If the sources cannot be restored exactly,
  keep Task 6 `BLOCKED`; never re-pin. Then recheck catalog/gold hashes,
  the SiliconFlow base URL, `BAAI/bge-m3` dimensions, planner model, and
  successful non-fallback online smokes. No clone or external
  publication without permission; Ollama is out of scope.

- [ ] **Step 6.2: paired real-corpus captures.** From one host session,
  run two separate-process captures for each isolated baseline and P14
  candidate under `hash`, then do the same under frozen SiliconFlow
  online embedding, alternating baseline/candidate order. The commands
  below are the first hash pair; repeat with `-r2` output names, then
  repeat all four commands with `online`:

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")
BASELINE_TREE=$(cat "$P14_COORD_ROOT/.quality/p14-online-baseline-tree.txt")
P8_SOURCES=$(cat "$P14_COORD_ROOT/.quality/p14-sources-root.txt")
P14_P8_ATTEMPT_ID=p8-initial
P14_P8_ATTEMPT_ROOT="$P14_RUN_ROOT/$P14_P8_ATTEMPT_ID"
mkdir -p "$P14_P8_ATTEMPT_ROOT"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py capture-p8 \
  --attempt-id "$P14_P8_ATTEMPT_ID" \
  --side baseline \
  --repeat 1 \
  --implementation-root "$BASELINE_TREE" \
  --sources "$P8_SOURCES" \
  --embedding hash \
  --timing-reps 3 \
  --output "$P14_P8_ATTEMPT_ROOT/hash-baseline-r1.json"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py capture-p8 \
  --attempt-id "$P14_P8_ATTEMPT_ID" \
  --side candidate \
  --repeat 1 \
  --implementation-root "$PWD" \
  --sources "$P8_SOURCES" \
  --embedding hash \
  --timing-reps 3 \
  --output "$P14_P8_ATTEMPT_ROOT/hash-candidate-r1.json"
```

  Warm/provider ordering must be symmetric. Assert module origins and
  implementation dirty state in every P14 capture envelope. The wrapper
  must fail if a baseline child resolves a module under the candidate
  tree or vice versa. Keep all raw captures immutable. For repeat 2,
  change both `--repeat` and the `-r2` output names. The online commands
  use the same attempt ID/root and `--embedding online`. Every online
  envelope must identify `openai-compatible`, `BAAI/bge-m3`, 1024
  dimensions, and `https://api.siliconflow.cn/v1`.

- [ ] **Step 6.3: evaluate the P14 subset gates.** Run the tracked P14
  checker over the four P8 baseline/candidate pairs. P14 does not
  require P8/P9's credited-gain gates. Write
  `real-corpus-gates.json` with:
  - Recall@12 candidate >= baseline per provider;
  - zero required losses per provider;
  - noise ratio candidate <= baseline per provider;
  - protected winners stable;
  - non-eligible cases preserve canonical non-timing ranking output,
    including membership, order, score, score parts, and reasons;
  - same-side capture determinism;
  - identical embedding request counts, static/descriptor embedding
    identities, selected-file counts, and structural counts;
  - baseline query-p95 max/min spread <= `0.15` per provider;
  - candidate/baseline median query p95 <= `1.10`.

  Record all numerators, denominators, ratios, and case-level deltas.
  Non-timing same-side drift is a `STOP` for diagnosis and is not
  retried. One complete paired rerun is allowed only when the baseline
  timing-stability gate fails; a second unstable baseline is `BLOCKED`,
  never a wider threshold. That rerun uses attempt ID `p8-retry-1`, a
  new `$P14_RUN_ROOT/p8-retry-1/` directory, and all eight fresh
  captures. The existing capture has no vector/manifest artifact
  digest, so P14 makes no unobservable byte-identity claim. Do not edit
  the runner's general P8/P9 ship gates.

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")
P14_P8_ATTEMPT_ID=p8-initial
P14_P8_ATTEMPT_ROOT="$P14_RUN_ROOT/$P14_P8_ATTEMPT_ID"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py compare-p8 \
  --attempt-id "$P14_P8_ATTEMPT_ID" \
  --eligible-inventory "$P14_RUN_ROOT/eligible-queries.json" \
  --hash-baseline-r1 "$P14_P8_ATTEMPT_ROOT/hash-baseline-r1.json" \
  --hash-baseline-r2 "$P14_P8_ATTEMPT_ROOT/hash-baseline-r2.json" \
  --hash-candidate-r1 "$P14_P8_ATTEMPT_ROOT/hash-candidate-r1.json" \
  --hash-candidate-r2 "$P14_P8_ATTEMPT_ROOT/hash-candidate-r2.json" \
  --online-baseline-r1 "$P14_P8_ATTEMPT_ROOT/online-baseline-r1.json" \
  --online-baseline-r2 "$P14_P8_ATTEMPT_ROOT/online-baseline-r2.json" \
  --online-candidate-r1 "$P14_P8_ATTEMPT_ROOT/online-candidate-r1.json" \
  --online-candidate-r2 "$P14_P8_ATTEMPT_ROOT/online-candidate-r2.json" \
  --output "$P14_P8_ATTEMPT_ROOT/real-corpus-gates.json"
```

- [x] **Step 6.4: close baseline, then capture candidate P1.** If Task 0
  was live `BLOCKED` but services are now available, first run all four
  Task-0.7 baseline captures and apply their `6/7`, Top-12, rank, and
  repeatability diagnostic gates.

  If Task 0 instead ended with unstable hybrid baseline gate inputs,
  consume the one global P1 retry now: rerun all four baseline captures
  under attempt ID/root `p1-retry-1`, and require that baseline to pass
  before proceeding. A second baseline instability is `BLOCKED`; do not
  capture an initial candidate or wait until comparison to trigger this
  retry.

  The candidate commands below are forbidden until the baseline for the
  active attempt passes. Use `p1-initial` when its baseline passed;
  otherwise use the already-stable `p1-retry-1`. Then run each candidate
  capture twice with distinct `-r1`/`-r2` output names:

```bash
set -euo pipefail

P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")
# Use p1-retry-1 here only when the pending-baseline branch above consumed it.
P14_P1_ATTEMPT_ID=p1-initial
P14_P1_ATTEMPT_ROOT="$P14_RUN_ROOT/$P14_P1_ATTEMPT_ID"
mkdir -p "$P14_P1_ATTEMPT_ROOT"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py capture-p1 \
  --attempt-id "$P14_P1_ATTEMPT_ID" \
  --side candidate \
  --repeat 1 \
  --implementation-root "$PWD" \
  --catalog tests/fixtures/retrieval_quality/queries.json \
  --profile p1_vector_bge \
  --output "$P14_P1_ATTEMPT_ROOT/vector-candidate-r1.json" \
  --markdown "$P14_P1_ATTEMPT_ROOT/vector-candidate-r1.md"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py capture-p1 \
  --attempt-id "$P14_P1_ATTEMPT_ID" \
  --side candidate \
  --repeat 1 \
  --implementation-root "$PWD" \
  --catalog tests/fixtures/retrieval_quality/queries.json \
  --profile p1_hybrid_bge \
  --output "$P14_P1_ATTEMPT_ROOT/hybrid-candidate-r1.json" \
  --markdown "$P14_P1_ATTEMPT_ROOT/hybrid-candidate-r1.md"

env CST_RUN_P1_ACCEPTANCE=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  "$P14_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_quality_p1.py -m integration
```

  Repeat the two capture commands with `--repeat 2` and `-r2` paths
  under the same attempt root. The focused pytest command runs once
  after both repeats.

  `p1-retry-1` consumed the one global retry. Vector reproduced `6/7`
  twice with owner rank 5. Hybrid produced `2/7` and `3/7`, with five
  and four online planner fallbacks respectively. The second hybrid
  baseline was unstable, so P1 is `BLOCKED` and candidate capture is
  forbidden. No Ollama fallback was used.

- [ ] **Step 6.5: run the tracked P1 comparison and focused gate.**
  Compare the four baseline and four candidate captures from the same
  active attempt. Vector non-timing gate-input drift is a `STOP` for
  diagnosis. If `p1-initial` was active and hybrid gate inputs are
  unstable, retain every initial artifact and consume the one global
  retry: use attempt ID `p1-retry-1`, a new
  `$P14_RUN_ROOT/p1-retry-1/` directory, and all eight fresh captures.
  Compare that complete attempt, never selected runs from different
  attempts. If `p1-retry-1` was already active because its baseline
  consumed the retry, any further instability is immediately
  `BLOCKED`. Raw hybrid planner text may differ but is disclosed; case
  status, required ranks, planner status, fallback state, and every
  other gate input named by the harness contract must be stable.

```bash
P14_COORD_ROOT=/Users/flobby/vibe_coding/context-search-tool
P14_PYTHON="$P14_COORD_ROOT/.quality/p5-runtime/bin/python"
P14_RUN_ROOT=$(cat "$P14_COORD_ROOT/.quality/p14-online-run-root.txt")
BASELINE_TREE=$(cat "$P14_COORD_ROOT/.quality/p14-online-baseline-tree.txt")
# Match the active attempt selected and captured in Step 6.4.
P14_P1_ATTEMPT_ID=p1-initial
P14_P1_ATTEMPT_ROOT="$P14_RUN_ROOT/$P14_P1_ATTEMPT_ID"

env PYTHONDONTWRITEBYTECODE=1 \
  "$P14_PYTHON" -P tests/p14_definition_owner_acceptance.py compare-p1 \
  --attempt-id "$P14_P1_ATTEMPT_ID" \
  --catalog "$BASELINE_TREE/tests/fixtures/retrieval_quality/queries.json" \
  --vector-baseline-r1 "$P14_P1_ATTEMPT_ROOT/vector-baseline-r1.json" \
  --vector-baseline-r2 "$P14_P1_ATTEMPT_ROOT/vector-baseline-r2.json" \
  --vector-candidate-r1 "$P14_P1_ATTEMPT_ROOT/vector-candidate-r1.json" \
  --vector-candidate-r2 "$P14_P1_ATTEMPT_ROOT/vector-candidate-r2.json" \
  --hybrid-baseline-r1 "$P14_P1_ATTEMPT_ROOT/hybrid-baseline-r1.json" \
  --hybrid-baseline-r2 "$P14_P1_ATTEMPT_ROOT/hybrid-baseline-r2.json" \
  --hybrid-candidate-r1 "$P14_P1_ATTEMPT_ROOT/hybrid-candidate-r1.json" \
  --hybrid-candidate-r2 "$P14_P1_ATTEMPT_ROOT/hybrid-candidate-r2.json" \
  --output "$P14_P1_ATTEMPT_ROOT/p1-gates.json"
```

- [ ] **Step 6.6: apply P1 gates verbatim.**
  - 7 selected and executed required cases per profile;
  - no error, skip, or embedding fallback;
  - both profiles `7/7`;
  - `AuditStatus.java` rank <= 3 in both;
  - all other cases retain pass status;
  - mixed `/apply/audit/pageEs INVOLVED_BY_ME` keeps its existing
    controller/endpoint gate;
  - unchanged `tests/test_quality_p1.py` focused pair gate passes,
    including hybrid aggregate metrics not below vector;
  - Top-1 rank is recorded but is not a gate.

- [x] **Step 6.7: record a provisional gate outcome.** Choose exactly
  one:
  - `ship`;
  - `reject`;
  - `blocked`.

  `ship` requires every offline, real-corpus, and P1 gate. A required
  loss, non-eligible behavior delta, noise increase, performance
  failure, or P1 result below `7/7` is `reject`. Missing live
  dependencies is `blocked`. This outcome is provisional until Task 7
  independent review and all affected reruns finish. Do not tune the
  grammar, eligibility, fixed `0.50`, or thresholds after this point.

  Provisional outcome: `blocked`. P1 exhausted its retry on unstable
  SiliconFlow planner fallbacks. The initial online real-corpus attempt
  is also incomplete because candidate embedding capture received a
  provider `TPM limit reached` response after the first online baseline
  had completed. Offline implementation and review remain runnable.

---

### Task 7: Independent Review and Evidence-Backed Documentation

- [x] **Step 7.1: independent review.** Run parallel Standards and Spec
  reviews against the isolated baseline:
  - Standards: exact production scope, repository conventions,
    determinism, trace/merge consistency, no hidden I/O.
  - Spec: every frozen grammar/eligibility/promotion/gate invariant and
    every negative case.

  Resolve all blocking findings with tests, then rerun affected gates.

- [x] **Step 7.2: final evidence run, then disposition.** After every
  blocking review finding is resolved, rerun the exact focused,
  protected, and full-offline commands recorded in this plan. For live
  gates, reuse the Task-6 command templates with the final attempt IDs
  below; do not reuse their literal `*-initial` assignments. Never
  overwrite Task-6 evidence:
  - write deterministic quality reports under a new
    `$P14_RUN_ROOT/final/` directory;
  - recapture all eight real-corpus inputs under attempt ID `p8-final`
    and `$P14_RUN_ROOT/p8-final/`;
  - capture all four P1 baseline inputs before all four candidate inputs
    under attempt ID `p1-final` and `$P14_RUN_ROOT/p1-final/`; and
  - run each compare command only against the eight files from its one
    final attempt.

  Apply the frozen retry rules before evaluating the result. Each gate
  family has its own one-retry allowance: one P8 timing retry and one P1
  hybrid retry. Each counter is global across Tasks 6 and 7 and is not
  reset for the final attempt; if that family's retry was already used,
  another instability is `BLOCKED`. If a required live dependency is
  unavailable, record those live gates as `not_run` and the disposition
  as `blocked`; do not pretend to rerun them.

  Only after every runnable final gate is closed may the implementation
  freeze exactly one `ship`, `reject`, or `blocked` disposition using
  the Task-6 rules. A review fix never permits a weight, grammar, gold,
  or threshold change after candidate evaluation.

- [x] **Step 7.3: implementation record.** Append to this plan:
  - entry SHA and dirty-state audit;
  - changed file list and optional commits;
  - exact grammar and eligible-query inventory SHA;
  - focused/protected/full suite accounting;
  - baseline/candidate P1 ranks and all seven case statuses;
  - hash/online real-corpus gate arithmetic;
  - performance and request-count arithmetic;
  - review findings/resolutions;
  - immutable evidence paths and SHA-256 values;
  - final disposition.

- [x] **Step 7.4: conditional docs.** Only for `ship`:
  - update README with exact whole-query behavior and its exclusions;
  - update `docs/retrieval-quality.md` with fresh P1 evidence;
  - close the independent P1 roadmap item.

  For `blocked`, document only completed offline work and every unrun
  live field as `not_run`. For `reject`, record the measured failure and
  leave user-facing behavior/roadmap unchanged.

- [x] **Step 7.5: final audit.**

```bash
set -euo pipefail

git diff --check
git status --short --untracked-files=all
git ls-files --others --exclude-standard
```

  This audit creates no new product evidence after the disposition is
  frozen. Commit/push only if separately authorized.

## Stop Conditions

- Implementation is not isolated from the current unrelated dirty work.
- Fresh baseline does not reproduce the ranking boundary: the target is
  already Top-3 or is absent from Top-12 in either P1 profile.
- Any production file outside the three reviewed paths is required.
- Any new recall source, store-query/file-read primitive, network or
  provider behavior, schema, downstream algorithm, or work cap appears.
  Different in-cap frontend/context-expansion read membership caused by
  an eligible exact-query order change is allowed.
- A non-exact or non-eligible query changes order, score parts, or
  selected membership.
- A path/content occurrence without a matching case-sensitive
  declaration-start `SymbolRef` receives the owner boost.
- A long-range symbol boosts a chunk that does not contain its
  declaration start.
- The owner feature changes evidence class, evidence priority,
  protected-direct status, global normalization, or any existing
  planner-ceiling/project-cohort/frontend-cohort algorithm or work cap.
- Candidate registration order affects the result.
- Expansion or trace attributes a losing item's owner boost to a winner.
- Any protected quality, trace, ContextPack, exploration, graph,
  selection, or boundary contract fails.
- Any real-corpus required loss, recall decrease, noise increase,
  protected-winner change, or query-p95 ratio above `1.10`.
- Either P1 profile is not a fresh, fully executed `7/7`, or
  `AuditStatus.java` remains below Top-3.
- Any grammar, `0.50` value, gate, threshold, catalog, or gold change
  after candidate evaluation.

## Implementation Record

Status: `blocked` on 2026-07-31.

Entry and scope:

- Behavior baseline:
  `501cf852ad54181eb823994747d2dc8555edc418`, captured from a clean
  detached online-baseline worktree.
- Pre-record candidate checkpoint:
  `91f7b8290e98ff2577dad2dff83f6020aa9ab2c1`, clean in
  `.quality/p14-verifiers/20260731T043828Z-p14-final-v2/candidate/`
  `context-search-tool`.
- The candidate changes exactly three production files:
  `identifier_intent.py`, `retrieval_core/ranking.py`, and
  `retrieval_core/context_expansion.py`.
- The complete 16-file change set is those three production files, the
  plan and design documents, the P14 harness and harness tests, and the
  nine planned regression/boundary files:
  `test_identifier_intent.py`, `test_retrieval_pipeline.py`,
  `test_retrieval_trace_pipeline.py`, `test_retrieval_core_boundaries.py`,
  `test_exploration_boundaries.py`,
  `test_retrieval_core_characterization.py`, `test_quality_p5.py`,
  `test_p5_protected_direct.py`, and `test_p6_benchmark.py`.

Frozen grammar and inventory:

- Exactness uses `fullmatch(query.strip())` against the frozen
  camel/Pascal, lower-snake, or
  `[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+` SCREAMING_SNAKE grammar. No wrapper,
  punctuation stripping, or prose parsing was added.
- `eligible-queries.json` SHA-256 is
  `b23fe482a4233a294e76317928daebd0b34ea515b543702e918af977e5103ff4`.
  Its four eligible source keys are
  `workspace-service-symbol` (characterization and quality),
  `owner-controller-exact`, and `audit-status-literal`; the P8 eligible
  case list is empty.

Final offline evidence:

- Focused identifier/ranking/trace: `365 passed`.
- Boundary/characterization/harness: `116 passed`.
- Protected P2/P3/P4/P5/P7 group: `709 passed, 5 skipped`.
- P6 six-file clean-tree group: `103 passed`.
- Full `not slow and not integration` suite:
  `3390 passed, 5 skipped, 6 deselected` in `124.89s`.
- Deterministic quality reports: P2 `5/5`, P4 `4/4`, P5 `12/12`, and
  raw CI `8/8`. Their JSON SHA-256 values are respectively
  `2f545a9ff4f44d829cf5e6ac45490e60d4e657a91b59714064b7928f647e2772`,
  `a7b1d1eedff87599b54e5f7e715462542805d65449a03f710a37fdda882e35d5`,
  `d23a4c67178098a4e55bf260eba63ba1dabc2985ca258ca94482966ab4c3f703`,
  and
  `7905f1261caba3c2250c6ae7d267111e7c4e08da8a08b656e00186939c5b3362`.

Live evidence and arithmetic:

- P8 hash baseline/candidate repeats completed offline with zero
  embedding requests. The online baseline used
  `openai-compatible/BAAI/bge-m3`, 1024 dimensions, and
  `https://api.siliconflow.cn/v1`; it made 23 RedInk plus 43 daily
  requests (`66` total) with query p95 `1.02580825s`.
- P8 online candidate capture produced no output after two provider
  `HTTP 429: TPM limit reached` responses. Therefore `p8-initial` was
  incomplete, comparison was not run, and every `p8-final` input,
  comparison, candidate timing ratio, recall/noise result, and request
  count is `not_run`.
- Initial P1 vector repeats were both `6/7`, owner rank `5`, with no
  fallback. Initial hybrid repeats were `4/7` at owner rank `5` and
  `2/7` at owner rank `6`, with unstable online-planner fallbacks.
- The globally allowed `p1-retry-1` vector repeats were again identical
  `6/7`, owner rank `5`: apply-audit, dashboard-cross-language,
  dashboard-controller-path, access-validation, blacklist-management,
  and order-service passed; audit-status failed.
- Retry hybrid repeat 1 was `2/7`, owner rank `5`: only
  dashboard-controller-path and order-service passed; the other five
  cases fell back and failed. Repeat 2 was `3/7`, owner rank `5`:
  apply-audit, dashboard-controller-path, and order-service passed;
  audit-status, dashboard-cross-language, access-validation, and
  blacklist-management fell back and failed.
- The second hybrid baseline instability consumed the P1 retry and set
  `candidate_capture_allowed=false`. Thus all seven candidate case
  statuses/ranks, all `p1-final` inputs and comparison outputs, and all
  candidate P1 performance/request fields are `not_run`.

Review:

- Parallel Standards and Spec reviews ran against `501cf852`. Standards
  findings were resolved by removing the trace middleman, naming
  reversed candidate order accurately, and reusing the ranking fixture
  helper.
- Spec fixes removed the forbidden owner-specific cohort-anchor rule,
  made eligible cohort deltas informational instead of rejecting,
  removed unrelated checkout-root normalization, and added direct
  `apply_dev` lower-snake owner proof.
- Both reviewers rechecked the fixes and reported no remaining
  blocker/high/medium finding.

Immutable evidence:

- Run root:
  `.quality/p14-runs/20260731T032623Z-online-task0`.
- Final offline reports:
  `.quality/p14-runs/20260731T032623Z-online-task0/final/`.
- Final verifier:
  `.quality/p14-verifiers/20260731T043828Z-p14-final-v2`.
- Source validation and infrastructure SHA-256 values are
  `7b45b85219eeb081786b65e65fe0351a4e15053895b3e2de2c8aa4975b47ac6d`
  and
  `cef9ebb9579e5d14a1cfed908a7751d3be18bd04dd089342c42610be28923591`.
- `p1-initial/baseline-status.json`,
  `p1-retry-1/baseline-status.json`, and `p8-initial/status.json`
  SHA-256 values are respectively
  `8c515d5fa54a3ee9bc2b083abb244e40da47f0eb5fdb6a63021b520fcdfa3bd9`,
  `46b4eb00ba21dc56ab5db62033540c7e700c6053e181c2f608e0736ff89af6ca`,
  and
  `f0629dde6bb2cca72d3a914500e78cbfda846b63bea5505a0bf4a9ffaa1c58f7`.

Final disposition: `blocked`. Offline implementation and all runnable
review gates pass, but the required fresh online P8 and P1 candidate
comparisons are unavailable after the frozen retry rules were exhausted.
No README, retrieval-quality, or roadmap behavior claim was changed.
