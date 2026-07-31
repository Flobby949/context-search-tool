import pytest

from context_search_tool.identifier_intent import (
    IdentifierIntent,
    infer_identifier_intent,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("useAuthStore", "useAuthStore"),
        (" AuditStatus ", "AuditStatus"),
        ("HTTPServer", "HTTPServer"),
        ("apply_dev", "apply_dev"),
    ),
)
def test_identifier_intent_marks_existing_whole_query_identifiers_exact(
    query: str,
    expected: str,
) -> None:
    intent = infer_identifier_intent(query, [])

    assert intent.exact_identifier == expected
    assert intent.identifiers == (expected,)


@pytest.mark.parametrize(
    "query",
    (
        "find AuditStatus",
        "apply_dev now",
    ),
)
def test_identifier_intent_requires_one_whole_query_identifier(
    query: str,
) -> None:
    intent = infer_identifier_intent(query, [])

    assert intent.exact_identifier is None


@pytest.mark.parametrize(
    "query",
    (
        "INVOLVED_BY_ME",
        "HTTP_2_MODE",
        "  INVOLVED_BY_ME  ",
    ),
)
def test_identifier_intent_marks_whole_screaming_snake_exact(
    query: str,
) -> None:
    intent = infer_identifier_intent(query, [])

    assert intent.exact_identifier == query.strip()
    assert intent.identifiers == ()


@pytest.mark.parametrize(
    "query",
    (
        "REST",
        "_INVOLVED_BY_ME",
        "INVOLVED_BY_ME_",
        "INVOLVED__BY_ME",
        "INVOLVED_BY_Me",
        "find INVOLVED_BY_ME",
        "`INVOLVED_BY_ME`",
        '"INVOLVED_BY_ME"',
        "(INVOLVED_BY_ME)",
        "INVOLVED_BY_ME!",
    ),
)
def test_identifier_intent_rejects_non_exact_screaming_snake_forms(
    query: str,
) -> None:
    intent = infer_identifier_intent(query, [])

    assert intent.exact_identifier is None
    assert intent.identifiers == ()


def test_identifier_intent_preserves_owner_member_file_and_suffix_hints() -> None:
    intent = infer_identifier_intent("Owner.MEMBER", [])

    assert intent.exact_identifier is None
    assert intent.identifiers == ()
    assert intent.file_hints == ("owner.member",)
    assert intent.suffix_hints == (".member",)
    assert intent.role_hints == ()


def test_identifier_intent_rejects_exactness_for_two_identifiers() -> None:
    intent = infer_identifier_intent("AuditStatus apply_dev", [])

    assert intent.exact_identifier is None
    assert intent.identifiers == ("AuditStatus", "apply_dev")
    assert intent.file_hints == ()
    assert intent.suffix_hints == ()
    assert intent.role_hints == ()


def test_identifier_intent_keeps_mixed_route_identifier_compatibility() -> None:
    intent = infer_identifier_intent(
        "/apply/audit/pageEs INVOLVED_BY_ME",
        ["apply", "audit", "page", "es", "involved", "by", "me"],
    )

    assert intent.exact_identifier is None
    assert intent.identifiers == ("pageEs",)


def test_identifier_intent_keeps_identifiers_unique_and_sorted() -> None:
    intent = infer_identifier_intent(
        "useAuthStore apply_dev AuditStatus useAuthStore apply_dev",
        [],
    )

    assert intent.exact_identifier is None
    assert intent.identifiers == ("AuditStatus", "apply_dev", "useAuthStore")


def test_identifier_intent_keeps_legacy_positional_constructor_order() -> None:
    intent = IdentifierIntent(
        ("AuditStatus",),
        ("audit.py",),
        (".py",),
        ("service",),
    )

    assert intent.identifiers == ("AuditStatus",)
    assert intent.file_hints == ("audit.py",)
    assert intent.suffix_hints == (".py",)
    assert intent.role_hints == ("service",)
    assert intent.exact_identifier is None


def test_identifier_intent_extracts_symbols_and_filenames() -> None:
    intent = infer_identifier_intent(
        "frontend useAuthStore auth.store.ts fetchCurrentUser Pinia",
        ["frontend", "use", "auth", "store", "auth", "store", "ts", "fetch", "current", "user", "pinia"],
    )

    assert intent.identifiers == ("fetchCurrentUser", "useAuthStore")
    assert intent.exact_identifier is None
    assert intent.file_hints == ("auth.store.ts",)
    assert intent.suffix_hints == (".ts",)
    assert intent.role_hints == ("state_store",)


def test_identifier_intent_extracts_snake_case_and_rust_commands() -> None:
    intent = infer_identifier_intent(
        "tauri command apply_dev restore_clean command handler",
        ["tauri", "command", "apply", "dev", "restore", "clean", "command", "handler"],
    )

    assert intent.identifiers == ("apply_dev", "restore_clean")
    assert intent.file_hints == ()
    assert intent.role_hints == ("command", "handler")


def test_identifier_intent_extracts_go_service_and_handler_roles() -> None:
    intent = infer_identifier_intent(
        "collector FundService CollectNav BatchCollectNav fund service",
        ["collector", "fund", "service", "collect", "nav", "batch", "collect", "nav", "fund", "service"],
    )

    assert intent.identifiers == ("BatchCollectNav", "CollectNav", "FundService")
    assert intent.role_hints == ("service",)


def test_identifier_intent_extracts_acronym_prefixed_pascal_case() -> None:
    intent = infer_identifier_intent(
        "java AIController HTTPServer URLParser SSEClient REST chatWithSse",
        ["java", "ai", "controller", "http", "server", "url", "parser", "sse", "client", "rest", "chat", "with", "sse"],
    )

    assert intent.identifiers == (
        "AIController",
        "HTTPServer",
        "SSEClient",
        "URLParser",
        "chatWithSse",
    )
    assert "REST" not in intent.identifiers


def test_identifier_intent_ignores_plain_business_words() -> None:
    intent = infer_identifier_intent(
        "auth portfolio fund service",
        ["auth", "portfolio", "fund", "service"],
    )

    assert intent.identifiers == ()
    assert intent.file_hints == ()
    assert intent.role_hints == ("service",)


def test_identifier_intent_extracts_storage_role() -> None:
    intent = infer_identifier_intent(
        "UploadHandler MultiUpload multipart file storage Save",
        ["upload", "handler", "multi", "upload", "multipart", "file", "storage", "save"],
    )

    assert intent.identifiers == ("MultiUpload", "UploadHandler")
    assert intent.role_hints == ("handler", "storage")
