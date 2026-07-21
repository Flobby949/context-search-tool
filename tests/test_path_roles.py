from dataclasses import fields
from pathlib import Path

import pytest

from context_search_tool import path_roles as path_roles_module
from context_search_tool.path_roles import PathRole, classify_path_role


def assert_path_role(
    path: str,
    name: str,
    priority: int,
    basis: str = "path",
    *,
    content: str = "",
) -> None:
    assert classify_path_role(Path(path), content) == PathRole(name, priority, basis)


def test_path_role_has_exact_required_fields_and_no_basis_default() -> None:
    assert tuple(field.name for field in fields(PathRole)) == (
        "name",
        "priority",
        "basis",
    )
    with pytest.raises(TypeError):
        PathRole("source", 60)  # type: ignore[call-arg]


def test_path_roles_classify_frontend_state_and_composable_files() -> None:
    assert_path_role("src/stores/modules/auth.store.ts", "state_store", 20)
    assert_path_role("src/views/chat/composables/useSseConnection.ts", "composable", 20)
    assert_path_role("src/views/chat/types.ts", "data_type", 45)
    assert_path_role("src/views/auth/register.vue", "view", 50)


def test_path_roles_do_not_treat_user_or_usage_as_composable() -> None:
    assert_path_role("src/main/java/com/example/service/UserService.java", "service", 30)
    assert_path_role(
        "src/main/java/com/example/controller/UserController.java",
        "entrypoint",
        10,
    )
    assert_path_role("src/utils/usage.ts", "source", 60, "fallback")
    assert_path_role("src/views/chat/composables/useSseConnection.ts", "composable", 20)


def test_path_roles_classify_backend_and_collector_files() -> None:
    assert_path_role("handler/upload.go", "handler", 25)
    assert_path_role("middleware/auth.go", "middleware", 25)
    assert_path_role("collector/internal/service/fund_service.go", "service", 30)
    assert_path_role(
        "collector/internal/repository/nav_repo.go",
        "repository",
        40,
    )
    assert_path_role(
        "collector/internal/source/eastmoney/nav.go",
        "source_adapter",
        40,
    )
    assert_path_role("collector/internal/scheduler/scheduler.go", "scheduler", 25)


def test_path_roles_preserve_java_specific_semantics() -> None:
    assert_path_role(
        "src/main/java/com/example/service/impl/AuthServiceImpl.java",
        "service_impl",
        10,
    )
    assert_path_role(
        "src/main/java/com/example/service/AuthService.java",
        "service_interface",
        35,
        "content",
        content="public interface AuthService {}",
    )
    assert_path_role(
        "src/main/java/com/example/service/PageAppCatalogQueryExe.java",
        "executor",
        20,
    )
    assert_path_role("src/main/java/com/example/dto/AuthDto.java", "data_type", 45)


def test_path_roles_classify_rust_tauri_files() -> None:
    assert_path_role("src-tauri/src/commands.rs", "command", 15)
    assert_path_role("src-tauri/src/engine.rs", "engine", 20)
    assert_path_role("src-tauri/src/settings.rs", "config", 70)


def test_path_roles_classify_storage_files() -> None:
    assert_path_role("storage/local.go", "storage", 30)
    assert_path_role("storage/s3.go", "storage", 30)
    assert_path_role("internal/storages/oss.go", "storage", 30)


