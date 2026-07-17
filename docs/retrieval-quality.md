# Retrieval Quality Workflow

## Profiles

| profile | dependency | purpose |
| --- | --- | --- |
| `ci` | committed snapshots | deterministic frontend, Java, exact, and noise gates |
| `smoke` | real generic repositories | all 22 generic cases |
| `planner` | Ollama and requests checkout | repo-aware planner and genuine cross-language cases |
| `calibration_bge` | BGE and two Java repositories | all eight Java calibration cases |
| `ab_hash` | committed A/B snapshot | local embedding baseline |
| `ab_bge` | Ollama BGE-M3 | BGE candidate report |
| `p1_vector_bge` | local `bge-m3` | Phase 1 vector-only acceptance baseline |
| `p1_hybrid_bge` | local `bge-m3` and `qwen3.5:4b-mlx` | Phase 1 hybrid acceptance candidate |
| `p2_context_pack` | committed snapshots and offline `hash-v1` | deterministic ContextPack v2 acceptance |
| `p2_real_context` | explicitly prepared pinned PetClinic checkout | opt-in real-project ContextPack v2 acceptance |
| `p4_exploration` | committed snapshots and offline `hash-v1` | deterministic controlled-exploration acceptance |
| `p4_real_exploration` | explicitly prepared pinned PetClinic checkout | opt-in real-project exploration acceptance |

All commands below assume that `cst` imports `context_search_tool` from the
current checkout. Editable installs and multiple worktrees can point elsewhere,
so pin and verify the import path before producing a report:

```bash
PYTHONPATH="$PWD/src" python - <<'PY'
from pathlib import Path
import context_search_tool

expected = (Path.cwd() / "src/context_search_tool/__init__.py").resolve()
actual = Path(context_search_tool.__file__).resolve()
if actual != expected:
    raise SystemExit(f"expected {expected}, imported {actual}")
print(actual)
PY
```

Use the same Python environment as the quality command. In editable or
multi-worktree development, prefix quality commands with `PYTHONPATH="$PWD/src"`
when needed. For example, use `PYTHONPATH="$PWD/src" cst quality run ...` or
`PYTHONPATH="$PWD/src" conda run -n base cst quality run ...`. The report's
`tool.git_commit` records metadata; it does not by itself prove which checkout
Python imported.

