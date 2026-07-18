# P5 Language And Framework Graphs v1 Design

Date: 2026-07-17
Status: Implemented and accepted on 2026-07-18
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor: `docs/superpowers/specs/2026-07-16-p4-controlled-multi-round-exploration-design.md`
Baseline: `319dfedc777b7479e9b542c1e65ddd15814100b1`
Implementation plan: `docs/superpowers/plans/2026-07-17-p5-language-framework-graphs.md` (complete)

## Summary

P5 makes CST's existing signal/relation graph precise enough to follow common
language and framework flows. Java/Spring is the first and deepest vertical
slice, but P5 v1 also covers MyBatis mapper XML, Vue/React route and import
graphs, and conservative test-to-production associations for Java, Go, Rust,
Python, JavaScript, and TypeScript.

The design evolves `CodeSignal` and `CodeRelation`; it does not add a second
graph store. File-local producers emit typed signals and structured unresolved
selectors. A repository-wide pass resolves a selector only when the target is
exact or unique in its legal scope. Ambiguous, external, and unresolved edges
are persisted for diagnostics but are never traversed or converted back into a
text match. Only explicitly legacy relations retain the old name fallback.

Java, JavaScript, TypeScript, and Vue script blocks use official Tree-sitter
grammars. The Java producer extracts declarations, lexical bindings, calls,
framework annotations, implementation relationships, and conservative
repository-local type usage. A safe MyBatis XML producer connects statements
to mapper methods. Frontend producers connect framework-anchored routes to
components and persist static imports/re-exports. A separate repository pass
creates exact same-unit test associations.

Resolved edges remain inside the existing relation-expansion stage and feed at
most one grounded hop to P4. P4's rounds, calls, goals, feedback, fusion, and
schemas remain unchanged. P5 adds bounded graph data to `explain`, but no new
top-level operation or trace schema.

## Baseline And Current Evidence

The reviewed baseline is commit
`319dfedc777b7479e9b542c1e65ddd15814100b1`:

- Phase 4 is implemented and verified;
- full suite at the recorded baseline: 2,181 passed, 9 established optional
  skips, and 0 xfails;
- P4 focused suite: 243 passed;
- protected P0-P3 suite: 194 passed;
- deterministic P4 profile: 4/4;
- P2 ContextPack profile: 5/5;
- raw CI profile: 8/8;
- P3 and P4 non-empty trace coverage: 1.0;
- Phase 1 remains independently pending at 6/7.

The repository already has the intended extension points:

- plugins emit symbols, signals, relations, tokens, and metadata;
- Java emits useful endpoint, method, type, call, use, and implementation
  evidence, but structural parsing is regex-based;
- SQLite persists active signals/relations and relation expansion is a named
  retrieval stage;
- P4 can derive one-hop probes from relations and on-demand frontend imports;
- project units, frontend roles/import resolution, test classification,
  ContextPack, and bounded traces already exist.

The current substrate is insufficient because relation targets are names, IDs
cannot distinguish structured overload selectors, frontend imports/routes and
test associations are not persistent graph edges, and indexing has no
repository-wide graph-completion contract.

## Problem Statement

For a call such as:

```java
return orderService.findById(id);
```

the current extractor can produce `OrderService.findById`, but retrieval cannot
prove which active declaration it means, distinguish same-arity overloads, or
walk from an interface method to an implementation. Name ambiguity compounds
over multiple hops and across monorepo units. Equivalent gaps exist for a Vue
lazy route, React Router component, MyBatis XML statement, and test module.

P5 must strengthen identity and resolution without claiming compiler-level
semantics, weakening direct evidence, executing repository code, or turning P4
into recursive exploration.

## Goals

1. Give signals and relations structured, collision-resistant v5 identities.
2. Resolve repository-local relation targets deterministically and fail closed
   on ambiguity.
3. Make graph readiness recoverable after partial indexing and safe under
   project-unit topology changes.
4. Replace supported Java structural extraction with AST-backed facts while
   preserving protected lexical/endpoint behavior.
5. Follow controller, service interface, implementation, mapper/repository,
   related type, mapper XML, and test evidence through conservative edges.
6. Persist framework-anchored Vue/React routes and static frontend module
   imports/re-exports.
7. Associate tests across the six declared language families only from closed,
   same-unit evidence.
8. Keep exact path, symbol, endpoint, constant, and direct-text evidence above
   graph-only evidence.
9. Integrate with the existing relation stage and P4 without changing public
   result, ContextPack, RetrievalTrace, or ExplorationTrace schema versions.
10. Expose bounded resolution state and graph neighbours through `explain`.
11. Add executable structural, synthetic-retrieval, real-project, privacy,
    compatibility, and failure-recovery gates.

## Non-Goals

P5 v1 does not:

- implement a Java compiler, build graph, classpath resolver, language server,
  points-to analysis, runtime Spring bean selection, or Lombok synthesis;
- implement Java assignability, widening, boxing, generic substitution, or
  chained-return inference;
- execute Maven, Gradle, npm, pnpm, TypeScript, XML includes, annotation
  processors, macros, tests, or application code;
- fetch parsers, grammars, DTDs, schemas, packages, or source while indexing;
- add AST language plugins for Go, Rust, or Python;
- support arbitrary TS `paths`, webpack/Vite aliases, dynamic route mutation,
  computed imports, or custom router DSLs;
- infer tests from raw substring similarity, directory proximity, or a global
  basename search;
- add another graph database, query stage, public graph command, ContextPack
  group, trace schema, recursive loop, P4 round, P4 probe, or model call;
- implement P6 service/watch mode, lazy refresh, performance targets, or
  approximate graph indexes;
- change Phase 1's independent 6/7 status;
- authorize an implementation plan or implementation.

## Assumptions And Decisions

- P5 is the whole roadmap phase: Java/Spring/MyBatis, frontend routes/imports,
  and generic test association. Java is the first implementation slice.
- Signal schema v5 requires a logical full reindex, including chunks, token/FTS
  rows, and vector embeddings, because AST-backed symbols and lexical tokens can
  change chunk identity and embedding input. This is not a signals-only rebuild.
- After ordinary file changes, all active structured relations are re-resolved.
  Dependency-aware invalidation is deferred to P6.
- The canonical project-unit key is the repository-relative POSIX unit root.
  `""` is the valid root-unit key, not a missing value.
- Parser versions are pinned and upper-bounded together in the later
  implementation plan; this design fixes grammar owners and behavior.
- New score/reason keys are additive only on candidates actually affected by a
  legal P5 edge. Protected direct candidates are immutable under graph merging.

## Architecture Decision

### Selected: Existing Signals And Relations, Two-Stage Resolution

File-local producers write signals and unresolved relation selectors. A global
pass first resolves producer relations, then generates test associations from
the resolved imports/types, resolves those associations, validates integrity,
and marks the graph ready.

This reuses current deletion, retrieval, trace, and P4 owners and keeps one
source of graph truth. A separate graph database was rejected because it would
duplicate node identity, project scope, soft deletion, and chunk mapping.

### Rejected Alternatives

- More suffix/name heuristics cannot prove a unique target.
- Query-time parsing repeats work, changes latency, and broadens P4 reads.
- A compiler/LSP requires classpaths and build execution outside CST's local
  partial-repository contract.
- A Java-only P5 leaves the roadmap's frontend and test graph work unfinished.
- Full plugins for Go/Rust/Python are not justified for exact path-based test
  association.

## Design Principles

- **Resolved or honest:** exact/unique edges carry a target ID; all other
  structured states carry none.
- **Syntax is not runtime truth:** AST evidence does not prove dynamic dispatch
  or framework wiring.
- **Generic core, typed producers:** persistence/traversal stays language-neutral.
- **One completed snapshot:** schema-5 graph data is consumed only at `ready`.
- **No convenient tie-break:** ambiguity never picks the first row or extension.
- **Fixed work:** count budgets and canonical ordering, never wall-clock cutoffs,
  determine output.
- **Direct evidence stays protected:** graph reachability cannot mutate a
  protected direct result's score, score parts, reasons, or precedence.

## Parser And XML Dependencies

P5 selects these upstream-owned packages:

- `tree-sitter` for the Python parser API;
- `tree-sitter-java` for Java;
- `tree-sitter-javascript` for JavaScript and JSX;
- `tree-sitter-typescript` for TypeScript and TSX;
- `defusedxml` for bounded MyBatis XML parsing after DOCTYPE validation.

The implementation plan must pin a mutually compatible runtime/grammar ABI and
prove import/parse smoke tests on supported Python versions and Linux/macOS CI
architectures before changing producers. There is no runtime download or
grammar compilation. A missing/broken package is an installation error; a
malformed individual source file follows the per-file fallback contract.

References:

- <https://tree-sitter.github.io/py-tree-sitter/>
- <https://github.com/tree-sitter/tree-sitter-java>
- <https://github.com/tree-sitter/tree-sitter-javascript>
- <https://github.com/tree-sitter/tree-sitter-typescript>
- <https://mybatis.org/mybatis-3/getting-started.html>

## Signal Contract

In this document, an `index-eligible file` is any path accepted by P5's scanner
contract (ignore, symlink/root, regular-file, binary, and size rules). A
`graph-eligible file` is an
active index-eligible source file that produced at least one chunk. Empty files
remain index-visible source records but are not graph-eligible.

