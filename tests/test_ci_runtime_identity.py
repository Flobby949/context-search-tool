from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/write_runtime_identity.py"


def _run_identity_writer(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_runtime_identity_cli_writes_closed_canonical_artifact(
    tmp_path: Path,
) -> None:
    output = tmp_path / "runtime-identity.json"

    completed = _run_identity_writer(output)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    raw = output.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert set(payload) == {
        "commit_sha",
        "os",
        "pytest_version",
        "python",
        "sqlite_version",
        "uv_lock_sha256",
        "uv_version",
    }
    assert set(payload["python"]) == {"implementation", "version"}
    assert set(payload["os"]) == {"machine", "release", "system"}
    assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", payload["commit_sha"])
    assert re.fullmatch(r"[0-9a-f]{64}", payload["uv_lock_sha256"])
    assert payload["uv_lock_sha256"] == hashlib.sha256(
        (ROOT / "uv.lock").read_bytes()
    ).hexdigest()
    for value in (
        *payload["python"].values(),
        *payload["os"].values(),
        payload["pytest_version"],
        payload["sqlite_version"],
        payload["uv_version"],
    ):
        assert isinstance(value, str) and value
    assert raw == json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"
    assert str(ROOT) not in raw
    assert str(Path.home()) not in raw
    assert not ({"env", "environment", "home", "hostname"} & set(payload))


def test_runtime_identity_cli_rejects_missing_output_parent_without_path_leak(
    tmp_path: Path,
) -> None:
    completed = _run_identity_writer(tmp_path / "missing/runtime-identity.json")

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == (
        "runtime identity error: output parent directory must already exist\n"
    )
    assert str(tmp_path) not in completed.stderr
