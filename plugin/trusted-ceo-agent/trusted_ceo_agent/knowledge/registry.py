from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.compiler import digest, verify_card


class KnowledgeRegistry:
    """Content-addressed, defensive registry for a frozen knowledge-card set."""

    def __init__(self, artifacts: Iterable[Mapping[str, Any]] = ()) -> None:
        self._artifacts: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            self.register(artifact)

    def register(self, artifact: Mapping[str, Any]) -> dict[str, Any]:
        verify_card(artifact)
        value = copy.deepcopy(dict(artifact))
        artifact_id = str(value["artifact_id"])
        current = self._artifacts.get(artifact_id)
        if current is not None:
            if canonical_bytes(current) != canonical_bytes(value):
                raise ContractError(f"knowledge artifact ID collision: {artifact_id}")
            return copy.deepcopy(current)
        self._artifacts[artifact_id] = value
        return copy.deepcopy(value)

    def get(self, artifact_id: str) -> dict[str, Any]:
        if artifact_id not in self._artifacts:
            raise ContractError(f"unknown knowledge artifact: {artifact_id}")
        return copy.deepcopy(self._artifacts[artifact_id])

    def find(
        self,
        *,
        artifact_type: str | None = None,
        issue_family_id: str | None = None,
        domain: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        values = [
            value
            for value in self._artifacts.values()
            if (artifact_type is None or value["artifact_type"] == artifact_type)
            and (issue_family_id is None or value["issue_family_id"] == issue_family_id)
            and (domain is None or value["domain"] == domain)
        ]
        values.sort(
            key=lambda value: (
                value["artifact_type"],
                value["issue_family_id"],
                value["version"],
                value["artifact_id"],
            )
        )
        return tuple(copy.deepcopy(value) for value in values)

    def snapshot(self) -> dict[str, Any]:
        manifest = [
            {
                "artifact_id": value["artifact_id"],
                "artifact_type": value["artifact_type"],
                "content_hash": value["content_hash"],
            }
            for value in self._artifacts.values()
        ]
        manifest.sort(
            key=lambda item: (item["artifact_type"], item["artifact_id"], item["content_hash"])
        )
        body = {"schema_version": "1.0.0", "artifact_manifest": manifest}
        body["snapshot_hash"] = digest(body)
        return body

    def __len__(self) -> int:
        return len(self._artifacts)
