from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.context_pack.models import ContextCandidate, EvidenceNeed
from context_search_tool.context_pack import needs as context_needs
from context_search_tool.context_pack.needs import (
    candidate_matches_need,
    derive_evidence_needs,
)
from context_search_tool.context_pack.roles import normalize_candidates
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.retrieval import QueryBundle
from context_search_tool.tokenizer import tokenize_query


def result(
    path: str,
    *,
    content: str = "source",
    reasons: list[str] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=1.0,
        score_parts={"evidence_priority": 0.0},
        reasons=list(reasons or ("fixture",)),
        followup_keywords=[],
    )


def anchor(
    path: str,
    *,
    content: str = "anchor",
    reasons: list[str] | None = None,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=0.5,
        score_parts={},
        reasons=list(reasons or ("fixture anchor",)),
        anchor_kind="other",
    )


def bundle(
    *,
    query: str,
    results: list[RetrievalResult] | None = None,
    anchors: list[EvidenceAnchor] | None = None,
    planner: QueryPlan | None = None,
    expanded_tokens: list[str] | None = None,
    followup_keywords: list[str] | None = None,
    summary: RetrievalSummary | None = None,
) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=list(expanded_tokens or ()),
        results=list(results or ()),
        followup_keywords=list(followup_keywords or ()),
        summary=summary or RetrievalSummary(),
        planner=planner or QueryPlan.disabled_default(),
        evidence_anchors=list(anchors or ()),
    )


def required(needs: tuple[EvidenceNeed, ...]) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (need.category, need.subject_terms)
        for need in needs
        if need.required
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "owner registration form validation flow",
            [("entrypoints", ("owner",))],
        ),
        (
            "OwnerController tests for owner registration validation",
            [
                ("entrypoints", ("OwnerController",)),
                ("tests", ("OwnerController",)),
            ],
        ),
        (
            "宠物主人详情页如何加载宠物和就诊记录",
            [("entrypoints", ("宠物主人详情页",))],
        ),
        (
            "MySQL PostgreSQL database profile configuration and integration tests",
            [
                ("configs_docs", ("MySQL",)),
                ("configs_docs", ("PostgreSQL",)),
                ("tests", ("MySQL",)),
                ("tests", ("PostgreSQL",)),
            ],
        ),
        ("Owner model type", [("related_types", ("Owner",))]),
        ("find service implementation", [("implementations", ())]),
    ],
)
def test_exact_query_matrix_derives_scoped_required_needs(
    query: str,
    expected: list[tuple[str, tuple[str, ...]]],
) -> None:
    needs = derive_evidence_needs(bundle(query=query), candidates=())

    assert required(needs) == expected


def test_multiple_database_subjects_have_distinct_ids_and_query_order() -> None:
    needs = derive_evidence_needs(
        bundle(
            query=(
                "MySQL PostgreSQL database profile configuration and "
                "integration tests"
            )
        ),
        candidates=(),
    )
    required_needs = tuple(need for need in needs if need.required)

    assert [(need.category, need.subject_terms) for need in required_needs] == [
        ("configs_docs", ("MySQL",)),
        ("configs_docs", ("PostgreSQL",)),
        ("tests", ("MySQL",)),
        ("tests", ("PostgreSQL",)),
    ]
    assert len({need.id for need in required_needs}) == 4


@pytest.mark.parametrize(
    "query",
    [
        "MySQL and PostgreSQL database profile configuration and integration tests",
        "MySQL, PostgreSQL database profile configuration, integration tests",
    ],
)
def test_coordinated_database_clauses_reuse_all_resolved_subjects(
    query: str,
) -> None:
    needs = derive_evidence_needs(bundle(query=query), candidates=())

    assert required(needs) == [
        ("configs_docs", ("MySQL",)),
        ("configs_docs", ("PostgreSQL",)),
        ("tests", ("MySQL",)),
        ("tests", ("PostgreSQL",)),
    ]


@pytest.mark.parametrize(
    "query",
    [
        "Owner and Pet controller and tests",
        "Owner, Pet controller, tests",
    ],
)
def test_coordinated_generic_clauses_reuse_all_resolved_subjects(
    query: str,
) -> None:
    needs = derive_evidence_needs(bundle(query=query), candidates=())

    assert required(needs) == [
        ("entrypoints", ("Owner",)),
        ("entrypoints", ("Pet",)),
        ("tests", ("Owner",)),
        ("tests", ("Pet",)),
    ]


def test_mixed_clauses_bind_each_subject_only_to_its_role_category() -> None:
    needs = derive_evidence_needs(
        bundle(query="Owner form and Pet model type"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("Owner",)),
        ("related_types", ("Pet",)),
    ]


