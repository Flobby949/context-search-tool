# P6 Freshness, Performance, And Large Repositories Design

Date: 2026-07-18
Status: Reviewed — ready for user approval and implementation planning
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Roadmap phase: Phase 6

## Summary

P6 makes Context Search Tool operationally trustworthy for larger repositories
and repeated agent use. It does not add a new retrieval model, language plugin,
or product surface. It establishes three contracts that can be tested
independently:

1. **Freshness truth:** an agent can distinguish a missing, stale, degraded,
   metadata-fresh, and content-verified index and can see exactly what evidence
   supports that conclusion.
2. **Incremental refresh:** a quick refresh walks repository metadata but reads,
   parses, and embeds only directly dirty paths or unchanged paths with a
   declared dependency invalidation reason; the existing authoritative index
   operation keeps a full-content verification path.
3. **Measured scalability:** profiling identifies the actual SQLite, vector,
   indexing, startup, and memory costs before any storage rewrite, approximate
   index, or resident service is selected.

The design deliberately separates observation from mutation. `status` and
`stats` are read-only. A new explicit `refresh` operation performs the lazy,
metadata-guided update. The existing `index` operation remains the authoritative
verified update and keeps its current safety meaning. Query, context, trace, and
explore do not silently mutate an index or transmit source to a remote embedding
provider.

P6 implementation may begin only from a clean commit that includes the pending
P5 path-inventory incremental fix and passes the P5 protected gates. This draft
does not assign that not-yet-created commit hash. The current working tree is
therefore sufficient for P6 design, but not yet the implementation baseline.

This document does not authorize implementation. A reviewed implementation plan
is required after this design is approved.

## Roadmap Contract

The Phase 6 roadmap requires:

- expanded `status` and `stats` for freshness, stale files, skipped files,
  vector coverage, embedding configuration, and index health;
- profiling of full-scan paths in SQLite and vector search;
- vector optimization or an approximate index only when profiling proves it is
  necessary;
- lazy refresh for files touched since the last successful index;
- consideration of service/watch mode only after status and incremental refresh
  are reliable.

P6 is complete only when agents can decide whether an index is fresh enough for
a query, the large-repository workload meets explicit latency and memory
budgets, and incremental recovery is proven before any daemon-style work.

## Entry Gate And Protected Baseline

P5 is functionally accepted, including schema-v5 graph lifecycle, immutable
vector generations, exclusive writer locking, deterministic and pinned-real
quality gates, and stale-graph retrieval degradation. One post-acceptance bug
fix is currently uncommitted: file additions and deletions must re-materialize
unchanged `imports` and `routes_to` sources whose resolution depends on the
active path inventory.

Before the P6 implementation plan is executed:

1. commit that fix as an isolated P5 correction;
2. record the resulting implementation commit as the P6 baseline;
3. rerun the focused incremental cases, deterministic P5 12/12, pinned-real P5
   2/2, P4 4/4, P2 5/5, raw CI 8/8, and the full suite with the audited skip
   identities;
4. preserve the P5 structural projections, protected-direct behavior,
   no-legal-edge behavior, ContextPack v2, RetrievalTrace v1, and
   ExplorationTrace v2 contracts.

P6 may add operational schema and output fields. It must not silently refresh a
protected quality baseline to accommodate ranking changes.

## Current Evidence

### Freshness And Status

The current CLI `status` checks only whether four legacy filenames exist:
`index.sqlite`, `manifest.json`, `vectors.npy`, and `vector_ids.json`. Schema-v5
publishes generation-qualified vector files behind `vector_snapshot.json`, so
the current status can report a healthy v5 index as missing its legacy vector
files and cannot answer whether repository content changed.

CLI `stats` and MCP `context_search_stats` report source/chunk/symbol/token
counts, disk usage, and embedding provider/model/dimensions. They do not report:

- source freshness or the evidence level used to assess it;
- added, changed, deleted, unreadable, or skipped paths;
- graph readiness and stale reason in the payload;
- manifest/config/schema compatibility;
- vector descriptor validity, coverage, or exact ID agreement;
- whether an index writer is active;
- whether the next update can be incremental or requires a full rebuild.

The read-only paths currently call `load_config()`, which can create
`.context-search/config.toml`. P6 status inspection must instead use a
non-creating read path.

### Incremental Indexing

Schema-v5 indexing is already content-incremental after discovery:

- every eligible file is safely read and SHA-256 hashed;
- stored source hashes and project-unit metadata determine changed paths;
- only selected files are parsed and embedded;
- deletions are removed, immutable vector generations are published, and graph
  readiness is committed only after validation;
- one exclusive writer is allowed while readers retain a committed SQLite
  snapshot.

This is reliable but not a lazy scan: even a no-op index reads every eligible
file body, validates the full vector generation, and reconstructs repository
path context. On a large repository, the no-op path can be dominated by source
I/O and vector validation despite parsing and embedding zero files.

The pending P5 fix also exposes an important rule for P6: a file-body delta and
a path-inventory delta are different invalidation classes. Adding or deleting a
target can change the resolution of unchanged import/router sources, so dirty
work is not always identical to directly touched files.

### Query Full-Scan Paths

The current query pipeline includes several costs that scale with all active
rows:

- a published vector generation is hash-validated and loaded for each CLI/MCP
  process invocation;
- `NumpyVectorStore.search()` normalizes the full matrix and fully sorts all
  scores for each query variant;
- path/symbol recall fetches every active chunk path, every active token row,
  and every active symbol row into Python;
- direct-text recall fetches every active chunk path and body into Python;
- signal recall fetches every active recallable signal and scans serialized
  metadata in Python;
- planner hints can repeat path/symbol and signal work;
- repository profile construction runs even when the planner is disabled and
  aggregates source paths, symbols, and tokens across their active tables;
- query startup materializes the complete active embedding-ID set and complete
  deleted chunk-ID set;
- every mutating index pass resolves the full persisted relation set and
  regenerates all test associations, even for a one-file edit;
- a one-file vector change loads, copies, sorts, writes, and repeatedly hashes
  the complete vector matrix and ID list;
- `PluginContext` canonicalizes the complete active path and unit collections
  for each rebuilt file, and frontend relation materialization repeatedly builds
  full active-path sets.

Repeated updates also have an unbounded maintenance risk today. Each non-no-op
publish creates a generation-qualified vector/ID pair with no reclamation
protocol, while soft-deleted chunks/signals/relations can accumulate. Querying
then materializes all deleted chunk IDs. P6 must measure and bound steady-state
churn, not only one clean snapshot.

SQLite FTS lexical recall is already bounded and indexed. P6 must profile these
paths separately rather than treating “SQLite search” as one undifferentiated
cost.

### Existing Performance Evidence

RetrievalTrace v1 records stage timings, and the quality reports aggregate query
latency. One unit test asserts that a 1,000-chunk direct-text scan completes
under 100 ms on its CI environment. These are useful signals, but they are not a
large-repository performance contract:

- there is no fixed generated workload or environment record;
- startup, vector tuple validation, and peak RSS are not isolated;
- current timing tests mix correctness and wall-clock assumptions;
- there is no cold/warm distinction, scaling ratio, or work counter;
- P5 explicitly made no P6 latency claim.

## Goals

1. Give CLI users and MCP agents one versioned, machine-readable health model.
2. State the difference between metadata freshness and content verification
   without ever promoting the former to a cryptographic claim.
3. Report bounded path samples plus complete counts for stale and skipped
   categories.
4. Keep status/stats read-only, no-fetch, and non-creating.
5. Preserve the authoritative verified `index` operation.
6. Add an explicit metadata-guided `refresh` operation that avoids unchanged
   file-body reads, parsing, embedding, and vector rewrites when possible.
7. Handle direct file changes, additions/deletions, path-dependent graph
   invalidation, project topology, configuration, schema, and integrity as
   distinct refresh reasons.
8. Measure cold/warm latency, stage cost, bytes read, rows visited, work counts,
   disk size, and peak RSS on deterministic repository tiers.
9. Remove proven full-scan or quadratic work with exact-result behavior first.
10. Establish a documented go/no-go decision for approximate vector search and
    for service/watch mode.
11. Preserve P0-P5 quality, privacy, lifecycle, output, and failure contracts.
12. Bound immutable-vector generations, SQLite tombstones, temporary disk high
    water, and latency drift under repeated incremental churn.

## Non-Goals

- Closing the independently pending Phase 1 cross-language quality gate.
- Adding languages, framework parsers, graph relation kinds, ranking features,
  query-planner behavior, or another model call.
- Changing ContextPack v2, RetrievalTrace v1, ExplorationTrace v2, or the raw
  query result schema merely to carry health data.
- Automatically refreshing during query/context/trace/explore.
- Making a read operation send source code to a local or remote embedding
  provider.
- Claiming that a metadata-only scan detects adversarial timestamp preservation.
- Selecting HNSW, IVF, a vector database, SQLite BLOB storage, or another ANN
  implementation before the exact-search profile crosses the reviewed trigger.
- Shipping a daemon, filesystem watcher, dashboard, or long-running MCP cache in
  the baseline P6 implementation.
- Treating ignored descendants, vendor trees, or unsupported binary assets as
  missing indexed source.
- Promising a universal latency number across arbitrary disks, CPUs, embedding
  providers, planners, or repository contents.

## Design Principles

### Truth Before Convenience

Every freshness assertion names its evidence. “Metadata fresh” means path
inventory and stable metadata match the last successful observation. “Verified
fresh” means eligible source content was safely read and matched stored hashes.
Neither label is shortened to an ambiguous bare `fresh` in machine output.

### Read-Only Means No Mutation

Status and stats do not create config, acquire a writer lock, update access
times intentionally, mark graph state, repair a manifest, write caches, append
feedback, call embeddings, or fetch from the network. A damaged index is
reported, not repaired by inspection.

### Explicit Mutation

Agents may call `refresh` when metadata freshness is sufficient for their
workflow or `index` when they require content verification. Query surfaces do
not guess whether remote embedding cost or repository writes are acceptable.

### Exact Optimization Before Approximation

P6 first removes repeated normalization, unbounded row materialization,
avoidable full sorts, and per-file repository-context reconstruction. ANN is a
separate reviewed decision, not an assumed phase deliverable.

### Work Proofs Before Stopwatch Proofs

CI primarily asserts bounded calls, rows, bytes, and asymptotic behavior.
Wall-clock and RSS gates run in a recorded acceptance environment with warmup,
repetition, and raw samples. This keeps functional CI deterministic without
abandoning real performance evidence.

## Terminology

