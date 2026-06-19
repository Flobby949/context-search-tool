# Generic Baseline Retrieval Quality Design

Date: 2026-06-19
Status: Draft for review
Repository: `/Users/flobby/Documents/context-seatch-tool`

## Summary

Improve CST's language-neutral baseline so it remains useful across Go, Rust, TypeScript, Java, and other common repositories without depending on a framework plugin for each ecosystem.

The next milestone should not add Go/Gin, Rust/Tauri, or another framework plugin. Plugins remain valuable for high-repeat, high-structure domains such as Java/Spring, but the main product line should be a stronger generic retrieval core: cleaner source ranking, less generated-file noise, and real-project quality evaluation before any language-specific semantics exist.

## Motivation

The generic language baseline now indexes common source suffixes. Real smoke checks showed the core problem has moved from "source files are skipped" to "the right source files are present but noisy files can still compete."

On `/Users/flobby/vibe_coding/imagebed`, CST now indexes Go files and can put these files at or near the top:

- `handler/upload.go` for upload handler queries.
- `middleware/auth.go` for auth middleware queries.
- `handler/delete.go` for delete queries.
- `main.go` for route queries.

The remaining issue is ranking cleanliness. For example, a storage query can include `main.go` and `storage/*.go`, but `templates/index.html` may rank too high because it contains related UI strings.

On `/Users/flobby/vibe_coding/env-change`, CST can find:

- `src-tauri/src/commands.rs` for Tauri command queries.
- `src-tauri/src/engine.rs` for `apply_dev`, `restore_clean`, session, and conflict logic.
- `src/main.ts` for frontend `invoke` queries.

The remaining issue is generic noise. `src-tauri/gen/schemas/*.json`, large schema files, lockfiles, templates, and unrelated config can enter top results. A targeted plugin would make this single project better, but that would not solve the general baseline problem.

Fast-context comparisons point in the same direction: the stronger pattern is not "write a plugin for every framework"; it is fast file/line evidence retrieval, broad but controlled exploration, and aggressive context-pollution management.

## Goals

- Build a reusable real-project retrieval quality suite for generic baseline work.
- Keep plugins as an enhancement layer, not the primary path for quality improvements.
- Reduce generated, dependency, lockfile, schema, and template noise in main code results.
- Preserve README and documentation as evidence anchors when useful, without letting them crowd out code.
- Define a deterministic two-pass retrieval strategy for a later phase, but keep the first implementation focused on evaluation and noise/rerank cleanup.
- Keep result scoring explainable through numeric `score_parts`.
- Improve quality on Go, Rust/Tauri, TypeScript, and existing Java smoke cases without adding new language plugins.
- Make future ranking changes measurable with file/line expectations, not only subjective result reading.

## Non-Goals

- No Go/Gin plugin in this milestone.
- No Rust/Tauri plugin in this milestone.
- No framework-specific route graph or command graph extraction.
- No LLM reranker.
- No remote model dependency.
- No embedding default change as part of this milestone.
- No schema-breaking change to `RetrievalResult`, MCP result payloads, or formatter contracts.
- No repository-specific alias map or hard-coded query shortcut.
- No attempt to match fast-context internals or claim fast-context parity.

## Design Principles

### Baseline First

The baseline should be good enough that a new repository is searchable before any plugin exists. A plugin should make a domain deeper, not rescue it from unusability.

### Evidence Before Tuning

Every ranking change should be checked against a small real-project query suite. The suite should record expected files, acceptable line ranges where practical, and known noise files.

### Demote Before Excluding

Some files are noisy for most queries but still useful for specific questions. The default behavior should prefer demotion for generated schemas, templates, lockfiles, and broad config files. Hard exclusion should be reserved for dependency directories, binary artifacts, and clearly generated vendor output.

### Main Results Are Code First

For code-like queries with function names, method names, endpoint strings, command names, or file path hints, source files should outrank docs, lockfiles, generated schemas, and broad templates unless those files contain uniquely strong direct evidence.