@pytest.mark.parametrize("separator", ["; ", "\n"])
def test_independent_boundaries_do_not_backfill_later_subjects(
    separator: str,
) -> None:
    needs = derive_evidence_needs(
        bundle(query=f"find service implementation{separator}Pet model type"),
        candidates=(),
    )

    assert required(needs) == [
        ("implementations", ()),
        ("related_types", ("Pet",)),
    ]


@pytest.mark.parametrize("separator", ["; ", "\n"])
def test_independent_boundaries_do_not_leak_identifier_subjects(
    separator: str,
) -> None:
    needs = derive_evidence_needs(
        bundle(query=f"OwnerController{separator}Pet model type"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("OwnerController",)),
        ("related_types", ("Pet",)),
    ]


def test_coordinated_identifier_boundary_does_not_override_scoped_subject() -> None:
    needs = derive_evidence_needs(
        bundle(query="OwnerController and Pet model type"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("OwnerController",)),
        ("related_types", ("Pet",)),
    ]


@pytest.mark.parametrize("separator", [" and ", ", "])
def test_following_identifier_boundary_does_not_override_scoped_subject(
    separator: str,
) -> None:
    needs = derive_evidence_needs(
        bundle(query=f"Pet model type{separator}OwnerController"),
        candidates=(),
    )

    assert required(needs) == [
        ("related_types", ("Pet",)),
        ("entrypoints", ("OwnerController",)),
    ]


@pytest.mark.parametrize("separator", [" and ", ", "])
def test_subjectful_test_stops_before_following_identifier(
    separator: str,
) -> None:
    needs = derive_evidence_needs(
        bundle(query=f"PetController tests{separator}OwnerController"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("PetController",)),
        ("entrypoints", ("OwnerController",)),
        ("tests", ("PetController",)),
    ]


@pytest.mark.parametrize("separator", [" and ", ", "])
def test_reversed_subjectful_test_has_symmetric_identifier_boundary(
    separator: str,
) -> None:
    needs = derive_evidence_needs(
        bundle(query=f"OwnerController{separator}PetController tests"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("OwnerController",)),
        ("entrypoints", ("PetController",)),
        ("tests", ("PetController",)),
    ]


@pytest.mark.parametrize("separator", [" and ", ", "])
def test_subjectless_role_consumes_one_following_identifier_boundary(
    separator: str,
) -> None:
    needs = derive_evidence_needs(
        bundle(query=f"tests{separator}OwnerController"),
        candidates=(),
    )

    assert required(needs) == [
        ("tests", ("OwnerController",)),
        ("entrypoints", ("OwnerController",)),
    ]


def test_unscoped_predicate_does_not_steal_a_later_coordinated_subject() -> None:
    needs = derive_evidence_needs(
        bundle(query="find service implementation and Pet model type"),
        candidates=(),
    )

    assert required(needs) == [
        ("implementations", ()),
        ("related_types", ("Pet",)),
    ]


def test_trailing_subject_propagates_left_across_subjectless_roles() -> None:
    needs = derive_evidence_needs(
        bundle(query="controller and service for Owner"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("Owner",)),
        ("implementations", ("Owner",)),
    ]


def test_trailing_combining_subject_uses_raw_offset_and_nfc_public_value() -> None:
    composed = derive_evidence_needs(
        bundle(query="controller and service for Café"),
        candidates=(),
    )
    decomposed = derive_evidence_needs(
        bundle(query="controller and service for Cafe\u0301"),
        candidates=(),
    )

    expected = [
        ("entrypoints", ("Café",)),
        ("implementations", ("Café",)),
    ]
    assert required(composed) == expected
    assert required(decomposed) == expected
    assert tuple(need for need in composed if need.required) == tuple(
        need for need in decomposed if need.required
    )


def test_trailing_database_subjects_propagate_left_as_one_resolved_set() -> None:
    needs = derive_evidence_needs(
        bundle(
            query=(
                "configuration and integration tests for MySQL and PostgreSQL"
            )
        ),
        candidates=(),
    )

    assert required(needs) == [
        ("configs_docs", ("MySQL",)),
        ("configs_docs", ("PostgreSQL",)),
        ("tests", ("MySQL",)),
        ("tests", ("PostgreSQL",)),
    ]


def test_trailing_model_subject_scopes_preceding_form_role() -> None:
    needs = derive_evidence_needs(
        bundle(query="form and model type for Owner"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("Owner",)),
        ("related_types", ("Owner",)),
    ]


