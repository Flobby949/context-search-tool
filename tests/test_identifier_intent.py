from context_search_tool.identifier_intent import infer_identifier_intent


def test_identifier_intent_extracts_symbols_and_filenames() -> None:
    intent = infer_identifier_intent(
        "frontend useAuthStore auth.store.ts fetchCurrentUser Pinia",
        ["frontend", "use", "auth", "store", "auth", "store", "ts", "fetch", "current", "user", "pinia"],
    )

    assert intent.identifiers == ("fetchCurrentUser", "useAuthStore")
    assert intent.file_hints == ("auth.store.ts",)
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


def test_identifier_intent_ignores_plain_business_words() -> None:
    intent = infer_identifier_intent(
        "auth portfolio fund service",
        ["auth", "portfolio", "fund", "service"],
    )

    assert intent.identifiers == ()
    assert intent.file_hints == ()
    assert intent.role_hints == ("service",)
