# Index Storage Slimming (Lexical Token Layout v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Date: 2026-07-26
Status: Ready for review
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: branch `fix/bounded-context-merge` at `49daea3`

**Goal:** Cut on-disk index size by ~33% (87 MB → ~58 MB on this repository) by
replacing the 64-char hex `chunk_id` foreign key in `chunk_tokens` with an
integer reference, without changing any retrieval output.

**Architecture:** `chunks` gains an explicit `chunk_ref INTEGER PRIMARY KEY`
(a rowid alias, stable across `VACUUM`), `chunk_id` becomes `TEXT NOT NULL
UNIQUE`. `chunk_tokens` stores `(chunk_ref, token)` instead of
`(chunk_id, token)`. A stored `storage_layout_version` metadata key gates the
layout the same way `signal_schema_version` gates the v5 graph schema: `cst
index` auto-rebuilds an old-layout index; query paths fail with a clean coded
error instead of a raw SQLite error.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`. No new dependencies.

## Measured Motivation (2026-07-26, this repository)

`dbstat` breakdown of the 87 MB `index.sqlite` (9.2 MB source corpus):

```text
chunk_tokens             36.8 MB   453,112 rows x 64-char hex chunk_id
idx_chunk_tokens_token    7.8 MB
chunks                   17.4 MB
chunks_fts_content       15.4 MB
chunks_fts_data           6.5 MB
```

Prototype measurement (real data, ATTACH + rebuilt tables):

```text
chunk_tokens today (table + token index):  43.2 MB
integer-ref layout (table + index + map):  14.4 MB   (-66%, -28.8 MB)
```

`VACUUM` reclaims only 2% (86.6 MB → 84.6 MB); the bloat is structural, so a
compaction path is not worth adding.

## Global Constraints

- Zero retrieval-output change: `tests/test_retrieval_core_characterization.py`
  must pass unchanged (frozen P7 trace hashes) on the supported runtime.
- Supported acceptance runtime: `.quality/p5-runtime/bin/python`
  (Python 3.13.12, SQLite 3.51.2). The `.venv` interpreter is Python 3.14 and
  fails 3 characterization/trace tests for unrelated platform-drift reasons;
  do not chase those.
- SQLite feature floor: 3.39.4 (CI matrix includes windows-latest /
  Python 3.11, whose bundled SQLite is 3.39.4). Do not use `contentless_delete`
  FTS (needs 3.43). Avoid `RETURNING` (3.35+, works, but a plain SELECT is
  version-proof and just as clear).
- Per-chunk token order must survive round-trips: `DocumentChunk.lexical_tokens`
  is read back `ORDER BY rowid` and feeds `followup_keywords`.
- Do not modify P6 benchmark policy or `scripts/p6_benchmark.py`.
- Do not touch `chunks_fts` layout in this plan (see Deferred).
- Known pre-existing failures on this machine (do not fix, do not regress):
  4 `tests/test_p6_measurement_worker.py` worker-subprocess tests; plus 6 more
  p6 gates that fail only while the working tree is dirty (they require
  `dirty_production_source == false`). Full-suite target on a clean committed
  tree: 2897+ passed, only the 4 known worker failures.
- TDD per task; one commit per task; do not push.

## File Structure

- Modify: `src/context_search_tool/sqlite_store.py` — all DDL and every
  `chunk_tokens` read/write/delete site (the layout is fully encapsulated here;
  `index_health.py`, `indexer.py`, `manifest.py` do not reference the table).
- Modify: `src/context_search_tool/retrieval.py` — preflight layout guard at
  the two `db_path` checks (`query_repository`, `trace_repository` area,
  lines ~129 and ~247).
- Modify: `src/context_search_tool/cli.py` — register the new error in the
  existing incompatible-error mapping (imports at lines 33-45).
- Test: `tests/test_sqlite_store.py` (layout gate, round-trip, migration),
  `tests/test_retrieval_pipeline.py` (preflight guard).
- Modify: `README.md` — one troubleshooting entry.

---

### Task 1: Storage layout version gate

**Files:**
- Modify: `src/context_search_tool/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