### Plugins Stay Optional

The Java/Spring plugin remains useful. Future plugins can add signals and relations, but generic scoring, file-role classification, and noise handling must work without them.

## Target User Experience

The user runs the same commands:

```text
cst index /path/to/repo
cst query /path/to/repo "UploadHandler MultiUpload multipart file storage Save"
cst query /path/to/repo "ProjectSwitcher apply_dev replace file_swap session.json"
```

The expected result shape improves:

- Main results prioritize implementation files.
- Generated schemas and lockfiles are absent from top results unless directly requested.
- README and docs appear as evidence anchors when they explain the feature.
- `score_parts` explain whether a result won because of direct text, path/name evidence, source role, or noise penalties.

## Architecture

The first-round retrieval flow remains deterministic and local.

```text
User Query
  -> Query Normalize
  -> Candidate Retrieval
       -> semantic candidates
       -> lexical candidates
       -> path/name candidates
       -> signal candidates when plugins provide signals
  -> Merge + Dedupe
  -> Generic Quality Rerank
       -> direct evidence
       -> file role
       -> noise demotion
       -> existing plugin signals and relations
  -> Evidence Anchor Split
  -> Context Expand
  -> Format Output
```

This milestone should implement the new quality behavior inside the existing retrieval pipeline instead of creating a separate agent. A later phase can add bounded readback and second-pass retrieval if the quality suite shows recall gaps after first-round noise cleanup.

## Components

### 1. Retrieval Quality Suite

Add a fixture-driven quality suite for real-project smoke checks. The fixture should be small, readable, and explicit.

Example shape:

```json
{
  "repo_key": "imagebed",
  "path_env": "CST_SMOKE_IMAGEBED_REPO",
  "repo_dir_name": "imagebed",
  "queries": [
    {
      "id": "go-upload-handler",
      "query": "UploadHandler MultiUpload multipart file storage Save",
      "expected_top_k": [
        {"path": "handler/upload.go", "top_k": 5}
      ],
      "absent_top_k": [
        {"path": "README.md", "top_k": 5}
      ]
    }
  ]
}
```

Repository paths should not be hard-coded into fixtures. Resolve each repo in this order:

1. Repo-specific environment variable such as `CST_SMOKE_IMAGEBED_REPO`.
2. `CST_SMOKE_REPOS_DIR / repo_dir_name`.
3. Skip the real-project smoke case if neither path exists.

The suite should support:

- `expected_top_k`: each listed file must appear within the specified top K.
- `expected_any_top_k`: at least one listed file must appear within top K.
- `absent_top_k`: listed files or glob patterns should not appear within top K.
- `outranks`: within a declared top-K window, a source path or glob must rank ahead of a noise path or glob if that noise item appears. If the noise item is absent from that top-K window, the assertion passes; source presence should be checked separately with `expected_top_k`.
- `anchor_expected`: listed docs should appear in `evidence_anchors`, not in primary `results`, when code results are available. First-round anchor assertions should target the already implemented anchor kinds: `README*.md`, `RISKS*.md`, and `pom.xml`.
- `known_gap`: documented misses that should not fail the suite yet.

Initial real-project cases:

- `imagebed`: upload, auth, storage, delete, route registration.
- `env-change`: Tauri commands, engine apply/restore, conflict checks, frontend invoke, settings persistence.
- Existing Java smoke cases that protect Spring path and Java plugin behavior from regression.

### 2. File Role And Noise Classification

Add a language-neutral file classifier. It should not parse framework semantics. It only labels broad retrieval roles.

Suggested roles:

- `source`: `.go`, `.rs`, `.java`, `.ts`, `.tsx`, `.py`, and similar source files.
- `template`: `.html`, `.vue`, `.svelte`, template-like files.
- `config`: `toml`, `yaml`, `json`, `properties`, and small config files.
- `doc`: markdown/rst docs. README/RISKS/pom anchoring is already implemented separately and should be regression-tested, not treated as a new feature.
- `lockfile`: indexed package manager lockfiles. Current scanner suffix support indexes JSON/YAML lockfiles such as `package-lock.json` and `pnpm-lock.yaml`, but does not index `.lock` files such as `Cargo.lock` or `yarn.lock`.
- `generated_schema`: large generated schema JSON and similar generated API metadata.
- `dependency`: files under dependency/vendor directories.
- `test`: test files.
- `unknown`: fallback.

