# P2 Context Pack Output Design

Date: 2026-07-14
Status: Approved; written review complete
Repository: `/Users/flobby/Documents/context-seatch-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor: `docs/superpowers/specs/2026-07-13-p1-query-understanding-closure-design.md`
Implementation plan: `docs/superpowers/plans/2026-07-14-p2-context-pack-output.md`

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
    "prompt_version": "qwen-query-planner-v2",
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
        "role": "summary_related_type",
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
        "reason": "recommended evidence for tests is missing from the bounded result set"
      }
    ],
    "next_queries": [
      {
        "query": "WorkspaceServiceImpl test",
        "purpose": "find_tests",
        "reason": "recommended evidence for tests is missing from the bounded result set"
      }
    ],
    "confidence": {
      "level": "medium",
      "reasons": [
        "all required evidence groups are present",
        "recommended evidence is missing: tests",
        "protected original direct evidence is present"
      ]
    },
    "budget": {
      "max_results": 12,
      "max_evidence_anchors": 4,
      "max_items": 16,
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
- `role` is the exact value selected by the closed classification table below;
  it is not an implementation-defined label.
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

Classification uses existing role helpers. It does not infer a new graph. The
selected row fixes all three public classification fields:

| selected condition | `group` | emitted `role` | `classification_basis` |
| --- | --- | --- | --- |
| evidence anchor kind `readme` | `configs_docs` | `readme` | `anchor_kind` |
| evidence anchor kind `risks` | `configs_docs` | `risks` | `anchor_kind` |
| evidence anchor kind `pom` | `configs_docs` | `pom` | `anchor_kind` |
| path role `test` | `tests` | `test` | `path_role` |
| path role `deployment_config`, `config_example`, `runtime_config`, `config`, or `doc` | `configs_docs` | the exact path-role value | `path_role` |
| frontend role `route_config`, `view_page`, or `layout_component` | `entrypoints` | the exact frontend-role value | `frontend_role` |
| frontend role `service`, `utility`, `store`, or `shared_component` | `implementations` | the exact frontend-role value | `frontend_role` |
| frontend role `type_decl` | `related_types` | `type_decl` | `frontend_role` |
| frontend role `lockfile` or `scratch_temp` | `supporting` | the exact frontend-role value | `frontend_role` |
| path role `entrypoint`, `router`, `command`, `handler`, or `view` | `entrypoints` | the exact path-role value | `path_role` |
| path role `service_impl`, `executor`, `engine`, `middleware`, `storage`, `service`, `repository`, `source_adapter`, `state_store`, `composable`, or `scheduler` | `implementations` | the exact path-role value | `path_role` |
| path role `data_type` or `service_interface` | `related_types` | the exact path-role value | `path_role` |
| path role `generated_output` or `lockfile` | `supporting` | the exact path-role value | `path_role` |
| eligible result matched by `RetrievalSummary.entry_points` | `entrypoints` | `summary_entrypoint` | `retrieval_summary` |
| eligible result matched by `RetrievalSummary.implementation` | `implementations` | `summary_implementation` | `retrieval_summary` |
| eligible result matched by `RetrievalSummary.related_types` | `related_types` | `summary_related_type` | `retrieval_summary` |
| remaining result with path role `source` or `component` | `supporting` | the exact path-role value | `fallback` |
| anchor with any other or empty kind | `supporting` | `evidence_anchor` | `fallback` |

Classification precedence is:

1. one of the three known evidence-anchor kinds for anchors; every other anchor
   takes the anchor fallback row immediately;
2. generic `test`, config, and documentation path roles, so a frontend test or
   config cannot be mistaken for a page or service;
3. frontend-specific role when it is not `other`;
4. remaining path roles except `source` and `component`;
5. case-insensitive file-stem ownership in the existing retrieval summary, only
   for results whose path role is `source` or `component`;
6. result fallback.

Summary ownership is deliberately narrow. A stem matches an entrypoint or
related-type name exactly. It owns an implementation name when the name equals
the stem or starts with `<stem>.`. This handles root-level files such as
`WorkspaceDto.java` without copying private filename heuristics from the ranking
module. If a stem matches more than one summary list, evaluate
`entry_points`, `implementation`, then `related_types`; the first match wins.
The role values `related_type`, `implementation`, and arbitrary anchor-kind
strings are therefore not valid v1 outputs. A result classifier value not
covered by the table raises `ContextPackError`; adding a classifier role requires
an explicit ContextPack contract update rather than silently assigning a group.

Tests and config/docs remain visible even if current ranking treats them as
secondary artifacts. Phase 2 reorganizes returned evidence; it does not promote
new candidates into the result set.

## Reading Order

Within a group, raw result order is preserved. Evidence anchors follow ranked
results in their group.

The default group order is the fixed order above. Promotion reuses the explicit
required-group union defined below; every group in that union moves to the front.
Planner-only requirements do not promote groups. This makes page/view hints
promote `entrypoints`, component/store hints promote `implementations`, type
hints promote `related_types`, and artifact-requesting test/config/doc intents
promote their artifact group. A config logic query with `wants_artifact = false`
does not promote `configs_docs`.

When several groups are promoted, their relative order remains the fixed v1
group order. This avoids depending on unordered intent sets.

Only the group order changes. No score or raw rank changes, and an item is never
duplicated to satisfy multiple roles.

## Expected And Missing Evidence

Missing evidence must be conservative. The builder distinguishes **required**
groups from **recommended** groups.

### Required Groups

The builder derives two existing intent views from `QueryBundle.query`:

- call `infer_query_intent()` with the raw query and
  `QueryBundle.query.split()` surface tokens, without camel-case or snake-case
  expansion;
- call `infer_identifier_intent()` with the raw query and the existing
  `tokenize_query()` output.

This keeps `WorkspaceController` available as an identifier with an entrypoint
role hint without treating its internal `Controller` segment as an explicit
endpoint word. Neither call may use `QueryBundle.expanded_tokens`, rewritten
queries, or planner hints: those values may contain generated role terms such as
`controller`, `service`, or `dto`. No new intent classifier is introduced.
Explicit required groups are the union of these rules:

| existing intent evidence | condition | required group added |
| --- | --- | --- |
| `QueryIntent.target_roles` | contains `entrypoint` | `entrypoints` |
| `QueryIntent.target_roles` | contains `implementation` | `implementations` |
| `IdentifierIntent.role_hints` | contains `entrypoint`, `router`, `command`, or `view` | `entrypoints` |
| `IdentifierIntent.role_hints` | contains `state_store`, `composable`, `service`, `handler`, `middleware`, `repository`, `source_adapter`, `storage`, `component`, or `engine` | `implementations` |
| `IdentifierIntent.role_hints` | contains `data_type` | `related_types` |
| `QueryIntent.target_roles` | contains `test` and `wants_artifact` is true | `tests` |
| `QueryIntent.target_roles` | intersects `config`, `deploy`, or `doc` and `wants_artifact` is true | `configs_docs` |

`QueryIntent`'s coarse `ui` role never adds a group by itself. Existing
identifier role hints distinguish page/view/route terms from component/store
terms; an ambiguous term such as `form` adds no required group. Likewise,
configuration words used in a logic query do not require `configs_docs` unless
`wants_artifact` is true. Thus `Pinia store component` requires
`implementations`, while `configuration page save logic` requires
`entrypoints` and `implementations` but not `configs_docs`.

When explicit intent provides no required group, a successful planner intent may
provide one:

| planner intent | required groups |
| --- | --- |
| `feature_lookup`, `data_flow`, `bug_trace` | `entrypoints`, `implementations` |
| `endpoint_lookup` | `entrypoints` |
| `symbol_lookup`, `unknown` | none |

Planner intent is a hint for completeness, not proof that a file has a role. If
the explicit union is non-empty, planner intent does not add further required
groups. Multiple groups are deduplicated and retained in the fixed v1 group
order. Here and below, a successful planner means `QueryPlan.status == "ok"`;
disabled and failed plans contribute no planner intent. Identifiers and file
hints do not create required groups merely by being present; only their listed
`role_hints` do.

### Recommended Groups

- A successful planner intent of `feature_lookup`, `data_flow`, or `bug_trace`
  recommends `related_types` and `tests`.
- A successful `endpoint_lookup`, or surface `QueryIntent.target_roles`
  containing `entrypoint`, recommends `implementations` and `tests`.
- When there is no successful non-unknown planner intent and the explicit
  required set is empty, a pack with an entrypoint but no implementation
  recommends `implementations`; the inverse recommends `entrypoints`.
- Remove every required group from the recommended set, deduplicate, and retain
  the fixed v1 group order.

No query receives a blanket config/doc requirement, and exact symbol queries do
not automatically report missing controllers, tests, or DTOs. `supporting` is
never required or recommended, so it never appears as a structural missing
category or next-query purpose.

Each absent expected category produces one object:

```json
{
  "category": "implementations",
  "required": true,
  "reason": "required evidence for implementations is missing from the bounded result set"
}
```

Structural categories use the six group names. The special category `results`
appears only for an empty pack and means that no raw result or evidence anchor
was returned. It is the sole missing-evidence object for an empty pack and uses
the exact reason `no result or evidence anchor is present in the bounded result
set`.

For a non-empty pack, emit absent required groups first, then absent recommended
groups. Each partition follows the fixed v1 group order. A group can appear at
most once. Reasons use exactly one of these templates:

- `required evidence for <category> is missing from the bounded result set`;
- `recommended evidence for <category> is missing from the bounded result set`.

These templates must not claim that the repository lacks the evidence.

## Next Queries

`next_queries` are deterministic search suggestions, not asserted facts.

Rules:

- Iterate non-`results` `missing_evidence` records in their already-defined
  order and generate at most one suggestion per record, stopping after three
  unique suggestions.
- For each category, inspect summary lists in the table's left-to-right order.
  Take the first non-empty string from the first non-empty list. Do not score or
  compare summary names.

| missing category | summary-list priority | `purpose` | fixed role terms |
| --- | --- | --- | --- |
| `entrypoints` | `implementation`, `related_types`, `entry_points` | `find_entrypoints` | `controller route entrypoint` |
| `implementations` | `entry_points`, `related_types`, `implementation` | `find_implementations` | `service implementation` |
| `related_types` | `implementation`, `entry_points`, `related_types` | `find_related_types` | `dto model type` |
| `tests` | `implementation`, `entry_points`, `related_types` | `find_tests` | `test` |
| `configs_docs` | `entry_points`, `implementation`, `related_types` | `find_configs_docs` | `config documentation` |

- If all listed summary lists are empty, use the file stem of `results[0]`. If
  there is no ranked result, use the original query. Evidence anchors are not
  seeds because their kinds do not provide a subject name.
- Normalize the selected seed by trimming it and collapsing every Unicode
  whitespace run to one ASCII space. A seed that is then empty is unsafe, so
  omit that suggestion.
- Compose `<seed> <fixed role terms>`. If this exceeds 160 Unicode code points,
  truncate only the seed to leave room for one separating space and the complete
  fixed role terms, then trim the shortened seed before composition. The role
  terms are never truncated.
- Deduplicate composed queries with Unicode `casefold()` after whitespace
  normalization. If a query duplicates an earlier suggestion, omit it and move
  to the next missing category; do not try a second seed for the same category.
- `purpose` is the exact table value. `reason` is copied byte-for-byte from the
  corresponding `missing_evidence.reason`.
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
- `medium`: every required group is present and either recommended evidence is
  missing or the pack has no protected original direct evidence;
- `high`: every required and recommended group is present and at least one
  result has protected original direct evidence.

Protected original direct evidence is read from the existing public numeric
diagnostic `score_parts.evidence_priority == 0`. Phase 2 does not copy ranking
thresholds or reclassify evidence independently. A missing or nonzero diagnostic
does not count as protected evidence.

There is no exact-lookup exception. An exact symbol query naturally reaches
`high` when it has protected direct evidence and no expected group is missing.
An endpoint lookup with a missing recommended implementation or test remains
`medium`, even when its direct endpoint result is protected.

Confidence reasons are also deterministic. An empty pack has the single reason
`no result or evidence anchor is present`. A non-empty pack emits reasons in this
order:

1. `required evidence is missing: <categories>` or
   `all required evidence groups are present`;
2. when the recommended set is non-empty, either
   `recommended evidence is missing: <categories>` or
   `all recommended evidence groups are present`;
3. `protected original direct evidence is present` or
   `protected original direct evidence is absent`.

Category lists are joined with `, ` in fixed v1 group order. The response does
not include a floating-point confidence score.

## Budget Contract

The budget reports effective inputs and actual returned content:

- `max_results`: effective `retrieval.final_top_k`, including an MCP per-call
  override; this limits ranked results only;
- `max_evidence_anchors`: the effective independent evidence-anchor limit;
- `max_items`: `max_results + max_evidence_anchors`, the maximum number of pack
  items for this request;
- `included_results`: length of `results`;
- `included_evidence_anchors`: length of `evidence_anchors`;
- `content_bytes`: sum of UTF-8 bytes in all returned result and anchor content;
- `context_before_lines` and `context_after_lines`: effective context window;
- `full_file`: whether full-file mode was requested;
- `max_full_file_bytes`: configured per-file full-content cap.

The retrieval path and context invocation use one shared public pure helper,
`evidence_anchor_top_k(max_results)`, for `max_evidence_anchors`. The invocation
passes the resulting value to `build_context_pack()` with the other effective
options; the builder does not copy the formula or import the retrieval pipeline.
The helper's Phase 2 behavior is the existing formula
`max(1, min(5, max_results // 3))` for the already-validated positive
`max_results`. Exposing it changes no ranking or limit behavior.

The pack does not emit a `truncated` boolean in v1. `QueryBundle` does not retain
the pre-limit result count, so such a field would pretend to know whether the
limit excluded relevant evidence. Phase 3 trace data can add honest pre/post
stage counts later.

Pack construction adds no third item budget. The separate result and anchor caps
define `max_items`, and every returned result and anchor is represented exactly
once. The builder validates `included_results <= max_results` and
`included_evidence_anchors <= max_evidence_anchors`; a bundle that violates an
effective limit is a contract failure rather than a budget object whose reported
maximum is already exceeded.

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
- Planner or embedding failures keep their existing query fallback behavior.
  The packer receives the resulting bundle and does not create a second fallback
  path.
- A valid retrieval with no results and no evidence anchors returns `ok: true`
  and an `empty` pack. Anchors alone still form a non-empty pack.
- An empty pack has no items, no reading order, `confidence.level = none`, and a
  required missing-evidence record with `category = results`.
- `next_queries` may be empty when there is no evidence-derived safe seed.

`context_pack.py` defines `ContextPackError` for known pack-contract failures,
including duplicate or unresolved item references, an invalid classification
value, and failure to materialize the typed pack as JSON-native values. The
public exception message is respectively one of these fixed strings: `duplicate
ContextPack item id`, `invalid ContextPack item reference`, `invalid ContextPack
classification`, `ContextPack budget exceeded`, or `ContextPack contains a
non-JSON value`. It contains no file path, source content, or raw exception text.
The context operation has two explicit exception phases:

1. repository resolution, config loading, argument validation,
   `query_repository()`, and construction of the unchanged raw query payload use
   the existing query error behavior;
2. `build_context_pack()`, item-reference validation, context payload
   materialization, and CLI ContextPack formatting/encoding form the pack phase.

For MCP, a `ContextPackError` in phase 2 returns the normal error envelope with
`code = context_failed` and the bounded contract message. Any other `Exception`
from phase 2 also returns `context_failed`, but with the fixed message `Context
pack construction failed`; internal exception text is not exposed. Neither case
is returned as `query_failed`, converted into a successful partial pack, or
allowed to escape the tool function. `BaseException` subclasses such as process
interrupts are not caught.

For the CLI, either phase-2 failure writes `Error: context_failed: <message>` to
stderr and exits with status 1. This remains true under `--json`, matching the
existing query command's stderr-and-exit behavior rather than inventing a CLI
JSON error envelope. Invalid Markdown dereferences and JSON encoding failures are
inside this boundary. MCP framework transport failures after the tool has
returned are outside it; contract tests must prove that the returned payload can
be encoded with `json.dumps()` so normal transport cannot encounter a pack value
type error.

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

The config/documentation case has a fixed committed source. Add
`tests/fixtures/context-pack-docs/README.md` with this minimal realistic
content:

```markdown
# Program Tool Developer Setup

Install dependencies and run the developer utilities locally.
```

Add a repository entry with `repo_key = context_pack_docs`, this snapshot path,
and only the `p2_context_pack` profile. Its required case uses query `Program
Tool Developer Setup documentation`. It must match `README.md` in
`configs_docs` and have no required `configs_docs` gap. A focused builder or
runner integration test also locks the resulting item role to `readme`; the
quality schema does not gain a role-specific matcher. Do not reuse the existing
`program_tool/package.json`: it is classified as generic `source` and modifying
that shared snapshot could change existing raw query anchors. The isolated
README is already recognized as evidence-anchor kind `readme`, so no classifier
or anchor-kind expansion is required.

The committed README is 94 UTF-8 bytes on disk because it has a final newline.
The default non-full-file retrieval path passes `splitlines()` output through
the existing context-window join, so the returned anchor content has no final
newline and is 93 UTF-8 bytes. `context_content_bytes` and the pack budget count
returned content, not source-file size; the deterministic docs case therefore
locks 93 bytes without changing retrieval behavior.

Unit tests, rather than the profile, cover synthetic empty and partial packs.
Phase 2 does not add a new model-backed acceptance dependency. If implementation
changes retrieval behavior despite this design, that is a design checkpoint and
requires rerunning the applicable Phase 1 gates.

## Testing Strategy

### Builder Unit Tests

- Every result and anchor produces one item and one valid reference.
- IDs, item order, group order, and reading order are deterministic.
- Frontend, generic path, retrieval-summary, anchor, and fallback role mappings
  emit the table's exact group, role, and basis values, including
  `summary_related_type` rather than `related_type`.
- Explicit test/config/entrypoint/implementation intents promote only group
  order, not raw result order.
- A component/store query requires `implementations` rather than `entrypoints`;
  configuration save logic with `wants_artifact = false` does not require
  `configs_docs`; page/view and explicit config-file cases exercise the opposite
  branches.
- Planner-added expanded tokens such as `controller`, `service`, and `dto` do
  not become explicit required groups.
- Required and recommended gaps are inferred conservatively, deduplicated in
  fixed order, and use the exact reason templates.
- Exact symbols such as `WorkspaceController` may require their own hinted group
  but do not receive implementation/test recommendations merely because the
  identifier contains `Controller`; a standalone `controller` term exercises
  the explicit-target branch.
- Next queries exercise every category's summary-list priority, result-stem and
  original-query fallback, duplicate omission, purpose value, fixed reason, and
  suffix-preserving 160-code-point cap.
- Confidence levels and ordered reasons follow the structural rules; in
  particular, an endpoint with protected direct evidence and a recommended gap
  remains `medium`.
- Budget counts, `max_evidence_anchors`, `max_items`, and UTF-8 byte totals are
  exact for multiple `final_top_k` values, and a synthetic over-limit bundle
  raises `ContextPackError`.
- Empty bundles produce a valid empty pack.

### Contract Tests

- Existing query JSON and MCP payloads retain their exact keys and values.
- For the same deterministic bundle, context output preserves the same raw
  `results`, `evidence_anchors`, query variants, semantic matches, and planner
  diagnostics as query output.
- Item references resolve to those raw arrays.
- CLI JSON and MCP serialize identical `context_pack` objects.
- The MCP payload is accepted by `json.dumps()` without a custom encoder.
- Markdown renders every reading-order item exactly once.
- Schema version, role, basis, purpose, status, confidence, and group values are
  locked by tests.

### Invocation Tests

- One context request calls `query_repository()` exactly once.
- One context request calls `build_context_pack()` exactly once.
- Pack construction performs no store, vector, filesystem, network, embedding,
  or planner invocation.
- Missing index and invalid `final_top_k` errors match the declared envelopes.
- A builder `ValueError`, explicit `ContextPackError`, unexpected `Exception`,
  invalid Markdown reference, and CLI JSON encoding failure stay inside the pack
  boundary and produce the declared MCP/CLI behavior.
- MCP registration exposes both query and context operations.

### Quality And Privacy Tests

- `p2_context_pack` executes and passes every required case.
- The isolated committed `context-pack-docs/README.md` case lands in
  `configs_docs` without changing a snapshot used by existing raw-result cases.
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
11. Known and unexpected pack-phase failures follow the declared
    `context_failed` and CLI exit contracts without leaking internal exception
    text or returning a fabricated partial pack.

## Likely Change Surface

Expected changes are intentionally bounded:

- Create `src/context_search_tool/context_pack.py`
  - define the typed ContextPack models;
  - define `ContextPackError` and validate references and JSON-native values;
  - implement pure classification, gap, query, confidence, budget, and payload
    helpers.
- Modify `src/context_search_tool/retrieval.py`
  - expose the existing `_evidence_anchor_top_k` calculation as the public pure
    `evidence_anchor_top_k` helper and use it from retrieval and the context
    invocation before passing the limit to the builder;
  - do not change its formula, candidate selection, ranking, or result limits.
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
- Add `tests/fixtures/context-pack-docs/README.md`
  - provide the exact committed documentation anchor for the declared
    config/documentation case in a P2-only snapshot.
- Add focused tests for the builder, formatters, CLI, MCP, quality schema,
  runner, aggregation, and feedback.
- Modify `README.md`, `docs/retrieval-quality.md`, and the roadmap after verified
  acceptance.

Apart from exposing the unchanged evidence-anchor limit helper, retrieval
behavior, ranking functions, embedding providers, vector storage, index schema,
and framework plugins are not expected to change. Any other change in those
areas requires a design review instead of silent scope expansion.

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
