from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _run_gate_preflight, _tracked_runtime_identity


_VALID_RUNTIME_IDENTITY = {
    "python_major_minor": [3, 13],
    "sys_platform": "darwin",
    "os_name": "posix",
    "sqlite_version": "3.51.2",
}


def test_product_selection_does_not_require_archival_root(tmp_path: Path) -> None:
    _run_gate_preflight(
        archival_modules=frozenset(),
        runtime_selected=False,
        evidence_root=None,
        repository_root=tmp_path,
        temporary_roots=(),
    )


def test_archival_runtime_overlap_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(pytest.UsageError, match="both archival_acceptance and runtime_pinned"):
        _run_gate_preflight(
            archival_modules=frozenset({"tests/example.py"}),
            runtime_selected=True,
            overlap_selected=True,
            evidence_root=str(tmp_path),
            repository_root=tmp_path,
            temporary_roots=(),
        )


def test_collect_only_bypasses_gate_preflight(tmp_path: Path) -> None:
    _run_gate_preflight(
        archival_modules=frozenset({"tests/example.py"}),
        runtime_selected=True,
        overlap_selected=False,
        collect_only=True,
        evidence_root=None,
        repository_root=tmp_path,
        temporary_roots=(),
    )


def test_collect_only_does_not_bypass_marker_overlap(tmp_path: Path) -> None:
    with pytest.raises(pytest.UsageError, match="both archival_acceptance and runtime_pinned"):
        _run_gate_preflight(
            archival_modules=frozenset({"tests/example.py"}),
            runtime_selected=True,
            overlap_selected=True,
            collect_only=True,
            evidence_root=None,
            repository_root=tmp_path,
            temporary_roots=(),
        )


def test_runtime_selection_rejects_identity_mismatch(tmp_path: Path) -> None:
    expected = _VALID_RUNTIME_IDENTITY
    actual = {**expected, "python_major_minor": [3, 14]}

    with pytest.raises(pytest.UsageError, match="runtime_pinned requires tracked runtime"):
        _run_gate_preflight(
            archival_modules=frozenset(),
            runtime_selected=True,
            evidence_root=None,
            repository_root=tmp_path,
            temporary_roots=(),
            expected_runtime=expected,
            actual_runtime=actual,
        )


def test_runtime_selection_accepts_tracked_identity(tmp_path: Path) -> None:
    identity = _VALID_RUNTIME_IDENTITY

    _run_gate_preflight(
        archival_modules=frozenset(),
        runtime_selected=True,
        evidence_root=None,
        repository_root=tmp_path,
        temporary_roots=(),
        expected_runtime=identity,
        actual_runtime=identity,
    )


@pytest.mark.parametrize(
    "identity",
    [
        pytest.param(
            {key: value for key, value in _VALID_RUNTIME_IDENTITY.items() if key != "os_name"},
            id="missing-key",
        ),
        pytest.param(
            {**_VALID_RUNTIME_IDENTITY, "implementation": "cpython"},
            id="extra-key",
        ),
        pytest.param(
            {**_VALID_RUNTIME_IDENTITY, "sys_platform": ""},
            id="empty-string",
        ),
        pytest.param(
            {**_VALID_RUNTIME_IDENTITY, "python_major_minor": [True, 13]},
            id="bool-version",
        ),
        pytest.param(
            {**_VALID_RUNTIME_IDENTITY, "python_major_minor": [3]},
            id="short-version",
        ),
        pytest.param(
            {**_VALID_RUNTIME_IDENTITY, "sqlite_version": 35102},
            id="wrong-type",
        ),
    ],
)
def test_tracked_runtime_identity_schema_fails_closed(
    tmp_path: Path,
    identity: dict[str, object],
) -> None:
    with pytest.raises(pytest.UsageError, match="tracked runtime identity is invalid"):
        _run_gate_preflight(
            archival_modules=frozenset(),
            runtime_selected=True,
            evidence_root=None,
            repository_root=tmp_path,
            temporary_roots=(),
            expected_runtime=identity,
            actual_runtime=_VALID_RUNTIME_IDENTITY,
        )


def test_actual_runtime_identity_schema_fails_closed(tmp_path: Path) -> None:
    invalid_actual = {**_VALID_RUNTIME_IDENTITY, "os_name": None}

    with pytest.raises(pytest.UsageError, match="actual runtime identity is invalid"):
        _run_gate_preflight(
            archival_modules=frozenset(),
            runtime_selected=True,
            evidence_root=None,
            repository_root=tmp_path,
            temporary_roots=(),
            expected_runtime=_VALID_RUNTIME_IDENTITY,
            actual_runtime=invalid_actual,
        )


