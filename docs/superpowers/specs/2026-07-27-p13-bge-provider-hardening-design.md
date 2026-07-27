# P13 BGE Provider Hardening and Independent Evaluation v1 Design

Date: 2026-07-27
Status: Reviewed r2; implementation not started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `122ed052284fa488943cb4464301a391bd2e7e24`
Predecessors: P10/P11/P12 implementation records

Review r2 note: parallel Standards and Spec reviews found two blocking
gaps in r1: a cached preflight could miss a model change during a
multi-batch operation, and existing vector loaders would reject the new
BGE identity before the candidate-layer check. r2 adds a cache-bypassing
production postflight before publication/search and explicitly splits
static config validation from exact runtime validation through every
load/validator path. It also makes commit checkpoints conditional,
defines a tracked baseline-measurement harness, limits live BLOCKED
status to live tasks, corrects test paths, and describes performance as
bounded rather than “no slower.” Follow-up review required fresh-process
isolation for every measured implementation root and a provider-
discriminated capture schema; both are included below.

## Decision

Treat BGE as an independent provider-hardening project, not as another
retrieval-policy experiment.

P10, P11, and P12 rejected three different retrieval mechanisms:
token-affinity relation selection, indexed-vector overflow reranking,
and a repo-grounded planner. Those dispositions remain closed. P13
does not reactivate relation slots, alter ranking, add planner hints, or
repin retrieval gold.

P11 nevertheless produced a useful provider-only control: on identical
behavior code, switching from hash to BGE improved combined Recall@12
from `0.859649` to `0.877193`, added one required hit, lost none, and
slightly reduced the noise ratio. It also exposed a real BGE product
defect and severe indexing cost. That is enough evidence to harden and
measure the provider independently; it is not enough evidence to make
BGE the default.

P13 therefore has two separate decisions:

1. **Engineering readiness:** is the BGE provider safe, reproducible,
   failure-atomic, observable, and within the pre-committed performance
   bounds relative to the current BGE implementation?
2. **Product recommendation:** on the same retrieval code, does
   hardened BGE provide enough paired quality benefit at an acceptable
   paired cost to recommend it for multilingual, quality-sensitive
   opt-in use?

Passing the first decision permits an opt-in provider merge. It does
not imply passing the second. P13 never changes the default provider.

## Preparation Evidence

### Fixed test environment

The project-fixed runtime is:

| component | frozen value |
| --- | --- |
| entry point | `.quality/p5-runtime/bin/python` |
| Python | 3.13.12 |
| SQLite | 3.51.2 |
| NumPy | 2.4.2 |
| pytest | 9.0.3 |

The three environment-sensitive characterization nodes pass under that
runtime. The non-slow suite produced `2978 passed, 5 failed, 5 skipped,
5 deselected` inside the restricted runner; all five failures were
macOS `sysctl` permission failures in P6 measurement workers. Running
those exact five nodes outside the restriction produced `5 passed`.
The effective fixed-environment baseline is therefore:

```text
2983 passed, 5 skipped, 5 deselected
```

No product failure or characterization drift is present at the design
baseline. `.venv` uses Python 3.14.6 and is not the accepted test entry.

### Live-provider availability

On 2026-07-27, `http://localhost:11434/api/version` was not reachable
with environment proxies bypassed. Live BGE correctness, performance,
and A/B gates are therefore **BLOCKED**, not passed. P13 must never
substitute hash vectors or mocked vectors for a live disposition.

### Existing BGE evidence

| evidence | quality | cost / defect |
| --- | --- | --- |
| P11 hash → BGE provider control | Recall@12 `0.859649 → 0.877193`; one new required; zero lost; noise `0.712963 → 0.708333` | RedInk index `0.1477s → 16.9936s` (~115x); daily index `2.1948s → 334.7759s` (~153x); mean query `0.47914s → 0.68957s` (~1.44x) |
| P1 `p1_vector_bge` | 6/7 cases passed | one audit-status literal miss |
| P1 `calibration_bge` | 8/8 cases passed | mean query latency ~2285.6ms; individual repositories varied materially |
| P11 dense-CJK indexing | not measurable without workaround | a 6,924-character chunk caused Ollama HTTP 400: input exceeded model context |

