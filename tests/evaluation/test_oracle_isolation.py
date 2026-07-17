import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "plugin" / "trusted-ceo-agent" / "trusted_ceo_agent"


class OracleIsolationTests(unittest.TestCase):
    def test_runtime_has_no_oracle_path_reference(self) -> None:
        needle = "tests/evaluation/" + "oracles"
        for path in RUNTIME.rglob("*.py"):
            with self.subTest(path=path.name):
                self.assertNotIn(needle, path.read_text("utf-8").replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
