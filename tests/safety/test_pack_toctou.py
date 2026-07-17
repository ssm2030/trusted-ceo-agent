import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.packs import PackLoader, PackRegistry


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


class PackToctouTests(unittest.TestCase):
    def test_identity_change_during_read_is_rejected(self) -> None:
        source = PLUGIN_ROOT / "packs" / "mission" / "trusted-ceo-default" / "1.0.0" / "pack.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "pack.json"
            target.write_bytes(source.read_bytes())
            registry = PackRegistry.load(
                PLUGIN_ROOT / "trust" / "pack-registry.json",
                PLUGIN_ROOT / "schemas" / "pack-registry.schema.json",
            )
            loader = PackLoader(root, PLUGIN_ROOT / "schemas", registry)
            with patch("trusted_ceo_agent.packs.loader._identity", side_effect=[(1, 1, 10, 1), (1, 1, 11, 2)]):
                with self.assertRaises(IntegrityError):
                    loader.load_path(target)


if __name__ == "__main__":
    unittest.main()