P5 appends defaulted fields to `CodeSignal`:

```python
qualified_name: str = ""
signature: str = ""
arity: int | None = None
project_unit_key: str = ""
producer: str = "legacy"
start_column: int = 0
end_column: int = 0
recallable: bool = True
```

`project_unit_key=""` means the repository root unit. `recallable=False` means
the node can be a resolver target, traversal node, and explain item but is
excluded from ordinary `signal_search()` and every textual relation fallback.
`start_column`/`end_column` are zero-based UTF-8 byte columns, with end
exclusive; legacy producers use zero for both.

### Core Module Signal

Every indexed non-binary source file with at least one active chunk has exactly
one `module` signal:

- `qualified_name` and `name`: repository-relative POSIX file path;
- `producer`: `core_module`;
- `project_unit_key`: canonical owning unit root;
- `tokens`: empty;
- `recallable`: false;
- chunk: first active chunk in source order.

Empty files keep their existing zero-chunk behavior and therefore have no
module signal. This is the explicit invariant boundary. The deterministic
module ID helper is shared by core, frontend, XML, and test-association code;
producers must not reconstruct it ad hoc.

All new graph-only plumbing nodes are non-recallable: core modules, frontend
routes, and MyBatis statements. Their containing chunks remain discoverable by
existing path/lexical/vector evidence and can then seed the attached graph node.
Existing user-facing Java declaration/endpoint signal classes remain recallable
under their protected parity contract. Slice 1 adds only the non-recallable
module node, so it cannot change signal recall.

### V5 Signal Identity

Legacy callers that omit every structured field retain the existing legacy ID
helper. Every P5 producer uses:

```text
s5:<full 64-hex sha256(canonical-json)>
```

The canonical JSON has fixed key order and UTF-8 NFC values:

```text
file_path, kind, qualified_name, signature,
start_line, start_column, end_line, end_column, producer
```

Paths are repository-relative POSIX paths. This distinguishes same-line
declarations by column and overloads by normalized signature and avoids the
existing 32-bit short-hash collision class. IDs are stable for identical
source positions within a snapshot; they are not promised across edits.

## Relation Contract

P5 appends defaulted fields to `CodeRelation`:

```python
target_kind: str = ""
target_qualified_name: str = ""
target_signature: str = ""
target_arity: int | None = None
target_project_unit_key: str = ""
target_signal_id: str = ""
resolution: str = "legacy"
producer: str = "legacy"
producer_confidence: float = 1.0
resolution_confidence: float | None = None
```

The existing `confidence` is the effective confidence:

```text
legacy: producer_confidence
structured unresolved: producer_confidence
structured resolved: min(producer_confidence, resolution_confidence)
```

Producer and resolver confidence are persisted separately, so re-resolution
never compounds a previously effective value. A v4 row decoded by the legacy
adapter gets `producer_confidence=confidence`, null resolution confidence, and
`resolution=legacy`.

For every structured row, `target_project_unit_key` is a legal-scope key, never
an "unknown" sentinel: Java and tests copy the source unit; an exact frontend
path uses the target path's detected unit; external selectors retain the source
search boundary. Thus `""` always means the root unit. The field is ignored only
for a row explicitly marked `legacy`.

### Resolution States

| state | target ID | traversable by ID | textual fallback |
| --- | --- | --- | --- |
| `resolved_exact` | required | yes | no |
| `resolved_unique` | required | yes | no |
| `ambiguous` | empty | no | no |
| `external` | empty | no | no |
| `unresolved` | empty | no | no |
| `legacy` | empty | no | yes, under legacy budgets |

Only the resolver writes a target ID. A structured producer always starts as
`unresolved` with an empty target ID. Structured ambiguous/external/unresolved
rows never degrade to textual matching.

### V5 Relation Identity And Occurrences

Legacy callers with no structured selector retain the current legacy ID helper.
Every P5 relation uses:

```text
r5:<full 64-hex sha256(canonical-json)>
```

The canonical JSON contains:

```text
source_signal_id, kind, target_kind, target_qualified_name,
target_signature, target_arity, target_project_unit_key, producer
```

Source position is already part of the v5 source-signal ID. Two calls from the
same source signal to the same semantic selector intentionally deduplicate into
one edge. Metadata then stores `first_source_line`, `first_source_column`, and
`occurrence_count`; earliest source order wins and counts are summed before the
per-file relation cap. Different overload signatures/arity or producers cannot
collide.

## Qualified Identity

| node | qualified identity |
| --- | --- |
| module | repository-relative POSIX path |
| Java type | package plus nested type name |
| Java method | fully qualified owner plus method name; signature is erased ordered parameter FQCNs |
| Java field | fully qualified owner plus field name |
| Spring endpoint | owning method identity plus normalized HTTP method/route metadata |
| frontend route | source module, composed route path/name, and source range |
| MyBatis statement | `<namespace>#<id>` |

Java generic arguments are erased, varargs normalize to arrays, whitespace is
removed, constructors use `<init>`, and nested types use `$`. These rules are
shared by declaration and selector producers.

## Relation Kinds And Directions

| kind | source -> target | ordinary direction | weight |
| --- | --- | --- | ---: |
| `calls` | method/endpoint -> method | outgoing | 1.00 |
| `implements` | implementation type -> interface type | both | 0.95 |
| `implements_method` | implementation method -> interface method | both | 0.95 |
| `uses_type` | method/endpoint -> repository-local type | outgoing | 0.75 |
| `imports_type` | Java module -> explicitly imported Java type | association-only; never retrieval/P4 | n/a |
| `imports` | frontend module -> repository module | outgoing | 0.85 |
| `routes_to` | frontend route -> component module | outgoing | 1.00 |
| `mapped_by` | MyBatis statement -> Java mapper method | both | 0.95 |
| `tests` | test module -> production module | intent-gated both | 0.80 |
| `uses` | existing name-only evidence | legacy outgoing only | existing |

`both` stores one row. Outgoing traversal reaches the resolved target; incoming
traversal reaches the active source. Specifically, interface-to-implementation,
Java-mapper-to-XML, and production-to-test traversal use the incoming row's
source, never its target.

## Project Unit Contract

The unit key is exactly the normalized repository-relative root returned by
project-unit ownership; the repository root is `""`. Project names are display
metadata and never resolution keys.

The index persists `project_unit_topology_fingerprint`, calculated as full
SHA-256 over canonical JSON of every detected unit's root, kind, and sorted
marker paths. Adding/removing/moving `pom.xml`, `build.gradle*`, `settings.gradle*`,
`go.mod`, `Cargo.toml`, `pyproject.toml`, or package manifests can therefore
invalidate unchanged files. A fingerprint change marks graph state stale and
forces full re-extraction of all graph-eligible files, module nodes, and test
associations before readiness.

V1 has no project dependency graph:

- Java structured resolution is restricted to the source unit, even for an
  FQCN; a repository declaration in another unit is not silently selected;
- test association never crosses units;
- a frontend relative or supported `@/` import may cross a detected unit only
  when syntax resolves to one exact repository path; basename/package search
  cannot cross;
- a module exact-path selector is otherwise legal only when its producer's
  closed rule says so.

## SQLite Schema And Lifecycle

### Signal Schema Version 5

`CURRENT_SIGNAL_SCHEMA_VERSION` becomes 5. Manifest schema version 1 remains
unchanged because its serialized format does not change.

`code_signals` gains the signal fields above, including indexed
`project_unit_key`, `qualified_name`, `arity`, and `recallable`.
`code_relations` gains the structured selector, both confidence components,
resolution state, target ID, and producer.

Required active indexes cover:

- signals by `(project_unit_key, language, kind, qualified_name, deleted_at)`;
- signals by `(project_unit_key, language, kind, qualified_name, arity, deleted_at)`;
- signals by `(recallable, deleted_at)` for ordinary signal search;
- relations by `(source_signal_id, deleted_at)`;
- relations by `(target_signal_id, deleted_at)`;
- relations by `(resolution, deleted_at)`;
- the existing textual target index for `legacy` only.

There is no hard foreign key to the soft-deleted target signal. Resolver
integrity and readiness enforce active references.

Index metadata also has exact keys:

```text
graph_resolution_state = stale | ready
graph_resolution_version = 1
graph_stale_reason = <stable local code or empty>
full_reindex_required = 0 | 1
project_unit_topology_fingerprint = <full sha256>
```

`full_reindex_required=1` survives process failure and is cleared only by the
same final transaction that marks a complete full index ready.

### Schema Capability Matrix

| stored signal schema/state | query behavior | index behavior |
| --- | --- | --- |
| missing or `< 5`, state not `stale` | legacy row adapter; current signal/name-relation behavior only | acquire lock and perform full v5 rebuild |
| missing or `< 5`, state `stale` | disable all signal/relation candidates; keep lexical/path/anchor retrieval and vector only when its external/SQLite snapshot tuple validates | acquire lock and perform full v5 rebuild |
| `== 5`, `ready` | v5 signal recall plus resolved-ID graph and explicit legacy fallback | normal incremental flow |
| `== 5`, `stale` | disable all signal and relation candidates; keep lexical/path/anchor retrieval, validated vector recall, and P4 on-demand frontend fallback | if full-reindex flag is 1, rebuild all index-eligible files; otherwise force graph-eligible re-extraction and association rebuild |
| `> 5` | fail with `incompatible_signal_schema`; do not query unknown columns | refuse downgrade; never drop/recreate |

