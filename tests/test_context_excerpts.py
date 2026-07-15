from __future__ import annotations

import time
import unicodedata
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from context_search_tool.context_pack import (
    builder,
    excerpts,
    models,
    needs,
    serialization,
)
from context_search_tool.models import (
    QueryPlan,
    RetrievalResult,
    RetrievalSpan,
    RetrievalSummary,
)
from context_search_tool.retrieval import QueryBundle


def _options(**changes: int) -> models.ContextPackOptions:
    values = {
        "max_items": 12,
        "max_excerpts_per_item": 2,
        "max_excerpt_bytes": 4096,
        "max_item_content_bytes": 8192,
        "max_total_content_bytes": 49_152,
        "max_pack_bytes": 65_536,
        "context_before_lines": 0,
        "context_after_lines": 0,
    }
    values.update(changes)
    return models.ContextPackOptions(**values)


def _candidate(
    content: str,
    *,
    path: str = "config/application.properties",
    group: str = "configs_docs",
    source_kind: str = "result",
    spans: tuple[RetrievalSpan, ...] = (),
    protected_direct: bool = False,
) -> models.ContextCandidate:
    line_count = max(1, len(content.splitlines()))
    return models.ContextCandidate(
        key=path,
        file_path=path,
        start_line=1,
        end_line=line_count,
        content=content,
        group=group,
        role="runtime_config",
        classification_basis="path",
        source_kind=source_kind,
        retrieval_rank=0 if source_kind == "result" else None,
        source_order=0,
        relevance_score=1.0 if source_kind == "result" else None,
        reasons=("fixture",),
        score_parts={},
        spans=spans,
        trusted_provenance_text=path,
        protected_direct=protected_direct,
    )


def _need(
    subject: str,
    *,
    need_id: str = "need:configs_docs:postgresql",
    required: bool = True,
    category: str = "configs_docs",
) -> models.EvidenceNeed:
    return models.EvidenceNeed(
        id=need_id,
        category=category,
        subject_terms=(subject,),
        required=required,
        provenance="explicit_query" if required else "structural_recommendation",
        matched_item_ids=(),
    )


def _result(
    path: str,
    content: str,
    *,
    spans: tuple[RetrievalSpan, ...] = (),
    rank_score: float = 1.0,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=rank_score,
        score_parts={"evidence_priority": 0.0},
        reasons=["fixture"],
        followup_keywords=[],
        spans=spans,
    )


def _bundle(query: str, results: list[RetrievalResult]) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=[],
        results=results,
        followup_keywords=[],
        summary=RetrievalSummary(),
        planner=QueryPlan.disabled_default(),
        evidence_anchors=[],
    )


def test_required_matching_span_wins_over_higher_scored_optional_span() -> None:
    candidate = _candidate(
        "optional\ncontext\nmore\npostgresql.url=db\ntail",
        spans=(
            RetrievalSpan(1, 1, 99.0, ("semantic",)),
            RetrievalSpan(4, 4, 1.0, ("lexical",)),
        ),
    )

    selected = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(_need("PostgreSQL"),),
        options=_options(max_excerpts_per_item=1),
    )

    assert [(item.start_line, item.end_line) for item in selected] == [(4, 4)]
    assert "postgresql" in selected[0].content.casefold()


def test_windows_expand_merge_adjacency_then_restore_source_order() -> None:
    candidate = _candidate(
        "one\ntwo\nthree\nfour\nfive\nsix",
        spans=(
            RetrievalSpan(5, 5, 8.0, ("semantic",)),
            RetrievalSpan(1, 1, 6.0, ("lexical",)),
            RetrievalSpan(2, 2, 7.0, ("signal",)),
        ),
    )

    selected = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(),
        options=_options(max_excerpts_per_item=2),
    )

    assert [(item.start_line, item.end_line) for item in selected] == [(1, 2), (5, 5)]
    assert [item.content for item in selected] == ["one\ntwo\n", "five\n"]


def test_duplicate_spans_keep_highest_score_and_stable_source_union() -> None:
    candidate = _candidate(
        "one\ntwo\nthree",
        spans=(
            RetrievalSpan(2, 2, 1.0, ("semantic", "semantic")),
            RetrievalSpan(2, 2, 3.0, ("lexical", "semantic")),
            RetrievalSpan(1, 2, 2.0, ("path_symbol",)),
        ),
    )

    normalized = excerpts.normalize_candidate_spans(candidate)

    assert normalized == (
        RetrievalSpan(2, 2, 3.0, ("semantic", "lexical")),
        RetrievalSpan(1, 2, 2.0, ("path_symbol",)),
    )