Suggested noise levels:

- `none`: normal source.
- `low`: tests and narrow config files.
- `medium`: templates, broad docs, broad config.
- `high`: lockfiles, generated schemas, minified/generated files.
- `excluded`: dependency/vendor/build artifacts.

This milestone should add an independent generic file-role/noise classifier used during retrieval. It must not reuse or mutate the existing `_chunk_role` business/code-role classifier, and it must not require an index schema migration. The classifier can be derived from path, suffix, size, generated markers, and directory names using metadata already available on chunks.

The implementation must account for the existing `_generated_or_test_penalty(chunk)` path in `retrieval.py`. New noise penalties should extend or consolidate that existing penalty path rather than create a second unrelated generated/test penalty system. Existing `is_generated` and `is_test` metadata should continue to feed the unified noise penalty.

### 3. Generic Noise Policy

Default behavior should combine hard skips and rank demotion.

Hard skip candidates:

- Dependency directories such as `node_modules/`, `vendor/`, `.venv/`, build outputs, and target directories.
- Binary artifacts and oversized files.
- CST's own `.context-search/`.

Current scanner behavior relies on `.gitignore` and configured excludes for dependency/build directories; it does not have built-in `node_modules/`, `vendor/`, `.venv/`, `dist/`, or `target/` defaults. This milestone should add a small default skip list for dependency and build-output directories so baseline quality does not depend on each target repo's `.gitignore` hygiene.

Include patterns should not override default hard skips, `.gitignore`, configured exclude patterns, internal paths, binary detection, or oversized file skips. Changing include precedence is out of scope for this milestone.

Demotion candidates:

- Indexed lockfiles such as `pnpm-lock.yaml` and `package-lock.json`. `.lock` files such as `Cargo.lock` and `yarn.lock` are not indexed by the current suffix map, so first-round demotion cannot affect them unless a later scanner change adds `.lock` support.
- Generated schemas such as `src-tauri/gen/schemas/*.json`.
- Large JSON schema/config files.
- Templates when the query looks implementation-oriented.
- Docs when code files contain enough direct evidence.

Demotion should be explainable in `reasons` and numeric in `score_parts`, for example:

- `file_role_source_boost`
- `noise_penalty`
- `generated_schema_penalty`
- `lockfile_penalty`
- `template_penalty`
- `doc_anchor_split`

Initial penalty sizing should stay close to existing score magnitudes:

| Noise level | Initial penalty | Notes |
| --- | ---: | --- |
| `high` | `0.20` | Existing generated penalty scale; generated schemas, minified/generated files, indexed lockfiles. |
| `medium` | `0.08` | Templates, broad docs, broad config, large JSON/config. |
| `low` | `0.03` | Tests or narrow config when still potentially useful. Existing test penalty is `0.10`; implementation should either keep that as a specific test penalty or explicitly fold it into this ladder with regression coverage. |

These values are starting points, not magic constants. They should not overpower strong original direct evidence or the established Java route/service/executor path boosts. Java regression gates must run before accepting any penalty tuning.

### 4. Future Two-Pass Retrieval

The second pass should be bounded and deterministic.

This is not part of the first implementation plan. It remains in the design as the next capability to add after the quality suite and conservative noise/rerank cleanup show whether recall still needs a second retrieval pass.

First pass:

- Use existing semantic, lexical, path/name, signal, and relation stages.
- Keep enough candidates for readback, not only final top K.

Readback:

- Inspect top candidate paths, roles, snippets, and follow-up keywords.
- Extract only bounded terms, such as identifiers, path stems, endpoint-like strings, command names, and filename terms.
- Do not invent business aliases.
- Do not add framework-specific assumptions.

