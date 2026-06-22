from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRole:
    name: str
    priority: int


def classify_path_role(path: Path, content: str = "") -> PathRole:
    normalized = path.as_posix().lower()
    parts = tuple(part for part in normalized.split("/") if part)
    name = path.name.lower()
    stem = path.stem.lower()
    original_stem = path.stem
    content_lower = content.lower()

    if _is_test_path(normalized, name, parts):
        return PathRole("test", 90)
    if name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "cargo.lock", "go.sum"}:
        return PathRole("lockfile", 90)
    if name in {"vite.config.ts", "vite.config.js", "webpack.config.js", "tsconfig.json"}:
        return PathRole("config", 70)
    if path.suffix.lower() in {".md", ".mdx", ".rst"}:
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
        or name.endswith(("_test.go", ".test.ts", ".spec.ts", "test.java"))
        or "/src/test/" in path
    )


def _is_frontend_use_hook(path: Path, stem: str) -> bool:
    return (
        path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}
        and len(stem) > 3
        and stem.startswith("use")
        and stem[3].isupper()
    )
