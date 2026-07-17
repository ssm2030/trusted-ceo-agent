"""Deterministic accounting Suite compiler and semantic release gate."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Any

from trusted_ceo_agent.accounting.seeds import (
    COMMON_PROCEDURE_IDS,
    DESIGN_REFS,
    ISSUE_PROCEDURE_MAP,
    ISSUE_ROWS,
    NORM_SEED_TITLES,
    PACK_SPECS,
    PROCEDURE_SEED_TITLES,
    norm_source_ref,
    procedure_source_ref,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError

SCHEMA_VERSION = "1.0.0"
SUITE_ID = "b2b-service-accounting-content-suite"
EXPECTED_DEPTH_GATES = tuple(f"D{number}" for number in range(1, 13))
EXPECTED_TEST_TYPES = ("normal", "error", "boundary", "counter_evidence", "compound")
EXPECTED_ISSUE_IDS = frozenset(
    f"{prefix}-{number:02d}"
    for prefix in PACK_SPECS
    for number in range(1, 17)
)
TIER_ZERO_ISSUES = ("AC-01", "AC-02", "AC-03", "AC-04", "AC-05")
TIER_ZERO_RECONCILIATIONS = (
    "debit_credit",
    "opening_closing",
    "gl_tb",
    "subledger_gl",
    "bank_gl",
)
AUTHORITY_ORDER = {"machine_draft": 0, "Boundary": 1, "Provisional": 2, "Full": 3}
_SCHEMA_STORE = SchemaStore()


def _digest(value: Mapping[str, Any], hash_field: str) -> str:
    body = {key: child for key, child in value.items() if key != hash_field}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _effective_period(effective_from: str, effective_to: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"from": effective_from, "to": effective_to}
    _validate_effective_period(result, "suite")
    return result


def _validate_effective_period(value: Mapping[str, Any], label: str) -> None:
    try:
        start = date.fromisoformat(str(value["from"]))
        raw_end = value.get("to")
        end = None if raw_end is None else date.fromisoformat(str(raw_end))
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError(f"{label} effective period is invalid") from error
    if end is not None and start > end:
        raise ContractError(f"{label} effective period ends before it starts")


def _issue_seed(row: tuple[str, str, str, str, str]) -> dict[str, Any]:
    issue_id, title, lens, procedure_summary, output = row
    prefix = issue_id[:2]
    spec = PACK_SPECS[prefix]
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_family_id": issue_id,
        "cycle_id": spec["cycle_id"],
        "title": title,
        "review_lens": lens,
        "economic_event_types": list(spec["economic_event_types"]),
        "accounts": list(spec["accounts"]),
        "assertions": [lens],
        "population_definition": spec["population_definition"],
        "mandatory_data_roles": list(spec["mandatory_data_roles"]),
        "optional_data_roles": list(spec["optional_data_roles"]),
        "expectation_card_refs": [f"E-{issue_id}"],
        "norm_card_refs": list(spec["norm_card_refs"]),
        "procedure_card_refs": [*COMMON_PROCEDURE_IDS, ISSUE_PROCEDURE_MAP[issue_id]],
        "counter_hypothesis_refs": [
            "CH-accounting-error",
            "CH-control-override",
            "CH-normal-business",
            "CH-data-mapping",
            "CH-multi-cause",
        ],
        "calculation_refs": [f"CAL-{issue_id}"],
        "cross_domain_trigger_refs": [f"TRIGGER-{prefix}-BOUNDARY"],
        "required_test_case_types": list(EXPECTED_TEST_TYPES),
        "authority_ceiling": "Boundary",
        "not_assessable_conditions": [
            "missing_mandatory_data_role",
            "norm_effective_status_unverified",
            "expert_pack_not_approved",
        ],
        "depth_gate_refs": list(EXPECTED_DEPTH_GATES),
        "depth_gate_status": "not_evaluated",
        "deterministic_procedure_summary": procedure_summary,
        "quantification_output": output,
        "source_design_ref": spec["source_design_ref"],
    }


def _pack_seed(
    prefix: str,
    issues: list[dict[str, Any]],
    period: Mapping[str, Any],
) -> dict[str, Any]:
    spec = PACK_SPECS[prefix]
    body: dict[str, Any] = {
        "pack_id": spec["pack_id"],
        "cycle_id": spec["cycle_id"],
        "source_design_ref": spec["source_design_ref"],
        "issue_family_count": 16,
        "issue_family_ids": [
            issue["issue_family_id"] for issue in issues if issue["issue_family_id"].startswith(prefix)
        ],
        "tier_zero_issue_family_ids": list(TIER_ZERO_ISSUES) if prefix == "AC" else [],
        "procedure_card_refs": list(spec["procedure_card_refs"]),
        "norm_card_refs": list(spec["norm_card_refs"]),
        "authority": "machine_draft",
        "authority_ceiling": "Boundary",
        "effective_period": dict(period),
    }
    return {**body, "content_hash": _digest(body, "content_hash")}


def build_machine_draft_suite(
    *,
    release_id: str,
    effective_from: str,
    effective_to: str | None = None,
) -> dict[str, Any]:
    """Compile the approved design seed without pretending expert promotion."""
    if not isinstance(release_id, str) or not release_id.strip():
        raise ContractError("release_id must be a non-empty string")
    period = _effective_period(effective_from, effective_to)
    issues = [_issue_seed(row) for row in ISSUE_ROWS]
    packs = [_pack_seed(prefix, issues, period) for prefix in PACK_SPECS]
    norm_seeds = [
        {
            "norm_card_id": norm_id,
            "title": title,
            "source_design_ref": norm_source_ref(norm_id),
            "authority": "machine_draft",
            "paragraph_refs": [],
            "effective_status": "unverified",
            "expert_review_status": "not_reviewed",
        }
        for norm_id, title in NORM_SEED_TITLES.items()
    ]
    procedure_seeds = [
        {
            "procedure_card_id": procedure_id,
            "title": title,
            "source_design_ref": procedure_source_ref(procedure_id),
            "authority": "machine_draft",
            "implementation_status": "not_implemented",
            "test_status": "not_tested",
        }
        for procedure_id, title in PROCEDURE_SEED_TITLES.items()
    ]
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": SUITE_ID,
        "release_id": release_id,
        "jurisdiction": "KR",
        "reporting_framework": "K-IFRS",
        "industry_scope": "B2B software, cloud, implementation, training and operations services",
        "effective_period": period,
        "authority": "machine_draft",
        "authority_ceiling": "Boundary",
        "design_refs": list(DESIGN_REFS),
        "packs": packs,
        "issue_families": issues,
        "norm_seeds": norm_seeds,
        "procedure_seeds": procedure_seeds,
        "tier_zero": {
            "mandatory_issue_family_ids": list(TIER_ZERO_ISSUES),
            "required_reconciliations": list(TIER_ZERO_RECONCILIATIONS),
            "omission_allowed": False,
        },
        "expert_approval": {"status": "not_approved", "approval_ref": None},
        "knowledge_release_state": "draft",
    }
    result = {**body, "content_hash": _digest(body, "content_hash")}
    validate_accounting_suite(result)
    return result


def rehash_suite(value: Mapping[str, Any], *, rehash_packs: bool = False) -> dict[str, Any]:
    """Test/tool helper: recompute hashes without weakening semantic validation."""
    result = copy.deepcopy(dict(value))
    if rehash_packs:
        result["packs"] = [
            {**pack, "content_hash": _digest(pack, "content_hash")}
            for pack in result.get("packs", [])
        ]
    result["content_hash"] = _digest(result, "content_hash")
    return result


def _precheck_issue_set(value: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], list[str]]:
    issues = value.get("issue_families")
    if not isinstance(issues, list):
        raise ContractError("issue_families must be a list of exactly 64 records")
    ids = [item.get("issue_family_id") for item in issues if isinstance(item, Mapping)]
    if len(ids) != len(issues):
        raise ContractError("every issue family must be an object with issue_family_id")
    if len(ids) != len(set(ids)):
        raise ContractError("duplicate accounting Issue Family ID")
    actual = set(ids)
    if len(ids) != 64 or actual != EXPECTED_ISSUE_IDS:
        missing = sorted(EXPECTED_ISSUE_IDS - actual)
        extra = sorted(actual - EXPECTED_ISSUE_IDS)
        raise ContractError(f"exactly 64 Issue Families required; missing={missing}; extra={extra}")
    return issues, ids


def validate_accounting_suite(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate closed schemas, seed completeness, references, authority and hashes."""
    if not isinstance(value, Mapping):
        raise ContractError("accounting suite must be an object")
    issues, _ = _precheck_issue_set(value)
    _SCHEMA_STORE.validate("accounting-content-suite.schema.json", value)

    packs = value["packs"]
    for pack in packs:
        if pack["content_hash"] != _digest(pack, "content_hash"):
            raise IntegrityError(f"accounting pack hash mismatch: {pack['pack_id']}")
    if value["content_hash"] != _digest(value, "content_hash"):
        raise IntegrityError("accounting suite hash mismatch")

    if set(value["design_refs"]) != set(DESIGN_REFS) or len(value["design_refs"]) != 9:
        raise ContractError("all nine accounting Suite design references are mandatory")
    _validate_effective_period(value["effective_period"], "suite")

    pack_by_id = {pack["pack_id"]: pack for pack in packs}
    expected_pack_ids = {spec["pack_id"] for spec in PACK_SPECS.values()}
    if len(pack_by_id) != 4 or set(pack_by_id) != expected_pack_ids:
        raise ContractError("exactly four unique accounting Pack groups are required")

    expected_cycle_by_prefix = {prefix: spec["cycle_id"] for prefix, spec in PACK_SPECS.items()}
    issue_by_prefix: dict[str, list[Mapping[str, Any]]] = {prefix: [] for prefix in PACK_SPECS}
    registered_norms = {item["norm_card_id"] for item in value["norm_seeds"]}
    registered_procedures = {item["procedure_card_id"] for item in value["procedure_seeds"]}
    if (
        registered_norms != set(NORM_SEED_TITLES)
        or len(registered_norms) != len(value["norm_seeds"])
    ):
        raise ContractError("Norm seed catalog is missing or contains unknown IDs")
    if (
        registered_procedures != set(PROCEDURE_SEED_TITLES)
        or len(registered_procedures) != len(value["procedure_seeds"])
    ):
        raise ContractError("Procedure seed catalog is missing or contains unknown IDs")

    expected_issue_by_id = {
        expected["issue_family_id"]: expected
        for expected in (_issue_seed(row) for row in ISSUE_ROWS)
    }

    for issue in issues:
        issue_id = issue["issue_family_id"]
        prefix = issue_id[:2]
        issue_by_prefix[prefix].append(issue)
        expected_issue = expected_issue_by_id[issue_id]
        for key, expected_value in expected_issue.items():
            if key != "depth_gate_status" and issue[key] != expected_value:
                raise ContractError(f"{issue_id} differs from its approved design seed: {key}")
        if issue["cycle_id"] != expected_cycle_by_prefix[prefix]:
            raise ContractError(f"{issue_id} is bound to the wrong cycle/pack")
        if issue["depth_gate_refs"] != list(EXPECTED_DEPTH_GATES):
            raise ContractError(f"{issue_id} must connect D1 through D12 in order")
        if set(issue["required_test_case_types"]) != set(EXPECTED_TEST_TYPES):
            raise ContractError(f"{issue_id} is missing a required synthetic test case type")
        if not set(issue["norm_card_refs"]).issubset(registered_norms):
            raise ContractError(f"{issue_id} has an unknown Norm seed reference")
        if not issue["procedure_card_refs"]:
            raise ContractError(f"{issue_id} has no Procedure seed reference")
        if not set(issue["procedure_card_refs"]).issubset(registered_procedures):
            raise ContractError(f"{issue_id} has an unknown Procedure seed reference")
        if not set(COMMON_PROCEDURE_IDS).issubset(issue["procedure_card_refs"]):
            raise ContractError(f"{issue_id} omits a common mandatory Procedure")
        if issue["authority_ceiling"] != "Boundary":
            raise ContractError(f"{issue_id} exceeds its pre-expert Boundary")

    for prefix, spec in PACK_SPECS.items():
        pack = pack_by_id[spec["pack_id"]]
        expected_ids = {item["issue_family_id"] for item in issue_by_prefix[prefix]}
        if pack["issue_family_count"] != 16 or set(pack["issue_family_ids"]) != expected_ids:
            raise ContractError(f"{pack['pack_id']} does not bind all 16 Issue Families")
        if pack["cycle_id"] != spec["cycle_id"]:
            raise ContractError(f"{pack['pack_id']} cycle binding mismatch")
        if pack["source_design_ref"] != spec["source_design_ref"]:
            raise ContractError(f"{pack['pack_id']} design source binding mismatch")
        expected_tier_zero = list(TIER_ZERO_ISSUES) if prefix == "AC" else []
        if pack["tier_zero_issue_family_ids"] != expected_tier_zero:
            raise ContractError(f"{pack['pack_id']} Tier 0 binding mismatch")
        if set(pack["norm_card_refs"]) != set(spec["norm_card_refs"]):
            raise ContractError(f"{pack['pack_id']} Norm seed binding mismatch")
        if set(pack["procedure_card_refs"]) != set(spec["procedure_card_refs"]):
            raise ContractError(f"{pack['pack_id']} Procedure seed binding mismatch")
        _validate_effective_period(pack["effective_period"], pack["pack_id"])
        if pack["effective_period"] != value["effective_period"]:
            raise ContractError(f"{pack['pack_id']} effective period differs from Suite")
        if pack["authority"] not in AUTHORITY_ORDER:
            raise ContractError(f"{pack['pack_id']} authority is unknown")
        if AUTHORITY_ORDER[pack["authority"]] > AUTHORITY_ORDER[value["authority"]]:
            raise ContractError(f"{pack['pack_id']} authority exceeds Suite authority")

    tier_zero = value["tier_zero"]
    if tier_zero["mandatory_issue_family_ids"] != list(TIER_ZERO_ISSUES):
        raise ContractError("Tier 0 must require AC-01 through AC-05")
    if set(tier_zero["required_reconciliations"]) != set(TIER_ZERO_RECONCILIATIONS):
        raise ContractError("Tier 0 reconciliation contract is incomplete")
    if tier_zero["omission_allowed"] is not False:
        raise ContractError("Tier 0 omission is forbidden")

    authority = value["authority"]
    if authority in {"Provisional", "Full"}:
        approval = value["expert_approval"]
        if approval["status"] != "approved" or not approval["approval_ref"]:
            raise ContractError("expert approval is required for Provisional or Full authority")

    for seed in value["norm_seeds"]:
        norm_id = seed["norm_card_id"]
        if seed["title"] != NORM_SEED_TITLES[norm_id]:
            raise ContractError(f"{norm_id} differs from its approved Norm seed title")
        if seed["source_design_ref"] != norm_source_ref(norm_id):
            raise ContractError(f"{norm_id} differs from its approved Norm design source")
        if seed["effective_status"] == "verified" and not seed["paragraph_refs"]:
            raise ContractError(f"{norm_id} verified status requires paragraph refs")
    for seed in value["procedure_seeds"]:
        procedure_id = seed["procedure_card_id"]
        if seed["title"] != PROCEDURE_SEED_TITLES[procedure_id]:
            raise ContractError(f"{procedure_id} differs from its approved Procedure seed title")
        if seed["source_design_ref"] != procedure_source_ref(procedure_id):
            raise ContractError(f"{procedure_id} differs from its approved Procedure design source")

    if authority in {"Boundary", "Provisional", "Full"}:
        if any(pack["authority"] != authority for pack in packs):
            raise ContractError("all Pack authority labels must match promoted Suite authority")
        if any(seed["authority"] != authority for seed in value["norm_seeds"]):
            raise ContractError("all Norm authority labels must match promoted Suite authority")
        if any(seed["authority"] != authority for seed in value["procedure_seeds"]):
            raise ContractError("all Procedure authority labels must match promoted Suite authority")
        if value["knowledge_release_state"] != "released":
            raise ContractError("approved Knowledge Release is required for promotion")
        if any(
            not item["paragraph_refs"]
            or item["effective_status"] != "verified"
            for item in value["norm_seeds"]
        ):
            raise ContractError("official Norm grounding is required")
        if any(
            item["implementation_status"] != "implemented"
            or item["test_status"] != "passed"
            for item in value["procedure_seeds"]
        ):
            raise ContractError("deterministic Procedure implementation and tests are required")
        if any(item["depth_gate_status"] != "passed" for item in issues):
            raise ContractError("D1-D12 Depth Gates must pass before promotion")
    if authority in {"Provisional", "Full"} and any(
        item["expert_review_status"] != "approved" for item in value["norm_seeds"]
    ):
        raise ContractError("expert-reviewed Norm seeds are required for Provisional or Full")
    if authority == "Full":
        raise ContractError("initial Suite cannot authorize company-wide Full accounting scope")

    return copy.deepcopy(dict(value))


