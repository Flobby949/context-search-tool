# P2.1 ContextPack v2 Agent-First Hardening Design

Date: 2026-07-15
Status: Approved; written review complete
Implementation plan: `docs/superpowers/plans/2026-07-15-p2-context-pack-v2-hardening.md`
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Predecessor: `docs/superpowers/specs/2026-07-14-p2-context-pack-output-design.md`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

## Summary

P2.1 replaces the reference-oriented ContextPack v1 response with an agent-first
ContextPack v2. The new `context` operation returns a compact, self-contained,
grouped reading set whose source excerpts are selected under a hard byte budget.
It evaluates concrete evidence needs instead of treating any non-empty group as
proof that the user's request is complete, and it creates follow-up queries only
from grounded subjects or the original query.

This is an intentional breaking change. There are no known consumers of the v1
context response, so preserving its raw-result duplication and local-reference
contract would make the product worse without providing migration value. The raw
`query` operation remains available for callers that need the complete ranked
result payload.

P2.1 remains a single-retrieval feature. It may preserve enough internal span
provenance to choose useful excerpts, but it does not add controlled multi-round
retrieval, graph traversal, or a full RetrievalTrace. Those remain later roadmap
work.

## Motivation And Fresh Evidence

The deterministic v1 profile and contract tests pass, but a fresh real-project
run against `spring-projects/spring-petclinic` at commit
`51045d1648dad955df586150c1a1a6e22ef400c2` exposed product-quality gaps that the
small committed fixtures do not cover.

Four fixed queries were run with a 12-result limit:

1. `owner registration form validation flow`
2. `OwnerController tests for owner registration validation`
3. `宠物主人详情页如何加载宠物和就诊记录`
4. `MySQL PostgreSQL database profile configuration and integration tests`

The manually verified critical-file coverage was:

| system | critical files found | coverage | mean query latency |
| --- | ---: | ---: | ---: |
| CST hash | 11/21 | 52.4% | 452.7 ms |
| CST BGE-M3 plus planner | 13/21 | 61.9% | 2840.4 ms |
| fast-context, three turns | 19/21 | 90.5% | 11590.8 ms |

P2.1 does not claim that packaging alone closes the retrieval-quality gap. The
comparison matters because a context pack must be honest about the evidence it
actually received and must not amplify weak retrieval into false readiness.

The observed v1 failures were:

- Spring `application-*.properties` results were placed in `supporting` rather
  than `configs_docs`.
- Java domain types such as `Owner`, `Pet`, and `Visit` often fell back to
  `supporting` when they were not located under a conventional `model` or `dto`
  directory.
- Spring Data interfaces named `*Repository.java` depended on retrieval summary
  inference instead of the shared artifact-role classifier.
- Thymeleaf files under `src/main/resources/templates` were not recognized as
  views.
- A config request could be marked `ready` because generic README or POM anchors
  made `configs_docs` non-empty even when the requested PostgreSQL properties
  file was absent.
- A Chinese owner-details query produced the unrelated follow-up query
  `GET /oups service implementation` because v1 selected the first non-empty
  retrieval-summary value without checking its relation to the user's request.
- One response included 148,433 bytes of source content, including a 3,132-line
  CSS span, even though ContextPack is intended to be a compact reading set.

## Root Causes

The issues come from five separate but connected design limits.

### Artifact Roles Are Too Path-Literal

`classify_path_role()` recognizes a limited set of config suffixes and directory
names. `.properties` is not an artifact-config suffix, Spring profile filenames
have no dedicated rule, Java domain annotations are ignored, `Repository` is not
a recognized class suffix, and `templates` is not a view directory.

Because the same role classifier contributes to retrieval reranking and context
grouping, context-only patches would create two inconsistent interpretations of
the same file. P2.1 therefore improves the shared classifier and protects the
change with existing raw-result quality profiles.

### V1 References Raw Arrays Instead Of Owning Excerpts

V1 requires every raw result and evidence anchor to appear exactly once as a
response-local reference. The context response also retains the full raw arrays.
The builder can count bytes but cannot reduce them without violating its defining
invariant. A hard payload budget is therefore impossible without changing the
schema.

### Readiness Checks Group Occupancy, Not Requested Evidence

V1 infers required groups, then treats any item in a required group as satisfying
the need. It cannot distinguish `application-mysql.properties` from `README.md`
when both are considered config or documentation evidence. Readiness is
structurally consistent with v1 but too weak for agent decisions.

### Follow-Up Seeds Trust Unscoped Summaries

V1 chooses the first value in a fixed retrieval-summary field order. Summary
values may describe a high-ranked but unrelated result. They are not scoped to a
specific missing need and are not required to overlap trusted query intent.

### Deterministic Fixtures Do Not Exercise Real Repository Shape

