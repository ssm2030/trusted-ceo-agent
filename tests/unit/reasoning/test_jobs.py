import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.document_evidence import build_document_evidence
from trusted_ceo_agent.reasoning.jobs import (
    build_reasoning_job,
    compile_stage_jobs,
    shard_reasoning_items,
)


class ReasoningJobTests(unittest.TestCase):
    @staticmethod
    def _lens_fields() -> dict:
        return {
            'stage': 'lens',
            'artifact_ref': 'artifact_documents',
            'mission_contract_hash': 'a' * 64,
            'pack_manifest_hash': 'b' * 64,
            'prompt_template_hash': 'c' * 64,
            'model_profile': 'balanced_structured',
            'output_schema_ref': 'lens-card-draft.schema.json',
            'lens_id': 'financial',
            'shard_index': 0,
            'shard_count': 1,
        }

    @staticmethod
    def _documents(text: str) -> list[dict]:
        return build_document_evidence(
            {
                'source_id': 'source_' + 'd' * 24,
                'display_name': 'strategy/plan.md',
            },
            text,
        )

    def test_document_context_is_exact_bounded_and_combined_with_fact_shards(self) -> None:
        documents = self._documents('# One\nFirst\n# Two\nSecond\n')
        work_items = [
            {
                'id': item['document_evidence_id'],
                'kind': 'document',
                'context': item,
                'scope': item['logical_path'],
                'period': item['line_start'],
            }
            for item in documents
        ] + [
            {
                'id': f'fact_{index:03d}',
                'kind': 'fact',
                'scope': 'enterprise',
                'period': '2026-01',
            }
            for index in range(47)
        ]
        fields = self._lens_fields()
        jobs = compile_stage_jobs(
            'lens',
            artifact_ref=fields['artifact_ref'],
            mission_contract_hash=fields['mission_contract_hash'],
            pack_manifest_hash=fields['pack_manifest_hash'],
            prompt_template_hash=fields['prompt_template_hash'],
            model_profile=fields['model_profile'],
            output_schema_ref=fields['output_schema_ref'],
            lens_id=fields['lens_id'],
            work_items=work_items,
        )

        self.assertEqual(2, len(jobs))
        emitted_document_ids: set[str] = set()
        for job in jobs:
            document_ids = job.get('allowed_document_evidence_ids', [])
            emitted_document_ids.update(document_ids)
            contexts = job.get('document_evidence_context', [])
            self.assertLessEqual(len(job['allowed_fact_ids']) + len(document_ids), 48)
            self.assertEqual(
                document_ids,
                [item['document_evidence_id'] for item in contexts],
            )
            self.assertTrue(set(document_ids).issubset(job['untrusted_text_markers']))
        self.assertEqual(
            {item['document_evidence_id'] for item in documents},
            emitted_document_ids,
        )

        legacy = build_reasoning_job(
            stage='lens',
            artifact_ref='artifact_legacy',
            mission_contract_hash='a' * 64,
            pack_manifest_hash='b' * 64,
            prompt_template_hash='c' * 64,
            model_profile='balanced_structured',
            output_schema_ref='lens-card-draft.schema.json',
            lens_id='financial',
            shard_index=0,
            shard_count=1,
            allowed_fact_ids=['fact_legacy'],
        )
        self.assertEqual('job_9ef083e6d90ff108addbbb57', legacy['job_id'])
        self.assertNotIn('document_evidence_context', legacy)

        with self.assertRaisesRegex(ContractError, 'context IDs must match'):
            build_reasoning_job(
                **fields,
                allowed_document_evidence_ids=['document_' + 'a' * 24],
                document_evidence_context=[documents[0]],
            )

        oversized = sorted(
            self._documents('# Large\n' + 'x' * 98_000),
            key=lambda item: item['document_evidence_id'],
        )
        with self.assertRaisesRegex(ContractError, '96,000'):
            build_reasoning_job(
                **fields,
                allowed_document_evidence_ids=[
                    item['document_evidence_id'] for item in oversized
                ],
                document_evidence_context=oversized,
            )

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

    def test_integrated_job_requires_a_sorted_card_allowlist(self) -> None:
        common = {
            "stage": "integrated",
            "artifact_ref": "artifact_001",
            "mission_contract_hash": "a" * 64,
            "pack_manifest_hash": "b" * 64,
            "prompt_template_hash": "c" * 64,
            "model_profile": "strong_structured",
            "output_schema_ref": "integrated-draft.schema.json",
            "join_manifest_ref": "join_001",
        }
        job = build_reasoning_job(
            **common,
            allowed_card_refs=["card_b", "card_a"],
        )

        self.assertEqual(["card_a", "card_b"], job["allowed_card_refs"])
        with self.assertRaises(ContractError):
            build_reasoning_job(**common)

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
                allowed_card_refs=["card_001"],
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
