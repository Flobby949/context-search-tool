# P13 BGE Provider Hardening and Independent Evaluation v1 Implementation Plan

> **For agentic workers:** Execute one task at a time, keep every change
> surgical, and stop at the declared gates. Do not combine P13 with a
> retrieval-policy experiment.

Date: 2026-07-27
Status: Reviewed r2; implementation not started
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `122ed052284fa488943cb4464301a391bd2e7e24`
Design:
`docs/superpowers/specs/2026-07-27-p13-bge-provider-hardening-design.md`

Review r2 incorporates the parallel Standards and Spec findings:
production preflight/postflight closes the mid-operation drift race;
every existing vector loader/validator separates static config identity
from exact descriptor identity; live unavailability blocks only live
tasks; the baseline harness is tracked and reproducible; commit
checkpoints are authorization-conditional; and all referenced test
paths exist.
Follow-up review additionally requires a fresh child process per
measured implementation root, module-origin assertions, a provider-
discriminated schema v4, and explicit dirty/untracked auditing when
commits are not authorized.

**Goal:** Harden the native Ollama BGE provider as a reproducible,
failure-atomic opt-in provider, then evaluate hash vs hardened BGE with
retrieval behavior held constant.

**Architecture:** BGE performs a cached preflight and a cache-bypassing
postflight around each product embedding interval, applies the frozen
`bge-input-v1` head/tail transform, batches up to eight texts with
server truncation disabled, and validates every response. Manifest v2
keeps the static config hash and binds a BGE runtime identity
transitively through the vector descriptor SHA. Index/refresh rebuild
on runtime drift; query rejects drift before vector search.

## Global Constraints

