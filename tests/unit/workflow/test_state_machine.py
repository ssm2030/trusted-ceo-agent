import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.workflow.state_machine import transition


class StateMachineTests(unittest.TestCase):
    def test_context_and_diagnostic_branches_are_explicit(self) -> None:
        state = transition({"status": "created", "revision": 0}, "start", {"mission_confirmed": False})
        self.assertEqual("context_confirmation_required", state["status"])
        state = transition(state, "approve_context", {"approval_valid": True})
        self.assertEqual("context_ready", state["status"])

        deep = transition(
            {"status": "diagnostic_approval_required", "revision": 5},
            "approve_diagnostic",
            {"approval_valid": True, "deep_scope_empty": False},
        )
        self.assertEqual("deep_dive_authorized", deep["status"])
        direct = transition(
            {"status": "diagnostic_approval_required", "revision": 5},
            "approve_diagnostic",
            {"approval_valid": True, "deep_scope_empty": True},
        )
        self.assertEqual("finalization_jobs_ready", direct["status"])

    def test_terminal_and_invalid_transitions_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            transition({"status": "finalized", "revision": 9}, "start", {})
        with self.assertRaises(ContractError):
            transition({"status": "created", "revision": 0}, "finalize", {})

    def test_blocked_resume_requires_resolution_and_expected_revision(self) -> None:
        blocked = {"status": "blocked", "revision": 4, "resume_state": "lens_jobs_ready", "blocker": "required_lens_failed"}
        with self.assertRaises(ContractError):
            transition(blocked, "resume", {"blocker_resolved": False, "expected_revision": 4})
        resumed = transition(blocked, "resume", {"blocker_resolved": True, "expected_revision": 4})
        self.assertEqual("lens_jobs_ready", resumed["status"])


if __name__ == "__main__":
    unittest.main()
