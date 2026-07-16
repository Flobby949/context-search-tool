# P3.1 RetrievalTrace v1 Design

Date: 2026-07-16
Status: Approved; written review complete; implementation verified
Implementation plan: `docs/superpowers/plans/2026-07-16-p3-1-retrieval-trace-v1.md`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Successor: a separate P3.2 retrieval-core decomposition design

## Summary

P3.1 adds a versioned, bounded, agent-readable `RetrievalTrace` without changing
the result of an ordinary query. A new `cst trace` command and
`context_search_trace` MCP operation execute the existing retrieval pipeline
once and expose:

- query variants and planner outcome;
- raw candidate counts by source;
- ordered snapshots for each retrieval stage;
- candidate provenance and semantic-variant attribution;
- rank movement and non-zero rerank adjustments;
- final result and evidence-anchor selection reasons;
- bounded stage and total timings.

The trace is an explicitly requested diagnostic response. It contains no source
content, is never persisted automatically, and is never copied into MCP feedback
logs. The existing `query` and `context` surfaces remain byte-for-byte compatible
for deterministic inputs.

P3.1 establishes observable stage boundaries but does not move the 4,249-line
`retrieval.py` implementation. P3.2 will use the protected trace contract and
parity tests to split the retrieval core in a separate design and plan.

## Baseline And Roadmap Reconciliation

The design was prepared from `be03fa73437cd897d112377d80dda5c83370def5`.
Fresh verification on 2026-07-16 produced:

- full suite: 1,832 passed and 9 skipped;
- P2/P2.1 focused deterministic suite: 1,278 passed and 6 skipped;
- `p2_context_pack`: selected/executed/passed 5/5/5;
- raw `ci`: selected/executed/passed 8/8/8;
- current pinned real-project P2 report: selected/executed/passed 4/4/4.

Phase 2 therefore satisfies its own implementation and acceptance criteria. Its
roadmap status should be recorded as complete independently of Phase 1.

Phase 1 remains a separate open acceptance item. Fresh vector and hybrid model
runs both selected and executed seven required cases but passed 6/7. The
`audit-status-literal` case still misses
`src/main/java/com/example/audit/AuditStatus.java` within Top-3, and the focused
pair gate fails. P3.1 must not mark Phase 1 complete or weaken that gate.

Proceeding with P3.1 is safe because it is additive and behavior-preserving. It
does not claim that the Phase 1 ranking gap is fixed, change ranking policy, or
make controlled exploration depend on unaccepted model output.

## Motivation

CST currently exposes detailed final `score_parts`, reasons, planner metadata,
and query variants, but those fields describe only surviving output. They do not
answer several questions needed for reliable retrieval work:

- How many candidates did semantic, lexical, path/symbol, direct-text, signal,
  planner, anchor, and relation sources contribute?
- Which candidate was visible at each merge and ranking stage?
- Did a result enter through the original query, a planner rewrite, a relation,
  or more than one source?
- Which boost, penalty, ceiling, or cohort adjustment changed its order?
- Was an expanded item omitted because of the code-result limit, anchor limit,
  duplicate-anchor suppression, or overlap merging?
- Which stage is responsible for a quality regression or a latency increase?

The lack of this information also makes structural refactoring risky. A final
result snapshot can prove that output stayed equal, but it cannot prove that a
new module preserved source contribution, expansion, or intermediate ordering.
P3.1 makes those stages observable before P3.2 changes their physical location.

## Goals

1. Define one exact, versioned `RetrievalTrace` schema.
2. Add independent CLI and MCP diagnostic operations.
3. Record all existing retrieval stages in deterministic order.
4. Expose raw source counts before candidate merging.
5. Explain final selection through provenance, rank history, adjustments, and
   selection reasons.
6. Bound structural amplification with fixed preview limits.
7. Preserve ordinary query and ContextPack behavior exactly.
8. Keep trace collection request-local and out of feedback persistence.
9. Create stable stage seams that P3.2 can implement as modules without changing
   the public trace contract.

