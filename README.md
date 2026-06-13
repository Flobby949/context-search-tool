# Context Search Tool

Local hybrid semantic retrieval for codebases.

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
