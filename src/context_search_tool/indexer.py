from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from context_search_tool.chunker import chunk_text
from context_search_tool.config import ToolConfig, render_config
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


@dataclass(frozen=True)
class _PreparedFile:
    source_file: SourceFile
    chunks: list[DocumentChunk]


def index_repository(repo: Path, config: ToolConfig) -> IndexSummary:
    repo = repo.resolve()
    index_dir = ensure_index_layout(repo)
    try:
        assert_manifest_compatible(repo, config)
    except ValueError as exc:
        raise IncompatibleIndexError(str(exc)) from exc

    store = SQLiteStore(index_dir / "index.sqlite")
    store.initialize()

    scanned_files = scan_workspace(repo, config)
    scanned_paths = {scanned_file.path for scanned_file in scanned_files}
    indexed_paths = store.source_file_paths()
    deleted_paths = indexed_paths - scanned_paths

    plugins = default_plugins()
    prepared_files: list[_PreparedFile] = []
    changed_chunks: list[DocumentChunk] = []
    files_skipped = 0

    for scanned_file in scanned_files:
        existing = store.source_file_for_path(scanned_file.path)
        if existing is not None and existing.sha256 == scanned_file.sha256:
            files_skipped += 1
            continue

        prepared_file = _prepare_file(scanned_file, plugins)
        prepared_files.append(prepared_file)
        changed_chunks.extend(prepared_file.chunks)

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

    for path in sorted(deleted_paths, key=lambda item: item.as_posix()):
        store.mark_file_deleted(path)

    for prepared_file in prepared_files:
        store.upsert_source_file(prepared_file.source_file)
        store.replace_chunks(prepared_file.source_file.path, prepared_file.chunks)

    _ensure_config_file(index_dir, config)

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
        files_indexed=len(prepared_files),
        files_skipped=files_skipped,
        files_deleted=len(deleted_paths),
        chunks_indexed=len(changed_chunks),
    )


def _ensure_config_file(index_dir: Path, config: ToolConfig) -> None:
    if not (index_dir / "config.toml").exists():
        (index_dir / "config.toml").write_text(
            render_config(config),
            encoding="utf-8",
        )


def _prepare_file(
    scanned_file: ScannedFile,
    plugins: list[LanguagePlugin],
) -> _PreparedFile:
    content = scanned_file.absolute_path.read_text(encoding="utf-8", errors="replace")
    extraction = _extract(scanned_file, content, plugins)
    metadata = dict(scanned_file.metadata)
    if extraction.metadata:
        metadata["plugin"] = extraction.metadata

    source_file = SourceFile(
        path=scanned_file.path,
        language=scanned_file.language,
        sha256=scanned_file.sha256,
        size=scanned_file.size,
        mtime_ns=scanned_file.mtime_ns,
        is_generated=scanned_file.is_generated,
        is_test=scanned_file.is_test,
        metadata=metadata,
    )

    chunks = [
        replace(
            chunk,
            lexical_tokens=_dedupe_tokens(
                [*chunk.lexical_tokens, *_localized_plugin_tokens(chunk, extraction)]
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
    return _PreparedFile(source_file=source_file, chunks=chunks)


def _extract(
    scanned_file: ScannedFile,
    content: str,
    plugins: list[LanguagePlugin],
) -> PluginExtraction:
    for plugin in plugins:
        if plugin.supports(scanned_file.path, scanned_file.language):
            return plugin.extract(scanned_file.path, content)
    return PluginExtraction()


def _localized_plugin_tokens(
    chunk: DocumentChunk,
    extraction: PluginExtraction,
) -> list[str]:
    content = chunk.content.lower()
    chunk_tokens = set(chunk.lexical_tokens)
    return [
        token
        for token in extraction.lexical_tokens
        if _is_token_evidenced(token, content, chunk_tokens)
    ]


def _is_token_evidenced(token: str, content: str, chunk_tokens: set[str]) -> bool:
    normalized = token.lower()
    if normalized in chunk_tokens:
        return True
    if any(not char.isalnum() for char in normalized):
        return normalized in content
    return False


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
