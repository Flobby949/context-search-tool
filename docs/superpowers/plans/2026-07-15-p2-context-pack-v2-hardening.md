# P2.1 ContextPack v2 Agent-First Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unused reference-oriented ContextPack v1 response with a deterministic, self-contained ContextPack v2 reading set whose excerpts, evidence claims, omissions, and canonical JSON all fit explicit hard budgets.

**Architecture:** Keep `query_repository()` as the only retrieval pass and preserve its public payload byte-for-byte. Record internal retrieval-span provenance while constructing results, classify artifacts through the shared role classifier, and feed the completed `QueryBundle` to a pure `context_pack` package split into models, roles, needs, excerpts, serialization, and orchestration. CLI, MCP, formatters, feedback, and quality profiles consume the same JSON-native pack object; explicit repository preparation is a separate opt-in quality command.

**Tech Stack:** Python 3.11+, frozen dataclasses, Typer, FastMCP, pytest, deterministic hash embeddings, canonical JSON, subprocess argument arrays for Git, and the existing retrieval-quality catalog.

---

## Planning Constraints And Assumptions

1. The approved source of truth is `docs/superpowers/specs/2026-07-15-p2-context-pack-v2-hardening-design.md`. The user's “开始执行” completes written review and authorizes this implementation plan; it does not reopen the approved schema or expand scope.
2. Work only in `/Users/flobby/vibe_coding/context-search-tool/.worktrees/p2-context-pack-v2-hardening` on branch `codex/p2-context-pack-v2-hardening`. The baseline is `1610 passed, 4 skipped`.
3. This is an intentional breaking change only for `cst context` and `context_search_context`. Raw `query` CLI/MCP schemas, JSON/Markdown serialization, scoring diagnostics, planner fields, and single-pass mechanics remain unchanged.
4. Context construction is pure after retrieval. It may inspect only `QueryBundle` fields and configured/request limits; it performs no filesystem, SQLite, vector, embedding, planner, network, model, or repository call.
5. The canonical pack limit applies to compact sorted JSON with `ensure_ascii=False`, `allow_nan=False`, and separators `(",", ":")`. `budget.pack_bytes` must include its own final digit width and converge exactly.
6. Persisted context limits use the approved defaults. Request `max_context_bytes` overrides only the pack ceiling, never enlarges subordinate configured limits, and has a public minimum of 4,096 bytes.
7. Shared role changes are retrieval changes. Add only the approved Spring/JVM cases and run the unchanged raw `ci`, smoke, applicable Phase 1, and focused ranking gates before making roadmap claims.
8. A selected item establishes a need match only when the retained excerpt still contains the relevant evidence. Candidate-level matching is provisional.
9. The opt-in `p2_real_context` profile never clones implicitly. `quality prepare` is the only network-mutating operation; `quality run` validates and consumes an exact prepared checkout.
10. Fast-context and model-backed profiles are dependency evidence, not deterministic CI gates. Unavailability is recorded explicitly and never reported as a pass.
11. Each task follows red-green-refactor: add one focused behavior, run it to observe the expected failure, implement the minimum, run focused plus named regressions, self-review, and commit.
12. Stop after ContextPack v2 and its quality loop. Do not implement automatic follow-up execution, multi-round retrieval, graph traversal, type resolution, or RetrievalTrace.

## File Map

### Replace

| Existing file | Replacement |
| --- | --- |
| `src/context_search_tool/context_pack.py` | Move the v1 body verbatim to `src/context_search_tool/context_pack/__init__.py` as a temporary compatibility shell, add `models.py`, `roles.py`, `needs.py`, `excerpts.py`, `builder.py`, and `serialization.py`, then replace the shell with small v2 exports in Task 7 |

### Create

| File | Responsibility |
| --- | --- |
| `src/context_search_tool/context_pack/__init__.py` | Small compatibility export surface for callers that currently import `context_search_tool.context_pack`. |
| `src/context_search_tool/context_pack/models.py` | Frozen public v2 records, internal candidate/window records, closed constants, effective options, and fixed errors. |
| `src/context_search_tool/context_pack/roles.py` | Map the shared `PathRole`/frontend roles to the six context groups and normalize result/anchor candidates. |
| `src/context_search_tool/context_pack/needs.py` | Evidence-need derivation, scoped matching, missing evidence, confidence, omissions, and grounded next queries. |
| `src/context_search_tool/context_pack/excerpts.py` | Retrieval-span normalization, window selection/merge, UTF-8-safe line cropping, and content allocation. |
| `src/context_search_tool/context_pack/builder.py` | Pure ten-stage orchestration, stable selection, re-matching after excerpts, compaction, and invariants. |
| `src/context_search_tool/context_pack/serialization.py` | Exact JSON-native materialization, canonical JSON bytes, self-sized `pack_bytes`, and closed-key validation. |
| `src/context_search_tool/quality/prepare.py` | Pinned remote declaration validation, safe Git clone/fetch/checkout, provenance manifest, and prepared-checkout validation. |
| `tests/test_context_needs.py` | Focused evidence-need, matching, missing-evidence, confidence, and next-query tests. |
| `tests/test_context_excerpts.py` | Focused span, Unicode cropping, allocation, canonical-size, and determinism tests. |
| `tests/test_quality_prepare.py` | Safe/idempotent preparation and wrong-source/commit/dirty/collision tests. |

### Modify

| File | Responsibility |
| --- | --- |
| `src/context_search_tool/config.py` | Add persisted `ContextConfig` defaults, rendering/loading, and strict context-limit validation. |
| `src/context_search_tool/models.py` | Add frozen internal `RetrievalSpan` and a defaulted `RetrievalResult.spans` tuple. |
| `src/context_search_tool/path_roles.py` | Add closed classification basis and conservative Spring/JVM config, template, repository, and Java type rules. |
| `src/context_search_tool/retrieval.py` | Preserve contributing spans through expansion/merge into `RetrievalResult` without changing raw payloads. |
| `src/context_search_tool/formatters.py` | Make context JSON use the bounded envelope only and render each excerpt once in reading order. |
| `src/context_search_tool/cli.py` | Add `--max-items`/`--max-context-bytes`, validate before retrieval, and return fixed context errors. |
| `src/context_search_tool/mcp_tools.py` | Add matching request overrides, bounded envelope, and privacy-safe v2 feedback. |
| `src/context_search_tool/mcp_server.py` | Expose the two nullable v2 context arguments without changing raw query signature. |
| `src/context_search_tool/quality/cases.py` | Add v2 expectations and mutually exclusive pinned-source declarations. |
| `src/context_search_tool/quality/metrics.py` | Add need/budget metrics while retaining historical group/path completeness. |
| `src/context_search_tool/quality/runner.py` | Validate prepared sources and evaluate v2 packs without implicit network access. |
| `src/context_search_tool/quality/__main__.py` | Register `quality prepare`. |
| `tests/test_config_paths.py` | Lock default/render/load/request validation for `[context]`. |
| `tests/test_path_roles.py` and focused ranking/profile tests | Lock role precedence and non-regression. |
| `tests/test_retrieval_pipeline.py` | Lock span creation/normalization, no extra I/O, and raw-result compatibility. |
| `tests/test_context_pack.py` | Replace v1 reference tests with exact v2 schema, builder, selection, errors, and purity tests. |
| `tests/test_formatters.py`, `tests/test_cli_commands.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` | Lock bounded public contracts, identity, one-pass calls, errors, and privacy. |
| `tests/test_quality_cases.py`, `tests/test_quality_metrics.py`, `tests/test_quality_runner.py`, `tests/test_quality_catalog.py`, `tests/test_quality_p2.py` | Migrate offline P2 and add pinned real-profile coverage. |
| `tests/fixtures/retrieval_quality/queries.json` | Migrate `p2_context_pack` cases and add pinned `spring_petclinic`/`p2_real_context` declarations and four cases. |
| `README.md`, `docs/retrieval-quality.md`, design/plan metadata, and roadmap | Document v2, preparation, evidence, dependency results, and conditional roadmap status. |

## Exact Public Contracts To Lock

`src/context_search_tool/config.py` gains:

```python
@dataclass(frozen=True)
class ContextConfig:
    max_items: int = 12
    max_excerpts_per_item: int = 2
    max_excerpt_bytes: int = 4096
    max_item_content_bytes: int = 8192
    max_total_content_bytes: int = 49152
    max_pack_bytes: int = 65536

@dataclass(frozen=True)
class ToolConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    query_planner: QueryPlannerConfig = field(default_factory=QueryPlannerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
```

`src/context_search_tool/models.py` gains:

