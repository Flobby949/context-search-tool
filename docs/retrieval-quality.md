# Retrieval Quality Workflow

## Profiles

| profile | dependency | purpose |
| --- | --- | --- |
| `p0_effects` | committed monorepo snapshot and offline `hash-v1` | deterministic query scope, ContextPack readiness, and P0 effect gates |
| `ci` | committed snapshots | deterministic frontend, Java, exact, and noise gates |
| `smoke` | real generic repositories | all 22 generic cases |
| `planner` | Ollama and requests checkout | repo-aware planner and genuine cross-language cases |
| `calibration_bge` | BGE and two Java repositories | all eight Java calibration cases |
| `ab_hash` | committed A/B snapshot | local embedding baseline |
| `ab_bge` | Ollama BGE-M3 | BGE candidate report |
| `p1_vector_bge` | runtime-selected BGE provider; final P14 used SiliconFlow `Pro/BAAI/bge-m3` | Phase 1 vector-only acceptance baseline |
| `p1_hybrid_bge` | the same BGE provider plus a planner; final P14 used `Qwen/Qwen2.5-14B-Instruct` | Phase 1 hybrid acceptance candidate |
| `p2_context_pack` | committed snapshots and offline `hash-v1` | deterministic ContextPack v2 acceptance |
| `p2_real_context` | explicitly prepared pinned PetClinic checkout | opt-in real-project ContextPack v2 acceptance |
| `p4_exploration` | committed snapshots and offline `hash-v1` | deterministic controlled-exploration acceptance |
| `p4_real_exploration` | explicitly prepared pinned PetClinic checkout | opt-in real-project exploration acceptance |
| `p5_language_graphs` | five committed synthetic repositories and offline `hash-v1` | deterministic language/framework graph acceptance |
| `p5_real_language_graphs` | pinned PetClinic plus committed `program_tool` snapshot | opt-in real-project graph acceptance |

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

## P0 Effects Acceptance

The committed `p0_effects` profile is the repeatable acceptance gate for the
three retrieval P0s. Run it from the current checkout:

```bash
PYTHONPATH="$PWD/src" python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/p0_effects.json \
  --profile p0_effects \
  --output .quality/p0-effects.json \
  --markdown .quality/p0-effects.md
```

Every quality case may declare one optional query-time scope. The same scope is
strictly validated and forwarded through `results`, `context_pack`, and
`exploration` execution, including exploration follow-ups:

```json
{
  "scope": {
    "include_paths": ["apps/billing/**"],
    "exclude_paths": ["apps/billing/generated/**"],
    "languages": ["python"],
    "code_only": true
  }
}
```

The required success criteria are:

- all selected cases pass with zero errors;
- aggregate `scope_escape_count.mean` is exactly `0`;
- aggregate `false_ready_count.mean` is exactly `0`;
- the no-needs case reports `partial/low`, `evidence_need_count=0`, and
  `false_ready_count=0`;
- scoped monorepo noise remains absent while existing Recall@K, MRR, noise, and
  latency metrics remain available for normal report comparison.

`expected_evidence_need_count` is an optional non-negative ContextPack or
exploration assertion. `false_ready_count` is always emitted for evaluated
packs and gates any `ready` pack with zero derived needs. `scope_escape_count`
is emitted only for active scopes and covers ranked results plus evidence
anchors. Exploration additionally covers every raw retrieval bundle, the fused
bundle, the final pack, and every probe seed path recorded in its trace.

Planner grounding cannot be expressed honestly as a generic retrieval metric
without fixing a model response. Its deterministic P0 fixture is therefore the
focused test below: it sends a fixed plan through a real temporary index and
the production validator, then proves that rare/mixed local hints are restored
while partial, invented, and scope-excluded hints remain discarded.

```bash
PYTHONPATH="$PWD/src" python -m pytest \
  tests/test_quality_planner.py::test_p0_grounding_restores_local_rare_and_mixed_hints_only \
  -q
```

Quality execution uses an empty context-local global config for each run
without changing `CST_GLOBAL_CONFIG_PATH`. This prevents user embedding
endpoints and credentials from changing a committed fixture's vector identity
or leaking into reports, including during concurrent in-process runs.

## Phase 2 Context Pack Acceptance

