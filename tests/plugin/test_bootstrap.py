import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin" / "trusted-ceo-agent"
PATH = PLUGIN / "scripts" / "bootstrap.py"


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap", PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("bootstrap module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapTests(unittest.TestCase):
    def test_analysis_command_is_frozen_offline_and_no_sync(self) -> None:
        module = load_bootstrap()
        command = module.analysis_command(PLUGIN, ["status"])

        self.assertEqual("uv", command[0])
        self.assertTrue({"--frozen", "--offline", "--no-sync"}.issubset(command))
        self.assertIn(str(PLUGIN), command)

    def test_preflight_never_installs_dependencies(self) -> None:
        module = load_bootstrap()
        command = module.analysis_command(PLUGIN, ["status"])

        self.assertNotIn("sync", command)
        self.assertNotIn("pip", command)


if __name__ == "__main__":
    unittest.main()
