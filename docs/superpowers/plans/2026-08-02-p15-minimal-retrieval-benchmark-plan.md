# P15 Minimal Retrieval Benchmark Plan (DRAFT)

Status: **DRAFT — user approval required; do not execute before approval.**

## Objective and fixed inputs

Compare three retrieval arms under the same fixed questions and `TopK=12`:

1. baseline: P15 feature off;
2. P15: feature on;
3. fast-context.

The source corpus is fixed to:

- `anyio@003e5d6bc3eba8f4e75bf2b2b5fb3f7dd11e6330`
- `multidict@41c1b9144b13dcdfa4c18085aedc874cc9d24006`

The 12 fixed questions and gold files come from the [query manifest](../../../tests/fixtures/p15_minimal_retrieval_benchmark/query-manifest.draft.json); its preparation and evidence are documented in the [query-manifest note](2026-08-02-p15-minimal-retrieval-benchmark-query-manifest.md). Repository, commit, query literal, gold file, model, and `TopK` are immutable during an attempt.

## Execution protocol

For each query, make exactly one online Qwen planner call and one BGE query-embedding call. Save their outputs with the common base retrieval state, then run two local replays from that identical state: baseline with the feature off and P15 with it on. This prevents planner, embedding, or base-state variation between the two local arms.

Run fast-context once per query against the matching fixed checkout with exactly:

```text
max_results=12
tree_depth=3
max_turns=3
include_snippets=false
```

Only its primary ranked file results count. Do not execute or incorporate grep suggestions. For all three arms, normalize results to unique repository-relative POSIX file paths, preserve first-ranked occurrence, and score only the first 12 unique paths.

Exact external/local call budget for 12 queries:

| Operation | Calls |
|---|---:|
| Online Qwen planner | 12 |
| BGE query embedding | 12 |
| fast-context MCP | 12 |
| Local replay: baseline + P15 | 24 |

MCP-internal backend calls are opaque and are not expanded into this budget. Ollama calls are `0`; retries are `0`.

## Metrics and acceptance

Report hits, `Recall@12`, and `MRR@12` overall and per repository. Record latency in three separate columns: baseline local replay, P15 local replay, and fast-context end-to-end. The fast-context end-to-end latency is descriptive only and must not be treated as a hard performance comparison with local replay latency.

The attempt passes only if all conditions hold:

- P15 total hits are at least baseline total hits plus 2.
- P15 loses zero baseline hits: every query hit by baseline is also hit by P15.
- P15 `MRR@12` is not lower than baseline `MRR@12`.
- P15 `Recall@12` is at least fast-context `Recall@12`.
- Across the 12 paired local replays, P15 median latency overhead versus baseline is at most 10%, or its absolute median increase is at most 5 ms.

## Result record

Ranks are `1..12`; use `—` for a miss. Latencies are milliseconds.

| Query | Repo | Baseline rank | P15 rank | fast-context rank | Baseline local ms | P15 local ms | fast-context E2E ms |
|---|---|---:|---:|---:|---:|---:|---:|
| anyio-q01 | anyio | TBD | TBD | TBD | TBD | TBD | TBD |
| anyio-q02 | anyio | TBD | TBD | TBD | TBD | TBD | TBD |
| anyio-q03 | anyio | TBD | TBD | TBD | TBD | TBD | TBD |
| anyio-q04 | anyio | TBD | TBD | TBD | TBD | TBD | TBD |
| anyio-q05 | anyio | TBD | TBD | TBD | TBD | TBD | TBD |
| anyio-q06 | anyio | TBD | TBD | TBD | TBD | TBD | TBD |
| multidict-q01 | multidict | TBD | TBD | TBD | TBD | TBD | TBD |
| multidict-q02 | multidict | TBD | TBD | TBD | TBD | TBD | TBD |
| multidict-q03 | multidict | TBD | TBD | TBD | TBD | TBD | TBD |
| multidict-q04 | multidict | TBD | TBD | TBD | TBD | TBD | TBD |
| multidict-q05 | multidict | TBD | TBD | TBD | TBD | TBD | TBD |
| multidict-q06 | multidict | TBD | TBD | TBD | TBD | TBD | TBD |

## Failure and iteration rules

Any external planner, embedding, or fast-context failure makes the attempt `INCOMPLETE`; do not retry, replace a query, or substitute a repository. If execution completes but the acceptance criteria fail, change only the P15 implementation and rerun the same manifest. Do not change repository, query, gold, model, `TopK`, or evaluation rules.

The previous 130-query catalog/reference/held-out structure and its multiple gates are explicitly retired from this benchmark. They must not be loaded, sampled, scored, or used as fallback acceptance gates.
