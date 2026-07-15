from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRole:
    name: str
    priority: int
    basis: str


_DEPLOYMENT_CONFIG_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

_ARTIFACT_CONFIG_SUFFIXES = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
}

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

_SPRING_CONFIG_NAME_RE = re.compile(
    r"(?:application|bootstrap)(?:-.+)?\.(?:properties|yaml|yml)"
)
_SPRING_LOGGING_CONFIG_RE = re.compile(r"(?:logback|log4j).*\.xml")
_JAVA_LINE_START_RE = re.compile(r"^[ \t]*", re.MULTILINE)
_JAVA_ANNOTATION_RE = re.compile(
    r"@(?P<name>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
)
_JAVA_MODIFIER_RE = re.compile(
    r"(?:public|protected|private|abstract|static|final|sealed|non-sealed|"
    r"strictfp)\b"
)
_JAVA_NAMED_TYPE_RE = re.compile(
    r"(?P<kind>class|interface|record|enum)\s+[A-Za-z_$][\w$]*\b"
)
_JAVA_DATA_TYPE_ANNOTATIONS = {
    "Document",
    "Embeddable",
    "Entity",
    "MappedSuperclass",
}
_JAVA_DATA_TYPE_STEM_SUFFIXES = (
    "Dto",
    "DTO",
    "Vo",
    "VO",
    "Request",
    "Response",
    "Entity",
    "Model",
)


def classify_path_role(path: Path, content: str = "") -> PathRole:
    normalized = path.as_posix().lower()
    parts = tuple(part for part in normalized.split("/") if part)
    name = path.name.lower()
    stem = path.stem.lower()
    original_stem = path.stem
    artifact_config_suffix = _artifact_config_suffix(path, name)
    spring_runtime_config = _is_spring_runtime_config(path, name, parts)
    config_artifact = (
        artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES
        or spring_runtime_config
    )

    if _is_test_path(normalized, name, parts):
        return PathRole("test", 90, "path")
    if name in {
        "cargo.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "yarn.lock",
    }:
        return PathRole("lockfile", 90, "path")
    if name in {
        "vite.config.ts",
        "vite.config.js",
        "webpack.config.js",
        "tsconfig.json",
    }:
        return PathRole("config", 70, "path")
    if name in _DEPLOYMENT_CONFIG_NAMES or (
        any(
            part in {"docker", "deploy", "deployment", "k8s", "helm"}
            for part in parts
        )
        and config_artifact
    ):
        return PathRole("deployment_config", 75, "path")
    if name.endswith(".example") or (
        config_artifact
        and any(part in {"example", "examples", "sample"} for part in parts)
    ):
        return PathRole("config_example", 75, "path")
    if config_artifact and any(
        part in {"history", "output", "outputs", "generated", "gen"} for part in parts
    ):
        return PathRole("generated_output", 85, "path")
    if spring_runtime_config:
        return PathRole("runtime_config", 65, "path")
    if artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES and any(
        part in {"config", "configs", "setting", "settings"} for part in parts
    ):
        return PathRole("runtime_config", 65, "path")
    if artifact_config_suffix in _ARTIFACT_CONFIG_SUFFIXES and (
        "config" in stem or "provider" in stem or "setting" in stem
    ):
        return PathRole("runtime_config", 65, "path")
    if (
        path.suffix.lower() in _DOC_SUFFIXES
        or name in _DOC_FILE_NAMES
    ):
        return PathRole("doc", 80, "path")

    if "/service/impl/" in normalized or "serviceimpl" in stem:
        return PathRole("service_impl", 10, "path")
    if "/service/" in normalized and _has_java_interface_declaration(content):
        return PathRole("service_interface", 35, "content")
    if stem.endswith(("queryexe", "qryexe", "executor", "queryexecutor", "exe")):
        return PathRole("executor", 20, "path")
    if (
        any(
            part in {"dto", "vo", "entity", "model", "models", "types", "type"}
            for part in parts
        )
        or stem in {"type", "types"}
        or name.endswith((".types.ts", ".types.tsx"))
    ):
        return PathRole("data_type", 45, "path")
    if any(part in {"store", "stores", "state"} for part in parts) or name.endswith(
        ".store.ts"
    ):
        return PathRole("state_store", 20, "path")
    if any(
        part in {"composable", "composables", "hook", "hooks"} for part in parts
    ) or _is_frontend_use_hook(path, original_stem):
        return PathRole("composable", 20, "path")
    if (
        any(part in {"controller", "controllers"} for part in parts)
        or "controller" in stem
    ):
        return PathRole("entrypoint", 10, "path")
    if (
        any(part in {"router", "routers", "routes"} for part in parts)
        or name == "router.go"
    ):
        return PathRole("router", 15, "path")
    if any(part in {"command", "commands"} for part in parts) or stem == "commands":
        return PathRole("command", 15, "path")
    if stem == "engine":
        return PathRole("engine", 20, "path")
    if (
        any(part in {"handler", "handlers"} for part in parts)
        or "handler" in stem
    ):
        return PathRole("handler", 25, "path")
    if (
        any(part in {"middleware", "middlewares"} for part in parts)
        or "middleware" in stem
    ):
        return PathRole("middleware", 25, "path")
    if any(part in {"storage", "storages"} for part in parts):
        return PathRole("storage", 30, "path")
    if any(part in {"service", "services"} for part in parts):
        return PathRole("service", 30, "path")
    if (
        any(
            part in {"repository", "repositories", "repo", "repos"}
            for part in parts
        )
        or stem.endswith("_repo")
        or (path.suffix.lower() == ".java" and original_stem.endswith("Repository"))
    ):
        return PathRole("repository", 40, "path")
    if any(
        part in {"source", "sources", "adapter", "adapters", "client", "clients"}
        for part in parts
    ):
        return PathRole("source_adapter", 40, "path")
    if (
        any(part in {"view", "views", "page", "pages"} for part in parts)
        or path.suffix.lower() in {".vue", ".svelte"}
        or (path.suffix.lower() == ".html" and "templates" in parts)
    ):
        return PathRole("view", 50, "path")
    if any(part in {"component", "components"} for part in parts):
        return PathRole("component", 50, "path")
    if "scheduler" in parts or "scheduler" in stem:
        return PathRole("scheduler", 25, "path")
    if stem in {"settings", "config"}:
        return PathRole("config", 70, "path")
    if path.suffix.lower() == ".java":
        if original_stem.endswith(_JAVA_DATA_TYPE_STEM_SUFFIXES):
            return PathRole("data_type", 45, "path")
        if _has_java_data_type_declaration(content):
            return PathRole("data_type", 45, "content")

    return PathRole("source", 60, "fallback")


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


