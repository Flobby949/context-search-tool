# P2 Context Pack Output Design

Date: 2026-07-14
Status: Approved direction; written review pending
Repository: `/Users/flobby/Documents/context-seatch-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor: `docs/superpowers/specs/2026-07-13-p1-query-understanding-closure-design.md`

## Summary

Phase 2 adds a first-class `ContextPack` output for coding agents. It turns one
bounded retrieval response into an ordered reading set with explicit groups,
evidence gaps, follow-up queries, readiness confidence, and budget accounting.

The selected design keeps raw search and agent-oriented context retrieval as two
separate public operations:

- `cst query` and `context_search_query` remain the fast, raw ranked-result
  interfaces and keep their current contracts.
- New `cst context` and `context_search_context` operations run the same single
  retrieval pass, then invoke one deterministic `ContextPack` builder.

The builder consumes the final `QueryBundle`; it does not collect new
candidates, change scores, invoke a model, traverse a graph, or run another
query. The context response retains the original `results` and
`evidence_anchors`. Pack items reference those arrays instead of duplicating
source content.

This gives agents a clearer response today and creates the correct public seam
for later `RetrievalTrace` and controlled multi-round exploration. Those later
features are not implemented in Phase 2.

## Phase Boundary And Preconditions

This design accepts the project decision that Phase 0 and Phase 1 are complete.
The repository currently contains the Phase 1 implementation and acceptance
gates, but the roadmap header still points to a Phase 1 acceptance review and
local `.quality/` artifacts may reflect earlier commits. Before Phase 2 is
declared complete, the implementation plan must reconcile the roadmap pointer
with the actual accepted Phase 1 commit and reports. Stale local reports must not
be presented as Phase 1 acceptance evidence.

That documentation reconciliation is a release precondition, not permission to
reopen Phase 1 or change its ranking behavior during Phase 2.

## Current State

CST already has most of the evidence needed to construct a useful context pack:

- `query_repository()` returns a `QueryBundle` containing ranked
  `RetrievalResult` values, `EvidenceAnchor` values, planner diagnostics, query
  variants, semantic provenance, follow-up keywords, and a `RetrievalSummary`.
- `RetrievalSummary` identifies likely entrypoints, implementations, related
  types, and possibly legacy symbols, but it contains names rather than a
  navigable reading set.
- `classify_path_role()` recognizes tests, entrypoints, services, repositories,
  data types, configuration, documentation, and other generic roles.
- `classify_frontend_role()` recognizes routes, pages, layouts, services,
  stores, utilities, shared components, and type declarations.
- CLI JSON and MCP already expose raw results, reasons, score parts, planner
  status, semantic matches, evidence anchors, and bounded result counts.
- The quality catalog has a `mode` field whose current effective behavior is
  always raw-result evaluation. Earlier design documentation reserved
  `context_pack` as a future mode.

The current gaps are output-level gaps:

- results are not tied to stable response-local reading items;
- tests and config/doc evidence are not grouped with code roles;
- the response does not distinguish a ready reading set from a structurally
  partial one;
- follow-up keywords are not expressed as actionable, purpose-labelled queries;
- effective retrieval limits and actual returned content size are not reported
  as one budget;
- agents must infer a reading order from score order alone.

## Goals

- Add a versioned, deterministic `ContextPack` contract.
- Give coding agents one explicit operation for task-oriented context retrieval.
- Preserve every raw result and evidence anchor in the richer response.
- Group returned evidence into entrypoints, implementations, related types,
  tests, configs/docs, and supporting evidence.
- Produce a deterministic reading order without changing retrieval rank.
- Report required and recommended missing evidence conservatively.
- Produce bounded, evidence- or query-derived `next_queries` without another
  model call.
- Report readiness confidence without presenting it as a probability of
  correctness.
- Report the effective result/context limits and actual content bytes.
- Extend the quality loop with context-group and context-completeness gates.
- Keep the design ready to receive trace and multi-round data through the new
  context surface later.

## Non-Goals

- No additional retrieval round.
- No candidate, ranking, score, weight, relation, or result-limit change.
- No `RetrievalTrace`; that remains Phase 3.
- No retrieval-core decomposition; only a new isolated packer is added.
- No controlled exploration, stopping policy, or marginal-gain calculation;
  those remain Phase 4.
- No AST, call graph, import graph, or new framework plugin.
- No LLM summarization, answer generation, or model-based confidence.
- No guarantee that a missing category is absent from the repository. Phase 2
  can only describe the bounded result set it received.
- No hidden removal of low-ranked, legacy, generated, or otherwise noisy raw
  results.
- No new global token budget. Phase 2 reports existing limits and actual UTF-8
  bytes; later work may add an explicit context token budget.
- No change to `cst query` or `context_search_query` response shapes.

## Decision And Alternatives

### Selected: Dedicated Context Surface Over A Shared Deterministic Packer

Add `cst context` and `context_search_context`. Both call the existing retrieval
core once and pass its `QueryBundle` to a shared builder in
`context_pack.py`.

This separates two stable product meanings:

- **query** means raw ranked search evidence;
- **context** means an agent-oriented reading set derived from that evidence.

The separation is more valuable than the small cost of one new CLI command and
one new MCP tool. Future trace or exploration behavior can be introduced through
the context operation without silently slowing or changing exact-search calls.

### Rejected: Add `context_pack` To Every Existing Query Response

This is the smallest initial API diff, but it makes one operation serve two
different consumers. Every exact lookup would pay the payload and conceptual
cost of a context pack. Later exploration budgets would either bloat the query
signature or change query latency unexpectedly.

The dedicated context operation remains additive while keeping the old contract
unambiguous.

### Rejected: Build Packs Inside `retrieval.py`

`retrieval.py` already owns candidate collection, expansion, ranking, and result
construction. Adding output grouping, gap inference, query suggestions, and
serialization there would increase the architecture pressure identified by the
roadmap. A pure post-retrieval module is smaller and independently testable.

### Rejected: Wait For Trace And Multi-Round Exploration

Trace and exploration can improve pack completeness, but neither is required to
make the current results easier for agents to consume. Waiting would combine
three roadmap phases and make it difficult to distinguish output-contract gains
from retrieval-quality gains.

## Runtime Architecture

```text
User / Coding Agent
  -> raw search
       -> cst query / context_search_query
       -> query_repository(...)
       -> existing QueryBundle and existing output contract

  -> task-oriented context
       -> cst context / context_search_context
       -> query_repository(...) exactly once
       -> existing QueryBundle
       -> build_context_pack(...) exactly once
            -> classify returned items
            -> infer expected evidence
            -> derive reading order
            -> describe missing evidence
            -> derive bounded next queries
            -> calculate readiness confidence
            -> record budget usage
       -> raw query fields + versioned ContextPack
