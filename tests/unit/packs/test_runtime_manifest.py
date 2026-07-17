import unittest

from trusted_ceo_agent.runtime_scan import _pack_artifacts
from tests.support import confirmed_mission


class RuntimePackManifestTests(unittest.TestCase):
    def test_supported_domain_snapshots_candidate_problem_packs(self) -> None:
        artifacts, manifest, selection = _pack_artifacts(confirmed_mission())
        self.assertEqual("b2b-services", selection.pack.pack_id)
        problem_entries = [item for item in manifest["packs"] if item["pack_type"] == "problem"]
        self.assertEqual(5, len(problem_entries))
        for entry in problem_entries:
            self.assertIn(f"packs/snapshots/{entry['pack_sha256']}.json", artifacts)

    def test_boundary_domain_does_not_authorize_problem_packs(self) -> None:
        _, manifest, selection = _pack_artifacts(
            confirmed_mission(business_model="regulated_bank")
        )
        self.assertEqual("generic-business-boundary", selection.pack.pack_id)
        self.assertFalse(any(item["pack_type"] == "problem" for item in manifest["packs"]))


if __name__ == "__main__":
    unittest.main()
