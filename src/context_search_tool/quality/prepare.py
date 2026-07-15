from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_search_tool.quality.cases import (
    QualityRepo,
    _validate_checkout_dir,
    _validate_portable_component,
    _validate_source_commit,
    _validate_source_url,
    load_quality_fixture,
)


PROVENANCE_FILENAME = ".cst-quality-provenance.json"
_PROVENANCE_SCHEMA_VERSION = 1
_RECORD_FIELDS = frozenset(
    {"source_url", "source_commit", "checkout_dir", "prepared_at"}
)


@dataclass(frozen=True)
class PreparedRepository:
    repo_key: str
    commit: str
    checkout_dir: str


def _git(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return completed.stdout.strip()


def prepare_quality_fixture(
    fixture_path: Path,
    profile: str,
    repos_dir: Path,
) -> tuple[PreparedRepository, ...]:
    fixture = load_quality_fixture(fixture_path)
    if profile not in fixture.profile_configs:
        raise ValueError(f"unknown quality profile: {profile}")
    selected = tuple(
        repo
        for repo in fixture.repos
        if repo.source_url
        and profile in repo.profiles
        and any(not case.profiles or profile in case.profiles for case in repo.queries)
    )
    if not selected:
        raise ValueError("quality profile selects no remote repositories")
    checkout_names = [repo.checkout_dir.casefold() for repo in selected]
    if len(checkout_names) != len(set(checkout_names)):
        raise ValueError("quality profile has duplicate checkout directories")

    root = _repos_root(repos_dir, create=True)
    manifest = _load_provenance(root, required=False)
    prepared: list[PreparedRepository] = []
    for repo in selected:
        _prepare_repo(repo, root, manifest)
        prepared.append(
            PreparedRepository(
                repo_key=repo.repo_key,
                commit=repo.source_commit,
                checkout_dir=repo.checkout_dir,
            )
        )
    return tuple(prepared)


def validate_prepared_repo(repo: QualityRepo, repos_dir: Path) -> Path:
    if not repo.source_url or not repo.source_commit or not repo.checkout_dir:
        raise ValueError("quality repository has no remote source declaration")
    root = _repos_root(repos_dir, create=False)
    manifest = _load_provenance(root, required=True)
    record = manifest["repos"].get(repo.repo_key)
    if not isinstance(record, dict) or not _record_matches(record, repo):
        raise ValueError("prepared provenance manifest does not match catalog")
    checkout = _checkout_path(root, repo.checkout_dir)
    if not _is_real_directory(checkout):
        raise ValueError("prepared checkout is missing")
    _validate_checkout(checkout, repo)
    return checkout


def _prepare_repo(
    repo: QualityRepo,
    root: Path,
    manifest: dict[str, Any],
) -> None:
    records = manifest["repos"]
    record = records.get(repo.repo_key)
    if record is not None and (
        not isinstance(record, dict)
        or not _record_source_identity_matches(record, repo)
    ):
        raise ValueError("prepared provenance manifest does not match catalog")
    for other_key, other_record in records.items():
        if (
            other_key != repo.repo_key
            and isinstance(other_record, dict)
            and other_record.get("checkout_dir", "").casefold()
            == repo.checkout_dir.casefold()
        ):
            raise ValueError("prepared checkout collision")

    checkout = _checkout_path(root, repo.checkout_dir)
    if _path_exists(checkout):
        if record is None:
            raise ValueError("prepared checkout collision")
        if not _is_real_directory(checkout):
            raise ValueError("prepared checkout collision")
        if _record_matches(record, repo):
            _validate_checkout(checkout, repo)
            return
        previous_repo = replace(repo, source_commit=record["source_commit"])
        try:
            _validate_checkout(checkout, previous_repo)
        except ValueError:
            raise ValueError(
                "prepared provenance manifest does not match catalog"
            ) from None
        _update_owned_checkout(
            checkout,
            repo,
            previous_repo,
            root,
            manifest,
        )
        return

    if record is not None and not _record_matches(record, repo):
        raise ValueError("prepared provenance manifest does not match catalog")

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{repo.checkout_dir}.", dir=root)
    )
    try:
        _git(
            "clone",
            "--no-checkout",
            "--",
            repo.source_url,
            str(temporary),
            cwd=root,
        )
        _git("checkout", "--detach", repo.source_commit, cwd=temporary)
        _validate_checkout(temporary, repo)
        if _path_exists(checkout):
            raise ValueError("prepared checkout collision")
        temporary.rename(checkout)
    except (OSError, subprocess.SubprocessError, ValueError):
        _remove_owned_temporary(temporary)
        raise ValueError("quality repository preparation failed") from None

    records[repo.repo_key] = _provenance_record(repo)
    try:
        _write_provenance(root, manifest)
    except Exception:
        # The checkout is ours, but without provenance it must not be left looking
        # user-owned or be reused implicitly on a later run.
        _remove_owned_temporary(checkout)
        records.pop(repo.repo_key, None)
        raise ValueError("quality repository preparation failed") from None


