import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.reasoning.jobs import build_reasoning_job, shard_reasoning_items


class ReasoningJobTests(unittest.TestCase):
    def test_lens_job_is_order_invariant_and_requires_lens_fields(self) -> None:
        common = {
            "stage": "lens",
            "artifact_ref": "artifact_001",
            "mission_contract_hash": "a" * 64,
            "pack_manifest_hash": "b" * 64,
            "prompt_template_hash": "c" * 64,
            "model_profile": "balanced_structured",
            "output_schema_ref": "lens-card-draft.schema.json",
            "lens_id": "financial",
            "shard_index": 0,
            "shard_count": 1,
        }
        first = build_reasoning_job(
            **common,
            allowed_fact_ids=["fact_b", "fact_a"],
            allowed_signal_ids=["signal_b", "signal_a"],
            allowed_problem_family_refs=["profitability", "concentration"],
            allowed_response_refs=["verify", "monitor"],
            required_signal_ids=["signal_b"],
        )
        second = build_reasoning_job(
            **common,
            allowed_fact_ids=["fact_a", "fact_b"],
            allowed_signal_ids=["signal_a", "signal_b"],
            allowed_problem_family_refs=["concentration", "profitability"],
            allowed_response_refs=["monitor", "verify"],
            required_signal_ids=["signal_b"],
        )
        self.assertEqual(first, second)
        self.assertEqual(["concentration", "profitability"], first["allowed_problem_family_refs"])
        self.assertEqual(["monitor", "verify"], first["allowed_response_refs"])
        self.assertTrue(first["job_id"].startswith("job_"))
        with self.assertRaises(ContractError):
            build_reasoning_job(**{key: value for key, value in common.items() if key != "lens_id"})

    def test_stage_specific_fields_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            build_reasoning_job(
                stage="integrated",
                artifact_ref="artifact_001",
                mission_contract_hash="a" * 64,
                pack_manifest_hash="b" * 64,
                prompt_template_hash="c" * 64,
                model_profile="strong_structured",
                output_schema_ref="integrated-draft.schema.json",
                join_manifest_ref="join_001",
                lens_id="forbidden",
            )

    def test_sharding_is_deterministic_and_bounded(self) -> None:
        items = [
            {"id": f"fact_{index:03d}", "scope": "enterprise", "period": "2026-01", "component_id": "aggregate"}
            for index in range(55)
        ]
        forward = shard_reasoning_items(items, limit=48)
        reverse = shard_reasoning_items(list(reversed(items)), limit=48)
        self.assertEqual(forward, reverse)
        self.assertEqual([48, 7], [len(shard) for shard in forward])


if __name__ == "__main__":
    unittest.main()
