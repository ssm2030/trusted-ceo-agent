from __future__ import annotations

from trusted_ceo_agent.knowledge.foundry import (
    build_feedback_preview,
    build_patch_proposal,
    build_regression_case,
    build_release_candidate,
    submit_feedback,
)
from trusted_ceo_agent.knowledge.release import (
    build_initial_release,
    build_knowledge_approval_request,
    record_knowledge_approval,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
T0 = "2026-07-17T00:00:00Z"
T1 = "2026-07-17T00:05:00Z"
T2 = "2026-07-17T01:00:00Z"


def structured_content(**overrides):
    value = {
        "facts": ["The signed acceptance date is after period end."],
        "criteria": ["Recognition requires completed acceptance."],
        "conclusions": ["Recognition before acceptance is unsupported."],
        "counter_evidence": ["No pre-period acceptance evidence was found."],
        "uncertainties": ["A separately archived acceptance may exist."],
        "verification_steps": ["Inspect the signed acceptance archive."],
    }
    value.update(overrides)
    return value


def privacy(*, tenant_id="tenant_alpha", **overrides):
    value = {
        "tenant_id": tenant_id,
        "contains_personal_data": False,
        "contains_confidential_data": True,
        "retention_class": "foundry_90_days",
        "evaluation_reuse_consent": False,
        "deidentification_status": "deidentified",
        "source_copy_allowed": False,
    }
    value.update(overrides)
    return value


def make_preview(*, tenant_id="tenant_alpha", content=None, privacy_value=None):
    return build_feedback_preview(
        source_type="field_feedback",
        run_id="run_001",
        run_revision=7,
        knowledge_release_id="knowledge_release_seed",
        issue_id="issue_001",
        issue_family_id="AC-REV-01",
        fact_refs=["fact_001"],
        signal_refs=["signal_001"],
        evidence_refs=["evidence_001"],
        feedback_type="false_negative",
        structured_content=content or structured_content(),
        requested_outcome="add a deterministic acceptance check",
        submitter_id="user_001",
        authenticated_role="business_owner",
        domain_credential_ref=None,
        trust_state="unverified_feedback",
        independence_flags=[],
        conflict_of_interest_flags=[],
        privacy=privacy_value or privacy(tenant_id=tenant_id),
    )


def approve_object(
    value,
    *,
    id_field,
    hash_field,
    stage,
    action,
    role,
    actor,
    expected_revision,
    nonce=None,
    requested_at=T0,
    expires_at=T2,
    approved_at=T1,
):
    secret = nonce or f"nonce-{stage}-{role}-{actor}"
    request = build_knowledge_approval_request(
        approval_stage=stage,
        object_id=value[id_field],
        object_hash=value[hash_field],
        expected_revision=expected_revision,
        requested_action=action,
        requested_by="maintainer_001",
        required_role=role,
        requested_at=requested_at,
        expires_at=expires_at,
        nonce=secret,
    )
    approval = record_knowledge_approval(
        request,
        object_id=value[id_field],
        object_hash=value[hash_field],
        current_revision=expected_revision,
        approved_by=actor,
        approver_role=role,
        nonce=secret,
        approved_at=approved_at,
    )
    return request, approval


def make_feedback(*, tenant_id="tenant_alpha"):
    preview = make_preview(tenant_id=tenant_id)
    request, approval = approve_object(
        preview,
        id_field="preview_id",
        hash_field="preview_hash",
        stage="feedback_submit",
        action="submit_feedback",
        role="feedback_submitter",
        actor="user_001",
        expected_revision=1,
    )
    feedback, receipt = submit_feedback(
        preview,
        approval,
        current_revision=1,
        submitted_at=T1,
    )
    return preview, request, approval, feedback, receipt


def make_regression(feedback):
    return build_regression_case(
        source_feedback_refs=[{
            "feedback_id": feedback["feedback_id"],
            "feedback_hash": feedback["feedback_hash"],
        }],
        fixture_kind="synthetic",
        fixture_ref="fixtures/revenue_acceptance.json",
        fixture_hash=HASH_C,
        consent_ref=None,
        expected=structured_content(),
        negative_control_refs=["case_normal_001"],
        counterexample_refs=["case_counter_001"],
        created_at=T1,
    )


def reproduction(*, result="reproduced"):
    return {
        "run_id": "run_001",
        "run_revision": 7,
        "knowledge_release_id": "knowledge_release_seed",
        "prompt_hash": HASH_A,
        "pack_hash": HASH_B,
        "component_hash": HASH_C,
        "result": result,
    }


def make_patch(*, tenant_id="tenant_alpha", reproduction_result="reproduced"):
    _, _, _, feedback, _ = make_feedback(tenant_id=tenant_id)
    regression = make_regression(feedback)
    patch = build_patch_proposal(
        feedback_records=[feedback],
        reproduction=reproduction(result=reproduction_result),
        failure_type="procedure",
        root_cause="The acceptance procedure omitted the signed-date check.",
        target_artifacts=[{
            "artifact_ref": "procedure/revenue_acceptance@1",
            "artifact_hash": HASH_D,
            "artifact_type": "procedure",
        }],
        before_semantics=structured_content(
            criteria=["Invoice issuance was treated as sufficient."],
        ),
        after_semantics=structured_content(),
        source_refs=["official_standard_001"],
        affected_issue_family_ids=["AC-REV-01"],
        affected_domains=["accounting"],
        risk_classification="high",
        regression_cases=[regression],
        expected_behavior_changes=["Flag pre-acceptance recognition."],
        forbidden_side_effects=["Do not alter accepted transactions."],
        rollback_conditions=["Target regression escapes production."],
        required_stage2_roles=["domain_expert", "maintainer"],
        created_at=T1,
    )
    return feedback, regression, patch


def make_initial_release():
    return build_initial_release(
        release_sequence=1,
        artifact_manifest=[{
            "artifact_ref": "procedure/revenue_acceptance@1",
            "artifact_hash": HASH_D,
            "artifact_type": "procedure",
        }],
        deployed_at=T0,
    )


def all_green_gates(**overrides):
    value = {
        "target_regression_passed": True,
        "full_regression_passed": True,
        "coverage_non_inferior": True,
        "security_passed": True,
        "determinism_passed": True,
        "performance_passed": True,
        "norm_effective": True,
        "jurisdiction_valid": True,
    }
    value.update(overrides)
    return value


def make_candidate(*, gates=None, stage2_actor_prefix="reviewer"):
    _, regression, patch = make_patch()
    approvals = []
    requests = []
    for role in patch["required_stage2_roles"]:
        request, approval = approve_object(
            patch,
            id_field="patch_id",
            hash_field="patch_hash",
            stage="patch_approve",
            action="approve_patch",
            role=role,
            actor=f"{stage2_actor_prefix}_{role}",
            expected_revision=3,
        )
        requests.append(request)
        approvals.append(approval)
    base = make_initial_release()
    candidate = build_release_candidate(
        base_release=base,
        patches=[patch],
        regression_cases=[regression],
        stage2_approvals=approvals,
        expected_revision=3,
        artifact_manifest=[{
            "artifact_ref": "procedure/revenue_acceptance@2",
            "artifact_hash": HASH_A,
            "artifact_type": "procedure",
        }],
        gate_results=gates or all_green_gates(),
        coverage_exception_approval_ref=None,
        rollback_release_id=base["release_id"],
        rollback_release_hash=base["release_hash"],
        created_at=T1,
    )
    return base, regression, patch, requests, approvals, candidate


def make_stage3(candidate, *, actor="release_admin", expected_revision=4):
    return approve_object(
        candidate,
        id_field="candidate_id",
        hash_field="candidate_hash",
        stage="release_deploy",
        action="deploy_release",
        role="release_manager",
        actor=actor,
        expected_revision=expected_revision,
    )
