from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


def _api():
    from trusted_ceo_agent.analysis.findings import (
        build_finding,
        build_finding_relation,
        build_issue_cluster,
        validate_finding_graph,
        validate_finding_records,
    )

    return (
        build_finding,
        build_finding_relation,
        build_issue_cluster,
        validate_finding_graph,
        validate_finding_records,
    )


def _spec(*, revision: int = 7, case_suffix: str = "a") -> dict:
    return {
        "run_id": "run_findings",
        "revision": revision,
        "case_id": "case_" + case_suffix * 24,
        "event_id": f"event_{case_suffix}",
        "signal_ids": ["signal_" + case_suffix * 24],
        "domain_assessment_refs": [f"assessment_{case_suffix}"],
        "issue_family_refs": ["AC-01"],
        "fact_refs": ["fact_" + case_suffix * 24],
        "evidence_link_refs": ["evidence_" + case_suffix * 24],
        "source_refs": ["source_" + case_suffix * 24],
        "procedure_result_refs": [f"procedure_result_{case_suffix}"],
        "norm_refs": [f"norm_{case_suffix}"],
        "calculation_refs": [f"calculation_{case_suffix}"],
        "hypotheses": ["The scoped issue is supported."],
        "counter_hypotheses": ["The pattern is a timing-only difference."],
        "supporting_evidence_refs": ["evidence_" + case_suffix * 24],
        "contradicting_evidence_refs": [],
        "unresolved_conflicts": [],
        "disposition": "substantiated",
        "conclusion": {
            "statement": "The issue is supported within the tested scope.",
            "scope": "The frozen evidence packet.",
            "basis_refs": [f"procedure_result_{case_suffix}"],
            "qualifier": "supported_within_current_scope",
        },
        "conclusion_strength": "supported",
        "impact_dimensions": {
            "amount": "material",
            "cash": "possible",
            "legal": "not_assessed",
            "tax": "not_assessed",
            "human": "not_assessed",
            "operations": "possible",
            "control": "material",
        },
        "coverage": {
            "required_procedures_complete": True,
            "counter_evidence_complete": True,
            "evidence_coverage_complete": True,
            "missing_evidence_refs": [],
            "missing_procedure_refs": [],
            "scope_note": "Frozen packet only.",
        },
        "data_gaps": [],
        "expert_review": {
            "required": False,
            "packet_ref": None,
            "decision_boundary": None,
            "owner": None,
        },
        "grade": {"status": "published", "grade_record_ref": f"grade_record_{case_suffix}"},
        "authority": {
            "effective_level": "Provisional",
            "pack_release_refs": ["pack_release_001"],
            "approval_refs": [],
        },
        "uncertainty": {"status": "partial", "reason_codes": ["sample_scope"]},
        "verification": {
            "required_procedure_refs": [f"procedure_{case_suffix}"],
            "completed_procedure_refs": [f"procedure_{case_suffix}"],
            "counter_evidence_checked": True,
            "counter_evidence_refs": ["evidence_" + "c" * 24],
            "verification_step_refs": [f"verification_{case_suffix}"],
        },
        "related_finding_ids": [],
        "supersedes_finding_id": None,
    }


