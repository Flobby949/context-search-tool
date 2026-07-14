# P2 Context Pack Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic ContextPack v1 output through a new `cst context` command and `context_search_context` MCP tool while preserving every existing raw-query contract and retrieval behavior.

**Architecture:** Keep `query_repository()` as the single retrieval pass. A new pure `context_pack.py` module receives the final `QueryBundle` plus effective request options, classifies every returned result and evidence anchor exactly once, derives reading order/gaps/queries/confidence/budget, validates response-local references, and materializes one shared JSON-native pack. CLI, MCP, and quality evaluation consume that same builder; raw `query` surfaces remain unchanged.

**Tech Stack:** Python 3.11+, frozen dataclasses, Typer, FastMCP, pytest, the existing hash/BGE retrieval stack, and JSON quality fixtures.

---

## Planning Constraints And Assumptions

1. The approved source of truth is `docs/superpowers/specs/2026-07-14-p2-context-pack-output-design.md`, including the review fixes made on 2026-07-14. The user's approval to begin planning completes written design review; its status and plan link are already recorded, and execution does not reopen its decisions.
2. Phase 2 is one bounded increment: ContextPack v1, its two dedicated public operations, deterministic offline quality coverage, privacy-safe feedback, documentation, and acceptance evidence.
3. Do not change retrieval candidates, scores, weights, relations, rank order, result limits, query planner behavior, index schema, embedding providers, or framework plugins. The only retrieval edit is exposing and reusing the existing evidence-anchor limit formula.
4. `cst query` and `context_search_query` are compatibility baselines. Their keys, values, order-bearing arrays, defaults, errors, and feedback event shape must remain unchanged.
5. One context invocation calls `query_repository()` exactly once and `build_context_pack()` exactly once. The builder performs no repository, index, vector, filesystem, network, embedding, planner, or model I/O.
6. No pack-specific tuning flags are added. Effective options come from the existing config plus the existing `context_lines`, `full_file`, and MCP `final_top_k` inputs.
7. The current checked-in `.quality/real-projects/p1-*.json` reports were generated at commit `911add4d20bfcbb3190bc9045478686a87226587` and each records one failing case. They are stale and must not be cited as accepted Phase 1 evidence. Fresh reports or an explicit `unverified_dependency` outcome are required before roadmap closure.
8. Existing committed Java fixtures cannot produce a distinct related-type pack item without changing a shared snapshot or relaxing the approved classifier. Use a minimal P2-only Java snapshot with controller, service implementation, DTO, and test files. This keeps the change deterministic and prevents Phase 2 fixtures from perturbing existing raw-result gates.
9. Reuse `tests/fixtures/real_projects/program_tool` read-only for the frontend case. Add the separately required P2-only README snapshot; do not modify `program_tool/package.json` or any other shared fixture.
10. `ContextPack` status/confidence describe structural readiness of the bounded response, not repository-wide completeness or retrieval correctness.
11. Stop after Phase 2 acceptance. Do not begin RetrievalTrace, retrieval-core decomposition, graph traversal, multi-round exploration, marginal-gain logic, or new token budgets.

## File Map

### Create

| File | Responsibility |
| --- | --- |
| `src/context_search_tool/context_pack.py` | Typed ContextPack v1 models, effective option resolution, pure builder, exact classifier, reference/budget/JSON validation, payload materialization, and item dereferencing. |
| `tests/test_context_pack.py` | Exhaustive builder tests for classification, intent, ordering, gaps, next queries, confidence, budgets, empty state, purity, and contract failures. |
| `tests/test_quality_p2.py` | Deterministic end-to-end `p2_context_pack` profile acceptance. |
| `tests/fixtures/context-pack-java/src/main/java/com/example/workspace/controller/WorkspaceController.java` | P2-only Java/Spring entrypoint fixture. |
| `tests/fixtures/context-pack-java/src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java` | P2-only Java implementation fixture. |
| `tests/fixtures/context-pack-java/src/main/java/com/example/workspace/dto/WorkspaceDto.java` | P2-only related-type fixture. |
| `tests/fixtures/context-pack-java/src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java` | P2-only test fixture. |
| `tests/fixtures/context-pack-docs/README.md` | Exact isolated documentation anchor required by the design. |

### Modify

| File | Responsibility |
| --- | --- |
| `src/context_search_tool/retrieval.py` | Rename `_evidence_anchor_top_k` to public `evidence_anchor_top_k` and reuse it internally without changing the formula. |
| `src/context_search_tool/formatters.py` | Extract raw query payload construction without shape changes; add context JSON and Markdown formatters. |
| `src/context_search_tool/cli.py` | Extract the smallest shared query preparation path and add `cst context` with the two declared exception phases. |
| `src/context_search_tool/mcp_tools.py` | Add `context_search_context_tool`, shared pack serialization, bounded context feedback, and exact error boundaries. |
| `src/context_search_tool/mcp_server.py` | Register `context_search_context` with the same arguments as the raw query tool. |
| `src/context_search_tool/quality/cases.py` | Validate the two legal modes and parse typed context-only expectations. |
| `src/context_search_tool/quality/metrics.py` | Evaluate expected group/path pairs and add the eight declared context metrics. |
| `src/context_search_tool/quality/runner.py` | Build/evaluate packs only for `context_pack` cases, expose status/confidence case metadata, and make P2 snapshot-only. |
| `tests/fixtures/retrieval_quality/queries.json` | Register the offline profile and five required P2 cases over three isolated/reused snapshots. |
| `tests/test_retrieval_pipeline.py` | Lock the public evidence-anchor limit helper and unchanged retrieval use. |
| `tests/test_formatters.py` | Lock raw-query compatibility, pack JSON identity, Markdown reading order, and invalid-reference failures. |
| `tests/test_cli_commands.py` | Cover context CLI invocation, flags, success output, empty state, and pack-phase failures. |
| `tests/test_mcp_tools.py` | Cover MCP context envelopes, one-pass invocation, raw preservation, JSON encoding, errors, and feedback privacy. |
| `tests/test_mcp_server.py` | Lock registration and callable signature of both query operations. |
| `tests/test_quality_cases.py` | Cover mode/expectation parsing, rejection rules, and P2 profile invariants. |
| `tests/test_quality_metrics.py` | Cover context pair matching, gates, counts, status, and confidence thresholds. |
| `tests/test_quality_runner.py` | Cover conditional pack construction, metadata, single build, failures, and result-mode non-regression. |
| `tests/test_quality_aggregate.py` | Prove generic numeric aggregation excludes null context completeness without changing aggregate code. |
| `tests/test_quality_catalog.py` | Lock P2 profile config, repo wiring, case manifest, snapshot hashes, and five-case selection. |
| `README.md` | Explain raw search versus agent-oriented context, both CLI/MCP operations, output, and errors. |
| `docs/retrieval-quality.md` | Document P2 profile, fixture schema, metrics, commands, and offline acceptance semantics. |
| `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` | Reconcile the stale Phase 1 pointer and mark Phase 2 complete only after all gates pass. |
| `docs/superpowers/specs/2026-07-14-p2-context-pack-output-design.md` | Record completed written review and link this plan; do not alter the approved contract. |

### Explicitly Do Not Modify

- `src/context_search_tool/models.py`: ContextPack is an output-layer model and belongs in the new module; `QueryBundle` remains unchanged.
- `src/context_search_tool/config.py`: v1 adds no new persisted configuration.
- `src/context_search_tool/quality/aggregate.py`: its existing generic numeric aggregation already ignores `None`; a focused regression test is sufficient.
- Existing shared fixture source files: add P2-only repo entries instead of changing their content.

## Public And Internal Interfaces To Lock

```python
# src/context_search_tool/retrieval.py
def evidence_anchor_top_k(max_results: int) -> int:
    if max_results <= 0:
        return 0
    return max(1, min(5, max_results // 3))
```

```python
# src/context_search_tool/context_pack.py
CONTEXT_PACK_SCHEMA_VERSION = 1
CONTEXT_GROUPS = (
    "entrypoints",
    "implementations",
    "related_types",
    "tests",
    "configs_docs",
    "supporting",
)

class ContextPackError(Exception):
    """A bounded public failure of the ContextPack contract."""

@dataclass(frozen=True)
class ContextPackOptions:
    max_results: int
    max_evidence_anchors: int
    context_before_lines: int
    context_after_lines: int
    full_file: bool
    max_full_file_bytes: int

def resolve_context_pack_options(
    config: ToolConfig,
    *,
    context_lines: int | None,
    full_file: bool,
    max_evidence_anchors: int,
) -> ContextPackOptions:
    """Resolve request/config inputs without importing the retrieval module."""

def build_context_pack(
    bundle: QueryBundle,
    options: ContextPackOptions,
) -> ContextPack:
    """Build and validate one deterministic, I/O-free ContextPack."""

def context_pack_payload(
    bundle: QueryBundle,
    pack: ContextPack,
) -> dict[str, Any]:
    """Validate references and return JSON-native ContextPack schema v1."""

def resolve_context_item(
    bundle: QueryBundle,
    item: ContextPackItem,
) -> RetrievalResult | EvidenceAnchor:
    """Dereference one response-local item or raise the fixed reference error."""
```

Use `from __future__ import annotations` and import `QueryBundle` under
`if TYPE_CHECKING:` only. Runtime code consumes the bundle by its declared public
fields; `context_pack.py` must not import the retrieval pipeline or its limit
helper at runtime.

The only messages that may be raised through `ContextPackError` are closed:

```python
DUPLICATE_ITEM_ERROR = "duplicate ContextPack item id"
INVALID_REFERENCE_ERROR = "invalid ContextPack item reference"
INVALID_CLASSIFICATION_ERROR = "invalid ContextPack classification"
BUDGET_EXCEEDED_ERROR = "ContextPack budget exceeded"
NON_JSON_ERROR = "ContextPack contains a non-JSON value"
```

The CLI and MCP pack-phase boundaries use one separate operational fallback for
unexpected `Exception` values:

```python
UNEXPECTED_CONTEXT_ERROR = "Context pack construction failed"
```

The builder never raises this fallback as `ContextPackError`; internal exception
text is discarded at the surface boundary.

Quality cases gain these typed fields and no others:

Append these fields after the current `QualityCase` fields without reordering any
existing field:

```python
expected_context_groups: dict[str, tuple[Matcher, ...]] = field(
    default_factory=dict
)
expected_pack_status: str | None = None
minimum_context_confidence: str | None = None
```

Executed context cases add this report metadata only; result-mode records omit it:

```json
{
  "context_pack": {
    "status": "ready",
    "confidence": "medium"
  }
}
```

## Success Criteria

- Both new public operations expose schema version 1 and preserve all raw query fields.
- Every returned result and anchor becomes one item, one group member, and one reading-order member with a valid local reference.
- Classification, explicit/planner intent handling, promotion, missing evidence, next queries, confidence, budgets, and errors match the approved closed rules exactly.
- Context construction adds no retrieval/model/I/O work and never mutates raw ranking.
- Empty retrieval is a successful explicit empty pack with no fabricated next query.
- Known and unexpected pack failures stay inside `context_failed`/CLI exit boundaries and leak no internal text.
- Context MCP feedback contains only approved counts/category metadata in addition to the existing raw query event.
- `p2_context_pack` selects, executes, and passes exactly five required offline cases; aggregate `context_completeness` is present and null values are excluded correctly.
- Existing `ci`, raw query tests, and the full test suite pass.
- Phase 1 documentation points only to fresh valid evidence or explicitly records an unverified dependency; Phase 2 is not marked complete prematurely.

## Task Dependency Order

