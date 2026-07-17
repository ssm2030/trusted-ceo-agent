from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.errors import ContractError

from tests.integrator_support import (
    FACT_ID,
    PACK_HASH,
    REVISION,
    RUN_ID,
    complete_inputs,
    rehash_assessment,
    rehash_route,
)


def build_manifest(inputs: dict, *, writer_id: str = "integrator_primary") -> dict:
    from trusted_ceo_agent.analysis.integrator import freeze_finding_join_manifest

    return freeze_finding_join_manifest(
        run_id=RUN_ID,
        revision=REVISION,
        event=inputs["event"],
        routes=inputs["routes"],
        domain_assessments=inputs["domain_assessments"],
        findings=inputs["findings"],
        relations=inputs["relations"],
        clusters=inputs["clusters"],
        writer_id=writer_id,
    )


def integrate(inputs: dict, manifest: dict, *, writer_id: str = "integrator_primary") -> dict:
    from trusted_ceo_agent.analysis.integrator import integrate_cross_domain

    return integrate_cross_domain(
        manifest=manifest,
        expected_manifest_hash=manifest["integrity"]["payload_hash"],
        writer_id=writer_id,
        event=inputs["event"],
        routes=inputs["routes"],
        domain_assessments=inputs["domain_assessments"],
        findings=inputs["findings"],
        relations=inputs["relations"],
        clusters=inputs["clusters"],
    )


class CrossDomainIntegratorTests(unittest.TestCase):
    def test_preserves_common_facts_conflict_lineage_and_decision_units(self) -> None:
        inputs = complete_inputs()
        result = integrate(inputs, build_manifest(inputs))

        self.assertEqual([FACT_ID], result["common_fact_refs"])
        self.assertEqual(PACK_HASH, result["pack_manifest_hash"])
        self.assertEqual(2, len(result["domain_judgment_refs"]))
        conflict = result["conflicts"][0]
        relation = inputs["relations"][0]
        self.assertEqual(relation["relation_id"], conflict["relation_id"])
        self.assertEqual(relation["evidence_refs"], conflict["evidence_refs"])
        self.assertEqual(
            relation["contradicting_evidence_refs"],
            conflict["contradicting_evidence_refs"],
        )
        self.assertEqual(
            inputs["clusters"][0]["decision_unit"],
            result["ceo_decision_units"][0]["decision_unit"],
        )

    def test_required_pending_failed_and_stale_routes_block_the_join(self) -> None:
        for status in ("deep_review_pending", "failed"):
            with self.subTest(status=status):
                inputs = complete_inputs()
                inputs["routes"][0]["status"] = status
                inputs["routes"][0] = rehash_route(inputs["routes"][0])
                inputs["domain_assessments"][0]["status"] = status
                inputs["domain_assessments"][0] = rehash_assessment(
                    inputs["domain_assessments"][0]
                )
                with self.assertRaises(ContractError):
                    build_manifest(inputs)

        stale = complete_inputs()
        stale["routes"][0]["integrity"]["payload_hash"] = "0" * 64
        with self.assertRaises(ContractError):
            build_manifest(stale)

    def test_manifest_freezes_inputs_and_rejects_late_changed_bytes(self) -> None:
        inputs = complete_inputs()
        manifest = build_manifest(inputs)
        changed = copy.deepcopy(inputs)
        changed["domain_assessments"][0]["additional_data_refs"] = ["late_packet"]
        changed["domain_assessments"][0] = rehash_assessment(
            changed["domain_assessments"][0]
        )
        with self.assertRaises(ContractError):
            integrate(changed, manifest)

    def test_single_writer_is_enforced_without_changing_authority(self) -> None:
        inputs = complete_inputs()
        manifest = build_manifest(inputs)
        with self.assertRaises(ContractError):
            integrate(inputs, manifest, writer_id="integrator_secondary")
        result = integrate(inputs, manifest)
        self.assertNotIn("effective_authority", result)
        self.assertEqual(
            ["provisional", "provisional"],
            [item["authority"] for item in result["domain_judgment_refs"]],
        )

    def test_unsupported_domain_is_preserved_as_expert_boundary(self) -> None:
        inputs = complete_inputs(include_unsupported=True)
        result = integrate(inputs, build_manifest(inputs))
        legal = next(
            item for item in result["required_domain_terminal_map"]
            if item["domain"] == "legal"
        )
        self.assertEqual("unsupported_pack", legal["status"])
        self.assertEqual("boundary", legal["authority"])
        self.assertEqual(
            [{
                "domain": "legal",
                "expert_role": "legal_counsel",
                "status": "unsupported_pack",
                "additional_data_refs": ["packet_legal"],
            }],
            result["expert_requirements"],
        )


if __name__ == "__main__":
    unittest.main()
