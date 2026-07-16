from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from context_search_tool.frontend_roles import classify_frontend_role
from context_search_tool.models import DocumentChunk


_SOURCE_SUFFIXES = {
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".py", ".pyw",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".c", ".h",
    ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".cs", ".swift",
    ".php", ".rb", ".lua", ".dart", ".sh", ".bash", ".zsh", ".fish",
}
_TEMPLATE_SUFFIXES = {".html", ".vue", ".svelte"}
_DOC_SUFFIXES = {".md", ".mdx", ".rst"}
_CONFIG_SUFFIXES = {
    ".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".properties", ".env", ".xml",
}
_INDEXED_LOCKFILE_NAMES = {
    "cargo.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "yarn.lock",
}
_LOCKFILE_QUERY_TOKENS = {
    "dependencies",
    "dependency",
    "lock",
    "lockfile",
    "lockfiles",
    "package",
    "packages",
    "version",
    "versions",
}


@dataclass(frozen=True)
class _GenericFileRole:
    name: str
    noise_level: str
    source_boost: float = 0.0
    penalty: float = 0.0
    penalty_key: str = ""


def _looks_implementation_query(query: str, tokens: list[str]) -> bool:
    if "/" in query:
        return True
    implementation_terms = {
        "handler", "middleware", "command", "engine", "service", "controller",
        "storage", "upload", "delete", "apply", "restore", "invoke", "route",
        "function", "class", "method",
    }
    return bool({token.lower() for token in tokens}.intersection(implementation_terms))


def _has_explicit_lockfile_query(tokens: list[str], name: str) -> bool:
    token_set = {token.lower() for token in tokens}
    if token_set & _LOCKFILE_QUERY_TOKENS:
        return True
    return name == "go.sum" and (
        "gosum" in token_set or {"go", "sum"}.issubset(token_set)
    )


def _is_generated_schema_path(path: str, suffix: str) -> bool:
    parts = [part for part in path.split("/") if part]
    if "generated" in parts:
        return True
    if "gen" not in parts:
        return False
    return suffix in {".json", ".yml", ".yaml"} or "schema" in path


def _generic_file_role(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> _GenericFileRole:
    path = chunk.file_path.as_posix().lower()
    suffix = chunk.file_path.suffix.lower()
    name = chunk.file_path.name.lower()
    is_implementation_query = _looks_implementation_query(query, tokens)

    if _is_test_path(path) or chunk.metadata.get("is_test"):
        return _GenericFileRole("test", "high", penalty=0.10, penalty_key="test_penalty")
    if chunk.metadata.get("is_generated") or _is_generated_schema_path(path, suffix):
        return _GenericFileRole(
            "generated_schema",
            "high",
            penalty=0.20,
            penalty_key="generated_schema_penalty",
        )
    if name in _INDEXED_LOCKFILE_NAMES:
        penalty = 0.0 if _has_explicit_lockfile_query(tokens, name) else 0.20
        return _GenericFileRole(
            "lockfile",
            "high",
            penalty=penalty,
            penalty_key="lockfile_penalty" if penalty else "",
        )
    if suffix in _TEMPLATE_SUFFIXES:
        if classify_frontend_role(chunk.file_path).name in {
            "view_page",
            "layout_component",
            "shared_component",
        }:
            return _GenericFileRole("source", "none", source_boost=0.03)
        penalty = 0.08 if is_implementation_query else 0.0
        return _GenericFileRole(
            "template",
            "medium" if penalty else "low",
            penalty=penalty,
            penalty_key="template_penalty" if penalty else "",
        )
    if suffix in _DOC_SUFFIXES:
        penalty = 0.03 if is_implementation_query else 0.0
        return _GenericFileRole(
            "doc",
            "low",
            penalty=penalty,
            penalty_key="doc_penalty" if penalty else "",
        )
    if suffix in _CONFIG_SUFFIXES:
        penalty = 0.03 if is_implementation_query else 0.0
        return _GenericFileRole(
            "config",
            "low",
            penalty=penalty,
            penalty_key="config_penalty" if penalty else "",
        )
    if suffix in _SOURCE_SUFFIXES:
        return _GenericFileRole("source", "none", source_boost=0.03)
    return _GenericFileRole("unknown", "none")


def _is_test_path(path: str) -> bool:
    return "/test/" in path or path.endswith("test.java")


def _is_readme_document(path: Path) -> bool:
    return path.suffix.lower() == ".md" and path.stem.lower().startswith("readme")