## Fast CI Run

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ci --output .quality/ci.json --markdown .quality/ci.md
```

## Phase 2 Context Pack Acceptance

Quality cases accept exactly two `mode` values: `results` (the default raw-result
evaluation) and `context_pack`. The following fields are valid only for
`context_pack` cases:

```json
{
  "mode": "context_pack",
  "expected_context_groups": {
    "entrypoints": [{"path": "src/AppController.java"}],
    "implementations": [{"glob": "src/**/*ServiceImpl.java"}],
    "related_types": [{"contains": "Dto"}]
  },
  "expected_pack_status": "ready",
  "minimum_context_confidence": "medium",
  "expected_need_matches": [
    {
      "category": "configs_docs",
      "subject": "postgresql",
      "required": true,
      "matched": false
    }
  ],
  "maximum_pack_bytes": 65536,
  "maximum_truncated_items": 4,
  "forbidden_next_query_patterns": ["/oups", "GET\\s+/owners dto"]
}
```

`expected_context_groups` uses the six ContextPack v2 group names and the
existing `path`, `glob`, or `contains` matchers. Legal status values are
`empty`, `partial`, and `ready`; legal minimum-confidence values are `none`,
`low`, `medium`, and `high`. Each `expected_need_matches` entry is a typed tuple
of category, normalized subject, required boolean, and matched boolean; all four
must match one returned need. Budget expectations are positive/non-negative
integers, not strings. Forbidden next-query patterns use a conservative safe
subset (literals, escaped literals, whitespace escapes, and a single `\s+`),
not arbitrary Python regular expressions.

Context metrics have these meanings:

| metric | definition |
| --- | --- |
| `context_completeness` | Matched pairs divided by expected pairs. With no expected pairs it is `null`, and that case is excluded from aggregate means. |
| `evidence_need_count` | All derived evidence needs. |
| `required_need_count` | Needs marked required. |
| `matched_required_need_count` | Required needs with at least one selected matching item. |
| `evidence_need_completeness` | Matched required needs divided by required needs; `null` when no required needs exist. |
| `pack_bytes` | Exact canonical compact UTF-8 ContextPack JSON bytes, including the final self-sized integer. |
| `content_bytes` | UTF-8 bytes included in item excerpts. |
| `truncated_item_count` | Included items with at least one truncated excerpt. |
| `omitted_item_count` | Total candidates omitted under item/content/pack budgets. |

The eight v2 metrics after historical `context_completeness` are the persisted
acceptance surface. Status and confidence are structural metadata on the bounded
pack; they are not relevance probabilities or repository-wide completeness
claims.

The offline profile contains five required cases over three committed snapshot
repositories:

| repo key | required cases |
| --- | --- |
| `context_pack_java` | `workspace-page-flow`, `workspace-test-file`, `workspace-service-symbol` |
| `context_pack_frontend` | `qrcode-feature-context` |
| `context_pack_docs` | `program-tool-developer-docs` |

`p2_context_pack` is snapshot-only: environment variables and direct repository
overrides cannot replace these inputs. Generate the P2 and unchanged raw-result
CI reports from the current checkout with:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output .quality/real-projects/p2-context-pack-v2-final.json \
  --markdown .quality/real-projects/p2-context-pack-v2-final.md

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/real-projects/ci-p2-1-final.json \
  --markdown .quality/real-projects/ci-p2-1-final.md
```

### Pinned real-project profile

`p2_real_context` uses
`https://github.com/spring-projects/spring-petclinic.git` at exact commit
`51045d1648dad955df586150c1a1a6e22ef400c2`. Preparation is the only step that
may clone or fetch:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality prepare \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos/p2-real-context-final

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos/p2-real-context-final \
  --output .quality/real-projects/p2-real-context-final.json \
  --markdown .quality/real-projects/p2-real-context-final.md
