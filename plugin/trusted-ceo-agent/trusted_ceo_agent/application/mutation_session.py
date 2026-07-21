from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.application.mutation_support import (
    application_result,
    snapshot_payloads,
    workflow_state,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.state_machine import TERMINAL


@dataclass
class MutationSession:
    args: SimpleNamespace
    store: ArtifactStore
    pointer: dict[str, Any]
    current: int
    files: dict[str, bytes]
    state: dict[str, Any]
    data: dict[str, Any] = field(default_factory=dict)
    exit_code: int = 0
    command_ok: bool = True
    command_message: str = "mutation committed"


def open_mutation_session(args: SimpleNamespace) -> MutationSession:
    store = ArtifactStore(args.artifact_root)
    store.open_run(args.run_id)
    pointer = store.state()
    current = int(pointer["revision"])
    if current != args.expected_revision:
        raise RevisionConflict(
            f"expected revision {args.expected_revision}, current is {current}"
        )
    files = snapshot_payloads(store, current)
    state = workflow_state(files)
    if state["state"] in TERMINAL:
        raise ContractError(f"terminal state cannot mutate: {state['state']}")
    return MutationSession(
        args=args,
        store=store,
        pointer=pointer,
        current=current,
        files=files,
        state=state,
    )


def commit_mutation_session(
    session: MutationSession,
) -> tuple[int, ApplicationResult]:
    args = session.args
    new_revision = session.current + 1
    session.state["revision"] = new_revision
    session.files["workflow/state.json"] = canonical_bytes(session.state)
    session.files[
        f"audit/events/r{new_revision:04d}-{args.command}.json"
    ] = canonical_bytes(
        {
            "command": args.command,
            "from_revision": session.current,
            "to_revision": new_revision,
        }
    )
    session.store.publish(session.current, session.files)
    return session.exit_code, application_result(
        command=args.command,
        ok=session.command_ok,
        code=session.exit_code,
        message=(
            "human action required"
            if session.exit_code == 2
            else session.command_message
        ),
        run_id=args.run_id,
        revision=new_revision,
        state=session.state["state"],
        data=session.data,
    )