def test_result_without_spans_uses_exact_legacy_fallback_span() -> None:
    candidate = replace(_candidate("one\ntwo\nthree"), relevance_score=2.5)

    assert excerpts.normalize_candidate_spans(candidate) == (
        RetrievalSpan(1, 3, 2.5, ("legacy_result",)),
    )


def test_anchor_prefers_exact_subject_line_then_head_fallback() -> None:
    candidate = _candidate(
        "head\nother\nPostgreSQL profile\ntail",
        source_kind="evidence_anchor",
    )

    matched = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(_need("PostgreSQL"),),
        options=_options(max_excerpts_per_item=1, max_excerpt_bytes=20),
    )
    fallback = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(_need("MySQL"),),
        options=_options(max_excerpts_per_item=1, max_excerpt_bytes=20),
    )

    assert (matched[0].start_line, matched[0].content) == (3, "PostgreSQL profile\n")
    assert (fallback[0].start_line, fallback[0].content) == (1, "head\n")


def test_short_anchor_is_retained_whole_and_long_anchor_expands_match() -> None:
    short = _candidate("README\nsetup", source_kind="evidence_anchor")
    long = _candidate(
        "head\nbefore\nPostgreSQL profile\nafter\ntail",
        source_kind="evidence_anchor",
    )

    short_excerpt = excerpts.build_candidate_excerpts(
        candidate=short,
        needs=(),
        options=_options(),
    )
    long_excerpt = excerpts.build_candidate_excerpts(
        candidate=long,
        needs=(_need("PostgreSQL"),),
        options=_options(
            max_excerpt_bytes=35,
            context_before_lines=1,
            context_after_lines=1,
        ),
    )

    assert short_excerpt[0].content == "README\nsetup"
    assert (long_excerpt[0].start_line, long_excerpt[0].end_line) == (2, 4)


@pytest.mark.parametrize(
    "candidate",
    [
        replace(_candidate("line"), start_line=0),
        replace(_candidate("line"), end_line=0),
        _candidate("line", spans=(RetrievalSpan(1, 1, float("nan"), ("ranked",)),)),
        _candidate("line", spans=(RetrievalSpan(2, 2, 1.0, ("ranked",)),)),
        _candidate("line\ntwo", spans=(RetrievalSpan(2, 1, 1.0, ("ranked",)),)),
    ],
)
def test_invalid_line_or_span_contract_fails_sanitized(
    candidate: models.ContextCandidate,
) -> None:
    with pytest.raises(models.ContextPackError) as exc_info:
        excerpts.build_candidate_excerpts(
            candidate=candidate,
            needs=(),
            options=_options(),
        )

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "content",
    [
        "ASCII alpha beta\nsecond line\n",
        "中文配置数据库\n第二行\n",
        "emoji 🐶🐱✨\nnext\n",
        "e\u0301cole and cafe\u0301\nnext\n",
        "first\r\nsecond\r\n",
        "one very very very long single line",
        "no final newline",
        "first\n\n",
    ],
)
def test_excerpt_cropping_is_utf8_safe_and_preserves_source_bytes(content: str) -> None:
    candidate = _candidate(content)
    selected = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(),
        options=_options(max_excerpt_bytes=17),
    )

    assert selected
    for excerpt in selected:
        assert excerpt.content_bytes == len(excerpt.content.encode("utf-8"))
        assert excerpt.content_bytes <= 17
        assert excerpt.content.encode("utf-8").decode("utf-8") == excerpt.content
        assert excerpt.content in content
    if len(content.encode("utf-8")) <= 17:
        assert selected[0].content == content


def test_byte_crop_keeps_required_subject_line_before_surrounding_context() -> None:
    candidate = _candidate(
        "large leading context line\nPostgreSQL\nlarge trailing context line",
        spans=(RetrievalSpan(1, 3, 1.0, ("semantic",)),),
    )

    selected = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(_need("PostgreSQL"),),
        options=_options(max_excerpt_bytes=12),
    )

    assert selected[0].content == "PostgreSQL\n"
    assert selected[0].truncated is True


@pytest.mark.parametrize(
    ("content", "subject"),
    [
        (f"{'ß' * 100}PostgreSQL", "PostgreSQL"),
        (f"{'x' * 100}Cafe\u0301", "Café"),
    ],
)
def test_required_crop_maps_normalized_match_to_original_offsets(
    content: str,
    subject: str,
) -> None:
    candidate = _candidate(
        content,
        spans=(RetrievalSpan(1, 1, 1.0, ("semantic",)),),
    )

    selected = excerpts.build_candidate_excerpts(
        candidate=candidate,
        needs=(_need(subject),),
        options=_options(max_excerpt_bytes=20),
    )

    assert unicodedata.normalize("NFC", subject).casefold() in unicodedata.normalize(
        "NFC",
        selected[0].content,
    ).casefold()
    assert selected[0].content in candidate.content
    assert selected[0].content_bytes <= 20