Second pass:

- Search for high-confidence readback terms through lexical/path lookup.
- Prefer terms that overlap the original query or appear in multiple first-pass candidates.
- Merge second-pass candidates with explicit diagnostic score parts.

The second pass should not become an uncontrolled crawler. Suggested limits:

- Max readback candidates: 12.
- Max derived terms: 24.
- Max second-pass candidates: 80.
- No recursive multi-turn loop in the future two-pass phase.

### 5. Generic Quality Rerank

Rerank should combine:

- Original query direct evidence.
- Existing semantic/lexical/path/signal score.
- File role and noise level.
- Existing Java/plugin relations when available.
- Evidence anchor separation for docs.

Broad rule:

```text
source implementation with direct evidence
  > narrow config or template with direct evidence
  > docs as anchors
  > generated schema / lockfile / broad config noise
```

This should remain soft enough that a query explicitly asking about an indexed config file, indexed lockfile, or generated schema can still find that file. Files not indexed by the scanner, such as `.lock` files in the current suffix map, remain out of scope for retrieval-time demotion.

### 6. Output And MCP Compatibility

No breaking output change is required.

Allowed additive diagnostics:

- New numeric `score_parts`.
- New human-readable reasons.
- Optional new fixture-only metrics output.

Avoid adding string labels into `score_parts`, because the existing contract expects numeric values. If a formatter or MCP payload needs role labels later, add a separate field deliberately and test compatibility.

## Initial Acceptance Targets

### `imagebed`

Repository: `/Users/flobby/vibe_coding/imagebed`

Expected:

- Upload query puts `handler/upload.go` in top 5.
- Auth query puts `middleware/auth.go` in top 5.
- Delete query puts `handler/delete.go` in top 5.
- Route query puts `main.go` in top 5.
- Storage query puts `main.go` and at least one `storage/*.go` file in top 8.
- For an implementation-oriented storage query, `main.go` and at least one `storage/*.go` path should outrank `templates/*.html` if template files appear at all.
- README-style docs appearing in `evidence_anchors`, not primary `results`, is existing behavior and should be kept as regression protection when code results are available.

### `env-change`

Repository: `/Users/flobby/vibe_coding/env-change`

Expected:

- Tauri command query puts `src-tauri/src/commands.rs` in top 3.
- Engine apply/restore query puts `src-tauri/src/engine.rs` in top 3.
- Conflict-check query puts `src-tauri/src/engine.rs` in top 3.
- Frontend invoke query puts `src/main.ts` in top 3.
- Settings query puts `src-tauri/src/settings.rs` in top 5.
- `src-tauri/gen/schemas/*.json` should not appear in top 8 for normal command, engine, frontend, or settings queries.
- Indexed lockfiles such as `pnpm-lock.yaml` should not appear in top 8 unless the query asks for dependencies or lockfiles. `.lock` files such as `Cargo.lock` are currently unindexed and should not be counted as a meaningful lockfile-demotion pass.

### Java Regression

Expected:

- Existing Java/Spring endpoint and relation smoke tests keep passing.
- Java plugin signals continue to improve Java ranking, but generic role/noise logic should not depend on Java-specific metadata.
- Gate at least:
  - `tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain`
  - `tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_es_audit_business_chain`
  - `tests/test_rerank_soft_sorting.py`
  - Existing Java path/context rerank tests in `tests/test_retrieval_pipeline.py` that assert executor/service/context boosts and test-file suppression.

## Testing Strategy

Unit tests:

- File role and noise classification for representative paths.
- Noise penalty scoring for indexed lockfiles, generated schemas, templates, docs, and normal source, while preserving the existing generated/test penalty path.
- Rerank ordering for source-vs-template and source-vs-generated cases.
- Numeric-only `score_parts` diagnostics.

Fixture tests:

- Synthetic Go/Rust/TypeScript fixtures for deterministic behavior.
- Existing Java fixtures for regression protection.