| term | meaning |
| --- | --- |
| eligible path | repository-relative regular non-symlink file allowed by include/exclude/gitignore/default rules and recognized by a source plugin |
| indexed path | eligible path represented by an active `source_files` row after the last ready commit |
| coverage skip | otherwise eligible source that cannot be indexed because it is too large, binary, unreadable, unsafe, or changed during a safe read |
| excluded path | ignored, internal, vendor/default-directory, explicitly excluded, or unsupported-language path; it is not missing index coverage |
| metadata observation | stable path, type, size, `mtime_ns`, and best-effort `ctime_ns`/platform change token captured without reading the body |
| complete inventory | every traversable repository subtree and freshness-affecting control file was observed without an unclassified traversal error |
| incomplete inventory | one or more subtrees or control files could not be observed; deletion and fresh-state inference are forbidden for that operation |
| metadata fresh | current eligible inventory and metadata observations equal the last ready observations |
| verified fresh | a complete safe content scan proves current SHA-256 values and inventory equal the ready index |
| dirty path | added, deleted, metadata-changed, content-changed, newly skipped, or recovered path requiring refresh work |
| dependent rebuild | unchanged source re-materialized because topology or active-path resolution changed |
| quick inspection | metadata, schema, descriptor, and count checks that avoid source/vector full-file hashing |
| verified inspection | quick inspection plus eligible source hashing, SQLite integrity checks, and exact vector tuple validation |
| retryable skip | transient `unreadable` or `changed_during_read` observation that quick refresh retries under a fixed fairness budget even if metadata is unchanged |

## Freshness And Health Model

### Independent Axes

One enum cannot truthfully represent every condition. The internal report keeps
five independent axes and derives a concise overall state:

1. `availability`: `missing | present | incompatible | corrupt`;
2. `freshness.status`: `unknown | stale | metadata_fresh | verified_fresh`;
3. `coverage.status`: `unknown | complete | degraded`;
4. `integrity.status`: `unchecked | valid_quick | valid_verified | invalid`.
5. `inventory.status`: `not_inspected | complete | incomplete`.

`writer.active` is orthogonal and has type `bool | null`; `null` means the
platform-safe lock probe could not decide. A writer can be active while readers
see a committed stale snapshot. It does not replace the five axes.

The derived `health` function uses this exact priority:
`missing > incompatible > corrupt > stale > degraded > healthy_verified >
healthy_metadata`. `corrupt` requires a confirmed invariant/digest/schema
failure while the SQLite ready generation and external small-file identities
remain stable across the inspection. Writer activity, generation drift,
incomplete traversal, and an interrupted verification are `unchecked`, never
`invalid`, and cannot derive `corrupt`.

The values are:

| health | derivation | query guidance |
| --- | --- | --- |
| `missing` | no SQLite index | run `index` |
| `incompatible` | future/unsupported schema or embedding contract | use a compatible CST or explicitly rebuild |
| `corrupt` | stable committed artifact identities fail confirmed validation | run authoritative `index`; do not claim semantic coverage |
| `stale` | direct/config/topology delta, committed stale graph, or incomplete inventory prevents equality proof | preserve old rows; `refresh` only when its legality matrix permits, otherwise `index` |
| `degraded` | snapshot is queryable but coverage skips, pending skip inspection/retry, or interrupted integrity evidence reduce confidence | query is allowed with explicit warnings; inspect reasons |
| `healthy_metadata` | queryable, complete, metadata-equal, quick integrity valid | suitable for normal editor/agent writes, not adversarial timestamp preservation |
| `healthy_verified` | queryable, complete, content-equal, verified integrity valid | strongest local freshness claim |

`queryable=true` means current inspection evidence found no P5 query blocker; it
is not a verified guarantee when payload content was not inspected and is not a
statement that the workspace is current. `queryability_evidence` is
`none | committed_snapshot_quick | committed_snapshot_verified | unknown`.
The machine report never emits generic `healthy` or `fresh` without its evidence
level.

After the top three priority states (`missing`, `incompatible`, confirmed
`corrupt`), the remaining combinations are total and deterministic:

| committed/in-flight evidence | freshness | integrity | health | action |
| --- | --- | --- | --- | --- |
| graph committed stale or unfinished file marker | `stale` | quick/verified result if available | `stale` | reason matrix chooses refresh/index |
| inventory incomplete | `unknown` | `unchecked` | `stale` | retry inspection; never delete |
| ready snapshot plus current workspace delta | `stale` | quick/verified result | `stale` | refresh/index |
| ready snapshot plus writer active or ready-generation drift | `unknown` | `unchecked` | `degraded` | retry inspection |
| already-stale snapshot plus writer/drift | `stale` | `unchecked` | `stale` | retry after writer, then reason matrix |
| writer state unknown, generations stable | otherwise derived freshness | `unchecked` | `degraded` | retry inspection for stronger claim |
| ready/stable plus coverage degraded/pending | otherwise derived freshness | quick/verified result | `degraded` | query with warning or repair coverage |
| ready/stable/complete/valid | metadata or verified fresh | matching valid level | matching `healthy_*` | query |

### Versioned Report

The canonical internal and JSON/MCP object is `IndexHealthReport v1`. Field
ordering is canonical for golden tests, but consumers must use names rather than
order.

```json
{
  "schema_version": 1,
  "health": "healthy_metadata",
  "queryable": true,
  "queryability_evidence": "committed_snapshot_quick",
  "availability": "present",
  "observation": {
    "started_at_epoch_ms": 0,
    "completed_at_epoch_ms": 0,
    "inventory_status": "complete",
    "unscannable_subtree_count": 0,
    "control_file_error_count": 0,
    "change_token_kind": "mtime_ns+ctime_ns",
    "limitations": [
      "metadata_not_content_proof",
      "vector_payload_content_not_verified"
    ]
  },
  "freshness": {
    "status": "metadata_fresh",
    "inspection_mode": "quick",
    "indexed_at_epoch_s": 0,
    "age_seconds": 0,
    "added": 0,
    "changed": 0,
    "deleted": 0,
    "metadata_unchanged": 0,
    "content_verified": 0,
    "samples": [],
    "sample_limit": 20,
    "sampled_total": 0,
    "evidence_generation": ""
  },
  "coverage": {
    "status": "complete",
    "evidence": "ready_snapshot",
    "indexed_files": 0,
    "coverage_skips": 0,
    "pending_inspection": 0,
    "pending_retry": 0,
    "skip_counts": {},
    "skip_samples": [],
    "excluded_counts": {}
  },
  "integrity": {
    "status": "valid_quick",
    "manifest": "valid",
    "sqlite": "valid_quick",
    "graph": "ready",
    "graph_stale_reason": "",
    "vector": "valid_identity_and_size"
  },
  "vectors": {
    "generation": "",
    "eligible_chunks": 0,
    "rows": 0,
    "coverage_ratio": 1.0,
    "coverage_evidence": "count_only",
    "missing_ids": null,
    "orphan_ids": null,
    "dimensions": 384
  },
  "indexed_embedding": {
    "status": "valid",
    "provider": "hash",
    "model": "hash-v1",
    "dimensions": 384,
    "config_hash": "",
    "network_egress_capable": false,
    "network_egress_evidence": "built_in_hash"
  },
  "configured_embedding": {
    "status": "valid",
    "provider": "hash",
    "model": "hash-v1",
    "dimensions": 384,
    "config_hash": "",
    "network_egress_capable": false,
    "network_egress_evidence": "built_in_hash"
  },
  "embedding_config_match": true,
  "refresh": {
    "required": false,
    "kind": "none",
    "reasons": [],
    "recommended_action": "query"
  },
  "writer": {
    "active": false,
    "state": "idle",
    "evidence": "lock_probe"
  },
  "diagnostics": []
}
```

`freshness.samples` items are closed objects with `category`, `path`, and
`reason`; skip samples use `path`, `reason`, and `retryable`; diagnostics use
`code`, `scope`, and an optional repository-relative `path`. Categories,
reasons, diagnostic codes, `refresh.kind` (`none | quick | authoritative`), and
`recommended_action` (`query | refresh | index | retry_inspection |
use_compatible_version`) are frozen by schema-v1 tests and sorted by their
declared canonical order, then path. Unknown values require a report schema
bump.

Schema v1 freezes sample categories `added | changed | deleted |
metadata_only | pending_inspection`; refresh reasons `source_changed |
path_inventory_changed | coverage_changed | index_config_changed |
embedding_config_changed | topology_changed | graph_stale | manifest_upgrade |
integrity_failed | inventory_incomplete`; and diagnostic codes
`legacy_manifest | inventory_incomplete | unscannable_subtree |
control_file_error | writer_state_unknown | inspection_interrupted |
verification_interrupted | vector_payload_unverified | manifest_identity_mismatch |
vector_identity_mismatch | orphan_generation | coverage_pending`. Multiple
reasons use this declaration order; path-bearing items then use POSIX path order.

`indexed_embedding` is read from the bound ready manifest and describes what the
current vectors used. `configured_embedding` is read only after schema preflight
from the current non-creating config reader and describes what the next
authoritative index would use. Each has `status=valid | missing | invalid |
not_inspected`; only the built-in hash provider is egress-false. Missing,
invalid, unknown-provider, and deliberately not-inspected configuration is
fail-closed as `network_egress_capable=true` with the corresponding evidence
code. `provider`, `model`, `dimensions`, and `config_hash` are nullable exactly
when `status != valid`; they are never guessed from the current configuration
for `indexed_embedding`. `embedding_config_match` is `true | false | null`, with
`null` whenever either identity is not valid. The existing MCP stats top-level
`embedding` retains its indexed meaning.

Every `IndexHealthReport v1` key shown above is required. Unknown evidence is
represented explicitly rather than by omitting a key: unavailable timestamps,
ages, counts, dimensions, vector coverage, and generation-bound values are
`null`; evidence-bearing arrays and closed count maps are `null` when not
inspected and are empty only when inspection proved there are no entries. A
missing index uses `indexed_embedding.status=missing` and
`configured_embedding.status=not_inspected`. A future schema uses
`status=not_inspected` for every identity that cannot be interpreted safely.
These rules let the same exact report shape represent missing and incompatible
states without crossing schema-first preflight.

Schema v1 also closes the explanatory leaf values:

| field | allowed values |
| --- | --- |
| `freshness.inspection_mode` | `none | quick | verified` |
| `coverage.evidence` | `not_inspected | ready_snapshot | verified_workspace` |
| `vectors.coverage_evidence` | `not_inspected | count_only | exact_ids` |
| `integrity.manifest` | `missing | not_inspected | valid | incompatible | invalid` |
| `integrity.sqlite` | `missing | not_inspected | valid_quick | valid_verified | incompatible | invalid` |
| `integrity.graph` | `missing | not_inspected | ready | stale | unfinished | incompatible | invalid` |
| `integrity.vector` | `missing | not_inspected | valid_identity_and_size | valid_exact | incompatible | invalid` |
| `writer.state` | `idle | active | unknown | not_inspected` |
| `writer.evidence` | `lock_probe | lock_probe_unavailable | generation_drift | not_inspected` |
| `network_egress_evidence` | `built_in_hash | configured_network_provider | unknown_provider | index_missing | config_missing | config_invalid | not_inspected` |

For missing/future preflight, `inspection_mode=none`, unobserved
evidence-bearing collections are `null`, and `writer.active=null` with
`state/evidence=not_inspected`. Golden payloads freeze these cases; implementations
cannot substitute empty collections or inferred configuration.

Timestamps bound an observation interval; they do not prove the workspace stayed
unchanged after `completed_at_epoch_ms`. `age_seconds` helps an agent apply its
own risk tolerance but never turns an unchanged snapshot stale by itself.

### Quick Inspection

Quick inspection performs bounded-memory work:

1. resolve the top-level repository root as P5 does, then reject/fail closed on
   symlinks below that root during traversal;
2. without reading config, inspect index existence, raw manifest version, and
   SQLite graph/operational schema through a minimal read-only capability probe;
3. return missing/future state immediately; no config/provider/feedback/profile
   code is crossed;
4. only for readable schemas, read configuration without creating it;
5. open an initial committed SQLite read snapshot and inspect supported schemas,
   readiness metadata, counts, last-ready observation generation, and unfinished
   file marker;
6. read SQLite's expected manifest/descriptor generation and digest, hash those
   small files, and compare their exact identities without hashing/loading the
   vector payload;
7. validate descriptor paths/generation names, referenced-file existence,
   regular/non-symlink type, owner/safety rules, and descriptor-bound byte sizes;
8. perform opening and closing `followlinks=False` inventory passes, capturing
   `os.walk` traversal errors and freshness-affecting control-file errors rather
   than silently dropping subtrees;
9. compare eligible observations with ready rows and derive additions,
   deletions, metadata changes, topology/config invalidation, ready-snapshot
   coverage, and count-only vector coverage;
10. after external and inventory checks, open a second short SQLite snapshot and
   require the same unique ready generation/bound identities;
11. probe writer-lock state without creating/modifying it; unsupported or racy
   platform probes return `active=null,state=unknown`, not a false idle value.

This schema-first preflight is shared by status, stats, refresh, and index. Index
may create/read normal configuration only after proving the persisted schemas are
not future. It preserves the existing future-signal guarantee that config,
provider, feedback, profile, scan, and mutation work is zero.

Quick inspection is `O(entries + indexed paths)` and reads no eligible source
body. It may read bounded control files such as `.gitignore`, config, manifest,
and the vector descriptor through the existing safe path rules. If either
inventory pass is incomplete, it reports every known unscannable subtree/control
error, does not infer deletions below it, sets freshness to `unknown` with health
`stale`, and cannot produce a fresh claim.

### Verified Inspection

`--verify` extends the same snapshot with:

- safe streaming SHA-256 of every eligible source file;
- detection of same-size/same-time content changes;
- SQLite `PRAGMA quick_check` and exact required metadata validation;
- vector descriptor SHA validation, exact vector-ID/active-embedding-ID equality,
  shape, row count, dimensions, and embedding identity;
- exact source-content and observation fingerprints.

Verified inspection retains at most one bounded file body buffer at a time and
does not parse or embed source. Its opening inventory, per-file stable reads, and
closing inventory define the reported observation interval. Any eligible path,
metadata, control-file, ready-generation, manifest identity, or descriptor
identity drift makes the attempt `integrity.status=unchecked` with
`verification_interrupted`; it never becomes corruption. A confirmed digest,
shape, schema, or exact-ID mismatch against stable bound identities is
`invalid`. No fresh result is emitted from an incomplete or interrupted pass.

### Metadata Limitation

No portable read-only API can prove arbitrary file content unchanged without
reading it or relying on an external change journal. A caller can rewrite bytes,
restore size and `mtime_ns`, and on some platforms evade the available change
token. Therefore:

- quick inspection may return `metadata_fresh` for such an adversarial edit;
- verified inspection must detect it through SHA-256;
- quick `refresh` must report `verification=metadata`, never
  `verification=content`;
- authoritative `index` must continue to detect it;
- tests explicitly demonstrate both outcomes.

### Stale And Skip Samples

Counts are complete only when `inventory.status=complete`; an incomplete report
states the known lower bounds and never converts absent observations into
deletions. Path lists are bounded to
20 canonical repository-relative POSIX paths per category by default, sorted
lexicographically, with `sampled_total` recording the unsampled count. No source
content, environment value, API key, embedding endpoint credentials, absolute
temporary path, or vector value appears in the report.

Skip reasons are closed and machine-stable:

- `too_large`;
- `binary`;
- `unreadable`;
- `unsafe_path`;
- `changed_during_read`;
- `unsupported_encoding` when decoding is required for indexing.

`too_large`, `binary`, `unsupported_encoding`, and an unchanged unsafe path are
stable skips retried after relevant metadata/config change. `unreadable` and
`changed_during_read` are retryable skips. Quick refresh retries at most 32
retryable paths per invocation, oldest observation generation then path first,
and advances a persisted attempt generation without storing exception text. A
no-op zero-body-read claim is legal only when the baseline inventory is complete
and no retryable skip is due. Otherwise coverage is `degraded` with
`evidence=ready_snapshot`, `pending_retry > 0`, and the attempted work is
reported.

Quick inspection cannot discover body-dependent properties of a new or dirty
path without reading it. Such paths count as stale `pending_inspection`, not as
current-workspace coverage skips. Verified inspection or a mutation resolves
them. Thus `coverage.evidence=ready_snapshot | verified_workspace`; it never
pretends a no-body quick pass proved current binary/encoding/readability state.

Ignored/internal/default-directory/config-excluded/unsupported-language counts
are reported separately as exclusions. A pruned directory counts as one pruned
entry; CST does not descend merely to manufacture a huge “skipped files” count.
Excluded/pruned path metadata and counts are informational only and do not enter
the source observation fingerprint. The fingerprint contains eligible
observations, coverage-skip observations, and identities of control files whose
contents affect classification. Churn wholly below an excluded subtree cannot
make an index stale.

An indexed path that becomes a coverage skip is stale and is removed on the next
successful refresh. A new coverage skip makes coverage degraded but cannot be
called missing indexed content because no valid source snapshot was accepted.

## Persistence And Migration

### Manifest v2

P6 bumps the operational manifest from v1 to v2. It does not bump the P5 graph
signal schema from v5. Manifest v2 adds:

- `index_config_hash` for include/exclude/size and scanner-affecting settings;
- `source_content_fingerprint` over canonical `(path, language, sha256)` rows;
- `source_observation_fingerprint` over canonical path classification and
  metadata observations;
- `observation_generation` shared with SQLite ready metadata;
- `manifest_generation`; the final SQLite ready metadata stores the canonical
  digest of the complete serialized manifest payload computed before publication;
- expected vector descriptor schema, generation, canonical descriptor digest,
  vector byte size, and ID-file byte size;
- `indexed_at_epoch_s`;
- `operational_schema_version`;
- last successful operation mode and bounded work metrics;
- existing embedding identity and file/chunk counts.

The fingerprints and small-file identity digests are lowercase SHA-256 of
canonical UTF-8 JSON with sorted keys,
repository-relative POSIX paths, and no timestamps that are not part of the
observation contract. Content and observation fingerprints stay separate so a
mere touch does not masquerade as a source-content change.

### SQLite Operational Schema v1

P6 adds an operational schema version independent of graph schema and adds:

1. stable metadata/change-token columns for indexed source observations;
2. a `scan_skips` table keyed by repository-relative path with closed reason,
   language, size, timestamps/change token, and last observation generation;
3. ready metadata for manifest version, config hash, content/observation
   fingerprints, observation generation, and last operation metrics;
4. in the same final ready transaction, exact expected manifest
   generation/digest and vector descriptor schema/generation/digest/byte sizes;
5. only the search-surface tables or indexes justified by the profile.

Skip rows store no source bytes or exception strings. Diagnostic exception
classes are normalized to the closed reason set.

Vector descriptor v2 adds the vector and ID byte sizes while retaining content
digests, row count, dimensions, and embedding identity. The final SQLite ready
transaction binds the descriptor's canonical small-file digest and generation,
not merely its row count. Quick inspection hashes the small manifest/descriptor,
checks their bound identities and referenced regular-file sizes, and labels ID
set/content agreement `count_only`; verified inspection hashes/loads the payload
and proves exact IDs. A metadata-only refresh may reuse the prior vector
generation but must bind that exact descriptor identity in its new ready
generation.

### v1-to-v2 Behavior

A manifest-v1/schema-v5 index remains queryable under current P5 rules but its
freshness is `unknown` and health is `degraded` until one authoritative verified
`index` run establishes P6 observations. The upgrade:

- hashes all eligible files;
- reuses unchanged chunks, signals, relations, and embeddings;
- fully validates the existing vector payload and may publish descriptor v2
  around the same immutable generation when the ordered vector set is unchanged;
- performs a full rebuild only if existing P5 integrity/config/schema rules
  already require one;
- publishes manifest v2 and operational metadata through the existing stale to
  ready lifecycle;
- is fault-injected so a crash leaves either the prior queryable v1 snapshot or a
  recoverable stale v2 attempt, never false `healthy_verified` state.

A future operational or manifest schema is reported as incompatible before any
mutation. Status can still produce a minimal incompatible report without trying
to interpret unknown rows.

Readers use `READABLE_MANIFEST_VERSIONS = {1, 2}` and dispatch only after parsing
the raw version; writers use `WRITE_MANIFEST_VERSION = 2`. The operational
version and ready-generation bindings become authoritative only in the final
SQLite ready transaction. Merely seeing new DDL is not proof that migration
completed.

### Capability Matrix

| persisted state | query/context/trace/explore | status | stats | quick refresh | authoritative index |
| --- | --- | --- | --- | --- | --- |
| no SQLite index | existing missing-index behavior | `missing`, reportable | preserve existing CLI/MCP missing error | `missing_index`, no mutation | create v2 |
| manifest v1, operational absent, graph v5 ready/stale | readable under exact P5 ready/stale rules | `degraded`, freshness `unknown` | existing counts/embedding fields | `authoritative_index_required` | verified v2 upgrade |
| manifest v2, operational v1, graph ready, identities bound | normal | full quick/verified report | existing fields plus health | allowed by reason matrix | allowed |
| manifest v2, operational v1, graph stale | existing P5 degraded retrieval | `stale` with committed reason | existing stale behavior plus health when readable | allowed only for incremental stale reasons and stable identities | recover |
| v2 DDL exists but operational ready metadata absent/incomplete | DDL alone is ignored: a still-bound manifest-v1/graph-ready snapshot keeps P5 behavior; any v2/stale attempt uses P5 stale degradation | prior-v1 degraded or `stale` migration-incomplete, as bound metadata proves | readable counts only when schema adapter proves safe | `authoritative_index_required` | resume/recover migration |
| future manifest, operational, or graph schema | reject before config/provider/feedback work | minimal `incompatible` report without unknown-row interpretation | preserve incompatible error envelope | incompatible error | incompatible error; never overwrite |
| stable bound identity/digest/integrity failure | fail closed according to affected P5 capability | `corrupt` | sanitized corruption error | `authoritative_index_required` | recover/rebuild |

Future operational schema does not receive a “P5-only” query exception: its
meaning may change snapshot identity, so all query and mutation surfaces reject
it. A generation change observed during inspection is not the stable-corruption
row; it is an interrupted report and may be retried.

Migration creates additive DDL without making it authoritative, then marks stale
before any v2 source/vector/manifest replacement. A crash before stale leaves the
bound v1 snapshot unchanged; a crash after stale is a recoverable migration
attempt. Only the final ready transaction installs operational v1 and v2
external identities together.

## Scanner And Inventory Contract

### Two-Phase Inventory

The scanner is split into:

1. `observe_workspace()`: safe path classification and metadata only;
2. `read_observed_file()`: bounded no-follow read, before/after descriptor and
   path identity checks, binary/encoding classification, and SHA-256.

It returns a `WorkspaceInventory`, not an ambiguous list that loses skip
reasons. The inventory contains sorted eligible observations, closed skip and
exclusion counts, `complete`, canonical `unscannable_subtrees`,
`control_file_errors`, change-token capability, and deterministic diagnostics.
`os.walk(onerror=...)` and every `.gitignore`/config/control-file read must feed
those fields. An incomplete inventory is a hard freshness barrier: no path below
an unscannable subtree is inferred deleted, no previous indexed row is removed,
and no ready/fresh commit occurs. Indexer adapters may expose `ScannedFile`
during migration, but freshness and refresh use the richer model.

### Stable Observation

The best available metadata tuple includes:

- repository-relative normalized path;
- regular-file type;
- size;
- `mtime_ns`;
- `ctime_ns` or platform-equivalent best-effort change token;
- device/inode identity only for in-process race detection, not as a portable
  persisted content identity.

The tuple is sampled before and after relevant reads. A mismatch becomes
`changed_during_read`; it is not silently retried into a mixed snapshot. Reports
also expose `change_token_kind` (`mtime_ns+ctime_ns`, `mtime_ns`, or
`platform_specific`) and the limitation that no token is a content proof.

Freshness is true only for a bounded observation interval:

1. an opening inventory fence records eligible paths, control identities, and
   observations;
2. required bodies are read/hashed/prepared against those observations;
3. a closing full metadata inventory fence repeats path/control/observation
   discovery immediately before publication or report completion;
4. any addition, deletion, observation change, incomplete traversal, or control
   drift returns `workspace_changed`/`verification_interrupted`; mutation keeps
   the previous rows and cannot commit ready.

The closing fence prevents an early-scanned file from changing unnoticed during
the evidence interval. `observation.completed_at_epoch_ms` is captured
immediately after that fence and is not moved forward to manifest publication or
command return. CST cannot lock the user's workspace after the interval ends, so
the report gives both interval timestamps and never claims perpetual freshness.

### Invalidation Classes

The inventory diff returns explicit reasons:

- `content_candidate`: metadata changed and the body must be hashed;
- `added_path`;
- `deleted_path`;
- `coverage_changed`;
- `index_config_changed`;
- `embedding_config_changed`;
- `project_topology_changed`;
- `path_inventory_changed`;
- `schema_or_integrity_rebuild`.

After hashing a `content_candidate`, equal SHA-256 means its body-derived index
does not rebuild, but its ready observation is updated. Additions/deletions feed
the P5 active-path dependent source invalidation. Topology and integrity retain
their stronger P5 rebuild rules.

The legal operation is fixed by reason:

| reason/config class | quick refresh | authoritative index |
| --- | --- | --- |
| include/exclude/max-file-size or freshness-affecting scanner config | reclassify complete inventory; read newly eligible/direct dirty paths | allowed |
| embedding provider/model/dimensions/base identity | reject with `authoritative_index_required` | full re-embed under existing compatibility/recovery rules |
| retrieval/context/planner-only config | does not affect index freshness | no index work required |
| project-unit topology | allowed but uses existing graph-safe dependent/full rebuild rule | allowed |
| path inventory | allowed with imports/routes dependent rebuild | allowed |
| future schema, stable corruption, missing operational baseline | reject before stale/mutation | recover only when schema is supported; future remains incompatible |

## Refresh Semantics

### Public Operations

P6 exposes two intentionally different mutations:

| operation | evidence after success | body reads | intended use |
| --- | --- | --- | --- |
| `index` | `verified_fresh` | all eligible files are hashed; only changed/dependent files parse/embed | authoritative initial index, audit, recovery, adversarial correctness |
| `refresh` | `metadata_fresh` | metadata-dirty, added, and dependency-required files only | repeated normal editor/agent workflow |

`refresh` requires an existing compatible P6 observation baseline. A missing
index returns `missing_index`; manifest v1 or an incomplete P6 migration returns
`authoritative_index_required`. Both perform no mutation.

Both operations acquire the existing non-blocking exclusive writer lock. Busy
returns immediately and performs no scan, embedding, feedback, or mutation.

### Quick Refresh Algorithm

1. Acquire the exclusive writer lock.
2. Open the current ready/stale snapshot and validate enough state to determine
   whether quick refresh is legal.
3. Build a complete opening metadata inventory and diff it from the last ready
   observation. Any traversal/control error stops with `inventory_incomplete`
   and preserves every prior row.
4. Apply the reason/config legality matrix. If schema, embedding identity, or
   stable integrity requires authoritative recovery,
   stop before marking stale and return `authoritative_index_required`.
5. Safely read/hash direct dirty candidates and the bounded retryable-skip queue.
   Equal-content touches update observations without parsing or embedding.
6. Compute dependent rebuild paths for project topology, test association, and
   active-path import/route resolution using persisted P5 facts.
7. Under the opening observations, complete **all** workspace-derived work for
   direct and dependent paths: safe reads, hashes, parsing, chunk/signal/relation
   materialization, and freezing of embedding inputs and returned vectors.
8. Run the closing inventory fence. Drift/incompleteness returns
   `workspace_changed` before stale and leaves the prior ready snapshot intact.
9. Only after the fence passes, mark graph state stale and persist the frozen
   prepared snapshot. From this point through ready commit, no repository source
   or freshness-affecting control file is read. Global graph resolution/test
   association may read SQLite plus frozen facts only.
10. Use the existing file-write marker, SQLite transaction boundaries,
   immutable vector generation publication, external validation, and final ready
   commit.
11. Publish manifest v2 and bind its generation/digest plus the exact vector
   descriptor identity in the final SQLite ready transaction.
12. Return work counts and a quick health report showing
   `freshness.status=metadata_fresh`.

Authoritative index uses the same prepare-then-closing-fence ordering after its
full hash pass. P6 therefore must refactor the current P5 stale-before-prepare
ordering; it may not defer dependent source reads or embedding calls until after
the fence. If a future implementation cannot freeze some workspace-derived
input, it must add a final complete fence after that input and before external
publication/ready, and bind `completed_at` to that last fence.

A complete-baseline no-op quick refresh with no due retryable skip performs zero
eligible body reads, hashes, parses,
embeddings, SQLite file replacements, vector generation writes, and ready-state
rewrites. It may read metadata/control files and query SQLite counts.

### Dependent Rebuilds

Quick refresh does not promise “only the touched path.” It promises that every
rebuilt path has a declared invalidation reason. The work summary separates:

- `direct_dirty_files`;
- `content_changed_files`;
- `metadata_only_files`;
- `dependent_rebuild_files` by reason;
- `deleted_files`;
- `coverage_skips`;
- `inventory_passes`, `inventory_entries`, `inventory_errors`, and
  `retryable_skip_attempts`;
- `parsed_files`;
- `embedded_chunks`;
- `source_bytes_read` and `source_bytes_hashed`;
- `repository_path_index_builds` and `paths_canonicalized`;
- `relations_scanned/resolved` and `association_inputs/writes`;
- `vector_bytes_read/copied/written/hashed`, payload passes by generation role,
  immutable generations before/after, and descriptor reuse/publication;
- tombstones before/purged/after and SQLite page/freelist counts.

At minimum, P6 retains these dependency rules:

- path additions/deletions re-materialize active `imports`/`routes_to` sources
  whose candidate resolution can change;
- project-unit topology changes use the existing full graph-safe rebuild rule;
- stale-on-entry and integrity failure never take a no-op shortcut;
- persisted import facts support test association rebuilds;
- vector IDs always exactly match active embedding IDs at ready commit.

Graph-only re-materialization with unchanged chunk content reuses existing
embeddings and the current vector generation. A new vector generation is
published only when the ordered `(embedding_id, vector)` set changes.

### Generation And Tombstone Maintenance

Repeated refresh must have a bounded steady state:

1. publication may temporarily leave the current descriptor generation plus one
   prepared generation;
2. the final SQLite ready commit acts as the rollback-journal reader barrier:
   readers that could have opened the previous descriptor finish before it
   commits;
3. after ready commits and while the writer lock remains held, cleanup keeps only
   the descriptor-referenced generation and removes closed-pattern, regular,
   non-symlink, current-owner unreferenced generation files;
4. cleanup failure does not invalidate the ready snapshot; it records bounded
   orphan diagnostics and the next writer retries cleanup before preparing more;
5. crash-left prepared generations, cleanup interleavings, Windows open-file
   behavior, symlinks, unexpected filenames, and every cleanup fault boundary
   are tested.

This barrier relies on the existing rollback-journal mode; P6 does not enable
WAL. `GraphReadSession` must hold its SQLite read transaction for descriptor
selection, payload/ID load or mmap, vector search, and all uses of that mapping.
No descriptor, payload handle, mmap, or vector view may escape the session. These
lifetime assertions make “possibly reader-visible” cleanup mechanically
testable on POSIX and Windows.

Soft-deleted chunk/signal/relation rows plus orphaned symbol/association rows are
physically purged in bounded batches in the final ready transaction only after
the new active vector identity is known. FTS/search payload cleanup remains exact.
Freed SQLite pages are reused;
automatic full `VACUUM` is not placed on the latency-sensitive refresh path.
Maintenance runs when tombstones exceed `max(5,000, 5% of active rows)` for a
table and leaves at most one batch below that threshold. A separate compacting
surface would require its own design if page-file shrink proves necessary.

After successful cleanup exactly one vector generation is retained. After an
injected failure at most one current plus one prepared/orphan generation is
allowed, and the next successful writer restores one. The churn acceptance gate
also bounds SQLite page growth, tombstone counts, disk high water, and query
latency drift.

### Remote Embedding Disclosure

`refresh` can send newly added or content-changed chunks that require a new
embedding to a configured remote provider, exactly as `index` does.
Dependency-only graph re-materialization reuses the existing embedding and sends
no unchanged source chunk. Its CLI help, MCP tool description,
README, and returned embedding metadata state this. Status/stats never call the
provider. Hash is the only built-in provider reported as
`network_egress_capable=false`; configured HTTP and unknown providers are
fail-closed as `true`. No endpoint or credential is emitted. Query embeddings
may send query text under their existing provider contract, but no query surface
opts into source refresh implicitly.

## CLI And MCP Contract

### CLI

`cst status [repo]` becomes the concise health surface:

- default: quick human-readable report;
- `--json`: canonical `StatusEnvelope v1` defined below;
- `--verify`: verified inspection;
- no config or index creation;
- a reportable missing/stale/degraded state is output, not repaired.

`cst stats [repo]` keeps all current human fields and adds indexed/skipped
counts, vector coverage/evidence, manifest and operational schemas, last-index
work metrics, disk components, and a compact health/freshness summary. On a
readable index, `--json` returns current fields plus the nested versioned health
report. Its existing top-level `embedding` remains the indexed identity; the
nested report separately exposes `indexed_embedding`, `configured_embedding`,
their egress capabilities, and `embedding_config_match`. It calls the same
inspector so status and stats cannot disagree. Existing missing/future schema
error behavior is preserved rather than converted to successful stats.

