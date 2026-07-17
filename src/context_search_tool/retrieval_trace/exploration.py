from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, fields
from pathlib import PurePosixPath
from typing import Any

from context_search_tool.context_pack import CONTEXT_GROUPS
from context_search_tool.exploration.models import (
    FOLLOWUP_FINAL_TOP_K,
    MAX_FINAL_EVIDENCE_PREVIEW,
    MAX_FOLLOWUP_PROBES,
    MAX_FRONTEND_HEADER_BYTES,
    MAX_FROZEN_GOALS,
    MAX_FUSED_ANCHORS,
    MAX_FUSED_RESULTS,
    MAX_LOGICAL_ROUNDS,
    MAX_PLANNED_PROBES,
    MAX_PROBE_SEED_PATHS,
    MAX_PROBE_TEXT_CODE_POINTS,
    MAX_RETRIEVAL_CALLS,
)
from context_search_tool.retrieval_trace.models import SOURCE_COUNT_KEYS


_MAX_FRONTEND_IMPORT_PATHS = 3
_TOP_LEVEL_PAIRS = {
    ("complete", "context_budget_zero"),
    ("complete", "exact_satisfied"),
    ("complete", "initial_satisfied"),
    ("complete", "no_grounded_probe"),
    ("complete", "satisfied"),
    ("complete", "no_marginal_gain"),
    ("complete", "probe_budget_exhausted"),
    ("empty", "initial_missing_index"),
    ("empty", "initial_empty"),
    ("partial", "initial_retrieval_incomplete"),
    ("partial", "followup_query_failed"),
}
_PROBE_PAIRS = {
    ("complete", "completed"),
    ("empty", "no_candidates"),
    ("empty", "missing_index"),
    ("partial", "store_read_error"),
    ("failed", "query_error"),
    ("failed", "provider_error"),
}
_PROBE_SOURCES = {
    "original",
    "next_query",
    "relation_target",
    "indexed_symbol",
    "endpoint_or_route",
    "static_import",
    "path_stem",
}
_GOAL_PROVENANCE = {
    "context_need",
    "explicit_query_role",
    "structural_cluster",
}
_SELECTION_REASONS = {
    "retained_initial_evidence",
    "replaced_by_goal_covering_probe",
    "added_novel_probe_evidence",
    "selected_evidence_anchor",
}
_FOLLOWUP_PURPOSE_RE = re.compile(
    r"^find_missing_(required|recommended)_(entrypoints|implementations|"
    r"related_types|tests|configs_docs|supporting)$"
)
_CLOSED_ROLES = {
    "command",
    "component",
    "composable",
    "config",
    "config_example",
    "data_type",
    "deployment_config",
    "doc",
    "engine",
    "entrypoint",
    "evidence_anchor",
    "executor",
    "generated_output",
    "handler",
    "implementation",
    "layout_component",
    "lockfile",
    "middleware",
    "pom",
    "readme",
    "repository",
    "risks",
    "route_config",
    "router",
    "runtime_config",
    "scheduler",
    "scratch_temp",
    "service",
    "service_impl",
    "service_interface",
    "shared_component",
    "source",
    "source_adapter",
    "state_store",
    "storage",
    "store",
    "test",
    "type_decl",
    "utility",
    "view",
    "view_page",
}


class ExplorationTraceError(RuntimeError):
    """Raised when exploration trace state violates the schema-v2 contract."""


def _fail(message: str) -> None:
    raise ExplorationTraceError(message)


def _non_negative_int(name: str, value: object) -> None:
    if type(value) is not int or value < 0:
        _fail(f"{name} must be a non-negative integer")


def _positive_int(name: str, value: object) -> None:
    if type(value) is not int or value < 1:
        _fail(f"{name} must be a positive integer")


def _nonempty_string(name: str, value: object) -> None:
    if type(value) is not str or not value:
        _fail(f"{name} must be a non-empty string")


def _canonical_path(name: str, value: object) -> None:
    if type(value) is not str:
        _fail(f"{name} must be repository-relative")
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or "." in path.parts
        or ".." in path.parts
    ):
        _fail(f"{name} must be repository-relative")