1. Freeze baseline and expose unchanged effective limits.
2. Build the structural pack and closed classifier.
3. Add intent-driven ordering and missing evidence.
4. Add next queries, confidence, validation, payload, and empty state.
5. Add formatters and CLI context operation.
6. Add MCP operation, registration, error envelopes, and privacy-safe feedback.
7. Activate quality schema/evaluation without changing result mode.
8. Add deterministic fixtures/profile and end-to-end acceptance.
9. Document, run all gates, reconcile Phase 1 evidence, and close Phase 2 conditionally.

### Task 1: Freeze the compatibility baseline and expose effective pack options

**Files:**

- Modify: `src/context_search_tool/retrieval.py`
- Create: `src/context_search_tool/context_pack.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Create: `tests/test_context_pack.py`

- [ ] **Step 1: Record the pre-change baseline and stale-evidence boundary**

Run:

```bash
git rev-parse HEAD
git status --short
for report in \
  .quality/real-projects/p1-vector-bge.json \
  .quality/real-projects/p1-hybrid-bge.json; do
  jq '{profile, generated_at, commit: .tool.git_commit, aggregate: .aggregate}' "$report"
done
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_quality_cases.py \
  tests/test_quality_runner.py \
  -q
```

Expected:

- the baseline commit is recorded in the execution log;
- only the reviewed design document and this plan are dirty before implementation;
- both old P1 reports identify `911add4d20bfcbb3190bc9045478686a87226587` and are explicitly excluded from acceptance evidence;
- all selected baseline tests pass.

If a baseline test already fails, stop and diagnose it before adding Phase 2 code. Do not absorb an unrelated failure into this plan.

- [ ] **Step 2: Write failing tests for the public anchor limit and effective options**

In `tests/test_retrieval_pipeline.py`, replace direct private-helper assertions with:

```python
@pytest.mark.parametrize(
    ("max_results", "expected"),
    [(-1, 0), (0, 0), (1, 1), (2, 1), (3, 1), (10, 3), (12, 4), (18, 5)],
)
def test_evidence_anchor_top_k_preserves_existing_formula(
    max_results: int,
    expected: int,
) -> None:
    assert retrieval.evidence_anchor_top_k(max_results) == expected
```

Also update the existing anchor-selection test to monkeypatch or call `retrieval.evidence_anchor_top_k`, proving the retrieval path uses the public helper rather than a copied formula.

In `tests/test_context_pack.py`, add:

```python
def test_resolve_context_pack_options_uses_effective_config_window() -> None:
    config = ToolConfig(
        index=IndexConfig(max_full_file_bytes=123_456),
        retrieval=RetrievalConfig(
            final_top_k=12,
            context_before_lines=8,
            context_after_lines=12,
        ),
    )

    options = resolve_context_pack_options(
        config,
        context_lines=None,
        full_file=False,
        max_evidence_anchors=4,
    )

    assert options == ContextPackOptions(
        max_results=12,
        max_evidence_anchors=4,
        context_before_lines=8,
        context_after_lines=12,
        full_file=False,
        max_full_file_bytes=123_456,
    )


def test_resolve_context_pack_options_applies_symmetric_override() -> None:
    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=0,
        full_file=True,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0
    assert options.full_file is True
```

- [ ] **Step 3: Run the new tests and verify the intended red state**

Run:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py \
  -q
```

Expected: collection or assertions fail because the public helper and context pack module do not yet exist. No existing retrieval assertion should fail for a different reason.

- [ ] **Step 4: Expose the unchanged helper and add typed pack models/options**

In `src/context_search_tool/retrieval.py`, rename the helper and update its only production caller:

```python
def evidence_anchor_top_k(max_results: int) -> int:
    if max_results <= 0:
        return 0
    return max(1, min(5, max_results // 3))
```

Do not keep a second private alias or a second formula.

In `src/context_search_tool/context_pack.py`, add frozen models with exact public fields:

```python
@dataclass(frozen=True)
class ContextPackItem:
    id: str
    source: str
    source_index: int
    file_path: str
    start_line: int
    end_line: int
    group: str
    role: str
    classification_basis: str


@dataclass(frozen=True)
class MissingEvidence:
    category: str
    required: bool
    reason: str


@dataclass(frozen=True)
class NextQuery:
    query: str
    purpose: str
    reason: str


@dataclass(frozen=True)
class ReadinessConfidence:
    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ContextBudget:
    max_results: int
    max_evidence_anchors: int
    max_items: int
    included_results: int
    included_evidence_anchors: int
    content_bytes: int
    context_before_lines: int
    context_after_lines: int
    full_file: bool
    max_full_file_bytes: int


@dataclass(frozen=True)
class ContextPack:
    schema_version: int
    status: str
    items: tuple[ContextPackItem, ...]
    groups: dict[str, tuple[str, ...]]
    reading_order: tuple[str, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    next_queries: tuple[NextQuery, ...]
    confidence: ReadinessConfidence
    budget: ContextBudget
```

Implement option resolution in this module. It may import `ToolConfig`; it must not import `evidence_anchor_top_k` or duplicate that formula. Clamp configured/overridden context line counts with the same `max(0, value)` semantics already used by retrieval.

- [ ] **Step 5: Run focused and raw-regression tests**

Run:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py \
  -q
git diff --check
```

Expected: the helper/options tests pass, retrieval tests remain green, and the diff check prints nothing.

- [ ] **Step 6: Commit the effective-limit seam**

```bash
git add \
  src/context_search_tool/retrieval.py \
  src/context_search_tool/context_pack.py \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py
git commit -m "feat: add context pack contract models"
```

### Task 2: Build the one-item/one-reference structure and closed classifier

**Files:**

- Modify: `src/context_search_tool/context_pack.py`
- Modify: `tests/test_context_pack.py`

- [ ] **Step 1: Add synthetic bundle factories and failing classification tests**

Use small in-memory helpers; do not index a repository in builder unit tests:

```python
def result(
    path: str,
    *,
    content: str = "source",
    evidence_priority: float | None = 0.0,
) -> RetrievalResult:
    score_parts = {}
    if evidence_priority is not None:
        score_parts["evidence_priority"] = evidence_priority
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=2,
        content=content,
        score=1.0,
        score_parts=score_parts,
        reasons=["fixture"],
        followup_keywords=[],
    )


def anchor(path: str, kind: str) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=Path(path),
        start_line=1,
        end_line=2,
        content="anchor",
        score=0.5,
        score_parts={},
        reasons=["fixture anchor"],
        anchor_kind=kind,
    )


def options(max_results: int = 12, max_anchors: int = 4) -> ContextPackOptions:
    return ContextPackOptions(
        max_results=max_results,
        max_evidence_anchors=max_anchors,
        context_before_lines=8,
        context_after_lines=12,
        full_file=False,
        max_full_file_bytes=200_000,
    )
```

Parameterize every closed-table family, including exact public role/basis values:

```python
@pytest.mark.parametrize(
    ("path", "content", "group", "role", "basis"),
    [
        ("tests/test_app.py", "source", "tests", "test", "path_role"),
        ("deploy/docker-compose.yml", "source", "configs_docs", "deployment_config", "path_role"),
        ("README.md", "source", "configs_docs", "doc", "path_role"),
        ("src/router/index.ts", "source", "entrypoints", "route_config", "frontend_role"),
        ("src/views/Home.vue", "source", "entrypoints", "view_page", "frontend_role"),
        ("src/services/api.ts", "source", "implementations", "service", "frontend_role"),
        ("src/stores/app.ts", "source", "implementations", "store", "frontend_role"),
        ("src/types/app.d.ts", "source", "related_types", "type_decl", "frontend_role"),
        ("src/main/controller/AppController.java", "source", "entrypoints", "entrypoint", "path_role"),
        ("src/main/service/impl/AppServiceImpl.java", "source", "implementations", "service_impl", "path_role"),
        ("src/main/dto/AppDto.java", "source", "related_types", "data_type", "path_role"),
        ("generated/output.json", "source", "supporting", "generated_output", "path_role"),
        ("src/plain.py", "source", "supporting", "source", "fallback"),
        ("src/components/Widget.py", "source", "supporting", "component", "fallback"),
    ],
)
def test_build_context_pack_emits_closed_classification_values(
    path: str,
    content: str,
    group: str,
    role: str,
    basis: str,
) -> None:
    bundle = QueryBundle(
        query="symbol",
        expanded_tokens=[],
        results=[result(path, content=content)],
        followup_keywords=[],
    )

    pack = build_context_pack(bundle, options())

    assert (pack.items[0].group, pack.items[0].role, pack.items[0].classification_basis) == (
        group,
        role,
        basis,
    )
```

Add separate tests for:

- frontend test/config precedence over frontend roles;
- summary ownership for `summary_entrypoint`, `summary_implementation`, and `summary_related_type` with case-insensitive stems and implementation `<stem>.method` matching;
- summary collision precedence `entry_points`, then `implementation`, then `related_types`;
- `readme`, `risks`, `pom`, and unknown/empty anchor kinds;
- all results followed by all anchors in `items` source order;
- all six group keys in fixed order, including empty groups;
- within-group result order followed by anchor order;
- exactly one occurrence of each ID across groups and reading order;
- invalid future path/frontend classifier values raising `invalid ContextPack classification`.

For the future-role tests, make an unknown path role accompany a path that would
otherwise receive a known frontend role, and make an unknown frontend role
accompany a known `source` path role. Neither unknown value may be masked by a
later precedence branch.

- [ ] **Step 2: Add failing reference and budget invariants**

Add tests that build two results and two anchors, then assert:

```python
assert [item.id for item in pack.items] == [
    "result:0",
    "result:1",
    "anchor:0",
    "anchor:1",
]
assert [item.source_index for item in pack.items] == [0, 1, 0, 1]
assert pack.budget.max_items == (
    pack.budget.max_results + pack.budget.max_evidence_anchors
)
assert pack.budget.content_bytes == sum(
    len(item.content.encode("utf-8"))
    for item in [*bundle.results, *bundle.evidence_anchors]
)
```

Also assert a result count above `max_results` or anchor count above `max_evidence_anchors` raises `ContextPackError("ContextPack budget exceeded")`. Include multibyte Chinese content so byte accounting cannot accidentally use character count.

- [ ] **Step 3: Run the structural tests and verify red**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  -q
```

Expected: new builder tests fail because structure/classification are not implemented; option tests remain green.

- [ ] **Step 4: Implement classification precedence and structural assembly**

Use closed maps rather than heuristic fallthrough:

```python
_PATH_GROUPS = {
    "test": "tests",
    "deployment_config": "configs_docs",
    "config_example": "configs_docs",
    "runtime_config": "configs_docs",
    "config": "configs_docs",
    "doc": "configs_docs",
    "entrypoint": "entrypoints",
    "router": "entrypoints",
    "command": "entrypoints",
    "handler": "entrypoints",
    "view": "entrypoints",
    "service_impl": "implementations",
    "executor": "implementations",
    "engine": "implementations",
    "middleware": "implementations",
    "storage": "implementations",
    "service": "implementations",
    "repository": "implementations",
    "source_adapter": "implementations",
    "state_store": "implementations",
    "composable": "implementations",
    "scheduler": "implementations",
    "data_type": "related_types",
    "service_interface": "related_types",
    "generated_output": "supporting",
    "lockfile": "supporting",
}

_FRONTEND_GROUPS = {
    "route_config": "entrypoints",
    "view_page": "entrypoints",
    "layout_component": "entrypoints",
    "service": "implementations",
    "utility": "implementations",
    "store": "implementations",
    "shared_component": "implementations",
    "type_decl": "related_types",
    "lockfile": "supporting",
    "scratch_temp": "supporting",
}
```

Implement result precedence exactly:

1. call `classify_path_role(path, content)`;
2. reject its name unless it is one of the approved path roles, including
   `source` and `component`;
3. immediately select generic test/config/doc roles;
4. call `classify_frontend_role(path.as_posix())`, reject its name unless it is
   one of the approved frontend roles or `other`, and select a non-`other` role;