## Non-Goals

P3.1 does not:

- change candidate scores, ranking rules, thresholds, or final limits;
- fix the open Phase 1 `audit-status-literal` acceptance failure;
- execute ContextPack `next_queries`;
- add controlled multi-round retrieval;
- add call-graph, import-graph, or type-resolution features;
- move candidate collection, expansion, ranking, or formatting functions out of
  `retrieval.py`;
- add a trace database, trace history, trace identifier, or background exporter;
- add trace configuration to `.context-search/config.toml`;
- add a generic free-form event log;
- add a new quality-runner case mode.

## Approaches Considered

### Selected: Typed Stage Snapshots With Bounded Details

Each stage emits one typed snapshot containing counts, duration, source counts,
and a small ordered candidate preview. Final selections carry richer typed
provenance and rank information. This produces a stable contract for CLI, MCP,
tests, and P3.2 while keeping payload growth bounded.

### Rejected: Reconstruct Trace From Final Results

Deriving diagnostics only from `QueryBundle`, `score_parts`, and final results
would require little instrumentation, but it cannot recover rejected candidates,
raw source counts, intermediate ordering, or selection-limit decisions. It would
be an explanation formatter rather than a retrieval trace.

### Rejected: Generic Event Stream

A free-form list of name/value events is easy to extend, but it transfers schema
interpretation to every consumer. Event names and payload shapes would drift,
quality tests would become weak, and P3.2 could appear compatible while emitting
meaningfully different diagnostics.

## Design Principles

### Trace Is Additive

Trace collection is enabled only by `trace_repository()`. Existing callers use
`query_repository()` with no collector and receive the same `QueryBundle`.
Existing JSON, Markdown, MCP query, ContextPack, and feedback contracts do not
gain trace fields.

### Behavior Before Observability

Instrumentation observes already computed values. It does not reorder
collections, introduce new score calculations, change sort keys, or use trace
state as retrieval input.

### Typed And Versioned

Public payloads are built from frozen dataclasses and explicit serializers.
There is no arbitrary `details: dict[str, object]` escape hatch. New meanings
require an additive schema field or a new schema version.

### Bounded By Construction

The trace records every stage count but previews at most five candidates per
stage, twenty final selections, and twenty-four adjustments per selection.
Stage truncation remains visible through uncapped output and unique-output
counts; final-selection and adjustment previews report explicit omitted counts.

### Explicitly Requested Data

A trace response may contain the original query, planner rewrite text, and
repository-relative file paths because the caller explicitly requested it. The
same data must not be persisted implicitly.

## Architecture

The new package has three responsibilities:

```text
src/context_search_tool/retrieval_trace/
  models.py         immutable trace contract and fixed limits
  collector.py      stage ordering, timing, bounds, and rank history
  serialization.py exact schema-v1 payload conversion
  __init__.py       supported public exports
```

`retrieval.py` remains the execution owner during P3.1. It gains:

- `TracedQueryBundle`, pairing the unchanged `QueryBundle` with a trace;
- `trace_repository()`, the only function that creates a collector;
- an optional keyword-only collector parameter on `query_repository()`;
- small conversion helpers that turn existing candidates, ranked chunks, and
  expanded results into trace observations;
- stage start/finish calls around existing operations.

The dependency direction is one-way:

```text
retrieval.py -> retrieval_trace models/collector
formatters.py -> retrieval_trace serialization
cli.py and mcp_tools.py -> retrieval.trace_repository + shared formatters
retrieval_trace package -/-> retrieval.py
```

This avoids a package cycle and lets P3.2 move the orchestration code while
keeping the trace package stable.

## Public Operations

### CLI

The new command mirrors query execution options:

```bash
cst trace /path/to/repo "owner registration validation" --json
cst trace /path/to/repo "数据看板统计图表功能" --planner
```

Arguments and options:

- the same `repo_or_question` and optional `question` resolution as `cst query`;
- `--json` for the exact JSON envelope; Markdown remains the default;
- `--context-lines` and `--full-file`, because context expansion is a traced
  stage and must use the same inputs as the equivalent query;
