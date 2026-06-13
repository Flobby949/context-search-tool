# Context Search Tool

Local hybrid semantic retrieval for codebases.

## Capabilities

- Core multi-stage retrieval across lexical, signal, and relation inputs.
- Core signal and relation model for code context.
- Java as the first signal producer.
- Summary output groups for query results.
- Current limitations: no complete Java call graph and no real semantic embedding by default.

## Install For Development

```bash
python -m pip install -e ".[dev]"
```

## Basic Usage

```bash
cst index /path/to/repo
cst query /path/to/repo "/apply/audit/pageEs INVOLVED_BY_ME"
cd /path/to/repo
cst query "/apply/audit/pageEs INVOLVED_BY_ME" --context-lines 20
cst query /path/to/repo "canApply filter" --json
cst stats /path/to/repo
cst explain /path/to/repo src/main/java/App.java:42
```

Indexes are stored in the target repository under `.context-search/`.

## Embeddings

The default `hash` provider is deterministic and offline. It is useful for development, tests, and exact-token-heavy searches. Configure `openai-compatible` in `.context-search/config.toml` to use a real embedding service that exposes `/v1/embeddings`.
