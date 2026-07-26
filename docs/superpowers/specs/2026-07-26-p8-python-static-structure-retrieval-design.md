# P8 Python Static Structure Retrieval v1 Design

Date: 2026-07-26
Status: Ready for review; implementation not authorized or started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `75cc65ed627dd5982460a4d4a10d28f10e7151b8`
Predecessor:
`docs/superpowers/plans/2026-07-26-p7-final-path-diverse-evidence-selection.md`
Companion implementation plan:
`docs/superpowers/plans/2026-07-26-p8-python-static-structure-retrieval.md`

## Summary

P8 v1 adds conservative Python structure to CST's existing graph pipeline:

```text
Python source bytes
  -> stdlib AST facts
  -> declaration symbols/signals
  -> repository-local static import selectors
  -> existing schema-v5 signals and relations
  -> existing repository-wide resolver
  -> existing exact test association
  -> existing relation expansion and ranking
  -> P7 path-diverse final selection
```

The first slice deliberately stops at declarations and static module imports.
It does not implement a Python call graph, type inference, runtime import
semantics, or a new reranker. The purpose is to answer one causal question:

> When a Python workflow file is already acquired, can exact repository-local
> import structure recover or raise its directly related implementation,
> support, schema, configuration, and test modules without harming protected
> retrieval behavior?

The design reuses `CodeSignal`, `CodeRelation`, graph schema 5, relation kind
`imports`, the current exact/unique resolver, existing test association, and
the current relation-expansion score. It adds one Python producer and one
internal producer-contract metadata version so an existing ready index cannot
silently retain pre-P8 Python files.

P8 v1 is accepted only if the import-only mechanism produces attributable
improvement on both pinned Python repositories and passes all existing P5, P6,
P7, quality, determinism, lifecycle, and privacy gates. If exact import edges
acquire the right files but ranking still keeps them below the evidence budget,
the next phase is a separately designed file-level reranking experiment. If
the necessary workflow link is not represented by imports, a separately
designed Python call-edge experiment may follow. Neither mechanism is bundled
into P8 v1.

## Decision Boundary

This document and its companion plan authorize no product changes by
themselves. Implementation starts only after explicit user approval.

The reviewed product slice is:

- Python module, class, top-level function, and class-method declarations;
- absolute and relative static `import` / `from ... import ...` module
  dependencies;
- deterministic repository-local module-path resolution;
- automatic reuse of existing exact test association;
- lifecycle activation for existing schema-v5 indexes;
- synthetic and pinned two-repository acceptance evidence.

The slice excludes:

- calls, overrides, inheritance, decorators, route inference, dependency
  injection, or framework-specific edges;
- ranking weights, query planning, candidate budgets, result budgets, or P7
  selection changes;
- new public operations, response fields, trace schemas, graph tables, or
  model/network dependencies.

Any implementation that needs an excluded mechanism must stop and revise this
design before continuing.

## Plan-Time Evidence

### P7 Residual

P7 Final fixed downstream result-slot starvation. On the pinned
`daily_stock_analysis` probe it changed 12 results from 2 unique paths to 12
unique paths and recovered:

- `src/core/pipeline.py`;
- `data_provider/base.py`.

P7 intentionally did not solve upstream Python structure. The same prepared
index has:

```text
201 active core module signals
0 Python declaration signals
0 active relations
0 relation-expansion candidates for the frozen P7 query
```

The frozen query is:

```text
data fetcher prefetch stock names provider fallback pipeline
```

After P7, its selected paths include `src/core/pipeline.py` at rank 2 and
`data_provider/base.py` at rank 3. This is now a non-regression witness, not a
claim that every semantically related file should be forced into the result.
In particular, `src/services/name_to_code_resolver.py` is not a mandatory gold
file for that query: its actual direct importer is
`src/services/import_parser.py`, not the pipeline.

### Current Product Boundary

The repository already contains the required substrate:

- `GraphLanguagePlugin` separates `parse()` from `materialize()`;
- `PluginContext` supplies a normalized repository-relative file path,
  project-unit key, active-path membership, and path-to-unit lookup;
- every active non-empty file already receives one non-recallable
  `core_module` signal;
- graph schema 5 already stores structured signal identity, unresolved
  selectors, resolution state, producer confidence, and exact target IDs;
- `resolve_graph_relations()` already resolves module selectors only when a
  target is exact or unique;
- `build_test_associations()` already turns resolved imports from a recognized
  Python test file into exact `tests` relations;
- relation kind `imports` already has outgoing traversal, weight `0.85`, graph
  decay `0.8`, score part `graph_imports_match`, and existing work budgets;
- P7 already ensures ordinary final results spend slots on distinct paths.

The missing layer is upstream production of Python declarations and imports.
No second store, resolver, traversal stage, or result selector is needed.

### Existing Activation Gap

Adding a plugin to `default_plugins()` is not sufficient for an existing
ready schema-v5 index:

- unchanged files are not reparsed on a quiet authoritative index or refresh;
- schema 5 currently records resolution readiness but not the producer
  contract that generated file-local graph facts;
- an existing Python index could therefore remain `ready` with no Python
  signals or relations after the binary is upgraded.

P8 must close this lifecycle gap. Bumping the SQL signal schema is unnecessary
because all required fields and relation kinds already exist. Silently relying
on users to delete `.context-search` is also unacceptable.

### Pinned Real Repositories

P8 uses two public repositories with different shapes:

| repository | pinned source | reviewed slice | plan-time baseline |
| --- | --- | --- | --- |
| RedInk | `https://github.com/HisMax/RedInk.git` at `4d48722344594cf00e0498f0e1ed3df9cd4fd6be` | `backend/**/*.py`, `tests/**/*.py`, `pyproject.toml` | 28 files, 87 chunks, 0 symbols, 25 core modules, 0 relations |
| daily_stock_analysis | `https://github.com/ZhuLinsen/daily_stock_analysis.git` at `487e49e565ffd1b96a7cf4d855f99cee3c981eaa` | the P7 continuity slice: `data_provider/**/*.py`, `src/**/*.py`, and `tests/test_data_fetcher_prefetch_stock_names.py` | 203 files, 1,596 chunks, 0 symbols, 201 core modules, 0 relations |

The local RedInk directory is not a Git worktree, but its 27 Python files plus
`pyproject.toml` are byte-for-byte identical to the stated public commit. This
was verified by comparing Git blob identities for all 28 paths. The local
directory's existing `.context-search` is a corrupt legacy artifact and is
never used.

The local `daily_stock_analysis` worktree has unrelated modifications and
untracked files. It is never indexed or changed. All P8 runs use a clean
detached preparation of the pinned commit.

Both profiles use deterministic hash embeddings with the query planner off.
No baseline or candidate run imports or executes either target project.

### Observed Rank Opportunities