@pytest.mark.parametrize(
    ("content", "subject", "max_excerpt_bytes", "expected"),
    [
        ("bobcat" + "x" * 100 + " cat", "cat", 4, "cat"),
        ("核心化" + "x" * 100, "核心", 6, "核心"),
    ],
)
def test_required_crop_uses_candidate_subject_matching_semantics(
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    subject: str,
    max_excerpt_bytes: int,
    expected: str,
) -> None:
    required = _need(subject)
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (required,),
    )

    pack = builder.build_context_pack(
        _bundle("fixture", [_result("config/application.properties", content)]),
        _options(
            max_excerpt_bytes=max_excerpt_bytes,
            max_item_content_bytes=max_excerpt_bytes,
            max_total_content_bytes=max_excerpt_bytes,
            max_pack_bytes=4096,
        ),
    )

    assert pack.items[0].excerpts[0].content == expected
    assert pack.evidence_needs[0].matched_item_ids == ("item:0",)
    assert pack.status == "ready"


def test_builder_enforces_each_subordinate_budget_and_rechecks_matches() -> None:
    results = [
        _result(
            "src/main/controller/OwnerController.java",
            "class OwnerController {}\nline two\nline three",
            spans=(
                RetrievalSpan(1, 1, 4.0, ("path_symbol",)),
                RetrievalSpan(3, 3, 2.0, ("semantic",)),
            ),
        ),
        _result(
            "tests/OwnerControllerTests.java",
            "class OwnerControllerTests {}\nline two\nline three",
            spans=(RetrievalSpan(1, 3, 3.0, ("lexical",)),),
        ),
    ]
    options = _options(
        max_items=1,
        max_excerpts_per_item=1,
        max_excerpt_bytes=18,
        max_item_content_bytes=18,
        max_total_content_bytes=18,
        max_pack_bytes=4096,
    )

    pack = builder.build_context_pack(
        _bundle("OwnerController tests", results),
        options,
    )
    payload = serialization.context_pack_payload(pack)

    assert len(pack.items) <= 1
    assert all(len(item.excerpts) <= 1 for item in pack.items)
    assert all(
        excerpt.content_bytes <= options.max_excerpt_bytes
        for item in pack.items
        for excerpt in item.excerpts
    )
    assert all(
        sum(excerpt.content_bytes for excerpt in item.excerpts)
        <= options.max_item_content_bytes
        for item in pack.items
    )
    assert pack.budget.content_bytes <= options.max_total_content_bytes
    assert pack.budget.pack_bytes == len(serialization.canonical_context_pack_bytes(pack))
    assert pack.budget.pack_bytes <= options.max_pack_bytes
    assert payload["budget"]["pack_bytes"] == pack.budget.pack_bytes


def test_required_512_reservation_precedes_recommended_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = models.EvidenceNeed(
        id="need:entrypoints:general",
        category="entrypoints",
        subject_terms=(),
        required=True,
        provenance="explicit_query",
        matched_item_ids=(),
    )
    recommended = models.EvidenceNeed(
        id="need:tests:general",
        category="tests",
        subject_terms=(),
        required=False,
        provenance="structural_recommendation",
        matched_item_ids=(),
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (required, recommended),
    )
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result("src/main/controller/AppController.java", "r" * 600),
                _result("tests/AppControllerTests.java", "t" * 600),
            ],
        ),
        _options(
            max_items=2,
            max_excerpt_bytes=600,
            max_item_content_bytes=600,
            max_total_content_bytes=700,
            max_pack_bytes=4096,
        ),
    )

    content_by_group = {
        item.group: sum(excerpt.content_bytes for excerpt in item.excerpts)
        for item in pack.items
    }
    assert content_by_group == {"entrypoints": 512, "tests": 188}


def test_allocation_redistributes_unused_line_cropping_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = models.EvidenceNeed(
        id="need:entrypoints:general",
        category="entrypoints",
        subject_terms=(),
        required=True,
        provenance="explicit_query",
        matched_item_ids=(),
    )
    recommended = models.EvidenceNeed(
        id="need:tests:general",
        category="tests",
        subject_terms=(),
        required=False,
        provenance="structural_recommendation",
        matched_item_ids=(),
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (required, recommended),
    )
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(
                    "src/main/controller/AppController.java",
                    f"{'r' * 399}\n{'R' * 400}",
                ),
                _result("tests/AppControllerTests.java", "t" * 600),
            ],
        ),
        _options(
            max_items=2,
            max_excerpt_bytes=800,
            max_item_content_bytes=800,
            max_total_content_bytes=800,
            max_pack_bytes=4096,
        ),
    )

    content_by_group = {
        item.group: sum(excerpt.content_bytes for excerpt in item.excerpts)
        for item in pack.items
    }
    assert content_by_group == {"entrypoints": 400, "tests": 400}