Real-project smoke:

- Run quality fixtures against temporary copies of `imagebed` and `env-change`, ignoring `.git` and `.context-search`, so indexing cannot mutate the user's working repositories or their `.gitignore` files.
- Record index stats, embedding provider, query, top results, and failures.
- Treat missing local repositories as skipped, not failed, in normal CI.

Comparison checks:

- Use fast-context periodically as a qualitative comparator for file sets, but do not make fast-context output a test oracle.

## Likely Files

- `src/context_search_tool/scanner.py`
- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/metrics.py`
- `src/context_search_tool/formatters.py`
- `src/context_search_tool/mcp_tools.py`
- `tests/test_tokenizer_scanner.py`
- `tests/test_retrieval_pipeline.py`
- `tests/test_rerank_soft_sorting.py`
- New quality fixture tests under `tests/`.
- New real-project query fixtures under `tests/fixtures/`.
- `README.md` for documenting baseline quality expectations after implementation.

## Risks

### Over-demotion

Generated, config, or template files are sometimes the right answer. Mitigation: use soft penalties, and reduce or remove penalties when the query directly names the file type, path, or config key.

### Hidden Framework Logic

Some frameworks encode behavior in config or generated files. Mitigation: this milestone improves generic defaults but does not hard-exclude all non-source files.

### Ranking Churn

Small scoring changes can move many results. Mitigation: add real-project fixtures first, then tune against explicit expected and noise cases.

### Plugin Regression

Generic role rules could accidentally overpower Java plugin signals. Mitigation: keep Java regression fixtures in the same verification set.

### Evaluation Overfitting

The fixture set may become too tailored to `imagebed` and `env-change`. Mitigation: write expectations around broad file-role behavior and add multiple language/project shapes over time.

## Confirmed Grill Decisions

- Classify file roles during retrieval first, using path, suffix, size, and metadata already available on chunks. Do not add an index schema migration for this milestone unless implementation proves the derived classifier is too expensive or inconsistent.
- First-round quality gates use `imagebed`, `env-change`, and existing Java regression coverage. Do not add a third non-Java project before the first implementation plan.
- Keep deterministic unit and synthetic fixture tests in normal pytest. Put external real-project smoke checks behind an explicit marker or helper command so missing local repositories skip cleanly; those real-project checks are still required before claiming a quality change is complete.
- Add a small scanner-level default skip list for dependency/build directories, binary artifacts, oversized files, and `.context-search/`; do not rely solely on each target repo's `.gitignore` for those paths.
- Use retrieval-time soft demotion for indexed lockfiles, generated schemas, templates, and broad config files. Do not add `.lock` scanner support in the first round; `.lock` files remain outside lockfile-demotion assertions unless a later scanner change indexes them.
- Extend or consolidate the existing `_generated_or_test_penalty` path for new noise penalties instead of introducing a competing penalty mechanism.
- Do not include two-pass retrieval in the first implementation plan. The first plan stops at the quality fixture runner, file role/noise classification, conservative rerank cleanup, and real-project smoke verification.
- Use top-K file hits and obvious-noise absence as hard acceptance criteria. Do not require exact top-1 ranking in the first round; top-1 remains an observation metric.
- Do not force embedding rebuilds during this milestone. Quality reports should record the active embedding provider/model for each target repo, and BGE-M3 can be used as an optional comparison run when available.

## Recommended First Implementation Slice

Start with evaluation and noise control. Do not implement two-pass retrieval in the first plan.

1. Add the generic retrieval quality fixture format and runner.
2. Add `imagebed` and `env-change` smoke fixtures with current known gaps.
3. Add file role/noise classification.
4. Apply conservative noise demotion in rerank.
5. Verify `imagebed`, `env-change`, and existing Java smoke cases.

This sequence keeps the milestone honest: measure first and reduce obvious pollution second. A later plan can add two-pass retrieval only if the evidence shows recall still misses expected implementation files after the first cleanup.