5. select remaining mapped path roles except `source`/`component`;
6. for `source`/`component`, apply narrow summary stem ownership;
7. emit fallback `source` or `component`.

For anchors, inspect only `anchor_kind`: known kinds map to `configs_docs`; every other value immediately becomes supporting `evidence_anchor` with fallback basis.

Build groups by filtering source-ordered items, not by appending from unordered sets. At this stage reading order may use fixed group order; Task 3 adds explicit promotion.

Because the public dataclass is already complete while Tasks 3–4 are still red,
use only this temporary neutral scaffold for fields not implemented in Task 2:

```python
status = "empty" if not items else "ready"
missing_evidence = ()
next_queries = ()
confidence = ReadinessConfidence(
    level="none" if not items else "medium",
    reasons=(),
)
```

No public CLI/MCP surface exists yet. Task 3 replaces non-empty status/gaps and
Task 4 replaces empty handling, next queries, confidence, and final payload
validation. Do not implement those later rules early merely to make this
structural commit look feature-complete.

- [ ] **Step 5: Implement budget accounting and validate structural invariants**

Before returning, verify limits and compute:

```python
content_bytes = sum(
    len(source.content.encode("utf-8"))
    for source in [*bundle.results, *bundle.evidence_anchors]
)
```

Add an internal `_validate_context_pack(bundle, pack)` that checks:

- schema version and fixed group keys;
- unique item IDs;
- ID/source/source-index agreement;
- file path and line fields agree with the referenced raw object;
- every item appears once in exactly one group;
- every item appears once in reading order;
- group/role/basis values are closed;
- included counts do not exceed effective limits.

Map each failure to the exact bounded public message; never include the offending path, ID, or exception text.

- duplicate item IDs use `duplicate ContextPack item id`;
- unresolved, repeated, missing, or inconsistent group/reading/source references use `invalid ContextPack item reference`;
- group/role/basis values outside the closed table use `invalid ContextPack classification`;
- count/limit violations use `ContextPack budget exceeded`;
- payload values outside finite JSON-native values use `ContextPack contains a non-JSON value`.

Validation must check approved `(group, role, classification_basis)` triples, not
three independent enum sets; a valid role paired with the wrong group or basis is
still `invalid ContextPack classification`.

- [ ] **Step 6: Run builder and existing role tests**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_path_roles.py \
  tests/test_frontend_roles.py \
  -q
git diff --check
```

Expected: structural/classifier tests pass, existing classifier behavior is unchanged, and no unrelated file is modified.

- [ ] **Step 7: Commit the deterministic structure**

```bash
git add src/context_search_tool/context_pack.py tests/test_context_pack.py
git commit -m "feat: build deterministic context pack items"
```

### Task 3: Derive required/recommended evidence and promoted reading order

**Files:**

- Modify: `src/context_search_tool/context_pack.py`
- Modify: `tests/test_context_pack.py`

- [ ] **Step 1: Write failing tests for explicit intent without generated-token leakage**

Add a table that locks the explicit required union:

| Query | Expected explicit required groups |
| --- | --- |
| `controller route` | `entrypoints` |
| `service repository` | `implementations` |
| `Pinia store component` | `implementations` |
| `WorkspaceDto` | `related_types` |
| `workspace test file` | `tests` |
| `Docker deployment config file` | `configs_docs` |
| `configuration page save logic` | `entrypoints`, `implementations` |
| `form save` | none |

Add a parameterized role-hint test that covers every identifier role admitted by
the approved union, not only the representative rows above:

```python
@pytest.mark.parametrize(
    ("query", "group"),
    [
        ("controller", "entrypoints"),
        ("router", "entrypoints"),
        ("command", "entrypoints"),
        ("view", "entrypoints"),
        ("page", "entrypoints"),
        ("store", "implementations"),
        ("composable", "implementations"),
        ("hook", "implementations"),
        ("service", "implementations"),
        ("handler", "implementations"),
        ("middleware", "implementations"),
        ("repository", "implementations"),
        ("source", "implementations"),
        ("adapter", "implementations"),
        ("client", "implementations"),
        ("storage", "implementations"),
        ("component", "implementations"),
        ("engine", "implementations"),
        ("dto", "related_types"),
        ("entity", "related_types"),
        ("model", "related_types"),
        ("type", "related_types"),
    ],
)
def test_identifier_role_hint_adds_only_its_declared_group(
    query: str,
    group: str,
) -> None:
    pack = build_context_pack(supporting_bundle(query), options())
    assert missing_categories(pack, required=True) == (group,)
```

Where a surface query keyword also contributes the same group, assert the union
still contains the group once.

For the camel-case boundary, create a bundle whose query is `WorkspaceController`, whose `expanded_tokens` and successful planner rewrites contain `controller service dto`, and whose only result is a controller. Assert:

- identifier intent may require `entrypoints` because `tokenize_query()` exposes the controller role hint;
- generated tokens do not require `implementations` or `related_types`;
- the camel-case identifier alone does not trigger the surface `entrypoint` recommendation branch, so it does not invent missing tests.

Add `OpaqueWidget src/opaque.py` as the opposite identifier case. Its identifier,
file hint, and suffix hint are retained by `IdentifierIntent`, but because it has
no listed role hint it adds no required group and causes no promotion.

For the configuration logic boundary, assert `configuration page save logic` does not require or promote `configs_docs` because `wants_artifact` is false.

- [ ] **Step 2: Write failing planner fallback and recommendation tests**

Cover each successful planner intent and status boundary:

```python
@pytest.mark.parametrize(
    ("intent", "required", "recommended"),
    [
        ("feature_lookup", ("entrypoints", "implementations"), ("related_types", "tests")),
        ("data_flow", ("entrypoints", "implementations"), ("related_types", "tests")),
        ("bug_trace", ("entrypoints", "implementations"), ("related_types", "tests")),
        ("endpoint_lookup", ("entrypoints",), ("implementations", "tests")),
        ("symbol_lookup", (), ()),
        ("unknown", (), ()),
    ],
)
def test_successful_planner_intent_fills_only_an_empty_explicit_union(
    intent: str,
    required: tuple[str, ...],
    recommended: tuple[str, ...],
) -> None:
    bundle = bundle_with_plan(query="opaque phrase", status="ok", intent=intent)
    pack = build_context_pack(bundle, options())
    assert missing_categories(pack, required=True) == required
    assert expected_recommended_categories(pack) == recommended
```

The helper should construct a non-empty supporting-only result so every expected structural group is absent and visible in `missing_evidence`.

Also test:

- planner `disabled` and `fallback` contribute no required/recommended intent;
- an explicit required group suppresses all planner-added required groups;
- suppressing planner-required fallback does not suppress recommendations: an
  explicit entrypoint query with a successful `feature_lookup` plan requires
  only `entrypoints` but recommends `implementations`, `related_types`, and
  `tests` in fixed order after removing required groups;
- planner-only required groups do not move ahead of the fixed reading order;
- a successful non-unknown planner, including `symbol_lookup`, prevents the entrypoint/implementation fallback recommendation;
- with no explicit requirement and either no successful planner or a successful
  `unknown` planner intent, present-entrypoint/absent-implementation recommends
  implementation, and the inverse recommends entrypoint;
- required groups are removed from recommendations;
- `supporting` is never required or recommended.

- [ ] **Step 3: Write failing gap/status/reading-order assertions**

Build a source-ordered bundle containing one item in each group. Assert:

```python
assert tuple(pack.groups) == CONTEXT_GROUPS
assert pack.reading_order == (
    "result:3",  # promoted tests group
    "result:0",  # remaining entrypoints
    "result:1",  # remaining implementations
    "result:2",  # remaining related_types
    "result:4",  # configs_docs
    "result:5",  # supporting
)
```

Use a query that explicitly requires only tests for this assertion. Add a second test with several explicit required groups and assert their relative order remains the fixed v1 order, regardless of set construction order.

Lock missing-evidence order and exact text:

```python
assert pack.missing_evidence == (
    MissingEvidence(
        category="entrypoints",
        required=True,
        reason=(
            "required evidence for entrypoints is missing from the bounded "
            "result set"
        ),
    ),
    MissingEvidence(
        category="tests",
        required=False,
        reason=(
            "recommended evidence for tests is missing from the bounded "
            "result set"
        ),
    ),
)
```

Assert status is `partial` when any required category is absent and `ready` when all required categories are present, even if recommended evidence is missing.

- [ ] **Step 4: Run the intent tests and verify red**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  -q
```

Expected: structural tests remain green; new intent/gap/order assertions fail.

- [ ] **Step 5: Implement explicit and planner required-group derivation**

Derive the two existing intent views exactly once:

```python
query_intent = infer_query_intent(bundle.query, bundle.query.split())
identifier_intent = infer_identifier_intent(
    bundle.query,
    tokenize_query(bundle.query),
)
```

Do not pass `bundle.expanded_tokens`, rewritten queries, grep keywords, symbol hints, file hints, or discarded hints into group inference.

Return both values from the internal helper:

```python
@dataclass(frozen=True)
class _ExpectedGroups:
    explicit_required: tuple[str, ...]
    required: tuple[str, ...]
    recommended: tuple[str, ...]
```

`explicit_required` drives reading-order promotion. `required` is the explicit set when non-empty, otherwise the successful planner fallback. Sort every union by `CONTEXT_GROUPS`; never sort alphabetically or iterate a set into output.

- [ ] **Step 6: Implement recommendations, gaps, status, and promotion**

Apply recommendation rules only after required groups are known. For non-empty packs:

```python
missing_required = tuple(
    group for group in expected.required if not pack_groups[group]
)
missing_recommended = tuple(
    group for group in expected.recommended if not pack_groups[group]
)
status = "partial" if missing_required else "ready"
```

Construct missing records required-first, with each partition already in fixed order. Reading order is:

```python
promoted = expected.explicit_required
ordered_groups = (
    *promoted,
    *(group for group in CONTEXT_GROUPS if group not in promoted),
)
reading_order = tuple(
    item_id
    for group in ordered_groups
    for item_id in groups[group]
)
```

Planner-only requirements do not enter `promoted`.

This step replaces the Task 2 non-empty `status` and `missing_evidence`
scaffold. Leave only `next_queries` and `confidence` on their declared temporary
values until their failing tests in Task 4 are in place.

- [ ] **Step 7: Run builder and intent-classifier regressions**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_query_intent.py \
  tests/test_identifier_intent.py \
  tests/test_tokenizer_scanner.py \
  -q
