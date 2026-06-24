from dataclasses import FrozenInstanceError

import pytest

from context_search_tool import frontend_roles
from context_search_tool.frontend_roles import (
    FrontendIntent,
    FrontendRole,
    classify_frontend_role,
    frontend_repo_enabled,
    infer_frontend_intent,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/router/index.ts", "route_config"),
        ("src/views/qrcode/QRCodeTool.vue", "view_page"),
        ("src/pages/qrcode/QRCodeTool.vue", "view_page"),
        ("src/components/AppLayout.vue", "layout_component"),
        ("src/components/ImageUploader.vue", "shared_component"),
        ("src/stores/app.ts", "store"),
        ("src/services/watermarkDetection.ts", "service"),
        ("src/api/toolApi.ts", "service"),
        ("src/utils/qrcodeUtils.ts", "utility"),
        ("src/types/qrcode-reader.d.ts", "type_decl"),
        ("temp/entityToMock.js", "scratch_temp"),
        ("package-lock.json", "lockfile"),
    ],
)
def test_classify_frontend_role(path: str, expected: str) -> None:
    assert classify_frontend_role(path).name == expected


@pytest.mark.parametrize(
    "path",
    [
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "bun.lockb",
    ],
)
def test_classify_frontend_role_covers_lockfiles(path: str) -> None:
    assert classify_frontend_role(path).name == "lockfile"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tmp/buildProbe.js", "scratch_temp"),
        (".cache/vite/deps/chunk.js", "scratch_temp"),
        ("src/routes/index.ts", "route_config"),
        ("src/components/layout/Sidebar.vue", "layout_component"),
        ("src/layouts/MainLayout.vue", "layout_component"),
        ("src/store/app.ts", "store"),
        ("src/lib/format.ts", "utility"),
        ("src/helpers/format.ts", "utility"),
        ("src/views/chat/message.d.ts", "type_decl"),
        ("src/main.ts", "other"),
    ],
)
def test_classify_frontend_role_covers_plan_mapping(path: str, expected: str) -> None:
    assert classify_frontend_role(path).name == expected


def test_classify_frontend_role_normalizes_windows_and_uppercase_paths() -> None:
    assert classify_frontend_role(r"SRC\VIEWS\QRCODE\QRCodeTool.vue").name == "view_page"


def test_infer_frontend_intent_for_qrcode_feature_query() -> None:
    intent = infer_frontend_intent("QRCode generate scan camera decode paste image qrcode-reader")

    assert intent.feature_entrypoint >= 0.65
    assert intent.utility_implementation >= 0.35
    assert intent.feature_entrypoint > intent.state


def test_infer_frontend_intent_for_json_to_entity_query() -> None:
    intent = infer_frontend_intent("JSON to entity generate Java TypeScript CSharp Python class interface")

    assert intent.utility_implementation >= 0.75
    assert intent.utility_implementation > intent.feature_entrypoint
    assert intent.state <= intent.feature_entrypoint


def test_infer_frontend_intent_for_layout_theme_query() -> None:
    intent = infer_frontend_intent("AppLayout theme sidebar tool categories dark light Pinia")

    assert intent.feature_entrypoint >= 0.55
    assert intent.state >= 0.35


def test_infer_frontend_intent_splits_pascal_case_terms() -> None:
    intent = infer_frontend_intent("AppLayout")

    assert intent.feature_entrypoint > 0


def test_infer_frontend_intent_splits_path_and_camel_case_terms() -> None:
    intent = infer_frontend_intent("src/utils/jsonToEntity.ts")

    assert intent.utility_implementation > intent.feature_entrypoint


def test_infer_frontend_intent_is_additive_and_clamped() -> None:
    weak_intent = infer_frontend_intent("layout")
    strong_intent = infer_frontend_intent("layout theme sidebar tool qrcode mqtt watermark chat")
    saturated_intent = infer_frontend_intent(
        "tool page view component layout chat qrcode mqtt watermark sidebar theme "
        "generate decode encode parse format convert entity class interface typescript java csharp python "
        "pinia store state theme sidebar dark light history"
    )

    assert strong_intent.feature_entrypoint > weak_intent.feature_entrypoint
    for score in (
        saturated_intent.feature_entrypoint,
        saturated_intent.utility_implementation,
        saturated_intent.state,
    ):
        assert 0.0 <= score <= 1.0


def test_frontend_role_is_immutable() -> None:
    role = FrontendRole(name="view_page")

    with pytest.raises(FrozenInstanceError):
        role.name = "other"  # type: ignore[misc]


def test_frontend_intent_is_immutable() -> None:
    intent = FrontendIntent(feature_entrypoint=0.0, utility_implementation=0.0, state=0.0)

    with pytest.raises(FrozenInstanceError):
        intent.state = 1.0  # type: ignore[misc]


def test_frontend_repo_enabled_for_frontend_paths() -> None:
    assert frontend_repo_enabled(
        [
            "package.json",
            "src/views/qrcode/QRCodeTool.vue",
            "src/components/AppLayout.vue",
        ]
    )


def test_frontend_repo_enabled_rejects_java_only_paths() -> None:
    assert not frontend_repo_enabled(
        [
            "pom.xml",
            "src/main/java/com/example/App.java",
            "src/test/java/com/example/AppTest.java",
        ]
    )


def test_frontend_repo_enabled_requires_repo_inventory_evidence() -> None:
    assert not frontend_repo_enabled(
        [
            "src/views/qrcode/QRCodeTool.vue",
            "src/utils/qrcodeUtils.ts",
        ]
    )


def test_frontend_candidate_scope_enabled_for_view_and_utility_pool() -> None:
    assert frontend_roles.frontend_candidate_scope_enabled(
        [
            "src/views/qrcode/QRCodeTool.vue",
            "src/utils/qrcodeUtils.ts",
        ]
    )


def test_frontend_candidate_scope_enabled_for_view_and_component_pool() -> None:
    assert frontend_roles.frontend_candidate_scope_enabled(
        [
            "src/views/qrcode/QRCodeTool.vue",
            "src/components/ImageUploader.vue",
        ]
    )


def test_frontend_candidate_scope_enabled_rejects_java_only_pool() -> None:
    assert not frontend_roles.frontend_candidate_scope_enabled(
        [
            "src/main/java/com/example/App.java",
            "src/test/java/com/example/AppTest.java",
        ]
    )
