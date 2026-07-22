from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from context_search_tool.graph_contract import RESOLUTION_STATES


TARGET_SIGNAL_SCHEMA_VERSION = 5
TARGET_GRAPH_RESOLUTION_VERSION = 1
TARGET_OPERATIONAL_SCHEMA_VERSION = 1

SIGNAL_SCHEMA_VERSION_KEY = "signal_schema_version"
OPERATIONAL_SCHEMA_VERSION_KEY = "operational_schema_version"
GRAPH_RESOLUTION_STATE_KEY = "graph_resolution_state"
GRAPH_RESOLUTION_VERSION_KEY = "graph_resolution_version"
GRAPH_STALE_REASON_KEY = "graph_stale_reason"
FULL_REINDEX_REQUIRED_KEY = "full_reindex_required"
PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY = "project_unit_topology_fingerprint"

GRAPH_METADATA_KEYS = (
    SIGNAL_SCHEMA_VERSION_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    GRAPH_RESOLUTION_VERSION_KEY,
    GRAPH_STALE_REASON_KEY,
    FULL_REINDEX_REQUIRED_KEY,
    PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
)


class MetadataReader(Protocol):
    def get_metadata(self, key: str) -> str | None: ...


class IncompatibleSignalSchemaError(RuntimeError):
    code = "incompatible_signal_schema"

    def __init__(self, stored_version: object) -> None:
        self.stored_version = stored_version
        super().__init__(f"incompatible signal schema {stored_version}")


class IncompatibleOperationalSchemaError(RuntimeError):
    code = "incompatible_operational_schema"

    def __init__(self, stored_version: object) -> None:
        self.stored_version = stored_version
        super().__init__(f"incompatible operational schema {stored_version}")


class IndexBusyError(RuntimeError):
    code = "index_busy"

    def __init__(self) -> None:
        super().__init__("index already in progress for repository")


class GraphIntegrityError(ValueError):
    code = "graph_integrity_error"


class OperationalIntegrityError(ValueError):
    code = "operational_integrity_error"


@dataclass(frozen=True)
class GraphCapability:
    schema_version: int
    status: Literal["legacy", "stale", "ready"]
    structured: bool
    signal_evidence_allowed: bool
    relation_evidence_allowed: bool
    full_reindex_required: bool
    stale_reason: str


@dataclass(frozen=True)
class OperationalCapability:
    schema_version: int
    status: Literal["legacy", "current"]


@dataclass(frozen=True)
class GraphIntegrityResult:
    dangling_targets: int = 0
    invalid_resolution_rows: int = 0
    orphan_sources: int = 0
    module_count_mismatches: int = 0

    @property
    def ok(self) -> bool:
        return not any(
            (
                self.dangling_targets,
                self.invalid_resolution_rows,
                self.orphan_sources,
                self.module_count_mismatches,
            )
        )


@dataclass(frozen=True)
class RawGraphSchemaCapability:
    status: Literal["legacy", "current", "future"]
    version: int
    error_code: str | None


def classify_raw_graph_schema(
    version: int | None,
) -> RawGraphSchemaCapability:
    normalized = 0 if version is None else version
    if normalized > TARGET_SIGNAL_SCHEMA_VERSION:
        return RawGraphSchemaCapability(
            status="future",
            version=normalized,
            error_code="future_graph_schema",
        )
    return RawGraphSchemaCapability(
        status=(
            "current"
            if normalized == TARGET_SIGNAL_SCHEMA_VERSION
            else "legacy"
        ),
        version=normalized,
        error_code=None,
    )


def read_graph_capability(metadata: MetadataReader) -> GraphCapability:
    raw_version = metadata.get_metadata(SIGNAL_SCHEMA_VERSION_KEY)
    if raw_version is None or raw_version == "":
        version = 0
    else:
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as error:
            raise IncompatibleSignalSchemaError(raw_version) from error
        if version < 0:
            raise IncompatibleSignalSchemaError(raw_version)
    if version > TARGET_SIGNAL_SCHEMA_VERSION:
        raise IncompatibleSignalSchemaError(version)

    raw_state = metadata.get_metadata(GRAPH_RESOLUTION_STATE_KEY)
    raw_resolution_version = metadata.get_metadata(
        GRAPH_RESOLUTION_VERSION_KEY
    )
    stale_reason = metadata.get_metadata(GRAPH_STALE_REASON_KEY) or ""
    full_reindex_required = metadata.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"
    if version < TARGET_SIGNAL_SCHEMA_VERSION:
        status: Literal["legacy", "stale", "ready"] = (
            "stale" if raw_state == "stale" else "legacy"
        )
        structured = False
    else:
        status = (
            "ready"
            if raw_state == "ready"
            and raw_resolution_version == str(TARGET_GRAPH_RESOLUTION_VERSION)
            and not full_reindex_required
            else "stale"
        )
        structured = True

    evidence_allowed = status in {"legacy", "ready"}
    return GraphCapability(
        schema_version=version,
        status=status,
        structured=structured,
        signal_evidence_allowed=evidence_allowed,
        relation_evidence_allowed=evidence_allowed,
        full_reindex_required=full_reindex_required,
        stale_reason=stale_reason,
    )


def read_operational_capability(metadata: MetadataReader) -> OperationalCapability:
    raw_version = metadata.get_metadata(OPERATIONAL_SCHEMA_VERSION_KEY)
    if raw_version is None or raw_version == "":
        return OperationalCapability(schema_version=0, status="legacy")
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as error:
        raise IncompatibleOperationalSchemaError(raw_version) from error
    if version < 0 or str(version) != str(raw_version):
        raise IncompatibleOperationalSchemaError(raw_version)
    if version != TARGET_OPERATIONAL_SCHEMA_VERSION:
        raise IncompatibleOperationalSchemaError(version)
    return OperationalCapability(schema_version=version, status="current")


def resolution_state_is_valid(value: str) -> bool:
    return value in RESOLUTION_STATES
