from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from context_search_tool.chunker import chunk_text
from context_search_tool.config import ToolConfig, render_config
from context_search_tool.embeddings import EmbeddingProvider, provider_from_config
from context_search_tool.graph_contract import (
    MAX_PRODUCER_RELATIONS_PER_FILE,
    MAX_SIGNALS_PER_FILE,
    generate_core_module_signal_id,
)
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
    GraphIntegrityError,
    IncompatibleSignalSchemaError,
    TARGET_SIGNAL_SCHEMA_VERSION,
    read_graph_capability,
)
from context_search_tool.graph_plugins import GraphLanguagePlugin, PluginContext
from context_search_tool.graph_resolution import resolve_graph_relations
from context_search_tool.index_lock import exclusive_index_lock
from context_search_tool.manifest import (
    SCHEMA_VERSION as MANIFEST_SCHEMA_VERSION,
    Manifest,
    assert_manifest_compatible,
    embedding_config_hash,
    load_manifest,
    write_manifest,
    write_manifest_v5,
)
from context_search_tool.models import DocumentChunk, SourceFile
from context_search_tool.models import CodeRelation, CodeSignal
from context_search_tool.paths import (
    atomic_write_index_bytes,
    ensure_index_gitignore_entry,
    ensure_index_layout,
    prepare_index_directory,
)
from context_search_tool.plugins import (
    LanguagePlugin,
    PluginExtraction,
    default_plugins,
    ordered_graph_plugins,
)
from context_search_tool.project_scope import (
    PROJECT_SCOPE_METADATA_VERSION,
    PROJECT_SCOPE_METADATA_VERSION_KEY,
    ProjectUnit,
    detect_project_units,
    project_metadata,
    project_unit_topology_fingerprint,
    unit_for_path,
)
from context_search_tool.scanner import (
    ScannedFile,
    read_scanned_file_bytes,
    scan_workspace,
    scan_workspace_v5,
)
from context_search_tool.sqlite_store import FILE_WRITE_IN_PROGRESS_KEY, SQLiteStore
from context_search_tool.test_paths import is_test_path
from context_search_tool.vector_store import NumpyVectorStore
from context_search_tool.test_association import regenerate_test_associations


logger = logging.getLogger(__name__)


class IncompatibleIndexError(RuntimeError):
    pass


CURRENT_SIGNAL_SCHEMA_VERSION = 5
SIGNAL_SCHEMA_VERSION_KEY = "signal_schema_version"


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
    signals: list[CodeSignal]
    relations: list[CodeRelation]


def index_repository(repo: Path, config: ToolConfig) -> IndexSummary:
    return build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=default_plugins(),
        scanner=scan_workspace_v5,
    )


