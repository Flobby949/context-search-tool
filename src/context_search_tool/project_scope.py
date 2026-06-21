from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from context_search_tool.models import DocumentChunk


PROJECT_SCOPE_METADATA_VERSION = 1
PROJECT_SCOPE_METADATA_VERSION_KEY = "project_scope_metadata_version"

_MARKER_NAMES = {
    "package.json",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "Cargo.toml",
    "pyproject.toml",
}
_SKIP_DIRS = {
    ".git",
    ".context-search",
    "node_modules",
    "vendor",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
}
_MARKER_ORDER = {
    "package.json": 0,
    "go.mod": 1,
    "pom.xml": 2,
    "build.gradle": 3,
    "settings.gradle": 4,
    "Cargo.toml": 5,
    "pyproject.toml": 6,
}
_BUSINESS_SHARED_WORDS = {
    "auth",
    "authentication",
    "authorization",
    "portfolio",
    "fund",
    "service",
    "shared",
    "common",
    "manager",
    "admin",
    "user",
    "order",
}
_ROOT_PACKAGE_SOURCE_DIRS = {
    "app",
    "components",
    "pages",
    "src",
}
_FILENAME_RE = re.compile(r"(?i)(?<![\w.-])[\w-]+(?:\.[\w-]+)+(?![\w.-])")
_PATH_RE = re.compile(r"(?i)(?<![\w.-])[\w.-]+(?:/[\w.-]+)+(?![\w.-])")


@dataclass(frozen=True)
class ProjectUnit:
    root: Path
    name: str
    kind: str
    languages: tuple[str, ...]
    markers: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class QueryScope:
    project_names: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    file_hints: tuple[str, ...] = ()
    confidence: float = 0.0


def detect_project_units(repo: Path, relative_paths: list[Path]) -> tuple[ProjectUnit, ...]:
    repo = repo.resolve()
    markers_by_root: dict[Path, set[str]] = {}
    observed_paths = [Path(path) for path in relative_paths]

    for path in observed_paths:
        if path.name in _MARKER_NAMES:
            markers_by_root.setdefault(path.parent, set()).add(path.name)

    for marker_path in _discover_marker_files(repo):
        relative_marker = marker_path.relative_to(repo)
        markers_by_root.setdefault(relative_marker.parent, set()).add(relative_marker.name)

    if not markers_by_root:
        return (
            ProjectUnit(
                root=Path(""),
                name=repo.name,
                kind="unknown",
                languages=(),
                markers=(),
                confidence=0.0,
            ),
        )

    units = [
        _unit_from_markers(repo, root, markers, observed_paths)
        for root, markers in markers_by_root.items()
    ]
    return tuple(sorted(units, key=lambda unit: (len(unit.root.parts), unit.root.as_posix())))


def unit_for_path(path: Path, units: Iterable[ProjectUnit]) -> ProjectUnit:
    unit_list = tuple(units)
    matches = [unit for unit in unit_list if _path_is_under(path, unit.root)]
    if matches:
        return max(matches, key=lambda unit: len(unit.root.parts))

    for unit in unit_list:
        if _is_root(unit.root):
            return unit

    return ProjectUnit(Path(""), "", "unknown", (), (), 0.0)


def project_metadata(unit: ProjectUnit) -> dict[str, Any]:
    return {
        PROJECT_SCOPE_METADATA_VERSION_KEY: PROJECT_SCOPE_METADATA_VERSION,
        "project_root": _root_to_metadata(unit.root),
        "project_name": unit.name,
        "project_kind": unit.kind,
        "project_languages": list(unit.languages),
        "project_markers": list(unit.markers),
    }


def project_units_from_chunk_metadata(
    chunks: Iterable[DocumentChunk],
) -> tuple[ProjectUnit, ...]:
    units: list[ProjectUnit] = []
    seen_roots: set[str] = set()
    for chunk in chunks:
        metadata = chunk.metadata
        if not _has_current_metadata(metadata):
            continue
        root = str(metadata.get("project_root", ""))
        if root in seen_roots:
            continue
        name = metadata.get("project_name")
        kind = metadata.get("project_kind")
        if not isinstance(name, str) or not isinstance(kind, str):
            continue
        languages = _string_tuple(metadata.get("project_languages", ()))
        markers = _string_tuple(metadata.get("project_markers", ()))
        units.append(ProjectUnit(Path(root), name, kind, languages, markers, 1.0))
        seen_roots.add(root)
    return tuple(units)