**Interfaces:**
- Produces: `TARGET_STORAGE_LAYOUT_VERSION = 2` (module constant),
  `STORAGE_LAYOUT_VERSION_KEY = "storage_layout_version"`,
  `class IncompatibleStorageLayoutError(RuntimeError)` with
  `code = "incompatible_storage_layout"` and attribute `stored_version: int`,
  `SQLiteStore.inspect_storage_layout_version() -> int` (0 when the key or the
  `index_metadata` table is absent),
  `SQLiteStore.require_current_storage_layout() -> None` (raises
  `IncompatibleStorageLayoutError` unless stored == TARGET).
- Consumes: existing `_stored_signal_schema_version` /
  `IncompatibleSignalSchemaError` as the pattern to mirror (sqlite_store.py:989,
  5806).

- [ ] **Step 1: Write the failing tests**

```python
def test_initialize_stamps_current_storage_layout(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    assert store.inspect_storage_layout_version() == 2
    store.require_current_storage_layout()


def test_storage_layout_guard_rejects_old_and_newer_layouts(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    with sqlite3.connect(tmp_path / "index.sqlite") as connection:
        connection.execute(
            "UPDATE index_metadata SET value = '3' WHERE key = ?",
            (sqlite_store_module.STORAGE_LAYOUT_VERSION_KEY,),
        )
    with pytest.raises(sqlite_store_module.IncompatibleStorageLayoutError) as newer:
        store.require_current_storage_layout()
    assert newer.value.stored_version == 3
    assert newer.value.code == "incompatible_storage_layout"

    with sqlite3.connect(tmp_path / "index.sqlite") as connection:
        connection.execute(
            "DELETE FROM index_metadata WHERE key = ?",
            (sqlite_store_module.STORAGE_LAYOUT_VERSION_KEY,),
        )
    with pytest.raises(sqlite_store_module.IncompatibleStorageLayoutError) as older:
        store.require_current_storage_layout()
    assert older.value.stored_version == 0
```