def test_path_roles_classify_all_indexed_lockfiles() -> None:
    for relative_path in (
        "Cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    ):
        assert_path_role(relative_path, "lockfile", 90)


def test_path_roles_classify_deployment_and_config_artifacts() -> None:
    assert_path_role("Dockerfile", "deployment_config", 75)
    assert_path_role("docker-compose.yml", "deployment_config", 75)
    assert_path_role("docker/image_providers.yaml", "deployment_config", 75)
    assert_path_role("docker/.env", "deployment_config", 75)
    assert_path_role("docker/entrypoint.sh", "source", 60, "fallback")
    assert_path_role("image_providers.yaml.example", "config_example", 75)
    assert_path_role("config/text_providers.yaml", "runtime_config", 65)
    assert_path_role("config/.env", "runtime_config", 65)
    assert_path_role("image_providers.yaml", "runtime_config", 65)
    assert_path_role("tsconfig.json", "config", 70)


def test_path_roles_classify_generated_output_and_docs() -> None:
    assert_path_role("history/index.json", "generated_output", 85)
    assert_path_role("output/task_1/result.json", "generated_output", 85)
    assert_path_role("README.md", "doc", 80)
    assert_path_role("docs/setup.md", "doc", 80)


def test_path_roles_do_not_classify_source_paths_as_generated_output() -> None:
    assert_path_role("src/views/history/index.vue", "view", 50)
    assert_path_role("src/pages/output/index.tsx", "view", 50)
    assert_path_role(
        "src/main/java/com/example/service/history/HistoryService.java",
        "service",
        30,
    )


def test_path_roles_classify_common_textual_artifacts_as_docs() -> None:
    for relative_path in (
        "README.rst",
        "docs/user/advanced.rst",
        "docs/usage.txt",
        "docs/api.adoc",
        "docs/api.asciidoc",
        "CHANGELOG",
        "CHANGELOG.txt",
        "HISTORY.md",
        "LICENSE",
        "NOTICE",
        "AUTHORS",
        "CONTRIBUTORS.txt",
    ):
        assert_path_role(relative_path, "doc", 80)


def test_path_roles_keep_production_source_as_source() -> None:
    assert_path_role("src/requests/sessions.py", "source", 60, "fallback")
    assert_path_role("src/requests/cookies.py", "source", 60, "fallback")
    assert_path_role("src/utils/usage.ts", "source", 60, "fallback")


def test_path_roles_do_not_classify_source_file_stems_as_docs() -> None:
    assert_path_role("src/history.py", "source", 60, "fallback")
    assert_path_role("internal/service/license.go", "service", 30)
    assert_path_role("src/notice.ts", "source", 60, "fallback")
    assert_path_role("src/contributors.rs", "source", 60, "fallback")
    assert_path_role("src/changelog.ts", "source", 60, "fallback")


@pytest.mark.parametrize(
    "path",
    [
        "src/main/resources/application.properties",
        "src/main/resources/application.yaml",
        "src/main/resources/application.yml",
        "src/main/resources/application-postgresql.yml",
        "src/main/resources/bootstrap.properties",
        "src/main/resources/bootstrap.yaml",
        "src/main/resources/bootstrap.yml",
        "src/main/resources/bootstrap-local.yaml",
        "config/messages_de.properties",
        "configs/messages_fr.properties",
        "src/main/resources/logback-spring.xml",
        "src/main/resources/log4j2.xml",
        "src/main/resources/persistence.xml",
        "src/main/resources/beans.xml",
    ],
)
def test_path_roles_classify_spring_runtime_config(path: str) -> None:
    assert_path_role(path, "runtime_config", 65)


@pytest.mark.parametrize(
    "path",
    [
        "src/main/resources/messages_de.properties",
        "src/main/resources/application-.yml",
        "src/main/resources/application.yml.bak",
        "src/main/resources/myapplication-prod.yml",
        "src/main/resources/logback.xml.bak",
        "src/main/resources/catalog.xml",
    ],
)
def test_path_roles_do_not_broadly_classify_properties_or_xml(path: str) -> None:
    assert_path_role(path, "source", 60, "fallback")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/test/resources/application.yml", ("test", 90, "path")),
        (
            "deploy/application.yml",
            ("deployment_config", 75, "path"),
        ),
        (
            "examples/application.yml",
            ("config_example", 75, "path"),
        ),
        (
            "generated/application.yml",
            ("generated_output", 85, "path"),
        ),
    ],
)
def test_spring_runtime_config_preserves_artifact_precedence(
    path: str,
    expected: tuple[str, int, str],
) -> None:
    assert classify_path_role(Path(path)) == PathRole(*expected)


def test_path_roles_classify_only_template_html_as_view() -> None:
    assert_path_role("src/main/resources/templates/owners/details.html", "view", 50)
    assert_path_role("src/main/resources/static/index.html", "source", 60, "fallback")


