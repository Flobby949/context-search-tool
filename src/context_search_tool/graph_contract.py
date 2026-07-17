from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Final


RESOLUTION_STATES: Final = (
    "resolved_exact",
    "resolved_unique",
    "ambiguous",
    "external",
    "unresolved",
    "legacy",
)
RESOLVED_STATES: Final = frozenset({"resolved_exact", "resolved_unique"})

RELATION_KINDS: Final = (
    "calls",
    "implements",
    "implements_method",
    "uses_type",
    "imports_type",
    "imports",
    "routes_to",
    "mapped_by",
    "tests",
    "uses",
)
RELATION_DIRECTIONS: Final = MappingProxyType(
    {
        "calls": "outgoing",
        "implements": "both",
        "implements_method": "both",
        "uses_type": "outgoing",
        "imports_type": "association_only",
        "imports": "outgoing",
        "routes_to": "outgoing",
        "mapped_by": "both",
        "tests": "intent_gated_both",
        "uses": "legacy_outgoing",
    }
)
RELATION_WEIGHTS: Final = MappingProxyType(
    {
        "calls": 1.0,
        "implements": 0.95,
        "implements_method": 0.95,
        "uses_type": 0.75,
        "imports_type": None,
        "imports": 0.85,
        "routes_to": 1.0,
        "mapped_by": 0.95,
        "tests": 0.8,
        "uses": None,
    }
)
RELATION_KIND_PRIORITY: Final = MappingProxyType(
    {kind: priority for priority, kind in enumerate(RELATION_KINDS)}
)

MAX_SIGNALS_PER_FILE: Final = 4_096
MAX_PRODUCER_RELATIONS_PER_FILE: Final = 8_192
MAX_FRONTEND_IMPORTS_PER_FILE: Final = 64
MAX_ROUTES_PER_ROUTER_FILE: Final = 128
MAX_TEST_TARGETS_PER_FILE: Final = 8
MAX_GRAPH_SEED_SIGNALS: Final = 512
MAX_RESOLVED_GRAPH_HOPS: Final = 4
MAX_LEGACY_RELATION_HOPS: Final = 3
MAX_EDGES_PER_SIGNAL_DIRECTION: Final = 64
EDGE_QUERY_LIMIT: Final = MAX_EDGES_PER_SIGNAL_DIRECTION + 1
MAX_SIGNALS_POPPED_PER_QUERY: Final = 4_096
MAX_EDGES_EXAMINED_PER_QUERY: Final = 16_384
MAX_FRONTIER_ENTRIES_PER_QUERY: Final = 8_192
MAX_RELATION_EXPANDED_CANDIDATES: Final = 1_000
MAX_EXPLAIN_SIGNALS: Final = 32
MAX_EXPLAIN_OUTGOING: Final = 32
MAX_EXPLAIN_INCOMING: Final = 32
GRAPH_SCORE_DECAY: Final = 0.8


def generate_v5_signal_id(
    *,
    file_path: str,
    kind: str,
    qualified_name: str,
    signature: str,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
    producer: str,
) -> str:
    values = (
        ("file_path", _normalize_repository_path(file_path)),
        ("kind", _normalize_text(kind, "kind")),
        ("qualified_name", _normalize_text(qualified_name, "qualified_name")),
        ("signature", _normalize_text(signature, "signature")),
        ("start_line", _integer(start_line, "start_line", minimum=1)),
        ("start_column", _integer(start_column, "start_column", minimum=0)),
        ("end_line", _integer(end_line, "end_line", minimum=1)),
        ("end_column", _integer(end_column, "end_column", minimum=0)),
        ("producer", _normalize_text(producer, "producer")),
    )
    return _canonical_id("s5:", values)


def generate_v5_relation_id(
    *,
    source_signal_id: str,
    kind: str,
    target_kind: str,
    target_qualified_name: str,
    target_signature: str,
    target_arity: int | None,
    target_project_unit_key: str,
    producer: str,
) -> str:
    values = (
        (
            "source_signal_id",
            _normalize_text(source_signal_id, "source_signal_id"),
        ),
        ("kind", _normalize_text(kind, "kind")),
        ("target_kind", _normalize_text(target_kind, "target_kind")),
        (
            "target_qualified_name",
            _normalize_text(target_qualified_name, "target_qualified_name"),
        ),
        (
            "target_signature",
            _normalize_text(target_signature, "target_signature"),
        ),
        ("target_arity", _optional_arity(target_arity)),
        (
            "target_project_unit_key",
            _normalize_project_unit_key(target_project_unit_key),
        ),
        ("producer", _normalize_text(producer, "producer")),
    )
    return _canonical_id("r5:", values)


def generate_core_module_signal_id(
    *,
    file_path: str,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
) -> str:
    normalized_path = _normalize_repository_path(file_path)
    return generate_v5_signal_id(
        file_path=normalized_path,
        kind="module",
        qualified_name=normalized_path,
        signature="",
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
        producer="core_module",
    )


def effective_relation_confidence(
    *,
    resolution: str,
    target_signal_id: str,
    producer_confidence: float,
    resolution_confidence: float | None,
) -> float:
    if resolution not in RESOLUTION_STATES:
        raise ValueError(f"unknown resolution state: {resolution!r}")
    if not isinstance(target_signal_id, str):
        raise ValueError("target_signal_id must be a string")

    producer_value = _confidence(producer_confidence, "producer_confidence")
    if resolution in RESOLVED_STATES:
        if not target_signal_id:
            raise ValueError(f"{resolution} requires target_signal_id")
        if resolution_confidence is None:
            raise ValueError(f"{resolution} requires resolution_confidence")
        resolution_value = _confidence(
            resolution_confidence, "resolution_confidence"
        )
        return min(producer_value, resolution_value)

    if target_signal_id:
        raise ValueError(f"{resolution} requires an empty target_signal_id")
    if resolution_confidence is not None:
        raise ValueError(f"{resolution} requires null resolution_confidence")
    return producer_value


def _canonical_id(prefix: str, values: tuple[tuple[str, object], ...]) -> str:
    payload = json.dumps(
        {key: value for key, value in values},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return prefix + hashlib.sha256(payload).hexdigest()


def _normalize_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return unicodedata.normalize("NFC", value)


def _normalize_repository_path(value: str) -> str:
    normalized = _normalize_text(value, "file_path")
    if not normalized or normalized == "." or "\\" in normalized:
        raise ValueError("file_path must be a repository-relative POSIX path")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != normalized
    ):
        raise ValueError("file_path must be a normalized repository-relative path")
    return normalized


def _normalize_project_unit_key(value: str) -> str:
    normalized = _normalize_text(value, "target_project_unit_key")
    if not normalized:
        return ""
    if normalized == "." or "\\" in normalized:
        raise ValueError("target_project_unit_key must be a POSIX path")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != normalized:
        raise ValueError("target_project_unit_key must be normalized and relative")
    return normalized


def _integer(value: int, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _optional_arity(value: int | None) -> int | None:
    if value is None:
        return None
    return _integer(value, "target_arity", minimum=0)


def _confidence(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    return normalized
