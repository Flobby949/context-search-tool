# Semantic Retrieval Tool Design

Date: 2026-06-13
Status: Approved for planning
Repository: `/Users/flobby/Documents/context-seatch-tool`

## Summary

Build a local semantic retrieval tool for codebases. The first version is a CLI-first hybrid search engine that indexes a target repository into a `.context-search/` directory inside that target repository, then answers natural-language queries with ranked code context bundles.

The design favors a strong core framework over a broad first release. The core must be language-neutral and useful on any codebase. Java support starts as a plugin that improves chunking, metadata, query expansion, and ranking for Spring-style backend projects without hard-coding Java assumptions into the core.

## Goals

- Provide a usable CLI for indexing and querying local repositories.
- Store each repository's index under that repository's root in `.context-search/`.
- Combine semantic, lexical, path, and symbol retrieval.
- Return file paths, line ranges, snippets, match reasons, score details, and follow-up search terms.
- Keep retrieval logic in reusable core modules so MCP can wrap the same engine later.
- Make language-specific behavior pluggable, starting with a lightweight Java plugin.
- Support incremental indexing by hashing files and skipping unchanged content.

## Non-Goals For Version 1

- No background file watcher.
- No MCP server.
- No remote service or multi-user deployment.
- No complete Java call graph.
- No deep MyBatis/XML mapper analysis.
- No commit history indexing.
- No LLM reranker.
- No large monorepo optimization target.
- No claim of ACE/Fast Context parity in the first version.

## User Experience

The initial CLI should expose four commands:

```text
cst index <repo>
cst query <repo> "<question>"
cst status <repo>
cst clean <repo>
```

`cst index` creates or updates `<repo>/.context-search/`.

`cst query` returns a Markdown context bundle by default and supports JSON output for automation:

```text
cst query <repo> "<question>" --json
```

The output should be useful to both humans and coding agents. Each result should include:

- File path.
- Start and end line.
- Code snippet.
- Overall score.
- Score parts.
- Human-readable match reasons.
- Follow-up keywords for additional grep/search.

## Index Location

The default index location is inside the target repository:

```text
<target-repo>/
  .context-search/
    manifest.json
    index.sqlite
    embeddings.npy
    config.toml
```

This keeps index state tied to the repository being searched, not to the retrieval tool source tree. A future `--index-dir` override can be added, but the first version should keep the default simple.

## Architecture

The system is organized as reusable core stages plus optional language plugins.

```text
CLI
  -> Core API
      -> Workspace Scanner
      -> Chunker / Extractor
      -> Embedding Provider
      -> Lexical Index
      -> Vector Store
      -> Retrieval Pipeline
      -> Reranker
      -> Formatter
      -> Language Plugins
```

The CLI should not contain retrieval logic. It should parse arguments, call the core API, and format errors.

## Core Components

### Workspace Scanner

Responsibilities:

- Discover indexable files.
- Respect `.gitignore`.
- Respect `.context-search/config.toml`.
- Exclude generated, vendor, dependency, binary, and oversized files where possible.
- Compute file hash, size, mtime, and language guess.
- Determine which files are new, changed, deleted, or unchanged.

The scanner does not understand code semantics. It emits file records for later stages.

### Chunker / Extractor

Responsibilities:

- Split files into retrievable `DocumentChunk` objects.
- Preserve stable line ranges.
- Keep chunks small enough for retrieval but large enough to be useful.
- Attach generic metadata, lexical tokens, and language plugin metadata.

The default chunker should work for any text file using line windows and lightweight structure hints. It should avoid splitting inside obvious contiguous blocks when practical, but correctness is more important than perfect AST boundaries in version 1.

### Embedding Provider

Responsibilities:

- Convert chunk content and queries into vectors.
- Hide provider-specific SDKs behind one interface.
- Support batching.
- Persist enough provider/model metadata to detect incompatible existing indexes.

The first implementation can choose one default provider, but the interface must allow OpenAI, local embedding models, Voyage, Jina, Qwen, BGE, or other providers later.

### Lexical Index

Responsibilities:

- Support exact and fuzzy-ish keyword lookup through SQLite FTS.
- Index identifiers, path tokens, filename tokens, and chunk text.
- Split camelCase, PascalCase, snake_case, kebab-case, and path fragments.

This gives the tool a reliable floor when semantic search misses exact code tokens.

### Vector Store

Responsibilities:

- Store chunk vectors.
- Search query vectors for top-k similar chunks.
- Delete vectors for removed chunks.
- Persist and reload local vectors.

Version 1 should define a `VectorStore` interface and use a simple local implementation, such as a NumPy matrix persisted to `embeddings.npy`. The interface should allow FAISS, LanceDB, Qdrant, or pgvector later.

### Retrieval Pipeline

Query flow:

```text
User Query
  -> Query Normalize
  -> Query Expansion
  -> Candidate Retrieval
       -> semantic topK
       -> lexical topK
       -> path/name/symbol topK
  -> Merge + Dedupe
  -> Rerank
  -> Context Expand
  -> Format Output
```

