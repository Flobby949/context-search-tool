from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import errno
import os
from pathlib import Path
import stat
import time
from typing import Any, Callable, Mapping, Sequence

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig, read_config
from context_search_tool.graph_lifecycle import (
    IncompatibleOperationalSchemaError,
    IncompatibleSignalSchemaError,
    TARGET_SIGNAL_SCHEMA_VERSION,
    classify_raw_graph_schema,
    read_graph_capability,
)
from context_search_tool.manifest import (
    IncompatibleManifestSchemaError,
    LoadedManifestSnapshot,
    Manifest,
    ManifestV2,
    READABLE_MANIFEST_VERSIONS,
    embedding_config_hash,
    index_config_hash,
    inspect_raw_manifest_schema,
    load_manifest_snapshot,
)
from context_search_tool.scanner import (
    CoverageSkipObservation,
    FileObservation,
    InventoryDiagnostic,
    ObservedFileRead,
    StableFileMetadata,
    WorkspaceInventory,
    observe_workspace,
    read_observed_file,
)
from context_search_tool.sqlite_store import (
    OperationalReadyIdentity,
    OperationalScanSkip,
    OperationalSnapshot,
    OperationalSourceObservation,
    SQLiteStore,
    TARGET_OPERATIONAL_SCHEMA_VERSION,
    inspect_raw_sqlite_schema_versions,
)
from context_search_tool.vector_store import (
    NumpyVectorStore,
    PublishedVectorDescriptor,
    VectorDescriptorCorruptionError,
    VectorIdMismatchError,
)


REPORT_KEYS = (
    "schema_version",
    "health",
    "queryable",
    "queryability_evidence",
    "availability",
    "observation",
    "freshness",
    "coverage",
    "integrity",
    "vectors",
    "indexed_embedding",
    "configured_embedding",
    "embedding_config_match",
    "refresh",
    "writer",
    "diagnostics",
)
OBSERVATION_KEYS = (
    "started_at_epoch_ms",
    "completed_at_epoch_ms",
    "inventory_status",
    "unscannable_subtree_count",
    "control_file_error_count",
    "change_token_kind",
    "limitations",
)
FRESHNESS_KEYS = (
    "status",
    "inspection_mode",
    "indexed_at_epoch_s",
    "age_seconds",
    "added",
    "changed",
    "deleted",
    "metadata_unchanged",
    "content_verified",
    "samples",
    "sample_limit",
    "sampled_total",
    "evidence_generation",
)
COVERAGE_KEYS = (
    "status",
    "evidence",
    "indexed_files",
    "coverage_skips",
    "pending_inspection",
    "pending_retry",
    "skip_counts",
    "skip_samples",
    "excluded_counts",
)
INTEGRITY_KEYS = (
    "status",
    "manifest",
    "sqlite",
    "graph",
    "graph_stale_reason",
    "vector",
)
VECTOR_KEYS = (
    "generation",
    "eligible_chunks",
    "rows",
    "coverage_ratio",
    "coverage_evidence",
    "missing_ids",
    "orphan_ids",
    "dimensions",
)
EMBEDDING_KEYS = (
    "status",
    "provider",
    "model",
    "dimensions",
    "config_hash",
    "network_egress_capable",
    "network_egress_evidence",
)
REFRESH_KEYS = ("required", "kind", "reasons", "recommended_action")
WRITER_KEYS = ("active", "state", "evidence")

FRESHNESS_CATEGORY_ORDER = (
    "added",
    "changed",
    "deleted",
    "metadata_only",
    "pending_inspection",
)
REFRESH_REASON_ORDER = (
    "source_changed",
    "path_inventory_changed",
    "coverage_changed",
    "index_config_changed",
    "embedding_config_changed",
    "topology_changed",
    "graph_stale",
    "manifest_upgrade",
    "integrity_failed",
    "inventory_incomplete",
)
DIAGNOSTIC_CODE_ORDER = (
    "legacy_manifest",
    "inventory_incomplete",
    "unscannable_subtree",
    "control_file_error",
    "writer_state_unknown",
    "inspection_interrupted",
    "verification_interrupted",
    "vector_payload_unverified",
    "manifest_identity_mismatch",
    "vector_identity_mismatch",
    "orphan_generation",
    "coverage_pending",
)
SKIP_REASON_ORDER = (
    "too_large",
    "binary",
    "unreadable",
    "unsafe_path",
    "changed_during_read",
    "unsupported_encoding",
)
EXCLUSION_REASON_ORDER = (
    "ignored",
    "internal",
    "default_directory",
    "config_excluded",
    "unsupported_language",
    "pruned_directory",
)

PUBLIC_OPERATIONS = frozenset(
    {
        "index",
        "query",
        "trace",
        "context",
        "explore",
        "status",
        "stats",
        "refresh",
        "explain",
    }
)


class MissingIndexError(RuntimeError):
    code = "missing_index"

    def __init__(self) -> None:
        super().__init__("index is missing")


class IndexCorruptionError(RuntimeError):
    code = "index_corrupt"

    def __init__(self) -> None:
        super().__init__("index is corrupt")


class Health(StrEnum):
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    CORRUPT = "corrupt"
    STALE = "stale"
    DEGRADED = "degraded"
    HEALTHY_VERIFIED = "healthy_verified"
    HEALTHY_METADATA = "healthy_metadata"


class Availability(StrEnum):
    MISSING = "missing"
    PRESENT = "present"
    INCOMPATIBLE = "incompatible"
    CORRUPT = "corrupt"


class FreshnessStatus(StrEnum):
    UNKNOWN = "unknown"
    STALE = "stale"
    METADATA_FRESH = "metadata_fresh"
    VERIFIED_FRESH = "verified_fresh"


class CoverageStatus(StrEnum):
    UNKNOWN = "unknown"
    COMPLETE = "complete"
    DEGRADED = "degraded"


class IntegrityStatus(StrEnum):
    UNCHECKED = "unchecked"
    VALID_QUICK = "valid_quick"
    VALID_VERIFIED = "valid_verified"
    INVALID = "invalid"


class InventoryStatus(StrEnum):
    NOT_INSPECTED = "not_inspected"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class FreshnessSample:
    category: str
    path: str
    reason: str


@dataclass(frozen=True)
class SkipSample:
    path: str
    reason: str
    retryable: bool


@dataclass(frozen=True)
class Diagnostic:
    code: str
    scope: str
    path: str | None


@dataclass(frozen=True)
class ObservationReport:
    started_at_epoch_ms: int | None
    completed_at_epoch_ms: int | None
    inventory_status: str
    unscannable_subtree_count: int | None
    control_file_error_count: int | None
    change_token_kind: str | None
    limitations: tuple[str, ...] | None


@dataclass(frozen=True)
class FreshnessReport:
    status: str
    inspection_mode: str
    indexed_at_epoch_s: int | None
    age_seconds: int | None
    added: int | None
    changed: int | None
    deleted: int | None
    metadata_unchanged: int | None
    content_verified: int | None
    samples: tuple[FreshnessSample, ...] | None
    sample_limit: int
    sampled_total: int | None
    evidence_generation: str | None


@dataclass(frozen=True)
class CoverageReport:
    status: str
    evidence: str
    indexed_files: int | None
    coverage_skips: int | None
    pending_inspection: int | None
    pending_retry: int | None
    skip_counts: tuple[tuple[str, int], ...] | None
    skip_samples: tuple[SkipSample, ...] | None
    excluded_counts: tuple[tuple[str, int], ...] | None


@dataclass(frozen=True)
class IntegrityReport:
    status: str
    manifest: str
    sqlite: str
    graph: str
    graph_stale_reason: str | None
    vector: str


@dataclass(frozen=True)
class VectorReport:
    generation: str | None
    eligible_chunks: int | None
    rows: int | None
    coverage_ratio: int | float | None
    coverage_evidence: str
    missing_ids: tuple[str, ...] | None
    orphan_ids: tuple[str, ...] | None
    dimensions: int | None


@dataclass(frozen=True)
class EmbeddingIdentity:
    status: str
    provider: str | None
    model: str | None
    dimensions: int | None
    config_hash: str | None
    network_egress_capable: bool
    network_egress_evidence: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> EmbeddingIdentity:
        _require_keys(raw, EMBEDDING_KEYS, "embedding identity")
        value = cls(**{key: raw[key] for key in EMBEDDING_KEYS})
        value._validate()
        return value

    @classmethod
    def hash_v1(cls, config_hash: str, dimensions: int) -> EmbeddingIdentity:
        return cls(
            status="valid",
            provider="hash",
            model="hash-v1",
            dimensions=dimensions,
            config_hash=config_hash,
            network_egress_capable=False,
            network_egress_evidence="built_in_hash",
        )

    def _validate(self) -> None:
        if self.status == "valid":
            if (
                not isinstance(self.provider, str)
                or not self.provider
                or not isinstance(self.model, str)
                or not self.model
                or type(self.dimensions) is not int
                or self.dimensions < 1
                or not isinstance(self.config_hash, str)
                or not self.config_hash
            ):
                raise ValueError("valid embedding identity is incomplete")
            if self.provider == "hash":
                if self.network_egress_capable or self.network_egress_evidence != (
                    "built_in_hash"
                ):
                    raise ValueError("hash embedding network egress must be false")
            elif not self.network_egress_capable:
                raise ValueError("network egress must fail closed")
            return
        if self.status not in {"missing", "invalid", "not_inspected"}:
            raise ValueError("embedding identity status is invalid")
        if any(
            value is not None
            for value in (
                self.provider,
                self.model,
                self.dimensions,
                self.config_hash,
            )
        ):
            raise ValueError("non-valid embedding identity must be null")
        if not self.network_egress_capable:
            raise ValueError("network egress must fail closed")


@dataclass(frozen=True)
class RefreshReport:
    required: bool
    kind: str
    reasons: tuple[str, ...]
    recommended_action: str


@dataclass(frozen=True)
class WriterReport:
    active: bool | None
    state: str
    evidence: str