The v4 adapter introspects available columns (`PRAGMA table_info`) and supplies
defaults instead of indexing missing SQLite row keys. Future versions are never
interpreted as old versions.

Vector recall validates one logical external/SQLite tuple: immutable vector and
ID file hashes/count/dimensions, embedding identity shared by descriptor/config/
manifest, and exact active SQLite embedding IDs from the operation's read
snapshot. A mismatch while state is stale logs stable
`vector_snapshot_mismatch` and disables only vector recall for that operation;
lexical/path/anchor recall remains available. The same mismatch at `ready` is an
integrity failure, never a silent fallback or a mixed-generation score.

For any stale state, CLI commands emit exactly one stderr warning per operation:

```text
Warning: P5 graph index is stale; signal and relation evidence was skipped.
```

Library/MCP paths log the stable code `graph_index_stale`; they do not add an
undeclared warning field. `explain.graph.status` exposes the state directly.

### Full V4-To-V5 Reindex

The first v5 index is a logical full rebuild of the active index snapshot:

- rescan all eligible files;
- rebuild chunks, symbols, token rows, FTS rows, signals, producer relations,
  and vector embeddings;
- rebuild test associations and resolve all structured edges;
- retain repository configuration/embedding identity metadata only when still
  compatible.

This is required because AST output can alter chunk symbols/tokens and therefore
embedding inputs. It is not valid to preserve old chunks/vectors while replacing
only signal tables.

The v4-to-v5 signal/relation DDL transition is one SQLite transaction: drop the
v4 signal/relation tables, create the exact v5 tables/indexes, write
`signal_schema_version=5`, write graph resolution version 1, and write
`graph_resolution_state=stale`, `graph_stale_reason=schema_migration`, and
`full_reindex_required=1`, then commit. Readers see either the complete old v4
schema or the complete empty v5-stale schema, never v5 rows under metadata 4.
If the transaction fails, SQLite rolls it back to v4. Subsequent extraction is
outside this DDL transaction but remains hidden from graph retrieval by v5-stale.

### Exclusive Indexing And Recovery Protocol

One repository-wide exclusive index lock covers schema detection through the
final readiness commit. A second indexer fails with the existing lock/busy
operation error; it never runs a competing resolver.

The exact write protocol is:

1. acquire the exclusive lock;
2. read schema, entry readiness, `full_reindex_required`, project topology, and
   changed/deleted files without mutating graph data; reject a future schema;
3. if the full-reindex flag is zero, schema/topology/files are unchanged, and
   entry state is ready, run readiness integrity checks; only a successful
   check may release the lock without changing readiness or running a resolver;
4. otherwise set `graph_resolution_state=stale` and commit it before the first
   graph-relevant write;
5. for schema migration, perform the atomic v4-DDL/metadata-to-v5-stale
   transaction above before extraction;
6. if schema migration or `full_reindex_required=1`, ignore every source hash
   and rebuild every index-eligible source record, chunk, token/FTS row, vector,
   signal, and relation, including correct zero-chunk handling for empty files;
   otherwise, topology change, stale-on-entry, or failed no-op integrity ignores
   hashes for every graph-eligible file while ordinary changed/deleted handling
   still covers non-graph files;
7. construct the complete next vector set—fresh for a full rebuild, or a
   validated prior generation plus canonical removals/upserts for incremental—
   and write/fsync/read-validate new immutable generation files without
   switching the published descriptor;
8. for each file, persist chunks/embedding identity, signals, and producer
   relations first; persist that source file's new hash last;
9. process deletions;
10. resolve every producer relation in one deterministic resolver transaction;
11. regenerate all test associations from the now-resolved imports/types, even
   if the current run reports no newly changed test file;
12. resolve the generated `tests` relations in a second deterministic resolver
   transaction;
13. while SQLite remains stale, atomically switch the one vector descriptor,
   atomically write config/manifest, reread them, and validate the logical tuple
   above; write no external artifact after readiness;
14. in one final transaction validate all active targets, counts, topology
   fingerprint, schema version, and full-rebuild completeness, then set graph
   resolution version 1, clear stale reason, set `full_reindex_required=0`, and
   set state `ready`;
15. release the lock.

If any chunk, vector, signal, relation, association, resolver, or validation
write fails, the operation fails and leaves state stale. Because the source
hash is last and stale-on-entry forces complete graph-eligible extraction, a
later run cannot skip a partially written file or association and incorrectly
mark it ready. If failure occurs after v5 DDL or anywhere in the mandatory full
rebuild, the persisted full-reindex flag additionally forces all index-eligible
files—not only graph-eligible files—to rebuild again.

A fault before or rolled back from the final readiness commit leaves stale. A
fault after an acknowledged successful commit leaves one complete ready/full=0
snapshot whose external tuple validates and whose next index is a verified
no-op. If process termination makes the commit result unknowable, restart may
observe complete stale or complete ready, never partial-ready, and follows the
corresponding recovery/no-op branch.

If a normal ready incremental run changes any file, all structured relations
are re-resolved. If no file/deletion/topology/schema change exists and state is
ready, the full-reindex flag is zero, and the no-op integrity check succeeds,
both resolution stages are skipped.

### Resolver Integrity

The resolver sorts by source unit, source path/range, kind, canonical selector,
and relation ID. It clears old target IDs before reclassification. A uniqueness
query fetches at most two rows. The final readiness transaction proves:

- every exact/unique relation has one active target;
- no other state has a target ID or resolution confidence;
- source and target units obey the producer rule;
- every active producer relation belongs to an active source signal;
- every eligible non-empty active file has one module signal;
- test associations were generated after the producer-resolution generation;
- persisted topology fingerprint equals the current scan.

## Repository Target Resolution

Resolution applies these rules in order:

1. An exact module path resolves only to its active core module signal.
2. Qualified name plus normalized signature resolves exact only when one active
   target matches language, kind, unit, qualified name, and signature.
3. Owner/name/arity resolves unique only when one active target exists in the
   legal unit.
4. Java explicit imports, same-package types, and wildcard imports only narrow
   candidates inside the same unit. Wildcards require one candidate.
5. Frontend imports with an explicit suffix resolve that exact regular file.
   Extensionless and directory-index forms resolve only when the complete
   supported candidate set contains exactly one active file. The existing
   preference order never selects among `view.ts`, `view.js`, or multiple index
   candidates.
6. JDK/framework/npm/package-only or provably out-of-repository selectors are
   external.
7. Zero legal repository targets is unresolved; two legal targets is ambiguous.

Resolution confidence is closed:

| basis | state | confidence |
| --- | --- | ---: |
| exact repository path | `resolved_exact` | 1.00 |
| exact qualified Java signature | `resolved_exact` | 1.00 |
| owner/name/arity unique in unit | `resolved_unique` | 0.90 |
| MyBatis namespace + ID unique mapper method | `resolved_unique` | 0.90 |
| MyBatis namespace + ID + exact parameter signature | `resolved_exact` | 1.00 |
| explicit resolved test import | `resolved_exact` | 1.00 |
| exact mirrored/sibling test path | `resolved_exact` | 0.95 |

## Java And Spring AST Producer

### Ownership And Fallback

`JavaPlugin` becomes a coordinator. A Java AST module owns parsing, scope facts,
and normalized identities; Spring interpretation and edge construction remain
plugin responsibilities. Retrieval core never imports parser nodes.

On an error-free relevant parse, AST output is authoritative for structural
facts. Existing comments/JavaDoc, lexical tokens, endpoints, enums, constants,
and annotation SQL must match protected fixtures before the regex structural
path is retired.

If any `ERROR` or missing node occurs anywhere in the Java compilation unit,
including package/import, type, field, local declaration, annotation, method,
or call syntax, the whole file uses the current legacy extractor, records
`graph_parse_status=legacy_fallback`, and emits no structured Java edge. Legacy
relations are labeled `legacy`; AST and regex identities are never mixed in one
file.

### Facts And Fixed Per-Node Caps

The producer extracts package/imports, top-level/nested classes/interfaces/
enums/records, inheritance, methods/constructors, fields, parameters, typed
locals, bounded annotations/literal arguments, invocations/constructor calls,
Spring routes, constants/enums, and annotation SQL.

Per declaration it keeps at most:

- 256 explicit Java import facts per file;
- 32 annotations;
- 16 literal arguments per annotation and 256 UTF-8 bytes per literal;
- 128 call occurrences before semantic-edge deduplication;
- 8 `uses_type` targets;
- 4,096 UTF-8 bytes of annotation SQL tokens.

Earliest source order wins and omitted counts are recorded. Comments and string
literals never become declarations, calls, imports, or annotations.

### Lexical Binding And Type Canonicalization

Receiver binding uses an explicit lexical scope stack:

1. innermost local declaration preceding the call;
2. method/constructor parameter;
3. owning type field;
4. outer lexical scope only when not shadowed.

`this.x` selects a field. A bare identifier follows the order above. A static
type-name receiver is allowed only after exact FQCN canonicalization. Duplicate
or unresolved declarations at the winning scope fail that relation closed.
Lambdas, anonymous classes, and nested types create their own scopes and retain
the nearest owning method/type.