def build_v5_index_snapshot(
    repo: Path,
    config: ToolConfig,
    *,
    graph_plugins: Iterable[GraphLanguagePlugin],
    scanner: Callable[[Path, ToolConfig], list[ScannedFile]],
    file_reader: Callable[..., bytes] = read_scanned_file_bytes,
    embedding_provider: EmbeddingProvider | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> IndexSummary:
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError("repository root must be a directory")
    index_dir = prepare_index_directory(repo)

    with exclusive_index_lock(index_dir):
        store = SQLiteStore(index_dir / "index.sqlite")
        stored_version = store.inspect_signal_schema_version()
        if stored_version > TARGET_SIGNAL_SCHEMA_VERSION:
            raise IncompatibleSignalSchemaError(stored_version)
        plugins = ordered_graph_plugins(graph_plugins)
        manifest_integrity_failed = False
        try:
            assert_manifest_compatible(repo, config)
        except (OSError, ValueError) as error:
            try:
                load_manifest(repo)
            except (OSError, ValueError):
                manifest_integrity_failed = True
            else:
                raise IncompatibleIndexError(str(error)) from error

        existing_files = {
            source.path: source for source in store.source_files_snapshot()
        }
        persisted_paths = store.persisted_file_paths_snapshot()
        scanned_files = _canonical_scanned_files(scanner(repo, config))
        scanned_paths = {scanned.path for scanned in scanned_files}
        deleted_paths = persisted_paths - scanned_paths
        units = detect_project_units(
            repo,
            [scanned.path for scanned in scanned_files],
        )
        topology_fingerprint = project_unit_topology_fingerprint(units)
        unit_by_path = {
            scanned.path: unit_for_path(scanned.path, units)
            for scanned in scanned_files
        }
        scanned_files = [
            replace(
                scanned,
                is_test=is_test_path(
                    scanned.path,
                    scanned.language,
                    _project_unit_key(unit_by_path[scanned.path]),
                ),
            )
            for scanned in scanned_files
        ]
        changed_paths = {
            scanned.path
            for scanned in scanned_files
            if _v5_source_changed(
                scanned,
                existing_files.get(scanned.path),
                unit_by_path[scanned.path],
            )
        }

        entry_state = "legacy"
        entry_full_reindex = stored_version < TARGET_SIGNAL_SCHEMA_VERSION
        stored_topology = None
        if stored_version == TARGET_SIGNAL_SCHEMA_VERSION:
            capability = read_graph_capability(store)
            entry_state = capability.status
            entry_full_reindex = capability.full_reindex_required
            stored_topology = store.get_metadata(
                PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY
            )
        topology_changed = (
            stored_version == TARGET_SIGNAL_SCHEMA_VERSION
            and stored_topology != topology_fingerprint
        )
        project_scope_metadata_current = (
            stored_version < TARGET_SIGNAL_SCHEMA_VERSION
            or project_scope_metadata_is_current(store)
        )
        embedding_identity = embedding_config_hash(config.embedding)
        vector_snapshot_valid = False
        if (
            stored_version == TARGET_SIGNAL_SCHEMA_VERSION
            and not entry_full_reindex
        ):
            try:
                _validate_published_vectors(
                    index_dir,
                    embedding_identity=embedding_identity,
                    dimensions=config.embedding.dimensions,
                    expected_ids=store.active_embedding_ids(),
                )
                vector_snapshot_valid = True
            except ValueError:
                vector_snapshot_valid = False

        no_file_changes = not changed_paths and not deleted_paths
        no_op_candidate = (
            stored_version == TARGET_SIGNAL_SCHEMA_VERSION
            and entry_state == "ready"
            and not entry_full_reindex
            and not topology_changed
            and project_scope_metadata_current
            and no_file_changes
            and vector_snapshot_valid
        )
        integrity_failed = False
        if no_op_candidate:
            stats = store.stats()
            expected_ids = store.active_embedding_ids()
            validator = _external_v5_validator(
                repo=repo,
                config=config,
                expected_embedding_identity=embedding_identity,
                expected_ids=expected_ids,
                expected_source_count=len(scanned_files),
                expected_chunk_count=stats["active_chunks"],
            )
            try:
                store.validate_ready_v5_snapshot(
                    topology_fingerprint=topology_fingerprint,
                    expected_embedding_ids=expected_ids,
                    expected_source_count=len(scanned_files),
                    expected_chunk_count=stats["active_chunks"],
                    external_validator=validator,
                )
            except (GraphIntegrityError, OSError, ValueError):
                integrity_failed = True
            else:
                return IndexSummary(
                    files_seen=len(scanned_files),
                    files_indexed=0,
                    files_skipped=len(scanned_files),
                    files_deleted=0,
                    chunks_indexed=0,
                )

        force_full_reindex = (
            stored_version < TARGET_SIGNAL_SCHEMA_VERSION
            or entry_full_reindex
            or not vector_snapshot_valid
            or integrity_failed
            or manifest_integrity_failed
            or not project_scope_metadata_current
        )
        if stored_version < TARGET_SIGNAL_SCHEMA_VERSION:
            stale_reason = (
                "schema_migration" if stored_version else "full_reindex"
            )
        elif entry_full_reindex:
            stale_reason = "full_reindex"
        elif (
            integrity_failed
            or manifest_integrity_failed
            or not vector_snapshot_valid
        ):
            stale_reason = "integrity_check_failed"
        elif topology_changed:
            stale_reason = "topology_changed"
        elif not project_scope_metadata_current:
            stale_reason = "project_scope_metadata_changed"
        elif changed_paths or deleted_paths:
            stale_reason = "files_changed"
        else:
            stale_reason = "stale_on_entry"

        ensure_index_gitignore_entry(repo)
        if stored_version < TARGET_SIGNAL_SCHEMA_VERSION:
            store.initialize_v5(stale_reason=stale_reason)
        else:
            store.mark_graph_stale(
                stale_reason,
                full_reindex_required=force_full_reindex,
            )
        _fault(fault_hook, "stale_committed")
        store.set_metadata(FILE_WRITE_IN_PROGRESS_KEY, "")

        active_paths = tuple(scanned.path for scanned in scanned_files)
        active_path_units = tuple(
            (
                scanned.path,
                _project_unit_key(unit_by_path[scanned.path]),
            )
            for scanned in scanned_files
        )
        rebuild_paths = set(changed_paths)
        if force_full_reindex:
            rebuild_paths = set(scanned_paths)
        elif entry_state == "stale" or topology_changed or integrity_failed:
            for scanned in scanned_files:
                if scanned.size > 0:
                    rebuild_paths.add(scanned.path)

        prepared_files = [
            _prepare_v5_file(
                repo=repo,
                scanned_file=scanned,
                project_unit=unit_by_path[scanned.path],
                plugins=plugins,
                active_paths=active_paths,
                active_path_units=active_path_units,
                file_reader=file_reader,
                max_file_bytes=config.index.max_file_bytes,
            )
            for scanned in scanned_files
            if scanned.path in rebuild_paths
        ]
        changed_chunks = [
            chunk
            for prepared in prepared_files
            for chunk in prepared.chunks
        ]
        replaced_paths = rebuild_paths | deleted_paths
        removed_embedding_ids = store.active_embedding_ids_for_files(
            replaced_paths
        )
        if force_full_reindex:
            vector_store = NumpyVectorStore.fresh(
                index_dir,
                dimensions=config.embedding.dimensions,
            )
            expected_vector_ids: set[str] = set()
        else:
            vector_store = NumpyVectorStore.load_published(
                index_dir,
                expected_embedding_identity=embedding_identity,
            )
            expected_vector_ids = set(vector_store.ids)
            vector_store.remove_many(sorted(removed_embedding_ids))
            expected_vector_ids -= removed_embedding_ids

        if changed_chunks:
            provider = embedding_provider or provider_from_config(config.embedding)
            _validate_embedding_provider(provider, config)
            vectors = provider.embed_texts(
                [_embedding_text_for_chunk(chunk) for chunk in changed_chunks]
            )
            if len(vectors) != len(changed_chunks):
                raise ValueError("embedding response count mismatch")
            vector_store.upsert_many(
                [
                    (chunk.embedding_id or chunk.chunk_id, vector)
                    for chunk, vector in zip(changed_chunks, vectors)
                ]
            )
        expected_vector_ids.update(
            chunk.embedding_id or chunk.chunk_id for chunk in changed_chunks
        )
        vector_store.sort_by_id()
        if set(vector_store.ids) != expected_vector_ids:
            raise GraphIntegrityError("prepared vector ID set mismatch")
        prepared_vectors = vector_store.prepare_generation(
            generation=uuid.uuid4().hex,
            embedding_identity=embedding_identity,
            fault_hook=fault_hook,
        )
        _fault(fault_hook, "vectors_prepared")

        for prepared in prepared_files:
            file_path = prepared.source_file.path
            store.begin_v5_file_write(file_path)
            _fault(fault_hook, "file_write_started")
            store.replace_chunks(file_path, prepared.chunks)
            _fault(fault_hook, "chunks_persisted")
            store.replace_signals(file_path, prepared.signals)
            _fault(fault_hook, "signals_persisted")
            store.replace_relations(file_path, prepared.relations)
            _fault(fault_hook, "producer_relations_persisted")
            store.finish_v5_file_write(prepared.source_file)
            _fault(fault_hook, "source_hash_persisted")

        for path in sorted(deleted_paths, key=lambda item: item.as_posix()):
            store.mark_file_deleted(path)
            _fault(fault_hook, "deletion_persisted")

        resolve_graph_relations(store, association_only=False)
        producer_generation = store.advance_producer_resolution_generation()
        _fault(fault_hook, "producer_resolver_complete")
        regenerate_test_associations(
            store,
            producer_resolution_generation=producer_generation,
        )
        _fault(fault_hook, "associations_complete")
        resolve_graph_relations(store, association_only=True)
        _fault(fault_hook, "association_resolver_complete")

        vector_store.publish_generation(
            prepared_vectors,
            fault_hook=fault_hook,
        )
        _fault(fault_hook, "vector_descriptor_published")
        atomic_write_index_bytes(
            index_dir / "config.toml",
            render_config(config).encode("utf-8"),
            fault_prefix="config",
            fault_hook=fault_hook,
        )
        stats = store.stats()
        manifest = Manifest(
            embedding_config_hash=embedding_identity,
            embedding_provider=config.embedding.provider,
            embedding_model=config.embedding.model,
            embedding_dimensions=config.embedding.dimensions,
            total_files=len(scanned_files),
            total_chunks=stats["active_chunks"],
        )
        write_manifest_v5(repo, manifest, fault_hook=fault_hook)
        expected_ids = set(vector_store.ids)
        validator = _external_v5_validator(
            repo=repo,
            config=config,
            expected_embedding_identity=embedding_identity,
            expected_ids=expected_ids,
            expected_source_count=len(scanned_files),
            expected_chunk_count=stats["active_chunks"],
        )
        validator()
        _fault(fault_hook, "external_artifacts_validated")
        store.set_metadata(
            PROJECT_SCOPE_METADATA_VERSION_KEY,
            str(PROJECT_SCOPE_METADATA_VERSION),
        )
        _fault(fault_hook, "final_validation")
        store.mark_graph_ready(
            topology_fingerprint=topology_fingerprint,
            expected_embedding_ids=expected_ids,
            expected_source_count=len(scanned_files),
            expected_chunk_count=stats["active_chunks"],
            expected_producer_resolution_generation=producer_generation,
            external_validator=validator,
            indexed_at=int(time.time()),
            before_commit=lambda: _fault(fault_hook, "before_ready_commit"),
        )
        _fault(fault_hook, "after_ready_commit")

        return IndexSummary(
            files_seen=len(scanned_files),
            files_indexed=len(prepared_files),
            files_skipped=len(scanned_files) - len(prepared_files),
            files_deleted=len(deleted_paths),
            chunks_indexed=len(changed_chunks),
        )


def _canonical_scanned_files(
    scanned_files: Iterable[ScannedFile],
) -> list[ScannedFile]:
    ordered = sorted(scanned_files, key=lambda item: item.path.as_posix())
    seen: set[Path] = set()
    for scanned in ordered:
        path = scanned.path
        if (
            path.is_absolute()
            or path.as_posix() in {"", "."}
            or ".." in path.parts
            or "\\" in path.as_posix()
        ):
            raise ValueError("scanner returned an invalid repository path")
        if path in seen:
            raise ValueError("scanner returned duplicate repository paths")
        seen.add(path)
    return ordered


def read_v5_vector_snapshot(
    repo: Path,
    config: ToolConfig,
    graph_session: Any,
) -> NumpyVectorStore | None:
    if not graph_session.capability.structured:
        return None
    source_count, chunk_count = graph_session.source_chunk_counts()
    expected_ids = graph_session.active_embedding_ids()
    embedding_identity = embedding_config_hash(config.embedding)
    try:
        return _load_validated_v5_vector_tuple(
            repo=repo.resolve(),
            config=config,
            expected_embedding_identity=embedding_identity,
            expected_ids=expected_ids,
            expected_source_count=source_count,
            expected_chunk_count=chunk_count,
        )
    except (GraphIntegrityError, OSError, ValueError) as error:
        if graph_session.capability.status == "ready":
            raise GraphIntegrityError("vector_snapshot_mismatch") from error
        logger.warning("vector_snapshot_mismatch")
        return None


def _v5_source_changed(
    scanned: ScannedFile,
    existing: SourceFile | None,
    project_unit: ProjectUnit,
) -> bool:
    if existing is None:
        return True
    expected_project = project_metadata(project_unit)
    return any(
        (
            existing.sha256 != scanned.sha256,
            existing.language != scanned.language,
            existing.size != scanned.size,
            existing.is_generated != scanned.is_generated,
            existing.is_test != scanned.is_test,
            existing.metadata.get("project_root")
            != expected_project["project_root"],
        )
    )


def _project_unit_key(project_unit: ProjectUnit) -> str:
    return str(project_metadata(project_unit)["project_root"])


def _v5_plugin_context(
    scanned_file: ScannedFile,
    project_unit: ProjectUnit,
    active_paths: tuple[Path, ...],
    active_path_units: tuple[tuple[Path, str], ...],
) -> PluginContext:
    return PluginContext(
        file_path=scanned_file.path,
        language=scanned_file.language,
        project_unit_key=_project_unit_key(project_unit),
        project_metadata=project_metadata(project_unit),
        active_paths=active_paths,
        active_path_project_units=active_path_units,
    )


def _prepare_v5_file(
    *,
    repo: Path,
    scanned_file: ScannedFile,
    project_unit: ProjectUnit,
    plugins: tuple[GraphLanguagePlugin, ...],
    active_paths: tuple[Path, ...],
    active_path_units: tuple[tuple[Path, str], ...],
    file_reader: Callable[..., bytes],
    max_file_bytes: int,
) -> _PreparedFile:
    content_bytes = file_reader(
        repo,
        scanned_file,
        max_file_bytes=max_file_bytes,
    )
    if (
        len(content_bytes) != scanned_file.size
        or hashlib.sha256(content_bytes).hexdigest() != scanned_file.sha256
    ):
        raise ValueError("file changed since scan")
    content = content_bytes.decode("utf-8", errors="replace")
    context = _v5_plugin_context(
        scanned_file,
        project_unit,
        active_paths,
        active_path_units,
    )
    supported = (
        tuple(plugin for plugin in plugins if plugin.supports(context))
        if content_bytes
        else ()
    )
    parsed = tuple(
        (plugin, plugin.parse(context, content_bytes)) for plugin in supported
    )
    symbols = [
        symbol
        for _plugin, facts in parsed
        for symbol in facts.symbols
    ]
    lexical_tokens = [
        token
        for _plugin, facts in parsed
        for token in facts.lexical_tokens
    ]
    project_fields = project_metadata(project_unit)
    scanner_fields = {"is_test": scanned_file.is_test}
    lexical_extraction = PluginExtraction(
        symbols=symbols,
        lexical_tokens=lexical_tokens,
    )
    chunks = [
        replace(
            chunk,
            lexical_tokens=_dedupe_tokens(
                [
                    *chunk.lexical_tokens,
                    *_localized_plugin_tokens(chunk, lexical_extraction),
                ]
            ),
            embedding_id=chunk.chunk_id,
            metadata={**chunk.metadata, **scanner_fields, **project_fields},
        )
        for chunk in chunk_text(
            scanned_file.path,
            content,
            scanned_file.language,
            symbols,
        )
    ]
    module_signal = _v5_module_signal(
        scanned_file,
        project_unit,
        chunks[0],
    ) if chunks else None
    materialized: list[tuple[GraphLanguagePlugin, Any]] = []
    if module_signal is not None:
        materialized = [
            (
                plugin,
                plugin.materialize(
                    context,
                    facts,
                    tuple(chunks),
                    module_signal,
                ),
            )
            for plugin, facts in parsed
        ]

    producer_signals = [
        signal
        for _plugin, graph in materialized
        for signal in graph.signals
    ]
    unique_signals: dict[str, CodeSignal] = {}
    for signal in sorted(producer_signals, key=_v5_signal_order):
        existing = unique_signals.get(signal.signal_id)
        if existing is not None and existing != signal:
            raise ValueError("conflicting graph signal identity")
        unique_signals.setdefault(signal.signal_id, signal)
    signal_budget = MAX_SIGNALS_PER_FILE - (1 if module_signal is not None else 0)
    retained_producer_signals = list(unique_signals.values())[:signal_budget]
    signals = (
        [module_signal, *retained_producer_signals]
        if module_signal is not None
        else []
    )
    active_signal_ids = {signal.signal_id for signal in signals}
    merged_relations = _merge_v5_relations(
        relation
        for _plugin, graph in materialized
        for relation in graph.relations
    )
    eligible_relations = [
        relation
        for relation in merged_relations
        if relation.source_signal_id in active_signal_ids
    ]
    relations = eligible_relations[:MAX_PRODUCER_RELATIONS_PER_FILE]
    plugin_metadata = {
        _graph_plugin_key(plugin): {
            "parse": dict(facts.metadata),
            "fallback_required": facts.fallback_required,
        }
        for plugin, facts in parsed
    }
    for plugin, graph in materialized:
        plugin_metadata.setdefault(_graph_plugin_key(plugin), {})[
            "materialize"
        ] = dict(graph.metadata)
    metadata = {
        **dict(scanned_file.metadata),
        **project_fields,
        "graph_plugins": plugin_metadata,
        "graph_omitted_signal_count": (
            len(unique_signals) - len(retained_producer_signals)
        ),
        "graph_omitted_relation_count": (
            len(merged_relations) - len(relations)
        ),
    }
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
    return _PreparedFile(
        source_file=source_file,
        chunks=chunks,
        signals=signals,
        relations=relations,
    )


def _v5_module_signal(
    scanned_file: ScannedFile,
    project_unit: ProjectUnit,
    chunk: DocumentChunk,
) -> CodeSignal:
    path = scanned_file.path.as_posix()
    return CodeSignal(
        signal_id=generate_core_module_signal_id(
            file_path=path,
            start_line=chunk.start_line,
            start_column=0,
            end_line=chunk.end_line,
            end_column=0,
        ),
        chunk_id=chunk.chunk_id,
        file_path=scanned_file.path,
        kind="module",
        name=path,
        qualified_name=path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        language=scanned_file.language,
        project_unit_key=_project_unit_key(project_unit),
        producer="core_module",
        recallable=False,
    )


def _v5_signal_order(signal: CodeSignal) -> tuple[object, ...]:
    return (
        signal.start_line,
        signal.start_column,
        signal.end_line,
        signal.end_column,
        signal.kind,
        signal.qualified_name,
        signal.signature,
        signal.signal_id,
    )


def _merge_v5_relations(
    relations: Iterable[CodeRelation],
) -> list[CodeRelation]:
    grouped: dict[str, list[CodeRelation]] = {}
    for relation in relations:
        grouped.setdefault(relation.relation_id, []).append(relation)
    merged: list[CodeRelation] = []
    for relation_id in sorted(grouped):
        occurrences = sorted(grouped[relation_id], key=_v5_relation_order)
        selected = occurrences[0]
        comparable = replace(selected, metadata={})
        if any(replace(item, metadata={}) != comparable for item in occurrences[1:]):
            raise ValueError("conflicting graph relation identity")
        metadata = dict(selected.metadata)
        metadata["occurrence_count"] = sum(
            max(1, int(item.metadata.get("occurrence_count", 1)))
            for item in occurrences
        )
        positions = [
            (
                int(item.metadata.get("first_source_line", 0)),
                int(item.metadata.get("first_source_column", 0)),
            )
            for item in occurrences
        ]
        first_line, first_column = min(positions)
        metadata["first_source_line"] = first_line
        metadata["first_source_column"] = first_column
        merged.append(replace(selected, metadata=metadata))
    return sorted(merged, key=_v5_relation_order)


def _v5_relation_order(relation: CodeRelation) -> tuple[object, ...]:
    return (
        int(relation.metadata.get("first_source_line", 0)),
        int(relation.metadata.get("first_source_column", 0)),
        relation.kind,
        relation.target_kind,
        relation.target_qualified_name,
        relation.target_signature,
        relation.target_arity if relation.target_arity is not None else -1,
        relation.target_project_unit_key,
        relation.relation_id,
    )


def _graph_plugin_key(plugin: GraphLanguagePlugin) -> str:
    return f"{type(plugin).__module__}.{type(plugin).__qualname__}"


def _validate_embedding_provider(
    provider: EmbeddingProvider,
    config: ToolConfig,
) -> None:
    fingerprint = provider.fingerprint()
    expected = {
        "provider": config.embedding.provider,
        "model": config.embedding.model,
        "dimensions": config.embedding.dimensions,
    }
    if any(fingerprint.get(key) != value for key, value in expected.items()):
        raise ValueError("embedding provider identity mismatch")


def _validate_published_vectors(
    index_dir: Path,
    *,
    embedding_identity: str,
    dimensions: int,
    expected_ids: set[str],
) -> None:
    descriptor, loaded = NumpyVectorStore.load_published_snapshot(
        index_dir,
        expected_embedding_identity=embedding_identity,
    )
    if descriptor is None:
        raise ValueError("published vector descriptor is missing")
    if descriptor.embedding_identity != embedding_identity:
        raise ValueError("vector embedding identity mismatch")
    if descriptor.dimensions != dimensions:
        raise ValueError("vector generation dimensions mismatch")
    if set(loaded.ids) != expected_ids:
        raise ValueError("vector snapshot IDs do not match SQLite")


def _external_v5_validator(
    *,
    repo: Path,
    config: ToolConfig,
    expected_embedding_identity: str,
    expected_ids: set[str],
    expected_source_count: int,
    expected_chunk_count: int,
) -> Callable[[], None]:
    def validate() -> None:
        _load_validated_v5_vector_tuple(
            repo=repo,
            config=config,
            expected_embedding_identity=expected_embedding_identity,
            expected_ids=expected_ids,
            expected_source_count=expected_source_count,
            expected_chunk_count=expected_chunk_count,
        )

    return validate


def _load_validated_v5_vector_tuple(
    *,
    repo: Path,
    config: ToolConfig,
    expected_embedding_identity: str,
    expected_ids: set[str],
    expected_source_count: int,
    expected_chunk_count: int,
) -> NumpyVectorStore:
    index_dir = repo / ".context-search"
    expected_config = render_config(config).encode("utf-8")
    if (index_dir / "config.toml").read_bytes() != expected_config:
        raise GraphIntegrityError("config snapshot mismatch")
    manifest = load_manifest(repo)
    if (
        manifest.schema_version != MANIFEST_SCHEMA_VERSION
        or manifest.embedding_config_hash != expected_embedding_identity
        or manifest.embedding_provider != config.embedding.provider
        or manifest.embedding_model != config.embedding.model
        or manifest.embedding_dimensions != config.embedding.dimensions
        or manifest.total_files != expected_source_count
        or manifest.total_chunks != expected_chunk_count
    ):
        raise GraphIntegrityError("manifest snapshot mismatch")
    descriptor, loaded = NumpyVectorStore.load_published_snapshot(
        index_dir,
        expected_embedding_identity=expected_embedding_identity,
    )
    if descriptor is None:
        raise GraphIntegrityError("vector descriptor is missing")
    if (
        descriptor.embedding_identity != expected_embedding_identity
        or descriptor.dimensions != config.embedding.dimensions
        or descriptor.row_count != expected_chunk_count
    ):
        raise GraphIntegrityError("vector descriptor snapshot mismatch")
    if loaded.ids != tuple(sorted(expected_ids)):
        raise GraphIntegrityError("vector ID snapshot mismatch")
    return loaded


def _fault(
    fault_hook: Callable[[str], None] | None,
    stage: str,
) -> None:
    if fault_hook is not None:
        fault_hook(stage)


def signal_schema_is_current(store: SQLiteStore) -> bool:
    version = store.get_metadata(SIGNAL_SCHEMA_VERSION_KEY)
    if version is None:
        return False
    try:
        return int(version) == CURRENT_SIGNAL_SCHEMA_VERSION
    except ValueError:
        return False


def project_scope_metadata_is_current(store: SQLiteStore) -> bool:
    version = store.get_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY)
    if version is None:
        return False
    try:
        return int(version) >= PROJECT_SCOPE_METADATA_VERSION
    except ValueError:
        return False


