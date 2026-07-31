# P15 Python Exact Imported-Symbol Relations v1 Design

Date: 2026-07-31
Status: Reviewed on 2026-07-31; implementation not authorized
Repository: `context-search-tool`
Behavior baseline: `main@5f56de2e1b57ed7f1ec0ee9a513b508461d78233`

## Decision

P15 tests one narrow acquisition change. For an eligible `from module import Name as LocalName`, retain P8's source-module to target-module `imports` relation and additionally target the one existing Python declaration signal for `Name`. The added relation reuses `imports`, weight `0.85`, graph decay `0.8`, `graph_imports_match`, reason `static module dependency`, outgoing-only traversal, current ranking, and P7 path-diverse selection.

No production work begins until a product-free oracle passes. This document does not authorize implementation.

## Evidence Boundary

P7's accepted follow-up rule requires distinguishing missing structural acquisition from acquired-but-low ranking. P15 follows that sequence.

P8 already emits Python top-level `type`/`function` signals and repository-local module imports, but `PythonImportFact` discards the imported name and alias. Consequently its relation targets the target file's `core_module` signal, not the declaration chunk. P8's final record showed useful structure but rejected its retrieval-quality claim; its remaining gains were not import-creditable.

P9, P9a, and P10 exhausted relation-slot membership and shallow affinity variants. P11 exhausted indexed-vector overflow admission. P12 showed that a true repository-term membership test is not a relevance ranker. P15 must not reopen those mechanisms or tune weights, predicates, or budgets after seeing gold.

P14's final accepted P8 captures leave 8 required items/7 paths under hash and 7 items/6 paths under online BGE. Current declaration applicability is only a source-level expectation, not an oracle result:

| residual path | existing P8 declaration surface | v1 expectation |
| --- | --- | --- |
| `src/agent/tools/registry.py` | `ToolRegistry`, top-level functions | potentially eligible |
| `src/schemas/decision_profile.py` | `DecisionProfileFilter`, normalization functions | potentially eligible |
| `src/schemas/decision_action.py` | top-level normalization/display functions; type aliases excluded | potentially eligible |
| `src/services/stock_code_utils.py` | top-level functions; missed in two cases | potentially eligible |
| `src/config.py` | `Config`, `get_config` | potentially eligible |
| `src/utils/analysis_metadata.py` | relevant assignment/constant only | expected non-goal residual |

`src/services/portfolio_service.py` is a hash-only additional miss with `PortfolioService`; online already selects it. The oracle must verify actual import witnesses before any path is credited.

`merge_score_parts()` max-merges graph evidence and keeps one graph choice, so module and exact-symbol edges cannot numerically double-add `graph_imports_match` on one chunk. They can reach different chunks in one path; P7 then keeps the first ranked chunk. Oracle credit must therefore bind the exact target signal and chunk, not merely count edges.

## Falsifiable Hypothesis

When an admitted workflow module statically imports a relevant support declaration, an exact declaration-target edge will acquire or strengthen the declaration chunk and improve net required Top-12 recall/rank without required loss or noise growth.

The hypothesis is false if the residual is not representable, the exact edge does not traverse, the declaration remains below selection, the module chunk still wins without net benefit, or any gain requires a new ranking/selection rule.

## Goals

1. Preserve imported name and local alias without changing module-edge output.
2. Resolve only exact same-unit declarations already represented by P8.
3. Target the existing declaration chunk with current relation semantics.
4. Make duplicate, ambiguity, relative-import, re-export, budget, lifecycle,
   attribution, privacy, and determinism behavior closed and testable.
5. Answer acquisition versus ranking before product implementation.

## Non-Goals

P15 v1 excludes call graphs, type inference, runtime imports, assignments, constants, type aliases, methods, nested functions, `import module as m; m.attr`, star/dynamic imports, re-export traversal, arbitrary packaging rules, language servers, new stores or SQL schema, query/planner changes, ranking weights, P9-P11 membership/listwise reranking, larger final/context/graph budgets, P6 release debt, dashboard work, and memory product surfaces.

`analysis_metadata.py` may remain missed. Adding assignment support to pass a gate invalidates P15.

## Exact Behavior Contract

### Facts and syntax

Keep `PythonImportFact` and existing module materialization unchanged. Add a
separate frozen `PythonImportedSymbolFact` containing module as written,
relative level, imported name, local name, and statement source range.

Emit it only for `ast.ImportFrom` with a non-empty named module, a non-star
simple imported identifier, and P8's successful AST-only parse. Named relative
forms such as `from .target import Name` are eligible. Bare
`from . import Name` is excluded because `Name` may be a sibling module,
package attribute, or re-export. Imports under functions, `try`, or
`TYPE_CHECKING` remain static, matching P8.