RedInk already has high lexical recall, making it a precision and provenance
guard rather than an easy missing-file benchmark:

| case | selected plan-time role ranks |
| --- | --- |
| application wiring | route registry 1, app factory 2 |
| content flow | service 1, route 4, text client 6 |
| outline flow | service 1, text client 3, route 4 |
| image flow | service 1, route 4, compressor 8, factory 10 |
| history flow | route 1, service 2 |
| provider configuration | config module 3, config route 5, route utility 7 |

The daily core slice contains clearer structural misses:

| case | selected plan-time role ranks |
| --- | --- |
| import parser | parser 1, resolver 3, stock-code utility absent from top 12 |
| analysis context | builder 4, context schema absent from top 12 |
| notification diagnostics | diagnostics 3, contracts 6, routing 8 |
| task queue | queue 1, run diagnostics 5, analysis metadata absent |
| runtime scheduler | service 3, config 4, scheduler 10 |
| portfolio risk | repository 1, risk service 3, import service 12, portfolio service absent |
| alert worker | worker 1, decision service 2, history service 3, alert service 7 |
| backtest | service 2, repository 4, engine absent |
| agent execution | chat context 1, executor 3, runner 9, orchestrator 10, registry 12 |
| decision signal | repository 1, service 2, action/profile schemas absent |

These observations support an import-edge experiment. They do not justify a
score change before structural evidence exists.

## Problem Statement

Generic token and embedding retrieval can find a Python file whose own text
matches the query, but it cannot reliably follow a dependency whose vocabulary
is different.

For example:

```python
from application.schemas.context_pack import ContextPack
```

The builder may match "analysis context builder", while the schema file may
contain mostly field names and validation code. The dependency is explicit,
static, repository-local, and already representable as an `imports` relation,
yet the current Python index emits no such relation.

The same gap affects:

- Flask route module -> service module -> client/factory module;
- service -> repository/schema/config/support module;
- test -> production module;
- worker -> service module;
- façade -> engine module.

The defect is not that CST lacks recursive program understanding. It is that it
ignores an exact, cheap, static dependency signal that the existing graph
pipeline is designed to consume.

## Goals

1. Parse eligible Python source with the standard library without executing
   project code or resolving installed packages.
2. Emit stable declaration symbols for useful chunking, signal recall, repo
   profiling, and explain output.
3. Emit exact or closed ambiguous repository-local module import selectors.
4. Resolve imports only within the source project unit and active path
   inventory.
5. Reuse schema-v5 identity, persistence, global resolution, test association,
   traversal, ranking, trace source attribution, and P7 final selection.
6. Make producer activation deterministic for old ready schema-v5 indexes
   without an SQL schema bump or mandatory vector rebuild for unaffected files.
7. Fail softly per malformed or unsupported Python file while preserving its
   generic chunks and core module.
8. Prove deterministic structural correctness on a synthetic fixture.
9. Prove attributable retrieval value on both pinned real repositories.
10. Preserve all protected Java, frontend, MyBatis, generic-language, P6, and
    P7 behavior.
11. Leave an evidence-based stop decision between call acquisition and
    file-level reranking.

## Non-Goals

P8 v1 does not:

- execute `import`, `__import__`, `importlib`, a package manager, project
  configuration, test discovery, application startup, or any target function;
- inspect `sys.path`, `site-packages`, virtual environments, editable installs,
  `.pth` files, environment variables, or runtime import hooks;
- implement Python name binding, type inference, data flow, points-to analysis,
  dispatch, monkeypatching, descriptor semantics, metaclasses, or re-export
  resolution;
- persist `calls`, `uses_type`, `implements`, decorator, inheritance, Flask,
  FastAPI, Django, Celery, SQLAlchemy, or dependency-injection relations;
- resolve dynamic import calls, computed module names, conditional runtime
  paths, plugin registries, or string-based class/function references;
- treat a star import as proof of any imported symbol; only its statically
  named source module may be recorded;
- infer that `from package import name` means `package.name` is a submodule;
  v1 records the statically named base package/module;
- parse `pyproject.toml`, `setup.py`, `setup.cfg`, or custom build backends to
  reproduce arbitrary package mappings;
- add a language server, Tree-sitter Python dependency, compiler daemon, or
  model call;
- add a second graph store, relation kind, retrieval stage, public graph
  operation, result type, ContextPack group, or trace schema;
- change relation weights, ranking penalties, candidate limits, context
  budgets, result budgets, query planning, exploration limits, or P7 path
  diversity;
- guarantee fast-context parity;
- copy either real repository's source into tracked fixtures;
- update the roadmap as "implemented" before all gates pass.

## Causal Hypothesis

The reviewed hypothesis is intentionally narrow:

```text
If:
  A. at least one workflow module is already admitted as a graph seed, and
  B. that module contains an exact repository-local static import, and
  C. the imported module is relevant to the reviewed query,
then:
  the existing relation stage should acquire or strengthen that imported
  module without changing upstream lexical/semantic scores or final budgets.
```

The corresponding falsification conditions are:

- the target is not connected by a static import;
- the importer never enters the bounded graph seed population;
- the target is acquired with relation provenance but remains too low;
- the import adds more reviewer-labeled noise than relevant evidence;
- improvements require changing a graph weight or unrelated ranking rule.

P8 v1 changes only A-to-B structural production. It does not hide falsification
with a second mechanism.

## Architecture Decision

### Selected: One Standard-Library Python Graph Producer

Add `PythonGraphProducer` as a normal `GraphLanguagePlugin`.

```text
plugins.default_plugins()
  -> JavaPlugin
  -> FrontendGraphProducer
  -> MyBatisGraphProducer
  -> PythonGraphProducer
```

`ordered_graph_plugins()` remains the canonical registration ordering owner, so
the literal list order above is not relied upon for persistence determinism.

The producer has no store, retrieval, CLI, quality, or network dependency. It
receives only `PluginContext`, source bytes, chunks, and the core module signal.

### Rejected: A Parallel Python Dependency Store

A second store would duplicate:

- repository-relative path identity;
- project-unit scoping;
- deletion and incremental refresh;
- resolution states;
- graph readiness and recovery;
- relation traversal and explain behavior.

The current schema already models the needed facts.

### Rejected: Call Graph First

Calls require substantially more assumptions:

- binding a local name to an import or declaration;
- distinguishing function, method, callable object, and dynamic dispatch;
- handling aliases, attributes, inheritance, decorators, and monkeypatching;
- selecting useful confidence and ambiguity rules.

Static module imports are exact enough to evaluate first. A call graph before
this experiment would make improvements impossible to attribute.

### Rejected: File-Level Reranking First

Several daily targets are absent from the top 12 but explicitly imported by a
high-ranked module. Adding a reranker before producing that evidence would
optimize around a missing acquisition channel and could overfit path names.