- `--planner` and `--no-planner`, with the existing mutual-exclusion behavior.

P3.1 does not add CLI knobs for stage preview limits. Fixed limits are part of
schema v1 and appear in the payload.

### MCP

The new tool is:

```text
context_search_trace(repo, query, context_lines, full_file, final_top_k)
```

The arguments match `context_search_query`. `final_top_k` changes retrieval in
the same way as the existing MCP query tool, but the trace still previews at
most twenty final selections.

The tool performs one retrieval pass. It does not call `context_search_query`
and does not execute a second pass to construct the trace.

### Shared Success Envelope

CLI JSON and MCP success return the same keys:

```json
{
  "ok": true,
  "repo": "/absolute/path/to/repo",
  "query": "owner registration validation",
  "trace": {}
}
```

The `trace` object is defined below. Raw source content and the full raw result
payload are intentionally absent; final selections include paths, spans, scores,
and explanations sufficient for diagnostics.

## RetrievalTrace Schema v1

The exact top-level trace keys, in serialization order, are:

```json
{
  "schema_version": 1,
  "outcome": "complete",
  "termination_reason": "completed",
  "duration_ms": 21,
  "limits": {
    "max_stages": 16,
    "stage_top_k": 5,
    "final_selection_top_k": 20,
    "adjustment_top_k": 24
  },
  "query": {
    "original_token_count": 3,
    "expanded_token_count": 3,
    "variant_retrieval_status": "original_only",
    "variants": [
      {
        "variant_id": "original",
        "text": "owner registration validation",
        "source": "original"
      }
    ],
    "planner": {
      "status": "disabled",
      "provider": "",
      "model": "",
      "intent": "unknown",
      "latency_ms": null,
      "discarded_hint_count": 0
    }
  },
  "source_counts": {
    "semantic": 12,
    "planner_semantic": 0,
    "lexical": 8,
    "path_symbol": 4,
    "direct_text": 2,
    "signal": 3,
    "planner_lexical": 0,
    "planner_path_symbol": 0,
    "planner_signal": 0,
    "anchor_expansion": 1,
    "relation": 5
  },
  "stages": [],
  "final_selection_count": 6,
  "final_selection_omitted_count": 0,
  "final_selections": []
}
```

Legal `outcome` values are:

- `complete`: the existing retrieval flow reached final selection;
- `empty`: retrieval returned before ranking because the index or candidates were
  absent;
- `partial`: retrieval returned an empty bundle after a handled store read error.

Legal `termination_reason` values are:

- `completed`;
- `missing_index`;
- `store_read_error`;
- `no_candidates`.

Public CLI and MCP preflight normally convert missing indexes into their existing
surface-specific behavior. The `missing_index` trace outcome remains defined for
direct library use and parity with `query_repository()`'s early return.

## Stage Contract

A stage has exactly these keys:

```json
{
  "name": "semantic_recall",
  "input_count": 1,
  "output_count": 12,
  "unique_output_count": 12,
  "duration_ms": 4,
  "source_counts": {
    "semantic": 12,
    "planner_semantic": 0
  },
  "decision_counts": {},
  "top_candidates": []
}
```

Counts describe the stage before preview truncation. `output_count` includes
duplicates when the operation naturally emits them; `unique_output_count` is by
chunk ID, or by expanded-result identity after context expansion.

A candidate preview has exactly these keys:

```json
{
  "rank": 1,
  "chunk_id": "37ee82f4:function:18:5406409b",
  "file_path": "src/example/OwnerController.java",
  "start_line": 18,
  "end_line": 42,
  "score": 0.91,
  "sources": ["semantic", "direct_text"],
  "variant_ids": ["original"]
}
```

Candidate order is the actual order used or returned by that stage. Trace code
must not sort a live retrieval collection merely to make the trace attractive.
When an operation returns an unordered mapping, the trace uses the same explicit
sort key already used by the following retrieval stage.

### Canonical Stage Order