```python
@dataclass(frozen=True)
class RetrievalSpan:
    start_line: int
    end_line: int
    score: float
    sources: tuple[str, ...]

@dataclass(frozen=True)
class RetrievalResult:
    # existing fields stay in their current order
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    spans: tuple[RetrievalSpan, ...] = ()
```

The raw formatter deliberately continues to serialize only the pre-existing
`RetrievalResult` fields.

After the Task 7 cutover, the v2 package exports:

```python
CONTEXT_PACK_SCHEMA_VERSION = 2
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

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

@dataclass(frozen=True)
class ContextPackOptions:
    max_items: int
    max_excerpts_per_item: int
    max_excerpt_bytes: int
    max_item_content_bytes: int
    max_total_content_bytes: int
    max_pack_bytes: int
    context_before_lines: int
    context_after_lines: int

def resolve_context_pack_options(
    config: ToolConfig,
    *,
    context_lines: int | None,
    max_evidence_anchors: int,
    max_items: int | None = None,
    max_pack_bytes: int | None = None,
) -> ContextPackOptions:
    """Validate and resolve configured/request ContextPack ceilings."""

def build_context_pack(
    bundle: QueryBundle,
    options: ContextPackOptions,
) -> ContextPack:
    """Build one deterministic, I/O-free ContextPack v2."""

def context_pack_payload(pack: ContextPack) -> dict[str, Any]:
    """Return the validated JSON-native schema-v2 object."""

def canonical_context_pack_bytes(
    pack_or_payload: ContextPack | dict[str, Any],
) -> bytes:
    """Return exact compact sorted UTF-8 JSON bytes."""
```

The `ContextPack` object has exactly these public records:

```python
@dataclass(frozen=True)
class ContextExcerpt:
    start_line: int
    end_line: int
    content: str
    content_bytes: int
    truncated: bool

@dataclass(frozen=True)
class ContextItem:
    id: str
    file_path: str
    group: str
    role: str
    classification_basis: str
    source_kind: str
    retrieval_rank: int | None
    relevance_score: float | None
    reasons: tuple[str, ...]
    matched_need_ids: tuple[str, ...]
    excerpts: tuple[ContextExcerpt, ...]

@dataclass(frozen=True)
class EvidenceNeed:
    id: str
    category: str
    subject_terms: tuple[str, ...]
    required: bool
    provenance: str
    matched_item_ids: tuple[str, ...]

@dataclass(frozen=True)
class MissingEvidence:
    need_id: str
    category: str
    required: bool
    reason: str

@dataclass(frozen=True)
class NextQuery:
    need_id: str
    query: str
    purpose: str

@dataclass(frozen=True)
class Omission:
    file_path: str
    group: str
    reason: str
    matched_need_ids: tuple[str, ...]

@dataclass(frozen=True)
class ReadinessConfidence:
    level: str
    reasons: tuple[str, ...]

@dataclass(frozen=True)
class ContextBudget:
    max_items: int
    max_excerpts_per_item: int
    max_excerpt_bytes: int
    max_item_content_bytes: int
    max_total_content_bytes: int
    max_pack_bytes: int
    included_items: int
    included_excerpts: int
    content_bytes: int
    pack_bytes: int
    truncated_item_count: int
    omitted_item_count: int
    budget_exhausted: bool

@dataclass(frozen=True)
class ContextPack:
    schema_version: int
    status: str
    items: tuple[ContextItem, ...]
    groups: dict[str, tuple[str, ...]]
    reading_order: tuple[str, ...]
    evidence_needs: tuple[EvidenceNeed, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    next_queries: tuple[NextQuery, ...]
    omissions: tuple[Omission, ...]
    confidence: ReadinessConfidence
    budget: ContextBudget
```

The internal records shared by `roles.py`, `needs.py`, `excerpts.py`, and
`builder.py` are:

```python
@dataclass(frozen=True)
class ContextCandidate:
    key: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    group: str
    role: str
    classification_basis: str
    source_kind: str
    retrieval_rank: int | None
    source_order: int
    relevance_score: float | None
    reasons: tuple[str, ...]
    score_parts: dict[str, float]
    spans: tuple[RetrievalSpan, ...]
    trusted_provenance_text: str
    protected_direct: bool

@dataclass(frozen=True)
class ExcerptWindow:
    start_line: int
    end_line: int
    required_need_ids: tuple[str, ...]
    recommended_need_ids: tuple[str, ...]
    score: float
    protected_direct: bool
```

`ContextCandidate.key` is the canonical case-sensitive repository-relative path.
`source_order` is the result rank or anchor encounter order used only after the
need/group priority keys. `trusted_provenance_text` is internal normalized text
derived from the already returned path and bounded public reasons, not from the
full content; candidate or retained-excerpt content is passed separately during
matching. It is never serialized. No task adds a second candidate type with
overlapping responsibility.

The materialized pack has exactly the eleven corresponding top-level keys. Item,
excerpt, need, missing-evidence, next-query, omission, confidence, and budget
objects have exactly the fields above in the approved design.

Public errors use these codes:

```text
invalid_context_options
context_failed
```

`invalid_context_options` is raised before retrieval for invalid persisted or
request limits. `context_failed` sanitizes classification, span, compaction,
canonical-size, reference, and unexpected serialization failures.

## Task Dependency Order

1. Context options and exact schema-v2 model/serialization contract.
2. Shared artifact-role hardening.
3. Retrieval-span provenance with raw-query compatibility.
4. Evidence-need derivation and scoped matching.
5. Deterministic excerpt selection and exact hard budgets.
6. Status, confidence, omissions, grounded next queries, and final builder invariants.
7. CLI, MCP, formatting, fixed errors, and feedback privacy.
8. Quality schema/metrics and offline profile migration.
9. Pinned repository preparation and `p2_real_context`.
10. Documentation, external evidence reconciliation, and final verification.

### Task 1: Add validated context options and the schema-v2 model contract

**Files:**

- Modify: `src/context_search_tool/config.py`
- Move verbatim: `src/context_search_tool/context_pack.py` → `src/context_search_tool/context_pack/__init__.py`
- Create: `src/context_search_tool/context_pack/models.py`
- Create: `src/context_search_tool/context_pack/serialization.py`
- Create: `src/context_search_tool/context_pack/builder.py`
- Create empty focused modules with documented exports: `roles.py`, `needs.py`, `excerpts.py`
- Modify: `tests/test_config_paths.py`
- Add v2-submodule contract tests to `tests/test_context_pack.py` while retaining the passing v1 top-level compatibility tests until Task 7

- [ ] **Step 1: Write failing config tests**

Add tests that assert the exact default `[context]` block, round-trip every value,
and reject non-integers, booleans, zero/negative values, inverted subordinate
limits, equal total/pack limits, and request pack limits below 4,096.

```python
def test_default_config_renders_context_limits() -> None:
    rendered = render_default_config()
    assert """
[context]
max_items = 12
max_excerpts_per_item = 2
max_excerpt_bytes = 4096
max_item_content_bytes = 8192
max_total_content_bytes = 49152
max_pack_bytes = 65536
""".strip() in rendered

def test_context_request_pack_ceiling_only_reduces_subordinate_limits() -> None:
    resolved = resolve_context_pack_options(
        ToolConfig(),
        context_lines=None,
        max_evidence_anchors=4,
        max_items=20,
        max_pack_bytes=4096,
    )
    assert resolved == ContextPackOptions(
        max_items=12,
        max_excerpts_per_item=2,
        max_excerpt_bytes=4095,
        max_item_content_bytes=4095,
        max_total_content_bytes=4095,
        max_pack_bytes=4096,
        context_before_lines=8,
        context_after_lines=12,
    )
```

For invalid cases, assert `ContextPackError` carries the fixed public code/message
data used by Task 7 rather than leaking a Python/dataclass error.

- [ ] **Step 2: Run the config/contract tests and observe RED**

Run:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_config_paths.py \
  tests/test_context_pack.py \
  -q
```

Expected: failures because `ContextConfig`, the package modules, schema version 2,
and the new option fields do not exist.

- [ ] **Step 3: Implement strict configuration and effective option resolution**

Add `ContextConfig` to `ToolConfig`, render/load it after `[retrieval]`, and add
one validator that uses `type(value) is int` so booleans are rejected. Validate:

```python
def validate_context_config(context: ContextConfig) -> None:
    values = dataclasses.asdict(context)
    for name, value in values.items():
        if type(value) is not int or value <= 0:
            raise ContextPackError(
                "invalid_context_options",
                f"context.{name} must be a positive integer",
            )
    if context.max_excerpt_bytes > context.max_item_content_bytes:
        raise ContextPackError(
            "invalid_context_options",
            "context.max_excerpt_bytes must not exceed max_item_content_bytes",
        )
    if context.max_item_content_bytes > context.max_total_content_bytes:
        raise ContextPackError(
            "invalid_context_options",
            "context.max_item_content_bytes must not exceed max_total_content_bytes",
        )
    if context.max_total_content_bytes >= context.max_pack_bytes:
        raise ContextPackError(
            "invalid_context_options",
            "context.max_total_content_bytes must be less than max_pack_bytes",
        )