def _string_tuple(
    name: str,
    values: object,
    *,
    maximum: int | None = None,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        _fail(f"{name} must be a tuple")
    if maximum is not None and len(values) > maximum:
        _fail(f"{name} exceeds its fixed limit")
    if any(type(value) is not str or not value for value in values):
        _fail(f"{name} must contain non-empty strings")
    if len(values) != len(set(values)):
        _fail(f"{name} must be unique")
    return values


def _source_counts(values: object) -> None:
    if type(values) is not tuple:
        _fail("source_counts must be a tuple")
    if tuple(key for key, _ in values) != SOURCE_COUNT_KEYS:
        _fail("source_counts keys must match canonical order")
    for key, value in values:
        _non_negative_int(key, value)


@dataclass(frozen=True)
class ExplorationLimits:
    max_rounds: int = MAX_LOGICAL_ROUNDS
    max_followup_probes: int = MAX_FOLLOWUP_PROBES
    max_retrieval_calls: int = MAX_RETRIEVAL_CALLS
    max_planned_probes: int = MAX_PLANNED_PROBES
    max_goals: int = MAX_FROZEN_GOALS
    max_probe_code_points: int = MAX_PROBE_TEXT_CODE_POINTS
    max_seed_paths: int = MAX_PROBE_SEED_PATHS
    max_frontend_import_header_bytes: int = MAX_FRONTEND_HEADER_BYTES
    max_frontend_import_paths: int = _MAX_FRONTEND_IMPORT_PATHS
    effective_initial_top_k: int = 12
    followup_top_k: int = FOLLOWUP_FINAL_TOP_K
    max_fused_results: int = MAX_FUSED_RESULTS
    max_fused_anchors: int = MAX_FUSED_ANCHORS
    final_evidence_top_k: int = MAX_FINAL_EVIDENCE_PREVIEW

    def __post_init__(self) -> None:
        for field in fields(self):
            _positive_int(field.name, getattr(self, field.name))
        if not 1 <= self.effective_initial_top_k <= 12:
            _fail("effective_initial_top_k must be between 1 and 12")
        actual = tuple(
            getattr(self, field.name)
            for field in fields(self)
            if field.name != "effective_initial_top_k"
        )
        expected = (
            2,
            2,
            3,
            8,
            8,
            160,
            3,
            16_384,
            3,
            6,
            24,
            8,
            20,
        )
        if actual != expected:
            _fail("schema-v2 exploration limits are fixed")


@dataclass(frozen=True)
class ExplorationGoalRecord:
    id: str
    kind: str
    category: str
    accepted_roles: tuple[str, ...]
    required: bool
    provenance: str
    initially_satisfied: bool
    finally_satisfied: bool

    def __post_init__(self) -> None:
        _nonempty_string("goal id", self.id)
        if self.kind not in {"need", "role_gap"}:
            _fail("goal kind is invalid")
        if self.category not in CONTEXT_GROUPS:
            _fail("goal category is invalid")
        roles = _string_tuple("accepted_roles", self.accepted_roles)
        if any(role not in _CLOSED_ROLES for role in roles):
            _fail("accepted_roles contains an invalid role")
        if self.kind == "need" and roles:
            _fail("need goals cannot carry accepted roles")
        if self.kind == "role_gap" and not roles:
            _fail("role-gap goals require accepted roles")
        if type(self.required) is not bool:
            _fail("required must be a boolean")
        if self.provenance not in _GOAL_PROVENANCE:
            _fail("goal provenance is invalid")
        if self.kind == "need" and self.provenance != "context_need":
            _fail("need goal provenance is invalid")
        if self.kind == "role_gap" and self.provenance == "context_need":
            _fail("role-gap goal provenance is invalid")
        if type(self.initially_satisfied) is not bool or type(
            self.finally_satisfied
        ) is not bool:
            _fail("goal satisfaction flags must be booleans")
        if self.initially_satisfied and not self.finally_satisfied:
            _fail("goal satisfaction cannot regress")


@dataclass(frozen=True)
class ExplorationProbe:
    id: str
    query: str
    purpose: str
    source: str
    goal_ids: tuple[str, ...]
    seed_paths: tuple[str, ...]
    retrieval_outcome: str
    retrieval_termination_reason: str
    duration_ms: int
    result_count: int
    evidence_anchor_count: int
    unique_path_count: int
    duplicate_path_count: int
    novel_path_count: int
    newly_satisfied_goal_ids: tuple[str, ...]
    source_counts: tuple[tuple[str, int], ...]
    final_selection_count: int

    def __post_init__(self) -> None:
        _nonempty_string("probe id", self.id)
        _nonempty_string("probe query", self.query)
        _nonempty_string("probe purpose", self.purpose)
        if self.source not in _PROBE_SOURCES:
            _fail("probe source is invalid")
        if self.source == "original":
            if self.purpose != "original_query":
                _fail("original probe purpose is invalid")
        else:
            if _FOLLOWUP_PURPOSE_RE.fullmatch(self.purpose) is None:
                _fail("follow-up probe purpose is invalid")
            if len(self.query) > MAX_PROBE_TEXT_CODE_POINTS or any(
                unicodedata.category(character).startswith("C")
                for character in self.query
            ):
                _fail("follow-up probe query is not bounded")
        _string_tuple("probe goal_ids", self.goal_ids)
        paths = _string_tuple(
            "seed_paths",
            self.seed_paths,
            maximum=MAX_PROBE_SEED_PATHS,
        )
        for path in paths:
            _canonical_path("seed path", path)
        if (
            self.retrieval_outcome,
            self.retrieval_termination_reason,
        ) not in _PROBE_PAIRS:
            _fail("probe outcome and termination reason are invalid")
        for name in (
            "duration_ms",
            "result_count",
            "evidence_anchor_count",
            "unique_path_count",
            "duplicate_path_count",
            "novel_path_count",
            "final_selection_count",
        ):
            _non_negative_int(name, getattr(self, name))
        _string_tuple(
            "newly_satisfied_goal_ids",
            self.newly_satisfied_goal_ids,
        )
        _source_counts(self.source_counts)
        if self.unique_path_count > self.result_count + self.evidence_anchor_count:
            _fail("unique path count exceeds returned evidence")
        if (
            self.duplicate_path_count + self.novel_path_count
            != self.unique_path_count
        ):
            _fail("probe path counts are inconsistent")
        if self.retrieval_outcome == "failed":
            counts = (
                self.result_count,
                self.evidence_anchor_count,
                self.unique_path_count,
                self.duplicate_path_count,
                self.novel_path_count,
                self.final_selection_count,
            )
            if any(counts) or self.newly_satisfied_goal_ids or any(
                value for _, value in self.source_counts
            ):
                _fail("failed probes must not fabricate retrieval state")
        elif self.final_selection_count != (
            self.result_count + self.evidence_anchor_count
        ):
            _fail("normal probe selection counts are inconsistent")


@dataclass(frozen=True)
class ExplorationRound:
    round_index: int
    kind: str
    duration_ms: int
    input_path_count: int
    output_path_count: int
    novel_path_count: int
    duplicate_path_count: int
    newly_satisfied_goal_ids: tuple[str, ...]
    probes: tuple[ExplorationProbe, ...]

    def __post_init__(self) -> None:
        for name in (
            "round_index",
            "duration_ms",
            "input_path_count",
            "output_path_count",
            "novel_path_count",
            "duplicate_path_count",
        ):
            _non_negative_int(name, getattr(self, name))
        if self.kind not in {"initial", "followup"}:
            _fail("round kind is invalid")
        _string_tuple(
            "round newly_satisfied_goal_ids",
            self.newly_satisfied_goal_ids,
        )
        if type(self.probes) is not tuple or not self.probes or any(
            type(probe) is not ExplorationProbe for probe in self.probes
        ):
            _fail("round probes must be a non-empty tuple")
        if len(self.probes) > MAX_FOLLOWUP_PROBES:
            _fail("round probe count exceeds the fixed limit")
        if self.output_path_count < self.input_path_count or (
            self.novel_path_count
            != self.output_path_count - self.input_path_count
        ):
            _fail("round path counts are inconsistent")
        if self.duplicate_path_count != sum(
            probe.duplicate_path_count for probe in self.probes
        ):
            _fail("round duplicate count is inconsistent")


@dataclass(frozen=True)
class FinalEvidence:
    item_id: str
    file_path: str
    source_round: int
    probe_id: str
    probe_rank: int
    goal_ids: tuple[str, ...]
    selection_reason: str

    def __post_init__(self) -> None:
        _nonempty_string("final evidence item_id", self.item_id)
        _canonical_path("final evidence file_path", self.file_path)
        if type(self.source_round) is not int or self.source_round not in {0, 1}:
            _fail("final evidence source_round is invalid")
        _nonempty_string("final evidence probe_id", self.probe_id)
        _positive_int("probe_rank", self.probe_rank)
        _string_tuple("final evidence goal_ids", self.goal_ids)
        if self.selection_reason not in _SELECTION_REASONS:
            _fail("final evidence selection_reason is invalid")
        if self.source_round == 0 and (
            self.probe_id != "r0p0"
            or self.selection_reason
            not in {"retained_initial_evidence", "selected_evidence_anchor"}
        ):
            _fail("initial evidence provenance is invalid")
        if self.source_round == 1 and (
            self.probe_id not in {"r1p0", "r1p1"}
            or self.selection_reason == "retained_initial_evidence"
        ):
            _fail("follow-up evidence provenance is invalid")


@dataclass(frozen=True)
class ExplorationTrace:
    schema_version: int
    mode: str
    outcome: str
    termination_reason: str
    duration_ms: int
    limits: ExplorationLimits
    initial_evidence_need_count: int
    candidate_goal_count: int
    retained_goal_count: int
    omitted_goal_count: int
    initial_satisfied_goal_count: int
    final_satisfied_goal_count: int
    planned_probe_count: int
    executed_probe_count: int
    stale_skipped_probe_count: int
    unexecuted_probe_count: int
    retrieval_call_count: int
    goals: tuple[ExplorationGoalRecord, ...]
    rounds: tuple[ExplorationRound, ...]
    final_evidence_count: int
    final_evidence_omitted_count: int
    final_evidence: tuple[FinalEvidence, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 2 or self.mode != "exploration":
            _fail("exploration trace identity is invalid")
        if (self.outcome, self.termination_reason) not in _TOP_LEVEL_PAIRS:
            _fail("exploration outcome and termination reason are invalid")
        _non_negative_int("duration_ms", self.duration_ms)
        if type(self.limits) is not ExplorationLimits:
            _fail("limits must be ExplorationLimits")
        for name in (
            "initial_evidence_need_count",
            "candidate_goal_count",
            "retained_goal_count",
            "omitted_goal_count",
            "initial_satisfied_goal_count",
            "final_satisfied_goal_count",
            "planned_probe_count",
            "executed_probe_count",
            "stale_skipped_probe_count",
            "unexecuted_probe_count",
            "retrieval_call_count",
            "final_evidence_count",
            "final_evidence_omitted_count",
        ):
            _non_negative_int(name, getattr(self, name))
        if type(self.goals) is not tuple or any(
            type(goal) is not ExplorationGoalRecord for goal in self.goals
        ):
            _fail("goals must be an ExplorationGoalRecord tuple")
        if type(self.rounds) is not tuple or any(
            type(round_record) is not ExplorationRound
            for round_record in self.rounds
        ):
            _fail("rounds must be an ExplorationRound tuple")
        if type(self.final_evidence) is not tuple or any(
            type(item) is not FinalEvidence for item in self.final_evidence
        ):
            _fail("final_evidence must be a FinalEvidence tuple")
        self._validate_counts()
        self._validate_goals_and_references()
        self._validate_rounds()
        self._validate_final_evidence()

    def _validate_counts(self) -> None:
        if self.retained_goal_count != len(self.goals) or (
            self.retained_goal_count > self.limits.max_goals
        ):
            _fail("retained goal count is inconsistent")
        if self.candidate_goal_count != (
            self.retained_goal_count + self.omitted_goal_count
        ):
            _fail("candidate goal count is inconsistent")
        initial_count = sum(goal.initially_satisfied for goal in self.goals)
        final_count = sum(goal.finally_satisfied for goal in self.goals)
        if self.initial_satisfied_goal_count != initial_count or (
            self.final_satisfied_goal_count != final_count
        ):
            _fail("satisfied goal counts are inconsistent")
        if self.planned_probe_count != (
            self.executed_probe_count
            + self.stale_skipped_probe_count
            + self.unexecuted_probe_count
        ):
            _fail("planned probe count is inconsistent")
        if self.retrieval_call_count != 1 + self.executed_probe_count:
            _fail("retrieval call count is inconsistent")
        if self.planned_probe_count > self.limits.max_planned_probes:
            _fail("planned probe count exceeds the fixed limit")
        if self.executed_probe_count > self.limits.max_followup_probes:
            _fail("executed probe count exceeds the fixed limit")
        if self.retrieval_call_count > self.limits.max_retrieval_calls:
            _fail("retrieval call count exceeds the fixed limit")
        if self.final_evidence_count != (
            len(self.final_evidence) + self.final_evidence_omitted_count
        ):
            _fail("final evidence counts are inconsistent")
        if len(self.final_evidence) > self.limits.final_evidence_top_k:
            _fail("final evidence preview exceeds the fixed limit")
        if self.final_evidence_count > (
            self.limits.max_fused_results + self.limits.max_fused_anchors
        ):
            _fail("final evidence count exceeds fused capacity")

    def _validate_goals_and_references(self) -> None:
        goal_ids = tuple(goal.id for goal in self.goals)
        if len(goal_ids) != len(set(goal_ids)):
            _fail("goal IDs must be unique")
        positions = {goal_id: index for index, goal_id in enumerate(goal_ids)}
        for round_record in self.rounds:
            _goal_references(
                "round newly satisfied goals",
                round_record.newly_satisfied_goal_ids,
                positions,
            )
            for probe in round_record.probes:
                _goal_references("probe goals", probe.goal_ids, positions)
                _goal_references(
                    "probe newly satisfied goals",
                    probe.newly_satisfied_goal_ids,
                    positions,
                )
        for item in self.final_evidence:
            _goal_references("final evidence goals", item.goal_ids, positions)

    def _validate_rounds(self) -> None:
        if not 1 <= len(self.rounds) <= self.limits.max_rounds:
            _fail("exploration rounds are missing or exceed the fixed limit")
        if tuple(round_record.round_index for round_record in self.rounds) != tuple(
            range(len(self.rounds))
        ):
            _fail("round indexes must be contiguous")
        if tuple(round_record.kind for round_record in self.rounds) != (
            ("initial",) if len(self.rounds) == 1 else ("initial", "followup")
        ):
            _fail("round kinds are inconsistent")
        initial_round = self.rounds[0]
        if initial_round.input_path_count != 0 or len(initial_round.probes) != 1:
            _fail("initial round shape is invalid")
        initial_probe = initial_round.probes[0]
        if (
            initial_probe.id != "r0p0"
            or initial_probe.source != "original"
            or initial_probe.purpose != "original_query"
            or initial_probe.goal_ids
            or initial_probe.seed_paths
            or initial_probe.duplicate_path_count != 0
            or initial_probe.novel_path_count != initial_probe.unique_path_count
            or initial_round.output_path_count != initial_probe.unique_path_count
            or initial_round.newly_satisfied_goal_ids
            != initial_probe.newly_satisfied_goal_ids
        ):
            _fail("initial probe shape is invalid")
        if initial_probe.result_count > self.limits.effective_initial_top_k:
            _fail("initial result count exceeds effective top-k")
        initial_anchor_limit = max(
            1,
            min(5, self.limits.effective_initial_top_k // 3),
        )
        if initial_probe.evidence_anchor_count > initial_anchor_limit:
            _fail("initial anchor count exceeds effective top-k")

        followup_records = (
            self.rounds[1].probes if len(self.rounds) == 2 else ()
        )
        if len(followup_records) != self.executed_probe_count or (
            bool(followup_records) != (len(self.rounds) == 2)
        ):
            _fail("follow-up round count is inconsistent")
        if len(self.rounds) == 2 and (
            self.rounds[1].input_path_count != initial_round.output_path_count
        ):
            _fail("follow-up round input count is inconsistent")
        if tuple(probe.id for probe in followup_records) != tuple(
            f"r1p{index}" for index in range(len(followup_records))
        ):
            _fail("follow-up probe IDs must be contiguous")
        for probe in followup_records:
            if probe.source == "original" or not probe.goal_ids:
                _fail("follow-up probe shape is invalid")
            if probe.result_count > self.limits.followup_top_k or (
                probe.evidence_anchor_count > max(
                    1,
                    min(5, self.limits.followup_top_k // 3),
                )
            ):
                _fail("follow-up evidence exceeds effective top-k")
            _validate_followup_purpose(probe, self.goals)

        for round_record in self.rounds:
            if (
                round_record.input_path_count
                > self.limits.max_fused_results + self.limits.max_fused_anchors
                or round_record.output_path_count
                > self.limits.max_fused_results + self.limits.max_fused_anchors
            ):
                _fail("round path count exceeds fused capacity")
            probe_new = tuple(
                goal_id
                for probe in round_record.probes
                for goal_id in probe.newly_satisfied_goal_ids
            )
            if set(probe_new) != set(round_record.newly_satisfied_goal_ids) or (
                len(probe_new) != len(set(probe_new))
            ):
                _fail("round goal gain is inconsistent")

        initial_goal_ids = tuple(
            goal.id for goal in self.goals if goal.initially_satisfied
        )
        final_goal_ids = tuple(
            goal.id for goal in self.goals if goal.finally_satisfied
        )
        all_new = _ordered_union(
            *(round_record.newly_satisfied_goal_ids for round_record in self.rounds)
        )
        if initial_round.newly_satisfied_goal_ids != initial_goal_ids or set(
            all_new
        ) != set(final_goal_ids):
            _fail("round goal ledger is inconsistent")
        if sum(
            len(round_record.newly_satisfied_goal_ids)
            for round_record in self.rounds
        ) != len(all_new):
            _fail("newly satisfied goals must not repeat across rounds")

    def _validate_final_evidence(self) -> None:
        item_ids = tuple(item.item_id for item in self.final_evidence)
        paths = tuple(item.file_path for item in self.final_evidence)
        if len(item_ids) != len(set(item_ids)) or len(paths) != len(set(paths)):
            _fail("final evidence IDs and paths must be unique")
        executed_probe_ids = {
            probe.id
            for round_record in self.rounds[1:]
            for probe in round_record.probes
        }
        for item in self.final_evidence:
            if item.source_round == 1 and item.probe_id not in executed_probe_ids:
                _fail("final evidence references an unexecuted probe")


def _goal_references(
    name: str,
    goal_ids: tuple[str, ...],
    positions: dict[str, int],
) -> None:
    if any(goal_id not in positions for goal_id in goal_ids):
        _fail(f"{name} contains an unknown goal")
    if tuple(positions[goal_id] for goal_id in goal_ids) != tuple(
        sorted(positions[goal_id] for goal_id in goal_ids)
    ):
        _fail(f"{name} is not in ledger order")


def _validate_followup_purpose(
    probe: ExplorationProbe,
    goals: tuple[ExplorationGoalRecord, ...],
) -> None:
    match = _FOLLOWUP_PURPOSE_RE.fullmatch(probe.purpose)
    if match is None:
        _fail("follow-up probe purpose is invalid")
    required_label, category = match.groups()
    required = required_label == "required"
    goal_by_id = {goal.id: goal for goal in goals}
    if not any(
        goal_by_id[goal_id].category == category
        and goal_by_id[goal_id].required is required
        for goal_id in probe.goal_ids
    ):
        _fail("follow-up purpose does not match its goals")


def _ordered_union(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            if value in seen:
                continue
            seen.add(value)
            values.append(value)
    return tuple(values)


def exploration_trace_payload(trace: ExplorationTrace) -> dict[str, Any]:
    if type(trace) is not ExplorationTrace:
        _fail("trace must be an ExplorationTrace")
    return {
        "schema_version": trace.schema_version,
        "mode": trace.mode,
        "outcome": trace.outcome,
        "termination_reason": trace.termination_reason,
        "duration_ms": trace.duration_ms,
        "limits": _limits_payload(trace.limits),
        "initial_evidence_need_count": trace.initial_evidence_need_count,
        "candidate_goal_count": trace.candidate_goal_count,
        "retained_goal_count": trace.retained_goal_count,
        "omitted_goal_count": trace.omitted_goal_count,
        "initial_satisfied_goal_count": trace.initial_satisfied_goal_count,
        "final_satisfied_goal_count": trace.final_satisfied_goal_count,
        "planned_probe_count": trace.planned_probe_count,
        "executed_probe_count": trace.executed_probe_count,
        "stale_skipped_probe_count": trace.stale_skipped_probe_count,
        "unexecuted_probe_count": trace.unexecuted_probe_count,
        "retrieval_call_count": trace.retrieval_call_count,
        "goals": [_goal_payload(goal) for goal in trace.goals],
        "rounds": [_round_payload(round_record) for round_record in trace.rounds],
        "final_evidence_count": trace.final_evidence_count,
        "final_evidence_omitted_count": trace.final_evidence_omitted_count,
        "final_evidence": [_evidence_payload(item) for item in trace.final_evidence],
    }


def canonical_exploration_trace_bytes(trace: ExplorationTrace) -> bytes:
    try:
        return json.dumps(
            exploration_trace_payload(trace),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except ExplorationTraceError:
        raise
    except Exception as exc:
        raise ExplorationTraceError("exploration trace serialization failed") from exc


def _limits_payload(limits: ExplorationLimits) -> dict[str, int]:
    return {field.name: getattr(limits, field.name) for field in fields(limits)}


def _goal_payload(goal: ExplorationGoalRecord) -> dict[str, Any]:
    return {
        "id": goal.id,
        "kind": goal.kind,
        "category": goal.category,
        "accepted_roles": list(goal.accepted_roles),
        "required": goal.required,
        "provenance": goal.provenance,
        "initially_satisfied": goal.initially_satisfied,
        "finally_satisfied": goal.finally_satisfied,
    }


def _probe_payload(probe: ExplorationProbe) -> dict[str, Any]:
    return {
        "id": probe.id,
        "query": probe.query,
        "purpose": probe.purpose,
        "source": probe.source,
        "goal_ids": list(probe.goal_ids),
        "seed_paths": list(probe.seed_paths),
        "retrieval_outcome": probe.retrieval_outcome,
        "retrieval_termination_reason": probe.retrieval_termination_reason,
        "duration_ms": probe.duration_ms,
        "result_count": probe.result_count,
        "evidence_anchor_count": probe.evidence_anchor_count,
        "unique_path_count": probe.unique_path_count,
        "duplicate_path_count": probe.duplicate_path_count,
        "novel_path_count": probe.novel_path_count,
        "newly_satisfied_goal_ids": list(probe.newly_satisfied_goal_ids),
        "source_counts": dict(probe.source_counts),
        "final_selection_count": probe.final_selection_count,
    }


def _round_payload(round_record: ExplorationRound) -> dict[str, Any]:
    return {
        "round_index": round_record.round_index,
        "kind": round_record.kind,
        "duration_ms": round_record.duration_ms,
        "input_path_count": round_record.input_path_count,
        "output_path_count": round_record.output_path_count,
        "novel_path_count": round_record.novel_path_count,
        "duplicate_path_count": round_record.duplicate_path_count,
        "newly_satisfied_goal_ids": list(
            round_record.newly_satisfied_goal_ids
        ),
        "probes": [_probe_payload(probe) for probe in round_record.probes],
    }


def _evidence_payload(item: FinalEvidence) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "file_path": item.file_path,
        "source_round": item.source_round,
        "probe_id": item.probe_id,
        "probe_rank": item.probe_rank,
        "goal_ids": list(item.goal_ids),
        "selection_reason": item.selection_reason,
    }


__all__ = [
    "ExplorationGoalRecord",
    "ExplorationLimits",
    "ExplorationProbe",
    "ExplorationRound",
    "ExplorationTrace",
    "ExplorationTraceError",
    "FinalEvidence",
    "canonical_exploration_trace_bytes",
    "exploration_trace_payload",
]