```

`build_context_pack()` is deterministic for the same bundle and effective
options. It performs no I/O and does not access the SQLite store, vector index,
repository files, network, or model provider.

## Public Operations

### Existing Raw Operations

The following remain unchanged:

```text
cst query [REPO] QUERY [--json] [--context-lines N] [--full-file]
          [--planner | --no-planner]

context_search_query(repo, query, context_lines, full_file, final_top_k)
```

Compatibility means more than keeping the names. For the same deterministic
configuration, their existing JSON/MCP keys, ranked result order, evidence
anchor order, planner fields, error envelopes, and defaults remain unchanged.

### New CLI Operation

```text
cst context [REPO] QUERY [--json] [--context-lines N] [--full-file]
            [--planner | --no-planner]
```

It follows the same repository resolution and planner-override behavior as
`cst query`.

- Default output is ContextPack-oriented Markdown.
- `--json` emits the full structured context response.
- The CLI uses `retrieval.final_top_k` from effective configuration, matching
  the existing query command.
- No pack-specific tuning flags are added in v1.

### New MCP Operation

```text
context_search_context(repo, query, context_lines, full_file, final_top_k)
```

It accepts the same arguments and validation rules as
`context_search_query`. In particular, `final_top_k` remains the only per-call
result-limit override, and values below one return `query_failed`.

The new tool uses the same success envelope (`ok`, `repo`, and `index`) and the
same structured `repo_not_found`, `missing_index`, and `query_failed` errors.
An internal ContextPack contract failure uses the additional `context_failed`
code described below.

## ContextPack V1 Contract

The context response contains all existing query payload fields plus one new
top-level `context_pack` object. The old query operation does not receive this
field.

An illustrative response is:

```json
{
  "query": "workspace page flow",
  "expanded_tokens": [
    "workspace",
    "page",
    "flow",
    "controller",
    "service",
    "dto"
  ],
  "query_variants": [
    {
      "variant_id": "original",
      "text": "workspace page flow",
      "source": "original"
    },
    {
      "variant_id": "planner:0",
      "text": "workspace controller service dto",
      "source": "planner"
    }
  ],
  "variant_retrieval_status": "hybrid",
  "followup_keywords": ["WorkspaceServiceImpl"],
  "summary": {
    "entry_points": ["GET /workspace/page"],
    "implementation": ["WorkspaceServiceImpl.list"],
    "related_types": ["WorkspaceDto"],
    "possibly_legacy": []
  },
  "planner": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen3.5:4b-mlx",
    "prompt_version": "qwen-query-planner-v1",
    "prompt_hash": "sha256:example",
    "status": "ok",
    "latency_ms": 42,
    "rewritten_queries": ["workspace controller service dto"],
    "grep_keywords": ["WorkspaceController"],
    "symbol_hints": ["WorkspaceServiceImpl"],
    "intent": "feature_lookup"
  },
  "results": [
    {
      "file_path": "src/WorkspaceController.java",
      "start_line": 10,
      "end_line": 24,
      "content": "class WorkspaceController { ... }",
      "score": 2.1,
      "score_parts": {"evidence_priority": 0.0},
      "reasons": ["endpoint signal match"],
      "followup_keywords": ["WorkspaceServiceImpl"],
      "semantic_matches": []
    },
    {
      "file_path": "src/WorkspaceServiceImpl.java",
      "start_line": 8,
      "end_line": 22,
      "content": "class WorkspaceServiceImpl { ... }",
      "score": 1.8,
      "score_parts": {"evidence_priority": 2.0},
      "reasons": ["implementation chain match"],
      "followup_keywords": ["WorkspaceDto"],
      "semantic_matches": []
    },
    {
      "file_path": "src/WorkspaceDto.java",
      "start_line": 1,
      "end_line": 8,
      "content": "class WorkspaceDto { ... }",
      "score": 1.2,
      "score_parts": {"evidence_priority": 2.0},
      "reasons": ["relation expansion"],
      "followup_keywords": [],
      "semantic_matches": []
    }
  ],
  "evidence_anchors": [],
  "context_pack": {
    "schema_version": 1,
    "status": "ready",
    "items": [
      {
        "id": "result:0",
        "source": "result",
        "source_index": 0,
        "file_path": "src/WorkspaceController.java",
        "start_line": 10,
        "end_line": 24,
        "group": "entrypoints",
        "role": "entrypoint",
        "classification_basis": "path_role"
      },
      {
        "id": "result:1",
        "source": "result",
        "source_index": 1,
        "file_path": "src/WorkspaceServiceImpl.java",
        "start_line": 8,
        "end_line": 22,
        "group": "implementations",
        "role": "service_impl",
        "classification_basis": "path_role"
      },
      {
        "id": "result:2",
        "source": "result",
        "source_index": 2,
        "file_path": "src/WorkspaceDto.java",
        "start_line": 1,
        "end_line": 8,
        "group": "related_types",
        "role": "related_type",
        "classification_basis": "retrieval_summary"
      }
    ],
    "groups": {
      "entrypoints": ["result:0"],
      "implementations": ["result:1"],
      "related_types": ["result:2"],
      "tests": [],
      "configs_docs": [],
      "supporting": []
    },
    "reading_order": ["result:0", "result:1", "result:2"],
    "missing_evidence": [
      {
        "category": "tests",
        "required": false,
        "reason": "feature context has no test in the bounded result set"
      }
    ],
    "next_queries": [
      {
        "query": "WorkspaceServiceImpl test",
        "purpose": "find_tests",
        "reason": "tests are recommended but missing"
      }
    ],
    "confidence": {
      "level": "medium",
      "reasons": [
        "all required evidence groups are present",
        "recommended test evidence is missing"
      ]
    },
    "budget": {
      "max_results": 12,
      "included_results": 3,
      "included_evidence_anchors": 0,
      "content_bytes": 93,
      "context_before_lines": 8,
      "context_after_lines": 12,
      "full_file": false,
      "max_full_file_bytes": 200000
    }
  }
}
```

The example uses shortened source snippets, but its item IDs and source indexes
resolve to the included raw result objects exactly as a real response does.

### Schema Version

`context_pack.schema_version` starts at integer `1`.

- Additive optional fields may be introduced without incrementing the version.
- Removing a field, changing its meaning or type, changing item-reference
  semantics, or changing a required enum value requires a new schema version.
- The version applies only to `context_pack`, not to the existing raw query
  payload.

### Status

`status` is one of:

- `empty`: no result or evidence-anchor item was returned;
- `partial`: at least one required evidence group is missing;
- `ready`: at least one item exists and every required group is present.

`ready` means ready for the next reading step. It does not claim that the pack
contains every relevant file in the repository.

## Item And Reference Contract

Every raw result and every evidence anchor becomes exactly one pack item:

```json
{
  "id": "result:0",
  "source": "result",
  "source_index": 0,
  "file_path": "src/WorkspaceController.java",
  "start_line": 10,
  "end_line": 24,
  "group": "entrypoints",
  "role": "entrypoint",
  "classification_basis": "path_role"
}
```

Item rules:

- IDs are deterministic and response-local: `result:<zero-based-index>` or
  `anchor:<zero-based-index>`.
- `source_index` addresses the top-level `results` or `evidence_anchors` array.
- File path and line fields are repeated so an agent can inspect the pack
  structure without first joining arrays.
- Content, score parts, semantic matches, and ranking reasons remain only in the
  raw source object and are not duplicated in the pack.
- `group` is one of the six fixed v1 group names.
- `role` is the detailed classifier result, such as `entrypoint`,
  `service_impl`, `test`, `runtime_config`, or `view_page`.
- `classification_basis` is `anchor_kind`, `frontend_role`, `path_role`,
  `retrieval_summary`, or `fallback`.
- Every item ID appears in exactly one group and exactly once in
  `reading_order`.
- `items` stays in source order: all ranked results, followed by all evidence
  anchors. Grouping never mutates raw rank.

This normalized reference shape avoids repeating source snippets while keeping
the raw evidence available in the same response.

## Deterministic Grouping

Groups are always present in this order:

1. `entrypoints`
2. `implementations`
3. `related_types`
4. `tests`
5. `configs_docs`
6. `supporting`

Classification uses existing role helpers. It does not infer a new graph.

| classifier role | ContextPack group |
| --- | --- |
| frontend `route_config`, `view_page`, `layout_component` | `entrypoints` |
| frontend `service`, `utility`, `store`, `shared_component` | `implementations` |
| frontend `type_decl` | `related_types` |
| path `entrypoint`, `router`, `command`, `handler`, `view` | `entrypoints` |
| path `service_impl`, `executor`, `engine`, `middleware`, `storage`, `service`, `repository`, `source_adapter`, `state_store`, `composable`, `scheduler` | `implementations` |
| path `data_type`, `service_interface` | `related_types` |
| path `test` | `tests` |
| path `deployment_config`, `config_example`, `runtime_config`, `config`, `doc` | `configs_docs` |
| evidence anchor kind `readme`, `risks`, `pom`, `config`, or `document` | `configs_docs` |
| a remaining result whose file stem matches `RetrievalSummary.entry_points` | `entrypoints` |
| a remaining result whose file stem owns a `RetrievalSummary.implementation` name | `implementations` |
| a remaining result whose file stem matches `RetrievalSummary.related_types` | `related_types` |
| every remaining role, including generic source, component, generated output, lockfile, and unknown anchor kinds | `supporting` |

Classification precedence is:

1. known evidence-anchor kind for anchors;
2. generic `test`, config, and documentation path roles, so a frontend test or
   config cannot be mistaken for a page or service;
3. frontend-specific role when it is not `other`;
4. remaining non-generic path roles;
5. case-insensitive file-stem ownership in the existing retrieval summary;
6. fallback.

Summary ownership is deliberately narrow. A stem matches an entrypoint or
related-type name exactly. It owns an implementation name when the name equals
the stem or starts with `<stem>.`. This handles root-level files such as
`WorkspaceDto.java` without copying private filename heuristics from the ranking
module.

Tests and config/docs remain visible even if current ranking treats them as
secondary artifacts. Phase 2 reorganizes returned evidence; it does not promote
new candidates into the result set.

## Reading Order

Within a group, raw result order is preserved. Evidence anchors follow ranked
results in their group.

The default group order is the fixed order above. An explicit query target may
move its corresponding group to the front:

- test intent promotes `tests`;
- config, deployment, or documentation intent promotes `configs_docs`;
- endpoint or entrypoint intent promotes `entrypoints`;
- implementation intent promotes `implementations`.

When several groups are promoted, their relative order remains the fixed v1
group order. This avoids depending on unordered intent sets.

Only the group order changes. No score or raw rank changes, and an item is never
duplicated to satisfy multiple roles.

## Expected And Missing Evidence

Missing evidence must be conservative. The builder distinguishes **required**
groups from **recommended** groups.

### Required Groups

Explicit deterministic query intent takes precedence:

| explicit target intent | required group |
| --- | --- |
| entrypoint | `entrypoints` |
| implementation | `implementations` |
| UI/page/view | `entrypoints` |
| test | `tests` |
| config, deployment, or documentation | `configs_docs` |

When explicit intent provides no required group, a successful planner intent may
provide one:

| planner intent | required groups |
| --- | --- |
| `feature_lookup`, `data_flow`, `bug_trace` | `entrypoints`, `implementations` |
| `endpoint_lookup` | `entrypoints` |
| `symbol_lookup`, `unknown` | none |

Planner intent is a hint for completeness, not proof that a file has a role.

### Recommended Groups

- Feature, data-flow, and bug-trace packs recommend `related_types` and `tests`.
- Endpoint packs recommend `implementations` and `tests`.
- If an unknown-intent pack contains an entrypoint but no implementation, the
  implementation group is recommended.
- If an unknown-intent pack contains an implementation but no entrypoint, the
  entrypoint group is recommended.

No query receives a blanket config/doc requirement, and exact symbol queries do
not automatically report missing controllers, tests, or DTOs.

Each absent expected category produces one object:

```json
{
  "category": "implementations",
  "required": true,
  "reason": "feature lookup requires an implementation, but none is present in the bounded result set"
}
```

Structural categories use the six group names. The special category `results`
appears only for an empty pack and means that no raw result or evidence anchor
was returned. The reason always says `bounded result set`. It must not claim
that the repository lacks the evidence.

## Next Queries

`next_queries` are deterministic search suggestions, not asserted facts.

Rules:

- Generate at most three queries.
- Generate required-gap queries before recommended-gap queries.
- Seed a query from trusted returned evidence or user input in this order:
  1. the most relevant complementary `RetrievalSummary` name;
  2. the highest-ranked result file stem;
  3. the original query.
- Append only fixed role terms:
  - entrypoint: `controller route entrypoint`;
  - implementation: `service implementation`;
  - related types: `dto model type`;
  - tests: `test`;
  - configs/docs: `config documentation`.
- Normalize whitespace, deduplicate case-insensitively, and cap each query at 160
  Unicode code points.
- Every suggestion includes a `purpose` and a reason tied to one missing
  category.
- Do not use a model, invent a symbol, or expose discarded planner hints.
- The special empty-pack `results` category does not generate an automatic
  query: appending a structural role to a zero-evidence query would guess the
  user's intent.
- If no non-empty safe seed exists, omit the suggestion. An empty
  `next_queries` list is valid.

The existing `followup_keywords` field remains unchanged and available to users
who want raw terms rather than composed queries.

## Readiness Confidence

`confidence` measures whether the returned structure supports the next reading
step. It is not a calibrated probability that the retrieval result is correct.

Levels are:

- `none`: the pack is empty;
- `low`: at least one required evidence group is missing;
- `medium`: every required group is present, but recommended evidence is missing
  or the pack has no protected original-query evidence;
- `high`: every required and recommended group is present and at least one
  result has protected original direct evidence; an exact symbol or endpoint
  lookup may also be high with one protected direct result.

Protected original direct evidence is read from the existing public numeric
diagnostic `score_parts.evidence_priority == 0`. Phase 2 does not copy ranking
thresholds or reclassify evidence independently. The exact-lookup exception is
deterministic: `infer_identifier_intent()` must find an identifier or file hint,
or explicit/planner intent must identify an endpoint lookup.

The response includes short deterministic reasons. It does not include a
floating-point confidence score.

## Budget Contract

The budget reports effective inputs and actual returned content:

- `max_results`: effective `retrieval.final_top_k`, including an MCP per-call
  override;
- `included_results`: length of `results`;
- `included_evidence_anchors`: length of `evidence_anchors`;
- `content_bytes`: sum of UTF-8 bytes in all returned result and anchor content;
- `context_before_lines` and `context_after_lines`: effective context window;
- `full_file`: whether full-file mode was requested;
- `max_full_file_bytes`: configured per-file full-content cap.

The pack does not emit a `truncated` boolean in v1. `QueryBundle` does not retain
the pre-limit result count, so such a field would pretend to know whether the
limit excluded relevant evidence. Phase 3 trace data can add honest pre/post
stage counts later.

Pack construction adds no separate item budget. Every returned result and anchor
is represented exactly once.

## Markdown Output

`cst context` renders:

1. query, pack status, and confidence;
2. `Read First`, following `reading_order` and displaying group/role, location,
   existing ranking reasons, and source snippet;
3. `Missing Evidence` with required/recommended labels;
4. `Next Queries` with purposes;
5. `Budget`;
6. planner status when already present in the bundle.

The Markdown formatter dereferences item IDs against the raw arrays. It must
fail tests on an invalid reference rather than silently omit an item. Users who
need raw rank order can continue using `cst query` or inspect the context JSON.

## Error And Empty-State Behavior

- Repository and index errors match the existing query surfaces.
- A pack-building programming or contract error is returned by MCP as
  `context_failed`; it is not rewritten as a successful partial pack.
- Planner or embedding failures keep their existing query fallback behavior.
  The packer receives the resulting bundle and does not create a second fallback
  path.
- A valid retrieval with no results and no evidence anchors returns `ok: true`
  and an `empty` pack. Anchors alone still form a non-empty pack.
- An empty pack has no items, no reading order, `confidence.level = none`, and a
  required missing-evidence record with `category = results`.
- `next_queries` may be empty when there is no evidence-derived safe seed.

## MCP Feedback And Privacy

`context_search_context` appends the same bounded feedback event style as the
existing query tool, with `tool = context_search_context`.

The event may add:

- pack status and confidence level;
- item and group counts;
- required/recommended missing-evidence category names;
- next-query count;
- budget counts and content-byte total.

It must not add source snippets, file paths, item IDs, composed next-query text,
planner rewrite text, semantic variant text, or discarded hints. Existing raw
query logging and feedback-summary privacy behavior remain unchanged.

## Quality Catalog Integration

Phase 2 activates the previously reserved case mode.

### Mode Validation

`QualityCase.mode` accepts exactly:

- `results`;
- `context_pack`.

Unknown values fail fixture validation. Existing cases default to `results` and
keep current evaluation behavior.

### Context Expectations

A `context_pack` case may add:

```json
{
  "mode": "context_pack",
  "expected_context_groups": {
    "entrypoints": [{"path": "src/WorkspaceController.java"}],
    "implementations": [{"path": "src/WorkspaceServiceImpl.java"}],
    "related_types": [{"path": "src/WorkspaceDto.java"}]
  },
  "expected_pack_status": "ready",
  "minimum_context_confidence": "medium"
}
```

Rules:

- group names must be one of the six v1 names;
- group matchers reuse existing path/glob/contains matcher semantics;
- pack status must be `empty`, `partial`, or `ready`;
- confidence ordering is `none < low < medium < high`;
- context-only expectation fields are rejected on `results` cases;
- existing raw-result expectations may remain on a `context_pack` case and are
  evaluated against the unchanged raw results.

### Metrics

Each context case records:

- `context_expected_count`;
- `context_matched_count`;
- `context_completeness`, defined as matched expected group/path pairs divided by
  expected pairs;
- `context_group_count`, counting non-empty groups only;
- `required_missing_count`;
- `recommended_missing_count`;
- `next_query_count`;
- `context_content_bytes`;
- pack status and confidence level as case metadata.

No expected pairs means `context_completeness = null`, not `1.0`.

### Deterministic P2 Profile

Add a `p2_context_pack` profile over committed snapshots. It remains offline,
planner-disabled, and deterministic. Required cases cover at least:

- a Java/Spring flow with entrypoint, implementation, and related type groups;
- a frontend feature with a page/route and supporting service/store/type roles;
- an explicit test query that promotes the tests group;
- a config or documentation query that places evidence in `configs_docs`;
- an exact symbol query that does not invent flow-oriented required gaps.

Unit tests, rather than the profile, cover synthetic empty and partial packs.
Phase 2 does not add a new model-backed acceptance dependency. If implementation
changes retrieval behavior despite this design, that is a design checkpoint and
requires rerunning the applicable Phase 1 gates.

## Testing Strategy

### Builder Unit Tests

- Every result and anchor produces one item and one valid reference.
- IDs, item order, group order, and reading order are deterministic.
- Frontend, generic path, retrieval-summary, anchor, and fallback role mappings
  follow the table.
- Explicit test/config/entrypoint/implementation intents promote only group
  order, not raw result order.
- Required and recommended gaps are inferred conservatively.
- Exact symbol queries do not receive unrelated required gaps.
- Next queries are evidence-derived, deduplicated, bounded to three, and capped
  at 160 code points.
- Confidence levels and reasons follow the structural rules.
- Budget counts and UTF-8 byte totals are exact.
- Empty bundles produce a valid empty pack.

### Contract Tests

- Existing query JSON and MCP payloads retain their exact keys and values.
- For the same deterministic bundle, context output preserves the same raw
  `results`, `evidence_anchors`, query variants, semantic matches, and planner
  diagnostics as query output.
- Item references resolve to those raw arrays.
- CLI JSON and MCP serialize identical `context_pack` objects.
- Markdown renders every reading-order item exactly once.
- Schema version and enum values are locked by tests.

### Invocation Tests

- One context request calls `query_repository()` exactly once.
- One context request calls `build_context_pack()` exactly once.
- Pack construction performs no store, vector, filesystem, network, embedding,
  or planner invocation.
- Missing index and invalid `final_top_k` errors match the declared envelopes.
- MCP registration exposes both query and context operations.

### Quality And Privacy Tests

- `p2_context_pack` executes and passes every required case.
- Existing `ci` raw-result cases still pass.
- Context completeness aggregates are stable and correctly exclude null cases.
- Feedback contains counts and category names but no source content, paths, item
  IDs, next-query text, or semantic/planner variant text.

## Acceptance Criteria

Phase 2 is complete only when all of the following are true:

1. `cst context` and `context_search_context` expose ContextPack schema v1.
2. `cst query` and `context_search_query` retain their existing response and
   ranking contracts.
3. Every raw result and anchor appears exactly once in pack items, one group, and
   reading order, with valid response-local references.
4. Group classification, group promotion, missing evidence, next queries,
   confidence, and budget output are deterministic.
5. Context construction performs no additional retrieval or model work.
6. A valid query with no result or anchor returns an explicit empty pack rather
   than an error or fabricated next query.
7. The new deterministic `p2_context_pack` profile executes all required cases,
   all per-case expectations pass, and aggregate context completeness is
   reported.
8. The existing full test suite and `ci` quality profile pass without raw-result
   regressions.
9. Context feedback remains bounded and satisfies the privacy contract.
10. README, retrieval-quality documentation, and the roadmap describe the two
    public operations consistently. The roadmap marks Phase 2 complete only
    after these gates pass.

## Likely Change Surface

Expected changes are intentionally bounded:

- Create `src/context_search_tool/context_pack.py`
  - define the typed ContextPack models;
  - implement pure classification, gap, query, confidence, budget, and payload
    helpers.
- Modify `src/context_search_tool/cli.py`
  - extract only the small shared query/config path needed by both commands;
  - add `cst context`.
- Modify `src/context_search_tool/formatters.py`
  - add ContextPack JSON and Markdown formatting.
- Modify `src/context_search_tool/mcp_tools.py`
  - add `context_search_context_tool` and bounded feedback metadata.
- Modify `src/context_search_tool/mcp_server.py`
  - register `context_search_context`.
- Modify `src/context_search_tool/quality/cases.py`
  - validate `context_pack` mode and its expectations.
- Modify `src/context_search_tool/quality/runner.py` and focused quality helpers
  - build/evaluate packs only for context cases;
  - emit context case metrics.
- Modify `tests/fixtures/retrieval_quality/queries.json`
  - add the deterministic P2 profile and required cases.
- Add focused tests for the builder, formatters, CLI, MCP, quality schema,
  runner, aggregation, and feedback.
- Modify `README.md`, `docs/retrieval-quality.md`, and the roadmap after verified
  acceptance.

`retrieval.py`, ranking functions, embedding providers, vector storage, index
schema, and framework plugins are not expected to change. If implementation
requires one of those changes, stop for a design review instead of expanding
scope silently.

## Risks And Mitigations

### Group Labels Overstate Semantics

Path roles are heuristics. Expose the detailed role and classification basis,
keep raw evidence, and use a `supporting` fallback rather than forcing every file
into a stronger category.

### A Clean Pack Hides Raw Rank

Keep raw arrays in the context response and preserve response-local references.
The old query operations remain available for direct rank inspection.

### Missing Evidence Sounds Like Repository Absence

Every message is explicitly scoped to the bounded result set. Only explicit or
well-defined planner intent creates required groups.

### Follow-Up Queries Hallucinate Symbols

Use returned summary names or file stems plus fixed role terms. Never use a new
model call or discarded planner hints, and omit unsafe suggestions.

### Confidence Is Misread As Relevance Probability

Use named readiness levels, deterministic reasons, and no floating-point value.
Document that confidence describes structural readiness only.

### New Surface Duplicates Query Logic

Share the small repository/config/query invocation path and the ContextPack
builder. Do not implement context by serializing and reparsing a query response.

### P2 Accidentally Becomes P3 Or P4

The builder receives only final output and performs no I/O. Trace fields,
pre-limit counts, extra probes, graph traversal, and exploration budgets require
later designs.

## Handoff Boundary

This document defines Phase 2 only. After written review approval, the next
artifact is a separate test-first implementation plan. That plan may implement
the new context surface and deterministic packer, but it must not begin
RetrievalTrace, retrieval-core decomposition, or controlled multi-round
exploration.