`cst refresh [repo]` performs quick refresh and prints direct/dependent work
counts plus resulting evidence level; `--json` emits `RefreshEnvelope v1`.
`cst index` keeps its current command name and authoritative semantics; its
summary gains the same additive work fields.

Human status exit behavior remains script-safe: producing a valid diagnostic
report exits zero even when stale/degraded/missing, matching the current
diagnostic nature. A new `--require verified|metadata|queryable` option may be
used for gating and exits nonzero when unmet; JSON content remains identical.

### MCP

`context_search_stats(repo, verify=false)` preserves existing top-level `ok`,
`repo`, `stats`, and `embedding` fields on success and adds `index_health`, whose
nested `schema_version` is 1. Existing field meanings do not change. Its exact
existing `repo_not_found`, `missing_index`, and incompatible-schema error
envelopes remain errors without an added sibling; agents use the dedicated
status tool when they need a report for those states.

P6 adds:

```text
context_search_status(repo: str, verify: bool = false) -> StatusEnvelope v1
context_search_refresh(repo: str) -> RefreshEnvelope v1
```

Status is read-only and returns success for missing, stale, degraded,
incompatible, and corrupt index states when the repository root itself is valid.
Refresh is explicitly documented as a repository/index mutation that can call
the configured embedding provider. It is not invoked by query/context/trace/
explore.

The two new envelopes have closed, ordered, required top-level fields:

```text
StatusEnvelopeV1 =
  {schema_version: 1, ok: true, repo: string,
   index_health: IndexHealthReportV1}
| {schema_version: 1, ok: false, error: StatusErrorV1}

RefreshEnvelopeV1 =
  {schema_version: 1, ok: true, repo: string,
   summary: RefreshSummaryV1, embedding: RefreshEmbeddingV1,
   index_health: IndexHealthReportV1}
| {schema_version: 1, ok: false, error: RefreshErrorV1}

StatusErrorV1 = {code: closed_error_code, message: sanitized_string}
RefreshErrorV1 = {code: closed_error_code, message: sanitized_string,
                  network_egress_outcome:
                    "not_attempted" | "possible" | "performed"}
```

There are no optional top-level siblings. The success field order above is the
canonical serializer order; consumers use names. `IndexHealthReportV1` is the
complete required-key object defined earlier. Status errors are only
`repo_not_found | status_failed`; all valid-root index conditions, including
missing/future/corrupt, are success reports. A refresh error contains no partial
summary or health claim. Its required egress outcome is a safety fact, not a
partial success claim: every pre-provider failure is `not_attempted`; once a
network-capable provider request may have crossed the process boundary it is at
least `possible`; a received provider response or later closing-fence/persistence
failure after a completed request is `performed`.

`RefreshSummaryV1` is this exact required-key tree; every count is a
non-negative integer and `dependent_rebuilds` is sorted by the closed
invalidation reason order, then omitted reasons are represented by no list item:

```json
{
  "operation": "quick_refresh",
  "outcome": "ready",
  "verification": "metadata",
  "observation_generation": "",
  "files": {
    "direct_dirty": 0,
    "content_changed": 0,
    "metadata_only": 0,
    "dependent_rebuild": 0,
    "dependent_rebuilds": [],
    "deleted": 0,
    "coverage_skips": 0,
    "parsed": 0
  },
  "chunks": {
    "embedded": 0
  },
  "work": {
    "inventory": {
      "passes": 2,
      "entries": 0,
      "errors": 0,
      "retryable_skip_attempts": 0
    },
    "source": {
      "bytes_read": 0,
      "bytes_hashed": 0
    },
    "path_index": {
      "builds": 0,
      "paths_canonicalized": 0
    },
    "graph": {
      "relations_scanned": 0,
      "relations_resolved": 0,
      "association_inputs": 0,
      "association_writes": 0
    },
    "vector": {
      "bytes_read": 0,
      "bytes_copied": 0,
      "bytes_written": 0,
      "bytes_hashed": 0,
      "payload_passes": 0,
      "prior_payload_passes": 0,
      "prepared_payload_passes": 0,
      "generations_before": 1,
      "generations_after": 1,
      "descriptor_action": "reused"
    },
    "maintenance": {
      "tombstones_before": 0,
      "tombstones_purged": 0,
      "tombstones_after": 0,
      "sqlite_pages_before": 0,
      "sqlite_pages_after": 0,
      "sqlite_freelist_before": 0,
      "sqlite_freelist_after": 0
    }
  }
}
```

Each `dependent_rebuilds` item is exactly `{reason, files}`.
`descriptor_action` is `reused | published`. `generations_before/after` count
immutable payload+ID generation pairs, not physical files. `payload_passes`
equals `prior_payload_passes + prepared_payload_passes`; the role-specific
fields make the prior-generation pass gate directly testable. `RefreshEmbeddingV1` has exact
fields `{indexed_before, configured, network_egress_performed,
embedded_chunks}`; the two identity objects use the same required embedding
identity fields as the health report. On success both identities are valid and
match. `network_egress_performed` is true only when this refresh actually sent
embedding inputs to a network-capable provider; capability alone never implies
that a request occurred, and `embedded_chunks` equals
`summary.chunks.embedded`.

Refresh error codes are exactly `repo_not_found | missing_index |
incompatible_manifest_schema | incompatible_operational_schema |
incompatible_signal_schema | index_busy | authoritative_index_required |
inventory_incomplete | workspace_changed | refresh_failed`. Stats retains its
existing envelope and adds only `index_health` on success; its closed P6 errors
are `repo_not_found | missing_index | incompatible_manifest_schema |
incompatible_operational_schema | incompatible_signal_schema | index_corrupt |
stats_failed`. The three incompatible codes are never collapsed into a generic
schema error, and stable corruption is never mislabeled as a future schema.

HTTP/provider exceptions are mapped to sanitized `refresh_failed`; raw response
bodies, configured URLs, headers, environment values, and source snippets never
enter the envelope.

### Operation Outcome Matrix

| state | CLI `status` | CLI `stats` | MCP status | MCP stats | CLI/MCP refresh |
| --- | --- | --- | --- | --- | --- |
| missing index | report `missing`, exit 0 unless `--require` | existing missing error, nonzero | `ok:true`, health `missing` | exact existing `missing_index` error | `missing_index` |
| manifest v1 | report `degraded/unknown` | existing successful counts | `ok:true` degraded report | existing success plus health | `authoritative_index_required` |
| v2 ready/stale | report, exit 0 unless requirement fails | success | `ok:true` | success | success or reason-specific authoritative requirement |
| future manifest | minimal incompatible report; no config/unknown-row read | `incompatible_manifest_schema`, nonzero | `ok:true`, health `incompatible` | `incompatible_manifest_schema` | `incompatible_manifest_schema` |
| future operational | minimal incompatible report; no config/unknown-row read | `incompatible_operational_schema`, nonzero | `ok:true`, health `incompatible` | `incompatible_operational_schema` | `incompatible_operational_schema` |
| future graph | minimal incompatible report; no config/unknown-row read | existing `incompatible_signal_schema`, nonzero | `ok:true`, health `incompatible` | exact existing `incompatible_signal_schema` | `incompatible_signal_schema` |
| stable corruption | report `corrupt` | `index_corrupt`, nonzero | `ok:true`, health `corrupt` | `index_corrupt` | `authoritative_index_required` |
| ready plus writer/generation drift during inspect | fixed degraded/unknown/unchecked report | success plus same health if readable | `ok:true`, action `retry_inspection` | success plus same health if readable | `index_busy` before work or `workspace_changed` at closing fence |
| already stale plus writer/generation drift | fixed stale/stale/unchecked report | existing stale success plus health | `ok:true`, action `retry_inspection` | success plus same health | `index_busy` or `workspace_changed` |

### Query Compatibility

P6 does not add health siblings to existing query, trace, context, or explore
envelopes. Their exact schema and one-retrieval/build/call budgets remain
protected. The intended agent loop is explicit:

```text
context_search_status -> optional context_search_refresh/index -> context_search_stats/query/context/explore
```

## Consistent Read And Failure Semantics

### Reader/Writer Interleavings

Status uses an opening SQLite read snapshot for readiness, metadata, IDs/counts,
operational/observation generation, expected manifest generation/digest, and
expected vector descriptor generation/digest/byte sizes. It hashes and compares
the small external identities, completes the closing inventory fence, closes the
opening transaction, then opens a second short SQLite snapshot and requires the
same unique ready/observation generation and bound identities. Re-reading inside
the first rollback-journal snapshot would not detect a concurrent commit and is
therefore insufficient. Outcomes are closed:

- ready generation and matching external tuple: normal report;
- committed stale graph or unfinished file marker: freshness `stale`, integrity
  at the evidence level already completed, and health `stale`;
- otherwise-ready snapshot plus writer active or ready-generation drift:
  freshness `unknown`, integrity `unchecked`, health `degraded`, and retry
  guidance;
- already-stale snapshot plus writer activity or drift: freshness `stale`,
  integrity `unchecked`, health `stale`, and retry guidance;
- any generation change during the attempt adds `verification_interrupted` and
  is never corruption;
- stable descriptor/manifest identity or digest mismatch: `invalid/corrupt`;
- a platform that cannot prove lock state: `writer.state=unknown`; generation
  fences still prevent a healthy mixed report and the total derivation table
  above supplies the exact degraded/stale outcome.

Status does not block indefinitely behind a writer. SQLite busy handling uses
the existing bounded rules.

### Refresh Failures

Fault injection covers opening inventory/traversal/control-file failure, body
read, a normal edit after an early observation, dirty preparation, closing
inventory drift, per-file
SQLite replacement, graph resolution, vector preparation/publication, manifest
write, bound-identity update, external validation, final ready commit, vector
cleanup, and tombstone maintenance. After any failure:

- no state reports metadata/verified fresh unless its matching ready generation
  committed;
- the previous ready snapshot remains queryable where P5 lifecycle permits;
- stale graph disables graph evidence as today;
- the next authoritative index can recover without manual file deletion;
- quick refresh refuses integrity states it cannot safely repair;
- incomplete traversal/control input never implies deletion and leaves prior
  indexed rows intact;
- generation cleanup never removes a referenced, unknown-name, symlink, or
  possibly reader-visible file.

## Performance Measurement Design

### Baseline Complexity Inventory

Every known repository-size path receives its own counter and decision branch:

| operation/stage | current scaling | mandatory counters | acceptance boundary | exact-first direction if over budget |
| --- | --- | --- | --- | --- |
| quick/verified inventory | entries and, for verify, source bytes | entries/dirs/control files/errors/body bytes/hash bytes | two complete fences; no retained bodies | directory/control caching only if truth is unchanged |
| authoritative full-build preparation | all parsed chunks/signals/relations, embedding inputs/results, and publication buffers | peak queued files/chunks/text bytes/vector rows, embedding batch calls/sizes, flush counts, peak RSS | bounded source buffers, explicit batch ceiling, full-build RSS/time budgets | stream deterministic parse/persist/embed batches and freeze only generation-required state |
| repo profile on every query | all source rows plus token/symbol aggregates | SQL VM steps, rows/bytes decoded, planner enabled flag | planner-disabled path must not build unused full profile | skip profile when planner disabled; cache immutable profile identity only if measured |
| query ID preflight | all active embedding IDs and all deleted IDs | IDs/bytes materialized | one bounded snapshot; no deleted-ID growth under churn | generation-bound compact active mapping |
| lexical FTS | indexed match plus top-k | VM steps/result rows | indexed plan and configured limit | retain FTS |
| path/symbol recall | all active chunks, tokens, and symbols | rows/bytes per table | declared scan contract below and latency budget | normalized indexed search surface |
| direct-text recall | all active chunk text | rows and text bytes decoded | at most one declared corpus pass and latency budget | portable exact inverted/n-gram surface if justified |
| signal recall | all recallable signals/metadata | rows and metadata bytes | at most one declared recallable pass and latency budget | normalized signal search surface |
| vector query | vector load/hash plus `O(rows*dimensions)` score and full sort | payload bytes, normalization count, scored rows, sorted rows | one load per invocation, one exact score pass, no full sort | mmap/pre-normalize/deterministic partial top-k |
| one-file vector update | load/copy/sort/write/hash complete vector generation | payload bytes read/copied/written/hashed, generations | bounded amplification and disk high water | stable row map/reuse; ANN only by later gate |
| graph resolution after mutation | all persisted relations and selector candidates | relations/selectors read and resolved | one declared pass; no duplicate source scans | incremental affected-selector resolution if dominant |
| test association after mutation | all active files/import facts | files/import facts/associations read/written | one declared pass | affected-unit/source incremental regeneration if dominant |
| plugin repository context | rebuilt files x all active paths/units | path-index builds, paths canonicalized/copied | one repository index build per operation | shared immutable `RepositoryPathIndex` |
| churn maintenance | generations plus soft-deleted rows over updates | generation files, tombstones, freelist/pages, disk/RSS/query drift | steady-state budgets below | cleanup and bounded physical purge |

Baseline and final reports contain every row even when its cost is zero. This
prevents a faster vector stage from hiding a newly dominant repo-profile,
resolver, publication, or tombstone path.

### Benchmark Harness

P6 adds a deterministic, no-network benchmark harness under tests/tooling rather
than committing a giant repository. It generates workloads from a versioned
seed and records:

- Python, CST, SQLite, NumPy, OS, architecture, CPU count, and memory;
- workload schema/seed and canonical generator hash;
- eligible file/byte distributions, chunk text bytes, path depth, metadata
  lengths, chunk/symbol/token/signal/relation cardinality and density,
  tombstones, and vector payload counts;
- embedding provider/model/dimensions and planner state;
- cold/warm classification and cache preparation;
- every raw sample, median, p50, p95, maximum, and coefficient of variation;
- stage timings, rows/calls/bytes/work counters, disk component sizes, and peak
  RSS in a fresh subprocess;
- git implementation commit and dirty-state marker.

The acceptance runtime uses Python 3.13 and the repository-pinned dependency
set, matching the P5 reference lineage unless the implementation plan records a
reviewed replacement. Hash embeddings and planner-disabled queries prevent
network/model variance.

Performance states are closed:

- `cli_process_cold`: a fresh CLI subprocess after one unmeasured identical run
  warms filesystem page cache; process/module/vector state is cold;
- `mcp_resident_warm`: repeated calls through one production MCP process after
  three warmups; any implemented in-process reuse is included;
- `filesystem_cold_diagnostic`: fresh process after a privileged/best-effort
  page-cache drop on a dedicated Linux host; informational and never substituted
  for the two product gates.

“Warm” never means a test-only preloaded store. The reference host is the same
physical machine for baseline/final, has at least 8 logical CPUs, 16 GiB RAM and
a local SSD, runs on external power with no swap growth and background CPU below
20%, and records power/governor state. A 512-MiB SHA-256 stream, the fixed
80k-by-384 NumPy dot product, and a fixed SQLite calibration run must be within
10% between paired baseline/final sessions or the session is invalid.

Peak RSS is measured inside a fresh operation subprocess with
`resource.getrusage(RUSAGE_SELF).ru_maxrss`, normalized as KiB on Linux and bytes
on macOS. `extra_peak_rss = max(0, operation_peak - empty_harness_peak)` on the
same runtime. Product benchmark cases spawn no children; a child process fails
the case. The vector payload formula is `rows * dimensions * 4` bytes. Resident
MCP reports both process-start RSS and peak/current RSS after each call.

Vector I/O counters cannot double-count hashing as if it were free.
`vector_bytes_read` is every logical byte requested from payload/ID generation
files, while `vector_bytes_hashed` is the subset fed to a digest and must be less
than or equal to bytes read. `vector_payload_passes` increments for each complete
logical traversal regardless of page-cache or mmap residency. A hash performed
by a second traversal therefore reports two payload passes and twice the logical
read bytes; mmap implementations must expose an equivalent traversal counter.
Byte-amplification gates and payload-pass gates are conjunctive.

### Workload Tiers

| tier | files | source MiB | chunks / text MiB | tokens / symbols / signals / relations | vector MiB (384d) | purpose |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| `smoke` | 1,000 | 24 | 4,000 / 12 | 80k / 8k / 12k / 16k | 5.9 | normal CI correctness/work counters |
| `large` | 20,000 | 512 | 80,000 / 256 | 1.6m / 160k / 240k / 320k | 117.2 | P6 latency/RSS/disk acceptance |
| `scale` | 5k then 10k | 128 then 256 | 20k then 40k / proportional | proportional to `large` | 29.3 then 58.6 | separate scaling ratios |
| `stress` | 50,000 | 1,280 | 200,000 / 640 | 4m / 400k / 600k / 800k | 293.0 | informational capacity evidence only |

The manifest freezes file-size p50/p95/max, chunk-size distribution, path-depth
distribution, token/symbol repetition, signal metadata byte p50/p95/max,
relation out-degree, and test/source ratios. It also freezes high-hit, low-hit,
zero-hit, and high-ambiguity queries for lexical, path/symbol substring, CJK and
ASCII direct text, signal, and semantic families, with exact query counts and
ordered output fingerprints. Planner-disabled and one P4-style explore family
are separate.

The generator includes additions/deletions, equal-content touches,
same-metadata content edits under an injected no-ctime observer, bounded stable
and retryable skips, directory/control-file failures, and a 100-step churn trace
that repeatedly modifies/deletes/restores files. Churn samples status/query every
10 steps and records generation files, tombstones, SQLite page/freelist counts,
disk high water, RSS, and latency drift.

Query-performance fixtures may construct canonical SQLite/vector snapshots
directly to avoid measuring parser setup in every run. Index/refresh workloads
use real generated source and the production scanner/indexer. The two fixture
types are reported separately and cannot substitute for one another.

Every one-file refresh sample starts from an observation-consistent ready
snapshot prepared outside the timed interval, applies the same seeded edit, then
runs one refresh. Setup must either restore every persisted metadata observation
including the platform change token, or rebuild the ready baseline against that
clone's actual current metadata; byte-identical source/index payloads alone are
insufficient. Samples never accumulate prior mutations or cleanup history. The
100-step churn workload is the separate test for sequential mutation,
maintenance, and steady-state behavior.

### Measurement Order

1. Capture the clean P6 entry baseline before optimization.
2. Profile cold and warm end-to-end operations.
3. Attribute startup/config/manifest/vector loading and every retrieval stage.
4. Record SQLite `EXPLAIN QUERY PLAN`, test-only VM-step progress counts,
   production-boundary rows/bytes decoded, and call counts for candidate sources.
5. Optimize the largest proven contributors with exact-result tests.
6. Rerun identical seeds on the same host and publish before/after raw reports.
7. Evaluate ANN/service triggers only from the post-exact-optimization profile.

### Acceptance Budgets

Wall-clock budgets apply to the recorded `large` reference host. Work-count and
correctness budgets apply in normal CI.

| operation | large-tier budget |
| --- | --- |
| initial authoritative full build, hash provider | 5 samples: median <= 300 s, max <= 420 s, peak RSS <= 2 GiB, ready index disk <= 2.5 GiB |
| authoritative no-op index | 5 samples: median <= 15 s, max <= 25 s, extra RSS <= 512 MiB; all 512 MiB source verified, zero parse/embed |
| quick status | 20 samples: nearest-rank p95 <= 2.0 s; extra RSS <= 256 MiB; zero eligible body/vector-payload bytes read |
| verified status | 5 samples: median source hashing >= 75 MiB/s, max <= 12 s; extra RSS <= 256 MiB; one bounded source buffer |
| no-op quick refresh | 20 samples: p95 <= 2.5 s; zero source-body reads/hashes/parses/embeddings/vector publishes |
| one-file quick refresh, hash embedding | 20 paired edits from observation-consistent ready snapshots: p95 <= 5.0 s; declared fan-out only; extra RSS <= vector payload x 2.2 + 256 MiB; vector read and write each <= 1.10x one generation and prior-generation payload passes <= 1 when changed |
| MCP resident-warm ordinary query, planner off | 30 samples per frozen query case in every family: each p95 <= 750 ms; semantic stage p95 <= 300 ms |
| CLI process-cold ordinary query, page-cache warm | 30 samples per frozen query case: each p95 <= 2.0 s |
| MCP resident-warm bounded explore | 30 samples per frozen case: each p95 <= 2.5 s and existing <=3 retrieval calls |
| query peak RSS | <= vector payload x 1.35 + 256 MiB |
| vector disk high water | <= 2.10x current generation payload+IDs during publish; exactly one generation after success |
| 100-step churn steady state | final disk/page count <= 1.25x compacted live baseline; tombstones below maintenance threshold; query p95 drift <= 10%; no more than two generations after an injected failure |
| 5k -> 10k full build scaling | time and peak-RSS ratios each <= 2.7 |
| 5k -> 10k authoritative no-op scaling | time and source-byte ratios <= 2.4 |
| 5k -> 10k quick status/no-op refresh scaling | time and entry-work ratios <= 2.4 |
| 5k -> 10k one-file vector-changing refresh | time, vector-byte and peak-RSS ratios <= 2.4 |

Nearest-rank p95 uses sorted sample `ceil(0.95*n)`. Samples are never mixed
across operations or query cases; a family passes only when every frozen case
passes. P95 gates have at least 20 same-condition
samples; five-sample expensive operations gate median and maximum, never p95.
Baseline/final relative gates use at least 30 alternating paired samples on the
same host and the median paired ratio. CV is population standard deviation
divided by the arithmetic mean for one same-case sample set. At most one complete
rerun is allowed.
CV >8% invalidates a 10% relative regression claim; CV >15% invalidates absolute
wall-clock evidence. If the one rerun remains over the applicable limit, the
gate fails rather than selecting a favorable run.

Protected small-repository paired latency may regress by no more than 10% when
its CV is <=8%; otherwise stable evidence must be re-established. Absolute
budgets, scaling, disk, and work proofs are conjunctive. An undeclared or repeated
full scan fails. A declared exact substring scan may remain only when it stays
within its one-pass row/byte contract and the absolute budget; this avoids
pretending portable exact substring semantics can be proven sublinear without a
portable search surface.