The offline P2 profile proves the declared contract against small controlled
snapshots. It does not protect Spring resource naming, feature-local entities,
large merged result spans, cross-language incompleteness, or misleading
follow-up seeds.

## Goals

P2.1 must:

1. Make `cst context` and `context_search_context` return ContextPack schema v2.
2. Return source excerpts exactly once, inside selected context items, without
   duplicating full raw query results.
3. Enforce deterministic item, per-item, content, and serialized-pack budgets.
4. Preserve enough retrieval-span provenance to excerpt the relevant parts of a
   large merged result without rereading the repository.
5. Improve shared artifact-role classification for the real Spring cases without
   weakening established generic, frontend, or Java ranking gates.
6. Represent concrete evidence needs with subject and group scope.
7. Make status, confidence, missing evidence, and follow-up queries derive from
   those needs and from budget outcomes.
8. Add a reproducible, pinned real-repository quality profile that catches the
   observed gaps.
9. Keep the raw `query` public schema, serialization, and single-pass mechanics
   unchanged; only the explicitly tested shared-role priority fixes may change
   ranking order.
10. Keep context construction pure and limited to the one already-completed
    retrieval pass.

## Non-Goals

P2.1 does not:

- add multi-round retrieval or automatically execute `next_queries`;
- add graph traversal, call-graph construction, or type resolution;
- implement the full Phase 3 RetrievalTrace contract;
- use fast-context output as an automated test oracle;
- require BGE-M3, a query planner, or network access for deterministic CI;
- close the roadmap while the documented Phase 1 acceptance dependency remains
  unresolved;
- preserve ContextPack v1 response compatibility.

## Decision And Alternatives

### Selected: Agent-First Schema V2

Replace the unused reference-oriented v1 context contract with one bounded,
self-contained reading set. This is the only option that can enforce an exact
payload budget, preserve relevant excerpts, and let readiness describe the
evidence an agent can actually see.

### Rejected: Add Excerpts Beside V1 Raw Arrays

Keeping raw arrays and adding excerpts would preserve a contract with no known
consumer while duplicating source content and making the hard pack budget
meaningless. Callers that need complete ranked evidence already have `query`.

### Rejected: Patch Grouping And Follow-Ups Only

Role fixes and safer query seeds would address visible symptoms, but v1 would
still confuse group occupancy with scoped evidence and could still emit
unbounded content. Those are contract problems, not isolated heuristics.

### Deferred: Multi-Round Retrieval

Executing follow-up queries could improve recall, but it changes latency,
stopping, trace, and budgeting semantics. P2.1 makes single-pass output honest
and useful first; controlled exploration remains Phase 4.

## Public Surface Decisions

### Raw Query Remains The Evidence Interface

`cst query` and `context_search_query` remain the operations for complete ranked
results, score parts, planner diagnostics, semantic matches, and follow-up
keywords. Their existing JSON, Markdown, MCP, error, and feedback contracts stay
unchanged.

### Context Becomes A Separate Agent Interface

`cst context` and `context_search_context` return a small envelope plus one
self-contained ContextPack v2. They do not copy `results` or `evidence_anchors`
into the response.

The success envelope is:

```json
{
  "ok": true,
  "repo": "/absolute/repo",
  "query": "owner registration flow",
  "retrieval": {
    "result_count": 12,
    "evidence_anchor_count": 2,
    "planner_status": "disabled",
    "planner_intent": "unknown"
  },
  "context_pack": {}
}
```

`retrieval` is deliberately bounded metadata. It does not contain source text,
raw result arrays, rewritten-query arrays, grep keywords, symbol hints, semantic
matches, or score-part maps. Relevant score and reason information is copied in
bounded form onto each selected context item.

### Context Options

Add a persisted `[context]` section:

```toml
[context]
max_items = 12
max_excerpts_per_item = 2
max_excerpt_bytes = 4096
max_item_content_bytes = 8192
max_total_content_bytes = 49152
max_pack_bytes = 65536
```

Rules:

- every value is a positive integer;
- `max_excerpt_bytes <= max_item_content_bytes`;
- `max_item_content_bytes <= max_total_content_bytes`;
- `max_total_content_bytes < max_pack_bytes` so metadata has reserved space;
- effective `max_items` is the lesser of its persisted or request value and the
  effective raw-result-plus-anchor limit;
- CLI and MCP may override `max_items` and `max_pack_bytes` per request;
- a request-level `max_pack_bytes` replaces only the configured pack ceiling;
  effective total content is
  `min(configured_max_total_content_bytes, request_max_pack_bytes - 1)`, effective
  item content is the lesser of its configured value and that total, and
  effective excerpt content is the lesser of its configured value and the
  effective item value; the canonical compactor may reduce content further to
  fit metadata;