@pytest.mark.parametrize(
    "path",
    [
        "src/main/java/com/example/OwnerDto.java",
        "src/main/java/com/example/FooDTO.java",
        "src/main/java/com/example/FooVo.java",
        "src/main/java/com/example/FooVO.java",
        "src/main/java/com/example/CreateOwnerRequest.java",
        "src/main/java/com/example/OwnerResponse.java",
        "src/main/java/com/example/OwnerEntity.java",
        "src/main/java/com/example/OwnerModel.java",
    ],
)
def test_path_roles_classify_java_type_stems(path: str) -> None:
    assert_path_role(path, "data_type", 45)


def test_path_roles_classify_java_repository_stem_without_repository_directory() -> None:
    assert_path_role(
        "src/main/java/com/example/petclinic/owner/OwnerRepository.java",
        "repository",
        40,
    )


@pytest.mark.parametrize(
    ("path", "content"),
    [
        (
            "src/main/java/com/example/Owner.java",
            "@Entity\npublic class Owner {}",
        ),
        (
            "src/main/java/com/example/Address.java",
            "@Embeddable\npublic class Address {}",
        ),
        (
            "src/main/java/com/example/BaseAggregate.java",
            "@MappedSuperclass\npublic abstract class BaseAggregate {}",
        ),
        (
            "src/main/java/com/example/SearchDocument.java",
            "@Document(collection = \"search\")\npublic class SearchDocument {}",
        ),
        (
            "src/main/java/com/example/Visit.java",
            "public record Visit(long id) {}",
        ),
        (
            "src/main/java/com/example/Kind.java",
            "public enum Kind { FIRST, SECOND }",
        ),
    ],
)
def test_path_roles_classify_java_type_declarations_from_content(
    path: str,
    content: str,
) -> None:
    assert_path_role(path, "data_type", 45, "content", content=content)


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (
            "src/main/java/com/example/Owner.java",
            "@Deprecated @Entity public class Owner {}",
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/Visit.java",
            "@Deprecated public record Visit(long id) {}",
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/Kind.java",
            "@Deprecated public enum Kind { FIRST }",
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/Aggregate.java",
            (
                '@Outer(value = @Inner(name = "owner", '
                'nested = @Nested(label = "primary"))) '
                "public enum Aggregate { OWNER }"
            ),
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/Aggregate.java",
            (
                'public @Deprecated(since = "1.0") '
                '@Entity(name = "owner") final class Aggregate {}'
            ),
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/service/OwnerService.java",
            "@FunctionalInterface public interface OwnerService {}",
            PathRole("service_interface", 35, "content"),
        ),
    ],
)
def test_java_declarations_accept_arbitrary_annotation_modifiers(
    path: str,
    content: str,
    expected: PathRole,
) -> None:
    assert classify_path_role(Path(path), content) == expected


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (
            "src/main/java/com/example/service/OwnerService.java",
            "class Holder { public interface OwnerService {} }",
            PathRole("service_interface", 35, "content"),
        ),
        (
            "src/main/java/com/example/Outer.java",
            "class Outer { record Visit(long id) {} }",
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/Outer.java",
            "class Outer { enum VisitKind { CHECKUP } }",
            PathRole("data_type", 45, "content"),
        ),
        (
            "src/main/java/com/example/Outer.java",
            (
                "class Outer { @jakarta.persistence.Entity(name = \"owner\") "
                "private static class Owner {} }"
            ),
            PathRole("data_type", 45, "content"),
        ),
    ],
)
def test_java_declarations_accept_same_line_nested_types(
    path: str,
    content: str,
    expected: PathRole,
) -> None:
    assert classify_path_role(Path(path), content) == expected


