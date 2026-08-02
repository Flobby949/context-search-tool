# P15 Minimal Retrieval Benchmark Query Manifest (DRAFT)

Status: **DRAFT**

User approval required: **yes**

Benchmark calls: **0**

This document accompanies `tests/fixtures/p15_minimal_retrieval_benchmark/query-manifest.draft.json`. It is a source-corpus preparation artifact only; it is not approved or execution-eligible.

## Fixed source corpus

- `anyio` at `003e5d6bc3eba8f4e75bf2b2b5fb3f7dd11e6330`
- `multidict` at `41c1b9144b13dcdfa4c18085aedc874cc9d24006`

Both public repositories were checked out independently at detached, clean commits and made read-only before question preparation. No repository substitution was needed.

## Selection and ordering

Candidates came from a stdlib-AST inventory of local import edges and actual loaded-name references, followed by direct reading of the source and target files. No retrieval system, online model, local model, Ollama, or benchmark call assisted selection.

The mechanical candidate key was repository order (`anyio`, then `multidict`), POSIX source path, import line, reference line, and POSIX gold path. Selection then rejected name-only questions, ambiguous resolutions, repeated question patterns, and any query literal containing a gold path/module or imported symbol. Natural source-behavior questions took priority over blindly taking the first six AST edges. The final manifest preserves repository order and assigns contiguous ordinals; it contains six questions per repository, covers six `anyio` source files and four `multidict` source files, and gives exactly one repository-relative gold file per question. The revised `multidict` set has five distinct gold files, no gold used more than twice, and five behavior, failure, or runtime/type-flow questions alongside one definition-oriented question.

## Approval gate

The manifest remains `DRAFT`, has `user_approval_required: true`, `execution_eligible: false`, and records `benchmark_calls: 0`. It must be reviewed and explicitly approved before any benchmark or model execution. Minor wording corrections should preserve the recorded source/import/reference/gold evidence and the no-leakage constraint.
