from __future__ import annotations

import unittest
from pathlib import Path

from trusted_ceo_agent.application import MutationRequest


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = (
    ROOT
    / "plugin"
    / "trusted-ceo-agent"
    / "trusted_ceo_agent"
    / "service"
)


class ServiceBoundaryTests(unittest.TestCase):
    def test_mutation_request_is_public_and_frozen(self) -> None:
        request = MutationRequest(
            artifact_root=ROOT / "runtime",
            run_id="run_test",
            expected_revision=1,
            command="scan",
            parameters={},
        )
        self.assertEqual("scan", request.command)
        with self.assertRaises((AttributeError, TypeError)):
            request.command = "cancel"  # type: ignore[misc]

    def test_service_never_imports_or_shells_out_to_cli(self) -> None:
        forbidden = (
            "trusted_ceo_agent.cli",
            "subprocess",
            "os.system",
            "shell=True",
        )
        sources = sorted(SERVICE_ROOT.rglob("*.py"))
        self.assertTrue(sources, "service boundary scan must inspect Python sources")
        violations: list[str] = []
        for path in sources:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    violations.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