@pytest.mark.parametrize(
    "content",
    [
        "import jakarta.persistence.Entity;\npublic class Owner {}",
        "// @Entity\npublic class Owner {}",
        "// public record Owner(long id) {}\npublic class Owner {}",
        "/* @Entity */\npublic class Owner {}",
        "/*\n * @Entity\n * public enum Kind { ONE }\n */\npublic class Owner {}",
        'public class Owner { String value = "@Entity record Fake() enum Kind"; }',
        'public class Owner { char quote = \'\\\'\'; String value = "enum"; }',
        (
            'public class Owner { String value = """\n@Entity\n'
            'record Fake(long id) {}\nenum Kind { ONE }\n"""; }'
        ),
        "public class Owner { void use(String value) {} } // record enum @Entity",
        "@Entity",
        "@Entity arbitrary occurrence\npublic class Owner {}",
        "public class Owner {\n  @Entity\n  private String marker;\n}",
        "public class Owner {\n  @Document\n  void document() {}\n}",
        "class Owner { @Entity private String marker; }",
        "class Owner { @Document void document() {} }",
    ],
)
def test_java_content_roles_ignore_non_declaration_occurrences(content: str) -> None:
    assert_path_role(
        "src/main/java/com/example/Owner.java",
        "source",
        60,
        "fallback",
        content=content,
    )


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (
            "src/test/java/com/example/OwnerTest.java",
            "@Entity\npublic record OwnerTest(long id) {}",
            ("test", 90, "path"),
        ),
        (
            "src/main/java/com/example/OwnerController.java",
            "@Entity\npublic enum OwnerController { INSTANCE }",
            ("entrypoint", 10, "path"),
        ),
        (
            "src/main/java/com/example/service/OwnerService.java",
            "@Entity\npublic record OwnerService(long id) {}",
            ("service", 30, "path"),
        ),
        (
            "src/main/java/com/example/OwnerRepository.java",
            "@Entity\npublic enum OwnerRepository { INSTANCE }",
            ("repository", 40, "path"),
        ),
        (
            "src/main/java/com/example/Config.java",
            "@Entity\npublic record Config(long id) {}",
            ("config", 70, "path"),
        ),
        (
            "src/main/java/com/example/service/impl/OwnerServiceImpl.java",
            "@Entity\npublic enum OwnerServiceImpl { INSTANCE }",
            ("service_impl", 10, "path"),
        ),
        (
            "src/main/java/com/example/service/OwnerService.java",
            "@Entity\npublic interface OwnerService {}",
            ("service_interface", 35, "content"),
        ),
        (
            "src/main/java/com/example/OwnerExecutor.java",
            "@Entity\npublic enum OwnerExecutor { INSTANCE }",
            ("executor", 20, "path"),
        ),
        (
            "src/main/java/com/example/OwnerHandler.java",
            "@Entity\npublic record OwnerHandler(long id) {}",
            ("handler", 25, "path"),
        ),
        (
            "generated/application.yml",
            "@Entity\npublic record GeneratedConfig(long id) {}",
            ("generated_output", 85, "path"),
        ),
    ],
)
def test_java_content_roles_do_not_demote_higher_precedence_roles(
    path: str,
    content: str,
    expected: tuple[str, int, str],
) -> None:
    assert classify_path_role(Path(path), content) == PathRole(*expected)


def test_java_role_classifier_skips_whitespace_boundaries_linearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("src/main/java/example/Padded.java")
    compact = "public class Padded {}\n"
    padded = compact + "\n".join(" " * 256 for _ in range(300)) + "\n"
    expected = classify_path_role(path, compact)
    skipped_characters = 0
    mask_calls = 0
    real_skip_whitespace = path_roles_module._skip_whitespace
    real_mask = path_roles_module._mask_java_comments_and_literals

    def counted_skip_whitespace(content: str, index: int) -> int:
        nonlocal skipped_characters
        result = real_skip_whitespace(content, index)
        skipped_characters += result - index
        return result

    def counted_mask(content: str) -> str:
        nonlocal mask_calls
        mask_calls += 1
        return real_mask(content)

    monkeypatch.setattr(
        path_roles_module,
        "_skip_whitespace",
        counted_skip_whitespace,
    )
    monkeypatch.setattr(
        path_roles_module,
        "_mask_java_comments_and_literals",
        counted_mask,
    )

    actual = classify_path_role(path, padded)

    assert actual == expected
    assert mask_calls == 0
    assert skipped_characters <= len(padded) * 2