```

`resolve_context_pack_options()` validates request integers with the same strict
type rule, caps `max_items` by configured/request/raw-result-plus-anchor limits,
and computes:

```python
effective_total = min(
    configured.max_total_content_bytes,
    effective_pack_bytes - 1,
)
effective_item = min(configured.max_item_content_bytes, effective_total)
effective_excerpt = min(configured.max_excerpt_bytes, effective_item)
```

- [ ] **Step 4: Implement exact records and JSON-native serialization**

Move the existing v1 module body verbatim into package `__init__.py` first so all
pre-existing public imports and tests remain green during Tasks 1–6. New v2 tests
import `context_search_tool.context_pack.models` and `serialization` directly.

Create the frozen records in the “Exact Public Contracts” section. Implement
payload functions with explicit dict/list construction; do not use `asdict()` or
a custom JSON encoder. Validate finite scores and closed keys/enum values before
calling:

```python
def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
```

Do not switch top-level exports or fabricate a partial v2 builder in this task.
`builder.py` contains only fully tested option/model helpers needed here; the
first end-to-end v2 build is completed in Tasks 4–6 and activated in Task 7.

- [ ] **Step 5: Add exact-key and self-sized `pack_bytes` tests**

Construct a small pack directly and assert:

```python
payload = context_pack_payload(pack)
assert tuple(payload) == (
    "schema_version", "status", "items", "groups", "reading_order",
    "evidence_needs", "missing_evidence", "next_queries", "omissions",
    "confidence", "budget",
)
assert payload["schema_version"] == 2
encoded = canonical_context_pack_bytes(payload)
assert payload["budget"]["pack_bytes"] == len(encoded)
assert json.loads(encoded) == payload
```

The implementation must iterate the `pack_bytes` field until digit width is
stable; cap iterations with a fixed internal constant and fail sanitized if it
does not converge.

- [ ] **Step 6: Run focused tests and regressions**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_config_paths.py \
  tests/test_context_pack.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_quality_cases.py \
  tests/test_quality_runner.py \
  -q
```

Expected: new v2 submodule tests and every retained v1 compatibility/raw-query
test pass. No public cutover occurs yet, and raw query assertions remain
byte-for-byte unchanged.

- [ ] **Step 7: Commit**

```bash
git add \
  src/context_search_tool/config.py \
  src/context_search_tool/context_pack \
  src/context_search_tool/context_pack.py \
  tests/test_config_paths.py \
  tests/test_context_pack.py
git commit -m "feat: define context pack v2 contract"
```

### Task 2: Harden the shared artifact-role classifier

**Files:**

- Modify: `src/context_search_tool/path_roles.py`
- Create: `src/context_search_tool/context_pack/roles.py`
- Modify: `tests/test_path_roles.py`
- Modify focused role/ranking tests in `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write failing precedence and basis tests**

Add one table-driven test covering every approved positive and negative case:

```python
@pytest.mark.parametrize(
    ("path", "content", "name", "basis"),
    [
        ("src/main/resources/application.properties", "", "runtime_config", "path"),
        ("src/main/resources/application-postgresql.yml", "", "runtime_config", "path"),
        ("src/main/resources/bootstrap-local.yaml", "", "runtime_config", "path"),
        ("config/messages_de.properties", "", "runtime_config", "path"),
        ("src/main/resources/messages_de.properties", "", "source", "fallback"),
        ("src/main/resources/logback-spring.xml", "", "runtime_config", "path"),
        ("src/main/resources/templates/owners/details.html", "", "view", "path"),
        ("src/main/resources/static/index.html", "", "source", "fallback"),
        ("src/main/java/example/OwnerRepository.java", "", "repository", "path"),
        ("src/main/java/example/Owner.java", "@Entity\nclass Owner {}", "data_type", "content"),
        ("src/main/java/example/Visit.java", "record Visit(int id) {}", "data_type", "content"),
        ("src/main/java/example/Kind.java", "enum Kind { CAT }", "data_type", "content"),
        ("src/main/java/example/OwnerDto.java", "", "data_type", "path"),
    ],
)
def test_classify_path_role_hardens_spring_roles(
    path: str, content: str, name: str, basis: str
) -> None:
    role = classify_path_role(Path(path), content)
    assert (role.name, role.basis) == (name, basis)
```

Add negatives proving annotation imports, comments, and string literals do not
trigger data types, and precedence proving tests/controllers/services/repositories
remain above generic annotation/record/enum/suffix detection.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_path_roles.py \
  tests/test_retrieval_pipeline.py -k "role or artifact or config" \
  -q
```

Expected: new cases fail because `PathRole` lacks `basis` and the Spring/JVM
rules are absent.

- [ ] **Step 3: Implement conservative shared rules**

Change the record to:

```python
@dataclass(frozen=True)
class PathRole:
    name: str
    priority: int
    basis: str
```

Use small helpers:

```python
def _path_role(name: str, priority: int) -> PathRole:
    return PathRole(name, priority, "path")

def _content_role(name: str, priority: int) -> PathRole:
    return PathRole(name, priority, "content")

_FALLBACK_SOURCE = PathRole("source", 60, "fallback")
```

Match Spring config basenames with anchored regexes; `application`/`bootstrap`
may have an optional profile suffix and only `.properties`/`.yaml`/`.yml`.
Recognize the approved XML basenames, `.properties` only under `config/configs`,
HTML below a `templates` segment, and Java declaration/annotation lines with
multiline anchored regexes. Keep existing priority order: tests and generated
artifacts first; config; controller/service/repository; then generic data types;
then fallback.

- [ ] **Step 4: Implement the context group adapter once**

`roles.py` owns the closed maps from shared path/frontend role to the six groups.
It must return the shared `PathRole.basis` unchanged and must not reproduce any
Spring/JVM classification rule. A result and anchor with the same normalized
case-sensitive repository path become one result-backed candidate with bounded,
ordered-unique reasons and no duplicated content.

- [ ] **Step 5: Run role and raw ranking regressions**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_path_roles.py \
  tests/test_frontend_roles.py \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py \
  -q
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/real-projects/p2-1-role-ci.json
```

Expected: focused tests pass and unchanged `ci` required cases remain passing.
Inspect the report rather than accepting exit status alone.

- [ ] **Step 6: Commit**

```bash
git add \
  src/context_search_tool/path_roles.py \
  src/context_search_tool/context_pack/roles.py \
  tests/test_path_roles.py \
  tests/test_retrieval_pipeline.py
git commit -m "feat: harden shared spring artifact roles"
```

### Task 3: Preserve internal retrieval-span provenance

**Files:**

- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_formatters.py`

- [ ] **Step 1: Capture the raw query compatibility fixture**

Before editing production code, serialize the existing deterministic bundle with
`query_payload()`/`format_json()` in a focused test and assert exact keys and
bytes. The expected object must not mention `spans`.

- [ ] **Step 2: Write failing span tests**

Cover one chunk, two overlapping chunks, two disjoint chunks from one file,
duplicate spans, full-file/capped results, and a legacy synthetic
`RetrievalResult(spans=())`. Assert:

```python
assert result.spans == (
    RetrievalSpan(
        start_line=ranked_chunk.start_line,
        end_line=ranked_chunk.end_line,
        score=ranked_score,
        sources=("lexical",),
    ),
)
```

For merged results, spans are valid, ordered by
`(start_line, end_line, -score, sources)`, exact duplicates collapse, overlapping
distinct contributors remain available for later window merging, and all spans
stay within the returned result's line range.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py -k "span or overlapping_results or expanded_result" \
  tests/test_formatters.py -k "raw or query" \
  -q
