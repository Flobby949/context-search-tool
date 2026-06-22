from pathlib import Path

from context_search_tool.path_roles import classify_path_role


def test_path_roles_classify_frontend_state_and_composable_files() -> None:
    assert classify_path_role(Path("src/stores/modules/auth.store.ts")).name == "state_store"
    assert classify_path_role(Path("src/views/chat/composables/useSseConnection.ts")).name == "composable"
    assert classify_path_role(Path("src/views/chat/types.ts")).name == "data_type"
    assert classify_path_role(Path("src/views/auth/register.vue")).name == "view"


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