A simple type becomes an FQCN only from an exact explicit import, exact
same-package declaration, exact nested type, or a unique same-unit wildcard
candidate. `java.lang`/JDK and known framework types can be classified external
but never linked to repository lookalikes. No global basename selection exists.

Exact overload argument evidence is allowed only when every argument type is
proven by one of:

- a bound field, parameter, or local with an exact declared FQCN;
- `new ExactType(...)`;
- an explicit cast to an exact FQCN.

Raw literals, `null`, lambdas, method references, generic type variables,
chained return values, and unresolved expressions do not establish an exact
signature. P5 performs no subtype, widening, boxing, varargs applicability, or
generic inference. Otherwise owner/name/arity can resolve only if unique;
same-arity overloads remain ambiguous.

### Java Edges

The producer emits:

- `implements` from implementing type to exact interface selector;
- `implements_method` from implementation method to an interface method with
  an exact normalized declaration signature;
- `calls` from owning method/endpoint to the closed receiver/method selector;
- `uses_type` from a method/endpoint to exact repository-local types appearing
  in its return type, parameters, referenced fields, explicitly typed locals,
  and direct `new ExactType` expressions;
- `imports_type` from the file's core module to each explicit, non-wildcard Java
  type import. This is a persisted/re-resolved association fact, not a retrieval
  edge; ordinary expansion and P4 always exclude it.

`uses_type` excludes primitives, arrays of excluded primitives, type variables,
JDK/Jakarta/Javax/Spring/framework types, and external dependencies. It is
outgoing only, has weight 0.75, and keeps at most eight distinct targets per
method in first-use order. This is the verified edge used for DTO/domain
acceptance; related types are not accepted from text co-occurrence alone.

Controller-to-service is a normal resolved `calls` edge with framework role
metadata, not a special relation kind.

### Framework Annotation Identity

Framework roles are recognized only after annotation identity resolves through
an exact FQCN or an explicit import binding. Simple-name coincidence is
insufficient. The v1 allowlist is:

- `org.springframework.stereotype.Controller`;
- `org.springframework.web.bind.annotation.RestController`;
- `org.springframework.stereotype.Service`;
- `org.springframework.stereotype.Repository`;
- `org.springframework.stereotype.Component`;
- `org.apache.ibatis.annotations.Mapper`;
- `org.springframework.beans.factory.annotation.Autowired`;
- the six Spring mapping annotations under
  `org.springframework.web.bind.annotation`.

MapStruct or user-defined `@Mapper`, `@Service`, and `@Route` annotations do not
receive Spring/MyBatis roles. Class and method literal routes compose as today;
non-literal annotation values remain diagnostic metadata only.

## MyBatis XML Producer

Only bounded XML whose root is `<mapper namespace="...">` enters this producer.
Other XML keeps generic indexing.

Standard MyBatis mapper files commonly contain a DOCTYPE. The safe protocol is:

1. scan the bounded bytes before XML parsing;
2. reject any `<!ENTITY`, entity reference other than the five predefined XML
   entities, XInclude element, internal subset (`[` inside DOCTYPE), parameter
   entity, or more than one DOCTYPE;
3. accept no DOCTYPE, or exactly `mapper` with public ID
   `-//mybatis.org//DTD Mapper 3.0//EN` and system URL
   `https://mybatis.org/dtd/mybatis-3-mapper.dtd` or the legacy `http` form;
4. replace that validated declaration with equal-length ASCII whitespace while
   preserving every newline, without fetching it;
5. parse with `defusedxml.ElementTree.fromstring`; never call external
   resolution or XInclude processing.

This accepts the official header while remaining fail closed for XXE and entity
expansion.

Because ElementTree does not provide stable source positions, a separate
bounded XML-aware byte lexer locates ranges; generic text search is not used.
The lexer tracks tag nesting and quoted `>` characters, skips comments, CDATA,
processing instructions, and the already validated whitespace DOCTYPE range,
and records each recognized direct child of `<mapper>` from its opening `<` to
the matching closing `>`/end tag. It derives zero-based UTF-8 byte columns and
original line numbers from the unmodified bytes.

The parsed direct-child `(local_tag, literal_id)` sequence must match the lexed
sequence one-for-one. A mismatched sequence, unbalanced/nested locator state,
duplicate statement ID in one namespace, or missing chunk for a start line
fails the whole MyBatis graph producer closed while generic indexing remains.
Each accepted statement signal uses the lexed exact range and attaches to the
active chunk containing its start line, so a statement late in a long mapper
does not point to the first chunk.

The closed statement tags are `select`, `insert`, `update`, and `delete` with a
literal `id`. Each yields a non-recallable `mybatis_statement` signal named
`<namespace>#<id>` and a `mapped_by` selector to Java owner `namespace`, method
`id`. `parameterType` contributes an exact signature only when every type can be
canonicalized; otherwise namespace+ID can resolve only as unique at 0.90.

Bounded SQL text and `parameterType`/`resultType` attributes contribute lexical
tokens; dynamic SQL control flow, includes, result maps, schemas, and SQL-to-
entity semantics are not interpreted.

Mapper XML is assigned existing ContextPack group `implementations` and existing
role `repository`; no serialized role/group is added.

## Frontend Route And Import Producer

### Parsing And Vue Included Ranges

`.js`, `.jsx`, `.ts`, and `.tsx` use their matching grammar. A bounded HTML
start-tag lexer discovers top-level Vue `<script>` and `<script setup>` ranges,
honors quoted `>` characters and HTML comments, rejects overlap/unclosed tags,
and preserves original byte/line offsets. It does not search with a regex that
can be fooled by template text. `lang="ts"` uses TypeScript; default uses
JavaScript.

If an import/route subtree has a parse error, no persistent frontend graph edge
is emitted from that file. The module remains. The current static-import regex
may still support P4's explicitly legacy on-demand probe fallback, but it never
creates a v5 relation because comments/strings/template literals can fool it.

### Static Module Edges

AST extraction supports:

- default, named, namespace, and side-effect static imports;
- `export { ... } from "..."` and `export * from "..."` re-exports;
- literal dynamic imports only when used directly by an accepted route form.

Resolved static imports/re-exports emit `imports` from importer module to exact
module. Relative and existing `@/` paths use the uniqueness rule above. Bare
packages are external. Computed imports, interpolation, arbitrary aliases, and
repository escapes are unresolved and non-traversable.

### Vue Router

Vue routes are accepted only when:

- `createRouter` is an unshadowed binding imported from `vue-router`; and
- the call's `routes` value is an inline array or one local const initialized
  by the literal array; and
- each route object has a literal `path` and a component that is either an
  identifier bound by an exact static import or a direct literal dynamic import.

Path-classification alone is not framework evidence. Spreads, mutation,
`addRoute`, factory wrappers, and unresolved/shadowed bindings are ignored.

Nested child paths compose deterministically: an absolute child replaces the
parent; a relative child joins with one slash; an empty literal child retains
the parent; `index: true` without a literal path, `.`/`..`, interpolation, and
non-literals are rejected. The composed
path is stored on the route signal.

### React Router

`Route`, `createBrowserRouter`, and `useRoutes` must be unshadowed named import
bindings from `react-router` or `react-router-dom`. The closed forms are:

- `<Route path="..." element={<ImportedComponent />} />`;
- `<Route path="..." Component={ImportedComponent} />`;
- literal object arrays passed directly, or through one local const, to
  `createBrowserRouter`/`useRoutes`, with literal `path` and imported
  `element`/`Component` or direct literal lazy import.

Nested paths compose by the same rule as Vue. Custom components named `Route`,
shadowed APIs, wrappers, computed paths, and runtime mutation produce no edge.

Each accepted route emits a non-recallable `route` signal and `routes_to` edge. The
normal forward path is route -> page/view module -> imported module.

## Generic Test Association

The association pass runs after producer relations are resolved and before its
own resolution pass. It stores one direction:

```text
test module --tests--> non-test production module
```

Targets must be active, same-unit, non-test, non-generated, and outside fixture,
snapshot, golden, test-data, and generated directories. Test-to-test edges are
always forbidden.

### Closed Conventions

| language | anchored test name | exact production rule |
| --- | --- | --- |
| Java | `FooTest`, `FooTests`, `FooIT`, `FooITCase` | Java rewrite below, or explicit resolved FQCN import |
| Go | `foo_test.go` | Go rewrite below |
| Rust | `foo_test.rs`, `foo_tests.rs`, or unit-root `tests/**/*.rs` | Rust rewrites below |
| Python | `test_foo.py`, `foo_test.py` | Python rewrites below |
| JS/TS | `foo.test.*`, `foo.spec.*` | JS/TS rewrites below, or explicit resolved import |

All rewrites operate on the path relative to `project_unit_key`. They generate a
complete set of exact POSIX candidate paths first, discard non-active/forbidden
targets, deduplicate paths, and create a convention edge only when exactly one
candidate remains. Table order never selects a winner.

