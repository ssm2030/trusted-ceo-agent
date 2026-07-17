from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.filesystem import atomic_write, ensure_within


@dataclass(frozen=True)
class SnapshotResult:
    source: dict[str, Any]
    resolver_entry: dict[str, str]


def _identity(stat_result: Any) -> tuple[int, int, int, int]:
    return (
        int(getattr(stat_result, "st_dev", 0)),
        int(getattr(stat_result, "st_ino", 0)),
        int(stat_result.st_size),
        int(stat_result.st_mtime_ns),
    )


class Snapshotter:
    def __init__(
        self,
        input_root: Path,
        artifact_root: Path,
        *,
        after_read_hook: Callable[[Path], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.input_root = input_root.resolve(strict=True)
        self.artifact_root = artifact_root.resolve(strict=False)
        try:
            self.artifact_root.relative_to(self.input_root)
            raise ValueError("artifact root must not overlap input root")
        except ValueError as error:
            if str(error) == "artifact root must not overlap input root":
                raise
        try:
            self.input_root.relative_to(self.artifact_root)
            raise ValueError("input root must not overlap artifact root")
        except ValueError as error:
            if str(error) == "input root must not overlap artifact root":
                raise
        self._after_read_hook = after_read_hook
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(
        self,
        path: Path,
        *,
        source_type: str = "uploaded_file",
        access_policy: str = "permitted",
        evidence_usage: str | None = None,
        observation_roles: Sequence[str] = (),
    ) -> SnapshotResult:
        source_path = ensure_within(self.input_root, path)
        with source_path.open("rb") as handle:
            before_handle = _identity(__import__("os").fstat(handle.fileno()))
            before_path = _identity(source_path.stat())
            hasher = hashlib.sha256()
            chunks: list[bytes] = []
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                chunks.append(chunk)
            if self._after_read_hook is not None:
                try:
                    self._after_read_hook(source_path)
                except OSError as error:
                    raise IntegrityError("source identity changed or could not be revalidated") from error
            after_handle = _identity(__import__("os").fstat(handle.fileno()))
            after_path = _identity(source_path.stat())
        if before_handle != after_handle or before_path != after_path or after_handle != after_path:
            raise IntegrityError("source changed while snapshot was being read")

        payload = b"".join(chunks)
        digest = hasher.hexdigest()
        blob = self.artifact_root / "sources" / "blobs" / digest
        if blob.exists():
            if blob.read_bytes() != payload:
                raise IntegrityError("content-addressed source blob mismatch")
        else:
            atomic_write(blob, payload)
        relative = source_path.relative_to(self.input_root).as_posix()
        path_token = make_id("path", {"relative_path": relative})
        received = self._clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        source = {
            "source_id": f"source_{digest[:24]}",
            "source_type": source_type,
            "access_policy": access_policy,
            "evidence_usage": evidence_usage or ("corroboration_only" if source_type == "official_external" else "primary"),
            "observation_roles": sorted(set(observation_roles)),
            "display_name": source_path.name,
            "media_type": mimetypes.guess_type(source_path.name)[0] or "application/octet-stream",
            "sha256": digest,
            "size_bytes": len(payload),
            "received_at": received,
            "snapshot_ref": f"sources/blobs/{digest}",
            "original_path_token": path_token,
            "aliases": [],
            "metadata": {},
        }
        return SnapshotResult(source, {"original_path_token": path_token, "absolute_path": str(source_path)})
