from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.mission import (
    is_confirmed_mission,
    materialize_confirmed_mission,
    validate_confirmed_mission,
)
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.approvals import current_approvals
from trusted_ceo_agent.workflow.state_machine import transition


PLUGIN_ROOT = Path(__file__).resolve().parents[1]

def _bootstrap_preflight() -> dict[str, Any]:
    path = PLUGIN_ROOT / "scripts" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("trusted_ceo_bootstrap", path)
    if spec is None or spec.loader is None:
        raise ContractError("bootstrap module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_project(PLUGIN_ROOT)


def _file_identity(details: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(getattr(details, "st_dev", 0)),
        int(getattr(details, "st_ino", 0)),
        int(details.st_size),
        int(details.st_mtime_ns),
    )


def _stable_read(path: Path) -> tuple[Path, bytes]:
    safe = ensure_within(path.parent.resolve(strict=True), path)
    with safe.open("rb") as handle:
        before_handle = _file_identity(os.fstat(handle.fileno()))
        before_path = _file_identity(safe.stat())
        chunks: list[bytes] = []
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_handle = _file_identity(os.fstat(handle.fileno()))
        after_path = _file_identity(safe.stat())
    if before_handle != after_handle or before_path != after_path or after_handle != after_path:
        raise IntegrityError(f"input changed while being read: {safe.name}")
    return safe, b"".join(chunks)


def _snapshot_payloads(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {item["path"]: (snapshot / Path(item["path"])).read_bytes() for item in manifest["files"]}


def _workflow_state(files: Mapping[str, bytes]) -> dict[str, Any]:
    raw = files.get("workflow/state.json")
    if raw is None:
        raise IntegrityError("workflow state is missing")
    return json.loads(raw.decode("utf-8"))


def _effective_mission(files: Mapping[str, bytes]) -> dict[str, Any]:
    stored = strict_loads(files.get("mission/effective-mission-contract.json", files["mission/mission-contract.json"]))
    if not isinstance(stored, Mapping):
        raise ContractError("Mission Contract must be an object")
    if is_confirmed_mission(stored):
        validate_confirmed_mission(stored)
        return dict(stored)
    approvals = current_approvals(files, gate="context")
    if len(approvals) != 1:
        raise ContractError("exactly one current Context approval is required")
    overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
    if not isinstance(overlay, Mapping):
        raise ContractError("HITL overlay must be an object")
    approval = approvals[0]
    return materialize_confirmed_mission(
        stored,
        overlay,
        actor_id=str(approval["actor_id"]),
        actor_role=str(approval["actor_role"]),
        confirmed_at=str(approval["created_at"]),
    )


def _advance(state: Mapping[str, Any], event: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    machine = dict(state)
    machine["status"] = machine.pop("state")
    advanced = transition(machine, event, context or {})
    result = dict(state)
    result["state"] = advanced["status"]
    for key in ("resume_state", "blocker", "failure_reason"):
        if key in advanced:
            result[key] = advanced[key]
        elif key in result and key not in advanced:
            result[key] = None
    return result


def _overlay_status(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("status", value.get("diagnostic_disposition"))
        return str(raw) if raw is not None else None
    return None


def _store_for(args: argparse.Namespace) -> ArtifactStore:
    store = ArtifactStore(args.artifact_root)
    store.open_run(args.run_id)
    return store
advance = _advance
bootstrap_preflight = _bootstrap_preflight
effective_mission = _effective_mission
overlay_status = _overlay_status
snapshot_payloads = _snapshot_payloads
stable_read = _stable_read
store_for = _store_for
workflow_state = _workflow_state
