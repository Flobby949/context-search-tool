# P1 Query Understanding Closure Design

Date: 2026-07-13
Status: Approved direction; written review pending
Repository: `/Users/flobby/Documents/context-seatch-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor: `docs/superpowers/specs/2026-07-11-p0-quality-control-loop-closure-design.md`

## Summary

Close Phase 1 of the fast-context-like retrieval roadmap by making query
rewrites participate in semantic retrieval, while preserving the exact-search
behavior that already works.

Phase 1 is not a greenfield query-understanding implementation. CST already
has an optional Ollama query planner, bounded structured output, a repository
profile, planner fallback behavior, lower-priority lexical and symbol hints,
and a quality runner. The remaining product gap is that planner rewrites do not
currently enter vector recall: only the original query is embedded, while
planner output affects lexical, path, symbol, signal, and relation recall.

The selected design has two runtime modes:

- **Vector mode:** when the planner is disabled or unavailable, embed and
  retrieve with the original query only.
- **Hybrid mode:** when the planner succeeds, batch-embed the original query
  and its bounded rewrites, search the same vector index for every variant,
  then merge candidates with explicit variant provenance.

This phase does not add a Chinese-English lexicon, a vector-first planning
pass, or multi-round exploration. Exact path, symbol, literal text, and strong
lexical evidence remain protected from planner-induced ranking regressions.

## Current State

The following Phase 1 foundations already exist and remain in place:

- `query_planner.py` defines the planner protocol, Ollama client, structured
  JSON cleanup, prompt diagnostics, repo-aware filtering, and fallback plans.
- `repo_profile.py` builds a bounded profile from indexed languages, source
  roots, representative files, symbols, and lexical tokens.
- `retrieval.py` invokes the planner before candidate collection and consumes
  planner terms as lexical, path/symbol, signal, and relation hints.
- Planner evidence uses separate score parts and is distinguishable from
  original-query evidence.
- JSON, Markdown, MCP responses, and bounded MCP planner diagnostics already
  expose planner status. The raw MCP feedback log stores the original query;
  the feedback summary hides query terms and examples by default.
- The canonical quality catalog has deterministic CI coverage, real model
  profiles, and a committed cross-language dashboard fixture.

The relevant current limitation is in semantic recall:

```text
_semantic_candidates(index_dir, original_query, ...)
```

Only the original query is embedded. `QueryPlan.rewritten_queries` are reduced
to tokens and never searched as vectors. This prevents the planner and the
embedding retriever from forming one coherent retrieval path.

There are two related gaps:

- Candidate provenance identifies planner score families but not the exact
  query variant that produced a semantic match.
- When strong original evidence creates a shared score ceiling, the current
  evidence-priority tie-break can place a weak original-query match above a
  stronger direct planner match.

## Verified Baseline

The design baseline was measured on commit `4e25092` on 2026-07-13:

- full test suite: `1121 passed, 3 skipped`;
- `ci` quality profile: 8 selected, 8 executed, 8 passed;
- `planner` profile with the committed dashboard snapshot: 1 executed and 1
  passed, while 3 `psf/requests` cases were skipped because no external source
  path was configured;
- dashboard planner latency on the local machine: 2448 ms;
- available local models: `qwen3.5:4b-mlx` and `bge-m3`.

These numbers are evidence for the starting point, not permanent latency
thresholds.

## Goals

- Make planner rewrites participate in semantic/vector recall.
- Keep planner-disabled behavior equivalent to original-query vector search.
- Batch embedding work into one retrieval-layer provider invocation per
  successful query plan.
- Preserve which query variant produced each semantic candidate.
- Let strong planner semantic evidence outrank weak incidental original-query
  evidence.
- Preserve strong exact, path, symbol, literal, and lexical behavior.
- Keep planner failure and unusable output as clean vector-only fallbacks.
- Measure vector-only and hybrid behavior over the same required quality cases.
- Keep the implementation bounded and compatible with the existing CLI and MCP
  response contracts.

## Non-Goals

- No static or repository-configured translation lexicon.
- No vector recall before planning and no second planning round.
- No autonomous or controlled multi-round exploration.
- No `ContextPack` output.
- No full `RetrievalTrace` or retrieval-core decomposition.
- No LLM reranker or answer generator.
- No new planner provider in this phase.
- No automatic embedding-provider selection.
- No silent fallback from one embedding model to another.
- No requirement that hash embeddings solve cross-language retrieval without a
  planner.
- No broad refactor of `retrieval.py` beyond the query-variant path and the
  ranking behavior it directly requires.

## Decision And Alternatives

### Selected: Plan Once, Then Run Bounded Multi-Query Vector Recall

When planning succeeds, construct one ordered set containing the original
query and valid planner rewrites. Pass that set to one retrieval-layer batch
embedding invocation, perform one vector-index search per vector, merge by
chunk ID, and keep the per-variant scores.

This is the smallest design that makes the existing planner and vector
retriever work together.

### Rejected: Static Translation Lexicon

A static lexicon is deterministic but cannot generalize across projects and
business domains. It creates an open-ended coverage and maintenance burden,
and ambiguous terms can introduce incorrect expansions. Phase 1 therefore
relies on two general mechanisms only: model-based rewriting and multilingual
vector similarity.

### Rejected: Vector Recall Before Planning

A vector-first flow would retrieve once, summarize the first result set for
the planner, then retrieve again. It adds latency, can feed noisy cross-language
results back into the planner, and begins to implement the multi-round behavior
reserved for Phase 4. The existing static repository profile is sufficient for
the bounded Phase 1 planner contract.

### Rejected: Planner Hints Without Variant Vector Search

This is the current behavior. It helps when a rewrite produces an exact English
identifier, but it does not let a natural-language English rewrite find
semantically related code. It also makes model and vector quality difficult to
evaluate as one path.

## Runtime Architecture

```text
User Query
  -> Build bounded static RepoProfile
  -> Query Planner (optional)
       -> disabled/fallback/empty: original query only
       -> ok: original query + validated rewritten queries
  -> Build ordered QueryVariants
  -> Invoke batch embedding once from the retrieval layer
  -> Search vector index once per variant
  -> Merge semantic candidates by chunk_id
       -> keep original semantic score
       -> keep maximum planner semantic score
       -> keep all per-variant semantic matches
  -> Existing recall sources
       -> original lexical/path/symbol/signal recall
       -> planner lexical/path/symbol/signal hints
       -> existing relation and anchor expansion
  -> Rerank with strong-original-evidence protection
  -> Existing context expansion and QueryBundle output
