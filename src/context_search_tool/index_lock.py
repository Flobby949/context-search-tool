from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat
from typing import Iterator

from context_search_tool.graph_lifecycle import IndexBusyError


INDEX_LOCK_FILENAME = "index.lock"
_LOCK_MODE = 0o600


@contextmanager
def exclusive_index_lock(index_dir: Path) -> Iterator[Path]:
    if not isinstance(index_dir, Path):
        index_dir = Path(index_dir)
    if index_dir.is_symlink() or not index_dir.is_dir():
        raise ValueError("index directory must be a regular non-symlink directory")

    lock_path = index_dir / INDEX_LOCK_FILENAME
    if lock_path.is_symlink():
        raise ValueError("index lock must be a regular non-symlink file")
    existed = os.path.lexists(lock_path)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(lock_path, flags, _LOCK_MODE)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.EMLINK}:
            raise ValueError(
                "index lock must be a regular non-symlink file"
            ) from error
        raise

    locked = False
    try:
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.lstat(lock_path)
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or stat.S_ISLNK(path_stat.st_mode)
            or (descriptor_stat.st_dev, descriptor_stat.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise ValueError("index lock must be a regular non-symlink file")
        if hasattr(os, "getuid") and descriptor_stat.st_uid != os.getuid():
            raise ValueError("index lock must be owned by the current user")
        mode = stat.S_IMODE(descriptor_stat.st_mode)
        if existed and mode != _LOCK_MODE:
            raise ValueError("index lock permissions must be 0600")
        if not existed and mode != _LOCK_MODE:
            os.fchmod(descriptor, _LOCK_MODE)

        _lock_descriptor(descriptor)
        locked = True
        yield lock_path
    finally:
        if locked:
            _unlock_descriptor(descriptor)
        os.close(descriptor)


def _lock_descriptor(descriptor: int) -> None:
    if os.name == "posix":
        try:
            import fcntl
        except ImportError as error:  # pragma: no cover - supported POSIX runtimes
            raise RuntimeError("exclusive index locking is unavailable") from error
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise IndexBusyError() from error
            raise
        return

    if os.name == "nt":  # pragma: no cover - exercised on Windows CI only
        try:
            import msvcrt
        except ImportError as error:
            raise RuntimeError("exclusive index locking is unavailable") from error
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise IndexBusyError() from error
        return

    raise RuntimeError("exclusive index locking is unavailable")


def _unlock_descriptor(descriptor: int) -> None:
    if os.name == "posix":
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)
    elif os.name == "nt":  # pragma: no cover - exercised on Windows CI only
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
