# P7A Retrieval Quality Attribution And Route Selection Implementation Plan

Date: 2026-07-25
Status: Reviewed detailed plan; implementation is not authorized
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Design: `docs/superpowers/specs/2026-07-25-p7a-retrieval-quality-attribution-route-selection-design.md`
Preserved prior plan: `docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md`
Behavior baseline: `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`
Authorization: planning and review only

## Outcome

Implement P7A as a diagnostic phase with one hard terminal:

```text
target-bearing public benchmark
  -> simultaneous feasible-cover proof
  -> behavior-neutral stage observer
  -> reproducible actual baseline
  -> file/span/pack upper-bound diagnostics
  -> reviewed route decision
  -> stop
```

This plan deliberately contains no exact injection, file projection,
result-path deduplication, score change, wider context boundary, pack
reservation, trace migration, parser, reranker, or controller work.

The route decision chooses the subject of a later P7B/P8 design. It does not
authorize that implementation.

## Plan-Time Evidence

The plan author reproduced the clean baseline on 2026-07-25:

```text
runtime: Python 3.13.12
SQLite: 3.51.2
command:
  PYTHONDONTWRITEBYTECODE=1
  PYTHONPATH="$PWD/src"
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider
result: 2896 passed, 9 skipped, 0 failed, 0 errors, 0 xfailed
warnings: 16
duration: 54.58 seconds
tracked diff after run: empty
```

Task 0 must reproduce this from the reviewed-document entry commit. Exact skip
IDs, source tree, dependencies, optional-environment presence, and prepared
profile identities matter; a matching count alone is insufficient.

## Source Of Truth

The reviewed design is normative:

`docs/superpowers/specs/2026-07-25-p7a-retrieval-quality-attribution-route-selection-design.md`

If this plan disagrees with the design:

1. stop;
2. amend both documents;
3. recompute fixed payload hashes; and
4. repeat all three independent reviews.

Do not silently implement whichever interpretation is easier.

## Execution Constraints

1. This document does not authorize implementation, branch creation, staging,
   commit, repository download, gold authoring, or benchmark execution.
2. After user approval, create one documentation-only entry commit whose parent
   is exactly `74aae0abe3dff685282fbcc785f7a9b3532cbbe6` and whose subject is
   `docs: preserve p7 and add reviewed p7a design`. Its only files are the
   byte-restored P7 spec/plan and the reviewed P7A spec/plan.
3. If any source, test, fixture, dependency, or roadmap change intervenes before
   that entry commit, stop and rebaseline the documents.
4. P7A changes no public product schema or retrieval behavior. RetrievalTrace
   remains v1; QueryBundle, ContextPack v2, and ExplorationTrace v2 stay exact.
5. Audit-disabled execution performs no extra store, source, graph, embedding,
   planner, network, exploration, or pack operation.
6. Gold is authored from pinned source and task meaning before the controlled
   baseline run. Baseline output, oracle output, fast-context, and private data
   cannot influence labels, cases, variants, quotas, or thresholds.
7. The product worker receives no gold, target, variant, gate, profile, route,
   or threshold metadata.
8. The worker/evaluator split is not claimed as an adversarial OS sandbox. P7A
   contains no post-gold candidate implementation and evaluates trusted code.
9. Only `required` and `known_gap` cases vote. `informational` cases never enter
   route denominators or support counts.
10. File/span/pack oracles are label-assisted upper bounds. They never cast
    route votes and never authorize a production mechanism.
11. Route claims are benchmark-scoped and use the `benchmark_` prefix.
12. Private repositories and fast-context are outside P7A acceptance.
13. Every code task starts with a focused ordinary assertion failure and ends
    with focused tests, protected tests, diff checks, and exact staged-name
    review.
14. Every task's `Files` section is its complete tracked commit boundary.
    Directory entries ending in `/**` are closed subtrees: staged descendants
    must equal the task's frozen file manifest. No other directory entry is a
    wildcard.
15. Generated copies, worktrees, raw reports, TDD logs, review inputs, and
    receipts live under the named ignored `.quality/p7a-*` roots.
16. Never use `git add -A`; stage exact paths only.
17. P7A ends after the route artifact/documentation commit. Do not begin the
    selected P7B/P8 mechanism in the same branch or plan.
18. P7A does not edit `quality/cases.py` or `quality/__init__.py`. Its case
    parser is independent; its product worker/observer import no `quality`
    package.
19. Every declared complete variant has a reviewed simultaneous
    `FeasibleCoverWitness` before controlled output exists.
20. The exact evaluator path-to-Git-blob/import closure is frozen before the
    first controlled role run.
21. Six-role quality equality uses the existing deterministic `clock_ns` seam
    and removes no timing fields. Real latency uses the unchanged P6 paired
    harness.
22. Reported ranges never prove terminal coverage; only target-independent
    logical-line commitments matched against pinned Git blobs may do so.
23. Four strict TDD checkpoints and all contiguous fixes are frozen in one
    manifest before attempt allocation.
24. Every abandoned or invalidated attempt has one immutable disposition;
    only four externally evidenced reasons authorize a same-byte retry.

## Definition Of Done

P7A is complete only when:

- the reviewed entry and behavior baseline are reproduced cleanly;
- case selection provenance, profile, sources, gold, coherent variants, exact
  identifier matches, and feasible-cover witnesses are frozen before
  controlled baseline output exists;
- the profile has the required cross-source, intent, surface, language, and
  confirmatory coverage;
- the observer is source-free, bounded, ContextVar-scoped, non-nestable, reset
  on every exit, stdlib-only, and import-isolated from `quality`;
- audit-disabled behavior and work are identical to the behavior baseline;
- audit-enabled and audit-disabled transient canonical public bytes (proved by
  hash/length plus source-free content-commitment projection) and work are
  identical on the instrumentation tree;
- the full public profile and audit leaves repeat exactly on clean prepared
  copies;
- every `(complete variant, decision-eligible required unit)` has one
  diagnostic terminal reason through the correct surface DAG, with a separate
  per-unit vote group;
- every terminal target/literal coverage claim is reproduced from exact
  full-line commitments, including line-internal crop cases;
- every stage/rank/result/reason metric uses its closed stable analysis atom,
  applicability, null, aggregation, and strata rule and is invariant to
  semantic-choice-preserving variant recombination;
- variant ties cannot use IDs, array order, or path lexicography to cast a
  reason vote;
- file/span/pack oracles obey actual population/budget bounds, complete-variant
  aggregation, exact reason-group mapping, and stage-local recovery; an
  upstream oracle never assumes downstream success;
- route dominance has two independent external sources plus matching
  confirmatory-only direction/threshold support, or the result is mixed/no-gap;
- the immutable baseline attempt, non-retry disposition ledger, and frozen
  four-checkpoint TDD manifest prevent cherry-picking, with every required
  disposition proposed by a semantic-delta-validated successor proof and
  consumed once by the locked reservation transaction;
- the evaluator closure predates all controlled roles;
- full suite, protected profiles, unchanged P6 paired median/RSS, exact context
  byte/work, lifecycle, and privacy gates pass;
- three agents review the same implementation/evidence hashes with zero blocker
  and zero major findings;
- the five baseline/review artifacts are promoted by a reviewed recoverable
  create-only receipt, and the final staged tree exactly matches the reviewed
  manifest plus deterministic post-review projection;
- README, roadmap, benchmark README, and the implementation record link the
  route and state the unconditional stop.

## Task And Commit Sequence

| task | purpose | commit |
| ---: | --- | --- |
| 0 | reproduce entry baseline | none |
| 1 | freeze compatibility and artifact contracts | `test: lock p7a attribution contracts` |
| 2 | implement frozen case/finalizer/oracle/decision semantics | `feat: add p7a attribution evaluator` |
| 3 | author, review, and freeze public benchmark gold | `test: freeze p7a route benchmark` |
| 4 | add behavior-neutral product observation hooks | `feat: add p7a retrieval audit hooks` |
| 5 | add frozen worker, runner, attempts, and publisher | `feat: add p7a baseline evidence runner` |
| 6 | run/review baseline, publish route, update docs | `docs: publish p7a route decision` |

No product retrieval task follows Task 6.

## File Responsibility Map

| area | owner | focused tests |
| --- | --- | --- |
| strict artifact/case contracts | `quality/p7a_contracts.py` | `test_p7a_contracts.py`, `test_p7a_cases.py` |
| target/witness/finalizer/metrics/oracles/route | `quality/p7a_evaluator.py` | `test_p7a_gold.py`, `test_p7a_finalize.py`, `test_p7a_oracle.py`, `test_p7a_decision.py` |
| private audit collector and leaf protocol | `retrieval_core/audit_observer.py` | `test_p7a_audit.py` |
| existing-stage hook call sites | `retrieval.py`, `context_pack/builder.py`, `exploration/runner.py`, `exploration/fusion.py` | existing characterization tests plus `test_p7a_audit.py` |
| isolated product worker | `_p7a_worker.py` | `test_p7a_runner.py`, import-closure tests |
| evaluator runner | `quality/p7a_runner.py` | `test_p7a_runner.py` |
| attempt/retry/publication | `quality/p7a_lifecycle.py` | `test_p7a_attempts.py`, `test_p7a_publish.py` |
| fixed public benchmark | `tests/fixtures/p7a_retrieval_quality/**` | `test_p7a_profile.py`, `test_p7a_gold.py` |
| tracked evidence | `docs/benchmarks/p7a/**` | schema and publication tests |

## Normative Environment Wrapper

All default/full/protected gates use this wrapper. Do not invoke `$P7A_RUNTIME`
directly for those gates because inherited optional environment variables can
activate external profiles or change skip identity.

```bash
export P7A_REPO_ROOT="$(git rev-parse --show-toplevel)"
export P7A_PUBLICATION_WORKTREE="$P7A_REPO_ROOT"
export P7A_RUNTIME="$P7A_REPO_ROOT/.quality/p5-runtime/bin/python"
test "$P7A_REPO_ROOT" = "$(pwd -P)"
test "$P7A_PUBLICATION_WORKTREE" = "$P7A_REPO_ROOT"
test -x "$P7A_RUNTIME"

p7a_run_default() {
  run_root="$1"
  shift
  (
    cd "$run_root"
    env \
      -u CST_CALIBRATION_CONSOLE_IOT_REPO \
      -u CST_CALIBRATION_OPERATION_CLIENT_REPO \
      -u CST_MCP_LOG_FILE \
      -u CST_P2_REAL_CONTEXT_REPOS_DIR \
      -u CST_PLANNER_REQUESTS_REPO \
      -u CST_PRIVATE_MANIFEST_SENTINEL \
      -u CST_QUALITY_AB_REPO \
      -u CST_RUN_P1_ACCEPTANCE \
      -u CST_SAMPLE_REPO \
      -u CST_SMOKE_ENV_CHANGE_REPO \
      -u CST_SMOKE_EXTERNAL_REPO \
      -u CST_SMOKE_IMAGEBED_REPO \
      -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
      -u CST_SMOKE_PROGRAM_TOOL_REPO \
      -u CST_SMOKE_REPOS_DIR \
      -u CST_TEST_KEY \
      PYTHONDONTWRITEBYTECODE=1 \
      PYTHONPATH="$run_root/src:$run_root/tests" \
      "$P7A_RUNTIME" "$@"
  )
}
```

The controlled public runner does not inherit the caller environment. It builds
its own exact allowlist in `_p7a_worker.py`, records presence rather than values,
and rejects unknown `CST_*`, `PYTHON*`, proxy, credential, or model-provider
variables.

## TDD Evidence

Use the strict `tdd_record` branch of `p7a-artifacts-v1` with
`producer=p7a-tdd-v1`. It retains the compatible P6 identity fields but defines
its own closed key set, including nullable `supersedes_sha256`; the existing P6
schema and fixed `producer=p6-benchmark-v1` are not reused or edited. The
separate `tdd_manifest` branch uses `producer=p7a-tdd-manifest-v1`. P7A has four
code checkpoints:

| checkpoint | task | canonical RED selectors |
| ---: | ---: | --- |
| 1 | 1 | `tests/test_p7a_contracts.py` |
| 2 | 2 | `tests/test_p7a_cases.py tests/test_p7a_gold.py tests/test_p7a_profile.py tests/test_p7a_finalize.py tests/test_p7a_oracle.py tests/test_p7a_decision.py` |
| 3 | 4 | `tests/test_p7a_audit.py` |
| 4 | 5 | `tests/test_p7a_runner.py tests/test_p7a_attempts.py tests/test_p7a_publish.py` |

Checkpoint 2 owns `tests/test_p7a_profile.py` from its initial RED. At that
point the test exercises profile, quota, selection-provenance, and
gold-validation contracts against committed synthetic schema examples; it does
not read benchmark bytes that Task 3 has not authored. Task 3 later runs this
unchanged test plus the evaluator preflight against the concrete public
benchmark. Task 3 is therefore a governed data-freeze step, not a fifth code
checkpoint.

Checkpoint 1 bootstraps the producer that does not yet exist. First write the
complete checkpoint test file, including every contractual assertion planned
for Task 1. Before editing any production/schema path, create-exclusive raw
files under `.quality/p7a-tdd/checkpoint-1/bootstrap/`:

```text
pre-change-commit.txt
pre-change-tree.txt
pytest.semantic-argv
test-input-sha256.txt
red.log
red.junit.xml
red.exit.txt
red-failing-node-ids.txt
bootstrap-envelope.sha256
```

`pytest.semantic-argv` is the exact NUL-safe test-selection/behavior argument
vector for `tests/test_p7a_contracts.py`; it deliberately excludes
phase-local evidence sinks. RED expands it with the create-only
`red.log`/`red.junit.xml` destinations, while GREEN expands the byte-identical
semantic vector with distinct create-only `green.log`/`green.junit.xml`
destinations. No other argument may differ. The input manifest hashes every
selected test byte. The RED command runs through `p7a_run_default`, must exit
exactly `1`, must report ordinary assertion failures with successful
collection, and must leave production/schema paths byte-identical to the
recorded pre-change tree. The bootstrap envelope is the domain-separated
SHA-256 of the preceding create-only files. The entire bootstrap directory must
be absent before capture. Any existing file, import/syntax/fixture/environment
error, unexpected pass, or product diff stops the task.

After Task 1 implementation is staged, the new producer executes:

```text
p7a-tdd-bootstrap
  --checkpoint 1
  --bootstrap <create-only bootstrap directory>
  --staged-tree <git write-tree>
  --output <create-only tdd-checkpoint-1.json>
```

It verifies the raw envelope, materializes the exact `git write-tree` object in
a fresh sterile temporary directory, verifies its own loaded blob and every
selected production/test/schema/fixture blob against that materialization,
runs the byte-identical semantic argv green only inside that tree with distinct
create-only GREEN sinks, and re-verifies the RED envelope unchanged afterward.
Every selected test blob in the staged tree must equal its RED SHA-256, and
every node ID in `red-failing-node-ids.txt` must exist in GREEN JUnit with a
passing outcome. Deleted, renamed, or rewritten RED assertions reject. It
records the GREEN log/JUnit and loaded-blob-manifest hashes, binds the final
staged tree and pre-change parent, emits the strict `tdd_record`, and validates
it before commit. Any unstaged or relevant untracked byte, staged-tree
materialization mismatch, test-hash mismatch, missing RED node, or loaded module
outside that tree fails. Thus no unimplemented P7A parser is trusted to capture
RED, while GREEN proves exactly the same failing tests against the bytes that
will be committed.

For checkpoints 2-4, `p7a-tdd-red` create-exclusively writes a pending envelope
before production edits; it binds pre-change commit/tree, exact argv/selectors,
test hashes, assertion-only RED log/JUnit/failing nodes, and exit `1`; `argv`
means the semantic vector and excludes the phase-local sinks.
After exact staging, `p7a-tdd-green` consumes that envelope and uses the same
staged-tree materialization/loaded-blob protocol as bootstrap. It reruns the
exact semantic argv with distinct create-only GREEN sinks, requires all nodes
green, requires every selected staged test hash to equal RED and every original
failing node ID to exist and pass, re-verifies RED evidence unchanged, binds
`git write-tree`, and create-exclusively emits the strict record.
`p7a-validate-artifact --kind
tdd_record --staged-tree ...` is a mandatory pre-commit gate in Tasks 1, 2, 4,
and 5.

If a later task exposes a defect in an earlier checkpoint, add a contiguous
`fix-01`, `fix-02`, ... record with the same selector identity and an exact
`supersedes_sha256` pointing to the prior P7A TDD record. Base RED/GREEN records
set that field to null. Write the complete failing regression test before each
fix RED and do not edit its selected test blobs before GREEN. Every file is
create-only; never rewrite a pending, base, or fix record.

The executable fix interface is:

