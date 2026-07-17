from __future__ import annotations

import copy
import hashlib
import unittest

from tests.integrator_support import (
    EVENT_ID,
    FACT_ID,
    REVISION,
    RUN_ID,
    finding_spec,
)
from trusted_ceo_agent.analysis.findings import (
    build_finding,
    build_finding_relation,
    build_issue_cluster,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.workflow.completion import assess_completion


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _grading_input(issue_id: str, evidence_ref: str) -> dict:
    return {
        "issue_id": issue_id,
        "assessability": "assessable",
        "not_assessable_reason_codes": [],
        "evidence_state": "sufficient",
        "impact_band": "high",
        "urgency_band": "near_term",
        "mission_priority_match": True,
        "executive_materiality": True,
        "decision_needed": True,
        "expert_trigger_state": "none",
        "pack_authority": "provisional",
        "diagnostic_disposition": "accepted",
        "verification_authorized": True,
        "issue_disposition": "standalone",
        "trackable": True,
        "response_eligibility": "eligible",
        "provenance_refs": [evidence_ref],
    }


def _completion(
    findings: list[dict],
    *,
    revision: int = REVISION,
    run_id: str = RUN_ID,
) -> dict:
    return assess_completion({
        "run_id": run_id,
        "revision": revision,
        "signal_cases": [],
        "work_items": [],
        "domain_routes": [],
        "findings": findings,
        "integrity_failure_refs": [],
        "contract_failure_refs": [],
        "stale_revision_refs": [],
        "coverage_gaps": [],
        "expert_review_refs": [],
        "blind_spot_refs": [],
        "cross_finding_join_complete": True,
        "cross_domain_integrator_complete": True,
        "duplicate_merge_complete": True,
        "conflicts_disclosed": True,
        "coverage_complete": True,
        "final_validator_passed": True,
        "tty_final_approval_ready": True,
        "limited_basis": "none",
        "user_confirmed_limitations": False,
    })


def _fixture(*, run_id: str = RUN_ID) -> dict:
    grading_inputs = []
    grade_records = []
    findings = []
    for suffix, domain in (("2", "accounting"), ("3", "tax")):
        case_id = "case_" + suffix * 24
        evidence_ref = "evidence_" + suffix * 24
        grading_input = _grading_input(case_id, evidence_ref)
        grade_record = grade(grading_input)
        spec = finding_spec(suffix, domain)
        spec["run_id"] = run_id
        spec["grade"]["grade_record_ref"] = grade_record["grade_record_id"]
        grading_inputs.append(grading_input)
        grade_records.append(grade_record)
        findings.append(build_finding(spec))

    relation = build_finding_relation({
        "run_id": run_id,
        "revision": REVISION,
        "source_finding_id": findings[0]["finding_id"],
        "target_finding_id": findings[1]["finding_id"],
        "relation_type": "contradicts",
        "evidence_refs": ["evidence_" + "4" * 24],
        "confidence_status": "verified",
        "contradicting_evidence_refs": ["evidence_" + "5" * 24],
    }, findings)
    cluster = build_issue_cluster({
        "run_id": run_id,
        "revision": REVISION,
        "finding_ids": [item["finding_id"] for item in findings],
        "relation_ids": [relation["relation_id"]],
        "decision_unit": {
            "title": "Resolve the verified accounting and tax conflict",
            "decision_required": True,
            "owner_role": "ceo",
            "option_refs": ["option_a", "option_b"],
        },
        "unresolved_conflicts": ["treatment_conflict"],
    }, findings=findings, relations=[relation])
    evidence_body = {
        "run_id": run_id,
        "revision": REVISION,
        "fact_refs": [FACT_ID],
        "signal_refs": ["signal_" + "2" * 24, "signal_" + "3" * 24],
        "evidence_link_refs": [
            "evidence_" + suffix * 24 for suffix in ("2", "3", "4", "5")
        ],
        "source_refs": ["source_" + "2" * 24, "source_" + "3" * 24],
    }
    evidence_index = {**evidence_body, "content_hash": _digest(evidence_body)}
    return {
        "expected_run_id": RUN_ID,
        "expected_revision": REVISION,
        "findings": findings,
        "relations": [relation],
        "clusters": [cluster],
        "completion": _completion(findings, run_id=run_id),
        "grading_inputs": grading_inputs,
        "grade_records": grade_records,
        "evidence_index": evidence_index,
        "expected_evidence_index_hash": evidence_index["content_hash"],
    }


class ProfessionalPublicationTests(unittest.TestCase):
    def _api(self):
        try:
            from trusted_ceo_agent.outputs.professional_publication import (
                build_professional_publication,
            )
        except ModuleNotFoundError:
            self.fail("professional publication adapter is missing")
        return build_professional_publication

    def test_projects_only_verified_engine_owned_values_deterministically(self) -> None:
        build = self._api()
        inputs = _fixture()

        first = build(**inputs)
        reversed_inputs = copy.deepcopy(inputs)
        for key in ("findings", "grade_records", "grading_inputs"):
            reversed_inputs[key].reverse()
        second = build(**reversed_inputs)

        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        issues = first["structured_output"]["issues"]
        self.assertEqual(
            [item["case_id"] for item in sorted(inputs["findings"], key=lambda x: x["case_id"])],
            [item["issue_id"] for item in issues],
        )
        by_issue = {item["issue_id"]: item for item in issues}
        grades = {item["issue_id"]: item for item in inputs["grade_records"]}
        for finding in inputs["findings"]:
            issue = by_issue[finding["case_id"]]
            self.assertEqual(finding["conclusion"]["statement"], issue["title_template"])
            self.assertEqual(finding["fact_refs"], issue["value_refs"])
            self.assertEqual(finding["evidence_link_refs"], issue["evidence_link_ids"])
            self.assertEqual(
                grades[finding["case_id"]]["primary_grade"],
                issue["primary_grade"],
            )
        edge = first["structured_output"]["cross_issue_relations"][0]
        self.assertEqual(inputs["relations"][0]["relation_id"], edge["relation_id"])
        self.assertEqual(inputs["findings"][0]["case_id"], edge["from_issue_ref"])
        self.assertEqual(inputs["findings"][1]["case_id"], edge["to_issue_ref"])

    def test_missing_stale_or_mismatched_inputs_fail_closed(self) -> None:
        build = self._api()
        valid = _fixture()
        mutations = []

        missing_grade = copy.deepcopy(valid)
        missing_grade["grade_records"].pop()
        mutations.append(("Grade Record", missing_grade))

        forged_grade = copy.deepcopy(valid)
        forged_grade["grade_records"][0]["primary_grade"] = "Monitor"
        mutations.append(("Grade Record", forged_grade))

        stale_completion = copy.deepcopy(valid)
        stale_completion["completion"] = _completion(
            stale_completion["findings"], revision=REVISION + 1
        )
        mutations.append(("revision", stale_completion))

        wrong_hash = copy.deepcopy(valid)
        wrong_hash["expected_evidence_index_hash"] = "0" * 64
        mutations.append(("hash", wrong_hash))

        for expected, inputs in mutations:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(IntegrityError, expected):
                    build(**inputs)


if __name__ == "__main__":
    unittest.main()
