from __future__ import annotations

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.application.mutation_commands import (
    analysis,
    approvals,
    lifecycle,
    reasoning,
)
from trusted_ceo_agent.application.mutation_session import (
    MutationSession,
    commit_mutation_session,
)
from trusted_ceo_agent.errors import ContractError


HANDLERS = (
    analysis.handle,
    reasoning.handle,
    approvals.handle,
    lifecycle.handle,
)


def execute_command(
    session: MutationSession,
) -> tuple[int, ApplicationResult]:
    for handler in HANDLERS:
        outcome = handler(session)
        if outcome is False:
            continue
        if isinstance(outcome, tuple):
            return outcome
        return commit_mutation_session(session)
    raise ContractError(f"unsupported mutation command: {session.args.command}")


__all__ = [
    "analysis",
    "approvals",
    "execute_command",
    "lifecycle",
    "reasoning",
]
