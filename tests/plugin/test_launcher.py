import subprocess
import sys
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "plugin" / "trusted-ceo-agent" / "scripts" / "trusted_ceo_agent.py"


class LauncherTests(unittest.TestCase):
    def test_help_works_from_arbitrary_cwd(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(LAUNCHER), "--help"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Trusted CEO Agent", completed.stdout)

    def test_launcher_does_not_shadow_package_when_pythonpath_already_contains_plugin(self) -> None:
        plugin_root = str(LAUNCHER.parents[1])
        environment = dict(os.environ)
        environment["PYTHONPATH"] = plugin_root
        completed = subprocess.run(
            [sys.executable, str(LAUNCHER), "--help"],
            cwd=ROOT.parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Trusted CEO Agent", completed.stdout)


if __name__ == "__main__":
    unittest.main()