def test_multiple_identifiers_bind_only_to_their_own_exact_roles() -> None:
    needs = derive_evidence_needs(
        bundle(query="OwnerController OwnerRepository"),
        candidates=(),
    )

    assert required(needs) == [
        ("entrypoints", ("OwnerController",)),
        ("implementations", ("OwnerRepository",)),
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("CloudPlatform", []),
        ("OwnerCommand", [("entrypoints", ("OwnerCommand",))]),
        ("OwnerServiceImpl", [("implementations", ("OwnerServiceImpl",))]),
        ("OwnerIntegrationTests", [("tests", ("OwnerIntegrationTests",))]),
        ("OwnerDTO", [("related_types", ("OwnerDTO",))]),
        ("OwnerVO", [("related_types", ("OwnerVO",))]),
    ],
)
def test_identifier_roles_use_exact_camel_suffix_tokens(
    query: str,
    expected: list[tuple[str, tuple[str, ...]]],
) -> None:
    needs = derive_evidence_needs(bundle(query=query), candidates=())

    assert required(needs) == expected


def test_subjects_normalize_unicode_and_collision_suffixes_in_encounter_order() -> None:
    needs = derive_evidence_needs(
        bundle(query="  Owner, owner! and OWNER\tcontroller"),
        candidates=(),
    )
    entrypoint_needs = tuple(
        need
        for need in needs
        if need.required and need.category == "entrypoints"
    )

    assert [need.subject_terms for need in entrypoint_needs] == [
        ("Owner",),
        ("owner",),
        ("OWNER",),
    ]
    assert [need.id for need in entrypoint_needs] == [
        "need:entrypoints:owner",
        "need:entrypoints:owner:2",
        "need:entrypoints:owner:3",
    ]

    unicode_cases = {
        "Cafe\u0301 controller": "Café",
        "\U0001f680 controller": "\U0001f680",
        f"{'\u754c' * 65} controller": "\u754c" * 64,
    }
    for query, expected_subject in unicode_cases.items():
        subject = next(
            need.subject_terms[0]
            for need in derive_evidence_needs(bundle(query=query), candidates=())
            if need.required and need.category == "entrypoints"
        )
        assert subject == expected_subject
        assert len(subject) <= 64


def test_exact_identifier_role_creates_only_its_own_required_category() -> None:
    needs = derive_evidence_needs(
        bundle(query="OwnerController"),
        candidates=(),
    )

    assert required(needs) == [("entrypoints", ("OwnerController",))]
    assert needs[0].provenance == "explicit_identifier"
    assert not any(
        need.required and need.category in {"implementations", "related_types"}
        for need in needs
    )


def test_duplicate_identifier_merge_keeps_earliest_category_order_and_provenance() -> None:
    needs = derive_evidence_needs(
        bundle(query="controller tests for OwnerController"),
        candidates=(),
    )
    required_needs = tuple(need for need in needs if need.required)

    assert [
        (need.category, need.subject_terms, need.provenance)
        for need in required_needs
    ] == [
        ("entrypoints", ("OwnerController",), "explicit_identifier"),
        ("tests", ("OwnerController",), "explicit_query"),
    ]
    assert sum(
        need.category == "entrypoints"
        and need.subject_terms == ("OwnerController",)
        for need in required_needs
    ) == 1


def test_grounded_successful_planner_term_is_recommended() -> None:
    query_bundle = bundle(
        query="opaque",
        results=[result("src/main/resources/application-postgresql.properties")],
        planner=QueryPlan(
            original_query="opaque",
            grep_keywords=["PostgreSQL"],
            status="ok",
        ),
    )
    candidates = normalize_candidates(query_bundle)

    needs = derive_evidence_needs(query_bundle, candidates=candidates)

    planner_need = next(need for need in needs if need.provenance == "planner_supported")
    assert (
        planner_need.category,
        planner_need.subject_terms,
        planner_need.required,
    ) == ("configs_docs", ("PostgreSQL",), False)


@pytest.mark.parametrize("status", ["ok", "disabled", "fallback", "error"])
def test_unsuccessful_or_ungrounded_planner_terms_create_no_need(status: str) -> None:
    query_bundle = bundle(
        query="opaque",
        results=[result("src/main/resources/application.properties")],
        planner=QueryPlan(
            original_query="opaque",
            grep_keywords=["PostgreSQL"],
            status=status,
        ),
    )

    needs = derive_evidence_needs(
        query_bundle,
        candidates=normalize_candidates(query_bundle),
    )

    assert not any(need.provenance == "planner_supported" for need in needs)