```

Preparation validates the catalog URL, 40-character pin and portable checkout
name, clones to a sibling temporary directory, checks out detached HEAD, and
records provenance only after verifying exact HEAD/origin and a clean tracked
worktree. Repeating it is idempotent. It refuses unrelated, symlinked, tracked-dirty,
wrong-remote or wrong-commit state. `quality run --profile p2_real_context`
accepts only that prepared checkout and never performs implicit network access,
environment fallback, or a skip on invalid state.

The four required queries are:

1. `owner registration form validation flow`
2. `OwnerController tests for owner registration validation`
3. `宠物主人详情页如何加载宠物和就诊记录`
4. `MySQL PostgreSQL database profile configuration and integration tests`

### P2.1 reconciliation (2026-07-15)

- Checked implementation commit: `9dd8254e30bb4fc2e8348c527fe3642e52366ca5`.
- `p2-context-pack-v2-final.json`: selected/executed/passed `5/5/5`;
  `ci-p2-1-final.json`: `8/8/8`; both had zero failures/errors.
- A brand-new guarded cache prepared the exact PetClinic pin in detached,
  tracked-clean state. A second prepare left the provenance bytes unchanged.
- Two real-profile runs each selected/executed/passed `4/4/4`. Pack sizes were
  40,748, 42,530, 33,977, and 39,650 bytes, all below 65,536. The first two
  packs were `ready/medium`; the latter two were honestly `partial/low`.
- The opt-in real acceptance test passed five tests covering four canonical pack
  repeats plus normalized report repeat and feedback privacy. The ContextPack
  feedback extension contains no file path, excerpt, need subject, or composed
  next-query text.

### Dated qualitative CST/fast-context comparison (2026-07-15)

All systems read the exact PetClinic pin above. CST used `final_top_k=12` and
the default v2 budget. The local candidate used BGE-M3 (1,024 dimensions) plus
the Ollama planner `qwen3.5:4b-mlx`; Ollama was 0.30.10 with local model IDs
`790764642607` and `61aa3858e9d3`. Fast-context used `max_turns=3`,
`max_results=12`, no snippets; it reduced the requested tree depth from 3 to 1
and reported hotspot depth 3. This is qualitative, model-driven evidence, not a
deterministic gate.

| query | CST hash v2 | BGE-M3 + planner v2 | fast-context |
| --- | --- | --- | --- |
| owner registration | `ready/medium`, 40,748 bytes; controller=entrypoint and Owner=data type; recommended test missing, next query `owner test` | `ready/medium`, 42,935 bytes; same critical controller/entity coverage | 12 files; controller, Owner and owner form template found |
| owner registration tests | `ready/medium`, 42,530 bytes; controller=entrypoint and OwnerControllerTests=test; recommended implementation missing | `ready/medium`, 46,974 bytes; controller/test roles retained | 6 files; controller, Owner and OwnerControllerTests found |
| owner details/pets/visits | `partial/low`, 33,977 bytes; controller found, but required scoped entrypoint evidence remained missing; grounded Chinese follow-ups, no `/oups` | `partial/low`, 46,227 bytes; additionally found OwnerRepository and Pet, but not the full critical set | 12 files; controller, repository, Owner, Pet, Visit and owner-details template found |
| MySQL/PostgreSQL profiles | `partial/low`, 39,650 bytes; both integration tests classified as tests, profile property files absent from Top-12 | `partial/low`, 43,897 bytes; both tests found, both config needs reported missing | 12 files; both application profile files and both integration tests found |

The first fast-context attempt for the registration query returned a truncated
remote tool response and no parsed files; one same-parameter retry produced the
12-file result above. Fast-context does not emit ContextPack group/role, byte,
missing-need, or next-query fields, so those columns are intentionally CST-only.

## Real Repository Smoke

```bash
CST_SMOKE_REPOS_DIR=/absolute/path/to/repos \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile smoke --output .quality/smoke.json --markdown .quality/smoke.md
```

On 2026-07-15 at implementation commit
`9dd8254e30bb4fc2e8348c527fe3642e52366ca5`, no external smoke repository
variables were set (`CST_SMOKE_REPOS_DIR`, `CST_SMOKE_IMAGEBED_REPO`,
`CST_SMOKE_ENV_CHANGE_REPO`, `CST_SMOKE_INVESTMENT_ASSISTANT_REPO`, and
`CST_SMOKE_PROGRAM_TOOL_REPO` were all unset). The exact command was:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile smoke \
  --output .quality/real-projects/smoke-p2-1-final.json \
  --markdown .quality/real-projects/smoke-p2-1-final.md
```

`smoke-p2-1-final.json` selected 22 cases, executed and passed the six committed
`program_tool` cases, and explicitly skipped 16 missing-repo cases, with zero
failures and errors. This is a partial dependency result, not a verified 22-case
smoke pass.

## Baseline And Candidate Comparison

From the baseline worktree, write its report to a shared absolute directory:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-quality-comparison/main.json \
  --markdown /tmp/cst-quality-comparison/main.md
```

From the candidate worktree, write the same profile to that directory:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-quality-comparison/branch.json \
  --markdown /tmp/cst-quality-comparison/branch.md
```

Then compare the two shared reports from the candidate worktree:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality compare \
  --baseline /tmp/cst-quality-comparison/main.json \
  --candidate /tmp/cst-quality-comparison/branch.json \
  --output /tmp/cst-quality-comparison/comparison.json \
  --markdown /tmp/cst-quality-comparison/comparison.md
