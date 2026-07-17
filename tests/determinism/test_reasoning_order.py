import unittest

from trusted_ceo_agent.reasoning.join import freeze_join_manifest, reduce_join


class ReasoningOrderTests(unittest.TestCase):
    def test_lens_completion_order_does_not_change_join_result(self) -> None:
        tasks = [
            {"job_id": "job_b", "required": True, "required_signal_ids": []},
            {"job_id": "job_a", "required": True, "required_signal_ids": []},
        ]
        manifest = freeze_join_manifest("artifact_1", "a" * 64, "b" * 64, tasks, "2026-07-17T00:00:00Z")
        results = [
            {"job_id": job_id, "status": "completed", "card": {
                "card_id": f"card_{job_id}", "job_id": job_id, "artifact_ref": "artifact_1", "pack_manifest_hash": "b" * 64,
                "normalized_payload": {"signal_dispositions": [], "problem_candidates": []},
            }}
            for job_id in ("job_a", "job_b")
        ]
        self.assertEqual(reduce_join(manifest, results), reduce_join(manifest, list(reversed(results))))


if __name__ == "__main__":
    unittest.main()