### Rejected: Signal Schema 6

No new table column, relation kind, selector field, or traversal state is
required. A schema bump would force a broader migration and vector rebuild than
the behavior change needs.

P8 instead versions the graph producer contract in index metadata.

## Python Parsing Contract

### Supported Files

The producer supports a file only when its repository-relative suffix is
exactly `.py` or `.pyw`, case-sensitive. The scanner language is expected to
be `python`, but the suffix remains the closed authority so a mislabeled Python
file still works and a Python-labeled non-source file does not.

`.pyi`, generated Cython, notebooks, zip members, and extension modules are
outside v1.

Empty files continue to receive no chunks and therefore no core module or
producer graph. Unsupported files are never parsed by this producer.

### Parser

Use the running Python standard library's AST-only compile path:

```python
compile(
    content,
    context.file_path.as_posix(),
    "exec",
    flags=ast.PyCF_ONLY_AST | ast.PyCF_TYPE_COMMENTS,
    dont_inherit=True,
    optimize=0,
)
```

The source is bytes so Python's normal source-encoding cookie handling applies.
Compilation with `PyCF_ONLY_AST` creates an AST and does not execute imports,
decorators, class bodies, annotations, defaults, or any other project code.

The supported CST runtime remains Python 3.11+. The parser accepts syntax
understood by the running runtime. A file using syntax newer than that runtime
fails softly like any other syntax failure.

The producer catches expected per-file parse failures:

- `SyntaxError`;
- `UnicodeDecodeError`;
- `ValueError`;
- `TypeError`;
- `RecursionError`.

It does not catch `MemoryError`, `KeyboardInterrupt`, `SystemExit`, or other
process-level failures.

### Failure Result

A parse failure returns:

- no Python symbols;
- no Python declaration signals;
- no Python import relations;
- metadata `graph_parse_status="syntax_error"` or the corresponding closed
  diagnostic status;
- bounded diagnostic code/count only, never the source line or exception text;
- `fallback_required=False`, because there is no legacy Python graph producer.

Generic chunking and the core module remain available. One malformed file does
not suppress Python graph facts from other files.

### Fact Model

`python_graph.py` owns small frozen fact types:

- `PythonSourceRange`;
- `PythonDeclarationFact`;
- `PythonImportFact`;
- `PythonFactDiagnostic`;
- `PythonFactSet`.

Facts contain only normalized strings, integers, booleans, and tuples. They
hold no AST nodes after `parse()` returns.

The fact order is:

1. start line;
2. start column;
3. end line;
4. end column;
5. fact kind;
6. qualified name or import specifier.

No dictionary or AST traversal order is a persistence tie-break.
After ordering, retain at most 4,095 declaration facts/symbols so the existing
4,096-signal budget still reserves one slot for the core module before
chunking. Record the exact omitted declaration count in bounded parse metadata.
Import facts use their separate 256-item materialization cap below.

## Declaration Contract

### Included Declarations

P8 v1 emits declarations for:

- module-level `ClassDef`;
- classes nested directly in another included class;
- module-level `FunctionDef`;
- module-level `AsyncFunctionDef`;
- `FunctionDef` and `AsyncFunctionDef` directly owned by an included class.

“Module-level” and “class-owned” refer to the nearest enclosing declaration
scope, not to immediate AST-list membership. The walker may cross module/class
control-flow statements such as `if`, `try`, `with`, `for`, `while`, and
`match`, but it never crosses into a function, method, lambda, or
comprehension when collecting declarations. Thus a conditional definition at
module scope remains module-level, while a definition inside a function stays
excluded.

The following are not declaration signals:

- functions or classes nested inside a function/method;
- lambdas;
- comprehensions;
- assignments;
- imported names;
- properties or decorated functions as a separate special kind.

This boundary captures the public structure used by the two repositories while
avoiding thousands of short-lived local helper scopes and extra chunk
fragmentation.

### SymbolRef Projection

Each declaration produces one `SymbolRef`:

| AST declaration | symbol kind | symbol name |
| --- | --- | --- |
| class | `class` | simple class name |
| top-level sync/async function | `function` | simple function name |
| sync/async class member | `method` | simple method name |

The language is `python`; start/end lines come from the AST. Symbol metadata is
limited to `qualified_name`, `owner_qualified_name`, and `is_async` where
applicable.

For a decorated class or function, the declaration start is the earliest
decorator start; the end remains the declaration node's end. This keeps the
written declaration together for chunking without interpreting decorator
semantics. Columns are the AST's zero-based UTF-8 byte offsets.

These symbols flow through existing chunking. The producer does not add
synthetic symbol names or docstring text.

### CodeSignal Projection

Each included declaration also produces one schema-v5 `CodeSignal`:

| declaration | signal kind | recallable |
| --- | --- | --- |
| class | `type` | true |
| top-level function | `function` | true |
| class member | `method` | true |

The producer is `python_ast`. Signature is `""` and arity is `None` in v1.
P8 does not claim call-compatible Python signatures.

The qualified name is:

```text
<canonical-module-name>.<class-or-function-owner>.<declaration-name>
```

Examples:

```text
backend.services.content.ContentService
backend.services.content.ContentService.generate_content
src.services.import_parser.parse_import_from_bytes
```

`__init__.py` contributes the containing package name. Other files contribute
their filename stem. The source range and producer remain part of the existing
v5 signal ID, so repeated definitions do not collide.

The signal attaches to the existing chunk containing its start line. If no
such chunk exists, materialization fails closed for Python producer signals and
relations in that file while generic chunks/core module remain.

### Lexical Tokens

The producer proposes segments from retained declaration names only. It does
not add import specifiers, imported attributes, or local aliases as a separate
lexical channel; generic chunk tokenization already sees the written import
statement. Existing `_localized_plugin_tokens()` retains only tokens evidenced
in each chunk, so P8 cannot inject terms absent from source.

No docstring, annotation, decorator, default expression, or inferred type is
added as a new lexical channel.

## Canonical Python Module Names

### Import Roots

For one project unit, v1 recognizes exactly two possible import roots:

1. the project-unit root;
2. `<project-unit>/src`.

The second root is considered only when the candidate path is present in the
active path inventory. P8 does not parse packaging configuration to invent
other roots.

This closed rule covers:

- RedInk root package `backend`;
- daily root packages `src` and `data_provider`;
- conventional `src/<package>/...` layouts.

If the same import name maps to more than one active path/root, resolution is
ambiguous and no edge is traversed.

### Path-to-Module Projection

For an active Python path under an import root:

- strip `.py` or `.pyw`;
- if the terminal stem is `__init__`, remove that terminal segment;
- join remaining path segments with `.`;
- when a project-unit-root `__init__.py` would otherwise be empty, use the
  stable declaration identity `__init__` without claiming that it is a runtime
  package name;