```text
p7a-tdd-red
  --checkpoint N
  --fix-ordinal NN
  --supersedes <prior-record>
  --pending <create-only fix-NN.pending.json>

p7a-tdd-green
  --pending <fix-NN.pending.json>
  --staged-tree <git write-tree>
  --output <create-only tdd-checkpoint-N-fix-NN.json>
```

The RED command requires `NN` to be the next contiguous ordinal and the
superseded hash to equal the current chain tip. GREEN uses the sterile staged
tree and the same semantic argv rules. After the corrective commit,
`p7a-freeze-tdd-manifest --supersedes-manifest <old> --disposition <failed
attempt disposition>` creates a new manifest that contains the old immutable
chain plus the new fix record/commit; no old record or manifest is rewritten.

After Task 5 commits, `p7a-freeze-tdd-manifest` verifies the four resulting task
commits/trees against their records, orders each contiguous fix chain, binds the
producer/schema Git blobs, and writes one content-addressed strict
`P7ATddManifest v1`. Task 6 freezes this manifest before allocating an attempt.
The sealed attempt, baseline identity, review candidate, three reviewer
records, evidence review, and final projection receipt all bind its digest.

## Task 0: Reproduce The Reviewed Entry

**Purpose:** Prove the plan starts from the exact reviewed state.

**Files:** None.

### Step 1: Verify commit and worktree

```bash
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD^)" = \
  "74aae0abe3dff685282fbcc785f7a9b3532cbbe6"
test "$(git log -1 --format=%s)" = \
  "docs: preserve p7 and add reviewed p7a design"
export P7A_ENTRY_COMMIT="$(git rev-parse HEAD)"
```

Require the entry diff to contain exactly:

```text
docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md
docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md
docs/superpowers/specs/2026-07-25-p7a-retrieval-quality-attribution-route-selection-design.md
docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md
```

The preserved P7 files must retain their recovered full-file SHA-256 values
`04bc5c52179cf63e29a7a6145e43416ab6e21d61de5e2bc2528b62ac12ca64e8`
and
`06f80aeda5c70afe315d1b30d2bf88b910b28c340f1fc252cc7d889c18b8c4a2`
respectively. The P7A files must match the approved fixed payload/review
record. Any other entry byte stops the plan.

If the reviewed docs have not yet been committed by an explicitly authorized
implementation run, this step has not begun.

### Step 2: Record runtime and dependencies

Write ignored `.quality/p7a-entry/environment.json` with:

- entry and parent commit/tree;
- Python implementation/version;
- SQLite version;
- dependency freeze hash;
- platform and architecture;
- sanitized optional-environment presence;
- clean status before/after.

Do not store values of credentials, repository paths, or private variables.

### Step 3: Run full suite and protected profiles

```bash
mkdir -p .quality/p7a-entry
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q -rsxX -p no:cacheprovider \
  --junitxml .quality/p7a-entry/full-suite.xml \
  > .quality/p7a-entry/full-suite.log 2>&1

p7a_run_default "$P7A_REPO_ROOT" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --repos-dir .quality/repos \
  --output .quality/p7a-entry/p0-ci.json

p7a_run_default "$P7A_REPO_ROOT" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --repos-dir .quality/repos \
  --output .quality/p7a-entry/p2-context.json

p7a_run_default "$P7A_REPO_ROOT" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p4_exploration.json \
  --profile p4_exploration \
  --repos-dir .quality/p4-repos \
  --output .quality/p7a-entry/p4-exploration.json

p7a_run_default "$P7A_REPO_ROOT" -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p5_language_graphs.json \
  --profile p5_language_graphs \
  --repos-dir .quality/p5-repos \
  --output .quality/p7a-entry/p5-language-graphs.json
```

Require:

- 2896 passed;
- the exact nine skip node IDs;
- zero failed/errors/xfails;
- P0 raw CI 8/8;
- P2 5/5;
- P4 4/4 and existing call ceilings;
- P5 12/12;
- clean worktree after all commands.

Any identity difference stops the plan for review.

### Step 4: Write ignored entry record

Record source/public projection hashes for:

- RetrievalTrace v1;
- ContextPack v2;
- ExplorationTrace v2;
- query/context/trace façade signatures;
- store/source/network work counters;
- protected fixture blobs.

Task 1 validates the record once the schema exists.

**Commit:** None.

## Task 1: Freeze Compatibility And Artifact Contracts

**Purpose:** Make the no-behavior-change boundary and every tracked evidence
shape executable before new semantics exist.

**Files:**

- `src/context_search_tool/quality/p7a_contracts.py`
- `tests/test_p7a_contracts.py`
- `tests/fixtures/p7a_retrieval_quality/contracts.json`
- `docs/benchmarks/p7a/README.md`
- `docs/benchmarks/p7a/schemas/p7a-artifacts-v1.json`

### Step 1: Capture RED

Add tests that fail because the schema loader/contracts do not yet exist.
Collection must succeed. The test uses an in-body capability assertion and
never imports the absent module at collection time.

Before editing any production/schema path, run the reviewed bootstrap capture:

```bash
export P7A_TDD1_ROOT="$P7A_REPO_ROOT/.quality/p7a-tdd/checkpoint-1/bootstrap"
test ! -e "$P7A_TDD1_ROOT"
mkdir -p "$P7A_TDD1_ROOT"
test -z "$(git diff --name-only -- \
  src/context_search_tool/quality \
  docs/benchmarks/p7a)"
test ! -e src/context_search_tool/quality/p7a_contracts.py
test ! -e docs/benchmarks/p7a/schemas/p7a-artifacts-v1.json

set -C
git rev-parse HEAD > "$P7A_TDD1_ROOT/pre-change-commit.txt"
git rev-parse 'HEAD^{tree}' > "$P7A_TDD1_ROOT/pre-change-tree.txt"
printf '%s\0' \
  -m pytest -q tests/test_p7a_contracts.py \
  > "$P7A_TDD1_ROOT/pytest.semantic-argv"
shasum -a 256 tests/test_p7a_contracts.py \
  > "$P7A_TDD1_ROOT/test-input-sha256.txt"
set +e
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q \
  tests/test_p7a_contracts.py \
  --junitxml "$P7A_TDD1_ROOT/red.junit.xml" \
  > "$P7A_TDD1_ROOT/red.log" 2>&1
p7a_red_status="$?"
set -e
printf '%s\n' "$p7a_red_status" > "$P7A_TDD1_ROOT/red.exit.txt"
test "$p7a_red_status" -eq 1
LC_ALL=C sed -n 's/^FAILED \([^ ]*\).*/\1/p' \
  "$P7A_TDD1_ROOT/red.log" |
  LC_ALL=C sort -u > "$P7A_TDD1_ROOT/red-failing-node-ids.txt"
test -s "$P7A_TDD1_ROOT/red-failing-node-ids.txt"
shasum -a 256 \
  "$P7A_TDD1_ROOT/pre-change-commit.txt" \
  "$P7A_TDD1_ROOT/pre-change-tree.txt" \
  "$P7A_TDD1_ROOT/pytest.semantic-argv" \
  "$P7A_TDD1_ROOT/test-input-sha256.txt" \
  "$P7A_TDD1_ROOT/red.log" \
  "$P7A_TDD1_ROOT/red.junit.xml" \
  "$P7A_TDD1_ROOT/red.exit.txt" \
  "$P7A_TDD1_ROOT/red-failing-node-ids.txt" \
  | shasum -a 256 > "$P7A_TDD1_ROOT/bootstrap-envelope.sha256"
set +C
```

The Task 1 producer later parses the JUnit failure types and independently
rejects collection/import/syntax/fixture/environment failures; the shell exit
check alone is not sufficient.

### Step 2: Freeze public compatibility

Characterize:

- `inspect.signature(query_repository)`;
- `inspect.signature(trace_repository)`;
- `inspect.signature(build_context_pack)`;
- public dataclass fields/defaults;
- query/context/trace CLI and MCP parameter names;
- QueryBundle, RetrievalTrace-v1, ContextPack-v2, and ExplorationTrace-v2
  canonical serialized keys;
- representative success/error payloads;
- store/source/network work projections.

The contract permits private audit hooks/value types only. Unknown public field,
version, stage, result membership/order, work count, or error change fails.

### Step 3: Implement one strict discriminated artifact schema

`p7a-artifacts-v1.json` uses `artifact_kind` plus `schema_version=1` to select
exactly one closed branch:

```text
entry_record
tdd_record
tdd_manifest
case_selection_provenance
gold_freeze_inputs
gold_provenance_seal
label_review
feasible_cover_witness
audit_leaf_report
role_run
baseline_neutrality_proof
evaluator_closure
prepared_repository_set
baseline_attempt
attempt_disposition
lineage_successor_proof
definition_effect_report
paired_performance_proof
baseline_identity
stage_summary
oracle_summary
route_decision
review_round
review_round_disposition
review_draft_manifest
review_draft_revision_manifest
agent_review
review_candidate
evidence_review
publish_set_receipt
final_tree_projection_receipt
```

This single schema avoids a directory of near-duplicate validators while still
giving every named JSON file a strict type. Each branch:

- has an exact top-level key set;
- rejects unknown enum values;
- uses finite canonical JSON with `allow_nan=False`;
- validates safe IDs, hashes, UTC timestamps, and relative public paths;
- rejects absolute paths and source/snippet/excerpt text;
- has explicit nullability;
- bounds arrays and diagnostic maps.

The transient `P7AWorkerRequest v1` and source-bearing `P7AWorkerFrame v1` are
not persisted and are not branches of this artifact schema. Their separate
closed in-memory schemas are frozen in `_p7a_worker.py` plus the evaluator
validator and bound by the evaluator closure. Persisted `role_run` accepts only
public-output/error hashes and byte lengths, source-free public
path/range/order/content-commitment projections, work/import facts, and audit
leaves.

Run/finalization-derived branches require one sealed baseline-attempt ID/hash.
Reservation, disposition, lineage-successor, and definition-effect branches
instead obey their exact predecessor rules below. Gold authoring branches, the
entry record, and TDD record/manifest branches reject attempt fields. Tests
enumerate all branches and prove that label review,
feasible-cover witness, role-run,
P7A TDD record/manifest, attempt disposition, lineage-successor proof,
definition-effect report, paired-performance proof, baseline identity, and
review round, review-round disposition, review-draft manifest, review candidate,
review-draft revision manifest, and final-tree projection receipt cannot be
accepted as arbitrary hashed JSON.

The `baseline_attempt` branch has a second closed discriminator
`attempt_state=reservation | sealed | complete`. Reservation cannot contain
prepared identities; sealed requires all six actual source/index identities
and forbids role output predating it; complete binds the sealed predecessor and
all proof/canonical hashes. The separate `attempt_disposition` branch has
`predecessor_kind=reservation | sealed | complete`, binds exactly that
predecessor hash, and implements the closed retry/non-retry reason and successor
taxonomy in the design. A review rejection also requires review-candidate and
all three reviewer-record hashes. Draft-only rejection uses
`review_round_disposition` instead and is forbidden from this branch.

The `lineage_successor_proof` branch has
`successor_mode=genesis | external_retry | corrective_commit |
reviewed_contract_amendment`, a sorted proposed-disposition set, predecessor
and successor semantic identities, mode-specific evidence, and one lineage
root. The `definition_effect_report` branch binds the old/new reviewed
contracts and proves no new-attempt output existed when it was built. Its
closed `comparison_status` is `computed` when all six old sealed roles can be
replayed, `unavailable_no_complete_role_set` when any role is absent, or
`unavailable_incompatible_old_evidence` when all six exist but a closed
missing-field, case/unit-domain, observation-domain, or normalization/schema
incompatibility prevents replay. Both unavailable states bind the exact
old/new compatibility manifests and make no effect claim. A proof only proposes
consumption; ledger validation treats a disposition as consumed only by one
atomically committed reservation and rejects multiply bound dispositions.

The `review_round` branch binds a complete attempt, the lowest unused `rNN`
ordinal, and either null or the immediately preceding
`review_round_disposition`. The disposition branch accepts only
`review_draft_rejected`, binds that round's candidate and three reviewer
records, and proves every blocker/major has derived scope
`review_draft_only`; it also binds every failed canonical finding identity and
its validated publication-region references. A canonical finding identity is
the domain-separated digest of
`(review_role, agent_review_sha256, local_finding_id)`, computed only after the
review record is sealed. Local IDs must be unique inside a record; equal local
IDs across different reviewer records remain distinct. The disposition cannot
invalidate or replace the complete attempt.

The `review_draft_manifest` derives its `draft_set_id` only from ordered
`(repository-relative destination, byte length, SHA-256)` tuples. Round IDs and
bundle-relative snapshot paths remain in the manifest but are excluded from the
content-set identity. The `review_draft_revision_manifest` has a closed
`revision_kind=initial | draft_revision` discriminator. `initial` is legal only
for `r01` and binds no predecessor or delta. `draft_revision` binds the
immediately preceding disposition/candidate, previous/current draft manifests
and distinct content-set IDs, byte-identical outside-region projections, a
nonempty ordered region-delta digest, and one resolution mapping per failed
draft-only canonical finding identity. Later rounds must keep all non-draft
evidence hashes identical, bind the preceding disposition, and pass this
content-level revision proof.

Every numbered review root is visible only after the round, four snapshots,
draft manifest, revision manifest, and candidate have all validated in one
unnumbered same-filesystem candidate root and that complete directory is
atomically renamed under the ledger lock. Pre-rename failure consumes no
ordinal; post-rename recovery always sees the whole bundle.

Every review candidate resolves the registry-defined publication-region IDs and
binds the registry hash, each exact marker pair, snapshot-relative
`[start,end)` byte interval, length, and SHA-256. A strict `agent_review`
finding uses a closed target union
of candidate-bound publication-region reference, corrective path, governed
path, or conceptual contract key; bare documentation paths and cross-boundary
region intervals cannot be classified as draft-only.

The `stage_summary` branch uses closed
`aggregation_kind=recall | rank_distribution | result_ratio |
duplicate_count | reason_count | mixed_count` sub-branches. Each accepts only
the raw counts, rational fields, nulls, order statistics, applicability, and
strata fields required by the metric table; a generic name/value map is
forbidden.

### Step 4: Freeze the publication-region registry

Define literal `P7A_PUBLICATION_REGION_REGISTRY_V1` in `p7a_contracts.py`:

| destination | region ID | exact opening marker | exact closing marker |
| --- | --- | --- | --- |
| `docs/benchmarks/p7a/README.md` | `p7a_benchmark_readme` | `<!-- P7A:BEGIN p7a_benchmark_readme -->` | `<!-- P7A:END p7a_benchmark_readme -->` |
| `README.md` | `p7a_root_readme` | `<!-- P7A:BEGIN p7a_root_readme -->` | `<!-- P7A:END p7a_root_readme -->` |
| `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` | `p7a_roadmap` | `<!-- P7A:BEGIN p7a_roadmap -->` | `<!-- P7A:END p7a_roadmap -->` |
| `docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md` | `p7a_plan_implementation_record` | `<!-- P7A:BEGIN p7a_plan_implementation_record -->` | `<!-- P7A:END p7a_plan_implementation_record -->` |

The ordered table has a domain-separated registry hash. Task 1 TDD, evaluator
closure, baseline attempt, and every review candidate bind the exact constant
and its defining blob. Marker literals are complete ASCII lines terminated by
LF. Each registered document permits exactly one region: its opening and
closing marker must each occur exactly once in order, and the mutable
`[start,end)` interval excludes both marker lines. Missing, duplicate, reversed,
nested, CRLF-mutated, or unregistered complete marker lines beginning
`<!-- P7A:BEGIN ` or `<!-- P7A:END ` fail before a numbered bundle publishes.
Inline code/table text is not a marker. `r01` uses only exact complete-line
table lookup; it performs no heading/prose heuristic. Tests enumerate the full
mapping and all malformed cases.

The benchmark README created in Task 1 includes its empty marked region. Task 6
adds the exact root README and roadmap marker pairs around only their P7A
blocks. This plan already carries its pair inside the excluded Implementation
Record; its headings, review ledger, and Stop Point remain outside the region.
A registry change is contract-governed, never a draft-only edit.

### Step 5: Validate the ignored entry record

```bash
p7a_run_default "$P7A_REPO_ROOT" -m context_search_tool.quality.p7a_contracts \
  validate \
  --schema docs/benchmarks/p7a/schemas/p7a-artifacts-v1.json \
  --kind entry_record \
  --input .quality/p7a-entry/entry-record.json
```

Default pytest uses committed synthetic examples only; it must not depend on
ignored artifacts or public repository availability.

### Step 6: Green and protected gates

```bash
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q \
  tests/test_p7a_contracts.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_trace.py \
  tests/test_context_pack.py \
  tests/test_exploration_contracts.py
```