@dataclass(frozen=True)
class IndexHealthReport:
    schema_version: int
    health: str
    queryable: bool
    queryability_evidence: str
    availability: str
    observation: ObservationReport
    freshness: FreshnessReport
    coverage: CoverageReport
    integrity: IntegrityReport
    vectors: VectorReport
    indexed_embedding: EmbeddingIdentity
    configured_embedding: EmbeddingIdentity
    embedding_config_match: bool | None
    refresh: RefreshReport
    writer: WriterReport
    diagnostics: tuple[Diagnostic, ...] | None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> IndexHealthReport:
        _require_keys(raw, REPORT_KEYS, "index health report")
        if raw["schema_version"] != 1:
            raise ValueError("unsupported index health report schema")
        Health(raw["health"])
        Availability(raw["availability"])
        observation_raw = _mapping(raw["observation"], "observation")
        freshness_raw = _mapping(raw["freshness"], "freshness")
        coverage_raw = _mapping(raw["coverage"], "coverage")
        integrity_raw = _mapping(raw["integrity"], "integrity")
        vector_raw = _mapping(raw["vectors"], "vectors")
        refresh_raw = _mapping(raw["refresh"], "refresh")
        writer_raw = _mapping(raw["writer"], "writer")
        _require_keys(observation_raw, OBSERVATION_KEYS, "observation")
        _require_keys(freshness_raw, FRESHNESS_KEYS, "freshness")
        _require_keys(coverage_raw, COVERAGE_KEYS, "coverage")
        _require_keys(integrity_raw, INTEGRITY_KEYS, "integrity")
        _require_keys(vector_raw, VECTOR_KEYS, "vectors")
        _require_keys(refresh_raw, REFRESH_KEYS, "refresh")
        _require_keys(writer_raw, WRITER_KEYS, "writer")
        InventoryStatus(observation_raw["inventory_status"])
        FreshnessStatus(freshness_raw["status"])
        CoverageStatus(coverage_raw["status"])
        IntegrityStatus(integrity_raw["status"])

        sample_limit = freshness_raw["sample_limit"]
        if type(sample_limit) is not int or sample_limit < 1:
            raise ValueError("freshness sample limit is invalid")
        freshness_samples = _freshness_samples(
            freshness_raw["samples"], sample_limit
        )
        skip_samples = _skip_samples(coverage_raw["skip_samples"], sample_limit)
        refresh_reasons = _ordered_strings(
            refresh_raw["reasons"], REFRESH_REASON_ORDER, "refresh reason"
        )
        diagnostics = _diagnostics(raw["diagnostics"])
        skip_counts = _closed_counts(
            coverage_raw["skip_counts"], SKIP_REASON_ORDER, "skip counts"
        )
        excluded_counts = _closed_counts(
            coverage_raw["excluded_counts"],
            EXCLUSION_REASON_ORDER,
            "excluded counts",
        )
        indexed_embedding = EmbeddingIdentity.from_dict(
            _mapping(raw["indexed_embedding"], "indexed embedding")
        )
        configured_embedding = EmbeddingIdentity.from_dict(
            _mapping(raw["configured_embedding"], "configured embedding")
        )
        expected_match = (
            _embedding_key(indexed_embedding) == _embedding_key(configured_embedding)
            if indexed_embedding.status == configured_embedding.status == "valid"
            else None
        )
        if raw["embedding_config_match"] != expected_match:
            raise ValueError("embedding configuration match is inconsistent")
        return cls(
            schema_version=1,
            health=str(raw["health"]),
            queryable=bool(raw["queryable"]),
            queryability_evidence=str(raw["queryability_evidence"]),
            availability=str(raw["availability"]),
            observation=ObservationReport(
                **{key: observation_raw[key] for key in OBSERVATION_KEYS[:-1]},
                limitations=(
                    tuple(observation_raw["limitations"])
                    if observation_raw["limitations"] is not None
                    else None
                ),
            ),
            freshness=FreshnessReport(
                **{key: freshness_raw[key] for key in FRESHNESS_KEYS[:9]},
                samples=freshness_samples,
                sample_limit=sample_limit,
                sampled_total=freshness_raw["sampled_total"],
                evidence_generation=freshness_raw["evidence_generation"],
            ),
            coverage=CoverageReport(
                status=coverage_raw["status"],
                evidence=coverage_raw["evidence"],
                indexed_files=coverage_raw["indexed_files"],
                coverage_skips=coverage_raw["coverage_skips"],
                pending_inspection=coverage_raw["pending_inspection"],
                pending_retry=coverage_raw["pending_retry"],
                skip_counts=skip_counts,
                skip_samples=skip_samples,
                excluded_counts=excluded_counts,
            ),
            integrity=IntegrityReport(
                **{key: integrity_raw[key] for key in INTEGRITY_KEYS}
            ),
            vectors=VectorReport(
                generation=vector_raw["generation"],
                eligible_chunks=vector_raw["eligible_chunks"],
                rows=vector_raw["rows"],
                coverage_ratio=vector_raw["coverage_ratio"],
                coverage_evidence=vector_raw["coverage_evidence"],
                missing_ids=(
                    tuple(vector_raw["missing_ids"])
                    if vector_raw["missing_ids"] is not None
                    else None
                ),
                orphan_ids=(
                    tuple(vector_raw["orphan_ids"])
                    if vector_raw["orphan_ids"] is not None
                    else None
                ),
                dimensions=vector_raw["dimensions"],
            ),
            indexed_embedding=indexed_embedding,
            configured_embedding=configured_embedding,
            embedding_config_match=expected_match,
            refresh=RefreshReport(
                required=bool(refresh_raw["required"]),
                kind=refresh_raw["kind"],
                reasons=refresh_reasons,
                recommended_action=refresh_raw["recommended_action"],
            ),
            writer=WriterReport(
                active=writer_raw["active"],
                state=writer_raw["state"],
                evidence=writer_raw["evidence"],
            ),
            diagnostics=diagnostics,
        )


def serialize_index_health(report: IndexHealthReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "health": report.health,
        "queryable": report.queryable,
        "queryability_evidence": report.queryability_evidence,
        "availability": report.availability,
        "observation": {
            "started_at_epoch_ms": report.observation.started_at_epoch_ms,
            "completed_at_epoch_ms": report.observation.completed_at_epoch_ms,
            "inventory_status": report.observation.inventory_status,
            "unscannable_subtree_count": (
                report.observation.unscannable_subtree_count
            ),
            "control_file_error_count": report.observation.control_file_error_count,
            "change_token_kind": report.observation.change_token_kind,
            "limitations": (
                list(report.observation.limitations)
                if report.observation.limitations is not None
                else None
            ),
        },
        "freshness": {
            "status": report.freshness.status,
            "inspection_mode": report.freshness.inspection_mode,
            "indexed_at_epoch_s": report.freshness.indexed_at_epoch_s,
            "age_seconds": report.freshness.age_seconds,
            "added": report.freshness.added,
            "changed": report.freshness.changed,
            "deleted": report.freshness.deleted,
            "metadata_unchanged": report.freshness.metadata_unchanged,
            "content_verified": report.freshness.content_verified,
            "samples": (
                [
                    {
                        "category": item.category,
                        "path": item.path,
                        "reason": item.reason,
                    }
                    for item in report.freshness.samples
                ]
                if report.freshness.samples is not None
                else None
            ),
            "sample_limit": report.freshness.sample_limit,
            "sampled_total": report.freshness.sampled_total,
            "evidence_generation": report.freshness.evidence_generation,
        },
        "coverage": {
            "status": report.coverage.status,
            "evidence": report.coverage.evidence,
            "indexed_files": report.coverage.indexed_files,
            "coverage_skips": report.coverage.coverage_skips,
            "pending_inspection": report.coverage.pending_inspection,
            "pending_retry": report.coverage.pending_retry,
            "skip_counts": (
                dict(report.coverage.skip_counts)
                if report.coverage.skip_counts is not None
                else None
            ),
            "skip_samples": (
                [
                    {
                        "path": item.path,
                        "reason": item.reason,
                        "retryable": item.retryable,
                    }
                    for item in report.coverage.skip_samples
                ]
                if report.coverage.skip_samples is not None
                else None
            ),
            "excluded_counts": (
                dict(report.coverage.excluded_counts)
                if report.coverage.excluded_counts is not None
                else None
            ),
        },
        "integrity": {
            "status": report.integrity.status,
            "manifest": report.integrity.manifest,
            "sqlite": report.integrity.sqlite,
            "graph": report.integrity.graph,
            "graph_stale_reason": report.integrity.graph_stale_reason,
            "vector": report.integrity.vector,
        },
        "vectors": {
            "generation": report.vectors.generation,
            "eligible_chunks": report.vectors.eligible_chunks,
            "rows": report.vectors.rows,
            "coverage_ratio": report.vectors.coverage_ratio,
            "coverage_evidence": report.vectors.coverage_evidence,
            "missing_ids": (
                list(report.vectors.missing_ids)
                if report.vectors.missing_ids is not None
                else None
            ),
            "orphan_ids": (
                list(report.vectors.orphan_ids)
                if report.vectors.orphan_ids is not None
                else None
            ),
            "dimensions": report.vectors.dimensions,
        },
        "indexed_embedding": _embedding_dict(report.indexed_embedding),
        "configured_embedding": _embedding_dict(report.configured_embedding),
        "embedding_config_match": report.embedding_config_match,
        "refresh": {
            "required": report.refresh.required,
            "kind": report.refresh.kind,
            "reasons": list(report.refresh.reasons),
            "recommended_action": report.refresh.recommended_action,
        },
        "writer": {
            "active": report.writer.active,
            "state": report.writer.state,
            "evidence": report.writer.evidence,
        },
        "diagnostics": (
            [
                {"code": item.code, "scope": item.scope, "path": item.path}
                for item in report.diagnostics
            ]
            if report.diagnostics is not None
            else None
        ),
    }


@dataclass(frozen=True)
class HealthDerivation:
    availability: str
    freshness: str
    coverage: str
    integrity: str
    inventory: str
    graph: str
    writer_active: bool | None
    generation_stable: bool


def derive_health(evidence: HealthDerivation) -> Health:
    if evidence.availability == "missing":
        return Health.MISSING
    if evidence.availability == "incompatible":
        return Health.INCOMPATIBLE
    stable_corruption = (
        evidence.availability == "corrupt" or evidence.integrity == "invalid"
    ) and evidence.writer_active is False and evidence.generation_stable
    if stable_corruption:
        return Health.CORRUPT
    if (
        evidence.graph in {"stale", "unfinished"}
        or evidence.inventory == "incomplete"
        or evidence.freshness == "stale"
    ):
        return Health.STALE
    if (
        evidence.writer_active is not False
        or not evidence.generation_stable
        or evidence.integrity == "unchecked"
        or evidence.coverage == "degraded"
    ):
        return Health.DEGRADED
    if (
        evidence.freshness == "verified_fresh"
        and evidence.integrity == "valid_verified"
    ):
        return Health.HEALTHY_VERIFIED
    return Health.HEALTHY_METADATA


@dataclass(frozen=True)
class RawIndexCapability:
    status: str
    index_exists: bool
    manifest_version: int | None
    operational_version: int | None
    graph_version: int | None
    error_code: str | None


