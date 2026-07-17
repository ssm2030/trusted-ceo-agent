"""Deterministic, authority-preserving multi-domain routing."""

from trusted_ceo_agent.routing.domain_router import (
    catalog_entries_from_runtime_index,
    catalog_entry_from_loaded_pack,
    route_economic_event,
)

__all__ = [
    "catalog_entries_from_runtime_index",
    "catalog_entry_from_loaded_pack",
    "route_economic_event",
]