def test_missing_tracked_runtime_baseline_fails_without_path_leak(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        pytest.UsageError,
        match="tracked runtime baseline is unavailable",
    ) as caught:
        _tracked_runtime_identity(tmp_path)

    assert str(tmp_path) not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json", id="bad-json"),
        pytest.param("{}", id="missing-runtime-key"),
        pytest.param('{"runtime": []}', id="wrong-runtime-type"),
    ],
)
def test_invalid_tracked_runtime_baseline_fails_without_content_leak(
    tmp_path: Path,
    payload: str,
) -> None:
    baseline = (
        tmp_path
        / "tests/fixtures/retrieval_core_decomposition/baseline.json"
    )
    baseline.parent.mkdir(parents=True)
    baseline.write_text(payload, encoding="utf-8")

    with pytest.raises(
        pytest.UsageError,
        match="tracked runtime baseline is unavailable",
    ) as caught:
        _tracked_runtime_identity(tmp_path)

    assert payload not in str(caught.value)


def test_archival_selection_requires_explicit_root(tmp_path: Path) -> None:
    with pytest.raises(pytest.UsageError, match="--archival-evidence-root is required"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p15_metric_replay.py"}
            ),
            runtime_selected=False,
            evidence_root=None,
            repository_root=tmp_path,
            temporary_roots=(),
        )


def test_archival_root_must_be_absolute_and_exist(tmp_path: Path) -> None:
    archival_modules = frozenset({"tests/test_p15_metric_replay.py"})
    with pytest.raises(pytest.UsageError, match="must be an absolute path"):
        _run_gate_preflight(
            archival_modules=archival_modules,
            runtime_selected=False,
            evidence_root="relative/evidence",
            repository_root=tmp_path,
            temporary_roots=(),
        )
    with pytest.raises(pytest.UsageError, match="existing directory"):
        _run_gate_preflight(
            archival_modules=archival_modules,
            runtime_selected=False,
            evidence_root=str(tmp_path / "missing"),
            repository_root=tmp_path,
            temporary_roots=(),
        )


def test_archival_root_rejects_temporary_directories(tmp_path: Path) -> None:
    with pytest.raises(pytest.UsageError, match="temporary directory"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p15_metric_replay.py"}
            ),
            runtime_selected=False,
            evidence_root=str(tmp_path),
            repository_root=tmp_path,
            temporary_roots=(tmp_path,),
        )


def test_archival_root_rejects_unsupported_external_root(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    external_root = tmp_path / "external"
    repository_root.mkdir()
    external_root.mkdir()

    with pytest.raises(pytest.UsageError, match="external roots are not yet supported"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p15_metric_replay.py"}
            ),
            runtime_selected=False,
            evidence_root=str(external_root),
            repository_root=repository_root,
            temporary_roots=(),
        )


def test_persistent_current_repository_root_is_accepted(tmp_path: Path) -> None:
    _run_gate_preflight(
        archival_modules=frozenset(
            {"tests/test_p15_metric_replay.py"}
        ),
        runtime_selected=False,
        evidence_root=str(tmp_path),
        repository_root=tmp_path,
        temporary_roots=(),
    )


@pytest.mark.parametrize(
    ("module", "required_paths"),
    [
        pytest.param(
            "tests/test_p15_python_import_symbol_acceptance.py",
            (
                ".quality/p15-review-seal/public_contract.json",
                ".quality/p15-review-seal/heldout_payload_v2.json.enc",
            ),
            id="p15-v1",
        ),
        pytest.param(
            "tests/test_p15_v2_python_import_symbol_acceptance.py",
            (
                ".quality/p15-runs/p15-v1-attempt-003/reject-index.json",
            ),
            id="p15-v2",
        ),
        pytest.param(
            "tests/test_p15_v3_exact_provenance_bonus_acceptance.py",
            (
                ".quality/p15-v3-recovery-seal-v2/roster_contract_v2.json",
                ".quality/p15-v3-recovery-seal-v2/seal_hashes_v2.json",
            ),
            id="p15-v3",
        ),
    ],
)
def test_archival_module_requires_its_minimal_local_evidence(
    tmp_path: Path,
    module: str,
    required_paths: tuple[str, ...],
) -> None:
    with pytest.raises(pytest.UsageError, match=required_paths[0]):
        _run_gate_preflight(
            archival_modules=frozenset({module}),
            runtime_selected=False,
            evidence_root=str(tmp_path),
            repository_root=tmp_path,
            temporary_roots=(),
        )

    for relative_path in required_paths:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    _run_gate_preflight(
        archival_modules=frozenset({module}),
        runtime_selected=False,
        evidence_root=str(tmp_path),
        repository_root=tmp_path,
        temporary_roots=(),
    )


