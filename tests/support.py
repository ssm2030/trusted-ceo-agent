from __future__ import annotations

import copy
import hashlib
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes


def mission_body(*, business_model: str = "project_b2b_services") -> dict[str, Any]:
    return {
        "mission_contract_id": "mission_" + "1" * 24,
        "contract_version": "1.0.0",
        "business_question": "Find material hidden issues",
        "business_model": business_model,
        "current_symptoms": [],
        "customer_hypotheses": [],
        "decision_context": "portfolio review",
        "decision_units": [],
        "decision_deadline": None,
        "analysis_horizon": {"start": "2025-01-01", "end": "2026-06-30"},
        "organization_scope": [],
        "priority_dimensions": [],
        "constraints": [],
        "recent_business_changes": [],
        "recent_organization_changes": [],
        "recent_policy_changes": [],
        "included_scopes": [],
        "excluded_scopes": [],
        "comparison_preferences": [],
        "materiality_context": {},
        "data_definitions": [],
        "confidentiality": "confidential",
        "required_human_roles": ["ceo"],
    }


def confirmed_mission(*, business_model: str = "project_b2b_services") -> dict[str, Any]:
    body = mission_body(business_model=business_model)
    mission = copy.deepcopy(body)
    mission["confirmation"] = {
        "confirmed": True,
        "actor_id": "ceo-1",
        "actor_role": "ceo",
        "confirmed_at": "2026-07-17T00:00:00Z",
        "contract_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }
    return mission