The P11 acceptance runner currently monkeypatches
`BGEEmbeddingProvider.embed_texts` to keep only the first 4,000
characters. That workaround proves the provider defect and permits an
experiment, but it is not an acceptable product contract:

- production indexing still fails on the same input;
- the transform is not recorded in the vector identity;
- head-only truncation drops the lexical-token suffix deliberately
  appended by `_embedding_text_for_chunk`;
- the server is free to truncate other inputs silently because the
  request does not set `truncate: false`.

### Current implementation gaps

`embeddings_bge.py` currently:

- hardcodes `http://localhost:11434/api/embed` and ignores
  `EmbeddingConfig.base_url`;
- batches at eight texts and 6,000 aggregate characters, producing many
  small requests on real repositories;
- does not preflight Ollama version, canonical model name, or digest;
- does not bind model/runtime/preprocessing identity to persisted
  vectors;
- permits Ollama's default server-side truncation;
- accepts zero and non-finite vectors and does not require a one-
  dimensional response;
- exposes only generic request exceptions and has no stable safe error
  taxonomy;
- creates a new provider at query time without checking that it matches
  the provider that built the index.

The existing manifest binds the configured provider/model/dimensions
but not the mutable `bge-m3:latest` digest or the Ollama runtime.

## Goals

1. Make BGE indexing and query embedding deterministic under one
   documented input transform.
2. Fail early and safely when Ollama, the configured model, or the
   response contract is invalid.
3. Prevent a query from mixing an old vector index with a different
   live BGE model/runtime.
4. Preserve the current atomic publication guarantees when a remote
   embedding batch fails.
5. Preserve source privacy: local Ollama calls bypass ambient proxies,
   and errors/logs never contain source or query text.
6. Keep refresh network-egress accounting truthful for preflight,
   embedding, and postflight, including failures.
7. Reduce current BGE request amplification without changing generic
   indexer batch semantics.
8. Measure provider quality and cost in an isolated hash-vs-BGE A/B
   with all retrieval behavior held constant.
9. Keep hash behavior and every existing characterization pin
   byte-identical.

## Non-Goals

- Changing the default from `hash` to `bge`.
- Reopening P9/P10/P11 relation quotas or reranking.
- Reopening the P12 planner.
- Changing chunking, lexical text construction, graph expansion,
  ranking weights, final selection, or gold expectations.
- Refactoring `openai-compatible` alongside BGE.
- Adding a generic retry framework, circuit breaker, daemon manager, or
  model installer.
- Silently falling back from BGE to hash.
- Automatically pulling or updating an Ollama model.
- Claiming a universal wall-clock latency across machines.

## Frozen Provider Contract

### 1. Configuration and transport

- Endpoint root is
  `config.base_url.rstrip("/")` when `base_url` is non-empty, otherwise
  `http://localhost:11434`.
- Embed endpoint is `<root>/api/embed`; preflight endpoints are
  `<root>/api/version` and `<root>/api/tags`.
- A provider-created `requests.Session` keeps `trust_env = False`.
  Source code must not be redirected through `HTTP_PROXY` or
  `HTTPS_PROXY`.
- A caller-supplied session remains caller-owned and is not mutated
  beyond the existing JSON content header behavior.
- Preflight timeout is 5 seconds; embedding timeout is 60 seconds.
  These are module constants in v1, not new configuration fields.
- There are no automatic retries. A caller may rerun the whole atomic
  index operation after correcting the service.

### 2. Cached preflight and forced postflight

Before the first non-empty embed on a provider instance:

1. `GET /api/version` must return a non-empty string field `version`.
2. `GET /api/tags` must return a list field `models`.
3. The configured model is canonicalized deterministically:
   `bge-m3` means exactly `bge-m3:latest`; an explicitly tagged model
   such as `bge-m3:v1` means exactly that name.
4. Exactly one canonical-name match must exist. Prefix matching is
   forbidden.
5. The matched model must have a lowercase 64-hex digest.

`embed_texts([])` returns `[]` without attestation or HTTP traffic.
For non-empty work, the provider caches the preflight attestation for
its lifetime and does not poll between internal batches. Indexing and
query entry points create separate provider instances.

The attestation contains:

```text
configured model
canonical model name
model digest
Ollama version
base URL
input transform ID
configured dimensions
```

The provider also exposes a cache-bypassing postflight that fetches
version and tags again and compares canonical model, digest, and
version with the cached preflight:

- authoritative index and incremental refresh call it after the final
  embed and before freezing or publishing vectors;
- query calls it after all query variants are embedded and before the
  first vector search;
- a mismatch aborts the operation with `bge_runtime_mismatch`.

This detects a model/runtime change across the observed embedding
interval without one tags request per internal batch. Capture
infrastructure performs one additional post-publication check as
evidence. Ollama offers no transaction or digest-pinned embed request,
so an unobservable ABA tag change remains a documented platform limit.

### 3. Deterministic input transform

The v1 transform ID is `bge-input-v1`.

For every indexing text and query variant:

```python
if len(text) <= 4000:
    prepared = text
else:
    prepared = text[:3000] + "\n" + text[-999:]
```

Length is Python Unicode code points, not UTF-8 bytes and not an
estimated token count. The result is at most 4,000 code points. The
3,000/999 split is frozen before evaluation:

- the head retains declaration and local context;
- the tail retains the lexical-token suffix and end-of-chunk evidence;
- the inserted newline prevents accidental token concatenation.

The request explicitly sends `"truncate": false`. If a prepared input
still exceeds the model context, the provider raises a safe
`bge_context_limit` error. There is no second truncation rule and no
server-silent transform.

The transform belongs inside `BGEEmbeddingProvider`, so authoritative
indexing, incremental refresh, queries, quality runners, and direct
provider use share exactly one behavior.

### 4. Batching and request body

- Preserve input order.
- Send at most eight prepared texts per `/api/embed` request.
- Delete the 6,000 aggregate-character request cap.
- A full request is therefore bounded by eight texts and at most
  32,000 Unicode code points.
- Send only:

```json
{
  "model": "<configured model>",
  "input": ["<prepared text>", "..."],
  "truncate": false
}
```

No source identifiers, repository paths, or trace metadata are sent.
Ollama documents array input and `truncate: false`; request-count and
latency gates below verify that the larger batches help on the actual
model rather than assuming they do.

### 5. Response validation

For each response:

- the JSON root must be an object;
- `embeddings` must be a list;
- its length must equal the request input count;
- every embedding must be a one-dimensional numeric sequence;
- every vector must have exactly `config.dimensions` values;
- all values must be finite;
- the float32 L2 norm must be finite and greater than zero.

Each valid vector is normalized to L2 unit length in float32 even
though Ollama currently documents unit-length output. Invalid vectors
fail the whole call. No partial vector list is returned.

### 6. Safe errors

One BGE base exception derives from `ValueError` and carries a stable
`code`; this preserves the existing CLI/MCP safe-value boundary without
a broad exception refactor. Public messages contain only
provider/model/input ordinal/length/status information, never request
text, response bodies, repository paths, or credentials.

The frozen v1 codes are:

| code | condition |
| --- | --- |
| `bge_unavailable` | connection, timeout, or invalid preflight transport |
| `bge_model_unavailable` | canonical model absent, ambiguous, or digest invalid |
| `bge_context_limit` | a prepared input is rejected for context length |
| `bge_request_rejected` | other non-success embed response |
| `bge_response_invalid` | malformed JSON, count, shape, dimensions, finite, or norm failure |
| `bge_runtime_mismatch` | live identity differs from the indexed identity |
| `bge_reindex_required` | legacy/unattested BGE vector identity |