def _ensure_config_file(index_dir: Path, config: ToolConfig) -> None:
    if not (index_dir / "config.toml").exists():
        (index_dir / "config.toml").write_text(
            render_config(config),
            encoding="utf-8",
        )


def _prepare_file(
    scanned_file: ScannedFile,
    plugins: list[LanguagePlugin],
    project_unit: ProjectUnit,
) -> _PreparedFile:
    content = scanned_file.absolute_path.read_text(encoding="utf-8", errors="replace")
    extraction = _extract(scanned_file, content, plugins)
    metadata = dict(scanned_file.metadata)
    if extraction.metadata:
        metadata["plugin"] = extraction.metadata
    project_fields = project_metadata(project_unit)
    scanner_fields = {
        "is_test": scanned_file.is_test,
    }

    source_file = SourceFile(
        path=scanned_file.path,
        language=scanned_file.language,
        sha256=scanned_file.sha256,
        size=scanned_file.size,
        mtime_ns=scanned_file.mtime_ns,
        is_generated=scanned_file.is_generated,
        is_test=scanned_file.is_test,
        metadata={**metadata, **project_fields},
    )

    chunks = [
        replace(
            chunk,
            lexical_tokens=_dedupe_tokens(
                [*chunk.lexical_tokens, *_localized_plugin_tokens(chunk, extraction)]
            ),
            embedding_id=chunk.chunk_id,
            metadata={**chunk.metadata, **scanner_fields, **project_fields},
        )
        for chunk in chunk_text(
            scanned_file.path,
            content,
            scanned_file.language,
            extraction.symbols,
        )
    ]
    signals = _attach_signals_to_chunks(scanned_file.path, extraction.signals, chunks)
    return _PreparedFile(
        source_file=source_file,
        chunks=chunks,
        signals=signals,
        relations=extraction.relations,
    )


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


def _attach_signals_to_chunks(
    file_path: Path,
    signals: list[CodeSignal],
    chunks: list[DocumentChunk],
) -> list[CodeSignal]:
    attached: list[CodeSignal] = []
    for signal in signals:
        chunk = _chunk_for_signal(signal, chunks)
        attached.append(
            replace(
                signal,
                chunk_id=chunk.chunk_id if chunk is not None else signal.chunk_id,
                file_path=file_path,
            )
        )
    return attached


def _chunk_for_signal(
    signal: CodeSignal,
    chunks: list[DocumentChunk],
) -> DocumentChunk | None:
    for chunk in chunks:
        if chunk.start_line <= signal.start_line <= chunk.end_line:
            return chunk
    return None


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