- Fixed runtime prefix and non-slow suite command:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  -m "not slow"
```

- The accepted starting account is `2983 passed, 5 skipped,
  5 deselected`. Five P6 worker nodes require an unrestricted macOS
  process because the restricted runner denies `sysctl`; run and count
  them explicitly rather than hiding them.
- `.venv` is Python 3.14.6 and is not a substitute for the fixed
  runtime.
- Current Ollama availability is BLOCKED. Offline Tasks 1-6 and the
  applicable implementation record/review in Task 9 still run. Tasks
  7-8 and any live ship/recommendation claim require a real local
  `bge-m3` service.
- Hash characterization, manifests, vector pins, retrieval results, and
  frozen gold are STOPs, never repins.
- P9/P10/P11 relation-slot machinery remains inert. P12 planner
  behavior remains unchanged. Do not touch ranking, chunking, graph
  expansion, selection, or planner code except the narrow provider
  identity check in candidate generation.
- No silent BGE → hash or BGE → lexical-only fallback.
- No source/query text, credentials, response bodies, or absolute
  repository paths in BGE errors or logs.
- No model pull, daemon start, commit, push, or PR without explicit user
  authorization.
- Commit messages below mark optional checkpoints only. At each one,
  commit only if the user has authorized commits; otherwise continue
  with the verified working diff.
- A candidate need not be clean when commits are not authorized.
  Before implementation, the only allowed delta from baseline is the
  two reviewed P13 documents. During implementation, every tracked and
  untracked path must be in the Planned File Map. Audit with both
  `git status --short --untracked-files=all` and
  `git ls-files --others --exclude-standard`; ordinary `git diff` and
  `git diff --stat` are insufficient for untracked files.
- No post-comparison tuning. A new transform, batch size, threshold, or
  gate requires a new design/version and fresh baseline.
- Use a single persisted evidence root:

```bash
P13_RUN_ROOT=$(mktemp -d /private/tmp/cst-p13-run.XXXXXX)
printf '%s\n' "$P13_RUN_ROOT" > .quality/p13-run-root.txt
```

- Every live capture records:
  source SHA/fingerprint, gold SHA, implementation commit/dirty state,
  Python/SQLite/NumPy versions, base URL, configured model, canonical
  model, digest, raw Ollama version, `bge-input-v1`, dimensions,
  request count, prepared-input length summary, index wall time, and
  query p50/p95.

## Planned File Map

| action | path | purpose |
| --- | --- | --- |
| modify | `src/context_search_tool/embeddings_bge.py` | complete BGE provider contract |
| modify | `src/context_search_tool/embeddings.py` | narrow runtime-identity seam |
| modify | `src/context_search_tool/vector_store.py` | expose loaded descriptor identity |
| modify | `src/context_search_tool/indexer.py` | BGE runtime-bound reuse/reindex |
| modify | `src/context_search_tool/retrieval_core/candidates.py` | pre-search live identity match |
| modify | `src/context_search_tool/index_health.py` | offline identity parsing/migration |
| modify | `tests/test_embeddings_bge.py` | provider RED/GREEN matrix + live integration |
| modify | `tests/test_embeddings_vector_store.py` | descriptor identity retention |
| modify | `tests/test_indexer_manifest.py` | manifest/descriptor binding |
| modify | `tests/test_incremental_refresh.py` | drift and atomic refresh behavior |
| modify | `tests/test_retrieval_pipeline.py` | query mismatch/no-fallback/privacy |
| modify | `tests/test_index_health.py` | offline identity/legacy/no-network health |
| modify | `tests/test_p5_privacy.py` | safe error/proxy/egress accounting |
| modify | `tests/p8_real_python_graphs_acceptance.py` | delete workaround; capture runtime/performance |
| modify | `tests/test_p8_real_python_graphs_acceptance.py` | acceptance schema/identity tests |
| add | `tests/p13_bge_provider_measurement.py` | clean detached baseline/current candidate measurement envelope |
| add | `tests/test_p13_bge_provider_measurement.py` | measurement instrumentation and guard tests |
| conditional | `README.md`, `docs/retrieval-quality.md` | evidence-backed final disposition |
| evidence | `$(cat .quality/p13-run-root.txt)` | immutable baseline/candidate captures |

---

### Task 0: Freeze Entry, Environment, and Evidence

- [ ] **Step 0.1: HEAD and scoped entry state.** Require HEAD
  `122ed052284fa488943cb4464301a391bd2e7e24`. At design handoff, allow
  exactly these two untracked files and no other delta:
  `docs/superpowers/specs/2026-07-27-p13-bge-provider-hardening-design.md`
  and
  `docs/superpowers/plans/2026-07-27-p13-bge-provider-hardening.md`.
  Create `codex/p13-bge-provider-hardening` only if branch creation is
  authorized. Record:

```bash
git status --short
git status --short --untracked-files=all
git ls-files --others --exclude-standard
git rev-parse HEAD
.quality/p5-runtime/bin/python -VV
.quality/p5-runtime/bin/python -c \
  'import sqlite3,numpy,pytest; print(sqlite3.sqlite_version,numpy.__version__,pytest.__version__)'
```

  Expected: fixed commit; only the two reviewed docs as entry deltas;
  Python 3.13.12, SQLite 3.51.2, NumPy 2.4.2, pytest 9.0.3. The detached
  performance baseline created later must be clean; the candidate runs
  from the current scoped working tree.

- [ ] **Step 0.2: suite baseline.** Run the non-slow suite under the
  fixed command. If the five known P6 nodes fail only because restricted
  macOS `sysctl` access is denied, rerun those exact node IDs
  unrestricted and record both outputs. Any other failure is a STOP.

- [ ] **Step 0.3: create evidence root.** Create
  `.quality/p13-run-root.txt` once. Copy the test outputs and an
  `environment.json` into that root. Evidence files are not committed.

- [ ] **Step 0.4: live preflight gate.** With ambient proxies bypassed:

```bash
curl --noproxy '*' -sS http://localhost:11434/api/version
curl --noproxy '*' -sS http://localhost:11434/api/tags
```

  Require a non-empty version and exactly one `bge-m3:latest` with a
  lowercase 64-hex digest. If absent, status is BLOCKED. Do not start
  Ollama or pull a model without user authorization.

- [ ] **Step 0.5: protect sources and gold.** Resolve the frozen P11
  RedInk/daily source roots and P1 committed fixtures. Record SHA-256
  for protected-source manifests, quality catalog/gold, and the
  acceptance runner. Abort on a later mismatch.

- [ ] **Step 0.6: freeze the measurement contract before edits.**
  Record these already-reviewed limits in
  `$P13_RUN_ROOT/measurement-contract.json`: baseline commit
  `122ed052`, three old-provider and three candidate warm captures,
  alternating baseline/candidate order, per-repo and aggregate
  `/api/embed` request counts, index median, and query p95. Baseline
  max/min spread must be ≤10% for index time and ≤15% for query p95;
  unstable timing is BLOCKED and never widens candidate thresholds.
  The tracked harness named in Task 5 performs the later measurements;
  no temporary runner edit is allowed.

**Verify Task 0:** fixed suite accounted for; live identity pinned or
the unavailability probe recorded; source/gold hashes and the
measurement contract pinned. If live service is unavailable, continue
all offline work through Task 6 and the applicable Task 9
record/review; mark only Tasks 7-8 and live documentation claims
BLOCKED.

---

### Task 1: RED — Freeze the Provider Contract

- [ ] **Step 1.1: URL/session tests** in
  `tests/test_embeddings_bge.py`:
  - empty `base_url` → `http://localhost:11434`;
  - trailing slash is normalized;
  - custom `base_url` reaches its `/api/version`, `/api/tags`, and
    `/api/embed`;
  - provider-created session has `trust_env is False`;
  - a caller-supplied session remains usable and no proxy setting is
    silently changed.