- lowering the request ceiling never changes relative selection priority and
  never permits any configured subordinate ceiling to be exceeded;
- the minimum accepted `max_pack_bytes` is 4,096 bytes.

The public CLI additions are:

```text
cst context REPO QUESTION --max-items N --max-context-bytes N
```

The MCP tool adds nullable `max_items` and `max_context_bytes` arguments with the
same validation and semantics.

## ContextPack Schema V2

`schema_version` is exactly `2`.

```json
{
  "schema_version": 2,
  "status": "partial",
  "items": [],
  "groups": {},
  "reading_order": [],
  "evidence_needs": [],
  "missing_evidence": [],
  "next_queries": [],
  "omissions": [],
  "confidence": {},
  "budget": {}
}
```

The object has exactly those eleven top-level keys. `groups` always has all six
closed group keys, including empty arrays, and each item ID occurs exactly once
across those arrays and exactly once in `reading_order`.

### Context Item

Each selected item is self-contained:

```json
{
  "id": "item:0",
  "file_path": "src/main/java/example/OwnerController.java",
  "group": "entrypoints",
  "role": "entrypoint",
  "classification_basis": "path",
  "source_kind": "result",
  "retrieval_rank": 0,
  "relevance_score": 2.41,
  "reasons": ["path/symbol match", "route token match"],
  "matched_need_ids": ["need:entrypoints:owner"],
  "excerpts": [
    {
      "start_line": 72,
      "end_line": 87,
      "content": "...",
      "content_bytes": 612,
      "truncated": false
    }
  ]
}
```

Constraints:

- an item has exactly the eleven shown keys and an excerpt has exactly the five
  shown keys;
- item IDs are assigned after final selection in reading order;
- `file_path` is repository-relative and never truncated;
- one file produces at most one item;
- an item contains at most `max_excerpts_per_item` non-overlapping excerpts;
- excerpts are ordered by source line and never duplicate source lines;
- `content_bytes` is the exact UTF-8 byte count of `content`;
- `reasons` contains at most four existing public reason strings;
- `relevance_score` is finite JSON or `null` for anchors;
- `retrieval_rank` is the original zero-based raw result rank or `null` for an
  evidence anchor;
- `classification_basis` is `path`, `content`, or `fallback`;
- `source_kind` is `result` or `evidence_anchor`;
- every `matched_need_id` resolves inside `evidence_needs`.

When a raw result and an evidence anchor refer to the same normalized path, they
become one result-backed candidate. The candidate retains the union of bounded
reasons and need matches; it does not duplicate content or consume two item
slots. Normalization is case-sensitive on case-sensitive repositories and uses
the repository's existing canonical relative paths.

The closed group names remain:

```text
entrypoints
implementations
related_types
tests
configs_docs
supporting
```

The group map and reading order contain selected item IDs only.

### Retrieval Span Provenance

Large v1 results occur when several contributing chunks from the same file are
merged into one broad line range. P2.1 adds an internal frozen `RetrievalSpan`
record to each `RetrievalResult`:

```python
@dataclass(frozen=True)
class RetrievalSpan:
    start_line: int
    end_line: int
    score: float
    sources: tuple[str, ...]
```

This field is internal to the in-memory bundle and is not added to raw query
formatters. Result construction records the contributing chunk windows before
they are merged. The ContextPack compactor uses those spans to select excerpts
from the already-returned result content. It performs no filesystem, store,
vector, network, planner, embedding, or retrieval call.

If a synthetic or legacy result has no spans, the compactor derives one fallback
span from its existing `start_line`, `end_line`, and content. This fallback is
deterministic and covered separately.

### Evidence Need

An `EvidenceNeed` states what evidence the query asks for, not merely which group
would be nice to populate:

```json
{
  "id": "need:configs_docs:postgresql",
  "category": "configs_docs",
  "subject_terms": ["postgresql"],
  "required": true,
  "provenance": "explicit_query",
  "matched_item_ids": []
}
```

Need IDs are deterministic, collision-free slugs derived from category and
normalized subject, with a numeric suffix on collision. A subject term is
trimmed to 64 Unicode code points at a code-point boundary before it enters any
public field or ID. Need order follows explicit query order first, then the
closed structural-recommendation order.

Closed provenance values are:

```text
explicit_query
explicit_identifier
planner_supported
structural_recommendation
```

Need derivation rules:

1. Explicit original-query role terms create required category needs.
2. Explicit identifiers and high-signal original-query subjects scope those
   needs. Multiple explicit subjects create separate needs when the grammar joins
   them, so `MySQL PostgreSQL ... configuration and integration tests` cannot be
   satisfied by MySQL evidence alone.
3. Exact identifier roles create required needs for their own category without
   inventing unrelated flow requirements.
