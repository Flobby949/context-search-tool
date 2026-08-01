# P15-v2 Python Exact Imported-Symbol Relations Design

Date: 2026-08-01

Status: Review candidate. Two independent replacement-efficacy development
seals and released-payload digests are hash-bound. Capture remains blocked on
independent plan review and final harness closure. This document does not
authorize held-out opening, online requests, or product changes.

## Decision

P15-v1 ended at the product-free Task-0 hash gate with a frozen `reject`.
P15-v2 is a separate replan. It keeps the reviewed product hypothesis and all
product-policy constraints, but replaces the development efficacy roster before
any new outcome is observed.

For an eligible Python statement of the form
`from module import Name as LocalName`, retain the existing P8 module import
relation and add one exact relation to the one existing top-level Python
`type` or `function` declaration signal for `Name` in the exact resolved target
file and project unit.

The added relation continues to reuse:

- relation kind `imports`;
- relation weight `0.85`;
- graph decay `0.8`;
- score key `graph_imports_match`;
- reason `static module dependency`;
- outgoing-only traversal;
- current ranking, evidence merge, and P7 path-diverse selection;
- all existing graph and retrieval budgets.

There is no ranking, boost, weight, quota, planner, query, or budget change in
P15-v2.

## Separation from P15-v1

The immutable P15-v1 attempt is indexed at
`.quality/p15-runs/p15-v1-attempt-003/reject-index.json`. Its hash oracle was
deterministic but produced no new required item and no exact rank gain. It has
no proceed marker, online capture, held-out opening, or product diff.

P15-v2 must not:

- overwrite, reinterpret, or reuse a P15-v1 capture as v2 evidence;
- edit the P15-v1 manifest, harness, fixtures, or reject index in place;
- change gold, thresholds, credit, TopK, weights, ranking, or budgets in
  response to the P15-v1 output;
- treat Daily or RedInk as fresh efficacy evidence.

All v2 evidence starts under a new attempt root after the replacement seals and
plan review pass.

## Frozen Product Contract

### Producer

`PythonImportFact` retains the imported name and local alias for each named
`ast.ImportFrom` alias. Wildcards, dynamic imports, re-export inference,
runtime import execution, package execution, and environment-dependent
`sys.path` behavior remain out of scope.

The existing source signal remains the Python `core_module` signal. The
existing module relation remains unchanged. Exact-symbol facts have an
independent deterministic per-source cap of `256`; applying that cap may not
remove or orphan the retained module relation.

### R1 union target selector

The unresolved exact-symbol relation uses:

```text
kind = imports
producer = python_ast
target_kind = python_declaration
target_qualified_name = <canonical target module>.<imported name>
target_signature = ""
target_arity = null
target_project_unit_key = <source project unit>
metadata.resolution_basis = exact_python_imported_symbol
metadata.selector_state = exact
metadata.target_file_path = <the one P8 module target path>
metadata.target_signal_kinds = [type, function]
```

Resolution accepts exactly one active row across the union of `type` and
`function` where producer is `python_ast`, language is Python, file path,
project unit, and qualified name all match exactly. Zero rows remain
unresolved; two rows are ambiguous. There is no case inference, wildcarding,
first-row selection, cross-file fallback, or producer fallback.

Integrity permits `target_kind=python_declaration` only for this closed
producer/relation/basis combination and only when the resolved target is an
allowed `type` or `function`. Generic relation integrity remains unchanged.

### Lifecycle and bounded reads

The exact relation participates in the existing graph lifecycle and stale-row
cleanup. Lifecycle metadata version parsing remains canonical: decimal digits
only, with no sign, leading zero, or surrounding whitespace.

The current outgoing and incoming `64`-edge read caps do not change. Ordering
must keep the existing resolved Python module edge before exact-symbol siblings
from the same source, and behavior under a hot incoming declaration must be
deterministic. No cap is raised.

`TARGET_GRAPH_PRODUCER_VERSION` changes from `1` to `2`; SQLite/graph schema
stays at `5`. Missing, `0`, and ready producer-v1 metadata become stale with
`producer_contract_changed` and require exactly one authoritative rebuild.
Producer version `2` is current. Malformed, negative, non-canonical, or future
values fail closed; canonical parsing accepts decimal digits only and rejects a
sign, leading zero, or surrounding whitespace. Authoritative refresh reparses
active files, resolves ordinary relations and test associations, and publishes
ready-v2 atomically. The next unchanged refresh parses zero files. Because P15
adds no chunk, symbol, or lexical token, rebuild and no-op reuse existing vector
rows and embedding IDs. Change/revert and delete/restore converge without a
schema migration.

## Evidence Roster

### Protected characterization only

The existing frozen P8 Daily and RedInk sources, queries, gold, roles, and
fixtures remain byte-for-byte unchanged. They are retained only as protected
characterization/regression corpora:

- no required loss;
- no closed-world noise growth;
- protected winners stable;
- module and non-Python projections stable;
- no unapproved membership drift;
- no local-model, fallback, integrity, or work-cap regression.

They contribute no item, case, repository, or denominator to v2 efficacy
credit.

### Replacement efficacy development

Two public Python repositories must be selected and sealed independently before
any v2 oracle capture. The implementation team does not choose them after
viewing retrieval outcomes. Each seal must freeze:

- URL, commit, tree, license, include/exclude rules;
- selected inventory, inventory SHA-256, and content SHA-256;
- repository role `efficacy_development`;
- exact queries, TopK `12`, required/contextual paths, necessity, protected
  winners, and the closed-world noise rule;
- a public contract, sealed payload digest, reviewer identity, timestamp, and
  proof that sealing preceded v2 capture and product changes.