- [ ] **Step 1.2: attestation tests:**
  - `bge-m3` resolves only `bge-m3:latest`;
  - an explicit tag requires exact match;
  - prefix-only, zero-match, two-match, missing-model-list, invalid
    digest, and empty/invalid version cases fail with the frozen safe
    code;
  - preflight happens once across several embed batches;
  - forced postflight bypasses the cache and detects digest, version, or
    canonical-model drift;
  - runtime fingerprint contains canonical model/digest/version/
    base URL/dimensions/transform and no source text;
  - descriptor identity exactly follows the design grammar.

- [ ] **Step 1.3: transform boundary tests:**
  - lengths 0, 3999, and 4000 are byte-for-byte unchanged;
  - length 4001 is exactly `text[:3000] + "\n" + text[-999:]`;
  - dense CJK is counted by code points;
  - the tail sentinel survives and a removed-middle sentinel does not;
  - input list/order is not mutated;
  - request JSON always includes `"truncate": false`.

- [ ] **Step 1.4: batching tests:**
  - 0 inputs → 0 preflight/embed requests and 0 vectors;
  - 1/8 inputs → one request;
  - 9/17 inputs → 2/3 requests;
  - eight 4,000-code-point prepared texts remain one request;
  - responses are flattened in original order.

- [ ] **Step 1.5: response matrix:**
  valid vectors normalize to float32 L2; reject non-object JSON,
  missing/non-list embeddings, wrong count, non-sequence item, scalar,
  2-D, wrong dimensions, nonnumeric, NaN, ±Inf, zero vector, and
  non-finite norm.

- [ ] **Step 1.6: transport/error/privacy matrix:**
  connection and timeout, preflight HTTP error, embed context HTTP 400,
  other embed HTTP error, and JSON decode failure map to the frozen
  codes. Use a unique raw sentinel in source/query and mocked response
  body; assert it is absent from `str(error)`, `repr(error)`, and
  captured logs.

