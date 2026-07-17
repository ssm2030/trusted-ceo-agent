from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from pathlib import Path, PurePosixPath
from typing import Mapping

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError, RevisionConflict
from trusted_ceo_agent.filesystem import atomic_write, ensure_within


_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe artifact path: {value}")
    if path.name == "snapshot-manifest.json":
        raise ValueError("snapshot manifest is reserved")
    return path


class ArtifactStore:
    def __init__(self, artifact_root: Path) -> None:
        self.root = artifact_root.resolve()
        self.run_dir: Path | None = None

    def create_run(self, run_id: str) -> Path:
        if not run_id.startswith("run_") or any(char in run_id for char in "/\\"):
            raise ValueError("invalid run ID")
        self.root.mkdir(parents=True, exist_ok=True)
        run_dir = ensure_within(self.root, self.root / run_id)
        run_dir.mkdir(mode=0o700)
        (run_dir / "snapshots").mkdir()
        atomic_write(
            run_dir / "state.json",
            canonical_bytes({"run_id": run_id, "revision": 0, "snapshot": None}),
        )
        self.run_dir = run_dir
        return run_dir

    def open_run(self, run_id: str) -> Path:
        run_dir = ensure_within(self.root, self.root / run_id)
        if not (run_dir / "state.json").is_file():
            raise FileNotFoundError(run_id)
        self.run_dir = run_dir
        return run_dir

    def _require_run(self) -> Path:
        if self.run_dir is None:
            raise RuntimeError("create_run or open_run must be called first")
        return self.run_dir

    def state(self) -> dict[str, object]:
        run_dir = self._require_run()
        return json.loads((run_dir / "state.json").read_text(encoding="utf-8"))

    def read_operational(self, name: str) -> bytes | None:
        """Read a non-semantic interaction receipt outside immutable revisions."""
        run_dir = self._require_run()
        relative = _relative_path(name)
        path = ensure_within(run_dir, run_dir / "operational" / Path(*relative.parts))
        if not path.exists():
            return None
        if not path.is_file():
            raise IntegrityError(f"operational artifact is not a file: {name}")
        return path.read_bytes()

    def put_operational_once(self, name: str, payload: bytes) -> bytes:
        """Atomically create an operational receipt, or return the existing bytes."""
        if not isinstance(payload, bytes):
            raise TypeError("operational artifact payload must be bytes")
        run_dir = self._require_run()
        relative = _relative_path(name)
        path = ensure_within(run_dir, run_dir / "operational" / Path(*relative.parts))
        lock = _lock_for(run_dir)
        with lock:
            if path.exists():
                if not path.is_file():
                    raise IntegrityError(f"operational artifact is not a file: {name}")
                return path.read_bytes()
            atomic_write(path, payload)
            return payload

    def publish(self, expected_revision: int, files: Mapping[str, bytes]) -> Path:
        run_dir = self._require_run()
        lock = _lock_for(run_dir)
        with lock:
            state = self.state()
            current = int(state["revision"])
            if current != expected_revision:
                raise RevisionConflict(f"expected revision {expected_revision}, current is {current}")

            revision = current + 1
            snapshots = run_dir / "snapshots"
            target = snapshots / f"r{revision:04d}"
            staging = snapshots / f".staging-r{revision:04d}-{uuid.uuid4().hex}"
            staging.mkdir()
            try:
                entries: list[dict[str, object]] = []
                for name in sorted(files):
                    relative = _relative_path(name)
                    payload = files[name]
                    if not isinstance(payload, bytes):
                        raise TypeError(f"artifact payload must be bytes: {name}")
                    destination = ensure_within(staging, staging.joinpath(*relative.parts))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    entries.append({"path": relative.as_posix(), "sha256": _sha256(payload), "size": len(payload)})

                manifest_body = {
                    "revision": revision,
                    "parent_revision": current,
                    "files": entries,
                }
                manifest = dict(manifest_body)
                manifest["manifest_hash"] = _sha256(canonical_bytes(manifest_body))
                manifest_bytes = canonical_bytes(manifest)
                with (staging / "snapshot-manifest.json").open("xb") as handle:
                    handle.write(manifest_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())

                if target.exists():
                    raise IntegrityError(f"revision already exists: {revision}")
                os.replace(staging, target)
                new_state = {
                    "run_id": state["run_id"],
                    "revision": revision,
                    "snapshot": target.name,
                    "manifest_hash": manifest["manifest_hash"],
                }
                atomic_write(run_dir / "state.json", canonical_bytes(new_state))
                return target
            except Exception:
                if staging.exists():
                    shutil.rmtree(staging)
                raise

    def verify_revision(self, revision: int) -> Path:
        run_dir = self._require_run()
        snapshot = ensure_within(run_dir, run_dir / "snapshots" / f"r{revision:04d}")
        manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
        body = {key: manifest[key] for key in ("revision", "parent_revision", "files")}
        if _sha256(canonical_bytes(body)) != manifest["manifest_hash"]:
            raise IntegrityError("snapshot manifest hash mismatch")
        for item in manifest["files"]:
            path = ensure_within(snapshot, snapshot / Path(item["path"]))
            payload = path.read_bytes()
            if len(payload) != item["size"] or _sha256(payload) != item["sha256"]:
                raise IntegrityError(f"artifact hash mismatch: {item['path']}")
        return snapshot