Both replacement seals and their release/open protocol must pass independent
review before the v2 manifest can become capture-ready.

The independently selected roster is now bound as follows:

| slot | repository | commit | public contract SHA-256 | released development payload SHA-256 |
| --- | --- | --- | --- | --- |
| A | Starlette | `5174d4c8358a6f06aa8056bafd14c2272dab8dd1` | `d230a78f86ab1225305e454b83a674e391faec5c4c024ee89c050fb6eefc35d8` | `309388945b12fb9becc15e2d037d85bfc7f09299f469dde5d8d5a8642fcd6182` |
| B | Requests | `414f0513c33883adf6f2b46901d4f0b38a455851` | `19a116a434debaba3dde6dfbeb3848d5a298477f79280be06d0c982c1a2ede51` | `cfa75bd1cf2cba1b4456fbf590c02fe85fd418d0e1e1c4032e880c569fd7f1ee` |

The roster contract SHA-256 is
`27ad5f2b6abb2f9d11c202877bb56f3e76cbcaaa5d58e1059b79fdffb1446823`.
The reviewer seal-hashes manifest SHA-256 is
`17e069d90f66899d0dab7b433b91b40620a55bcc92df881d1e038aa55cc78b1f`.
Each replacement freezes four cases and twelve required items at TopK `12`.
The reviewer recorded no pre-seal oracle execution, no post-oracle gold edit,
no Click access, and no Ollama use. Released development payload hashes match
the contracts' sealed plaintext digests; this permits schema validation but
does not authorize capture before plan review.

### Held-out

The existing independent Click contract is carried forward unchanged:

- repository `pallets/click`;
- commit `00e592cea702e0b2caa0dee42489fdb1c22cd845`;
- four cases, twelve required items, TopK `12`;
- public-contract SHA-256
  `a0b881dee27fdc05155139a97d398f22f5a14bb2fb33fc492fb512565753e582`;
- ciphertext SHA-256
  `329226be63911c8f7fddd0b6ff9ec6b9a5cd5c2217b3c482964fceab9329d979`;
- plaintext digest
  `cbe4efbcd88a41f61d643a9200d6acc817fcc4784eaecd575f869a7650b61217`.

The Click payload remains unopened until a v2 candidate is frozen and every
pre-open gate passes. Carry-forward itself requires independent plan review;
no v1 held-out outcome exists to reuse.

## Frozen Acceptance

The numeric R2 floor and credit rule do not change. On the two replacement
efficacy development repositories, the product-free hash oracle must:

- improve combined micro required Recall@12 by at least `0.05` absolute;
- select at least `3` new required items across at least `3` distinct cases;
- produce at least one exact-symbol-credited gain in each replacement efficacy
  repository;
- lose no previously selected required item;
- increase no per-case closed-world noise;
- preserve protected winners and unapproved memberships;
- pass canonical/reversed and two-process deterministic projections.

A newly selected item receives causal credit only when all links close:

1. an independently frozen named `ImportFrom` source fact identifies the
   importer, module, imported name, alias, and source location;
2. the one pre-existing `python_ast` `resolved_exact` module relation remains
   present and identifies the same exact target file/unit;
3. the added exact-symbol relation is derived from that fact and references the
   preserved module-relation ID;
4. one and only one active Python `python_ast` `type`/`function` signal matches
   the exact target file, unit, and qualified name;
5. persisted relation resolution is `resolved_exact` and its target signal ID
   is that unique declaration signal;
6. the gained result's primary chunk equals the target signal's active chunk;
7. the gained result contains `graph_imports_match` and reason
   `static module dependency`, with resolved-relation provenance;
8. the required path was outside baseline TopK `12` and is inside oracle or
   candidate TopK `12`, with no unrelated query/policy/gold difference.

Missing any link gives no causal credit. The P8 `relation_slot` rule remains
forbidden.

The final candidate must recover every credited development gain and gain at
least `2` held-out required items across `2` held-out cases. Daily index
regression remains at most `25%`; query regression remains at most `10%` when
the absolute increase is at least `5 ms`. Existing work caps and budgets may
not increase.

## Online Safety

Hash evidence is primary and must proceed before any online request. Online
confirmation keeps the P14 identity unchanged:

```text
provider: openai-compatible
model: Pro/BAAI/bge-m3
dimensions: 1024
base_url: https://api.siliconflow.cn/v1
planner: disabled
tokens/minute: 240000
tokens/request: 80000
minimum interval: 2 seconds
batching: p14-bounded-greedy-v1
```

Ollama and every other local model are forbidden and fail closed. Online
evidence cannot rescue a failed hash gate.

## Allowed Product Surface

If and only if the v2 Task-0 oracle passes, implementation remains limited to:

- `src/context_search_tool/python_graph.py`;
- `src/context_search_tool/graph_resolution.py`;
- `src/context_search_tool/sqlite_store.py`;
- `src/context_search_tool/graph_lifecycle.py`.

Needing ranking, relation policy, expansion, selection, query, planner, public
schema, or budget changes is a redesign stop.

## Current Blocking Conditions

No v2 capture or product work is authorized until all are true:

1. two independent replacement efficacy development seals exist and validate;
2. an independent reviewer approves this design and the companion plan;
3. the v2 manifest is closed with real identities and hashes, with no pending
   placeholders;
4. the v2 harness negative tests and zero-evidence preflight pass;
5. Click remains sealed and unopened;
6. `src/context_search_tool` remains clean against the behavior baseline.

Condition 1 is satisfied by the bound Starlette and Requests contracts above.
The remaining conditions stay blocking.
