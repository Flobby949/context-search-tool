from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRole:
    name: str
    priority: int


_DEPLOYMENT_CONFIG_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

_ARTIFACT_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env"}

_DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc", ".asciidoc"}
_DOC_FILE_NAMES = {
    "authors",
    "changelog",
    "code_of_conduct",
    "contributors",
    "copying",
    "history",
    "license",
    "notice",
    "readme",
}


def classify_path_role(path: Path, content: str = "") -> PathRole:
    normalized = path.as_posix().lower()
    parts = tuple(part for part in normalized.split("/") if part)
    name = path.name.lower()
    stem = path.stem.lower()
    original_stem = path.stem
    content_lower = content.lower()
    artifact_config_suffix = _artifact_config_suffix(path, name)

    if _is_test_path(normalized, name, parts):
        return PathRole("test", 90)
    if name in {
        "cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    }:
        return PathRole("lockfile", 90)
    if name in {"vite.config.ts", "vite.config.js", "webpack.config.js", "tsconfig.json"}:
        return PathRole("config", 70)
    if name in _DEPLOYMENT_CONFIG_NAMES or (
        any(part in {"docker", "deploy", "deployment", "k8s", "helm"} for part in parts)
        and artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES
    ):
        return PathRole("deployment_config", 75)
    if name.endswith(".example") or (
        artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES
        and any(part in {"example", "examples", "sample"} for part in parts)
    ):
        return PathRole("config_example", 75)
    if artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES and any(
        part in {"history", "output", "outputs", "generated", "gen"} for part in parts
    ):
        return PathRole("generated_output", 85)
    if artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES and any(
        part in {"config", "configs", "setting", "settings"} for part in parts
    ):
        return PathRole("runtime_config", 65)
    if artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES and (
        "config" in stem or "provider" in stem or "setting" in stem
    ):
        return PathRole("runtime_config", 65)
    if (
        path.suffix.lower() in _DOC_SUFFIXES
        or name in _DOC_FILE_NAMES
    ):
        return PathRole("doc", 80)

    if "/service/impl/" in normalized or "serviceimpl" in stem:
        return PathRole("service_impl", 10)
    if "/service/" in normalized and "interface " in content_lower:
        return PathRole("service_interface", 35)
    if stem.endswith(("queryexe", "qryexe", "executor", "queryexecutor", "exe")):
        return PathRole("executor", 20)
    if (
        any(part in {"dto", "vo", "entity", "model", "models", "types", "type"} for part in parts)
        or stem in {"type", "types"}
        or name.endswith((".types.ts", ".types.tsx"))
    ):
        return PathRole("data_type", 45)
    if any(part in {"store", "stores", "state"} for part in parts) or name.endswith(".store.ts"):
        return PathRole("state_store", 20)
    if any(part in {"composable", "composables", "hook", "hooks"} for part in parts) or _is_frontend_use_hook(path, original_stem):
        return PathRole("composable", 20)
    if any(part in {"controller", "controllers"} for part in parts) or "controller" in stem:
        return PathRole("entrypoint", 10)
    if any(part in {"router", "routers", "routes"} for part in parts) or name == "router.go":
        return PathRole("router", 15)
    if any(part in {"command", "commands"} for part in parts) or stem == "commands":
        return PathRole("command", 15)
    if stem == "engine":
        return PathRole("engine", 20)
    if any(part in {"handler", "handlers"} for part in parts) or "handler" in stem:
        return PathRole("handler", 25)
    if any(part in {"middleware", "middlewares"} for part in parts) or "middleware" in stem:
        return PathRole("middleware", 25)
    if any(part in {"storage", "storages"} for part in parts):
        return PathRole("storage", 30)
    if any(part in {"service", "services"} for part in parts):
        return PathRole("service", 30)
    if any(part in {"repository", "repositories", "repo", "repos"} for part in parts) or stem.endswith("_repo"):
        return PathRole("repository", 40)
    if any(part in {"source", "sources", "adapter", "adapters", "client", "clients"} for part in parts):
        return PathRole("source_adapter", 40)
    if any(part in {"view", "views", "page", "pages"} for part in parts) or path.suffix.lower() in {".vue", ".svelte"}:
        return PathRole("view", 50)
    if any(part in {"component", "components"} for part in parts):
        return PathRole("component", 50)
    if "scheduler" in parts or "scheduler" in stem:
        return PathRole("scheduler", 25)
    if stem in {"settings", "config"}:
        return PathRole("config", 70)

    return PathRole("source", 60)


def _is_test_path(path: str, name: str, parts: tuple[str, ...]) -> bool:
    return (
        "test" in parts
        or "tests" in parts
        or "/src/test/" in path
        or name.endswith(
            (
                "_test.go",
                "_test.rs",
                "_spec.rs",
                ".test.ts",
                ".spec.ts",
                ".test.tsx",
                ".spec.tsx",
                ".test.js",
                ".spec.js",
                ".test.jsx",
                ".spec.jsx",
                "test.java",
            )
        )
    )


def _artifact_config_suffix(path: Path, name: str) -> str:
    if name == ".env":
        return ".env"
    return path.suffix.lower()


def _is_frontend_use_hook(path: Path, stem: str) -> bool:
    return (
        path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}
        and len(stem) > 3
        and stem.startswith("use")
        and stem[3].isupper()
    )
