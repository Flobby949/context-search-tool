from __future__ import annotations

from pathlib import Path, PurePosixPath


_JAVASCRIPT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".vue")
_JAVA_TEST_SUFFIXES = ("ITCase", "Tests", "Test", "IT")
_FORBIDDEN_TARGET_DIRECTORIES = frozenset(
    {
        "__generated__",
        "__snapshots__",
        "fixture",
        "fixtures",
        "generated",
        "golden",
        "goldens",
        "snapshot",
        "snapshots",
        "test-data",
        "test_data",
        "testdata",
    }
)


def is_test_path(
    path: Path | str,
    language: str,
    project_unit_key: str = "",
) -> bool:
    normalized = _normalized_path(path)
    unit = _normalized_unit(project_unit_key)
    if normalized is None or unit is None:
        return False
    relative = _relative_to_unit(normalized, unit)
    if relative is None or not relative.parts:
        return False
    family = _language_family(language, normalized.suffix.lower())
    name = relative.name
    stem = relative.stem
    if family == "java":
        return (
            normalized.suffix == ".java"
            and _java_production_stem(stem) is not None
        )
    if family == "go":
        return (
            normalized.suffix == ".go"
            and _strip_suffix(stem, "_test") is not None
        )
    if family == "rust":
        if normalized.suffix != ".rs":
            return False
        return (
            _strip_longest(stem, ("_tests", "_test")) is not None
            or relative.parts[0] == "tests"
        )
    if family == "python":
        if normalized.suffix != ".py":
            return False
        return (
            _strip_prefix(stem, "test_") is not None
            or _strip_suffix(stem, "_test") is not None
        )
    if family == "javascript":
        suffix = next(
            (item for item in _JAVASCRIPT_SUFFIXES if name.endswith(item)),
            "",
        )
        if not suffix:
            return False
        pre_extension = name[: -len(suffix)]
        return (
            _strip_suffix(pre_extension, ".test") is not None
            or _strip_suffix(pre_extension, ".spec") is not None
        )
    return False


def production_candidates_for_test(
    path: Path | str,
    language: str,
    project_unit_key: str = "",
) -> tuple[Path, ...]:
    normalized = _normalized_path(path)
    unit = _normalized_unit(project_unit_key)
    if normalized is None or unit is None:
        return ()
    relative = _relative_to_unit(normalized, unit)
    if relative is None or not is_test_path(normalized, language, project_unit_key):
        return ()
    family = _language_family(language, normalized.suffix.lower())
    candidates: set[PurePosixPath] = set()
    if family == "java":
        candidates.update(_java_candidates(relative))
    elif family == "go":
        candidates.update(_go_candidates(relative))
    elif family == "rust":
        candidates.update(_rust_candidates(relative))
    elif family == "python":
        candidates.update(_python_candidates(relative))
    elif family == "javascript":
        candidates.update(_javascript_candidates(relative))
    return tuple(
        Path(_join_unit(unit, candidate).as_posix())
        for candidate in sorted(candidates, key=lambda item: item.as_posix())
    )


def is_forbidden_test_target_path(path: Path | str) -> bool:
    normalized = _normalized_path(path)
    if normalized is None:
        return True
    return any(
        part.lower() in _FORBIDDEN_TARGET_DIRECTORIES
        for part in normalized.parts[:-1]
    )


is_test_source_path = is_test_path
test_target_candidates = production_candidates_for_test


def _java_candidates(relative: PurePosixPath) -> tuple[PurePosixPath, ...]:
    prefix = ("src", "test", "java")
    if relative.parts[:3] != prefix or len(relative.parts) <= 3:
        return ()
    stem = _java_production_stem(relative.stem)
    if stem is None:
        return ()
    return (
        PurePosixPath("src", "main", "java", *relative.parts[3:-1], stem + ".java"),
    )


def _go_candidates(relative: PurePosixPath) -> tuple[PurePosixPath, ...]:
    stem = _strip_suffix(relative.stem, "_test")
    if stem is None:
        return ()
    return (relative.with_name(stem + ".go"),)


def _rust_candidates(relative: PurePosixPath) -> tuple[PurePosixPath, ...]:
    candidates: list[PurePosixPath] = []
    stem = _strip_longest(relative.stem, ("_tests", "_test"))
    if stem is not None:
        candidates.append(relative.with_name(stem + ".rs"))
    if relative.parts[0] == "tests" and len(relative.parts) > 1:
        candidates.append(PurePosixPath("src", *relative.parts[1:]))
    return tuple(candidates)


