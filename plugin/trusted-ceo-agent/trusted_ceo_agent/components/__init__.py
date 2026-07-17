from trusted_ceo_agent.components.models import ComponentContract, ComponentRunResult
from trusted_ceo_agent.components.registry import CONTRACTS
from trusted_ceo_agent.components.runner import execute_component, execute_plan


def component_contracts() -> dict[str, ComponentContract]:
    return dict(CONTRACTS)


__all__ = [
    "ComponentContract",
    "ComponentRunResult",
    "component_contracts",
    "execute_component",
    "execute_plan",
]