CLI and MCP boundaries may continue mapping these to their existing
privacy-safe generic remote-embedding message. Tests assert the raw
source/query string is absent from exception text and logs.

## Runtime Identity and Persistence

### Static configuration identity remains unchanged

`manifest.embedding_config_hash` remains the SHA-256 of provider,
model, dimensions, and base URL. Hash and openai-compatible behavior
remain unchanged.

### BGE descriptor identity

For BGE only, the vector descriptor's `embedding_identity` becomes:

```text
bge-ollama-v1:
<embedding_config_hash>:
<model_digest>:
<sha256(UTF-8 Ollama version)>:
bge-input-v1
```

The actual string is one colon-delimited line. The model digest and
both SHA-256 fields are lowercase 64-hex values.

The raw Ollama version and canonical model name are recorded in quality
capture evidence, while the descriptor stores a bounded stable
identity. The configured model and dimensions remain in the manifest.

### Why manifest v3 is not required

Manifest v2 already binds the complete vector descriptor by SHA-256:

```text
manifest.embedding_config_hash
        |
        +---- must equal the config-hash segment in BGE identity

manifest.vector_descriptor_sha256
        |
        +---- binds vector_snapshot.json
                         |
                         +---- embedding_identity
                                  |
                                  +---- model digest
                                  +---- Ollama version hash
                                  +---- input transform ID
```

Changing any BGE runtime component changes the descriptor bytes and
therefore the manifest-bound descriptor SHA. A new manifest field would
duplicate an already authenticated relationship.

### Static load validation versus exact runtime validation

Current vector call sites assume
`descriptor.embedding_identity == manifest.embedding_config_hash`.
P13 must replace that assumption deliberately; exposing the identity on
`NumpyVectorStore` alone is insufficient.

The offline BGE matcher parses the descriptor identity and validates:

1. the full descriptor remains bound by the manifest/operational
   descriptor SHA, generation, byte counts, row count, and dimensions;
2. the identity grammar is exact;
3. its config-hash segment equals
   `manifest.embedding_config_hash`.

It does not contact Ollama. Once that relationship passes,
`read_v5_vector_snapshot`, `_load_validated_v5_vector_tuple`,
`_prepared_external_validator`, `_external_v5_validator`, and bound
snapshot loads pass the descriptor's **actual** runtime identity into
the vector store's existing exact-identity check. The generic vector
store does not gain a permissive predicate.

The live comparison is separate: index/refresh compare the actual
descriptor identity to the attested provider identity before reuse;
query compares it before embedding and again confirms the provider
postflight before search.

### Lifecycle rules

**Authoritative index**

- Resolve the live BGE identity before deciding whether vectors can be
  reused.
- If no BGE index exists, embed and publish with that identity.
- If the stored BGE identity is legacy, malformed, or differs from the
  live identity, force a complete vector reindex.
- All batches in one index operation use the same attested provider
  instance.
- After the final embed, force a fresh attestation before freezing or
  publishing. Drift abandons the prepared generation.

**Incremental refresh**

- Resolve the live BGE identity even when source inventory appears
  quiet.
- Exact identity match permits the existing no-op/incremental path.
- Mismatch routes to authoritative reindex; it must not reuse old rows
  and append new-runtime rows.
- Any embedding path performs the same pre-publication postflight as
  authoritative indexing. A true no-op performs only the initial live
  identity comparison because it creates no vectors.
- Existing egress tracking surrounds all BGE preflight/postflight calls:
  request started but no response is `possible`; any response is
  `performed`. A BGE quiet refresh is therefore no longer reported as
  `not_attempted`.

**Query**