```

Expected: missing `RetrievalSpan`/`spans` failures while the pre-existing raw
compatibility assertion passes.

- [ ] **Step 4: Implement span creation and merge**

Add `RetrievalSpan` and the defaulted final `RetrievalResult.spans` field. Add
`spans: tuple[RetrievalSpan, ...]` to `_ExpandedResult`. Each ranked chunk creates
one span from its original chunk window (clamped to returned content) with a
finite rerank score. Derive `sources` from a fixed ordered list of actual positive
retrieval source score-part keys:

```python
_SPAN_SOURCE_KEYS = (
    "path_symbol", "lexical", "semantic", "planner_semantic",
    "signal", "planner_hint", "anchor_expansion", "relation",
)
```

Use `("ranked",)` only when none is present. Normalize without I/O, preserve spans
through `_cap_expanded_result()` and `_merge_expanded_result()`, and copy the final
tuple onto visible `RetrievalResult` values. Do not add spans to evidence-anchor
or raw formatter payloads.

- [ ] **Step 5: Prove no extra retrieval or I/O**

Use monkeypatch counters around store lookups and file reads for a known query.
Assert adding spans does not change counts relative to the existing expansion
path and does not issue an extra query/build/read after `QueryBundle` is returned.

- [ ] **Step 6: Run focused and full raw contract tests**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py -k query \
  tests/test_mcp_tools.py -k query \
  -q
```

Expected: all pass and the captured raw JSON bytes are unchanged.

- [ ] **Step 7: Commit**

```bash
git add \
  src/context_search_tool/models.py \
  src/context_search_tool/retrieval.py \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py
git commit -m "feat: retain retrieval span provenance"
```

### Task 4: Derive concrete evidence needs and scoped candidate matches

**Files:**

- Modify: `src/context_search_tool/context_pack/models.py`
- Modify: `src/context_search_tool/context_pack/roles.py`
- Implement: `src/context_search_tool/context_pack/needs.py`
- Modify: `src/context_search_tool/context_pack/builder.py`
- Create: `tests/test_context_needs.py`
- Modify: `tests/test_context_pack.py`

- [ ] **Step 1: Write failing need-derivation tests**

Use synthetic bundles/candidates to lock these exact cases:

| Query | Required needs |
| --- | --- |
| `owner registration form validation flow` | entrypoint subject `owner` |
| `OwnerController tests for owner registration validation` | entrypoint subject `OwnerController` and test subject `OwnerController` |
| `宠物主人详情页如何加载宠物和就诊记录` | entrypoint subject `宠物主人详情页` |
| `MySQL PostgreSQL database profile configuration and integration tests` | config subjects `MySQL` and `PostgreSQL` plus test subjects `MySQL` and `PostgreSQL` |
| `Owner model type` | related-type subject `Owner` only |
| `find service implementation` | one unscoped implementation need; no invented owner/controller/type need |

The four database needs must have distinct IDs. Need order is original subject
order within explicit category order, followed by structural recommendations in
`CONTEXT_GROUPS` order.

```python
def test_multiple_database_subjects_create_distinct_scoped_needs() -> None:
    needs = derive_evidence_needs(
        bundle(query="MySQL PostgreSQL database profile configuration and integration tests"),
        candidates=(),
    )
    assert [(n.category, n.subject_terms, n.required) for n in needs] == [
        ("configs_docs", ("MySQL",), True),
        ("configs_docs", ("PostgreSQL",), True),
        ("tests", ("MySQL",), True),
        ("tests", ("PostgreSQL",), True),
    ]
    assert len({need.id for need in needs}) == 4
```

Add subject normalization tests for whitespace, punctuation, case-insensitive ID
collisions, CJK, emoji, combining characters, and a 65-code-point subject. Public
subjects are trimmed to 64 Unicode code points without cutting a code point; ID
collisions receive `:2`, `:3` suffixes in encounter order.

- [ ] **Step 2: Write failing provenance and exclusion tests**

Prove:

- exact identifier roles create a required need only for their own category;
- a successful planner term grounded in a returned path/symbol/route/content
  becomes recommended with `planner_supported`;
- an ungrounded planner term produces no need;
- `discarded_hints`, generated expanded tokens, `followup_keywords`, and
  `RetrievalSummary` values never create needs or subjects;
- structural adjacent groups are recommended, never required;
- an import/comment/string containing `@Entity` does not affect need category.

Use a bundle whose misleading summary contains `GET /oups` and assert no need
contains `oups`.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_needs.py \
  tests/test_context_pack.py -k need \
  -q
```

Expected: failures because `derive_evidence_needs()` and candidate-scoped matching
do not exist.

- [ ] **Step 4: Implement deterministic subject and category extraction**

Keep closed role phrases in data tables inside `needs.py`:

```python
_EXPLICIT_ROLE_TERMS = {
    "entrypoints": (
        "controller", "route", "router", "endpoint", "entrypoint",
        "form", "page", "view", "详情页", "页面",
    ),
    "implementations": (
        "implementation", "service", "handler", "repository",
        "storage", "实现", "服务",
    ),
    "related_types": (
        "dto", "model", "entity", "type", "record", "enum", "模型", "类型",
    ),
    "tests": ("test", "tests", "integration test", "测试", "集成测试"),
    "configs_docs": (
        "config", "configuration", "properties", "profile",
        "documentation", "配置", "文档",
    ),
}
```

Use `infer_query_intent()` and `infer_identifier_intent()` only on the original
query. Explicit CamelCase identifiers keep their public spelling. High-signal
subjects come from original-query spans adjacent to explicit role phrases after
removing a closed stop/role-word set; conjunctions split independent subjects.
The database aliases `mysql` and `postgresql` are independent subjects, never one
compound phrase. For the approved Chinese page grammar, preserve the noun phrase
ending in `详情页`/`页面`. When a category is explicit but no safe subject remains,
create one unscoped need with an empty `subject_terms` tuple.

Need IDs use:

```python
base = f"need:{category}:{slug_or_general}"
candidate = base if base not in used else f"{base}:{collision_index}"
```

The slug is Unicode-aware, casefolded, whitespace/punctuation collapsed to `-`,
and never exposes more than the already bounded public subject.

- [ ] **Step 5: Implement candidate normalization and matching**

`roles.normalize_candidates(bundle)` emits at most one candidate per normalized
repository-relative path. If a result and anchor collide, keep the result as the
source, union at most four existing public reasons in stable order, and retain
anchor subject provenance only as searchable trusted text—not as duplicated
content.

`candidate_matches_need(candidate, need, content=None)` returns true only when:

1. candidate group equals need category; and
2. every normalized explicit subject term appears in the candidate path/stem,
   declaration/symbol/route token, trusted retrieval provenance, or the supplied
   content.

Passing `content` is how Task 5 rechecks retained excerpts. Do not accept group
occupancy alone. Matching is Unicode casefolded and token-boundary aware for
ASCII identifiers, while CJK uses normalized substring matching.

- [ ] **Step 6: Implement planner grounding and structural recommendations**

Planner fields are considered only when `planner.status == "ok"` and the field is
not discarded. A planner subject must already match a returned candidate; its
need is recommended and uses `planner_supported`. Structural recommendations use
`structural_recommendation` and are added only for applicable adjacent evidence:

```python
_STRUCTURAL_RECOMMENDATIONS = {
    "entrypoints": ("implementations", "tests"),
    "implementations": ("entrypoints", "tests"),
    "related_types": (),
    "tests": (),
    "configs_docs": (),
}
```

Never upgrade these to required and never create a duplicate of an explicit need.

- [ ] **Step 7: Run focused tests and context purity checks**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_needs.py \
  tests/test_context_pack.py \
  tests/test_query_intent.py \
  tests/test_identifier_intent.py \
  -q
```

Expected: all pass; monkeypatched filesystem/store/planner functions are never
called by need derivation or matching.

- [ ] **Step 8: Commit**

```bash
git add \
  src/context_search_tool/context_pack/models.py \
  src/context_search_tool/context_pack/roles.py \
  src/context_search_tool/context_pack/needs.py \
  src/context_search_tool/context_pack/builder.py \
  tests/test_context_needs.py \
  tests/test_context_pack.py
git commit -m "feat: derive scoped context evidence needs"
```

### Task 5: Select excerpts and enforce exact hard budgets

**Files:**

- Implement: `src/context_search_tool/context_pack/excerpts.py`
- Modify: `src/context_search_tool/context_pack/models.py`
- Modify: `src/context_search_tool/context_pack/builder.py`
- Modify: `src/context_search_tool/context_pack/serialization.py`
- Create: `tests/test_context_excerpts.py`
- Modify: `tests/test_context_pack.py`

- [ ] **Step 1: Write failing span-window tests**

Cover:

- retrieval spans sorted by required match, recommended match, protected direct
  evidence, score descending, then source line;
- configured before/after expansion clamped to result lines;
- overlapping or adjacent windows merged;
- at most two non-overlapping excerpts restored to source-line order;
- a synthetic result with no spans deriving one fallback span from its current
  line range/content;
- anchors using exact subject matches, then first matching window, then file head.

