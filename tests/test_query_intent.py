from context_search_tool.query_intent import infer_query_intent


def test_query_intent_detects_config_save_logic_without_artifact_request() -> None:
    intent = infer_query_intent(
        "配置页面保存文本服务商和图片服务商 YAML active provider",
        ["配置", "页面", "保存", "文本", "服务商", "图片", "yaml", "active", "provider"],
    )

    assert intent.operations == frozenset({"save"})
    assert "config" in intent.target_roles
    assert "ui" in intent.target_roles
    assert not intent.wants_artifact
    assert intent.confidence >= 2


def test_query_intent_detects_deployment_artifact_request() -> None:
    intent = infer_query_intent(
        "docker compose deployment yaml mount history output",
        ["docker", "compose", "deployment", "yaml", "mount", "history", "output"],
    )

    assert "deploy" in intent.target_roles
    assert "config_artifact" in intent.artifact_roles
    assert intent.wants_artifact


def test_query_intent_detects_plural_test_artifact_request() -> None:
    intent = infer_query_intent(
        "tests for session cookies",
        ["tests", "for", "session", "cookies"],
    )

    assert "test" in intent.target_roles
    assert "test_artifact" in intent.artifact_roles
    assert intent.wants_artifact


def test_query_intent_detects_config_file_artifact_request() -> None:
    intent = infer_query_intent(
        "config file for provider settings",
        ["config", "file", "for", "provider", "settings"],
    )

    assert "config" in intent.target_roles
    assert "config_artifact" in intent.artifact_roles
    assert intent.wants_artifact


def test_query_intent_detects_generated_file_artifact_request() -> None:
    intent = infer_query_intent(
        "generated files for history index",
        ["generated", "files", "for", "history", "index"],
    )

    assert "generated_artifact" in intent.artifact_roles
    assert intent.wants_artifact


def test_query_intent_detects_documentation_artifact_request() -> None:
    intent = infer_query_intent(
        "documentation for cookies",
        ["documentation", "for", "cookies"],
    )

    assert "doc" in intent.target_roles
    assert "doc_artifact" in intent.artifact_roles
    assert intent.wants_artifact


def test_query_intent_detects_download_logic() -> None:
    intent = infer_query_intent(
        "历史记录打包下载 zip 接口",
        ["历史", "记录", "打包", "下载", "zip", "接口"],
    )

    assert "download" in intent.operations
    assert "entrypoint" in intent.target_roles
    assert not intent.wants_artifact


def test_query_intent_keeps_plain_business_query_low_confidence() -> None:
    intent = infer_query_intent(
        "auth portfolio provider history",
        ["auth", "portfolio", "provider", "history"],
    )

    assert intent.operations == frozenset()
    assert intent.target_roles == frozenset()
    assert not intent.wants_artifact
    assert intent.confidence == 0


def test_query_intent_uses_exact_english_terms_not_substrings() -> None:
    intent = infer_query_intent(
        "rapid assets editor gzip docker-compose",
        ["rapid", "assets", "editor", "gzip", "docker", "compose"],
    )

    assert "update" not in intent.operations
    assert "download" not in intent.operations
    assert "doc" not in intent.target_roles
    assert "deploy" in intent.target_roles
