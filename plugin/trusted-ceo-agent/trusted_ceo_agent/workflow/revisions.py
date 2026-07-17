from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from trusted_ceo_agent.errors import RevisionConflict
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


Validator = Callable[[Mapping[str, bytes]], None]


class RevisionManager:
    """Full-snapshot compare-and-swap layered on the trusted ArtifactStore."""

    def __init__(self, store: ArtifactStore, validator: Validator | None = None) -> None:
        self.store = store
        self.validator = validator or (lambda _: None)

    def current_revision(self) -> int:
        return int(self.store.state()["revision"])

    def files(self, revision: int | None = None) -> dict[str, bytes]:
        current = self.current_revision()
        selected = current if revision is None else revision
        if selected > current or selected < 0:
            raise RevisionConflict(f"revision is unavailable: {selected}")
        if selected == 0:
            return {}
        snapshot = self.store.verify_revision(selected)
        result: dict[str, bytes] = {}
        for path in snapshot.rglob("*"):
            if path.is_file() and path.name != "snapshot-manifest.json":
                result[path.relative_to(snapshot).as_posix()] = path.read_bytes()
        return result

    def read(self, path: str, *, revision: int | None = None) -> bytes:
        try:
            return self.files(revision)[path]
        except KeyError as error:
            raise FileNotFoundError(path) from error

    def commit(
        self,
        expected_revision: int,
        updates: Mapping[str, bytes | None],
        *,
        validator: Validator | None = None,
    ) -> int:
        if self.current_revision() != expected_revision:
            raise RevisionConflict(
                f"expected revision {expected_revision}, current is {self.current_revision()}"
            )
        files = self.files(expected_revision)
        for path, payload in updates.items():
            if payload is None:
                files.pop(path, None)
            else:
                files[path] = payload
        (validator or self.validator)(files)
        target = self.store.publish(expected_revision, files)
        return int(target.name[1:])
