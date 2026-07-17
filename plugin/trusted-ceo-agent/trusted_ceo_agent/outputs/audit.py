from __future__ import annotations

import hashlib
from typing import Mapping

from trusted_ceo_agent.canonical import canonical_bytes


def build_audit_manifest(files: Mapping[str, bytes]) -> dict[str, object]:
    entries = [
        {"path": path, "sha256": hashlib.sha256(files[path]).hexdigest(), "size": len(files[path])}
        for path in sorted(files)
    ]
    body: dict[str, object] = {"files": entries}
    body["manifest_hash"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body