@pytest.mark.parametrize(
    "module",
    [
        "tests/test_p8_real_python_graphs_acceptance.py",
        "tests/test_p13_bge_provider_measurement.py",
    ],
    ids=("p8", "p13"),
)
def test_p8_p13_pointer_requires_persistent_protected_inputs(
    tmp_path: Path,
    module: str,
) -> None:
    pointer = tmp_path / ".quality/p13-run-root.txt"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("relative-evidence\n", encoding="utf-8")

    with pytest.raises(pytest.UsageError, match="target must be absolute"):
        _run_gate_preflight(
            archival_modules=frozenset({module}),
            runtime_selected=False,
            evidence_root=str(tmp_path),
            repository_root=tmp_path,
            temporary_roots=(),
        )

    target = tmp_path / "persistent-evidence"
    target.mkdir()
    pointer.write_text(f"{target}\n", encoding="utf-8")
    with pytest.raises(pytest.UsageError, match="protected-inputs.json"):
        _run_gate_preflight(
            archival_modules=frozenset({module}),
            runtime_selected=False,
            evidence_root=str(tmp_path),
            repository_root=tmp_path,
            temporary_roots=(),
        )

    (target / "protected-inputs.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(pytest.UsageError, match="temporary directory"):
        _run_gate_preflight(
            archival_modules=frozenset({module}),
            runtime_selected=False,
            evidence_root=str(tmp_path),
            repository_root=tmp_path,
            temporary_roots=(target,),
        )

    _run_gate_preflight(
        archival_modules=frozenset({module}),
        runtime_selected=False,
        evidence_root=str(tmp_path),
        repository_root=tmp_path,
        temporary_roots=(),
    )


def test_p8_p13_rejects_ancestor_evidence_that_would_override_pointer(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "project/repository"
    repository_root.mkdir(parents=True)
    (repository_root.parent / "protected-inputs.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    with pytest.raises(pytest.UsageError, match="remove ambient override"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p8_real_python_graphs_acceptance.py"}
            ),
            runtime_selected=False,
            evidence_root=str(repository_root),
            repository_root=repository_root,
            temporary_roots=(),
        )


def test_required_archival_file_rejects_symlink_escape(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    required = (
        repository_root
        / ".quality/p15-runs/p15-v1-attempt-003/reject-index.json"
    )
    required.parent.mkdir(parents=True)
    outside = tmp_path / "outside-reject-index.json"
    outside.write_text("{}\n", encoding="utf-8")
    required.symlink_to(outside)

    with pytest.raises(pytest.UsageError, match="must not be a symlink"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p15_v2_python_import_symbol_acceptance.py"}
            ),
            runtime_selected=False,
            evidence_root=str(repository_root),
            repository_root=repository_root,
            temporary_roots=(),
        )


def test_p8_p13_pointer_rejects_symlink(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    pointer = repository_root / ".quality/p13-run-root.txt"
    pointer.parent.mkdir(parents=True)
    target = repository_root / "evidence"
    target.mkdir()
    (target / "protected-inputs.json").write_text("{}\n", encoding="utf-8")
    outside_pointer = tmp_path / "pointer.txt"
    outside_pointer.write_text(f"{target}\n", encoding="utf-8")
    pointer.symlink_to(outside_pointer)

    with pytest.raises(pytest.UsageError, match="must not be a symlink"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p8_real_python_graphs_acceptance.py"}
            ),
            runtime_selected=False,
            evidence_root=str(repository_root),
            repository_root=repository_root,
            temporary_roots=(),
        )


def test_p8_p13_pointer_rejects_empty_or_non_utf8_content(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    pointer = repository_root / ".quality/p13-run-root.txt"
    pointer.parent.mkdir(parents=True)

    pointer.write_text("", encoding="utf-8")
    with pytest.raises(pytest.UsageError, match="must contain one absolute target"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p8_real_python_graphs_acceptance.py"}
            ),
            runtime_selected=False,
            evidence_root=str(repository_root),
            repository_root=repository_root,
            temporary_roots=(),
        )

    pointer.write_bytes(b"\xff")
    with pytest.raises(pytest.UsageError, match="could not be read"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p8_real_python_graphs_acceptance.py"}
            ),
            runtime_selected=False,
            evidence_root=str(repository_root),
            repository_root=repository_root,
            temporary_roots=(),
        )


def test_p8_p13_pointer_accepts_one_target_with_trailing_newline(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    pointer = repository_root / ".quality/p13-run-root.txt"
    pointer.parent.mkdir(parents=True)
    target = repository_root / "evidence"
    target.mkdir()
    (target / "protected-inputs.json").write_text("{}\n", encoding="utf-8")
    pointer.write_text(f"{target}\n", encoding="utf-8")

    _run_gate_preflight(
        archival_modules=frozenset(
            {"tests/test_p8_real_python_graphs_acceptance.py"}
        ),
        runtime_selected=False,
        evidence_root=str(repository_root),
        repository_root=repository_root,
        temporary_roots=(),
    )


def test_p8_p13_protected_inputs_rejects_symlink_escape(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    pointer = repository_root / ".quality/p13-run-root.txt"
    pointer.parent.mkdir(parents=True)
    target = repository_root / "evidence"
    target.mkdir()
    outside = tmp_path / "outside-protected-inputs.json"
    outside.write_text("{}\n", encoding="utf-8")
    (target / "protected-inputs.json").symlink_to(outside)
    pointer.write_text(f"{target}\n", encoding="utf-8")

    with pytest.raises(pytest.UsageError, match="must not be a symlink"):
        _run_gate_preflight(
            archival_modules=frozenset(
                {"tests/test_p8_real_python_graphs_acceptance.py"}
            ),
            runtime_selected=False,
            evidence_root=str(repository_root),
            repository_root=repository_root,
            temporary_roots=(),
        )
