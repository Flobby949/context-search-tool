from pathlib import Path

from context_search_tool.path_roles import classify_path_role


def test_path_roles_classify_frontend_state_and_composable_files() -> None:
    assert classify_path_role(Path("src/stores/modules/auth.store.ts")).name == "state_store"
    assert classify_path_role(Path("src/views/chat/composables/useSseConnection.ts")).name == "composable"
    assert classify_path_role(Path("src/views/chat/types.ts")).name == "data_type"
    assert classify_path_role(Path("src/views/auth/register.vue")).name == "view"


def test_path_roles_do_not_treat_user_or_usage_as_composable() -> None:
    assert classify_path_role(Path("src/main/java/com/example/service/UserService.java")).name == "service"
    assert classify_path_role(Path("src/main/java/com/example/controller/UserController.java")).name == "entrypoint"
    assert classify_path_role(Path("src/utils/usage.ts")).name == "source"
    assert classify_path_role(Path("src/views/chat/composables/useSseConnection.ts")).name == "composable"


def test_path_roles_classify_backend_and_collector_files() -> None:
    assert classify_path_role(Path("handler/upload.go")).name == "handler"
    assert classify_path_role(Path("middleware/auth.go")).name == "middleware"
    assert classify_path_role(Path("collector/internal/service/fund_service.go")).name == "service"
    assert classify_path_role(Path("collector/internal/repository/nav_repo.go")).name == "repository"
    assert classify_path_role(Path("collector/internal/source/eastmoney/nav.go")).name == "source_adapter"
    assert classify_path_role(Path("collector/internal/scheduler/scheduler.go")).name == "scheduler"


def test_path_roles_preserve_java_specific_semantics() -> None:
    assert classify_path_role(Path("src/main/java/com/example/service/impl/AuthServiceImpl.java")).name == "service_impl"
    assert classify_path_role(Path("src/main/java/com/example/service/AuthService.java"), "interface AuthService {}").name == "service_interface"
    assert classify_path_role(Path("src/main/java/com/example/service/PageAppCatalogQueryExe.java")).name == "executor"
    assert classify_path_role(Path("src/main/java/com/example/dto/AuthDto.java")).name == "data_type"


def test_path_roles_classify_rust_tauri_files() -> None:
    assert classify_path_role(Path("src-tauri/src/commands.rs")).name == "command"
    assert classify_path_role(Path("src-tauri/src/engine.rs")).name == "engine"
    assert classify_path_role(Path("src-tauri/src/settings.rs")).name == "config"


def test_path_roles_classify_storage_files() -> None:
    assert classify_path_role(Path("storage/local.go")).name == "storage"
    assert classify_path_role(Path("storage/s3.go")).name == "storage"
    assert classify_path_role(Path("internal/storages/oss.go")).name == "storage"


def test_path_roles_classify_all_indexed_lockfiles() -> None:
    for relative_path in (
        "Cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    ):
        assert classify_path_role(Path(relative_path)).name == "lockfile"


def test_path_roles_classify_deployment_and_config_artifacts() -> None:
    dockerfile_role = classify_path_role(Path("Dockerfile"))
    assert dockerfile_role.name == "deployment_config"
    assert dockerfile_role.priority == 75
    assert classify_path_role(Path("docker-compose.yml")).name == "deployment_config"
    assert classify_path_role(Path("docker/image_providers.yaml")).name == "deployment_config"
    docker_env_role = classify_path_role(Path("docker/.env"))
    assert docker_env_role.name == "deployment_config"
    assert docker_env_role.priority == 75
    assert classify_path_role(Path("docker/entrypoint.sh")).name == "source"
    example_role = classify_path_role(Path("image_providers.yaml.example"))
    assert example_role.name == "config_example"
    assert example_role.priority == 75
    runtime_config_role = classify_path_role(Path("config/text_providers.yaml"))
    assert runtime_config_role.name == "runtime_config"
    assert runtime_config_role.priority == 65
    config_env_role = classify_path_role(Path("config/.env"))
    assert config_env_role.name == "runtime_config"
    assert config_env_role.priority == 65
    assert classify_path_role(Path("image_providers.yaml")).name == "runtime_config"
    assert classify_path_role(Path("tsconfig.json")).name == "config"


def test_path_roles_classify_generated_output_and_docs() -> None:
    generated_role = classify_path_role(Path("history/index.json"))
    assert generated_role.name == "generated_output"
    assert generated_role.priority == 85
    assert classify_path_role(Path("output/task_1/result.json")).name == "generated_output"
    assert classify_path_role(Path("README.md")).name == "doc"
    assert classify_path_role(Path("docs/setup.md")).name == "doc"


def test_path_roles_do_not_classify_source_paths_as_generated_output() -> None:
    assert classify_path_role(Path("src/views/history/index.vue")).name == "view"
    assert classify_path_role(Path("src/pages/output/index.tsx")).name == "view"
    assert classify_path_role(Path("src/main/java/com/example/service/history/HistoryService.java")).name == "service"