def test_item_allocation_reserves_each_disjoint_required_excerpt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = tuple(
        _need(subject, need_id=f"need:configs_docs:{subject.casefold()}")
        for subject in ("Alpha", "Beta")
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: required,
    )
    content = "Alpha " + "x" * 594 + "\nnoise\nBeta"
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(
                    "config/application.properties",
                    content,
                    spans=(
                        RetrievalSpan(1, 1, 2.0, ("lexical",)),
                        RetrievalSpan(3, 3, 1.0, ("semantic",)),
                    ),
                )
            ],
        ),
        _options(
            max_items=1,
            max_excerpts_per_item=2,
            max_excerpt_bytes=512,
            max_item_content_bytes=512,
            max_total_content_bytes=512,
            max_pack_bytes=4096,
        ),
    )

    assert [excerpt.start_line for excerpt in pack.items[0].excerpts] == [1, 3]
    assert all(
        any(subject in excerpt.content for excerpt in pack.items[0].excerpts)
        for subject in ("Alpha", "Beta")
    )
    assert pack.budget.content_bytes == 512
    assert all(need.matched_item_ids == ("item:0",) for need in pack.evidence_needs)
    assert pack.status == "ready"


def test_item_allocation_prefers_one_excerpt_with_strictly_more_required_coverage(
) -> None:
    alpha = "甲" * 64
    beta = "乙" * 64
    alpha_only = models.ContextExcerpt(
        start_line=1,
        end_line=1,
        content=alpha,
        content_bytes=len(alpha.encode("utf-8")),
        truncated=False,
    )
    alpha_and_beta = models.ContextExcerpt(
        start_line=2,
        end_line=2,
        content=alpha + beta,
        content_bytes=len((alpha + beta).encode("utf-8")),
        truncated=False,
    )

    fitted = excerpts.fit_excerpts_to_bytes(
        (alpha_only, alpha_and_beta),
        512,
        required_subject_terms=(alpha, beta),
    )

    assert fitted == (alpha_and_beta,)


def test_item_allocation_uses_smaller_combination_when_coverage_ties() -> None:
    alpha = "甲" * 64
    beta = "乙" * 64
    redundant_large = models.ContextExcerpt(
        start_line=1,
        end_line=1,
        content=alpha + "x" * 100 + beta,
        content_bytes=len((alpha + "x" * 100 + beta).encode("utf-8")),
        truncated=False,
    )
    alpha_only = models.ContextExcerpt(
        start_line=2,
        end_line=2,
        content=alpha,
        content_bytes=len(alpha.encode("utf-8")),
        truncated=False,
    )
    beta_only = models.ContextExcerpt(
        start_line=3,
        end_line=3,
        content=beta,
        content_bytes=len(beta.encode("utf-8")),
        truncated=False,
    )

    fitted = excerpts.fit_excerpts_to_bytes(
        (redundant_large, alpha_only, beta_only),
        512,
        required_subject_terms=(alpha, beta),
    )

    assert fitted == (alpha_only, beta_only)
    assert sum(excerpt.content_bytes for excerpt in fitted) == 384


@pytest.mark.parametrize(
    ("subjects", "source_prefix"),
    [
        (("Alpha", "Beta"), "Beta Alpha "),
        (("Café", "核心"), "核心 Cafe\u0301 "),
    ],
)
def test_item_allocation_preserves_joint_required_slice_in_source_order(
    monkeypatch: pytest.MonkeyPatch,
    subjects: tuple[str, str],
    source_prefix: str,
) -> None:
    required = tuple(
        _need(subject, need_id=f"need:configs_docs:{index}")
        for index, subject in enumerate(subjects)
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: required,
    )
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(
                    "config/application.properties",
                    source_prefix + "x" * 594,
                    spans=(RetrievalSpan(1, 1, 1.0, ("semantic",)),),
                )
            ],
        ),
        _options(
            max_items=1,
            max_excerpts_per_item=1,
            max_excerpt_bytes=512,
            max_item_content_bytes=512,
            max_total_content_bytes=512,
            max_pack_bytes=4096,
        ),
    )

    assert pack.items[0].excerpts[0].content.startswith(source_prefix)
    assert pack.items[0].excerpts[0].content_bytes == 512
    assert all(need.matched_item_ids == ("item:0",) for need in pack.evidence_needs)
    assert pack.status == "ready"


