from collections.abc import Iterator, Mapping
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

import pytest


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_BASELINE = Path(
    "tests/fixtures/retrieval_core_decomposition/baseline.json"
)
_RUNTIME_IDENTITY_KEYS = frozenset(
    {
        "python_major_minor",
        "sys_platform",
        "os_name",
        "sqlite_version",
    }
)
_ARCHIVAL_REQUIRED_FILES = {
    "tests/test_p15_python_import_symbol_acceptance.py": (
        ".quality/p15-review-seal/public_contract.json",
        ".quality/p15-review-seal/heldout_payload_v2.json.enc",
    ),
    "tests/test_p15_v2_python_import_symbol_acceptance.py": (
        ".quality/p15-runs/p15-v1-attempt-003/reject-index.json",
    ),
    "tests/test_p15_v3_exact_provenance_bonus_acceptance.py": (
        ".quality/p15-v3-recovery-seal-v2/roster_contract_v2.json",
        ".quality/p15-v3-recovery-seal-v2/seal_hashes_v2.json",
    ),
}
_P13_POINTER_MODULES = frozenset(
    {
        "tests/test_p8_real_python_graphs_acceptance.py",
        "tests/test_p13_bge_provider_measurement.py",
    }
)


def _is_temporary(path: Path, temporary_roots: tuple[Path, ...]) -> bool:
    for temporary_root in temporary_roots:
        temporary = temporary_root.resolve(strict=False)
        if path == temporary or temporary in path.parents:
            return True
    return False


def _resolve_archival_root(
    raw_root: str,
    *,
    repository_root: Path,
    temporary_roots: tuple[Path, ...],
) -> Path:
    requested = Path(raw_root)
    if not requested.is_absolute():
        raise pytest.UsageError(
            "--archival-evidence-root must be an absolute path"
        )
    try:
        resolved = requested.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise pytest.UsageError(
            "--archival-evidence-root must resolve to an existing directory"
        ) from None
    if not resolved.is_dir():
        raise pytest.UsageError(
            "--archival-evidence-root must resolve to an existing directory"
        )
    if _is_temporary(resolved, temporary_roots):
        raise pytest.UsageError(
            "--archival-evidence-root must not be a temporary directory"
        )
    if resolved != repository_root.resolve(strict=True):
        raise pytest.UsageError(
            "external roots are not yet supported; use the current repository root"
        )
    return resolved


def _require_archival_file(root: Path, relative_path: str) -> Path:
    requested = root / relative_path
    cursor = root
    for part in requested.relative_to(root).parts:
        cursor /= part
        if cursor.is_symlink():
            raise pytest.UsageError(
                f"archival evidence must not be a symlink: {relative_path}"
            )
    try:
        resolved = requested.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise pytest.UsageError(
            f"archival evidence is missing required input: {relative_path}"
        ) from None
    if not resolved.is_file():
        raise pytest.UsageError(
            f"archival evidence must be a regular file: {relative_path}"
        )
    return resolved


def _validate_p13_pointer(
    root: Path,
    *,
    temporary_roots: tuple[Path, ...],
) -> None:
    if any(
        (ancestor / "protected-inputs.json").is_file()
        or (ancestor / "protected-inputs.json").is_symlink()
        for ancestor in (root, *root.parents)
    ):
        raise pytest.UsageError(
            "remove ambient override protected-inputs.json before running "
            "archival acceptance"
        )
    pointer_path = ".quality/p13-run-root.txt"
    pointer = _require_archival_file(root, pointer_path)
    try:
        raw_target = pointer.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise pytest.UsageError(
            ".quality/p13-run-root.txt could not be read"
        ) from None
    if not raw_target or "\n" in raw_target or "\r" in raw_target:
        raise pytest.UsageError(
            ".quality/p13-run-root.txt must contain one absolute target"
        )
    target = Path(raw_target)
    if not target.is_absolute():
        raise pytest.UsageError(
            ".quality/p13-run-root.txt target must be absolute"
        )
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise pytest.UsageError(
            ".quality/p13-run-root.txt target must be an existing directory"
        ) from None
    if not resolved.is_dir():
        raise pytest.UsageError(
            ".quality/p13-run-root.txt target must be an existing directory"
        )
    if _is_temporary(resolved, temporary_roots):
        raise pytest.UsageError(
            ".quality/p13-run-root.txt target must not be a temporary directory"
        )
    _require_archival_file(resolved, "protected-inputs.json")


def _validate_archival_inputs(
    root: Path,
    *,
    archival_modules: frozenset[str],
    temporary_roots: tuple[Path, ...],
) -> None:
    if archival_modules & _P13_POINTER_MODULES:
        _validate_p13_pointer(root, temporary_roots=temporary_roots)
    for module in archival_modules:
        for relative_path in _ARCHIVAL_REQUIRED_FILES.get(module, ()):
            _require_archival_file(root, relative_path)