class FindingTests(unittest.TestCase):
    """D09 §§10.2–10.3, 12.6; Integration Index Task J."""

    def test_finding_is_deterministic_and_preserves_structured_authority(self) -> None:
        build, _, _, _, _ = _api()
        spec = _spec()
        reversed_spec = copy.deepcopy(spec)
        for field in (
            "signal_ids",
            "fact_refs",
            "evidence_link_refs",
            "procedure_result_refs",
            "supporting_evidence_refs",
        ):
            reversed_spec[field] = list(reversed(reversed_spec[field]))
        first = build(spec)
        second = build(reversed_spec)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual("analysis_runtime", first["producer"])
        self.assertEqual("Provisional", first["authority"]["effective_level"])
        self.assertEqual("published", first["grade"]["status"])
        self.assertNotIn("primary_grade", first["grade"])

    def test_substantiated_requires_procedure_counter_evidence_and_coverage(self) -> None:
        build, _, _, _, _ = _api()
        for mutate in (
            lambda item: item["procedure_result_refs"].clear(),
            lambda item: item["verification"].update(counter_evidence_checked=False),
            lambda item: item["coverage"].update(required_procedures_complete=False),
            lambda item: item["coverage"].update(evidence_coverage_complete=False),
        ):
            spec = _spec()
            mutate(spec)
            with self.subTest(spec=spec):
                with self.assertRaises(ContractError):
                    build(spec)

    def test_non_substantiated_and_inconclusive_cannot_overstate_scope(self) -> None:
        build, _, _, _, _ = _api()
        unsupported = _spec()
        unsupported["disposition"] = "not_substantiated"
        unsupported["conclusion"]["qualifier"] = "no_company_issue"
        with self.assertRaises(ContractError):
            build(unsupported)

        inconclusive = _spec()
        inconclusive["disposition"] = "inconclusive"
        inconclusive["conclusion"]["qualifier"] = "insufficient_evidence"
        inconclusive["data_gaps"] = []
        inconclusive["coverage"]["evidence_coverage_complete"] = False
        inconclusive["uncertainty"] = {"status": "material", "reason_codes": ["missing_contracts"]}
        with self.assertRaises(ContractError):
            build(inconclusive)

        inconclusive["data_gaps"] = ["signed contracts"]
        inconclusive["coverage"]["missing_evidence_refs"] = ["contract_register"]
        finding = build(inconclusive)
        self.assertEqual("inconclusive", finding["disposition"])

    def test_runtime_rejects_direct_grade_approval_fact_signal_and_hidden_reasoning(self) -> None:
        build, _, _, _, _ = _api()
        for field, value in (
            ("primary_grade", "Decision Required"),
            ("approval", True),
            ("new_fact", {"claim": "invented"}),
            ("new_signal", {"claim": "invented"}),
            ("chain_of_thought", "hidden"),
        ):
            spec = _spec()
            spec[field] = value
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    build(spec)

        full = _spec()
        full["authority"]["effective_level"] = "Full"
        with self.assertRaises(ContractError):
            build(full)

    def test_supersession_links_new_revision_without_mutating_prior_bytes(self) -> None:
        build, _, _, _, validate_records = _api()
        prior = build(_spec(revision=7))
        prior_bytes = canonical_bytes(prior)
        next_spec = _spec(revision=8)
        next_spec["conclusion"]["statement"] = "New evidence changes the scoped conclusion."
        next_spec["supersedes_finding_id"] = prior["finding_id"]
        current = build(next_spec, prior_findings=[prior])
        self.assertEqual(prior["finding_id"], current["supersedes_finding_id"])
        self.assertEqual(prior_bytes, canonical_bytes(prior))
        validate_records([current, prior])

        fork_spec = _spec(revision=9)
        fork_spec["supersedes_finding_id"] = prior["finding_id"]
        fork = build(fork_spec, prior_findings=[prior])
        with self.assertRaises(ContractError):
            validate_records([prior, current, fork])

    def test_relations_fail_closed_on_dangling_causality_cycle_and_conflict(self) -> None:
        build, relation, _, validate_graph, _ = _api()
        a = build(_spec(case_suffix="a"))
        b = build(_spec(case_suffix="b"))
        c = build(_spec(case_suffix="c"))
        base = {
            "run_id": "run_findings",
            "revision": 7,
            "source_finding_id": a["finding_id"],
            "target_finding_id": b["finding_id"],
            "relation_type": "possible_cause_of",
            "evidence_refs": ["evidence_" + "d" * 24],
            "confidence_status": "verified",
            "contradicting_evidence_refs": [],
        }
        with self.assertRaises(ContractError):
            relation({**base, "target_finding_id": "finding_" + "f" * 24}, [a, b, c])
        with self.assertRaises(ContractError):
            relation({**base, "evidence_refs": []}, [a, b, c])

        ab = relation(base, [a, b, c])
        bc = relation(
            {
                **base,
                "source_finding_id": b["finding_id"],
                "target_finding_id": c["finding_id"],
            },
            [a, b, c],
        )
        ca = relation(
            {
                **base,
                "source_finding_id": c["finding_id"],
                "target_finding_id": a["finding_id"],
            },
            [a, b, c],
        )
        with self.assertRaises(ContractError):
            validate_graph([a, b, c], [ab, bc, ca])

        supports = relation(
            {
                **base,
                "relation_type": "supports",
                "source_finding_id": a["finding_id"],
                "target_finding_id": b["finding_id"],
            },
            [a, b],
        )
        contradicts = relation(
            {
                **base,
                "relation_type": "contradicts",
                "source_finding_id": a["finding_id"],
                "target_finding_id": b["finding_id"],
            },
            [a, b],
        )
        with self.assertRaises(ContractError):
            validate_graph([a, b], [supports, contradicts])

    def test_issue_cluster_is_order_invariant_connected_and_verified(self) -> None:
        build, relation, cluster, _, _ = _api()
        a = build(_spec(case_suffix="a"))
        b = build(_spec(case_suffix="b"))
        rel = relation(
            {
                "run_id": "run_findings",
                "revision": 7,
                "source_finding_id": a["finding_id"],
                "target_finding_id": b["finding_id"],
                "relation_type": "supports",
                "evidence_refs": ["evidence_" + "d" * 24],
                "confidence_status": "verified",
                "contradicting_evidence_refs": [],
            },
            [a, b],
        )
        kwargs = {
            "run_id": "run_findings",
            "revision": 7,
            "finding_ids": [a["finding_id"], b["finding_id"]],
            "relation_ids": [rel["relation_id"]],
            "decision_unit": {
                "title": "Resolve the shared issue",
                "decision_required": True,
                "owner_role": "CEO",
                "option_refs": ["option_a", "option_b"],
            },
            "unresolved_conflicts": [],
        }
        first = cluster(kwargs, findings=[a, b], relations=[rel])
        reversed_kwargs = copy.deepcopy(kwargs)
        reversed_kwargs["finding_ids"].reverse()
        reversed_kwargs["decision_unit"]["option_refs"].reverse()
        second = cluster(reversed_kwargs, findings=[b, a], relations=[rel])
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

        disconnected = copy.deepcopy(kwargs)
        disconnected["relation_ids"] = []
        with self.assertRaises(ContractError):
            cluster(disconnected, findings=[a, b], relations=[rel])


if __name__ == "__main__":
    unittest.main()