Quality cases accept three `mode` values: `results` (the default raw-result
evaluation), `context_pack`, and `exploration`. The following fields are valid
for ContextPack-producing cases:

```json
{
  "mode": "context_pack",
  "expected_context_groups": {
    "entrypoints": [{"path": "src/AppController.java"}],
    "implementations": [{"glob": "src/**/*ServiceImpl.java"}],
    "related_types": [{"contains": "Dto"}]
  },
  "expected_pack_status": "ready",
  "expected_evidence_need_count": 3,
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
| `false_ready_count` | `1` only for the invalid state `ready` with zero needs; such a case fails. |
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

The commands above are the legacy local diagnostic path. The authoritative
P14 closure uses the tracked external acceptance harness, which injects the
validated online provider sections without changing the catalog bytes. Its
final runtime was SiliconFlow `Pro/BAAI/bge-m3` (1024 dimensions) plus
`Qwen/Qwen2.5-14B-Instruct`; Ollama and planner fallback were forbidden. A
missing service/model is `unverified_dependency`, and skipped, error,
fallback, or zero-executed evidence cannot close Phase 1. Reports record
latency `mean`, `p50`, and `p95` under
`aggregate.metrics.overall.latency_ms`.

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

### Phase 1 closure (2026-07-31, P14)

- Final status: `ship` by explicit definition-owner acceptance of bounded
  probabilistic online-model drift. This is not a claim that the strict raw
  gates were all green.
- Runtime: SiliconFlow `openai-compatible/Pro/BAAI/bge-m3`, 1024 dimensions,
  and `openai-compatible/Qwen/Qwen2.5-14B-Instruct`; 14/14 final hybrid
  planner calls were `ok`, with zero fallback/error/skip and no
  exact-identifier rewrite.
- Vector candidate: `7/7` in both repeats, owner ranks `[2,2]`, MRR
  `0.8571428571428571`.
- Hybrid candidate: `6/7` at owner rank 4 and `7/7` at owner rank 3. Both
  repeats retained Recall@5 and entrypoint Top-3 `1.0`; MRR was
  `0.8214285714285714` and `0.8333333333333334`.
- Strict evidence: `p1-final-v4/gates.json` is retained as `blocked`. Repeat 1
  exceeds the automatic `1/42` MRR tolerance, so it is accepted only by the
  separately hashed `p1-final-v4/owner-acceptance.json`, not by rewriting the
  raw gate.
- Real-corpus safety: P8 required losses were zero; hash recall/noise stayed
  `49/57` and `154/216`; online recall/noise stayed `50/57` and `153/216`;
  the online timing ratio was `1.0036899347718384 < 1.10`. Its strict raw
  report remains `reject` for exact repeat/parity rules and its separate owner
  record is `ship`.
- Evidence root:
  `.quality/p14-runs/20260731T080504Z-online-pro-business-stable/`.
- Final post-review clean-tree regression: `3411 passed, 9 skipped`. The
  original acceptance-snapshot result (`3403 passed, 9 skipped`) remains
  separately hashed; the only later `src/tests` change is the shared planner
  identifier-regression matrix, and production source bytes are unchanged.

The accepted drift boundary covers continuous online scores, auxiliary
planner hints, same-path chunk evidence, and the observed near-tie rank
movement only while selected membership, protected winners, required recall,
noise, structure, requests, and performance remain safe. It does not waive a
wrong provider/model, Ollama substitution, fallback, error, skip, required
loss, recall decrease, noise increase, protected-winner or membership change,
structural/request drift, or a query-p95 ratio above `1.10`.

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
does not add a quality-catalog mode. Phase 1 remained independent and pending at
the P3.1 record date; P14 subsequently closed it with the raw/owner disposition
split recorded above.

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
- At the P3.2 record date Phase 1 remained independently pending at `6/7`;
  P14 subsequently closed it without reclassifying the historical P3.2 result.

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

Verified on 2026-08-12:

| case | stop | initial → final coverage | gain | probes / calls | final noise | trace coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `owner-registration-form-test` | `satisfied` | 0.1667 → 0.8333 | 4 | 1 / 2 | 0 | 1.0 |
| `owner-controller-exact` | `exact_satisfied` | 0.25 → 0.25 | 0 | 0 / 1 | 0 | 1.0 |
| `qrcode-route-service-type` | `satisfied` | 0.125 → 0.875 | 6 | 2 / 3 | 0 | 1.0 |
| `solo-controller-no-gain` | `no_marginal_gain` | 0.20 → 0.20 | 0 | 1 / 2 | 0 | 1.0 |

The profile selected/executed/passed `4/4/4`, with zero failures/errors. The P4
catalog SHA-256 is
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
coverage 0.25 → 0.75, used 34,697 pack bytes, had zero configured noise, and had
ExplorationTraceCoverage 1.0.

The 2026-08-12 production-profile verification passed `1/1` with zero
failures or errors.

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
- At this Phase 4 record date, Phase 1 remained independently pending at
  `6/7`; P14 subsequently closed it under the documented owner waiver.

## Phase 5 Language And Framework Graph Acceptance

P5 completed on 2026-07-18. The deterministic `p5_language_graphs` profile
passed exactly `12/12`; P4, P2, and raw CI remained green at `4/4`, `5/5`, and
`8/8`. The protected-direct winner/line/direct-score assays and the standalone
no-legal-edge projection remain exact. The reviewed compatibility allowlist is
the empty JSON array.

The final unrestricted suite, including the local Ollama BGE integration,
reported `2,621 passed`, the established `9 skipped`, `0 failures`, `0 errors`,
and `0 xfails`. The skips are one unconfigured investment-assistant repo, one
opt-in P1 model acceptance, five unprepared P2 real-repo cases, and two
unconfigured planner checkout cases. The offline suite reported `2,620 passed`,
`5 skipped`, and `5` explicitly deselected slow/integration cases.

The parser runtime was Python 3.13.12, SQLite 3.51.2, macOS arm64, with exact
versions `tree-sitter==0.26.0`, `tree-sitter-java==0.23.5`,
`tree-sitter-javascript==0.25.0`, `tree-sitter-typescript==0.23.2`, and
`defusedxml==0.7.1`. The eight Linux/macOS x Python 3.11-3.14 ABI jobs all
passed in [GitHub Actions run 29592106267](https://github.com/Flobby949/context-search-tool/actions/runs/29592106267).

Structural projection SHA-256 values are:

| projection | SHA-256 |
| --- | --- |
| compatibility allowlist (`[]`) | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` |
| generic tests | `8c1bdbbfc221e187e7e9355bc8adb891c6eacbddb87025e58b65086ac8068586` |
| Java/Spring/MyBatis | `307a4883929c33cc54e83e0cdced2de77c841a3f4cdb8b28018322ac8a84bfb8` |
| malformed compatibility | `68a3192aa60e0e9d1a81a48043cea2d724d405d7d2ffb991e8b13a9d18524531` |
| React | `02e313399c5d0267ef1aea11dde63c0a5239eee958fbcab6d83429a685715bb6` |
| Vue | `d5cee8b3108311ef68ac98cfcbcf50b94fa34112bf554df215a0f171441aa736` |

