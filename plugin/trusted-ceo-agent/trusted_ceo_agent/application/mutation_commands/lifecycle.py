from __future__ import annotations

from trusted_ceo_agent.application.mutation_session import MutationSession
from trusted_ceo_agent.application.mutation_support import (
    advance as _advance,
    recorded_blocker_is_resolved as _recorded_blocker_is_resolved,
)
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.runtime_finalization import build_delivery_package


COMMANDS = frozenset({"resume", "stop", "cancel", "finalize"})


def handle(session: MutationSession) -> bool:
    if session.args.command not in COMMANDS:
        return False
    args = session.args
    current = session.current
    files = session.files
    state = session.state
    data = session.data
    if args.command == "resume":
        blocker_resolved = _recorded_blocker_is_resolved(files, state)
        if not blocker_resolved:
            raise ContractError("recorded blocker is unresolved")
        state = _advance(
            state,
            "resume",
            {"blocker_resolved": blocker_resolved, "expected_revision": current},
        )
    elif args.command == "stop":
        state = _advance(state, "stop", {})
    elif args.command == "cancel":
        state = _advance(state, "cancel", {})
    elif args.command == "finalize":
        if state["state"] != "delivery_approved":
            raise ContractError("finalize requires delivery_approved state")
        revalidate_component_artifacts(files)
        package = build_delivery_package(files, run_id=args.run_id, revision=current + 1)
        files.update(package)
        data["delivery_files"] = sorted(package)
        state = _advance(state, "finalize", {"final_validator_passed": True})
    session.files = files
    session.state = state
    session.data = data
    return True