- preserve case and Unicode exactly.

P8 does not case-fold, normalize filesystem aliases, resolve symlinks, or infer
namespace ownership from the host interpreter.

One path can have two valid import spellings. For example,
`src/payments/engine.py` can be imported as either `src.payments.engine` from
the project-unit root or `payments.engine` from the optional `src` root.
Declaration identity always uses the project-unit-root projection
(`src.payments.engine` in this example). Alternate-root spellings are lookup
aliases only; they do not create duplicate declaration signals.

### Module-to-Path Candidates

For import name `a.b`, each legal import root contributes:

```text
<root>/a/b.py
<root>/a/b.pyw
<root>/a/b/__init__.py
<root>/a/b/__init__.pyw
```

Only normalized active paths inside the source project unit survive. Candidate
paths are deduplicated and sorted by normalized repository-relative path before
they are stored or used as an identity input. No directory scan or filesystem
read occurs during materialization; `RepositoryPathIndex` is the authority.
Directories never become synthetic module signals, so an import of a bare
namespace package without an active module or `__init__` file has no target;
an explicit submodule file under that namespace may still resolve.

Candidate classification is:

- one active path: `selector_state="exact"`;
- more than one active path: `selector_state="candidates"`, later resolving to
  `ambiguous`;
- no active path for an absolute import: `selector_state="external"`;
- invalid/escaping relative selector: `selector_state="unresolved"`.

External, unresolved, and ambiguous rows remain diagnostic-only and are never
traversed. An exact active path that has no core module signal, such as an
empty file under the current core-module contract, remains unresolved and
non-traversable. More than one distinct active candidate remains ambiguous
even when one candidate is empty and therefore lacks a core module signal;
signal absence must not turn a path ambiguity into a unique resolution.

## Static Import Contract

### Supported Syntax

| syntax | recorded module dependency |
| --- | --- |
| `import a` | `a` |
| `import a.b as local` | `a.b` |
| `import a, b.c` | one dependency for `a`, one for `b.c` |
| `from a.b import Name` | `a.b` |
| `from a.b import Name as Local` | `a.b` |
| `from a.b import *` | `a.b`; no imported-symbol claim |
| `from .a import Name` | package-relative module `.a` |
| `from ..a import Name` | parent-package-relative module `..a` |
| `from . import sibling` | relative `sibling` module, only when its active path is exact/closed |
| `from . import *` | current package `__init__.py` only when that active path is exact |

Imports are collected wherever they occur in the AST, including a function,
class body, `try`, or `if TYPE_CHECKING` block. They remain module-level
dependency relations because P8 does not model execution paths or scope-local
bindings.

### Explicitly Unsupported Import Semantics

The producer emits no dependency for:

```python
importlib.import_module(name)
__import__(name)
exec(source)
eval(source)
```

It also does not infer:

- that an imported attribute is a function/class in the target;
- that `from package import child` necessarily targets `package.child`;
- a re-export chain through `__init__.py`;
- any installed/external target.

### Relative Resolution

For a normal module, relative imports start from its containing package. For
`__init__.py`, they start from that package itself.

`level=1` means current package, `level=2` removes one package segment, and so
on. Removing beyond the known package is an unresolved escape. A relative
import from a normal file with no package segment is unresolved. A
project-unit-root `__init__.py` is the closed exception: `.sibling` may resolve
to an exact sibling path inside that project unit.

Relative arithmetic is path-based inside the source project unit, so it does
not depend on choosing between a root and `src` import spelling. The resulting
path still goes through the same active-path and same-unit candidate rules.
Relative syntax never authorizes a cross-unit edge.

## Relation Contract

Every accepted static dependency becomes a schema-v5 `CodeRelation`:

```text
source_signal_id: current file's core module signal
kind: imports
target_kind: module
target_qualified_name: first canonical candidate path or raw selector
target_project_unit_key: source project unit
resolution: unresolved at materialization time
producer: python_ast
producer_confidence: 1.0
```

Metadata contains:

- `selector_state`;
- `specifier`;
- `candidates`;
- `import_form` (`import` or `from`);
- `relative_level`;
- `first_source_line`;
- `first_source_column`;
- `occurrence_count`.

The relation ID uses the existing `generate_v5_relation_id()`. Repeated
semantically identical imports in one file merge into one relation. The merge
keeps:

- the earliest source location;
- a summed occurrence count;

Different target modules never merge. External/unresolved rows use no active
target ID. Imported attribute names and local aliases are intentionally not
persisted: v1 models a module dependency, and retaining them would add metadata
without affecting resolution or retrieval.

Import locations use the enclosing `Import` or `ImportFrom` statement start,
not an alias token's implementation-dependent position. Multiple dependencies
from one statement therefore share a location and are ordered by their
semantic target.

### Budgets

P8 adds:

```text
MAX_PYTHON_IMPORTS_PER_FILE = 256
```

The cap applies after semantic target deduplication in canonical source order.
The producer also remains inside existing limits:

| budget | existing/new limit |
| --- | ---: |
| source bytes | existing `index.max_file_bytes` |
| Python declaration facts/symbols | 4,095, derived from the existing signal cap minus the core module |
| all signals per file, including module | existing 4,096 |
| all producer relations per file | existing 8,192 |
| distinct Python imports per file | new 256 |
| graph seeds/hops/edges/frontier/candidates | existing P5 limits |

Omitted counts are recorded through existing graph plugin/truncation metadata.
No unbounded list is stored in relation metadata.

## Producer Contract Activation

### Metadata Version

Add internal index metadata:

```text
graph_producer_version
```

and:

```text
TARGET_GRAPH_PRODUCER_VERSION = 1
```

The metadata version describes the complete file-local graph producer contract,
not the SQL schema and not only Python.

### Read Rules

For signal schema 5:

- stored producer version `1`: current;
- missing or `0`: pre-P8 producer contract, therefore graph status `stale`
  with reason `producer_contract_changed` when no stronger stale reason already
  exists;
- malformed or negative: raise the existing
  `IncompatibleSignalSchemaError`;
- stored version greater than `1`: future producer contract, fail closed and
  raise the same existing error before any write; never downgrade/reindex it
  with the older binary.

Schema versions below 5 retain existing legacy behavior. A future signal schema
retains existing incompatibility behavior.

### Upgrade Behavior

On the first authoritative index/refresh under P8:

1. the missing producer version makes a former ready-v5 graph stale;
2. the existing stale-on-entry path reparses every active non-empty file;
3. graph rows are replaced using the registered producer set;
4. only paths whose chunk/embedding identity actually changes rebuild vectors;
5. producer relations resolve;
6. test associations regenerate from the resolved imports;
7. test relations resolve;
8. integrity validation completes;
9. `graph_producer_version=1` is written or retained atomically with final
   ready state.