def probe_raw_index_capability(repo: Path) -> RawIndexCapability:
    try:
        resolved_repo = repo.resolve(strict=True)
    except OSError as error:
        raise ValueError("repository root does not exist") from error
    if not resolved_repo.is_dir():
        raise ValueError("repository root must be a directory")
    internal = resolved_repo / ".context-search"
    database = internal / "index.sqlite"
    manifest_path = internal / "manifest.json"
    if os.path.lexists(internal) and (internal.is_symlink() or not internal.is_dir()):
        return RawIndexCapability(
            status="corrupt",
            index_exists=True,
            manifest_version=None,
            operational_version=None,
            graph_version=None,
            error_code="unsafe_index_directory",
        )
    if not os.path.lexists(database) and not os.path.lexists(manifest_path):
        return RawIndexCapability(
            status="missing",
            index_exists=False,
            manifest_version=None,
            operational_version=None,
            graph_version=None,
            error_code="missing_index",
        )
    manifest = inspect_raw_manifest_schema(resolved_repo)
    if manifest.status != "valid" or manifest.version is None:
        return RawIndexCapability(
            status="corrupt",
            index_exists=True,
            manifest_version=manifest.version,
            operational_version=None,
            graph_version=None,
            error_code=manifest.error_code,
        )
    if manifest.version > max(READABLE_MANIFEST_VERSIONS):
        return RawIndexCapability(
            status="incompatible",
            index_exists=True,
            manifest_version=manifest.version,
            operational_version=None,
            graph_version=None,
            error_code="future_manifest_schema",
        )
    if manifest.version not in READABLE_MANIFEST_VERSIONS:
        return RawIndexCapability(
            status="corrupt",
            index_exists=True,
            manifest_version=manifest.version,
            operational_version=None,
            graph_version=None,
            error_code="invalid_manifest_schema",
        )

    sqlite_versions = inspect_raw_sqlite_schema_versions(database)
    if sqlite_versions.status != "valid":
        return RawIndexCapability(
            status="corrupt",
            index_exists=True,
            manifest_version=manifest.version,
            operational_version=sqlite_versions.operational_version,
            graph_version=sqlite_versions.graph_version,
            error_code=sqlite_versions.error_code,
        )
    operational = sqlite_versions.operational_version
    if operational is not None and operational > TARGET_OPERATIONAL_SCHEMA_VERSION:
        return RawIndexCapability(
            status="incompatible",
            index_exists=True,
            manifest_version=manifest.version,
            operational_version=operational,
            graph_version=None,
            error_code="future_operational_schema",
        )
    graph = classify_raw_graph_schema(sqlite_versions.graph_version)
    if graph.status == "future":
        return RawIndexCapability(
            status="incompatible",
            index_exists=True,
            manifest_version=manifest.version,
            operational_version=operational,
            graph_version=graph.version,
            error_code=graph.error_code,
        )
    return RawIndexCapability(
        status="compatible",
        index_exists=True,
        manifest_version=manifest.version,
        operational_version=operational,
        graph_version=sqlite_versions.graph_version,
        error_code=None,
    )


def preflight_public_operation(
    repo: Path,
    operation: str,
) -> RawIndexCapability:
    """Inspect persisted schema capability before operation-specific work."""
    if operation not in PUBLIC_OPERATIONS:
        raise ValueError("unknown public operation")
    capability = probe_raw_index_capability(repo)
    if operation == "status":
        return capability
    if capability.status == "incompatible":
        if capability.error_code == "future_manifest_schema":
            raise IncompatibleManifestSchemaError(capability.manifest_version)
        if capability.error_code == "future_operational_schema":
            raise IncompatibleOperationalSchemaError(
                capability.operational_version
            )
        if capability.error_code == "future_graph_schema":
            raise IncompatibleSignalSchemaError(capability.graph_version)
        raise IndexCorruptionError()
    if operation == "index":
        return capability
    if capability.status == "missing":
        raise MissingIndexError()
    if capability.status == "corrupt":
        if (
            capability.error_code == "missing_manifest"
            and operation in {"query", "trace", "context", "explore", "explain"}
        ):
            return capability
        raise IndexCorruptionError()
    return capability


@dataclass(frozen=True)
class IndexedFileObservation:
    path: str
    language: str
    size: int
    mtime_ns: int
    change_token: int | str | None
    change_token_kind: str
    sha256: str


@dataclass(frozen=True)
class CommittedSnapshotStabilityToken:
    manifest: ManifestV2
    manifest_sha256: str
    operational: OperationalReadyIdentity
    vector_descriptor: PublishedVectorDescriptor
    vector_generation_count: int


@dataclass(frozen=True)
class CommittedIndexSnapshot:
    ready_generation: str
    manifest_version: int
    operational_version: int | None
    graph_version: int
    graph_status: str
    graph_stale_reason: str
    queryable: bool
    indexed_at_epoch_s: int | None
    indexed_files: tuple[IndexedFileObservation, ...]
    coverage_skips: tuple[CoverageSkipObservation, ...]
    eligible_chunks: int
    vector_rows: int
    vector_generation: str
    vector_dimensions: int
    manifest_valid: bool
    sqlite_valid: bool
    vector_identity_valid: bool
    indexed_embedding: EmbeddingIdentity
    active_embedding_ids: tuple[str, ...] = ()
    index_config_hash: str | None = None
    vector_generation_count: int = 1
    stability_token: CommittedSnapshotStabilityToken | None = None


@dataclass(frozen=True)
class VectorVerification:
    status: str
    missing_ids: tuple[str, ...]
    orphan_ids: tuple[str, ...]

    @classmethod
    def valid(cls) -> VectorVerification:
        return cls("valid", (), ())

    @classmethod
    def invalid(
        cls,
        *,
        missing_ids: Sequence[str] = (),
        orphan_ids: Sequence[str] = (),
    ) -> VectorVerification:
        return cls("invalid", tuple(missing_ids), tuple(orphan_ids))

    @classmethod
    def interrupted(cls) -> VectorVerification:
        return cls("interrupted", (), ())


def read_committed_index_snapshot(repo: Path) -> CommittedIndexSnapshot:
    resolved = repo.resolve(strict=True)
    index_dir = resolved / ".context-search"
    store = SQLiteStore(index_dir / "index.sqlite")
    loaded_manifest = load_manifest_snapshot(resolved)
    manifest = loaded_manifest.manifest
    operational = store.read_operational_snapshot()
    if isinstance(manifest, Manifest):
        return _legacy_committed_snapshot(store, index_dir, manifest)
    if operational is None:
        return _unbound_v2_snapshot(store, index_dir, manifest)

    descriptor_snapshot: PublishedVectorDescriptor | None
    try:
        descriptor_snapshot = NumpyVectorStore.inspect_published_descriptor(index_dir)
    except VectorDescriptorCorruptionError:
        descriptor_snapshot = None
    return _committed_v2_snapshot(
        resolved,
        loaded_manifest,
        operational,
        descriptor_snapshot,
    )


def _committed_v2_snapshot(
    resolved: Path,
    loaded_manifest: LoadedManifestSnapshot,
    operational: OperationalSnapshot,
    descriptor_snapshot: PublishedVectorDescriptor | None,
) -> CommittedIndexSnapshot:
    manifest = loaded_manifest.manifest
    if not isinstance(manifest, ManifestV2):
        raise ValueError("committed v2 snapshot requires a v2 manifest")
    index_dir = resolved / ".context-search"
    manifest_valid = _manifest_matches_operational(
        manifest,
        loaded_manifest.sha256,
        operational,
    )
    vector_valid = _vector_matches_bound_snapshot(
        manifest,
        operational,
        descriptor_snapshot,
    )
    descriptor = (
        descriptor_snapshot.descriptor if descriptor_snapshot is not None else None
    )
    vector_generation_count = (
        1
        + NumpyVectorStore.unreferenced_generation_count(
            index_dir,
            keep_generation=(
                descriptor.generation
                if descriptor is not None
                else manifest.vector_generation
            ),
        )
    )
    stability_token = (
        CommittedSnapshotStabilityToken(
            manifest=manifest,
            manifest_sha256=loaded_manifest.sha256,
            operational=operational.ready_identity,
            vector_descriptor=descriptor_snapshot,
            vector_generation_count=vector_generation_count,
        )
        if descriptor_snapshot is not None
        and operational.sqlite_change_counter_bound
        else None
    )
    return CommittedIndexSnapshot(
        ready_generation=operational.binding.manifest_generation,
        manifest_version=manifest.schema_version,
        operational_version=operational.operational_version,
        graph_version=operational.graph_version,
        graph_status=operational.graph_status,
        graph_stale_reason=operational.graph_stale_reason,
        queryable=(
            operational.graph_status == "ready" and manifest_valid and vector_valid
        ),
        indexed_at_epoch_s=operational.binding.indexed_at_epoch_s,
        indexed_files=tuple(
            _indexed_file_observation(item)
            for item in operational.source_observations
        ),
        coverage_skips=tuple(
            _coverage_skip_observation(item) for item in operational.scan_skips
        ),
        eligible_chunks=operational.chunk_count,
        vector_rows=descriptor.row_count if descriptor is not None else 0,
        vector_generation=(
            descriptor.generation
            if descriptor is not None
            else operational.binding.vector_generation
        ),
        vector_dimensions=(
            descriptor.dimensions
            if descriptor is not None
            else manifest.embedding_dimensions
        ),
        manifest_valid=manifest_valid,
        sqlite_valid=True,
        vector_identity_valid=vector_valid,
        indexed_embedding=_indexed_embedding(manifest),
        active_embedding_ids=operational.active_embedding_ids,
        index_config_hash=operational.binding.index_config_hash,
        vector_generation_count=vector_generation_count,
        stability_token=stability_token,
    )


def recheck_committed_index_snapshot(
    repo: Path,
    opening: CommittedIndexSnapshot,
) -> CommittedIndexSnapshot:
    """Use a short second SQLite snapshot when the bound v2 identity is stable."""
    expected = opening.stability_token
    if expected is None:
        return read_committed_index_snapshot(repo)
    try:
        resolved = repo.resolve(strict=True)
        index_dir = resolved / ".context-search"
        loaded_manifest = load_manifest_snapshot(resolved)
        if not isinstance(loaded_manifest.manifest, ManifestV2):
            return read_committed_index_snapshot(repo)
        descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
        if descriptor is None:
            return read_committed_index_snapshot(repo)
        vector_generation_count = (
            1
            + NumpyVectorStore.unreferenced_generation_count(
                index_dir,
                keep_generation=descriptor.descriptor.generation,
            )
        )
        operational = SQLiteStore(
            index_dir / "index.sqlite"
        ).read_operational_ready_identity()
        if operational is None:
            return read_committed_index_snapshot(repo)
        current = CommittedSnapshotStabilityToken(
            manifest=loaded_manifest.manifest,
            manifest_sha256=loaded_manifest.sha256,
            operational=operational,
            vector_descriptor=descriptor,
            vector_generation_count=vector_generation_count,
        )
    except (OSError, RuntimeError, ValueError):
        return read_committed_index_snapshot(repo)
    if current == expected:
        return opening
    return read_committed_index_snapshot(repo)


