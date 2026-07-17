from __future__ import annotations

import os
import stat
import time
from pathlib import Path


FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_REPLACE_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.32)


def _is_reparse(path: Path) -> bool:
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, FileNotFoundError):
        return False
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def ensure_within(root: Path, candidate: Path, *, allow_hardlink: bool = False) -> Path:
    root_resolved = root.resolve(strict=True)
    raw = candidate if candidate.is_absolute() else root_resolved / candidate

    current = raw
    existing: list[Path] = []
    while True:
        if current.exists() or current.is_symlink():
            existing.append(current)
        if current == current.parent or current == root_resolved:
            break
        current = current.parent

    for part in reversed(existing):
        if part.is_symlink() or _is_reparse(part):
            raise ValueError(f"reparse or symbolic-link path is forbidden: {part}")

    resolved = raw.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"path escapes allowed root: {candidate}") from error

    if resolved.exists() and resolved.is_file() and not allow_hardlink:
        details = resolved.stat()
        if getattr(details, "st_nlink", 1) > 1:
            raise ValueError(f"hard-linked file is forbidden: {candidate}")
        if stat.S_ISLNK(details.st_mode):
            raise ValueError(f"symbolic link is forbidden: {candidate}")
    return resolved


def replace_with_retry(
    source: Path,
    target: Path,
    *,
    target_must_not_exist: bool = False,
) -> None:
    for delay in (*_REPLACE_RETRY_DELAYS, None):
        if target_must_not_exist and target.exists():
            raise FileExistsError(target)
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    replace_with_retry(temporary, path)