def infer_query_scope(
    query: str,
    tokens: list[str],
    project_units: Iterable[ProjectUnit],
) -> QueryScope:
    units = tuple(project_units)
    text = " ".join([query, *tokens])
    text_lower = text.lower()
    words = set(re.findall(r"[a-z0-9_@+-]+", text_lower))
    words -= _BUSINESS_SHARED_WORDS

    project_names: set[str] = set()
    kinds: set[str] = set()
    languages: set[str] = set()
    path_prefixes: list[str] = []
    file_hints: list[str] = []

    for unit in units:
        name = unit.name.lower()
        kind = unit.kind.lower()
        root = _root_to_metadata(unit.root).lower()
        if name and name in words:
            project_names.add(unit.name)
        if kind and kind in words:
            kinds.add(unit.kind)
            languages.update(unit.languages)
        if root and any(prefix == root or prefix.startswith(f"{root}/") for prefix in _path_hints(text_lower)):
            project_names.add(unit.name)

    for path_hint in _path_hints(text_lower):
        if _looks_like_layout_path(path_hint):
            _append_unique(path_prefixes, path_hint)
            first = path_hint.split("/", 1)[0]
            for unit in units:
                if first in {unit.name.lower(), _root_to_metadata(unit.root).lower()}:
                    project_names.add(unit.name)

    for filename in _filename_hints(text_lower):
        if filename in _MARKER_NAMES_LOWER or "." in filename:
            _append_unique(file_hints, filename)
        _add_scope_for_filename(filename, kinds, languages)

    for marker in ("package.json", "go.mod", "pom.xml"):
        if marker in text_lower:
            _append_unique(file_hints, marker)
            _add_scope_for_filename(marker, kinds, languages)

    _add_word_hints(words, kinds, languages)

    for unit in units:
        if unit.name in project_names:
            kinds.add(unit.kind)
            languages.update(unit.languages)

    signal_count = (
        len(project_names)
        + len(kinds)
        + len(languages)
        + len(path_prefixes)
        + len(file_hints)
    )
    confidence = min(1.0, 0.25 + signal_count * 0.10) if signal_count else 0.0

    return QueryScope(
        project_names=tuple(sorted(project_names)),
        kinds=tuple(sorted(kind for kind in kinds if kind)),
        languages=tuple(sorted(languages)),
        path_prefixes=tuple(path_prefixes),
        file_hints=tuple(file_hints),
        confidence=confidence,
    )


def project_scope_score_parts(
    chunk: DocumentChunk,
    query_scope: QueryScope,
    project_unit_count: int,
) -> dict[str, float]:
    if project_unit_count <= 1 or query_scope.confidence <= 0.0:
        return {}

    metadata = chunk.metadata
    if not _has_current_metadata(metadata):
        return {}

    chunk_name = str(metadata.get("project_name", ""))
    chunk_kind = str(metadata.get("project_kind", ""))
    chunk_languages = set(_string_tuple(metadata.get("project_languages", ())))
    chunk_path = chunk.file_path.as_posix().lower()
    chunk_filename = chunk.file_path.name.lower()
    parts: dict[str, float] = {}

    if chunk_name and chunk_name in query_scope.project_names:
        parts["project_scope_boost"] = 0.10
    if chunk_kind and chunk_kind in query_scope.kinds:
        parts["project_kind_boost"] = 0.06
    if chunk_languages.intersection(query_scope.languages):
        parts["project_language_boost"] = 0.04
    if any(chunk_path.startswith(f"{prefix}/") or chunk_path == prefix for prefix in query_scope.path_prefixes):
        parts["project_path_hint_boost"] = 0.08
    elif chunk_filename in query_scope.file_hints and not _scope_conflicts_with_chunk(
        query_scope,
        chunk_name,
        chunk_kind,
        chunk_languages,
    ):
        parts["project_path_hint_boost"] = 0.08

    if parts:
        return parts
    if query_scope.confidence < 0.60 or _is_mixed_scope(query_scope):
        return {}
    if _is_evidence_or_project_anchor(chunk):
        return {}

    return {"project_scope_mismatch_penalty": -0.06}


def project_scope_rerank_adjustment(score_parts: dict[str, float]) -> float:
    return sum(
        value
        for key, value in score_parts.items()
        if key.startswith("project_")
    )


_MARKER_NAMES_LOWER = {marker.lower() for marker in _MARKER_NAMES}


def _discover_marker_files(repo: Path) -> Iterable[Path]:
    stack = [repo]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    stack.append(entry)
            elif entry.name in _MARKER_NAMES:
                yield entry


def _unit_from_markers(
    repo: Path,
    root: Path,
    markers: set[str],
    observed_paths: list[Path],
) -> ProjectUnit:
    ordered_markers = tuple(sorted(markers, key=lambda marker: _MARKER_ORDER[marker]))
    kind, languages = _classify_unit(repo, root, markers, observed_paths)
    return ProjectUnit(
        root=root,
        name=repo.name if _is_root(root) else root.name,
        kind=kind,
        languages=languages,
        markers=ordered_markers,
        confidence=0.9,
    )


def _classify_unit(
    repo: Path,
    root: Path,
    markers: set[str],
    observed_paths: list[Path],
) -> tuple[str, tuple[str, ...]]:
    if "go.mod" in markers:
        return "go", ("go",)
    if "pom.xml" in markers:
        return "java", ("java",)
    if "build.gradle" in markers or "settings.gradle" in markers:
        return "java", ("java", "kotlin")
    if "Cargo.toml" in markers:
        return "rust", ("rust",)
    if "pyproject.toml" in markers:
        return "python", ("python",)
    if "package.json" in markers:
        return _classify_package_json_unit(repo, root, observed_paths)
    return "unknown", ()