- Load and manifest-validate the persisted descriptor offline.
- Expose its `embedding_identity` on the loaded
  `NumpyVectorStore`.
- Before embedding query variants, attest the live BGE provider and
  compare the exact runtime identity.
- After all variants are embedded, force a fresh attestation before
  the first local vector search.
- A mismatch raises `bge_runtime_mismatch` with “reindex required”
  semantics before vector search. It never degrades to lexical-only or
  hash.

**Status/index health**

- Remains read-only and network-free.
- For BGE, parse the descriptor identity, validate its grammar, and
  require its config-hash segment to equal the manifest config hash.
- Legacy config-hash-only BGE descriptors are reported as requiring an
  authoritative reindex.
- Only index/query/live-integration operations claim that the current
  Ollama runtime matches the persisted identity.

**Hash and openai-compatible**

- Continue storing the plain config hash as descriptor identity.
- Do not preflight or change their query/index flow in P13.

## Atomicity and Concurrency

- Preflight, embedding, and forced postflight happen before
  manifest/descriptor publication.
- If any batch fails after earlier batches succeeded, the prepared
  generation is abandoned and the previously published manifest,
  descriptor, vector files, SQLite binding, and query results remain
  readable and unchanged.
- The cached preflight identity is immutable for one provider instance.
  P13 does not poll between internal batches, but it performs one forced
  production postflight after the complete embed interval.
- Capture infrastructure performs a third, post-publication
  attestation. If digest/version changed, the capture is invalid and
  the experiment stops.

## Compatibility and Migration

| existing index | P13 behavior |
| --- | --- |
| hash descriptor with config hash | unchanged and queryable |
| openai-compatible descriptor with config hash | unchanged and queryable |
| BGE descriptor containing only config hash | healthy files remain intact; query reports `bge_reindex_required`; next authoritative index rebuilds vectors |
| BGE v1 attested descriptor, exact live match | reusable/queryable |
| BGE v1 attested descriptor, model/runtime mismatch | no mixed search; authoritative reindex required |
| malformed BGE identity | integrity failure; no query |

There is no in-place descriptor-only migration because old BGE vectors
cannot prove which digest, runtime, or transform created them.

## Verification Strategy

### Reproducible measurement boundary

The existing real-project acceptance capture advances from schema v3
to provider-discriminated schema v4. Historical v3 evidence is not
rewritten:

| provider | v4 identity contract |
| --- | --- |
| `hash` | static config identity and descriptor identity required; canonical model, digest, Ollama version, transform ID, and post-capture attestation are explicitly `null`; zero Ollama calls |
| `bge` | static config identity plus canonical model, digest, raw Ollama version, `bge-input-v1`, exact descriptor identity, and matching pre/post attestation all required |

`tests/p13_bge_provider_measurement.py` is a tracked, unit-tested outer
envelope (`p13-bge-provider-measurement-v1`) used only for the
old-provider/current-provider cost comparison. Its controller never
imports a target package. Every individual capture runs in a fresh
child process with only that target root's `src` and `tests` prepended
to `PYTHONPATH`; the child asserts that the package, BGE provider, and
target runner `__file__` values resolve inside that root and records
their relative paths and SHA-256 values. The child wraps that root's
`_embed_batch` only to count calls; it does not alter input, batching,
response, or timing scope. Legacy mode is accepted only for a clean
detached worktree at
`122ed052284fa488943cb4464301a391bd2e7e24` and records the old P11
runner's `p11-runner-head-4000` transform. Native mode rejects that
marker and records `bge-input-v1`.

The harness records its own SHA, target runner SHA, implementation
identity, live identity, effective transform, request counts, and
timing. Its paired command alternates baseline/candidate execution and
warms the same pinned model before every capture. The controller
performs proxy-bypassed live attestation immediately before and after
each child and invalidates the pair on drift; this also guards the
legacy implementation, which has no production postflight. Schema v3
is accepted only as nested legacy input to this envelope and is never
accepted by native schema-v4 validation. Thus the accepted legacy
workaround can measure the old provider without entering candidate
correctness or quality evidence.