4. Planner terms are never required on their own. A planner-supported subject
   becomes a recommended need only when it is present in a non-discarded planner
   field and is grounded by a returned path, symbol, route, or content token.
5. Structural recommendations may request adjacent groups, such as tests for an
   entrypoint flow, but remain recommended.
6. Generated expanded tokens, discarded planner hints, follow-up keywords, and
   retrieval-summary values do not create subjects.

Need matching requires both:

- the candidate belongs to the need's category; and
- every explicit subject represented by that need matches normalized candidate
  path, symbol, route, content, or trusted retrieval provenance.

A generic README or POM therefore cannot satisfy a PostgreSQL configuration need
unless it actually contains the PostgreSQL subject.

### Missing Evidence

One missing-evidence entry corresponds to one unmatched or budget-omitted need:

```json
{
  "need_id": "need:configs_docs:postgresql",
  "category": "configs_docs",
  "required": true,
  "reason": "required PostgreSQL configuration evidence is missing from the bounded context"
}
```

Reasons use fixed templates and may contain only normalized public subject terms;
they do not copy planner rewrites or source content.

### Omissions

Candidates not selected under the item or byte budget are reported separately:

```json
{
  "file_path": "src/main/resources/static/app.css",
  "group": "supporting",
  "reason": "lower priority than selected evidence under the context budget",
  "matched_need_ids": []
}
```

`budget.omitted_item_count` is the total number of unselected normalized
candidates. `omissions` is only a deterministic preview: required-need matches
first, then recommended-need matches, then candidate selection order, capped at
`max_items` and reduced further if metadata must be compacted. Omissions carry no
source content, scores, planner text, or private diagnostic data. It is therefore
valid for `len(omissions) < budget.omitted_item_count`.

### Status And Confidence

Status values remain `empty`, `partial`, and `ready`, with stronger semantics:

- `empty`: retrieval returned no usable result or anchor;
- `partial`: at least one required evidence need is unmatched, every candidate
  matching a required need was omitted by budget, or usable retrieval evidence
  exists but no item can fit the requested pack budget;
- `ready`: every required evidence need is matched by a selected item.

Truncation alone does not make a pack partial when the retained excerpt contains
the matched evidence. If truncation removes the only matching span, the need is
unmatched.

Confidence remains `none`, `low`, `medium`, or `high`:

- `none`: empty;
- `low`: partial, including when no required match can be selected;
- `medium`: ready but recommended needs are missing, selected required evidence
  is truncated, planner-supported evidence is material to readiness, or protected
  original-direct evidence is absent;
- `high`: ready, all recommended needs are matched or inapplicable, required
  evidence is not truncated, and protected original-direct evidence is present.

Confidence reasons are closed, deterministic strings.

Protected original-direct evidence means an original retrieval result whose
existing public `score_parts.evidence_priority` is exactly `0`. Anchors and
missing or nonzero diagnostics do not count as protected evidence.

The confidence object has exactly this shape:

```json
{
  "level": "medium",
  "reasons": ["all required evidence is selected", "recommended tests are missing"]
}
```

It contains at most four reasons in fixed precedence order.

### Next Queries

Next queries are built from missing needs, required first, in evidence-need order,
with at most three suggestions.

Seed priority is:

1. the missing need's explicit original-query subject;
2. a selected item stem that both matches the need and has protected direct
   evidence;
3. the normalized original user query.

Planner-only subjects may be used only after grounding to a selected item. Raw
retrieval-summary lists, generated expansions, discarded hints, and unrelated
routes are never seeds.

The category suffixes remain bounded phrases such as `service implementation`,
`test`, `configuration documentation`, and `model type`. Suggestions are
whitespace-normalized, case-insensitively deduplicated, capped at 160 Unicode code
points without cutting the suffix, and linked to `need_id`.

Each entry has exactly this shape:

```json
{
  "need_id": "need:configs_docs:postgresql",
  "query": "PostgreSQL configuration documentation",
  "purpose": "find missing required configuration evidence"
}
```

`purpose` comes from a closed category-and-requiredness template table; it never
contains source, planner, or free-form model text.

For the observed cases, acceptable examples include:

```text
PostgreSQL configuration documentation
OwnerController test
宠物主人详情页如何加载宠物和就诊记录 service implementation
```

`GET /oups service implementation` is explicitly forbidden for the pinned
owner-details case.

### Budget

The budget object is:

```json
{
  "max_items": 12,
  "max_excerpts_per_item": 2,
  "max_excerpt_bytes": 4096,
  "max_item_content_bytes": 8192,
  "max_total_content_bytes": 49152,
  "max_pack_bytes": 65536,
  "included_items": 8,
  "included_excerpts": 11,
  "content_bytes": 43820,
  "pack_bytes": 60314,
  "truncated_item_count": 2,
  "omitted_item_count": 4,
  "budget_exhausted": true
}
```