| language | exact candidate generation |
| --- | --- |
| Java | Require the exact prefix `src/test/java/`; replace it once with `src/main/java/`; strip exactly one longest anchored stem suffix in order `ITCase`, `Tests`, `Test`, `IT`; append `.java`. No other source root is tried. |
| Go | In the same directory, strip the anchored `_test` from the stem and append `.go`. |
| Rust | For anchored `_tests`/`_test`, strip the longest suffix and try the same directory. Separately, when the path is below the unit-root `tests/`, replace that one leading segment with `src/` and keep the remaining directories/stem. The union must be unique. |
| Python | For each independently matching anchored `test_` prefix and `_test` suffix, generate one stem with only that side removed; take their union and never recursively strip again. Thus `test_foo_test.py` produces stems `foo_test` and `test_foo`, not `foo`. If below unit-root `tests/`, generate exactly `<unit>/<remaining-dirs>/<stem>.py` and `<unit>/src/<remaining-dirs>/<stem>.py` for every stem; do not try a file inside `tests/`. Otherwise generate only same-directory siblings. The complete union must be unique. |
| JS/TS | Strip one final `.test` or `.spec` from the pre-extension stem. If the path contains one `__tests__` segment, remove that segment; else if below unit-root `tests/`, generate both unit-root and `src/` replacements; otherwise use the same directory. For every generated base, enumerate the complete suffix set `.ts`, `.tsx`, `.js`, `.jsx`, `.vue`; exactly one active non-test path must remain. |

More than one `__tests__` segment, a non-leading Python/JS `tests` directory,
an empty normalized stem, or a path containing `.`/`..` produces no convention
candidate. Explicit imports remain separate higher-confidence evidence.

Java matching operates on the complete original stem, so `Contest.java` is not
a test and `FooTests.java`/`FooITCase.java` are. Go/Rust/Python have no P5 AST
symbol producer, so raw tokens or comment/string references never strengthen a
basename match. There is no generic symbol-evidence fallback.

Explicit resolved imports may yield up to eight production targets. A
convention rule yields at most one. Multiple exact candidates mean no relation;
extension order and lexicographic order do not decide.

Here, an explicit frontend import means a producer `imports` row already
resolved in stage one. An explicit Java import means a resolved, persisted
`imports_type` fact; the association pass maps that type's source file to its
module signal. Because the fact survives unchanged-file runs, rebuilding all
associations never depends on an in-memory AST from only the current change
set. Go/Rust/Python imports are not interpreted in v1.

Ordinary traversal enables `tests` only when existing `infer_query_intent()`
returns its exact `test` intent; P5 adds no second vocabulary. P4 may reverse a
test edge only for an already-frozen unsatisfied test goal or explicit test
intent.

## Relation Expansion

The existing `relation_candidates()` stage remains the only owner. It receives
the normalized existing test intent but no new retrieval stage is added.

### Frontier And State Rules

Initial frontier signals come from already admitted seed candidates, ordered by
seed rank, source priority, file path, signal range, and signal ID, capped at
512. For every admitted seed chunk, expansion batch-loads both signals attached
to that chunk and the one core module signal selected by the chunk's
`file_path`, even when the module is attached to another/first chunk. The module
is deduplicated by signal ID and participates in the same 512 ordering/cap.
Other non-recallable nodes enter only through their overlapping admitted chunk
or a resolved edge, never ordinary signal search. This file-level module
promotion is what makes module-source imports/test edges reachable after a hit
in a long file's second or later chunk.

At schema 5 ready:

1. resolved outgoing edges map to the active target signal/chunk;
2. resolved incoming edges map to the active source signal/chunk;
3. only explicit `legacy` rows enter textual target matching;
4. ambiguous/external/unresolved rows are ignored;
5. tests obey exact intent/P4-goal gating;
6. direct protected candidates reached by graph are returned unchanged: no
   graph score, score part, reason, evidence priority, or sort key is merged.

"Protected direct" means the existing ranking class `original_direct` (the
current strong-original-evidence predicate, which becomes
`evidence_priority == 0`). Expansion applies that same predicate before merge;
it does not invent a second protection definition.

Any stale state skips all signal/relation candidates. Schema <5 in a non-stale
legacy state uses only legacy behavior. Future schema fails before retrieval.

### Scores And Visibility

For a resolved hop:

```text
next_score = current_score * effective_confidence * kind_weight * 0.8
```

Graph candidates use these adjustment-visible keys:

- `graph_calls_match`;
- `graph_implements_match`;
- `graph_uses_type_match`;
- `graph_imports_match`;
- `graph_routes_to_match`;
- `graph_mapped_by_match`;
- `graph_tests_match`.

Exactly one graph-kind `_match` key is nonzero on a resolved graph candidate:
its value is the clamped `next_score`, and `_combined_score()` adds the maximum
of the closed graph-kind keys exactly once. Since only the best path key is
retained, the raw `_match` value is the actual additive pre-normalization score
contribution exposed by `final_selection[].adjustments`.

Resolved candidates do not also set numeric `relation`, `original_relation`, or
`planner_relation`; doing so would double-count the same hop. Instead they carry
non-scoring provenance flags `resolved_relation=1`, plus exactly one of
`graph_seed_original=1` or `graph_seed_planner=1`, and the existing evidence-
class logic maps those seed flags to the current original/planner relation
priority. The existing numeric aggregate channels and scoring remain unchanged
for explicit `legacy` candidates only.

Every existing relation-provenance consumer is updated consistently without
making the flags additive: rank-tier relation support recognizes
`resolved_relation`; original/planner evidence predicates use the corresponding
`graph_seed_*` flag; span/trace source mapping reports the existing `relation`
source; and relation-support reasons recognize any closed graph-kind key. No
consumer tests only the legacy numeric fields after P5.

RetrievalTrace remains version 1. `TraceCandidate` previews do not contain score
parts and therefore expose only their existing source labels/counts. Graph
adjustments appear on selected results through existing
`final_selection[].adjustments` because the new names end in `_match`; existing
bounded final reasons carry the human explanation. Exact edge IDs and neighbour
lists are available only through `explain`.

### Complete Deterministic Dominance

A path is ordered by the full tuple:

1. higher resulting score;
2. fewer hops;
3. higher minimum confidence;
4. closed relation-kind priority in the table above;
5. outgoing before incoming;
6. source signal ID, target signal ID, then chunk ID.

The frontier records the best complete tuple per signal. A signal is revisited
only when a new tuple is strictly better, including an equal-score path with
fewer hops or better later tie-break. Frontier truncation, candidate truncation,
and final best-path selection use this same ordering, so arrival/SQLite order
cannot change reasons.

### Structural Work Budgets

| budget | limit |
| --- | ---: |
| graph-capable file bytes | existing `index.max_file_bytes` |
| signals per file, including module | 4,096 |
| producer relation candidates per file | 8,192 |
| frontend imports/re-exports per file | 64 |
| routes per router file | 128 |
| test targets per file | 8 |
| graph seed signals | 512 |
| resolved graph hops | 4 |
| legacy relation hops | existing 3 |
| edges per signal per direction | 64 |
| signals popped per query | 4,096 |
| edges examined per query | 16,384 |
| frontier entries created per query | 8,192 |
| relation-expanded candidates | existing 1,000 |
| explain signals/outgoing/incoming | 32 each |

Edge SQL queries request `LIMIT 65` after canonical ordering, retain 64, and
record truncation; they do not load unbounded adjacency into Python. Once any
global work cap is reached, traversal stops after the current canonical item and
returns the already ordered prefix. High-degree, many-signals-per-chunk, cyclic,
and repeated-improvement fixtures must prove the caps.

Four resolved hops are separate from the legacy depth of three. They cover the
controller -> service interface -> implementation -> mapper -> XML chain; P4
still inspects only one graph hop.

### Reasons

An affected non-protected final result gets at most one best-path graph reason:
`resolved Java method call`, `Spring interface implementation`,
`repository-local related type`, `frontend route target`, `frontend import
dependency`, `MyBatis mapper statement`, or `associated test module`. Existing
reason caps apply.

## ContextPack And P4

ContextPack remains schema version 2 and I/O-free. Graph results pass through
normal item, excerpt, content, and byte budgets. Mapper XML uses existing group
`implementations` and role `repository`.

The ready-v5 retrieval operation records this classification as one private,
defaulted, non-comparing `RetrievalResult` hint only when the same read snapshot
contains an accepted active `mybatis_statement` signal for that file. ContextPack
role normalization consumes the hint in memory with existing classification
basis `content`; it does not reopen SQLite, reparse XML, infer from a suffix or
basename, add a score part, or serialize the hint. Legacy/stale/rejected mapper
and ordinary XML results carry no hint and retain their existing role.

The exact additive internal field is:

```python
_context_role_hint: str | None = field(default=None, repr=False, compare=False)
```

Its closed values are `None` and `"mybatis_repository"`. It is populated when
the final `RetrievalResult` is first assembled, never by mutating or merging a
protected direct result. Existing explicit serializers omit it; dataclass
equality, score parts, reasons, spans, ordering, and traces ignore it. Standard
`deepcopy`/`dataclasses.replace` used by exploration must preserve it so fused
ContextPacks do not lose a proven mapper role.

P4 remains one initial round and at most two sequential probes/three total
retrieval calls. Goals, planner-off follow-ups, fusion, stop rules, ContextPack
v2, ExplorationTrace v2, and feedback projection stay unchanged.