### Step 7: Stage exact files and commit

```bash
git add \
  src/context_search_tool/quality/p7a_contracts.py \
  tests/test_p7a_contracts.py \
  tests/fixtures/p7a_retrieval_quality/contracts.json \
  docs/benchmarks/p7a/README.md \
  docs/benchmarks/p7a/schemas/p7a-artifacts-v1.json
test -z "$(git diff --name-only)"
test -z "$(git ls-files --others --exclude-standard)"
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-bootstrap \
  --checkpoint 1 \
  --bootstrap "$P7A_TDD1_ROOT" \
  --green-root-mode staged-tree \
  --reject-unstaged-and-relevant-untracked \
  --staged-tree "$(git write-tree)" \
  --output .quality/p7a-tdd/tdd-checkpoint-1.json
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-validate-artifact \
  --kind tdd_record \
  --input .quality/p7a-tdd/tdd-checkpoint-1.json \
  --staged-tree "$(git write-tree)"
git diff --cached --check
git diff --cached --name-only
git commit -m "test: lock p7a attribution contracts"
```

**Commit:** `test: lock p7a attribution contracts`

## Task 2: Implement Frozen Attribution Semantics

**Purpose:** Freeze case parsing, coherent finalization, label-assisted upper
bounds, metrics, and route selection before the benchmark is authored.

**Files:**

- `src/context_search_tool/quality/p7a_contracts.py`
- `src/context_search_tool/quality/p7a_evaluator.py`
- `tests/test_p7a_cases.py`
- `tests/test_p7a_gold.py`
- `tests/test_p7a_profile.py`
- `tests/test_p7a_finalize.py`
- `tests/test_p7a_oracle.py`
- `tests/test_p7a_decision.py`
- `tests/fixtures/p7a_retrieval_quality/schema_examples.json`

### Step 1: Capture RED

Cover ordinary assertions for:

- schema-v2 parsing and v1 compatibility;
- profile, quota, and selection-provenance validation over synthetic schema
  examples without depending on future Task 3 benchmark bytes;
- exact-identifier extraction and target resolution;
- duplicate/overlap rejection and simultaneous feasible-cover witnesses;
- coherent variants and the exact progress-vector formula;
- variant-tie ambiguity;
- surface DAG finalization;
- semantic-choice-stable recall/rank/result/count metric aggregators and strata;
- three bounded oracles;
- dominance formulas and route mapping.

Before editing production semantics:

```bash
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-red \
  --checkpoint 2 \
  --pre-change-commit "$(git rev-parse HEAD)" \
  --pending .quality/p7a-tdd/tdd-checkpoint-2.pending.json \
  -- \
  tests/test_p7a_cases.py \
  tests/test_p7a_gold.py \
  tests/test_p7a_profile.py \
  tests/test_p7a_finalize.py \
  tests/test_p7a_oracle.py \
  tests/test_p7a_decision.py
```

### Step 2: Add schema-v2 values

Implement frozen dataclasses for:

```text
P7ASourceIdentity
CaseSelectionRecord
EvidenceTarget
EvidenceAlternative
EvidenceUnit
EvidenceCoverChoice
EvidenceCoverVariant
P7AQualityCase
FeasibleCoverWitness
GoldFreezeInputs
GoldProvenanceSeal
ResolvedGoldProvenance
```

Validation follows the design exactly. In particular:

- `required` and `known_gap` vote;
- `informational` never votes;
- NFC exact-identifier tokens use the design's closed boundaries and exact
  indexed symbol/basename/stem mapping;
- exact-identifier variants always choose a required alternative on a named
  path;
- exploratory variants cover two paths and roles/project units;
- duplicate resolved units and same-path overlapping co-selected ranges reject;
- source independence and cross-source quotas are closed fields;
- no “absolute pass” value is inferred from unit `required`.

### Step 3: Resolve targets against pinned indexed source

Preflight, separate from JSON parsing:

- verifies clean pinned source/index identity;
- resolves symbols and ranges;
- enforces one-to-eighty-line canonical targets;
- rejects a target when its normalized logical-line payloads have aggregate
  UTF-8 byte length zero;
- requires active indexed chunk coverage;
- validates target literals inside the range;
- stores ranges/counts/hashes, never source content.

### Step 4: Implement simultaneous feasible-cover preflight

Enumerate legal cover atoms from pinned source/index structure and the exact
query/context/explore capacities. For each complete variant:

- cover every required target simultaneously;
- enforce result/anchor or QueryBundle/fusion capacities;
- enforce all frozen `ContextPackOptions` fields where applicable:
  `max_items`, `max_excerpts_per_item`, `max_excerpt_bytes`,
  `max_item_content_bytes`, `max_total_content_bytes`, `max_pack_bytes`,
  `context_before_lines`, and `context_after_lines`;
- choose the exact lexicographic minimum tuple from the design;
- emit source-free paths/ranges/chunk-window IDs/counts/hashes; and
- reject the variant/case before baseline if no complete witness exists.

Tests include the IR reviewer's blocker: every individual unit fits, but their
joint result/item/excerpt/byte requirements do not. That case must fail
preflight rather than enter a miss denominator. A second case satisfies every
aggregate item/total/pack budget but exceeds only `max_excerpt_bytes`; it must
also fail. An empty-only range fails target preflight before either witness or
baseline construction.

### Step 5: Implement coherent finalization

Implement the closed
`python313-utf8-replace-universal-newline-splitlines-v1` segmentation and
`MaterializedContentCommitment v1` validators as pure functions. One helper
builds target-independent commitments from transient public segments; a
separate finalizer helper reads pinned Git blobs, recomputes canonical full-line
hashes, and accepts target coverage only when one segment exactly commits every
target line. The helper performs UTF-8 replacement decoding, CRLF/bare-CR
universal translation, and Python 3.13 `str.splitlines(keepends=True)` over the
closed LF/VT/FF/FS/GS/RS/NEL/U+2028/U+2029 boundary set. Target resolution,
feasible-cover, commitment creation, and blob replay must call this same helper.
Evaluate complete variants independently.

Tests must prove:

- no alternative mixing;
- semantic permutation invariance;
- exact deepest-to-shallowest progress-vector dimensions, counts, direction,
  and best-vector tie retention;
- diagnostic semantic-min backlink does not vote;
- every tied `(variant, unit)` retains its own
  `diagnostic_terminal_reason`;
- all-satisfied tied reasons yield `unit_satisfied`; all non-satisfied reasons
  in one group yield that group; every satisfied/miss or cross-group mix yields
  `unit_mixed`;
- a tied case yields `case_mixed`;
- every applicable `(variant, unit)` receives exactly one reason;
- missing applicable leaves invalidate the role;
- query/context/explore carrier-lineage first-failure chains follow the design
  exactly;
- an adjacent acquired seed whose expansion covers the target is valid carrier
  success even when the seed chunk itself does not cover the target;
- query terminal success checks every public result/anchor commitment, not only
  the first same-path result;
- materialized coverage uses full-line content commitments, not ranges; tests
  include same-range single-line mid-byte and first/last-line crops, literal
  removal, CJK UTF-8 boundaries, CRLF/bare-CR/LF, every VT/FF/FS/GS/RS/NEL/
  U+2028/U+2029 boundary, no-final-newline, a later same-path fully committed
  result, and a full target with extra context;
- seed target-span acquisition and expansion-carrier metrics assert their exact
  distinct numerators/denominators, including adjacent-seed expansion;
- the evaluator's final-selection projection reproduces
  `split_results_and_anchors` on synthetic fixtures and keeps rank-capacity
  decisions disjoint from the exact `duplicate_anchor` non-rank decision for
  query, context, and every explore probe.

### Step 5A: Implement the closed metric contract

Metrics run only after six-role equality and read
`instrumentation-enabled-a` as the canonical role. Build one `metric_unit` per
required `(case_id, unit_id)`. Its alternative set is the distinct semantic
choice keys used by retained complete variants; never count the same
alternative once per variant. For each applicable recall stage, the unit is a
hit only when every distinct retained choice satisfies the stage.

Implement and schema-lock:

- path, seed-span, expansion-carrier, surface-terminal, item, and excerpt recall
  with the exact surface applicability and predecessor-false rules in the
  design;
- raw hit/total, exact reduced-rational unit-micro, exact reduced-rational
  case-macro, and contributing-case count;
- target-carrier rank over unique semantic-choice atoms, including explicit
  missing count and nearest-rank p50/p90; explore rank is the minimum global
  one-based position in the actual flattened pre-fusion input stream, ordered
  as initial call then ascending `probe_ordinal`, with each call preserving its
  final merged expanded-carrier order;
- per-case, pooled, and case-macro unique-result-path ratio;
- per-case duplicate-slot count plus aggregate sum and exact case mean;
- semantic-choice-deduplicated terminal-reason counts and one-per-unit/case
  mixed counts; and
- independent all-profile, source, surface, intent, language, confirmatory, and
  gate slices using the metric-specific aggregation rule.

Tests must include:

- a new legal coherent variant that only recombines already-retained semantic
  choices; every metric remains byte-identical;
- the same semantic choice appearing in several variants, counted once, and an
  inconsistent reason for that choice rejecting finalization;
- all six recall metrics on query/context/explore, including query null
  item/excerpt, prior-stage misses counted false, empty denominators, and missing
  applicable leaves;
- unequal per-case denominators proving unit-micro and case-macro differ but
  match exact rational formulas;
- empty output and all-missing-rank cases, one present rank, nearest-rank
  boundaries, and explore's initial-then-probe flattened pre-fusion order,
  including a target repeated in the initial call and follow-up probes;
- zero-result null unique-path ratio, duplicate slots, anchors excluded from
  result counts, and post-fusion explore results; and
- every stratum dimension, empty strata, informational versus
  decision-eligible gates, and proof that only the latter can support route
  diagnostics.

### Step 6: Implement oracles

File oracle:

- uses only actual acquired/expanded selector-input carriers and fusion
  representatives;
- preserves actual capacity/partition and chooses at most one actual
  representative for each deduplication key;
- may prefer an existing target carrier over a non-target carrier with the same
  key, but cannot add/alter a path/span or recover a non-selection reason;
- covers exactly `raw_selection`, `raw_selection_after_all_probes`, and
  `fused_selection`, with query/context duplicate-anchor, explore
  duplicate-carrier, and fusion-replacement tests;
- stops after the failed selection/fusion leaf becomes true and marks every
  downstream counterfactual leaf `not_evaluated`; it never replays or assumes
  pack/excerpt success.

Span oracle:

- uses only actual acquired seed chunks and their legal carrier windows;
- preserves actual path population, capacity, partitions, and
  materialization/output bounds;
- cannot add a path/seed or enlarge expansion bounds and recovers only the
  closed span/ranking reasons;
- stops after the mapped span/materialization leaf becomes true and never
  replays or assumes later selection/fusion/pack/excerpt behavior.

Pack oracle:

- uses only the actual QueryBundle;
- preserves actual item/excerpt/byte budgets;
- cannot add an absent file/span or recover a non-pack reason;
- may report terminal satisfaction only when it recovers the terminal excerpt
  leaf; recovery of an earlier pack-group leaf remains stage-local.

Each oracle evaluates every complete variant against that same variant's
immutable actual leaves. Certificate lift contains only
`newly_mapped_boundary_recovered_required_count`; variant lift is its maximum
over legal certificates, including one always-legal closed zero-lift no-op.
Every other certificate performs exactly one mapped typed intervention. There
is no secondary cross-reason or downstream
tie-breaker. Within each `(oracle, variant)`, retain every maximal-lift
certificate mathematically and first intersect their recovered unit sets. Keep
the persisted proof bounded: record one semantic-min maximal witness, then for
each candidate unit solve the constrained optimum with that unit unrecovered
and record its semantic-min countercertificate. A unit is in the intersection
only when the constrained optimum is strictly lower; equality excludes it.
Synthetic exhaustive enumeration must match this proof. Case support then
intersects those per-variant sets across every maximal-lift complete variant.
Per-unit maxima across certificates or variants are a failing Frankenstein
test. Tests cover equally scoring interventions that recover different units,
duplicate-carrier choices, and every carrier/certificate/variant permutation.
They also reject copying actual downstream leaves, using a feasibility witness
as downstream success, or replaying fusion/pack after a file/span intervention.
A span intervention may report terminal satisfaction only for query
`raw_target_not_materialized`, whose mapped leaf is itself terminal; all other
span/file recoveries remain stage-local.

### Step 7: Implement route decision

Freeze:

- terminal reason map;
- decision-eligible gates;
- five reason groups;
- `unit_mixed`/`case_mixed` handling;
- exact integer-cross-product threshold checks;
- independent-source and confirmatory support;
- intent/surface cohort reconciliation plus strict confirmatory-only
  reconciliation of the global group;
- no oracle requirement for path/target-span acquisition;
- exact span→span-oracle, selection→file-oracle, and pack→pack-oracle mapping,
  with route support counted only from the two-level
  `case_supported_units` intersection, stage-local boundary recovery, and no
  upstream-oracle downstream claim;
- seven outcomes and one-to-one next actions.

The confirmatory-only rule is intentionally a direction check, not a second
full dominance election. After the global absolute minima pass, two
confirmatory failed cases/two supporting units may confirm the global group
only when one case comes from each external source and all four slice ratios are
`1.0`.

Tests include every inclusive boundary and:

```text
global A + cohort A -> A
global A + cohort B -> benchmark_mixed_expand
global mixed + cohort A -> benchmark_mixed_expand
global A + confirmatory-only A -> A
global A + confirmatory-only B -> benchmark_mixed_expand
global A + tied/threshold-ineligible confirmatory-only -> benchmark_mixed_expand
global-qualified A + Mc=2/Fc=2/U_A=2/C_A=2,
  one case per external and all four ratios 1.0 -> A
informational-only support -> no effect
CST + one external -> insufficient repository support
two external but no confirmatory support -> insufficient
no misses -> no_proven_gap
```

### Step 8: Green and protected gates

```bash
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q \
  tests/test_p7a_cases.py \
  tests/test_p7a_gold.py \
  tests/test_p7a_profile.py \
  tests/test_p7a_finalize.py \
  tests/test_p7a_oracle.py \
  tests/test_p7a_decision.py
```

### Step 9: Stage and commit

```bash
git add \
  src/context_search_tool/quality/p7a_contracts.py \
  src/context_search_tool/quality/p7a_evaluator.py \
  tests/test_p7a_cases.py \
  tests/test_p7a_gold.py \
  tests/test_p7a_profile.py \
  tests/test_p7a_finalize.py \
  tests/test_p7a_oracle.py \
  tests/test_p7a_decision.py \
  tests/fixtures/p7a_retrieval_quality/schema_examples.json
test -z "$(git diff --name-only)"
test -z "$(git ls-files --others --exclude-standard)"
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-green \
  --pending .quality/p7a-tdd/tdd-checkpoint-2.pending.json \
  --green-root-mode staged-tree \
  --reject-unstaged-and-relevant-untracked \
  --staged-tree "$(git write-tree)" \
  --output .quality/p7a-tdd/tdd-checkpoint-2.json
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-validate-artifact \
  --kind tdd_record \
  --input .quality/p7a-tdd/tdd-checkpoint-2.json \
  --staged-tree "$(git write-tree)"
git diff --cached --check
git diff --cached --name-only
git commit -m "feat: add p7a attribution evaluator"
```

After this commit, parsing, witness, progress, reason, metric, oracle, threshold,
and route semantics are frozen. Later tasks may call them but cannot edit them
without a reviewed contract amendment, new gold freeze, and old/new baseline
effect.

**Commit:** `feat: add p7a attribution evaluator`

## Task 3: Author And Freeze The Public Benchmark

**Purpose:** Freeze target-bearing cases and selection provenance before the
controlled baseline exists.

**Files:**

- `tests/fixtures/p7a_retrieval_quality/sources.json`
- `tests/fixtures/p7a_retrieval_quality/case_selection_provenance.json`
- `tests/fixtures/p7a_retrieval_quality/p7a_route.json`
- `tests/fixtures/p7a_retrieval_quality/p7a_profile.json`
- `tests/fixtures/p7a-retrieval-quality/**`
- `docs/benchmarks/p7a/gold/gold-freeze-inputs.json`
- `docs/benchmarks/p7a/gold/feasible-cover-witness.json`
- `docs/benchmarks/p7a/gold/label-review.json`

The closed subtree `tests/fixtures/p7a-retrieval-quality/**` must match the exact
source/fixture manifest generated before staging.