(`import pytest` is already available in `tests/test_sqlite_store.py`? It is
not — add `import pytest` to the file's imports.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_sqlite_store.py -k storage_layout`
Expected: FAIL with `AttributeError: ... has no attribute 'inspect_storage_layout_version'`

- [ ] **Step 3: Implement the gate**

In `sqlite_store.py`, next to the signal-schema constants:

```python
STORAGE_LAYOUT_VERSION_KEY = "storage_layout_version"
TARGET_STORAGE_LAYOUT_VERSION = 2


class IncompatibleStorageLayoutError(RuntimeError):
    code = "incompatible_storage_layout"

    def __init__(self, stored_version: int) -> None:
        self.stored_version = stored_version
        super().__init__(
            "index storage layout "
            f"{stored_version} is not supported; run `cst index` to rebuild"
        )
```

Helper next to `_stored_signal_schema_version` (line ~5806), same shape:

```python
def _stored_storage_layout_version(connection: sqlite3.Connection) -> int:
    if not _table_exists(connection, "index_metadata"):
        return 0
    row = connection.execute(
        "SELECT value FROM index_metadata WHERE key = ?",
        (STORAGE_LAYOUT_VERSION_KEY,),
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0
```

Methods on `SQLiteStore` (next to `inspect_signal_schema_version`, line ~989):

```python
def inspect_storage_layout_version(self) -> int:
    with self._connect() as connection:
        return _stored_storage_layout_version(connection)

def require_current_storage_layout(self) -> None:
    stored = self.inspect_storage_layout_version()
    if stored != TARGET_STORAGE_LAYOUT_VERSION:
        raise IncompatibleStorageLayoutError(stored)
```

In `initialize()`, after the schema statements run, stamp the version using the
existing `_set_metadata_row(connection, key, value, now)` helper:

```python
_set_metadata_row(
    connection,
    STORAGE_LAYOUT_VERSION_KEY,
    str(TARGET_STORAGE_LAYOUT_VERSION),
    _now(),
)
```

(Locate `initialize()` and reuse whatever metadata-write helper it already has
in scope; `_set_metadata_row` is the one the v5 migration uses.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_sqlite_store.py`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat: add storage layout version gate"
```

---

### Task 2: Integer token reference layout

**Files:**
- Modify: `src/context_search_tool/sqlite_store.py` (DDL ~5103-5155; insert
  ~2858-2932; reads ~2286, ~2644, ~2937, ~2965; delete ~2833)
- Test: `tests/test_sqlite_store.py`

**Interfaces:**
- Consumes: Task 1's `TARGET_STORAGE_LAYOUT_VERSION` stamp (already written by
  `initialize()`).
- Produces: on-disk layout v2. Public `SQLiteStore` method signatures are
  unchanged — `token_search`, `token_counts_for_profile`, `stats`,
  `replace_chunks`, `chunk_for_id`, `chunks_for_ids` keep exact behavior.

- [ ] **Step 1: Write the failing round-trip test**

```python
def test_lexical_tokens_round_trip_preserves_order_in_layout_v2(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = _chunk("order-chunk", "src/Order.java", ["zeta", "alpha", "zeta2"])
    store.replace_chunks(chunk.file_path, [chunk])

    loaded = store.chunk_for_id("order-chunk")

    assert loaded.lexical_tokens == ["zeta", "alpha", "zeta2"]
    with sqlite3.connect(tmp_path / "index.sqlite") as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(chunk_tokens)")
        }
    assert columns == {"chunk_ref", "token"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_sqlite_store.py -k layout_v2`
Expected: FAIL — `columns == {"chunk_id", "token"}`

- [ ] **Step 3: Change the DDL**

In `_common_schema_statements()` (line ~5103), `chunks` becomes:

```sql
CREATE TABLE IF NOT EXISTS chunks (
    chunk_ref INTEGER PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    embedding_id TEXT,
    deleted_at INTEGER,
    metadata TEXT NOT NULL
)
```

`chunk_tokens` becomes:

```sql
CREATE TABLE IF NOT EXISTS chunk_tokens (
    chunk_ref INTEGER NOT NULL,
    token TEXT NOT NULL,
    FOREIGN KEY (chunk_ref) REFERENCES chunks(chunk_ref)
)
```

`idx_chunk_tokens_token` is unchanged. `chunk_symbols` (187 rows) stays on
`chunk_id` — not worth touching.

- [ ] **Step 4: Update the write path**

In `_insert_chunk` (~2858): the chunks upsert SQL is unchanged (it names its
columns; `chunk_ref` self-assigns). After the upsert, resolve the ref and use
it for tokens:

```python
chunk_ref = connection.execute(
    "SELECT chunk_ref FROM chunks WHERE chunk_id = ?",
    (chunk.chunk_id,),
).fetchone()[0]
connection.executemany(
    """
    INSERT INTO chunk_tokens (chunk_ref, token)
    VALUES (?, ?)
    """,
    [(chunk_ref, token) for token in chunk.lexical_tokens],
)
```

(Do not use `cursor.lastrowid` — the upsert's DO UPDATE branch does not set it
reliably. Do not use `RETURNING` — plain SELECT is version-proof.)

- [ ] **Step 5: Update the four read/delete sites**

`token_search` (~2286):

```sql
SELECT chunks.chunk_id, chunk_tokens.token
FROM chunk_tokens
JOIN chunks ON chunks.chunk_ref = chunk_tokens.chunk_ref
WHERE chunks.deleted_at IS NULL
  AND chunk_tokens.token IN ({placeholders})
```

`token_counts_for_profile` (~2644):

```sql
SELECT chunk_tokens.token, COUNT(*) AS count
FROM chunk_tokens
JOIN chunks ON chunks.chunk_ref = chunk_tokens.chunk_ref
WHERE chunks.deleted_at IS NULL
GROUP BY chunk_tokens.token
ORDER BY count DESC, chunk_tokens.token
LIMIT ?
```

`stats` (~2671): `SELECT COUNT(*) AS count FROM chunk_tokens` — unchanged.

`_chunk_from_row` (~2937) — the row now carries `chunk_ref` (SELECT \*):

```sql
SELECT token
FROM chunk_tokens
WHERE chunk_ref = ?
ORDER BY rowid
```

bound with `(row["chunk_ref"],)`.

`_chunks_from_rows` (~2965):

```sql
SELECT chunks.chunk_id, chunk_tokens.token
FROM chunk_tokens
JOIN chunks ON chunks.chunk_ref = chunk_tokens.chunk_ref
WHERE chunks.chunk_id IN ({placeholders})
ORDER BY chunk_tokens.rowid
```

Delete path (~2833):

```sql
DELETE FROM chunk_tokens
WHERE chunk_ref IN (
    SELECT chunk_ref FROM chunks WHERE chunk_id IN ({placeholders})
)
```

- [ ] **Step 6: Run the store suites**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_sqlite_store.py tests/test_sqlite_store_query_work.py`
Expected: all pass. Two tests trace SQL text and may need their match strings
updated — `test_sqlite_store_query_work.py:57` matches
`" from chunk_tokens "` and `test_sqlite_store.py:618` matches
`"from chunk_tokens"`; both still appear in the new SQL, so they should pass
untouched. If one fails, fix the match string, never the traced behavior.

- [ ] **Step 7: Run the wider net**

Run: `.quality/p5-runtime/bin/python -m pytest -q -m "not slow" -p no:cacheprovider`
Expected: no new failures beyond the documented pre-existing set (dirty-tree
p6 gates fire until the commit below; re-check after committing).

- [ ] **Step 8: Commit**

```bash
git add src/context_search_tool/sqlite_store.py tests/test_sqlite_store.py
git commit -m "perf: store lexical tokens against integer chunk refs"
```

Then: `.quality/p5-runtime/bin/python -m pytest -q -m "not slow" -p no:cacheprovider`
Expected on the clean tree: only the 4 known worker failures.

---

### Task 3: Auto-rebuild migration on `cst index`

**Files:**
- Modify: `src/context_search_tool/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

**Interfaces:**
- Consumes: Task 1 gate, Task 2 DDL, existing
  `FULL_REINDEX_REQUIRED_KEY = "full_reindex_required"`
  (`graph_lifecycle.py:18`) and the v5 migration shape
  (`migrate_signal_schema_v5`, sqlite_store.py:~1051).
- Produces: `SQLiteStore.migrate_storage_layout_v2() -> None`, called from
  `initialize()` before the schema statements run.

- [ ] **Step 1: Write the failing test**

```python
def _create_layout_v1_index(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                embedding_id TEXT,
                deleted_at INTEGER,
                metadata TEXT NOT NULL
            );
            CREATE TABLE chunk_tokens (
                chunk_id TEXT NOT NULL,
                token TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE chunks_fts
            USING fts5(chunk_id UNINDEXED, file_path, content, tokens);
            CREATE TABLE index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            INSERT INTO chunks VALUES
                ('old-1', 'src/App.java', 1, 5, 'class App {}',
                 'symbol', 'old-1', NULL, '{}');
            INSERT INTO chunk_tokens VALUES ('old-1', 'app');
            """
        )


def test_initialize_rebuilds_layout_v1_index_and_requires_full_reindex(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "index.sqlite"
    _create_layout_v1_index(db_path)

    store = SQLiteStore(db_path)
    store.initialize()

    store.require_current_storage_layout()
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(chunk_tokens)")
        }
        chunk_count = connection.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]
        full_reindex = connection.execute(
            "SELECT value FROM index_metadata WHERE key = 'full_reindex_required'"
        ).fetchone()[0]
    assert columns == {"chunk_ref", "token"}
    assert chunk_count == 0
    assert full_reindex == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_sqlite_store.py -k rebuilds_layout_v1`
Expected: FAIL — old-layout `chunks` survives (`CREATE TABLE IF NOT EXISTS`
skips it), `require_current_storage_layout()` may raise, or the column set is
`{"chunk_id", "token"}` depending on where initialize currently stops.

- [ ] **Step 3: Implement the migration**

Mirror `migrate_signal_schema_v5`'s transaction discipline (BEGIN IMMEDIATE,
re-check stored version inside the transaction, rollback on error). Called at
the top of `initialize()`:

```python
def migrate_storage_layout_v2(
    self,
    *,
    busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
) -> None:
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = _open_connection(self.db_path, busy_timeout_ms)
    try:
        stored = _stored_storage_layout_version(connection)
        if stored > TARGET_STORAGE_LAYOUT_VERSION:
            raise IncompatibleStorageLayoutError(stored)
        if stored == TARGET_STORAGE_LAYOUT_VERSION:
            return
        if not _table_exists(connection, "chunks"):
            return  # fresh database; initialize() will create v2 directly
        connection.execute("BEGIN IMMEDIATE")
        stored = _stored_storage_layout_version(connection)
        if stored == TARGET_STORAGE_LAYOUT_VERSION:
            connection.rollback()
            return
        for table in (
            "chunk_tokens",
            "chunk_symbols",
            "symbols",
            "chunks_fts",
            "chunks",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        now = _now()
        _set_metadata_row(connection, FULL_REINDEX_REQUIRED_KEY, "1", now)
        _set_metadata_row(
            connection,
            STORAGE_LAYOUT_VERSION_KEY,
            str(TARGET_STORAGE_LAYOUT_VERSION),
            now,
        )
        connection.commit()
    except BaseException as error:
        if connection.in_transaction:
            connection.rollback()
        _raise_if_busy(error)
        raise
    finally:
        connection.close()
```