def assess_suite_readiness(
    value: Mapping[str, Any],
    *,
    execution_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    suite = validate_accounting_suite(value)
    blockers: set[str] = set()
    if any(
        not seed["paragraph_refs"]
        or seed["effective_status"] != "verified"
        or seed["expert_review_status"] != "approved"
        for seed in suite["norm_seeds"]
    ):
        blockers.add("norm_grounding_unverified")
    procedure_execution_complete = False
    if execution_evidence is not None:
        from trusted_ceo_agent.accounting.execution import (
            verify_accounting_execution_manifest,
        )

        evidence = verify_accounting_execution_manifest(execution_evidence)
        if (
            evidence["suite_id"] != suite["suite_id"]
            or evidence["release_id"] != suite["release_id"]
            or evidence["suite_hash"] != suite["content_hash"]
        ):
            raise ContractError("accounting execution evidence does not bind to Suite")
        procedure_execution_complete = evidence["coverage_complete"]
    if not procedure_execution_complete and any(
        seed["implementation_status"] != "implemented" or seed["test_status"] != "passed"
        for seed in suite["procedure_seeds"]
    ):
        blockers.add("procedure_implementation_incomplete")
    if any(issue["depth_gate_status"] != "passed" for issue in suite["issue_families"]):
        blockers.add("depth_gate_incomplete")
    if suite["expert_approval"]["status"] != "approved":
        blockers.add("expert_review_required")
    if suite["knowledge_release_state"] != "released":
        blockers.add("knowledge_release_not_released")
    ordered = sorted(blockers)
    activation = not ordered and suite["authority"] in {"Provisional", "Full"}
    return {
        "blocker_codes": ordered,
        "analysis_plane_activation_allowed": activation,
        "senior_accountant_claim_allowed": activation,
        "maximum_current_authority": suite["authority"],
    }


def assert_product_claim_allowed(
    value: Mapping[str, Any],
    claim: str,
    *,
    execution_evidence: Mapping[str, Any] | None = None,
) -> str:
    suite = validate_accounting_suite(value)
    if claim == "machine_draft":
        return claim
    if claim == "accounting_core_screened":
        if execution_evidence is None:
            raise ContractError("Tier 0 execution evidence is required for accounting_core_screened")
        from trusted_ceo_agent.accounting.core_procedures import (
            assert_accounting_core_screened,
        )

        return assert_accounting_core_screened(execution_evidence)
    if claim == "three_cycles_boundary":
        if suite["authority"] != "Boundary":
            raise ContractError("three_cycles_boundary requires implemented Boundary Packs")
        return claim
    if claim == "senior_accountant_draft_scope":
        if not assess_suite_readiness(suite)["senior_accountant_claim_allowed"]:
            raise ContractError("senior accountant claim requires expert-reviewed Knowledge Release")
        return claim
    if claim == "company_wide_accounting_full":
        raise ContractError("company-wide/company_wide Full requires all material Account Families")
    raise ContractError(f"unknown accounting product claim: {claim}")