When graph state is ready, the grounded seed collector reads at most one
eligible hop from initially selected origin signals. As in ordinary expansion,
each selected origin chunk additionally promotes its owning file's core module,
deduplicated and within the existing P4 seed cap; this applies even when the
selected chunk is not the first chunk. For an outgoing row the neighbour is the
resolved target; for an incoming row the neighbour is the active source.
Resolved imports map to existing `static_import`; other kinds map to existing
`relation_target`. Edge kind remains internal for route/test goal gating; source
enums do not change.

Ambiguous, external, unresolved, stale, and out-of-scope edges never seed a
probe. When stale or legacy, P4 retains its current bounded on-demand frontend
import fallback. It adds no repository read, round, probe, or model-planner call.

## Public Operations And Explain

No top-level operation or configuration is added. Ready graph data applies to
library `query_repository()`, `trace_repository()`, and `explore_repository()`;
CLI query/context/trace/explore; and matching MCP tools.

### MCP Explain Contract

Successful MCP explain changes from top-level `{ok, repo, chunk}` to the exact
ordered keys `{ok, repo, chunk, graph}`. Existing `chunk` is byte-compatible.
`graph` always has these ordered keys:

```json
{
  "status": "ready",
  "schema_version": 5,
  "signals": [],
  "outgoing": [],
  "incoming": [],
  "omitted_signal_count": 0,
  "omitted_outgoing_count": 0,
  "omitted_incoming_count": 0
}
```

`status` is `legacy`, `stale`, or `ready`; a future schema returns the normal
`incompatible_signal_schema` error instead. Legacy/stale arrays are empty and
omitted counts are zero. `schema_version` is the stored integer signal schema;
missing metadata renders as JSON integer `0`.

For ready state, the explain signal universe is the union of every active signal
attached to the selected chunk and the selected chunk file's owning core module
signal, even when that module is attached to the first/another chunk. IDs are
deduplicated before sorting. `signals` is the first 32 of that complete universe.
`outgoing` is the first 32 active relations whose source is in the complete
universe, including diagnostic non-traversable states/facts; `incoming` is the
first 32 resolved active relations whose target ID is in the universe. Each
omitted count is computed against its corresponding complete pre-cap set. Thus
explain for a long file's later chunk shows the same module-level import/reverse-
test neighbourhood that retrieval and P4 can actually use.

Signal item ordered keys are:

```text
signal_id, kind, name, qualified_name, producer,
start_line, end_line, recallable
```

Edge item ordered keys are:

```text
relation_id, kind, direction, confidence, producer_confidence,
resolution_confidence, resolution, source_signal_id, source_name,
target_signal_id, target_name, target_path
```

`resolution_confidence` is JSON null when absent; unresolved `target_signal_id`
and `target_path` are empty strings. Signals/edges sort by range/kind/ID and
direction/kind/source/target/ID, respectively. Caps are 32 each with exact
omitted counts. No new source excerpt is returned.

### CLI Explain Contract

Existing lines remain unchanged and are followed by:

```text
Graph: ready (signal schema 5)
Graph signals: N (omitted M)
Graph outgoing: N (omitted M)
Graph incoming: N (omitted M)
```

For ready state, each bounded signal then renders as
`Signal: <kind> <qualified-or-name> [<producer>] <start>-<end>` and each edge as
`Outgoing:`/`Incoming: <kind> <resolution> <source> -> <target> (<confidence>)`.
Legacy/stale render only the four summary lines. Exact golden tests own spacing,
ordering, null/empty rendering, and caps.

## Error And Fallback Semantics

- Any Java compilation-unit `ERROR` or missing node: whole-file legacy
  structural extraction; no structured edge.
- Frontend relevant parse failure: module only; no persistent import/route
  edge; P4 may use its legacy on-demand fallback.
- MyBatis safe-parse failure: generic chunks/module only; no statement/edge.
- Ambiguous/external/unresolved: expected persisted states, never operation
  errors and never traversal evidence.
- DB/vector/resolver/invariant failure: index operation fails and remains stale.
- Missing resolved target at query time in a state marked ready: stop graph use
  for the rest of that operation and attempt one short SQLite transaction that
  sets state `stale` plus stable marker `dangling_target`. If the database is
  read-only/busy, log the marker in-process and continue only lexical/vector/path
  fallback. Every otherwise no-op index command re-runs readiness integrity
  before exiting, so it discovers the same dangling edge and enters stale
  recovery even when the query could not persist the marker. Never synthesize a
  text target.
- Future schema: explicit incompatibility error and no destructive downgrade.

## Security And Privacy

### Repository And Parser Safety

Before reading a candidate, the scanner:

- rejects a file or any below-root path component that is a symlink;
- resolves the repository and candidate strictly and proves the candidate is
  below the resolved repository root;
- then applies existing ignore, regular-file, binary, and byte-size rules.

External-file symlinks, internal symlink chains, broken links, and paths that
escape after resolution are not indexed. Tests cover a repository link to an
outside file and a linked-directory chain.

Parsers run locally over bounded bytes. Vue included ranges cannot read another
file. Frontend targets must resolve to scanned regular repository files. MyBatis
uses the closed DOCTYPE/entity protocol and never fetches resources.

### Remote Disclosure Contract

P5 adds no network client or new remote model/planner call. It does not send AST
objects, relation rows, explain payloads, or parser diagnostics as separate
remote payloads.

Existing configured embedding behavior still applies and must be described
honestly:

- a remote embedding provider receives source chunk text during indexing;
- the mandatory v5 full reindex can resend all active source chunks;
- query/explore sends normal query text, and P4 follow-up probe text can contain
  graph-derived names or paths even though the query planner stays off;
- graph metadata is not separately serialized to the embedding provider;
- existing P4 feedback remains bounded and does not persist relation/signal IDs
  or graph paths.

With the local hash provider used by deterministic gates, none of this leaves
the machine. P5 makes no broader privacy claim.

## Quality Contract

P5 adds two named profiles and never edits protected P0-P4 catalog bytes.

### Deterministic Profile: `p5_language_graphs`

Catalog:

```text
tests/fixtures/retrieval_quality/p5_language_graphs.json
```

Exact configuration:

- hash provider, model `hash-v1`, 384 dimensions;
- query planner disabled and no remote settings;
- `final_top_k=12`;
- context `max_items=12`, `max_context_bytes=65536`;
- exploration uses P4's fixed maximum of three retrieval calls and 65,536 pack
  bytes.

The catalog declares exactly five local snapshot repos:

- `p5_java_spring` -> `tests/fixtures/p5-language-graphs/java-spring`, containing
  `OrderController.java`, `OrderService.java`, `DefaultOrderService.java`,
  `OrderMapper.java`, `Order.java`, `OrderDto.java`,
  `resources/mappers/OrderMapper.xml`, `OrderControllerTests.java`, one unrelated
  test, one same-arity overload pair, and a nested-marker duplicate unit;
- `p5_vue` -> `tests/fixtures/p5-language-graphs/vue`, containing
  `src/router/index.ts`, `src/views/OrdersView.vue`,
  `src/services/orderService.ts`, `src/stores/orderStore.ts`,
  `src/types/order.ts`, and an `Ambiguous.ts`/`Ambiguous.js` tie;
- `p5_react` -> `tests/fixtures/p5-language-graphs/react`, containing
  `src/routes.tsx`, `src/pages/OrdersPage.tsx`,
  `src/services/orderService.ts`, and `src/types/order.ts`;
- `p5_generic_tests` -> `tests/fixtures/p5-language-graphs/generic-tests`, with
  one positive and one forbidden negative for each declared language;
- `p5_malformed_compat` ->
  `tests/fixtures/p5-language-graphs/malformed-compat`, with malformed
  Java/frontend/XML plus a frozen standalone no-edge case.

The profile inventory is exactly 12 required cases:

| ID | repo/mode | exact query | required proof |
| --- | --- | --- | --- |
| `java-owner-flow-results` | Java/results | `OrderController create order business flow` | the seven declared controller/interface/implementation/mapper/XML/domain/DTO paths in top 12 |
| `java-owner-flow-context` | Java/context_pack | same query | the same seven paths within 12 items/65,536 bytes |
| `java-owner-test` | Java/results | `OrderController tests` | `OrderControllerTests.java` present; unrelated and duplicate-unit tests absent |
| `java-overload-ambiguous` | Java/results | `OverloadCaller same arity dispatch` | caller present; neither overload declaration admitted solely by the ambiguous edge |
| `java-duplicate-unit` | Java/results | `OrderController service implementation` | main-unit service present; nested-marker duplicate absent |
| `vue-route-flow` | Vue/results | `orders route view service store type` | the five declared router/view/service/store/type paths in top 12 |
| `vue-route-exploration` | Vue/exploration | `orders page route type` | under the profile's fixed top-12 config, router and type are declared `initial_absent`, both are final-present after <=3 calls, zero lock-file noise |
| `react-route-flow` | React/results | `orders react route page service type` | all four declared paths in top 12 |
| `frontend-ambiguous-import` | Vue/results | `AmbiguousImporter exact dependency` | importer present; both tied target files absent as graph-only hits |
| `generic-test-conventions` | generic/results | `tests for cross language payment modules` | all six declared positive test/production pairs represented in top 12; every forbidden path absent |
| `malformed-fallback` | malformed/results | `MalformedUniqueLexicalToken` | direct lexical file first; no parse-derived neighbour |
| `no-legal-edge-compat` | malformed/results | `StandaloneUniqueToken` | exact frozen normalized result projection equals pre-P5 output |