def _validate_runtime_identity(
    identity: Mapping[str, object],
    *,
    label: str,
) -> Mapping[str, object]:
    if not isinstance(identity, Mapping) or set(identity) != _RUNTIME_IDENTITY_KEYS:
        raise pytest.UsageError(f"{label} runtime identity is invalid")
    version = identity["python_major_minor"]
    if (
        not isinstance(version, list)
        or len(version) != 2
        or any(type(part) is not int for part in version)
    ):
        raise pytest.UsageError(f"{label} runtime identity is invalid")
    if any(
        not isinstance(identity[key], str) or not identity[key].strip()
        for key in ("sys_platform", "os_name", "sqlite_version")
    ):
        raise pytest.UsageError(f"{label} runtime identity is invalid")
    return identity


def _run_gate_preflight(
    *,
    archival_modules: frozenset[str],
    runtime_selected: bool,
    evidence_root: str | None,
    repository_root: Path,
    temporary_roots: tuple[Path, ...],
    overlap_selected: bool = False,
    collect_only: bool = False,
    expected_runtime: Mapping[str, object] | None = None,
    actual_runtime: Mapping[str, object] | None = None,
) -> None:
    if not archival_modules and not runtime_selected:
        return
    if overlap_selected:
        raise pytest.UsageError(
            "selected tests contain both archival_acceptance and runtime_pinned"
        )
    if collect_only:
        return
    if archival_modules and evidence_root is None:
        raise pytest.UsageError(
            "--archival-evidence-root is required for archival_acceptance tests"
        )
    if archival_modules:
        resolved_root = _resolve_archival_root(
            evidence_root,
            repository_root=repository_root,
            temporary_roots=temporary_roots,
        )
        _validate_archival_inputs(
            resolved_root,
            archival_modules=archival_modules,
            temporary_roots=temporary_roots,
        )
    if runtime_selected:
        if expected_runtime is None or actual_runtime is None:
            raise pytest.UsageError(
                "runtime_pinned preflight requires runtime identity inputs"
            )
        expected_runtime = _validate_runtime_identity(
            expected_runtime,
            label="tracked",
        )
        actual_runtime = _validate_runtime_identity(
            actual_runtime,
            label="actual",
        )
        differences = [
            f"{key}: expected {value!r}, actual {actual_runtime.get(key)!r}"
            for key, value in expected_runtime.items()
            if actual_runtime.get(key) != value
        ]
        if differences:
            raise pytest.UsageError(
                "runtime_pinned requires tracked runtime identity; "
                + "; ".join(differences)
            )


def _runtime_identity() -> dict[str, object]:
    return {
        "python_major_minor": [sys.version_info.major, sys.version_info.minor],
        "sys_platform": sys.platform,
        "os_name": os.name,
        "sqlite_version": sqlite3.sqlite_version,
    }


def _tracked_runtime_identity(repository_root: Path) -> Mapping[str, object]:
    try:
        baseline = json.loads(
            (repository_root / _RUNTIME_BASELINE).read_text(encoding="utf-8")
        )
        identity = baseline["runtime"]
        return _validate_runtime_identity(identity, label="tracked")
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        pytest.UsageError,
    ):
        raise pytest.UsageError(
            "tracked runtime baseline is unavailable or invalid"
        ) from None


def _default_temporary_roots() -> tuple[Path, ...]:
    return (
        Path(tempfile.gettempdir()),
        Path("/tmp"),
        Path("/private/tmp"),
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--archival-evidence-root",
        action="store",
        default=None,
        help="persistent repository root for archival acceptance evidence",
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    archival_modules: set[str] = set()
    runtime_selected = False
    overlap_selected = False
    for item in session.items:
        archival = item.get_closest_marker("archival_acceptance") is not None
        runtime = item.get_closest_marker("runtime_pinned") is not None
        overlap_selected = overlap_selected or (archival and runtime)
        runtime_selected = runtime_selected or runtime
        if archival:
            item_path = Path(str(item.path)).resolve()
            try:
                module = item_path.relative_to(_REPOSITORY_ROOT).as_posix()
            except ValueError:
                module = item_path.name
            archival_modules.add(module)

    collect_only = bool(session.config.option.collectonly)
    expected_runtime = None
    actual_runtime = None
    if runtime_selected and not collect_only:
        expected_runtime = _tracked_runtime_identity(_REPOSITORY_ROOT)
        actual_runtime = _runtime_identity()
    _run_gate_preflight(
        archival_modules=frozenset(archival_modules),
        runtime_selected=runtime_selected,
        overlap_selected=overlap_selected,
        collect_only=collect_only,
        evidence_root=session.config.getoption("archival_evidence_root"),
        repository_root=_REPOSITORY_ROOT,
        temporary_roots=_default_temporary_roots(),
        expected_runtime=expected_runtime,
        actual_runtime=actual_runtime,
    )


@pytest.fixture(scope="session", autouse=True)
def isolate_global_config(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    variable = "CST_GLOBAL_CONFIG_PATH"
    previous = os.environ.get(variable)
    isolated = tmp_path_factory.mktemp("global-config") / "missing-config.toml"
    os.environ[variable] = str(isolated)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = previous
