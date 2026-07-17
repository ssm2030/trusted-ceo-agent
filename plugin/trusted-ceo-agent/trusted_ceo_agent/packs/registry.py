from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.packs.schema_validation import validate_document


@dataclass(frozen=True)
class PackRegistry:
    entries: list[dict[str, Any]]

    @classmethod
    def load(cls, path: Path, schema_path: Path) -> "PackRegistry":
        document = strict_loads(path.read_bytes())
        validate_document(document, schema_path)
        return cls(entries=[dict(entry) for entry in document["entries"]])

    def authority_for(self, pack_sha256: str, pack_id: str, pack_version: str) -> str | None:
        matches = [
            entry
            for entry in self.entries
            if entry["pack_sha256"] == pack_sha256
            and entry["pack_id"] == pack_id
            and entry["pack_version"] == pack_version
            and entry["revoked_at"] is None
        ]
        if len(matches) > 1:
            raise ValueError(f"duplicate active registry entry: {pack_id}@{pack_version}")
        return str(matches[0]["effective_authority"]) if matches else None