`local_name` is the alias when present, otherwise the imported name. It is
bounded metadata only: it changes neither target qualified name, lexical
tokens, query terms, score parts, nor ranking. P15 does not require an AST Load
use of the local binding; that would be a separate binding-analysis contract.

### Module and target resolution

Run `python_module_selector()` first. A symbol selector is traversable only for
an active same-project-unit target. Multi-path module ambiguity stays ambiguous
even if one path alone declares the name. External, escaping, missing, empty,
or bare-relative targets do not traverse.

Derive the canonical target with existing `python_module_name()`:

```text
<canonical target module>.<imported_name>
```

An eligible target is an active signal with exact target file path and
qualified name, producer `python_ast`, language `python`, and kind exactly
`type` or `function`. One match resolves; zero stays unresolved; two or more,
including a same-name type/function or repeated definition, are ambiguous.
Capitalization is never a kind heuristic.

Methods, nested declarations, assignments, constants, and type aliases do not
qualify. A re-export qualifies only if the named target module itself owns the
declaration signal; P15 never follows an alias chain through `__init__.py`.

### Relation, deduplication, and budgets

The relation originates at the importing file's core-module signal, uses kind
`imports`, producer `python_ast`, confidence `1.0`, and the same project unit.
Metadata records `resolution_basis=exact_python_imported_symbol`, module
selector, exact target path, imported name, sorted unique local names, relative
level, earliest source location, and occurrence count.

Repeated imports deduplicate by existing v5 relation identity, retain the
earliest location, sum occurrences, and union local names deterministically.
Keep the module-import 256 cap intact. Apply the same 256 value as an independent
exact-symbol cap so new evidence cannot evict a P8 module edge; report
`graph_omitted_imported_symbols`. Existing 8,192 producer-relation and all query
work caps remain unchanged.

### Frozen resolver seam

The current resolver accepts one literal `target_kind`; it cannot safely express
the union `{type,function}`. Guessing from case or emitting independently
resolvable type/function edges would mishandle cross-kind ambiguity.

The 2026-07-31 review freezes R1 as one internal selector target kind
`python_declaration` with closed metadata
`target_signal_kinds=("type","function")`. A fail-closed resolver/SQLite
lookup constrains exact path, producer, language, and qualified name, then
reuses existing cardinality classification. The selector kind remains stable
for relation identity; `target_signal_id` identifies the actual declaration.
The resolution session and graph-integrity check must explicitly validate the
actual target kind against that closed set; the pseudo-kind must never be
compared as though it were the persisted signal kind. This adds no relation
kind or SQL schema. If implementation cannot preserve this exact encoding and
generic integrity outside it, P15 stops for redesign.

### Retrieval, explain, and lifecycle

Keep the module edge. Exact-symbol and module evidence share one score key and
max merge. No symbol-specific boost, reason, selection slot, or public field is
added. Tests must cover same-chunk merge, different-chunk winners in both
directions, unique final paths, and winner-consistent trace/reasons.

RetrievalTrace stays v1. Existing explain rows expose selector basis,
resolution, target signal ID, and declaration range. Acceptance credit requires
the persisted P15 relation ID, source signal, target signal, and selected or
rank-improved target chunk; `graph_imports_match` alone is insufficient.

Bump `TARGET_GRAPH_PRODUCER_VERSION` from 1 to 2. Schema remains 5. Missing/0/1 becomes stale with `producer_contract_changed`; 2 is current; malformed,
negative, or future values fail closed. Authoritative refresh reparses active
files, resolves relations and test associations, then publishes ready
atomically. A second no-op parses zero files. P15 adds no symbols, chunks, or
lexical tokens, so vectors must be reused.

## Task-0 Oracle

No product file changes before an oracle disposition of `proceed`.

The test-only oracle freezes source/gold/query/role/threshold hashes, indexes
baseline code in disposable workspaces, and runs only on the two development
repositories. It applies the closed rule repository-wide (never only to gold),
looks up existing declaration signals, inserts already resolved test-only
`imports` edges, and reruns the unchanged pipeline. Using actual resolved
signal kinds isolates headroom from R1 plumbing.

For every residual it records one terminal state: not representable, no exact
signal, ambiguous signal, resolved-not-traversed, acquired-below-ranking,
ranked-not-selected, selected-wrong-chunk, or selected-exact-declaration-chunk.
The old `relation_slot` credit rule is forbidden.

