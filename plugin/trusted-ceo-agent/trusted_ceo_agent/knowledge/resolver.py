from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.compiler import verify_card


AUTHORITATIVE_SOURCE_TYPES = frozenset({"official_primary", "approved_company_policy"})


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ContractError(f"{field} must be an ISO date") from error


def covers_date(*, effective_from: Any, effective_to: Any, effective_on: str) -> bool:
    target = parse_date(effective_on, "effective_on")
    start = parse_date(effective_from, "effective_from")
    if target < start:
        return False
    if effective_to is None:
        return True
    return target <= parse_date(effective_to, "effective_to")


def source_blockers(card: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: set[str] = set()
    for source in card.get("source_refs", ()):
        if not isinstance(source, Mapping):
            blockers.add("source_contract_invalid")
            continue
        source_id = str(source.get("source_id", "unknown"))
        if source.get("approved") is not True:
            blockers.add(f"source_unapproved:{source_id}")
        if source.get("source_hash") != source.get("verified_hash"):
            blockers.add(f"source_hash_mismatch:{source_id}")
        if source.get("source_type") not in AUTHORITATIVE_SOURCE_TYPES:
            blockers.add(f"source_not_authoritative:{source_id}")
        if source.get("retrieval") == "remote" and not source.get("verified_hash"):
            blockers.add(f"remote_source_unverified:{source_id}")
    return tuple(sorted(blockers))


def applicability_blockers(
    card: Mapping[str, Any], *, jurisdiction: str, effective_on: str
) -> tuple[str, ...]:
    blockers: set[str] = set()
    artifact_id = str(card.get("artifact_id", "unknown"))
    if card.get("status") == "revoked":
        blockers.add(f"artifact_revoked:{artifact_id}")
    elif card.get("status") != "active":
        blockers.add(f"artifact_not_active:{artifact_id}")
    if card.get("jurisdiction") != jurisdiction:
        blockers.add(f"jurisdiction_mismatch:{artifact_id}")
    try:
        active = covers_date(
            effective_from=card.get("effective_from"),
            effective_to=card.get("effective_to"),
            effective_on=effective_on,
        )
    except ContractError:
        active = False
    if not active:
        blockers.add(f"effective_period_gap:{artifact_id}")
    blockers.update(source_blockers(card))
    return tuple(sorted(blockers))


def resolve_norm(
    norm_cards: Sequence[Mapping[str, Any]],
    *,
    issue_family_id: str,
    jurisdiction: str,
    effective_on: str,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    failures: set[str] = set()
    for raw in norm_cards:
        try:
            verify_card(raw)
        except ContractError:
            failures.add(f"norm_contract_invalid:{raw.get('artifact_id', 'unknown')}")
            continue
        card = copy.deepcopy(dict(raw))
        if card["artifact_type"] != "norm_card":
            continue
        if card["issue_family_id"] != issue_family_id:
            continue
        blockers = applicability_blockers(
            card, jurisdiction=jurisdiction, effective_on=effective_on
        )
        if blockers:
            failures.update(blockers)
            continue
        candidates.append(card)
    candidates.sort(key=lambda value: (value["version"], value["artifact_id"]), reverse=True)
    if not candidates:
        detail = ",".join(sorted(failures)) or "no_matching_norm"
        raise ContractError(f"no applicable approved Norm Card: {detail}")
    top_version = candidates[0]["version"]
    same_version = [card for card in candidates if card["version"] == top_version]
    if len(same_version) != 1:
        raise ContractError("ambiguous applicable Norm Cards at the same version")
    return copy.deepcopy(same_version[0])
