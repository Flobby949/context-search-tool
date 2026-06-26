# Storage Role And Scanner Noise Followups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Q5 storage-role ranking gap and make scanner-driven lockfile/test metadata broad enough for existing generic noise demotion to apply across common ecosystems.

**Architecture:** Keep both changes as small generic baseline improvements. Storage role work extends the existing identifier-intent/path-role rerank path and real-project fixture gates; scanner work extends indexing metadata and lockfile language coverage so retrieval's existing aggregate `penalty` path can demote newly indexed noise without new ranking weights.

**Tech Stack:** Python 3.11+, pytest, existing scanner/indexer/retrieval pipeline, existing generic baseline real-project fixtures, SQLite-backed chunk metadata.

**Test Command Convention:** Use `conda run -n base python -m pytest ...` for all plan commands. This matches the interpreter used by the existing CST plans and avoids depending on the local `.venv`.

---

## 1. Problem Statement

After the explicit identifier and Top1 cohort work, the remaining known gaps are two different mechanisms:

- Q5 `imagebed` upload queries mention `storage`, but `storage/*.go` does not receive the role hint. `cmd/typora/main.go` can still enter Top5 through lexical overlap even though `handler/upload.go` is already Top1.
- Existing retrieval demotion already knows about lockfile and test noise, but scanner coverage is incomplete: names such as `Cargo.lock`, `yarn.lock`, and `go.sum` may not be indexed, and cross-language test metadata should be set during scanning rather than relying on retrieval path-string heuristics.
- `package-lock.json` and `pnpm-lock.yaml` are already indexed today through their `.json`/`.yaml` suffixes. This scanner slice intentionally reclassifies those names from `json`/`yaml` to `lockfile`, so chunking and metadata for those files may change.

These are not cohort-rerank changes. Do not tune Top1 cohort penalties, do not add repo-specific aliases, and do not add hard filters.

## 2. Scope

### In Scope

- Add `storage` as a generic identifier-intent role hint.
- Classify `storage/` and `storages/` paths as a generic `storage` path role.
- Treat `storage` as a high-confidence role for mismatch penalties when the query explicitly names storage and a competing file has no matching identifier evidence.
- Add synthetic ranking coverage proving `storage/local.go` receives `path_role_hint_boost` and an unrelated CLI entrypoint can receive `path_role_mismatch_penalty`.
- Add real-smoke fixture gates for the Q5 `imagebed` upload query:
  - keep `handler/upload.go` Top1;
  - require at least one `storage/*.go` result in Top5;
  - keep `cmd/typora/main.go` out of Top5.
- Index common suffix-less or special-name lockfiles that currently lack useful suffix coverage.
- Reclassify existing JSON/YAML lockfiles as `lockfile` so scanner, path-role, and retrieval lockfile handling use one name set.
- Mark common cross-language test files at scan time.
- Propagate scanner `is_test` into chunk metadata so retrieval's existing `_generic_noise_score_parts` can consume it.
- Extend retrieval's indexed-lockfile name list to the newly scanned and reclassified lockfiles.

### Out Of Scope

- No two-pass readback.
- No storage-specific repository aliasing.
- No hard filtering of `cmd/`, Java, or cross-project files.
- No changes to `_combined_score` for storage role work.
- No new scanner skip directories.
- No broad dependency or build-output skip changes.
- No SQLite schema migration.
- No generated-file detector in this slice; generated schema demotion remains covered by existing path heuristics such as `gen/` and `generated/`.

## 3. Files And Responsibilities

- Modify: `src/context_search_tool/identifier_intent.py`
  - Add `storage` role hint mapping.
- Modify: `src/context_search_tool/path_roles.py`
  - Classify storage directories before generic source fallback.
  - Keep lockfile path-role names synchronized with scanner and retrieval.
- Modify: `src/context_search_tool/retrieval.py`
  - Add `storage` to high-confidence role mismatch handling.
  - Add newly indexed and reclassified lockfile names to `_INDEXED_LOCKFILE_NAMES`.