def test_joint_required_slice_uses_nearest_source_occurrences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = tuple(
        _need(subject, need_id=f"need:configs_docs:{index}")
        for index, subject in enumerate(("Alpha", "Beta"))
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: required,
    )
    content = "Alpha " + "x" * 100 + " Beta Alpha " + "y" * 594
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(
                    "config/application.properties",
                    content,
                    spans=(RetrievalSpan(1, 1, 1.0, ("semantic",)),),
                )
            ],
        ),
        _options(
            max_items=1,
            max_excerpts_per_item=1,
            max_excerpt_bytes=512,
            max_item_content_bytes=512,
            max_total_content_bytes=512,
            max_pack_bytes=4096,
        ),
    )

    assert pack.items[0].excerpts[0].content.startswith("Beta Alpha ")
    assert all(need.matched_item_ids == ("item:0",) for need in pack.evidence_needs)
    assert pack.status == "ready"


def test_joint_required_slice_considers_overlapping_cjk_occurrences() -> None:
    content = "哈哈哈核心"
    original = models.ContextExcerpt(
        start_line=1,
        end_line=1,
        content=content,
        content_bytes=len(content.encode("utf-8")),
        truncated=False,
    )

    fitted = excerpts.fit_excerpts_to_bytes(
        (original,),
        12,
        required_subject_terms=("哈哈", "核心"),
    )

    assert fitted[0].content == "哈哈核心"
    assert fitted[0].content_bytes == 12


def test_overlapping_occurrence_scan_preserves_ascii_token_boundaries() -> None:
    content = "catcat cat Core"
    original = models.ContextExcerpt(
        start_line=1,
        end_line=1,
        content=content,
        content_bytes=len(content.encode("utf-8")),
        truncated=False,
    )

    fitted = excerpts.fit_excerpts_to_bytes(
        (original,),
        12,
        required_subject_terms=("cat", "Core"),
    )

    assert fitted[0].content == "cat Core"
    assert fitted[0].content_bytes == 8


@pytest.mark.parametrize(
    ("content", "subject", "expected"),
    [
        (
            "AppController app controller AppControllerX AppController",
            "AppController",
            ((0, 13), (14, 28), (29, 42), (44, 57)),
        ),
        ("哈哈哈核心", "哈哈", ((0, 2), (1, 3))),
        ("Cafe\u0301 Café", "Café", ((0, 5), (6, 10))),
        ("Straße STRASSE", "straße", ((0, 6), (7, 14))),
        ("catcat cat Core", "cat", ((7, 10),)),
    ],
)
def test_occurrence_scan_preserves_normalized_subject_semantics(
    content: str,
    subject: str,
    expected: tuple[tuple[int, int], ...],
) -> None:
    assert excerpts._normalized_match_spans(content, subject) == expected


def test_casefold_expansion_interior_matches_cover_raw_codepoint() -> None:
    assert needs.normalized_subject_match_spans("ß", "ſ") == ((0, 1), (1, 2))
    assert excerpts._normalized_match_spans("ß", "ſ") == ((0, 1), (0, 1))


def test_casefold_expansion_reservation_keeps_higher_priority_evidence() -> None:
    sharp_s = models.ContextExcerpt(
        start_line=1,
        end_line=1,
        content="ß",
        content_bytes=2,
        truncated=False,
    )
    beta = models.ContextExcerpt(
        start_line=2,
        end_line=2,
        content="Beta",
        content_bytes=4,
        truncated=False,
    )

    fitted = excerpts.fit_excerpts_to_bytes(
        (sharp_s, beta),
        4,
        required_subject_terms=("ſ", "Beta"),
    )

    assert fitted == (sharp_s,)


def test_decomposed_match_end_includes_zero_growth_combining_mark() -> None:
    assert excerpts._normalized_match_spans("Cafe\u0301Beta", "Café") == ((0, 5),)


@pytest.mark.parametrize(
    ("content", "subject"),
    [("ß", "ſ"), ("İ", "\u0307"), ("ﬃ", "ﬀ")],
)
def test_nonempty_normalized_matches_have_nonempty_raw_spans(
    content: str,
    subject: str,
) -> None:
    normalized = needs.normalized_subject_match_spans(content, subject)
    raw = excerpts._normalized_match_spans(content, subject)

    assert normalized
    assert all(start < end for start, end in normalized)
    assert len(raw) == len(normalized)
    assert all(start < end for start, end in raw)