All 12 must pass; no percentage threshold substitutes for a case.

Quality profile validation is extended by an exact allowlist, not a prefix
rule. `p5_language_graphs` and `p5_real_language_graphs` require hash-v1/384,
planner disabled, and no remote settings. Their selected cases may use
`results`, `context_pack`, or `exploration`; existing P4 profiles still require
exploration-only cases, and no other profile gains exploration permission.

### Structural Projection Gate

`tests/test_p5_graph_contract.py` loads the synthetic repositories directly,
indexes them twice, and compares canonical store projections with committed
files under:

```text
tests/fixtures/p5-language-graphs/expected/*.json
```

The projection includes schema/readiness/topology fingerprint, stable v5 signal
identity fields, relation selector/state/target/both confidence components,
occurrence metadata, truncation counts, and exact module/test invariants. It
excludes row order, timing, absolute paths, vector floats, and parser objects.
This gate—not `QualityCase`—proves graph structure, ambiguity, incoming source
semantics, failure recovery, and no forbidden edge.

The companion `tests/test_quality_p5.py` inspects raw selected result score
parts in addition to catalog path expectations: the Java flow must contain at
least one `Order.java`/`OrderDto.java` result with
`graph_uses_type_match > 0`, route cases must contain
`graph_routes_to_match > 0`, and mapped XML must contain
`graph_mapped_by_match > 0`. Ambiguity cases must have no target carrying a
resolved graph `_match` key. This prevents textual co-occurrence from satisfying
a graph acceptance case.

### Real Profile: `p5_real_language_graphs`

Catalog:

```text
tests/fixtures/retrieval_quality/p5_real_language_graphs.json
```

The opt-in profile has the same local hash/planner settings, `final_top_k=12`,
and exactly two required cases:

1. pinned Spring PetClinic commit
   `51045d1648dad955df586150c1a1a6e22ef400c2`, case ID
   `petclinic-owner-graph`, query
   `OwnerController owner flow repository domain tests`: the final exploration
   pack must contain `OwnerController.java`, `OwnerRepository.java`,
   `Owner.java`, and `OwnerControllerTests.java` within 12 items, <=3 calls, and
   65,536 bytes;
2. committed `tests/fixtures/real_projects/program_tool`, case ID
   `program-tool-qrcode-graph`, query `QRCode page route service type`: the final
   exploration pack must include `src/router/index.ts` plus at least two of its
   declared QRCode page/service/type targets, exclude `package-lock.json` and
   `pnpm-lock.yaml`, use <=3 calls, and stay within 65,536 bytes.

The catalog pins repository identity, selected-case inventory, and expected
paths. No live fast-context service is a gate.

### Protected Compatibility Gates

Acceptance also requires:

- raw CI 8/8, P2 5/5, deterministic P4 4/4;
- non-empty protected P3/P4 trace coverage 1.0;
- protected catalogs and inventories byte-identical;
- P4 call/privacy/schema/budget tests exact;
- exact endpoint/path/symbol cases retain the same top direct candidate and
  direct score parts;
- cases with no legal P5 edge retain byte-identical normalized output;
- every allowed existing-case change appears in one reviewed allowlist with
  before/after edge evidence;
- full suite passes with audited skip/xfail counts;
- Phase 1 remains separately 6/7.

P5 records index/query timings diagnostically but sets no p95 target; that is P6.

## Testing Strategy

### Identity, Store, And Lifecycle

- same-line overload signals and selector-different relations have distinct v5
  IDs; a generated short-hash collision cannot merge v5 rows;
- semantic duplicate calls merge with exact first location/count;
- v4 row adapter reads missing columns; v4 index rebuilds fully; v6 is rejected
  without table mutation;
- concurrent reads/fault injection around the atomic v4-DDL/metadata transition
  observe only v4-complete or v5-stale, never mixed rows; failure after that
  commit leaves `full_reindex_required=1` and rebuilds every eligible file;
- rollback-journal readers keep one SQLite snapshot; writer commit waits for an
  existing reader, and descriptor/config/manifest interleavings either validate
  one exact vector tuple or skip vector with `vector_snapshot_mismatch` while
  stale—never mix an ID file, matrix, or SQLite generation;
- root unit `""`, topology fingerprint changes, and cross-unit restrictions;
- exclusive-index lock contention;
- fault injection after chunks, vectors, signals, producer relations, first
  resolver, test association, and final validation; next run re-extracts and
  cannot report ready with missing data;
- stale-on-entry rebuilds associations even with no newly changed files;
- deleted targets reclassify and no ready edge references inactive signals.

### Java And XML

- grammar ABI smoke matrix;
- scope shadowing, `this`, locals/parameters/fields, nested types/lambdas, FQCN,
  wildcard ambiguity, overload evidence/negative forms;
- package/import syntax errors trigger the same whole-file fallback;
- exact framework import allowlist and custom/MapStruct annotation negatives;
- calls, interface method pairs, and capped `uses_type` DTO/domain edges;
- comments/strings never become structure; AST/legacy parity and fallback;
- official MyBatis DOCTYPE positive, no-DOCTYPE positive, namespace/ID unique vs
  signature exact, malformed/XXE/internal-subset/entity/XInclude negatives;
- long mapper statements attach to their own start-line chunks; comment/CDATA
  fake tags, lexer/parser sequence mismatch, and duplicate IDs fail closed;
- SQL/annotation/literal caps and omitted counts.

### Frontend And Tests

- JS/JSX/TS/TSX and safely discovered Vue script ranges;
- static import and re-export edges;
- extension/index ambiguity, repository escape, string/comment/template fake
  import negatives;
- Vue/React framework import binding, shadowing, nested route composition, and
  custom API negatives;
- anchored Java `Contest`/`FooTests`/`FooITCase` classification;
- an unchanged Java test rebuilds its association from persisted
  `imports_type` after an ordinary production-file-only incremental change;
- exact conventions for every language, no token-only matching, no test-to-test,
  no generated/fixture/snapshot/data/cross-unit target.

### Retrieval, P4, And Explain

- every relation direction, including incoming source semantics;
- a hit in a long file's non-first chunk promotes its module and can follow
  frontend import, reverse test, and P4 test-gap edges;
- four-hop resolved flow and three-hop legacy limit;
- complete-tuple equal-score revisit and deterministic candidate truncation;
- global signals/edges/frontier caps, SQL `LIMIT 65`, cycles, high degree, and
  many signals on one chunk;
- `_match` adjustment visibility and truthful TraceCandidate limitations;
- graph reaching a protected direct candidate mutates nothing;
- exact existing test intent and P4 frozen test-goal gating;
- P4 stays <=3 calls, uses current source enums, and never seeds stale/ambiguous
  data;
- MCP exact graph sibling, CLI golden output, legacy/stale/future behavior, and
  `explore_repository()` coverage.
- a query-time dangling target persists stale when possible; when it cannot,
  the next unchanged index still fails no-op integrity and recovers.

## Likely Change Surface

| area | likely files |
| --- | --- |
| dependencies | `pyproject.toml` |
| models/plugin contract | `models.py`, `plugins.py` |
| producers | `java_plugin.py`, new Java AST/frontend graph/MyBatis modules |
| scanning/association | `scanner.py`, new test-association module |
| persistence/lifecycle | `sqlite_store.py`, `indexer.py`, index lock helper |
| traversal/ranking | `retrieval_core/expansion.py`, relation policy/reason helpers |
| P4 | `exploration/probes.py` |
| explain | `cli.py`, `mcp_tools.py` |
| quality | focused profile/catalog/projection tests and fixtures |
| docs | roadmap and evidence after approval/acceptance |

Unrelated ranking, ContextPack construction, trace models, vector search, and
CLI/MCP structure are not refactored.

## Delivery Decomposition

This design does not authorize implementation. A later plan should keep these
reviewable slices:

1. v5 identity/schema, adapter, full migration, lock/readiness/recovery, module
   nodes, and structural tests with no ranking change;
2. Java AST parity and safe fallback;
3. Java/Spring `calls`/`implements`/`uses_type` plus MyBatis;
4. resolved traversal, complete dominance, global budgets, explain;
5. frontend imports/re-exports and framework-anchored routes;
6. test association after producer resolution and P4 one-hop integration;
7. deterministic/real quality, protected gates, evidence, and roadmap update.

## Risks And Mitigations

- **False compiler claim:** persist syntax/producer/resolution confidence and
  keep unsupported Java semantics closed.
- **Convenient ambiguous target:** fetch two, never first; test overload,
  extension, wildcard, unit, and duplicate names.
- **Partial index marked ready:** stale-before-write, source hash last,
  stale-on-entry full extraction, two resolver stages, final integrity commit,
  and fault injection.
- **Topology drift:** persist fingerprint and invalidate unchanged files.
- **Graph flood:** outgoing-only imports/type use, four-hop cap, per-edge SQL
  limit, global work caps, and direct-evidence immutability.
- **Test pollution:** existing exact test intent/P4 goal gating and non-test
  target invariant.
- **Parser regression:** whole-file Java fallback and protected parity fixtures.
- **Frontend false framework:** exact framework import binding and shadowing
  rules; regex never persists edges.
