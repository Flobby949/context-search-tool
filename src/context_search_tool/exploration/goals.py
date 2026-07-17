from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from context_search_tool.context_pack import ContextItem, ContextPack, EvidenceNeed
from context_search_tool.context_pack.needs import retained_item_matches_need
from context_search_tool.context_pack.roles import normalize_candidates
from context_search_tool.exploration.models import (
    MAX_FROZEN_GOALS,
    ExplorationGoal,
    FrozenGoals,
)
from context_search_tool.identifier_intent import infer_identifier_intent
from context_search_tool.tokenizer import tokenize_query

if TYPE_CHECKING:
    from context_search_tool.retrieval import QueryBundle


@dataclass(frozen=True)
class ExplicitRoleClass:
    name: str
    aliases: tuple[str, ...]
    category: str
    accepted_roles: tuple[str, ...]


EXPLICIT_ROLE_CLASSES = (
    ExplicitRoleClass(
        "form/page/view",
        ("form", "forms", "page", "pages", "view", "views"),
        "entrypoints",
        ("view", "view_page", "layout_component"),
    ),
    ExplicitRoleClass(
        "component",
        ("component", "components"),
        "supporting",
        ("component", "shared_component", "layout_component"),
    ),
    ExplicitRoleClass(
        "store/state",
        ("store", "stores", "state", "states"),
        "implementations",
        ("state_store", "store"),
    ),
    ExplicitRoleClass("test", ("test", "tests"), "tests", ("test",)),
    ExplicitRoleClass(
        "config",
        ("config", "configs", "configuration", "configurations"),
        "configs_docs",
        ("deployment_config", "config_example", "runtime_config", "config", "pom"),
    ),
    ExplicitRoleClass(
        "doc",
        ("doc", "docs", "documentation"),
        "configs_docs",
        ("doc",),
    ),
    ExplicitRoleClass(
        "route/controller/entrypoint",
        (
            "route",
            "routes",
            "controller",
            "controllers",
            "entrypoint",
            "entrypoints",
        ),
        "entrypoints",
        ("entrypoint", "router", "command", "handler", "route_config"),
    ),
    ExplicitRoleClass(
        "implementation/service/repository",
        (
            "implementation",
            "implementations",
            "service",
            "services",
            "repository",
            "repositories",
        ),
        "implementations",
        (
            "service_impl",
            "executor",
            "engine",
            "middleware",
            "storage",
            "service",
            "repository",
            "source_adapter",
            "state_store",
            "composable",
            "scheduler",
            "utility",
            "store",
            "shared_component",
        ),
    ),
)