It has exactly the shown fields and reports effective limits after request
overrides. `content_bytes` is the sum of all excerpt `content_bytes` values;
`truncated_item_count` counts items with at least one truncated excerpt; and
`budget_exhausted` is true when any item, excerpt, content, or canonical-pack
ceiling removes or truncates otherwise selectable evidence.

`pack_bytes` is the exact UTF-8 length of canonical compact JSON produced by:

```python
json.dumps(
    context_pack_payload,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
```

The final `pack_bytes` value is calculated with that field set to its final
integer value. The builder must account for digit-width changes and converge
deterministically; it may not report a pre-update estimate.

## Deterministic Compaction Algorithm

The builder runs these pure stages:

1. Normalize raw results and anchors into candidates.
2. Classify each candidate exactly once.
3. Derive ordered evidence needs.
4. Match candidates to needs.
5. Rank candidates for selection.
6. Build preferred excerpt windows from retrieval spans.
7. Select items and allocate content under all budgets.
8. Re-evaluate need matches against retained excerpts.
9. Derive omissions, status, confidence, and next queries.
10. Materialize and validate canonical schema v2 JSON.

### Candidate Selection Order

Selection uses this stable key:

1. covers an unmatched required need;
2. number of required needs covered, descending;
3. covers an unmatched recommended need;
4. number of recommended needs covered, descending;
5. promoted group order from explicit query intent;
6. original retrieval result before evidence anchor only when all prior keys tie;
7. original retrieval rank or anchor order;
8. repository-relative path.

The selector first reserves one candidate for every matchable required need, then
recommended needs, then fills remaining item slots with supporting evidence.
One candidate may satisfy several needs.

### Excerpt Windows

For each selected result:

- locate windows that carry each matched need using path, declaration, route,
  symbol, and content-match provenance;
- order windows that preserve required matches first, then recommended matches,
  protected original-direct evidence, span score descending, and source line;
- expand each span by the effective existing context-line setting;
- merge overlapping or adjacent windows;
- keep at most `max_excerpts_per_item` windows;
- restore source-line order before rendering;
- crop at complete line and Unicode-code-point boundaries;
- if a single line exceeds its remaining byte budget, crop the line at a valid
  UTF-8 boundary and set `truncated = true`;
- never insert content that is not present in the QueryBundle result.

If the excerpt-count or byte limit cannot retain all of a candidate's claimed
need matches, only matches visible in the retained windows survive. The selector
may then choose a different candidate for an uncovered need; otherwise the need
is reported missing. Candidate-level matching alone never establishes readiness.

For anchors without scored spans, exact subject matches define windows. A short
anchor fits whole; otherwise the first matching window wins, then the file head as
a deterministic fallback.

### Byte Allocation

Allocation is deterministic and group-aware:

1. Reserve metadata space by limiting source content to
   `max_total_content_bytes`.
2. Give each required-coverage item up to 512 bytes when available.
3. Give each recommended-coverage item up to 512 bytes when available.
4. Fill items in final reading order up to `max_item_content_bytes` and the global
   content limit.
5. Materialize canonical JSON and account for every candidate's actual path and
   metadata before admitting it to the final item list.
6. If canonical JSON exceeds `max_pack_bytes`, first remove lowest-priority
   omission-preview entries, then surplus item reason strings, then content one
   complete line at a time from the lowest-priority optional item, optional
   excerpts, and the lowest-priority required item while retaining its matched
   span when possible.
7. If further compaction is required, omit the lowest-priority optional item and
   re-run need and status derivation. Repeat deterministically.
8. If metadata plus the minimum representation of one match per required need
   cannot fit, omit the lowest-priority conflicting need match, mark the need
   missing, and return `partial` rather than violating the budget.
9. Raise `ContextPackError` only if the mandatory schema skeleton itself cannot
   fit the caller's valid minimum budget or canonical JSON cannot be made
   self-consistent.

The algorithm never silently exceeds a configured byte limit. It never truncates
repository-relative paths, need IDs, JSON keys, or fixed enum values; a candidate
whose minimum self-contained representation does not fit is omitted honestly.

## Shared Artifact-Role Improvements

Role detection remains centralized. ContextPack must not carry a second private
classifier that disagrees with retrieval ranking.

The shared role result gains a closed `basis` value (`path`, `content`, or
`fallback`) in addition to name and priority. Existing callers that use name and
priority remain straightforward.

Add these conservative rules with explicit precedence tests:

### Spring And JVM Config

- `application.properties`
- `application-*.properties`
- `bootstrap.properties`
- `bootstrap-*.properties`
- the same names with `.yaml` or `.yml`
- `.properties` under `config` or `configs`
- `logback*.xml`, `log4j*.xml`, `persistence.xml`, and `beans.xml`

