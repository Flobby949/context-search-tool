# P5 Language And Framework Graphs Implementation Plan

Date: 2026-07-17
Status: Plan approved by agent review; implementation not started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Design: `docs/superpowers/specs/2026-07-17-p5-language-framework-graphs-design.md`
Protected P0-P4 implementation baseline: `319dfedc777b7479e9b542c1e65ddd15814100b1`
Authorization: this document and its review only; Task 0 requires a later explicit implementation instruction

> **For agentic workers:** Execute one task at a time and keep every task green.
> Start production behavior changes with a failing or protective test, run the
> listed compatibility gates, stage only the exact paths owned by that task,
> and create the focused commit shown below. Stop on any schema/readiness,
> protected-direct, parser ABI, fixture identity, P4 call-count, trace schema,
> privacy, skip/xfail, or Phase 6 boundary mismatch. Never refresh a protected
> input or expected output merely to make a test pass.

**Goal:** Replace name-guess relation expansion with one recoverable schema-v5
language/framework graph: AST-backed Java/Spring facts, safe MyBatis XML,
framework-anchored Vue/React imports and routes, and exact same-unit test
associations. Resolved graph evidence must improve flow retrieval without
weakening direct evidence or changing ContextPack v2, RetrievalTrace v1,
ExplorationTrace v2, or P4's three-call ceiling.

**Architecture:** File-local parsers emit bounded facts and structured selectors.
One locked repository index operation persists a complete v5 snapshot, resolves
producer edges, rebuilds test associations from persisted resolved facts,
resolves those associations, validates integrity, and only then marks the graph
ready. Retrieval continues to use the existing relation-expansion stage. Only
exact/unique target IDs traverse; legacy rows alone retain textual fallback.

**Tech Stack:** Python 3.11+, SQLite, NumPy vector files, frozen dataclasses,
Typer, FastMCP, Tree-sitter runtime and official Java/JavaScript/TypeScript
grammars, `defusedxml`, current local hash-v1 embeddings, pytest, canonical JSON
with `allow_nan=False`, and a small Linux/macOS parser ABI workflow.

---

## Source Of Truth And Execution Constraints

The reviewed design is the normative source:

- `docs/superpowers/specs/2026-07-17-p5-language-framework-graphs-design.md`

If this plan and the design disagree, stop and amend/re-review the documents;
do not silently choose the easier implementation.

The protected baseline is commit
`319dfedc777b7479e9b542c1e65ddd15814100b1`:

- full suite: 2,181 passed, exact 9 established optional skips, 0 xfails;
- P4 focused suite: 243 passed;
- protected P0-P3 suite: 194 passed;
- deterministic P4 profile: 4/4;
- P2 ContextPack profile: 5/5;
- raw CI profile: 8/8;
- non-empty P3/P4 trace coverage: 1.0;
- Phase 1 remains independently pending at 6/7.

Protected input identities at plan time are:

| path | Git blob | SHA-256 |
| --- | --- | --- |
| `tests/fixtures/retrieval_quality/queries.json` | `8bbe4d560fec1499aa1f436af929b8a6bb6f3eac` | `ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5` |
| `tests/fixtures/retrieval_quality/p4_exploration.json` | `2dde23938277e3fec5d63c6037365eedfbce74e4` | `110e806dead64b4270d579a955abc8f56d7ec23d1b1f61a7951e5e4309a9c683` |
| `tests/fixtures/p4_exploration/input_manifest.json` | `f89118ea8c5e3fa94b9fcac5c832adc4326dd138` | `78e81f1c08c8216dc3355519cb89f07577ed61706e8150c9575e8395141c0b40` |
| `tests/fixtures/retrieval_core_decomposition/baseline.json` | `a0011178b2671af25cb0853260c8fdcf586acee0` | `4235ec5539c548005d75b98be4a0c347364d40ec28a79fc45b10d351bcf8bed7` |

Execution constraints:

1. This plan authorizes neither Task 0 nor production implementation. A later
   explicit user instruction is required.
2. Task 0 must run from the protected source lineage and reproduce the baseline
   with the one recorded command prefix `conda run -n base`, whose interpreter
   must be Python 3.13 and SQLite 3.51 before implementation begins. The current
   workstation's separate Python 3.14/SQLite 3.53 result of 2,178 passed, 9
   skipped, and three environment-characterization failures is not an accepted
   substitute. If `base` no longer matches, stop and amend this plan rather than
   mixing another runtime command into later evidence.
3. Task 1 freezes every new deterministic P5 source fixture, catalog, query,
   path expectation, negative, and pre-P5 no-edge projection before production
   graph code changes.
4. Protected P0-P4 catalogs, fixture inventories, baselines, trace schemas, and
   expected projections are immutable. A later compatibility allowlist records
   justified P5 effects; it never edits the protected inputs.
5. The dependency versions in this plan are exact pins. Task 2 must prove their
   runtime/grammar ABI across the declared matrix before any parser-backed
   producer is activated. A matrix failure stops implementation for plan review.
6. Parser/fact modules, v5 storage/indexing helpers, producer adapters, and
   resolved traversal may be built and tested internally before activation, but
   public `index_repository()`, `CURRENT_SIGNAL_SCHEMA_VERSION`,
   `default_plugins()`, and the production scan path remain on exact v4 behavior
   through Task 9.
7. Task 10 is the only activation boundary. Resolved traversal, every legacy/
   provenance consumer, exact graph explain, and MyBatis's existing ContextPack
   role/group are green before the public index entry point changes from schema
   4 to 5, registers every P5 producer together, uses the safe scan path, takes
   the exclusive lock, and forces the complete chunk/FTS/vector/graph rebuild.
   There is no feature flag, compatibility alias, or intermediate publicly
   reachable ready-v5 snapshot with only part of the P5 contract.
8. Existing structured files must not be skipped by old source hashes at the
   activation boundary. `full_reindex_required=1` is durable until final vector
   and graph coverage validation succeeds.
9. Every graph-relevant write is hidden behind `stale`; every file hash is
   written last; resolver order is producer edges, all test associations, test
   edges, final validation.
10. A structured ambiguous/external/unresolved edge never text-falls back. Only
    a row explicitly decoded or produced as `legacy` may use the existing name
    fallback and three-hop budget.
11. No task adds a graph database, public graph command, configuration flag,
    ContextPack group, trace schema, P4 round/probe/source enum, model call, or
    runtime grammar/DTD download.
12. No task executes repository code, build tools, package managers, Maven,
    Gradle, npm, TypeScript, annotation processors, XML includes, or tests from
    the indexed repository.
13. The existing Java regex extractor remains the whole-file fallback. It is
    not partially mixed with AST facts after any compilation-unit `ERROR` or
    missing node.
14. Each task's `Files` list is the authoritative write boundary for that task;
    every staged path must appear there. The responsibility map describes final
    production/new-artifact ownership and need not repeat every existing test
    file touched by a task. Any additional path requires a reviewed plan
    amendment. Adjacent refactors and formatting cleanup are out of scope.
15. Every task stages exact paths; never use `git add -A` in the shared dirty
    worktree.
16. Real-project preparation may use the quality tool's existing pinned checkout
    workflow. Indexing/querying itself stays local and performs no fetch.
17. Phase 1 stays 6/7 and Phase 6 freshness/performance/service work stays out
    of scope.

## Dependency Pins And ABI Gate

P5 pins the parser/XML packages exactly:

```text
tree-sitter==0.26.0
tree-sitter-java==0.23.5
tree-sitter-javascript==0.25.0
tree-sitter-typescript==0.23.2
defusedxml==0.7.1
```

These are installation dependencies, not runtime fetches. `defusedxml` 0.7.1
is used because 0.8.0 is still a prerelease at plan time. If the exact set is
not mutually compatible, do not loosen a bound opportunistically: amend the
five-pin set, rerun agent review, then restart Task 2.

The parser ABI workflow has exactly eight jobs:

- `ubuntu-latest` x64 on Python 3.11, 3.12, 3.13, and 3.14;
- `macos-latest` arm64 on Python 3.11, 3.12, 3.13, and 3.14.

Each job runs `python -m pip install '.[dev]'` from `pyproject.toml`, prints
Python/platform and the five installed versions, and runs only
`python -m pytest -q tests/test_parser_abi.py`. That test
constructs every grammar from packaged language capsules, parses valid Java,
JavaScript, JSX, TypeScript, and TSX, observes a bounded malformed tree without
crashing, and proves parser initialization performs no network access or
runtime grammar compilation. All eight jobs must pass before Task 3.

## Definition Of Done

P5 implementation is complete only when:

- v5 defaulted signal/relation fields and full SHA-256 canonical identities are
  implemented without changing legacy IDs for legacy callers;
- every graph-eligible file has exactly one shared-helper-created,
  non-recallable module signal and empty files have none;
- the v4 adapter, atomic v4-to-v5 DDL transition, v5 stale behavior, future
  schema refusal, topology fingerprint, and exclusive lock match the capability
  matrix;
- full rebuild recreates source/chunk/token/FTS/vector/signal/relation data,
  bypasses corrupt old vectors, writes source hashes last, and cannot mark a
  partial snapshot ready;
- producer relations resolve before all test associations are regenerated and
  resolved; exact/unique target integrity holds in the final transaction;
- Java AST facts preserve protected declarations/endpoints/tokens and implement
  only the closed lexical/type/annotation/call rules; malformed files fall back
  as a whole;
- official/no-DOCTYPE MyBatis mapper XML works without fetch, while entity,
  subset, XInclude, malformed, duplicate-ID, lexer/parser-mismatch, and missing-
  chunk cases fail closed;
- static frontend imports/re-exports and framework-bound Vue/React routes use
  exact paths, safe Vue ranges, deterministic nested routes, and no extension
  or index preference tie-break;
- Java, Go, Rust, Python, JavaScript, and TypeScript test conventions produce
  only exact same-unit, non-test, non-generated production targets;
- resolved graph traversal uses target IDs, incoming edges reach the source,
  complete-tuple dominance is deterministic, four-hop/global budgets hold, and
  legacy traversal remains three hops;
- exactly one closed graph-kind `_match` score is counted per retained best
  path and graph reachability mutates no protected direct candidate field;
- P4 receives at most one grounded ready-graph hop, still makes at most three
  retrieval calls, and keeps every v2 exploration contract unchanged;
- MCP/CLI explain adds the exact bounded graph sibling/lines while preserving
  the old chunk payload/lines byte-for-byte;
- scanner symlink/root safety, parser byte caps, XML safety, and honest remote
  embedding disclosure are tested;
- committed structural projections match two independent indexes;
- deterministic `p5_language_graphs` is exactly 12/12 and opt-in
  `p5_real_language_graphs` is exactly 2/2 twice;
- P4 is 4/4, P2 is 5/5, raw CI is 8/8, protected trace coverage is 1.0,
  protected identities remain exact, and every allowed output change has
  reviewed before/after graph evidence;
- the full suite passes with audited skip/xfail identities and Phase 1 remains
  6/7;
- README, quality documentation, design/plan evidence, and roadmap are updated
  only after acceptance.

## File Responsibility Map

| file | final responsibility |
| --- | --- |
| `pyproject.toml` | Exact five-package P5 dependency pins |
| `.github/workflows/p5-parser-abi.yml` | Eight-job Linux/macOS, Python 3.11-3.14 parser smoke gate only |
| `src/context_search_tool/graph_contract.py` | V5 states/kinds/weights/budgets, canonical JSON IDs, confidence rules, shared module identity |
| `src/context_search_tool/graph_lifecycle.py` | Capability matrix, metadata keys, stable stale/future errors, readiness transitions/integrity result |
| `src/context_search_tool/graph_resolution.py` | Deterministic structured selector classification through a bounded store protocol |
| `src/context_search_tool/graph_plugins.py` | Leaf-owned PluginContext, parsed-fact envelope, and two-phase GraphLanguagePlugin protocol |
| `src/context_search_tool/models.py` | Additive defaulted graph fields plus one private non-serialized ContextPack role hint; legacy/public payload compatibility |
| `src/context_search_tool/syntax_parsers.py` | Cached packaged Tree-sitter language/parser construction; no domain policy or I/O |
| `src/context_search_tool/java_ast.py` | Java syntax facts, scopes, FQCN/signature normalization, closed AST caps/fallback signal |
| `src/context_search_tool/java_graph.py` | AST-to-v5 Java/Spring fact materializer used by the Java coordinator |
| `src/context_search_tool/java_plugin.py` | Final JavaPlugin coordinator plus preserved private whole-file legacy extractor |
| `src/context_search_tool/frontend_graph.py` | Vue range lexer, JS/TS/TSX AST facts, static imports/re-exports, framework-bound route producer |
| `src/context_search_tool/mybatis_xml.py` | Closed DOCTYPE validator, equal-length scrub, safe parse, byte range lexer, statement producer |
| `src/context_search_tool/test_paths.py` | Leaf-owned exact six-family test classification and pure candidate rewrites |
| `src/context_search_tool/test_association.py` | Legal-target filtering plus convention/persisted-import association generation |
| `src/context_search_tool/index_lock.py` | Repository-wide advisory lock and stable busy failure; no unlocked fallback |
| `src/context_search_tool/plugins.py` | Legacy plugin surface plus final function-local P5 producer registration order |
| `src/context_search_tool/project_scope.py` | Canonical unit key and topology fingerprint |
| `src/context_search_tool/scanner.py` | Resolved-root and any-component symlink rejection before file reads |
| `src/context_search_tool/sqlite_store.py` | V4 adapter, v5 DDL/indexes/codecs, bounded resolver/adjacency APIs, one-snapshot GraphReadSession, transactional readiness/integrity |
| `src/context_search_tool/vector_store.py` | Immutable vector generations plus one atomic descriptor; full rebuild need not load old/corrupt files |
| `src/context_search_tool/manifest.py` | Schema-v1-compatible atomic temp/fsync/rename manifest persistence |
| `src/context_search_tool/paths.py` | Validated lock-only index-dir bootstrap before normal locked layout writes |
| `src/context_search_tool/indexer.py` | Lock-to-ready protocol, atomic activation/full rebuild, source-hash-last, two resolver stages |
| `src/context_search_tool/retrieval.py` | One-snapshot GraphReadSession lifetime, stale logging, and future-schema fail-closed path |
| `src/context_search_tool/retrieval_core/candidates.py` | Stale gating and module-aware seed lookup only if not owned by expansion |
| `src/context_search_tool/retrieval_core/expansion.py` | Sole resolved/legacy traversal owner, incoming semantics, dominance, caps, dangling-target fallback |
| `src/context_search_tool/retrieval_core/relation_policy.py` | Closed directions/kind priority/weights/reasons and separate resolved/legacy limits |
| `src/context_search_tool/retrieval_core/ranking.py` | One-time maximum closed graph `_match` contribution and protected-direct immutability |
| `src/context_search_tool/retrieval_core/evidence_merge.py` | Resolved provenance merge without legacy numeric double count |
| `src/context_search_tool/retrieval_core/context_expansion.py` | Existing relation-context policy recognizes resolved non-scoring provenance |
| `src/context_search_tool/retrieval_core/selection.py` | Summary/reason relation support plus final private mapper-role hint assembly use the same legal read session without mutating direct evidence |
| `src/context_search_tool/retrieval_core/tracing.py` | Existing source/reason mapping recognizes non-scoring graph provenance; no trace schema change |
| `src/context_search_tool/exploration/probes.py` | One-hop ready-graph seeds, non-first-chunk module promotion, exact test-goal gating |
| `src/context_search_tool/context_pack/roles.py` | I/O-free consumption of the private accepted-mapper role hint into existing group/role values |
| `src/context_search_tool/cli.py` | One stale warning per operation, stable index-busy/future errors, exact graph explain lines |
| `src/context_search_tool/mcp_tools.py` | Stable stale log/future error and exact ordered explain graph sibling |
| `src/context_search_tool/quality/cases.py` | Exact P5 profile allowlist and closed mode/config validation |
| `src/context_search_tool/quality/runner.py` | Results/context/exploration ownership for the two P5 profiles, no second baseline query |
| `tests/test_p5_inputs.py` | Frozen fixture/catalog/protected identity and pre-P5 assay gates |
| `tests/test_parser_abi.py` | Packaged grammar import/parse/no-fetch ABI matrix |
| `tests/test_graph_models.py` | V5 IDs/defaults/confidence/occurrence/module identity |
| `tests/test_java_ast.py` | AST facts, parity, binding, annotation, overload, caps, whole-file fallback |
| `tests/test_frontend_graph.py` | Vue ranges, imports/re-exports, Vue/React binding/routes, ambiguity/escape negatives |
| `tests/test_mybatis_xml.py` | Safe official header, exact ranges/chunks, resolution inputs, XXE/fail-closed negatives |
| `tests/test_graph_store.py` | V4 adapter, v5 schema/index/codecs, bounded lookups, resolution state integrity |
| `tests/test_graph_lifecycle.py` | Lock, migration snapshots, topology, full/incremental recovery and fault injection |
| `tests/test_graph_resolution.py` | Exact/unique/ambiguous/external/unresolved rules and deterministic two-row queries |
| `tests/test_test_association.py` | Complete six-family rewrite matrix and persisted-import/stale rebuild behavior |
| `tests/test_resolved_graph_expansion.py` | Directions, four/three hops, dominance, caps, scoring, direct immutability, P4 seeds |
| `tests/test_p5_explain.py` | Exact MCP keys/ordering/caps and CLI goldens for legacy/stale/ready/future |
| `tests/test_p5_graph_contract.py` | Twice-indexed canonical structural projections and forbidden-edge/recovery invariants |
| `tests/test_quality_p5.py` | 12-case deterministic profile plus raw graph score-part proof and compatibility allowlist |
| `tests/test_p5_privacy.py` | Recording-provider proof of full-reindex/query/probe disclosure and no graph-object payload/new client |
| `tests/p5_graph_identity.py` | Test-only input/store/result canonical projection helpers |
| `tests/generate_p5_graph_manifest.py` | One-shot pre-production input manifest generator |
| `tests/generate_p5_graph_expected.py` | Refuse-overwrite initializer requiring two byte-identical structural candidates |
| `tests/p5_real_language_graphs_acceptance.py` | Explicit two-case repeated real projection; deliberately not default-collected |
| `tests/fixtures/p5-language-graphs/**` | Five frozen synthetic repositories plus post-implementation expected projections |
| `tests/fixtures/p5_language_graphs/input_manifest.json` | New input hashes plus protected P0-P4 identities; excludes generated expected outputs |
| `tests/fixtures/p5_language_graphs/pre_p5_no_edge_projection.json` | Frozen normalized baseline for the standalone no-legal-edge case |
| `tests/fixtures/p5_language_graphs/real_acceptance.json` | Twice-produced normalized PetClinic/program-tool acceptance projection |
| `tests/fixtures/retrieval_quality/p5_language_graphs.json` | Exact 12-case deterministic catalog |
| `tests/fixtures/retrieval_quality/p5_real_language_graphs.json` | Exact two-case pinned/committed real catalog |
| `README.md`, `docs/retrieval-quality.md` | Accepted graph behavior, safety, stale operation, and honest remote disclosure |
| P5 design, this plan, and roadmap | Reviewed/implemented status and exact acceptance record |