| position | stage | input/output meaning |
| ---: | --- | --- |
| 1 | `query_understanding` | original tokens to expanded tokens and variants |
| 2 | `semantic_recall` | query variants to vector matches |
| 3 | `lexical_recall` | original tokens to FTS candidates |
| 4 | `path_symbol_recall` | original tokens to path/symbol candidates |
| 5 | `direct_text_recall` | direct probes to raw-text candidates |
| 6 | `signal_recall` | original tokens to code-signal candidates |
| 7 | `planner_hint_recall` | planner-only tokens to lexical/path/signal candidates |
| 8 | `direct_merge` | raw direct candidates to unique direct candidates |
| 9 | `anchor_expansion` | direct candidates to evidence-anchor expansions |
| 10 | `relation_expansion` | direct and anchor seeds to related candidates |
| 11 | `candidate_merge` | all candidate sources to one candidate per chunk |
| 12 | `ranking` | merged candidates to ranked chunks |
| 13 | `cohort_rerank` | ranked chunks to frontend-cohort-adjusted order |
| 14 | `context_expansion` | ranked chunks to expanded and overlap-merged results |
| 15 | `final_selection` | expanded results to code results and evidence anchors |

A zero-result stage is still recorded when execution reaches it. Stages after an
early return are absent; `termination_reason` explains why.

The collector rejects duplicate, unknown, or out-of-order stage names. This
turns the stage sequence into a protected P3.2 interface instead of an informal
logging convention.

## Source Counts

Top-level source counts are captured before merging and use a fixed key order:

1. `semantic`
2. `planner_semantic`
3. `lexical`
4. `path_symbol`
5. `direct_text`
6. `signal`
7. `planner_lexical`
8. `planner_path_symbol`
9. `planner_signal`
10. `anchor_expansion`
11. `relation`

Counts are raw contributions, so the same chunk may contribute to more than one
source. `direct_merge` and `candidate_merge` show the corresponding unique
counts. This distinction is required to diagnose source overlap.

## Final Selection Contract

A final selection has exactly these fields:

```json
{
  "rank": 1,
  "selection_kind": "result",
  "selection_reason": "selected_within_result_limit",
  "file_path": "src/example/OwnerController.java",
  "start_line": 18,
  "end_line": 62,
  "score": 1.42,
  "origin_chunk_ids": ["37ee82f4:function:18:5406409b"],
  "sources": ["semantic", "direct_text", "signal"],
  "variant_ids": ["original"],
  "rank_history": [
    {"stage": "ranking", "rank": 2, "score": 1.31},
    {"stage": "cohort_rerank", "rank": 1, "score": 1.42},
    {"stage": "context_expansion", "rank": 1, "score": 1.42},
    {"stage": "final_selection", "rank": 1, "score": 1.42}
  ],
  "adjustments": [
    {"name": "frontend_import_support_boost", "value": 0.3},
    {"name": "role_boost", "value": 0.2}
  ],
  "adjustment_omitted_count": 0,
  "reasons": ["semantic match", "direct text match", "business role boost"]
}
```

`selection_kind` is `result` or `evidence_anchor`. Legal reasons are:

- `selected_within_result_limit`;
- `selected_within_anchor_limit`.

The `final_selection` stage additionally records decision counts for:

- `selected_result`;
- `selected_anchor`;
- `duplicate_anchor`;
- `result_limit`;
- `anchor_limit`.

Overlap merging is represented by multiple `origin_chunk_ids` on the resulting
selection and by the `context_expansion` input/unique-output count delta. It is
not mislabeled as a final-selection drop.

### Provenance

`sources` is a canonical deduplicated union across all origin chunks. It derives
from existing candidate sources and score-part families; trace collection does
not infer provenance from display reasons. `variant_ids` comes from existing
`SemanticMatch` records and retains original-before-planner ordering.

### Rank History

The collector retains rank/score positions for all candidates internally at the
three rank-bearing stages, then serializes history only for previewed final
selections. For an overlap-merged result, each stage uses the best rank among its
origin chunks and the score at that rank. Every final selection contains exactly
`ranking`, `cohort_rerank`, `context_expansion`, and `final_selection` history in
that order.