This is not an SQL schema migration. Non-Python files may be reparsed once, but
their unchanged chunks and vectors are reused. A fault before final ready
leaves graph evidence stale and recoverable under the existing P5/P6 contract.

### Future Changes

Any future change that alters persisted producer facts for unchanged files must
increment `TARGET_GRAPH_PRODUCER_VERSION`. Cosmetic refactors that leave the
fact contract byte-identical do not.

## Resolution And Test Association

P8 does not add a Python-specific global resolver.

The existing resolver receives path candidates and:

- resolves the single exact active core module;
- marks multiple matches ambiguous;
- leaves absent/external/unresolved selectors without a target ID;
- preserves producer and resolution confidence separately.

Because Python imports are same-unit by construction, no project-unit widening
is permitted.

After producer resolution, the existing test-association pass sees resolved
`imports` relations from recognized Python test files. It may then create up to
eight exact `tests` relations to non-test, non-generated, same-unit modules.

P8 adds tests proving this reuse. It does not add:

- a global test boost;
- test-to-test edges;
- substring/basename association;
- broad trust in a persisted `is_test` flag;
- ungated reverse test traversal.

The current exact test intent/P4 goal gate remains the only traversal gate for
`tests`.

## Retrieval Behavior

### No New Stage Or Weight

Resolved Python imports enter the existing relation stage:

```text
next_score =
  current_score
  * effective_confidence
  * 0.85
  * 0.8
```

They use:

- score part `graph_imports_match`;
- provenance flag `resolved_relation`;
- the existing original/planner graph-seed flag;
- existing candidate dominance, work caps, and protected-direct behavior.

Existing ready-graph seeding already adds the file's `core_module` signal for
every selected seed chunk, even when the matching chunk is a later declaration
chunk. Because Python import relations originate at that core module, no new
chunk-to-module bridge or relation source is needed.

P8 does not tune the import weight after seeing the benchmark.

### Language-Neutral Reason

The current reason for `graph_imports_match` is `frontend import dependency`.
That becomes inaccurate once Python uses the same relation kind.

P8 changes the human reason to:

```text
static module dependency
```

The score-part key, relation kind, trace source `relation`, and response schemas
do not change. Existing frontend tests and characterization fixtures must
accept only this intentional wording change; their membership, scores, and
ordering remain protected.

### Direction

`imports` remains outgoing-only.

If route module A imports service module B, a seed in A may acquire B. A seed
in B does not automatically acquire every importer of B. This prevents a
popular utility from flooding results with all callers and keeps P8's causal
claim narrow.

### P7 Interaction

P7's final selection remains authoritative:

- the first ranked chunk for a path wins;
- ordinary result paths remain unique;
- anchors remain independently allocated;
- `duplicate_result_path` accounting remains exact.

Python graph evidence can add or strengthen candidate paths before that
boundary; it cannot consume multiple result slots for one file.

An import targets the existing core-module signal, so a graph-origin candidate
initially represents that module's core owner chunk. P8 does not search the
target file for a better declaration chunk. If the correct path is acquired
but its selected chunk is repeatedly insufficient, that is evidence for the
separate file-level reranking outcome, not permission to add reranking here.

## Public Compatibility

P8 keeps:

- `cst index`, `refresh`, `query`, `trace`, `context`, `explore`, `stats`, and
  `explain` command names and arguments;
- MCP operation names and payload schemas;
- RetrievalTrace v1;
- ContextPack v2;
- ExplorationTrace v2;
- result, anchor, and summary dataclasses;
- relation kind names and graph schema 5;
- all current budgets.

Expected observable changes are limited to:

- Python symbols and graph neighbours in existing stats/explain surfaces;
- relation-origin candidates and `graph_imports_match` on affected results;
- the language-neutral import reason;
- a previously unsafe multi-path module selector stays ambiguous when one
  active candidate has no core signal, instead of becoming
  `resolved_unique`;
- one-time graph producer-contract refresh of an old ready-v5 index.

No public payload exposes raw AST, source bytes, local absolute paths, or the
producer-contract metadata key.

## Security And Privacy

P8 parsing:

- operates only on bytes already admitted by the scanner;
- stays inside the existing maximum file size;
- never follows a symlink or repository-relative escape;
- never opens an imported module during producer materialization;
- never executes source, imports, build files, tests, decorators, or defaults;
- never contacts a network service;
- never reads environment variables or credentials;
- stores only declaration/import identifiers already present in indexed source.

Remote embedding disclosure remains unchanged: if a user configures a remote
embedding provider, existing source chunks and queries may be sent under the
current documented contract. P8 adds no remote caller and the acceptance
profiles use local hash embeddings.

Tracked benchmark artifacts may contain:

- public repository URL;
- exact public commit;
- repository-relative file paths;
- authored query text;
- role labels, ranks, scores, relation IDs, and hashes.

They must not contain:

- `/Users/flobby/...` source locators in portable fixtures;
- local dirty-worktree contents;
- `.env`, provider YAML secrets, runtime history/images, databases, or logs;
- source file bodies from either external repository;
- raw exception text that may echo source.

## Benchmark Design

### Source Preparation

Both real repositories use the existing remote quality preparation contract:

- HTTPS source URL;
- exact 40-hex commit;
- detached checkout under `.quality/repos`;
- checkout provenance validation;
- a separate disposable indexed workspace;
- hash embedding, planner off;
- exact include patterns;
- no writes to the user's original directories.

RedInk include patterns:

```text
backend/**/*.py
tests/**/*.py
pyproject.toml
```

Daily include patterns:

```text
data_provider/**/*.py
src/**/*.py
tests/test_data_fetcher_prefetch_stock_names.py
```

The daily list intentionally preserves the 203-file P7 continuity corpus.

### Role Vocabulary

Every gold path is reviewer-labeled with one role:

- `entrypoint`: route, worker, façade, orchestration entry, or public workflow
  function/module;
- `implementation`: service, engine, factory, repository, or core behavior;
- `support`: schema, configuration, client, utility, contract, or adapter;
- `test`: a test module for the reviewed behavior.

Gold also has necessity:

- `required`: needed to answer the query;
- `contextual`: useful corroborating context but not required for pass.

Tests are required only when the query explicitly asks for tests. The frozen P7
query does not require the prefetch test. A file is not gold merely because an
import edge exists.

Before candidate execution, every prose contextual category in the tables
below is expanded to an exact path list in the manifest. For noise accounting,
an ordinary selected path is relevant when it is frozen as required or
contextual for that case; every other selected ordinary path is noise. There
is no post-candidate relevance relabeling. This conservative closed-world rule
makes baseline/candidate noise deltas reproducible and prevents a newly
observed import from being declared relevant merely because P8 selected it.

### RedInk Cases

