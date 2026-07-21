from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.mission import (
    is_confirmed_mission,
    materialize_confirmed_mission,
    validate_confirmed_mission,
)
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.approvals import current_approvals
from trusted_ceo_agent.workflow.state_machine import transition

def _application_result(
    *,
    command: str,
    ok: bool,
    code: int,
    message: str,
    run_id: str | None = None,
    revision: int | None = None,
    state: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> ApplicationResult:
    return ApplicationResult(
        command=command,
        ok=ok,
        code=code,
        message=message,
        run_id=run_id,
        revision=revision,
        state=state,
        data=data or {},
    )


def _snapshot_payloads(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / Path(item["path"])).read_bytes()
        for item in manifest["files"]
    }


def _workflow_state(files: Mapping[str, bytes]) -> dict[str, Any]:
    raw = files.get("workflow/state.json")
    if raw is None:
        raise IntegrityError("workflow state is missing")
    state = json.loads(raw.decode("utf-8"))
    if not isinstance(state, dict):
        raise IntegrityError("workflow state is invalid")
    return state


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


def _recorded_blocker_is_resolved(files: Mapping[str, bytes], state: Mapping[str, Any]) -> bool:
    if state.get("blocker") != "component_contract_failure":
        return False
    component_runs = [
        strict_loads(payload)
        for path, payload in files.items()
        if path.startswith("components/runs/") and path.endswith(".json")
    ]
    return bool(component_runs) and all(
        isinstance(run, Mapping) and run.get("status") != "failed"
        for run in component_runs
    )


def _overlay_status(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("status", value.get("diagnostic_disposition"))
        return str(raw) if raw is not None else None
    return None
advance = _advance
application_result = _application_result
effective_mission = _effective_mission
overlay_status = _overlay_status
recorded_blocker_is_resolved = _recorded_blocker_is_resolved
snapshot_payloads = _snapshot_payloads
workflow_state = _workflow_state