```

## Planner, Calibration, And A/B

### External Source Variables

| variable | repository |
| --- | --- |
| `CST_SMOKE_IMAGEBED_REPO` | imagebed |
| `CST_SMOKE_ENV_CHANGE_REPO` | env-change |
| `CST_SMOKE_INVESTMENT_ASSISTANT_REPO` | Investment-Assistant |
| `CST_SMOKE_PROGRAM_TOOL_REPO` | program-tool |
| `CST_CALIBRATION_OPERATION_CLIENT_REPO` | operation-client-api |
| `CST_CALIBRATION_CONSOLE_IOT_REPO` | console-iot-api |
| `CST_PLANNER_REQUESTS_REPO` | psf/requests |
| `CST_QUALITY_AB_REPO` | optional A/B replacement repository |
| `CST_SMOKE_REPOS_DIR` | shared parent fallback for each `repo_dir_name` |

Each value is an absolute directory used only to locate input. Reports record
the variable name, never its value.

### Planner

```bash
CST_PLANNER_REQUESTS_REPO=/absolute/path/to/requests \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile planner --output .quality/planner.json --markdown .quality/planner.md
```

### Calibration BGE

```bash
CST_CALIBRATION_OPERATION_CLIENT_REPO=/absolute/path/to/operation-client-api \
CST_CALIBRATION_CONSOLE_IOT_REPO=/absolute/path/to/console-iot-api \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile calibration_bge \
  --output .quality/calibration-bge.json \
  --markdown .quality/calibration-bge.md
```

### A/B Hash

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ab_hash --output .quality/ab-hash.json
```

### A/B BGE

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ab_bge --output .quality/ab-bge.json
```

## Phase 1 Model Acceptance

The `p1_vector_bge` and `p1_hybrid_bge` profiles select the identical seven
required cases from committed repository snapshots. Run both reports and the
focused pair gate:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_vector_bge \
  --output .quality/real-projects/p1-vector-bge-p2-1-final.json \
  --markdown .quality/real-projects/p1-vector-bge-p2-1-final.md

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_hybrid_bge \
  --output .quality/real-projects/p1-hybrid-bge-p2-1-final.json \
  --markdown .quality/real-projects/p1-hybrid-bge-p2-1-final.md

CST_RUN_P1_ACCEPTANCE=1 \
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_p1.py \
  -m integration \
  -q
```

`p1_vector_bge` requires the local `bge-m3` model. `p1_hybrid_bge` requires
both local `bge-m3` and `qwen3.5:4b-mlx`. A missing service/model or an
unsuccessful required profile/pair gate is `unverified_dependency`. A skipped,
error, fallback, failed, or zero-executed run cannot close Phase 1. The focused
pair test, not the general comparison command alone, enforces the Phase 1
aggregate delta gate. Both reports record latency `mean`, `p50`, and `p95`
under `aggregate.metrics.overall.latency_ms`.

### Phase 1 reconciliation (2026-07-15)

- Status: `unverified_dependency`
- Checked implementation commit: `9dd8254e30bb4fc2e8348c527fe3642e52366ca5`.
- Provider/model: Ollama 0.30.10; BGE profile `bge-m3` (local
  `bge-m3:latest`, ID `790764642607`); planner `qwen3.5:4b-mlx` (ID
  `61aa3858e9d3`).
- Evidence: `p1-vector-bge-p2-1-final.json` and
  `p1-hybrid-bge-p2-1-final.json` each selected and executed 7/7 required
  cases but passed 6/7 with zero runtime errors. Both missed
  `src/main/java/com/example/audit/AuditStatus.java` within Top-3 for
  `audit-status-literal`; the focused pair command then failed one test.
- Roadmap closure: pending
- Reason: an executed-but-failed required case and failed pair gate cannot close
  the roadmap's independent Phase 1 acceptance dependency. No earlier report is
  substituted for this fresh result.

