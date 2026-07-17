from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_search_tool.context_pack import ContextPack
    from context_search_tool.retrieval import QueryBundle
    from context_search_tool.retrieval_trace.exploration import ExplorationTrace


MAX_LOGICAL_ROUNDS = 2
MAX_FOLLOWUP_PROBES = 2
MAX_RETRIEVAL_CALLS = 3
MAX_FROZEN_GOALS = 8
MAX_PLANNED_PROBES = 8
MAX_PROBE_TEXT_CODE_POINTS = 160
MAX_PROBE_SEED_PATHS = 3
MAX_FRONTEND_HEADER_BYTES = 16_384
MAX_INITIAL_RESULTS = 12
FOLLOWUP_FINAL_TOP_K = 6
MAX_FUSED_RESULTS = 24
MAX_FUSED_ANCHORS = 8
MAX_FINAL_EVIDENCE_PREVIEW = 20
DUPLICATE_STOP_RATIO = 0.80


@dataclass(frozen=True)
class ExplorationGoal:
    id: str
    kind: str
    category: str
    accepted_roles: tuple[str, ...]
    subject_terms: tuple[str, ...]
    required: bool
    provenance: str
    initially_satisfied: bool


@dataclass(frozen=True)
class FrozenGoals:
    initial_evidence_need_count: int
    candidate_goal_count: int
    goals: tuple[ExplorationGoal, ...]
    omitted_goal_count: int


@dataclass(frozen=True)
class ProbeCandidate:
    query: str
    source: str
    purpose: str
    goal_ids: tuple[str, ...]
    seed_paths: tuple[str, ...]
    required: bool
    goal_order: int
    source_rank: int


@dataclass(frozen=True)
class EvidenceOrigin:
    file_path: str
    round_index: int
    probe_id: str
    source_kind: str
    source_rank: int
    selection_reason: str
    goal_ids: tuple[str, ...]


@dataclass(frozen=True)
class FusedEvidenceState:
    bundle: QueryBundle
    origins: tuple[EvidenceOrigin, ...]
    satisfied_goal_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExploredContext:
    initial_bundle: QueryBundle
    initial_pack: ContextPack
    fused_bundle: QueryBundle
    final_pack: ContextPack
    trace: ExplorationTrace


@dataclass(frozen=True)
class ExplorationError(Exception):
    code: str = "explore_failed"
    message: str = "Controlled exploration failed"

    def __post_init__(self) -> None:
        if (self.code, self.message) != (
            "explore_failed",
            "Controlled exploration failed",
        ):
            raise ValueError("ExplorationError uses one stable public failure")

    def __str__(self) -> str:
        return self.message