def _classify_package_json_unit(
    repo: Path,
    root: Path,
    observed_paths: list[Path],
) -> tuple[str, tuple[str, ...]]:
    package_text = _read_text(repo / root / "package.json")
    package_lower = package_text.lower()
    nearby_paths = [
        path for path in observed_paths if _path_belongs_to_package_unit(path, root)
    ]
    has_vue = (
        "vue" in package_lower
        or "@vitejs/plugin-vue" in package_lower
        or any(path.suffix == ".vue" for path in nearby_paths)
        or _has_nearby_suffix(repo / root, ".vue", root_is_repo=_is_root(root))
    )
    has_vite = "vite" in package_lower
    has_ts = (
        any(path.suffix in {".ts", ".tsx"} for path in nearby_paths)
        or _has_nearby_suffix(repo / root, ".ts", root_is_repo=_is_root(root))
        or _has_nearby_suffix(repo / root, ".tsx", root_is_repo=_is_root(root))
    )

    languages: list[str] = []
    if has_ts:
        languages.append("typescript")
    if has_vue:
        languages.append("vue")
    if has_vue or has_vite:
        return "frontend", tuple(languages)
    return "node", tuple(languages)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _has_nearby_suffix(root: Path, suffix: str, root_is_repo: bool = False) -> bool:
    if not root.exists():
        return False
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in _SKIP_DIRS:
                    continue
                if current != root or not root_is_repo or entry.name in _ROOT_PACKAGE_SOURCE_DIRS:
                    stack.append(entry)
            elif entry.suffix == suffix:
                return True
    return False


def _path_is_under(path: Path, root: Path) -> bool:
    if _is_root(root):
        return True
    return path == root or root in path.parents


def _path_belongs_to_package_unit(path: Path, root: Path) -> bool:
    if not _is_root(root):
        return _path_is_under(path, root)
    if len(path.parts) == 1:
        return True
    return bool(path.parts) and path.parts[0] in _ROOT_PACKAGE_SOURCE_DIRS


def _is_root(path: Path) -> bool:
    return path in {Path(""), Path(".")}


def _root_to_metadata(root: Path) -> str:
    return "" if _is_root(root) else root.as_posix()


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _has_current_metadata(metadata: dict[str, Any]) -> bool:
    return metadata.get(PROJECT_SCOPE_METADATA_VERSION_KEY) == PROJECT_SCOPE_METADATA_VERSION


def _path_hints(text: str) -> list[str]:
    return [match.group(0).strip("./") for match in _PATH_RE.finditer(text)]


def _filename_hints(text: str) -> list[str]:
    return [match.group(0).lower() for match in _FILENAME_RE.finditer(text)]


def _looks_like_layout_path(path_hint: str) -> bool:
    parts = path_hint.split("/")
    if len(parts) < 2:
        return False
    if "." in parts[-1]:
        return False
    return any(part in {"src", "internal", "app", "pkg", "cmd"} for part in parts)


def _add_scope_for_filename(
    filename: str,
    kinds: set[str],
    languages: set[str],
) -> None:
    if filename == "package.json":
        kinds.add("frontend")
    elif filename == "go.mod" or filename.endswith(".go"):
        kinds.add("go")
        languages.add("go")
    elif filename == "pom.xml" or filename.endswith(".java"):
        kinds.add("java")
        languages.add("java")
    elif filename.endswith(".vue"):
        kinds.add("frontend")
        languages.add("vue")
    elif filename.endswith((".ts", ".tsx")):
        languages.add("typescript")


def _add_word_hints(
    words: set[str],
    kinds: set[str],
    languages: set[str],
) -> None:
    if words.intersection({"vue", "pinia", "vite", "eventsource"}):
        kinds.add("frontend")
    if "vue" in words:
        languages.add("vue")
    if words.intersection({"pinia", "vite", "eventsource"}):
        languages.add("typescript")
    if words.intersection({"gin", "go"}):
        kinds.add("go")
        languages.add("go")
    if words.intersection({"maven", "spring", "java"}):
        kinds.add("java")
        languages.add("java")


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _is_mixed_scope(query_scope: QueryScope) -> bool:
    return (
        len(query_scope.project_names) > 1
        or len(query_scope.kinds) > 1
        or len(query_scope.path_prefixes) > 1
    )


def _scope_conflicts_with_chunk(
    query_scope: QueryScope,
    chunk_name: str,
    chunk_kind: str,
    chunk_languages: set[str],
) -> bool:
    if query_scope.project_names and chunk_name not in query_scope.project_names:
        return True
    if query_scope.kinds and chunk_kind not in query_scope.kinds:
        return True
    return bool(query_scope.languages and not chunk_languages.intersection(query_scope.languages))


def _is_evidence_or_project_anchor(chunk: DocumentChunk) -> bool:
    path = chunk.file_path.as_posix().lower()
    name = chunk.file_path.name.lower()
    if name == "pom.xml":
        return True
    if name.startswith("readme"):
        return True
    if "risks" in path:
        return True
    if chunk.file_path.suffix.lower() in {".md", ".mdx", ".rst"}:
        return True
    return str(chunk.metadata.get("anchor_kind", "")) != ""