The real profile passed `2/2` twice and produced byte-identical normalized
projections with SHA-256
`13d1b24040eee0a99641176eb48a97c136f7b5154ea741042f6d766e13e00578`.
Pinned PetClinic commit `51045d1648dad955df586150c1a1a6e22ef400c2`
used 2 retrieval calls, 12 final items, 37,965 bytes, trace coverage 1.0, and
zero configured noise. `program_tool` used 1 call, 11 items, 23,307 bytes,
trace coverage 1.0, and zero configured noise. Both stayed below the fixed
3-call, 12-item, and 65,536-byte ceilings.

The draft Task-12 command that compared the entire P2/CI report projection to
P4 bytes was removed during final execution: those reports include ranks,
graph score parts, and graph-derived additions that P5 is explicitly designed
to change, so byte identity conflicts with Task 11's reviewed legal-delta
contract. Immutable protection remains at the catalog/input hashes,
protected-direct objects, no-edge projection, trace schemas, and required
profile gates; no protected baseline was refreshed.

All parsers, XML checks, and graph resolution run locally and perform no fetch
while indexing. A configured remote embedding provider still receives source
chunks, including a possible full resend during v4-to-v5 migration. Query and
explore send their normal query/probe text, which can contain graph-derived
names or paths; graph objects are not serialized as a separate remote payload.
When graph state is stale, signal/relation evidence is disabled while other
recall remains available. Migration requires a full reindex and may be costly;
P5 makes no P6 latency claim.