This task authors and freezes data only. It must not edit
`tests/test_p7a_profile.py`, `tests/test_p7a_gold.py`, or any other
checkpoint-2 test/evaluator byte. Those tests were frozen at checkpoint 2 and
are rerun unchanged as contract regressions; the evaluator preflight validates
the new concrete fixture. Selection provenance, independent label review, the
feasible-cover witness, and the gold input/seal lineage provide the reviewable
evidence for these newly authored data bytes.

### Step 1: Prepare pinned sources

Use isolated ignored roots:

```bash
export P7A_SOURCE_ROOT="$P7A_REPO_ROOT/.quality/p7a-sources"
export P7A_GOLD_PREFLIGHT_ROOT="$P7A_REPO_ROOT/.quality/p7a-gold-preflight"
mkdir -p "$P7A_SOURCE_ROOT" "$P7A_GOLD_PREFLIGHT_ROOT"
```

For each source:

- fetch/clone only if explicitly authorized during implementation;
- detach at the exact commit/object;
- require clean status;
- record normalized source-tree and indexing-option hashes;
- create a separate preflight copy;
- never use the mutable CST working tree as source evidence.

### Step 2: Freeze selection provenance first

Before authoring controlled outputs, record:

- available source-task universe;
- deterministic selection rule;
- every inclusion/exclusion;
- design-motivating flag;
- confirmatory membership;
- authoring UTC;
- author and planned reviewer identities.

Require six cases per source and at least three confirmatory cases from each
independent external source.

### Step 3: Author eighteen cases

Author exactly eighteen schema-v2 cases and at least forty-eight required units.
Meet every source×intent×surface quota.

For each alternative:

- inspect pinned source directly;
- record exact path, symbol/range, and optional literals;
- freeze the exact NFC query tokens and indexed symbol/basename/stem matches;
- define coherent variants from task meaning;
- do not run CST quality, any oracle, or fast-context.

### Step 4: Run target/variant/quota preflight

Run the already frozen checkpoint-2 tests without editing them:

```bash
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q \
  tests/test_p7a_profile.py \
  tests/test_p7a_gold.py \
  tests/test_p7a_cases.py

p7a_run_default "$P7A_REPO_ROOT" -m context_search_tool.quality.p7a_evaluator \
  preflight-gold \
  --sources tests/fixtures/p7a_retrieval_quality/sources.json \
  --selection-provenance \
  tests/fixtures/p7a_retrieval_quality/case_selection_provenance.json \
  --fixture tests/fixtures/p7a_retrieval_quality/p7a_route.json \
  --profile tests/fixtures/p7a_retrieval_quality/p7a_profile.json \
  --prepared-sources "$P7A_GOLD_PREFLIGHT_ROOT" \
  --preflight-output "$P7A_GOLD_PREFLIGHT_ROOT/preflight.json" \
  --witness-output "$P7A_GOLD_PREFLIGHT_ROOT/feasible-cover-witness.json"
```

The command performs no query/context/explore call. It rejects duplicate
resolved units, overlapping co-selected ranges, any complete variant without a
simultaneous feasible cover, and any unknown surface budget. Before it runs,
assert only that the current in-progress gold-freeze/preflight root has no
controlled role output and that no sealed attempt already binds this exact
uncommitted gold lineage. Never scan for or reject immutable role output from a
historical attempt: old attempts remain preserved, retain their own
gold/closure hashes, and enter any required old/new effect disclosure.

### Step 5: Independent label review

A read-only reviewer who did not author the cases verifies:

- task meaning;
- case-selection provenance;
- targets/literals;
- exact-identifier token/match report;
- coherent variants;
- every simultaneous feasible-cover path/window/partition and item/excerpt/byte
  count;
- confirmatory status;
- quotas;
- no baseline/comparator-derived label.

Author and reviewer IDs must differ. Every accepted/rejected comment, exact
resolved hash, witness hash, and helper/options hash enters the strict
`label_review` artifact. The accepted source-free witness bytes are promoted
unchanged to `docs/benchmarks/p7a/gold/feasible-cover-witness.json`.

Promotion is mechanical and create-only:

```bash
test ! -e docs/benchmarks/p7a/gold/feasible-cover-witness.json
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_evaluator promote-reviewed-witness \
  --source "$P7A_GOLD_PREFLIGHT_ROOT/feasible-cover-witness.json" \
  --label-review docs/benchmarks/p7a/gold/label-review.json \
  --destination docs/benchmarks/p7a/gold/feasible-cover-witness.json
cmp \
  "$P7A_GOLD_PREFLIGHT_ROOT/feasible-cover-witness.json" \
  docs/benchmarks/p7a/gold/feasible-cover-witness.json
shasum -a 256 \
  "$P7A_GOLD_PREFLIGHT_ROOT/feasible-cover-witness.json" \
  docs/benchmarks/p7a/gold/feasible-cover-witness.json
```

The command validates the strict review, source/helper/options hashes, opens the
destination with exclusive creation, and refuses replacement. A failed partial
write is not accepted; the destination must validate and compare byte-for-byte
before staging.

### Step 6: Write pre-commit gold inputs

`gold-freeze-inputs.json` binds the design's complete input set, including the
strict label-review artifact, exact-identifier report, feasible-cover witness,
and Task 2 helper/reason/finalizer/metric/oracle/decision blobs. It cannot name
its own future commit. No baseline result or oracle output exists yet.

### Step 7: Stage exact files and commit

```bash
git add \
  tests/fixtures/p7a_retrieval_quality/sources.json \
  tests/fixtures/p7a_retrieval_quality/case_selection_provenance.json \
  tests/fixtures/p7a_retrieval_quality/p7a_route.json \
  tests/fixtures/p7a_retrieval_quality/p7a_profile.json \
  tests/fixtures/p7a-retrieval-quality \
  docs/benchmarks/p7a/gold/gold-freeze-inputs.json \
  docs/benchmarks/p7a/gold/feasible-cover-witness.json \
  docs/benchmarks/p7a/gold/label-review.json
git diff --cached --check
git diff --cached --name-only > .quality/p7a-gold-preflight/staged-files.txt
cmp \
  .quality/p7a-gold-preflight/staged-files.txt \
  .quality/p7a-gold-preflight/expected-staged-files.txt
git commit -m "test: freeze p7a route benchmark"
export P7A_GOLD_FREEZE_COMMIT="$(git rev-parse HEAD)"
```

Task 5 creates the post-commit `GoldProvenanceSeal` and verifies all blobs
against this commit. No later task edits gold/evaluator semantics.

**Commit:** `test: freeze p7a route benchmark`

## Task 4: Add Behavior-Neutral Audit Hooks

**Purpose:** Observe existing execution stages without adding retrieval work or
changing public behavior.

**Files:**

- `src/context_search_tool/retrieval_core/audit_observer.py`
- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/context_pack/builder.py`
- `src/context_search_tool/exploration/runner.py`
- `src/context_search_tool/exploration/fusion.py`
- `tests/test_p7a_audit.py`
- `tests/test_retrieval_pipeline.py`
- `tests/test_context_pack.py`
- `tests/test_exploration_runner.py`
- `tests/test_exploration_fusion.py`

### Step 1: Capture RED

Add tests for:

- non-nestable ContextVar observer;
- reset after success/error/cancellation/early return;
- exact closed leaf keys;
- query/context/explore ledger counts;
- source-content rejection;
- disabled-mode no payload allocation/work;
- observer imports only the standard library and does not import `quality`;
- enabled/disabled public projection equality.

Before editing any product hook:

```bash
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-red \
  --checkpoint 3 \
  --pre-change-commit "$(git rev-parse HEAD)" \
  --pending .quality/p7a-tdd/tdd-checkpoint-3.pending.json \
  -- tests/test_p7a_audit.py
```

### Step 2: Implement the collector

`retrieval_core/audit_observer.py` owns private immutable leaf/envelope values
and:

```text
install_p7a_observer
emit_p7a_leaf
finish_p7a_observer
```

`emit_p7a_leaf` checks the ContextVar first and returns immediately when unset.
Call sites use `p7a_observer_active()` before constructing a tuple or map, so
disabled mode creates no candidate snapshot. The module imports only stdlib
types/ContextVar and accepts already-computed scalars only. Values are bounded
and source-free.

### Step 3: Add hooks at existing boundaries

Hook only the four orchestration files in `Files`, at points where the values
already exist:

- retrieval lane/candidate completion already present in `retrieval.py`;
- final merged candidate population;
- ranked order;
- expanded ranges with their already-computed `chunk_ids` backlinks plus the
  already-existing order/partition/dedup scalars needed by the frozen evaluator
  replay;
- actual final selected membership; the evaluator, not product code, derives
  exact `selected_result | selected_anchor | result_limit | anchor_limit |
  duplicate_anchor` decisions;
- QueryBundle result/anchor membership;
- final stable ContextPack selector membership, closed omission decisions, item
  paths, and excerpt ranges after retry/compaction;
- P4 retrieval-call start/end, fusion, final pack/excerpts;
- existing work counters and closed error state.

Do not:

- scan a new identifier;
- open a store/session;
- read/stat a source file;
- copy source text;
- invoke a planner/embedding;
- change a limit/order/member;
- add a public field.

Synthetic audit tests include an acquired adjacent seed whose expanded range
covers the target and a duplicate anchor whose target carrier is excluded
without a rank-capacity failure.

### Step 4: Prove no-observer behavior

For a matrix of success, no-candidate, missing-index, planner
enabled/fallback, graph ready/stale/fault, query/context/trace/explore:

- canonical public bytes equal the pre-task projection;
- store/source/network work equals exactly;
- no observer object remains;
- public signatures and dataclass fields equal Task 1 fixtures;
- `sys.modules` contains neither `context_search_tool.quality` nor any P7A
  evaluator module after an ordinary import/query;
- `quality/__init__.py` is byte-identical to the entry commit.

### Step 5: Green and protected gates

```bash
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q \
  tests/test_p7a_audit.py \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_context_pack.py \
  tests/test_exploration_runner.py \
  tests/test_exploration_fusion.py \
  tests/test_retrieval_trace.py
```

### Step 6: Stage and commit

```bash
git add \
  src/context_search_tool/retrieval_core/audit_observer.py \
  src/context_search_tool/retrieval.py \
  src/context_search_tool/context_pack/builder.py \
  src/context_search_tool/exploration/runner.py \
  src/context_search_tool/exploration/fusion.py \
  tests/test_p7a_audit.py \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py \
  tests/test_exploration_runner.py \
  tests/test_exploration_fusion.py
test -z "$(git diff --name-only)"
test -z "$(git ls-files --others --exclude-standard)"
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-green \
  --pending .quality/p7a-tdd/tdd-checkpoint-3.pending.json \
  --green-root-mode staged-tree \
  --reject-unstaged-and-relevant-untracked \
  --staged-tree "$(git write-tree)" \
  --output .quality/p7a-tdd/tdd-checkpoint-3.json
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-validate-artifact \
  --kind tdd_record \
  --input .quality/p7a-tdd/tdd-checkpoint-3.json \
  --staged-tree "$(git write-tree)"
git diff --cached --check
git diff --cached --name-only
git commit -m "feat: add p7a retrieval audit hooks"
```

**Commit:** `feat: add p7a retrieval audit hooks`

## Task 5: Add The Frozen Baseline Evidence Runner

**Purpose:** Separate product execution from gold evaluation, freeze the
evaluator closure, enforce immutable attempts, and prepare recoverable
create-only publication.

**Files:**

- `src/context_search_tool/_p7a_worker.py`
- `src/context_search_tool/quality/__main__.py`
- `src/context_search_tool/quality/p7a_runner.py`
- `src/context_search_tool/quality/p7a_lifecycle.py`
- `tests/test_p7a_runner.py`
- `tests/test_p7a_attempts.py`
- `tests/test_p7a_publish.py`
- `tests/test_quality_cli.py`

### Step 1: Capture RED

Tests cover:

- framed subprocess protocol;
- bounded stdout/stderr frames and cancel/timeout/protocol-error
  terminate→grace→kill→wait/reap ordering before partial hashes or disposition;
- absolute-path isolated `-I -B` bootstrap, transient
  role/root/commit/tree verification, bytecode-write rejection, and ambient
  instrumentation-root rejection;
- ordinary and worker import closures exclude `quality`/evaluator modules;
- worker input excludes gold metadata and persisted output excludes its
  absolute product root;
- transient worker request/frame and persisted source-free `role_run` artifacts
  obey distinct closed schemas; source-bearing public bytes never reach disk;
- target-independent logical-line content commitments detect same-range
  single-line/first-line/last-line crops, CJK boundaries, the complete frozen
  `splitlines()` boundary set, repeated substrings, and missing final newlines;
- deterministic-clock raw equality for explore timing;
- GoldFreezeInputs + post-commit seal resolution;
- evaluator recomputation of every derived value;
- six-role neutrality proof;
- evaluator-closure path/blob verification;
- atomic attempt allocation, retry/non-retry dispositions, post-completion
  review rejection, and lowest-ordinal rule;
- non-consuming candidate proofs plus locked atomic reservation consumption,
  including concurrent builders, competing allocators, crash-before-publish,
  and orphan-proof cases;
- governed/corrective path-map disjointness, corrective bypass rejection,
  contract-amendment semantic delta, and all three definition-effect states;
- successful registry/schema/evaluator/profile-test amendments returning to
  their Task 1/2 owning checkpoints with exact governed tests/fixtures, plus
  omitted-test and misclassified-corrective rejection;
- successful data-only selection/profile/source/gold amendments retaining the
  unchanged four-checkpoint manifest while rebuilding selection, independent
  label-review, feasible-cover, gold-seal, closure, definition-effect, and
  successor-attempt lineage, plus missing-lineage and illicit-test-edit
  rejection;
- deterministic non-retryable `declared_timeout` classification;
- four-checkpoint TDD-manifest creation and binding;
- RED/GREEN semantic-argv and selected-test-hash identity, exact RED-failing-node
  transition to GREEN pass, distinct create-only sinks, staged-tree GREEN
  materialization, and unstaged-pass/staged-fail rejection;
- prepare/review/promote publication;
- create-only review rounds/draft snapshots, draft-only revision chains,
  stable region IDs and finding locators, content-only draft-set identities,
  nonempty region-delta/resolution proofs, governed-over-mixed finding
  precedence, and clean corrective-worktree enforcement;
- atomic complete review-input bundle publication, with validation and injected
  crashes at every pre/post-rename boundary proving no stranded numbered round;
- plan-region inside/outside/cross-boundary findings, bare-document-path
  rejection, same-byte or snapshot-relocation-only successor rejection, stale
  predecessor rejection, and multi-document mixed-target classification;
- exact first-round registry bootstrap plus missing, duplicate, reversed,
  nested, CRLF-mutated, unregistered, and cross-revision marker rejection;
- schema-valid stale/unknown/out-of-bounds/wrong-slice/cross-boundary region
  targets sealing as governed amendment rather than stranding the round;
- duplicate local finding IDs within one reviewer rejection and equal local IDs
  across two reviewers producing distinct canonical resolution obligations;
- persistent corrective successor branch plus exact reviewed-implementation
  parent and exact reviewed staged-tree OID for the final publication commit;
- commit-mode projection verification, including a synthetic pre-commit hook
  that rewrites the index and must be caught by post-commit tree equality;
- end-to-end rejected→corrective commit→new attempt→PASS round→publication and
  draft-rejected→revised round→PASS round state machines;
- exact three-role, pairwise-distinct reviewer invocation enforcement;
- deterministic post-review ledger projection and exact final staged-tree
  verification.

Before implementing the runner:

```bash
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-red \
  --checkpoint 4 \
  --pre-change-commit "$(git rev-parse HEAD)" \
  --pending .quality/p7a-tdd/tdd-checkpoint-4.pending.json \
  -- \
  tests/test_p7a_runner.py \
  tests/test_p7a_attempts.py \
  tests/test_p7a_publish.py