- Modify: `src/context_search_tool/scanner.py`
  - Recognize special lockfile names independent of suffix.
  - Mark cross-language test files in `ScannedFile.is_test`.
- Modify: `src/context_search_tool/indexer.py`
  - Add scanner `is_test` values to chunk metadata.
- Modify: `tests/test_identifier_intent.py`
  - Unit coverage for storage role extraction.
- Modify: `tests/test_path_roles.py`
  - Unit coverage for storage path classification.
- Modify: `tests/test_retrieval_pipeline.py`
  - Synthetic storage rerank and generic lockfile-demotion coverage.
- Modify: `tests/test_tokenizer_scanner.py`
  - Scanner coverage for common lockfiles and cross-language test markers.
- Modify: `tests/test_indexer_manifest.py`
  - Indexer propagation coverage for scanner test metadata.
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
  - Add Q5 storage/coherence real-smoke gates.

## 4. Success Criteria

- Focused storage unit and synthetic retrieval tests pass.
- Focused scanner/indexer metadata tests pass.
- Existing generic noise tests still pass.
- `imagebed` Q5 keeps `handler/upload.go` at Top1 and puts at least one `storage/*.go` in Top5.
- `cmd/typora/main.go` is absent from Top5 for the Q5 upload query.
- All configured slow/integration generic baseline smoke repos still pass.
- Rank distribution remains `15/15` Top1 for existing `preferred_rank` targets.
- The existing `go-storage-implementations` query still passes after `storage` becomes a high-confidence role hint.

## 5. Implementation Tasks

### Task 1: Add Storage Role Intent And Q5 Gates

**Files:**
- Modify: `tests/test_identifier_intent.py`
- Modify: `tests/test_path_roles.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
- Modify: `src/context_search_tool/identifier_intent.py`
- Modify: `src/context_search_tool/path_roles.py`
- Modify: `src/context_search_tool/retrieval.py`

- [ ] **Step 1: Write failing identifier-intent storage test**

Append to `tests/test_identifier_intent.py`:

```python
def test_identifier_intent_extracts_storage_role() -> None:
    intent = infer_identifier_intent(
        "UploadHandler MultiUpload multipart file storage Save",
        ["upload", "handler", "multi", "upload", "multipart", "file", "storage", "save"],
    )

    assert intent.identifiers == ("MultiUpload", "UploadHandler")
    assert intent.role_hints == ("handler", "storage")
```

- [ ] **Step 2: Run the failing identifier-intent test**

Run:

```bash
conda run -n base python -m pytest tests/test_identifier_intent.py::test_identifier_intent_extracts_storage_role -q
```

Expected: FAIL because `storage` is not present in `intent.role_hints`.

- [ ] **Step 3: Add storage to role hints**

In `src/context_search_tool/identifier_intent.py`, add these entries to `_ROLE_HINTS` near the other infrastructure roles:

```python
    "storage": "storage",
    "storages": "storage",
```

- [ ] **Step 4: Verify identifier-intent storage test passes**

Run:

```bash
conda run -n base python -m pytest tests/test_identifier_intent.py::test_identifier_intent_extracts_storage_role -q
```

Expected: PASS.

- [ ] **Step 5: Write failing path-role storage test**

Append to `tests/test_path_roles.py`:

```python
def test_path_roles_classify_storage_files() -> None:
    assert classify_path_role(Path("storage/local.go")).name == "storage"
    assert classify_path_role(Path("storage/s3.go")).name == "storage"
    assert classify_path_role(Path("internal/storages/oss.go")).name == "storage"
```

- [ ] **Step 6: Run the failing path-role test**

Run:

```bash
conda run -n base python -m pytest tests/test_path_roles.py::test_path_roles_classify_storage_files -q
```

Expected: FAIL because storage paths currently fall through to `source`.

- [ ] **Step 7: Classify storage paths before generic source fallback**

In `src/context_search_tool/path_roles.py`, add this branch after middleware and before service/repository/source-adapter checks:

```python
    if any(part in {"storage", "storages"} for part in parts):
        return PathRole("storage", 30)