def test_generated_discarded_followup_and_summary_values_never_create_subjects() -> None:
    forbidden = {
        "expanded-secret",
        "followup-secret",
        "discarded-secret",
        "oups",
    }
    query_bundle = bundle(
        query="owner controller",
        results=[result("src/main/controller/OwnerController.java")],
        expanded_tokens=["expanded-secret"],
        followup_keywords=["followup-secret"],
        summary=RetrievalSummary(
            entry_points=["GET /oups"],
            implementation=["discarded-secret"],
        ),
        planner=QueryPlan(
            original_query="owner controller",
            grep_keywords=["discarded-secret"],
            discarded_hints=["discarded-secret"],
            status="ok",
        ),
    )

    needs = derive_evidence_needs(
        query_bundle,
        candidates=normalize_candidates(query_bundle),
    )

    public_text = " ".join(
        (need.id + " " + " ".join(need.subject_terms)).casefold()
        for need in needs
    )
    assert all(value not in public_text for value in forbidden)


def test_intent_inference_runs_once_and_only_on_the_original_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_calls: list[tuple[str, list[str]]] = []
    identifier_calls: list[tuple[str, list[str]]] = []
    real_query_intent = context_needs.infer_query_intent
    real_identifier_intent = context_needs.infer_identifier_intent

    def capture_query_intent(query: str, tokens: list[str]):
        query_calls.append((query, tokens))
        return real_query_intent(query, tokens)

    def capture_identifier_intent(query: str, tokens: list[str]):
        identifier_calls.append((query, tokens))
        return real_identifier_intent(query, tokens)

    monkeypatch.setattr(context_needs, "infer_query_intent", capture_query_intent)
    monkeypatch.setattr(
        context_needs,
        "infer_identifier_intent",
        capture_identifier_intent,
    )
    original = "OwnerController tests"
    query_bundle = bundle(
        query=original,
        results=[result("src/main/controller/OwnerController.java")],
        planner=QueryPlan(
            original_query=original,
            rewritten_queries=["PostgreSQL configuration"],
            grep_keywords=["PostgreSQL"],
            symbol_hints=["PostgreSQLConfig"],
            status="ok",
        ),
    )

    derive_evidence_needs(
        query_bundle,
        candidates=normalize_candidates(query_bundle),
    )

    assert [call[0] for call in query_calls] == [original]
    assert [call[0] for call in identifier_calls] == [original]
    assert query_calls[0][1] == original.split()
    assert identifier_calls[0][1] == tokenize_query(original)


def test_structural_recommendations_are_scoped_ordered_and_never_required() -> None:
    needs = derive_evidence_needs(
        bundle(query="OwnerController controller"),
        candidates=(),
    )

    assert [(need.category, need.required, need.provenance) for need in needs] == [
        ("entrypoints", True, "explicit_identifier"),
        ("implementations", False, "structural_recommendation"),
        ("tests", False, "structural_recommendation"),
    ]
    assert all(need.subject_terms == ("OwnerController",) for need in needs)


def test_explicit_test_need_suppresses_duplicate_structural_test_need() -> None:
    needs = derive_evidence_needs(
        bundle(query="OwnerController tests"),
        candidates=(),
    )

    assert sum(
        need.category == "tests" and need.subject_terms == ("OwnerController",)
        for need in needs
    ) == 1
    assert next(need for need in needs if need.category == "tests").required is True


def make_candidate(
    *,
    path: str = "src/main/controller/OwnerController.java",
    group: str = "entrypoints",
    content: str = "class OwnerController {}",
    provenance: str | None = None,
) -> ContextCandidate:
    return ContextCandidate(
        key=path,
        file_path=path,
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        group=group,
        role="fixture",
        classification_basis="path",
        source_kind="result",
        retrieval_rank=0,
        source_order=0,
        relevance_score=1.0,
        reasons=("fixture",),
        score_parts={},
        spans=(),
        trusted_provenance_text=provenance or path,
        protected_direct=True,
    )


def need(
    category: str,
    *subjects: str,
) -> EvidenceNeed:
    return EvidenceNeed(
        id=f"need:{category}:fixture",
        category=category,
        subject_terms=tuple(subjects),
        required=True,
        provenance="explicit_query",
        matched_item_ids=(),
    )


def test_candidate_matching_requires_category_and_every_explicit_subject() -> None:
    candidate = make_candidate()

    assert candidate_matches_need(candidate, need("entrypoints", "Owner"))
    assert candidate_matches_need(
        candidate,
        need("entrypoints", "Owner", "Controller"),
    )
    assert not candidate_matches_need(candidate, need("tests", "Owner"))
    assert not candidate_matches_need(
        candidate,
        need("entrypoints", "Owner", "Pet"),
    )