def verify_committed_vector_snapshot(
    repo: Path,
    snapshot: CommittedIndexSnapshot,
) -> VectorVerification:
    if not snapshot.vector_identity_valid:
        return VectorVerification.invalid()
    try:
        verified = NumpyVectorStore.verify_published_snapshot(
            repo.resolve(strict=True) / ".context-search",
            expected_ids=snapshot.active_embedding_ids,
        )
    except VectorIdMismatchError:
        try:
            verified = NumpyVectorStore.verify_published_snapshot(
                repo.resolve(strict=True) / ".context-search",
            )
        except ValueError:
            return VectorVerification.invalid()
        expected = set(snapshot.active_embedding_ids)
        actual = set(verified.ids)
        return VectorVerification.invalid(
            missing_ids=tuple(sorted(expected - actual)),
            orphan_ids=tuple(sorted(actual - expected)),
        )
    except ValueError:
        return VectorVerification.invalid()
    if verified.descriptor_snapshot.descriptor.generation != snapshot.vector_generation:
        return VectorVerification.interrupted()
    return VectorVerification.valid()


def _manifest_matches_operational(
    manifest: ManifestV2,
    manifest_sha256: str,
    operational: OperationalSnapshot,
) -> bool:
    binding = operational.binding
    return all(
        (
            manifest.schema_version == binding.manifest_schema_version,
            manifest.manifest_generation == binding.manifest_generation,
            manifest_sha256 == binding.manifest_sha256,
            manifest.index_config_hash == binding.index_config_hash,
            manifest.source_content_fingerprint
            == binding.source_content_fingerprint,
            manifest.source_observation_fingerprint
            == binding.source_observation_fingerprint,
            manifest.observation_generation == binding.observation_generation,
            manifest.vector_descriptor_schema_version
            == binding.vector_descriptor_schema_version,
            manifest.vector_generation == binding.vector_generation,
            manifest.vector_descriptor_sha256
            == binding.vector_descriptor_sha256,
            manifest.vector_bytes == binding.vector_bytes,
            manifest.vector_ids_bytes == binding.vector_ids_bytes,
            manifest.indexed_at_epoch_s == binding.indexed_at_epoch_s,
            manifest.operational_schema_version
            == operational.operational_version,
            manifest.operation_mode == binding.operation_mode,
            manifest.work_metrics == binding.work_metrics,
            manifest.total_files == operational.source_count,
            manifest.total_chunks == operational.chunk_count,
        )
    )


def _vector_matches_bound_snapshot(
    manifest: ManifestV2,
    operational: OperationalSnapshot,
    snapshot: PublishedVectorDescriptor | None,
) -> bool:
    if snapshot is None:
        return False
    descriptor = snapshot.descriptor
    binding = operational.binding
    return all(
        (
            descriptor.schema_version == binding.vector_descriptor_schema_version,
            descriptor.generation == binding.vector_generation,
            snapshot.sha256 == binding.vector_descriptor_sha256,
            descriptor.vectors_bytes == binding.vector_bytes,
            descriptor.ids_bytes == binding.vector_ids_bytes,
            descriptor.schema_version == manifest.vector_descriptor_schema_version,
            descriptor.generation == manifest.vector_generation,
            snapshot.sha256 == manifest.vector_descriptor_sha256,
            descriptor.row_count == len(operational.active_embedding_ids),
            descriptor.dimensions == manifest.embedding_dimensions,
            _descriptor_embedding_matches(descriptor.embedding_identity, manifest),
        )
    )


def _descriptor_embedding_matches(identity: str, manifest: ManifestV2) -> bool:
    return identity in {
        manifest.embedding_config_hash,
        f"{manifest.embedding_model}:{manifest.embedding_dimensions}",
    }


def _indexed_file_observation(
    item: OperationalSourceObservation,
) -> IndexedFileObservation:
    return IndexedFileObservation(
        path=item.path.as_posix(),
        language=item.language,
        size=item.size,
        mtime_ns=item.mtime_ns,
        change_token=item.change_token,
        change_token_kind=item.change_token_kind,
        sha256=item.sha256,
    )


def _coverage_skip_observation(
    item: OperationalScanSkip,
) -> CoverageSkipObservation:
    metadata = (
        StableFileMetadata(
            size=item.size,
            mtime_ns=item.mtime_ns,
            change_token=item.change_token,
            change_token_kind=item.change_token_kind,
            device=0,
            inode=0,
            mode=0,
        )
        if item.size is not None and item.mtime_ns is not None
        else None
    )
    return CoverageSkipObservation(
        path=item.path,
        language=item.language or "",
        reason=item.reason,
        retryable=item.retryable,
        metadata=metadata,
    )


def _indexed_embedding(manifest: Manifest | ManifestV2) -> EmbeddingIdentity:
    if manifest.embedding_provider == "hash":
        return EmbeddingIdentity.hash_v1(
            manifest.embedding_config_hash,
            manifest.embedding_dimensions,
        )
    return EmbeddingIdentity(
        status="valid",
        provider=manifest.embedding_provider,
        model=manifest.embedding_model,
        dimensions=manifest.embedding_dimensions,
        config_hash=manifest.embedding_config_hash,
        network_egress_capable=True,
        network_egress_evidence="persisted_manifest",
    )


def indexed_embedding_identity(
    manifest: Manifest | ManifestV2,
) -> EmbeddingIdentity:
    return _indexed_embedding(manifest)


def configured_embedding_identity(config: ToolConfig) -> EmbeddingIdentity:
    embedding = config.embedding
    identity = EmbeddingIdentity(
        status="valid",
        provider=embedding.provider,
        model=embedding.model,
        dimensions=embedding.dimensions,
        config_hash=embedding_config_hash(embedding),
        network_egress_capable=embedding.provider != "hash",
        network_egress_evidence=(
            "built_in_hash"
            if embedding.provider == "hash"
            else (
                "configured_network_provider"
                if embedding.provider in {"openai-compatible", "bge"}
                else "unknown_provider"
            )
        ),
    )
    identity._validate()
    return identity


def _legacy_committed_snapshot(
    store: SQLiteStore,
    index_dir: Path,
    manifest: Manifest,
) -> CommittedIndexSnapshot:
    sources = store.source_files_snapshot()
    graph = read_graph_capability(store)
    active_ids = tuple(sorted(store.active_embedding_ids()))
    try:
        descriptor_snapshot = NumpyVectorStore.inspect_published_descriptor(
            index_dir
        )
    except VectorDescriptorCorruptionError:
        descriptor_snapshot = None
    descriptor = (
        descriptor_snapshot.descriptor
        if descriptor_snapshot is not None
        else None
    )
    vector_valid = descriptor is not None and (
        descriptor.embedding_identity == manifest.embedding_config_hash
        and descriptor.row_count == len(active_ids)
        and descriptor.dimensions == manifest.embedding_dimensions
    )
    raw_indexed_at = store.get_metadata("indexed_at")
    try:
        indexed_at = int(raw_indexed_at) if raw_indexed_at is not None else None
    except ValueError:
        indexed_at = None
    return CommittedIndexSnapshot(
        ready_generation=(descriptor.generation if descriptor is not None else "legacy-v1"),
        manifest_version=1,
        operational_version=None,
        graph_version=graph.schema_version,
        graph_status=graph.status,
        graph_stale_reason=graph.stale_reason,
        queryable=graph.status in {"legacy", "ready"} and vector_valid,
        indexed_at_epoch_s=indexed_at,
        indexed_files=tuple(
            IndexedFileObservation(
                path=item.path.as_posix(),
                language=item.language,
                size=item.size,
                mtime_ns=item.mtime_ns,
                change_token=None,
                change_token_kind="unavailable",
                sha256=item.sha256,
            )
            for item in sources
        ),
        coverage_skips=(),
        eligible_chunks=manifest.total_chunks,
        vector_rows=descriptor.row_count if descriptor is not None else 0,
        vector_generation=descriptor.generation if descriptor is not None else "",
        vector_dimensions=(
            descriptor.dimensions if descriptor is not None else manifest.embedding_dimensions
        ),
        manifest_valid=True,
        sqlite_valid=True,
        vector_identity_valid=vector_valid,
        indexed_embedding=_indexed_embedding(manifest),
        active_embedding_ids=active_ids,
        vector_generation_count=(
            1
            + NumpyVectorStore.unreferenced_generation_count(
                index_dir,
                keep_generation=descriptor.generation,
            )
            if descriptor is not None
            else NumpyVectorStore.generation_pair_count(index_dir)
        ),
    )


def _unbound_v2_snapshot(
    store: SQLiteStore,
    index_dir: Path,
    manifest: ManifestV2,
) -> CommittedIndexSnapshot:
    graph = read_graph_capability(store)
    active_ids = tuple(sorted(store.active_embedding_ids()))
    try:
        descriptor_snapshot = NumpyVectorStore.inspect_published_descriptor(index_dir)
    except VectorDescriptorCorruptionError:
        descriptor_snapshot = None
    descriptor = (
        descriptor_snapshot.descriptor if descriptor_snapshot is not None else None
    )
    return CommittedIndexSnapshot(
        ready_generation=manifest.manifest_generation,
        manifest_version=2,
        operational_version=None,
        graph_version=graph.schema_version,
        graph_status=graph.status,
        graph_stale_reason=graph.stale_reason or "migration_incomplete",
        queryable=False,
        indexed_at_epoch_s=manifest.indexed_at_epoch_s,
        indexed_files=(),
        coverage_skips=(),
        eligible_chunks=manifest.total_chunks,
        vector_rows=descriptor.row_count if descriptor is not None else 0,
        vector_generation=manifest.vector_generation,
        vector_dimensions=manifest.embedding_dimensions,
        manifest_valid=True,
        sqlite_valid=False,
        vector_identity_valid=False,
        indexed_embedding=_indexed_embedding(manifest),
        active_embedding_ids=active_ids,
        index_config_hash=manifest.index_config_hash,
        vector_generation_count=(
            1
            + NumpyVectorStore.unreferenced_generation_count(
                index_dir,
                keep_generation=manifest.vector_generation,
            )
        ),
    )


@dataclass(frozen=True)
class WriterProbe:
    active: bool | None
    state: str
    evidence: str

    @classmethod
    def idle(cls) -> WriterProbe:
        return cls(False, "idle", "lock_probe")

    @classmethod
    def active_writer(cls) -> WriterProbe:
        return cls(True, "active", "lock_probe")

    @classmethod
    def unknown(cls, evidence: str = "lock_probe_unavailable") -> WriterProbe:
        return cls(None, "unknown", evidence)