### Adjustments

Adjustments are non-zero score parts whose existing names end in `_boost`,
`_penalty`, or `_match`, plus a synthetic `planner_ceiling_clamp` equal to the
final minus pre-ceiling rerank score. They are ordered by descending absolute
value and then name, capped at twenty-four. This is a diagnostic factor list, not
an additive reconciliation of the final score: existing scorer branches that do
not materialize a named score part remain visible through rank-history score
movement. P3.1 does not rewrite ranking policy merely to manufacture a ledger.

## Timing

The collector uses `time.perf_counter_ns()` and serializes non-negative integer
milliseconds. An injectable monotonic clock makes unit tests deterministic.

Stage timings measure only the existing operation wrapped by that stage. Trace
observation conversion happens after the stage timer stops so formatting
overhead is not misreported as retrieval latency. `duration_ms` covers the whole
traced retrieval request, including observation conversion.

No acceptance test uses a wall-clock percentage threshold. Performance safety is
proved structurally: an ordinary query creates no collector, captures no clock,
and does not build candidate observations.

## Bounds And Invariants

Schema v1 has these fixed structural limits:

| limit | value | behavior when exceeded |
| --- | ---: | --- |
| stages | 16 | collector rejects an invalid implementation |
| candidate previews per stage | 5 | retain actual first five and full counts |
| final selection previews | 20 | retain first twenty and omitted count |
| adjustments per selection | 24 | retain strongest twenty-four and omitted count |

Additional invariants:

- all counts and timings are non-negative integers;
- all scores and adjustment values are finite floats;
- ranks are positive, contiguous within a preview, and no larger than the full
  stage output count;
- file paths are repository-relative POSIX paths;
- no candidate or selection contains source content;
- source and decision maps use canonical key order;
- JSON serialization uses `allow_nan=False`;
- `final_selection_count` equals the uncapped result-plus-anchor selection count;
- `final_selection_omitted_count` equals count minus serialized preview length;
- a completed trace has a `final_selection` stage;
- ordinary retrieval does not depend on any trace object or field.

The serialized stage and selection structures are bounded independently of the
number of retrieval candidates. Request-local collection still retains a
lightweight rank/score history for candidates that reach rank-bearing stages, so
collector working memory is O(N) within the retrieval engine's existing
candidate limits. Query and repository-relative path strings retain their actual
values, so schema v1 does not claim a fixed global byte ceiling.

## Data Flow

```text
CLI trace / MCP context_search_trace
  -> resolve repository and existing query configuration
  -> trace_repository(...)
       -> create RetrievalTraceCollector
       -> query_repository(..., trace_collector=collector)
            -> run unchanged query understanding and retrieval stages
            -> time each existing operation
            -> record bounded observations after each operation
            -> build the unchanged QueryBundle
       -> collector.finish(...)
       -> TracedQueryBundle(bundle, trace)
  -> shared trace_payload(...)
  -> JSON or Markdown formatting
```

`query_repository()` continues to use its current early returns. When a collector
is present, each early-return branch records the matching outcome before returning
the same `QueryBundle` it returns today.

## Ordinary Query Compatibility

P3.1 uses an optional keyword-only collector argument. `None` is the null
recorder and is the default. The no-trace path:

- does not instantiate `RetrievalTraceCollector`;
- does not read the monotonic clock;
- does not resolve additional chunks for display paths;
- does not allocate stage candidate previews or rank-history maps;
- does not change any sort or merge input;
- returns the same `QueryBundle` type.

A deterministic end-to-end parity test runs the same indexed fixture through
`query_repository()` and `trace_repository().bundle`, then compares the complete
raw query payload. A second parity test builds ContextPack v2 from both bundles
and compares canonical bytes.

## Error And Early-Return Semantics

### Library

Handled early returns produce a valid trace:

| condition | outcome | termination reason |
| --- | --- | --- |
| missing `index.sqlite` | `empty` | `missing_index` |
| handled `deleted_chunk_ids()` SQLite error | `partial` | `store_read_error` |
| merged candidate set empty | `empty` | `no_candidates` |
| final selection reached | `complete` | `completed` |

Existing query/config `ValueError` and `requests.HTTPError` behavior remains
unchanged. Trace-only invariant, collection, and formatting failures use
`RetrievalTraceError`, a dedicated `RuntimeError` subclass, so public adapters
can distinguish them from query failures without inspecting exception text.
Unexpected collector or serialization errors are trace-surface failures; they
never affect ordinary query calls because those calls have no collector.

### CLI

Existing query/config errors use the existing CLI error path. An unexpected trace
assembly or formatting error exits with stable public text `Retrieval trace
failed`; internal exception text is not printed.

### MCP

The MCP tool preserves existing `repo_not_found`, `missing_index`, and
`query_failed` error codes. Unexpected trace assembly or serialization returns:

```json
{
  "ok": false,
  "error": {
    "code": "trace_failed",
    "message": "Retrieval trace failed"
  }
}
```

No error response contains a partial trace.

## Privacy And Persistence

The requested response may contain:

- the original query;
- executed query variant text;
- repository-relative paths and line spans;
- scores, reasons, source names, and timings.

It must not contain:

- source excerpts or `_context_content`;
- prompt text, API keys, environment values, or request headers;
- absolute file paths inside candidate or selection entries;
- internal exception strings on the public MCP surface.

`context_search_trace_tool()` never calls `_try_append_query_feedback()` or
`_append_query_feedback()`. It does not create or modify
`.context-search/mcp_calls.jsonl`. A sentinel test places source, query, and
variant secrets in a trace request, confirms they appear only where explicitly
allowed in the returned payload, and confirms the feedback file is unchanged.

## P3.2 Boundary Contract

P3.2 will receive stable logical boundaries from the stage sequence:

| future responsibility | protected P3.1 stages |
| --- | --- |
| query understanding | `query_understanding` |
| candidate sources | four direct recall stages plus signal and planner hint |
| expansion | direct merge, anchor expansion, relation expansion, candidate merge |
| ranking policy | ranking and cohort rerank |
| result expansion | context expansion |
| selection/explanation | final selection and trace serialization |

P3.2 may move code behind these boundaries but must preserve:

- schema version 1;
- canonical stage names and order;
- source-count semantics;
- deterministic candidate and selection order;
- raw query and ContextPack parity;
- feedback privacy.

If P3.2 needs a materially different stage model, it must define schema version 2
rather than silently changing version 1.

## Testing Strategy

### Contract And Collector Tests

Add focused tests for:

- exact dataclass and serialized key sets;
- canonical source/stage ordering;
- non-negative count and finite-score validation;
- injected-clock stage and total timings;
- stage, candidate, final-selection, and adjustment bounds;
- duplicate/out-of-order stage rejection;
- JSON rejection of NaN and infinity;
- no source-content fields.

### Retrieval Pipeline Tests

Use deterministic indexed fixtures to prove:

- the fifteen stages appear in order on a full retrieval;
- raw source counts precede merge deduplication;
- original and planner semantic variants retain provenance;
- relation and anchor candidates retain their sources;
- ranking and cohort movement produce rank history;
- overlap-merged results retain every origin chunk ID;
- final decision counts distinguish result/anchor limits and duplicates;
- trace and non-trace bundles have identical raw query payloads;
- trace and non-trace bundles build identical ContextPack v2 bytes;
- normal queries do not create observations or read the trace clock;
- all early-return outcomes are exact.

### CLI And MCP Tests

Prove:

- CLI JSON and MCP adapters produce identical envelopes when given the same
  trace object; separate live executions compare equal after normalizing only
  request and stage timing values;
- Markdown includes outcome, source counts, stages, final selections, provenance,
  rank history, and adjustments without source excerpts;
