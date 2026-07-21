from __future__ import annotations

import json
from typing import Any, Mapping

from trusted_ceo_agent.errors import ContractError


def load_document(files: Mapping[str, bytes], path: str, default: Any = None) -> Any:
    payload = files.get(path)
    if payload is None:
        if default is not None:
            return default
        raise ContractError(f"required artifact is missing: {path}")
    return json.loads(payload.decode("utf-8"))


def status_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("status", value.get("diagnostic_disposition"))
        return str(raw) if raw is not None else None
    return None


def mission_document(files: Mapping[str, bytes]) -> Mapping[str, Any]:
    path = (
        "mission/effective-mission-contract.json"
        if "mission/effective-mission-contract.json" in files
        else "mission/mission-contract.json"
    )
    mission = load_document(files, path)
    if not isinstance(mission, Mapping):
        raise ContractError("Mission contract must be an object")
    return mission


def artifact_payload(document: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(document, Mapping):
        raise ContractError(f"{label} must be an object")
    payload = document.get("payload", document)
    if not isinstance(payload, Mapping):
        raise ContractError(f"{label} payload must be an object")
    return payload
