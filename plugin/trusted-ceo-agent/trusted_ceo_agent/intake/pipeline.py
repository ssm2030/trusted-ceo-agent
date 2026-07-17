from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trusted_ceo_agent.intake.adapters.selection import select_adapter
from trusted_ceo_agent.intake.models import ParsedDataset
from trusted_ceo_agent.intake.snapshot import SnapshotResult, Snapshotter


@dataclass(frozen=True)
class IntakeResult:
    snapshot: SnapshotResult
    dataset: ParsedDataset | None


class IntakePipeline:
    def __init__(self, snapshotter: Snapshotter) -> None:
        self.snapshotter = snapshotter

    def ingest(self, path: Path, *, observation_roles: tuple[str, ...] = ()) -> IntakeResult:
        snapshot = self.snapshotter.snapshot(path, observation_roles=observation_roles)
        blob = self.snapshotter.artifact_root / snapshot.source["snapshot_ref"]
        suffix = path.suffix.casefold()
        if suffix in {".txt", ".md", ".pdf"}:
            dataset = None
        else:
            adapter = select_adapter(path.name, blob)
            dataset = adapter.parse(blob, snapshot.source["source_id"])
        return IntakeResult(snapshot, dataset)

