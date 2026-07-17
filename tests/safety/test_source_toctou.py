import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.intake.snapshot import Snapshotter


class SourceToctouTests(unittest.TestCase):
    def test_changed_identity_or_size_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "inputs"
            artifacts = root / "artifacts"
            inputs.mkdir()
            source = inputs / "source.csv"
            source.write_bytes(b"a\n1\n")

            def replace(path: Path) -> None:
                replacement = path.with_suffix(".replacement")
                replacement.write_bytes(b"a\n2\n3\n")
                replacement.replace(path)

            with self.assertRaises(IntegrityError):
                Snapshotter(inputs, artifacts, after_read_hook=replace).snapshot(source)


if __name__ == "__main__":
    unittest.main()