```

### Step 2: Implement product worker

The worker:

- starts with a sterile temporary cwd;
- runs in a new process group with evaluator-owned bounded pipes;
- is launched exactly as
  `"$P7A_RUNTIME" -I -B "$P7A_WORKER_ABSOLUTE_PATH"`; its stdlib-only bootstrap
  removes the empty entry, script directory, cwd, `PYTHONPATH`, ambient
  repository roots, and every non-selected CST source root before inserting the
  explicit behavior or instrumentation product `src` root; it preserves only
  the runtime-identity-bound stdlib and site-packages roots needed by declared
  dependencies;
- asserts `sys.dont_write_bytecode is True` before any product import;
- verifies every imported `context_search_tool` module resolves below that
  selected root and every third-party module below a frozen runtime dependency
  root before invoking a façade;
- receives a closed canonical `P7AWorkerRequest v1` on stdin containing the
  transient absolute `product_src_root`, expected product commit/tree, opaque
  invocation ID, surface, ordinary façade inputs, source/index identity, and
  audit mode;
- selects behavior versus instrumentation root from the sealed role, rejects
  every role/root/commit/tree mismatch, and never echoes the absolute root;
- runs exactly one supported query/context case or one complete explore case;
- installs the closed deterministic `clock_ns` sequence for quality explore
  calls; it uses no deterministic clock in performance mode;
- writes one framed output to stdout;
- never imports `context_search_tool.quality`, fixture, gold, witness,
  finalizer, oracle, or decision modules;
- rejects unknown environment and protocol fields;
- emits no raw traceback/source on failure;
- records its post-run `sys.modules` closure so the evaluator can reject a
  quality import;
- returns ordinary public output only in the transient frame; it never opens a
  run artifact or log path.

The evaluator owns profile iteration and sends no case gate/profile/target data.
This is a separation contract, not a claim of filesystem confinement.

### Step 3: Implement evaluator runner

The runner:

1. in role mode, resolves only the sealed ordinary query/options and validates
   source/index identity; it does not resolve target/variant gold;
2. invokes the worker;
3. validates the transient worker schema in memory, canonicalizes and hashes
   public output/error bytes, derives source-free public projections plus one
   `MaterializedContentCommitment v1` per content-bearing result, anchor, or
   ContextPack excerpt, and prevents the raw frame from being logged or
   persisted; `ContextItem` has no content commitment because it has no public
   content field;
4. validates work/leaves and writes only the strict source-free `role_run`;
5. after all six role files are sealed, finalization mode resolves gold from
   exact Git blobs, recomputes canonical full-line commitments, and joins
   alternatives to public projections/leaves; a range alone never proves
   target/literal coverage;
6. runs frozen variant finalization;
7. computes metrics, per-variant diagnostic reasons, and separate vote groups;
8. runs oracles after actual output is immutable;
9. aggregates the route decision.

Product output cannot supply any derived result.

On cancellation, declared timeout, malformed/oversized frame, or parent error,
the runner closes stdin, terminates the process group, waits the frozen
monotonic grace interval, kills the group if needed, and always reaps it. It
validates/hashes bounded stderr only in memory. It may record partial hashes,
recheck clean worktrees/prepared repositories, or write a disposition only
after reap; tests use a child-spawning fake worker and prove no descendant or
mutable partial output survives.
Exceeding the frozen worker deadline always seals non-retryable
`declared_timeout` after reap; only independent host evidence can select an
external reason.

### Step 4: Freeze evaluator closure

`p7a-freeze-closure` writes a sorted exact path-to-Git-blob manifest covering:

- top-level stdlib worker bootstrap, transient request/frame validators,
  content-commitment builder, and observer enums;
- artifact schema and canonical JSON;
- case/provenance/target/exact-identifier/gold/feasible-cover resolvers;
- surface chains, selection projection, progress vector, finalizer, terminal
  reason map, metrics, oracles, thresholds, and decision;
- attempt/review-round allocator and validator,
  disposition/lineage/definition-effect/finding-scope builders,
  review-draft revision/candidate/evidence projection, final-tree verifier, and
  publisher;
- the literal `P7A_PUBLICATION_REGION_REGISTRY_V1`, marker parser, and registry
  hash derivation;
- fixed fixtures/profile/source, label-review, and witness manifests;
- the evaluator import closure plus one statically resolved worker-import
  allowlist for every `(behavior-disabled | instrumentation-disabled |
  instrumentation-enabled, case ID, surface)` key.

The closure excludes its own output, contains one domain-separated digest, and
is created at a content-addressed path without replacing an older closure. Any
changed local dependency invalidates it. It also contains two disjoint closed
maps:

- `contract_governed_blobs`: the two reviewed payload identities;
  `p7a_contracts.py`, `p7a_evaluator.py`, artifact schema,
  `tests/test_p7a_contracts.py`,
  `tests/fixtures/p7a_retrieval_quality/contracts.json`, the Task 1
  `docs/benchmarks/p7a/README.md` marker template, Task 2 schema examples and
  case/gold/profile/finalizer/oracle/decision tests, and every Task 3
  source-pin/selection/case/profile/gold/label/witness input; and
- `corrective_implementation_paths`: only Task 4 behavior-neutral product hooks
  and compatibility tests plus Task 5 worker/CLI/runner/lifecycle/publisher
  implementations and runner/attempt/publication tests.

The maps are mutually exclusive; an unlisted semantic path fails closure
validation. For the current reservation only, a
controlled role-run guard refuses to run if the sealed attempt is absent, if
its role directory predates that attempt's closure/seal, or if any
path/blob/import differs. Each single-case actual closure must be a subset of
its exact keyed allowlist, contain required roots, and exclude
`quality`/evaluator modules; A/B closures must be exactly equal for the same
key. Different cases/surfaces and behavior/instrumentation classes need not
have equal closures. Historical attempts retain and disclose their own closure
hashes and do not trip this current-attempt guard.

Contract-amendment mode returns to every owning **code** checkpoint affected by
its governed delta: Task 1 for schema/registry/contracts and the exact contract
test/fixture/benchmark-README marker template, and Task 2 for evaluator,
profile-validation, gold-validation, finalizer, oracle, metric, and decision
semantics plus their tests. Each affected checkpoint uses a contiguous TDD fix
chain before a successor proof is eligible.

Task 3 selection/profile/source/gold inputs have no code checkpoint. A
data-only amendment keeps the four-checkpoint manifest and every selected test
blob unchanged, repeats Task 3 selection provenance, independent label review,
simultaneous feasible-cover, data commit, post-commit gold seal, closure,
definition-effect report, and successor-attempt construction. The verifier
rejects a stale/missing data-lineage link or any checkpoint-owned byte that
differs from the retained manifest. If validator or test semantics also change,
the amendment first extends checkpoint 1 or 2 and then rebuilds the Task 3 data
lineage. Tests exercise both successful branches and reject omitted owning
tests, illicit data-only test edits, or classification of any governed path as
corrective.

### Step 5: Implement attempt lifecycle

Commands:

```text
p7a-build-lineage-successor
p7a-next-baseline-attempt
p7a-seal-baseline-attempt
p7a-record-attempt-disposition
p7a-close-baseline-attempt
p7a-freeze-review-input
p7a-seal-review-failure
p7a-build-evidence-review
```

`p7a-build-lineage-successor` create-exclusively emits a content-addressed
candidate proof and lineage root before allocation. It proposes dispositions
but consumes none. Genesis is legal only with an empty ledger. External retry
proposes only externally retryable dispositions and proves all semantic hashes
unchanged. Corrective mode proves commit ancestry, byte-identical reviewed
payloads/gold/every governed blob, a nonempty delta wholly inside the corrective
implementation map, a contiguous TDD fix, and a changed closure; a governed,
mixed-set, docs-only, or unrelated delta fails. Contract-amendment mode binds
newly PASS-reviewed document payloads plus their excluded hash-bound review
ledgers, new gold/closure, and a strict definition-effect report over only old
sealed or partial bytes. It reports `computed` only when six old roles can be
replayed, `unavailable_no_complete_role_set` when a role is absent, or
`unavailable_incompatible_old_evidence` when all six exist but a closed
field/domain/normalization incompatibility prevents replay. Both unavailable
forms bind exact old/new compatibility manifests and make no effect claim; the
builder derives the state and rejects a caller-selected unavailable result.
`required_successor=abandon_phase` is terminal and makes `--mode auto` refuse
allocation.

`p7a-next-baseline-attempt` atomically creates the lowest unused legal ordinal
under one ledger lock. It rescans all reservations/dispositions, revalidates the
candidate proof, and publishes a fully formed temporary attempt directory by
one atomic rename to the absent final root; that reservation commit is the only
event that consumes proposed dispositions. Concurrent or orphan candidate
proofs have no ledger effect and cannot authorize a role. The caller cannot
supply `a01` or another ordinal. It fails closed when `a01` through `a99` are
occupied and never wraps or reuses an ordinal. It writes only
`reservation.json`; a pre-rename crash leaves an ignored non-ordinal temporary
root, while a post-rename crash leaves a complete reservation. After
repository/index preparation, `p7a-seal-baseline-attempt` create-exclusively writes
`attempt.json`, binding the reservation, actual six-repository identities,
runtime/environment, gold, TDD manifest, content-addressed closure, and lineage
root before any role run.

`p7a-record-attempt-disposition` create-exclusively writes
`attempt-disposition.json` against the latest reservation, sealed attempt, or
complete predecessor. The only `retry_authorized=true` reasons are:

```text
runner_startup_external
host_signal_external
storage_failure_external
host_resource_exhaustion_external
```

All other closed reasons are non-retryable:

```text
implementation_invalid
contract_invalid
provenance_invalid
repeat_invalid
neutrality_invalid
audit_invalid
quality_invalid
decision_invalid
review_rejected
manual_cancelled
declared_timeout
undeclared_timeout
```

They set `retry_authorized=false` and
`required_successor=corrective_commit | reviewed_contract_amendment |
abandon_phase`. A review rejection binds `complete.json`,
the selected round's `review-candidate.json`, and all three strict reviewer
records, permanently making that complete route ineligible. This branch rejects
an all-`review_draft_only` finding set, which must use a round disposition
instead. Pre-seal disposition binds the reservation; post-seal binds
`attempt.json`; post-completion binds `complete.json`.

A same-commit retry before `complete.json` may occur only when the disposition
has one of the four external reasons, independent host evidence, last completed
step/case, partial-byte hashes, and UTC, and an `external_retry` successor proof
proposes it; the next locked reservation consumes it. The next attempt creates
fresh repositories and reads no partial
run byte. Gold joining/finalization is forbidden until all six roles are
complete and sealed, so a partial infrastructure attempt has no route result.

`host_signal_external` requires an externally attributable signal plus a
matching host/supervisor record. A worker exception, traceback, nonzero exit,
abort, or unexplained crash is an implementation failure.

The frozen worker deadline maps only to non-retryable `declared_timeout`; it
cannot be relabeled as a host failure. Manual cancellation, declared or
undeclared timeout, schema/provenance/repeat/neutrality/
audit/quality/decision/review failure cannot authorize another ordinal on the
same bytes. After `complete.json`, an infrastructure interruption resumes the
same attempt from byte-identical review/publication inputs and never allocates
a new ordinal. Once promote starts, signal/storage interruption uses only
same-receipt continuation; receipt/destination mismatch writes a
non-retryable `contract_invalid` disposition. The publisher selects the lowest
eligible complete ordinal, rejects any complete attempt with a disposition,
requires exactly one disposition for every earlier abandoned root and exactly
one successor consumption where required, and audits/discloses superseded
corrective lineages.

### Step 6: Implement two-phase publication

`p7a-publish` has mutually exclusive modes:

```text
prepare
promote
```

Prepare:

- consumes the four canonical artifact inputs;
- validates each exact `p7a-artifacts-v1` branch and the whole set before
  writing;
- creates an attempt-local staging tree and receipt;
- writes nothing under tracked destinations.

Promote:

- requires the reviewed set hash and evidence-review artifact;
- validates all five bytes first;
- requires every tracked destination absent or byte-identical from an
  interrupted same receipt;
- create-exclusively writes in one frozen order and journals completed paths;
- refuses changed replacement.

Because ordinary filesystems do not provide a five-file transaction, this is a
recoverable create-only promotion, not a claim of multi-file atomicity. Replaying
the exact same receipt verifies existing bytes and continues missing paths in
the same attempt. It is not an attempt failure or a reason to allocate a new
ordinal.

### Step 7: Green and protected gates

```bash
p7a_run_default "$P7A_REPO_ROOT" -m pytest -q \
  tests/test_p7a_runner.py \
  tests/test_p7a_attempts.py \
  tests/test_p7a_publish.py \
  tests/test_quality_cli.py \
  tests/test_p7a_contracts.py \
  tests/test_p7a_finalize.py \
  tests/test_p7a_oracle.py \
  tests/test_p7a_decision.py \
  tests/test_p7a_audit.py
```

### Step 8: Stage and commit

```bash
git add \
  src/context_search_tool/_p7a_worker.py \
  src/context_search_tool/quality/__main__.py \
  src/context_search_tool/quality/p7a_runner.py \
  src/context_search_tool/quality/p7a_lifecycle.py \
  tests/test_p7a_runner.py \
  tests/test_p7a_attempts.py \
  tests/test_p7a_publish.py \
  tests/test_quality_cli.py
test -z "$(git diff --name-only)"
test -z "$(git ls-files --others --exclude-standard)"
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-tdd-green \
  --pending .quality/p7a-tdd/tdd-checkpoint-4.pending.json \
  --green-root-mode staged-tree \
  --reject-unstaged-and-relevant-untracked \
  --staged-tree "$(git write-tree)" \
  --output .quality/p7a-tdd/tdd-checkpoint-4.json
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-validate-artifact \
  --kind tdd_record \
  --input .quality/p7a-tdd/tdd-checkpoint-4.json \
  --staged-tree "$(git write-tree)"
git diff --cached --check
git diff --cached --name-only
git commit -m "feat: add p7a baseline evidence runner"
export P7A_INSTRUMENTATION_COMMIT="$(git rev-parse HEAD)"
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality p7a-freeze-tdd-manifest \
  --records .quality/p7a-tdd \
  --implementation-commit "$P7A_INSTRUMENTATION_COMMIT" \
  --output-root .quality/p7a-tdd/manifests
export P7A_TDD_MANIFEST="$(
  p7a_run_default "$P7A_REPO_ROOT" \
    -m context_search_tool.quality p7a-print-tdd-manifest-path \
    --root .quality/p7a-tdd/manifests
)"
p7a_run_default "$P7A_REPO_ROOT" \
  -m context_search_tool.quality.p7a_contracts p7a-validate-artifact \
  --kind tdd_manifest \
  --input "$P7A_TDD_MANIFEST"
```

**Commit:** `feat: add p7a baseline evidence runner`

## Task 6: Run, Review, And Publish The P7A Route

**Purpose:** Produce the only P7A terminal result from one immutable, reviewed
baseline attempt.

**Files:**

- `docs/benchmarks/p7a/baseline/baseline-identity.json`
- `docs/benchmarks/p7a/baseline/stage-summary.json`
- `docs/benchmarks/p7a/baseline/oracle-summary.json`
- `docs/benchmarks/p7a/baseline/route-decision.json`
- `docs/benchmarks/p7a/baseline/evidence-review.json`
- `docs/benchmarks/p7a/README.md`
- `README.md`
- `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
- `docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md`

No production, test, fixture, schema, gold, or threshold file may change in
this task.

### Step 1: Create isolated worktrees

```bash
export P7A_WORKTREE_ROOT="$P7A_REPO_ROOT/.quality/p7a-worktrees"
mkdir -p "$P7A_WORKTREE_ROOT"
export P7A_INSTRUMENTATION_SHORT="${P7A_INSTRUMENTATION_COMMIT:0:12}"
export P7A_BEHAVIOR_WORKTREE="$P7A_WORKTREE_ROOT/behavior-74aae0abe3df"
export P7A_INSTRUMENTATION_WORKTREE="$P7A_WORKTREE_ROOT/instrumentation-$P7A_INSTRUMENTATION_SHORT"

if test ! -e "$P7A_BEHAVIOR_WORKTREE"; then
  git worktree add --detach "$P7A_BEHAVIOR_WORKTREE" \
    74aae0abe3dff685282fbcc785f7a9b3532cbbe6
fi
if test ! -e "$P7A_INSTRUMENTATION_WORKTREE"; then
  git worktree add --detach "$P7A_INSTRUMENTATION_WORKTREE" \
    "$P7A_INSTRUMENTATION_COMMIT"
fi
test "$(git -C "$P7A_BEHAVIOR_WORKTREE" rev-parse HEAD)" = \
  74aae0abe3dff685282fbcc785f7a9b3532cbbe6
test "$(git -C "$P7A_INSTRUMENTATION_WORKTREE" rev-parse HEAD)" = \
  "$P7A_INSTRUMENTATION_COMMIT"
test -z "$(git -C "$P7A_BEHAVIOR_WORKTREE" status --porcelain)"
test -z "$(git -C "$P7A_INSTRUMENTATION_WORKTREE" status --porcelain)"
```

The instrumentation path is commit-keyed. A corrective commit therefore gets a
new worktree; an external retry may reuse only the same exact clean detached
code worktrees, while its prepared repository/index sets are always new.

### Step 2: Create the post-commit gold seal and evaluator closure

From the instrumentation worktree:

```bash
export P7A_GOLD_SEAL="$(
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-seal-gold \
    --gold-freeze-commit "$P7A_GOLD_FREEZE_COMMIT" \
    --inputs docs/benchmarks/p7a/gold/gold-freeze-inputs.json \
    --output-root "$P7A_REPO_ROOT/.quality/p7a-seals/gold" \
    --print-created-or-identical-path
)"

export P7A_EVALUATOR_CLOSURE="$(
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-freeze-closure \
    --instrumentation-commit "$P7A_INSTRUMENTATION_COMMIT" \
    --gold-seal "$P7A_GOLD_SEAL" \
    --tdd-manifest "$P7A_TDD_MANIFEST" \
    --artifact-schema docs/benchmarks/p7a/schemas/p7a-artifacts-v1.json \
    --label-review docs/benchmarks/p7a/gold/label-review.json \
    --feasible-cover docs/benchmarks/p7a/gold/feasible-cover-witness.json \
    --output-root "$P7A_REPO_ROOT/.quality/p7a-seals/evaluator-closures" \
    --print-created-or-identical-path
)"

export P7A_LINEAGE_PROOF="$(
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-build-lineage-successor \
    --mode auto \
    --attempts-root "$P7A_REPO_ROOT/.quality/p7a-attempts" \
    --behavior-commit 74aae0abe3dff685282fbcc785f7a9b3532cbbe6 \
    --instrumentation-commit "$P7A_INSTRUMENTATION_COMMIT" \
    --gold-seal "$P7A_GOLD_SEAL" \
    --evaluator-closure "$P7A_EVALUATOR_CLOSURE" \
    --tdd-manifest "$P7A_TDD_MANIFEST" \
    --design \
    "$P7A_PUBLICATION_WORKTREE/docs/superpowers/specs/2026-07-25-p7a-retrieval-quality-attribution-route-selection-design.md" \
    --plan \
    "$P7A_PUBLICATION_WORKTREE/docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md" \
    --definition-effects-root \
    "$P7A_REPO_ROOT/.quality/p7a-seals/definition-effects" \
    --output-root "$P7A_REPO_ROOT/.quality/p7a-seals/lineage" \
    --print-created-or-identical-path
)"
test -f "$P7A_GOLD_SEAL"
test -f "$P7A_EVALUATOR_CLOSURE"
test -f "$P7A_LINEAGE_PROOF"
```

All three outputs are ignored, content-addressed, create-only, and later bound
by the sealed attempt and tracked baseline identity. `--mode auto` is
fail-closed: it selects genesis only for an empty ledger and otherwise derives
the sole legal mode from unconsumed dispositions; the caller cannot choose a
more favorable successor. Creating `P7A_LINEAGE_PROOF` does not consume a
disposition; only Step 3's reservation transaction can do so. Historical
attempts may
exist. The guard is scoped to the subsequently allocated reservation: no role
directory below that new root may exist before its `attempt.json`, which binds
this already frozen closure.

### Step 3: Open the lowest unused attempt

```bash
export P7A_ATTEMPT_ROOT="$(
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-next-baseline-attempt \
    --attempts-root "$P7A_REPO_ROOT/.quality/p7a-attempts" \
    --behavior-commit 74aae0abe3dff685282fbcc785f7a9b3532cbbe6 \
    --instrumentation-commit "$P7A_INSTRUMENTATION_COMMIT" \
    --gold-seal "$P7A_GOLD_SEAL" \
    --evaluator-closure "$P7A_EVALUATOR_CLOSURE" \
    --tdd-manifest "$P7A_TDD_MANIFEST" \
    --lineage-proof "$P7A_LINEAGE_PROOF" \
    --print-created-root
)"
export P7A_ATTEMPT_ID="${P7A_ATTEMPT_ROOT##*/}"
printf '%s\n' "$P7A_ATTEMPT_ID" |
  rg -q '^b-[0-9a-f]{12}-a(0[1-9]|[1-9][0-9])$'
test -f "$P7A_ATTEMPT_ROOT/reservation.json"
test ! -e "$P7A_ATTEMPT_ROOT/attempt.json"
test ! -e "$P7A_ATTEMPT_ROOT/runs"
```

The command owns ordinal selection and create-exclusive root creation. It
holds the ledger lock, scans and validates every earlier ledger entry, rechecks
the proposed proof, and atomically publishes the complete reservation
directory before returning the created root. That single commit consumes the
proof's proposed dispositions. A competing allocator must observe the
consumption and fail or build a new proof; orphan proofs are ignored. The
caller cannot request, skip, or reuse an ordinal. A reservation is not yet
eligible to run or finalize.

### Step 4: Prepare six byte-identical repository sets

```text
repos/behavior-a
repos/behavior-b
repos/instrumentation-disabled-a
repos/instrumentation-disabled-b
repos/instrumentation-enabled-a
repos/instrumentation-enabled-b
```

`p7a-prepare-attempt-repos`:

- creates destinations only;
- verifies pinned commits/subtree object;
- creates indexes with frozen options;
- records source/index hashes;
- proves normalized equality across all six sets;
- performs no retrieval.

```bash
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-prepare-attempt-repos \
  --reservation "$P7A_ATTEMPT_ROOT/reservation.json" \
  --sources tests/fixtures/p7a_retrieval_quality/sources.json \
  --destination "$P7A_ATTEMPT_ROOT/repos" \
  --identity-output "$P7A_ATTEMPT_ROOT/prepared-repositories.json"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-seal-baseline-attempt \
  --reservation "$P7A_ATTEMPT_ROOT/reservation.json" \
  --prepared-repositories "$P7A_ATTEMPT_ROOT/prepared-repositories.json" \
  --gold-seal "$P7A_GOLD_SEAL" \
  --evaluator-closure "$P7A_EVALUATOR_CLOSURE" \
  --tdd-manifest "$P7A_TDD_MANIFEST" \
  --lineage-proof "$P7A_LINEAGE_PROOF" \
  --output "$P7A_ATTEMPT_ROOT/attempt.json"

test -f "$P7A_ATTEMPT_ROOT/attempt.json"
test ! -e "$P7A_ATTEMPT_ROOT/runs"
```

`attempt.json` is create-only and binds the actual prepared source/index,
runtime, sanitized environment-presence, reservation, gold, TDD manifest,
closure, and lineage-root hashes. Every subsequent command validates that
hash.

### Step 5: Run the six-role matrix

Every role uses the complete eighteen-case `p7a_route` profile.

```bash
for role in \
  behavior-a \
  behavior-b \
  instrumentation-disabled-a \
  instrumentation-disabled-b \
  instrumentation-enabled-a \
  instrumentation-enabled-b
do
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-run-role \
    --attempt "$P7A_ATTEMPT_ROOT/attempt.json" \
    --role "$role" \
    --behavior-root "$P7A_BEHAVIOR_WORKTREE" \
    --instrumentation-root "$P7A_INSTRUMENTATION_WORKTREE" \
    --repos "$P7A_ATTEMPT_ROOT/repos/$role" \
    --fixture "$P7A_INSTRUMENTATION_WORKTREE/tests/fixtures/p7a_retrieval_quality/p7a_route.json" \
    --profile "$P7A_INSTRUMENTATION_WORKTREE/tests/fixtures/p7a_retrieval_quality/p7a_profile.json" \
    --output "$P7A_ATTEMPT_ROOT/runs/$role.json"
done
```

The role validator determines product root and audit mode from the closed role;
CLI callers cannot provide contradictory flags. Every explore request uses the
same closure-bound deterministic clock sequence. Each output validates as the
strict source-free `role_run` artifact before it is sealed create-only. Raw
public output exists only in the validated in-memory worker frame; the artifact
stores its canonical SHA-256/byte length plus source-free path/range/order and
logical-line content-commitment projections.

After every role, verify worktree commit/clean state and prepared source/index
hashes.

### Step 6: Prove neutrality and repeatability

```bash
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-prove-neutrality \
  --attempt "$P7A_ATTEMPT_ROOT/attempt.json" \
  --runs "$P7A_ATTEMPT_ROOT/runs" \
  --output "$P7A_ATTEMPT_ROOT/proofs/baseline-neutrality.json"
```

Require equality of canonical transient public-output/error SHA-256 and byte
length, source-free public projections including content commitments, and work
with no timing-pointer normalization; exact enabled-leaf repeat equality; the
expected audit-presence matrix; and zero residual observer state. For each
`(role class, case ID, surface)`, the actual product-module closure must be a
subset of its frozen keyed allowlist, contain required roots, exclude
`quality`/evaluator modules, and equal its same-key A/B repeat exactly. Do not
compare closures from different cases/surfaces or require behavior and
instrumentation closures to equal; the declared instrumentation observer delta
is explicit.

### Step 7: Finalize actual stages, oracles, and route

```bash
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-finalize-baseline \
  --attempt "$P7A_ATTEMPT_ROOT/attempt.json" \
  --neutrality "$P7A_ATTEMPT_ROOT/proofs/baseline-neutrality.json" \
  --canonical-run "$P7A_ATTEMPT_ROOT/runs/instrumentation-enabled-a.json" \
  --repeat-run "$P7A_ATTEMPT_ROOT/runs/instrumentation-enabled-b.json" \
  --stage-output "$P7A_ATTEMPT_ROOT/canonical/stage-summary.json" \
  --oracle-output "$P7A_ATTEMPT_ROOT/canonical/oracle-summary.json" \
  --decision-output "$P7A_ATTEMPT_ROOT/canonical/route-decision.json"
```

The command:

- recomputes all derived fields;
- refuses to join gold until all six sealed role files exist;
- recomputes canonical full-line commitments from pinned Git blobs and rejects
  range-only, partial-line, or cross-segment target coverage;
- verifies exact repeat leaves;
- validates first-failure completeness, complete-variant progress/ties,
  per-variant diagnostic reasons, and separate mixed voting;
- binds case-selection provenance;
- computes confirmatory-only unit/case counts and exact shares/leads and refuses
  a global route whose group is not independently supported by that slice;
- recomputes the feasible-cover identity and computes complete-variant,
  reason-mapped stage-boundary oracle headroom after actual output, without
  downstream replay for file/span interventions;
- emits one closed route and next action;
- contains no source text or local path.

### Step 8: Run protected and performance gates

```bash
mkdir -p "$P7A_ATTEMPT_ROOT/protected"
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" -m pytest -q -rsxX \
  -p no:cacheprovider \
  --junitxml "$P7A_ATTEMPT_ROOT/protected/full-suite.xml"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" -m pytest -q \
  tests/test_p7a_contracts.py \
  tests/test_p7a_cases.py \
  tests/test_p7a_gold.py \
  tests/test_p7a_profile.py \
  tests/test_p7a_finalize.py \
  tests/test_p7a_oracle.py \
  tests/test_p7a_decision.py \
  tests/test_p7a_audit.py \
  tests/test_p7a_runner.py \
  tests/test_p7a_attempts.py \
  tests/test_p7a_publish.py \
  tests/test_quality_p2.py \
  tests/test_quality_p4.py \
  tests/test_quality_p5.py
```

Prepare the existing pinned P6 smoke workload and run the unchanged paired
harness with real clocks and audit disabled:

```bash
mkdir -p "$P7A_ATTEMPT_ROOT/performance"
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  scripts/p6_benchmark.py generate \
  --tier smoke \
  --manifest tests/fixtures/p6_performance/workload_manifest.json \
  --output "$P7A_ATTEMPT_ROOT/performance/pristine-smoke"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  scripts/p6_benchmark.py paired \
  --baseline-root "$P7A_BEHAVIOR_WORKTREE" \
  --final-root "$P7A_INSTRUMENTATION_WORKTREE" \
  --repo "$P7A_ATTEMPT_ROOT/performance/pristine-smoke" \
  --manifest tests/fixtures/p6_performance/workload_manifest.json \
  --pairs 30 \
  --operation-set protected_small_entry_comparable \
  --output "$P7A_ATTEMPT_ROOT/performance/p6-paired.json"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-build-performance-proof \
  --paired "$P7A_ATTEMPT_ROOT/performance/p6-paired.json" \
  --neutrality "$P7A_ATTEMPT_ROOT/proofs/baseline-neutrality.json" \
  --output "$P7A_ATTEMPT_ROOT/proofs/paired-performance.json"
```

Require the existing P6 validator and calibration to pass, every `query_*` and
`explore_p4_bounded` median ratio `<=1.03`, and existing explore call ceilings.
For each of those protected operations and each side, recompute
`max_extra_peak_bytes` as the maximum supported raw sample
`rss.extra_peak_bytes`, after verifying each value equals
`max(0, peak_bytes - empty_harness_peak_bytes)`. Require a positive baseline
maximum and the integer comparison
`100 * final_max_extra_peak_bytes <= 102 * baseline_max_extra_peak_bytes` for
every operation; zero denominator, missing/unsupported side, or invalid sample
fails the proof. Bind the sorted
`(operation_id, pair_id, side, order_index, case_id)` sample IDs and every
per-operation maximum. The proof also binds exact ContextPack output hashes,
source-free projections, and work/item/excerpt/byte counters from neutrality.
There is no standalone context latency or p95 gate because the existing P6
paired harness supplies neither.

### Step 9: Close attempt and prepare publication

```bash
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-seal-baseline-identity \
  --attempt "$P7A_ATTEMPT_ROOT/attempt.json" \
  --tdd-manifest "$P7A_TDD_MANIFEST" \
  --lineage-proof "$P7A_LINEAGE_PROOF" \
  --neutrality "$P7A_ATTEMPT_ROOT/proofs/baseline-neutrality.json" \
  --performance "$P7A_ATTEMPT_ROOT/proofs/paired-performance.json" \
  --stage-summary "$P7A_ATTEMPT_ROOT/canonical/stage-summary.json" \
  --oracle-summary "$P7A_ATTEMPT_ROOT/canonical/oracle-summary.json" \
  --route-decision "$P7A_ATTEMPT_ROOT/canonical/route-decision.json" \
  --output "$P7A_ATTEMPT_ROOT/canonical/baseline-identity.json"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-close-baseline-attempt \
  --attempt "$P7A_ATTEMPT_ROOT/attempt.json" \
  --neutrality "$P7A_ATTEMPT_ROOT/proofs/baseline-neutrality.json" \
  --performance "$P7A_ATTEMPT_ROOT/proofs/paired-performance.json" \
  --canonical-dir "$P7A_ATTEMPT_ROOT/canonical" \
  --protected-dir "$P7A_ATTEMPT_ROOT/protected" \
  --output "$P7A_ATTEMPT_ROOT/complete.json"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-publish \
  --mode prepare \
  --attempt "$P7A_ATTEMPT_ROOT/complete.json" \
  --baseline-identity "$P7A_ATTEMPT_ROOT/canonical/baseline-identity.json" \
  --stage-summary "$P7A_ATTEMPT_ROOT/canonical/stage-summary.json" \
  --oracle-summary "$P7A_ATTEMPT_ROOT/canonical/oracle-summary.json" \
  --route-decision "$P7A_ATTEMPT_ROOT/canonical/route-decision.json" \
  --staging-root "$P7A_ATTEMPT_ROOT/publish-set" \
  --receipt "$P7A_ATTEMPT_ROOT/publish-set-receipt.json"
```

`baseline-identity.json` is created only after protected and performance proofs
exist. It binds the strict role-run set, gold/witness/label review, four-record
TDD manifest, evaluator closure, neutrality, performance, and the other three
canonical artifact hashes plus the lineage root. The publisher rejects a
free-form or pre-performance identity.

The hash DAG is directional and acyclic: reservation points to the already
created lineage-successor proof/root; role/proof artifacts point to the sealed
attempt; baseline identity points to the lineage root, those proofs, and
canonical summaries; the prepare receipt points to baseline identity and
prepared bytes; each review round points only to the complete attempt and prior
closed round, the review-draft manifest points to its round and create-only
snapshots, and the review-draft revision manifest points to the current
manifest plus, only for `draft_revision`, the immediately preceding
candidate/disposition and prior manifest; `initial` points to no candidate or
disposition. The review candidate points to the current manifests and receipt;
reviewer records
point to the candidate/lineage; a failed draft-only round disposition points to
those reviews, while evidence review points to the final PASS candidate, every
prior round disposition/revision manifest, receipt, reviews, TDD manifest, and
lineage; and the final projection receipt points to
evidence/generated-plan bytes. No manifest contains a future candidate hash and
no earlier artifact points to a later one. The excluded Implementation Record
does not contain its own hash, the final projection-receipt hash, or the final
commit hash.

Confirm tracked baseline destinations are still absent.

### Step 10: Draft documentation against the prepared hashes

In `P7A_PUBLICATION_WORKTREE`, update:

- `docs/benchmarks/p7a/README.md` with methodology and artifact links;
- root `README.md` with the benchmark-scoped outcome;
- roadmap with P7A route-selection completion and the selected next design
  subject;
- this plan's excluded Implementation Record template, with all result/evidence
  fields filled except the three reviewer-record hashes, verdict/counts,
  and evidence-review hash.

