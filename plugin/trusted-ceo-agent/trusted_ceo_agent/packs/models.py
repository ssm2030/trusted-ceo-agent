from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class LoadedPack:
    path: Path
    raw_sha256: str
    document: Mapping[str, Any]
    effective_authority: str

    @property
    def pack_id(self) -> str:
        return str(self.document["pack_id"])

    @property
    def pack_version(self) -> str:
        return str(self.document["pack_version"])

    @property
    def pack_type(self) -> str:
        return str(self.document["pack_type"])

    @property
    def ref(self) -> str:
        return f"{self.pack_id}@{self.pack_version}"


@dataclass(frozen=True)
class DomainSelection:
    status: str
    pack: LoadedPack
    candidate_refs: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()