```

There is no preliminary vector pass. In hybrid mode, planning happens before
the one retrieval-layer batch embedding invocation.

## Query Variant Contract

Add a small public data model so CLI JSON and MCP can use the same contract:

```python
@dataclass(frozen=True)
class QueryVariant:
    variant_id: str
    text: str
    source: str


@dataclass(frozen=True)
class SemanticMatch:
    variant_id: str
    score: float
```

Allowed `source` values are `original` and `planner`.

Variant construction follows these rules:

1. The original query is always first and has ID `original`.
2. Planner variants exist only when `QueryPlan.status == "ok"`.
3. Only `rewritten_queries` become semantic query variants.
   `grep_keywords` and `symbol_hints` remain lexical and symbol hints.
4. Normalize surrounding and repeated whitespace.
5. Reject planner variants longer than 256 Unicode code points and record them
   as discarded planner output. Do not truncate a query into a different
   semantic statement. The original user query is not length-limited here.
6. Drop empty strings and case-insensitive duplicates of the original query or
   an earlier retained planner variant.
7. Limit planner variants with the existing `max_rewritten_queries` setting.
8. Assign stable IDs in retained order: `planner:0`, `planner:1`, and so on.

The exact order is therefore normalize, length validation, deduplication,
count limiting, then ID assignment. Stable IDs make provenance compact and
prevent response consumers from needing to compare query text.

## Semantic Recall And Candidate Merging

Invoke the existing embedding provider's batch API once from the retrieval
layer:

```text
embed_texts([variant.text for variant in variants])
```

The provider invocation returns one vector per retained variant. A provider may
split that invocation into multiple transport requests according to its
existing limits; for example, BGE batches by text count and character budget.
Each returned vector is searched against the same compatible
`NumpyVectorStore` using the existing `semantic_top_k` value.

The semantic candidate bound is therefore:

```text
(1 + max_rewritten_queries) * semantic_top_k
```

With current defaults, this is at most 400 pre-merge semantic candidates. The
bound is explicit, requires no new user configuration, and is reduced by chunk
deduplication before ranking.

For each chunk:

- keep the original-query semantic score separately;
- keep the maximum planner-variant semantic score separately;
- keep one `SemanticMatch` per matched variant, retaining the highest score for
  that variant;
- do not sum scores from duplicate or synonymous planner variants;
- preserve semantic matches when the same chunk is later merged with lexical,
  symbol, signal, anchor, or relation candidates;
- when adjacent chunks are expanded or merged into one output item, take the
  union of their matches, keep the highest score per variant, and order matches
  by the corresponding `QueryVariant` order.

`RetrievalCandidate`, `RetrievalResult`, and `EvidenceAnchor` gain a
default-empty `semantic_matches` field. Internal ranked and expanded result
structures carry the field through context expansion and file-level merging.
Existing constructors and non-semantic sources remain compatible through the
default.

## Ranking Policy

Semantic variants use a max-based blend rather than additive scoring:

```text
if planner_semantic_max exists and planner_semantic_max > 0:
    adjusted_planner_semantic = planner_weight * planner_semantic_max
