from __future__ import annotations

from typing import Iterable

from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.evidence.lineage import LineageStore


def independence_group_id(source_roles: Iterable[str], lineage_refs: Iterable[str]) -> str:
    return make_id("independence", {"source_roles": sorted(set(source_roles)), "lineage_refs": sorted(set(lineage_refs))})


def are_independent(
    *,
    left_role: str,
    left_lineage: str,
    right_role: str,
    right_lineage: str,
    independent_role_pairs: set[tuple[str, str]],
    allow_disjoint_same_role: bool,
    store: LineageStore,
) -> bool:
    pair = tuple(sorted((left_role, right_role)))
    if pair in {tuple(sorted(item)) for item in independent_role_pairs}:
        return True
    return left_role == right_role and allow_disjoint_same_role and store.intersection_count(left_lineage, right_lineage) == 0

