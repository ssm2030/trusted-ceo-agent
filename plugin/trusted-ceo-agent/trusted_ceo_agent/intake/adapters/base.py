from __future__ import annotations

from pathlib import Path
from typing import Protocol

from trusted_ceo_agent.intake.models import ParsedDataset


class IntakeAdapter(Protocol):
    def parse(self, path: Path, source_id: str) -> ParsedDataset: ...