The authored bytes must use the exact Task 1 registry markers. Keep the existing
`p7a_benchmark_readme` and `p7a_plan_implementation_record` pairs and change
only their interiors. Add exactly one `p7a_root_readme` pair around the new root
README block and one `p7a_roadmap` pair around the new roadmap block. No other
P7A marker prefix is allowed. Before freezing, the registry validator must
resolve all four pairs and print the registry hash plus each
`(destination, region ID, start, end, region SHA-256)`.

Do not claim retrieval quality is solved. Do not begin the next mechanism.
The publication worktree, whether original or corrective, must own the exact
reviewed implementation parent:

```bash
test "$(git -C "$P7A_PUBLICATION_WORKTREE" rev-parse HEAD)" = \
  "$P7A_INSTRUMENTATION_COMMIT"
```

Freeze, validate, and atomically publish one complete review-input bundle:

```bash
export P7A_REVIEW_ROUND_ROOT="$(
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-freeze-review-input \
    --attempt "$P7A_ATTEMPT_ROOT/complete.json" \
    --rounds-root "$P7A_ATTEMPT_ROOT/review-rounds" \
    --candidate-root "$P7A_ATTEMPT_ROOT/review-input-candidates" \
    --repo-root "$P7A_PUBLICATION_WORKTREE" \
    --tdd-manifest "$P7A_TDD_MANIFEST" \
    --lineage-proof "$P7A_LINEAGE_PROOF" \
    --receipt "$P7A_ATTEMPT_ROOT/publish-set-receipt.json" \
    --file docs/benchmarks/p7a/README.md \
    --file README.md \
    --file roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md \
    --file \
    docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md \
    --print-created-root
)"
test -f "$P7A_REVIEW_ROUND_ROOT/review-round.json"
test -f "$P7A_REVIEW_ROUND_ROOT/review-draft-manifest.json"
test -f "$P7A_REVIEW_ROUND_ROOT/review-draft-revision-manifest.json"
test -f "$P7A_REVIEW_ROUND_ROOT/review-candidate.json"
```

The command holds one ledger lock, rescans all published rounds, selects the
lowest unused `r01` through `r99`, and constructs everything under a unique
unnumbered same-filesystem candidate root. `r01` binds no predecessor. A later
round is legal only when the immediately preceding round has exactly one
`review_draft_rejected` disposition; the new round binds it and keeps every
non-draft evidence hash identical. The command never skips or wraps an ordinal.
Every persisted intra-bundle path is bundle-relative; the temporary candidate
directory name enters no artifact or digest.
It loads the literal registry only from the reviewed `p7a_contracts.py` blob
bound by the TDD manifest/evaluator closure; there is no caller-supplied region
manifest or heuristic discovery.

Inside the unpublished root it creates, in dependency order:

1. the strict round record;
2. four byte-for-byte draft snapshots and their strict draft manifest;
3. the strict review-draft revision manifest; and
4. the strict review candidate.

The draft manifest records ordered repository-relative destination, byte
length, SHA-256, and create-only bundle-relative snapshot path tuples. Its
`draft_set_id` uses only ordered `(destination, byte length, SHA-256)` content
tuples; it excludes round and snapshot paths. It contains no future candidate
hash or absolute source path. The builder rejects tracked or non-ignored
untracked changes outside the four declared draft paths.

For `r01`, the revision manifest emits `revision_kind=initial`, binds the
current content-set ID, and forbids predecessor/delta fields. A later
`revision_kind=draft_revision` dereferences the immediately preceding
disposition/candidate and compares prior/current frozen snapshots using stable
marker-bound regions. It requires:

- distinct previous/current content-set IDs;
- byte-identical ordered outside-region projections for every draft;
- a nonempty canonical ordered set of byte replacement hunks and its
  domain-separated digest; each hunk binds destination/region ID,
  previous/current region-relative intervals, and before/after length/SHA-256;
- unchanged unique marker bytes and stable region IDs; and
- one resolution mapping for every failed draft-only canonical finding identity
  to at least one hunk whose prior interval overlaps its finding reference, or
  whose zero-width insertion point lies inside or on that reference's boundary.

The frozen byte-diff algorithm minimizes unit-cost byte insertions/deletions,
then chooses the lexicographically least full operation sequence by
`(previous offset, current offset, operation kind, unsigned byte)` with delete
before insert. It coalesces adjacent operations and requires that applying the
ordered non-overlapping hunks exactly reproduce every current region.

The review candidate binds:

- the four prepared artifact hashes and publish-set receipt;
- the frozen TDD manifest and all ordered checkpoint/fix record hashes;
- the lineage root/successor proof, every consumed disposition, and any
  definition-effect report;
- the review-round record, strict review-draft and revision manifests,
  content-only `draft_set_id`, and exact hashes of all four snapshots;
- closed P7A publication regions for each draft, each with a stable
  registry-defined `publication_region_id`, registry version/hash, exact
  opening/closing marker pair, current `[start,end)` byte interval, byte length,
  and SHA-256; the plan exposes only the marked interior of its excluded
  Implementation Record;
- the exact nine-path final Task 6 manifest;
- the evaluator-closure blob that implements the only legal post-review
  projection; and
- placeholder names/types for only the reviewer/evidence fields listed above.

The builder rejects any other placeholder, changed Task 6 path, same-byte or
snapshot-relocation-only revision, unreferenced/out-of-region edit, changed or
missing marker, missing finding mapping, stale predecessor, or invalid
candidate field before publication. It then rescans the ledger and source
draft hashes, durably flushes the candidate files/directories, atomically
renames the complete candidate directory to the absent numbered root, and
durably flushes the rounds parent. Validation failure or any pre-rename crash
leaves no numbered round and does not consume the ordinal; an unnumbered orphan is never
ledger evidence. On restart the command first validates and returns the highest
complete open bundle instead of allocating another ordinal, but only when its
attempt/TDD/lineage/receipt bindings equal the request; a mismatch fails closed.
Reviewer dispatch resumes from its frozen snapshots even if mutable draft bytes
changed. No partial numbered root can exist.

### Step 11: Run fixed-evidence three-agent review

Freeze and provide each reviewer:

```text
design review payload hash
plan review payload hash
implementation commit/tree
gold freeze commit and resolved provenance hash
label-review and feasible-cover witness hashes
publication-region registry hash
evaluator closure hash
TDD manifest hash, four base record hashes, and every contiguous fix-chain hash
lineage-root/successor-proof hash and all consumed disposition hashes
baseline attempt ID/hash
neutrality proof hash
strict role-run and full-suite/protected/paired-performance hashes
four prepared artifact hashes and publish-set hash
review-round/draft-manifest/revision-manifest/candidate hashes and exact tracked source/test/doc diff
deterministic post-review projection blob/hash
```

Review rubrics:

1. architecture: compatibility, phase boundary, no hidden product change;
2. IR/evaluation: gold, variants, attribution, oracles, selection bias, route
   math;
3. feasibility: TDD lineage, runner isolation, attempts, reproducibility,
   privacy, publication.

Each strict `agent_review` record binds the review-round, candidate, and
TDD-manifest digests plus its role, reviewer identity, verdict, and
blocker/major/minor findings. Every finding has a `local_finding_id` unique
inside that reviewer record and a nonempty closed target union:

- `publication_region_ref` binds the candidate/draft-set hashes, destination,
  stable `publication_region_id`, and a nonempty region-relative `[start,end)`
  byte interval plus the referenced slice SHA-256;
- `corrective_path_ref` binds one exact corrective-map path;
- `governed_path_ref` binds one exact governed-map path; or
- `conceptual_contract_key` binds one closed conceptual key.

Every blocker/major also states whether reviewed semantics must change. The
validator checks the references rather than trusting prose and derives
`review_draft_only`, `corrective_only`, or `governed_or_mixed`. Draft-only
requires every target to be a valid reference inside a candidate publication
region and semantics unchanged. Corrective-only requires only exact corrective
path references and semantics unchanged. Every governed, mixed-kind, unlisted
or bare path, conceptual key, invalid/cross-boundary region reference, or
semantic finding is governed-or-mixed. The evidence builder requires
pairwise-distinct invocation IDs and exactly the three closed roles. A
prose-only finding, duplicate invocation, or record over a different
round/manifest/revision/lineage is not evidence.

Unknown target discriminators, malformed hashes, and structurally invalid
objects are rejected before an `agent_review` record is sealed. Once a record
is structurally valid, a stale candidate/draft-set binding, unknown region ID,
out-of-bounds interval, wrong slice hash, or cross-boundary reference is not a
sealer error: it deterministically derives `governed_or_mixed`, so the failed
round receives an attempt disposition requiring
`reviewed_contract_amendment`.

After each review record is sealed, the builder derives every canonical finding
identity as the domain-separated digest of
`(review_role, agent_review_sha256, local_finding_id)`. The record does not
contain its own hash. Duplicate local IDs in one record reject; the same local
ID in two review records yields distinct identities. Every round disposition,
revision resolution, and final chain replay uses this canonical identity, never
the local string alone.

Any blocker or major finding fails that review round. A non-draft code/gold/
schema/decision defect requires the corresponding corrective commit/freeze and
a new eligible attempt; it cannot be called transient.

After all three records arrive, a failed round must be sealed before any
successor work. One command derives the union scope and creates exactly one of
the two output kinds:

```bash
export P7A_REVIEW_FAILURE_ACTION="$(
  p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
    -m context_search_tool.quality p7a-seal-review-failure \
    --round "$P7A_REVIEW_ROUND_ROOT/review-round.json" \
    --review-candidate "$P7A_REVIEW_ROUND_ROOT/review-candidate.json" \
    --architecture "$P7A_REVIEW_ROUND_ROOT/reviews/architecture.json" \
    --ir-evaluation "$P7A_REVIEW_ROUND_ROOT/reviews/ir-evaluation.json" \
    --feasibility "$P7A_REVIEW_ROUND_ROOT/reviews/feasibility.json" \
    --round-disposition-output \
    "$P7A_REVIEW_ROUND_ROOT/review-round-disposition.json" \
    --attempt-disposition-output \
    "$P7A_ATTEMPT_ROOT/attempt-disposition.json" \
    --print-action
)"
```

If every blocker/major is `review_draft_only`, the action is
`revise_review_drafts`: only the round disposition is created; the complete
attempt remains eligible, no baseline/TDD reruns, and the disposition binds
each failed canonical finding identity and its allowed publication-region
references. Step 10 repeats after editing only those declared regions in
`P7A_PUBLICATION_WORKTREE`; the next round's revision manifest must prove a
nonempty content change and cover every finding. All non-draft hashes remain
identical, and the next round binds the rejected round. Otherwise only the
attempt disposition is created: any
`governed_or_mixed` finding takes
precedence and derives `reviewed_contract_amendment`; otherwise at least one
`corrective_only` finding exists and derives `corrective_commit`, with any
accompanying draft-only fixes deferred to the successor attempt's new drafts.
The caller cannot choose or override the action. PASS-only input, missing roles,
a structurally corrupt/hash-mismatched review record, or two outputs fails
before any record is treated as sealed. A schema-valid but semantically invalid
region reference always takes the governed amendment path above. Same-byte,
relocation-only, stale-predecessor, and uncovered-finding successors fail in
the atomic review-input builder before any numbered round publishes and are
rechecked by the final evidence builder even when the newest round is PASS.

For `corrective_commit`, leave the rejected attempt, candidate, draft
snapshots, and reviewer records untouched. Create a fresh clean corrective
worktree at the rejected instrumentation commit, keyed by commit and
disposition hash. The old attempt/evidence roots are mounted or supplied
read-only; new pending/fix records use a distinct create-only corrective
evidence root. Assert zero tracked, unstaged, and non-ignored untracked changes
there before returning to the owning code checkpoint and using the closed
`--fix-ordinal/--supersedes` TDD commands. A GREEN from the dirty drafting
worktree is invalid:

```bash
export P7A_REJECTED_COMMIT_SHORT="$(
  git rev-parse --short=12 "$P7A_INSTRUMENTATION_COMMIT"
)"
export P7A_DISPOSITION_SHORT="$(
  shasum -a 256 "$P7A_ATTEMPT_ROOT/attempt-disposition.json" |
    cut -c1-12
)"
export P7A_CORRECTIVE_WORKTREE="$P7A_REPO_ROOT/.quality/p7a-worktrees/corrective/$P7A_REJECTED_COMMIT_SHORT-$P7A_DISPOSITION_SHORT"
export P7A_CORRECTIVE_TDD_ROOT="$P7A_REPO_ROOT/.quality/p7a-tdd/corrective/$P7A_REJECTED_COMMIT_SHORT-$P7A_DISPOSITION_SHORT"
export P7A_CORRECTIVE_BRANCH="codex/p7a-corrective-$P7A_REJECTED_COMMIT_SHORT-$P7A_DISPOSITION_SHORT"
test ! -e "$P7A_CORRECTIVE_WORKTREE"
if git show-ref --verify --quiet "refs/heads/$P7A_CORRECTIVE_BRANCH"; then
  exit 1
fi
git worktree add -b "$P7A_CORRECTIVE_BRANCH" \
  "$P7A_CORRECTIVE_WORKTREE" "$P7A_INSTRUMENTATION_COMMIT"
test "$(git -C "$P7A_CORRECTIVE_WORKTREE" rev-parse HEAD)" = \
  "$P7A_INSTRUMENTATION_COMMIT"
test -z "$(git -C "$P7A_CORRECTIVE_WORKTREE" status \
  --porcelain --untracked-files=all)"
test -f "$P7A_REVIEW_ROUND_ROOT/review-draft-manifest.json"
test ! -e "$P7A_CORRECTIVE_TDD_ROOT"
```

Every corrective RED/GREEN/commit command uses
`P7A_CORRECTIVE_WORKTREE`; its new evidence root is outside the rejected
attempt and absent before capture. After that focused commit:

```bash
export P7A_PREVIOUS_TDD_MANIFEST="$P7A_TDD_MANIFEST"
export P7A_INSTRUMENTATION_COMMIT="$(
  git -C "$P7A_CORRECTIVE_WORKTREE" rev-parse HEAD
)"
test "$(git rev-parse "$P7A_CORRECTIVE_BRANCH")" = \
  "$P7A_INSTRUMENTATION_COMMIT"
export P7A_PUBLICATION_WORKTREE="$P7A_CORRECTIVE_WORKTREE"
export P7A_TDD_MANIFEST="$(
  p7a_run_default "$P7A_CORRECTIVE_WORKTREE" \
    -m context_search_tool.quality p7a-freeze-tdd-manifest \
    --records "$P7A_CORRECTIVE_TDD_ROOT" \
    --implementation-commit "$P7A_INSTRUMENTATION_COMMIT" \
    --supersedes-manifest "$P7A_PREVIOUS_TDD_MANIFEST" \
    --disposition "$P7A_ATTEMPT_ROOT/attempt-disposition.json" \
    --output-root "$P7A_REPO_ROOT/.quality/p7a-tdd/manifests" \
    --print-created-or-identical-path
)"
```

Then discard no old worktree or evidence, create a new instrumentation
worktree, refreeze the evaluator closure, and run Step 2's `--mode auto`
lineage command. Its proof only proposes the failed disposition. It must choose
`corrective_commit` and prove byte-identical reviewed payloads/gold/governed
blobs plus a delta wholly inside the closed corrective set, TDD, and closure
changes. Step 3's locked reservation transaction consumes the disposition once
before a successor can run.

For `reviewed_contract_amendment`, preserve the rejected draft tree and create a
separate persistent amendment branch/worktree from the rejected
instrumentation commit:

```bash
export P7A_REJECTED_COMMIT_SHORT="$(
  git rev-parse --short=12 "$P7A_INSTRUMENTATION_COMMIT"
)"
export P7A_DISPOSITION_SHORT="$(
  shasum -a 256 "$P7A_ATTEMPT_ROOT/attempt-disposition.json" |
    cut -c1-12
)"
export P7A_AMENDMENT_BRANCH="codex/p7a-amendment-$P7A_REJECTED_COMMIT_SHORT-$P7A_DISPOSITION_SHORT"
export P7A_AMENDMENT_WORKTREE="$P7A_REPO_ROOT/.quality/p7a-worktrees/amendment/$P7A_REJECTED_COMMIT_SHORT-$P7A_DISPOSITION_SHORT"
test ! -e "$P7A_AMENDMENT_WORKTREE"
if git show-ref --verify --quiet "refs/heads/$P7A_AMENDMENT_BRANCH"; then
  exit 1
fi
git worktree add -b "$P7A_AMENDMENT_BRANCH" \
  "$P7A_AMENDMENT_WORKTREE" "$P7A_INSTRUMENTATION_COMMIT"
export P7A_PUBLICATION_WORKTREE="$P7A_AMENDMENT_WORKTREE"
test -z "$(git -C "$P7A_PUBLICATION_WORKTREE" status \
  --porcelain --untracked-files=all)"
```

