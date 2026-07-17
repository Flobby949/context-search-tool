from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from context_search_tool.graph_contract import generate_core_module_signal_id
from context_search_tool.models import CodeRelation, CodeSignal, SourceFile
from context_search_tool.test_association import (
    TestAssociationSnapshot,
    build_test_associations,
    regenerate_test_associations,
)
from context_search_tool.test_paths import (
    is_forbidden_test_target_path,
    is_test_path,
    production_candidates_for_test,
)


@pytest.mark.parametrize(
    ("path", "language", "unit", "expected"),
    [
        (
            "java/src/test/java/demo/PaymentServiceTests.java",
            "java",
            "java",
            {"java/src/main/java/demo/PaymentService.java"},
        ),
        ("go/payment_test.go", "go", "go", {"go/payment.go"}),
        (
            "rust/src/payment_tests.rs",
            "rust",
            "rust",
            {"rust/src/payment.rs"},
        ),
        (
            "rust/tests/api/payment.rs",
            "rust",
            "rust",
            {"rust/src/api/payment.rs"},
        ),
        (
            "python/tests/test_payment.py",
            "python",
            "python",
            {"python/payment.py", "python/src/payment.py"},
        ),
        (
            "python/tests/test_payment_test.py",
            "python",
            "python",
            {
                "python/payment_test.py",
                "python/src/payment_test.py",
                "python/test_payment.py",
                "python/src/test_payment.py",
            },
        ),
        (
            "typescript/src/__tests__/payment.spec.ts",
            "typescript",
            "typescript",
            {
                f"typescript/src/payment{suffix}"
                for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue")
            },
        ),
        (
            "javascript/tests/payment.test.js",
            "javascript",
            "javascript",
            {
                f"javascript/payment{suffix}"
                for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue")
            }
            | {
                f"javascript/src/payment{suffix}"
                for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue")
            },
        ),
        (
            "src/payment.test.tsx",
            "typescript",
            "",
            {
                f"src/payment{suffix}"
                for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue")
            },
        ),
    ],
)
def test_complete_six_family_candidate_rewrite_matrix(
    path: str,
    language: str,
    unit: str,
    expected: set[str],
) -> None:
    assert is_test_path(path, language, unit)
    assert {
        item.as_posix()
        for item in production_candidates_for_test(path, language, unit)
    } == expected


@pytest.mark.parametrize(
    ("path", "language", "unit"),
    [
        ("", "python", ""),
        ("tests/./test_payment.py", "python", ""),
        ("tests/../test_payment.py", "python", ""),
        ("src/__tests__/nested/__tests__/payment.test.ts", "typescript", ""),
        ("src/tests/payment.test.ts", "typescript", ""),
        ("src/tests/test_payment.py", "python", ""),
        ("src/Test.java", "java", ""),
        ("src/payment_test.go", "python", ""),
    ],
)
def test_invalid_or_nonclosed_paths_produce_no_candidates(
    path: str,
    language: str,
    unit: str,
) -> None:
    assert production_candidates_for_test(path, language, unit) == ()


def test_test_classifier_is_anchored_and_case_sensitive() -> None:
    assert is_test_path("src/FooTest.java", "java")
    assert is_test_path("src/FooTests.java", "java")
    assert is_test_path("src/FooIT.java", "java")
    assert is_test_path("src/FooITCase.java", "java")
    assert not is_test_path("src/Contest.java", "java")
    assert not is_test_path("src/FooTEST.java", "java")
    assert is_test_path("src/test_foo.py", "Python")


@pytest.mark.parametrize(
    "path",
    [
        "src/generated/payment.py",
        "fixtures/payment.go",
        "src/__snapshots__/payment.ts",
        "golden/payment.rs",
        "test-data/payment.java",
        "src/testdata/payment.js",
    ],
)
def test_forbidden_target_directories_are_closed(path: str) -> None:
    assert is_forbidden_test_target_path(path)


def _source(
    path: str,
    language: str,
    *,
    is_test: bool = False,
    is_generated: bool = False,
) -> SourceFile:
    return SourceFile(
        path=Path(path),
        language=language,
        sha256="hash",
        size=1,
        mtime_ns=1,
        is_test=is_test,
        is_generated=is_generated,
    )


def _module(path: str, language: str, unit: str = "") -> CodeSignal:
    signal_id = generate_core_module_signal_id(
        file_path=path,
        start_line=1,
        start_column=0,
        end_line=1,
        end_column=0,
    )
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=f"chunk:{path}",
        file_path=Path(path),
        kind="module",
        name=path,
        start_line=1,
        end_line=1,
        language=language,
        qualified_name=path,
        project_unit_key=unit,
        producer="core_module",
        recallable=False,
    )


def _type(path: str, qualified_name: str, unit: str = "") -> CodeSignal:
    return CodeSignal(
        signal_id=f"type:{qualified_name}",
        chunk_id=f"chunk:{path}",
        file_path=Path(path),
        kind="type",
        name=qualified_name.rsplit(".", 1)[-1],
        start_line=1,
        end_line=1,
        language="java",
        qualified_name=qualified_name,
        project_unit_key=unit,
        producer="java_ast",
    )


def _resolved_import(source: CodeSignal, target: CodeSignal) -> CodeRelation:
    return CodeRelation(
        relation_id=f"import:{source.signal_id}:{target.signal_id}",
        source_signal_id=source.signal_id,
        target_name=target.qualified_name,
        kind="imports_type" if target.kind == "type" else "imports",
        confidence=1.0,
        metadata={
            "first_source_line": 3,
            "first_source_column": 7,
            "occurrence_count": 1,
        },
        target_kind=target.kind,
        target_qualified_name=target.qualified_name,
        target_project_unit_key=source.project_unit_key,
        target_signal_id=target.signal_id,
        resolution="resolved_exact",
        producer="java_ast" if target.kind == "type" else "frontend_graph",
        producer_confidence=1.0,
        resolution_confidence=1.0,
    )