| id | query | required roles/paths | contextual paths |
| --- | --- | --- | --- |
| `redink-app-wiring` | `Flask app register API blueprints routes` | entrypoint `backend/app.py`; entrypoint `backend/routes/__init__.py` | concrete route modules |
| `redink-content-flow` | `content generation route service text chat client` | entrypoint `backend/routes/content_routes.py`; implementation `backend/services/content.py`; support `backend/utils/text_client.py` | route utility |
| `redink-outline-flow` | `outline generation upload base64 service text client` | entrypoint `backend/routes/outline_routes.py`; implementation `backend/services/outline.py`; support `backend/utils/text_client.py` | route utility |
| `redink-image-flow` | `image generation retry service generator factory compressor` | entrypoint `backend/routes/image_routes.py`; implementation `backend/services/image.py`; implementation `backend/generators/factory.py`; support `backend/utils/image_compressor.py` | concrete generators |
| `redink-history-flow` | `history list detail delete route service archive` | entrypoint `backend/routes/history_routes.py`; implementation `backend/services/history.py` | app wiring |
| `redink-provider-config` | `配置页面保存文本服务商和图片服务商 YAML active_provider` | entrypoint `backend/routes/config_routes.py`; support `backend/config.py`; support `backend/routes/utils.py` | content/outline/image consumers |

RedInk has no substantive test module at the pinned commit. Its two files under
`tests/` are package/setup scaffolding. This is intentional: P8 cannot pass the
real profile by over-optimizing test association.

### Daily Cases

| id | query | required roles/paths |
| --- | --- | --- |
| `daily-prefetch-continuity` | `data fetcher prefetch stock names provider fallback pipeline` | implementation `src/core/pipeline.py`; implementation `data_provider/base.py` |
| `daily-prefetch-tests` | `tests for stock name prefetch provider fallback pipeline` | test `tests/test_data_fetcher_prefetch_stock_names.py`; implementation `src/core/pipeline.py`; implementation `data_provider/base.py` |
| `daily-import-parser` | `import parser stock name resolver code normalization` | entrypoint `src/services/import_parser.py`; implementation `src/services/name_to_code_resolver.py`; support `src/services/stock_code_utils.py` |
| `daily-analysis-context` | `analysis context builder schema prompt sanitized fields` | implementation `src/services/analysis_context_builder.py`; support `src/schemas/analysis_context_pack.py` |
| `daily-notification-diagnostics` | `notification diagnostics channel routing contracts endpoints` | entrypoint `src/services/notification_diagnostics.py`; support `src/notification_routing.py`; support `src/notification_contracts.py` |
| `daily-task-queue` | `task queue run diagnostics stock code analysis metadata` | entrypoint `src/services/task_queue.py`; support `src/services/run_diagnostics.py`; support `src/utils/analysis_metadata.py`; support `src/services/stock_code_utils.py` |
| `daily-runtime-scheduler` | `runtime scheduler schedule times config service` | entrypoint `src/services/runtime_scheduler.py`; implementation `src/scheduler.py`; support `src/config.py` |
| `daily-portfolio-risk` | `portfolio risk positions decisions repository calculations` | entrypoint `src/services/portfolio_risk_service.py`; implementation `src/services/portfolio_service.py`; implementation `src/repositories/portfolio_repo.py`; support `src/services/decision_signal_service.py` |
| `daily-alert-worker` | `alert worker rules history decisions market phase service` | entrypoint `src/services/alert_worker.py`; implementation `src/services/alert_service.py`; support `src/services/history_service.py`; support `src/services/decision_signal_service.py` |
| `daily-backtest` | `backtest service engine repository performance evaluation` | entrypoint `src/services/backtest_service.py`; implementation `src/core/backtest_engine.py`; implementation `src/repositories/backtest_repo.py` |
| `daily-agent-execution` | `agent execution loop tool registry chat context provider trace` | entrypoint `src/agent/executor.py`; implementation `src/agent/runner.py`; support `src/agent/tools/registry.py`; support `src/agent/chat_context.py`; support `src/agent/provider_trace.py` |
| `daily-decision-signal` | `decision signal service repository profile action guardrail` | entrypoint `src/services/decision_signal_service.py`; implementation `src/repositories/decision_signal_repo.py`; support `src/schemas/decision_profile.py`; support `src/schemas/decision_action.py` |

Before implementation, every gold path and role is rechecked against the pinned
source. Any correction is made in the manifest before a candidate run, with a
recorded reason. Candidate results may not be used to invent new gold.

### Context And Exploration Witnesses

The standard quality catalog evaluates all 18 cases in informational results
mode; it is a compatibility/metrics surface rather than the ship authority.
The paired runner additionally replays these fixed witnesses through existing
public surfaces:

| mode | case | purpose |
| --- | --- | --- |
| ContextPack | `redink-image-flow` | multi-hop route -> service -> factory/compressor coverage |
| ContextPack | `daily-analysis-context` | builder -> schema coverage |
| exploration | `redink-content-flow` | route -> service -> client coverage and bounded termination |
| exploration | `daily-import-parser` | parser -> resolver/utility coverage and bounded termination |
| exploration | `daily-prefetch-continuity` | P7 path-diversity and retrieval-call non-regression |

These are alternate projections of existing cases, not five additional gold
cases, and they do not change the 18-case Recall@12 denominator. They use the
existing default ContextPack/exploration budgets; P8 does not tune them.

### Baseline And Candidate Pairing

The baseline is built from exact commit
`75cc65ed627dd5982460a4d4a10d28f10e7151b8`. The candidate is built from the
P8 implementation tree. Both use:

- the same prepared source commits and include patterns;
- the same hash embedding configuration;
- planner disabled;
- the same retrieval/context/exploration budgets;
- a fresh index;
- two repeated runs after warm-up;
- normalized timing kept separate from deterministic membership evidence.

The artifact records stage trajectory for every required/contextual path:

```text
semantic acquisition rank
lexical acquisition rank
path/symbol acquisition rank
direct acquisition rank
merged candidate rank
ranking rank
context-expansion rank
final selected rank
relation provenance and edge ID
```

`not_acquired` is distinct from `acquired_below_limit`.

### Structural Metrics

The structural report records:

- Python files parsed/rejected;
- declarations by kind;
- imports by selector state;
- resolved, ambiguous, external, and unresolved relation counts;
- exact test associations;
- omitted signal/import counts;
- deterministic signal/relation ID projection;
- old-v5 upgrade and recovery state.

### Retrieval Metrics

One required item is the exact tuple:

```text
(repository, case_id, normalized path, role, necessity=required)
```

Repeated broad role labels such as `implementation` do not collapse distinct
required paths. Per-repository and combined required-role Recall@12 are micro
averages over these required items; the combined value is not an unweighted
average of the two repositories. An unselected required item uses sentinel
rank 13 only for rank-delta arithmetic, while its acquisition trajectory still
distinguishes `not_acquired`, `acquired_below_limit`, and
`acquired_not_selected`.