elif planner_semantic_max exists:
    adjusted_planner_semantic = planner_semantic_max

if original_semantic exists and adjusted_planner_semantic exists:
    effective_semantic = max(
        original_semantic,
        adjusted_planner_semantic,
    )
elif original_semantic exists:
    effective_semantic = original_semantic
elif adjusted_planner_semantic exists:
    effective_semantic = adjusted_planner_semantic
else:
    there is no semantic component

semantic_component = existing_semantic_weight * effective_semantic
```

Existence is tracked separately from the numeric value. In particular, no
planner match is not represented as score `0`: vector similarities may be
negative, and substituting zero would change planner-disabled and fallback
ranking. The planner weight attenuates only positive similarity. Multiplying a
negative score by a value below one would incorrectly make it less negative and
therefore improve it; non-positive planner similarities retain their raw value.

The raw values remain visible when they exist as:

- `semantic`: original-query semantic score;
- `planner_semantic`: maximum raw planner-variant semantic score;
- `effective_semantic`: the value consumed by combined scoring.

`planner_weight` is an internal ranking constant, not a new user setting. Its
initial value is selected by comparing the Phase 1 quality profiles. It must be
large enough for a strong planner rewrite to help a vague or cross-language
query, but less than or equal to the original semantic contribution.

The max-based formula provides dynamic behavior without a language detector or
query router:

- when original semantic evidence is stronger, planner semantic evidence adds
  nothing;
- when a planner variant is materially stronger, it replaces the weak semantic
  contribution after applying the planner weight;
- emitting more variants cannot accumulate extra semantic score.

### Evidence Ordering

Strong original direct evidence remains the protected top class. It includes
the existing strong path/symbol, literal text, token-coverage, signal, and
corroborated lexical or semantic thresholds.

Planner semantic evidence never counts as strong *original* evidence. The
original semantic field and original-query signals alone determine that
protection.

Below that protected class, weak original direct evidence and direct planner
evidence share one priority and are ordered by their rerank scores. Preserve
the current strong-original ceiling. If that ceiling makes two non-strong
scores equal, use their pre-ceiling rerank score before role and path tie-breaks
so the ceiling protects strong evidence without erasing the relative strength
of weaker candidates.

The intended priority is:

1. strong original direct evidence;
2. weak original direct or direct planner evidence, ordered by score;
3. original relation evidence;
4. planner relation evidence;
5. weak or generic evidence.

Planner lexical, path/symbol, signal, and relation evidence keep their existing
separate score parts. Phase 1 changes only what is necessary to add planner
semantic evidence and remove the weak-original blanket suppression.
Existing planner-evidence predicates and reason formatting must recognize
`planner_semantic` as direct planner evidence and emit a planner semantic match
reason when it contributes.

## Configuration And Operating Modes

The existing explicit switch remains authoritative:

```toml
[query_planner]
enabled = true
```

The rendered default config already contains provider and model names. Their
presence does not imply that planning is enabled. CLI `--planner` and
`--no-planner` continue to override the setting for one query.

| planner outcome | semantic behavior |
| --- | --- |
| disabled | embed and search the original query |
| ok with valid rewrites | batch-embed and search original plus rewrites |
| ok with no valid rewrites | embed and search the original query |
| timeout, HTTP failure, invalid JSON, or validation failure | embed and search the original query |
| variant batch embedding failure | discard variants and retry the original query once |
| embedding provider or index incompatibility | propagate the existing query error path; do not switch providers |

Planner failure must not block the original vector path. Embedding-provider
failure is different: hash vectors cannot query a BGE index, and silently
changing providers would return invalid similarity scores.

`QueryBundle.query_variants` describes variants that were actually searched,
not every rewrite proposed by the planner. After an embedding fallback it
contains only `original`; the planner section still contains the proposed
rewrites. Add `variant_retrieval_status` with these values:

- `original_only`: no planner variant was searched;
- `hybrid`: one or more planner variants were searched;
- `embedding_fallback`: planner variants were prepared, batch embedding failed,
  and the original-only retry was used.

`QueryBundle.query_variants` uses a default-empty list and
`variant_retrieval_status` defaults to `original_only` so existing test and
consumer constructors remain valid. Real query execution always includes the
`original` variant, including empty-result paths.

## Output And Privacy

`QueryBundle` gains `query_variants` and `variant_retrieval_status`. Retrieval
results and evidence anchors gain `semantic_matches`.

The JSON and MCP shape is additive:

```json
{
  "query_variants": [
    {"variant_id": "original", "source": "original", "text": "数据看板统计图表功能"},
    {"variant_id": "planner:0", "source": "planner", "text": "dashboard statistics chart"}
  ],
  "variant_retrieval_status": "hybrid",
  "results": [
    {
      "path": "src/main/java/com/example/dashboard/DashboardController.java",
      "semantic_matches": [
        {"variant_id": "planner:0", "score": 0.84}
      ]
    }
  ]
}
```

Existing fields remain unchanged. Markdown keeps the current concise planner
expansion line and does not print a per-result provenance table.

The raw MCP feedback log continues to store the original query under the
existing contract. Phase 1 does not add rewritten query text to that log. It may
add variant count, source, stable position, text hash, and retrieval status.
The existing quality-feedback summary continues to omit original query terms
and examples unless its explicit inclusion flags are used.

This is deliberately not a complete retrieval trace. Stage counts, candidate
survival, and full rerank explanations remain Phase 3 work.

## Quality Profiles

Keep the current `ci`, `planner`, `calibration_bge`, `ab_hash`, and `ab_bge`
profiles. Add two Phase 1 profiles that run the same cases:

| profile | embedding | planner | purpose |
| --- | --- | --- | --- |
| `p1_vector_bge` | BGE-M3 | disabled | validate the generalized vector-only path |
| `p1_hybrid_bge` | BGE-M3 | Qwen | validate planner plus vector recall |

Canonical profile validation must enforce the names rather than merely accept
their configuration dictionaries:

- `p1_vector_bge` requires provider `bge`, model `bge-m3`, dimensions `1024`,
  and a disabled planner;
- `p1_hybrid_bge` requires the same embedding configuration plus an enabled
  Ollama planner using `qwen3.5:4b-mlx`.

Misconfigured Phase 1 profiles fail fixture validation before any repository is
copied or indexed.

Cross-language success in vector-only mode is evaluated with a multilingual
embedding model. Hash embedding remains the deterministic offline and CI
baseline, but is not expected to bridge unrelated Chinese and English terms on
its own.

The Phase 1 case set must include:

- at least three required cross-language queries;
- at least two committed snapshot repositories;
- the existing dashboard query and suitable cases from the existing
  `embedding_ab` snapshot where possible;
- representative exact path or symbol queries under hybrid mode to prove that
  planner activation does not weaken exact retrieval.

Required Phase 1 cases use committed snapshots so the profile does not skip
them because an external checkout is absent. A missing local BGE or Qwen model
is reported as `unverified_dependency`, following the Phase 0 policy; it is not
reported as a pass.

### Profile-Specific Runtime Expectations

Result-path assertions alone cannot prove that hybrid mode ran: a strong BGE
original-query result could pass after the planner fell back. Extend the
canonical case schema with optional `profile_expectations` keyed by profile.
The supported expectation fields are:

```json
{
  "profile_expectations": {
    "p1_vector_bge": {
      "planner_status": "disabled",
      "variant_retrieval_status": "original_only"
    },
    "p1_hybrid_bge": {
      "planner_status": "ok",
      "variant_retrieval_status": "hybrid",
      "top_result_planner_semantic_match": true
    }
  }
}
```

The runner evaluates these expectations as part of the case gate, not only as
report diagnostics. Cross-language hybrid cases require planner status `ok`
and actual hybrid variant retrieval. At least one designated case also requires
the Top 1 result to contain a `planner:*` semantic match. Exact-protection cases
may require planner status `ok` without requiring a rewrite, because an exact
query can legitimately produce no useful planner variant.

The report records `variant_retrieval_status`, executed `query_variants`, and
result semantic matches so failed expectations are inspectable. A planner
fallback, empty cross-language rewrite set, or missing semantic provenance
cannot be reported as a passing hybrid verification.

## Testing Strategy

### Unit Tests

- variant creation, ordering, normalization, deduplication, and IDs;
- count and 256-code-point planner-variant bounds;
- rejection rather than truncation of an overlong planner variant;
- disabled, fallback, empty, and successful plans;
- one retrieval-layer `EmbeddingProvider.embed_texts` invocation for all
  variants, independent of provider-internal transport batching;
- one vector search per retained variant;
- per-chunk, per-variant max merging;
- final result and evidence-anchor union merging with stable variant order;
- max-based semantic scoring without count-based inflation;
- preservation of a negative original semantic score when no planner semantic
  match exists;
- non-positive planner similarities are never improved by the planner weight;
- weak original and planner-direct shared evidence priority;
- pre-ceiling rerank ordering when protected candidates create equal ceilings;
- strong original exact-evidence protection;
- original-only retry after a variant batch embedding failure.

### Retrieval Integration Tests

- a fake planner rewrite retrieves a chunk through vector similarity, not only
  planner lexical or symbol hints;
- a planner-semantic result can outrank an incidental weak original match;
- an exact path, symbol, endpoint, or literal query keeps its expected Top 1;
- planner-disabled and planner-fallback paths produce the same ranked results
  for the same original query and embedding provider;
- after variant embedding fallback, executed variants contain only `original`
  and status is `embedding_fallback`;
- duplicate rewrites do not change result score or ordering.

### Contract And Privacy Tests

- JSON and MCP expose `query_variants` and `semantic_matches` additively;
- Markdown remains concise;
- raw MCP feedback retains its existing original query but stores hashes and
  counts rather than rewritten variant text;
- existing consumers that ignore new fields retain the old result contract.

### Quality Tests

- run the full test suite;
- run the existing deterministic `ci` profile;
- run `p1_vector_bge`;
- run `p1_hybrid_bge`;
- compare vector and hybrid reports over the identical selected cases;
- retain the current planner/hash profile to isolate planner behavior from
  multilingual embedding behavior.

The standard comparison command remains useful for the report and its existing
regression classes, but it does not enforce zero decline for every Phase 1
metric. Add a focused model-backed Phase 1 acceptance test that runs both
profiles from committed snapshots and asserts:

- identical case-key and gate sets;
- every profile-specific runtime expectation;
- no negative aggregate delta for MRR mean, Recall@5 mean, or entrypoint Top3
  rate;
- no required-case status regression.

The test is marked `integration` and guarded by an explicit environment switch
so the ordinary offline test suite does not require local models. The Phase 1
acceptance command enables that switch; a skipped or dependency-unverified run
cannot close the phase. This focused gate avoids changing the default tolerance
semantics of the general-purpose quality comparator.

## Acceptance Criteria

Phase 1 is complete only when all of the following are true:

1. The full test suite passes and the existing `ci` profile has no gating
   regression.
2. Every required committed-snapshot case in `p1_vector_bge` and
   `p1_hybrid_bge` executes and passes.
3. The focused Phase 1 profile-pair gate confirms identical case/gate sets and
   no negative required-case, MRR, Recall@5, or entrypoint Top3 delta. The
   default comparison CLI result alone is not sufficient for this criterion.
4. At least one deterministic test proves that the winning chunk was recalled
   by a `planner:*` semantic variant rather than only by planner lexical hints.
5. Exact path, symbol, endpoint, and literal-text regression cases preserve
   their required ranks with the planner enabled.
6. Planner timeout, malformed output, unsupported output, and empty output all
   complete through original-query vector retrieval.
7. A successful hybrid query performs at most one planner request, one
   retrieval-layer `embed_texts` invocation, and `1 + N` vector searches for
   `N` retained planner variants. Provider-internal transport batching remains
   allowed.
8. JSON/MCP provenance is complete and MCP feedback does not expose variant
   text by default.
9. Latency mean, p50, and p95 are recorded for both Phase 1 profiles. No
   machine-specific millisecond gate is introduced in this phase.
10. The roadmap is marked Phase 1 complete only after the required profiles
    have been exercised; missing model dependencies cannot be counted as
    acceptance.

## Likely Change Surface

Expected source changes are intentionally narrow:

- `src/context_search_tool/models.py`
  - add `QueryVariant` and `SemanticMatch`;
  - add default-empty semantic provenance to retrieval candidates, results, and
    evidence anchors.
- `src/context_search_tool/query_planner.py`
  - enforce the planner-variant length bound during cleanup or variant
    construction.
- `src/context_search_tool/retrieval.py`
  - build variants;
  - batch embeddings and run per-variant vector searches;
  - merge semantic provenance;
  - add planner semantic scoring and the revised evidence priority.
- `src/context_search_tool/formatters.py`
  - serialize variant and semantic-match fields.
- `src/context_search_tool/mcp_tools.py`
  - expose additive provenance and preserve feedback privacy.
- `src/context_search_tool/quality/cases.py`
  - validate both Phase 1 profile configurations;
  - parse and validate profile-specific runtime expectations.
- `src/context_search_tool/quality/runner.py`
  - serialize executed variant provenance;
  - make runtime expectations part of case pass/fail evaluation.
- focused tests for the modules above.
- a model-backed Phase 1 profile-pair acceptance test with an explicit
  execution switch.
- `tests/fixtures/retrieval_quality/queries.json`
  - add Phase 1 profile configs and shared required cases.
- `docs/retrieval-quality.md`
  - document the new profile commands.
- the roadmap
  - update status only after acceptance passes.

The existing embedding-provider and vector-store APIs already accept batched
texts and independent vector searches. They should not need redesign. If
implementation reveals otherwise, that is a design-change gate rather than
permission for a broader refactor.

## Risks And Mitigations

### Generic Or Hallucinated Planner Rewrites

Keep existing repository-profile filtering, variant count and length bounds,
lower planner weight, exact-evidence protection, and visible provenance.

### Candidate Growth

The number of searches and candidates is bounded by existing configuration.
Merge by chunk ID before ranking and never sum synonymous variant scores.

### Score Comparability

Every query variant uses the same embedding provider and the same compatible
index. Use max-based blending rather than adding cosine similarities across
variants. Treat missing scores as absent rather than zero so negative cosine
similarities retain their current meaning.

### Model Nondeterminism

Use the existing strict structured output, prompt version/hash, repository
filter, and required quality cases. Deterministic unit tests use a fake planner;
real-model profiles validate operational behavior separately.

### Exact-Search Regression

Keep strong original direct evidence in the protected top class and exercise
exact queries with the planner enabled before marking the phase complete.

### Model Availability

Planner failure falls back to vector-only mode. Model-dependent acceptance
profiles report unavailable dependencies explicitly and cannot silently pass.

## Handoff Boundary

This document defines the Phase 1 design only. After written review approval,
the next artifact is a separate implementation plan with test-first tasks and
quality checkpoints. No Phase 2, Phase 3, or Phase 4 work is implied by that
plan.