git diff --check
```

Expected: exact intent, missing reason, status, and promotion tests pass without changing existing intent classifiers.

- [ ] **Step 8: Commit structural completeness inference**

```bash
git add src/context_search_tool/context_pack.py tests/test_context_pack.py
git commit -m "feat: infer context pack completeness"
```

### Task 4: Add bounded next queries, readiness confidence, empty state, and payload validation

**Files:**

- Modify: `src/context_search_tool/context_pack.py`
- Modify: `tests/test_context_pack.py`

- [ ] **Step 1: Write failing next-query tests for every category and seed source**

Parameterize the exact table:

| Category | Summary priority | Purpose | Suffix |
| --- | --- | --- | --- |
| `entrypoints` | implementation, related types, entry points | `find_entrypoints` | `controller route entrypoint` |
| `implementations` | entry points, related types, implementation | `find_implementations` | `service implementation` |
| `related_types` | implementation, entry points, related types | `find_related_types` | `dto model type` |
| `tests` | implementation, entry points, related types | `find_tests` | `test` |
| `configs_docs` | entry points, implementation, related types | `find_configs_docs` | `config documentation` |

For each row, make the first priority list empty and the second non-empty once, proving left-to-right selection rather than scoring. Then add focused tests for:

- first non-empty string from the first non-empty summary list;
- `results[0].file_path.stem` fallback;
- original query fallback when only anchors exist;
- Unicode whitespace collapsed to ASCII spaces;
- empty normalized seed omits the suggestion;
- casefold/whitespace duplicate omission without trying another seed for the same category;
- at most three unique suggestions in missing-evidence order;
- reason copied exactly from its missing record;
- fixed suffix preserved in full when a query is capped at 160 Unicode code points;
- `results` and `supporting` produce no suggestion;
- discarded planner hints and rewritten query text never appear.

The truncation assertion must check both `len(query) == 160` and `query.endswith(f" {suffix}")`.

- [ ] **Step 2: Write failing confidence tests and exclude boolean pseudo-numerics**

Cover the full level matrix:

```python
@pytest.mark.parametrize(
    ("has_required_gap", "has_recommended_gap", "priority", "level"),
    [
        (True, False, 0.0, "low"),
        (False, True, 0.0, "medium"),
        (False, False, 1.0, "medium"),
        (False, False, None, "medium"),
        (False, False, 0.0, "high"),
    ],
)
def test_readiness_confidence_matrix(
    has_required_gap: bool,
    has_recommended_gap: bool,
    priority: float | None,
    level: str,
) -> None:
    pack = build_confidence_case(
        has_required_gap=has_required_gap,
        has_recommended_gap=has_recommended_gap,
        evidence_priority=priority,
    )
    assert pack.confidence.level == level
```

Add a separate case with `score_parts={"evidence_priority": False}`. Python booleans compare equal to zero, but this diagnostic is not numeric evidence; it must not count as protected direct evidence. Accept only `type(value) in (int, float)` and `value == 0`.

Add an anchor-only case whose anchor has
`score_parts={"evidence_priority": 0.0}` and assert protected direct evidence is
still absent. Only entries in `bundle.results` can satisfy this rule; evidence
anchors never do.

Assert ordered reason strings for required missing/present, optional recommended state, and protected evidence state. Specifically lock an endpoint query with protected direct evidence and missing recommended implementation/tests at `medium`.

Add an exact `WorkspaceController` identifier case with protected direct evidence,
its hinted entrypoint present, no surface-keyword recommendations, and confidence
`high`. This proves there is no special exact-lookup branch while preserving the
natural high-confidence outcome.

- [ ] **Step 3: Write failing empty, dereference, and JSON-native tests**

The empty assertion is exact:

```python
assert pack.status == "empty"
assert pack.items == ()
assert pack.groups == {group: () for group in CONTEXT_GROUPS}
assert pack.reading_order == ()
assert pack.next_queries == ()
assert pack.confidence == ReadinessConfidence(
    level="none",
    reasons=("no result or evidence anchor is present",),
)
assert pack.missing_evidence == (
    MissingEvidence(
        category="results",
        required=True,
        reason=(
            "no result or evidence anchor is present in the bounded result set"
        ),
    ),
)
assert pack.budget.included_results == 0
assert pack.budget.included_evidence_anchors == 0
assert pack.budget.content_bytes == 0
```

Use an empty bundle whose query explicitly mentions several structural roles.
Even then, `results` is the sole missing record and no structural next query is
fabricated; empty-state handling takes precedence over intent-derived gaps.

Then use `dataclasses.replace()` to construct invalid packs and assert fixed errors for:

- duplicate item ID;
- nonexistent/out-of-range ID/source index;
- repeated fields that disagree with the source object;
- invalid group/role/basis;
- over-budget counts;
- a tuple injected into a scalar field, `Path`, NaN, infinity, non-string dict key, or arbitrary object reaching materialized output causes `ContextPack contains a non-JSON value`; legitimate tuple container fields are first converted to JSON lists.

Finally assert:

```python
payload = context_pack_payload(bundle, pack)
json.dumps(payload, allow_nan=False)
assert isinstance(payload["items"], list)
assert isinstance(payload["reading_order"], list)
assert all(isinstance(value, list) for value in payload["groups"].values())
assert "truncated" not in payload["budget"]
assert "truncated" not in payload
```

Assert each materialized item contains exactly the nine declared reference and
classification fields. In particular, pack items must not duplicate `content`,
`score`, `score_parts`, `semantic_matches`, ranking `reasons`, or follow-up
keywords from their raw result/anchor object.

Lock the complete v1 object key sets as well: the pack has exactly
`schema_version`, `status`, `items`, `groups`, `reading_order`,
`missing_evidence`, `next_queries`, `confidence`, and `budget`; confidence has
only `level`/`reasons`; each missing/next-query object has only its three
declared fields; and budget has exactly the ten approved fields. Assert no
floating-point confidence `score` appears anywhere under `confidence`.

- [ ] **Step 4: Prove the builder is I/O-free using nonexistent paths**

Build with `full_file=True` and results whose paths do not exist on disk. Patch `Path.open`, `Path.read_text`, and `Path.read_bytes` to raise `AssertionError` if called. The build must still succeed from the already-returned content. The module must not import SQLite/vector stores, requests, embedding providers, indexer, or query planner modules.

- [ ] **Step 5: Run the expanded tests and verify red**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  -q
```

Expected: new query/confidence/empty/payload tests fail; Tasks 1–3 remain green.

- [ ] **Step 6: Implement next-query composition exactly**

Normalize seeds with:

```python
def _normalize_seed(value: str) -> str:
    return " ".join(value.strip().split())
```

Compose with full suffix preservation:

```python
max_seed_length = 160 - len(role_terms) - 1
bounded_seed = normalized_seed[:max_seed_length].strip()
if not bounded_seed:
    return None
query = f"{bounded_seed} {role_terms}"
```

Use normalized query `.casefold()` as the dedupe key. Do not derive a second seed after a duplicate and do not inspect anchors for a seed.

- [ ] **Step 7: Implement confidence, empty state, and JSON-native payloads**

Confidence should consume the already-derived missing records and expected recommendation set rather than re-running intent inference. Manual payload construction converts every tuple to a list and keeps all six groups. Validate recursively that only JSON-native scalar/list/dict values exist, string keys are used, and all floats are finite; then call `json.dumps(payload, allow_nan=False)` inside the validation boundary.

`resolve_context_item()` must validate ID, source, index, path, and lines before returning the raw source object. `context_pack_payload()` must call structural/reference validation again so an externally constructed or replaced pack cannot bypass the contract.

- [ ] **Step 8: Run the complete builder contract suite**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_retrieval_pipeline.py \
  -q
git diff --check
```

Expected: all builder branches pass, the payload is accepted by standard JSON encoding, and retrieval remains unchanged.

- [ ] **Step 9: Commit ContextPack v1 core**

```bash
git add src/context_search_tool/context_pack.py tests/test_context_pack.py
git commit -m "feat: complete context pack schema v1"
```

### Task 5: Add shared formatting and the `cst context` command

**Files:**

- Modify: `src/context_search_tool/formatters.py`
- Modify: `src/context_search_tool/cli.py`
- Modify: `tests/test_formatters.py`
- Modify: `tests/test_cli_commands.py`

- [ ] **Step 1: Lock raw JSON byte-for-byte, then write failing context formatter tests**

Before changing `format_json()`, add a literal expected JSON string for a small
deterministic bundle and assert the complete output string, including indentation,
ASCII escaping, sorted object keys, and terminal-newline behavior. Generate the
literal once from the pre-change implementation, review it, and commit it as test
data; the test must not derive its expected value through `query_payload()` or
another serializer that will be refactored in the same change.

Then compare parsed raw output to context output:

```python
def test_context_json_adds_only_context_pack_to_raw_query_payload() -> None:
    bundle = context_bundle()
    pack = build_context_pack(bundle, context_options())
    raw = json.loads(format_json(bundle))
    context = json.loads(format_context_json(raw, bundle, pack))

    assert context.pop("context_pack") == context_pack_payload(bundle, pack)
    assert context == raw
```

This test must include query variants, semantic matches, evidence anchors, summary, planner diagnostics, discarded hints, numeric score parts, and raw ranked order. It is the compatibility guard for the formatter refactor.

Add Markdown assertions for the exact section order:

```text
# Context Pack
Query:
Status:
Confidence:
## Read First
## Missing Evidence
## Next Queries
## Budget
```

For every ID in `reading_order`, assert one rendered location heading and one source snippet. Verify each row includes group/role, location, and existing reasons; anchor rows use anchor reasons/content. Add both a nonexistent reading-order ID and an invalid source-index pack and assert `ContextPackError("invalid ContextPack item reference")` rather than silent omission.

- [ ] **Step 2: Write failing CLI success, sharing, and compatibility tests**

Extend the existing lifecycle test to invoke:

```python
context_result = runner.invoke(
    app,
    ["context", str(repo), "/apply/audit/pageEs", "--json"],
)
assert context_result.exit_code == 0
context_payload = json.loads(context_result.output)
assert context_payload["context_pack"]["schema_version"] == 1
assert context_payload["results"] == parsed["results"]
```

Add focused monkeypatched tests that assert:

- `context` supports the same cwd/repo positional forms as `query`;
- `--context-lines`, `--full-file`, `--planner`, and `--no-planner` reach the shared query invocation unchanged; captured pack options also reflect the effective symmetric context window, full-file flag, configured result limit, derived anchor limit, and configured full-file byte cap;
- conflicting planner flags produce the existing exact error for both commands;
- missing index produces the existing exact error and no artifacts for both commands;
- one context call increments a fake `query_repository` counter once and a fake `build_context_pack` counter once;
- one query call never invokes `build_context_pack`;
- context default output is Markdown and `--json` is structured JSON.
- a monkeypatched valid empty `QueryBundle` makes `context --json` exit 0 with
  `context_pack.status == "empty"`, its sole `results` missing-evidence record,
  and no fabricated next query; the default Markdown path also renders the
  empty pack without an error.

Before implementation, add a test that calls raw `query --json` and compares its
entire parsed object with a literal pre-refactor expected object. Do not update
either compatibility fixture merely to make the refactor pass.

- [ ] **Step 3: Write failing CLI phase-boundary tests**

Parameterize the pack phase:

| Injected failure | Expected stderr |
| --- | --- |
| `ContextPackError("invalid ContextPack classification")` | `Error: context_failed: invalid ContextPack classification` |
| builder `ValueError("secret")` | `Error: context_failed: Context pack construction failed` |
| builder `RuntimeError("secret")` | `Error: context_failed: Context pack construction failed` |
| invalid Markdown reference | `Error: context_failed: invalid ContextPack item reference` |
| JSON encoding `TypeError("secret")` | `Error: context_failed: Context pack construction failed` |

Every case exits 1, including `--json`, and output must not contain `secret`. Add a separate query-phase `ValueError` assertion proving it still uses the existing `Error: <message>` behavior rather than `context_failed`.

- [ ] **Step 4: Run format/CLI tests and verify red**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  -q
```

Expected: new symbols/command are absent; every pre-existing raw-query test still passes.

- [ ] **Step 5: Refactor raw formatter payload construction without a shape change**

Move the existing dictionary literal from `format_json()` into:

```python
def query_payload(bundle: QueryBundle) -> dict[str, Any]:
    return {
        "query": bundle.query,
        "expanded_tokens": bundle.expanded_tokens,
        "query_variants": [
            _query_variant_payload(variant) for variant in bundle.query_variants
        ],
        "variant_retrieval_status": bundle.variant_retrieval_status,
        "followup_keywords": bundle.followup_keywords,
        "summary": {
            "entry_points": bundle.summary.entry_points,
            "implementation": bundle.summary.implementation,
            "related_types": bundle.summary.related_types,
            "possibly_legacy": bundle.summary.possibly_legacy,
        },
        "planner": _planner_payload(bundle.planner),
        "results": [
            {
                "file_path": result.file_path.as_posix(),
                "start_line": result.start_line,
                "end_line": result.end_line,
                "content": result.content,
                "score": result.score,
                "score_parts": result.score_parts,
                "reasons": result.reasons,
                "followup_keywords": result.followup_keywords,
                "semantic_matches": [
                    _semantic_match_payload(match)
                    for match in result.semantic_matches
                ],
            }
            for result in bundle.results
        ],
        "evidence_anchors": [
            _anchor_payload(anchor) for anchor in bundle.evidence_anchors
        ],
    }


def format_json(bundle: QueryBundle) -> str:
    return json.dumps(
        query_payload(bundle),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
```

