from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from context_search_tool.chunker import chunk_text
from context_search_tool.config import ToolConfig, load_config, read_config, render_config
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
    IncompatibleOperationalSchemaError,
    IncompatibleSignalSchemaError,
    IndexBusyError,
    OperationalIntegrityError,
    TARGET_SIGNAL_SCHEMA_VERSION,
    read_graph_capability,
    read_operational_capability,
)
from context_search_tool.graph_plugins import (
    GraphLanguagePlugin,
    PluginContext,
    RepositoryPathIndex,
)
from context_search_tool.graph_resolution import resolve_graph_relations
from context_search_tool.index_lock import exclusive_index_lock
from context_search_tool.index_health import (
    EmbeddingIdentity,
    configured_embedding_identity,
    indexed_embedding_identity,
    preflight_public_operation,
    probe_raw_index_capability,
)
from context_search_tool.manifest import (
    SCHEMA_VERSION as MANIFEST_SCHEMA_VERSION,
    Manifest,
    ManifestV2,
    IncompatibleManifestSchemaError,
    LoadedManifestSnapshot,
    PreparedManifestV2,
    assert_manifest_compatible,
    embedding_config_hash,
    index_config_hash,
    inspect_raw_manifest_schema,
    load_manifest,
    load_manifest_snapshot,
    prepare_manifest_v2,
    publish_manifest_v2,
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
    CoverageSkipObservation,
    ObservedFileRead,
    ScannedFile,
    WorkspaceInventory,
    observe_workspace,
    read_observed_file,
    read_scanned_file_bytes,
    scan_workspace,
    scan_workspace_v5,
    workspace_inventory_identity,
)
from context_search_tool.sqlite_store import (
    FILE_WRITE_IN_PROGRESS_KEY,
    OperationalControlObservation,
    OperationalReadyBinding,
    OperationalScanSkip,
    OperationalSnapshot,
    OperationalSourceObservation,
    SQLiteStore,
    operational_content_fingerprint,
    operational_observation_fingerprint,
)
from context_search_tool.test_paths import is_test_path
from context_search_tool.vector_store import (
    FrozenVectorGeneration,
    NumpyVectorStore,
    PreparedVectorGeneration,
    PublishedVectorDescriptor,
)
from context_search_tool.test_association import regenerate_test_associations


logger = logging.getLogger(__name__)


class IncompatibleIndexError(RuntimeError):
    pass


class InventoryIncompleteError(ValueError):
    code = "inventory_incomplete"

    def __init__(self) -> None:
        super().__init__("repository inventory is incomplete")


class WorkspaceChangedError(ValueError):
    code = "workspace_changed"

    def __init__(self) -> None:
        super().__init__("repository changed during index preparation")


CURRENT_SIGNAL_SCHEMA_VERSION = 5
SIGNAL_SCHEMA_VERSION_KEY = "signal_schema_version"
_PATH_INVENTORY_RELATION_KINDS = ("imports", "routes_to")
_QUICK_RETRY_LIMIT = 32
_QUICK_ALLOWED_STALE_REASONS = frozenset(
    {"files_changed", "path_inventory_changed", "topology_changed", "stale_on_entry"}
)
_DEPENDENT_REASON_ORDER = (
    "content_candidate",
    "added_path",
    "deleted_path",
    "coverage_changed",
    "index_config_changed",
    "embedding_config_changed",
    "project_topology_changed",
    "path_inventory_changed",
    "schema_or_integrity_rebuild",
)


@dataclass(frozen=True)
class IndexSummary:
    files_seen: int
    files_indexed: int
    files_skipped: int
    files_deleted: int
    chunks_indexed: int


@dataclass(frozen=True)
class DependentRebuildCount:
    reason: str
    files: int

    def to_dict(self) -> dict[str, int | str]:
        return {"reason": self.reason, "files": self.files}


@dataclass(frozen=True)
class RefreshFileCounts:
    direct_dirty: int = 0
    content_changed: int = 0
    metadata_only: int = 0
    dependent_rebuild: int = 0
    dependent_rebuilds: tuple[DependentRebuildCount, ...] = ()
    deleted: int = 0
    coverage_skips: int = 0
    parsed: int = 0


@dataclass(frozen=True)
class RefreshChunkCounts:
    embedded: int = 0


@dataclass(frozen=True)
class RefreshInventoryWork:
    passes: int = 2
    entries: int = 0
    errors: int = 0
    retryable_skip_attempts: int = 0


@dataclass(frozen=True)
class RefreshSourceWork:
    bytes_read: int = 0
    bytes_hashed: int = 0


@dataclass(frozen=True)
class RefreshPathIndexWork:
    builds: int = 0
    paths_canonicalized: int = 0


@dataclass(frozen=True)
class RefreshGraphWork:
    relations_scanned: int = 0
    relations_resolved: int = 0
    association_inputs: int = 0
    association_writes: int = 0


@dataclass(frozen=True)
class RefreshVectorWork:
    bytes_read: int = 0
    bytes_copied: int = 0
    bytes_written: int = 0
    bytes_hashed: int = 0
    payload_passes: int = 0
    prior_payload_passes: int = 0
    prepared_payload_passes: int = 0
    generations_before: int = 1
    generations_after: int = 1
    descriptor_action: str = "reused"


@dataclass(frozen=True)
class RefreshMaintenanceWork:
    tombstones_before: int = 0
    tombstones_purged: int = 0
    tombstones_after: int = 0
    sqlite_pages_before: int = 0
    sqlite_pages_after: int = 0
    sqlite_freelist_before: int = 0
    sqlite_freelist_after: int = 0


@dataclass(frozen=True)
class RefreshWorkCounts:
    inventory: RefreshInventoryWork = RefreshInventoryWork()
    source: RefreshSourceWork = RefreshSourceWork()
    path_index: RefreshPathIndexWork = RefreshPathIndexWork()
    graph: RefreshGraphWork = RefreshGraphWork()
    vector: RefreshVectorWork = RefreshVectorWork()
    maintenance: RefreshMaintenanceWork = RefreshMaintenanceWork()


@dataclass(frozen=True)
class RefreshSummaryV1:
    operation: str
    outcome: str
    verification: str
    observation_generation: str
    files: RefreshFileCounts
    chunks: RefreshChunkCounts
    work: RefreshWorkCounts

    def to_dict(self) -> dict[str, Any]:
        _validate_refresh_summary(self)
        rendered = asdict(self)
        rendered["files"]["dependent_rebuilds"] = [
            item.to_dict() for item in self.files.dependent_rebuilds
        ]
        return rendered


@dataclass(frozen=True)
class RefreshSuccess:
    summary: RefreshSummaryV1
    indexed_before: EmbeddingIdentity
    configured: EmbeddingIdentity
    freshness: str = "metadata_fresh"
    network_egress_performed: bool = False
    ok: bool = True


@dataclass(frozen=True)
class RefreshFailure:
    code: str
    message: str
    network_egress_outcome: str = "not_attempted"
    ok: bool = False


RefreshResult = RefreshSuccess | RefreshFailure


@dataclass
class _EgressTracker:
    network_capable: bool
    outcome: str = "not_attempted"

    def request_started(self) -> None:
        if self.network_capable:
            self.outcome = "possible"

    def response_received(self) -> None:
        if self.network_capable:
            self.outcome = "performed"


@dataclass(frozen=True)
class _PersistenceWork:
    relations_resolved: int
    association_writes: int
    tombstones_purged: int


@dataclass(frozen=True)
class _QuickBaseline:
    loaded_manifest: LoadedManifestSnapshot
    manifest: ManifestV2
    operational: OperationalSnapshot
    descriptor: PublishedVectorDescriptor
    topology_fingerprint: str
    graph_status: str
    graph_stale_reason: str


class _AuthoritativeRefreshRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class _PreparedFile:
    source_file: SourceFile
    chunks: tuple[DocumentChunk, ...]
    signals: tuple[CodeSignal, ...]
    relations: tuple[CodeRelation, ...]


@dataclass(frozen=True)
class PreparedIndexSnapshot:
    effective_config: ToolConfig
    effective_config_payload: bytes
    index_config_hash: str
    opening_inventory: WorkspaceInventory
    closing_inventory: WorkspaceInventory
    observation_started_at_epoch_ms: int
    observation_completed_at_epoch_ms: int
    observation_generation: int
    source_observations: tuple[OperationalSourceObservation, ...]
    scan_skips: tuple[OperationalScanSkip, ...]
    control_observations: tuple[OperationalControlObservation, ...]
    source_content_fingerprint: str
    source_observation_fingerprint: str
    scanned_files: tuple[ScannedFile, ...]
    repository_path_index: RepositoryPathIndex
    prepared_files: tuple[_PreparedFile, ...]
    deleted_paths: tuple[Path, ...]
    project_units: tuple[ProjectUnit, ...]
    topology_fingerprint: str
    expected_vector_ids: tuple[str, ...]
    frozen_vector_generation: FrozenVectorGeneration | None
    prepared_vector_generation: PreparedVectorGeneration
    vector_descriptor_snapshot: PublishedVectorDescriptor
    publish_vector_descriptor: bool
    prepared_manifest: PreparedManifestV2
    work_metrics: tuple[tuple[str, int | str], ...]
    stale_reason: str
    force_full_reindex: bool
    stored_signal_version: int
    suppress_fault_hooks: bool
    summary: IndexSummary


def index_repository(
    repo: Path,
    config: ToolConfig | None = None,
    *,
    config_loader: Callable[[Path], ToolConfig] | None = None,
) -> IndexSummary:
    preflight_public_operation(repo, "index")
    deferred_config_loader = config_loader or (lambda path: load_config(path))
    return build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=default_plugins(),
        scanner=scan_workspace_v5,
        config_loader=deferred_config_loader,
    )