A later explicitly authorized fast-context rerun on the same pinned PetClinic
checkout and exact query succeeded. The service used `tree_depth=1`,
`hotspot_depth=3`, `max_turns=3`, and `max_results=12`; it returned 12 paths,
with 4 selected by the model search and 8 added by grep expansion. Its result
and the 12-path CST final pack shared 7 paths: 58.3% coverage from either side
and a 41.2% Jaccard overlap across the 17-path union. All four model-selected
fast-context paths were present in the CST pack: `OwnerControllerTests.java`,
`OwnerController.java`, `Owner.java`, and `OwnerRepository.java`.

Both systems therefore covered the controller, repository, owner domain type,
and controller test explicitly requested by the query. Fast-context concentrated
those four files at ranks 1-4 and uniquely added `package-info.java`,
`PetType.java`, `ClinicServiceTests.java`, `ownersList.html`, and
`ownerDetails.html`. CST uniquely added `VetController.java`,
`PetTypeRepository.java`, `VetRepository.java`, `Pet.java`, and
`CacheConfiguration.java`, reflecting a broader backend graph expansion. This
comparison remains qualitative and non-gating because the external service does
not expose CST's context-pack, budget, role, or trace contract.

Protected SHA-256 identities stayed:
`ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5`
for the P0-P3 catalog,
`110e806dead64b4270d579a955abc8f56d7ec23d1b1f61a7951e5e4309a9c683`
for the P4 catalog,
`78e81f1c08c8216dc3355519cb89f07577ed61706e8150c9575e8395141c0b40`
for the P4 input manifest, and
`4235ec5539c548005d75b98be4a0c347364d40ec28a79fc45b10d351bcf8bed7`
for the retrieval-core baseline. At this Phase 5 record date, Phase 1
remained `6/7`; P14 subsequently closed it, while Phase 6 remained next
in the historical sequence.

## Phase 7 Final Path-Diverse Selection Acceptance

P7 Final changes the existing `final_selection` boundary rather than adding a
recall source or a second ContextPack policy. Ordinary results now retain only
the first, highest-ranked chunk for each exact repository-relative path.
Evidence anchors keep their existing independent `(anchor_kind, file_path)`
allocation. No score, candidate limit, context budget, content, span, or
upstream rank is changed.

RetrievalTrace v1 keeps its schema and final stage. Its canonical
`decision_counts` sequence is now:

```text
selected_result
selected_anchor
duplicate_result_path
duplicate_anchor
result_limit
anchor_limit
```

The counters still sum exactly to the final-selection input population.
`duplicate_result_path` includes later repeats encountered after the result
limit is full.

Acceptance evidence:

- the deterministic `ci` quality profile selected, executed, and passed `8/8`;
- focused retrieval/trace tests passed `266`, ContextPack/formatter tests passed
  `156`, and exploration runner/fusion plus P7 integration tests passed `40`;
- all `26` retrieval-core boundary and characterization tests passed;
- the protected P3.2 fixture remains immutable. A P7 overlay freezes the exact
  new trace hash for all 13 legacy cases and proves that the four full stage
  ledgers add only `duplicate_result_path=0`; all non-trace hashes remain
  unchanged;
- the P6 paired/benchmark/worker protection group passed `81/81` in a temporary
  clean acceptance commit. Its final post-review working-tree rerun also passed
  `81/81`. An earlier post-review sequential run was `80/81`; the new failure,
  which had no matching entry failure, was
  `tests/test_p6_measurement_worker.py::test_final_resident_benchmark_reuses_one_session`,
  which then passed `1/1`. The later complete P6 group and full suite both
  passed without any P6 file change;
- the second complete clean-suite run passed `2,899` with the established `9`
  optional skips and no failures. The first run reproduced one entry-baseline
  P6 checkpoint calibration instability; its exact node passed immediately in
  isolation before the clean full rerun passed;
- after the final evidence-test strengthening, the post-review working-tree
  focused group passed `462`, and the complete suite passed `2,900` with the
  same `9` optional skips, `16` warnings, and no failures. This supplements
  rather than replaces the historical clean-commit result;