def _python_candidates(relative: PurePosixPath) -> tuple[PurePosixPath, ...]:
    if "tests" in relative.parts[1:-1]:
        return ()
    stems: list[str] = []
    prefix_stem = _strip_prefix(relative.stem, "test_")
    suffix_stem = _strip_suffix(relative.stem, "_test")
    if prefix_stem is not None:
        stems.append(prefix_stem)
    if suffix_stem is not None and suffix_stem not in stems:
        stems.append(suffix_stem)
    candidates: list[PurePosixPath] = []
    if relative.parts[0] == "tests":
        remaining = relative.parts[1:-1]
        for stem in stems:
            candidates.append(PurePosixPath(*remaining, stem + ".py"))
            candidates.append(PurePosixPath("src", *remaining, stem + ".py"))
    else:
        for stem in stems:
            candidates.append(relative.with_name(stem + ".py"))
    return tuple(candidates)


def _javascript_candidates(relative: PurePosixPath) -> tuple[PurePosixPath, ...]:
    if relative.parts.count("__tests__") > 1:
        return ()
    if "tests" in relative.parts[1:-1]:
        return ()
    suffix = next(
        (item for item in _JAVASCRIPT_SUFFIXES if relative.name.endswith(item)), ""
    )
    if not suffix:
        return ()
    pre_extension = relative.name[: -len(suffix)]
    stem = _strip_longest(pre_extension, (".test", ".spec"))
    if stem is None:
        return ()

    bases: list[PurePosixPath] = []
    if "__tests__" in relative.parts:
        parts = list(relative.parts[:-1])
        parts.remove("__tests__")
        bases.append(PurePosixPath(*parts, stem))
    elif relative.parts[0] == "tests":
        remaining = relative.parts[1:-1]
        bases.append(PurePosixPath(*remaining, stem))
        bases.append(PurePosixPath("src", *remaining, stem))
    else:
        bases.append(relative.parent / stem)

    return tuple(
        PurePosixPath(base.as_posix() + candidate_suffix)
        for base in bases
        for candidate_suffix in _JAVASCRIPT_SUFFIXES
    )


def _java_production_stem(stem: str) -> str | None:
    return _strip_longest(stem, _JAVA_TEST_SUFFIXES)


def _strip_longest(stem: str, suffixes: tuple[str, ...]) -> str | None:
    for suffix in suffixes:
        stripped = _strip_suffix(stem, suffix)
        if stripped is not None:
            return stripped
    return None


def _strip_suffix(stem: str, suffix: str) -> str | None:
    if not stem.endswith(suffix):
        return None
    stripped = stem[: -len(suffix)]
    return stripped or None


def _strip_prefix(stem: str, prefix: str) -> str | None:
    if not stem.startswith(prefix):
        return None
    stripped = stem[len(prefix) :]
    return stripped or None


def _language_family(language: str, suffix: str) -> str:
    normalized = language.strip().lower() if isinstance(language, str) else ""
    if normalized in {"java", "go", "rust", "python"}:
        return normalized
    if normalized in {
        "javascript",
        "javascriptreact",
        "jsx",
        "typescript",
        "typescriptreact",
        "tsx",
        "vue",
    }:
        return "javascript"
    return {
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "javascript",
        ".tsx": "javascript",
        ".vue": "javascript",
    }.get(suffix, "")


def _normalized_path(value: Path | str) -> PurePosixPath | None:
    text = value.as_posix() if isinstance(value, (Path, PurePosixPath)) else value
    if not isinstance(text, str) or not text or text == "." or "\\" in text:
        return None
    raw_parts = text.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or path.as_posix() != text:
        return None
    return path


def _normalized_unit(value: str) -> PurePosixPath | None:
    if value == "":
        return PurePosixPath()
    return _normalized_path(value)


def _relative_to_unit(
    path: PurePosixPath, unit: PurePosixPath
) -> PurePosixPath | None:
    if not unit.parts:
        return path
    try:
        return path.relative_to(unit)
    except ValueError:
        return None


def _join_unit(unit: PurePosixPath, path: PurePosixPath) -> PurePosixPath:
    return unit / path if unit.parts else path
