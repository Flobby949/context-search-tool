from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from context_search_tool.chunker import chunk_text
from context_search_tool.config import ToolConfig, load_config
from context_search_tool.embeddings import provider_from_config
from context_search_tool.manifest import (
    Manifest,
    assert_manifest_compatible,
    embedding_config_hash,
    write_manifest,
)
from context_search_tool.models import DocumentChunk, SourceFile
from context_search_tool.paths import ensure_index_layout
from context_search_tool.plugins import LanguagePlugin, PluginExtraction, default_plugins
from context_search_tool.scanner import ScannedFile, scan_workspace
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.vector_store import NumpyVectorStore


class IncompatibleIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class IndexSummary:
    files_seen: int
    files_indexed: int
    files_skipped: int
    files_deleted: int
    chunks_indexed: int


def index_repository(repo: Path, config: ToolConfig) -> IndexSummary:
    repo = repo.resolve()
    index_dir = ensure_index_layout(repo)
    _ensure_config_file(repo, index_dir)
    try:
        assert_manifest_compatible(repo, config)
    except ValueError as exc:
        raise IncompatibleIndexError(str(exc)) from exc

    store = SQLiteStore(index_dir / "index.sqlite")
    store.initialize()

    scanned_files = scan_workspace(repo, config)
    scanned_paths = {scanned_file.path for scanned_file in scanned_files}
    indexed_paths = store.indexed_file_paths()
    deleted_paths = indexed_paths - scanned_paths
    for path in sorted(deleted_paths, key=lambda item: item.as_posix()):
        store.mark_file_deleted(path)

    plugins = default_plugins()
    changed_chunks: list[DocumentChunk] = []
    files_indexed = 0
    files_skipped = 0

    for scanned_file in scanned_files:
        existing = store.source_file_for_path(scanned_file.path)
        if (
            scanned_file.path in indexed_paths
            and existing is not None
            and existing.sha256 == scanned_file.sha256
        ):
            files_skipped += 1
            continue

        chunks = _index_file(store, scanned_file, plugins)
        changed_chunks.extend(chunks)
        files_indexed += 1

    if changed_chunks:
        provider = provider_from_config(config.embedding)
        vectors = provider.embed_texts(
            [_embedding_text_for_chunk(chunk) for chunk in changed_chunks]
        )
        vector_store = NumpyVectorStore(index_dir)
        vector_store.upsert_many(
            [
                (chunk.embedding_id or chunk.chunk_id, vector)
                for chunk, vector in zip(changed_chunks, vectors)
            ]
        )
        vector_store.persist()

    stats = store.stats()
    write_manifest(
        repo,
        Manifest(
            embedding_config_hash=embedding_config_hash(config.embedding),
            embedding_provider=config.embedding.provider,
            embedding_model=config.embedding.model,
            embedding_dimensions=config.embedding.dimensions,
            total_files=len(scanned_files),
            total_chunks=stats["active_chunks"],
        ),
    )

    return IndexSummary(
        files_seen=len(scanned_files),
        files_indexed=files_indexed,
        files_skipped=files_skipped,
        files_deleted=len(deleted_paths),
        chunks_indexed=len(changed_chunks),
    )


def _ensure_config_file(repo: Path, index_dir: Path) -> None:
    if not (index_dir / "config.toml").exists():
        load_config(repo)


def _index_file(
    store: SQLiteStore,
    scanned_file: ScannedFile,
    plugins: list[LanguagePlugin],
) -> list[DocumentChunk]:
    content = scanned_file.absolute_path.read_text(encoding="utf-8", errors="replace")
    extraction = _extract(scanned_file, content, plugins)
    metadata = dict(scanned_file.metadata)
    if extraction.metadata:
        metadata["plugin"] = extraction.metadata

    store.upsert_source_file(
        SourceFile(
            path=scanned_file.path,
            language=scanned_file.language,
            sha256=scanned_file.sha256,
            size=scanned_file.size,
            mtime_ns=scanned_file.mtime_ns,
            is_generated=scanned_file.is_generated,
            is_test=scanned_file.is_test,
            metadata=metadata,
        )
    )

    chunks = [
        replace(
            chunk,
            lexical_tokens=_dedupe_tokens(
                [*chunk.lexical_tokens, *extraction.lexical_tokens]
            ),
            embedding_id=chunk.chunk_id,
        )
        for chunk in chunk_text(
            scanned_file.path,
            content,
            scanned_file.language,
            extraction.symbols,
        )
    ]
    store.replace_chunks(scanned_file.path, chunks)
    return chunks


def _extract(
    scanned_file: ScannedFile,
    content: str,
    plugins: list[LanguagePlugin],
) -> PluginExtraction:
    for plugin in plugins:
        if plugin.supports(scanned_file.path, scanned_file.language):
            return plugin.extract(scanned_file.path, content)
    return PluginExtraction()


def _embedding_text_for_chunk(chunk: DocumentChunk) -> str:
    if not chunk.lexical_tokens:
        return chunk.content
    return f"{chunk.content}\n\n{' '.join(chunk.lexical_tokens)}"


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