@dataclass(frozen=True)
class InspectionAdapters:
    raw_probe: Callable[[Path], RawIndexCapability]
    snapshot_reader: Callable[[Path], CommittedIndexSnapshot]
    inventory_reader: Callable[[Path, Any], WorkspaceInventory]
    file_reader: Callable[..., ObservedFileRead]
    vector_verifier: Callable[[Path, CommittedIndexSnapshot], VectorVerification]
    configured_embedding_reader: Callable[[Path], EmbeddingIdentity]
    writer_probe: Callable[[Path], WriterProbe]
    clock_ms: Callable[[], int]
    max_file_bytes: int = 16 * 1024 * 1024
    configured_index_hash_reader: Callable[[Path], str | None] | None = None
    snapshot_rechecker: (
        Callable[[Path, CommittedIndexSnapshot], CommittedIndexSnapshot] | None
    ) = None


def inspect_index_health(
    repo: Path,
    *,
    mode: str,
    adapters: InspectionAdapters,
) -> IndexHealthReport:
    if mode not in {"quick", "verified"}:
        raise ValueError("inspection mode must be quick or verified")
    raw = adapters.raw_probe(repo)
    if raw.status != "compatible":
        return _preflight_report(raw)

    started = adapters.clock_ms()
    configured_embedding = adapters.configured_embedding_reader(repo)
    configured_index_hash = (
        adapters.configured_index_hash_reader(repo)
        if adapters.configured_index_hash_reader is not None
        else None
    )
    opening_snapshot = adapters.snapshot_reader(repo)
    opening_inventory = adapters.inventory_reader(repo, None)
    content_results: dict[str, ObservedFileRead] = {}
    vector_result: VectorVerification | None = None
    if mode == "verified":
        for observation in opening_inventory.eligible:
            content_results[observation.path.as_posix()] = adapters.file_reader(
                repo,
                observation,
                max_file_bytes=adapters.max_file_bytes,
                require_utf8=True,
            )
        vector_result = adapters.vector_verifier(repo, opening_snapshot)
    closing_inventory = adapters.inventory_reader(repo, None)
    closing_snapshot = (
        adapters.snapshot_rechecker(repo, opening_snapshot)
        if adapters.snapshot_rechecker is not None
        else adapters.snapshot_reader(repo)
    )
    writer = adapters.writer_probe(repo)
    completed = adapters.clock_ms()
    return _observed_report(
        mode=mode,
        started=started,
        completed=completed,
        raw=raw,
        opening_snapshot=opening_snapshot,
        closing_snapshot=closing_snapshot,
        opening_inventory=opening_inventory,
        closing_inventory=closing_inventory,
        content_results=content_results,
        vector_result=vector_result,
        configured_embedding=configured_embedding,
        configured_index_hash=configured_index_hash,
        writer=writer,
    )


def inspect_repository_health(repo: Path, *, mode: str) -> IndexHealthReport:
    """Inspect repository health without creating index or configuration files."""
    if mode not in {"quick", "verified"}:
        raise ValueError("inspection mode must be quick or verified")
    capability = preflight_public_operation(repo, "status")
    if capability.status != "compatible":
        return _preflight_report(capability)

    config, configured_embedding = _read_inspection_configuration(repo)
    adapters = InspectionAdapters(
        raw_probe=lambda _repo: capability,
        snapshot_reader=read_committed_index_snapshot,
        inventory_reader=lambda inspected_repo, _unused: observe_workspace(
            inspected_repo,
            config,
        ),
        file_reader=lambda inspected_repo, observation, **kwargs: read_observed_file(
            inspected_repo,
            observation,
            retain_content=False,
            **kwargs,
        ),
        vector_verifier=verify_committed_vector_snapshot,
        configured_embedding_reader=lambda _repo: configured_embedding,
        writer_probe=probe_writer_state,
        clock_ms=lambda: time.time_ns() // 1_000_000,
        max_file_bytes=config.index.max_file_bytes,
        configured_index_hash_reader=lambda _repo: index_config_hash(config),
        snapshot_rechecker=recheck_committed_index_snapshot,
    )
    return inspect_index_health(repo, mode=mode, adapters=adapters)


def quick_refresh_noop_health_report(
    repo: Path,
    *,
    loaded_manifest: LoadedManifestSnapshot,
    operational: OperationalSnapshot,
    descriptor: PublishedVectorDescriptor,
    opening_inventory: WorkspaceInventory,
    closing_inventory: WorkspaceInventory,
    configured_embedding: EmbeddingIdentity,
    configured_index_hash: str,
    started_at_epoch_ms: int,
    completed_at_epoch_ms: int,
) -> IndexHealthReport:
    """Reuse a completed, no-write refresh observation as quick health evidence."""
    resolved = repo.resolve(strict=True)
    snapshot = _committed_v2_snapshot(
        resolved,
        loaded_manifest,
        operational,
        descriptor,
    )
    raw = RawIndexCapability(
        status="compatible",
        index_exists=True,
        manifest_version=snapshot.manifest_version,
        operational_version=snapshot.operational_version,
        graph_version=snapshot.graph_version,
        error_code=None,
    )
    return _observed_report(
        mode="quick",
        started=started_at_epoch_ms,
        completed=completed_at_epoch_ms,
        raw=raw,
        opening_snapshot=snapshot,
        closing_snapshot=snapshot,
        opening_inventory=opening_inventory,
        closing_inventory=closing_inventory,
        content_results={},
        vector_result=None,
        configured_embedding=configured_embedding,
        configured_index_hash=configured_index_hash,
        writer=WriterProbe.idle(),
    )


def status_success_envelope(
    repo: str,
    report: IndexHealthReport,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ok": True,
        "repo": repo,
        "index_health": serialize_index_health(report),
    }


def status_error_envelope(code: str) -> dict[str, Any]:
    messages = {
        "repo_not_found": "repository root was not found",
        "status_failed": "status inspection failed",
    }
    if code not in messages:
        raise ValueError("unknown status error code")
    return {
        "schema_version": 1,
        "ok": False,
        "error": {"code": code, "message": messages[code]},
    }


_REFRESH_ERROR_MESSAGES = {
    "repo_not_found": "repository root was not found",
    "missing_index": "an existing v2 index is required",
    "incompatible_manifest_schema": "manifest schema is incompatible",
    "incompatible_operational_schema": "operational schema is incompatible",
    "incompatible_signal_schema": "signal schema is incompatible",
    "index_busy": "another index writer is active",
    "authoritative_index_required": "authoritative indexing is required",
    "inventory_incomplete": "repository inventory is incomplete",
    "workspace_changed": "repository changed during refresh",
    "refresh_failed": "refresh failed",
}
_REFRESH_EGRESS_OUTCOMES = frozenset({"not_attempted", "possible", "performed"})


def refresh_error_envelope(
    code: str,
    network_egress_outcome: str = "not_attempted",
) -> dict[str, Any]:
    if code not in _REFRESH_ERROR_MESSAGES:
        code = "refresh_failed"
    if network_egress_outcome not in _REFRESH_EGRESS_OUTCOMES:
        network_egress_outcome = "possible"
    return {
        "schema_version": 1,
        "ok": False,
        "error": {
            "code": code,
            "message": _REFRESH_ERROR_MESSAGES[code],
            "network_egress_outcome": network_egress_outcome,
        },
    }


def refresh_success_envelope(
    repo: str,
    *,
    summary: Any,
    indexed_before: EmbeddingIdentity,
    configured: EmbeddingIdentity,
    network_egress_performed: bool,
    report: IndexHealthReport,
) -> dict[str, Any]:
    summary_payload = summary.to_dict()
    indexed_before._validate()
    configured._validate()
    if _embedding_key(indexed_before) != _embedding_key(configured):
        raise ValueError("refresh embedding identity mismatch")
    if type(network_egress_performed) is not bool:
        raise ValueError("refresh network egress fact must be boolean")
    embedded_chunks = summary_payload["chunks"]["embedded"]
    if type(embedded_chunks) is not int or embedded_chunks < 0:
        raise ValueError("refresh embedded chunk count is invalid")
    return {
        "schema_version": 1,
        "ok": True,
        "repo": repo,
        "summary": summary_payload,
        "embedding": {
            "indexed_before": serialize_embedding_identity(indexed_before),
            "configured": serialize_embedding_identity(configured),
            "network_egress_performed": network_egress_performed,
            "embedded_chunks": embedded_chunks,
        },
        "index_health": serialize_index_health(report),
    }


def format_refresh_human(envelope: Mapping[str, Any]) -> str:
    if envelope.get("ok") is not True:
        raise ValueError("refresh success envelope is required")
    summary = _mapping(envelope.get("summary"), "refresh summary")
    files = _mapping(summary.get("files"), "refresh files")
    embedding = _mapping(envelope.get("embedding"), "refresh embedding")
    health = _mapping(envelope.get("index_health"), "refresh health")
    freshness = _mapping(health.get("freshness"), "refresh freshness")
    return (
        f"Refreshed {envelope['repo']}: "
        f"direct_dirty={files['direct_dirty']} "
        f"content_changed={files['content_changed']} "
        f"metadata_only={files['metadata_only']} "
        f"dependent={files['dependent_rebuild']} "
        f"deleted={files['deleted']} parsed={files['parsed']} "
        f"embedded={embedding['embedded_chunks']}; "
        f"freshness={freshness['status']} health={health['health']}"
    )


def status_requirement_satisfied(
    report: IndexHealthReport,
    requirement: str,
) -> bool:
    if requirement == "verified":
        return report.health == Health.HEALTHY_VERIFIED
    if requirement == "metadata":
        return report.health in {
            Health.HEALTHY_METADATA,
            Health.HEALTHY_VERIFIED,
        }
    if requirement == "queryable":
        return report.queryable
    raise ValueError("requirement must be verified, metadata, or queryable")