The implementation must copy the existing body exactly; do not serialize then parse JSON, rename fields, change list order, or deduplicate raw data.

Add:

```python
def format_context_json(
    raw_payload: dict[str, Any],
    bundle: QueryBundle,
    pack: ContextPack,
) -> str:
    payload = dict(raw_payload)
    payload["context_pack"] = context_pack_payload(bundle, pack)
    return json.dumps(
        payload,
        ensure_ascii=True,
        indent=2,
        sort_keys=False,
        allow_nan=False,
    )
```

`format_json()` keeps `sort_keys=True` for raw compatibility. Context JSON uses insertion order so the six `groups` keys retain the required v1 order; add `assert list(context["context_pack"]["groups"]) == list(CONTEXT_GROUPS)` to the contract test.

The locked dereference API accepts a `ContextPackItem`, not an ID. Resolve the
reading-order IDs explicitly before calling it:

```python
items_by_id = {item.id: item for item in pack.items}
for item_id in pack.reading_order:
    item = items_by_id.get(item_id)
    if item is None:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    source = resolve_context_item(bundle, item)
```

Use `source` for the row content and reasons. The builder/payload validation
already owns duplicate-ID detection; the formatter must not silently skip or
invent an item when the lookup fails. Reuse `_markdown_fence` and existing reason
formatting; do not duplicate or mutate source content. Emit `Planner: <status>`
for `disabled`, `ok`, and `fallback`, and add the existing concise planner-hint
line only when `_planner_markdown_line()` returns one.

- [ ] **Step 6: Extract only shared CLI query preparation**

Declare `context` with the same two positional arguments and the same
`--json`, `--context-lines`, `--full-file`, `--planner`, and `--no-planner`
option defaults/help semantics as `query`. Do not add a CLI `final_top_k` or any
pack-specific option.

Use one helper for repository/question resolution, index check, config load, planner conflict/override, and stale-schema warning:

```python
def _prepare_query_command(
    repo_or_question: str,
    question: str | None,
    *,
    planner: bool,
    no_planner: bool,
) -> tuple[Path, str, ToolConfig]:
    if question is None:
        repo = _resolve_repo(None)
        query_text = repo_or_question
    else:
        repo = _resolve_repo(Path(repo_or_question))
        query_text = question

    _require_index(repo)
    config = load_config(repo)
    if planner and no_planner:
        typer.echo(
            "Error: --planner and --no-planner cannot be used together",
            err=True,
        )
        raise typer.Exit(code=1)
    if planner or no_planner:
        config = replace(
            config,
            query_planner=replace(config.query_planner, enabled=planner),
        )
    _warn_if_signal_schema_stale(repo)
    return repo, query_text, config
```

Both public commands call `query_repository()` themselves inside their query phase. Do not hide the retrieval and pack calls in one broad helper or exception block.

The context command flow is:

```python
repo, query_text, config = _prepare_query_command(
    repo_or_question,
    question,
    planner=planner,
    no_planner=no_planner,
)

try:
    bundle = query_repository(
        repo,
        query_text,
        config,
        context_lines=context_lines,
        full_file=full_file,
    )
    raw_payload = query_payload(bundle)
except (ValueError, requests.HTTPError) as exc:
    _exit_with_error(exc)

try:
    anchor_limit = evidence_anchor_top_k(config.retrieval.final_top_k)
    pack_options = resolve_context_pack_options(
        config,
        context_lines=context_lines,
        full_file=full_file,
        max_evidence_anchors=anchor_limit,
    )
    pack = build_context_pack(bundle, pack_options)
    output = (
        format_context_json(raw_payload, bundle, pack)
        if json_output
        else format_context_markdown(bundle, pack)
    )
except ContextPackError as exc:
    _exit_context_error(str(exc))
except Exception:
    _exit_context_error(UNEXPECTED_CONTEXT_ERROR)

typer.echo(output)
```

Catch `Exception`, never `BaseException`, in the pack phase. `_exit_context_error` must not attach or print the unexpected internal exception.

- [ ] **Step 7: Run formatter/CLI and raw-operation regression suites**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  -q
git diff --check
```

Expected: new context output passes, raw formatter text is byte-for-byte
unchanged, raw CLI payloads are structurally identical, and all failures stay in
the declared phase.

- [ ] **Step 8: Commit the CLI surface**

```bash
git add \
  src/context_search_tool/formatters.py \
  src/context_search_tool/cli.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py
git commit -m "feat: add context pack CLI output"
```

### Task 6: Add `context_search_context`, exact error envelopes, and bounded feedback

**Files:**

- Modify: `src/context_search_tool/mcp_tools.py`
- Modify: `src/context_search_tool/mcp_server.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing MCP success and raw-preservation tests**

Import `context_search_context_tool` and extend the Java lifecycle test:

```python
context = context_search_context_tool(
    repo=str(repo),
    query="/apply/audit/pageEs",
    context_lines=0,
    full_file=False,
    final_top_k=1,
)

assert context["ok"] is True
assert context["repo"] == str(repo)
assert context["index"] == queried["index"]
assert context["context_pack"]["schema_version"] == 1
assert context["results"] == queried["results"]
assert context["evidence_anchors"] == queried["evidence_anchors"]
assert context["context_pack"]["budget"]["max_results"] == 1
assert context["context_pack"]["budget"]["max_evidence_anchors"] == 1
assert context["context_pack"]["budget"]["max_items"] == 2
assert context["context_pack"]["budget"]["context_before_lines"] == 0
assert context["context_pack"]["budget"]["context_after_lines"] == 0
```

With a monkeypatched deterministic `QueryBundle`, compare every raw key from `_query_payload(bundle)` against the context payload and assert the context pack equals the CLI pack payload for the same bundle/options. Also call `json.dumps(context, allow_nan=False)` with no custom encoder.

Add a valid empty-bundle case and assert the MCP response keeps `ok is True`,
uses `context_pack.status == "empty"`, has the single required `results` gap and
no next query, and does not contain an `error` key. This distinguishes successful
zero evidence from pack construction failure at the public boundary.

- [ ] **Step 2: Write failing one-pass and error-envelope tests**

Use counters to assert one query and one pack build per successful context call. Cover exact errors:

```python
assert context_search_context_tool(str(repo), "query", final_top_k=0) == {
    "ok": False,
    "error": {
        "code": "query_failed",
        "message": "final_top_k must be greater than zero",
    },
}
```

Add matching `repo_not_found` and `missing_index` assertions based on the existing query tool. Then parameterize pack failures:

```python
@pytest.mark.parametrize(
    ("exception", "message"),
    [
        (
            ContextPackError("ContextPack budget exceeded"),
            "ContextPack budget exceeded",
        ),
        (ValueError("private detail"), "Context pack construction failed"),
        (RuntimeError("private detail"), "Context pack construction failed"),
    ],
)
def test_mcp_context_contains_pack_phase_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    message: str,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    def fail_pack(*args: object, **kwargs: object) -> ContextPack:
        raise exception

    monkeypatch.setattr(mcp_tools, "build_context_pack", fail_pack)
    payload = context_search_context_tool(str(repo), "audit")

    assert payload == {
        "ok": False,
        "error": {"code": "context_failed", "message": message},
    }
```

Assert no raw bundle fields leak into an error envelope and `private detail` is absent. Add a `KeyboardInterrupt` test only if the test runner can safely prove it propagates; never catch `BaseException` in production.

- [ ] **Step 3: Write failing feedback privacy tests**

After one context call, inspect the last JSONL event. Keep the existing base event fields and assert:

```python
assert event["tool"] == "context_search_context"
assert event["context_pack"] == {
    "status": "ready",
    "confidence": "medium",
    "item_count": 3,
    "group_counts": {
        "entrypoints": 1,
        "implementations": 1,
        "related_types": 1,
        "tests": 0,
        "configs_docs": 0,
        "supporting": 0,
    },
    "required_missing_categories": [],
    "recommended_missing_categories": ["tests"],
    "next_query_count": 1,
    "budget": {
        "max_results": 12,
        "max_evidence_anchors": 4,
        "max_items": 16,
        "included_results": 3,
        "included_evidence_anchors": 0,
        "content_bytes": expected_bytes,
    },
}
```

Use the actual test fixture counts rather than forcing this illustrative count if they differ. The schema and allowed keys are fixed.

Insert unique sentinels into source content, file paths, item IDs, composed next-query text, planner rewrites, semantic variant text, and discarded hints. Assert none appears in `json.dumps(event)`. The original raw `query` field remains because existing query logging is explicitly unchanged.

For an unexpected pack failure, assert the event still uses
`tool="context_search_context"` and `error_code="context_failed"`, omits the
nested context metadata because no valid pack exists, and contains neither the
private exception text nor partial raw bundle fields.

Add a malformed-payload test proving group counts are filtered to the six group
names, missing categories are filtered to those six names plus the special
required-only `results` category, and non-integer/boolean counts are ignored
rather than logging arbitrary nested values. For the valid empty MCP case,
assert feedback reports `status="empty"`, `confidence="none"`, zero item/next
query counts, and `required_missing_categories=["results"]` without adding a
path, item ID, or query string.

- [ ] **Step 4: Write failing MCP server registration tests**

In `tests/test_mcp_server.py`, assert:

```python
assert callable(mcp_server.context_search_query)
assert callable(mcp_server.context_search_context)
assert inspect.signature(mcp_server.context_search_context) == inspect.signature(
    mcp_server.context_search_query
)
```

The descriptions must distinguish raw ranked search from an agent-oriented context pack.

- [ ] **Step 5: Run MCP tests and verify red**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  -q
```

Expected: new tool/registration tests fail; existing query/index/stats/explain tests remain green.

- [ ] **Step 6: Implement the MCP query phase and pack phase separately**

Follow the same repository/missing-index path as `context_search_query_tool`. The query phase contains config override validation, `query_repository`, `_query_payload`, `ok`/`repo`/`index`, and catches only the existing query exceptions. The pack phase computes the public anchor limit, resolves options, builds once, materializes once, and catches:

```text
except ContextPackError as exc:
    payload = _error("context_failed", str(exc))
except Exception:
    payload = _error("context_failed", UNEXPECTED_CONTEXT_ERROR)
```

Append feedback after either success or handled error. Feedback failure remains non-fatal as it is for query today.

- [ ] **Step 7: Generalize feedback with a default that preserves query events**

Keep `_try_append_query_feedback` and `_append_query_feedback` names so existing focused tests and private call sites remain stable. Add `tool: str = "context_search_query"`; existing calls pass nothing and therefore produce byte-equivalent event shape. Only when `tool == "context_search_context"` add a nested `context_pack` object generated by a fail-closed `_feedback_context_pack_payload()` helper.

The helper may read only validated status/confidence enum values, list lengths,
fixed category names, and the approved budget keys. Canonicalize and deduplicate
missing categories in fixed order: required accepts `results` plus the six group
names (maximum seven), while recommended accepts only the six group names.
Accept count/budget values only when `type(value) is int`, the value is
non-negative, and the key is approved. It must never copy item dictionaries,
missing reasons, or next-query objects.

- [ ] **Step 8: Register the server operation**

Add the wrapper beside `context_search_query`:

```python
@mcp.tool()
def context_search_context(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    """Return an agent-oriented ContextPack from one bounded retrieval pass."""
    return context_search_context_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
    )