For required gold, report:

- role Recall@12;
- path Recall@12;
- MRR@12;
- worst required rank;
- newly satisfied required roles;
- lost required roles.

For the selected set:

- reviewer-labeled noise count/ratio;
- unique path count;
- graph-origin candidate count;
- relation-supported selected count;
- winner and protected-direct stability.

Aggregate noise ratio is total reviewer-labeled noise paths divided by total
selected ordinary paths across all 18 cases. A selected path is
relation-supported only when its final score/provenance contains
`graph_imports_match` and the capture names the persisted resolved exact
`imports` relation that supplied that contribution.

A required-item gain or rank improvement is credited to the import mechanism
only when the improved selected representative is graph-origin with that exact
import witness. A change that occurs through declaration-driven chunking,
direct symbol recall, or localized lexical tokens is reported as a
non-relation producer effect and does not satisfy the qualifying-improvement
gates below.

Context/exploration witnesses additionally record:

- final ContextPack role coverage;
- graph-origin target chunk range and reviewed-role coverage;
- initial/final goal coverage;
- retrieval call count;
- final unique paths;
- relation source counts.

### Ship Gates

P8 v1 ships only when all are true:

1. required-role Recall@12 is non-decreasing for each repository;
2. graph-origin exact imports newly satisfy at least 0.05 of the combined
   required-item denominator, and total combined required-role Recall@12
   improves by at least that amount;
3. no required path present in the baseline top 12 falls out;
4. at least four cases gain a required path or improve the worst required rank
   by at least three positions through a credited graph-origin import;
5. at least three qualifying improvements occur in daily; RedInk's already
   saturated required recall is judged as a precision/provenance guard rather
   than requiring artificial rank movement;
6. at least six cases select relation-supported evidence, including at least
   two RedInk and three daily cases;
7. every claimed relation witness maps to one persisted resolved exact import;
8. reviewer-labeled aggregate noise ratio increases by no more than 0.02 and no
   case gains more than one new noise path;
9. the frozen P7 continuity query retains 12 unique paths and both required
   paths;
10. explicit path/symbol/direct protected winners remain unchanged;
11. deterministic repeated path/rank/relation projections are byte-identical.

If gate 2 is not met, P8 does not change weights to manufacture a pass. The
experiment is reported as insufficient and the next mechanism is selected from
the observed failure boundary.

## Performance And Resource Gates

P8 uses the existing P6 benchmark and work-accounting contracts.

Required results:

- P6 focused suite remains fully passing;
- no new full-suite failure or established-skip change;
- graph traversal stays inside all current P5 work caps;
- no query adds an extra retrieval call or exploration round;
- the paired real-profile report includes index wall time, query latency,
  SQLite size, vector bytes written/reused, declarations, and relations.

The Python producer should be cheap, but this design does not hide cost with an
unreviewed threshold. A candidate with either:

- more than 25% index wall-time regression on the 203-file daily slice; or
- more than 10% paired query-latency regression when the absolute increase is
  at least 5 ms

requires review and cannot ship automatically. Timing is measured repeatedly
and reported separately from deterministic correctness.

## Determinism

The following must be independent of file insertion, plugin registration,
SQLite row, dictionary, and AST traversal order:

- module candidate order;
- declaration fact order;
- signal IDs;
- relation IDs;
- relation occurrence merging;
- resolution state;
- test associations;
- relation-expanded candidate order;
- final path order.

The synthetic fixture is indexed in forward and reverse input order. Fresh,
no-op authoritative, incremental change, deletion, recovery, and repeated query
projections must converge to the same active graph for the same source state.

## Change Surface

Expected product changes:

| file | responsibility |
| --- | --- |
| `src/context_search_tool/python_graph.py` | pure AST facts, module selectors, declarations, signals, import relations |
| `src/context_search_tool/plugins.py` | register `PythonGraphProducer` |
| `src/context_search_tool/graph_contract.py` | Python import cap |
| `src/context_search_tool/graph_lifecycle.py` | producer-contract metadata/version validation |
| `src/context_search_tool/sqlite_store.py` | initialize/finalize producer version with graph readiness |
| `src/context_search_tool/indexer.py` | producer-contract stale activation and reason |
| `src/context_search_tool/graph_resolution.py` | generic module-candidate ambiguity guard for signal-less active paths |
| `src/context_search_tool/retrieval_core/relation_policy.py` | language-neutral import reason |

Expected tests/artifacts:

| path | responsibility |
| --- | --- |
| `tests/test_python_graph.py` | parse/materialize/module-resolution contract |
| `tests/test_graph_lifecycle.py` | old/current/future producer versions |
| `tests/test_graph_store.py` | initialization and both ready-publication paths |
| `tests/test_index_health.py` | stale/current/future health projection |
| `tests/test_indexer_manifest.py` | producer-contract activation |
| `tests/test_graph_resolution.py` | exact/ambiguous/external Python module selectors |
| `tests/test_incremental_refresh.py` | activation/change/delete/no-op/recovery |
| `tests/test_test_association.py` | resolved Python import -> exact test association |
| `tests/test_resolved_graph_expansion.py` | existing imports traversal/weight/protection |
| `tests/test_retrieval_pipeline.py` | end-to-end synthetic retrieval and P7 selection |
| `tests/test_p5_explain.py` | existing explain surface |
| `tests/test_exploration_p7.py` | P7 interaction witness if needed |
| `tests/test_p8_graph_contract.py` | deterministic structural projection |
| `tests/fixtures/p8-python-graphs/` | synthetic positive/negative repository |
| `tests/fixtures/retrieval_quality/p8_python_graphs.json` | pinned two-repository catalog |
| `tests/fixtures/p8_python_graphs/input_manifest.json` | protected sources, queries, roles, hashes |
| `tests/p8_python_graph_identity.py` | protected constants and manifest validation |
| `tests/generate_p8_python_graph_manifest.py` | reviewed manifest/projection generator |
| `tests/p8_real_python_graphs_acceptance.py` | paired baseline/candidate trajectory and witness checks |
| `tests/test_p8_real_python_graphs_acceptance.py` | runner identity/privacy/gate tests |

Existing expected P5 projections may change only for:

- additive producer-contract readiness metadata;
- Python facts in a fixture that actually contains Python files;
- the language-neutral import reason.

Java/frontend/MyBatis graph membership and all no-Python fixture projections
must otherwise remain exact.

## Delivery Decomposition

The implementation should remain reviewable in these logical slices:

1. freeze baseline, source identity, gold roles, and current projections;
2. add failing pure AST/declaration/import-selector tests;
3. implement the isolated Python producer without default registration;
4. add failing producer-version activation/recovery tests;
5. register the producer and activate old schema-v5 indexes;
6. prove existing resolver and test association with Python imports;
7. prove relation retrieval and P7 compatibility without score changes;
8. run the pinned paired benchmark and apply the ship/stop gates;
9. run protected/full/P6/quality gates and update documentation only after
   acceptance.