def refresh_repository(
    repo: Path,
    config: ToolConfig | None = None,
    *,
    graph_plugins: Iterable[GraphLanguagePlugin] | None = None,
    inventory_observer: Callable[[Path, ToolConfig], WorkspaceInventory] | None = None,
    observed_reader: Callable[..., ObservedFileRead] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    config_loader: Callable[[Path], ToolConfig] | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> RefreshResult:
    """Refresh a compatible v2 index from metadata-dirty source paths only.

    This is intentionally an internal seam in Task 6. Public CLI and MCP
    exposure is added separately so query-like operations cannot opt into a
    repository mutation implicitly.
    """
    try:
        resolved = repo.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("repository root must be a directory")
        capability = probe_raw_index_capability(resolved)
    except (OSError, ValueError):
        return _refresh_failure("refresh_failed")

    preflight_failure = _quick_preflight_failure(capability)
    if preflight_failure is not None:
        return preflight_failure

    tracker = _EgressTracker(network_capable=True)
    try:
        with exclusive_index_lock(resolved / ".context-search"):
            effective_config = _freeze_effective_config(
                config
                if config is not None
                else (config_loader or read_config)(resolved)
            )
            tracker.network_capable = effective_config.embedding.provider != "hash"
            return _refresh_repository_locked(
                repo=resolved,
                config=effective_config,
                graph_plugins=ordered_graph_plugins(
                    graph_plugins if graph_plugins is not None else default_plugins()
                ),
                inventory_observer=inventory_observer or observe_workspace,
                observed_reader=observed_reader or read_observed_file,
                embedding_provider=embedding_provider,
                fault_hook=fault_hook,
                tracker=tracker,
            )
    except IndexBusyError:
        return _refresh_failure("index_busy")
    except IncompatibleManifestSchemaError:
        return _refresh_failure("incompatible_manifest_schema")
    except IncompatibleOperationalSchemaError:
        return _refresh_failure("incompatible_operational_schema")
    except IncompatibleSignalSchemaError:
        return _refresh_failure("incompatible_signal_schema")
    except InventoryIncompleteError:
        return _refresh_failure("inventory_incomplete", tracker.outcome)
    except WorkspaceChangedError:
        return _refresh_failure("workspace_changed", tracker.outcome)
    except _AuthoritativeRefreshRequired:
        return _refresh_failure("authoritative_index_required", tracker.outcome)
    except Exception:
        return _refresh_failure("refresh_failed", tracker.outcome)


def build_v5_index_snapshot(
    repo: Path,
    config: ToolConfig | None,
    *,
    graph_plugins: Iterable[GraphLanguagePlugin],
    scanner: Callable[[Path, ToolConfig], list[ScannedFile]],
    file_reader: Callable[..., bytes] | None = None,
    inventory_observer: Callable[[Path, ToolConfig], WorkspaceInventory] | None = None,
    observed_reader: Callable[..., ObservedFileRead] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    config_loader: Callable[[Path], ToolConfig] | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> IndexSummary:
    del scanner  # The authoritative path uses the richer two-fence inventory contract.
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError("repository root must be a directory")
    index_dir = prepare_index_directory(repo)

    with exclusive_index_lock(index_dir):
        store = SQLiteStore(index_dir / "index.sqlite")
        stored_version = store.inspect_signal_schema_version()
        _require_authoritative_schema_compatibility(repo, store, stored_version)

        provided_config = config is not None
        effective_config = _freeze_effective_config(
            config
            if config is not None
            else (config_loader or load_config)(repo)
        )
        loaded_manifest, manifest_integrity_failed = _load_authoritative_manifest(
            repo,
            effective_config,
        )
        _retry_existing_vector_generation_cleanup(repo, store)
        _initialize_index_controls(
            repo,
            effective_config,
            overwrite_config=provided_config,
        )

        prepared = _prepare_authoritative_index(
            repo=repo,
            store=store,
            stored_version=stored_version,
            config=effective_config,
            graph_plugins=ordered_graph_plugins(graph_plugins),
            file_reader=file_reader or read_scanned_file_bytes,
            inventory_observer=inventory_observer or observe_workspace,
            observed_reader=observed_reader or read_observed_file,
            embedding_provider=embedding_provider,
            loaded_manifest=loaded_manifest,
            manifest_integrity_failed=manifest_integrity_failed,
            fault_hook=fault_hook,
        )
        _persist_prepared_index(
            repo=repo,
            store=store,
            prepared=prepared,
            fault_hook=fault_hook,
        )
        return prepared.summary


def _quick_preflight_failure(capability: Any) -> RefreshFailure | None:
    if capability.status == "missing":
        return _refresh_failure("missing_index")
    if capability.status == "incompatible":
        return _refresh_failure(
            {
                "future_manifest_schema": "incompatible_manifest_schema",
                "future_operational_schema": "incompatible_operational_schema",
                "future_graph_schema": "incompatible_signal_schema",
            }.get(capability.error_code, "authoritative_index_required")
        )
    if capability.status == "corrupt":
        return _refresh_failure("authoritative_index_required")
    if capability.manifest_version != 2:
        return _refresh_failure("authoritative_index_required")
    return None


def _refresh_failure(
    code: str,
    network_egress_outcome: str = "not_attempted",
) -> RefreshFailure:
    messages = {
        "missing_index": "an existing v2 index is required",
        "authoritative_index_required": "authoritative indexing is required",
        "incompatible_manifest_schema": "manifest schema is incompatible",
        "incompatible_operational_schema": "operational schema is incompatible",
        "incompatible_signal_schema": "signal schema is incompatible",
        "index_busy": "another index writer is active",
        "inventory_incomplete": "repository inventory is incomplete",
        "workspace_changed": "repository changed during refresh",
        "refresh_failed": "refresh failed",
    }
    if network_egress_outcome not in {"not_attempted", "possible", "performed"}:
        network_egress_outcome = "possible"
    return RefreshFailure(
        code=code,
        message=messages.get(code, "refresh failed"),
        network_egress_outcome=network_egress_outcome,
    )


def _refresh_repository_locked(
    *,
    repo: Path,
    config: ToolConfig,
    graph_plugins: tuple[GraphLanguagePlugin, ...],
    inventory_observer: Callable[[Path, ToolConfig], WorkspaceInventory],
    observed_reader: Callable[..., ObservedFileRead],
    embedding_provider: EmbeddingProvider | None,
    fault_hook: Callable[[str], None] | None,
    tracker: _EgressTracker,
) -> RefreshSuccess:
    index_dir = repo / ".context-search"
    store = SQLiteStore(index_dir / "index.sqlite")
    baseline = _load_quick_baseline(repo, store)
    generations_before = NumpyVectorStore.generation_pair_count(index_dir)
    _cleanup_unreferenced_vector_generations(
        index_dir,
        store,
        keep_generation=baseline.descriptor.descriptor.generation,
    )
    pages_before, freelist_before = store.storage_page_metrics()
    tombstones_before = store.tombstone_count()
    effective_index_hash = index_config_hash(config)
    embedding_identity = embedding_config_hash(config.embedding)
    indexed_before = indexed_embedding_identity(baseline.manifest)
    configured = configured_embedding_identity(config)

    observation_started = time.time_ns() // 1_000_000
    opening = inventory_observer(repo, config)
    _fault(fault_hook, "opening_inventory_complete")
    if not opening.complete:
        raise InventoryIncompleteError()
    if baseline.manifest.embedding_config_hash != embedding_identity:
        raise _AuthoritativeRefreshRequired()

    quiet = (
        baseline.graph_status == "ready"
        and _quick_inventory_matches_snapshot(
            opening,
            baseline.operational,
            effective_index_hash,
        )
    )
    if quiet:
        closing = inventory_observer(repo, config)
        if (
            not closing.complete
            or workspace_inventory_identity(opening)
            != workspace_inventory_identity(closing)
        ):
            raise WorkspaceChangedError()
        _fault(fault_hook, "closing_inventory_complete")
        pages_after, freelist_after = store.storage_page_metrics()
        summary = _quick_noop_summary(
            baseline=baseline,
            opening=opening,
            closing=closing,
            generations_before=generations_before,
            generations_after=NumpyVectorStore.generation_pair_count(index_dir),
            tombstones=tombstones_before,
            pages_before=pages_before,
            pages_after=pages_after,
            freelist_before=freelist_before,
            freelist_after=freelist_after,
        )
        return RefreshSuccess(
            summary=summary,
            indexed_before=indexed_before,
            configured=configured,
        )

    prior_sources = {
        item.path: item for item in baseline.operational.source_observations
    }
    prior_skips = {item.path: item for item in baseline.operational.scan_skips}
    eligible = {item.path: item for item in opening.eligible}
    current_inventory_skips = {
        item.path: item for item in opening.coverage_skips
    }
    retry_candidates = sorted(
        (
            prior
            for path, prior in prior_skips.items()
            if prior.retryable and path in eligible
        ),
        key=_retryable_skip_order,
    )
    selected_retry_paths = {
        item.path for item in retry_candidates[:_QUICK_RETRY_LIMIT]
    }
    deferred_retry_paths = {
        item.path for item in retry_candidates[_QUICK_RETRY_LIMIT:]
    }
    metadata_candidates = {
        path
        for path in set(eligible) & set(prior_sources)
        if not _observation_matches_source(eligible[path], prior_sources[path])
    }
    newly_eligible = {
        path
        for path in set(eligible) - set(prior_sources)
        if path not in deferred_retry_paths
        and (
            path not in prior_skips
            or not prior_skips[path].retryable
            or path in selected_retry_paths
        )
    }
    direct_paths = tuple(
        sorted(
            metadata_candidates | newly_eligible | selected_retry_paths,
            key=lambda item: item.as_posix(),
        )
    )
    bodies: dict[Path, bytes] = {}
    read_results: dict[Path, ObservedFileRead] = {}
    read_skips: dict[Path, CoverageSkipObservation] = {}
    content_paths: set[Path] = set()
    metadata_only_paths: set[Path] = set()
    for path in direct_paths:
        observation = eligible[path]
        result = observed_reader(
            repo,
            observation,
            max_file_bytes=config.index.max_file_bytes,
            require_utf8=False,
        )
        read_results[path] = result
        _fault(fault_hook, "direct_read_complete")
        if _successful_observed_read(result):
            assert result.content is not None and result.sha256 is not None
            bodies[path] = result.content
            previous = prior_sources.get(path)
            if (
                previous is not None
                and previous.sha256 == result.sha256
                and previous.language == observation.language
            ):
                metadata_only_paths.add(path)
            else:
                content_paths.add(path)
        else:
            if result.reason == "changed_during_read":
                raise WorkspaceChangedError()
            read_skips[path] = _coverage_skip_from_read(observation, result)

    active_paths = set(eligible) - deferred_retry_paths - set(read_skips)
    deleted_paths = set(prior_sources) - active_paths
    active_path_tuple = tuple(sorted(active_paths, key=lambda item: item.as_posix()))
    project_units = detect_project_units(repo, active_path_tuple)
    topology_fingerprint = project_unit_topology_fingerprint(project_units)
    unit_by_path = {
        path: unit_for_path(path, project_units) for path in active_path_tuple
    }
    active_path_units = tuple(
        (path, _project_unit_key(unit_by_path[path])) for path in active_path_tuple
    )
    repository_path_index = RepositoryPathIndex(
        active_path_tuple,
        active_path_units,
    )
    topology_changed = topology_fingerprint != baseline.topology_fingerprint
    path_inventory_changed = active_paths != set(prior_sources)

    dependency_reasons: dict[Path, set[str]] = {}

    def depend(paths: Iterable[Path], reason: str) -> None:
        for path in paths:
            if path in active_paths and path not in content_paths:
                dependency_reasons.setdefault(path, set()).add(reason)

    nonempty_active = {
        path for path in active_paths if eligible[path].size > 0
    }
    if topology_changed:
        depend(nonempty_active, "project_topology_changed")
    if path_inventory_changed:
        depend(
            store.active_relation_source_paths(_PATH_INVENTORY_RELATION_KINDS),
            "path_inventory_changed",
        )
    if baseline.graph_status == "stale":
        depend(nonempty_active, "schema_or_integrity_rebuild")

    dependent_paths = set(dependency_reasons)
    for path in sorted(dependent_paths, key=lambda item: item.as_posix()):
        if path in bodies:
            continue
        observation = eligible[path]
        result = observed_reader(
            repo,
            observation,
            max_file_bytes=config.index.max_file_bytes,
            require_utf8=False,
        )
        read_results[path] = result
        _fault(fault_hook, "dependent_read_complete")
        if not _successful_observed_read(result):
            raise WorkspaceChangedError()
        assert result.content is not None and result.sha256 is not None
        bodies[path] = result.content
        previous = prior_sources.get(path)
        if (
            previous is None
            or previous.sha256 != result.sha256
            or previous.language != observation.language
        ):
            content_paths.add(path)
            metadata_only_paths.discard(path)

    scanned_files: list[ScannedFile] = []
    for path in active_path_tuple:
        observation = eligible[path]
        result = read_results.get(path)
        previous = prior_sources.get(path)
        sha256 = (
            result.sha256
            if result is not None and result.sha256 is not None
            else previous.sha256 if previous is not None else ""
        )
        if not sha256:
            raise WorkspaceChangedError()
        scanned_files.append(
            ScannedFile(
                path=path,
                absolute_path=observation.absolute_path,
                language=observation.language,
                sha256=sha256,
                size=observation.size,
                mtime_ns=observation.mtime_ns,
                is_test=is_test_path(
                    path,
                    observation.language,
                    _project_unit_key(unit_by_path[path]),
                ),
            )
        )
    scanned_files = _canonical_scanned_files(scanned_files)
    rebuild_paths = content_paths | dependent_paths
    prepared_files = tuple(
        _prepare_v5_file(
            repo=repo,
            scanned_file=scanned,
            project_unit=unit_by_path[scanned.path],
            plugins=graph_plugins,
            repository_path_index=repository_path_index,
            file_reader=read_scanned_file_bytes,
            max_file_bytes=config.index.max_file_bytes,
            content_bytes=bodies[scanned.path],
        )
        for scanned in scanned_files
        if scanned.path in rebuild_paths
    )
    _fault(fault_hook, "preparation_complete")

    prepared_by_path = {
        item.source_file.path: item for item in prepared_files
    }
    vector_rebuild_paths = set(content_paths)
    removed_embedding_ids = store.active_embedding_ids_for_files(
        vector_rebuild_paths | deleted_paths
    )
    embedding_chunks = tuple(
        chunk
        for path in sorted(vector_rebuild_paths, key=lambda item: item.as_posix())
        for chunk in prepared_by_path[path].chunks
    )
    expected_vector_ids = set(baseline.operational.active_embedding_ids)
    expected_vector_ids -= removed_embedding_ids
    expected_vector_ids.update(
        chunk.embedding_id or chunk.chunk_id for chunk in embedding_chunks
    )
    vector_changed = bool(removed_embedding_ids or embedding_chunks)
    frozen_vectors: FrozenVectorGeneration | None = None
    if vector_changed:
        try:
            loaded_descriptor, vector_store = NumpyVectorStore.load_published_snapshot(
                index_dir,
                expected_embedding_identity=embedding_identity,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise _AuthoritativeRefreshRequired() from error
        if (
            loaded_descriptor != baseline.descriptor.descriptor
            or vector_store.ids
            != tuple(sorted(baseline.operational.active_embedding_ids))
        ):
            raise _AuthoritativeRefreshRequired()
        vector_store.remove_many(sorted(removed_embedding_ids))
        if embedding_chunks:
            provider = embedding_provider or provider_from_config(config.embedding)
            _validate_embedding_provider(provider, config)
            tracker.request_started()
            vectors = provider.embed_texts(
                [_embedding_text_for_chunk(chunk) for chunk in embedding_chunks]
            )
            tracker.response_received()
            if len(vectors) != len(embedding_chunks):
                raise ValueError("embedding response count mismatch")
            vector_store.upsert_many(
                [
                    (chunk.embedding_id or chunk.chunk_id, vector)
                    for chunk, vector in zip(embedding_chunks, vectors)
                ]
            )
        _fault(fault_hook, "embedding_complete")
        vector_store.sort_by_id()
        if vector_store.ids != tuple(sorted(expected_vector_ids)):
            raise GraphIntegrityError("prepared vector ID set mismatch")
        frozen_vectors = vector_store.freeze_generation_v2(
            generation=uuid.uuid4().hex,
            embedding_identity=embedding_identity,
            normalization="none",
        )
        prepared_vectors = PreparedVectorGeneration(
            index_dir,
            frozen_vectors.descriptor,
        )
        descriptor_snapshot = NumpyVectorStore.prepared_descriptor_snapshot(
            prepared_vectors
        )
        publish_descriptor = True
        descriptor_action = "published"
    else:
        prepared_vectors = PreparedVectorGeneration(
            index_dir,
            baseline.descriptor.descriptor,
        )
        descriptor_snapshot = baseline.descriptor
        publish_descriptor = False
        descriptor_action = "reused"

    closing = inventory_observer(repo, config)
    if not closing.complete:
        raise WorkspaceChangedError()
    if workspace_inventory_identity(opening) != workspace_inventory_identity(closing):
        raise WorkspaceChangedError()
    observation_completed = time.time_ns() // 1_000_000
    _fault(fault_hook, "closing_inventory_complete")

    observation_generation = baseline.operational.binding.observation_generation + 1
    source_observations = _quick_source_observations(
        tuple(scanned_files),
        eligible,
        observation_generation,
    )
    deferred_skips = tuple(
        CoverageSkipObservation(
            path=path,
            language=eligible[path].language,
            reason=prior_skips[path].reason,
            retryable=True,
            metadata=eligible[path].metadata,
        )
        for path in sorted(deferred_retry_paths, key=lambda item: item.as_posix())
    )
    scan_skips = _quick_scan_skips(
        (
            *current_inventory_skips.values(),
            *read_skips.values(),
            *deferred_skips,
        ),
        generation=observation_generation,
        prior=baseline.operational,
        attempted_paths=selected_retry_paths,
    )
    controls = _operational_control_observations(opening, observation_generation)
    content_fingerprint = operational_content_fingerprint(source_observations)
    observation_fingerprint = operational_observation_fingerprint(
        source_observations,
        scan_skips,
        controls,
    )
    manifest_generation = f"manifest-{uuid.uuid4().hex}"
    read_bytes = sum(
        int(result.size or 0)
        for result in read_results.values()
        if result.status == "read"
    )
    dependency_counts = _dependent_rebuild_counts(dependency_reasons)
    vector_bytes = (
        len(frozen_vectors.vectors_payload) + len(frozen_vectors.ids_payload)
        if frozen_vectors is not None
        else 0
    )
    prior_vector_bytes = (
        int(baseline.descriptor.descriptor.vectors_bytes or 0)
        + int(baseline.descriptor.descriptor.ids_bytes or 0)
        if vector_changed
        else 0
    )
    summary = RefreshSummaryV1(
        operation="quick_refresh",
        outcome="ready",
        verification="metadata",
        observation_generation=manifest_generation,
        files=RefreshFileCounts(
            direct_dirty=len(direct_paths),
            content_changed=len(content_paths),
            metadata_only=len(metadata_only_paths),
            dependent_rebuild=len(dependent_paths),
            dependent_rebuilds=dependency_counts,
            deleted=len(deleted_paths),
            coverage_skips=len(scan_skips),
            parsed=len(prepared_files),
        ),
        chunks=RefreshChunkCounts(embedded=len(embedding_chunks)),
        work=RefreshWorkCounts(
            inventory=RefreshInventoryWork(
                entries=_inventory_entry_count(opening)
                + _inventory_entry_count(closing),
                retryable_skip_attempts=len(selected_retry_paths),
            ),
            source=RefreshSourceWork(
                bytes_read=read_bytes,
                bytes_hashed=read_bytes,
            ),
            path_index=RefreshPathIndexWork(
                builds=1,
                paths_canonicalized=len(active_paths),
            ),
            vector=RefreshVectorWork(
                bytes_read=prior_vector_bytes,
                bytes_written=vector_bytes,
                bytes_hashed=prior_vector_bytes,
                payload_passes=int(vector_changed) + int(frozen_vectors is not None),
                prior_payload_passes=int(vector_changed),
                prepared_payload_passes=int(frozen_vectors is not None),
                generations_before=generations_before,
                generations_after=1,
                descriptor_action=descriptor_action,
            ),
            maintenance=RefreshMaintenanceWork(
                tombstones_before=tombstones_before,
                tombstones_after=tombstones_before,
                sqlite_pages_before=pages_before,
                sqlite_pages_after=pages_before,
                sqlite_freelist_before=freelist_before,
                sqlite_freelist_after=freelist_before,
            ),
        ),
    )
    work_metrics = _refresh_manifest_work_metrics(summary)
    descriptor = descriptor_snapshot.descriptor
    if descriptor.vectors_bytes is None or descriptor.ids_bytes is None:
        raise _AuthoritativeRefreshRequired()
    manifest = ManifestV2(
        embedding_config_hash=embedding_identity,
        embedding_provider=config.embedding.provider,
        embedding_model=config.embedding.model,
        embedding_dimensions=config.embedding.dimensions,
        index_config_hash=effective_index_hash,
        source_content_fingerprint=content_fingerprint,
        source_observation_fingerprint=observation_fingerprint,
        observation_generation=observation_generation,
        manifest_generation=manifest_generation,
        vector_descriptor_schema_version=descriptor.schema_version,
        vector_generation=descriptor.generation,
        vector_descriptor_sha256=descriptor_snapshot.sha256,
        vector_bytes=descriptor.vectors_bytes,
        vector_ids_bytes=descriptor.ids_bytes,
        indexed_at_epoch_s=observation_completed // 1_000,
        operational_schema_version=1,
        operation_mode="quick_refresh",
        work_metrics=work_metrics,
        total_files=len(scanned_files),
        total_chunks=len(expected_vector_ids),
    )
    prepared_manifest = prepare_manifest_v2(manifest)
    stale_reason = (
        "topology_changed"
        if topology_changed
        else "path_inventory_changed"
        if path_inventory_changed
        else "files_changed"
        if content_paths or metadata_only_paths or scan_skips
        else "stale_on_entry"
    )
    prepared = PreparedIndexSnapshot(
        effective_config=config,
        effective_config_payload=render_config(config).encode("utf-8"),
        index_config_hash=effective_index_hash,
        opening_inventory=opening,
        closing_inventory=closing,
        observation_started_at_epoch_ms=observation_started,
        observation_completed_at_epoch_ms=observation_completed,
        observation_generation=observation_generation,
        source_observations=source_observations,
        scan_skips=scan_skips,
        control_observations=controls,
        source_content_fingerprint=content_fingerprint,
        source_observation_fingerprint=observation_fingerprint,
        scanned_files=tuple(scanned_files),
        repository_path_index=repository_path_index,
        prepared_files=prepared_files,
        deleted_paths=tuple(sorted(deleted_paths, key=lambda item: item.as_posix())),
        project_units=project_units,
        topology_fingerprint=topology_fingerprint,
        expected_vector_ids=tuple(sorted(expected_vector_ids)),
        frozen_vector_generation=frozen_vectors,
        prepared_vector_generation=prepared_vectors,
        vector_descriptor_snapshot=descriptor_snapshot,
        publish_vector_descriptor=publish_descriptor,
        prepared_manifest=prepared_manifest,
        work_metrics=work_metrics,
        stale_reason=stale_reason,
        force_full_reindex=False,
        stored_signal_version=TARGET_SIGNAL_SCHEMA_VERSION,
        suppress_fault_hooks=False,
        summary=IndexSummary(
            files_seen=len(scanned_files),
            files_indexed=len(prepared_files),
            files_skipped=len(scanned_files) - len(prepared_files),
            files_deleted=len(deleted_paths),
            chunks_indexed=len(embedding_chunks),
        ),
    )
    persistence = _persist_prepared_index(
        repo=repo,
        store=store,
        prepared=prepared,
        fault_hook=fault_hook,
    )
    pages_after, freelist_after = store.storage_page_metrics()
    tombstones_after = store.tombstone_count()
    generations_after = NumpyVectorStore.generation_pair_count(index_dir)
    summary = replace(
        summary,
        work=replace(
            summary.work,
            graph=RefreshGraphWork(
                relations_scanned=persistence.relations_resolved,
                relations_resolved=persistence.relations_resolved,
                association_inputs=persistence.association_writes,
                association_writes=persistence.association_writes,
            ),
            vector=replace(
                summary.work.vector,
                generations_after=generations_after,
            ),
            maintenance=RefreshMaintenanceWork(
                tombstones_before=tombstones_before,
                tombstones_purged=persistence.tombstones_purged,
                tombstones_after=tombstones_after,
                sqlite_pages_before=pages_before,
                sqlite_pages_after=pages_after,
                sqlite_freelist_before=freelist_before,
                sqlite_freelist_after=freelist_after,
            ),
        ),
    )
    _validate_refresh_summary(summary)
    return RefreshSuccess(
        summary=summary,
        indexed_before=indexed_before,
        configured=configured,
        network_egress_performed=tracker.outcome == "performed",
    )


def _load_quick_baseline(repo: Path, store: SQLiteStore) -> _QuickBaseline:
    try:
        loaded = load_manifest_snapshot(repo)
        if not isinstance(loaded.manifest, ManifestV2):
            raise _AuthoritativeRefreshRequired()
        if store.inspect_signal_schema_version() != TARGET_SIGNAL_SCHEMA_VERSION:
            raise _AuthoritativeRefreshRequired()
        operational = store.read_operational_snapshot()
        if operational is None:
            raise _AuthoritativeRefreshRequired()
        graph = read_graph_capability(store)
        if graph.full_reindex_required:
            raise _AuthoritativeRefreshRequired()
        if graph.status == "stale" and graph.stale_reason not in (
            _QUICK_ALLOWED_STALE_REASONS
        ):
            raise _AuthoritativeRefreshRequired()
        if graph.status not in {"ready", "stale"}:
            raise _AuthoritativeRefreshRequired()
        descriptor = NumpyVectorStore.inspect_published_descriptor(
            repo / ".context-search"
        )
        if descriptor is None:
            raise _AuthoritativeRefreshRequired()
        topology = store.get_metadata(PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY)
        if topology is None or len(topology) != 64:
            raise _AuthoritativeRefreshRequired()
        manifest = loaded.manifest
        if (
            _bound_v2_identity_failed(
                loaded,
                operational,
                descriptor,
                entry_state=graph.status,
            )
            or manifest.total_files != operational.source_count
            or manifest.total_chunks != operational.chunk_count
            or descriptor.descriptor.schema_version != 2
            or descriptor.descriptor.dimensions != manifest.embedding_dimensions
            or descriptor.descriptor.row_count
            != len(operational.active_embedding_ids)
            or descriptor.descriptor.embedding_identity
            not in {
                manifest.embedding_config_hash,
                f"{manifest.embedding_model}:{manifest.embedding_dimensions}",
            }
            or not project_scope_metadata_is_current(store)
            or store.get_metadata(FILE_WRITE_IN_PROGRESS_KEY) not in {None, ""}
        ):
            raise _AuthoritativeRefreshRequired()
    except (
        GraphIntegrityError,
        OperationalIntegrityError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        if isinstance(
            error,
            (
                IncompatibleManifestSchemaError,
                IncompatibleOperationalSchemaError,
                IncompatibleSignalSchemaError,
                _AuthoritativeRefreshRequired,
            ),
        ):
            raise
        raise _AuthoritativeRefreshRequired() from error
    return _QuickBaseline(
        loaded_manifest=loaded,
        manifest=manifest,
        operational=operational,
        descriptor=descriptor,
        topology_fingerprint=topology,
        graph_status=graph.status,
        graph_stale_reason=graph.stale_reason,
    )


def _quick_noop_summary(
    *,
    baseline: _QuickBaseline,
    opening: WorkspaceInventory,
    closing: WorkspaceInventory,
    generations_before: int,
    generations_after: int,
    tombstones: int,
    pages_before: int,
    pages_after: int,
    freelist_before: int,
    freelist_after: int,
) -> RefreshSummaryV1:
    summary = RefreshSummaryV1(
        operation="quick_refresh",
        outcome="ready",
        verification="metadata",
        observation_generation=baseline.manifest.manifest_generation,
        files=RefreshFileCounts(
            coverage_skips=len(baseline.operational.scan_skips),
        ),
        chunks=RefreshChunkCounts(),
        work=RefreshWorkCounts(
            inventory=RefreshInventoryWork(
                entries=_inventory_entry_count(opening)
                + _inventory_entry_count(closing),
            ),
            vector=RefreshVectorWork(
                generations_before=generations_before,
                generations_after=generations_after,
            ),
            maintenance=RefreshMaintenanceWork(
                tombstones_before=tombstones,
                tombstones_after=tombstones,
                sqlite_pages_before=pages_before,
                sqlite_pages_after=pages_after,
                sqlite_freelist_before=freelist_before,
                sqlite_freelist_after=freelist_after,
            ),
        ),
    )
    _validate_refresh_summary(summary)
    return summary


def _quick_inventory_matches_snapshot(
    inventory: WorkspaceInventory,
    operational: OperationalSnapshot,
    effective_index_hash: str,
) -> bool:
    if (
        operational.binding.index_config_hash != effective_index_hash
        or not inventory.complete
    ):
        return False
    eligible = {item.path: item for item in inventory.eligible}
    sources = {item.path: item for item in operational.source_observations}
    if set(eligible) != set(sources):
        return False
    if any(
        not _observation_matches_source(eligible[path], sources[path])
        for path in eligible
    ):
        return False
    controls = {Path(item.path): item for item in inventory.control_observations}
    persisted_controls = {
        item.path: item for item in operational.control_observations
    }
    if set(controls) != set(persisted_controls):
        return False
    if any(
        path != Path(".context-search/config.toml")
        and (
            controls[path].sha256,
            controls[path].metadata.size,
            controls[path].metadata.mtime_ns,
            controls[path].metadata.change_token,
            controls[path].metadata.change_token_kind,
        )
        != (
            persisted_controls[path].sha256,
            persisted_controls[path].size,
            persisted_controls[path].mtime_ns,
            persisted_controls[path].change_token,
            persisted_controls[path].change_token_kind,
        )
        for path in controls
    ):
        return False
    skips = {item.path: item for item in inventory.coverage_skips}
    persisted_skips = {item.path: item for item in operational.scan_skips}
    if set(skips) != set(persisted_skips):
        return False
    return all(
        _coverage_skip_matches(skips[path], persisted_skips[path])
        for path in skips
    )


def _observation_matches_source(
    observed: Any,
    persisted: OperationalSourceObservation,
) -> bool:
    return (
        observed.language,
        observed.size,
        observed.mtime_ns,
        observed.change_token,
        observed.change_token_kind,
    ) == (
        persisted.language,
        persisted.size,
        persisted.mtime_ns,
        persisted.change_token,
        persisted.change_token_kind,
    )


def _coverage_skip_matches(
    observed: CoverageSkipObservation,
    persisted: OperationalScanSkip,
) -> bool:
    metadata = observed.metadata
    return (
        observed.reason,
        observed.language or None,
        observed.retryable,
        metadata.size if metadata is not None else None,
        metadata.mtime_ns if metadata is not None else None,
        metadata.change_token if metadata is not None else None,
        metadata.change_token_kind if metadata is not None else "unavailable",
    ) == (
        persisted.reason,
        persisted.language,
        persisted.retryable,
        persisted.size,
        persisted.mtime_ns,
        persisted.change_token,
        persisted.change_token_kind,
    )


def _retryable_skip_order(item: OperationalScanSkip) -> tuple[Any, ...]:
    return (
        item.last_retry_generation is not None,
        item.last_retry_generation if item.last_retry_generation is not None else -1,
        item.first_observation_generation,
        item.path.as_posix(),
    )


def _successful_observed_read(result: ObservedFileRead) -> bool:
    return all(
        (
            result.status == "read",
            result.content is not None,
            result.sha256 is not None,
            result.size is not None,
            result.metadata is not None,
        )
    )


def _coverage_skip_from_read(
    observation: Any,
    result: ObservedFileRead,
) -> CoverageSkipObservation:
    return CoverageSkipObservation(
        path=observation.path,
        language=observation.language,
        reason=result.reason or "unreadable",
        retryable=result.retryable,
        metadata=result.metadata or observation.metadata,
    )


def _quick_source_observations(
    scanned_files: tuple[ScannedFile, ...],
    observations: dict[Path, Any],
    generation: int,
) -> tuple[OperationalSourceObservation, ...]:
    return tuple(
        OperationalSourceObservation(
            path=item.path,
            language=item.language,
            sha256=item.sha256,
            size=item.size,
            mtime_ns=observations[item.path].mtime_ns,
            change_token=observations[item.path].change_token,
            change_token_kind=observations[item.path].change_token_kind,
            observation_generation=generation,
        )
        for item in scanned_files
    )


def _quick_scan_skips(
    skips: Iterable[CoverageSkipObservation],
    *,
    generation: int,
    prior: OperationalSnapshot,
    attempted_paths: set[Path],
) -> tuple[OperationalScanSkip, ...]:
    previous = {item.path: item for item in prior.scan_skips}
    by_path = {item.path: item for item in skips}
    prepared: list[OperationalScanSkip] = []
    for path, item in sorted(by_path.items(), key=lambda pair: pair[0].as_posix()):
        old = previous.get(path)
        metadata = item.metadata
        prepared.append(
            OperationalScanSkip(
                path=path,
                reason=item.reason,
                language=item.language or None,
                size=metadata.size if metadata is not None else None,
                mtime_ns=metadata.mtime_ns if metadata is not None else None,
                change_token=metadata.change_token if metadata is not None else None,
                change_token_kind=(
                    metadata.change_token_kind
                    if metadata is not None
                    else "unavailable"
                ),
                retryable=item.retryable,
                first_observation_generation=(
                    old.first_observation_generation if old is not None else generation
                ),
                last_observation_generation=generation,
                last_retry_generation=(
                    generation
                    if path in attempted_paths
                    else old.last_retry_generation if old is not None else None
                ),
                metadata=old.metadata if old is not None else (),
            )
        )
    return tuple(prepared)


def _dependent_rebuild_counts(
    reasons: dict[Path, set[str]],
) -> tuple[DependentRebuildCount, ...]:
    counts = {reason: 0 for reason in _DEPENDENT_REASON_ORDER}
    for values in reasons.values():
        selected = min(values, key=_DEPENDENT_REASON_ORDER.index)
        counts[selected] += 1
    return tuple(
        DependentRebuildCount(reason=reason, files=counts[reason])
        for reason in _DEPENDENT_REASON_ORDER
        if counts[reason]
    )


def _inventory_entry_count(inventory: WorkspaceInventory) -> int:
    return len(inventory.eligible) + len(inventory.coverage_skips)


def _refresh_manifest_work_metrics(
    summary: RefreshSummaryV1,
) -> tuple[tuple[str, int | str], ...]:
    return tuple(
        sorted(
            {
                "chunks.embedded": summary.chunks.embedded,
                "files.content_changed": summary.files.content_changed,
                "files.deleted": summary.files.deleted,
                "files.dependent_rebuild": summary.files.dependent_rebuild,
                "files.direct_dirty": summary.files.direct_dirty,
                "files.metadata_only": summary.files.metadata_only,
                "files.parsed": summary.files.parsed,
                "inventory.entries": summary.work.inventory.entries,
                "inventory.passes": summary.work.inventory.passes,
                "source.bytes_hashed": summary.work.source.bytes_hashed,
                "source.bytes_read": summary.work.source.bytes_read,
                "vector.bytes_read": summary.work.vector.bytes_read,
                "vector.bytes_written": summary.work.vector.bytes_written,
                "vector.descriptor_action": summary.work.vector.descriptor_action,
            }.items()
        )
    )


def _validate_refresh_summary(summary: RefreshSummaryV1) -> None:
    if (
        summary.operation != "quick_refresh"
        or summary.outcome != "ready"
        or summary.verification != "metadata"
        or not summary.observation_generation
    ):
        raise ValueError("invalid refresh summary identity")
    rendered = asdict(summary)
    stack: list[Any] = [rendered]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend(value)
        elif type(value) is int and value < 0:
            raise ValueError("refresh work counts must be non-negative")
    if summary.files.dependent_rebuild != sum(
        item.files for item in summary.files.dependent_rebuilds
    ):
        raise ValueError("dependent rebuild count mismatch")
    vector = summary.work.vector
    if vector.descriptor_action not in {"reused", "published"}:
        raise ValueError("invalid vector descriptor action")
    if vector.payload_passes != (
        vector.prior_payload_passes + vector.prepared_payload_passes
    ):
        raise ValueError("vector payload pass accounting mismatch")
    if vector.bytes_hashed > vector.bytes_read:
        raise ValueError("vector hash bytes exceed vector read bytes")


def _require_authoritative_schema_compatibility(
    repo: Path,
    store: SQLiteStore,
    stored_version: int,
) -> None:
    raw_manifest = inspect_raw_manifest_schema(repo)
    if (
        raw_manifest.status == "valid"
        and raw_manifest.version is not None
        and raw_manifest.version > 2
    ):
        raise IncompatibleManifestSchemaError(raw_manifest.version)
    if stored_version > TARGET_SIGNAL_SCHEMA_VERSION:
        raise IncompatibleSignalSchemaError(stored_version)
    if stored_version:
        read_operational_capability(store)


def _freeze_effective_config(config: ToolConfig) -> ToolConfig:
    if not isinstance(config, ToolConfig):
        raise ValueError("config loader returned an invalid configuration")
    return replace(
        config,
        index=replace(
            config.index,
            include=tuple(config.index.include),  # type: ignore[arg-type]
            exclude=tuple(config.index.exclude),  # type: ignore[arg-type]
        ),
    )


def _load_authoritative_manifest(
    repo: Path,
    config: ToolConfig,
) -> tuple[LoadedManifestSnapshot | None, bool]:
    path = repo / ".context-search" / "manifest.json"
    if not os.path.lexists(path):
        return None, False
    try:
        loaded = load_manifest_snapshot(repo)
    except IncompatibleManifestSchemaError:
        raise
    except (OSError, ValueError):
        return None, True
    if loaded.manifest.embedding_config_hash != embedding_config_hash(config.embedding):
        raise IncompatibleIndexError(
            "incompatible embedding configuration for existing index"
        )
    return loaded, False


def _initialize_index_controls(
    repo: Path,
    config: ToolConfig,
    *,
    overwrite_config: bool,
) -> None:
    ensure_index_gitignore_entry(repo)
    path = repo / ".context-search" / "config.toml"
    if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
        raise ValueError("config must be a regular non-symlink file")
    payload = render_config(config).encode("utf-8")
    if not path.exists() or (overwrite_config and path.read_bytes() != payload):
        atomic_write_index_bytes(
            path,
            payload,
            fault_prefix="config_initialize",
        )


def _prepare_authoritative_index(
    *,
    repo: Path,
    store: SQLiteStore,
    stored_version: int,
    config: ToolConfig,
    graph_plugins: tuple[GraphLanguagePlugin, ...],
    file_reader: Callable[..., bytes],
    inventory_observer: Callable[[Path, ToolConfig], WorkspaceInventory],
    observed_reader: Callable[..., ObservedFileRead],
    embedding_provider: EmbeddingProvider | None,
    loaded_manifest: LoadedManifestSnapshot | None,
    manifest_integrity_failed: bool,
    fault_hook: Callable[[str], None] | None,
) -> PreparedIndexSnapshot:
    observation_started = time.time_ns() // 1_000_000
    existing_files = {
        source.path: source for source in store.source_files_snapshot()
    }
    persisted_paths = store.persisted_file_paths_snapshot()

    entry_state = "legacy"
    entry_full_reindex = stored_version < TARGET_SIGNAL_SCHEMA_VERSION
    stored_topology: str | None = None
    operational_snapshot: OperationalSnapshot | None = None
    operational_integrity_failed = False
    if stored_version == TARGET_SIGNAL_SCHEMA_VERSION:
        capability = read_graph_capability(store)
        entry_state = capability.status
        entry_full_reindex = capability.full_reindex_required
        stored_topology = store.get_metadata(
            PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY
        )
        try:
            if read_operational_capability(store).status == "current":
                operational_snapshot = store.read_operational_snapshot()
        except (OperationalIntegrityError, ValueError):
            operational_integrity_failed = True

    embedding_identity = embedding_config_hash(config.embedding)
    effective_index_hash = index_config_hash(config)
    existing_ids = (
        store.active_embedding_ids()
        if stored_version == TARGET_SIGNAL_SCHEMA_VERSION
        else set()
    )
    vector_snapshot_valid = False
    current_vector_store: NumpyVectorStore | None = None
    current_descriptor: PublishedVectorDescriptor | None = None
    if stored_version == TARGET_SIGNAL_SCHEMA_VERSION and not entry_full_reindex:
        try:
            descriptor, current_vector_store = (
                NumpyVectorStore.load_published_snapshot(
                    repo / ".context-search",
                    expected_embedding_identity=embedding_identity,
                )
            )
            current_descriptor = NumpyVectorStore.inspect_published_descriptor(
                repo / ".context-search"
            )
            if descriptor is None or current_descriptor is None:
                raise ValueError("published vector descriptor is missing")
            if descriptor != current_descriptor.descriptor:
                raise ValueError("vector descriptor changed during validation")
            if descriptor.dimensions != config.embedding.dimensions:
                raise ValueError("vector generation dimensions mismatch")
            if current_vector_store.ids != tuple(sorted(existing_ids)):
                raise ValueError("vector snapshot IDs do not match SQLite")
            vector_snapshot_valid = True
        except (OSError, RuntimeError, ValueError):
            vector_snapshot_valid = False
            current_vector_store = None
            current_descriptor = None

    binding_integrity_failed = _bound_v2_identity_failed(
        loaded_manifest,
        operational_snapshot,
        current_descriptor,
        entry_state=entry_state,
    )
    opening_inventory = inventory_observer(repo, config)
    quiet_candidate = _opening_matches_operational_snapshot(
        opening_inventory,
        operational_snapshot,
        effective_index_hash,
    )
    preparation_fault_hook = None if quiet_candidate else fault_hook
    _fault(preparation_fault_hook, "opening_inventory_complete")
    if not opening_inventory.complete:
        raise InventoryIncompleteError()

    bodies: dict[Path, bytes] = {}
    read_results: dict[Path, ObservedFileRead] = {}
    read_skips: list[CoverageSkipObservation] = []
    read_interrupted = False
    for observation in opening_inventory.eligible:
        result = observed_reader(
            repo,
            observation,
            max_file_bytes=config.index.max_file_bytes,
            require_utf8=False,
        )
        read_results[observation.path] = result
        _fault(preparation_fault_hook, "source_read_complete")
        if (
            result.status == "read"
            and result.content is not None
            and result.sha256 is not None
            and result.size is not None
            and result.metadata is not None
        ):
            bodies[observation.path] = result.content
        else:
            if result.reason == "changed_during_read":
                read_interrupted = True
            read_skips.append(
                CoverageSkipObservation(
                    path=observation.path,
                    language=observation.language,
                    reason=result.reason or "unreadable",
                    retryable=result.retryable,
                    metadata=result.metadata,
                )
            )

    observations_by_path = {
        item.path: item for item in opening_inventory.eligible
    }
    scanned_files = _canonical_scanned_files(
        ScannedFile(
            path=path,
            absolute_path=observations_by_path[path].absolute_path,
            language=observations_by_path[path].language,
            sha256=read_results[path].sha256 or "",
            size=read_results[path].size or 0,
            mtime_ns=(
                read_results[path].metadata.mtime_ns
                if read_results[path].metadata is not None
                else observations_by_path[path].mtime_ns
            ),
            is_test=observations_by_path[path].is_test,
        )
        for path in bodies
    )
    scanned_paths = {scanned.path for scanned in scanned_files}
    deleted_paths = persisted_paths - scanned_paths
    path_inventory_changed = scanned_paths != persisted_paths

    project_units = detect_project_units(
        repo,
        [scanned.path for scanned in scanned_files],
    )
    topology_fingerprint = project_unit_topology_fingerprint(project_units)
    unit_by_path = {
        scanned.path: unit_for_path(scanned.path, project_units)
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
    topology_changed = (
        stored_version == TARGET_SIGNAL_SCHEMA_VERSION
        and stored_topology != topology_fingerprint
    )
    project_scope_metadata_current = (
        stored_version < TARGET_SIGNAL_SCHEMA_VERSION
        or project_scope_metadata_is_current(store)
    )

    no_file_changes = not changed_paths and not deleted_paths
    graph_integrity_failed = False
    if (
        stored_version == TARGET_SIGNAL_SCHEMA_VERSION
        and entry_state == "ready"
        and not entry_full_reindex
        and vector_snapshot_valid
        and no_file_changes
        and not topology_changed
        and project_scope_metadata_current
    ):
        try:
            stats = store.stats()
            store.validate_ready_v5_snapshot(
                topology_fingerprint=topology_fingerprint,
                expected_embedding_ids=existing_ids,
                expected_source_count=len(scanned_files),
                expected_chunk_count=stats["active_chunks"],
                external_validator=lambda: None,
            )
        except (GraphIntegrityError, OSError, ValueError):
            graph_integrity_failed = True

    force_full_reindex = (
        stored_version < TARGET_SIGNAL_SCHEMA_VERSION
        or entry_full_reindex
        or not vector_snapshot_valid
        or graph_integrity_failed
        or manifest_integrity_failed
        or operational_integrity_failed
        or binding_integrity_failed
        or not project_scope_metadata_current
    )
    stale_reason = _authoritative_stale_reason(
        stored_version=stored_version,
        entry_full_reindex=entry_full_reindex,
        integrity_failed=(
            graph_integrity_failed
            or manifest_integrity_failed
            or operational_integrity_failed
            or binding_integrity_failed
            or not vector_snapshot_valid
        ),
        topology_changed=topology_changed,
        project_scope_metadata_current=project_scope_metadata_current,
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
    )

    rebuild_paths = set(changed_paths)
    if force_full_reindex:
        rebuild_paths = set(scanned_paths)
    elif entry_state == "stale" or topology_changed or graph_integrity_failed:
        rebuild_paths.update(
            scanned.path for scanned in scanned_files if scanned.size > 0
        )
    elif path_inventory_changed and stored_version == TARGET_SIGNAL_SCHEMA_VERSION:
        rebuild_paths.update(
            store.active_relation_source_paths(
                _PATH_INVENTORY_RELATION_KINDS
            )
            & scanned_paths
        )

    active_paths = tuple(scanned.path for scanned in scanned_files)
    active_path_units = tuple(
        (
            scanned.path,
            _project_unit_key(unit_by_path[scanned.path]),
        )
        for scanned in scanned_files
    )
    repository_path_index = RepositoryPathIndex(active_paths, active_path_units)
    prepared_files = tuple(
        _prepare_v5_file(
            repo=repo,
            scanned_file=scanned,
            project_unit=unit_by_path[scanned.path],
            plugins=graph_plugins,
            repository_path_index=repository_path_index,
            file_reader=file_reader,
            max_file_bytes=config.index.max_file_bytes,
            content_bytes=(
                bodies[scanned.path]
                if file_reader is read_scanned_file_bytes
                else None
            ),
        )
        for scanned in scanned_files
        if scanned.path in rebuild_paths
    )
    _fault(preparation_fault_hook, "preparation_complete")

    prepared_by_path = {
        prepared.source_file.path: prepared for prepared in prepared_files
    }
    vector_rebuild_paths = {
        path
        for path in rebuild_paths
        if (
            force_full_reindex
            or existing_files.get(path) is None
            or existing_files[path].sha256 != prepared_by_path[path].source_file.sha256
            or existing_files[path].language != prepared_by_path[path].source_file.language
        )
    }
    if not force_full_reindex and stored_version == TARGET_SIGNAL_SCHEMA_VERSION:
        for path, prepared_file in prepared_by_path.items():
            if path in vector_rebuild_paths:
                continue
            previous = store.active_embedding_ids_for_files({path})
            current = {
                chunk.embedding_id or chunk.chunk_id
                for chunk in prepared_file.chunks
            }
            if previous != current:
                vector_rebuild_paths.add(path)

    vector_removed_paths = vector_rebuild_paths | deleted_paths
    removed_embedding_ids = (
        store.active_embedding_ids_for_files(vector_removed_paths)
        if stored_version == TARGET_SIGNAL_SCHEMA_VERSION
        else set()
    )
    if force_full_reindex:
        vector_store = NumpyVectorStore.fresh(
            repo / ".context-search",
            dimensions=config.embedding.dimensions,
        )
        expected_vector_ids: set[str] = set()
    else:
        if current_vector_store is None:
            raise GraphIntegrityError("validated vector snapshot is unavailable")
        vector_store = current_vector_store
        expected_vector_ids = set(vector_store.ids)
        vector_store.remove_many(sorted(removed_embedding_ids))
        expected_vector_ids -= removed_embedding_ids

    embedding_chunks = tuple(
        chunk
        for path in sorted(vector_rebuild_paths, key=lambda item: item.as_posix())
        for chunk in prepared_by_path[path].chunks
    )
    if embedding_chunks:
        provider = embedding_provider or provider_from_config(config.embedding)
        _validate_embedding_provider(provider, config)
        vectors = provider.embed_texts(
            [_embedding_text_for_chunk(chunk) for chunk in embedding_chunks]
        )
        if len(vectors) != len(embedding_chunks):
            raise ValueError("embedding response count mismatch")
        vector_store.upsert_many(
            [
                (chunk.embedding_id or chunk.chunk_id, vector)
                for chunk, vector in zip(embedding_chunks, vectors)
            ]
        )
    _fault(preparation_fault_hook, "embedding_complete")
    expected_vector_ids.update(
        chunk.embedding_id or chunk.chunk_id for chunk in embedding_chunks
    )
    vector_store.sort_by_id()
    if vector_store.ids != tuple(sorted(expected_vector_ids)):
        raise GraphIntegrityError("prepared vector ID set mismatch")

    vector_changed = bool(
        force_full_reindex or vector_rebuild_paths or deleted_paths
    )
    frozen_vectors: FrozenVectorGeneration | None = None
    publish_vector_descriptor = False
    if (
        not vector_changed
        and current_descriptor is not None
        and current_descriptor.descriptor.schema_version == 2
    ):
        prepared_vectors = PreparedVectorGeneration(
            repo / ".context-search",
            current_descriptor.descriptor,
        )
        descriptor_snapshot = current_descriptor
        descriptor_action = "reused"
    elif not vector_changed and current_descriptor is not None:
        prepared_vectors = NumpyVectorStore.prepare_existing_generation_v2(
            repo / ".context-search",
            expected_embedding_identity=embedding_identity,
            expected_ids=expected_vector_ids,
        )
        descriptor_snapshot = NumpyVectorStore.prepared_descriptor_snapshot(
            prepared_vectors
        )
        publish_vector_descriptor = True
        descriptor_action = "published"
    else:
        frozen_vectors = vector_store.freeze_generation_v2(
            generation=uuid.uuid4().hex,
            embedding_identity=embedding_identity,
            normalization="none",
        )
        prepared_vectors = PreparedVectorGeneration(
            repo / ".context-search",
            frozen_vectors.descriptor,
        )
        descriptor_snapshot = NumpyVectorStore.prepared_descriptor_snapshot(
            prepared_vectors
        )
        publish_vector_descriptor = True
        descriptor_action = "published"

    closing_inventory = inventory_observer(repo, config)
    if not closing_inventory.complete:
        raise InventoryIncompleteError()
    if (
        read_interrupted
        or workspace_inventory_identity(opening_inventory)
        != workspace_inventory_identity(closing_inventory)
    ):
        raise WorkspaceChangedError()
    observation_completed = time.time_ns() // 1_000_000
    _fault(preparation_fault_hook, "closing_inventory_complete")

    observation_generation = (
        operational_snapshot.binding.observation_generation + 1
        if operational_snapshot is not None
        else 1
    )
    source_observations = _operational_source_observations(
        tuple(scanned_files),
        read_results,
        observation_generation,
    )
    scan_skips = _operational_scan_skips(
        (*opening_inventory.coverage_skips, *read_skips),
        observation_generation,
        operational_snapshot,
    )
    control_observations = _operational_control_observations(
        opening_inventory,
        observation_generation,
    )
    content_fingerprint = operational_content_fingerprint(source_observations)
    observation_fingerprint = operational_observation_fingerprint(
        source_observations,
        scan_skips,
        control_observations,
    )
    hashed_results = tuple(
        result
        for result in read_results.values()
        if result.status == "read" and result.size is not None
    )
    work_metrics = tuple(
        sorted(
            {
                "chunks.embedded": len(embedding_chunks),
                "files.parsed": len(prepared_files),
                "path_index.builds": 1,
                "path_index.paths_canonicalized": len(active_paths),
                "source.bytes_hashed": sum(
                    int(result.size or 0) for result in hashed_results
                ),
                "source.files_hashed": len(hashed_results),
                "vector.bytes_written": (
                    int(descriptor_snapshot.descriptor.vectors_bytes or 0)
                    + int(descriptor_snapshot.descriptor.ids_bytes or 0)
                    if frozen_vectors is not None
                    else 0
                ),
                "vector.descriptor_action": descriptor_action,
            }.items()
        )
    )
    descriptor = descriptor_snapshot.descriptor
    if descriptor.vectors_bytes is None or descriptor.ids_bytes is None:
        raise GraphIntegrityError("prepared vector descriptor is not v2")
    manifest = ManifestV2(
        embedding_config_hash=embedding_identity,
        embedding_provider=config.embedding.provider,
        embedding_model=config.embedding.model,
        embedding_dimensions=config.embedding.dimensions,
        index_config_hash=effective_index_hash,
        source_content_fingerprint=content_fingerprint,
        source_observation_fingerprint=observation_fingerprint,
        observation_generation=observation_generation,
        manifest_generation=f"manifest-{uuid.uuid4().hex}",
        vector_descriptor_schema_version=descriptor.schema_version,
        vector_generation=descriptor.generation,
        vector_descriptor_sha256=descriptor_snapshot.sha256,
        vector_bytes=descriptor.vectors_bytes,
        vector_ids_bytes=descriptor.ids_bytes,
        indexed_at_epoch_s=observation_completed // 1_000,
        operational_schema_version=1,
        operation_mode="authoritative_index",
        work_metrics=work_metrics,
        total_files=len(scanned_files),
        total_chunks=len(expected_vector_ids),
    )
    prepared_manifest = prepare_manifest_v2(manifest)
    suppress_fault_hooks = bool(
        quiet_candidate
        and not force_full_reindex
        and not changed_paths
        and not deleted_paths
        and not topology_changed
        and not graph_integrity_failed
        and isinstance(
            loaded_manifest.manifest if loaded_manifest is not None else None,
            ManifestV2,
        )
    )
    summary = IndexSummary(
        files_seen=len(scanned_files),
        files_indexed=len(prepared_files),
        files_skipped=len(scanned_files) - len(prepared_files),
        files_deleted=len(deleted_paths),
        chunks_indexed=len(embedding_chunks),
    )
    return PreparedIndexSnapshot(
        effective_config=config,
        effective_config_payload=render_config(config).encode("utf-8"),
        index_config_hash=effective_index_hash,
        opening_inventory=opening_inventory,
        closing_inventory=closing_inventory,
        observation_started_at_epoch_ms=observation_started,
        observation_completed_at_epoch_ms=observation_completed,
        observation_generation=observation_generation,
        source_observations=source_observations,
        scan_skips=scan_skips,
        control_observations=control_observations,
        source_content_fingerprint=content_fingerprint,
        source_observation_fingerprint=observation_fingerprint,
        scanned_files=tuple(scanned_files),
        repository_path_index=repository_path_index,
        prepared_files=prepared_files,
        deleted_paths=tuple(
            sorted(deleted_paths, key=lambda item: item.as_posix())
        ),
        project_units=project_units,
        topology_fingerprint=topology_fingerprint,
        expected_vector_ids=tuple(sorted(expected_vector_ids)),
        frozen_vector_generation=frozen_vectors,
        prepared_vector_generation=prepared_vectors,
        vector_descriptor_snapshot=descriptor_snapshot,
        publish_vector_descriptor=publish_vector_descriptor,
        prepared_manifest=prepared_manifest,
        work_metrics=prepared_manifest.manifest.work_metrics,
        stale_reason=stale_reason,
        force_full_reindex=force_full_reindex,
        stored_signal_version=stored_version,
        suppress_fault_hooks=suppress_fault_hooks,
        summary=summary,
    )


def _bound_v2_identity_failed(
    loaded_manifest: LoadedManifestSnapshot | None,
    operational: OperationalSnapshot | None,
    descriptor: PublishedVectorDescriptor | None,
    *,
    entry_state: str,
) -> bool:
    if loaded_manifest is None or not isinstance(loaded_manifest.manifest, ManifestV2):
        return False
    if operational is None:
        return entry_state == "ready"
    manifest = loaded_manifest.manifest
    binding = operational.binding
    if descriptor is None:
        return True
    return not all(
        (
            loaded_manifest.sha256 == binding.manifest_sha256,
            manifest.manifest_generation == binding.manifest_generation,
            manifest.index_config_hash == binding.index_config_hash,
            manifest.source_content_fingerprint
            == binding.source_content_fingerprint,
            manifest.source_observation_fingerprint
            == binding.source_observation_fingerprint,
            manifest.observation_generation == binding.observation_generation,
            manifest.vector_generation == binding.vector_generation,
            manifest.vector_descriptor_sha256
            == binding.vector_descriptor_sha256,
            manifest.vector_bytes == binding.vector_bytes,
            manifest.vector_ids_bytes == binding.vector_ids_bytes,
            descriptor.sha256 == binding.vector_descriptor_sha256,
            descriptor.descriptor.generation == binding.vector_generation,
            descriptor.descriptor.vectors_bytes == binding.vector_bytes,
            descriptor.descriptor.ids_bytes == binding.vector_ids_bytes,
        )
    )


def _opening_matches_operational_snapshot(
    inventory: WorkspaceInventory,
    operational: OperationalSnapshot | None,
    effective_index_hash: str,
) -> bool:
    if (
        operational is None
        or operational.graph_status != "ready"
        or operational.binding.index_config_hash != effective_index_hash
        or not inventory.complete
    ):
        return False
    eligible = {item.path: item for item in inventory.eligible}
    if set(eligible) != {item.path for item in operational.source_observations}:
        return False
    for persisted in operational.source_observations:
        observed = eligible[persisted.path]
        if (
            observed.language != persisted.language
            or observed.size != persisted.size
            or observed.mtime_ns != persisted.mtime_ns
            or observed.change_token != persisted.change_token
            or observed.change_token_kind != persisted.change_token_kind
        ):
            return False
    controls = {
        Path(item.path): item for item in inventory.control_observations
    }
    if set(controls) != {item.path for item in operational.control_observations}:
        return False
    for persisted in operational.control_observations:
        observed = controls[persisted.path]
        if (
            observed.sha256 != persisted.sha256
            or observed.metadata.size != persisted.size
            or observed.metadata.mtime_ns != persisted.mtime_ns
            or observed.metadata.change_token != persisted.change_token
            or observed.metadata.change_token_kind != persisted.change_token_kind
        ):
            return False
    return not operational.scan_skips and not inventory.coverage_skips


def _authoritative_stale_reason(
    *,
    stored_version: int,
    entry_full_reindex: bool,
    integrity_failed: bool,
    topology_changed: bool,
    project_scope_metadata_current: bool,
    changed_paths: set[Path],
    deleted_paths: set[Path],
) -> str:
    if stored_version < TARGET_SIGNAL_SCHEMA_VERSION:
        return "schema_migration" if stored_version else "full_reindex"
    if entry_full_reindex:
        return "full_reindex"
    if integrity_failed:
        return "integrity_check_failed"
    if topology_changed:
        return "topology_changed"
    if not project_scope_metadata_current:
        return "project_scope_metadata_changed"
    if changed_paths or deleted_paths:
        return "files_changed"
    return "stale_on_entry"


def _operational_source_observations(
    scanned_files: tuple[ScannedFile, ...],
    results: dict[Path, ObservedFileRead],
    generation: int,
) -> tuple[OperationalSourceObservation, ...]:
    observations: list[OperationalSourceObservation] = []
    for scanned in scanned_files:
        metadata = results[scanned.path].metadata
        if metadata is None:
            raise WorkspaceChangedError()
        observations.append(
            OperationalSourceObservation(
                path=scanned.path,
                language=scanned.language,
                sha256=scanned.sha256,
                size=scanned.size,
                mtime_ns=metadata.mtime_ns,
                change_token=metadata.change_token,
                change_token_kind=metadata.change_token_kind,
                observation_generation=generation,
            )
        )
    return tuple(sorted(observations, key=lambda item: item.path.as_posix()))


def _operational_scan_skips(
    skips: Iterable[CoverageSkipObservation],
    generation: int,
    prior: OperationalSnapshot | None,
) -> tuple[OperationalScanSkip, ...]:
    previous = (
        {item.path: item for item in prior.scan_skips}
        if prior is not None
        else {}
    )
    by_path = {item.path: item for item in skips}
    prepared: list[OperationalScanSkip] = []
    for path, item in sorted(by_path.items(), key=lambda pair: pair[0].as_posix()):
        metadata = item.metadata
        old = previous.get(path)
        prepared.append(
            OperationalScanSkip(
                path=path,
                reason=item.reason,
                language=item.language or None,
                size=metadata.size if metadata is not None else None,
                mtime_ns=metadata.mtime_ns if metadata is not None else None,
                change_token=(
                    metadata.change_token if metadata is not None else None
                ),
                change_token_kind=(
                    metadata.change_token_kind
                    if metadata is not None
                    else "unavailable"
                ),
                retryable=item.retryable,
                first_observation_generation=(
                    old.first_observation_generation
                    if old is not None
                    else generation
                ),
                last_observation_generation=generation,
                last_retry_generation=(
                    old.last_retry_generation if old is not None else None
                ),
            )
        )
    return tuple(prepared)


def _operational_control_observations(
    inventory: WorkspaceInventory,
    generation: int,
) -> tuple[OperationalControlObservation, ...]:
    return tuple(
        OperationalControlObservation(
            path=Path(item.path),
            sha256=item.sha256,
            size=item.metadata.size,
            mtime_ns=item.metadata.mtime_ns,
            change_token=item.metadata.change_token,
            change_token_kind=item.metadata.change_token_kind,
            observation_generation=generation,
        )
        for item in inventory.control_observations
    )


def _persist_prepared_index(
    *,
    repo: Path,
    store: SQLiteStore,
    prepared: PreparedIndexSnapshot,
    fault_hook: Callable[[str], None] | None,
) -> _PersistenceWork:
    active_fault_hook = None if prepared.suppress_fault_hooks else fault_hook
    publisher = NumpyVectorStore.fresh(
        repo / ".context-search",
        dimensions=prepared.effective_config.embedding.dimensions,
    )
    vector_generation = prepared.prepared_vector_generation
    quick_refresh = prepared.prepared_manifest.manifest.operation_mode == "quick_refresh"
    if quick_refresh:
        if prepared.frozen_vector_generation is not None:
            vector_generation = publisher.materialize_frozen_generation(
                prepared.frozen_vector_generation,
                fault_hook=active_fault_hook,
            )
        _fault(active_fault_hook, "vectors_prepared")

    if prepared.stored_signal_version < TARGET_SIGNAL_SCHEMA_VERSION:
        store.initialize_v5(stale_reason=prepared.stale_reason)
    else:
        store.mark_graph_stale(
            prepared.stale_reason,
            full_reindex_required=prepared.force_full_reindex,
        )
    _fault(active_fault_hook, "stale_committed")

    store.initialize_operational_schema_v1(
        before_commit=lambda: _fault(active_fault_hook, "operational_ddl_commit"),
    )
    _fault(active_fault_hook, "operational_ddl_complete")
    store.set_metadata(FILE_WRITE_IN_PROGRESS_KEY, "")

    for item in prepared.prepared_files:
        file_path = item.source_file.path
        store.begin_v5_file_write(file_path)
        _fault(active_fault_hook, "file_write_started")
        store.replace_chunks(file_path, list(item.chunks))
        _fault(active_fault_hook, "chunks_persisted")
        store.replace_signals(file_path, list(item.signals))
        _fault(active_fault_hook, "signals_persisted")
        store.replace_relations(file_path, list(item.relations))
        _fault(active_fault_hook, "producer_relations_persisted")
        store.finish_v5_file_write(item.source_file)
        _fault(active_fault_hook, "source_hash_persisted")

    for path in prepared.deleted_paths:
        store.mark_file_deleted(path)
        _fault(active_fault_hook, "deletion_persisted")

    producer_resolved = resolve_graph_relations(store, association_only=False)
    producer_generation = store.advance_producer_resolution_generation()
    _fault(active_fault_hook, "producer_resolver_complete")
    associations = regenerate_test_associations(
        store,
        producer_resolution_generation=producer_generation,
    )
    _fault(active_fault_hook, "associations_complete")
    association_resolved = resolve_graph_relations(store, association_only=True)
    _fault(active_fault_hook, "association_resolver_complete")

    store.replace_operational_observations(
        observation_generation=prepared.observation_generation,
        source_observations=prepared.source_observations,
        scan_skips=prepared.scan_skips,
        control_observations=prepared.control_observations,
    )
    _fault(active_fault_hook, "operational_observations_persisted")

    if not quick_refresh:
        if prepared.frozen_vector_generation is not None:
            vector_generation = publisher.materialize_frozen_generation(
                prepared.frozen_vector_generation,
                fault_hook=active_fault_hook,
            )
        _fault(active_fault_hook, "vectors_prepared")
    if prepared.publish_vector_descriptor:
        publisher.publish_generation(
            vector_generation,
            fault_hook=active_fault_hook,
        )
        _fault(active_fault_hook, "vector_descriptor_published")
    else:
        _fault(active_fault_hook, "vector_descriptor_reused")

    for stage in (
        "config_temp_write",
        "config_file_fsync",
        "config_rename",
        "config_directory_fsync",
    ):
        _fault(active_fault_hook, stage)
    for stage in (
        "manifest_temp_write",
        "manifest_file_fsync",
        "manifest_rename",
        "manifest_directory_fsync",
    ):
        _fault(active_fault_hook, stage)
    publish_manifest_v2(
        repo,
        prepared.prepared_manifest,
        fault_hook=active_fault_hook,
    )

    expected_ids = set(prepared.expected_vector_ids)
    validator = _prepared_external_validator(
        repo=repo,
        prepared=prepared,
    )
    validator()
    _fault(active_fault_hook, "external_artifacts_validated")
    store.set_metadata(
        PROJECT_SCOPE_METADATA_VERSION_KEY,
        str(PROJECT_SCOPE_METADATA_VERSION),
    )
    _fault(active_fault_hook, "final_validation")
    manifest = prepared.prepared_manifest.manifest
    binding = OperationalReadyBinding(
        index_config_hash=manifest.index_config_hash,
        source_content_fingerprint=manifest.source_content_fingerprint,
        source_observation_fingerprint=manifest.source_observation_fingerprint,
        observation_generation=manifest.observation_generation,
        manifest_schema_version=manifest.schema_version,
        manifest_generation=manifest.manifest_generation,
        manifest_sha256=prepared.prepared_manifest.sha256,
        vector_descriptor_schema_version=manifest.vector_descriptor_schema_version,
        vector_generation=manifest.vector_generation,
        vector_descriptor_sha256=manifest.vector_descriptor_sha256,
        vector_bytes=manifest.vector_bytes,
        vector_ids_bytes=manifest.vector_ids_bytes,
        indexed_at_epoch_s=manifest.indexed_at_epoch_s,
        operation_mode=manifest.operation_mode,
        work_metrics=manifest.work_metrics,
    )
    tombstones_before_ready = store.tombstone_count()
    tombstone_purge_limit = (
        5_000
        if manifest.operation_mode == "quick_refresh" and store.maintenance_required()
        else 0
    )
    store.commit_operational_ready_v1(
        binding=binding,
        topology_fingerprint=prepared.topology_fingerprint,
        expected_embedding_ids=expected_ids,
        expected_source_count=manifest.total_files,
        expected_chunk_count=manifest.total_chunks,
        external_validator=validator,
        tombstone_purge_limit=tombstone_purge_limit,
        before_commit=lambda: _fault(
            active_fault_hook,
            "before_ready_commit",
        ),
    )
    _fault(active_fault_hook, "after_ready_commit")
    tombstones_after_ready = store.tombstone_count()
    try:
        _cleanup_unreferenced_vector_generations(
            repo / ".context-search",
            store,
            keep_generation=manifest.vector_generation,
        )
    except (OSError, ValueError):
        logger.warning("vector_generation_cleanup_failed")
    _fault(active_fault_hook, "generation_cleanup_complete")
    return _PersistenceWork(
        relations_resolved=producer_resolved + association_resolved,
        association_writes=len(associations),
        tombstones_purged=max(0, tombstones_before_ready - tombstones_after_ready),
    )


def _retry_existing_vector_generation_cleanup(
    repo: Path,
    store: SQLiteStore,
) -> None:
    try:
        descriptor = NumpyVectorStore.inspect_published_descriptor(
            repo / ".context-search"
        )
    except (OSError, RuntimeError, ValueError):
        return
    if descriptor is None:
        return
    _cleanup_unreferenced_vector_generations(
        repo / ".context-search",
        store,
        keep_generation=descriptor.descriptor.generation,
    )


def _cleanup_unreferenced_vector_generations(
    index_dir: Path,
    store: SQLiteStore,
    *,
    keep_generation: str,
) -> int:
    if not NumpyVectorStore.has_safe_unreferenced_generation_artifacts(
        index_dir,
        keep_generation=keep_generation,
    ):
        return 0
    return NumpyVectorStore.cleanup_unreferenced_generations(
        index_dir,
        keep_generation=keep_generation,
        journal_mode=store.journal_mode(),
    )


def _prepared_external_validator(
    *,
    repo: Path,
    prepared: PreparedIndexSnapshot,
) -> Callable[[], None]:
    def validate() -> None:
        manifest = load_manifest_snapshot(repo)
        if (
            manifest.manifest != prepared.prepared_manifest.manifest
            or manifest.sha256 != prepared.prepared_manifest.sha256
        ):
            raise GraphIntegrityError("manifest snapshot mismatch")
        descriptor = NumpyVectorStore.inspect_published_descriptor(
            repo / ".context-search"
        )
        if descriptor != prepared.vector_descriptor_snapshot:
            raise GraphIntegrityError("vector descriptor snapshot mismatch")
        verified = NumpyVectorStore.verify_published_snapshot(
            repo / ".context-search",
            expected_ids=set(prepared.expected_vector_ids),
            expected_embedding_identity=prepared.prepared_manifest.manifest.embedding_config_hash,
        )
        if verified.ids != prepared.expected_vector_ids:
            raise GraphIntegrityError("vector ID snapshot mismatch")

    return validate


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
    repository_path_index: RepositoryPathIndex,
) -> PluginContext:
    return PluginContext(
        file_path=scanned_file.path,
        language=scanned_file.language,
        project_unit_key=_project_unit_key(project_unit),
        project_metadata=project_metadata(project_unit),
        repository_path_index=repository_path_index,
    )


def _prepare_v5_file(
    *,
    repo: Path,
    scanned_file: ScannedFile,
    project_unit: ProjectUnit,
    plugins: tuple[GraphLanguagePlugin, ...],
    repository_path_index: RepositoryPathIndex,
    file_reader: Callable[..., bytes],
    max_file_bytes: int,
    content_bytes: bytes | None = None,
) -> _PreparedFile:
    if content_bytes is None:
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
        repository_path_index,
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
        chunks=tuple(chunks),
        signals=tuple(signals),
        relations=tuple(relations),
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
        manifest.embedding_config_hash != expected_embedding_identity
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
    if isinstance(manifest, ManifestV2):
        descriptor_snapshot = NumpyVectorStore.inspect_published_descriptor(index_dir)
        if (
            manifest.index_config_hash != index_config_hash(config)
            or descriptor_snapshot is None
            or descriptor_snapshot.sha256 != manifest.vector_descriptor_sha256
            or descriptor.schema_version
            != manifest.vector_descriptor_schema_version
            or descriptor.generation != manifest.vector_generation
            or descriptor.vectors_bytes != manifest.vector_bytes
            or descriptor.ids_bytes != manifest.vector_ids_bytes
        ):
            raise GraphIntegrityError("manifest vector binding mismatch")
    elif manifest.schema_version != MANIFEST_SCHEMA_VERSION:
        raise GraphIntegrityError("manifest snapshot mismatch")
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