def test_high_frequency_ascii_occurrences_normalize_content_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "\n".join(
        f".row-{index} {{ color: #123456; }}" for index in range(3132)
    )
    normalize = unicodedata.normalize
    tokenize = needs._ascii_and_camel_token_spans
    large_normalization_calls = 0
    tokenized_lengths: list[int] = []

    def counting_normalize(form: str, value: str) -> str:
        nonlocal large_normalization_calls
        if len(value) > 4096:
            large_normalization_calls += 1
        return normalize(form, value)

    def counting_tokenize(value: str):
        tokenized_lengths.append(len(value))
        return tokenize(value)

    monkeypatch.setattr(unicodedata, "normalize", counting_normalize)
    monkeypatch.setattr(needs, "_ascii_and_camel_token_spans", counting_tokenize)
    started = time.perf_counter()

    selected = excerpts._required_subject_slice(content, 4096, ("row",))

    elapsed = time.perf_counter() - started
    assert len(content) == 92_849
    assert selected == (1, 4, ("row",))
    assert large_normalization_calls == 1
    assert tokenized_lengths == [3, len(content)]
    assert elapsed < 5.0


def test_item_byte_ceiling_is_independent_of_excerpt_ceiling() -> None:
    content = "abcdefghij\nseparator\nklmnopqrst"
    pack = builder.build_context_pack(
        _bundle(
            "find source",
            [
                _result(
                    "src/plain.py",
                    content,
                    spans=(
                        RetrievalSpan(1, 1, 2.0, ("lexical",)),
                        RetrievalSpan(3, 3, 1.0, ("semantic",)),
                    ),
                )
            ],
        ),
        _options(
            max_excerpt_bytes=11,
            max_item_content_bytes=15,
            max_total_content_bytes=100,
            max_pack_bytes=4096,
        ),
    )

    assert len(pack.items[0].excerpts) == 2
    assert all(excerpt.content_bytes <= 11 for excerpt in pack.items[0].excerpts)
    assert sum(excerpt.content_bytes for excerpt in pack.items[0].excerpts) == 15


def test_excerpt_count_budget_only_exhausts_when_merged_window_is_lost() -> None:
    def build(spans: tuple[RetrievalSpan, ...]):
        return builder.build_context_pack(
            _bundle(
                "find source",
                [_result("src/plain.py", "one\ntwo\nthree", spans=spans)],
            ),
            _options(max_excerpts_per_item=1),
        )

    adjacent = build(
        (
            RetrievalSpan(1, 1, 2.0, ("lexical",)),
            RetrievalSpan(2, 2, 1.0, ("semantic",)),
        )
    )
    disjoint = build(
        (
            RetrievalSpan(1, 1, 2.0, ("lexical",)),
            RetrievalSpan(3, 3, 1.0, ("semantic",)),
        )
    )

    assert adjacent.budget.budget_exhausted is False
    assert disjoint.budget.budget_exhausted is True


def test_metadata_too_large_omits_unfit_item_without_exceeding_pack_ceiling() -> None:
    long_path = f"src/{'x' * 5000}/OwnerController.java"
    pack = builder.build_context_pack(
        _bundle("OwnerController", [_result(long_path, "class OwnerController {}")]),
        _options(
            max_excerpt_bytes=512,
            max_item_content_bytes=1024,
            max_total_content_bytes=1024,
            max_pack_bytes=4096,
        ),
    )

    assert pack.items == ()
    assert pack.status == "partial"
    assert pack.budget.pack_bytes <= 4096
    assert pack.budget.omitted_item_count == 1


def test_unfit_required_candidate_retries_bounded_alternative() -> None:
    unfit_path = f"config/{'x' * 5000}/postgresql.properties"
    fallback_path = "config/postgresql.properties"

    pack = builder.build_context_pack(
        _bundle(
            "PostgreSQL configuration",
            [
                _result(unfit_path, "postgresql.url=first"),
                _result(fallback_path, "postgresql.url=second"),
            ],
        ),
        _options(
            max_items=1,
            max_excerpt_bytes=512,
            max_item_content_bytes=1024,
            max_total_content_bytes=1024,
            max_pack_bytes=4096,
        ),
    )

    assert [item.file_path for item in pack.items] == [fallback_path]
    assert pack.evidence_needs[0].matched_item_ids == ("item:0",)
    assert pack.budget.omitted_item_count == 1


def test_retry_keeps_alternative_when_primary_match_is_compacted_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = _need("PostgreSQL")
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (required,),
    )
    primary = replace(
        _result("config/a.properties", "url=db"),
        reasons=["PostgreSQL " + "x" * 3000],
    )
    alternative_path = f"config/{'b' * 2700}/postgresql.properties"
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [primary, _result(alternative_path, "PostgreSQL")],
        ),
        _options(
            max_items=2,
            max_excerpt_bytes=512,
            max_item_content_bytes=1024,
            max_total_content_bytes=2048,
            max_pack_bytes=4096,
        ),
    )

    assert [item.file_path for item in pack.items] == [alternative_path]
    assert pack.items[0].excerpts[0].content == "PostgreSQL"
    assert pack.evidence_needs[0].matched_item_ids == ("item:0",)
    assert pack.status == "ready"
    assert pack.budget.pack_bytes <= 4096