def _update_owned_checkout(
    checkout: Path,
    repo: QualityRepo,
    previous_repo: QualityRepo,
    root: Path,
    manifest: dict[str, Any],
) -> None:
    records = manifest["repos"]
    previous_record = dict(records[repo.repo_key])
    checkout_attempted = False
    manifest_attempted = False
    try:
        _git("fetch", "--", "origin", repo.source_commit, cwd=checkout)
        checkout_attempted = True
        _git("checkout", "--detach", repo.source_commit, cwd=checkout)
        _validate_checkout(checkout, repo)
        records[repo.repo_key] = _provenance_record(repo)
        manifest_attempted = True
        _write_provenance(root, manifest)
    except Exception:
        records[repo.repo_key] = previous_record
        if checkout_attempted:
            try:
                _git(
                    "checkout",
                    "--detach",
                    previous_repo.source_commit,
                    cwd=checkout,
                )
                _validate_checkout(checkout, previous_repo)
            except Exception:
                pass
        if manifest_attempted:
            try:
                _write_provenance(root, manifest)
            except Exception:
                pass
        raise ValueError("quality repository preparation failed") from None


def _provenance_record(repo: QualityRepo) -> dict[str, str]:
    return {
        "source_url": repo.source_url,
        "source_commit": repo.source_commit,
        "checkout_dir": repo.checkout_dir,
        "prepared_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _repos_root(repos_dir: Path, *, create: bool) -> Path:
    raw = repos_dir.expanduser()
    if _has_symlink_component(raw):
        raise ValueError("quality repositories directory is invalid")
    if _path_exists(raw):
        try:
            mode = raw.lstat().st_mode
        except OSError:
            raise ValueError("quality repositories directory is invalid") from None
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError("quality repositories directory is invalid")
    elif create:
        try:
            raw.mkdir(parents=True)
        except OSError:
            raise ValueError("quality repositories directory is invalid") from None
    else:
        raise ValueError("prepared repositories directory is missing")
    return raw.resolve()


def _has_symlink_component(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if stat.S_ISLNK(mode):
            return True
    return False


def _checkout_path(root: Path, checkout_dir: str) -> Path:
    checkout = root / checkout_dir
    if checkout.parent != root:
        raise ValueError("prepared checkout escapes repositories directory")
    return checkout


def _load_provenance(root: Path, *, required: bool) -> dict[str, Any]:
    path = root / PROVENANCE_FILENAME
    if not _path_exists(path):
        if required:
            raise ValueError("prepared provenance manifest is missing")
        return {"schema_version": _PROVENANCE_SCHEMA_VERSION, "repos": {}}
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "repos"}
            or data["schema_version"] != _PROVENANCE_SCHEMA_VERSION
            or not isinstance(data["repos"], dict)
        ):
            raise ValueError
        for repo_key, record in data["repos"].items():
            if (
                not isinstance(repo_key, str)
                or not repo_key
                or _validate_portable_component(repo_key, "repo_key") != repo_key
                or not _valid_record(record)
            ):
                raise ValueError
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise ValueError("prepared provenance manifest is invalid") from None
    return data


def _valid_record(record: Any) -> bool:
    if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
        return False
    if not all(isinstance(value, str) and value for value in record.values()):
        return False
    try:
        parsed = datetime.fromisoformat(record["prepared_at"].replace("Z", "+00:00"))
        source_url = _validate_source_url(record["source_url"])
        source_commit = _validate_source_commit(record["source_commit"])
        checkout_dir = _validate_checkout_dir(record["checkout_dir"])
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and source_url == record["source_url"]
        and source_commit == record["source_commit"]
        and checkout_dir == record["checkout_dir"]
    )


def _record_matches(record: dict[str, Any], repo: QualityRepo) -> bool:
    return (
        _record_source_identity_matches(record, repo)
        and record["source_commit"] == repo.source_commit
    )


def _record_source_identity_matches(
    record: dict[str, Any],
    repo: QualityRepo,
) -> bool:
    return (
        _valid_record(record)
        and record["source_url"] == repo.source_url
        and record["checkout_dir"] == repo.checkout_dir
    )


def _write_provenance(root: Path, manifest: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{PROVENANCE_FILENAME}.",
        dir=root,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / PROVENANCE_FILENAME)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _validate_checkout(checkout: Path, repo: QualityRepo) -> None:
    try:
        head = _git("rev-parse", "HEAD", cwd=checkout)
        branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout)
        remote = _git("config", "--get", "remote.origin.url", cwd=checkout)
        status_output = _git(
            "status",
            "--porcelain",
            "--untracked-files=no",
            cwd=checkout,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("prepared checkout is invalid") from None
    if (
        head.lower() != repo.source_commit
        or branch != "HEAD"
        or remote != repo.source_url
        or status_output
    ):
        raise ValueError("prepared checkout is invalid")


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _is_real_directory(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISDIR(mode) and not stat.S_ISLNK(mode)


def _remove_owned_temporary(path: Path) -> None:
    if not _path_exists(path):
        return
    try:
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError:
        pass


__all__ = (
    "PROVENANCE_FILENAME",
    "PreparedRepository",
    "prepare_quality_fixture",
    "validate_prepared_repo",
)