### Engineering-readiness gates (all required)

1. Fixed Python 3.13 runtime suite passes with no pin changes. The five
   known P6 `sysctl` nodes may be executed outside a restricted runner,
   but may not be skipped from the final accounting.
2. Unit contract covers URL selection, proxy bypass, exact model
   resolution, digest/version validation, transform boundaries,
   batching/order, `truncate: false`, and every response/error branch.
3. The known 6,924-character dense-CJK product path indexes without
   runner monkeypatching.
4. The same text embedded alone and in a batch has cosine similarity
   at least `0.999999` and maximum absolute component difference at
   most `1e-5`.
5. Two live captures have identical non-timing membership and metrics.
6. Model digest, Ollama version, or transform identity drift before,
   during, or after embedding is rejected before publication/search.
7. A failure on batch N leaves the previously published snapshot and
   query behavior unchanged.
8. No tested exception or log contains the raw sentinel source/query
   text.
9. Against the pre-P13 provider in a detached baseline worktree:
   - candidate embed request count is non-increasing per repository and
     strictly lower in aggregate;
   - candidate median index wall time over three warm captures is no
     more than `1.10x` baseline;
   - candidate query p95 is no more than `1.15x` the current-BGE
     baseline.
10. Live Ollama `bge-m3` integration passes. If unavailable, the final
    engineering disposition is `BLOCKED`, never inferred from mocks.

Engineering gates do not compare BGE retrieval quality to hash. They
answer whether the provider implementation itself is sound.

### Product-recommendation gates (all required)

Run paired hash and hardened-BGE captures from the same P13 code,
source snapshots, gold, planner state, and retrieval configuration.

1. Combined frozen P11 Recall@12 is non-decreasing.
2. No previously satisfied required item is lost.
3. At least one required item is newly satisfied.
4. Noise ratio does not increase.
5. Existing P1 BGE profile outcomes do not regress.
6. BGE/hash query p95 ratio is at most `1.50`.
7. BGE/hash index-wall-time ratio is at most `50` on each frozen real
   repository.
8. Capture-twice non-timing results are identical.

The `50x` paired index ceiling is deliberately much lower than P11's
~115x/~153x evidence but still recognizes that a local neural provider
is more expensive than hashing. It is a recommendation gate, not a
universal service-level promise.

The engineering `1.10x` index and `1.15x` query limits are explicit
experiment budgets, not a “no slower” claim. Before candidate results
are visible, the three old-provider captures must themselves have
max/min spread no greater than 10% for index median and 15% for query
p95; otherwise timing comparison is BLOCKED as unstable, and the
budgets are not widened. The recommendation query ceiling uses the
quality system's existing “more than 50%” latency-warning boundary.
The `50x` index ceiling is the pre-committed P13 target for reducing the
observed 115x–153x paired cost.

No threshold is tuned after seeing the comparison. No failed quality
gate is repaired by changing ranking, quotas, planner behavior, gold,
or the input transform.

### Outcome matrix

| engineering | recommendation | disposition |
| --- | --- | --- |
| pass | pass | merge as supported opt-in; document as recommended for measured multilingual/quality-sensitive workloads; hash remains default |
| pass | fail | merge as supported opt-in/experimental; publish costs and failed gates; make no quality recommendation |
| fail | not run or fail | reject P13 implementation; retain current provider and the runner workaround until a new design |
| blocked by live service | not run | report BLOCKED; unit/mock results are not a ship decision |

## Planned Change Surface

