from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter
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
        if suffix == ".csv":
            dataset = CsvAdapter().parse(blob, snapshot.source["source_id"])
        elif suffix == ".json":
            dataset = JsonAdapter().parse(blob, snapshot.source["source_id"])
        elif suffix == ".xlsx":
            dataset = XlsxAdapter().parse(blob, snapshot.source["source_id"])
        elif suffix in (".txt", ".md", ".pdf"):
            dataset = None
        else:
            raise ContractError(f"unsupported intake type: {suffix}")
        return IntakeResult(snapshot, dataset)