```python
def test_required_matching_span_wins_over_higher_scored_optional_span() -> None:
    excerpts = build_candidate_excerpts(
        candidate=large_candidate_with_required_match_on_lines_70_to_72(),
        needs=(required_postgresql_need(),),
        options=options(max_excerpts_per_item=1),
    )
    assert [(item.start_line, item.end_line) for item in excerpts] == [(70, 72)]
    assert "postgresql" in excerpts[0].content.casefold()
```

- [ ] **Step 2: Write failing Unicode/line-boundary tests**

Parameterize ASCII, CJK, emoji, combining marks, CRLF, one overlong line, no final
newline, and an empty last line. For every excerpt assert:

```python
assert excerpt.content_bytes == len(excerpt.content.encode("utf-8"))
assert excerpt.content_bytes <= options.max_excerpt_bytes
excerpt.content.encode("utf-8").decode("utf-8")  # valid UTF-8 round trip
```

Cropping removes complete trailing lines first. Only when one line alone exceeds
the remaining limit may it crop that line at a Unicode-code-point/UTF-8 boundary
and set `truncated=True`. Preserve original newline bytes for retained complete
lines; never synthesize source text.

- [ ] **Step 3: Write failing allocation and canonical-budget tests**

Construct packs that separately exhaust:

- `max_items`;
- `max_excerpts_per_item`;
- `max_excerpt_bytes`;
- `max_item_content_bytes`;
- `max_total_content_bytes`;
- `max_pack_bytes` with long paths/metadata;
- 65,536 bytes with a 3,132-line CSS candidate;
- metadata too large for every required match;
- the `pack_bytes` digit-width boundary;
- repeated identical builds.

Required-match items receive up to 512 bytes before recommended items, recommended
items before optional support, then remaining bytes follow final reading order.
Assert no subordinate ceiling is exceeded and repeated payload objects/bytes are
identical.

- [ ] **Step 4: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_excerpts.py \
  tests/test_context_pack.py -k "budget or excerpt or deterministic" \
  -q
```

Expected: failures because windowing/allocation and canonical compaction are not
implemented.

- [ ] **Step 5: Implement line-addressable source views and span normalization**

Build an immutable source-line table from candidate `start_line` and `content`
using `splitlines(keepends=True)`, preserving CRLF/final-newline facts. Reject
invalid start/end lines, non-finite span scores, spans outside candidate range,
and reversed spans with fixed `context_failed`.

Normalize exact duplicate spans by keeping the highest finite score and stable
ordered union of `sources`. Keep overlapping distinct spans until window
selection; fallback is:

```python
RetrievalSpan(
    start_line=candidate.start_line,
    end_line=candidate.end_line,
    score=candidate.relevance_score or 0.0,
    sources=("legacy_result",),
)
```

- [ ] **Step 6: Implement window scoring, merging, and UTF-8-safe cropping**

Use an internal `ExcerptWindow` record containing source lines, covered need IDs,
span score, and protected-direct status. Rank before limiting:

```python
(
    0 if required_need_ids else 1,
    0 if recommended_need_ids else 1,
    0 if protected_direct else 1,
    -score,
    start_line,
    end_line,
)
```

Expand by effective context lines, merge overlap/adjacency with unioned provenance,
take the configured count, restore line order, then crop. Required subject-bearing
lines are retained before surrounding context whenever a byte cap forces
cropping.

- [ ] **Step 7: Implement deterministic candidate selection and content allocation**

`builder.py` uses the approved stable candidate key:

```python
(
    not covers_unmatched_required,
    -required_count,
    not covers_unmatched_recommended,
    -recommended_count,
    promoted_group_position,
    0 if source_kind == "result" else 1,
    retrieval_rank_or_anchor_order,
    file_path,
)
```

Reserve one candidate for each matchable required need, then recommended needs,
then optional support. One candidate may cover several needs. Do not assign public
item IDs until final selection and reading order stabilize.

Allocation runs in this exact sequence:

1. reserve configured total content;
2. allocate up to 512 bytes to each required-coverage item;
3. allocate up to 512 bytes to each recommended-coverage item;
4. fill items in reading order up to per-item/global limits;
5. materialize canonical JSON with actual paths/metadata;
6. remove lowest-priority omission previews;
7. remove surplus reason strings from lowest-priority items;
8. remove complete lines from optional content, optional excerpts, then
   lowest-priority required content while retaining its matching line;
9. omit lowest-priority optional items and recompute;
10. when a required minimum representation cannot fit, omit that match, recompute
    as partial, and stay within the ceiling.

- [ ] **Step 8: Re-evaluate matches only against retained excerpts**

After allocation, call
`candidate_matches_need(candidate, need, content=joined_excerpts)`.
Remove provisional matches whose subject is no longer visible. If another
candidate can cover the need within limits, select it and rerun allocation;
otherwise leave the need unmatched for Task 6. Bound retries by candidate count
and fail sanitized on non-convergence.

- [ ] **Step 9: Run focused, raw compatibility, and performance-sanity tests**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_excerpts.py \
  tests/test_context_pack.py \
  tests/test_retrieval_pipeline.py -k "span or raw_payload" \
  tests/test_formatters.py -k query \
  -q
```

Expected: all pass; the large CSS test stays at or below 65,536 canonical bytes,
does not reread its source file, and completes deterministically.

- [ ] **Step 10: Commit**

```bash
git add \
  src/context_search_tool/context_pack/excerpts.py \
  src/context_search_tool/context_pack/models.py \
  src/context_search_tool/context_pack/builder.py \
  src/context_search_tool/context_pack/serialization.py \
  tests/test_context_excerpts.py \
  tests/test_context_pack.py
git commit -m "feat: compact context excerpts under hard budgets"
```

### Task 6: Derive honest readiness, omissions, confidence, and next queries

**Files:**

- Modify: `src/context_search_tool/context_pack/needs.py`
- Modify: `src/context_search_tool/context_pack/builder.py`
- Modify: `src/context_search_tool/context_pack/serialization.py`
- Modify: `tests/test_context_needs.py`
- Modify: `tests/test_context_pack.py`
- Modify: `tests/test_context_excerpts.py`

- [ ] **Step 1: Write failing status and missing-evidence tests**

Lock:

- `empty` only when retrieval has no usable result/anchor;
- `partial` when any required need is unmatched, all candidates for one required
  need are omitted, or usable evidence exists but no item fits;
- `ready` only when every required need has a selected excerpt-visible match;
- truncation alone does not make a retained match partial;
- truncating away the only subject line does.

Even an `empty` pack derives explicit needs from the original query and reports
them missing, but status/confidence remain `empty`/`none` because no usable
candidate exists. A query with no derivable need may have empty need/missing
arrays; never invent a non-group `results` category.

Each missing entry corresponds to one unmatched/budget-omitted need and uses a
fixed category/requiredness template containing only its bounded public subject.

- [ ] **Step 2: Write failing omission tests**

Assert total `budget.omitted_item_count` counts every normalized unselected
candidate, while public `omissions` is only a deterministic preview. Preview order
is required matches, recommended matches, candidate selection order; it is capped
at effective `max_items` and may shrink for metadata compaction. The entry has
only `file_path`, `group`, fixed reason, and matched need IDs—no content, score,
planner text, or diagnostics.

`budget.budget_exhausted` is true whenever an item, excerpt-count, excerpt-byte,
item-byte, total-content, or canonical-pack ceiling truncates/removes otherwise
selectable evidence; it is false when every normalized candidate fits intact.

- [ ] **Step 3: Write failing confidence tests**

Use a table covering:

| Condition | Level |
| --- | --- |
| empty | none |
| partial | low |
| ready, recommended missing | medium |
| ready, required excerpt truncated | medium |
| ready, planner-supported evidence material | medium |
| ready, no protected original-direct result | medium |
| ready, all recommendations satisfied, required untruncated, protected result selected | high |

Protected evidence means `score_parts["evidence_priority"] == 0` exactly on an
original result. Anchors, missing keys, booleans, NaN, and nonzero values do not
count. Confidence contains at most four closed reasons in fixed precedence.

- [ ] **Step 4: Write failing grounded next-query tests**

For at most three missing needs, required first in need order, assert seed
priority:

1. explicit original-query subject;
2. selected matching protected-direct file stem;
3. normalized original query.

Planner-only subjects are allowed only when grounded to a selected item. Suggestions
are whitespace-normalized, case-insensitively deduplicated, no more than 160 code
points, and retain their category suffix intact. Lock:

```python
assert queries_for(mysql_postgresql_bundle()) == [
    {
        "need_id": "need:configs_docs:postgresql",
        "query": "PostgreSQL configuration documentation",
        "purpose": "find missing required configuration evidence",
    },
]
assert all("/oups" not in item.query for item in owner_details_pack.next_queries)
assert all("owner dto" not in item.query.casefold() for item in config_test_pack.next_queries)
```

- [ ] **Step 5: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_needs.py \
  tests/test_context_pack.py \
  tests/test_context_excerpts.py \
  -q
```

Expected: new readiness/confidence/omission/query assertions fail.

- [ ] **Step 6: Implement fixed derivations and final orchestration**

Implement fixed template maps for missing reasons, next-query suffixes/purposes,
and confidence reasons. `build_context_pack()` now performs exactly:

```text
normalize candidates
classify candidates
derive ordered needs
match candidates provisionally
rank/select candidates
build preferred windows
allocate under every limit
re-match retained excerpts
derive omissions/status/confidence/next queries
materialize, compact, and validate canonical v2 JSON
```

Populate `EvidenceNeed.matched_item_ids` and `ContextItem.matched_need_ids` only
after public IDs are assigned in final reading order. Every ID resolves exactly
once; groups always have six keys; each selected item appears once across groups
and once in reading order.

- [ ] **Step 7: Add adversarial invariant failures**

Directly construct malformed packs/candidates for duplicate IDs, missing group
references, invalid roles/bases/source kinds, reversed excerpts, wrong byte
counts, non-finite scores, unresolved need IDs, duplicate source lines, invalid
budget totals, non-JSON values, and canonical byte mismatch. Each public build
boundary returns only fixed `context_failed`; no internal exception text appears.

- [ ] **Step 8: Run the complete pure-pack suite twice**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_context_needs.py \
  tests/test_context_excerpts.py \
  -q
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_context_pack.py \
  tests/test_context_needs.py \
  tests/test_context_excerpts.py \
  -q
```

Expected: both runs pass with identical deterministic snapshots/counts.

- [ ] **Step 9: Commit**

```bash
git add \
  src/context_search_tool/context_pack/needs.py \
  src/context_search_tool/context_pack/builder.py \
  src/context_search_tool/context_pack/serialization.py \
  tests/test_context_needs.py \
  tests/test_context_pack.py \
  tests/test_context_excerpts.py
git commit -m "feat: report honest context readiness"
```

### Task 7: Replace CLI/MCP context surfaces and keep feedback private

**Files:**

- Modify: `src/context_search_tool/formatters.py`
- Modify: `src/context_search_tool/cli.py`
- Modify: `src/context_search_tool/mcp_tools.py`
- Modify: `src/context_search_tool/mcp_server.py`
- Replace compatibility body with small v2 exports: `src/context_search_tool/context_pack/__init__.py`
- Replace remaining v1 reference assertions: `tests/test_context_pack.py`
- Modify: `tests/test_formatters.py`
- Modify: `tests/test_cli_commands.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing bounded-envelope tests**

The shared context success envelope has exactly:

```python
{
    "ok": True,
    "repo": str(repo.resolve()),
    "query": bundle.query,
    "retrieval": {
        "result_count": len(bundle.results),
        "evidence_anchor_count": len(bundle.evidence_anchors),
        "planner_status": bundle.planner.status,
        "planner_intent": (
            bundle.planner.intent if bundle.planner.status == "ok" else "unknown"
        ),
    },
    "context_pack": context_pack_payload(pack),
}
```

Assert `results`, `evidence_anchors`, summary arrays, query variants, rewritten
queries, grep/symbol hints, semantic matches, and score-part maps are absent.
Assert CLI JSON and MCP `context_pack` values are exactly equal for the same
bundle/options and contain source content only in item excerpts.

- [ ] **Step 2: Write failing option/error/one-pass tests**

Add CLI flags:

```text
--max-items N
--max-context-bytes N
```

Add nullable MCP parameters `max_items` and `max_context_bytes`. Tests assert
invalid request/persisted limits fail before `query_repository()` with:

```text
Error: invalid_context_options: <fixed validation message>
```

and MCP:

```python
{"ok": False, "error": {"code": "invalid_context_options", "message": fixed}}
```

Known or unexpected pack failures after retrieval use `context_failed` with the
closed/sanitized message. Counters prove one valid invocation performs exactly
one retrieval and one build; invalid options perform zero of both. Existing repo,
index, manifest, query, HTTP, and planner errors retain their existing codes.

- [ ] **Step 3: Write failing Markdown tests**

Markdown follows `reading_order` and renders each selected item/excerpt once.
Assert headings include status, confidence, needs, missing evidence, omissions,
next queries, and budget. Assert duplicate source sentinels occur once and no
formatter dereferences `bundle.results`/anchors after receiving the pack. The
Markdown byte size is not reported as `budget.pack_bytes`.

- [ ] **Step 4: Write failing privacy tests**

The context feedback subobject contains only bounded metadata:

```python
{
    "schema_version": 2,
    "status": "partial",
    "confidence": "low",
    "group_counts": {group: int for group in CONTEXT_GROUPS},
    "need_count": int,
    "required_need_count": int,
    "selected_item_count": int,
    "excerpt_count": int,
    "truncated_item_count": int,
    "omitted_item_count": int,
    "required_missing_categories": list[str],
    "recommended_missing_categories": list[str],
    "budget": {
        "max_items": int,
        "max_pack_bytes": int,
        "content_bytes": int,
        "pack_bytes": int,
    },
    "next_query_count": int,
}
```

Serialize a payload containing unique path/content/subject/need-ID/next-query/
planner/discarded-hint sentinels and assert none occur in the feedback JSONL.
Malformed pack metadata produces no fabricated context feedback.

- [ ] **Step 5: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_formatters.py -k context \
  tests/test_cli_commands.py -k context \
  tests/test_mcp_tools.py -k context \
  tests/test_mcp_server.py \
  -q
```

Expected: v1 envelope/signature/format/privacy assertions fail.

- [ ] **Step 6: Implement one shared envelope and formatters**

First replace the temporary v1 `context_pack/__init__.py` body with explicit v2
exports from `models.py`, `builder.py`, and `serialization.py`; export only the
constants, records, fixed error, option resolver, builder, payload, and canonical
byte helper listed in this plan. Remove v1 dereference/reference helpers and
replace their remaining tests with v2 self-contained-item invariants.

Add `context_payload(repo, bundle, pack)` in `formatters.py` and consume it in CLI
and MCP. `format_context_json()` uses
`json.dumps(envelope, allow_nan=False)` on that
envelope. `format_context_markdown()` accepts only pack/envelope data and indexes
items by ID solely to follow reading order; it never reads source from a second
array.

- [ ] **Step 7: Validate context options before retrieval**

In CLI and MCP, load/apply `final_top_k` first, compute
`evidence_anchor_top_k(final_top_k)`, resolve context options (including request
overrides), and only then call `query_repository()`. Keep `context_lines`,
`full_file`, planner switches, and raw query behavior unchanged. Pass
`max_context_bytes` to the resolver as `max_pack_bytes`.

- [ ] **Step 8: Replace feedback extraction with strict v2 metadata**

Extract only fields/types from the approved feedback shape. Build missing
category lists in closed group order; do not copy public subject terms or IDs.
Do not reuse raw-query score/summary extraction for the context envelope because
those arrays are intentionally absent.

- [ ] **Step 9: Run all public contract regressions**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  tests/test_context_pack.py \
  tests/test_context_needs.py \
  tests/test_context_excerpts.py \
  -q
```

Expected: all pass; raw query tests are unchanged except shared helper imports.

- [ ] **Step 10: Commit**

```bash
git add \
  src/context_search_tool/formatters.py \
  src/context_search_tool/cli.py \
  src/context_search_tool/mcp_tools.py \
  src/context_search_tool/mcp_server.py \
  src/context_search_tool/context_pack/__init__.py \
  tests/test_context_pack.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py
git commit -m "feat: expose bounded context pack v2 surfaces"
```

### Task 8: Migrate quality schema, metrics, and the offline P2 profile

**Files:**

- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/metrics.py`
- Modify: `src/context_search_tool/quality/runner.py`
- Modify: `tests/fixtures/retrieval_quality/queries.json`
- Modify: `tests/test_quality_cases.py`
- Modify: `tests/test_quality_metrics.py`
- Modify: `tests/test_quality_runner.py`
- Modify: `tests/test_quality_catalog.py`
- Modify: `tests/test_quality_p2.py`

- [ ] **Step 1: Write failing typed-schema tests**

Add:

