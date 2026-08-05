from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
UV_VERSION_PATTERN = re.compile(r"uv ([0-9A-Za-z.+-]+)(?:\s|$)")


class RuntimeIdentityError(Exception):
    pass


def _command_output(*command: str) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeIdentityError("runtime identity collection failed") from None
    if completed.returncode != 0:
        raise RuntimeIdentityError("runtime identity collection failed")
    return completed.stdout.strip()


def _runtime_identity() -> dict[str, object]:
    commit_sha = _command_output("git", "rev-parse", "HEAD")
    uv_output = _command_output("uv", "--version")
    uv_match = UV_VERSION_PATTERN.match(uv_output)
    if COMMIT_PATTERN.fullmatch(commit_sha) is None or uv_match is None:
        raise RuntimeIdentityError("runtime identity collection failed")
    try:
        uv_lock_sha256 = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
        pytest_version = importlib.metadata.version("pytest")
    except (OSError, importlib.metadata.PackageNotFoundError):
        raise RuntimeIdentityError("runtime identity collection failed") from None
    identity = {
        "commit_sha": commit_sha,
        "os": {
            "machine": platform.machine(),
            "release": platform.release(),
            "system": platform.system(),
        },
        "pytest_version": pytest_version,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "sqlite_version": sqlite3.sqlite_version,
        "uv_lock_sha256": uv_lock_sha256,
        "uv_version": uv_match.group(1),
    }
    strings = (
        identity["commit_sha"],
        identity["pytest_version"],
        identity["sqlite_version"],
        identity["uv_lock_sha256"],
        identity["uv_version"],
        *identity["python"].values(),
        *identity["os"].values(),
    )
    if any(not isinstance(value, str) or not value for value in strings):
        raise RuntimeIdentityError("runtime identity collection failed")
    return identity


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="write closed CI runtime identity")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not arguments.output.parent.is_dir():
        print(
            "runtime identity error: output parent directory must already exist",
            file=sys.stderr,
        )
        return 2
    try:
        content = _canonical_json(_runtime_identity())
    except RuntimeIdentityError as error:
        print(f"runtime identity error: {error}", file=sys.stderr)
        return 2
    try:
        arguments.output.write_text(
            content,
            encoding="utf-8",
            newline="\n",
        )
    except OSError:
        print(
            "runtime identity error: artifact could not be written",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