```

- [ ] **Step 8: Treat storage as a high-confidence role**

In `src/context_search_tool/retrieval.py`, add `"storage"` to the `high_confidence_roles` set in `_strong_role_mismatch`:

```python
        "storage",
```

No change is required in `_path_role_matches_intent`; the exact match path already handles `path_role.name == "storage"` with `role_hints=("storage",)`.

- [ ] **Step 9: Verify storage unit tests pass**

Run:

```bash
conda run -n base python -m pytest tests/test_identifier_intent.py::test_identifier_intent_extracts_storage_role tests/test_path_roles.py::test_path_roles_classify_storage_files -q
```

Expected: PASS.

- [ ] **Step 10: Write failing synthetic storage rerank test**

Append to `tests/test_retrieval_pipeline.py` near the existing identifier-intent tests:

```python
def test_identifier_intent_ranks_storage_source_above_unrelated_cli_entrypoint(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    storage = DocumentChunk(
        chunk_id="local-storage",
        file_path=Path("storage/local.go"),
        start_line=1,
        end_line=80,
        content="type LocalStorage struct{} func (s *LocalStorage) Save(file multipart.File) error { return nil }",
        chunk_type="symbol",
        lexical_tokens=["local", "storage", "save", "file", "multipart"],
        metadata={"language": "go"},
    )
    typora = DocumentChunk(
        chunk_id="typora-main",
        file_path=Path("cmd/typora/main.go"),
        start_line=1,
        end_line=80,
        content="func main() { uploadFromTypora(); saveFile(); }",
        chunk_type="symbol",
        lexical_tokens=["typora", "upload", "save", "file", "main"],
        metadata={"language": "go"},
    )
    for chunk in (storage, typora):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "local-storage": RetrievalCandidate(
                chunk_id="local-storage",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.42, "path_symbol": 2.0, "direct_text": 0.8},
            ),
            "typora-main": RetrievalCandidate(
                chunk_id="typora-main",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.50, "path_symbol": 2.0, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("UploadHandler MultiUpload multipart file storage Save"),
        "UploadHandler MultiUpload multipart file storage Save",
    )

    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].chunk.chunk_id == "local-storage"
    assert score_parts_by_chunk["local-storage"]["path_role_hint_boost"] == pytest.approx(0.14)
    assert score_parts_by_chunk["typora-main"]["path_role_mismatch_penalty"] == pytest.approx(-0.08)
```

- [ ] **Step 11: Run the failing synthetic storage rerank test**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_identifier_intent_ranks_storage_source_above_unrelated_cli_entrypoint -q
```

Expected before implementation is complete: FAIL because `storage/local.go` does not receive the storage role hint and the unrelated CLI entrypoint is not penalized for storage mismatch.

- [ ] **Step 12: Verify synthetic storage rerank test passes**