### CI Strategy

Normal CI runs the `smoke` workload and proves:

- no-op quick refresh body/hash/parse/embed/publish counters are zero;
- single-file refresh direct work is one plus exact declared dependencies;
- repository path indexes are built once per operation, not once per file;
- test-only `sqlite3.Connection.set_progress_handler` VM-step counters plus
  store-boundary row/byte counters enforce the source-specific contracts below;
- vector top-k does not fully sort all rows after exact optimization;
- output order and score floats match the exact protected implementation;
- benchmark schemas, seeds, and metric units are valid.

Dedicated acceptance runs enforce wall-clock and RSS budgets. The current
100-ms direct-text unit test is converted to a work/correctness smoke guard or
moved into the recorded performance profile; a host-sensitive assertion does
not remain disguised as a deterministic unit test.

The allowed exact-search scan contracts are:

| source | allowed work before a new search surface is mandatory |
| --- | --- |
| lexical FTS | configured result limit, reviewed FTS plan, no Python corpus materialization |
| exact token | indexed equality seeks; decoded rows are matching rows only |
| path/symbol substring | at most one pass over normalized active path/symbol columns, never the token table or chunk bodies |
| direct text | at most one pass over active chunk text bytes per distinct normalized probe set; planner overlap is reused |
| signal | at most one pass over recallable normalized signal fields/metadata; non-recallable rows excluded in SQL |
| vector | one generation load and one score pass per invocation; one matrix normalization; zero full-score sort |

`EXPLAIN QUERY PLAN` is supporting evidence, not a visited-row counter. Instrumented
work-proof runs are separate from uninstrumented wall-clock runs and must return
identical ordered candidates/scores.

## Optimization Decision Tree

### Indexing And Inventory First

The known per-file active-path canonicalization is removed by constructing one
immutable `RepositoryPathIndex` per operation. It owns canonical paths,
membership, and path-to-project-unit lookup. Plugin contexts reference it rather
than sorting/copying the repository inventory. Frontend relation
materialization reuses membership and unit maps.

This change must preserve plugin immutability and exact graph projections. The
scale gate and allocation/work counters prove that doubling files does not
quadruple repository-context construction.

The same profile decides whether full relation resolution and full test
association remain one-pass exact work or need affected-selector/unit
incrementality. Planner-disabled queries skip repo-profile construction
entirely; planner-enabled profile identity may be cached only against the bound
ready generation. Active/deleted ID materialization and one-file full-vector
publication remain separate measured stages rather than being charged to
“semantic search.”

### SQLite Exact Search

Profiles evaluate these sources independently:

1. lexical FTS;
2. exact/prefix token lookup;
3. path and symbol substring matching;
4. direct-text ASCII and CJK probes;
5. recallable signal lookup and metadata search;
6. planner-hint repetition;
7. graph expansion queries.

Low-risk changes are preferred:

- use existing indexed `chunk_tokens.token` equality instead of loading all
  tokens;
- add normalized path/symbol/signal search surfaces only when their storage and
  update cost is measured;
- issue one bounded query per candidate source or one reviewed union, not an
  unbounded Python materialization;
- reuse planner-hint results for overlapping normalized tokens;
- preserve CJK substring behavior and deterministic tie ordering;
- require `EXPLAIN QUERY PLAN` and exact candidate/score projections before and
  after each rewrite.

FTS5 trigram or another tokenizer cannot be assumed available across supported
SQLite builds. A feature-detected optimization must have an exact fallback and
cannot change acceptance semantics.

### Exact Vector Search

Before ANN, P6 measures and may implement:

- immutable generation loading with `mmap_mode="r"` when integrity and platform
  tests permit;
- normalization once per loaded generation rather than once per query variant;
- normalized vectors at publish time if the descriptor records that invariant;
- partial top-k without sorting every score: compute the kth score threshold,
  keep every row above it, choose the lexicographically smallest chunk IDs among
  boundary-equal rows to fill the remainder, then sort only the final set by
  `(-score, chunk_id)`;
- deleted-ID masking before selection;
- avoiding duplicate generation hashing/loading within one process invocation;
- explicit separation of quick descriptor validation from verified integrity
  validation without weakening the P5 rule that a ready query cannot pair
  mismatched SQLite IDs and vector rows.

Any relaxation of per-query cryptographic file hashing requires a precise
replacement invariant based on immutable generation names, atomic descriptor
publication, descriptor-bound file metadata, verified publication, and
fail-closed load errors. It must be reviewed as a lifecycle change, not smuggled
in as a micro-optimization.

### ANN Trigger And Gate

ANN is considered only if, after exact optimizations on the `large` tier, both
conditions hold:

1. semantic recall p95 remains above 300 ms or the query RSS budget is exceeded;
2. the per-sample `semantic_stage_ms / end_to_end_ms` median is at least 40% on
   the same paired warm samples, or exact vectors are the measured dominant
   source of excess RSS.

Crossing the trigger authorizes a separate prototype and design amendment, not
automatic adoption. An ANN candidate must then prove:

- local/offline operation and supported-platform wheels or no new dependency;
- deterministic build inputs and versioned serialization;
- exact fallback and migration/recovery behavior;
- tie-aware per-query Recall@80 against the deterministic exact set, with macro
  mean >= 0.99 and every query >= 0.95; candidates tied at the exact kth boundary
  count only according to the frozen `(score, chunk_id)` reference order;
- all protected final retrieval/ContextPack gates still pass;
- p95 and RSS meet the P6 budgets with at least 30% semantic-stage improvement;
- index disk usage <= 1.5x the exact vector payload unless explicitly approved;
- incremental insert/delete/compaction behavior fits the P5 ready/stale lifecycle.

If the trigger is not crossed, P6 records “exact search retained” and ships no
ANN dependency.

## Service And Watch Decision

The baseline P6 implementation ships no service or watcher. At acceptance it
records only `deferred` or `eligible_for_separate_design`; it does not build a
resident-service or watcher prototype without new user authorization. Eligibility
requires:

1. status, authoritative index, quick refresh, crash recovery, and reader/writer
   interleavings pass all P6 gates;
2. on the same repeated production-warm samples, the median of each sample's
   `immutable_state_load_ms / end_to_end_ms` is at least 40%, or immutable-state
   loading prevents the ordinary query budget; independently computed stage and
   end-to-end p95 values are never divided to claim this threshold;
3. a counterfactual using the paired production stage trace shows that removing
   repeated immutable-state load would either improve p95 by at least 2x or meet
   the 750-ms budget, and one retained mapped generation fits the RSS formula;
4. the inventory/verified-index design remains sufficient as the eventual
   reconciliation source of truth.

Only the separately authorized design may prototype service lifecycle or prove
watcher event loss, overflow, rename, symlink, ignore/config change, sleep
recovery, shutdown, exposure/authentication, privacy, and cache invalidation.

Otherwise the P6 record says `deferred`. Even a later watcher is never allowed to
become the only freshness proof.

## Security And Privacy

- Scanner, parser, graph resolution, status/stats, and the hash-only benchmark
  harness remain local and no-fetch. Index, refresh, and query embedding may use
  a configured HTTP provider and therefore may perform network I/O under their
  explicit existing/new disclosure contracts.
- Status follows P5 top-level root resolution, rejects/fails closed on symlinks
  below that root, and preserves the bounded-read/path-race rules.
- Reports contain repository-relative paths only in bounded samples.
- Config hashes do not serialize API-key values; status omits environment values
  and credential-bearing URLs.
- Benchmark artifacts contain generated source only. Real repository source,
  vector values, query content outside committed fixtures, environment dumps,
  and absolute temporary paths are rejected by privacy tests.
- Remote embedding disclosure remains explicit for index/refresh/query as
  applicable. Unknown providers are reported network-capable. Status/stats never
  instantiate an embedding provider.
- Provider tests freeze exact source/query payload scope; HTTP errors containing
  response bodies, configured URLs, headers, or secrets are sanitized before CLI
  or MCP output.
- SQLite and vector diagnostics are sanitized closed codes, not raw exception or
  filesystem text.
- Metrics/feedback writes are not added to read-only query or inspection paths.

## Compatibility Contract

P6 must preserve:

- manifest-v1/schema-v5 queryability until authoritative migration;
- future graph schema rejection before config creation or mutation;
- exact current `context_search_stats` fields and meanings;
- raw query ranking, score parts, reasons, follow-up keywords, and result shape;
- ContextPack v2 canonical bytes for protected cases;
- RetrievalTrace v1 and ExplorationTrace v2 schema and privacy;
- P4 <=3 calls, 12 items, and 65,536-byte real-case budgets;
- stale graph behavior: lexical/semantic recall remains available while
  graph-derived evidence is skipped;
- vector generation atomicity and exact SQLite/vector identity at ready commit;
- one non-blocking exclusive writer and committed reader snapshots;
- deterministic P5 graph projections and no forbidden ambiguity edge;
- current local hash and optional remote embedding behavior.

Operational search rewrites must compare exact ordered candidate IDs and scores
before ranking. Any unavoidable floating-point difference requires a reviewed
numeric tolerance plus proof that protected ordering is unchanged; silent
baseline refresh is prohibited.

## Testing Strategy

### Health Contract

- missing index, partial legacy files, manifest v1, valid v2, future manifest,
  future operational schema, future graph schema;
- raw schema-first preflight proves missing/future outcomes before config,
  provider, feedback, profile, scanner, or unknown-row interpretation on status,
  stats, refresh, and index;
- healthy metadata and verified reports from the same snapshot;
- changed, added, deleted, touched-but-content-equal, and same-size/same-time
  content-changed files under both ctime-capable and injected mtime-only observers;
- opening/closing inventory fences, an early-observed file edited later, a path
  added after the scan cursor, and post-completion limitation disclosure;
- directory traversal failure, unreadable subtree, `.gitignore`/config/control
  read failure, lower-bound counts, zero inferred deletion, and recovery;
- indexed path becoming too large/binary/unreadable and new coverage skip;
- ready-snapshot versus verified-workspace coverage, pending inspection, stable
  skip, bounded/fair retryable skip, and transient recovery;
- ignored/default/vendor/unsupported paths excluded from coverage gaps;
- config, embedding, project topology, graph stale, unfinished file marker,
  bound generation/digest mismatch, ID count mismatch, exact ID mismatch,
  missing/symlink/non-regular/wrong-size/truncated vector or ID files, corrupt
  NumPy/JSON, and SQLite quick-check failure;
- bounded canonical samples and complete counts;
- quick count-only versus verified exact vector coverage;
- indexed versus configured embedding identity, true/false/null config match,
  missing/invalid/not-inspected/unknown-provider fail-closed egress capability,
  and unchanged indexed meaning of MCP stats top-level `embedding`;
- status/stats create and modify no files and perform no embedding/network call;
- exhaustive table-driven health derivation across graph state, inventory
  completeness, workspace delta, writer true/false/null, generation stable/drift,
  coverage, and integrity; stable sample/diagnostic schemas; and CLI/MCP
  operation-outcome matrix parity;
