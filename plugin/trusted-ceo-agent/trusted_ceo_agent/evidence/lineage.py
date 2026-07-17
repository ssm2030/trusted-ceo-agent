from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.filesystem import atomic_write, ensure_within


def _lineage_payload(entries: list[dict[str, Any]]) -> tuple[str, bytes]:
    normalized = sorted(entries, key=lambda item: (item["row_fingerprint"], item["occurrence_index"]))
    digest = hashlib.sha256(canonical_bytes(normalized)).hexdigest()
    reference = f"lineage/sets/{digest}.json"
    payload = canonical_bytes({"lineage_set_ref": reference, "entries": normalized, "sha256": digest})
    return reference, payload


def build_lineage_payload(rows: Iterable[Mapping[str, Any]]) -> tuple[str, bytes]:
    counts: Counter[str] = Counter()
    entries: list[dict[str, Any]] = []
    for row in rows:
        fingerprint = hashlib.sha256(canonical_bytes(dict(row))).hexdigest()
        counts[fingerprint] += 1
        entries.append({"row_fingerprint": fingerprint, "occurrence_index": counts[fingerprint]})
    return _lineage_payload(entries)


def build_lineage_entry_payload(
    row: Mapping[str, Any],
    occurrence_index: int,
) -> tuple[str, bytes]:
    if not isinstance(occurrence_index, int) or isinstance(occurrence_index, bool) or occurrence_index < 1:
        raise ValueError("lineage occurrence_index must be a positive integer")
    fingerprint = hashlib.sha256(canonical_bytes(dict(row))).hexdigest()
    return _lineage_payload([{"row_fingerprint": fingerprint, "occurrence_index": occurrence_index}])


class LineageStore:
    def __init__(self, artifact_root: Path) -> None:
        self.root = artifact_root.resolve(strict=False)

    def put(self, rows: Iterable[Mapping[str, Any]]) -> str:
        reference, payload = build_lineage_payload(rows)
        destination = self.root / reference
        if destination.exists():
            if destination.read_bytes() != payload:
                raise IntegrityError("lineage content-address collision")
        else:
            atomic_write(destination, payload)
        return reference

    def load(self, reference: str) -> dict[str, Any]:
        path = ensure_within(self.root, self.root / reference)
        try:
            payload = strict_loads(path.read_bytes())
        except (OSError, UnicodeError, ValueError) as error:
            raise IntegrityError(f"invalid lineage set: {reference}") from error
        entries = [
            {"row_fingerprint": item["row_fingerprint"], "occurrence_index": int(item["occurrence_index"])}
            for item in payload["entries"]
        ]
        payload["entries"] = entries
        body_hash = hashlib.sha256(canonical_bytes(entries)).hexdigest()
        if body_hash != payload.get("sha256") or reference != payload.get("lineage_set_ref"):
            raise IntegrityError(f"lineage set hash mismatch: {reference}")
        return payload

    def intersection_count(self, left: str, right: str) -> int:
        left_entries = {(item["row_fingerprint"], int(item["occurrence_index"])) for item in self.load(left)["entries"]}
        right_entries = {(item["row_fingerprint"], int(item["occurrence_index"])) for item in self.load(right)["entries"]}
        return len(left_entries & right_entries)