Generated files under `tests/fixtures/p5-language-graphs/expected/` are outputs,
not Task-1 inputs. They are initialized only in Task 11 after two independent
canonical projections compare byte-for-byte. The input manifest must reject any
attempt to include them retroactively.

## Final Import Adjacency

The boundary tests treat an edge as importer -> imported. P5-specific allowed
edges are:

| importer | allowed P5 dependencies |
| --- | --- |
| `graph_contract.py` | standard library only |
| `models.py` | `graph_contract` only for pure identity helpers if needed; graph contract never imports models |
| `syntax_parsers.py` | Tree-sitter runtime/grammar packages and standard library only |
| `java_ast.py` | `syntax_parsers`, tokenizer primitives; no store/index/retrieval imports |
| `graph_plugins.py` | standard library and model type annotations only; no producer registration/imports |
| `java_graph.py` | `java_ast`, `graph_contract`, models, leaf `graph_plugins` types; no legacy/coordinator import |
| `java_plugin.py` | Existing legacy dependencies plus one-way final coordinator use of `java_graph`; its private legacy extractor has no graph-producer dependency |
| `frontend_graph.py` | `syntax_parsers`, `graph_contract`, models, leaf `graph_plugins` types, path normalization |
| `mybatis_xml.py` | `defusedxml`, `graph_contract`, models, leaf `graph_plugins` types; no network/XML resolver |
| `test_paths.py` | standard library/path primitives only; no scanner/store/project/index imports |
| `test_association.py` | `graph_contract`, models, project scope, SQLite store read/write API |
| `graph_lifecycle.py` | `graph_contract`, standard library, and a locally declared structural store protocol; no concrete SQLite-store import |
| `graph_resolution.py` | `graph_contract`, models, and a locally declared bounded-store protocol; no concrete SQLite-store import |
| `index_lock.py` | standard-library OS locking only |
| `sqlite_store.py` | models and graph contract/lifecycle value types; no parser/producer/retrieval imports |
| `indexer.py` | scanner/project scope/plugins/store/vector/lock/lifecycle/resolution/test association |
| retrieval-core expansion/policy | graph contract, existing retrieval types, SQLite read API |
| `exploration/probes.py` | graph contract and SQLite read API; no parser/indexer imports |
| `context_pack/roles.py` | Existing path/frontend classifiers plus private result hint only; no store, parser, resolver, or repository I/O |
| CLI/MCP | public index/retrieval/explain helpers; no parser implementation imports |
| quality modules | public index/query/context/explore surfaces; test-only projection helpers never enter production |

Forbidden edges include:

- any graph/parser/producer/store module -> CLI, MCP, quality, or exploration;
- parser/fact modules -> SQLite, vector store, indexer, retrieval, or repository
  filesystem traversal;
- `graph_contract.py` -> models/store/indexer/retrieval;
- `sqlite_store.py` -> any language/framework producer;
- retrieval core -> parser or indexer;
- P4 -> parser, resolver, or test-association writer;
- production code -> `tests`, fixture catalogs, projection scripts, or expected
  JSON;
- any P5 module -> HTTP client, subprocess/build tool, dynamic grammar loader,
  or external XML resolver.

## Public And Persistent Surface

P5 adds no top-level operation and no user configuration. The supported public
surface remains query, context, trace, explore, stats, explain, and index.

Additive model fields are exactly those in the design. ContextPack stays v2,
RetrievalTrace stays v1, ExplorationTrace stays v2, and manifest stays v1.
MCP explain alone adds the exact ordered `graph` sibling; CLI explain appends
the reviewed graph lines after every existing line.

The persistent metadata keys are exactly:

```text
signal_schema_version
graph_resolution_state
graph_resolution_version
graph_stale_reason
full_reindex_required
project_unit_topology_fingerprint
```

`project_scope_metadata_version` and existing index metadata remain; P5 does not
invent a producer-version shortcut to avoid the one required full rebuild.

The baseline has no dedicated public lock error. The minimal mapping is an
internal `IndexBusyError`: CLI uses its existing index error rendering, and MCP
uses its existing `index_failed` envelope with the stable local message
`index already in progress for repository`. No absolute lock path or new MCP
error shape is exposed. Future schema is different: every affected MCP operation
returns the stable existing error envelope with code
`incompatible_signal_schema`, and CLI/library raises/renders the shared
`IncompatibleSignalSchemaError` without mutating the database.

## Task And Commit Order

| task | purpose | focused commit |
| ---: | --- | --- |
| 0 | Reproduce protected runtime/input/quality baseline | no commit |
| 1 | Freeze P5 inputs, assays, catalogs, and identities | `test: lock p5 language graph inputs` |
| 2 | Pin and prove parser/XML dependency ABI | `build: pin p5 parser dependencies` |
| 3 | Add pure v5 graph value/identity contract | `feat: add p5 graph value contract` |
| 4 | Add directly tested Java AST facts without activation | `feat: add java ast facts` |
| 5 | Add directly tested frontend and MyBatis parsers without activation | `feat: add frontend and mybatis facts` |
| 6 | Add directly tested v5 store/resolver/lifecycle primitives without activation | `feat: add graph lifecycle primitives` |
| 7 | Add directly tested producer adapters and test association without registration | `feat: add p5 graph producers` |
| 8 | Build/test the complete internal v5 index path without switching public v4 behavior | `feat: prepare p5 graph indexing` |
| 9 | Add directly tested resolved traversal/P4 support while public behavior remains v4 | `feat: add dormant resolved graph evidence` |
| 10 | Add exact explain/ContextPack role behavior, then atomically activate complete public v5 | `feat: activate complete p5 graph behavior` |
| 11 | Add structural projections and deterministic 12/12 quality gate | `test: verify p5 language graph quality` |
| 12 | Run real 2/2/protected/full acceptance and record docs | `docs: record p5 language graph acceptance` |

Tasks 3-9 deliberately expose no new public ready-v5 behavior. Their internal
functions/classes are directly tested, and Task 8's complete v5 orchestrator is
invoked only through an explicit test helper/injected entry point while public
indexing remains v4. Task 9 finishes resolved traversal, provenance, selection,
and P4 handling behind private injected seams. Task 10 first completes exact
explain and existing-role integration, then removes all isolation in one switch
of the current schema/public index/query surfaces and all adapters. Do not add a
temporary config/feature flag to simulate this boundary.

## Shared Verification Commands

Run default gates with optional external variables absent:

```bash
unset \
  CST_RUN_P1_ACCEPTANCE \
  CST_P2_REAL_CONTEXT_REPOS_DIR \
  CST_P4_REAL_EXPLORATION_REPOS_DIR \
  CST_P5_REAL_LANGUAGE_GRAPHS_REPOS_DIR \
  CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
  CST_SMOKE_REPOS_DIR \
  CST_PLANNER_REQUESTS_REPO
test -z "$(env | rg '^(CST_RUN_P1_ACCEPTANCE|CST_P2_REAL_CONTEXT_REPOS_DIR|CST_P4_REAL_EXPLORATION_REPOS_DIR|CST_P5_REAL_LANGUAGE_GRAPHS_REPOS_DIR|CST_SMOKE_INVESTMENT_ASSISTANT_REPO|CST_SMOKE_REPOS_DIR|CST_PLANNER_REQUESTS_REPO)=' || true)"
export P5_RUNTIME="$PWD/.quality/p5-runtime/bin/python"
test -x "$P5_RUNTIME"
```

After Task 2, use only that baseline-derived P5 runtime for these named gates.
Task 0 and Task 1 explicitly use pristine `conda run -n base` instead:

```bash
# P5 parser/producer foundation
PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
  tests/test_parser_abi.py \
  tests/test_graph_models.py \
  tests/test_java_ast.py \
  tests/test_frontend_graph.py \
  tests/test_mybatis_xml.py

# P5 persistence/index lifecycle
PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
  tests/test_graph_store.py \
  tests/test_graph_lifecycle.py \
  tests/test_graph_resolution.py \
  tests/test_test_association.py

# P5 retrieval/public/quality
PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
  tests/test_resolved_graph_expansion.py \
  tests/test_p5_explain.py \
  tests/test_p5_graph_contract.py \
  tests/test_quality_p5.py

# Protected P0-P4 contracts
PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_context_pack.py \
  tests/test_exploration_boundaries.py \
  tests/test_exploration_contracts.py \
  tests/test_exploration_runner.py \
  tests/test_quality_p3.py \
  tests/test_quality_p4.py

# Full suite
PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q -rs
```

Omit a not-yet-created P5 test file until its owning task creates it. Every
production task runs its focused gate plus protected P0-P4 contracts. Tasks
8-12 additionally run the full suite. No task introduces a default skip/xfail.

Every commit step has one mandatory check after its exact `git add` and before
`git commit`:

```bash
git diff --cached --check
git diff --cached --name-only
```

The staged-name output must equal that task's `Files` subset actually changed;
unstaged/untracked user work remains untouched. This post-stage check, not the
earlier `git diff --check` alone, covers newly created files.

### Task 0: Establish A Reproducible Protected Start

**Files:** none

- [ ] **Step 1: Start only after explicit implementation authorization**

  Record the user instruction and create a branch from the reviewed docs/source
  lineage:

  ```bash
  git status --short
  git rev-parse HEAD
  git switch -c codex/p5-language-framework-graphs
  ```

  Expected before switching: only the reviewed P5 design/plan/roadmap document
  lineage differs from baseline source. Preserve unrelated user changes.

- [ ] **Step 2: Prove production source lineage**

  ```bash
  git diff --exit-code \
    319dfedc777b7479e9b542c1e65ddd15814100b1 -- \
    src/context_search_tool pyproject.toml tests
  ```

  Expected: no unreviewed implementation/test/dependency drift. Documentation
  commits after the baseline are allowed.

- [ ] **Step 3: Prove protected input identities**

  Re-run `git hash-object` and SHA-256 for the four files in the protected table,
  and run `git diff --exit-code` from the baseline across all existing P0-P4
  fixture/catalog/projection directories. Every value must match exactly.

- [ ] **Step 4: Prove the baseline runtime**

  ```bash
  PYTHONPATH="$PWD/src" conda run --no-capture-output -n base python -c \
    'import platform, sqlite3, sys; print(sys.version); print(platform.platform(), platform.machine()); print(sqlite3.sqlite_version); assert sys.version_info[:2] == (3, 13); assert sqlite3.sqlite_version_info[:2] == (3, 51)'
  ```

  Required: visible version/platform output and zero exit only for the accepted
  Python 3.13/SQLite 3.51 family. Any assertion failure blocks implementation;
  do not redefine the baseline from Python 3.14 characterization output.

- [ ] **Step 5: Capture machine-readable baseline evidence**

  ```bash
  mkdir -p .quality/p5-artifacts
  env \
    -u CST_RUN_P1_ACCEPTANCE \
    -u CST_P2_REAL_CONTEXT_REPOS_DIR \
    -u CST_P4_REAL_EXPLORATION_REPOS_DIR \
    -u CST_P5_REAL_LANGUAGE_GRAPHS_REPOS_DIR \
    -u CST_SMOKE_INVESTMENT_ASSISTANT_REPO \
    -u CST_SMOKE_REPOS_DIR \
    -u CST_PLANNER_REQUESTS_REPO \
    PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q -rs \
    --junitxml=.quality/p5-artifacts/baseline.xml
  ```

  Required: 2,181 passed, exact 9 known skips, 0 xfails, 0 errors. Parse the
  JUnit file rather than trusting only terminal text.

