import os
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.filesystem import ensure_within


class FilesystemTests(unittest.TestCase):
    def test_parent_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(ValueError):
                ensure_within(root, root / ".." / "escape.json")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_existing_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outside = root.parent / f"{root.name}-outside"
            outside.mkdir(exist_ok=True)
            link = root / "linked"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlink privilege unavailable")
            try:
                with self.assertRaises(ValueError):
                    ensure_within(root, link / "artifact.json")
            finally:
                link.unlink(missing_ok=True)
                outside.rmdir()


if __name__ == "__main__":
    unittest.main()