def _is_spring_runtime_config(
    path: Path,
    name: str,
    parts: tuple[str, ...],
) -> bool:
    suffix = path.suffix.lower()
    return (
        _SPRING_CONFIG_NAME_RE.fullmatch(name) is not None
        or (
            suffix == ".properties"
            and any(part in {"config", "configs"} for part in parts)
        )
        or _SPRING_LOGGING_CONFIG_RE.fullmatch(name) is not None
        or name in {"persistence.xml", "beans.xml"}
    )


def _has_java_interface_declaration(content: str) -> bool:
    return any(
        kind == "interface"
        for kind, _ in _iter_java_type_declarations(
            _mask_java_comments_and_literals(content)
        )
    )


def _has_java_data_type_declaration(content: str) -> bool:
    masked = _mask_java_comments_and_literals(content)
    return any(
        kind in {"record", "enum"} or has_data_type_annotation
        for kind, has_data_type_annotation in _iter_java_type_declarations(masked)
    )


def _iter_java_type_declarations(masked: str) -> Iterator[tuple[str, bool]]:
    for line_start in _JAVA_LINE_START_RE.finditer(masked):
        index = line_start.end()
        has_data_type_annotation = False
        while index < len(masked):
            index = _skip_whitespace(masked, index)
            annotation = _JAVA_ANNOTATION_RE.match(masked, index)
            if annotation is not None:
                annotation_name = annotation.group("name").rsplit(".", 1)[-1]
                has_data_type_annotation = (
                    has_data_type_annotation
                    or annotation_name in _JAVA_DATA_TYPE_ANNOTATIONS
                )
                index = _consume_annotation_arguments(masked, annotation.end())
                continue
            modifier = _JAVA_MODIFIER_RE.match(masked, index)
            if modifier is not None:
                index = modifier.end()
                continue
            break
        index = _skip_whitespace(masked, index)
        declaration = _JAVA_NAMED_TYPE_RE.match(masked, index)
        if declaration is not None:
            yield declaration.group("kind"), has_data_type_annotation


def _consume_annotation_arguments(content: str, index: int) -> int:
    index = _skip_whitespace(content, index)
    if index >= len(content) or content[index] != "(":
        return index
    depth = 0
    while index < len(content):
        if content[index] == "(":
            depth += 1
        elif content[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def _skip_whitespace(content: str, index: int) -> int:
    while index < len(content) and content[index].isspace():
        index += 1
    return index


def _mask_java_comments_and_literals(content: str) -> str:
    masked: list[str] = []
    index = 0
    state = "code"
    while index < len(content):
        if state == "code":
            if content.startswith("//", index):
                masked.extend((" ", " "))
                index += 2
                state = "line_comment"
            elif content.startswith("/*", index):
                masked.extend((" ", " "))
                index += 2
                state = "block_comment"
            elif content.startswith('"""', index):
                masked.extend((" ", " ", " "))
                index += 3
                state = "text_block"
            elif content[index] == '"':
                masked.append(" ")
                index += 1
                state = "string"
            elif content[index] == "'":
                masked.append(" ")
                index += 1
                state = "character"
            else:
                masked.append(content[index])
                index += 1
            continue

        if content[index] == "\n":
            masked.append("\n")
            index += 1
            if state == "line_comment":
                state = "code"
            continue
        if state == "block_comment" and content.startswith("*/", index):
            masked.extend((" ", " "))
            index += 2
            state = "code"
            continue
        if state == "text_block" and content.startswith('"""', index):
            masked.extend((" ", " ", " "))
            index += 3
            state = "code"
            continue
        if state in {"string", "character", "text_block"} and content[index] == "\\":
            masked.append(" ")
            index += 1
            if index < len(content):
                masked.append("\n" if content[index] == "\n" else " ")
                index += 1
            continue
        if state == "string" and content[index] == '"':
            masked.append(" ")
            index += 1
            state = "code"
            continue
        if state == "character" and content[index] == "'":
            masked.append(" ")
            index += 1
            state = "code"
            continue
        masked.append(" ")
        index += 1
    return "".join(masked)


def _is_frontend_use_hook(path: Path, stem: str) -> bool:
    return (
        path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"}
        and len(stem) > 3
        and stem.startswith("use")
        and stem[3].isupper()
    )