- [ ] **Step 1.7: run RED.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_bge.py -m "not integration"
```

  Confirm failures are the missing P13 behavior, not bad fixtures.

**Checkpoint boundary after GREEN only:** do not create even an
authorized checkpoint for RED alone.

---

### Task 2: GREEN — Harden `BGEEmbeddingProvider`

- [ ] **Step 2.1: safe errors and constants.** In
  `embeddings_bge.py`, add only the BGE base error/subclasses or code
  mapping required by Task 1. The base derives from `ValueError` so the
  existing CLI/MCP boundary remains safe without unrelated handler
  changes. Freeze:

```text
_DEFAULT_BASE_URL = "http://localhost:11434"
_PREFLIGHT_TIMEOUT_SECONDS = 5.0
_EMBED_TIMEOUT_SECONDS = 60.0
_MAX_TEXTS_PER_REQUEST = 8
_MAX_TEXT_CODEPOINTS = 4000
_HEAD_CODEPOINTS = 3000
_TAIL_CODEPOINTS = 999
_INPUT_TRANSFORM_ID = "bge-input-v1"
```

  Delete `_MAX_CHARS_PER_REQUEST`.

- [ ] **Step 2.2: implement lazy attestation.** Add one cached immutable
  runtime-attestation value. Use exact canonical-name lookup and
  validate payloads without including bodies in errors. `fingerprint()`
  stays network-free and static; a separately named
  `runtime_fingerprint()` performs/returns attestation, and
  `assert_runtime_unchanged()` bypasses the cache for production
  postflight. Empty input returns before either method is invoked.

- [ ] **Step 2.3: implement one private input transform.** Apply it
  before batching for every provider call. Do not add tokenizers,
  model-specific packages, or a second fallback transform.

- [ ] **Step 2.4: implement count-only batching and embed request.**
  Preserve order, send `truncate: false`, and use the configured root.
  No retry and no source metadata.

- [ ] **Step 2.5: implement strict response validation.** Convert only
  after structural checks, require finite/nonzero exact-dimension
  vectors, normalize float32, and build a local result list so the
  method cannot return partial results.

- [ ] **Step 2.6: GREEN and focused regression.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_bge.py -m "not integration"
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_vector_store.py tests/test_manifest_v2.py
```

- [ ] **Step 2.7:** `git diff --check`; optional authorized checkpoint:
  `feat: harden native BGE provider (P13 Task 2)`. Without commit
  authorization, record the verified diff and continue.

---

### Task 3: RED/GREEN — Bind BGE Runtime Identity

- [ ] **Step 3.1: define the narrow generic seam.** In
  `embeddings.py`, add a helper that returns:
  - plain `embedding_config_hash` for hash/openai-compatible;
  - attested BGE descriptor identity for BGE.

  Do not make openai-compatible perform a new network call. Keep the
  helper small; do not introduce a provider registry or inheritance
  hierarchy.

- [ ] **Step 3.2: RED vector-store tests.** A loaded
  `NumpyVectorStore` exposes the exact descriptor
  `embedding_identity`; fresh stores expose `None`. Every load path
  (`load_published_snapshot`, bound v2 load, verified load) retains it.
  Close/reopen does not alter it.

- [ ] **Step 3.3: GREEN vector store.** Store the value as private
  metadata and expose a read-only property. Vector payload/descriptor
  schema and serialization remain unchanged.

- [ ] **Step 3.4: RED manifest/indexer tests.**
  - new BGE index: manifest config hash stays static; descriptor gets
    the exact attested identity; manifest descriptor SHA binds it;
  - exact live identity reuses vectors;
  - model digest/version/transform change forces full vector rebuild;
  - legacy config-hash-only BGE identity forces rebuild;
  - hash and openai-compatible descriptors remain plain config hashes;
  - a custom/fake provider used by tests cannot accidentally bypass a
    configured BGE identity assertion;
  - drift after one or more successful embed batches but before
    publication aborts and preserves the old snapshot.

- [ ] **Step 3.5: GREEN authoritative index.** Resolve the BGE identity
  before vector reuse. Thread two explicitly named values:
  `embedding_config_identity` for the manifest and
  `vector_embedding_identity` for the descriptor. Remove ambiguous
  local names only where touched by P13. After the final embed call,
  invoke `assert_runtime_unchanged()` before vector freeze/publication.

- [ ] **Step 3.6: RED/GREEN every vector load/validator path.** Cover
  and update `read_v5_vector_snapshot`,
  `_load_validated_v5_vector_tuple`, `_prepared_external_validator`,
  `_external_v5_validator`, published-snapshot load, and bound-ready
  load:
  - manifest/operational descriptor SHA, generation, byte counts,
    dimensions, rows, and IDs remain exact;
  - BGE descriptor grammar/config-hash relation is checked offline;
  - the descriptor's actual runtime identity is then passed to the
    vector store's exact identity check;
  - hash/openai-compatible still require plain equality;
  - no vector-store API accepts a permissive identity predicate.

- [ ] **Step 3.7: RED/GREEN incremental refresh.**
  - quiet source inventory + exact identity → current no-op;
  - quiet inventory + BGE runtime drift → authoritative reindex;
  - changed files + drift → full vector rebuild, never mixed rows;
  - preflight or forced postflight failure preserves the old committed
    snapshot;
  - egress outcome is `possible` after a request without response and
    `performed` after any preflight/postflight response, including a
    quiet BGE refresh;
  - hash quick-refresh work counters remain pinned.