def test_canonical_compaction_retains_required_matching_line_when_possible() -> None:
    lines = [
        *(f"leading context {index:03d}" for index in range(180)),
        "spring.datasource.platform=PostgreSQL",
        *(f"trailing context {index:03d}" for index in range(180)),
    ]
    content = "\n".join(lines)
    pack = builder.build_context_pack(
        _bundle(
            "PostgreSQL configuration",
            [
                _result(
                    "config/application.properties",
                    content,
                    spans=(RetrievalSpan(1, len(lines), 1.0, ("semantic",)),),
                )
            ],
        ),
        _options(
            max_excerpt_bytes=3500,
            max_item_content_bytes=3500,
            max_total_content_bytes=3500,
            max_pack_bytes=4096,
        ),
    )

    retained = "".join(
        excerpt.content for item in pack.items for excerpt in item.excerpts
    )
    assert "PostgreSQL" in retained
    assert pack.evidence_needs[0].matched_item_ids == ("item:0",)
    assert pack.budget.pack_bytes <= 4096


def test_optional_item_is_omitted_before_required_minimum_is_destroyed() -> None:
    optional_path = f"src/{'x' * 2700}/helper.py"
    pack = builder.build_context_pack(
        _bundle(
            "PostgreSQL configuration",
            [
                _result(
                    "config/application.properties",
                    "spring.datasource.platform=PostgreSQL",
                ),
                _result(optional_path, "def helper(): pass"),
            ],
        ),
        _options(
            max_items=2,
            max_excerpt_bytes=1024,
            max_item_content_bytes=1024,
            max_total_content_bytes=2048,
            max_pack_bytes=4096,
        ),
    )

    assert [item.file_path for item in pack.items] == [
        "config/application.properties"
    ]
    assert pack.items[0].excerpts[0].content == (
        "spring.datasource.platform=PostgreSQL"
    )
    assert pack.evidence_needs[0].matched_item_ids == ("item:0",)
    assert pack.budget.omitted_item_count == 1


def test_compaction_uses_candidate_priority_not_reverse_reading_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recommended = models.EvidenceNeed(
        id="need:configs_docs:postgresql",
        category="configs_docs",
        subject_terms=("PostgreSQL",),
        required=False,
        provenance="structural_recommendation",
        matched_item_ids=(),
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (recommended,),
    )
    support_path = "README.md"
    recommended_path = "config/application.properties"
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(support_path, "s" * 1700),
                _result(recommended_path, "PostgreSQL " + "r" * 1689),
            ],
        ),
        _options(
            max_items=2,
            max_excerpt_bytes=1800,
            max_item_content_bytes=1800,
            max_total_content_bytes=3400,
            max_pack_bytes=4096,
        ),
    )

    content_bytes = {
        item.file_path: sum(excerpt.content_bytes for excerpt in item.excerpts)
        for item in pack.items
    }
    assert content_bytes[recommended_path] == 1700
    assert content_bytes.get(support_path, 0) < 1700
    assert pack.evidence_needs[0].matched_item_ids


def test_empty_optional_omission_restores_preferred_recommended_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recommended = models.EvidenceNeed(
        id="need:tests:owner",
        category="tests",
        subject_terms=(),
        required=False,
        provenance="structural_recommendation",
        matched_item_ids=(),
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (recommended,),
    )
    recommended_path = "tests/OwnerTests.java"
    support_path = f"src/{'x' * 1500}/helper.py"
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(recommended_path, "t" * 1700),
                _result(support_path, "s" * 100),
            ],
        ),
        _options(
            max_items=2,
            max_excerpt_bytes=1800,
            max_item_content_bytes=1800,
            max_total_content_bytes=1800,
            max_pack_bytes=4096,
        ),
    )

    assert [item.file_path for item in pack.items] == [recommended_path]
    assert sum(
        excerpt.content_bytes for excerpt in pack.items[0].excerpts
    ) == 1700
    assert pack.budget.pack_bytes < 4096