After Steps 3, 7, and 8, rerun:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_identifier_intent_ranks_storage_source_above_unrelated_cli_entrypoint -q
```

Expected: PASS.

- [ ] **Step 13: Verify Q5 real-repo paths before fixture edit**

Run this check with `CST_SMOKE_IMAGEBED_REPO` or `CST_SMOKE_REPOS_DIR` configured:

```bash
IMAGEBED_REPO="${CST_SMOKE_IMAGEBED_REPO:-${CST_SMOKE_REPOS_DIR:+$CST_SMOKE_REPOS_DIR/imagebed}}"
test -n "$IMAGEBED_REPO"
test -f "$IMAGEBED_REPO/handler/upload.go"
ls "$IMAGEBED_REPO"/storage/*.go
test -f "$IMAGEBED_REPO/cmd/typora/main.go"
```

Expected: all commands exit 0. If the repo path is not configured, stop and record that Q5 real-smoke validation cannot be claimed locally. Do not add or weaken fixture gates without checking the actual repo shape.

- [ ] **Step 14: Add Q5 real-smoke fixture gates**

In `tests/fixtures/generic_baseline_quality/queries.json`, update the `imagebed` query with `"id": "go-upload-handler"` so it keeps the existing Top1 target and adds these gates:

```json
        "expected_top_k": [
          {"path": "handler/upload.go", "top_k": 5},
          {"glob": "storage/*.go", "top_k": 5}
        ],
        "preferred_rank": [
          {"path": "handler/upload.go", "top_k": 5, "max_rank": 1}
        ],
        "absent_top_k": [
          {"glob": "templates/*", "top_k": 5},
          {"path": "cmd/typora/main.go", "top_k": 5}
        ]
```

- [ ] **Step 15: Run focused storage verification**

Run:

```bash
conda run -n base python -m pytest tests/test_identifier_intent.py tests/test_path_roles.py tests/test_retrieval_pipeline.py::test_identifier_intent_ranks_storage_source_above_unrelated_cli_entrypoint -q
```

Expected: PASS.

- [ ] **Step 16: Run real-smoke verification for Q5 and storage spillover**

Run with the imagebed repo configured:

```bash
conda run -n base python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected: PASS for `imagebed`, including both `go-upload-handler` and the existing `go-storage-implementations` query. If local smoke repos are not configured, pytest skips those cases. Do not weaken the fixture gates to satisfy an unconfigured environment.

If this fails only because `storage/*.go` is present in the candidate/result evidence but lands at rank 6-8, stop and record the observed top paths before changing the fixture to `{"glob": "storage/*.go", "top_k": 8}`. If `storage/*.go` is absent from the candidate pool, treat that as a recall problem and do not solve it by increasing role weights.

- [ ] **Step 17: Commit storage role slice**

Run:

```bash
git add src/context_search_tool/identifier_intent.py src/context_search_tool/path_roles.py src/context_search_tool/retrieval.py tests/test_identifier_intent.py tests/test_path_roles.py tests/test_retrieval_pipeline.py tests/fixtures/generic_baseline_quality/queries.json
git commit -m "feat: add storage role rerank coverage"
```

### Task 2: Add Scanner Lockfile And Cross-Language Test Metadata

**Files:**
- Modify: `tests/test_tokenizer_scanner.py`
- Modify: `tests/test_path_roles.py`
- Modify: `tests/test_indexer_manifest.py`
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `src/context_search_tool/scanner.py`
- Modify: `src/context_search_tool/path_roles.py`
- Modify: `src/context_search_tool/indexer.py`
- Modify: `src/context_search_tool/retrieval.py`

- [ ] **Step 1: Write failing scanner lockfile coverage**

Append to `tests/test_tokenizer_scanner.py`:

```python
def test_scanner_indexes_common_lockfiles_for_noise_demotion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "Cargo.lock": "[[package]]\nname = \"demo\"\n",
        "yarn.lock": "left-pad@^1.0.0:\n  version \"1.0.0\"\n",
        "go.sum": "example.com/lib v1.0.0 h1:abc\n",
        "package-lock.json": "{\"packages\": {}}\n",
        "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
        "pnpm-lock.yml": "lockfileVersion: '9.0'\n",
    }
    for relative_path, content in files.items():
        (repo / relative_path).write_text(content, encoding="utf-8")

    scanned = scan_workspace(repo, DEFAULT_CONFIG)

    paths = {item.path.as_posix() for item in scanned}
    assert paths == set(files)
    assert {item.language for item in scanned} == {"lockfile"}
```

- [ ] **Step 2: Run the failing scanner lockfile test**

Run:

```bash
conda run -n base python -m pytest tests/test_tokenizer_scanner.py::test_scanner_indexes_common_lockfiles_for_noise_demotion -q
```

Expected: FAIL because suffix-less/special-name lockfiles are not all included as `lockfile`; `package-lock.json` and `pnpm-lock.yaml` may already be indexed but are still classified as `json`/`yaml`.

- [ ] **Step 3: Write failing path-role lockfile coverage**

Append to `tests/test_path_roles.py`:

```python
def test_path_roles_classify_all_indexed_lockfiles() -> None:
    for relative_path in (
        "Cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    ):
        assert classify_path_role(Path(relative_path)).name == "lockfile"
```

- [ ] **Step 4: Run the failing path-role lockfile test**

Run:

```bash
conda run -n base python -m pytest tests/test_path_roles.py::test_path_roles_classify_all_indexed_lockfiles -q
```

Expected: FAIL because `pnpm-lock.yml` is not currently classified as a lockfile.

- [ ] **Step 5: Write failing scanner cross-language test metadata coverage**

Append to `tests/test_tokenizer_scanner.py`:

```python
def test_scanner_marks_cross_language_test_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "service/upload_test.go": "package service\nfunc TestUpload() {}\n",
        "src/components/upload.test.ts": "test('upload', () => {})\n",
        "src/components/upload.spec.tsx": "test('upload', () => {})\n",
        "tests/integration/upload.rs": "#[test]\nfn upload() {}\n",
        "src/main/java/com/example/UploadTest.java": "class UploadTest {}\n",
        "src/main/java/com/example/UploadService.java": "class UploadService {}\n",
    }
    for relative_path, content in files.items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    scanned = scan_workspace(repo, DEFAULT_CONFIG)
    by_path = {item.path.as_posix(): item for item in scanned}

    assert by_path["service/upload_test.go"].is_test
    assert by_path["src/components/upload.test.ts"].is_test
    assert by_path["src/components/upload.spec.tsx"].is_test
    assert by_path["tests/integration/upload.rs"].is_test
    assert by_path["src/main/java/com/example/UploadTest.java"].is_test
    assert not by_path["src/main/java/com/example/UploadService.java"].is_test
```

- [ ] **Step 6: Run the failing scanner test metadata test**

Run:

```bash
conda run -n base python -m pytest tests/test_tokenizer_scanner.py::test_scanner_marks_cross_language_test_files -q
```

Expected: FAIL because `ScannedFile.is_test` is not set from path patterns.

- [ ] **Step 7: Implement scanner and path-role lockfile language plus test-path detection**

In `src/context_search_tool/scanner.py`, add these helpers near `_LANGUAGES_BY_SUFFIX`:

```python
_LOCKFILE_NAMES = {
    "cargo.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "yarn.lock",
}
```

In `src/context_search_tool/path_roles.py`, keep the lockfile path-role set synchronized with the same six names:

```python
    if name in {
        "cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    }:
        return PathRole("lockfile", 90)
```

Replace `_language_for_path` with:

```python
def _language_for_path(path: Path) -> str:
    if path.name.lower() in _LOCKFILE_NAMES:
        return "lockfile"
    return _LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), "")
```

Add this helper near `_language_for_path`:

```python
def _is_test_path(relative_path: Path) -> bool:
    normalized = relative_path.as_posix().lower()
    parts = tuple(part.lower() for part in relative_path.parts)
    name = relative_path.name.lower()
    return (
        "test" in parts
        or "tests" in parts
        or "/src/test/" in normalized
        or name.endswith(
            (
                "_test.go",
                "_test.rs",
                "_spec.rs",
                ".test.ts",
                ".spec.ts",
                ".test.tsx",
                ".spec.tsx",
                ".test.js",
                ".spec.js",
                ".test.jsx",
                ".spec.jsx",
                "test.java",
            )
        )
    )
```

In `_scan_file`, compute the relative path once and set `is_test`:

```python
    relative_path = path.relative_to(repo)
    return ScannedFile(
        path=relative_path,
        absolute_path=path,
        language=language,
        sha256=hashlib.sha256(content).hexdigest(),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        is_test=_is_test_path(relative_path),
    )
```

This introduces `relative_path` as a local variable before the `ScannedFile(...)` constructor and uses it for both `path=` and `is_test=`.

- [ ] **Step 8: Verify scanner and path-role tests pass**

Run:

```bash
conda run -n base python -m pytest tests/test_tokenizer_scanner.py::test_scanner_indexes_common_lockfiles_for_noise_demotion tests/test_tokenizer_scanner.py::test_scanner_marks_cross_language_test_files tests/test_path_roles.py::test_path_roles_classify_all_indexed_lockfiles -q
```

Expected: PASS.

- [ ] **Step 9: Write failing indexer chunk-metadata propagation test**

Append to `tests/test_indexer_manifest.py`:

```python
def test_index_repository_propagates_scanner_test_metadata_to_chunks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "service" / "upload_test.go"
    source.parent.mkdir(parents=True)
    source.write_text(
        "package service\nfunc TestUpload() {}\n",
        encoding="utf-8",
    )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    chunk = store.chunk_for_line(Path("service/upload_test.go"), 2)
    assert chunk.metadata["language"] == "go"
    assert chunk.metadata["is_test"]
```

- [ ] **Step 10: Run the failing indexer metadata test**

Run:

```bash
conda run -n base python -m pytest tests/test_indexer_manifest.py::test_index_repository_propagates_scanner_test_metadata_to_chunks -q
```

Expected: FAIL because chunk metadata does not yet include scanner `is_test`.

- [ ] **Step 11: Propagate scanner test flag into chunk metadata**

In `src/context_search_tool/indexer.py`, update `_prepare_file` so chunk metadata includes the scanner test flag:

```python
    scanner_fields = {
        "is_test": scanned_file.is_test,
    }
```

Then change the `replace(... metadata=...)` call inside the `chunks = [...]` list to:

```python
            metadata={**chunk.metadata, **scanner_fields, **project_fields},
```

Keep the existing `SourceFile(is_generated=..., is_test=...)` fields unchanged.

- [ ] **Step 12: Verify indexer metadata test passes**

Run:

```bash
conda run -n base python -m pytest tests/test_indexer_manifest.py::test_index_repository_propagates_scanner_test_metadata_to_chunks -q
```

Expected: PASS.

- [ ] **Step 13: Write failing retrieval coverage for newly indexed and reclassified lockfile names**

Append to the generic-noise section of `tests/test_retrieval_pipeline.py`:

```python
@pytest.mark.parametrize(
    "lockfile_path",
    [
        "Cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    ],
)
def test_generic_noise_indexed_common_lockfiles_demote_below_source(
    tmp_path: Path,
    lockfile_path: str,
) -> None:
    lockfile = _generic_noise_chunk(
        "lockfile",
        lockfile_path,
        "storage save upload lock dependency",
        ["storage", "save", "upload", "lock"],
    )
    source = _generic_noise_chunk(
        "source",
        "storage/local.go",
        "type LocalStorage struct{} func (s *LocalStorage) Save() {}",
        ["storage", "local", "save", "upload"],
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [lockfile, source],
        {
            "lockfile": {"lexical": 0.8, "direct_text": 0.7},
            "source": {"lexical": 0.8, "direct_text": 0.7},
        },
        ["storage", "save", "upload"],
        "storage save upload implementation",
    )

    by_id = {item.chunk.chunk_id: item for item in ranked}
    assert ranked[0].chunk.chunk_id == "source"
    assert by_id["lockfile"].score_parts["lockfile_penalty"] < 0
    assert by_id["lockfile"].score_parts["penalty"] == pytest.approx(-0.20)
```

- [ ] **Step 14: Run the failing retrieval lockfile coverage**

Run:

```bash
conda run -n base python -m pytest tests/test_retrieval_pipeline.py::test_generic_noise_indexed_common_lockfiles_demote_below_source -q
```

Expected: FAIL for lockfile names not present in retrieval's `_INDEXED_LOCKFILE_NAMES`.

- [ ] **Step 15: Extend retrieval indexed-lockfile names**

In `src/context_search_tool/retrieval.py`, replace `_INDEXED_LOCKFILE_NAMES` with:

```python
_INDEXED_LOCKFILE_NAMES = {
    "cargo.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "yarn.lock",
}
```

- [ ] **Step 16: Verify scanner/indexer/retrieval noise tests pass**

Run:

```bash
conda run -n base python -m pytest tests/test_tokenizer_scanner.py::test_scanner_indexes_common_lockfiles_for_noise_demotion tests/test_tokenizer_scanner.py::test_scanner_marks_cross_language_test_files tests/test_path_roles.py::test_path_roles_classify_all_indexed_lockfiles tests/test_indexer_manifest.py::test_index_repository_propagates_scanner_test_metadata_to_chunks tests/test_retrieval_pipeline.py::test_generic_noise_indexed_common_lockfiles_demote_below_source -q
```

Expected: PASS.

- [ ] **Step 17: Run broader focused baseline tests**

Run:

```bash
conda run -n base python -m pytest tests/test_tokenizer_scanner.py tests/test_path_roles.py tests/test_indexer_manifest.py tests/test_retrieval_pipeline.py -q
```

Expected: PASS or existing unrelated skips only.

- [ ] **Step 18: Run real-smoke verification**

Run:

```bash
conda run -n base python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected: PASS when smoke repos are configured; skipped cases are acceptable only when the corresponding repo path environment variables are absent.

- [ ] **Step 19: Commit scanner noise slice**

Run:

```bash
git add src/context_search_tool/scanner.py src/context_search_tool/path_roles.py src/context_search_tool/indexer.py src/context_search_tool/retrieval.py tests/test_tokenizer_scanner.py tests/test_path_roles.py tests/test_indexer_manifest.py tests/test_retrieval_pipeline.py
git commit -m "feat: index lockfile and test noise metadata"
```

## 6. Final Verification

After both tasks are complete, run:

```bash
conda run -n base python -m pytest tests/test_identifier_intent.py tests/test_path_roles.py tests/test_tokenizer_scanner.py tests/test_indexer_manifest.py tests/test_retrieval_pipeline.py -q
conda run -n base python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected:

- Focused unit and retrieval suites pass.
- Real-smoke suites pass when configured.
- Existing `preferred_rank` Top1 targets remain unchanged.
- The existing `go-storage-implementations` query still passes after `storage` becomes high-confidence.
- Q5 `go-upload-handler` includes `handler/upload.go` Top1 and a `storage/*.go` file in Top5, unless Step 16 records real evidence for revising the storage gate to Top8.
- `cmd/typora/main.go` is absent from Q5 Top5.

## 7. Risks And Guardrails

- If adding `storage` causes unrelated storage-client files to overtake exact handler/file-name matches, do not increase storage boost. Keep handler/file-name evidence stronger and use fixture gates to detect the regression.
- If scanner lockfile indexing or reclassification causes lockfiles to appear in ordinary results, do not add a hard filter. Confirm `_INDEXED_LOCKFILE_NAMES` and `lockfile_penalty` are applied through the aggregate `penalty` path.
- If chunk metadata still lacks `is_test` after Task 2 Step 11, inspect `indexer._prepare_file` and `SQLiteStore._insert_chunk`; do not duplicate test-path logic in retrieval as the primary fix.
- If slow/integration tests skip locally, record the skip reason and run focused synthetic tests. Do not claim real-smoke validation without configured repos.

## 8. Self-Review

- Spec coverage: Task 1 covers Q5 storage role recognition and real-smoke gates; Task 2 covers scanner lockfile and cross-language test metadata.
- Placeholder scan: Every implementation step names exact files, code snippets, commands, and expected outcomes.
- Type consistency: Scanner metadata uses existing `ScannedFile.is_test` and `DocumentChunk.metadata` dictionaries; retrieval continues to consume numeric `score_parts` only.