Notes for the implementer:
- `FULL_REINDEX_REQUIRED_KEY` lives in `graph_lifecycle.py`; import the string
  or redefine the literal `"full_reindex_required"` locally, matching how
  sqlite_store currently references operational keys (check imports first;
  sqlite_store must not grow an import cycle — if `graph_lifecycle` imports
  `sqlite_store`, use the string literal with a comment pointing at
  `graph_lifecycle.FULL_REINDEX_REQUIRED_KEY`).
- Dropping `chunks` invalidates vector/graph derived state; setting
  `full_reindex_required=1` routes the next index build through the existing
  full-rebuild path (`indexer.py:1166`), which regenerates chunks, vectors,
  signals, and associations. If `index_metadata` does not exist yet, create it
  first with the existing DDL (same statement as `_common_schema_statements`).
- The metadata table itself is preserved — only chunk-derived tables drop.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_sqlite_store.py`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat: auto-rebuild layout v1 indexes on cst index"
```

---

### Task 4: Query preflight guard and CLI error mapping

**Files:**
- Modify: `src/context_search_tool/retrieval.py` (~129, ~247)
- Modify: `src/context_search_tool/cli.py` (error imports ~33-45, handler ~89)
- Test: `tests/test_retrieval_pipeline.py`

**Interfaces:**
- Consumes: `IncompatibleStorageLayoutError`,
  `SQLiteStore.require_current_storage_layout()` from Task 1.
- Produces: `cst query` / `trace` / `context` / `explore` against an old-layout
  index exit with the coded error `incompatible_storage_layout` instead of an
  `sqlite3.OperationalError`.

- [ ] **Step 1: Write the failing test**

In `tests/test_retrieval_pipeline.py` (reuse the `_create_layout_v1_index`
helper — move it to module scope in `tests/test_sqlite_store.py` and import it,
or duplicate the 30-line helper; duplication is acceptable here):

```python
def test_query_repository_rejects_layout_v1_index_with_coded_error(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".context-search").mkdir(parents=True)
    _create_layout_v1_index(repo / ".context-search" / "index.sqlite")

    with pytest.raises(
        sqlite_store.IncompatibleStorageLayoutError
    ) as excinfo:
        retrieval.query_repository(repo, "audit", ToolConfig())
    assert excinfo.value.code == "incompatible_storage_layout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_retrieval_pipeline.py -k layout_v1`
Expected: FAIL with `sqlite3.OperationalError` (no such column) or an
unstructured failure — not the coded error.

- [ ] **Step 3: Wire the guard**