- [ ] **Step 3.8: focused verification.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_vector_store.py \
  tests/test_indexer_manifest.py \
  tests/test_incremental_refresh.py \
  tests/test_p5_privacy.py
```

- [ ] **Step 3.9:** `git diff --check`; optional authorized checkpoint:
  `feat: bind BGE runtime identity to vector snapshots (P13 Task 3)`.
  Without commit authorization, record the verified diff and continue.

---

### Task 4: RED/GREEN — Reject Query-Time Runtime Drift

- [ ] **Step 4.1: RED query tests** in
  `tests/test_retrieval_pipeline.py`:
  - exact live BGE identity embeds and searches normally;
  - digest mismatch, version mismatch, and transform mismatch raise the
    correct safe error before `NumpyVectorStore.search`;
  - a provider that changes after returning query vectors is caught by
    forced postflight before `NumpyVectorStore.search`;
  - legacy BGE identity raises `bge_reindex_required`;
  - mismatch never invokes hash, lexical-only completion, or planner
    fallback;
  - raw query sentinel is absent from exception/log text;
  - hash query membership remains byte-identical.

- [ ] **Step 4.2: GREEN candidate check.** After loading the manifest-
  bound vector snapshot but before embedding query variants, resolve
  the provider identity and compare it to
  `vector_store.embedding_identity`. After all variants are embedded,
  call `assert_runtime_unchanged()` before the first search. Keep
  variant fallback behavior unchanged for ordinary embedding errors;
  both preflight and postflight identity errors live outside that
  fallback and are non-fallback failures.

- [ ] **Step 4.3: RED/GREEN offline health.**
  - valid BGE v1 identity parses and its config-hash segment matches the
    manifest;
  - malformed/mismatched identity is an integrity failure;
  - legacy BGE identity requests authoritative reindex;
  - status makes zero HTTP calls;
  - hash/openai-compatible status payloads stay pinned.

- [ ] **Step 4.4: focused verification.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_retrieval_pipeline.py \
  tests/test_index_health.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py
```

- [ ] **Step 4.5:** `git diff --check`; optional authorized checkpoint:
  `feat: reject stale BGE query runtimes (P13 Task 4)`. Without commit
  authorization, record the verified diff and continue.

---

### Task 5: RED/GREEN — Product Path, Atomicity, and Capture Schema

- [ ] **Step 5.1: RED known-defect regression.** Build the same
  6,924-character dense-CJK embedding text shape observed in P11,
  including a tail lexical sentinel. Index through the public product
  path with a contract-faithful fake Ollama session. Assert:
  - no acceptance-runner monkeypatch;
  - sent text is 4,000 code points;
  - head and tail sentinels survive;
  - `truncate` is false;
  - the index publishes and queries.

- [ ] **Step 5.2: RED atomicity fault matrix.** From a readable
  committed index, fail BGE at:
  preflight, first batch, middle batch after successful responses,
  response validation, forced postflight after successful batches,
  frozen-vector preparation, and descriptor/manifest publication fault
  hooks. After each failure assert old manifest/descriptor SHA,
  generation, SQLite binding, vector IDs, and a pinned query result are
  unchanged.

- [ ] **Step 5.3: GREEN only as needed.** Reuse existing indexer atomic
  preparation/publication. Make no new transaction abstraction unless
  a RED test proves an actual gap.

- [ ] **Step 5.4: remove capture workaround.** Delete
  `_BGE_MAX_TEXT_CHARS`, `_install_bge_truncation`, its invocation, and
  its idempotence tests from the P8/P11 acceptance runner. The provider
  is now the single transform owner.

- [ ] **Step 5.5: capture schema v4.** Set the existing acceptance
  runner's `CAPTURE_SCHEMA_VERSION = 4` exactly once. It is
  provider-discriminated:
  - `hash` requires its static config and descriptor identity; canonical
    model, digest, Ollama version, transform ID, and pre/post
    attestation fields are explicitly `null`, and any Ollama call is a
    validation failure;
  - `bge` requires configured provider/model/dimensions, canonical
    model, digest, raw version, `bge-input-v1`, exact descriptor
    identity, and matching pre/post attestation.

  Validation fails, rather than annotates, on any disagreement. Schema
  v3 remains historical evidence, is accepted only as nested input to
  the legacy measurement envelope, and is never silently upgraded or
  accepted by native v4 validation.

