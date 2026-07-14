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
| `p2_context_pack` | committed snapshots and offline `hash-v1` | Phase 2 deterministic ContextPack acceptance |

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
  "minimum_context_confidence": "medium"
}
```

`expected_context_groups` uses the six ContextPack v1 group names and the
existing `path`, `glob`, or `contains` matchers. Legal status values are
`empty`, `partial`, and `ready`; legal minimum-confidence values are `none`,
`low`, `medium`, and `high`.

Context metrics have these meanings:

| metric | definition |
| --- | --- |
| `context_expected_count` | Declared group/matcher pairs in the case. |
| `context_matched_count` | Expected pairs matched by at least one item in the same declared group. |
| `context_completeness` | Matched pairs divided by expected pairs. With no expected pairs it is `null`, and that case is excluded from aggregate means. |
| `context_group_count` | Number of non-empty groups in the returned pack. |
| `required_missing_count` | Missing-evidence records marked required. |
| `recommended_missing_count` | Missing-evidence records marked recommended rather than required. |
| `next_query_count` | Deterministically composed next-query records in the pack. |
| `context_content_bytes` | UTF-8 bytes of returned result and evidence-anchor content recorded by the pack budget. |

`context_pack` status and confidence are structural metadata on the bounded
returned pack, and the quality report records them as case metadata; they are
not relevance probabilities and do not claim repository-wide completeness.

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
PYTHONPATH="$PWD/src" conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output .quality/real-projects/p2-context-pack-final.json \
  --markdown .quality/real-projects/p2-context-pack-final.md

PYTHONPATH="$PWD/src" conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/real-projects/ci-p2-final.json \
  --markdown .quality/real-projects/ci-p2-final.md
```

## Real Repository Smoke

```bash
CST_SMOKE_REPOS_DIR=/absolute/path/to/repos \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile smoke --output .quality/smoke.json --markdown .quality/smoke.md
```

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
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_vector_bge \
  --output .quality/p1-vector-bge.json \
  --markdown .quality/p1-vector-bge.md

conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_hybrid_bge \
  --output .quality/p1-hybrid-bge.json \
  --markdown .quality/p1-hybrid-bge.md

CST_RUN_P1_ACCEPTANCE=1 \
conda run -n base python -m pytest \
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

### Phase 1 reconciliation (2026-07-14)

- Status: `unverified_dependency`
- Checked implementation commit: `d321f5680774b871c87dbd699129eed219b1eb81`
- Evidence: No fresh Phase 1 pair was accepted. `p1-vector-bge-reconciled.json` and `p1-hybrid-bge-reconciled.json` each selected and executed 7/7 cases but passed 6/7, and the persisted pair gate failed. The last Phase 1 closure commit is `b8527e75e602023aa7e31d360ada4595ffb444f2`; reports from `911add4d20bfcbb3190bc9045478686a87226587` are stale and explicitly rejected as acceptance evidence.
- Roadmap closure: pending
- Reason: `cst quality run ... --profile p1_vector_bge` and `cst quality run ... --profile p1_hybrid_bge` each returned 6/7 because `audit-status-literal` missed its Top-3 `AuditStatus.java` expectation; the persisted pair gate then failed.

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