## Phase 3.1 Retrieval Trace Acceptance

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_quality_p3.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  -q
```

TraceCoverage is the number of serialized final selections with non-empty source
provenance, rank history, and a selection reason divided by all serialized final
selections. Every non-empty committed P3.1 case requires TraceCoverage 1.0.

Stage and selection counts describe uncapped work, not preview length. Timings are
informational in end-to-end tests; collector unit tests use an injected clock. P3.1
does not add a quality-catalog mode. Phase 1 model acceptance remains independent
and pending until its own required 7/7 gate passes.

## Phase 3.2 Retrieval Core Decomposition Acceptance

P3.2 was verified on 2026-07-16 at Task 9 commit
`b21f0a350b3f132f8befebf87f5e211092fe7ad1`. The Task 10 documentation commit
is intentionally not self-recorded here.

Final acceptance evidence:

- With all five optional CST acceptance/repository variables unset, the full
  suite passed `1,938` tests, skipped `9`, and xfailed `0`. The JUnit evidence at
  `/tmp/cst-p3-2-final.xml` matched the immutable Slice 1 manifest exactly for
  every skip/xfail node ID and reason; there were no failures or errors.
- The six-file P3.1/P3.2 focused gate passed `76` tests. Reprojection matched
  all 13 characterization cases, both complete 13-case operation ledgers, and
  all four full-stage ledgers byte-for-byte. TraceCoverage remained `1.0` for
  every committed non-empty P3.1 case and every full-stage ledger case.
- `p2_context_pack` selected/executed/passed `5/5/5`; raw `ci` passed `8/8/8`.
  Both had zero failures and errors. Reports are
  `/tmp/cst-p3-2-p2.{json,md}` and `/tmp/cst-p3-2-ci.{json,md}`.
- The strict AST gate matched the exact acyclic 12-node facade/core import
  adjacency and exact module ownership. All 72 migrated rows have
  `remaining: 0` and a resolved task; all eight supported-facade rows retain
  their contracts. The protected-source diff and source worktree status were
  clean.
- Phase 1 remains independently pending at `6/7`; P3.2 does not reclassify it.

The immutable Slice 1 baseline is commit
`680b252b5c863fce9b236771b1a54c28e3f9839e`, and its `baseline.json` blob is
`a0011178b2671af25cb0853260c8fdcf586acee0`. Final frozen-input identity was
clean for tracked, staged, unstaged, and untracked state:

| input | Git OID | working-tree SHA-256 |
| --- | --- | --- |
| catalog `queries.json` | `8bbe4d560fec1499aa1f436af929b8a6bb6f3eac` | `ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5` |
| `program_tool` snapshot | `a8c0ace36cf82e2c743f06726944f20ce740000f` | `d67190cda56426f21bbc26e19fd16ef9b83b6eb1de62dec865c3040b59a7c663` |
| `java-spring-mini` snapshot | `f005cb94bac1fd2e81705d0f9454803ea9ab7030` | `11708de34709f1a8a71c781bd0d2f4a987c879dff0fc4517e4c149b6c9f9aadf` |
| `context-pack-java` snapshot | `e65c04eb4b2eda11b4814d5b183f4297a6f6050b` | `71435f6c894d7bb7326f9197e97672af14485eae1bad134dc1f1f8a51b029bce` |
| `context-pack-docs` snapshot | `18d9167866632df391fdbc7b356a427dec0ab9f2` | `991f9f83dd86717005e650e6effa3084ac09fee63da76e09ff278676d124fc17` |

Implementation and closure commits:

| task | commit |
| --- | --- |
| Task 1: immutable baseline | `680b252b5c863fce9b236771b1a54c28e3f9839e` |
| Task 2: primitives | `fafea37b89190bdeed0a7baea972d01889570b46` |
| Task 3: candidates | `70d41a745b0c1c5f65f8516d8b6f2c4ad1f87db9` |
| Task 4: expansion | `c1fad40c631eefec84a2057ff18a800c2c3cc6cf` |
| Task 5: ranking | `2dba63e52d20a2afa3dc347df8b21217448fd7a1` |
| Task 6: context expansion | `17ca0a527864630c5420de1ed7237fa5c0f12ee6` |
| Task 7: selection | `fd2340ac91e21099b44d82fbd7ee62b797bc4d09` |
| Task 8: trace adapters | `d0a65a5af560e8eeff46000be0cf88490e6c4bca` |
| Task 9: strict boundary closure | `b21f0a350b3f132f8befebf87f5e211092fe7ad1` |

## Phase 4 Controlled Exploration Acceptance

P4 adds a third quality-case mode, `exploration`, in the separate catalog
`tests/fixtures/retrieval_quality/p4_exploration.json`. Ordinary `results` and
`context_pack` cases keep their previous execution paths. Exploration cases add
exactly these ten closed fields: `initial_absent`, `final_present`,
`final_at_least`, `final_forbidden`, `final_noise_matchers`,
`expected_termination_reason`, `expected_retrieval_call_count`,
`maximum_retrieval_call_count`, `minimum_goal_gain`, and
`maximum_final_noise_items`.

The operation is explicitly requested and bounded: one traced initial call,
one follow-up round, at most two sequential planner-off probes, at most three
retrieval calls, eight frozen goals, eight planned probes, and a normal
65,536-byte ContextPack v2. It does not recursively explore, persist state,
compare scores across queries, generate probes with a model, or alter ordinary
`query`, `context`, or `trace` behavior.

Exploration metrics are:

| metric | definition |
| --- | --- |
| `exploration_goal_coverage_initial` / `final` | Satisfied frozen goals divided by retained goals before/after exploration. |
| `exploration_goal_gain` | Final minus initial satisfied-goal count. |
| `novel_path_count` | Follow-up repository-relative paths absent from round 0. |
| `duplicate_path_ratio` | Duplicate follow-up paths divided by all follow-up paths; `null` with no follow-up paths. |
| `executed_probe_count` | Follow-up probes actually sent to retrieval. |
| `probe_efficiency` | Probes with positive goal gain divided by executed probes; `null` with no executed probes. |
| `retrieval_call_count` | Initial call plus executed probes; a hard gate. |
| `exploration_trace_coverage` | Fully proven final-evidence entries divided by all final-evidence entries. |
| `final_pack_noise_count` / `ratio` | Matched configured noise items and their share of the final pack. |
| `exploration_latency_ms` | Total explore duration; reported and compared as neutral, never substituted for round-0 `latency_ms`. |

Run the deterministic profile with:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p4_exploration.json \
  --profile p4_exploration \
  --output /tmp/cst-p4-final.json \
  --markdown /tmp/cst-p4-final.md
```