def format_index_health_human(repo: Path, report: IndexHealthReport) -> str:
    freshness = report.freshness
    coverage = report.coverage
    integrity = report.integrity
    vectors = report.vectors
    lines = [
        f"Repository: {repo}",
        f"Health: {report.health}",
        (
            f"Queryable: {_human_bool(report.queryable)} "
            f"({report.queryability_evidence})"
        ),
        f"Availability: {report.availability}",
        (
            f"Freshness: {freshness.status} "
            f"(inspection={freshness.inspection_mode}, "
            f"generation={freshness.evidence_generation or 'unknown'})"
        ),
        (
            f"Changes: added={_human_value(freshness.added)} "
            f"changed={_human_value(freshness.changed)} "
            f"deleted={_human_value(freshness.deleted)} "
            f"content_verified={_human_value(freshness.content_verified)}"
        ),
        (
            f"Coverage: {coverage.status} ({coverage.evidence}); "
            f"indexed={_human_value(coverage.indexed_files)} "
            f"skipped={_human_value(coverage.coverage_skips)} "
            f"pending={_human_value(coverage.pending_inspection)}"
        ),
        (
            f"Integrity: {integrity.status}; manifest={integrity.manifest} "
            f"sqlite={integrity.sqlite} graph={integrity.graph} "
            f"vector={integrity.vector}"
        ),
        (
            f"Vectors: rows={_human_value(vectors.rows)}/"
            f"{_human_value(vectors.eligible_chunks)} "
            f"coverage={_human_value(vectors.coverage_ratio)} "
            f"evidence={vectors.coverage_evidence}"
        ),
        f"Indexed embedding: {_human_embedding(report.indexed_embedding)}",
        f"Configured embedding: {_human_embedding(report.configured_embedding)}",
        f"Embedding match: {_human_value(report.embedding_config_match)}",
        (
            f"Writer: {report.writer.state} "
            f"(active={_human_value(report.writer.active)}, "
            f"evidence={report.writer.evidence})"
        ),
        (
            "Refresh reasons: "
            + (", ".join(report.refresh.reasons) or "(none)")
        ),
        f"Recommended action: {report.refresh.recommended_action}",
    ]
    if report.observation.limitations:
        lines.append(
            "Limitations: " + ", ".join(report.observation.limitations)
        )
    if freshness.samples:
        lines.extend(
            f"Sample: {item.category} {item.path} ({item.reason})"
            for item in freshness.samples
        )
    if coverage.skip_samples:
        lines.extend(
            f"Skip: {item.path} ({item.reason}, retryable={_human_bool(item.retryable)})"
            for item in coverage.skip_samples
        )
    return "\n".join(lines)


def build_index_stats_payload(
    repo: Path,
    report: IndexHealthReport,
) -> dict[str, Any]:
    capability = preflight_public_operation(repo, "stats")
    if report.health == Health.CORRUPT:
        raise IndexCorruptionError()
    index_dir = repo.resolve(strict=True) / ".context-search"
    counts = SQLiteStore(index_dir / "index.sqlite").stats()
    disk_components = index_disk_components(index_dir)
    identity = report.indexed_embedding
    if identity.status != "valid":
        raise IndexCorruptionError()
    last_work: dict[str, Any] | None = None
    if capability.manifest_version == 2:
        manifest = load_manifest_snapshot(repo).manifest
        if not isinstance(manifest, ManifestV2):
            raise IndexCorruptionError()
        last_work = {
            "operation": manifest.operation_mode,
            "indexed_at_epoch_s": manifest.indexed_at_epoch_s,
            "observation_generation": manifest.observation_generation,
            "metrics": dict(manifest.work_metrics),
        }
    return {
        "ok": True,
        "repo": str(repo),
        "stats": {
            "total_files": counts["source_files"],
            "total_chunks": counts["active_chunks"],
            "deleted_chunks": counts["deleted_chunks"],
            "symbols": counts["symbols"],
            "lexical_tokens": counts["tokens"],
            "disk_usage_bytes": disk_components["total_bytes"],
            "indexed_files": report.coverage.indexed_files,
            "coverage_skips": report.coverage.coverage_skips,
            "vector_rows": report.vectors.rows,
            "vector_eligible_chunks": report.vectors.eligible_chunks,
            "vector_coverage_ratio": report.vectors.coverage_ratio,
            "vector_coverage_evidence": report.vectors.coverage_evidence,
            "manifest_schema_version": capability.manifest_version,
            "operational_schema_version": capability.operational_version,
            "graph_schema_version": capability.graph_version,
            "disk_components": disk_components,
            "last_work": last_work,
        },
        "embedding": {
            "provider": identity.provider,
            "model": identity.model,
            "dimensions": identity.dimensions,
        },
        "index_health": serialize_index_health(report),
    }


def index_disk_components(index_dir: Path) -> dict[str, int]:
    components = {
        "sqlite_bytes": 0,
        "vector_bytes": 0,
        "manifest_bytes": 0,
        "config_bytes": 0,
        "feedback_bytes": 0,
        "other_bytes": 0,
    }
    if index_dir.is_symlink() or not index_dir.is_dir():
        return {**components, "total_bytes": 0}
    for path in index_dir.rglob("*"):
        try:
            path_stat = path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(path_stat.st_mode):
            continue
        name = path.name
        if name == "index.sqlite" or name.startswith("index.sqlite-"):
            key = "sqlite_bytes"
        elif name == "manifest.json":
            key = "manifest_bytes"
        elif name == "config.toml":
            key = "config_bytes"
        elif (
            name == "vector_snapshot.json"
            or name.startswith("vectors.")
            or name.startswith("vector_ids.")
            or name in {"vectors.npy", "vector_ids.json"}
        ):
            key = "vector_bytes"
        elif name.endswith(".jsonl") or name.endswith(".log"):
            key = "feedback_bytes"
        else:
            key = "other_bytes"
        components[key] += path_stat.st_size
    return {**components, "total_bytes": sum(components.values())}


def probe_writer_state(repo: Path) -> WriterProbe:
    lock_path = repo.resolve(strict=True) / ".context-search" / "index.lock"
    if not os.path.lexists(lock_path):
        return WriterProbe.idle()
    descriptor: int | None = None
    locked = False
    try:
        path_stat = os.lstat(lock_path)
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            return WriterProbe.unknown()
        if hasattr(os, "getuid") and path_stat.st_uid != os.getuid():
            return WriterProbe.unknown()
        if stat.S_IMODE(path_stat.st_mode) != 0o600:
            return WriterProbe.unknown()
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags)
        descriptor_stat = os.fstat(descriptor)
        final_stat = os.lstat(lock_path)
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or stat.S_ISLNK(final_stat.st_mode)
            or (descriptor_stat.st_dev, descriptor_stat.st_ino)
            != (final_stat.st_dev, final_stat.st_ino)
        ):
            return WriterProbe.unknown()
        locked = _try_lock_descriptor(descriptor)
        return WriterProbe.idle() if locked else WriterProbe.active_writer()
    except OSError:
        return WriterProbe.unknown()
    finally:
        if descriptor is not None:
            if locked:
                _unlock_probe_descriptor(descriptor)
            os.close(descriptor)


def _read_inspection_configuration(
    repo: Path,
) -> tuple[ToolConfig, EmbeddingIdentity]:
    config_path = repo.resolve(strict=True) / ".context-search" / "config.toml"
    if not os.path.lexists(config_path):
        return DEFAULT_CONFIG, _nonvalid_embedding("missing", "config_missing")
    try:
        config_stat = os.lstat(config_path)
    except OSError:
        return DEFAULT_CONFIG, _nonvalid_embedding("invalid", "config_invalid")
    if stat.S_ISLNK(config_stat.st_mode) or not stat.S_ISREG(config_stat.st_mode):
        return DEFAULT_CONFIG, _nonvalid_embedding("invalid", "config_invalid")
    try:
        config = read_config(repo)
    except (OSError, TypeError, ValueError):
        return DEFAULT_CONFIG, _nonvalid_embedding("invalid", "config_invalid")
    try:
        identity = configured_embedding_identity(config)
    except (TypeError, ValueError):
        return config, _nonvalid_embedding("invalid", "config_invalid")
    return config, identity


def _try_lock_descriptor(descriptor: int) -> bool:
    if os.name == "posix":
        try:
            import fcntl
        except ImportError:
            raise OSError("lock probing is unavailable")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                return False
            raise
        return True
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI only
        import msvcrt

        if os.fstat(descriptor).st_size < 1:
            raise OSError("lock probing is unavailable")
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    raise OSError("lock probing is unavailable")


def _unlock_probe_descriptor(descriptor: int) -> None:
    if os.name == "posix":
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)
    elif os.name == "nt":  # pragma: no cover - exercised on Windows CI only
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


def _human_embedding(identity: EmbeddingIdentity) -> str:
    if identity.status != "valid":
        return f"{identity.status} ({identity.network_egress_evidence})"
    return (
        f"provider={identity.provider} model={identity.model} "
        f"dimensions={identity.dimensions} "
        f"network_egress_capable={_human_bool(identity.network_egress_capable)}"
    )


def _human_bool(value: bool) -> str:
    return "true" if value else "false"


def _human_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if type(value) is bool:
        return _human_bool(value)
    return str(value)


def _preflight_report(capability: RawIndexCapability) -> IndexHealthReport:
    missing = capability.status == "missing"
    incompatible = capability.status == "incompatible"
    availability = (
        "missing" if missing else "incompatible" if incompatible else "corrupt"
    )
    health = availability
    manifest_integrity = "missing" if missing else "not_inspected"
    sqlite_integrity = "missing" if missing else "not_inspected"
    graph_integrity = "missing" if missing else "not_inspected"
    if capability.error_code == "future_manifest_schema":
        manifest_integrity = "incompatible"
    elif capability.error_code == "future_operational_schema":
        manifest_integrity = "valid"
        sqlite_integrity = "incompatible"
    elif capability.error_code == "future_graph_schema":
        manifest_integrity = "valid"
        sqlite_integrity = "valid_quick"
        graph_integrity = "incompatible"
    elif not missing and not incompatible:
        manifest_errors = {
            "missing_manifest",
            "unsafe_manifest",
            "manifest_too_large",
            "unreadable_manifest",
            "manifest_changed",
            "malformed_manifest",
            "invalid_manifest_schema",
        }
        if capability.error_code in manifest_errors:
            manifest_integrity = "invalid"
        elif capability.error_code == "invalid_graph_schema":
            manifest_integrity = "valid"
            sqlite_integrity = "valid_quick"
            graph_integrity = "invalid"
        elif capability.error_code not in {None, "unsafe_index_directory"}:
            manifest_integrity = "valid"
            sqlite_integrity = "invalid"
    indexed_embedding = (
        _nonvalid_embedding("missing", "index_missing")
        if missing
        else _nonvalid_embedding("not_inspected", "not_inspected")
    )
    raw = {
        "schema_version": 1,
        "health": health,
        "queryable": False,
        "queryability_evidence": "none",
        "availability": availability,
        "observation": {
            "started_at_epoch_ms": None,
            "completed_at_epoch_ms": None,
            "inventory_status": "not_inspected",
            "unscannable_subtree_count": None,
            "control_file_error_count": None,
            "change_token_kind": None,
            "limitations": None,
        },
        "freshness": {
            "status": "unknown",
            "inspection_mode": "none",
            "indexed_at_epoch_s": None,
            "age_seconds": None,
            "added": None,
            "changed": None,
            "deleted": None,
            "metadata_unchanged": None,
            "content_verified": None,
            "samples": None,
            "sample_limit": 20,
            "sampled_total": None,
            "evidence_generation": None,
        },
        "coverage": {
            "status": "unknown",
            "evidence": "not_inspected",
            "indexed_files": None,
            "coverage_skips": None,
            "pending_inspection": None,
            "pending_retry": None,
            "skip_counts": None,
            "skip_samples": None,
            "excluded_counts": None,
        },
        "integrity": {
            "status": "unchecked",
            "manifest": manifest_integrity,
            "sqlite": sqlite_integrity,
            "graph": graph_integrity,
            "graph_stale_reason": None,
            "vector": "missing" if missing else "not_inspected",
        },
        "vectors": {
            "generation": None,
            "eligible_chunks": None,
            "rows": None,
            "coverage_ratio": None,
            "coverage_evidence": "not_inspected",
            "missing_ids": None,
            "orphan_ids": None,
            "dimensions": None,
        },
        "indexed_embedding": _embedding_dict(indexed_embedding),
        "configured_embedding": _embedding_dict(
            _nonvalid_embedding("not_inspected", "not_inspected")
        ),
        "embedding_config_match": None,
        "refresh": {
            "required": True,
            "kind": "authoritative",
            "reasons": [],
            "recommended_action": (
                "index" if not incompatible else "use_compatible_version"
            ),
        },
        "writer": {
            "active": None,
            "state": "not_inspected",
            "evidence": "not_inspected",
        },
        "diagnostics": None,
    }
    return IndexHealthReport.from_dict(raw)