- [ ] **Step 5.6: tracked paired-measurement harness.** Add
  `tests/p13_bge_provider_measurement.py` with envelope schema
  `p13-bge-provider-measurement-v1`. It:
  - accepts an exact implementation root, protected source root, output
    path, repetition count, and mode `legacy-baseline|native`;
  - exposes a `paired` command that alternates
    baseline/native, native/baseline, baseline/native for three pairs
    and warms the exact model before each capture;
  - keeps the controller free of `context_search_tool` imports and
    starts one fresh child process per individual capture with
    `PYTHONPATH=<target>/src:<target>/tests`;
  - runs the child with the fixed Python's `-P` safe-path mode so the
    controller's repository does not enter the target import path;
  - asserts in each child that `context_search_tool`,
    `embeddings_bge`, and the loaded target runner resolve inside the
    requested root; records their root-relative paths and SHA-256
    values;
  - refuses `legacy-baseline` unless the implementation root is a clean
    detached worktree at
    `122ed052284fa488943cb4464301a391bd2e7e24`;
  - loads that implementation root's P8 runner, so only the legacy mode
    retains that baseline runner's documented head-4,000 workaround;
  - wraps the target provider's `_embed_batch` read-only to count
    `/api/embed` calls without changing request text, batches, or
    responses;
  - records its own source SHA, target runner SHA, target commit/dirty
    state, effective transform (`p11-runner-head-4000` or
    `bge-input-v1`), live identity, request counts, and timing;
  - refuses `native` if the legacy monkeypatch marker is installed.
  - performs proxy-bypassed tags/version attestation in the controller
    immediately before and after every child; drift invalidates the
    capture, including the legacy path.

  Both trees are measured through the same outer envelope; the legacy
  transform is permitted only for measuring the accepted pre-P13
  provider, never for candidate correctness or quality.

- [ ] **Step 5.7: runner tests.** Cover schema validation, missing
  identity fields, legacy schema rejection, no monkeypatch, model drift
  during capture, timing-excluded repeat comparison, and protected-
  source/gold hash checks. In
  `tests/test_p13_bge_provider_measurement.py`, cover exact baseline
  commit/cleanliness guards, native refusal of the legacy marker,
  request counting without payload mutation, fresh-process isolation,
  module-origin rejection, controller pre/post drift, and both recorded
  transform identities. Hash schema tests assert all BGE-only fields
  are null and no Ollama call occurs.

- [ ] **Step 5.8: focused verification.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_bge.py \
  tests/test_indexer_manifest.py \
  tests/test_incremental_refresh.py \
  tests/test_p8_real_python_graphs_acceptance.py \
  tests/test_p13_bge_provider_measurement.py
```

- [ ] **Step 5.9:** `git diff --check`; optional authorized checkpoint:
  `test: make BGE product captures provider-native (P13 Task 5)`.
  Without commit authorization, record the verified diff and continue.

---

### Task 6: Fixed-Runtime Regression Closure

- [ ] **Step 6.1: exact characterizations.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_retrieval_core_characterization.py \
  tests/test_retrieval_trace_pipeline.py
```

  No snapshot, pin, or expected-membership edit is permitted.

- [ ] **Step 6.2: full non-slow suite.** Run the fixed command with
  `-m "not slow"`. Rerun only the known P6 `sysctl` nodes unrestricted
  if necessary. Compare exact accounting to Task 0.

- [ ] **Step 6.3: static hygiene.** Run repository-declared lint/type
  commands if present, `git diff --check`, and inspect
  `git diff --stat 122ed052`,
  `git status --short --untracked-files=all`, and
  `git ls-files --others --exclude-standard`. For every untracked file,
  also run `git diff --no-index --check /dev/null <path>` and interpret
  exit `1` with empty diagnostics as clean (the file is merely new);
  any whitespace diagnostic or exit greater than `1` fails the check.
  Verify every tracked or untracked changed file appears in the Planned
  File Map or is explicitly justified in the implementation record.