These are `runtime_config`. Localization bundles such as
`messages_de.properties` remain source/supporting unless stored in a config
directory.

### Spring Templates

HTML files below a `templates` directory are `view`. Static HTML outside template
directories remains source unless another existing rule applies.

### Java Implementations And Types

- stems ending `Repository` are `repository`;
- stems ending `Service`, `ServiceImpl`, `Handler`, or existing executor patterns
  retain their current roles and precedence;
- Java declarations annotated with `@Entity`, `@Embeddable`,
  `@MappedSuperclass`, or Spring Data `@Document` are `data_type`;
- Java `record` and `enum` declarations are `data_type` when no higher-precedence
  service, controller, repository, test, or config role applies;
- stems ending `Dto`, `DTO`, `Vo`, `VO`, `Request`, `Response`, `Entity`, or
  `Model` are `data_type`.

Content rules match declarations and annotation lines, not imports, comments, or
arbitrary string literals. Tests, controllers, services, repositories, configs,
and generated artifacts retain precedence over generic type detection.

Every role change is considered a retrieval change because role priority affects
reranking. The complete `ci`, `smoke`, applicable Phase 1, and real P2.1 profiles
must be compared before roadmap claims change.

## Internal Module Boundaries

The current `context_pack.py` is already large. V2 converts it into a package while
preserving imports through `context_search_tool.context_pack.__init__`:

```text
src/context_search_tool/context_pack/
  __init__.py
  models.py
  roles.py
  needs.py
  excerpts.py
  builder.py
  serialization.py
```

Responsibilities:

- `models.py`: frozen v2 records, closed values, options, and fixed errors;
- `roles.py`: context group mapping from shared artifact and frontend roles;
- `needs.py`: need derivation, matching, missing evidence, confidence, and next
  queries;
- `excerpts.py`: span normalization, excerpt windows, UTF-8-safe cropping, and
  byte allocation;
- `builder.py`: pure stage orchestration and final invariants;
- `serialization.py`: exact JSON-native payloads and canonical byte accounting;
- `__init__.py`: intentionally small public export surface.

The package performs no I/O. Retrieval, CLI, MCP, quality, and formatters remain
outside it.

## CLI, MCP, And Formatting

### Invocation

Each context invocation still calls `query_repository()` exactly once and the v2
builder exactly once. Retrieval-span recording occurs during that same query.

### JSON

CLI JSON and MCP return identical `context_pack` objects for the same bundle and
options. JSON is strict: `allow_nan=False`, no custom encoder, and no dataclass or
Path objects in the payload.

### Markdown

Markdown follows `reading_order`, rendering each selected item and excerpt once.
It includes status, confidence, needs, missing evidence, omissions, next queries,
and budget. It never dereferences a second raw array.

Markdown content obeys the same content and item limits. Rendering overhead is
reported separately in formatter tests; `max_pack_bytes` is specifically the
canonical JSON pack limit so its definition is transport-independent.

### Errors

Public fixed error codes are:

- existing repo/index/query errors before pack construction;
- `invalid_context_options` for invalid persisted or request budget values;
- `context_failed` for internal classification, span, compaction, reference,
  canonical-size, or serialization failures.

CLI writes the existing `Error: <code>: <message>` shape to stderr and exits 1.
MCP returns the existing `{ok: false, error: {code, message}}` envelope. Unexpected
pack exceptions map to a fixed sanitized message. No partial fabricated pack is
returned after an internal failure.

Budget exhaustion during valid compaction is not an error; it produces omissions
and may produce `partial`.

## Feedback And Privacy

The context feedback event records only bounded metadata:

- schema version, status, confidence;
- group, need, selected-item, excerpt, truncation, and omission counts;
- required and recommended missing categories;
- configured and used byte counts;
- next-query count.

It must not add source content, file paths, item or need IDs, subject terms,
next-query text, planner rewrite text, semantic variants, or discarded hints.
Existing raw query logging and repository hashing behavior remain unchanged.

## Reproducible Real-Repository Quality Profile

Add an opt-in profile named `p2_real_context`. It is not part of offline CI and
does not silently access the network during `quality run`.

### Pinned Repository Declaration

The quality catalog gains optional source fields:

```json
{
  "repo_key": "spring_petclinic",
  "source_url": "https://github.com/spring-projects/spring-petclinic.git",
  "source_commit": "51045d1648dad955df586150c1a1a6e22ef400c2",
  "checkout_dir": "spring-petclinic",
  "profiles": ["p2_real_context"]
}
```

The existing committed-snapshot fields remain mutually exclusive with remote
source fields.

### Preparation Command

Add:

```text
cst quality prepare tests/fixtures/retrieval_quality/queries.json \
  --profile p2_real_context \
  --repos-dir .quality/repos
```

