import unittest

from trusted_ceo_agent.workflow.overlays import invalidated_gates
from trusted_ceo_agent.workflow.state_machine import transition


class RequestChangesLoopTests(unittest.TestCase):
    def test_diagnostic_data_change_returns_to_evidence_and_invalidates_downstream(self) -> None:
        state = transition(
            {"status": "diagnostic_approval_required", "revision": 7},
            "request_diagnostic_changes",
            {"change_scope": "data"},
        )
        self.assertEqual("evidence_ready", state["status"])
        self.assertEqual(
            {"diagnostic", "deep_authorization", "final"},
            invalidated_gates(["/mapping/columns/revenue/unit_code"]),
        )


if __name__ == "__main__":
    unittest.main()
