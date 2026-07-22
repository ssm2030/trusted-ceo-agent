from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


class ServiceRootLease:
    """Hold one cross-process owner for a local service root."""

    def __init__(self, handle: BinaryIO) -> None:
        self._handle = handle
        self._closed = False

    @classmethod
    def acquire(cls, service_root: Path) -> ServiceRootLease:
        root = service_root.resolve()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = root / "service-owner.lock"
        handle = path.open("a+b")
        try:
            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                path.chmod(0o600)
            except OSError:
                pass
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError("service root is already in use") from error
        return cls(handle)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()

    def __enter__(self) -> ServiceRootLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