The pipeline should be explicit stages, not one large function. Each stage should receive and return typed data so future stages can be inserted without rewriting the flow.

### Reranker

Version 1 uses deterministic, explainable ranking rules:

- Semantic similarity.
- Lexical coverage.
- Exact token matches.
- Path and filename matches.
- Symbol matches.
- Chunk density.
- Query token position.
- Test file boost or penalty depending on query.
- Generated/vendor/dependency penalty.
- Language plugin boosts.

LLM reranking is reserved for later.

### Formatter

Responsibilities:

- Produce Markdown output for humans.
- Produce JSON output for MCP and automation.
- Keep all paths, line ranges, reasons, and score parts visible.

## Data Model

Core data structures should remain language-neutral.

```text
Workspace
- root_path
- index_id
- ignore_rules
- created_at
- updated_at

SourceFile
- path
- language
- hash
- size
- mtime
- is_generated
- is_test
- metadata

DocumentChunk
- chunk_id
- file_path
- start_line
- end_line
- content
- chunk_type
- symbols
- lexical_tokens
- embedding_id
- metadata

SymbolRef
- name
- kind
- start_line
- end_line
- language
- metadata

RetrievalResult
- file_path
- start_line
- end_line
- content
- score
- score_parts
- reasons
- followup_keywords
```

Language plugins can add metadata, but consumers should not need Java-specific fields to use the core retrieval API.

## Java Plugin V0

The first Java plugin is lightweight. It improves retrieval quality without implementing a full parser or call graph.

Capabilities:

- Detect `.java` files.
- Extract package declarations.
- Extract imports.
- Extract class/interface/enum names.
- Extract method-like declarations with approximate line ranges.
- Extract annotations.
- Detect common Spring route annotations:
  - `@RequestMapping`
  - `@GetMapping`
  - `@PostMapping`
  - `@PutMapping`
  - `@DeleteMapping`
  - `@PatchMapping`
- Add naming signals for common backend roles:
  - Controller
  - Service
  - Mapper
  - Repository
  - DTO
  - Query
  - Command
  - Executor/Exe

Expected improvements:

- More complete method/class chunks.
- Better endpoint queries.
- Better ranking for controller, DTO, service, mapper, and query classes.
- Better query expansion from route paths and Java identifiers.
- More useful context bundles for Spring backend investigations.

The plugin must not make the core Java-only.

## Configuration

Each target repository may contain `.context-search/config.toml`.

Initial settings:

```toml
[index]
include = []
exclude = []
max_file_bytes = 500000

[retrieval]
semantic_top_k = 80
lexical_top_k = 80
final_top_k = 12
context_before_lines = 8
context_after_lines = 12

[embedding]
provider = "default"
model = "default"
```

The tool should create a reasonable default config when indexing for the first time.

## Error Handling

Version 1 should handle common local failures clearly:

- Target repository does not exist.
- Target path is not a directory.
- Index does not exist for query/status.
- Embedding provider is unavailable or misconfigured.
- Existing index was built with an incompatible schema or embedding model.
- File cannot be decoded as text.
- Repository has no indexable files.

Errors should be concise and actionable.

## Testing Strategy

Tests should focus on behavior and boundaries:

- Scanner respects ignore rules and detects changed/deleted files.
- Chunker preserves correct line ranges.
- Tokenizer splits camelCase, snake_case, path fragments, and code identifiers.
- SQLite FTS returns exact-token matches.
- Vector store can persist, reload, search, and delete vectors.
- Retrieval pipeline merges, dedupes, reranks, and expands context.
- Formatter emits stable Markdown and JSON.
- Java plugin extracts route, class, method, package, import, and annotation signals from representative snippets.

Use small fixture repositories instead of mocking the entire pipeline.

## Acceptance Criteria

Using a real Java repository, this flow should work:

```text
cst index /path/to/java-repo
cst query /path/to/java-repo "/apply/audit/pageEs INVOLVED_BY_ME why does it leak across regions"
```

Expected behavior:

- The index is created in `/path/to/java-repo/.context-search/`.
- Re-running index skips unchanged files.
- Query returns 5 to 15 ranked results by default.
- Results include file paths, line ranges, snippets, reasons, and score parts.
- At least some controller/query/service/mapper candidates are surfaced when they exist and are textually or semantically connected to the query.
- JSON output contains the same structured data needed by a future MCP server.

## Future Extensions

Planned extension points:

- MCP server wrapping the core query API.
- Tree-sitter chunkers for multiple languages.
- Deeper Java parsing through tree-sitter or JDT.
- MyBatis/XML mapper relationship extraction.
- Call graph and reference graph reranking.
- Commit history indexing.
- LLM or cross-encoder reranker.
- Agentic Fast Context-style retrieval stage.
- Alternative vector stores.
- Multi-repository workspace support.
- Background watcher.

## Design Principles

- Core first: language-neutral retrieval must be useful without Java plugins.
- Plugins enhance signals, not control the pipeline.
- Store indexes in the target repository by default.
- Keep retrieval explainable in version 1.
- Prefer incremental, testable stages over a large opaque search function.
- Avoid building distributed-scale infrastructure before local quality is proven.