No staging, commit, push, or pull request is implied by these slices.

## Risks And Mitigations

- **False runtime-import claim:** resolve only active repository paths under two
  closed roots; persist ambiguity/external/unresolved states and never traverse
  them.
- **Producer added but old index remains empty:** producer-contract metadata
  makes pre-P8 ready-v5 state stale and reparses active files.
- **Unnecessary schema migration:** reuse schema 5 and rebuild vectors only
  where chunk identity changes.
- **Future binary downgrades graph facts:** a stored producer version above the
  supported target fails closed.
- **AST parser executes code:** use AST-only compile on bytes; never import or
  evaluate target code.
- **Malformed file breaks repository:** return bounded per-file diagnostics and
  keep generic chunks/core module.
- **Chunk explosion:** include only module-level/class-owned declarations and
  retain the 4,096-signal limit.
- **Import flood:** source-order dedupe and a 256-import cap, plus existing
  traversal work caps.
- **Popular utility floods callers:** imports remain outgoing-only.
- **Test pollution:** reuse existing exact same-unit association and intent
  gate; RedInk supplies no substantive tests.
- **Gold overfit:** freeze roles before candidate runs; an import edge alone
  never makes a file relevant.
- **Weight tuning hides weak evidence:** import weight and ranking stay fixed;
  failure selects the next phase.
- **Dirty local repos contaminate evidence:** prepare exact remote commits in
  disposable workspaces and never index originals.
- **Reason wording silently changes compatibility:** isolate the one
  language-neutral wording delta in characterization/format tests.
- **Private data enters artifacts:** persist only public commits, relative
  paths, queries, ranks, hashes, and bounded graph metadata.

## Acceptance Criteria

P8 Python Static Structure Retrieval v1 is complete only when:

1. `PythonGraphProducer` is the only new language producer.
2. It uses the standard library AST-only path and executes no target code.
3. Supported, empty, encoded, malformed, and unsupported files follow the
   declared parse/fallback contract.
4. Included declaration boundaries, qualified names, ranges, symbols, signal
   kinds, recallability, and IDs are deterministic.
5. Function/method signature and arity remain unclaimed in v1.
6. Root and `src` import roots are the only roots; active same-unit paths are
   the only targets.
7. Absolute, relative, alias, multi-import, star-source, package-init, `.pyw`,
   ambiguity, external, escape, and dynamic-import cases match the closed
   syntax table.
8. `from package import name` does not invent a `package.name` submodule edge.
9. Relations originate at the core module, use `imports`, producer
   `python_ast`, confidence 1.0, and existing v5 identity.
10. Repeated imports merge deterministically with exact occurrence metadata.
11. The 256 Python import cap and all existing P5 graph caps are enforced.
12. Exact/unique imports resolve; ambiguous/external/unresolved imports never
    traverse or text-fallback.
13. Producer resolution precedes regenerated test association, which precedes
    association resolution.
14. Python tests create only exact same-unit non-test/non-generated
    associations and remain intent-gated.
15. A pre-P8 ready schema-v5 index becomes stale, reparses safely, and reaches
    ready with producer version 1.
16. Current producer version no-ops; malformed/negative/future versions fail
    according to the declared contract without downgrade.
17. Faults during activation never expose partially refreshed graph evidence
    and converge after recovery.
18. SQL schema remains 5 and no new graph table/column/relation kind appears.
19. Resolved Python imports use the existing weight, decay, score part,
    dominance, budgets, and protected-direct behavior.
20. The only intended shared reason change is `static module dependency`.
21. RetrievalTrace v1, ContextPack v2, ExplorationTrace v2, public operations,
    payload shapes, and budgets remain unchanged.
22. P7 ordinary result paths remain unique and duplicate accounting remains
    exact.
23. Synthetic projections are byte-identical across forward/reverse, fresh,
    no-op, incremental, delete, and recovery paths.
24. Both real sources match their pinned commit/inventory contract.
25. Gold roles are frozen before candidate execution and resolver is not
    incorrectly added to the P7 continuity gold.
26. Every real relation claim has a persisted exact-edge witness.
27. All eleven retrieval ship gates pass.
28. RedInk proves exact relation provenance without forced required-rank
    movement or a substantive test suite; daily proves relation-attributable
    recall/rank value and explicit test association only on the test-intent
    case.
29. P5 Java/frontend/MyBatis/generic projections and protected direct winners
    remain within the reviewed allowlist.
30. P6 focused performance/freshness gates pass with no product-policy edit.
31. Raw CI quality, protected P2/P4/P5/P7 gates, focused suites, and full suite
    pass with the established skips audited.
32. No local absolute source path, dirty-worktree content, secret, source body,
    or raw exception enters tracked benchmark artifacts.
33. The final diff contains only lines traceable to this design and companion
    plan.
34. Roadmap/README completion claims are added only after acceptance.
35. Implementation stops without adding calls or reranking.

## Stop And Next-Phase Decision

After the import-only candidate is measured, choose exactly one outcome:

### Outcome A: Ship P8 v1

All acceptance and real-profile gates pass. Document the bounded claim:
Python declarations and exact static module dependencies now participate in
existing graph retrieval.

### Outcome B: Structural Acquisition Works, Ranking Is Still The Loss

Required targets carry exact relation provenance in the expanded population but
remain below the distinct-path result budget. Stop P8 and design a separate
file-level structural reranker. Do not change the import weight inside P8.

### Outcome C: Imports Do Not Represent The Missing Workflow Link

Required targets are not connected by a static import from admitted seeds.
Stop P8 and decide whether a small Python call/binding slice has enough exact
evidence for a new design. Do not add calls opportunistically.

### Outcome D: Noise Or Cost Exceeds Value

The real profile fails precision, protected behavior, determinism, lifecycle,
or performance gates. Reject or narrow the producer. Do not publish a partial
quality claim.

## Review Checklist

A reviewer should explicitly verify:

- AST-only safety and failure handling;
- declaration boundary and chunking impact;
- root/`src` path semantics;
- relative-import level arithmetic;
- exact/ambiguous/external selector classification;
- relation identity/occurrence merge;
- producer-version upgrade and future-version downgrade prevention;
- resolver/test-association sequencing;
- outgoing-only traversal and unchanged weight;
- P7 result interaction;
- source/gold freeze and two-repository causal metrics;
- protected P5/P6/P7 compatibility;
- privacy of tracked evidence;
- unconditional stop before calls/reranking.

Any unresolved blocker or major correctness, lifecycle, security, privacy,
determinism, compatibility, or benchmark-validity finding keeps this design in
draft.
