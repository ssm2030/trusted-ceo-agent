from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


class KeylessFakeReasoningGateway:
    """Deterministic schema-valid stand-in used only by tests and demo E2E."""

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve()
        self.schemas = SchemaStore()
        self.calls: list[dict[str, str]] = []

    def execute(self, job: Mapping[str, Any]) -> dict[str, Any]:
        stage = str(job.get("stage", ""))
        job_id = str(job.get("job_id", ""))
        self.calls.append({"stage": stage, "job_id": job_id})
        files = self._files(job)
        builders = {
            "schema_mapping": self._schema_mapping,
            "lens": self._lens,
            "integrated": self._integrated,
            "deep_dive": self._deep_dive,
            "writer": self._writer,
        }
        builder = builders.get(stage)
        if builder is None:
            raise ContractError(f"fake gateway does not support stage: {stage}")
        result = builder(job, files)
        schema_ref = job.get("output_schema_ref")
        if not isinstance(schema_ref, str):
            raise ContractError("fake gateway job is missing output_schema_ref")
        self.schemas.validate(schema_ref, result)
        return result

    def _files(self, job: Mapping[str, Any]) -> dict[str, bytes]:
        artifact_ref = job.get("artifact_ref")
        if not isinstance(artifact_ref, str) or "@r" not in artifact_ref:
            raise ContractError("fake gateway artifact_ref is invalid")
        run_id, suffix = artifact_ref.split("@r", 1)
        revision_text = suffix.split(":", 1)[0]
        try:
            revision = int(revision_text)
        except ValueError as error:
            raise ContractError("fake gateway artifact revision is invalid") from error
        store = ArtifactStore(self.artifact_root)
        store.open_run(run_id)
        snapshot = store.verify_revision(revision)
        manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
        return {
            item["path"]: (snapshot / item["path"]).read_bytes()
            for item in manifest["files"]
        }

    @staticmethod
    def _schema_mapping(
        _job: Mapping[str, Any],
        files: Mapping[str, bytes],
    ) -> dict[str, Any]:
        value = strict_loads(files["intake/canonical-mapping-proposal.json"])
        if not isinstance(value, dict):
            raise IntegrityError("canonical mapping proposal is invalid")
        return value

    @staticmethod
    def _lens(job: Mapping[str, Any], _files: Mapping[str, bytes]) -> dict[str, Any]:
        facts = list(job.get("allowed_fact_ids", []))
        if not facts:
            raise ContractError("fake lens requires an allowed fact")
        evidence_ref = str(facts[0])
        signals = [str(value) for value in job.get("required_signal_ids", [])]
        families = [str(value) for value in job.get("allowed_problem_family_refs", [])]
        if not families:
            raise ContractError("fake lens requires an allowed problem family")
        family_ref = (
            "profitability_erosion"
            if "profitability_erosion" in families
            else families[0]
        )
        return {
            "assessment_status": "partial",
            "status_reason_codes": ["counter_hypothesis_pending"],
            "observations": [{
                "local_key": "observation_material_movement",
                "statement_template": "A material movement is present in approved evidence.",
                "value_refs": [],
                "fact_ids": [evidence_ref],
                "signal_ids": signals,
            }],
            "business_meanings": [{
                "local_key": "meaning_executive_attention",
                "statement_template": "The movement warrants bounded executive review.",
                "value_refs": [],
                "evidence_proposals": [{
                    "evidence_ref": evidence_ref,
                    "polarity": "supports",
                    "role": "observation",
                }],
                "observation_local_keys": ["observation_material_movement"],
            }],
            "problem_candidates": [{
                "local_key": "problem_material_movement",
                "business_meaning_local_keys": ["meaning_executive_attention"],
                "problem_family_ref": family_ref,
                "statement_template": "The material movement requires verification.",
                "value_refs": [],
                "evidence_proposals": [{
                    "evidence_ref": evidence_ref,
                    "polarity": "supports",
                    "role": "observation",
                }],
            }],
            "cause_hypotheses": [],
            "counter_hypotheses": [],
            "challenge_reviews": [],
            "verification_tests": [],
            "signal_dispositions": [{
                "signal_id": signal_id,
                "disposition": "used_support",
                "target_local_keys": ["problem_material_movement"],
                "duplicate_of_signal_id": None,
                "context_evidence_ids": [],
                "rationale_template": "The signal supports bounded review.",
            } for signal_id in signals],
            "uncertainties": [],
            "data_requests": [],
            "human_questions": [],
            "expert_trigger_candidates": [],
            "limitations": [{
                "local_key": "limitation_cause_unverified",
                "statement_template": "The leading cause is not yet independently verified.",
            }],
        }

    @staticmethod
    def _integrated(
        job: Mapping[str, Any],
        files: Mapping[str, bytes],
    ) -> dict[str, Any]:
        joined = strict_loads(files["reasoning/join-result.json"])
        claims = sorted(
            item["claim_id"]
            for path, payload in files.items()
            if path.startswith("tasks/") and path.endswith("/card.json")
            for item in strict_loads(payload)["normalized_payload"]["problem_candidates"]
        )
        facts = [str(value) for value in job.get("allowed_fact_ids", [])]
        families = [str(value) for value in job.get("allowed_problem_family_refs", [])]
        units = [str(value) for value in job.get("allowed_decision_unit_refs", [])]
        decisions = [str(value) for value in job.get("allowed_decision_type_refs", [])]
        if not claims or not facts or not families or not units:
            raise ContractError("fake integrated stage lacks required allowlisted references")
        family_ref = (
            "profitability_erosion"
            if "profitability_erosion" in families
            else families[0]
        )
        decision = None
        if decisions:
            decision = {
                "decision_type_ref": decisions[0],
                "decision_unit_ref": units[0],
                "basis_claim_refs": [claims[0]],
                "rationale_template": "The accepted issue may require an executive decision.",
            }
        return {
            "join_manifest_ref": job["join_manifest_ref"],
            "card_refs": joined["card_refs"],
            "issue_clusters": [],
            "integrated_issues": [{
                "local_key": "issue_material_movement",
                "payload": {
                    "problem_family_ref": family_ref,
                    "scope_key": "enterprise",
                    "decision_unit_ref": units[0],
                    "source_candidate_ids": [claims[0]],
                    "observation_claim_refs": [],
                    "cause_hypothesis_refs": [],
                    "counter_hypothesis_refs": [],
                    "unresolved_conflict_refs": [],
                    "impact_evidence_refs": [facts[0]],
                    "urgency_evidence_refs": [],
                    "counter_evidence_refs": [],
                    "decision_need_proposal": decision,
                    "verification_requirement_refs": [],
                    "response_type_refs": [],
                    "expert_trigger_refs": [],
                },
            }],
            "causal_relation_hypotheses": [],
            "cross_issue_conflicts": [],
            "blind_spots": [],
            "response_type_candidates": [],
            "expert_review_candidates": [],
        }

    @staticmethod
    def _deep_dive(
        job: Mapping[str, Any],
        _files: Mapping[str, bytes],
    ) -> dict[str, Any]:
        return {
            "approved_scope_ref": job["approved_scope_ref"],
            "component_run_refs": list(job["component_run_refs"]),
            "updated_cause_hypotheses": [],
            "updated_counter_hypotheses": [],
            "distinguishing_test_results": [],
            "conditional_response_candidates": [],
            "expert_review_candidates": [],
            "remaining_uncertainties": [],
            "additional_data_requests": [],
        }

    @staticmethod
    def _writer(job: Mapping[str, Any], _files: Mapping[str, bytes]) -> dict[str, Any]:
        claim_ids = [str(value) for value in job.get("allowed_claim_ids", [])]
        return {
            "structured_output_ref": job["structured_output_ref"],
            "claim_templates": [{
                "claim_id": claim_id,
                "template": "Approved evidence supports a bounded executive review.",
            } for claim_id in claim_ids],
            "expert_packet_templates": [],
            "ceo_brief_section_order": [],
        }