The command:

1. validates catalog URLs, exact 40-character commits, and checkout names;
2. clones or fetches with `git` argument arrays, never a shell string;
3. checks out the exact commit in detached-HEAD state;
4. verifies `HEAD`, remote URL, and a clean tracked worktree;
5. writes a small provenance manifest under `.quality/repos`;
6. is idempotent and refuses to overwrite an unrelated directory.

`quality run --profile p2_real_context` resolves only the prepared checkout. A
missing, dirty, wrong-commit, or wrong-remote checkout is an explicit required
error, never a skip or silent fallback.

### Required Spring PetClinic Cases

The profile uses offline hash embeddings and planner disabled. It contains the
four fresh-validation queries listed in this design.

It locks:

- expected critical paths and group assignments that are actually present in the
  bounded result set;
- `OwnerController`, repositories, domain entities, tests, templates, and Spring
  config roles where retrieved;
- explicit MySQL and PostgreSQL config/test evidence needs;
- honest `partial` status when retrieval misses required evidence;
- no follow-up query containing `/oups` for the owner-details query;
- no config/test query that asks for an unrelated owner DTO;
- canonical pack size at or below 65,536 bytes;
- per-item and excerpt limits;
- deterministic repeated JSON output;
- context feedback privacy.

The real profile does not require every one of the 21 manually reviewed files to
be recalled by hash retrieval. Missing critical evidence must instead be reported
honestly and produce a grounded next query. Retrieval coverage remains a separate
metric and future tuning target.

### Fast-Context Comparison

Documentation records the comparison parameters and results, but fast-context is
not a gate because it is remote, model-driven, quota-dependent, and not guaranteed
deterministic. Pinned CST cases and source inspection define CST behavior.

## Quality Schema And Metrics

Context quality cases retain group/path matchers and add:

```json
{
  "expected_need_matches": [
    {
      "category": "configs_docs",
      "subject": "postgresql",
      "required": true,
      "matched": true
    }
  ],
  "maximum_pack_bytes": 65536,
  "maximum_truncated_items": 4,
  "forbidden_next_query_patterns": ["/oups", "GET /owners dto"]
}
```

New metrics are:

- `evidence_need_count`;
- `required_need_count`;
- `matched_required_need_count`;
- `evidence_need_completeness`;
- `pack_bytes`;
- `content_bytes`;
- `truncated_item_count`;
- `omitted_item_count`.

`context_completeness` remains for group/path expectations so existing historical
reports stay interpretable. The v2 profile gates both context completeness and
evidence-need completeness.

## Testing Strategy

Implementation follows strict red-green-refactor cycles. Each behavior below must
have a focused failing test before production code changes.

### Shared Role Tests

- Spring profile property names classify as runtime config.
- localization property bundles remain source/supporting.
- Thymeleaf templates classify as views.
- `*Repository.java` classifies as repository.
- Java entity annotations, records, enums, and type suffixes classify as data
  types only when higher-precedence roles do not apply.
- imports, comments, and string literals do not trigger content roles.
- existing role and ranking tests remain unchanged unless the approved new role
  intentionally changes their expected result.

### Retrieval Span Tests

- every contributing chunk creates one valid internal span;
- duplicate and overlapping spans normalize deterministically;
- adding internal spans alone leaves raw query payloads byte-for-byte unchanged;
- recording spans performs no additional retrieval or I/O;
- synthetic results without spans use the declared fallback.

### Need Tests

- explicit multiple subjects produce distinct scoped needs;
- group-only evidence cannot satisfy a subject-scoped need;
- planner-only terms require grounding and remain recommended;
- discarded and generated hints never create or seed needs;
- budget omission of the only required match makes the need missing;
- exact symbol requests do not invent flow needs.

### Excerpt And Budget Tests

- excerpt windows use top retrieval spans and source-line order;
- overlap merging, maximum excerpts, per-excerpt, per-item, content, item, and
  canonical pack limits are exact;
- ASCII, CJK, emoji, combining characters, CRLF, a single overlong line, and no
  final newline crop at valid boundaries;
- a large CSS result cannot force a pack above 65,536 canonical bytes;
- required need coverage is reserved before optional supporting content;
- impossible minimum representations return an honest partial pack;
- canonical `pack_bytes` includes its own final integer width;
- repeated builds produce identical objects and bytes.

### Contract Tests

- schema version is exactly 2 with exact closed keys and values;
- context responses omit raw `results` and `evidence_anchors`;
- item excerpts contain the only source content in a context pack;
- CLI and MCP pack payloads are identical;
- Markdown renders every excerpt exactly once in reading order;
- raw query CLI and MCP schemas and serialization remain unchanged;
- context option errors and unexpected failures use fixed envelopes;
- one invocation performs one retrieval and one build.

