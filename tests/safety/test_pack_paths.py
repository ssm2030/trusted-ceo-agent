import os
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.packs import PackLoader, PackRegistry


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


class PackPathSafetyTests(unittest.TestCase):
    def loader(self, root: Path) -> PackLoader:
        registry = PackRegistry.load(
            PLUGIN_ROOT / "trust" / "pack-registry.json",
            PLUGIN_ROOT / "schemas" / "pack-registry.schema.json",
        )
        return PackLoader(root, PLUGIN_ROOT / "schemas", registry)

    def test_parent_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "packs"
            root.mkdir()
            outside = Path(directory) / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.loader(root).load_path(root / ".." / "outside.json")

    def test_symlink_and_hardlink_pack_are_rejected_when_supported(self) -> None:
        source = PLUGIN_ROOT / "packs" / "mission" / "trusted-ceo-default" / "1.0.0" / "pack.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "packs"
            root.mkdir()
            symlink = root / "symlink.json"
            try:
                symlink.symlink_to(source)
            except OSError:
                pass
            else:
                with self.assertRaises(ValueError):
                    self.loader(root).load_path(symlink)
            hardlink = root / "hardlink.json"
            try:
                os.link(source, hardlink)
            except OSError:
                pass
            else:
                with self.assertRaises(ValueError):
                    self.loader(root).load_path(hardlink)


if __name__ == "__main__":
    unittest.main()