- [ ] **Step 6.4: hash identity proof.** Build/query/refresh a hash
  fixture from a clean detached baseline and from the current scoped
  candidate working tree. Descriptor identity, manifest/config hashes,
  membership, trace projection, and no-op work counters must match.

- [ ] **Step 6.5:** optional authorized checkpoint:
  `test: close fixed-runtime BGE hardening regressions (P13 Task 6)`.
  Without commit authorization, record the verified diff and continue.

**STOP:** any characterization or hash drift. Never repin.

Task 6 is mandatory even when Ollama is unavailable; it closes the
offline implementation state before a BLOCKED report.

---

### Task 7: Live BGE Correctness and Provider Performance

- [ ] **Step 7.1: revalidate live identity.** Compare current
  version/digest to Task 0. A change invalidates the baseline and stops
  the run; do not mix captures.

- [ ] **Step 7.2: live provider integration.**

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  .quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_embeddings_bge.py -m integration
```

  Exercise English, Chinese, mixed-language, 4,000-code-point, and
  known dense-CJK-overflow inputs.

- [ ] **Step 7.3: singleton/batch equivalence.** Embed the same frozen
  inputs alone and in batches of eight. Require cosine ≥ `0.999999` and
  maximum absolute component delta ≤ `1e-5`; record the actual maxima.

- [ ] **Step 7.4: reproducible old-provider/candidate captures.** Add a
  clean detached baseline worktree, then use the tracked, hashed
  harness from Task 5 for both trees:

```bash
P13_RUN_ROOT=$(cat .quality/p13-run-root.txt)
git worktree add --detach "$P13_RUN_ROOT/baseline-tree" \
  122ed052284fa488943cb4464301a391bd2e7e24
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD/tests" \
  .quality/p5-runtime/bin/python -P \
  tests/p13_bge_provider_measurement.py paired \
  --baseline-root "$P13_RUN_ROOT/baseline-tree" \
  --candidate-root "$PWD" \
  --sources "$(cat .quality/p8-baseline-root.txt)" \
  --output "$P13_RUN_ROOT/provider-paired.json" \
  --pairs 3