- [ ] **Step 6: Reproduce protected quality evidence**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run --no-capture-output -n base \
    python -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_exploration_contracts.py \
    tests/test_exploration_inputs.py \
    tests/test_quality_p3.py \
    tests/test_quality_p4.py

  PYTHONPATH="$PWD/src" conda run --no-capture-output -n base \
    python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output .quality/p5-artifacts/baseline-p4.json \
    --markdown .quality/p5-artifacts/baseline-p4.md
  PYTHONPATH="$PWD/src" conda run --no-capture-output -n base \
    python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output .quality/p5-artifacts/baseline-p2.json \
    --markdown .quality/p5-artifacts/baseline-p2.md
  PYTHONPATH="$PWD/src" conda run --no-capture-output -n base \
    python -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output .quality/p5-artifacts/baseline-ci.json \
    --markdown .quality/p5-artifacts/baseline-ci.md

  conda run --no-capture-output -n base python -c \
    'import json; paths=(".quality/p5-artifacts/baseline-p4.json", ".quality/p5-artifacts/baseline-p2.json", ".quality/p5-artifacts/baseline-ci.json"); reports=[json.load(open(path, encoding="utf-8")) for path in paths]; assert [(d["profile"], d["aggregate"]["selected"], d["aggregate"]["executed"], d["aggregate"]["passed"], d["aggregate"]["failed"], d["aggregate"]["errors"]) for d in reports] == [("p4_exploration", 4, 4, 4, 0, 0), ("p2_context_pack", 5, 5, 5, 0, 0), ("ci", 8, 8, 8, 0, 0)]; coverage=[case["metrics"].get("exploration_trace_coverage") for case in reports[0]["cases"] if case["metrics"].get("exploration_trace_coverage") is not None]; assert coverage and all(value == 1.0 for value in coverage)'

  PYTHONPATH="$PWD/src:$PWD/tests" conda run --no-capture-output -n base \
    python tests/p4_exploration_identity.py quality-projection \
    --input .quality/p5-artifacts/baseline-p2.json \
    --output .quality/p5-artifacts/baseline-p2-projection.json
  PYTHONPATH="$PWD/src:$PWD/tests" conda run --no-capture-output -n base \
    python tests/p4_exploration_identity.py quality-projection \
    --input .quality/p5-artifacts/baseline-ci.json \
    --output .quality/p5-artifacts/baseline-ci-projection.json
  cmp -s tests/fixtures/p4_exploration/p0_p3_p2_quality.json \
    .quality/p5-artifacts/baseline-p2-projection.json
  cmp -s tests/fixtures/p4_exploration/p0_p3_ci_quality.json \
    .quality/p5-artifacts/baseline-ci-projection.json
  ```

  The executable assertion owns selected/executed/passed P4 4/4/4, P2 5/5/5,
  raw CI 8/8/8, zero error/failure, and P4 non-empty trace coverage 1.0;
  `test_quality_p3.py` owns P3 coverage 1.0. Both `cmp` calls and all protected
  contract tests must pass. Preserve these reports as Task-12 baselines.

**Stop:** any baseline/runtime/input mismatch blocks Task 1. Task 0 creates no
commit and changes no tracked file.

### Task 1: Freeze P5 Inputs And Pre-P5 Compatibility Evidence

**Files:**

- Create: `tests/fixtures/p5-language-graphs/java-spring/**`
- Create: `tests/fixtures/p5-language-graphs/vue/**`
- Create: `tests/fixtures/p5-language-graphs/react/**`
- Create: `tests/fixtures/p5-language-graphs/generic-tests/**`
- Create: `tests/fixtures/p5-language-graphs/malformed-compat/**`
- Create: `tests/fixtures/p5_language_graphs/input_manifest.json`
- Create: `tests/fixtures/p5_language_graphs/pre_p5_no_edge_projection.json`
- Create: `tests/fixtures/retrieval_quality/p5_language_graphs.json`
- Create: `tests/fixtures/retrieval_quality/p5_real_language_graphs.json`
- Create: `tests/p5_graph_identity.py`
- Create: `tests/generate_p5_graph_manifest.py`
- Create: `tests/test_p5_inputs.py`

- [ ] **Step 1: Write the raw input validator first**

  The test must fail until all five repository keys, exactly 12 deterministic
  case IDs, exactly two real case IDs, exact queries/modes/configs, declared
  positive/negative paths, pinned PetClinic commit, and protected identities
  exist. It parses raw JSON itself; production quality code is unchanged.

- [ ] **Step 2: Build only the reviewed fixture inventory**

  Create the exact five snapshots and files named in the design. Add focused
  negatives for same-arity overloads, nested duplicate units, custom Spring/
  MyBatis annotation names, frontend extension/index ties, framework API
  shadowing, XXE/internal-subset/XInclude/fake tags, forbidden test targets,
  malformed sources, and the frozen standalone no-edge case.

  Each source contains only the minimum tokens needed for its declared proof.
  Do not add repeated query prose that lets lexical retrieval satisfy a graph
  case accidentally.

- [ ] **Step 3: Assay baseline v4 behavior before freezing**

  Index each synthetic repository with the baseline implementation into a
  disposable directory and capture a non-committed raw assay. Required before
  freeze:

  - the standalone no-edge case has a stable normalized result projection;
  - malformed lexical tokens still return their own direct file first;
  - the Vue exploration case's declared router and type are both absent from
    the initial pack under the fixed profile;
  - every required graph-specific positive later has either an absent path or a
    planned raw `_match` assertion, so text co-occurrence cannot be mistaken for
    graph proof;
  - every negative path is absent under baseline behavior.

  If an assay fails, edit the new fixture now and repeat. No production tuning
  is allowed in this task.

- [ ] **Step 4: Freeze the no-edge and protected comparison anchors**

  Commit the canonical pre-P5 no-edge projection. Record baseline direct winner
  and direct score parts for every protected endpoint/path/symbol case in the
  input manifest's evidence section without copying timing, absolute paths, or
  vector floats.

- [ ] **Step 5: Generate the immutable input manifest once**

  The generator hashes all new source fixtures, both P5 catalogs, the pre-P5
  no-edge projection, this exact inventory, and the protected P0-P4 identities.
  It must:

  - use repository-relative POSIX paths and full SHA-256;
  - reject symlinks, duplicate paths, and files outside the reviewed roots;
  - explicitly exclude `expected/**`, `real_acceptance.json`, temporary reports,
    indexes, and parser objects;
  - refuse overwrite;
  - produce canonical JSON with fixed keys and `allow_nan=False`.

- [ ] **Step 6: Prove identity and compatibility tests are green**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" conda run -n base python -m pytest -q \
    tests/test_p5_inputs.py \
    tests/test_exploration_inputs.py \
    tests/test_quality_catalog.py
  git diff --check
  ```

- [ ] **Step 7: Commit only the frozen inputs**

  ```bash
  git add \
    tests/fixtures/p5-language-graphs \
    tests/fixtures/p5_language_graphs/input_manifest.json \
    tests/fixtures/p5_language_graphs/pre_p5_no_edge_projection.json \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    tests/p5_graph_identity.py \
    tests/generate_p5_graph_manifest.py \
    tests/test_p5_inputs.py
  git commit -m "test: lock p5 language graph inputs"
  ```

After this commit, no later task edits the frozen fixture source bytes, either
catalog, input manifest, or pre-P5 no-edge projection. Test/generator harness
code such as `tests/test_p5_inputs.py` may gain read-only assertions later. The
only new fixture bytes allowed after Task 1 are the two explicitly
post-implementation output locations excluded from the input manifest.

### Task 2: Pin And Prove Parser/XML Dependencies

**Files:**

- Modify: `pyproject.toml`
- Create: `.github/workflows/p5-parser-abi.yml`
- Create: `src/context_search_tool/syntax_parsers.py`
- Create: `tests/test_parser_abi.py`
- Modify: `tests/test_exploration_boundaries.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

> **User-approved execution amendment (2026-07-17):** Retain the reviewed
> `syntax_parsers.py` leaf boundary. Let the local P5 venv inherit the already-
> proven `base` site packages so the protected NumPy/BLAS characterization stays
> byte-exact, and update only the two phase-scoped production-path inventories
> needed for incremental P5 work. Dependency pins, remote ABI isolation, P5
> behavior, and protected baselines remain unchanged.

- [ ] **Step 1: Add failing ABI/import tests**

  Assert the five exact installed versions, language capsule construction, valid
  Java/JavaScript/JSX/TypeScript/TSX root nodes, bounded malformed-tree behavior,
  UTF-8 byte offsets, parser reuse isolation, and no import-time socket/
  subprocess/dynamic-build call.

- [ ] **Step 2: Pin the exact five dependencies**

  Add only the versions in the dependency section. Do not loosen existing
  unrelated dependencies or add a lockfile/tooling migration. Then create one
  repository-local P5 runtime from the already-proven baseline interpreter and
  install the project including its test extra:

  ```bash
  test ! -e .quality/p5-runtime
  conda run --no-capture-output -n base python -m venv \
    --system-site-packages .quality/p5-runtime
  export P5_RUNTIME="$PWD/.quality/p5-runtime/bin/python"
  "$P5_RUNTIME" -m pip install '.[dev]'
  "$P5_RUNTIME" -c 'import sqlite3, sys; assert sys.version_info[:2] == (3, 13); assert sqlite3.sqlite_version_info[:2] == (3, 51)'
  ```

  `--system-site-packages` is deliberate: it preserves the exact already-proven
  local NumPy/BLAS behavior while installing the five P5 pins into the venv.
  `.quality/p5-runtime` is ignored evidence infrastructure, not a committed
  artifact. Every Task-2-through-12 local Python command uses this exact
  `P5_RUNTIME`; Task 0/1 alone use pristine `conda base` for pre-dependency
  baseline/input work. Do not install P5 packages into the global base env.

- [ ] **Step 3: Implement the narrow parser runtime wrapper**

  Construct languages from the packaged grammar capsules using the pinned
  Tree-sitter API. Expose only explicit Java, JavaScript, JSX, TypeScript, and
  TSX parse functions. Cache immutable languages; create/reset parser state so
  concurrent calls cannot leak included ranges. No repository path, network,
  grammar compilation, or policy belongs here.

- [ ] **Step 4: Add the eight-job ABI workflow**

  The workflow runs only on changes to dependency/parser/P5 workflow files and
  manual dispatch. Use official checkout/setup-python actions, the exact OS/
  Python matrix above, `python -m pip install '.[dev]'`, version output, and
  `python -m pytest -q tests/test_parser_abi.py`. It does not run external
  repositories or the full suite and never depends on a runner's ambient
  pytest installation.

- [ ] **Step 5: Run local smoke and full compatibility**

  ```bash
  export P5_RUNTIME="$PWD/.quality/p5-runtime/bin/python"
  "$P5_RUNTIME" -m pip show \
    tree-sitter tree-sitter-java tree-sitter-javascript \
    tree-sitter-typescript defusedxml pytest
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_parser_abi.py
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q
  git diff --check
  ```

  Required locally: smoke passes and the full suite retains exact skip/xfail
  identities. Required remotely before Task 3: all eight ABI jobs pass. If the
  workflow cannot run in this repository, produce equivalent signed CI evidence
  from the same eight environments and stop for reviewer approval; do not claim
  the matrix from one machine.

  The two boundary tests keep the complete P4 diff mandatory, permit only the
  exact P5 production paths already named in this plan's responsibility map,
  and reject every other dirty or changed production path. They do not alter a
  protected fixture, baseline, schema, or behavioral projection.

- [ ] **Step 6: Commit**

  ```bash
  git add \
    pyproject.toml \
    .github/workflows/p5-parser-abi.yml \
    src/context_search_tool/syntax_parsers.py \
    tests/test_parser_abi.py \
    tests/test_exploration_boundaries.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "build: pin p5 parser dependencies"
  ```

### Task 3: Add The Pure V5 Graph Value Contract

**Files:**

- Create: `src/context_search_tool/graph_contract.py`
- Modify: `src/context_search_tool/models.py`
- Create: `tests/test_graph_models.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write failing default/identity tests**

  Cover every additive `CodeSignal` and `CodeRelation` default, root unit `""`,
  zero-based byte columns, recallability, all six resolution states, separated
  producer/resolution/effective confidence, and the exact closed relation kinds.

  Identity tests must prove:

  - a caller omitting every structured field receives the unchanged legacy ID;
  - a P5 signal is `s5:` plus 64 lowercase hex characters from fixed-key-order,
    UTF-8 NFC canonical JSON;
  - a P5 relation is `r5:` plus 64 lowercase hex characters from its exact
    selector tuple;
  - same-line, different-column overload declarations remain distinct;
  - same source/kind but different signature, arity, unit, or producer relations
    remain distinct;
  - semantic duplicate occurrences intentionally share one relation ID;
  - generated inputs that collide under the old eight-hex helper do not collide
    under v5.

- [ ] **Step 2: Implement one acyclic value owner**

  `graph_contract.py` owns only immutable constants, normalization, canonical
  JSON, ID helpers, confidence calculation, relation direction/weight/priority,
  and work budgets. It imports no domain model or store.

  Keep legacy ID helpers callable exactly as before. Add explicitly named v5
  helpers rather than making legacy behavior depend on truthy/empty structured
  fields. Reject non-finite/out-of-range confidence and invalid resolution/
  target-ID combinations at construction or persistence boundaries.

- [ ] **Step 3: Add the shared module identity helper**

  The helper accepts normalized repository-relative POSIX path, first chunk/range
  fields, and produces the one canonical `core_module` v5 identity. Later core,
  frontend, XML, explain, traversal, and association code must call it; boundary
  tests forbid those modules from reconstructing module IDs.

- [ ] **Step 4: Extend models additively**

  Append the exact defaulted fields from the design without reordering existing
  constructor parameters. Existing equality/serialization tests for legacy
  instances must remain unchanged. Occurrence location/count stays in relation
  metadata exactly as designed; do not add another top-level model field.

- [ ] **Step 5: Verify pure and protected behavior**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_graph_models.py \
    tests/test_sqlite_store.py \
    tests/test_chunker_java_plugin.py \
    tests/test_retrieval_core_boundaries.py
  git diff --check
  ```

  At this task boundary the production schema/indexer/default producer remains
  v4. New values are internal and directly tested only.

- [ ] **Step 6: Commit**

  ```bash
  git add \
    src/context_search_tool/graph_contract.py \
    src/context_search_tool/models.py \
    tests/test_graph_models.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "feat: add p5 graph value contract"
  ```

### Task 4: Add Java AST Facts Without Production Activation

**Files:**

- Create: `src/context_search_tool/java_ast.py`
- Create: `tests/test_java_ast.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write whole-file parser/fallback tests first**

  Valid fixtures must return one immutable fact set. Any compilation-unit
  `ERROR` or missing node—including package/import regions—must return one
  explicit `fallback_required` outcome and zero AST structural facts. Comments,
  strings, text blocks, annotation prose, and malformed suffixes cannot become
  declarations or edges.

- [ ] **Step 2: Freeze the internal fact vocabulary**

  Use narrow frozen dataclasses for package/imports, nested types, fields,
  methods/constructors, annotations, parameters/locals, call sites, type uses,
  and source byte ranges. Facts contain no SQLite IDs, chunks, scores, retrieval
  types, or repository-wide target decisions.

  All ranges use original zero-based UTF-8 byte columns and one-based lines. A
  shared byte-to-line map performs conversion; do not index Python character
  offsets as byte columns.

- [ ] **Step 3: Implement qualified declaration normalization**

  Cover package plus nested `$` type names, constructor `<init>`, erased ordered
  parameter FQCN signature, generic erasure, varargs-to-array normalization,
  primitives, arrays, explicit imports, same-package types, and wildcard
  candidate sets. Unproven type variables/external names remain unresolved facts
  rather than guessed FQCNs.

- [ ] **Step 4: Implement lexical binding and closed call evidence**

  Resolve receiver ownership only from `this`, exact typed parameters/locals/
  fields, and explicit exact constructors/casts. Respect nested scopes,
  shadowing, lambdas, anonymous classes, nested types, and local classes. Exact call signatures require every
  argument type to be proven by the design's closed evidence; otherwise emit
  owner/name/arity only. Never implement widening, boxing, subtype, chained-
  return, generic, lambda, method-reference, or varargs applicability.

- [ ] **Step 5: Implement closed type/framework facts and caps**

  Emit candidate facts for implements/interface method pairs, calls, return/
  parameter/field/local/new uses, and explicit non-wildcard imports. Framework
  annotation roles require exact FQCN or explicit import binding from the design
  allowlist. Custom/MapStruct names are negative.

  `uses_type` excludes primitives (including arrays), type variables, JDK/
  Jakarta/Javax/Spring/framework types, and external dependencies; only an exact
  same-unit repository type can survive later resolution.

  Apply the exact source-order caps before adapting facts: 256 explicit imports
  per file, 32 annotations per declaration, 16 literal arguments per annotation,
  256 UTF-8 bytes per literal, 128 call occurrences per declaration before edge
  deduplication, eight distinct `uses_type` targets, and 4,096 UTF-8 bytes of
  annotation SQL tokens. Record every omitted count. A source file must be
  unable to allocate unbounded fact lists before the later per-file 4,096/8,192
  caps.

- [ ] **Step 6: Prove protected Java parity**

  Compare the AST facts with current `JavaPlugin` outputs for the protected
  endpoint, route, symbol, method, type, token, comment-adjacent token, and
  malformed fixtures. The test owns an explicit parity matrix:

  - declaration/endpoint facts that must remain exact;
  - lexical metadata that must remain exact;
  - new structured facts allowed only after activation;
  - whole-file legacy output expected on fallback.

  Do not compare unordered sets where source order is contractual.

- [ ] **Step 7: Verify without registering the parser**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_parser_abi.py \
    tests/test_java_ast.py \
    tests/test_chunker_java_plugin.py \
    tests/test_acceptance_java_fixture.py \
    tests/test_retrieval_core_boundaries.py
  git diff --check
  ```

  Boundary tests prove `default_plugins()` still instantiates only the existing
  legacy Java producer and no ordinary import loads `java_ast`.

- [ ] **Step 8: Commit**

  ```bash
  git add \
    src/context_search_tool/java_ast.py \
    tests/test_java_ast.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "feat: add java ast facts"
  ```

### Task 5: Add Frontend And MyBatis Facts Without Production Activation

**Files:**

- Create: `src/context_search_tool/frontend_graph.py`
- Create: `src/context_search_tool/mybatis_xml.py`
- Create: `tests/test_frontend_graph.py`
- Create: `tests/test_mybatis_xml.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write Vue included-range lexer tests first**

  Test top-level `<script>` and `<script setup>`, quoted `>`, attributes,
  comments, multiple valid blocks, default JS, `lang="ts"`, original byte/line
  offsets, overlap/unclosed/nested negatives, and fake script text inside
  templates/comments. The bounded lexer returns ranges only; it reads no other
  file.

- [ ] **Step 2: Write JS/TS/TSX import and route tests first**

  Cover default/named/namespace/side-effect imports, both re-export forms, direct
  literal dynamic imports, extension and directory-index candidate sets,
  repository escape, bare package external state, computed/template imports,
  string/comment fakes, and parse-error subtrees. A standalone literal dynamic
  import outside one accepted route component/lazy form is an explicit negative:
  it does not emit an ordinary persistent `imports` edge.

  Vue `createRouter` and React `Route`/`createBrowserRouter`/`useRoutes` require
  unshadowed exact framework import bindings. Test inline/one-local-const arrays,
  literal components/lazy imports, exact nested path composition, and negatives
  for shadowing, wrappers, spreads, mutation, computed paths, custom APIs, and
  `.`/`..`.

- [ ] **Step 3: Implement pure frontend facts**

  Parser output contains module selectors, route source ranges/composed paths,
  component selectors, and producer diagnostics; it does not choose among
  active repository files. If a relevant import/route subtree has a parse error,
  the file emits no persistent frontend edge facts. The current regex fallback
  remains completely separate for later stale/legacy P4 on-demand use.

- [ ] **Step 4: Write the MyBatis security/range tests first**

  Positive: no DOCTYPE, both official HTTP/HTTPS Mapper 3.0 headers, the five
  predefined entities, and legal decimal/hex numeric character references.
  Negative: second/wrong DOCTYPE, internal subset, `<!ENTITY`, parameter entity,
  other named entity reference, XInclude detected by namespace URI regardless of
  prefix, malformed XML, wrong root, duplicate statement ID, parser/lexer
  sequence mismatch, and unbalanced locator.

  Range cases include quoted `>`, comments, CDATA fake tags, processing
  instructions, nested dynamic tags, multibyte text, self-closing direct child,
  and a late statement's original start/end range. Chunk attachment for that
  late statement and the missing-start-line-chunk failure belong to Task 7,
  after materialization exists.

- [ ] **Step 5: Implement the closed XML protocol**

  Scan bounded original bytes, validate at most the official DOCTYPE, replace
  only that declaration with equal-length ASCII whitespace while preserving
  every newline, then call `defusedxml.ElementTree.fromstring`. Never configure
  an external resolver or XInclude.

  The independent byte lexer records exact recognized direct-child statement
  ranges. Parsed and lexed `(local_tag, literal_id)` sequences must match
  one-for-one. Any mismatch fails the whole graph fact set closed while leaving
  generic indexing possible.

- [ ] **Step 6: Verify pure facts and no activation**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_parser_abi.py \
    tests/test_frontend_graph.py \
    tests/test_mybatis_xml.py \
    tests/test_frontend_roles.py \
    tests/test_retrieval_core_boundaries.py
  git diff --check
  ```

  `default_plugins()` and the production indexer still do not import/register
  either module. No test reaches the network.

- [ ] **Step 7: Commit**

  ```bash
  git add \
    src/context_search_tool/frontend_graph.py \
    src/context_search_tool/mybatis_xml.py \
    tests/test_frontend_graph.py \
    tests/test_mybatis_xml.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "feat: add frontend and mybatis facts"
  ```

### Task 6: Add V5 Store, Resolver, Lock, And Recovery Primitives

**Files:**

- Create: `src/context_search_tool/graph_lifecycle.py`
- Create: `src/context_search_tool/graph_resolution.py`
- Create: `src/context_search_tool/index_lock.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/vector_store.py`
- Modify: `src/context_search_tool/project_scope.py`
- Modify: `src/context_search_tool/scanner.py`
- Create: `tests/test_graph_store.py`
- Create: `tests/test_graph_resolution.py`
- Create: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_project_scope.py`
- Modify: `tests/test_tokenizer_scanner.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write v4/v5/future schema tests first**

  Build literal v4 databases independent of current constructors. Prove column
  introspection supplies all defaults and never indexes a missing SQLite row
  key. Build v5 databases and prove exact columns, active indexes, codecs,
  root-unit `""`, recallable filtering, both confidence components, occurrence
  metadata, and resolved incoming/outgoing queries.

  A stored version >5 must raise `IncompatibleSignalSchemaError` before any
  unknown-column query or DDL. Capture table/schema/metadata hashes before and
  after refusal and require equality.

- [ ] **Step 2: Implement the atomic v4-to-v5 DDL transaction**

  One explicit transaction drops only v4 signal/relation tables, creates exact
  v5 tables/indexes, and writes schema 5, graph version 1, stale state,
  `schema_migration`, and durable full-reindex flag 1. Fault before commit must
  leave a complete v4 database; a concurrent read may observe only complete v4
  or empty v5-stale, never mixed metadata/tables. In the retained rollback
  journal, a reader already holding the v4 snapshot keeps it and the DDL commit
  waits; the next reader after commit sees only complete empty v5-stale.

  This helper remains inaccessible from the production indexer until Task 8.

- [ ] **Step 3: Implement bounded v5 store APIs**

  Add transaction-scoped bulk replace APIs, active signal lookup by exact
  selector, uniqueness lookup with SQL `LIMIT 2`, source/target adjacency with
  canonical order and `LIMIT 65`, chunk-attached plus owning-module lookup,
  active module lookup by exact path, association generation markers, integrity
  counts, and stale marker transition.

  `signal_search()` on a direct v5 test store filters `recallable=1`. Textual
  target lookup accepts only `resolution='legacy'`. The existing
  `signals_for_chunks()`/`relations_for_source(s)`/`relations_targeting()` APIs
  remain an explicit legacy-compatible read view and never expose a structured
  row to old expansion/ranking/selection/P4 callers. New, clearly named graph
  APIs own module promotion, structured outgoing/incoming rows, and diagnostic
  states. No API returns all graph rows and truncates them only in Python.

  Add `GraphReadSession`, backed by one SQLite connection and explicit read
  transaction. It reads capability/state once from that snapshot and owns every
  signal/module/adjacency/target-integrity lookup for one graph-consuming
  operation. Preserve SQLite's existing rollback-journal mode; P5 does not add a
  WAL migration. Direct concurrency tests pause a ready reader, start an indexer,
  and prove its conflicting commit waits while the reader finishes against the
  complete old-ready snapshot. After that read transaction closes, the writer
  commits stale before graph writes and a later session sees stale/no-graph. Use
  one explicit 5,000 ms production busy timeout and fail with the stable internal
  busy error if the reader outlives it; focused tests inject a shorter timeout.
  No per-method new connection may escape this session. Task 9 wires the private
  query/selection/P4 seams to it; Task 10 wires public query and explain.

- [ ] **Step 4: Implement resolver state transitions**

  Resolve in canonical source unit/path/range/kind/selector/relation-ID order.
  Clear target/resolution confidence before classification. Apply exact module,
  exact Java signature, unique owner/name/arity, frontend complete-candidate,
  external, unresolved, and ambiguous rules in the design; fetch at most two
  legal rows.

  Resolver tests cover cross-unit rejection, root unit, wildcard ambiguity,
  extension/index ties, deleted targets, exact vs unique confidence, re-running
  from prior resolved state without confidence compounding, and deterministic
  output under reversed insertion order.

- [ ] **Step 5: Add exclusive lock primitives**

  Lock a fixed regular file inside the repository index directory from schema
  detection through readiness. Validate owner/type/mode and reject symlinks.
  Use supported standard-library advisory locking on POSIX and Windows; if
  exclusive locking is unavailable, fail closed. A second process raises the
  stable internal busy error and never enters DDL/resolution. Keep the lock file
  and release its descriptor; do not unlink it and create a race.

- [ ] **Step 6: Add fresh vector replacement**

  A mandatory full rebuild creates a new in-memory ID/vector set without loading
  existing files. An incremental rebuild loads one validated published
  generation, applies all canonical removals/upserts in memory, and likewise
  produces a complete replacement set; P5 never updates either published file
  in place. Persist each next immutable generation pair such as
  `vectors.<generation>.npy` and `vector_ids.<generation>.json`, plus one small
  descriptor containing generation, filenames, hashes, row count, dimensions,
  and embedding-config identity. Write each generation file through a
  same-directory temp, flush, fsync, rename, and directory-fsync; read it back
  and validate pair hashes/counts before any source hash is committed. Preparing
  the files does not publish them. Only the later artifact-publication step may
  atomically replace/fsync the single descriptor after SQLite file writes and
  both resolver stages are complete.

  Never overwrite a generation in place and retain at least the prior complete
  generation through the entire operation/recovery; cleanup is outside this P5
  transaction. A reader can load either the old or new descriptor, never mixed
  IDs/matrix. It must then validate descriptor hashes/counts/embedding identity,
  manifest/config identity, and equality with active SQLite embedding IDs in its
  own read snapshot before vector recall. Any mismatch in a stale snapshot skips
  the vector stage for that operation, logs stable `vector_snapshot_mismatch`,
  and continues only lexical/path/anchor recall; a ready snapshot mismatch is an
  integrity error and cannot silently degrade. Legacy indexes without a
  descriptor read the current `vectors.npy`/`vector_ids.json` pair until v5
  activation. Inject a crash at every generation temp write/fsync/rename and
  later descriptor replace/directory-fsync seam. Final coverage validation
  compares active chunk embedding IDs to the descriptor-selected vector ID set
  exactly for full and incremental indexes.

- [ ] **Step 7: Add unit topology and scanner safety**

  Fingerprint full canonical JSON of unit root, kind, and sorted marker paths
  with SHA-256. Test every listed marker add/remove/move, nested units, root
  `""`, order independence, and display-name irrelevance.

  Add a new, currently uncalled v5-safe candidate/read path. It resolves the
  repository and candidate strictly, rejects a symlink at the file or any
  below-root path component, proves resolved containment, then applies existing
  ignore/regular/binary/size rules. Its bounded `read_scanned_file_bytes` helper
  repeats those checks and verifies size/full SHA-256 immediately before
  preparation, so a scan-to-index swap cannot feed different bytes. It returns
  one immutable byte buffer for parsing and chunk decoding; `ScannedFile` does
  not retain every repository file body in memory. Direct tests cover outside
  file links, internal link chains, broken links, escape-after-resolution, and
  replacement between scan/read.

  Do not change or call the current public `scan_workspace()` path in this task.
  A boundary AST/import/call test proves public v4 indexing still uses the exact
  old scanner. Task 8's test-only v5 orchestrator calls the safe path explicitly;
  Task 10 switches public indexing and the canonical Task-7 test classifier
  together.

- [ ] **Step 8: Test readiness/failure primitives directly**

  Direct tests inject failures at DDL, fresh vector write, resolver transaction,
  and final integrity. They assert state never becomes ready prematurely and
  `full_reindex_required` cannot clear independently from the final ready
  transaction. Deterministic interleaving tests also prove `GraphReadSession`
  snapshot isolation, rollback-journal writer-waits-for-reader behavior with the
  bounded busy outcome, and old/new-complete vector generation reads. Full index
  orchestration/source-hash-last belongs to Task 8.

- [ ] **Step 9: Verify focused and protected gates**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_graph_store.py \
    tests/test_graph_resolution.py \
    tests/test_graph_lifecycle.py \
    tests/test_sqlite_store.py \
    tests/test_embeddings_vector_store.py \
    tests/test_project_scope.py \
    tests/test_tokenizer_scanner.py \
    tests/test_retrieval_core_boundaries.py
  git diff --check
  ```

  Boundary tests prove production `CURRENT_SIGNAL_SCHEMA_VERSION` remains 4 and
  indexer does not import/use the new migration, resolver, or lock yet.

- [ ] **Step 10: Commit**

  ```bash
  git add \
    src/context_search_tool/graph_lifecycle.py \
    src/context_search_tool/graph_resolution.py \
    src/context_search_tool/index_lock.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/vector_store.py \
    src/context_search_tool/project_scope.py \
    src/context_search_tool/scanner.py \
    tests/test_graph_store.py \
    tests/test_graph_resolution.py \
    tests/test_graph_lifecycle.py \
    tests/test_embeddings_vector_store.py \
    tests/test_project_scope.py \
    tests/test_tokenizer_scanner.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "feat: add graph lifecycle primitives"
  ```

### Task 7: Add Producer Adapters And Exact Test Association

**Files:**

- Create: `src/context_search_tool/java_graph.py`
- Create: `src/context_search_tool/graph_plugins.py`
- Create: `src/context_search_tool/test_paths.py`
- Create: `src/context_search_tool/test_association.py`
- Modify: `src/context_search_tool/frontend_graph.py`
- Modify: `src/context_search_tool/mybatis_xml.py`
- Create: `tests/test_test_association.py`
- Modify: `tests/test_java_ast.py`
- Modify: `tests/test_frontend_graph.py`
- Modify: `tests/test_mybatis_xml.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Add an internal project-aware graph extraction context**

  Define one frozen `PluginContext` containing normalized source path/language,
  project-unit key/metadata, and scanned active path inventory. Define a separate
  internal `GraphLanguagePlugin` protocol for the new adapters in leaf module
  `graph_plugins.py`, with two pure phases:

  1. `parse(context, content)` returns symbols/tokens plus immutable language
     facts or a whole-file fallback payload;
  2. `materialize(context, parsed, chunks, module_signal)` returns final
     signals/relations after chunks and the canonical module identity exist.

  The protocol contains no store, retrieval config, network client, callback,
  repository read, or mutable repository-wide resolver state. This sequencing
  avoids inventing a module ID before its first active chunk exists and lets XML
  fail closed when a statement has no containing chunk.

  Do not change the existing `LanguagePlugin.extract(path, content)` protocol,
  the legacy `JavaPlugin`, current indexer call site, or `default_plugins()` in
  this task. `JavaGraphProducer.parse()` returns the AST layer's immutable
  `fallback_required` marker and zero structured facts; it must not import or
  invoke `JavaPlugin`. Task 10's final coordinator alone converts that marker to
  the preserved private whole-file legacy extraction result. This keeps the
  import direction one-way and atomically changes the production protocol/call
  site and registration together.

- [ ] **Step 2: Write Java graph-adapter tests first**

  Instantiate `JavaGraphProducer` explicitly. Valid AST facts must produce v5
  declaration/endpoint signals, `implements`, `implements_method`, `calls`,
  capped `uses_type`, and module-source `imports_type` selectors with exact
  producer/range/unit/signature/arity/confidence fields.

  Whole-file fallback returns only the explicit marker and zero structured
  signals/relations—no mix of legacy declarations and structured edges. A
  boundary test separately proves the still-public legacy plugin output remains
  unchanged; Task 10 owns the exactly-once coordinator fallback test. The parity
  matrix remains exact for recallable protected signals/tokens.

- [ ] **Step 3: Add frontend and MyBatis adapters**

  Explicit producer instances materialize accepted facts into non-recallable
  route/MyBatis statement signals and structured `imports`, `routes_to`, and
  `mapped_by` selectors only after chunks/module are passed in. Every accepted
  graph-only signal attaches to the chunk containing its own start line; missing
  attachment fails that producer closed and returns only generic chunks/module.

  Frontend candidate enumeration uses the complete active scanned set and never
  `resolve_frontend_import()`'s old preference-first result. XML statements use
  shared module identity and exact lexed ranges. Neither adapter is registered
  by default yet. Materialization tests prove a late mapper statement attaches
  to its own containing chunk and a missing start-line chunk fails the entire
  MyBatis graph producer closed while retaining generic chunks/module.

  A MyBatis selector is `<namespace>#<literal-id>`. Canonicalize
  `parameterType` to an exact method signature only when every type is proven;
  otherwise emit namespace+ID for unique resolution at 0.90. Bounded SQL plus
  `parameterType`/`resultType` supply lexical tokens only, never entity/SQL
  semantics.

- [ ] **Step 4: Write the complete test rewrite matrix first**

  Cover every positive and negative in the design table, including Java longest
  suffix and `Contest`, Go `_test`, Rust same-dir plus unit-root `tests/`, Python
  independent prefix/suffix union, JS/TS `__tests__`/unit-root/sibling complete
  suffix set, empty/dot/dot-dot/multiple-`__tests__`, generated/fixture/snapshot/
  golden/test-data directories, cross-unit, inactive, and test-to-test targets.

  Put the case-sensitive anchored test classifier and pure candidate rewrites in
  leaf module `test_paths.py` as the one canonical P5 owner used by association
  and the later v5 scanner
  path. It recognizes the exact language table and Java `FooTest`, `FooTests`,
  `FooIT`, and `FooITCase` from the complete original stem; `Contest.java`
  remains production. Task 10 wires it into public scanning.

- [ ] **Step 5: Implement persisted-import association**

  Generate convention candidates as a complete set, filter active legal module
  targets, and accept only one. Separately read resolved stage-one `imports_type`
  and frontend `imports` rows, map their target source file to the canonical
  module signal, and retain at most eight exact production targets. Never use
  raw token/comment/basename evidence.

  Test that an unchanged Java test recovers its association from persisted
  `imports_type` after only a production file changes. Generation deletes and
  rebuilds all prior `producer='test_association'` rows transactionally.
  Explicit resolved imports produce exact 1.00 resolution confidence;
  unique mirrored/sibling convention paths produce exact 0.95. If both evidence
  paths name the same module, canonical deduplication retains one deterministic
  association with the strongest legal evidence and occurrence provenance.

- [ ] **Step 6: Prove adapters remain unregistered**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_java_ast.py \
    tests/test_frontend_graph.py \
    tests/test_mybatis_xml.py \
    tests/test_test_association.py \
    tests/test_chunker_java_plugin.py \
    tests/test_retrieval_core_boundaries.py
  git diff --check
  ```

  Tests instantiate new adapters through the internal graph protocol directly.
  Production schema remains 4, the existing plugin protocol/call site and
  `default_plugins()` remain legacy-only, and ordinary query/index behavior is
  byte-compatible with the Task-0 baseline.

- [ ] **Step 7: Commit**

  ```bash
  git add \
    src/context_search_tool/java_graph.py \
    src/context_search_tool/graph_plugins.py \
    src/context_search_tool/test_paths.py \
    src/context_search_tool/test_association.py \
    src/context_search_tool/frontend_graph.py \
    src/context_search_tool/mybatis_xml.py \
    tests/test_test_association.py \
    tests/test_java_ast.py \
    tests/test_frontend_graph.py \
    tests/test_mybatis_xml.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "feat: add p5 graph producers"
  ```

### Task 8: Build The Complete Internal V5 Index Path Without Activation

**Files:**

- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/plugins.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/vector_store.py`
- Modify: `src/context_search_tool/manifest.py`
- Modify: `src/context_search_tool/paths.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_graph_store.py`
- Modify: `tests/test_graph_resolution.py`
- Modify: `tests/test_indexer_manifest.py`
- Modify: `tests/test_embeddings_vector_store.py`
- Modify: `tests/test_config_paths.py`
- Modify: `tests/test_retrieval_core_boundaries.py`

- [ ] **Step 1: Write internal v5-orchestrator tests first**

  Add one narrow internal `build_v5_index_snapshot()` orchestration seam and
  invoke it only from focused tests with explicitly injected P5 plugins/safe
  scanner. Tests must fail before it exists and cover:

  - a fresh repository becomes schema 5/graph version 1/ready and has exactly
    one module signal for every active non-empty file;
  - an empty file keeps a source record but no chunk/module;
  - a literal v4 database transitions atomically to empty v5-stale/full=1, then
    rebuilds every index-eligible file/chunk/token/FTS/vector/signal/relation;
  - old source hashes and corrupt/mismatched vector files cannot skip a mandatory
    full rebuild;
  - all three explicitly injected producer adapters run in deterministic order;
    malformed Java returns only `fallback_required` and zero structured facts,
    while the still-public v4 Java plugin remains unchanged; Task 10 owns the
    final coordinator's exactly-once private legacy fallback proof;
  - source hash changes only after that file's chunks/vector identity/signals/
    producer relations persist;
  - producer resolver completes before association generation, which completes
    before the second resolver and final readiness;
  - a ready unchanged no-op performs integrity checks but no extraction,
    embedding, resolver, association, or source write;
  - a changed ready index marks stale before its first graph-relevant write and
    re-resolves every active structured relation;
  - stale-on-entry and topology change re-extract every graph-eligible file even
    when hashes match; full=1 re-extracts every index-eligible file;
  - deletions remove/reclassify targets before ready and test associations are
    regenerated even when no test source changed.

- [ ] **Step 2: Complete internal graph capability/read views**

  The internal v5 builder treats versions exactly as `<5`, `==5`, or `>5`;
  future versions refuse before initialization or table mutation. Direct-store
  tests exercise the complete capability matrix and v4 adapter.

  The existing broad store reads used by current expansion/ranking/selection/P4
  are the explicit legacy-only views described in Task 6. A ready-v5 direct
  store containing resolved, ambiguous, external, unresolved, and imports_type
  rows must still yield none of those rows through the old APIs. Public query,
  CLI, MCP, schema constant, and capability dispatch remain v4 until Task 10.

- [ ] **Step 3: Acquire one lock across the entire protocol**

  Before the lock, allow only validated index-directory creation and lock-file
  bootstrap—no `.gitignore`, config, manifest, SQLite schema, or vector write.
  Resolve repository/index path, acquire the exclusive lock, then inspect
  schema/readiness/full flag/topology/scanned changes. Hold it through final
  manifest/config/indexed-at writes and ready commit. A second index operation
  fails with the internal busy error and performs zero mutation/embedding/
  resolution. Task 10 wires that error to existing CLI/MCP surfaces.

- [ ] **Step 4: Implement read-before-mutation and stale-before-write**

  Scan eligible files, detect units/topology, compare active paths/hashes, and
  determine full/graph recovery without graph mutation. For an unchanged
  ready/full=0 snapshot, run bounded readiness integrity and exit only if it
  succeeds.

  Otherwise commit `graph_resolution_state=stale` and a stable reason before the
  first graph-relevant write. For v4 use the atomic migration helper first. For
  new/missing schema, create the complete empty v5-stale/full=1 schema directly;
  never create an intermediate v4 database.

  Closed stable reasons are at least `schema_migration`, `full_reindex`,
  `topology_changed`, `files_changed`, `stale_on_entry`,
  `integrity_check_failed`, and later `dangling_target`. Do not persist exception
  text or absolute paths.

- [ ] **Step 5: Rebuild complete file snapshots with source hash last**

  Refactor preparation to call the scanner's bounded, revalidating read helper
  once and use that verified byte buffer for plugin parsing, text decoding,
  chunking, and hash confirmation; do not call `absolute_path.read_text()` or
  open an unchecked path. Run the exact two-phase protocol: parse facts/symbols,
  build chunks, create the shared module signal on the first active chunk, then
  materialize and attach producer signals/relations. Merge semantic duplicate
  relation occurrences by earliest byte position/count, then apply per-file
  4,096-signal and 8,192-producer-relation caps.

  The core module is never displaced by a cap. Producer facts retain canonical
  source-range/kind/ID order, and existing source-file plugin metadata persists
  exact omitted counts for every per-node/per-file truncation; do not add an
  unreviewed table or public field for those diagnostics.

  Before committing any changed source hash, construct the complete next vector
  set across the whole operation. A mandatory full rebuild starts empty; an
  incremental run loads one validated published generation and applies all
  deletions/upserts in canonical order. Write, fsync, and read-validate the new
  immutable generation files now, but leave the descriptor pointing at the old
  generation. If generation preparation fails, no source hash may change.

  Persist in this order for each file:

  1. chunks, token/FTS rows, and embedding identity that already exists in the
     validated unpublished generation;
  2. signals, including module;
  3. deduplicated producer relations;
  4. source file record/new hash last.

  A file with no chunks persists its source hash only after its empty chunk/
  graph state is complete. Both full and incremental vector generations are
  durably prepared before any source hash that claims their embedding snapshot;
  neither path mutates a published vector/ID file in place.

- [ ] **Step 6: Enforce the two resolver stages**

  After all file writes and deletions:

  1. resolve every non-association structured producer relation in one
     deterministic transaction;
  2. delete/regenerate all test association rows from active modules and the
     now-resolved imports/type facts in one transaction;
  3. resolve every generated `tests` row in a second transaction.

  The association-generation marker records its source producer-resolution
  generation so final integrity can prove ordering. Do not use only changed-file
  in-memory facts.

- [ ] **Step 7: Durably finish external artifacts, then mark ready last**

  While SQLite is still stale and after both resolvers, atomically publish the
  already validated immutable vector generation by replacing/fsyncing its one
  descriptor. Then atomically write config and schema-v1 manifest through
  same-directory temp+file-fsync+rename+directory-fsync. Read all external
  artifacts back as one logical tuple and validate descriptor file hashes,
  counts, dimensions, embedding/config/manifest identity, and exact equality
  between descriptor IDs and active SQLite embedding IDs. No external artifact
  is written after ready.

  A stale reader uses one SQLite read snapshot and independently validates that
  same tuple. If it overlaps SQLite commits or any descriptor/config/manifest
  rename and the tuple does not match, it emits the one stale warning/log plus
  stable `vector_snapshot_mismatch`, skips vector recall, and continues only the
  coherent lexical/path/anchor results from that SQLite snapshot; it never mixes
  vector scores from another generation. Once state is ready, the same mismatch
  is fatal integrity failure and the next index marks stale/recovers. Tests pause
  at every publication boundary and prove exactly these outcomes.

  Only then, in one final SQLite transaction, prove exact schema/version, active
  target integrity, state/target/confidence equations, active source ownership, one module per
  graph-eligible file, association ordering, current topology fingerprint,
  active chunk-to-vector ID equality for every rebuild, source/chunk counts,
  external-artifact reread, and no unfinished file write. Then write
  `indexed_at`/fingerprint/version, clear stale reason/full flag, and set ready
  together. If anything fails, leave stale and report no successful summary.

  Until Task 10, expose these as explicitly named v5 persistence helpers used
  only by the internal builder; leave the current v4 `persist()`/manifest/config
  call path and serialized bytes exact. Task 10's public switch reaches the v5
  helpers only through `build_v5_index_snapshot()`.

- [ ] **Step 8: Add exhaustive crash/recovery seams**

  Parameterize failures after chunks, vectors, signals, producer relations,
  source hash, deletions, first resolver, association generation, second
  resolver, every vector/config/manifest temp-write/fsync/rename/directory-fsync,
  external reread, final validation, immediately before ready commit, and after
  an acknowledged ready commit. Before/rolled-back commit failures must remain
  stale; if migration/full work began they retain full=1. A crash after a
  successful acknowledged commit must expose one complete ready/full=0 snapshot
  whose external tuple validates, and the rerun must take the verified no-op
  path. For a process-kill/commit-result-unknown seam, restart may observe either
  complete stale or complete ready, but never partial-ready; inspect state and
  follow the corresponding recovery/no-op path before comparing the same
  canonical ready projection.

  Specifically prove a failure after a source hash cannot cause a later skip:
  stale-on-entry forces graph-eligible re-extraction, while durable full=1 forces
  all files. Also prove no ready edge points to a deleted/soft-deleted signal.

- [ ] **Step 9: Prove public production remains exactly v4**

  AST/import/call boundary tests prove public `index_repository()` still calls
  the current v4 scanner/plugin path, `CURRENT_SIGNAL_SCHEMA_VERSION == 4`,
  `default_plugins()` remains legacy-only, no public CLI/MCP/query path imports
  or calls `build_v5_index_snapshot()`, and current expansion/ranking/selection/
  P4 cannot read a structured row through a legacy API. Current v4 vector/
  manifest/config persistence methods remain the invoked methods. The internal
  builder may create a ready v5 test repository; ordinary production cannot
  reach it yet.

- [ ] **Step 10: Run internal-index and protected-v4 gates**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q \
    tests/test_graph_store.py \
    tests/test_graph_lifecycle.py \
    tests/test_graph_resolution.py \
    tests/test_test_association.py \
    tests/test_indexer_manifest.py \
    tests/test_embeddings_vector_store.py \
    tests/test_config_paths.py \
    tests/test_retrieval_core_boundaries.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_exploration_contracts.py \
    tests/test_exploration_runner.py
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

  The full suite may gain P5 test passes but retains the exact nine skip
  identities and zero xfails. Existing public index/query/direct winners/score
  parts and no-edge baseline remain byte-identical because schema 5 and resolved
  traversal are both still production-unreachable.

- [ ] **Step 11: Commit the activation-ready internal path**

  ```bash
  git add \
    src/context_search_tool/indexer.py \
    src/context_search_tool/plugins.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/vector_store.py \
    src/context_search_tool/manifest.py \
    src/context_search_tool/paths.py \
    tests/test_graph_lifecycle.py \
    tests/test_graph_store.py \
    tests/test_graph_resolution.py \
    tests/test_indexer_manifest.py \
    tests/test_embeddings_vector_store.py \
    tests/test_config_paths.py \
    tests/test_retrieval_core_boundaries.py
  git commit -m "feat: prepare p5 graph indexing"
  ```

### Task 9: Build Resolved Graph Evidence Without Public Activation

**Files:**

- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `src/context_search_tool/retrieval_core/candidates.py`
- Modify: `src/context_search_tool/retrieval_core/expansion.py`
- Modify: `src/context_search_tool/retrieval_core/relation_policy.py`
- Modify: `src/context_search_tool/retrieval_core/ranking.py`
- Modify: `src/context_search_tool/retrieval_core/evidence_merge.py`
- Modify: `src/context_search_tool/retrieval_core/context_expansion.py`
- Modify: `src/context_search_tool/retrieval_core/selection.py`
- Modify: `src/context_search_tool/retrieval_core/tracing.py`
- Modify: `src/context_search_tool/exploration/probes.py`
- Create: `tests/test_resolved_graph_expansion.py`
- Modify: `tests/test_retrieval_core_primitives.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_retrieval_core_boundaries.py`
- Modify: `tests/test_exploration_probes.py`
- Modify: `tests/test_exploration_runner.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`

- [ ] **Step 1: Write direction and admission tests first**

  For each closed kind, prove the exact outgoing/incoming behavior. Incoming
  `implements`, `implements_method`, `mapped_by`, and gated `tests` must admit
  the active source chunk, never re-use the row target. `imports_type` is always
  association-only. Structured non-resolved states and stale graph data admit
  nothing; legacy rows retain existing outgoing name behavior only.

- [ ] **Step 2: Build the exact initial frontier**

  Add one private, explicitly injected v5 retrieval seam in `retrieval.py`; the
  public `query_repository()` still calls only its v4 path. The private seam
  opens one `GraphReadSession` before graph capability/signal recall and keeps
  that same SQLite snapshot through relation expansion, ranking, context
  expansion, selection summary/reasons, and trace collection. Every graph helper
  receives the session explicitly; none reopens the database behind it. A
  stale/legacy session exposes only its legal capability. An injected P4
  post-query seed collection opens one separate bounded session and either sees
  one complete ready snapshot or uses the existing legacy/stale fallback.

  From already admitted seed candidates, batch-load signals attached to each
  seed chunk plus its file's core module even when that module lives on another
  chunk. Deduplicate IDs, order by seed rank/source priority/path/range/ID, and
  cap the total at 512. Other non-recallable nodes enter only by an overlapping
  admitted chunk or resolved ID edge.

  Add long-file fixtures proving a second/later chunk can follow a module import,
  reverse test, and P4 test-gap edge.

- [ ] **Step 3: Implement resolved and legacy traversal separately**

  Resolved edges walk IDs for at most four hops; legacy edges keep the current
  three-hop name fallback. Apply per-direction SQL `LIMIT 65`/retain 64 and the
  global limits: 4,096 signals popped, 16,384 edges examined, 8,192 frontier
  entries, and existing 1,000 relation-expanded candidates.

  Stop after the current canonical item when a global cap is reached and return
  the already ordered prefix. Record internal truncation for explain/tests but
  add no trace schema field.

- [ ] **Step 4: Implement complete-tuple dominance**

  Store and compare the full tuple: resulting score descending, hops ascending,
  minimum confidence descending, kind priority, outgoing before incoming,
  source ID, target ID, chunk ID. Revisit a signal only for a strictly better
  complete tuple, including equal score/fewer hops/later tie-break improvement.
  Use the same comparator for frontier, candidate truncation, and retained best
  reason.

  Tests reverse SQLite insertion/adjacency order and cover cycles, diamonds,
  repeated improvements, high degree, many signals in one chunk, and exact cap
  prefixes.

- [ ] **Step 5: Add one truthful graph score contribution**

  Calculate `next_score = current_score * effective_confidence * kind_weight *
  0.8`. Set exactly one of the seven closed graph `_match` keys to the clamped
  retained best-path score. `implements_method` shares
  `graph_implements_match`.

  `_combined_score()` adds the maximum closed graph key exactly once. Resolved
  candidates set non-scoring `resolved_relation=1` plus exactly one
  `graph_seed_original=1` or `graph_seed_planner=1`; they never set numeric
  `relation`, `original_relation`, or `planner_relation`. Legacy behavior remains
  unchanged.

- [ ] **Step 6: Update every provenance consumer consistently**

  Rank tier, original/planner relation predicates, span/trace source mapping,
  relation-support reasons, adjustment visibility, and evidence merge must all
  recognize the new flags/keys without treating flags as score. A selected
  graph result exposes the `_match` adjustment through the existing trace final
  selection; `TraceCandidate` remains unchanged and makes no edge-ID claim.

  Update `selection.py` and `context_expansion.py` explicitly: structured
  non-resolved rows provide no relation support; resolved provenance maps to the
  existing `relation` span/source class without a numeric score; implementation
  summary/reason construction uses the session's legal resolved/legacy view;
  graph reachability cannot add `implementation chain match` or mutate summary/
  reasons for a protected direct result. No consumer may query the old broad
  relation APIs after v5 activation.

  Add one best-path human reason from the exact seven design phrases under the
  existing reason cap.

- [ ] **Step 7: Protect direct evidence before merge**

  Apply the existing `original_direct` predicate, represented by
  `evidence_priority == 0`, before any graph merge. If graph reaches a protected
  direct candidate, return the original object/value unchanged: score, every
  score part, reasons, evidence priority, semantic matches, spans, and ordering
  key all remain exact. Do not create a second direct-protection predicate.

- [ ] **Step 8: Gate tests and P4 with existing intent/goals**

  Pass the normalized existing `infer_query_intent()` test intent to the sole
  relation stage. Ordinary retrieval traverses `tests` only for exact test
  intent. P4 may reverse a test edge only for explicit test intent or an already
  frozen unsatisfied test goal.

  P4's collector reads at most one ready resolved hop from selected origin
  signals/modules within its existing seed cap. Resolved imports map to existing
  `static_import`; all other allowed kinds map to existing `relation_target`.
  Do not add an enum, probe, round, concurrent call, or model planner. Prove the
  total remains <=3 retrieval calls.

- [ ] **Step 9: Fail closed on a dangling target**

  If a ready resolved row references a missing/inactive target during a query,
  stop all graph use for the remainder of that operation and return only already
  collected lexical/vector/path/anchor evidence. Record the fault on the read
  session, close/roll back that read transaction, then attempt one separate short
  write transaction to persist stale/`dangling_target`; never try to upgrade the
  read snapshot. On read-only/busy failure, log the stable marker in-process. The
  next unchanged index no-op integrity check must discover and recover the same
  issue. Never synthesize a name match.

- [ ] **Step 10: Prove the complete implementation remains dormant**

  Direct tests inject a ready-v5 store into the private retrieval/P4 seams and
  prove every traversal, scoring, provenance, cap, dangling-target, and
  concurrency rule above. Separate boundary tests prove public
  `index_repository()`/`query_repository()`, current schema constant,
  `default_plugins()`, scanner, CLI/MCP payload/text, ContextPack roles, and P4
  still execute exact v4 behavior. No public import or default call reaches the
  private v5 retrieval seam. Task 10 is the sole activation boundary after
  explain and MyBatis role behavior are green too.

- [ ] **Step 11: Verify focused, protected, and full gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_resolved_graph_expansion.py \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_runner.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_context_pack.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_exploration_contracts.py
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

- [ ] **Step 12: Commit dormant resolved graph evidence**

  ```bash
  git add \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/candidates.py \
    src/context_search_tool/retrieval_core/expansion.py \
    src/context_search_tool/retrieval_core/relation_policy.py \
    src/context_search_tool/retrieval_core/ranking.py \
    src/context_search_tool/retrieval_core/evidence_merge.py \
    src/context_search_tool/retrieval_core/context_expansion.py \
    src/context_search_tool/retrieval_core/selection.py \
    src/context_search_tool/retrieval_core/tracing.py \
    src/context_search_tool/exploration/probes.py \
    tests/test_resolved_graph_expansion.py \
    tests/test_retrieval_core_primitives.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_runner.py \
    tests/test_retrieval_trace_pipeline.py
  git commit -m "feat: add dormant resolved graph evidence"
  ```

### Task 10: Prepare Explainability And Activate Complete Public V5

**Files:**

- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/plugins.py`
- Modify: `src/context_search_tool/java_plugin.py`
- Modify: `src/context_search_tool/scanner.py`
- Modify: `src/context_search_tool/models.py`
- Modify: `src/context_search_tool/sqlite_store.py`
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `src/context_search_tool/retrieval_core/selection.py`
- Modify: `src/context_search_tool/context_pack/roles.py`
- Modify: `src/context_search_tool/cli.py`
- Modify: `src/context_search_tool/mcp_tools.py`
- Create: `tests/test_p5_explain.py`
- Create: `tests/test_p5_privacy.py`
- Modify: `tests/test_graph_lifecycle.py`
- Modify: `tests/test_indexer_manifest.py`
- Modify: `tests/test_tokenizer_scanner.py`
- Modify: `tests/test_chunker_java_plugin.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/test_retrieval_core_boundaries.py`
- Modify: `tests/test_context_pack.py`
- Modify: `tests/test_cli_commands.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_exploration_probes.py`
- Modify: `tests/test_exploration_fusion.py`
- Modify: `tests/test_exploration_runner.py`
- Modify: `tests/test_retrieval_trace_pipeline.py`

Steps 1-5 add direct-testable projection and role helpers only. Public schema,
index/query/plugin/scanner/CLI/MCP/ContextPack behavior must remain v4 until the
single switch in Step 6; the task is not committed in an intermediate state.

- [ ] **Step 1: Write exact MCP payload tests first**

  Preserve existing `chunk` bytes and top-level `ok, repo, chunk` order, then
  append `graph`. Assert exact graph/signal/edge key order, integer schema 0 for
  missing metadata, null resolution confidence, empty unresolved target ID/path,
  canonical sort, 32/32/32 caps, and exact omitted counts.

  Ready membership is the complete union of signals attached to the selected
  chunk and its owning file module, even when the module is on another chunk.
  Outgoing diagnostics include all active states/facts from the complete
  universe; incoming includes active resolved rows targeting it. Dedupe before
  sort/cap and compute omission against the complete pre-cap sets.

- [ ] **Step 2: Write legacy/stale/future explain tests**

  Missing/<5 renders `legacy`, stale renders `stale`, arrays empty, omission
  counts zero. Future schema returns the normal `incompatible_signal_schema`
  error without reading unknown columns. No graph state returns a source excerpt
  beyond the existing chunk payload.

- [ ] **Step 3: Write CLI golden tests first**

  Require every existing line byte-for-byte, then the four exact summaries and
  bounded `Signal`, `Outgoing`, and `Incoming` lines from the design. Own spaces,
  source/target fallback names, confidence formatting, ordering, empty/null
  rendering, and omission counts. Legacy/stale renders only the four summaries.

- [ ] **Step 4: Implement one bounded graph projection**

  Put membership/query/canonical item construction in a shared internal helper
  used by CLI and MCP, returning values rather than pre-rendered text. Fetch
  bounded adjacency through one `GraphReadSession` snapshot; do not reopen per
  list, expose all graph rows, or invoke parser/resolver/indexing.

- [ ] **Step 5: Assign MyBatis existing role/group**

  Add one defaulted private `_context_role_hint` field to `RetrievalResult`, with
  `repr=False` and `compare=False`. It is not emitted by query/MCP/trace/explain
  serializers and adds no score part, public JSON key, role, or group. Before the
  ready-v5 `GraphReadSession` closes, retrieval sets exact value
  `mybatis_repository` only on results whose active file owns an accepted
  `mybatis_statement` signal with the reviewed producer in that same snapshot;
  use one indexed file/kind/producer `EXISTS`/`LIMIT 1` session lookup, never an
  all-row fetch. Task 9 has already threaded that session through selection;
  Task 10 modifies the real `selection.py` `RetrievalResult(...)` construction
  point to attach the hint exactly once. Do not post-process with
  `retrieval.py`/`replace`, use candidate merge, or mutate an existing protected
  direct result. Missing/legacy/stale graph capability sets no hint.

  `context_pack/roles.py::_result_candidate()` consumes only that in-memory hint
  before ordinary path classification and maps it to existing group
  `implementations`, role `repository`, and existing basis `content`. It performs
  no SQLite/parser/repository I/O and never infers the hint from an XML suffix,
  basename, content substring, graph score, or `mapped_by` resolution. Anchors do
  not synthesize it. Exact tests prove the hint survives result normalization,
  exploration's actual `deepcopy`/`dataclasses.replace` fusion path, and final
  pack construction; it is absent from every public payload/trace and ignored by
  dataclass equality, score, reasons, spans, and ordering. Ordinary, protected
  direct public fields, legacy, stale, rejected-mapper, and non-mapper XML remain
  byte-identical. Thus the behavior remains dormant before Step 6 and
  ContextPack v2's closed schema is unchanged.

- [ ] **Step 6: Switch every public surface only after all behavior is green**

  In one final implementation step of this task:

  - change the single current signal schema constant from 4 to 5;
  - make public `index_repository()` delegate to Task 8's complete v5 builder;
  - turn the existing `JavaPlugin` into the reviewed coordinator: error-free
    files materialize `JavaGraphProducer`'s AST facts, while its
    `fallback_required` marker invokes the coordinator's preserved private
    whole-file legacy extractor exactly once; `java_graph.py` never imports the
    coordinator; boundary tests import both modules in both orders, instantiate
    defaults, and prove no recursion or partial initialization;
  - make `default_plugins()` function-locally import/register that Java
    coordinator plus frontend and MyBatis graph producers in canonical order;
  - switch public indexing to the safe scanner/read path and Task-7 canonical
    test classifier;
  - make public query/context/trace/explore call Task 9's private v5 path through
    `GraphReadSession` and the exact missing/<5/v5 stale/v5 ready/future matrix;
  - expose the already-green exact graph explain sibling and mapper XML's
    existing `implementations`/`repository` classification in the same switch;
  - map internal busy/future errors through existing CLI/MCP envelopes; and
  - prove ready v5 never executes structured `target_name` fallback or exposes
    `imports_type` to retrieval/P4.

  For an existing stale index, every CLI operation that consumes it—query,
  context, trace, explore, stats, and explain—emits the exact warning once;
  index itself attempts recovery. Library/MCP paths log only stable
  `graph_index_stale` and add no warning field. Explore's multiple internal
  retrievals still yield one CLI warning. Future schema returns
  `incompatible_signal_schema` before planner, embeddings, parser, graph read,
  or database mutation.

  Add deterministic rollback-journal concurrency tests. An old-ready query keeps
  one complete read snapshot while the indexer's conflicting commit waits; when
  that read closes, stale commits before further graph writes. A later stale
  query uses no graph and validates the descriptor/config/manifest/SQLite vector
  tuple before vector recall; every injected publication mismatch skips vector
  with `vector_snapshot_mismatch` and returns only coherent lexical/path/anchor
  evidence. After ready, a third query sees the complete new snapshot and exact
  vector tuple. A reader held past the 5,000 ms production timeout (shortened by
  a test seam) yields stable busy, never partial state.

- [ ] **Step 7: Prove the remote-disclosure boundary with a recorder**

  `tests/test_p5_privacy.py` uses one fake recording embedding provider across a
  forced v4-to-v5 full reindex, query, exact graph explain, and graph-grounded
  explore. It asserts the provider receives every active source chunk during the
  mandatory rebuild and normal query/probe strings (which may contain
  graph-derived names/paths), but never an AST object, relation/signal row,
  explain payload, parser diagnostic, feedback payload, or separate graph
  serialization. Patch socket/requests to fail so the test also proves no new
  remote client executes.

- [ ] **Step 8: Verify the sole public activation and full compatibility**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_p5_explain.py \
    tests/test_p5_privacy.py \
    tests/test_graph_lifecycle.py \
    tests/test_indexer_manifest.py \
    tests/test_tokenizer_scanner.py \
    tests/test_chunker_java_plugin.py \
    tests/test_resolved_graph_expansion.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_context_pack.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_exploration_runner.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_formatters.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_exploration_contracts.py
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

- [ ] **Step 9: Commit the single complete public activation boundary**

  ```bash
  git add \
    src/context_search_tool/indexer.py \
    src/context_search_tool/plugins.py \
    src/context_search_tool/java_plugin.py \
    src/context_search_tool/scanner.py \
    src/context_search_tool/models.py \
    src/context_search_tool/sqlite_store.py \
    src/context_search_tool/retrieval.py \
    src/context_search_tool/retrieval_core/selection.py \
    src/context_search_tool/context_pack/roles.py \
    src/context_search_tool/cli.py \
    src/context_search_tool/mcp_tools.py \
    tests/test_p5_explain.py \
    tests/test_p5_privacy.py \
    tests/test_graph_lifecycle.py \
    tests/test_indexer_manifest.py \
    tests/test_tokenizer_scanner.py \
    tests/test_chunker_java_plugin.py \
    tests/test_retrieval_pipeline.py \
    tests/test_retrieval_core_boundaries.py \
    tests/test_context_pack.py \
    tests/test_cli_commands.py \
    tests/test_mcp_tools.py \
    tests/test_exploration_probes.py \
    tests/test_exploration_fusion.py \
    tests/test_exploration_runner.py \
    tests/test_retrieval_trace_pipeline.py
  git commit -m "feat: activate complete p5 graph behavior"
  ```

### Task 11: Freeze Structural Projections And Pass Deterministic 12/12

**Files:**

- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/runner.py`
- Create: `tests/generate_p5_graph_expected.py`
- Create: `tests/test_p5_graph_contract.py`
- Create: `tests/test_quality_p5.py`
- Create: `tests/fixtures/p5-language-graphs/expected/*.json`
- Create: `tests/fixtures/p5-language-graphs/expected/compatibility_allowlist.json`
- Modify: `tests/test_quality_cases.py`
- Modify: `tests/test_quality_runner.py`
- Modify: `tests/test_p5_inputs.py`

- [ ] **Step 1: Add the exact profile validator tests first**

  Accept only profile names `p5_language_graphs` and
  `p5_real_language_graphs`, hash-v1/384, planner disabled, no remote settings,
  top 12, ContextPack 12/65,536, and P4's fixed <=3 calls/65,536 bytes. Allow
  results/context_pack/exploration modes only for these exact P5 profiles;
  existing P4 profiles stay exploration-only and no prefix/wildcard rule grants
  another profile permission.

- [ ] **Step 2: Write the structural projection gate first**

  Canonically project all five synthetic repositories with schema/readiness/
  topology, v5 signal identity fields, relation selector/state/target/both
  confidence components, occurrence metadata, truncation counts, module/test
  invariants, and failure-recovery markers. Exclude row order, timing, absolute
  paths, vector floats, and parser objects.

  `tests/test_p5_graph_contract.py` creates two independent fresh indexes in
  reversed scan/insertion order where injectable, compares A to B byte-for-byte,
  then compares both with committed expected JSON. It also proves every
  forbidden edge and incoming-source invariant, and exercises one full-rebuild
  recovery projection.

- [ ] **Step 3: Initialize expected outputs safely**

  Generate candidates under `/tmp`, compare them visibly with `cmp -s`, then run
  the initializer. It must internally compare A/B, validate the frozen input
  manifest, reject unexpected files/keys, refuse overwrite, and write canonical
  JSON only after all checks pass. Review the diff semantically before staging.

  Example workflow:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/generate_p5_graph_expected.py project \
    --manifest tests/fixtures/p5_language_graphs/input_manifest.json \
    --output-dir /tmp/cst-p5-graph-a
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/generate_p5_graph_expected.py project \
    --manifest tests/fixtures/p5_language_graphs/input_manifest.json \
    --reverse-order \
    --output-dir /tmp/cst-p5-graph-b
  diff -ru /tmp/cst-p5-graph-a /tmp/cst-p5-graph-b
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/generate_p5_graph_expected.py initialize \
    --manifest tests/fixtures/p5_language_graphs/input_manifest.json \
    --candidate-a /tmp/cst-p5-graph-a \
    --candidate-b /tmp/cst-p5-graph-b \
    --output-dir tests/fixtures/p5-language-graphs/expected
  ```

- [ ] **Step 4: Run the exact 12-case deterministic profile**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    --profile p5_language_graphs \
    --output /tmp/cst-p5-deterministic.json \
    --markdown /tmp/cst-p5-deterministic.md
  ```

  Required: exactly the 12 reviewed IDs, 12/12, no skipped/failed/error case,
  fixed top/context/call/byte budgets, and the exact path positives/negatives.
  The Vue exploration case proves both declared paths initially absent and final
  present within <=3 calls with no lock-file noise.

- [ ] **Step 5: Prove graph evidence, not textual coincidence**

  Inspect raw selected result score parts in the same run:

  - Java domain/DTO has `graph_uses_type_match > 0`;
  - Vue/React route targets have `graph_routes_to_match > 0`;
  - mapped XML has `graph_mapped_by_match > 0`;
  - ambiguous overload/import cases have no target with any closed graph key;
  - every graph-selected candidate has exactly one closed graph `_match` key;
  - protected direct candidates have byte-identical score parts/reasons.

  Quality path assertions alone are insufficient.

- [ ] **Step 6: Build and review the compatibility allowlist**

  Compare Task-0 protected normalized results with the candidate for every
  existing case. Direct top candidates and direct fields may not differ. The
  allowlist is `[]` if there are no other changes. Otherwise each entry must
  contain exact profile/case/path/before-rank/after-rank, relation ID/kind/
  direction, and why the new target is legal. It may permit only a graph-derived
  addition/reordering outside the protected direct object, never a removal,
  score mutation, trace schema change, new call, or forbidden path.

  This output is reviewed and committed under `expected/`; it never changes a
  P0-P4 catalog or baseline. `tests/test_quality_p5.py` must expose the stable
  acceptance nodes
  `test_compatibility_allowlist_has_only_graph_proven_deltas` and
  `test_protected_direct_and_no_edge_projections_are_exact`; Task 12 invokes
  those exact nodes rather than relying on narrative review.

- [ ] **Step 7: Re-run structural, deterministic, protected, and full gates**

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_p5_inputs.py \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_quality_cases.py \
    tests/test_quality_runner.py
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_retrieval_core_characterization.py \
    tests/test_retrieval_trace.py \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_context_pack.py \
    tests/test_exploration_boundaries.py \
    tests/test_exploration_contracts.py \
    tests/test_exploration_runner.py \
    tests/test_quality_p3.py \
    tests/test_quality_p4.py
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q -rs
  git diff --check
  ```

- [ ] **Step 8: Commit generated evidence and exact quality support**

  ```bash
  git add \
    src/context_search_tool/quality/cases.py \
    src/context_search_tool/quality/runner.py \
    tests/generate_p5_graph_expected.py \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/fixtures/p5-language-graphs/expected \
    tests/test_quality_cases.py \
    tests/test_quality_runner.py \
    tests/test_p5_inputs.py
  git commit -m "test: verify p5 language graph quality"
  ```

### Task 12: Run Real/Protected Acceptance And Record P5 Completion

**Files:**

- Create: `tests/p5_real_language_graphs_acceptance.py`
- Create: `tests/fixtures/p5_language_graphs/real_acceptance.json`
- Modify: `README.md`
- Modify: `docs/retrieval-quality.md`
- Modify: `docs/superpowers/specs/2026-07-17-p5-language-framework-graphs-design.md`
- Modify: this plan
- Modify: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

- [ ] **Step 1: Prepare and verify the pinned real repositories**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality prepare \
    tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos
  ```

  PetClinic must be exactly
  `51045d1648dad955df586150c1a1a6e22ef400c2` with a clean prepared tree.
  `program_tool` must resolve to the committed fixture inventory/hash in the P5
  input manifest. Do not substitute another commit or fetch during indexing.

- [ ] **Step 2: Run the exact real profile twice**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output /tmp/cst-p5-real-a.json
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output /tmp/cst-p5-real-b.json
  ```

  Required twice:

  - exactly 2/2, no error/skip;
  - PetClinic final pack contains OwnerController, OwnerRepository, Owner, and
    OwnerControllerTests within 12 items, <=3 calls, <=65,536 bytes;
  - program-tool final pack contains router plus at least two declared QRCode
    page/service/type targets, excludes both lock files, within the same budgets;
  - every non-empty exploration trace coverage value is 1.0;
  - no network/model/planner call beyond configured local embeddings;
  - timing may differ, canonical normalized content must not.

- [ ] **Step 3: Create one non-default normalized real projection**

  `tests/p5_real_language_graphs_acceptance.py` is not named `test_*.py`. Its
  `run` command owns the exact pinned/profile/two-case projection and strips only
  reviewed timing/temp-root fields. Run A and B separately, compare visibly,
  then initialize with internal A/B equality and refuse-overwrite checks. Verify
  both candidates against the committed projection.

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output /tmp/cst-p5-real-projection-a.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output /tmp/cst-p5-real-projection-b.json
  cmp -s /tmp/cst-p5-real-projection-a.json /tmp/cst-p5-real-projection-b.json
  test ! -e tests/fixtures/p5_language_graphs/real_acceptance.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py initialize \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --candidate-a /tmp/cst-p5-real-projection-a.json \
    --candidate-b /tmp/cst-p5-real-projection-b.json \
    --output tests/fixtures/p5_language_graphs/real_acceptance.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate /tmp/cst-p5-real-projection-a.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate /tmp/cst-p5-real-projection-b.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  ```

  `initialize` independently checks A/B bytes, both case identities, pinned repo
  identity, budgets, and fixture/profile hashes before its one refuse-overwrite
  write. The standalone `cmp` remains visible evidence rather than its only
  equality check.

- [ ] **Step 4: Run every protected profile and identity gate**

  ```bash
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    --profile p5_language_graphs \
    --output .quality/p5-artifacts/final-p5.json \
    --markdown .quality/p5-artifacts/final-p5.md
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p4_exploration.json \
    --profile p4_exploration \
    --output .quality/p5-artifacts/final-p4.json \
    --markdown .quality/p5-artifacts/final-p4.md
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile p2_context_pack \
    --output .quality/p5-artifacts/final-p2.json \
    --markdown .quality/p5-artifacts/final-p2.md
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output .quality/p5-artifacts/final-ci.json \
    --markdown .quality/p5-artifacts/final-ci.md

  "$P5_RUNTIME" -c \
    'import json; paths=(".quality/p5-artifacts/final-p5.json", ".quality/p5-artifacts/final-p4.json", ".quality/p5-artifacts/final-p2.json", ".quality/p5-artifacts/final-ci.json"); reports=[json.load(open(path, encoding="utf-8")) for path in paths]; assert [(d["profile"], d["aggregate"]["selected"], d["aggregate"]["executed"], d["aggregate"]["passed"], d["aggregate"]["failed"], d["aggregate"]["errors"]) for d in reports] == [("p5_language_graphs", 12, 12, 12, 0, 0), ("p4_exploration", 4, 4, 4, 0, 0), ("p2_context_pack", 5, 5, 5, 0, 0), ("ci", 8, 8, 8, 0, 0)]; coverage=[case["metrics"].get("exploration_trace_coverage") for case in reports[1]["cases"] if case["metrics"].get("exploration_trace_coverage") is not None]; assert coverage and all(value == 1.0 for value in coverage)'

  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p4_exploration_identity.py quality-projection \
    --input .quality/p5-artifacts/final-p2.json \
    --output .quality/p5-artifacts/final-p2-projection.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p4_exploration_identity.py quality-projection \
    --input .quality/p5-artifacts/final-ci.json \
    --output .quality/p5-artifacts/final-ci-projection.json
  cmp -s tests/fixtures/p4_exploration/p0_p3_p2_quality.json \
    .quality/p5-artifacts/final-p2-projection.json
  cmp -s tests/fixtures/p4_exploration/p0_p3_ci_quality.json \
    .quality/p5-artifacts/final-ci-projection.json

  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_p5_inputs.py \
    tests/test_exploration_inputs.py \
    tests/test_quality_p3.py::test_p3_trace_coverage_is_complete_and_raw_results_are_unchanged \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py::test_compatibility_allowlist_has_only_graph_proven_deltas \
    tests/test_quality_p5.py::test_protected_direct_and_no_edge_projections_are_exact \
    tests/test_retrieval_core_characterization.py
  ```

  These executable gates own the complete P5 manifest/four protected hashes,
  compatibility allowlist, direct endpoint/path/symbol winners and score parts,
  pre-P5 no-edge projection, P3/P4 trace coverage 1.0, and byte-identical P2/CI
  stable projections. No prose-only acceptance is permitted.

- [ ] **Step 5: Run security/privacy/full acceptance**

  Use a fake recording remote embedding provider to prove the mandatory v5 full
  rebuild may resend every source chunk, and query/explore may send query/probe
  text containing graph-derived names/paths, while no AST/relation/explain object
  is separately serialized and no new remote client exists. Verify source/trace/
  feedback privacy tests, parser no-fetch tests, XML XXE tests, scanner link tests,
  lock contention, crash recovery, and future-schema refusal.

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_p5_privacy.py::test_full_reindex_query_and_explore_disclosure_contract \
    tests/test_parser_abi.py \
    tests/test_mybatis_xml.py::test_mybatis_security_matrix_fails_closed \
    tests/test_tokenizer_scanner.py::test_v5_scanner_rejects_symlink_and_escape_matrix \
    tests/test_graph_lifecycle.py::test_exclusive_index_lock_rejects_second_writer \
    tests/test_graph_lifecycle.py::test_fault_matrix_recovers_complete_ready_snapshot \
    tests/test_graph_store.py::test_future_signal_schema_is_non_destructive \
    tests/test_exploration_contracts.py::test_explore_feedback_is_exact_aggregate_only \
    tests/test_exploration_contracts.py::test_explore_error_feedback_keeps_all_keys_without_error_detail
  ```

  Then run the full suite with JUnit evidence. Audit exact skip node IDs and zero
  xfails rather than only counts. No P5 real case is a default skip.

- [ ] **Step 6: Update documentation only after all gates pass**

  Record exact dependency versions/matrix URLs, implementation commits, test
  counts/skips/xfails, structural projection hashes, 12/12 and 2/2 reports,
  call/byte budgets, protected hashes, and compatibility allowlist result.

  README/quality docs must state honestly:

  - parsers/resolver run locally and fetch nothing while indexing;
  - a configured remote embedding provider receives source chunks, including a
    full resend during v5 migration;
  - query/explore sends normal query/probe text, which can contain graph-derived
    names/paths;
  - graph objects are not a separate remote payload;
  - stale graph disables signal/relation evidence but keeps other recall;
  - reindex is required after v4 and may be expensive; no P6 latency promise.

  Mark design/plan/roadmap implemented only now. Phase 1 remains 6/7 and Phase 6
  remains next; do not call P5 complete earlier in history.

- [ ] **Step 7: Final verification and focused docs commit**

  ```bash
  git diff --check
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py run \
    --fixture tests/fixtures/retrieval_quality/p5_real_language_graphs.json \
    --profile p5_real_language_graphs \
    --repos-dir .quality/p5-repos \
    --output /tmp/cst-p5-real-projection-final.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" \
    tests/p5_real_language_graphs_acceptance.py verify \
    --candidate /tmp/cst-p5-real-projection-final.json \
    --expected tests/fixtures/p5_language_graphs/real_acceptance.json
  PYTHONPATH="$PWD/src:$PWD/tests" "$P5_RUNTIME" -m pytest -q \
    tests/test_p5_inputs.py \
    tests/test_p5_privacy.py \
    tests/test_p5_graph_contract.py \
    tests/test_quality_p5.py \
    tests/test_resolved_graph_expansion.py \
    tests/test_p5_explain.py
  PYTHONPATH="$PWD/src" "$P5_RUNTIME" -m pytest -q -rs \
    --junitxml=.quality/p5-artifacts/final.xml
  ```

  ```bash
  git add \
    tests/p5_real_language_graphs_acceptance.py \
    tests/fixtures/p5_language_graphs/real_acceptance.json \
    README.md \
    docs/retrieval-quality.md \
    docs/superpowers/specs/2026-07-17-p5-language-framework-graphs-design.md \
    docs/superpowers/plans/2026-07-17-p5-language-framework-graphs.md \
    roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
  git commit -m "docs: record p5 language graph acceptance"
  ```

  Report the documentation commit in the implementation handoff; the document
  cannot self-record the hash of the commit that contains its final edit.

## Design-To-Task Acceptance Map

| design acceptance | owning task(s) |
| --- | --- |
| 1-3: additive v5 values, identities, module invariants | 3, 7-10 |
| 4-8: units, v4/v5/future, lock/recovery, resolution/confidence | 6, 8-10 |
| 9-11: Java AST parity/binding/framework/flow/types | 4, 7, 8, 10, 11 |
| 12-13: safe MyBatis and mapper direction/confidence | 5, 7, 8-11 |
| 14-15: frontend imports/routes and ambiguity negatives | 5, 7-11 |
| 16-17: exact tests and two-stage association | 7, 8, 11 |
| 18-21: traversal/dominance/budgets/scoring/intent | 9, 11 |
| 22: unchanged ContextPack/trace/P4 contracts | 9-12 protected gates |
| 23: exact explain | 10 |
| 24-25: scanner/parser safety and privacy | 2, 5, 6, 10, 12 |
| 26-27: twice structural and 12/12 + 2/2 quality | 11, 12 |
| 28-30: protected/full/Phase-1 acceptance | 0, 8-12 |
| 31: no P6/public/schema/model scope creep | boundary tests and every task |
| 32: docs/roadmap only after acceptance | 12 |

No acceptance item is satisfied only by prose. Every row has a focused test or
executable report gate in its owning task.

## Implementation And Acceptance Record

Pending. Task 12 must replace this paragraph only after implementation passes
all reviewed gates. The record must include exact commit lineage, parser matrix
run links, JUnit counts/skip node IDs/xfails, structural projection hashes,
deterministic and real report paths/hashes, protected compatibility result,
privacy/security results, and Phase 1's unchanged 6/7 status.

## Stop Conditions

Stop implementation and request design/plan review if any of these occurs:

- the baseline runtime, suite, protected profile, trace coverage, catalog blob,
  input manifest, or skip/xfail identity cannot be reproduced;
- the exact dependency set fails any required ABI job or needs a runtime
  download/compiler;
- a partial Java AST can be mixed safely only by weakening whole-file fallback;
- Java resolution needs compiler/classpath/build execution, assignability,
  inference, Lombok/processor output, or an unreviewed heuristic;
- a frontend edge requires preference-first extension/index resolution,
  arbitrary alias/config execution, computed imports/routes, or regex persistence;
- safe official MyBatis headers require external DTD fetch, entity expansion,
  generic text ranges, or accepting a lexer/parser mismatch;
- a test association requires raw substring/basename similarity, crossing units,
  test-to-test/generated targets, or table-order tie-breaking;
- v5 cannot be activated with all producers in one mandatory full rebuild;
- a full rebuild would preserve old chunks/vectors, load corrupt vectors, clear
  `full_reindex_required` before ready, or write source hashes before graph data;
- full/incremental vector updates would mutate published files in place, publish
  the descriptor before resolver completion, or score a stale mismatched
  descriptor/config/manifest/SQLite tuple instead of skipping vector recall;
- schema DDL/metadata cannot be atomic or a second indexer can run without the
  exclusive lock;
- stale/future behavior would query unknown columns, destructively downgrade,
  or use signal/relation evidence;
- a structured non-resolved edge must text-fallback, or a resolved target cannot
  be proven active/in-scope in final validation;
- arrival/SQLite order changes dominance, truncation, reason, target, or
  structural projection;
- a resolved hop needs more than four hops/global budgets or a legacy hop needs
  more than three;
- graph scoring needs multiple `_match` additions, legacy numeric double count,
  or any mutation of a protected direct candidate;
- P4 needs another round/probe/source enum/call/model planner, or exceeds three
  retrieval calls/65,536 bytes;
- ContextPack v2, RetrievalTrace v1, ExplorationTrace v2, manifest v1, feedback,
  or existing MCP operation schemas would need a version/change;
- explain cannot preserve old chunk/lines byte-for-byte or needs unbounded rows/
  new source excerpts;
- a remote client, AST/relation payload, repository code execution, or false
  local-only privacy statement enters implementation;
- a deterministic case can pass only by editing frozen input, weakening a
  negative, relying on text co-occurrence, or refreshing expected output without
  two equal projections and semantic review;
- a protected direct/no-edge result or P0-P4 input changes outside the exact
  reviewed allowlist;
- a new default skip/xfail appears, real acceptance is made optional inside the
  default suite, or a quality threshold replaces exact 12/12 or 2/2;
- implementation begins P6 caching/watch/service/performance work, a new
  Go/Rust/Python AST plugin, a public graph operation/config, or Phase 1 status
  change.

These are contract failures, not permission to improvise a broader P5.

## Final Implementation Review Checklist

Before requesting implementation review, verify:

- [ ] exact baseline runtime/evidence and four protected hashes reproduced;
- [ ] all five dependency pins and eight ABI jobs pass;
- [ ] P5 inputs were frozen before production and expected outputs excluded;
- [ ] graph contract is acyclic and legacy IDs remain exact;
- [ ] v5 IDs use full canonical SHA-256 and duplicate occurrence merge is exact;
- [ ] root unit `""`, topology fingerprint, and cross-unit rules are exact;
- [ ] scanner rejects every symlink/root escape before reading;
- [ ] v4 adapter, v5 DDL, stale, future refusal, and no-op integrity are exact;
- [ ] lock covers schema detection through ready and has no unlocked fallback;
- [ ] full rebuild includes chunks/FTS/vectors and bypasses old/corrupt vectors;
- [ ] full and incremental vectors use complete immutable generations prepared
  before source hashes, descriptor publication after resolvers, and exact stale/
  ready tuple validation;
- [ ] stale-before-write, source-hash-last, durable full flag, and every failure
  seam recover;
- [ ] pre-commit faults stay stale, acknowledged post-commit faults stay complete
  ready/full=0, and unknown commit results recover from only those two states;
- [ ] producer resolution, all associations, test resolution, and final ready
  occur in exact order;
- [ ] one module exists per graph-eligible file and no empty-file module exists;
- [ ] only exact/unique active targets traverse and only legacy text-falls back;
- [ ] Java relevant errors/missing nodes use whole-file legacy fallback;
- [ ] Java scopes/FQCN/signatures/overloads/annotation allowlist fail closed;
- [ ] MyBatis official headers work without fetch and every XXE/range negative
  fails closed;
- [ ] frontend parser/range/framework/route/import ambiguity rules are exact;
- [ ] all six language test rewrites and persisted-import associations are exact;
- [ ] module promotion works for non-first chunks in retrieval, P4, and explain;
- [ ] resolved four-hop/legacy three-hop traversal, directions, complete tuple,
  SQL/global caps, cycles, and deterministic prefixes pass;
- [ ] one graph `_match` is counted once and every provenance consumer is updated;
- [ ] protected direct candidates are immutable under graph merge;
- [ ] exact test intent/P4 frozen-goal gating and <=3 calls pass;
- [ ] dangling targets stop graph use and force/prompt stale recovery;
- [ ] MCP/CLI explain keys/lines/order/caps/omissions are exact;
- [ ] mapper XML uses only existing ContextPack role/group;
- [ ] structural projections compare A/B/expected and prove forbidden edges;
- [ ] deterministic profile is exact 12/12 with raw graph score proof;
- [ ] real profile is exact 2/2 twice within item/call/byte budgets;
- [ ] P4 4/4, P2 5/5, CI 8/8, protected trace coverage 1.0, and identity gates pass;
- [ ] compatibility allowlist is empty or every entry has reviewed edge evidence;
- [ ] remote disclosure/no-new-client/privacy tests are honest and exact;
- [ ] full suite skip node IDs/xfails are audited and Phase 1 remains 6/7;
- [ ] docs/roadmap changed only after all acceptance gates.

## Plan Review Rubric

Independent plan reviewers must check:

1. whether every task can end green and has one focused, non-overlapping commit;
2. whether Tasks 3-9 leave every public surface genuinely on v4 without a hidden
   feature flag/half-ready schema, and Task 10 activates only after every v5
   traversal/provenance/P4/explain/ContextPack caller is green;
3. whether the dependency pins/matrix are current, mutually testable, and cover
   packaged grammar construction without runtime fetch/compile;
4. whether v5 identity/default/confidence/occurrence/module contracts are exact
   and acyclic;
5. whether v4/missing/v5 stale/ready/future behavior, atomic DDL, lock scope,
   full vector rebuild, source-hash-last, and crash recovery are implementable
   with the current store/indexer layout;
6. whether resolver target scopes, two-row uniqueness, confidence, association
   generation ordering, topology, and final integrity close every false-ready
   path;
7. whether Java AST scope/signature/annotation/parity/fallback rules can be
   implemented from the pinned grammar without compiler claims;
8. whether Vue included ranges, frontend framework anchoring/ambiguity, and
   MyBatis official-DOCTYPE/range protocol are safe and deterministic;
9. whether all six test rewrite algorithms are complete-set/unique and can be
   rebuilt from persisted facts after unchanged-file runs;
10. whether traversal directions, module promotion, complete dominance, SQL and
    global caps, scoring/provenance, dangling-target fallback, and direct
    immutability update all real consumers;
11. whether P4 remains one-hop/three-call/schema-compatible and exact test intent
    gates both ordinary and exploration paths;
12. whether MCP/CLI explain preserves old payload/text while proving complete
    pre-cap membership and exact omission counts;
13. whether input freeze, twice-generated structural projections, raw score
    assertions, compatibility allowlist, 12/12, and 2/2 gates cannot pass through
    textual coincidence or refreshed expectations;
14. whether protected quality/trace/privacy/security/full-suite gates and docs
    evidence are executable from real repository commands;
15. whether any step silently introduces P6, another schema/public surface,
    runtime build/fetch, remote graph disclosure, or a new language AST plugin.

Any unresolved blocker or major correctness, safety, compatibility, privacy,
determinism, dependency, task-order, or acceptance finding keeps this plan in
draft status.

## Agent Review Record

Three independent read-only agents reviewed the complete draft on 2026-07-17.
The first pass reported:

- architecture/index lifecycle: FAIL, 1 blocker, 6 majors, 2 minors;
- language/framework ecosystem: FAIL, 0 blockers, 5 majors, 4 minors;
- public contract/quality/compatibility: FAIL, 0 blockers, 5 majors, 2 minors.

The revisions closed the shared and follow-up findings: Task 10 is now the sole
public activation after traversal, explain, MyBatis ContextPack classification,
Java coordination, safe scanning, and every provenance consumer are green;
Tasks 3-9 stay publicly v4. Vector publication is a two-phase immutable
generation protocol for both full and incremental work, stale readers validate
the complete external/SQLite tuple, and final-commit fault states distinguish
stale, acknowledged ready, and unknown outcomes. `GraphReadSession` has an exact
rollback-journal lifetime; Java fallback is one-way and exactly once; the
repository-local parser runtime/CI matrix, lock bootstrap, source-hash order,
Files/staging boundaries, real/privacy gates, and exact P5/P4/P2/CI commands are
all executable. The accepted MyBatis role uses a private non-serialized result
hint at the real selection constructor and is preserved by exploration fusion
without ContextPack I/O or protected-direct mutation.

Final targeted review bound all three conclusions to plan content SHA-256
`5f5f6866d53b1092e034a7cfc1d693228688760b244aff3f3f5844f80f2be334`:

- architecture/index lifecycle: PASS, 0 unresolved blockers/majors;
- language/framework ecosystem: PASS, 0 unresolved blockers/majors;
- public contract/quality/compatibility: PASS, 0 unresolved blockers/majors.

No reviewer reported a remaining minor. The hash predates this approval
record/status edit and the later user-approved Task-2 execution amendment. That
amendment changes only local environment inheritance and phase-scoped path
inventories; it does not change the reviewed P5 behavior or acceptance scope.

## Stop Point

The user explicitly authorized implementation in this thread on 2026-07-17.
Task 0 and Task 1 are complete and Task 2 is underway; activation remains
confined to Task 10 and remote CI still requires separate publication authority.
Phase 6 remains out of scope, and Phase 1 remains independently pending at 6/7.