### Quality And Real-Project Tests

- the existing offline `p2_context_pack` cases are migrated to schema v2 and pass;
- existing `ci` raw-result cases pass;
- prepared-repository validation rejects wrong commit, remote, dirtiness, and
  directory collisions;
- the four pinned Spring cases execute without a model;
- every real pack stays within budget and repeats identically;
- the observed config/type/template and next-query regressions are locked;
- fast-context remains documentation evidence only.

### Full Verification

Before P2.1 completion claims:

1. run focused role, retrieval, pack, CLI, MCP, quality, and preparation tests;
2. run the complete pytest suite;
3. run offline `p2_context_pack` and unchanged `ci` profiles;
4. prepare and run `p2_real_context` from an empty cache;
5. rerun `p2_real_context` from the populated cache to prove idempotence;
6. compare applicable model-backed Phase 1 profiles because shared role priorities
   change retrieval behavior;
7. repeat the four manual CST and fast-context queries for a dated qualitative
   report;
8. inspect feedback for privacy and payload-size claims;
9. run diff, artifact, import-path, and clean-worktree checks.

An unavailable model or remote comparator is recorded as an explicit dependency
result, never converted into a pass. The pinned hash real profile itself must be
fully executable once its checkout has been prepared.

## Error And Edge-Case Matrix

| condition | result |
| --- | --- |
| missing index | existing `missing_index` behavior |
| invalid context limits | `invalid_context_options` before retrieval |
| valid empty retrieval | successful schema v2 `empty` pack |
| required evidence not retrieved | successful `partial` pack plus next query |
| required evidence omitted by budget | successful `partial` pack plus omission |
| optional content exceeds budget | successful bounded pack, possibly `ready` |
| metadata cannot fit valid minimum | sanitized `context_failed` |
| invalid span/reference/classification | sanitized `context_failed` |
| JSON-native or canonical-size failure | sanitized `context_failed` |
| prepared repo missing or wrong | required quality error |
| fast-context unavailable | comparison dependency note, not CST gate |

## Likely Change Surface

Expected implementation work includes:

- replace `src/context_search_tool/context_pack.py` with the v2 package;
- extend `src/context_search_tool/models.py` with internal retrieval spans;
- update retrieval result construction without changing raw query output;
- improve `src/context_search_tool/path_roles.py` and focused role helpers;
- add `[context]` config parsing and rendering;
- replace context JSON and Markdown formatting;
- update CLI and MCP context options, envelopes, feedback, and descriptions;
- migrate context quality schema, metrics, runner behavior, and offline cases;
- add pinned source declarations and `quality prepare`;
- add the `p2_real_context` catalog cases and tests;
- update README, quality documentation, design/plan links, and roadmap evidence
  without marking blocked phases complete.

No implementation file is changed as part of this design commit.

## Acceptance Criteria

P2.1 is implementation-complete only when all are true:

1. CLI and MCP expose identical ContextPack schema v2 objects.
2. Context responses contain no raw result or anchor arrays and no duplicated
   source content.
3. Every selected item is self-contained, deterministically grouped, and rendered
   once in reading order.
4. Every pack satisfies item, excerpt, content, and exact canonical pack byte
   limits.
5. Large merged results are excerpted from recorded retrieval spans without extra
   I/O or retrieval.
6. Shared roles correctly cover the declared Spring config, template, repository,
   and Java type cases without raw-result gate regression.
7. Readiness is based on scoped evidence needs rather than group occupancy.
8. Missing evidence and follow-up queries are grounded, deterministic, and free
   of the observed unrelated `/oups` and owner-DTO suggestions.
9. Raw query contracts remain unchanged.
10. Offline P2, CI, full-suite, and pinned real-project gates pass.
11. Feedback remains bounded and privacy-safe.
12. Documentation reports model and fast-context dependencies honestly, and the
    roadmap is updated only when its independent acceptance conditions pass.

## Delivery Decomposition

The implementation plan should preserve reviewable checkpoints in this order:

1. Context options and schema v2 model contract.
2. Shared artifact-role hardening.
3. Retrieval-span provenance with raw-query compatibility.
4. Evidence-need derivation and matching.
5. Deterministic excerpt selection and hard budgets.
6. Status, confidence, omissions, and grounded next queries.
7. CLI, MCP, formatting, errors, and privacy.
8. Quality schema and offline profile migration.
9. Pinned repository preparation and real profile.
10. Documentation, model reconciliation, fast-context comparison, and final
    verification.

Each checkpoint must use focused failing tests before implementation and a commit
after its focused and relevant regression gates pass.

## Stop Point

This design ends after ContextPack v2 and its real-project quality loop are
implemented and verified. It does not proceed into automatic follow-up execution,
multi-round retrieval, graph traversal, or full RetrievalTrace work.