def test_persisted_import_survives_production_only_rebuild_and_dedupes_path() -> None:
    test_path = "src/test/java/demo/PaymentServiceTests.java"
    production_path = "src/main/java/demo/PaymentService.java"
    test_module = _module(test_path, "java")
    production_module = _module(production_path, "java")
    production_type = _type(production_path, "demo.PaymentService")
    persisted = _resolved_import(test_module, production_type)
    sources = (
        _source(test_path, "java"),
        _source(production_path, "java"),
    )

    first = build_test_associations(
        source_files=sources,
        signals=(test_module, production_module, production_type),
        resolved_relations=(persisted,),
    )
    after_production_change = build_test_associations(
        source_files=(sources[0], _source(production_path, "java")),
        signals=(test_module, production_module, production_type),
        resolved_relations=(persisted,),
    )

    assert first == after_production_change
    [relation] = first
    assert relation.kind == "tests"
    assert relation.target_qualified_name == production_path
    assert relation.metadata["resolution_basis"] == "exact_test_import"
    assert relation.metadata["provenance_relation_id"] == persisted.relation_id
    assert relation.metadata["first_source_line"] == 3
    assert relation.metadata["first_source_column"] == 7


def test_convention_requires_one_active_legal_same_unit_production_target() -> None:
    test_path = "pkg/tests/payment.test.ts"
    test_module = _module(test_path, "typescript", "pkg")
    ts_module = _module("pkg/src/payment.ts", "typescript", "pkg")
    js_module = _module("pkg/src/payment.js", "javascript", "pkg")
    sources = (
        _source(test_path, "typescript"),
        _source("pkg/src/payment.ts", "typescript"),
        _source("pkg/src/payment.js", "javascript"),
    )

    ambiguous = build_test_associations(
        source_files=sources,
        signals=(test_module, ts_module, js_module),
        resolved_relations=(),
    )
    unique = build_test_associations(
        source_files=sources[:2],
        signals=(test_module, ts_module),
        resolved_relations=(),
    )

    assert ambiguous == ()
    [relation] = unique
    assert relation.target_qualified_name == "pkg/src/payment.ts"
    assert relation.metadata["resolution_basis"] == "exact_test_path"


def test_generated_cross_unit_inactive_and_test_targets_are_rejected() -> None:
    test_module = _module("unit/payment_test.go", "go", "unit")
    legal_path = "unit/payment.go"
    legal_module = _module(legal_path, "go", "unit")
    cross_module = _module("other/payment.go", "go", "other")
    target_test = _module("unit/other_test.go", "go", "unit")
    explicit = (
        _resolved_import(test_module, cross_module),
        _resolved_import(test_module, target_test),
    )

    assert build_test_associations(
        source_files=(
            _source("unit/payment_test.go", "go"),
            _source(legal_path, "go", is_generated=True),
            _source("other/payment.go", "go"),
            _source("unit/other_test.go", "go"),
        ),
        signals=(test_module, legal_module, cross_module, target_test),
        resolved_relations=explicit,
    ) == ()


def test_canonical_classifier_does_not_trust_a_broad_persisted_test_flag() -> None:
    contest_path = "src/main/java/demo/Contest.java"
    production_path = "src/main/java/demo/PaymentService.java"

    assert build_test_associations(
        source_files=(
            _source(contest_path, "java", is_test=True),
            _source(production_path, "java"),
        ),
        signals=(
            _module(contest_path, "java"),
            _module(production_path, "java"),
        ),
        resolved_relations=(),
    ) == ()


def test_explicit_import_associations_are_capped_after_target_deduplication() -> None:
    test_path = "src/payment.test.ts"
    test_module = _module(test_path, "typescript")
    targets = tuple(
        _module(f"src/target{index}.ts", "typescript") for index in range(9)
    )
    sources = (_source(test_path, "typescript"),) + tuple(
        _source(target.file_path.as_posix(), "typescript") for target in targets
    )
    imports = tuple(_resolved_import(test_module, target) for target in targets)

    relations = build_test_associations(
        source_files=sources,
        signals=(test_module,) + targets,
        resolved_relations=imports + (imports[0],),
    )

    assert len(relations) == 8
    assert len({relation.target_qualified_name for relation in relations}) == 8
    assert all(relation.producer == "test_association" for relation in relations)


def test_regeneration_replaces_all_rows_in_one_session() -> None:
    test_path = "src/test/java/demo/PaymentServiceTests.java"
    production_path = "src/main/java/demo/PaymentService.java"
    snapshot = TestAssociationSnapshot(
        source_files=(
            _source(test_path, "java"),
            _source(production_path, "java"),
        ),
        signals=(
            _module(test_path, "java"),
            _module(production_path, "java"),
        ),
        resolved_relations=(),
    )

    class Session:
        def __init__(self) -> None:
            self.replaced = None

        def snapshot(self):
            return snapshot

        def replace_test_associations(self, relations, *, producer_resolution_generation):
            self.replaced = (relations, producer_resolution_generation)

    class Store:
        def __init__(self) -> None:
            self.session = Session()
            self.closed = False

        @contextmanager
        def test_association_session(self):
            try:
                yield self.session
            finally:
                self.closed = True

    store = Store()
    relations = regenerate_test_associations(
        store,
        producer_resolution_generation=7,
    )

    assert store.closed is True
    assert store.session.replaced == (relations, 7)
    assert len(relations) == 1