```python
@dataclass(frozen=True)
class ExpectedNeedMatch:
    category: str
    subject: str
    required: bool
    matched: bool

@dataclass(frozen=True)
class QualityCase:
    # existing fields retain order
    expected_need_matches: tuple[ExpectedNeedMatch, ...] = ()
    maximum_pack_bytes: int | None = None
    maximum_truncated_items: int | None = None
    forbidden_next_query_patterns: tuple[str, ...] = ()
```

These fields are legal only for `mode="context_pack"`. Validate closed categories,
non-empty subject at most 64 code points, strict booleans, positive pack limit,
non-negative truncation limit, non-empty bounded patterns, and compile each
pattern case-insensitively during fixture load. Result-mode cases reject them.

- [ ] **Step 2: Write failing metric/gate tests**

`evaluate_context_pack()` retains `context_completeness` for historical group/path
matchers and adds exactly:

```text
evidence_need_count
required_need_count
matched_required_need_count
evidence_need_completeness
pack_bytes
content_bytes
truncated_item_count
omitted_item_count
```

Expected need matching compares normalized category, casefolded public subject,
requiredness, and whether `matched_item_ids` is non-empty. Gate failures name the
bounded expected subject but never source content. `maximum_pack_bytes` checks
both reported and freshly canonicalized bytes. Forbidden patterns scan only
`next_queries[*].query`.

- [ ] **Step 3: Write failing runner/non-regression tests**

Prove:

- only context cases build a pack;
- one case performs one retrieval and one build;
- case records include v2 status/confidence and the eight metrics;
- raw result-mode record keys/values remain unchanged;
- a build failure becomes the existing sanitized quality error record;
- `p2_context_pack` remains offline hash/planner-disabled and snapshot-only.

- [ ] **Step 4: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py \
  -q
```

Expected: v2 field/metric/profile assertions fail.

- [ ] **Step 5: Implement typed parsing and evaluation**

Parse the fields exactly once in `cases.py`. In `metrics.py`, materialize the pack
through the canonical serializer rather than trusting stale budget bytes. The
context gate fails on any expected mismatch, over-limit value, forbidden query,
or existing group/path expectation. Aggregate code remains generic; add a focused
assertion that the new numeric metrics aggregate and null historical completeness
is still excluded.

- [ ] **Step 6: Migrate the five committed `p2_context_pack` cases**

Keep their repo/query selection and raw expected paths, replace schema-v1
reference/budget expectations with v2 group/path and scoped need expectations,
and set:

```json
{
  "maximum_pack_bytes": 65536,
  "maximum_truncated_items": 4,
  "forbidden_next_query_patterns": ["/oups", "GET /owners dto"]
}
```

Each case must state the evidence need outcome actually required by its original
query. Do not weaken existing raw `ci` cases or change their mode.

- [ ] **Step 7: Run the migrated offline profile and unchanged `ci`**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py \
  -q
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output .quality/real-projects/p2-context-pack-v2.json \
  --markdown .quality/real-projects/p2-context-pack-v2.md
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/real-projects/p2-context-ci.json \
  --markdown .quality/real-projects/p2-context-ci.md
```

Expected: all selected required cases pass, both context completeness and
evidence-need completeness gates are present for P2, every pack is within its
reported maximum, and `ci` retains its unchanged selected IDs/results.

- [ ] **Step 8: Commit**

```bash
git add \
  src/context_search_tool/quality/cases.py \
  src/context_search_tool/quality/metrics.py \
  src/context_search_tool/quality/runner.py \
  tests/fixtures/retrieval_quality/queries.json \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py
git commit -m "test: migrate context quality gates to v2"
```

### Task 9: Add safe pinned-repository preparation and the real Spring profile

**Files:**

- Create: `src/context_search_tool/quality/prepare.py`
- Modify: `src/context_search_tool/quality/__main__.py`
- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/runner.py`
- Modify: `tests/fixtures/retrieval_quality/queries.json`
- Create: `tests/test_quality_prepare.py`
- Modify: `tests/test_quality_cases.py`
- Modify: `tests/test_quality_runner.py`
- Modify: `tests/test_quality_catalog.py`
- Modify: `tests/test_quality_p2.py`

- [ ] **Step 1: Write failing pinned-source declaration tests**

`QualityRepo` gains optional `source_url`, `source_commit`, and `checkout_dir`.
Remote fields must appear together and are mutually exclusive with committed
snapshot/direct/env source fields. Validate:

- HTTPS URL with a non-empty host/path and no credentials, fragment, newline, or
  leading Git option;
- lowercase/uppercase exact 40-hex commit normalized to lowercase;
- one safe portable checkout component (not absolute, dot, parent, separator,
  Windows reserved name, or option-like);
- at least one profile and query.

Lock the exact declaration:

```json
{
  "repo_key": "spring_petclinic",
  "source_url": "https://github.com/spring-projects/spring-petclinic.git",
  "source_commit": "51045d1648dad955df586150c1a1a6e22ef400c2",
  "checkout_dir": "spring-petclinic",
  "profiles": ["p2_real_context"]
}
```

- [ ] **Step 2: Write failing safe/idempotent preparation tests**

Use a local bare Git remote—never the network—in unit tests. Assert the command:

- invokes Git with argument arrays and `shell=False`;
- clones/fetches and checks out exact detached HEAD;
- verifies `rev-parse HEAD`, canonical `remote.origin.url`, and
  `status --porcelain --untracked-files=no`;
- writes `<repos-dir>/.cst-quality-provenance.json` atomically with repo key, URL,
  commit, checkout directory, and preparation timestamp;
- is idempotent on a valid checkout;
- rejects wrong commit, wrong remote, tracked dirtiness, symlink/path escape,
  unrelated non-empty directory, malformed manifest, and Git failures;
- never deletes or overwrites an unrelated checkout.

- [ ] **Step 3: Write failing run-time prepared-source tests**

`quality run --profile p2_real_context` accepts `--repos-dir` (default
`.quality/repos`), validates the prepared checkout/manifest again, and copies the
source into the existing isolated quality workspace. Missing, dirty, wrong
commit/remote, or mismatched manifest is a required error—not a skip and not a
snapshot/env fallback. Other profiles preserve existing source resolution.

- [ ] **Step 4: Run RED**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_prepare.py \
  tests/test_quality_cases.py -k "source or profile" \
  tests/test_quality_runner.py -k "source or prepared" \
  -q
```

Expected: missing declaration/preparation/CLI failures.

- [ ] **Step 5: Implement safe Git operations**

Use one helper:

```python
def _git(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return completed.stdout.strip()
```

Pass `--` before any caller-derived path where Git accepts it. Create the target
only after validating its parent and existing state. Clone to a sibling temporary
directory, verify, then atomically rename into place; fetch/update an already
owned checkout without resetting unrelated directories. Use fixed sanitized
public errors and clean temporary directories after failure.

- [ ] **Step 6: Register `quality prepare` and prepared run resolution**

Add:

```text
cst quality prepare FIXTURE --profile p2_real_context --repos-dir .quality/repos
cst quality run FIXTURE --profile p2_real_context --repos-dir .quality/repos
```

Preparation selects only remote repos used by the profile and errors when none
exist. It prints bounded repo key/commit/checkout information, never source
content or credentials.

- [ ] **Step 7: Add the four exact Spring cases**

Use hash embeddings, planner disabled, final top-k 12, and the default v2 budget.
Add:

1. `owner registration form validation flow` — lock retrieved roles for
   `src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java`,
   `Owner.java`, `src/test/java/org/springframework/samples/petclinic/owner/OwnerControllerTests.java`,
   and `src/main/resources/templates/owners/createOrUpdateOwnerForm.html` when
   present in the bounded result; require honest missing needs otherwise.
2. `OwnerController tests for owner registration validation` — lock controller
   and `OwnerControllerTests.java` roles and scoped identifier/test needs.
3. `宠物主人详情页如何加载宠物和就诊记录` — lock available
   `OwnerController.java`, `OwnerRepository.java`, `Owner.java`, `Pet.java`,
   `Visit.java`, and `src/main/resources/templates/owners/ownerDetails.html`
   assignments; forbid every next query matching `/oups`.
4. `MySQL PostgreSQL database profile configuration and integration tests` —
   lock available `src/main/resources/application-mysql.properties`,
   `src/main/resources/application-postgres.properties`,
   `src/test/java/org/springframework/samples/petclinic/MySqlIntegrationTests.java`,
   and `PostgresIntegrationTests.java`; assert distinct MySQL/PostgreSQL
   config/test need outcomes and forbid unrelated owner DTO queries.

