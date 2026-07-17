import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.intake.snapshot import Snapshotter
from trusted_ceo_agent.intake.source_registry import SourceRegistry


class SnapshotAndRegistryTests(unittest.TestCase):
    def test_snapshot_is_content_addressed_and_registry_deduplicates_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            artifact_root = root / "artifacts"
            input_root.mkdir()
            first = input_root / "first.csv"
            second = input_root / "second.csv"
            first.write_bytes(b"a,b\n1,2\n")
            second.write_bytes(first.read_bytes())

            snapshotter = Snapshotter(input_root, artifact_root)
            one = snapshotter.snapshot(first, observation_roles=("ledger",))
            two = snapshotter.snapshot(second, observation_roles=("ledger",))
            registry = SourceRegistry()
            registry.add(one)
            registry.add(two)

            self.assertEqual(one.source["source_id"], two.source["source_id"])
            self.assertEqual(1, len(registry.sources))
            self.assertEqual(["second.csv"], registry.sources[0]["aliases"])
            blob = artifact_root / one.source["snapshot_ref"]
            self.assertEqual(first.read_bytes(), blob.read_bytes())
            self.assertNotEqual(first.stat().st_ino, blob.stat().st_ino)
            self.assertNotIn(str(first.resolve()), str(registry.sources))
            self.assertEqual(2, len(registry.resolver_entries))

    def test_mutation_during_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            artifact_root = root / "artifacts"
            input_root.mkdir()
            source = input_root / "changing.csv"
            source.write_bytes(b"a\n1\n")

            def mutate(path: Path) -> None:
                path.write_bytes(path.read_bytes() + b"2\n")

            snapshotter = Snapshotter(input_root, artifact_root, after_read_hook=mutate)
            with self.assertRaises(IntegrityError):
                snapshotter.snapshot(source)


if __name__ == "__main__":
    unittest.main()
