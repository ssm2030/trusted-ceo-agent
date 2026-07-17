import unittest

from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.runtime_scan import _pack_artifacts
from tests.support import confirmed_mission


class RuntimePackIndexTests(unittest.TestCase):
    def test_index_reads_only_manifested_immutable_snapshots(self) -> None:
        artifacts, _, _ = _pack_artifacts(confirmed_mission())
        index = RuntimePackIndex.from_files(artifacts)
        self.assertEqual("b2b-services@1.0.0", index.domain_ref)
        self.assertEqual(5, len(index.problem_packs))
        self.assertEqual("0.3", index.thresholds["driver_contribution_plausible"])
        self.assertEqual("provisional", index.effective_authority)

    def test_tampered_snapshot_is_rejected(self) -> None:
        artifacts, manifest, _ = _pack_artifacts(confirmed_mission())
        digest = manifest["packs"][0]["pack_sha256"]
        artifacts[f"packs/snapshots/{digest}.json"] += b" "
        with self.assertRaises(IntegrityError):
            RuntimePackIndex.from_files(artifacts)


if __name__ == "__main__":
    unittest.main()