def test_candidate_matching_uses_ascii_boundaries_cjk_and_supplied_content() -> None:
    neutral = make_candidate(
        path="src/main/controller/Details.java",
        content="PostgreSQL 宠物主人详情页",
    )
    misleading = replace(neutral, content="postgresqlish")

    assert candidate_matches_need(neutral, need("entrypoints", "PostgreSQL"))
    assert candidate_matches_need(neutral, need("entrypoints", "宠物主人详情页"))
    assert not candidate_matches_need(misleading, need("entrypoints", "PostgreSQL"))
    assert not candidate_matches_need(
        replace(misleading, content="PostgreSQL2"),
        need("entrypoints", "PostgreSQL"),
    )
    assert candidate_matches_need(
        misleading,
        need("entrypoints", "PostgreSQL"),
        content="PostgreSQL retained excerpt",
    )
    assert not candidate_matches_need(
        neutral,
        need("entrypoints", "PostgreSQL"),
        content="subject was truncated away",
    )


def test_anchor_reason_provenance_remains_searchable_without_content_duplication() -> None:
    query_bundle = bundle(
        query="PostgreSQL configuration",
        results=[
            result(
                "src/main/resources/application.properties",
                content="spring.application.name=petclinic",
                reasons=["result"],
            )
        ],
        anchors=[
            anchor(
                "src/main/resources/application.properties",
                content="ANCHOR CONTENT MUST NOT BE COPIED",
                reasons=["PostgreSQL profile anchor"],
            )
        ],
    )

    candidate = normalize_candidates(query_bundle)[0]

    assert candidate.content == "spring.application.name=petclinic"
    assert "ANCHOR CONTENT MUST NOT BE COPIED" not in candidate.trusted_provenance_text
    assert candidate_matches_need(candidate, need("configs_docs", "PostgreSQL"))


@pytest.mark.parametrize(
    "content",
    [
        "import jakarta.persistence.Entity;\npublic class Owner {}",
        "// @Entity\npublic class Owner {}",
        'String marker = "@Entity";\npublic class Owner {}',
        'String marker = """@Entity""";\npublic class Owner {}',
    ],
)
def test_non_declaration_entity_mentions_do_not_change_candidate_category(
    content: str,
) -> None:
    query_bundle = bundle(
        query="Owner model type",
        results=[result("src/main/java/example/Owner.java", content=content)],
    )
    candidate = normalize_candidates(query_bundle)[0]
    owner_need = next(
        item
        for item in derive_evidence_needs(query_bundle, candidates=(candidate,))
        if item.required
    )

    assert candidate.group == "supporting"
    assert not candidate_matches_need(candidate, owner_need)


def test_need_derivation_and_matching_are_pure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_io(*args: object, **kwargs: object) -> None:
        pytest.fail("context need logic must not perform I/O")

    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)
    query_bundle = bundle(
        query="OwnerController tests",
        results=[result("src/main/controller/OwnerController.java")],
    )
    candidates = normalize_candidates(query_bundle)

    needs = derive_evidence_needs(query_bundle, candidates=candidates)

    assert any(candidate_matches_need(candidates[0], item) for item in needs)


def test_missing_evidence_uses_fixed_bounded_public_templates() -> None:
    evidence_needs = (
        EvidenceNeed(
            id="need:configs_docs:postgresql",
            category="configs_docs",
            subject_terms=("PostgreSQL",),
            required=True,
            provenance="explicit_query",
            matched_item_ids=(),
        ),
        EvidenceNeed(
            id="need:tests:owner-controller",
            category="tests",
            subject_terms=("OwnerController",),
            required=False,
            provenance="structural_recommendation",
            matched_item_ids=(),
        ),
        EvidenceNeed(
            id="need:implementations:any",
            category="implementations",
            subject_terms=(),
            required=True,
            provenance="explicit_query",
            matched_item_ids=("item:0",),
        ),
    )

    missing = context_needs.derive_missing_evidence(evidence_needs)

    assert [vars(item) for item in missing] == [
        {
            "need_id": "need:configs_docs:postgresql",
            "category": "configs_docs",
            "required": True,
            "reason": (
                "required PostgreSQL configuration evidence is missing "
                "from the bounded context"
            ),
        },
        {
            "need_id": "need:tests:owner-controller",
            "category": "tests",
            "required": False,
            "reason": (
                "recommended OwnerController test evidence is missing "
                "from the bounded context"
            ),
        },
    ]