_ROLE_CLASS_BY_ALIAS = {
    alias: role_class
    for role_class in EXPLICIT_ROLE_CLASSES
    for alias in role_class.aliases
}
_ELIGIBLE_ENTRYPOINT_ROLES = {
    "entrypoint",
    "router",
    "command",
    "handler",
    "view",
    "route_config",
    "view_page",
    "layout_component",
}
_IMPLEMENTATION_ROLES = EXPLICIT_ROLE_CLASSES[-1].accepted_roles
_RELATED_TYPE_ROLES = ("data_type", "service_interface", "type_decl")
_FRONTEND_SUPPORT_ROLES = (
    "service",
    "state_store",
    "store",
    "utility",
    "type_decl",
)
_ROLE_SUFFIX_RE = re.compile(
    r"(?:Controller|Service|Repository|Implementation|Component|Entrypoint|"
    r"Router|Route|Page|View|Form|Tests?|Store|State|Tool)$",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def freeze_goals(
    query: str,
    initial_bundle: QueryBundle,
    initial_pack: ContextPack,
) -> FrozenGoals:
    need_goals = tuple(
        _need_goal(need, ordinal)
        for ordinal, need in enumerate(initial_pack.evidence_needs)
    )
    role_goals = _explicit_role_goals(query, initial_pack)
    structural_goals = _structural_goals(initial_bundle, initial_pack)

    ordered = (
        tuple(goal for goal in need_goals if goal.required and not goal.initially_satisfied)
        + role_goals
        + tuple(goal for goal in need_goals if goal.required and goal.initially_satisfied)
        + tuple(goal for goal in need_goals if not goal.required and not goal.initially_satisfied)
        + structural_goals
        + tuple(goal for goal in need_goals if not goal.required and goal.initially_satisfied)
    )
    retained = ordered[:MAX_FROZEN_GOALS]
    return FrozenGoals(
        initial_evidence_need_count=len(initial_pack.evidence_needs),
        candidate_goal_count=len(ordered),
        goals=retained,
        omitted_goal_count=len(ordered) - len(retained),
    )


def unsatisfied_goals(frozen: FrozenGoals) -> tuple[ExplorationGoal, ...]:
    return tuple(goal for goal in frozen.goals if not goal.initially_satisfied)


def goal_is_satisfied(goal: ExplorationGoal, pack: ContextPack) -> bool:
    for item in pack.items:
        if goal.kind == "role_gap" and item.role not in goal.accepted_roles:
            continue
        category = goal.category if goal.kind == "need" else item.group
        need = EvidenceNeed(
            id=goal.id,
            category=category,
            subject_terms=goal.subject_terms,
            required=goal.required,
            provenance="explicit_query",
            matched_item_ids=(),
        )
        if retained_item_matches_need(item, need):
            return True
    return False


def satisfied_goal_ids(
    frozen: FrozenGoals,
    pack: ContextPack,
) -> tuple[str, ...]:
    return tuple(goal.id for goal in frozen.goals if goal_is_satisfied(goal, pack))


def exact_satisfied(
    query: str,
    initial_bundle: QueryBundle,
    frozen: FrozenGoals,
) -> bool:
    if any(goal.required and not goal.initially_satisfied for goal in frozen.goals):
        return False
    intent = infer_identifier_intent(query, tokenize_query(query))
    hints = (*intent.file_hints, *intent.identifiers)
    if not hints:
        return False
    for candidate in normalize_candidates(initial_bundle):
        if not candidate.protected_direct:
            continue
        path = candidate.file_path.casefold()
        stem = PurePosixPath(candidate.file_path).stem.casefold()
        normalized_path = _NON_ALNUM_RE.sub("", path)
        normalized_stem = _NON_ALNUM_RE.sub("", stem)
        for hint in hints:
            normalized_hint = _NON_ALNUM_RE.sub("", hint.casefold())
            if normalized_hint and (
                normalized_hint == normalized_stem
                or normalized_hint in normalized_path
            ):
                return True
    return False


def eligible_structural_entrypoints(
    initial_bundle: QueryBundle,
    initial_pack: ContextPack,
) -> tuple[ContextItem, ...]:
    candidates = {
        candidate.file_path: candidate
        for candidate in normalize_candidates(initial_bundle)
    }
    required_entrypoint_items = {
        item_id
        for need in initial_pack.evidence_needs
        if need.required and need.category == "entrypoints"
        for item_id in need.matched_item_ids
    }
    eligible: list[ContextItem] = []
    for item in initial_pack.items:
        candidate = candidates.get(item.file_path)
        if (
            item.group == "entrypoints"
            and item.role in _ELIGIBLE_ENTRYPOINT_ROLES
            and candidate is not None
            and (
                candidate.protected_direct
                or item.id in required_entrypoint_items
            )
        ):
            eligible.append(item)
    return tuple(eligible)


def _need_goal(need: EvidenceNeed, ordinal: int) -> ExplorationGoal:
    return ExplorationGoal(
        id=f"goal-need-{need.category}-{ordinal}",
        kind="need",
        category=need.category,
        accepted_roles=(),
        subject_terms=tuple(need.subject_terms),
        required=need.required,
        provenance="context_need",
        initially_satisfied=bool(need.matched_item_ids),
    )


def _explicit_role_goals(
    query: str,
    initial_pack: ContextPack,
) -> tuple[ExplorationGoal, ...]:
    seen_classes: set[str] = set()
    role_classes: list[ExplicitRoleClass] = []
    for token in tokenize_query(query):
        role_class = _ROLE_CLASS_BY_ALIAS.get(token.casefold())
        if role_class is None or role_class.name in seen_classes:
            continue
        seen_classes.add(role_class.name)
        role_classes.append(role_class)

    subject_terms = _role_subject_terms(query, initial_pack)
    goals: list[ExplorationGoal] = []
    for role_class in role_classes:
        if any(item.role in role_class.accepted_roles for item in initial_pack.items):
            continue
        ordinal = len(goals)
        goals.append(
            ExplorationGoal(
                id=f"goal-role-{role_class.category}-{ordinal}",
                kind="role_gap",
                category=role_class.category,
                accepted_roles=role_class.accepted_roles,
                subject_terms=subject_terms,
                required=True,
                provenance="explicit_query_role",
                initially_satisfied=False,
            )
        )
    return tuple(goals)


def _structural_goals(
    initial_bundle: QueryBundle,
    initial_pack: ContextPack,
) -> tuple[ExplorationGoal, ...]:
    need_categories = {need.category for need in initial_pack.evidence_needs}
    present_roles = {item.role for item in initial_pack.items}
    goals: list[ExplorationGoal] = []
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()

    def add(category: str, roles: tuple[str, ...], subjects: tuple[str, ...]) -> None:
        key = (category, roles, subjects)
        if key in seen or present_roles.intersection(roles):
            return
        seen.add(key)
        ordinal = len(goals)
        goals.append(
            ExplorationGoal(
                id=f"goal-structural-{category}-{ordinal}",
                kind="role_gap",
                category=category,
                accepted_roles=roles,
                subject_terms=subjects,
                required=False,
                provenance="structural_cluster",
                initially_satisfied=False,
            )
        )

    for item in eligible_structural_entrypoints(initial_bundle, initial_pack):
        subjects = (_entrypoint_subject(item.file_path),)
        if "implementations" not in need_categories:
            add("implementations", _IMPLEMENTATION_ROLES, subjects)
        if "tests" not in need_categories:
            add("tests", ("test",), subjects)
        if _is_frontend_entrypoint(item):
            counterpart_roles = (
                ("entrypoint", "router", "command", "handler", "route_config")
                if item.role in {"view", "view_page", "layout_component"}
                else ("view", "view_page", "layout_component")
            )
            add("entrypoints", counterpart_roles, subjects)
            add("supporting", _FRONTEND_SUPPORT_ROLES, subjects)
        if _is_java_controller(item) and (
            "related_types" not in need_categories
        ):
            add("related_types", _RELATED_TYPE_ROLES, subjects)
    return tuple(goals)


def _role_subject_terms(
    query: str,
    initial_pack: ContextPack,
) -> tuple[str, ...]:
    intent = infer_identifier_intent(query, tokenize_query(query))
    for identifier in intent.identifiers:
        subject = _normalized_subject(_ROLE_SUFFIX_RE.sub("", identifier))
        if subject:
            return (subject,)
    for need in initial_pack.evidence_needs:
        for term in need.subject_terms:
            subject = _normalized_subject(_ROLE_SUFFIX_RE.sub("", term))
            if subject:
                return (subject,)
    return ()


def _entrypoint_subject(file_path: str) -> str:
    stem = PurePosixPath(file_path).stem
    return _normalized_subject(_ROLE_SUFFIX_RE.sub("", stem)) or stem.casefold()


def _normalized_subject(value: str) -> str:
    return _NON_ALNUM_RE.sub("", value.casefold())[:64]


def _is_frontend_entrypoint(item: ContextItem) -> bool:
    return item.role in {"route_config", "view_page", "layout_component"} or (
        PurePosixPath(item.file_path).suffix.casefold()
        in {".astro", ".js", ".jsx", ".svelte", ".ts", ".tsx", ".vue"}
    )


def _is_java_controller(item: ContextItem) -> bool:
    path = PurePosixPath(item.file_path)
    return (
        path.suffix.casefold() == ".java"
        and item.role == "entrypoint"
        and "controller" in path.stem.casefold()
    )