Development corpora remain RedInk at
`4d48722344594cf00e0498f0e1ed3df9cd4fd6be` and daily_stock_analysis at
`487e49e565ffd1b96a7cf4d855f99cee3c981eaa`, with the existing frozen P8
inventories and gold.

Before implementation, an independent reviewer must select and seal one public
Python held-out corpus: URL, exact commit, license/provenance, include/content
hashes, queries, roles, gold, and baseline headroom. The implementation team
receives only its identity/hash contract and denominator; the hidden query/gold
payload and outcomes are opened only in final acceptance. This draft claims no
held-out result.

## Profiles and Gates

Primary causal evidence uses hash embeddings, planner off, fresh indexes, and
two separate-process captures per side. Canonical projections must be
byte-identical after timing/implementation removal. Online evidence cannot
rescue a failed hash oracle or candidate.

After the hash gate passes, confirmatory safety uses the P14-approved online identity:
`openai-compatible/Pro/BAAI/bge-m3`, 1024 dimensions,
`https://api.siliconflow.cn/v1`, planner off. Freeze pacing and batching before
capture. Two captures per side must match on the predeclared stable projection:
selected membership/order, required ranks, protected winners, graph-key
presence, relation/target identities, structure, and request counts. Continuous
scores and timing alone are masked. No owner waiver replaces an automatic gate.

Fixed gates are:

1. oracle precedes product code and uses no gold-derived predicate;
2. zero baseline-required Top-12 loss in every corpus/provider;
3. per-repository and combined Recall@12 non-decreasing;
4. aggregate noise ratio non-increasing and no case gains a noise path;
5. every gain has an exact relation/target/chunk witness;
6. protected winners, P7 continuity, module edges, and non-Python projections
   remain stable;
7. repeat and input-order determinism pass;
8. daily index regression is at most P8's `25%` bound; query regression is at
   most `10%` when absolute increase is at least `5 ms`;
9. embedding request counts and retrieval-call counts are unchanged; existing
   graph caps hold;
10. focused lifecycle/resolution/retrieval, protected P2-P7/P14, P6, raw CI,
    and full suites pass;
11. tracked artifacts contain no absolute local path, source body, secret, or
    raw exception text.

R2 is frozen by the 2026-07-31 review as this efficacy floor: the development
oracle improves combined micro required Recall@12 by at least
`0.05`, gains at least three required items across three cases with selected
exact-symbol witnesses in both development repositories, and has zero required
loss/noise growth. Production must recover every oracle-credited gain; the
sealed held-out must gain at least two items across two cases, also with zero
loss/noise growth. Before capture, the independent reviewer must freeze at
least 12 held-out required items across at least four cases. These values may
not change after review or in response to oracle/candidate output.

## Compatibility and Privacy

P15 executes no project code, runtime import, package config, or environment
lookup. It reads only scanner-approved bytes and active same-index graph rows.
Public query, trace, ContextPack, exploration, CLI, and MCP schemas stay
unchanged. Non-eligible deterministic queries preserve membership, order,
score parts, and reasons byte-for-byte.

Expected product files are `python_graph.py`, `graph_resolution.py`, `sqlite_store.py`, and `graph_lifecycle.py`. `graph_contract.py`, relation policy, expansion, ranking, selection, query, planner, and public schemas should remain unchanged; needing one of them is a redesign stop.

## Risks and Open Decisions

- Different module/symbol chunks may leave the old winner: the oracle gates on
  exact target-chunk outcomes.
- Same-name declarations may look unique by kind: R1 queries both kinds
  together and fails ambiguous.
- Re-exports may look local: require exact target-file ownership.
- New facts may be absent from ready indexes: producer v2 forces refresh.
- Gold may shape the mechanism: freeze inputs and apply the rule repository-wide.
- Familiar corpora may overstate value: require a sealed independent held-out.
- Constant pressure may expand scope: keep `analysis_metadata.py` as a named
  non-goal residual.

R1's resolver encoding and R2's numeric rules are frozen by this review. Task 0
must still seal the concrete held-out identity, denominator, hidden gold, and
manifest hashes before any oracle output; none may change afterward.

## Acceptance Summary

P15 is accepted only if R1/R2 are frozen, the product-free oracle passes, the
implementation retains every module edge and adds only the closed exact-symbol
edge, production realizes oracle headroom with zero loss/noise growth, held-out
and online automatic gates pass, lifecycle/determinism/performance/privacy and
all protected suites pass, and independent Standards + Spec review has no
blocking finding. Otherwise stop without calls, assignments, weights, quotas,
planner changes, or budget expansion.

Document review is complete. Implementation remains unauthorized until the
user explicitly approves Task 0, and product work remains gated on `proceed`.