Verified on 2026-07-17:

| case | stop | initial → final coverage | gain | probes / calls | final noise | trace coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `owner-registration-form-test` | `satisfied` | 0.1667 → 0.6667 | 3 | 1 / 2 | 0 | 1.0 |
| `owner-controller-exact` | `exact_satisfied` | 0.25 → 0.25 | 0 | 0 / 1 | 0 | 1.0 |
| `qrcode-route-service-type` | `satisfied` | 0.125 → 0.875 | 6 | 1 / 2 | 0 | 1.0 |
| `solo-controller-no-gain` | `no_marginal_gain` | 0.20 → 0.20 | 0 | 1 / 2 | 0 | 1.0 |

The profile selected/executed/passed `4/4/4`, with zero failures/errors; report
SHA-256 is
`81ff1c53dab0af00d59adc71be6ab8a9aacb15c72e0ae34109fd17759cc031f9`.
The P4 catalog SHA-256 is
`110e806dead64b4270d579a955abc8f56d7ec23d1b1f61a7951e5e4309a9c683`;
the frozen input-manifest SHA-256 is
`78e81f1c08c8216dc3355519cb89f07577ed61706e8150c9575e8395141c0b40`.

### Pinned PetClinic exploration

`p4_real_exploration` uses Spring PetClinic at exact commit
`51045d1648dad955df586150c1a1a6e22ef400c2`. Preparation is explicit and
network-capable; profile execution accepts only the already prepared, detached,
tracked-clean checkout:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality prepare \
  tests/fixtures/retrieval_quality/p4_exploration.json \
  --profile p4_real_exploration \
  --repos-dir .quality/p4-repos

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p4_exploration.json \
  --profile p4_real_exploration \
  --repos-dir .quality/p4-repos \
  --output /tmp/cst-p4-real.json