- planner flag resolution matches `query` and `context`;
- MCP tool registration and argument forwarding are exact;
- trace failures return stable public errors with no partial payload;
- the feedback file is never created or modified by a trace call.

### Deterministic P3.1 Acceptance

`tests/test_quality_p3.py` runs representative committed Java, frontend, and
documentation fixtures with offline hash embeddings. It computes
`TraceCoverage` as:

```text
final selections with non-empty sources, rank history, and selection reason
divided by all serialized final selections
```

Acceptance requires `TraceCoverage == 1.0`, complete required stages for every
non-empty case, exact selection counts, and raw-result parity. This focused test
does not add a new quality catalog mode.

### Regression Verification

Required final commands include:

```bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output /tmp/cst-p3-1-p2.json
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p3-1-ci.json
```

P2 must remain 5/5 and raw CI 8/8. The open P1 6/7 model result is documented
but is not reclassified as a P3.1 regression unless trace work changes raw
retrieval output, which the parity gates forbid.

## Documentation And Roadmap Updates

The implementation updates:

- `README.md` with CLI and MCP examples and privacy semantics;
- `docs/retrieval-quality.md` with the deterministic P3.1 acceptance command and
  `TraceCoverage` definition;
- the roadmap with independent P1/P2 status, the P3.1/P3.2 split, and P3.1
  completion evidence only after every acceptance gate passes.

P3.1 completion does not mark P3.2 or Phase 3 as a whole complete.

## Risks And Mitigations

### Instrumentation Changes Ordering

Risk: converting mappings or candidates for trace output accidentally changes
the live collection order.

Mitigation: observation conversion occurs after the retrieval operation, reads
copies or immutable values, and is protected by full payload parity tests.

### Trace Payload Becomes A Second Raw Result Dump

Risk: full candidates, score parts, or content make the trace too large.

Mitigation: fixed previews, no source content, full counts, final-only detailed
adjustments, and explicit omitted counts.

### Trace Schema Couples To Private Classes

Risk: serializing `_RankedChunk` or `_ExpandedResult` directly makes P3.2 unable
to change internals.

Mitigation: convert private objects into public trace dataclasses inside
`retrieval.py`; serialization imports only trace models.

### Diagnostics Leak Into Feedback

Risk: reuse of query-tool helpers persists paths, variants, or trace data.

Mitigation: the trace MCP path has no feedback call, and sentinel tests verify
that the log is unchanged.

### Timings Make Tests Flaky

Risk: real clock values change on every run.

Mitigation: inject the clock in collector unit tests and assert only type/range in
end-to-end tests.

## Acceptance Criteria

P3.1 is complete only when all of the following are true:

1. `RetrievalTrace` schema version 1 has exact typed models and serialization.
2. `cst trace` and `context_search_trace` execute exactly one retrieval pass.
3. The canonical fifteen stages and raw source counts are present when reached.
4. Stage candidate previews, final selections, and adjustments obey fixed limits;
   stages retain uncapped counts, while final and adjustment previews report
   omitted counts.
5. Every serialized final selection has provenance, rank history, a selection
   reason, and finite values for any materialized adjustments.
6. Trace output contains no source content and is never written to MCP feedback.
7. Deterministic trace/non-trace raw query payloads are identical.
8. Deterministic trace/non-trace ContextPack v2 canonical bytes are identical.
9. Ordinary queries allocate no collector, candidate preview, or rank history.
10. Early-return and public-error semantics match this design.
11. `TraceCoverage` is 1.0 on the committed P3.1 acceptance cases.
12. The full suite, P2 5/5 profile, and raw CI 8/8 profile pass.
13. Roadmap and operational documentation record exact evidence without claiming
    Phase 1 or P3.2 completion.

## Stop Point

P3.1 ends after the trace contract, request-local collector, existing-pipeline
instrumentation, CLI/MCP operations, deterministic acceptance coverage,
documentation, and conditional roadmap update are implemented and verified.

It does not split `retrieval.py`, change ranking, execute follow-up queries, add
multi-round exploration, persist traces, or begin P3.2 implementation.
