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
        ("pages/index.tsx", "view_page"),
        ("src/App.tsx", "layout_component"),
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
    strong_intent = infer_frontend_intent("layout theme sidebar tool route navigation reader scanner camera image")
    saturated_intent = infer_frontend_intent(
        "tool page view component layout route navigation reader scanner camera image upload download sidebar theme "
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


def test_frontend_intent_scoring_tokens_exclude_fixture_domains() -> None:
    forbidden_tokens = {"qrcode", "mqtt", "watermark", "chat"}

    assert forbidden_tokens.isdisjoint(frontend_roles._FEATURE_ENTRYPOINT_TOKENS)
    assert forbidden_tokens.isdisjoint(frontend_roles._UTILITY_IMPLEMENTATION_TOKENS)
    assert forbidden_tokens.isdisjoint(frontend_roles._STATE_TOKENS)


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


def test_frontend_candidate_scope_enabled_rejects_python_like_view_service_pool() -> None:
    assert not frontend_roles.frontend_candidate_scope_enabled(
        [
            "src/views/users.py",
            "src/services/users.py",
        ]
    )


@pytest.mark.parametrize(
    "paths",
    [
        ["pages/index.tsx", "src/utils/image.ts"],
        ["src/App.tsx", "src/services/api.ts"],
    ],
)
def test_frontend_candidate_scope_enabled_accepts_common_frontend_layouts(
    paths: list[str],
) -> None:
    assert frontend_roles.frontend_candidate_scope_enabled(paths)


def test_frontend_score_parts_disabled_returns_empty() -> None:
    assert (
        frontend_roles.frontend_score_parts(
            "src/views/image/ImageTool.vue",
            "image canvas remove scan reader upload preview",
            enabled=False,
        )
        == {}
    )


def test_frontend_score_parts_boost_entrypoint_and_support_roles() -> None:
    feature_parts = frontend_roles.frontend_score_parts(
        "src/views/image/ImageTool.vue",
        "image canvas remove scan reader upload preview",
        enabled=True,
    )
    utility_parts = frontend_roles.frontend_score_parts(
        "src/utils/entityFactory.ts",
        "entity generate TypeScript class interface parse convert",
        enabled=True,
    )

    assert feature_parts["frontend_entrypoint_boost"] == pytest.approx(0.35)
    assert "frontend_support_boost" not in feature_parts
    assert utility_parts["frontend_support_boost"] == pytest.approx(0.18)
    assert "frontend_entrypoint_boost" not in utility_parts


def test_frontend_score_parts_use_targeted_noise_penalties() -> None:
    lockfile_parts = frontend_roles.frontend_score_parts(
        "package-lock.json",
        "image canvas remove scan reader upload preview",
        enabled=True,
    )
    scratch_parts = frontend_roles.frontend_score_parts(
        "temp/imageProbe.ts",
        "image canvas remove scan reader upload preview",
        enabled=True,
    )
    type_parts = frontend_roles.frontend_score_parts(
        "src/types/entity.d.ts",
        "image canvas remove scan reader upload preview",
        enabled=True,
    )

    assert lockfile_parts["frontend_lockfile_penalty"] == pytest.approx(-0.80)
    assert lockfile_parts["penalty"] == pytest.approx(-0.80)
    assert scratch_parts["frontend_scratch_temp_penalty"] == pytest.approx(-0.60)
    assert scratch_parts["penalty"] == pytest.approx(-0.60)
    assert type_parts["frontend_type_decl_penalty"] == pytest.approx(-0.12)
    assert type_parts["penalty"] == pytest.approx(-0.12)


def test_frontend_score_parts_do_not_penalize_explicit_type_or_lock_queries() -> None:
    type_parts = frontend_roles.frontend_score_parts(
        "src/types/entity.d.ts",
        "entity type declaration d.ts",
        enabled=True,
    )
    lockfile_parts = frontend_roles.frontend_score_parts(
        "package-lock.json",
        "package dependency lock versions",
        enabled=True,
    )

    assert type_parts["frontend_support_boost"] > 0
    assert "frontend_type_decl_penalty" not in type_parts
    assert "frontend_lockfile_penalty" not in lockfile_parts


def test_frontend_score_parts_treat_matching_type_decl_path_as_explicit_type_evidence() -> None:
    parts = frontend_roles.frontend_score_parts(
        "src/types/image-reader.d.ts",
        "image reader scan camera",
        enabled=True,
    )

    assert "frontend_type_decl_penalty" not in parts
    assert "penalty" not in parts


def test_frontend_score_parts_do_not_penalize_explicit_scratch_queries() -> None:
    parts = frontend_roles.frontend_score_parts(
        "temp/entityMock.ts",
        "temp scratch entity mock",
        enabled=True,
    )

    assert "frontend_scratch_temp_penalty" not in parts
    assert "penalty" not in parts


def test_frontend_score_parts_penalize_generic_index_type_path_for_feature_query() -> None:
    parts = frontend_roles.frontend_score_parts(
        "src/types/index.ts",
        "index page route",
        enabled=True,
    )

    assert parts["frontend_type_decl_penalty"] == pytest.approx(-0.12)
    assert parts["penalty"] == pytest.approx(-0.12)


def test_extract_static_imports_returns_static_frontend_specifiers() -> None:
    content = """
import { detect } from "@/services/imageDetection"
import { resize } from "@/utils/imageUtils";
import type { ImageReader } from "@/types/image-reader"
import "@/styles/main"

const loader = () => import("@/services/lazyImageDetection")
""".strip()

    assert frontend_roles.extract_static_imports(content) == (
        "@/services/imageDetection",
        "@/utils/imageUtils",
        "@/types/image-reader",
        "@/styles/main",
    )


def test_extract_static_imports_ignores_commented_and_dynamic_imports() -> None:
    content = """
// import { disabledLine } from "@/services/disabledLine"
/*
import { disabledBlock } from "@/services/disabledBlock"
import "@/styles/disabledBlock"
*/
<!--
import { disabledTemplate } from "@/services/disabledTemplate"
-->
import { enabled } from "@/services/enabled"
import { enabledAgain } from "@/services/enabled"

const loader = () => import("@/services/lazyEnabled")
""".strip()

    assert frontend_roles.extract_static_imports(content) == ("@/services/enabled",)


def test_resolve_frontend_import_handles_alias_type_and_relative_imports(
    tmp_path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "services").mkdir(parents=True)
    (repo / "src" / "types").mkdir(parents=True)
    (repo / "src" / "views" / "image").mkdir(parents=True)
    (repo / "src" / "services" / "imageDetection.ts").write_text(
        "export function detect() {}",
        encoding="utf-8",
    )
    (repo / "src" / "types" / "image-reader.d.ts").write_text(
        "export interface ImageReader {}",
        encoding="utf-8",
    )
    (repo / "src" / "views" / "image" / "localMask.ts").write_text(
        "export const localMask = true",
        encoding="utf-8",
    )

    importer = "src/views/image/ImageTool.vue"

    assert (
        frontend_roles.resolve_frontend_import(
            repo,
            importer,
            "@/services/imageDetection",
        )
        == "src/services/imageDetection.ts"
    )
    assert (
        frontend_roles.resolve_frontend_import(
            repo,
            importer,
            "@/types/image-reader",
        )
        == "src/types/image-reader.d.ts"
    )
    assert (
        frontend_roles.resolve_frontend_import(repo, importer, "./localMask")
        == "src/views/image/localMask.ts"
    )
    assert (
        frontend_roles.resolve_frontend_import(
            repo,
            repo / importer,
            "./localMask",
        )
        == "src/views/image/localMask.ts"
    )


@pytest.mark.parametrize("specifier", ["vue", "pinia", "axios"])
def test_resolve_frontend_import_rejects_package_imports(
    tmp_path,
    specifier: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert frontend_roles.resolve_frontend_import(
        repo,
        "src/views/image/ImageTool.vue",
        specifier,
    ) is None


def test_resolve_frontend_import_rejects_relative_repo_escape_before_file_probe(
    tmp_path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "views").mkdir(parents=True)
    (tmp_path / "outside.ts").write_text(
        "export const outside = true",
        encoding="utf-8",
    )
    original_is_file = type(repo).is_file

    def reject_escaped_probe(path):
        try:
            path.resolve().relative_to(repo.resolve())
        except ValueError as exc:
            raise AssertionError("escaped import candidate was probed") from exc
        return original_is_file(path)

    monkeypatch.setattr(type(repo), "is_file", reject_escaped_probe)

    assert (
        frontend_roles.resolve_frontend_import(
            repo,
            "src/views/Page.vue",
            "../../../outside",
        )
        is None
    )


def test_resolve_frontend_import_rejects_symlink_escape_before_file_probe(
    tmp_path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "views").mkdir(parents=True)
    outside = tmp_path / "outside.ts"
    outside.write_text("export const outside = true", encoding="utf-8")
    link = repo / "src" / "views" / "linked.ts"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    original_is_file = type(repo).is_file

    def reject_escaped_probe(path):
        try:
            path.resolve().relative_to(repo.resolve())
        except ValueError as exc:
            raise AssertionError("escaped import candidate was probed") from exc
        return original_is_file(path)

    monkeypatch.setattr(type(repo), "is_file", reject_escaped_probe)

    assert (
        frontend_roles.resolve_frontend_import(
            repo,
            "src/views/Page.vue",
            "./linked",
        )
        is None
    )


def test_resolve_frontend_import_rejects_absolute_importer_outside_repo(
    tmp_path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "helper.ts").write_text("export const helper = true", encoding="utf-8")
    outside_importer = tmp_path / "outside" / "Page.vue"

    assert (
        frontend_roles.resolve_frontend_import(
            repo,
            outside_importer,
            "./helper",
        )
        is None
    )
