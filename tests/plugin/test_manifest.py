import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin" / "trusted-ceo-agent"


class PluginManifestTests(unittest.TestCase):
    def test_manifest_name_matches_plugin_root(self) -> None:
        path = PLUGIN / ".codex-plugin" / "plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(PLUGIN.name, manifest["name"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("Trusted CEO Agent", manifest["interface"]["displayName"])


if __name__ == "__main__":
    unittest.main()
