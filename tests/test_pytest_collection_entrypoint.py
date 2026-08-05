from __future__ import annotations

import os
import shutil
import subprocess
import sysconfig
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
ARCHIVAL_NODE = (
    "tests/test_p15_metric_replay.py::"
    "test_same_capture_gain_records_marker_and_closed_witness"
)


def _run_pytest(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for variable in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
        environment.pop(variable, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    scripts_directory = sysconfig.get_path("scripts")
    assert scripts_directory, "Python scripts directory is unavailable"
    pytest_executable = shutil.which("pytest", path=scripts_directory)
    assert pytest_executable is not None, (
        "pytest console script was not found in the Python scripts directory"
    )
    return subprocess.run(
        [pytest_executable, *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_pytest_console_script_collects_profile_test_without_pythonpath() -> None:
    completed = _run_pytest(
        "-q",
        "--collect-only",
        "tests/test_profile_retrieval.py",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "test_every_profile_target_exists_and_wrapper_is_hit" in completed.stdout


def test_archival_selection_requires_root_before_execution() -> None:
    completed = _run_pytest(
        "-q",
        ARCHIVAL_NODE,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 4, output
    assert "--archival-evidence-root is required" in output


def test_collect_only_bypasses_archival_preflight() -> None:
    completed = _run_pytest(
        "-q",
        "--collect-only",
        ARCHIVAL_NODE,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_archival_preflight_ignores_parent_pytest_addopts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")

    completed = _run_pytest(
        "-q",
        ARCHIVAL_NODE,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 4, output
    assert "--archival-evidence-root is required" in output