For a critical path absent from the bounded hash result, encode the corresponding
need as unmatched/partial rather than removing the subject requirement. Every
case sets 65,536 maximum pack bytes, exact per-item/excerpt ceilings, deterministic
repeat comparison, and v2 feedback privacy.

- [ ] **Step 8: Run unit tests, prepare from empty cache, and execute twice**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_prepare.py \
  tests/test_quality_cases.py \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py \
  -q
test ! -e .quality/repos/p2-real-context-verification-empty
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality prepare \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos/p2-real-context-verification-empty
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos/p2-real-context-verification-empty \
  --output .quality/real-projects/p2-real-context-first.json \
  --markdown .quality/real-projects/p2-real-context-first.md
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality prepare \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos/p2-real-context-verification-empty
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos/p2-real-context-verification-empty \
  --output .quality/real-projects/p2-real-context-second.json \
  --markdown .quality/real-projects/p2-real-context-second.md
```

The `test ! -e` guard proves the first preparation starts from an empty named
ignored directory without deleting any prior user state. Expected: preparation is idempotent, both reports
pass all required gates, and their case `context_pack`/metric payloads are
identical after excluding timestamps/workspace provenance.

- [ ] **Step 9: Commit**

```bash
git add \
  src/context_search_tool/quality/prepare.py \
  src/context_search_tool/quality/__main__.py \
  src/context_search_tool/quality/cases.py \
  src/context_search_tool/quality/runner.py \
  tests/fixtures/retrieval_quality/queries.json \
  tests/test_quality_prepare.py \
  tests/test_quality_cases.py \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py
git commit -m "test: add pinned real context quality profile"
```

### Task 10: Document, reconcile external evidence, and run final verification

**Files:**

- Modify: `README.md`
- Modify: `docs/retrieval-quality.md`
- Modify: `docs/superpowers/specs/2026-07-15-p2-context-pack-v2-hardening-design.md` metadata only
- Modify: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` only when independent acceptance permits
- Verify every source/test/fixture/plan file named above

- [ ] **Step 1: Update design/plan metadata without changing decisions**

Set:

```text
Status: Approved; written review complete
Implementation plan: docs/superpowers/plans/2026-07-15-p2-context-pack-v2-hardening.md
```

Do not edit design contract text during documentation cleanup. A discovered
contract conflict returns to review rather than being silently rewritten.

- [ ] **Step 2: Document v2 public behavior and quality preparation**

README must explain:

- raw `query` versus self-contained `context`;
- schema v2 breaking change and exact bounded envelope;
- CLI/MCP `max_items`/`max_context_bytes`;
- evidence needs, missing evidence, reading order, excerpts, omissions,
  confidence, and exact canonical budget;
- one retrieval pass/no context I/O;
- fixed errors and privacy-safe feedback.

`docs/retrieval-quality.md` must document:

- migrated `p2_context_pack` and opt-in `p2_real_context`;
- typed need/budget expectations and eight metrics;
- `quality prepare`/`quality run --repos-dir` commands;
- pinned URL/commit, detached/clean verification, and no implicit network;
- the four Spring queries and dated CST/fast-context comparison parameters;
- unavailable model/comparator dependencies as explicit outcomes.

- [ ] **Step 3: Run every focused deterministic suite**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_config_paths.py \
  tests/test_path_roles.py \
  tests/test_context_pack.py \
  tests/test_context_needs.py \
  tests/test_context_excerpts.py \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_catalog.py \
  tests/test_quality_p2.py \
  tests/test_quality_prepare.py \
  -q
```

Expected: zero failures. Diagnose rather than weaken any closed schema, byte, need,
or pinned-source gate.

- [ ] **Step 4: Run the full suite and deterministic profiles**

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
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

Inspect aggregate counts, selected case IDs, evidence-need completeness, canonical
pack limits, and raw `ci` results from the JSON—not only process exit codes.

- [ ] **Step 5: Re-run the pinned real profile from empty and populated caches**

Repeat Task 9 Step 8 with a new ignored directory
`.quality/repos/p2-real-context-final`. Verify exact commit, remote, clean tracked
state, detached HEAD, idempotent preparation, all four required case results,
deterministic pack payloads, and forbidden-query/privacy assertions.

- [ ] **Step 6: Reconcile shared-role retrieval dependencies**

Run applicable smoke and model-backed Phase 1 commands documented in
`docs/retrieval-quality.md`. Record the exact command, implementation commit,
model/provider version, selected/passed counts, and any sanitized dependency
failure. Never cite stale reports as current evidence and never mark a failed or
unavailable profile as passing.

- [ ] **Step 7: Repeat the four dated CST/fast-context comparisons**

Against the exact prepared PetClinic commit, run the four design queries with CST
hash (`final_top_k=12`), any available BGE/planner profile, and fast-context three
turns using the same parameters. Manually inspect critical-file coverage,
group/role assignments, pack bytes, missing needs, and next queries. Document
results as qualitative evidence; do not turn remote/model output into a
deterministic oracle.

- [ ] **Step 8: Update the roadmap conditionally**

Only when the roadmap's independent Phase 1 acceptance dependency and every P2.1
gate pass, record P2.1 completion with exact report names/counts and point the
next-stage review to RetrievalTrace/core decomposition. Otherwise keep acceptance
pending and document the explicit unresolved dependency. Do not begin later-phase
implementation.

- [ ] **Step 9: Run final contract/privacy/diff/artifact checks**

```bash
git diff --check
git status --short
git diff --stat f3d6fb46fe49a50d0f6807a3e084cc7c572d5252..HEAD
rg -n "schema_version.*1|result:0|anchor:0" \
  src/context_search_tool/context_pack \
  tests/test_context_pack.py \
  tests/test_context_needs.py \
  tests/test_context_excerpts.py
rg -n "RetrievalTrace|multi-round|graph traversal|marginal gain" src tests
```

Expected:

- `git diff --check` prints nothing;
- only planned files changed;
- ignored `.quality` artifacts are not staged;
- no v1 reference contract remains in v2 package/tests;
- no Phase 3/4 implementation appears;
- final committed worktree is clean.

- [ ] **Step 10: Commit documentation and conditional roadmap state**

When roadmap acceptance is still pending:

```bash
git add \
  README.md \
  docs/retrieval-quality.md \
  docs/superpowers/specs/2026-07-15-p2-context-pack-v2-hardening-design.md \
  docs/superpowers/plans/2026-07-15-p2-context-pack-v2-hardening.md
git commit -m "docs: document context pack v2 hardening"
```

When every independent acceptance condition passes, include the roadmap in the
same commit. Do not stage generated quality reports unless the repository's
existing evidence policy explicitly requires the named artifacts.

## Final Verification Matrix

| Requirement | Focused proof | Acceptance proof |
| --- | --- | --- |
| Exact schema v2 and self-contained items | `test_context_pack.py` exact keys/invariants | CLI/MCP pack identity and P2 reports |
| Persisted/request limits | `test_config_paths.py` strict matrix | every profile reports effective ceilings |
| Shared Spring/JVM roles and basis | `test_path_roles.py` precedence table | `ci`/smoke/Phase 1 plus real Spring cases |
| Internal spans, raw compatibility | retrieval merge/span tests and raw byte fixture | raw CLI/MCP/`ci` unchanged |
| Scoped needs, no group-occupancy false readiness | `test_context_needs.py` | MySQL/PostgreSQL and owner cases |
| Excerpt relevance and Unicode safety | `test_context_excerpts.py` matrix | large CSS and real-source packs |
| Exact item/content/canonical budgets | boundary/digit-width/repeat tests | all P2 packs ≤ 65,536 bytes |
| Honest status/confidence/omissions | pure builder tables | offline and real profile gates |
| Grounded follow-ups | misleading summary/planner tests | no `/oups` or unrelated owner DTO |
| One retrieval/one build/no context I/O | monkeypatch counters | CLI/MCP/runner integration |
| Fixed errors | invalid/adversarial surface tests | no internal text in reports |
| Feedback privacy | sentinel JSONL tests | real profile feedback inspection |
| Safe explicit preparation | local-bare-remote tests | empty/populated pinned cache runs |
| Quality metrics/history | cases/metrics/runner tests | P2 completeness/need gates and raw `ci` |
| External evidence honesty | dependency-result tests/docs | dated model/fast-context comparison |
| Scope and repository hygiene | grep/diff/artifact checks | clean committed worktree |

## Stop Point

This plan ends after ContextPack v2, its bounded public surfaces, offline and
pinned real-project quality loops, documentation, and conditional roadmap
reconciliation are implemented and verified. It does not execute generated next
queries or begin multi-round retrieval, graph traversal, type resolution, or
RetrievalTrace.