| path | responsibility |
| --- | --- |
| `src/context_search_tool/embeddings_bge.py` | transport, preflight, attestation, transform, batching, validation, safe errors |
| `src/context_search_tool/embeddings.py` | narrow runtime-identity helper/protocol seam; hash/openai behavior unchanged |
| `src/context_search_tool/vector_store.py` | retain loaded descriptor identity and expose it read-only |
| `src/context_search_tool/indexer.py` | distinguish static config hash from vector runtime identity; reindex on BGE drift |
| `src/context_search_tool/retrieval_core/candidates.py` | exact live-vs-indexed identity check before semantic search |
| `src/context_search_tool/index_health.py` | offline BGE identity grammar/config binding and legacy migration diagnosis |
| `tests/test_embeddings_bge.py` | complete provider contract and live integration |
| `tests/test_embeddings_vector_store.py` | loaded identity and bound descriptor checks |
| `tests/test_indexer_manifest.py` | descriptor/manifest identity chain and authoritative migration |
| `tests/test_incremental_refresh.py` | quiet refresh drift and failure atomicity |
| `tests/test_retrieval_pipeline.py` | query drift rejection, no fallback, privacy |
| `tests/test_index_health.py` | offline identity parsing, legacy diagnosis, zero-network status |
| `tests/test_p5_privacy.py` | safe errors, proxy bypass, and honest egress outcome |
| `tests/p8_real_python_graphs_acceptance.py` | remove monkeypatch; record raw runtime identity and request/timing evidence |
| `tests/test_p8_real_python_graphs_acceptance.py` | capture identity schema and no-workaround tests |
| `tests/p13_bge_provider_measurement.py` | reproducible detached-baseline/current-provider measurement envelope |
| `tests/test_p13_bge_provider_measurement.py` | measurement mode, instrumentation, identity, and source guards |
| `README.md`, `docs/retrieval-quality.md` | final disposition, setup, migration, real cost; only after evidence |

No manifest schema change, retrieval-policy change, configuration-field
addition, or gold update is planned.

## Rejected Alternatives

### Keep the acceptance-runner monkeypatch

It does not protect production, is not identity-bound, and drops the
most useful suffix. Rejected.

### Rely on Ollama's default truncation

The transformation would be server/version-dependent and invisible in
the index identity. Rejected; P13 sends `truncate: false`.

### Store only the model name

`bge-m3:latest` is mutable. The same name can produce incompatible
index/query vectors after a pull. Rejected.

### Add manifest v3

Manifest v2 already hashes the full descriptor. Adding duplicate
runtime fields broadens migration and validation code without adding an
authentication edge. Rejected for v1.

### Make all embedding providers runtime-attested

That would turn a BGE repair into a provider-framework rewrite.
OpenAI-compatible endpoints have different model-version semantics.
Deferred.

### Retry failed batches or fall back to hash

Retries complicate failure attribution and can mix service states;
fallback would mix vector spaces or silently change configured
behavior. Rejected.

### Promote BGE based on the P11 control alone

The quality gain was small and indexing cost was extreme. P13 requires
paired post-hardening evidence. Rejected.

## Risks

- **4,000 code points is model-specific, not a token proof.** Sending
  `truncate: false` converts remaining overflow into a visible failure.
  A future token-aware transform requires a new transform ID and full
  reindex.
- **Ollama upgrades may force expensive reindexing.** v1 chooses
  reproducibility over reuse because runtime changes are not proven
  vector-compatible.
- **Larger eight-text requests may increase tail latency or memory.**
  The current-provider paired performance gate decides this.
- **Version/tag endpoints may differ on unsupported Ollama releases.**
  P13 fails closed and documents the minimum tested version; it does
  not guess.
- **Live timing is noisy.** Use the same host, warm model, paired
  sources, request counts, three captures, and median/p95 reporting.

## Official Ollama Contract References

- [Ollama `/api/embed`](https://docs.ollama.com/api/embed): string or
  array input and explicit `truncate` behavior.
- [Ollama embedding capabilities](https://docs.ollama.com/capabilities/embeddings):
  use the same model for indexing and querying, batch inputs, and
  unit-length vectors.
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility):
  not selected for P13; the native endpoint remains the narrower
  existing integration.
