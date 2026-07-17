from __future__ import annotations

from typing import Any

from trusted_ceo_agent.knowledge.compiler import (
    REQUIRED_ORACLE_CASE_TYPES,
    compile_card,
    compile_issue_family,
    depth_slot,
)


def make_knowledge_bundle(
    *,
    trust_level: str = "full",
    pack_authority: str = "full",
    source_approved: bool = True,
    source_hash: str = "a" * 64,
    verified_hash: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    source = {
        "source_id": "KIFRS-TEST",
        "source_type": "official_primary",
        "retrieval": "remote",
        "locator": "K-IFRS/test/1",
        "source_hash": source_hash,
        "verified_hash": verified_hash or source_hash,
        "approved": source_approved,
    }
    common = {
        "domain": "accounting",
        "issue_family_id": "AC-TEST",
        "version": 1,
        "status": "active",
        "trust_level": trust_level,
        "jurisdiction": "KR",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "source_refs": [source],
        "author": "knowledge_author",
        "reviewer_refs": ["reviewer_accounting"],
        "created_at": "2026-01-01T00:00:00Z",
        "supersedes": None,
        "test_refs": list(REQUIRED_ORACLE_CASE_TYPES),
    }
    method = compile_card(
        artifact_type="method_card",
        content={
            "review_sequence": ["define population", "test assertions"],
            "required_questions": ["is the population complete?"],
            "scope_conditions": ["B2B service accounting"],
        },
        **common,
    )
    norm = compile_card(
        artifact_type="norm_card",
        content={
            "atomic_claim": "Apply the effective requirement to the scoped event.",
            "requirements": ["recognize only when criteria are met"],
            "exceptions": ["explicit standard exception"],
            "options": [],
            "conflicts": [],
            "paragraph_locator": "K-IFRS/test/1",
        },
        **common,
    )
    expectation = compile_card(
        artifact_type="expectation_card",
        content={
            "relationship": "supported events reconcile to recorded amounts",
            "metrics": ["count", "amount", "period"],
            "exclusion_conditions": ["approved out-of-scope event"],
        },
        **common,
    )
    procedure = compile_card(
        artifact_type="procedure_card",
        content={
            "inputs": ["fact population", "evidence roles"],
            "population": "all scoped economic events",
            "calculations": ["reconcile count and amount"],
            "decision_conditions": ["difference equals zero"],
            "failure_states": ["missing evidence", "not assessable"],
            "required_evidence_roles": ["ledger", "source document"],
        },
        **common,
    )
    counter = compile_card(
        artifact_type="counter_hypothesis_card",
        content={
            "hypothesis": "recorded amount is erroneous",
            "alternative_explanation": "timing or mapping explains the signal",
            "counter_evidence_roles": ["subsequent event", "mapping table"],
            "distinguishing_procedure_refs": [procedure["artifact_id"]],
        },
        **common,
    )
    trigger = compile_card(
        artifact_type="cross_domain_trigger_card",
        content={
            "target_domain": "tax",
            "conditions": ["tax treatment may differ"],
            "shared_fact_refs": ["economic_event_ref"],
            "forbidden_conclusions": ["do not conclude tax liability"],
            "conflict_states": ["accounting_tax_conflict"],
        },
        **common,
    )
    cards = [method, norm, expectation, procedure, counter, trigger]
    slots = {
        "D1": depth_slot("D1", [method]),
        "D2": depth_slot("D2", [expectation]),
        "D3": depth_slot("D3", [expectation]),
        "D4": depth_slot("D4", [counter]),
        "D5": depth_slot("D5", [norm]),
        "D6": depth_slot("D6", [procedure]),
        "D7": depth_slot("D7", [procedure, counter]),
        "D8": depth_slot("D8", [procedure]),
        "D9": depth_slot("D9", [method]),
        "D10": depth_slot("D10", [trigger]),
        "D11": depth_slot("D11", [norm]),
        "D12": depth_slot("D12", [procedure, counter]),
    }
    family = compile_issue_family(
        issue_family_id="AC-TEST",
        domain="accounting",
        industry_scope="b2b_services",
        jurisdiction="KR",
        effective_from="2026-01-01",
        effective_to="2026-12-31",
        risk_level="standard",
        pack_id="accounting-test-pack",
        pack_version="1.0.0",
        pack_hash="b" * 64,
        pack_authority=pack_authority,
        depth_slots=slots,
        required_test_case_types=REQUIRED_ORACLE_CASE_TYPES,
        not_assessable_conditions=["mandatory evidence unavailable"],
    )
    expert = {
        "approved": True,
        "issue_family_id": "AC-TEST",
        "domain": "accounting",
        "jurisdiction": "KR",
        "reviewer_id": "cpa_1",
        "reviewer_role": "accounting_domain_expert",
        "independent_second_review": False,
    }
    release = {
        "release_id": "knowledge-release-test",
        "release_hash": "c" * 64,
        "status": "active",
        "quality_gate_passed": True,
        "release_manager_approved": True,
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "artifact_hashes": sorted({card["content_hash"] for card in cards}),
    }
    return family, cards, expert, release