def _observed_report(
    *,
    mode: str,
    started: int,
    completed: int,
    raw: RawIndexCapability,
    opening_snapshot: CommittedIndexSnapshot,
    closing_snapshot: CommittedIndexSnapshot,
    opening_inventory: WorkspaceInventory,
    closing_inventory: WorkspaceInventory,
    content_results: Mapping[str, ObservedFileRead],
    vector_result: VectorVerification | None,
    configured_embedding: EmbeddingIdentity,
    configured_index_hash: str | None,
    writer: WriterProbe,
) -> IndexHealthReport:
    del raw
    snapshot_stable = opening_snapshot == closing_snapshot
    inventory_stable = _inventory_identity(opening_inventory) == _inventory_identity(
        closing_inventory
    )
    complete_inventory = opening_inventory.complete and closing_inventory.complete
    generation_stable = snapshot_stable and inventory_stable
    verification_interrupted = any(
        result.reason == "changed_during_read" for result in content_results.values()
    ) or (vector_result is not None and vector_result.status == "interrupted") or (
        mode == "verified" and not generation_stable
    )
    interrupted = (
        not generation_stable
        or writer.active is not False
        or verification_interrupted
    )

    indexed = {item.path: item for item in opening_snapshot.indexed_files}
    observed = {
        item.path.as_posix(): item for item in opening_inventory.eligible
    }
    samples: list[dict[str, str]] = []
    if complete_inventory:
        added_paths = sorted(set(observed) - set(indexed))
        deleted_paths = sorted(set(indexed) - set(observed))
        metadata_changed = sorted(
            path
            for path in set(observed) & set(indexed)
            if not _metadata_equal(observed[path], indexed[path])
        )
    else:
        added_paths = []
        deleted_paths = []
        metadata_changed = []

    content_changed: list[str] = []
    metadata_only: list[str] = []
    content_verified = 0
    if mode == "verified":
        for path, result in sorted(content_results.items()):
            if result.status != "read" or result.sha256 is None:
                continue
            content_verified += 1
            expected = indexed.get(path)
            if expected is None:
                continue
            if expected.sha256 != result.sha256:
                content_changed.append(path)
            elif path in metadata_changed:
                metadata_only.append(path)
        changed_paths = sorted(set(content_changed) | set(metadata_only))
    else:
        changed_paths = metadata_changed

    for path in added_paths:
        samples.append({"category": "added", "path": path, "reason": "source_changed"})
    for path in changed_paths:
        samples.append(
            {
                "category": "metadata_only" if path in metadata_only else "changed",
                "path": path,
                "reason": "source_changed",
            }
        )
    for path in deleted_paths:
        samples.append(
            {"category": "deleted", "path": path, "reason": "path_inventory_changed"}
        )

    current_skips = {item.path.as_posix(): item for item in opening_inventory.coverage_skips}
    if mode == "verified":
        for path, result in content_results.items():
            if result.status == "skipped" and result.reason is not None:
                observation = observed[path]
                current_skips[path] = CoverageSkipObservation(
                    path=observation.path,
                    language=observation.language,
                    reason=result.reason,
                    retryable=result.retryable,
                    metadata=result.metadata,
                )
    prior_skip_paths = {
        item.path.as_posix(): item for item in opening_snapshot.coverage_skips
    }
    skip_counts = {reason: 0 for reason in SKIP_REASON_ORDER}
    for item in current_skips.values():
        if item.reason in skip_counts:
            skip_counts[item.reason] += 1
    skip_samples = [
        {
            "path": path,
            "reason": item.reason,
            "retryable": item.retryable,
        }
        for path, item in sorted(current_skips.items())
    ]
    pending_retry = sum(item.retryable for item in current_skips.values())
    pending_inspection = (
        len(added_paths) + len(metadata_changed) if mode == "quick" else 0
    )
    coverage_degraded = bool(current_skips or pending_inspection or pending_retry)

    stable_artifact_invalid = not all(
        (
            opening_snapshot.manifest_valid,
            opening_snapshot.sqlite_valid,
            opening_snapshot.vector_identity_valid,
        )
    ) or (vector_result is not None and vector_result.status == "invalid")
    confirmed_corrupt = (
        stable_artifact_invalid
        and generation_stable
        and complete_inventory
        and writer.active is False
        and not verification_interrupted
    )
    legacy = opening_snapshot.manifest_version == 1
    graph_stale = opening_snapshot.graph_status in {"stale", "unfinished"}
    index_config_changed = (
        opening_snapshot.index_config_hash is not None
        and configured_index_hash is not None
        and opening_snapshot.index_config_hash != configured_index_hash
    )
    has_delta = bool(
        added_paths or deleted_paths or changed_paths or index_config_changed
    )

    if confirmed_corrupt:
        integrity_status = "invalid"
    elif interrupted or not complete_inventory or legacy:
        integrity_status = "unchecked"
    else:
        integrity_status = "valid_verified" if mode == "verified" else "valid_quick"
    if confirmed_corrupt:
        freshness_status = "unknown"
    elif graph_stale or has_delta:
        freshness_status = "stale"
    elif interrupted or not complete_inventory or legacy:
        freshness_status = "unknown"
    else:
        freshness_status = (
            "verified_fresh" if mode == "verified" else "metadata_fresh"
        )
    coverage_status = (
        "unknown" if legacy else "degraded" if coverage_degraded else "complete"
    )
    inventory_status = "complete" if complete_inventory else "incomplete"
    availability = "corrupt" if confirmed_corrupt else "present"
    derived = derive_health(
        HealthDerivation(
            availability=availability,
            freshness=freshness_status,
            coverage=coverage_status,
            integrity=integrity_status,
            inventory=inventory_status,
            graph=opening_snapshot.graph_status,
            writer_active=writer.active,
            generation_stable=generation_stable,
        )
    )

    refresh_reasons: list[str] = []
    if has_delta:
        if changed_paths or added_paths:
            refresh_reasons.append("source_changed")
        if added_paths or deleted_paths:
            refresh_reasons.append("path_inventory_changed")
    if set(current_skips) != set(prior_skip_paths) or any(
        current_skips[path].reason != prior_skip_paths[path].reason
        for path in set(current_skips) & set(prior_skip_paths)
    ):
        refresh_reasons.append("coverage_changed")
    if graph_stale:
        refresh_reasons.append("graph_stale")
    if index_config_changed:
        refresh_reasons.append("index_config_changed")
    if legacy:
        refresh_reasons.append("manifest_upgrade")
    if confirmed_corrupt:
        refresh_reasons.append("integrity_failed")
    embedding_match = (
        _embedding_key(opening_snapshot.indexed_embedding)
        == _embedding_key(configured_embedding)
        if opening_snapshot.indexed_embedding.status
        == configured_embedding.status
        == "valid"
        else None
    )
    if embedding_match is False:
        refresh_reasons.append("embedding_config_changed")
    if not complete_inventory:
        refresh_reasons.append("inventory_incomplete")

    if interrupted and not graph_stale:
        refresh_required = False
        refresh_kind = "none"
        action = "retry_inspection"
    elif not complete_inventory:
        refresh_required = False
        refresh_kind = "none"
        action = "retry_inspection"
    elif any(
        reason
        in {
            "index_config_changed",
            "embedding_config_changed",
            "manifest_upgrade",
            "integrity_failed",
        }
        for reason in refresh_reasons
    ):
        refresh_required = True
        refresh_kind = "authoritative"
        action = "index"
    elif refresh_reasons:
        refresh_required = True
        refresh_kind = "quick"
        action = "refresh"
    else:
        refresh_required = False
        refresh_kind = "none"
        action = "query"

    diagnostics = [
        {"code": item.code, "scope": item.scope, "path": item.path}
        for item in (*opening_inventory.diagnostics, *closing_inventory.diagnostics)
    ]
    if legacy:
        diagnostics.append({"code": "legacy_manifest", "scope": "manifest", "path": None})
    if not complete_inventory:
        diagnostics.append(
            {"code": "inventory_incomplete", "scope": "inventory", "path": None}
        )
    if not snapshot_stable:
        diagnostics.append(
            {"code": "inspection_interrupted", "scope": "generation", "path": None}
        )
    elif writer.active is True:
        diagnostics.append(
            {"code": "inspection_interrupted", "scope": "writer", "path": None}
        )
    elif writer.active is None:
        diagnostics.append(
            {"code": "writer_state_unknown", "scope": "writer", "path": None}
        )
    if verification_interrupted:
        diagnostics.append(
            {"code": "verification_interrupted", "scope": "inventory", "path": None}
        )
    if confirmed_corrupt and not opening_snapshot.manifest_valid:
        diagnostics.append(
            {"code": "manifest_identity_mismatch", "scope": "manifest", "path": None}
        )
    if confirmed_corrupt and (
        not opening_snapshot.vector_identity_valid
        or (vector_result is not None and vector_result.status == "invalid")
    ):
        diagnostics.append(
            {"code": "vector_identity_mismatch", "scope": "vector", "path": None}
        )
    if max(
        opening_snapshot.vector_generation_count,
        closing_snapshot.vector_generation_count,
    ) > 1:
        diagnostics.append(
            {"code": "orphan_generation", "scope": "vector", "path": None}
        )
    for item in skip_samples:
        diagnostics.append(
            {"code": "coverage_pending", "scope": "coverage", "path": item["path"]}
        )

    metadata_unchanged = sum(
        _metadata_equal(observed[path], indexed[path])
        for path in set(observed) & set(indexed)
    )
    ratio = (
        opening_snapshot.vector_rows / opening_snapshot.eligible_chunks
        if opening_snapshot.eligible_chunks
        else 1.0
    )
    exact_vectors = (
        mode == "verified"
        and vector_result is not None
        and vector_result.status in {"valid", "invalid"}
    )
    raw_report = {
        "schema_version": 1,
        "health": derived.value,
        "queryable": opening_snapshot.queryable and not confirmed_corrupt,
        "queryability_evidence": (
            "none"
            if not opening_snapshot.queryable
            else (
                "committed_snapshot_verified"
                if integrity_status == "valid_verified"
                else "committed_snapshot_quick"
            )
        ),
        "availability": availability,
        "observation": {
            "started_at_epoch_ms": started,
            "completed_at_epoch_ms": completed,
            "inventory_status": inventory_status,
            "unscannable_subtree_count": len(
                set(opening_inventory.unscannable_subtrees)
                | set(closing_inventory.unscannable_subtrees)
            ),
            "control_file_error_count": len(
                {
                    (item.scope, item.path)
                    for item in (
                        *opening_inventory.control_file_errors,
                        *closing_inventory.control_file_errors,
                    )
                }
            ),
            "change_token_kind": opening_inventory.change_token_kind,
            "limitations": (
                []
                if mode == "verified"
                else [
                    "metadata_not_content_proof",
                    "vector_payload_content_not_verified",
                ]
            ),
        },
        "freshness": {
            "status": freshness_status,
            "inspection_mode": mode,
            "indexed_at_epoch_s": opening_snapshot.indexed_at_epoch_s,
            "age_seconds": (
                max(0, completed // 1000 - opening_snapshot.indexed_at_epoch_s)
                if opening_snapshot.indexed_at_epoch_s is not None
                else None
            ),
            "added": len(added_paths),
            "changed": len(changed_paths),
            "deleted": len(deleted_paths),
            "metadata_unchanged": metadata_unchanged,
            "content_verified": content_verified,
            "samples": samples,
            "sample_limit": 20,
            "sampled_total": len(samples),
            "evidence_generation": opening_snapshot.ready_generation,
        },
        "coverage": {
            "status": coverage_status,
            "evidence": (
                "not_inspected"
                if legacy
                else "verified_workspace" if mode == "verified" else "ready_snapshot"
            ),
            "indexed_files": None if legacy else len(indexed),
            "coverage_skips": None if legacy else len(current_skips),
            "pending_inspection": None if legacy else pending_inspection,
            "pending_retry": None if legacy else pending_retry,
            "skip_counts": None if legacy else skip_counts,
            "skip_samples": None if legacy else skip_samples,
            "excluded_counts": (
                None if legacy else dict(opening_inventory.excluded_counts)
            ),
        },
        "integrity": {
            "status": integrity_status,
            "manifest": (
                "invalid"
                if confirmed_corrupt and not opening_snapshot.manifest_valid
                else "valid"
            ),
            "sqlite": (
                "invalid"
                if confirmed_corrupt and not opening_snapshot.sqlite_valid
                else "valid_verified" if mode == "verified" else "valid_quick"
            ),
            "graph": opening_snapshot.graph_status,
            "graph_stale_reason": opening_snapshot.graph_stale_reason,
            "vector": (
                "invalid"
                if confirmed_corrupt
                and (
                    not opening_snapshot.vector_identity_valid
                    or (vector_result is not None and vector_result.status == "invalid")
                )
                else "valid_exact" if exact_vectors else "valid_identity_and_size"
            ),
        },
        "vectors": {
            "generation": opening_snapshot.vector_generation,
            "eligible_chunks": opening_snapshot.eligible_chunks,
            "rows": opening_snapshot.vector_rows,
            "coverage_ratio": ratio,
            "coverage_evidence": "exact_ids" if exact_vectors else "count_only",
            "missing_ids": (
                list(vector_result.missing_ids) if exact_vectors else None
            ),
            "orphan_ids": (
                list(vector_result.orphan_ids) if exact_vectors else None
            ),
            "dimensions": opening_snapshot.vector_dimensions,
        },
        "indexed_embedding": _embedding_dict(opening_snapshot.indexed_embedding),
        "configured_embedding": _embedding_dict(configured_embedding),
        "embedding_config_match": embedding_match,
        "refresh": {
            "required": refresh_required,
            "kind": refresh_kind,
            "reasons": refresh_reasons,
            "recommended_action": action,
        },
        "writer": {
            "active": writer.active,
            "state": writer.state,
            "evidence": writer.evidence,
        },
        "diagnostics": diagnostics,
    }
    return IndexHealthReport.from_dict(raw_report)


def _require_keys(
    raw: Mapping[str, Any],
    expected: Sequence[str],
    label: str,
) -> None:
    if set(raw) != set(expected):
        raise ValueError(f"{label} keys are not closed")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _freshness_samples(
    raw: Any,
    limit: int,
) -> tuple[FreshnessSample, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("freshness samples must be a list or null")
    order = {name: index for index, name in enumerate(FRESHNESS_CATEGORY_ORDER)}
    values: list[FreshnessSample] = []
    for item in raw:
        mapping = _mapping(item, "freshness sample")
        _require_keys(mapping, ("category", "path", "reason"), "freshness sample")
        category = mapping["category"]
        if category not in order:
            raise ValueError("freshness sample category is invalid")
        path = _safe_report_path(mapping["path"])
        values.append(FreshnessSample(category, path, str(mapping["reason"])))
    values.sort(key=lambda item: (order[item.category], item.path, item.reason))
    return tuple(values[:limit])


def _skip_samples(
    raw: Any,
    limit: int,
) -> tuple[SkipSample, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("skip samples must be a list or null")
    order = {name: index for index, name in enumerate(SKIP_REASON_ORDER)}
    values: list[SkipSample] = []
    for item in raw:
        mapping = _mapping(item, "skip sample")
        _require_keys(mapping, ("path", "reason", "retryable"), "skip sample")
        reason = mapping["reason"]
        if reason not in order:
            raise ValueError("skip sample reason is invalid")
        values.append(
            SkipSample(
                path=_safe_report_path(mapping["path"]),
                reason=reason,
                retryable=bool(mapping["retryable"]),
            )
        )
    values.sort(key=lambda item: (order[item.reason], item.path))
    return tuple(values[:limit])


def _diagnostics(raw: Any) -> tuple[Diagnostic, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("diagnostics must be a list or null")
    order = {name: index for index, name in enumerate(DIAGNOSTIC_CODE_ORDER)}
    values: list[Diagnostic] = []
    for item in raw:
        mapping = _mapping(item, "diagnostic")
        _require_keys(mapping, ("code", "scope", "path"), "diagnostic")
        code = mapping["code"]
        if code not in order:
            raise ValueError("diagnostic code is invalid")
        path = mapping["path"]
        values.append(
            Diagnostic(
                code=code,
                scope=str(mapping["scope"]),
                path=_safe_report_path(path) if path is not None else None,
            )
        )
    values.sort(key=lambda item: (order[item.code], item.path or "", item.scope))
    deduped: list[Diagnostic] = []
    seen: set[tuple[str, str, str | None]] = set()
    for item in values:
        key = (item.code, item.scope, item.path)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return tuple(deduped)


def _closed_counts(
    raw: Any,
    keys: Sequence[str],
    label: str,
) -> tuple[tuple[str, int], ...] | None:
    if raw is None:
        return None
    mapping = _mapping(raw, label)
    _require_keys(mapping, keys, label)
    values: list[tuple[str, int]] = []
    for key in keys:
        value = mapping[key]
        if type(value) is not int or value < 0:
            raise ValueError(f"{label} values must be non-negative integers")
        values.append((key, value))
    return tuple(values)


def _ordered_strings(
    raw: Any,
    order_values: Sequence[str],
    label: str,
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{label}s must be a list")
    order = {name: index for index, name in enumerate(order_values)}
    if any(value not in order for value in raw):
        raise ValueError(f"{label} is invalid")
    return tuple(sorted(set(raw), key=order.__getitem__))


def _safe_report_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("report path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("report path must be repository-relative")
    return path.as_posix()


def _embedding_dict(value: EmbeddingIdentity) -> dict[str, Any]:
    return {
        "status": value.status,
        "provider": value.provider,
        "model": value.model,
        "dimensions": value.dimensions,
        "config_hash": value.config_hash,
        "network_egress_capable": value.network_egress_capable,
        "network_egress_evidence": value.network_egress_evidence,
    }


def serialize_embedding_identity(value: EmbeddingIdentity) -> dict[str, Any]:
    value._validate()
    return _embedding_dict(value)


def _embedding_key(value: EmbeddingIdentity) -> tuple[str, str, int, str]:
    if (
        value.status != "valid"
        or value.provider is None
        or value.model is None
        or value.dimensions is None
        or value.config_hash is None
    ):
        raise ValueError("embedding identity is not valid")
    return (
        value.provider,
        value.model,
        value.dimensions,
        value.config_hash,
    )


def _nonvalid_embedding(status: str, evidence: str) -> EmbeddingIdentity:
    return EmbeddingIdentity(
        status=status,
        provider=None,
        model=None,
        dimensions=None,
        config_hash=None,
        network_egress_capable=True,
        network_egress_evidence=evidence,
    )


def _metadata_equal(
    observed: FileObservation,
    indexed: IndexedFileObservation,
) -> bool:
    stable_metadata_equal = (
        observed.language == indexed.language
        and observed.size == indexed.size
        and observed.mtime_ns == indexed.mtime_ns
    )
    if indexed.change_token_kind == "unavailable":
        return stable_metadata_equal
    return (
        stable_metadata_equal
        and observed.change_token == indexed.change_token
        and observed.change_token_kind == indexed.change_token_kind
    )


def _inventory_identity(inventory: WorkspaceInventory) -> tuple[Any, ...]:
    return (
        tuple(
            (
                item.path.as_posix(),
                item.language,
                item.metadata,
                item.is_test,
            )
            for item in inventory.eligible
        ),
        tuple(
            (
                item.path.as_posix(),
                item.language,
                item.reason,
                item.retryable,
                item.metadata,
            )
            for item in inventory.coverage_skips
        ),
        inventory.excluded_counts,
        inventory.complete,
        inventory.unscannable_subtrees,
        tuple((item.scope, item.path) for item in inventory.control_file_errors),
        inventory.change_token_kind,
        inventory.diagnostics,
        inventory.control_observations,
    )