- golden required-key/order tests for `IndexHealthReport v1`, `StatusEnvelope
  v1`, `RefreshEnvelope v1`, all three incompatible error codes, stable
  corruption, missing/future nullable collections and leaf enums, and every
  operation-specific error allowlist.

### Refresh Contract

- no-op zero-work proof;
- one direct edit, equal-content touch, addition, deletion, rename, and recovery
  from skip;
- path addition/deletion transitions `unresolved -> resolved_unique`,
  `resolved_unique -> ambiguous`, and `ambiguous -> resolved_unique` for
  unchanged sources;
- test association and project topology dependent rebuilds;
- changed-during-scan/read and repeated modification do not commit mixed data;
- incomplete inventory/control input preserves every old row and cannot mark
  ready;
- an instrumented boundary fails any repository source, `.gitignore`, current
  config, or topology-control read after the stale commit, proving persistence
  consumes frozen facts only;
- metadata quick refresh limitation is explicit; authoritative index catches the
  preserved-metadata edit;
- remote provider receives only newly added/content-changed chunks whose
  embedding must change; dependency-only rebuilds send none;
- busy writer returns before scan/provider/mutation;
- every P5 fault boundary plus observation/manifest-v2 boundaries recovers;
- ready commit requires matching observation generation, fingerprints,
  bound manifest/descriptor identity, config, SQLite counts, graph invariants,
  and vector tuple;
- vector generation reuse for graph-only changes, reader-barrier cleanup,
  prepared/orphan crash recovery, closed-path/symlink safety, bounded tombstone
  purge, and 100-step churn steady state;
- explicit `PRAGMA journal_mode` assertions cover every supported
  rollback-journal mode; generation cleanup fails closed rather than assuming a
  reader barrier under WAL or an unknown mode;
- exact provider payload scope, unknown-provider network-capable disclosure,
  status zero provider/network calls, sanitized secret-bearing HTTP failures,
  and fail-closed `not_attempted | possible | performed` refresh-error egress
  outcomes at every provider/fence/persistence fault boundary.

### Search And Performance Contract

- exact candidate projections per source before/after SQL rewrites;
- CJK direct substring, path substring, symbol substring, exact token, signal
  metadata, planner hint, deleted rows, and deterministic ties;
- vector exact top-k equivalence including equal scores, NaN/Inf normalization,
  deleted IDs, empty store, multiple variants, and top-k boundaries;
- query stage/call/row/byte counters and benchmark report validation;
- process-cold/resident-warm/filesystem-cold separation, reference-host
  calibration, platform-normalized RSS units, and no child processes;
- smoke, large, scale, and stress generator identity;
- workload byte/density/selectivity fingerprints, churn identity, exact nearest-
  rank p95, paired samples, one-rerun ceiling, and CV failure behavior;
- repo-profile, active/deleted IDs, graph resolver, test association, vector
  publication, and tombstone stage counters;
- full-build preparation queue/batch/RSS counters, observation-consistent
  ready-snapshot one-file samples, vector read/hash subset accounting, and
  role-specific payload-pass gates;
- ANN trigger false/true decisions from synthetic reports without installing an
  ANN dependency;
- service/watch decision record validation.

### Protected Quality And Lifecycle

- deterministic P5 12/12 and structural projections;
- pinned-real P5 2/2 twice with exact normalized projection hash unless a
  reviewed operational-only envelope field is excluded before comparison;
- P4 4/4, P2 5/5, raw CI 8/8;
- protected-direct and no-legal-edge exact behavior;
- full suite with audited skip/xfail identities;
- Python 3.11-3.14 and supported OS matrix for functional behavior;
- parser initialization and all P6 status/benchmark paths remain no-fetch.

## Acceptance Artifacts

P6 closes with committed, privacy-audited artifacts containing:

1. P6 entry baseline identity and clean-tree proof;
2. health/refresh schema and golden examples;
3. benchmark generator manifest and SHA-256;
4. baseline and final raw performance reports for smoke/large/scale plus the
   100-step churn trace;
5. exact before/after search candidate projection hashes;
6. work-counter, RSS, vector generation/tombstone, disk high-water, and
   calibration summaries;
7. deterministic and pinned-real quality reports;
8. skip/xfail and dependency/ABI audit;
9. ANN trigger decision and evidence;
10. service/watch `deferred | eligible_for_separate_design` decision and evidence;
11. capability/API outcome matrix projections;
12. roadmap and `docs/retrieval-quality.md` update only after every gate passes.

Reports fail privacy validation if they contain source bodies, vector floats,
secrets, environment values, absolute temporary roots, or unapproved real query
text.

## Likely Change Surface

| area | likely files |
| --- | --- |
| health/inventory contracts | new `index_health.py` and/or `freshness.py`, `scanner.py`, `models.py` |
| operational persistence | `manifest.py`, `sqlite_store.py`, `graph_lifecycle.py` only where generation coupling requires it |
| indexing/refresh | `indexer.py`, `index_lock.py`, `graph_plugins.py`, `frontend_graph.py` |
| exact search | `retrieval_core/candidates.py`, `sqlite_store.py`, `vector_store.py`, narrowly `retrieval.py` for load instrumentation |
| public surfaces | `cli.py`, `mcp_tools.py`, `mcp_server.py`, `README.md` |
| benchmarks | new deterministic generator/runner plus focused tests and `.quality` schemas |
| quality/evidence | protected tests, `docs/retrieval-quality.md`, roadmap after acceptance |

ContextPack construction, ranking policy, exploration policy, parser semantics,
and language/framework scope are not refactored.

## Delivery Decomposition

A later implementation plan should keep these reviewable slices:

1. freeze the clean P6 entry baseline and capture unoptimized performance;
2. define report/inventory models, manifest v2, operational schema migration,
   and read-only quick/verified inspector;
3. expose CLI status/stats and MCP status/stats without mutation;
4. add fenced complete-inventory quick refresh, work counters, dependent
   invalidation, generation/tombstone maintenance, and failure recovery;
5. add the deterministic benchmark/churn harness and enforce acceptance report schemas;
6. remove per-file repository-context reconstruction and prove scaling;
7. optimize profiled repo-profile/ID/graph/test-association and SQLite exact
   search paths with exact projections;
8. optimize exact vector loading/search/publication while preserving lifecycle
   and deterministic boundary-tie invariants;
9. evaluate ANN trigger and implement only through an approved amendment;
10. run all quality/performance/privacy gates, record service/watch decision, and
    update roadmap/evidence.

Measurement harness and baseline capture precede performance optimization. The
health contract precedes refresh. ANN and service/watch decisions come last.

## Definition Of Done

P6 is complete only when all of the following are true:

1. the P6 baseline is a clean commit containing the P5 path-inventory fix;
2. status/stats expose `IndexHealthReport v1` and are proven read-only;
3. agents can distinguish metadata freshness, verified freshness, degradation,
   corruption, incompatibility, and required refresh kind;
4. complete inventories produce exact stale/skip counts with bounded safe
   samples; incomplete inventories preserve rows and cannot claim fresh;
5. vector coverage and embedding identity are truthful at quick and verified
   evidence levels;
6. no-op quick refresh reads/hashes/parses/embeds/publishes zero source/vector
   work as specified;
7. opening/closing observation fences prevent mid-operation false freshness;
8. direct/dependent invalidation, retryable coverage recovery, generation cleanup,
   tombstone maintenance, and crash recovery pass;
9. authoritative index detects same-metadata content edits;
10. large-tier latency, RSS, disk, churn, scaling, and work-count budgets pass;
11. exact search outputs and P0-P5 protected contracts pass;
12. ANN has either passed its separate gate or is explicitly retained as exact;
13. service/watch has an evidence-backed eligibility/defer record and is not shipped
    without separate approval;
14. privacy/no-fetch/network disclosure and dependency audits pass;
15. roadmap/evidence is updated only after acceptance.

Any unresolved blocker or major correctness, lifecycle, compatibility, privacy,
freshness-truth, performance-methodology, or acceptance finding keeps the design
in draft.

## Agent Review Rubric

Independent reviewers must verify:

- freshness axes, evidence labels, and no impossible metadata proof;
- P5 ready/stale/vector generation and reader/writer compatibility;
- v1/v2/future migration and crash recovery;
- path-inventory and topology dependent invalidation;
- read-only status privacy and mutation boundaries;
- quick refresh remote-provider disclosure and failure behavior;
- benchmark reproducibility, scale realism, budgets, RSS units, and CI strategy;
- exact SQL/vector optimization ordering and ANN trigger sufficiency;
- protected query/ContextPack/trace/exploration compatibility;
- executable acceptance artifacts and service/watch deferral.

## Agent Review Record

First review (2026-07-18) used three independent read-only agents:

- architecture/lifecycle: FAIL, 2 blockers, 4 majors, and 2 minors;
- performance methodology: FAIL, 0 blockers, 7 majors, and 2 minors;
- adversarial acceptance/failure recovery: FAIL, 1 blocker, 7 majors, and 3
  minors.

The revision above addresses the reported blockers and majors with complete
inventory/error barriers, opening/closing observation fences, stable-generation
corruption rules, SQLite-bound manifest/vector identities, explicit migration
and operation matrices, retryable coverage semantics, reason/config legality,
safe generation/tombstone maintenance, fail-closed network disclosure, and
quick vector identity/size checks. It also expands the performance contract for
repo-profile/ID/graph/test/vector-publication hotspots, workload bytes/density/
selectivity, churn, cold/warm/RSS definitions, executable VM-step/row/byte work
proofs, per-case statistics, full-build/disk budgets, deterministic vector ties,
tie-aware ANN gates, and separately authorized service/watch work.

Second review (2026-07-18) re-ran the same three independent agents against the
revised document:

- architecture/lifecycle: FAIL, 0 blockers, 1 major, and 2 non-blocking
  observations;
- performance methodology: PASS, 0 blockers, 0 majors, and 4 minors;
- adversarial acceptance/failure recovery: FAIL, 0 blockers, 4 majors, and 2
  minors.

This revision closes the remaining architecture ordering gap by freezing every
workspace-derived direct/dependent artifact and embedding result before the
closing fence, then forbidding repository/control reads after stale begins. It
also makes schema-first preflight common to all operations; defines separate
indexed/configured embedding identities and fail-closed egress evidence; freezes
canonical status/refresh envelopes and operation-specific error codes; makes
health derivation total under writer/generation interleavings; and incorporates
the four performance clarifications for full-build memory, vector traversal
accounting, isolated one-file samples, and paired service ratios.

Final targeted review (2026-07-18) reported:

- architecture/lifecycle: PASS, 0 blockers, 0 majors, and 2 non-blocking
  implementation notes;
- performance methodology: PASS, 0 blockers, 0 majors, and 3 minors;
- adversarial acceptance/failure recovery: PASS, 0 blockers, 0 majors, and 2
  minor observations.

The non-blocking findings were incorporated: journal-mode and post-stale
zero-workspace-read tests; generation/pass unit alignment and
observation-consistent benchmark snapshots; required refresh-error egress
outcomes; and closed leaf/null/missing/future report contracts. A final read-only
regression confirmation by all three reviewers then returned PASS with 0
blockers and 0 majors. The independent agent-review gate is complete.