def test_compaction_preserves_dynamic_unique_required_selection_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    needs = tuple(
        models.EvidenceNeed(
            id=f"need:configs_docs:{subject.casefold()}",
            category="configs_docs",
            subject_terms=(subject,),
            required=True,
            provenance="explicit_query",
            matched_item_ids=(),
        )
        for subject in ("Alpha", "Beta", "Gamma")
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: needs,
    )
    primary_path = "config/primary.properties"
    redundant_path = f"config/{'x' * 2000}/redundant.properties"
    gamma_path = "config/gamma.properties"
    pack = builder.build_context_pack(
        _bundle(
            "fixture",
            [
                _result(primary_path, "Alpha Beta"),
                _result(redundant_path, "Alpha Beta"),
                _result(gamma_path, "Gamma"),
            ],
        ),
        _options(
            max_items=3,
            max_excerpt_bytes=512,
            max_item_content_bytes=512,
            max_total_content_bytes=1536,
            max_pack_bytes=4096,
        ),
    )

    assert [item.file_path for item in pack.items] == [primary_path, gamma_path]
    assert pack.status == "ready"
    assert all(need.matched_item_ids for need in pack.evidence_needs)


def test_retained_rematch_does_not_trust_compacted_away_reason() -> None:
    raw_result = replace(
        _result("config/application.properties", "url=db"),
        reasons=[f"PostgreSQL {'x' * 2990}"],
    )

    pack = builder.build_context_pack(
        _bundle("PostgreSQL configuration", [raw_result]),
        _options(
            max_excerpt_bytes=1024,
            max_item_content_bytes=1024,
            max_total_content_bytes=2048,
            max_pack_bytes=4096,
        ),
    )

    assert pack.items[0].reasons == ()
    assert pack.items[0].matched_need_ids == ()
    assert pack.evidence_needs[0].matched_item_ids == ()
    assert pack.status == "partial"


def test_retained_rematch_never_synthesizes_cross_excerpt_adjacency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = models.EvidenceNeed(
        id="need:configs_docs:owner-controller",
        category="configs_docs",
        subject_terms=("Owner Controller",),
        required=True,
        provenance="explicit_query",
        matched_item_ids=(),
    )
    monkeypatch.setattr(
        builder,
        "derive_evidence_needs",
        lambda bundle, *, candidates: (required,),
    )
    raw_result = replace(
        _result(
            "config/application.properties",
            "Owner\nnoise\nController",
            spans=(
                RetrievalSpan(1, 1, 2.0, ("lexical",)),
                RetrievalSpan(3, 3, 1.0, ("semantic",)),
            ),
        ),
        reasons=[f"Owner Controller {'x' * 3000}"],
    )

    pack = builder.build_context_pack(
        _bundle("fixture", [raw_result]),
        _options(
            max_excerpts_per_item=2,
            max_excerpt_bytes=128,
            max_item_content_bytes=256,
            max_total_content_bytes=256,
            max_pack_bytes=4096,
        ),
    )

    assert pack.items[0].reasons == ()
    assert [(excerpt.start_line, excerpt.end_line) for excerpt in pack.items[0].excerpts] == [
        (1, 1),
        (3, 3),
    ]
    assert pack.items[0].matched_need_ids == ()
    assert pack.evidence_needs[0].matched_item_ids == ()
    assert pack.status == "partial"


def test_large_css_pack_is_bounded_deterministic_and_performs_no_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "\n".join(f".row-{index} {{ color: #123456; }}" for index in range(3132))
    result = _result(
        "src/main/resources/static/app.css",
        content,
        spans=(RetrievalSpan(1, 3132, 1.0, ("semantic",)),),
    )
    bundle = _bundle("find stylesheet", [result])

    def fail_io(*args: object, **kwargs: object) -> None:
        pytest.fail("context construction must not reread candidate files")

    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)
    first = builder.build_context_pack(bundle, _options())
    second = builder.build_context_pack(bundle, _options())
    first_bytes = serialization.canonical_context_pack_bytes(first)
    second_bytes = serialization.canonical_context_pack_bytes(second)

    assert len(content.splitlines()) == 3132
    assert first == second
    assert first_bytes == second_bytes
    assert len(first_bytes) == first.budget.pack_bytes <= 65_536
    assert first.budget.content_bytes <= 49_152


def test_builder_pack_bytes_converges_at_decimal_digit_boundary() -> None:
    base = "x" * 9100
    pack = builder.build_context_pack(
        _bundle("find source", [_result("src/plain.py", base)]),
        _options(
            max_excerpt_bytes=9500,
            max_item_content_bytes=9500,
            max_total_content_bytes=9500,
            max_pack_bytes=12_000,
        ),
    )
    encoded = serialization.canonical_context_pack_bytes(pack)

    assert pack.budget.pack_bytes == len(encoded)
    assert 10_000 <= len(encoded) < 12_000
    assert len(str(pack.budget.pack_bytes)) == 5
