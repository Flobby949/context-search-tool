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