In `retrieval.py`, immediately after each existing `db_path.exists()` preflight
(both sites), before any retrieval work:

```python
store = sqlite_store.SQLiteStore(db_path)
store.require_current_storage_layout()
```

(If the function already constructs the store later, hoist that construction —
do not open two stores.) Keep the missing-index branch first: a nonexistent
`index.sqlite` must still produce the existing missing-index error, and the
guard must not add any `Path.stat` calls before the existing preflight —
`tests/test_retrieval_trace_pipeline.py::test_trace_repository_reports_missing_index_without_changing_bundle`
asserts the preflight stat sequence exactly.

In `cli.py`, add `IncompatibleStorageLayoutError` to the existing import list
from `sqlite_store` (line ~33-45) and to the exception tuple the CLI already
maps to coded stderr output (line ~89).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.quality/p5-runtime/bin/python -m pytest -q tests/test_retrieval_pipeline.py tests/test_retrieval_trace_pipeline.py tests/test_cli_commands.py`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/retrieval.py src/context_search_tool/cli.py tests/test_retrieval_pipeline.py
git commit -m "feat: fail old storage layouts with a coded error"
```

---

### Task 5: End-to-end acceptance and docs

**Files:**
- Modify: `README.md` (troubleshooting section, after the embedding
  incompatibility entry)
- No production code.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Real-index migration check**

The repository's own `.context-search/index.sqlite` is a genuine layout-v1
index. Run:

```bash
.venv/bin/cst query . "NumpyVectorStore" 2>&1 | head -3   # expect coded error
.venv/bin/cst index .                                      # expect full rebuild
.venv/bin/cst query . "NumpyVectorStore" 2>&1 | head -3   # expect results
```

Record before/after `index.sqlite` sizes. Expected: ~87 MB → ~58 MB and the
query top-5 unchanged from the pre-migration ranking
(`index_health.py`, `indexer.py`, `vector_store.py` lead for this query).

- [ ] **Step 2: Characterization and quality gates**

```bash
.quality/p5-runtime/bin/python -m pytest -q -m "not slow" -p no:cacheprovider
.venv/bin/cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ci --output .quality/ci-layout-v2.json --markdown .quality/ci-layout-v2.md
```

Expected: only the 4 known worker failures; quality 8/8. The characterization
suite passing proves zero retrieval-output drift.

- [ ] **Step 3: README troubleshooting entry**

Add after the embedding-incompatibility troubleshooting block:

```markdown
### 查询时报 incompatible_storage_layout

索引存储布局已升级(lexical token 表改用整数引用)。运行:

​```bash
cst index /path/to/repo
​```

`index` 会自动执行一次完整重建;`clean` 不是必需的。
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe storage layout v2 migration"
```

---

## Deferred (measured, decided against for now)

- **FTS content dedup** (`chunks_fts_content` 15.4 MB): `contentless_delete=1`
  needs SQLite ≥ 3.43, but the CI matrix includes Python 3.11 on
  windows-latest with bundled SQLite 3.39.4. The external-content alternative
  requires storing the joined token text on `chunks` (+~5 MB) and the special
  FTS delete-command sync protocol, netting only ~10 MB for real complexity.
  Revisit when the CI floor moves to Python ≥ 3.12.
- **VACUUM/compaction path**: measured 2% reclaim; structural bloat, not
  fragmentation. Rejected.
- **`chunk_symbols` integer refs**: 187 rows, ~0 MB. Not worth the churn.

## Risks

- `_chunks_from_rows` ordering: v1 ordered by `chunk_tokens.rowid` globally;
  v2 must keep `ORDER BY chunk_tokens.rowid` so per-chunk token order (and
  therefore `followup_keywords`) is byte-identical. The Task 2 round-trip test
  pins this.
- Import cycle between `sqlite_store` and `graph_lifecycle` for
  `FULL_REINDEX_REQUIRED_KEY`: resolved by string literal if needed (Task 3).
- The real-index migration in Task 5 rebuilds this repo's own index; vectors
  regenerate from hash embeddings (offline, deterministic) — no data loss risk
  beyond a rebuild-time window.
