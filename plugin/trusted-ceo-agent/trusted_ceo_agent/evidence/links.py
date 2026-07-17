from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.contracts.ids import evidence_link_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


def build_evidence_link(
    *,
    target_ref: str,
    target_type: str,
    evidence_ref: str,
    evidence_kind: str,
    evidence_outcome: str | None,
    polarity: str,
    role: str,
    rationale_template: str,
    value_refs: Sequence[Mapping[str, Any]],
    stage: str,
    materialized_by: str,
    origin: Mapping[str, Any],
    independence_group_id: str,
) -> dict[str, Any]:
    if evidence_kind not in {"fact", "signal"} or not evidence_ref.startswith(f"{evidence_kind}_"):
        raise ContractError("Evidence kind does not match Evidence reference")
    if evidence_kind == "signal" and evidence_outcome == "not_assessable" and polarity == "supports" and target_type not in {"expert_review_need"}:
        raise ContractError("not_assessable Signal may only support a boundary or expert review need")
    if evidence_kind == "signal" and evidence_outcome == "not_triggered" and polarity == "supports" and target_type != "counter_hypothesis":
        raise ContractError("not_triggered Signal may only support a counter hypothesis")
    identity = {"target_ref": target_ref, "evidence_ref": evidence_ref, "polarity": polarity, "role": role, "stage": stage}
    result = {
        "evidence_link_id": evidence_link_id(identity),
        "target_ref": target_ref,
        "target_type": target_type,
        "evidence_ref": evidence_ref,
        "evidence_kind": evidence_kind,
        "polarity": polarity,
        "role": role,
        "rationale_template": rationale_template,
        "value_refs": sorted((deepcopy(dict(item)) for item in value_refs), key=lambda item: item["token"]),
        "stage": stage,
        "materialized_by": materialized_by,
        "origin": deepcopy(dict(origin)),
        "independence_group_id": independence_group_id,
    }
    SchemaStore().validate("evidence-link.schema.json", result)
    return result