```

- [ ] **Step 9: Run all public-surface and privacy tests**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  -q
git diff --check
```

Expected: both public context surfaces pass, query feedback remains unchanged, context feedback is bounded, and all payloads encode with standard JSON.

- [ ] **Step 10: Commit the MCP surface**

```bash
git add \
  src/context_search_tool/mcp_tools.py \
  src/context_search_tool/mcp_server.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py
git commit -m "feat: add context pack MCP tool"
```

### Task 7: Activate typed `context_pack` quality cases without changing result mode

**Files:**

- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/metrics.py`
- Modify: `src/context_search_tool/quality/runner.py`
- Modify: `tests/test_quality_cases.py`
- Modify: `tests/test_quality_metrics.py`
- Modify: `tests/test_quality_runner.py`
- Modify: `tests/test_quality_aggregate.py`

- [ ] **Step 1: Write failing fixture-schema tests for the two legal modes**

In `tests/test_quality_cases.py`, add a successful canonical parse:

```python
case = load_case(
    {
        "mode": "context_pack",
        "expected_context_groups": {
            "entrypoints": [{"path": "src/AppController.java"}],
            "implementations": [
                {"glob": "src/**/*ServiceImpl.java"},
                {"contains": "Repository"},
            ],
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "medium",
    }
)

assert case.mode == "context_pack"
assert case.expected_context_groups == {
    "entrypoints": (Matcher(path="src/AppController.java"),),
    "implementations": (
        Matcher(glob="src/**/*ServiceImpl.java"),
        Matcher(contains="Repository"),
    ),
}
assert case.expected_pack_status == "ready"
assert case.minimum_context_confidence == "medium"
```

Parameterize exact rejections:

- mode is not `results` or `context_pack`;
- any context-only field appears on a `results` case, including an explicitly empty object/string-invalid value;
- `expected_context_groups` is not an object;
- a group name is not one of the six v1 names;
- a group's value is not a list/tuple of valid existing matchers;
- status is not `empty`, `partial`, or `ready`;
- minimum confidence is not `none`, `low`, `medium`, or `high`;
- explicit nulls for status/confidence are rejected when the field is present.

Existing cases with no mode must still parse as `results` with empty/`None` context fields.

- [ ] **Step 2: Write failing profile invariant tests for `p2_context_pack`**

Extend `validate_profile_compatible()` coverage:

```python
validate_profile_compatible(
    "p2_context_pack",
    ToolConfig(
        embedding=EmbeddingConfig(
            provider="hash",
            model="hash-v1",
            dimensions=384,
        ),
        query_planner=QueryPlannerConfig(enabled=False),
    ),
    canonical=True,
)
```

Reject BGE/remote embeddings, enabled planner, remote embedding base URL, and API-key environment configuration for this profile. This proves the profile is offline, planner-disabled, and deterministic rather than merely named that way.

- [ ] **Step 3: Write failing context evaluation tests**

In `tests/test_quality_metrics.py`, construct a typed pack with:

- two expected matchers in one group where one matches;
- one matcher in a second group that matches;
- one non-empty unexpected group;
- one required and two recommended missing records;
- two next queries;
- known content byte count;
- status `ready` and confidence `medium`.

Apply context evaluation to an existing raw `CaseEvaluation` and assert:

```python
assert evaluation.metrics["context_expected_count"] == 3
assert evaluation.metrics["context_matched_count"] == 2
assert evaluation.metrics["context_completeness"] == pytest.approx(2 / 3)
assert evaluation.metrics["context_group_count"] == 3
assert evaluation.metrics["required_missing_count"] == 1
assert evaluation.metrics["recommended_missing_count"] == 2
assert evaluation.metrics["next_query_count"] == 2
assert evaluation.metrics["context_content_bytes"] == 321
```

Assert deterministic failures for the unmatched pair, exact status mismatch, and confidence below threshold. The confidence order is:

```python
_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
```

Add cases for:

- path/glob/contains matcher semantics within the declared group only;
- an item in the wrong group does not satisfy the pair;
- duplicate pack paths do not over-count one expected pair;
- no expected pairs produces `context_completeness is None` and zero expected/matched counts;
- required, known-gap, and informational gate statuses retain existing semantics after context failures;
- the original raw metrics/top results are preserved.
- a `context_pack` case with both a failing raw expectation and a failing context
  expectation retains both failures in raw-first order; context evaluation must
  be additive rather than replacing the existing result evaluation.

- [ ] **Step 4: Write failing runner tests for conditional construction and metadata**

Patch `query_repository`, `build_context_pack`, and `evaluate_context_pack` with counters. Use a fixture containing one `results` case and one `context_pack` case, then assert:

- query runs once per case;
- pack build runs exactly once for the context case and zero times for the results case;
- the builder receives `max_results=config.retrieval.final_top_k`, `max_evidence_anchors=evidence_anchor_top_k(max_results)`, default config context windows, `full_file=False`, and configured full-file byte cap;
- the synthetic context record has
  `{"context_pack": {"status": "ready", "confidence": "medium"}}`;
- the result record has no `context_pack` key and exactly its previous shape;
- a pack exception becomes the existing quality `error` case rather than a fabricated partial pack;
- non-executed/skipped records do not invent status/confidence metadata.
- one context case combines an existing raw-result failure, a failing
  `profile_expectations` check, and a context-pair failure; assert failures stay
  in that exact raw-result → profile-expectation → context order.

Extend the existing snapshot-source tests so `p2_context_pack` ignores a
configured `path_env` and smoke-root repository in favor of its committed
snapshot, and so a missing P2 snapshot fails with the profile name in the fixed
error. This is the direct regression proof for adding P2 to
`_SNAPSHOT_ONLY_PROFILES`.

Add a real builder integration test with an anchor-only README bundle and assert the item role is exactly `readme`, basis `anchor_kind`, group `configs_docs`.

- [ ] **Step 5: Write the null-aware aggregation regression before touching aggregate code**

In `tests/test_quality_aggregate.py`:

```python
def test_context_completeness_aggregation_excludes_null_cases() -> None:
    aggregate = aggregate_cases(
        [
            _case(
                "a",
                "measured",
                "pass",
                attempted=True,
                metrics={"context_completeness": 0.5},
            ),
            _case(
                "a",
                "no-expectations",
                "pass",
                attempted=True,
                metrics={"context_completeness": None},
            ),
        ],
        [_repo("a")],
        "p2_context_pack",
    )

    assert aggregate["metrics"]["overall"]["context_completeness"] == {
        "count": 1,
        "mean": 0.5,
    }
```

This test should already pass. If it does, do not edit `quality/aggregate.py`.

- [ ] **Step 6: Run schema/evaluation/runner tests and verify the intended split**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_aggregate.py \
  -q
```

Expected: the new aggregate regression passes immediately; schema/evaluation/runner tests fail because their features are absent.

- [ ] **Step 7: Implement typed context expectations and exact mode validation**

Add constants in `quality/cases.py`:

```python
_QUALITY_MODES = {"results", "context_pack"}
_PACK_STATUSES = {"empty", "partial", "ready"}
_CONFIDENCE_LEVELS = {"none", "low", "medium", "high"}
_CONTEXT_ONLY_FIELDS = {
    "expected_context_groups",
    "expected_pack_status",
    "minimum_context_confidence",
}
```

Parse `mode` before context fields. For `results`, reject if any context-only key is present, even when its value is empty. For `context_pack`, parse groups in `CONTEXT_GROUPS` order and reuse `Matcher.from_raw()` unchanged.

Extend canonical profile validation with a dedicated `p2_context_pack` branch. Do not silently treat every unknown profile as P2-compatible.

- [ ] **Step 8: Implement context evaluation as an additive pass**

Add:

```python
def evaluate_context_pack(
    case: QualityCase,
    pack: ContextPack,
    evaluation: CaseEvaluation,
) -> CaseEvaluation:
    """Apply context-only expectations and metrics to raw evaluation."""
```

Iterate expected pairs in fixed group order and matcher declaration order. A pair counts once if any item path in that exact group matches. Append failures after existing raw failures in this order: missing pairs, pack status, minimum confidence. Recompute status through the existing `_status(case.gate, failures)` helper.

- [ ] **Step 9: Wire only context cases in the runner**

Import `evidence_anchor_top_k`, resolve options with `context_lines=None` and `full_file=False`, and build after the one query call:

Preserve the current two raw passes before adding context evaluation. The exact
order inside the case loop is `evaluate_case()` →
`_apply_profile_expectations()` → `build_context_pack()` →
`evaluate_context_pack()` → `_case_record()`. Do not insert context evaluation
before `_apply_profile_expectations()`, because that would reorder existing
profile failures behind newly added context failures.

```python
pack: ContextPack | None = None
if case.mode == "context_pack":
    pack_options = resolve_context_pack_options(
        repo_config,
        context_lines=None,
        full_file=False,
        max_evidence_anchors=evidence_anchor_top_k(
            repo_config.retrieval.final_top_k
        ),
    )
    pack = build_context_pack(bundle, pack_options)
    evaluation = evaluate_context_pack(case, pack, evaluation)
```

Pass `pack` into `_case_record` as a keyword-only optional argument and emit nested status/confidence metadata only when non-`None`. Add `p2_context_pack` to `_SNAPSHOT_ONLY_PROFILES` so direct paths/environment variables cannot replace its committed fixtures.

- [ ] **Step 10: Run all quality unit suites**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_aggregate.py \
  tests/test_quality_reports.py \
  tests/test_quality_cli.py \
  -q
git diff --check
```

Expected: context quality tests pass, result-mode tests/reports remain unchanged, and `quality/aggregate.py` is unmodified.

- [ ] **Step 11: Commit quality-mode support**

```bash
git add \
  src/context_search_tool/quality/cases.py \
  src/context_search_tool/quality/metrics.py \
  src/context_search_tool/quality/runner.py \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_aggregate.py
git commit -m "feat: evaluate context pack quality cases"
```

### Task 8: Add the deterministic five-case P2 profile and committed snapshots

**Files:**

- Create: `tests/fixtures/context-pack-java/src/main/java/com/example/workspace/controller/WorkspaceController.java`
- Create: `tests/fixtures/context-pack-java/src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java`
- Create: `tests/fixtures/context-pack-java/src/main/java/com/example/workspace/dto/WorkspaceDto.java`
- Create: `tests/fixtures/context-pack-java/src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java`
- Create: `tests/fixtures/context-pack-docs/README.md`
- Modify: `tests/fixtures/retrieval_quality/queries.json`
- Modify: `tests/test_quality_catalog.py`
- Create: `tests/test_quality_p2.py`

- [ ] **Step 1: Write the approved P2 catalog manifest tests first**

In `tests/test_quality_catalog.py`, add `p2_context_pack` to `EXPECTED_PROFILE_CONFIGS`:

```python
{
    "p2_context_pack": {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    },
}
```

Add three repo wiring rows in this order after `java_spring_mini` and before remote/calibration repos:

```python
(
    "context_pack_java",
    ("p2_context_pack",),
    "",
    "",
    "tests/fixtures/context-pack-java",
    {},
),
(
    "context_pack_frontend",
    ("p2_context_pack",),
    "",
    "",
    "tests/fixtures/real_projects/program_tool",
    {},
),
(
    "context_pack_docs",
    ("p2_context_pack",),
    "",
    "",
    "tests/fixtures/context-pack-docs",
    {},
),
```

Update the expected catalog case count from 44 to 49. Extend the manifest helper/defaults with the three new typed context fields so existing result cases explicitly expect `{}`, `None`, `None`, while the five P2 cases lock their declared values.

Add:

```python
EXPECTED_P2_CASE_KEYS = {
    "context_pack_java/workspace-page-flow",
    "context_pack_java/workspace-test-file",
    "context_pack_java/workspace-service-symbol",
    "context_pack_frontend/qrcode-feature-context",
    "context_pack_docs/program-tool-developer-docs",
}
```

Assert the selected set for `p2_context_pack` equals this set, every case is required and `mode == "context_pack"`, and no P2 case is selected by `ci`, `smoke`, planner, or either Phase 1 profile. Also lock `ci` to its existing eight selected cases before and after adding the P2-only repos.

Lock exact new-file SHA-256 values:

```python
P2_SNAPSHOT_SHA256 = {
    "context-pack-java/src/main/java/com/example/workspace/controller/WorkspaceController.java": "8eae09e3be12a8a7fd2d3fae0f0f78f6f976ea7d83c7d35a55c43f2f1a217836",
    "context-pack-java/src/main/java/com/example/workspace/dto/WorkspaceDto.java": "4fc2a6227363216628f45820feb35c61c35d9fe644eddeb98853803562bef08a",
    "context-pack-java/src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java": "a91c95dc085f344436a68f2d4e7e9faf60b0b5ad374c1fdd7542d974febff73d",
    "context-pack-java/src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java": "6f92b729f375d82c7b9fb0a3f20a18d955814e21673797569be81433d35f84e3",
    "context-pack-docs/README.md": "13be45c211302d2cec0ff73310ab374f32ef73302189fc00998e53a3173347fc",
}
```

- [ ] **Step 2: Write the end-to-end P2 profile test before adding the profile**

Create `tests/test_quality_p2.py`:

```python
from pathlib import Path

from context_search_tool.quality.runner import run_quality_fixture


CATALOG = Path(__file__).parent / "fixtures" / "retrieval_quality" / "queries.json"


def test_p2_context_pack_profile_passes_all_required_cases() -> None:
    report = run_quality_fixture(
        CATALOG,
        profile="p2_context_pack",
        output_path=None,
        markdown_path=None,
    )

    counts = dict(report["aggregate"])
    counts.pop("metrics")
    assert counts == {
        "total": 5,
        "selected": 5,
        "attempted": 5,
        "executed": 5,
        "passed": 5,
        "failed": 0,
        "skipped": 0,
        "known_gaps": 0,
        "informational": 0,
        "errors": 0,
    }
    overall = report["aggregate"]["metrics"]["overall"]
    assert overall["context_completeness"] == {"count": 5, "mean": 1.0}
    assert overall["context_expected_count"] == {"count": 5, "mean": 2.0}

    cases = {case["case_id"]: case for case in report["cases"]}
    assert {case["context_pack"]["status"] for case in cases.values()} == {
        "ready"
    }
    assert {
        case_id: case["context_pack"]["confidence"]
        for case_id, case in cases.items()
    } == {
        "workspace-page-flow": "high",
        "workspace-test-file": "high",
        "workspace-service-symbol": "high",
        "qrcode-feature-context": "medium",
        "program-tool-developer-docs": "medium",
    }
    assert cases["workspace-service-symbol"]["metrics"][
        "required_missing_count"
    ] == 0
    assert cases["qrcode-feature-context"]["metrics"][
        "recommended_missing_count"
    ] == 1
    assert cases["program-tool-developer-docs"]["metrics"][
        "context_content_bytes"
    ] == 93
```

This is an ordinary offline deterministic test, not an `integration` test:
`integration` is reserved by this repository for external-service requirements.
The aggregate metric tree remains asserted separately from the ten exact count
fields.

- [ ] **Step 3: Run catalog and P2 tests and verify red**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py \
  -q
```

Expected: catalog/profile tests fail because the profile, repos, cases, and files do not exist.

- [ ] **Step 4: Add the exact P2-only Java snapshot**

Create `WorkspaceController.java` with a final newline:

```java
package com.example.workspace.controller;

import com.example.workspace.dto.WorkspaceDto;
import com.example.workspace.service.impl.WorkspaceServiceImpl;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/workspace")
public class WorkspaceController {
    private final WorkspaceServiceImpl workspaceService;

    public WorkspaceController(WorkspaceServiceImpl workspaceService) {
        this.workspaceService = workspaceService;
    }

    @GetMapping("/page")
    public WorkspaceDto page() {
        return workspaceService.page();
    }
}
```

Create `WorkspaceServiceImpl.java` with a final newline:

```java
package com.example.workspace.service.impl;

import com.example.workspace.dto.WorkspaceDto;

public class WorkspaceServiceImpl {
    public WorkspaceDto page() {
        return new WorkspaceDto("ready");
    }
}
```

Create `WorkspaceDto.java` with a final newline:

```java
package com.example.workspace.dto;

public class WorkspaceDto {
    private final String status;

    public WorkspaceDto(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }
}
```

Create `WorkspaceControllerTest.java` with a final newline:

```java
package com.example.workspace.controller;

public class WorkspaceControllerTest {
    public void returnsWorkspacePage() {
        String scenario = "workspace test file";
    }
}
```

These four paths deliberately exercise existing `entrypoint`, `service_impl`, `data_type`, and `test` path roles. Do not add new classifier rules for them.

- [ ] **Step 5: Add the exact isolated README snapshot**

Create `tests/fixtures/context-pack-docs/README.md` with exactly:

```markdown
# Program Tool Developer Setup

Install dependencies and run the developer utilities locally.
```

Include the final newline. The committed file is therefore 94 UTF-8 bytes and
must retain the declared SHA-256, but default retrieval normalizes the returned
context window without that final newline. The pack/report expectation is 93
returned content bytes. Do not add package metadata or another file; anchor-only
behavior is part of the test.

- [ ] **Step 6: Register the offline P2 profile and three repos**

Add the profile config shown in Step 1 to `profile_configs`.

Add `context_pack_java` with three cases:

```json
{
  "repo_key": "context_pack_java",
  "snapshot_path": "tests/fixtures/context-pack-java",
  "profiles": ["p2_context_pack"],
  "queries": [
    {
      "id": "workspace-page-flow",
      "query": "workspace page flow controller service dto",
      "profiles": ["p2_context_pack"],
      "mode": "context_pack",
      "tags": ["p2", "java_spring", "context_pack"],
      "gate": "required",
      "expected_top_k": [
        {
          "path": "src/main/java/com/example/workspace/controller/WorkspaceController.java",
          "top_k": 5
        },
        {
          "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java",
          "top_k": 5
        },
        {
          "path": "src/main/java/com/example/workspace/dto/WorkspaceDto.java",
          "top_k": 5
        }
      ],
      "expected_context_groups": {
        "entrypoints": [
          {
            "path": "src/main/java/com/example/workspace/controller/WorkspaceController.java"
          }
        ],
        "implementations": [
          {
            "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java"
          }
        ],
        "related_types": [
          {
            "path": "src/main/java/com/example/workspace/dto/WorkspaceDto.java"
          }
        ]
      },
      "expected_pack_status": "ready",
      "minimum_context_confidence": "high"
    },
    {
      "id": "workspace-test-file",
      "query": "workspace test file",
      "profiles": ["p2_context_pack"],
      "mode": "context_pack",
      "tags": ["p2", "java", "test", "context_pack"],
      "gate": "required",
      "expected_top_k": [
        {
          "path": "src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java",
          "top_k": 5
        }
      ],
      "expected_context_groups": {
        "tests": [
          {
            "path": "src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java"
          }
        ]
      },
      "expected_pack_status": "ready",
      "minimum_context_confidence": "high"
    },
    {
      "id": "workspace-service-symbol",
      "query": "WorkspaceServiceImpl",
      "profiles": ["p2_context_pack"],
      "mode": "context_pack",
      "tags": ["p2", "java", "exact_symbol", "context_pack"],
      "gate": "required",
      "expected_top_k": [
        {
          "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java",
          "top_k": 3
        }
      ],
      "expected_context_groups": {
        "implementations": [
          {
            "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java"
          }
        ]
      },
      "expected_pack_status": "ready",
      "minimum_context_confidence": "high"
    }
  ]
}
```

The exact-symbol case must have zero required missing groups; it proves camel-case surface tokens do not create flow/test requirements.

- [ ] **Step 7: Register the frontend and documentation cases**

Add the frontend repo entry without modifying its shared snapshot:

```json
{
  "repo_key": "context_pack_frontend",
  "snapshot_path": "tests/fixtures/real_projects/program_tool",
  "profiles": ["p2_context_pack"],
  "queries": [
    {
      "id": "qrcode-feature-context",
      "query": "QRCode page route service type",
      "profiles": ["p2_context_pack"],
      "mode": "context_pack",
      "tags": ["p2", "frontend", "vue", "context_pack"],
      "gate": "required",
      "expected_top_k": [
        {"path": "src/views/qrcode/QRCodeTool.vue", "top_k": 5},
        {"path": "src/router/index.ts", "top_k": 5},
        {"path": "src/types/qrcode-reader.d.ts", "top_k": 5},
        {"path": "src/utils/qrcodeUtils.ts", "top_k": 5}
      ],
      "expected_context_groups": {
        "entrypoints": [
          {"path": "src/views/qrcode/QRCodeTool.vue"},
          {"path": "src/router/index.ts"}
        ],
        "implementations": [
          {"path": "src/utils/qrcodeUtils.ts"}
        ],
        "related_types": [
          {"path": "src/types/qrcode-reader.d.ts"}
        ]
      },
      "expected_pack_status": "ready",
      "minimum_context_confidence": "medium"
    }
  ]
}
```

Add the required docs entry:

```json
{
  "repo_key": "context_pack_docs",
  "snapshot_path": "tests/fixtures/context-pack-docs",
  "profiles": ["p2_context_pack"],
  "queries": [
    {
      "id": "program-tool-developer-docs",
      "query": "Program Tool Developer Setup documentation",
      "profiles": ["p2_context_pack"],
      "mode": "context_pack",
      "tags": ["p2", "documentation", "context_pack"],
      "gate": "required",
      "expected_context_groups": {
        "configs_docs": [{"path": "README.md"}]
      },
      "expected_pack_status": "ready",
      "minimum_context_confidence": "medium"
    }
  ]
}
```

The README is an evidence anchor, so do not add `expected_top_k`; the context group expectation is the gate.

- [ ] **Step 8: Complete catalog manifests and verify file hashes**

Update `EXPECTED_NEW_CASES`, context defaults, explicit profile selection maps, and repo wiring to match the exact JSON above. Then run:

```bash
find \
  tests/fixtures/context-pack-java \
  tests/fixtures/context-pack-docs \
  -type f -print0 | sort -z | xargs -0 shasum -a 256
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_catalog.py \
  -q
```

Expected: hashes equal `P2_SNAPSHOT_SHA256`, the catalog has 49 cases, and the P2 selection is exactly five required cases.

- [ ] **Step 9: Run the deterministic P2 profile and existing `ci` profile**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_p2.py \
  -q
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output .quality/real-projects/p2-context-pack.json \
  --markdown .quality/real-projects/p2-context-pack.md
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/real-projects/ci-p2-regression.json \
  --markdown .quality/real-projects/ci-p2-regression.md
```

Expected:

- P2 selects/executes/passes 5/5 required cases;
- context completeness count is 5 and mean is 1.0;
- the docs case has a ready configs/docs pack and 93 returned content bytes;
- `ci` selects and passes its unchanged 8/8 required raw-result cases;
- neither profile needs a model service or network.

- [ ] **Step 10: Commit the deterministic profile**

```bash
git add \
  tests/fixtures/context-pack-java \
  tests/fixtures/context-pack-docs/README.md \
  tests/fixtures/retrieval_quality/queries.json \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py
git commit -m "test: add phase two context pack profile"
```

### Task 9: Document, verify, reconcile Phase 1 evidence, and close Phase 2 conditionally

**Files:**

- Modify: `README.md`
- Modify: `docs/retrieval-quality.md`
- Modify: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` only after all closure gates pass
- Modify: `docs/superpowers/specs/2026-07-14-p2-context-pack-output-design.md`
- Verify: all implementation, test, fixture, and plan files named above

- [ ] **Step 1: Verify the completed written-review metadata without changing the contract**

Confirm the design metadata already reads exactly:

```text
Status: Approved; written review complete
Implementation plan: docs/superpowers/plans/2026-07-14-p2-context-pack-output.md
```

If execution began from a copy where this metadata is absent, make only this
metadata update. Do not rewrite decisions, tables, error strings, or acceptance
criteria during this step. Any discovered contract change returns to design
review instead of being buried in documentation.

- [ ] **Step 2: Document the two product meanings and both public operations**

In `README.md`, add concise sections that state:

- `query` is raw ranked evidence and retains its contract;
- `context` is one raw retrieval plus deterministic agent-oriented packing;
- CLI examples for default Markdown and `--json`;
- `context_search_context(repo, query, context_lines, full_file, final_top_k)` beside the existing query tool;
- pack schema version, six groups, reading order, missing evidence, next queries, readiness confidence, and budget;
- `empty` is a successful result;
- `context_failed` is an internal pack contract/construction failure, while repo/index/query errors retain their existing codes;
- no extra retrieval/model call is performed;
- context feedback remains bounded and does not store source paths/content or composed next queries.

Use concrete examples:

```bash
cst context /path/to/repo "workspace page flow"
cst context /path/to/repo "workspace page flow" --json
cst context "WorkspaceServiceImpl" --context-lines 20
```

Keep all existing `cst query` examples and descriptions.

In `docs/retrieval-quality.md`, add:

- a profile-table row for offline hash-based `p2_context_pack`;
- legal `mode` values and context-only expectation schema;
- definitions for all eight context metrics;
- the three snapshot repo keys and five required cases;
- commands for P2 and `ci` reports;
- statement that no expected pairs yields null completeness and is excluded from aggregate means;
- statement that pack status/confidence are case metadata, not relevance probabilities;
- statement that the P2 profile cannot use environment/direct repo overrides.
- a dated `Phase 1 reconciliation (2026-07-14)` status block with the fields
  `Status`, `Checked implementation commit`, `Evidence`, and `Roadmap closure`;
  include `Reason` only for `unverified_dependency`, using a sanitized one-line
  dependency/gate diagnostic with no workspace path, source content, or secret.

- [ ] **Step 3: Run every focused deterministic suite**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_aggregate.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py \
  -q
```

Expected: all focused tests pass. Diagnose any failure before continuing; do not compensate by weakening a fixture gate or changing a closed enum/string.

- [ ] **Step 4: Run the complete suite and both deterministic quality profiles**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output .quality/real-projects/p2-context-pack-final.json \
  --markdown .quality/real-projects/p2-context-pack-final.md
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/real-projects/ci-p2-final.json \
  --markdown .quality/real-projects/ci-p2-final.md
jq '{profile, commit: .tool.git_commit, aggregate: .aggregate}' \
  .quality/real-projects/p2-context-pack-final.json \
  .quality/real-projects/ci-p2-final.json
```

Expected:

- the full suite passes;
- P2 is 5 selected, 5 attempted, 5 executed, 5 passed, 0 failed/error/skipped;
- P2 overall context completeness is count 5, mean 1.0;
- `ci` selects and passes its unchanged 8/8 raw-result case set;
- both reports identify the current implementation commit and contain no workspace paths beyond existing report provenance fields.

- [ ] **Step 5: Reconcile Phase 1 using fresh evidence, never the stale reports**

First prove the only retrieval edit since the Phase 2 design baseline is the public helper rename/use:

```bash
git diff 96b837aef83f15b1635e6a5236ac8ab48c90d516..HEAD \
  -- src/context_search_tool/retrieval.py
```

Expected: only `_evidence_anchor_top_k` becoming `evidence_anchor_top_k` and its call site change; formula and all ranking code are identical. Any wider retrieval diff is a design checkpoint and requires applicable Phase 1 reruns plus review.

Then inspect local model availability and generate fresh reports:

```bash
ollama list
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_vector_bge \
  --output .quality/real-projects/p1-vector-bge-reconciled.json \
  --markdown .quality/real-projects/p1-vector-bge-reconciled.md
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p1_hybrid_bge \
  --output .quality/real-projects/p1-hybrid-bge-reconciled.json \
  --markdown .quality/real-projects/p1-hybrid-bge-reconciled.md
PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -c '
import json
from pathlib import Path

from test_quality_p1 import _assert_phase_one_pair

vector = json.loads(
    Path(".quality/real-projects/p1-vector-bge-reconciled.json").read_text(
        encoding="utf-8"
    )
)
hybrid = json.loads(
    Path(".quality/real-projects/p1-hybrid-bge-reconciled.json").read_text(
        encoding="utf-8"
    )
)
_assert_phase_one_pair(vector, hybrid)
'
```

The final command deliberately reuses the focused pair-gate assertion against
the two JSON objects just written. Do not rerun both model-backed profiles inside
the integration test: a second execution would be expensive and would validate
different artifacts from the reports cited as reconciliation evidence. The full
suite in Step 4 already runs the pair gate's synthetic regression tests.

Passing reconciliation means:

- both profiles select/execute/pass 7/7 required cases;
- neither report has skipped, error, or failed cases;
- the focused pair gate passes its planner/provenance and non-decline assertions
  against those exact persisted report objects;
- report commit IDs match the current output-only implementation state;
- documentation identifies `b8527e75e602023aa7e31d360ada4595ffb444f2` as the last Phase 1 closure commit and the new reports as fresh reconciliation evidence, not as evidence produced by that older commit.

Record the outcome in the committed `docs/retrieval-quality.md` status block,
not only in terminal output:

- On success, set `Status: verified`, record the actual implementation commit,
  name both reconciled report files with their 7/7 results and the persisted
  pair-gate result, and set `Roadmap closure: eligible after all Phase 2 gates`.
- If a local model/service is missing or either profile/pair gate fails, set
  `Status: unverified_dependency`, record the actual checked commit, state that
  no fresh Phase 1 pair was accepted, name the failing command plus a sanitized
  one-line reason, explicitly reject the reports from
  `911add4d20bfcbb3190bc9045478686a87226587` as stale evidence, and set
  `Roadmap closure: pending`.

In the second branch, do not mark Phase 2 complete in the roadmap. The
implementation and deterministic P2 evidence may still be delivered, but
closure remains pending.

- [ ] **Step 6: Update the roadmap only when Steps 3–5 all pass**

When every deterministic gate and fresh Phase 1 reconciliation pass:

- change the header to `Next-stage review: Phase 3 Retrieval Trace and Core Decomposition design review`;
- mark Phase 1 complete with its closure commit and fresh reconciliation report names;
- replace the obsolete Phase 1 static-lexicon wording with the implemented bounded multi-query/provenance behavior;
- add `Status: Complete (2026-07-14)` under Phase 2;
- link the approved design and this implementation plan;
- state that `cst context`/`context_search_context` are dedicated operations and raw query contracts remain unchanged;
- record the 5/5 offline P2 profile result, full suite, and `ci` regression result;
- retain Phase 3/4 scope verbatim.

If Step 5 is an `unverified_dependency`, do not add either completion status.
README may describe the implemented feature, and `docs/retrieval-quality.md`
must commit the dated unverified status block from Step 5, but the roadmap must
continue to show acceptance pending.

- [ ] **Step 7: Run final contract, privacy, artifact, and diff checks**

```bash
jq -e '
  .aggregate.total == 5 and
  .aggregate.selected == 5 and
  .aggregate.attempted == 5 and
  .aggregate.executed == 5 and
  .aggregate.passed == 5 and
  .aggregate.failed == 0 and
  .aggregate.errors == 0 and
  .aggregate.skipped == 0 and
  .aggregate.known_gaps == 0 and
  .aggregate.informational == 0 and
  .aggregate.metrics.overall.context_completeness == {
    "count": 5,
    "mean": 1
  }
' .quality/real-projects/p2-context-pack-final.json
jq -e '
  .aggregate.total == 8 and
  .aggregate.selected == 8 and
  .aggregate.attempted == 8 and
  .aggregate.executed == 8 and
  .aggregate.passed == 8 and
  .aggregate.failed == 0 and
  .aggregate.errors == 0 and
  .aggregate.skipped == 0 and
  .aggregate.known_gaps == 0 and
  .aggregate.informational == 0
' .quality/real-projects/ci-p2-final.json
rg -n \
  "cst context|context_search_context|p2_context_pack|context_completeness|ContextPack" \
  README.md \
  docs/retrieval-quality.md \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md \
  tests/fixtures/retrieval_quality/queries.json
rg -n \
  "RetrievalTrace|multi-round|marginal.gain|graph traversal" \
  src tests || true
git diff --check
git status --short
```

Expected:

- the report assertions pass;
- all new operation/profile/metric names appear in intended docs/fixture;
- no Phase 3/4 implementation appears in source/tests;
- `git diff --check` prints nothing;
- only files named in this plan are modified or created;
- `.quality/` artifacts remain untracked/ignored and are not staged.

- [ ] **Step 8: Commit documentation and conditional roadmap closure**

If fresh Phase 1 reconciliation passed and the roadmap was updated:

```bash
git add \
  README.md \
  docs/retrieval-quality.md \
  docs/superpowers/specs/2026-07-14-p2-context-pack-output-design.md \
  docs/superpowers/plans/2026-07-14-p2-context-pack-output.md \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
git commit -m "docs: close phase two context pack output"
```

If reconciliation is an `unverified_dependency`, omit the roadmap:

```bash
git add \
  README.md \
  docs/retrieval-quality.md \
  docs/superpowers/specs/2026-07-14-p2-context-pack-output-design.md \
  docs/superpowers/plans/2026-07-14-p2-context-pack-output.md
git commit -m "docs: document context pack output"
```

## Final Verification Matrix

| Requirement | Focused proof | Acceptance proof |
| --- | --- | --- |
| One result/anchor → one item/group/order entry | `tests/test_context_pack.py` reference invariants | P2 profile cases encode successfully |
| Closed role/group/basis table | parameterized builder classifications | Java/frontend/docs group gates |
| No generated-token intent leakage | camel-case/planner-token unit tests | exact-symbol P2 case has zero required gaps |
| Conservative required/recommended gaps | intent/gap matrix | frontend recommended-test gap remains non-fatal |
| Bounded deterministic next queries | category/seed/cap/dedupe tests | count appears in report/feedback |
| Structural confidence | full level/reason matrix | high Java/exact cases and medium frontend/docs cases |
| Honest effective budgets | helper/options/UTF-8/over-limit tests | docs case reports 93 returned content bytes |
| Empty success | synthetic empty builder plus CLI/MCP tests | no model-backed fixture needed |
| Raw query compatibility | formatter/CLI/MCP exact comparisons | `ci` profile and full suite |
| One retrieval and one build | CLI/MCP counters | P2 runner builds only context cases |
| Pack error containment | known/unexpected CLI/MCP phase tests | no fabricated partial pack |
| Feedback privacy | sentinel and malformed-payload tests | context JSONL contains only bounded metadata |
| Quality schema/metrics | case/metric/runner/aggregate tests | 5/5 profile; completeness mean 1.0 |
| Phase 1 evidence reconciliation | helper-only retrieval diff | fresh 7/7 pair gate or explicit unverified dependency |
| Documentation/roadmap honesty | grep and conditional edit rules | roadmap closes only after every gate |

## Stop Point

This plan ends after ContextPack v1 implementation, deterministic P2 and raw-query regression verification, documentation, and conditional Phase 2 closure. Do not begin RetrievalTrace, retrieval-core decomposition, controlled multi-round exploration, graph traversal, or a new token budget in the same execution.