```

For `owner registration form validation flow`, round 0 ranked
`OwnerController.java` first. The single grounded follow-up
`createOrUpdateOwnerForm form template view test` added the owner form and
`OwnerControllerTests.java`; the final pack also retained `Owner.java` and the
controller. It stopped `satisfied` after 2 calls, gained 2 goals, reached goal
coverage 0.5 → 1.0, used 40,139 pack bytes, had zero configured noise, and had
ExplorationTraceCoverage 1.0.

Two production-profile runs each passed `1/1`; their timing-bearing report
SHA-256 values are
`599de075e6ccc5db8d7edb0bf7bb09c92ddd543682c74c75cc4e2ec32dd950e7`
and
`d838db9568b988215749dca617e684812f53ed7e8237220e4d0a3f60dac1b915`.
The two independently generated acceptance projections were byte-identical to
the committed baseline, SHA-256
`a0f21574ba933ae9ab6f55bdfe080755f2c6cd333c0935d108f002089074df7e`;
only approved timing fields are normalized.

The requested fresh fast-context comparison was attempted against this same
pinned checkout after explicit user authorization, but the configured service
rejected the call under its tenant privacy policy. It returned no file/range
suggestions, so no new overlap table can be reported honestly. This availability
failure is qualitative and non-gating; the CST PetClinic acceptance above
remains mandatory and passed. The earlier dated P2 comparison remains historical
evidence, not a substitute P4 result.

### Final compatibility and privacy evidence

- P4 focused gate: `243` passed, no skip/xfail.
- Protected P0-P3 gate: `194` passed; all 13 characterization cases, four
  full-stage ledgers, RetrievalTrace v1, P3 TraceCoverage, and ContextPack v2
  contracts remained exact.
- Full suite: `2,181` passed, the same `9` skip node IDs/reasons, `0` xfails;
  the P4 delta was exactly `243`. The real acceptance helper is not default
  collected. The BGE integration passed when the sandbox allowed its local
  Ollama connection.
- P2 and raw CI selected/executed/passed `5/5/5` and `8/8/8`; their non-timing
  projections remained byte-identical with SHA-256
  `57d42f4c1ef17aa4fe28176c08189cf286a1b8a68baea5b63518515c88d0e1b5`
  and `5b581b2eb66379a377392c91dad156f6ccff12556a2aa853f368aa41a1b41013`.
  Both baseline comparisons reported zero gating regressions.
- The protected P0-P3 catalog Git OID stayed
  `8bbe4d560fec1499aa1f436af929b8a6bb6f3eac`; the immutable P3.2 baseline
  stayed `a0011178b2671af25cb0853260c8fdcf586acee0`; protected retrieval core,
  ContextPack, RetrievalTrace-v1, scanner/indexer/chunker/manifest files had no
  diff from `b827707`.
- Explore feedback contains only bounded aggregate counts and limit/outcome
  fields. Generated probes/queries, goal IDs, seed/final paths, source content,
  source-count detail, and exception text are excluded.
- Phase 1 remains independently pending at `6/7`.

## MCP Feedback Privacy

```bash
cst quality feedback .context-search/mcp_calls.jsonl \
  --output .quality/feedback.json
```

Query terms and examples remain excluded unless their explicit flags are used.

## Interpreting Results

Required failures, required removals, execution regressions, coverage loss, and
gate weakening are gating regressions. Known-gap and informational cases remain
non-gating observations; their metric declines are shown separately. A skip
means a source was unavailable. An optional profile that cannot be exercised is
`unverified_dependency`, never passed. Metadata warnings identify input or
configuration differences and do not by themselves fail comparison. Generated
`.quality/` artifacts are local and untracked.
