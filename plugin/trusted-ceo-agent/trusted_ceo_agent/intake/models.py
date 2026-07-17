from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def semantic_rows_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    fingerprints = sorted(sha256_canonical(dict(row)) for row in rows)
    return sha256_canonical(fingerprints)


@dataclass(frozen=True)
class ParsedRecord:
    logical_index: int
    locator_type: str
    locator: dict[str, Any]
    values: dict[str, Any]


@dataclass
class ParsedDataset:
    source_id: str
    media_type: str
    fields: tuple[str, ...]
    records: tuple[ParsedRecord, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    quality_issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def semantic_rows_hash(self) -> str:
        return semantic_rows_hash(record.values for record in self.records)

    def source_reference(
        self,
        record: ParsedRecord,
        selected_fields: Sequence[str],
        operation: str,
        lineage_set_ref: str,
        *,
        observation_role: str = "unspecified",
    ) -> dict[str, Any]:
        selected = {name: record.values[name] for name in sorted(selected_fields)}
        row_hash = semantic_rows_hash([selected])
        payload = {
            "source_id": self.source_id,
            "observation_role": observation_role,
            "locator_type": record.locator_type,
            "locator": record.locator,
            "selected_fields": sorted(set(selected_fields)),
            "record_count": 1,
            "filters": [],
            "group_by": [],
            "operation": operation,
            "normalized_rows_hash": row_hash,
            "row_multiset_hash": row_hash,
            "lineage_set_ref": lineage_set_ref,
        }
        payload["extraction_hash"] = sha256_canonical(payload)
        return payload