```

  The harness alternates capture order and warms before every capture.
  The baseline envelope must report
  `p11-runner-head-4000`; candidate must report `bge-input-v1`.
  Record `/api/embed` requests, prepared lengths, index wall time,
  query p50/p95, identities, and non-timing results. Do not compare
  baseline/candidate retrieval membership because their transforms
  differ; this step compares provider cost only.

- [ ] **Step 7.5: evaluate engineering gates.** Compare medians/p95 to
  the paired file:
  - baseline max/min spread satisfies Task 0's 10%/15% stability gate;
  - request count is non-increasing per repo and strictly lower in
    aggregate;
  - index median ≤ `1.10x` old BGE;
  - query p95 ≤ `1.15x` old BGE;
  - repeated non-timing results identical.

  Write `engineering-gates.json` with every numerator, denominator,
  ratio, threshold, pass/fail, and evidence path.

- [ ] **Step 7.6: failure disposition.** Any correctness/privacy/
  identity/atomicity failure rejects the implementation. A performance
  failure prevents engineering readiness under v1; record it without
  changing batch size or thresholds.

---

### Task 8: Independent Hash-vs-BGE Product Evaluation

Run only if every Task 7 engineering gate passes.

- [ ] **Step 8.1: freeze comparison inputs.** Recheck protected-source
  and gold hashes. Use candidate P13 code on both sides. Planner is
  disabled, relation quota remains inert, and retrieval configuration
  is identical except:

```text
hash: provider=hash, frozen hash model/dimensions
bge:  provider=bge, model=bge-m3, dimensions=1024
```

- [ ] **Step 8.2: paired captures.** Capture hash twice and BGE twice
  on the P11 frozen RedInk/daily corpus. Run existing P1 BGE profiles
  without changing their gold. Every BGE capture asserts the exact
  Task 7 live identity. Every hash capture asserts static
  config/descriptor identity, null BGE-only fields, and zero Ollama
  calls.

- [ ] **Step 8.3: deterministic check.** Within each provider, compare
  captures excluding only declared timing/implementation fields.
  Membership or metric drift is a STOP.

- [ ] **Step 8.4: quality comparison.** Produce
  `product-comparison.json` and enumerate:
  combined/per-repo Recall@12, newly satisfied required items, lost
  required items, noise ratio, P1 profile outcomes, query p50/p95,
  index wall time, and BGE/hash ratios.

- [ ] **Step 8.5: apply all recommendation gates verbatim:**
  - recall non-decreasing;
  - zero required losses;
  - at least one newly satisfied required;
  - noise does not increase;
  - no P1 BGE profile regression;
  - query p95 ratio ≤ `1.50`;
  - index ratio ≤ `50` on each real repo;
  - capture-twice stable.

- [ ] **Step 8.6: write disposition before documentation edits.**
  Select exactly one:
  - `supported-opt-in-and-recommended`;
  - `supported-opt-in-no-recommendation`;
  - `reject`;
  - `blocked`.

  Do not flip the default in any branch.

---

### Task 9: Documentation and Implementation Record

- [ ] **Step 9.1: implementation record.** Append to this plan:
  commit list, changed files, fixed-suite accounting, raw live identity,
  legacy migration behavior, transform examples, request-count and
  latency arithmetic, engineering-gate table, recommendation-gate
  table, evidence paths, and final disposition.
  If live work is BLOCKED, record completed offline gates and name every
  unrun live field as `not_run`, never zero/pass.

- [ ] **Step 9.2: README.** Only after a non-BLOCKED live disposition:
  - document `base_url`, exact model requirement, reindex-on-runtime-
    change, no silent fallback, transform ID, and privacy behavior;
  - replace “fast inference/minimal overhead” language with measured
    paired costs;
  - label BGE supported/recommended/experimental exactly as the
    disposition permits;
  - keep hash as default.

- [ ] **Step 9.3: retrieval-quality docs.** Record how to run live BGE
  profiles, capture runtime identity, distinguish BLOCKED from fail,
  and reproduce the P13 comparison. Under BLOCKED, document commands
  and missing precondition without making provider claims.

- [ ] **Step 9.4: final verification.** Re-run changed-doc link checks,
  focused tests, full fixed suite, `git diff --check`, and worktree
  status. No generated evidence or `.quality` runtime files are staged.

- [ ] **Step 9.5: final review.** Run a fresh Standards and Spec agent
  review over the implementation diff from
  `122ed052284fa488943cb4464301a391bd2e7e24`; resolve findings or record
  an explicit user-owned decision.

  Steps 9.1, 9.3, 9.4, and 9.5 run even when Tasks 7-8 are BLOCKED.

- [ ] **Step 9.6:** final commit only if authorized:
  `docs: record P13 BGE provider disposition`.

## Stop Conditions

- Ollama or exact `bge-m3:latest` is unavailable for live gates:
  **BLOCKED**, never mocked into a pass.
- Model digest or Ollama version changes between baseline, candidate,
  or repeated captures: invalidate the run and restart from Task 0.
- Any hash characterization, vector identity, retrieval membership,
  trace, counter, or gold drift: STOP, never repin.
- Product code still needs the acceptance-runner truncation: reject.
- Ollama silently truncates because `truncate: false` is absent: reject.
- A prepared 4,000-code-point known input still hits context overflow:
  reject v1 transform; do not add a second transform after comparison.
- Singleton/batch equivalence misses either tolerance: reject the
  batching contract.
- Live runtime mismatch reaches vector search or silently degrades:
  reject.
- A failed batch changes the published snapshot or query behavior:
  reject.
- Any raw source/query sentinel appears in error/log text: reject.
- Current-BGE paired performance gate fails: engineering readiness
  fails; no tuning in this run.
- Recommendation gate fails: no recommendation/default change. It does
  not retroactively fail an otherwise passing engineering disposition.
- Any quota, planner, ranking, chunking, gold, or post-comparison
  threshold edit appears in the diff: stop and remove it.

## Implementation Record

Status: NOT STARTED.

The fixed environment is restored and verified at design time, but
local Ollama is currently unavailable. No live engineering or product
gate has been claimed.