Stop implementation, amend and re-review both document payloads in that
worktree, and classify the governed delta before making implementation
changes:

- a Task 1 contract/schema/registry/test/template delta extends checkpoint 1;
- a Task 2 evaluator/validator/governed-test delta, including
  `tests/test_p7a_profile.py`, extends checkpoint 2; and
- a Task 3 data-only selection/profile/source/gold delta edits no checkpoint
  test, repeats the deterministic selection-provenance authoring, independent
  label review, simultaneous feasible-cover preflight, data commit, and
  post-commit `GoldProvenanceSeal`, and retains the prior TDD manifest after
  proving every checkpoint-owned blob unchanged.

A mixed amendment performs every applicable branch. Refreeze the evaluator
closure in all cases; create a successor TDD manifest only when a checkpoint
chain changed, otherwise bind the unchanged prior manifest. Build the
definition-effect report and a new successor attempt from the amended gold and
closure. Then set `P7A_INSTRUMENTATION_COMMIT` to the amendment branch HEAD and
verify the branch points to it. Before the successor proof:

```bash
export P7A_INSTRUMENTATION_COMMIT="$(
  git -C "$P7A_AMENDMENT_WORKTREE" rev-parse HEAD
)"
test "$(git rev-parse "$P7A_AMENDMENT_BRANCH")" = \
  "$P7A_INSTRUMENTATION_COMMIT"
```

```text
p7a-build-definition-effect
  --predecessor <old reservation.json | attempt.json | complete.json>
  --old-contract <old reviewed payloads/gold/closure>
  --new-contract <new reviewed payloads/gold/closure>
  --old-attempt-root <old immutable complete-or-partial artifact set>
  --derive-comparison-status
  --assert-no-new-controlled-run
  --output <content-addressed definition-effect-report.json>
```

The builder compares exact required-field, case/unit-domain, observation-domain,
and normalization/schema manifests. It cannot accept a caller-selected
unavailable status: compatible complete evidence must be computed, missing
roles select `unavailable_no_complete_role_set`, and complete but mechanically
incompatible evidence selects `unavailable_incompatible_old_evidence` with one
closed incompatibility reason and no effect claim.

The new `--mode auto` lineage proof must choose
`reviewed_contract_amendment`, propose the disposition, and bind that report.
Step 3 consumes it only through the committed reservation. A docs-only commit
without the required reviewed contract/gold/closure transition, an unchanged
closure, a missing checkpoint fix where checkpoint-owned semantics changed, a
data-only amendment with changed selected test bytes or incomplete
selection/label/witness/gold lineage, or reuse of a consumed disposition fails
before allocation.

### Step 12: Build evidence-review record

After all three PASS on the same hashes:

```bash
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-build-evidence-review \
  --review-rounds-root "$P7A_ATTEMPT_ROOT/review-rounds" \
  --review-candidate "$P7A_REVIEW_ROUND_ROOT/review-candidate.json" \
  --tdd-manifest "$P7A_TDD_MANIFEST" \
  --lineage-proof "$P7A_LINEAGE_PROOF" \
  --receipt "$P7A_ATTEMPT_ROOT/publish-set-receipt.json" \
  --architecture "$P7A_REVIEW_ROUND_ROOT/reviews/architecture.json" \
  --ir-evaluation "$P7A_REVIEW_ROUND_ROOT/reviews/ir-evaluation.json" \
  --feasibility "$P7A_REVIEW_ROUND_ROOT/reviews/feasibility.json" \
  --evidence-output "$P7A_ATTEMPT_ROOT/publish-set/evidence-review.json" \
  --plan-template \
  "$P7A_PUBLICATION_WORKTREE/docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md" \
  --plan-output "$P7A_ATTEMPT_ROOT/final-tree/p7a-plan.md" \
  --projection-receipt \
  "$P7A_ATTEMPT_ROOT/final-tree/final-tree-projection-receipt.json"
```

The builder requires exact fixed hashes and zero blocker/major counts. It may
fill only the declared Implementation Record fields and emits a strict
`final_tree_projection_receipt` binding the evidence-review byte, generated plan
byte, every unchanged draft byte, the nine-path manifest, and the reviewed
candidate. It derives and binds the expected full Git tree OID from the exact
instrumentation parent plus those final bytes/modes. It also requires the
selected PASS round to be the highest allocated round and every earlier round
to have exactly one valid draft-only disposition.
It replays every content-only draft-set identity and revision manifest,
requires distinct adjacent IDs, nonempty permitted-region deltas,
outside-region equality, the exact registry hash/marker table, and complete
finding-resolution mappings keyed by recomputed canonical finding identities.
An identical-byte/snapshot-relocation retry, stale link, uncovered finding,
out-of-region change, other byte difference, or open round fails even if the
final reviewer records say PASS.

### Step 13: Promote reviewed artifacts

```bash
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-publish \
  --mode promote \
  --receipt "$P7A_ATTEMPT_ROOT/publish-set-receipt.json" \
  --review "$P7A_ATTEMPT_ROOT/publish-set/evidence-review.json" \
  --publication-root \
  "$P7A_PUBLICATION_WORKTREE/docs/benchmarks/p7a/baseline"

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-apply-final-projection \
  --review-candidate "$P7A_REVIEW_ROUND_ROOT/review-candidate.json" \
  --projection-receipt \
  "$P7A_ATTEMPT_ROOT/final-tree/final-tree-projection-receipt.json" \
  --generated-plan "$P7A_ATTEMPT_ROOT/final-tree/p7a-plan.md" \
  --destination \
  "$P7A_PUBLICATION_WORKTREE/docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md"
```

Promotion is recoverable create-only for the five baseline files; an identical
receipt replay continues the same attempt and is not a retry. The projection
command first requires the destination plan to equal the reviewed draft, then
replaces only its excluded Implementation Record with the generated bytes.
Verify all nine tracked bytes against the projection receipt.

### Step 14: Final diff and smoke validation

```bash
test "$(git -C "$P7A_PUBLICATION_WORKTREE" rev-parse HEAD)" = \
  "$P7A_INSTRUMENTATION_COMMIT"
git -C "$P7A_PUBLICATION_WORKTREE" diff --check
p7a_run_default "$P7A_PUBLICATION_WORKTREE" -m pytest -q \
  tests/test_p7a_contracts.py \
  tests/test_p7a_publish.py \
  tests/test_p7a_decision.py

p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-verify-final-tree \
  --repo "$P7A_PUBLICATION_WORKTREE" \
  --projection-receipt \
  "$P7A_ATTEMPT_ROOT/final-tree/final-tree-projection-receipt.json" \
  --mode worktree
```

The verifier parses tracked modifications and non-ignored untracked paths,
requires exactly the nine Task 6 `Files`, hashes each proposed final byte, and
rejects every extra path. Printing status is not a substitute.

### Step 15: Stage and commit

```bash
git -C "$P7A_PUBLICATION_WORKTREE" add \
  docs/benchmarks/p7a/baseline/baseline-identity.json \
  docs/benchmarks/p7a/baseline/stage-summary.json \
  docs/benchmarks/p7a/baseline/oracle-summary.json \
  docs/benchmarks/p7a/baseline/route-decision.json \
  docs/benchmarks/p7a/baseline/evidence-review.json \
  docs/benchmarks/p7a/README.md \
  README.md \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md \
  docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md
git -C "$P7A_PUBLICATION_WORKTREE" diff --cached --check
export P7A_REVIEWED_FINAL_TREE="$(
  git -C "$P7A_PUBLICATION_WORKTREE" write-tree
)"
test -n "$P7A_REVIEWED_FINAL_TREE"
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-verify-final-tree \
  --repo "$P7A_PUBLICATION_WORKTREE" \
  --projection-receipt \
  "$P7A_ATTEMPT_ROOT/final-tree/final-tree-projection-receipt.json" \
  --mode staged \
  --expected-tree "$P7A_REVIEWED_FINAL_TREE"
test -z "$(git -C "$P7A_PUBLICATION_WORKTREE" diff --name-only)"
test -z "$(git -C "$P7A_PUBLICATION_WORKTREE" \
  ls-files --others --exclude-standard)"
test "$(git -C "$P7A_PUBLICATION_WORKTREE" rev-parse HEAD)" = \
  "$P7A_INSTRUMENTATION_COMMIT"
git -C "$P7A_PUBLICATION_WORKTREE" \
  commit -m "docs: publish p7a route decision"
test "$(git -C "$P7A_PUBLICATION_WORKTREE" rev-parse HEAD^)" = \
  "$P7A_INSTRUMENTATION_COMMIT"
test "$(git -C "$P7A_PUBLICATION_WORKTREE" rev-parse 'HEAD^{tree}')" = \
  "$P7A_REVIEWED_FINAL_TREE"
git -C "$P7A_PUBLICATION_WORKTREE" merge-base --is-ancestor \
  "$P7A_INSTRUMENTATION_COMMIT" HEAD
p7a_run_default "$P7A_INSTRUMENTATION_WORKTREE" \
  -m context_search_tool.quality p7a-verify-final-tree \
  --repo "$P7A_PUBLICATION_WORKTREE" \
  --projection-receipt \
  "$P7A_ATTEMPT_ROOT/final-tree/final-tree-projection-receipt.json" \
  --mode commit \
  --commit "$(git -C "$P7A_PUBLICATION_WORKTREE" rev-parse HEAD)" \
  --expected-tree "$P7A_REVIEWED_FINAL_TREE"
```

Staged mode compares the exact sorted name/hash manifest, not only a count, and
requires no unstaged tracked or non-ignored untracked file. The exact-parent
assertion guarantees the published documentation commit contains the
implementation commit reviewed by the successful baseline, including a
corrective successor rather than the rejected parent. Saving the staged tree
before commit and comparing it with `HEAD^{tree}`, followed by commit-mode
receipt validation, rejects a pre-commit hook or concurrent index rewrite that
would otherwise preserve the parent while changing published bytes.

### Step 16: Stop

Report:

- route outcome and next-action label;
- evidence/review links;
- baseline attempt identity;
- full-suite/protected/performance results;
- explicit statement that no selected mechanism was implemented.

Do not create a P7B/P8 branch, spec, or code in this task.

**Commit:** `docs: publish p7a route decision`

## Verification Matrix

| contract | task | evidence |
| --- | ---: | --- |
| behavior baseline exact | 0, 6 | full suite, skip IDs, protected hashes |
| public schema unchanged | 1, 4, 6 | compatibility fixtures and neutrality |
| source selection provenance | 3, 6 | tracked manifest and route binding |
| target-bearing coherent gold | 2-3 | preflight, reviewer, Git seal |
| simultaneous surface feasibility | 2-3, 6 | witness helper/blob, review, route binding |
| source-free bounded audit | 4-6 | leaf schema, lifecycle/work tests |
| full materialized target proof | 2, 5-6 | logical-line commitments, crop/Unicode/newline tests, Git-blob replay |
| product/evaluator import isolation | 4-6 | stdlib observer and `sys.modules` proofs |
| actual carrier-lineage DAG finalization | 2, 5-6 | adjacent expansion, selector-decision, per-variant reason and vote-group proofs |
| representation-invariant metrics | 2, 6 | semantic-choice deduplication, six recall formulas, rank/result/count aggregators, strata/null tests |
| no path-order tie voting | 2, 6 | permutation and mixed tests |
| oracle upper bounds only | 2, 6 | complete-variant, reason-mapped population/budget assertions |
| benchmark dominance | 2-3, 6 | two-source, confirmatory-only reconciliation, intent/surface cohort proofs |
| pre-run evaluator closure | 5-6 | path/blob/per-case keyed import manifest and run guard |
| six-role transient-byte equality | 5-6 | deterministic clock, hashes/projections, strict source-free role-run artifacts |
| mandatory TDD lineage | 1-6 | four strict records, contiguous fixes, identical RED/GREEN test blobs and failing-node transition, frozen review-bound manifest |
| anti-cherry-pick attempts | 5-6 | non-consuming proofs, atomic reservation consumption, governed/corrective disjointness, dispositions, definition-effect states, no partial reuse |
| feasible performance claim | 6 | unchanged P6 median/per-operation RSS plus exact context byte/work |
| reviewed recoverable publication | 1, 5-6 | frozen four-entry region registry, atomic create-only review bundles, stable region refs, nonempty content-only draft revision closure, three PASS, persistent successor branch, exact-parent/exact-tree commit projection |
| unconditional P7A stop | design, 6 | roadmap/README/plan handoff |

## Known Residual Limits

- The initial eighteen-case benchmark is curated and cannot estimate production
  query frequencies.
- Confirmatory cases and two external repositories reduce but do not eliminate
  selection bias.
- Oracles use labels and prove feasible headroom, not a deployable policy.
- The worker split prevents accidental gold coupling but is not an OS security
  sandbox.
- P7A does not measure a private owner repository.
- P7A does not make fast-context a stable comparator or parity target.
- P7A makes no standalone context-latency or p95 claim; the existing P6 paired
  harness supports median query/explore and RSS evidence only.
- P6 release-grade scale/stress/churn work remains independent.

These limits must appear in the route decision and public handoff.

## Independent Plan Review Record

This section and the following Implementation Record are excluded from the
stable plan review payload. The stable `plan_review_payload_sha256` is computed
by:

1. removing the single `Status:` line; and
2. removing bytes from `## Independent Plan Review Record` up to, but not
   including, `## Stop Point`.

Any other byte change requires a new complete fixed-payload review.

### Fixed-Payload Review: PASS (Round 11)

The final candidate identities reviewed from line 1 through EOF were:

- design full SHA-256
  `7c6c37a3938a8fbeb8171e3987266489c6429039e46f43000d8874389825b42a`,
  stable payload SHA-256
  `0ca18e89be73fbb0019e90bef24a3c956dfff9a47b4755aa06764b0c6fd89a02`,
  2,146 lines, 108,973 bytes; and
- plan full SHA-256
  `c24e2d88a5b8e183a8c137314d7cac0a6e857a6b0c27a38918f45e705ac68072`,
  stable payload SHA-256
  `c2fa3c40d61be75b8814ffabdd96287451c1a841fc51fe1dd3b299fd5511afc5`,
  3,005 lines, 135,303 bytes.

| review role | reviewer | verdict | blocker | major | minor |
| --- | --- | --- | ---: | ---: | ---: |
| architecture/contract | Poincare (`/root/p7_architecture_review`) | PASS | 0 | 0 | 0 |
| IR/evaluation/gold | Peirce (`/root/p7_ir_evaluation_review`) | PASS | 0 | 0 | 0 |
| implementation/TDD/operability | Kierkegaard (`/root/p7_feasibility_review`) | PASS | 0 | 0 | 0 |

The immediately preceding fixed candidate, Round 10, had design full/payload
SHA-256 `e8edda7a79c194190fcc63fe9c28d9e2a1dcc36cb6eea7e720f8d610781ffbab` /
`9e053ac9d3ace34347e03576b6ce0d9a747f69554eb0696c6e10b96bfb8d76c4`
and plan full/payload SHA-256
`cf08c2c7b73405bce36812cdfb76c4a824d277f19713c48cbd0cce468918543a` /
`7e2fd9fd90bd9cec644e0a2e834577ed9b2f84166a67272d3f6a0e75c22c1dfa`.
All three roles returned FAIL with 0 blocker, 1 major, and 0 minor because Task
3 data amendments were assigned to a nonexistent TDD checkpoint. Round 11
closed that issue by assigning the profile validator test to checkpoint 2 from
its initial RED and making Task 3 data-only with its own complete governed-data
lineage. Each reviewer confirmed the fix and reran their full regression scope
without modifying the files.

The plan is reviewed, but implementation remains unauthorized until the user
explicitly approves and starts it.

## Implementation Record

<!-- P7A:BEGIN p7a_plan_implementation_record -->
Pending. This excluded ledger may be filled only during an explicitly
authorized implementation. It must record commits, attempt ID, exact test and
artifact hashes, reviewer verdicts, route outcome, and the final stop.
<!-- P7A:END p7a_plan_implementation_record -->

## Stop Point

This document ends at a reviewed plan.

Do not create a branch, edit production/tests/fixtures/roadmap, stage, commit,
prepare public repositories, author gold, or run P7A until:

1. the design and plan fixed payloads receive three PASS verdicts with zero
   blocker and zero major findings;
2. the review ledgers are filled without changing either payload;
3. the user approves the revised diagnostic-only P7A boundary; and
4. the user explicitly authorizes implementation.

After Task 6 later publishes the route, stop again. The selected P7B/P8
mechanism requires a new reviewed design and plan plus explicit authorization.