- on the pinned public Python probe, query diversity improved from `2/12` paths
  to `12/12`; `src/core/pipeline.py` remained present and
  `data_provider/base.py` became selectable. The trace recorded `76` duplicate
  result paths and the ContextPack contained 12 unique paths;
- a sanitized Java check returned `12/12` unique paths and retained the
  previously represented high-level chain.

The public probe is a mechanism check, not a new claim of fast-context parity.
Targets still ranked below the selected distinct-path population remain
evidence for a later Python structural-acquisition or ranking experiment.
Widening the result/context pool was explicitly rejected because the probe
admitted unrelated paths without reliably recovering those residual targets.

## MCP Feedback Privacy

```bash
cst quality feedback .context-search/mcp_calls.jsonl \
  --output .quality/feedback.json
```

Query terms and examples remain excluded unless their explicit flags are used.

## P13 BGE Provider Hardening Disposition

P13 ended in **engineering PASS + recommendation FAIL → supported opt-in,
no recommendation**. This is neither `reject` nor `BLOCKED`, and the default
remains `hash`.

The fixed CPython 3.13.12 / SQLite 3.51.2 / NumPy 2.4.2 / pytest 9.0.3
authoritative final-main offline closure produced `3,240 passed`, `5 skipped`,
and `6 deselected`, with zero failures, errors, xfail, or xpass. The focused
selection passed `838/838` with `2` terminal deselections, and
characterization passed `36/36`. All `2,993` baseline nodes retained their
historical outcomes and markers. Hash behavior was byte-identical on both
sides at SHA-256
`f0445affe9f29a338894f73bbbdc6fb219e2a46e4e84de89cecaf0457e8b0508`.
The summary is
`/tmp/context-search-p13-main-final-run.YCY121/evidence/final-offline-authoritative/summary.json`
(SHA-256
`98bb0bfe93aae799b46c8a10048ccd9734847b704456eadf8153c7e76fbc54ee`);
the offline evidence manifest has SHA-256
`1da91c49637f7e96c5c3a7b635c67f584387b3760d2fbe55029f392d10249f5e`.

Live correctness passed the public index/query path for English, Chinese,
mixed-language, 4,000-code-point, and 6,924-code-point dense-CJK inputs.
Singleton/batch equivalence measured minimum cosine
`0.9999998807907104` and maximum component delta `0.0`. Runtime identity
remained fixed at Ollama `0.30.10`, canonical model `bge-m3:latest`, digest
`7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`,
and transform `bge-input-v2`. The frozen preflight SHA-256 is
`08ceed5f8b4cfaf31dc825cf0e4938ee10aa44b41bb0400caef922f94a97c833`;
the raw correctness record SHA-256 is
`35aa8b8d15d721f2ed8c26dd429f2fa1ff699149a842005a9298f3dfe45eec75`;
the integration JUnit SHA-256 is
`6fe3566c1c3927ed09bf112161f970be71e9798e718389d67c7d47a49e32aa54`.
The live summary at
`/tmp/context-search-p13-main-final-run.YCY121/evidence/final-live-authoritative/summary.json`
has SHA-256
`c09210b1c7f0200f6c9a92dadb132e49581471a5c566618675bdb7dd2cbc35e5`;
its evidence manifest has SHA-256
`60fbd61f7ee35d5d7e1f2e03682047a5659123a5293e4e8b5c1982fec2e841cf`.

All eleven engineering gates passed. Candidate/legacy-BGE index ratios were
`125.437593 / 334.611 = 0.37487587975290715` for daily,
`7.851179 / 18.194 = 0.43152572276574697` for RedInk, and
`133.26474100000001 / 352.805 = 0.37772917333938016` in aggregate, all
below `1.10`. Query p95 was
`1.0082055 / 1.018875666 = 0.9895275092378152`, below `1.15`.
Embedding requests fell from `1462` to `239` on daily, `89` to `33` on
RedInk, and `1551` to `272` overall. An independent recomputation matched
these ratios. The eleven-gate JSON SHA-256 is
`d83679d2dbf61fb07d24120ef244e79a77cbb59b0b69f1963046eaf9614044dc`.

The independent product comparison passed seven of eight recommendation
gates:

| gate | measured result | threshold | result |
| --- | --- | --- | --- |
| Recall@12 | BGE `0.8771929824561403`; hash `0.8596491228070176` | non-decreasing | PASS |
| required items | zero lost; one new (`src/services/portfolio_service.py`) | zero lost, at least one new | PASS |
| noise ratio | BGE `0.7083333333333334`; hash `0.7129629629629629` | non-increasing | PASS |
| query p95 | `1.0157435415 / 0.807222146 = 1.2583197159955024` | `≤ 1.50` | PASS |
| per-repository index | daily `122.1016075 / 2.3921405 = 51.042824407680065` (**FAIL**); RedInk `7.325094 / 0.1713095 = 42.7594149769861` (PASS) | both `≤ 50` | **FAIL** |
| P1 continuity | both mandatory profiles retain 6/7 | historical 6/7 | PASS |
| repeated captures | zero non-timing mismatches | zero | PASS |

The only P1 miss remained `audit-status-literal` for both
`p1_vector_bge` and `p1_hybrid_bge`. Because both per-repository index-cost
ratios must pass and daily missed the frozen limit, the results support opt-in
use but do not support a recommendation or default change.

The P1 wrapper at
`/tmp/context-search-p13-main-final-run.YCY121/evidence/final-live-authoritative/p1/p1-continuity.json`
has SHA-256
`2cc387b7eff643262a9ab417d214a23457ea08c626e8a1cb829222d1e8375cc5`;
its vector and hybrid raw reports have SHA-256
`15f66a8cb89cf24c717507eeb1eab678344c1b742dae34877814de0d6973144a`
and
`07722aed23d30de1c2779db2bfcad411fe57f926ea0c465323223024502863d4`.
The final product comparison is
`/tmp/context-search-p13-main-final-run.YCY121/evidence/final-live-authoritative/product-comparison.json`
(SHA-256
`9162167b4d27a68d5aa8a92c969260ba0e94f572f40aa87961d3cd06ccd7883d`).

All authoritative evidence was executed against clean physical `main` and a
clean detached delivery replica at
`3b81d72ef8c438da4049875d3e68ef6ec1a133c7`, both with tree
`4a189adc7ef6eba724047021e3f3764c5175df67`; their identities and clean state
matched before and after execution, prior to these documentation-only edits.
The final verifier reported zero unresolved findings. Earlier environment
attempts affected by a stale evidence pointer, ancestor working directory,
resolved launcher paths, or an over-strict import preflight are invalid
partial pre-product evidence and are excluded from every authoritative value
above.

To rerun live correctness, engineering comparison, or product comparison,
first freeze the Ollama version/model digest and use clean detached
baseline/candidate trees. The tracked controller commands are:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_bge.py -m integration

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  python -P tests/p13_bge_provider_measurement.py paired \
  --baseline-root "$P13_BASELINE_ROOT" \
  --candidate-root "$P13_CANDIDATE_ROOT" \
  --expected-candidate-commit \
    3b81d72ef8c438da4049875d3e68ef6ec1a133c7 \
  --sources "$P8_SOURCES_ROOT" \
  --output "$P13_EVIDENCE_ROOT/engineering-gates.json"

env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  python -P tests/p13_bge_provider_measurement.py product-paired \
  --candidate-root "$P13_CANDIDATE_ROOT" \
  --expected-candidate-commit \
    3b81d72ef8c438da4049875d3e68ef6ec1a133c7 \
  --sources "$P8_SOURCES_ROOT" \
  --p1-evidence "$P13_EVIDENCE_ROOT/p1/p1-continuity.json" \
  --output "$P13_EVIDENCE_ROOT/product-comparison.json"
```

Unavailable or drifting Ollama identity is `BLOCKED`; a completed gate that
misses its frozen threshold is FAIL. See the
[P13 implementation record](superpowers/plans/2026-07-27-p13-bge-provider-hardening.md#implementation-record)
for full arithmetic and evidence provenance.

## Interpreting Results

Required failures, required removals, execution regressions, coverage loss, and
gate weakening are gating regressions. Known-gap and informational cases remain
non-gating observations; their metric declines are shown separately. A skip
means a source was unavailable. An optional profile that cannot be exercised is
`unverified_dependency`, never passed. Metadata warnings identify input or
configuration differences and do not by themselves fail comparison. Generated
`.quality/` artifacts are local and untracked.