- **XML attack:** accept only the validated official header, strip without
  fetching, use defused parser, reject entities/subsets/XInclude.
- **Remote privacy overclaim:** state existing embedding disclosure and v5
  resend explicitly; add no new remote caller.
- **P6 scope creep:** full deterministic re-resolution is accepted; caches,
  daemons, and latency targets remain deferred.

## Acceptance Criteria

P5 v1 is complete only when all are true:

1. Defaulted v5 fields evolve existing signals/relations; no parallel store.
2. V5 full SHA-256 identities distinguish same-line overloads and structured
   selectors; semantic duplicate occurrence merging is exact.
3. Every eligible non-empty file has one non-recallable module signal; empty
   files have none; module nodes never enter ordinary signal/text fallback.
4. Unit key/fingerprint contracts are exact, root `""` is valid, and topology
   change re-extracts unchanged files.
5. V4 reads through an adapter and triggers a full chunk/vector/graph rebuild;
   v5 stale disables signal/relation evidence; future schema never downgrades.
6. Exclusive lock, stale-before-write, source-hash-last, two resolver stages,
   final validation, and every injected failure recover without false ready.
7. Only exact/unique rows have active target IDs; ambiguous/external/unresolved
   never traverse or text-fallback; only legacy rows can text-fallback.
8. Producer/resolution/effective confidence round-trip independently.
9. Java AST facts preserve protected behavior and malformed relevant files use
   whole-file legacy fallback with no structured edge.
10. Lexical scope, FQCN, annotation allowlist, and exact overload-evidence rules
    fail closed on every declared negative.
11. Java fixtures resolve controller/service/interface/implementation/mapper
    calls and exact `uses_type` DTO/domain edges.
12. Standard MyBatis DOCTYPE/no-DOCTYPE files parse without fetch; XXE/entity/
    internal-subset/XInclude/malformed files emit no mapper edge.
13. Mapper namespace+ID is unique at 0.90 unless an exact signature proves 1.00;
    incoming Java-mapper traversal reaches the XML source.
14. Frontend AST persists static imports/re-exports and only framework-anchored
    Vue/React routes with exact nested path composition.
15. Extension/index ties, custom/shadowed router APIs, fake imports, computed
    paths/imports, and escapes emit no resolved edge.
16. Exact Java/Go/Rust/Python/JS/TS test conventions produce only same-unit,
    non-test, non-generated production targets; `Contest.java` stays non-test.
17. Producer relations resolve before associations; associations are rebuilt on
    stale recovery and no test-to-test/token-only edge exists.
18. Resolved traversal uses four hops, legacy uses three, incoming reaches the
    source, and complete path dominance is arrival-order independent.
19. Per-node SQL and global work caps terminate high-degree/cyclic graphs with
    deterministic prefixes.
20. Graph scores use declared `_match` keys; trace visibility claims match
    existing schema; graph cannot mutate a protected direct candidate.
21. Existing test intent and P4 frozen goals gate test edges exactly.
22. ContextPack v2, RetrievalTrace v1, ExplorationTrace v2, P4 rounds/probes/
    calls/planner/fusion/feedback contracts remain unchanged.
23. MCP/CLI explain matches exact fields/order/caps and legacy/stale/future
    behavior; existing chunk payload is unchanged.
24. Scanner rejects repository escapes/symlinks and parsers perform no network
    or repository-code execution.
25. Privacy documentation and tests reflect remote embedding source/query/probe
    disclosure and no new remote caller.
26. Structural projections pass twice and cover failure recovery/forbidden edges.
27. `p5_language_graphs` is exactly 12/12 and
    `p5_real_language_graphs` exactly 2/2 within declared budgets.
28. Raw CI 8/8, P2 5/5, deterministic P4 4/4, protected trace coverage 1.0,
    and protected catalog/inventory identities remain exact.
29. Direct endpoint/path/symbol winners remain protected; no-edge normalized
    outputs are byte-identical; changes use the reviewed allowlist.
30. Full suite passes with audited skips/xfails; Phase 1 stays independently 6/7.
31. No P6 surface, extra language plugin, recursive exploration, public graph
    operation, new schema, or model dependency enters P5.
32. Roadmap/evidence is updated only after implementation acceptance.

## Agent Review Rubric

Independent reviewers must verify identity collision resistance, v4/v5/future
schema behavior, partial-write recovery, topology invalidation, closed
resolution, Java semantic limits, framework anchoring, safe standard MyBatis
DOCTYPE support, frontend ambiguity, language-specific test evidence, incoming
neighbour semantics, complete path ordering, global budgets, protected direct
immutability, trace/explain truthfulness, privacy, executable quality inventory,
and the P4/P6 boundary.

Any unresolved blocker or major correctness, safety, compatibility, privacy,
determinism, dependency, or acceptance finding keeps the design in draft.

## Agent Review Record

First review (2026-07-17) used three independent read-only agents:

- architecture/index lifecycle: FAIL, 1 blocker and 7 major findings;
- language/framework ecosystem: FAIL, 2 blockers and 7 major findings;
- contract/quality/compatibility: FAIL, 3 blockers and 9 major findings.

The revision above addresses the shared findings: full v5 identity selectors,
stale recovery and source-hash ordering, two-stage resolution/association,
topology fingerprinting, explicit v4/v5/future behavior, non-recallable modules,
`uses_type`, lexical/annotation binding, safe official MyBatis DOCTYPE support,
framework-anchored frontend parsing, exact language-specific test rules, full
path dominance and work caps, incoming-source semantics, truthful trace/explain
visibility, existing remote embedding disclosure, and closed quality profiles.

Second targeted review (2026-07-17), after iterative fixes:

- architecture/index lifecycle: PASS, 0 blockers and 0 majors;
- language/framework ecosystem: PASS, 0 blockers and 0 majors;
- contract/quality/compatibility: PASS, 0 blockers and 0 majors.

Findings raised during the second pass were also fixed and re-reviewed: atomic
DDL/metadata migration, persistent full-reindex recovery, non-first-chunk module
promotion, persisted Java import facts, single-count graph adjustments, exact
cross-language path rewrites, fixed-profile quality configuration, MyBatis
position-preserving statement ranges, and explain membership. All reported
non-blocking wording minors—column coordinates, explicit regressions, and
missing-schema/fallback rendering—were incorporated. No blocker or major
remained at the review point; the user subsequently authorized implementation.

The subsequent implementation-plan review also re-reviewed the synchronized
design clarifications for rollback-journal read snapshots, two-phase immutable
vector generations and stale tuple validation, final-commit outcomes, and the
private I/O-free MyBatis ContextPack role hint. Architecture, ecosystem, and
contract/quality reviewers all passed the final plan with zero unresolved
blockers or majors.

Local verification note: `git diff --check` passed on the first draft. The full
test command available in this workspace ran under Python 3.14/SQLite 3.53,
while the frozen baseline uses Python 3.13/SQLite 3.51; it reported 2,178 passed,
9 skipped, and 3 environment-characterization failures unrelated to this
Markdown-only change. This note does not alter the recorded baseline.

## Completion Record

The user authorized implementation after review. P5 was delivered through the
focused lineage `1cdb171`, `eef1c22`, `abdfe45`, `ab630a7`, `ecae77f`,
`418241e`, `ca38856`, `3a62f12`, `de7c433`, `2e7a8a7`, `d931fab`, and
`9cad09e`. The final documentation commit is intentionally not self-recorded in
this file.

Acceptance on 2026-07-18 established:

- parser pins exactly matched the five versions in this design, and all eight
  Linux/macOS x Python 3.11-3.14 jobs passed in GitHub Actions run
  `29592106267`;
- structural projections were deterministic in forward/reverse indexing and
  the compatibility allowlist was `[]`;
- deterministic P5 passed 12/12; pinned PetClinic plus `program_tool` passed
  2/2 twice within 3 calls, 12 items, and 65,536 bytes;
- P4, P2, and raw CI passed 4/4, 5/5, and 8/8; protected-direct objects,
  no-legal-edge behavior, protected input hashes, and trace contracts stayed
  exact;
- the unrestricted suite passed 2,621 tests with the established 9 optional
  skips and 0 xfails; the local Ollama BGE integration was included;
- privacy/security, parser no-fetch, XML fail-closed, scanner escape, graph
  lifecycle/recovery, and feedback disclosure gates passed.

The Task-12 draft's whole-report P2/CI byte comparison was corrected during
execution because those reports include graph-derived ranks and score parts
that P5 is expressly designed to change. Keeping that comparison would
contradict the reviewed legal-delta rule in Task 11. No protected baseline was
refreshed; compatibility is enforced by immutable input identities,
protected-direct/no-edge projections, closed graph proofs, and the required
profile gates.

Index parsing and resolution remain local and perform no runtime fetch. Remote
embedding disclosure remains honest: a configured provider receives source
chunks, including a possible full resend during v5 migration, and query/explore
text may contain graph-derived names or paths; graph objects are not a separate
remote payload. Stale graph state disables graph evidence while preserving
other recall. V4-to-v5 requires full reindex and carries no P6 latency promise.

Exact hashes, real-case budgets, skip identities, and the non-gating
fast-context tenant-privacy rejection are recorded in
`docs/retrieval-quality.md`. Phase 5 is complete, Phase 1 remains independently
pending at 6/7, and Phase 6 is next.
