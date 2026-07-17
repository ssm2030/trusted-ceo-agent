from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.knowledge.release import ReleaseRegistry

from tests.foundry_support import approve_object, make_candidate, make_stage3


class ReleaseRegistryTests(unittest.TestCase):
    def test_deploy_rejects_stale_revision_and_hash_tamper(self):
        base, _, _, _, _, candidate = make_candidate()
        registry = ReleaseRegistry(base)
        _, approval = make_stage3(candidate)
        with self.assertRaises(RevisionConflict):
            registry.deploy(candidate, approval, current_revision=5)

        tampered = copy.deepcopy(candidate)
        tampered["artifact_manifest"][0]["artifact_hash"] = "f" * 64
        with self.assertRaisesRegex(ContractError, "candidate hash"):
            registry.deploy(tampered, approval, current_revision=4)

    def test_stage2_reviewer_cannot_self_deploy(self):
        base, _, _, _, approvals, candidate = make_candidate()
        registry = ReleaseRegistry(base)
        actor = approvals[0]["approved_by"]
        _, stage3 = make_stage3(candidate, actor=actor)
        with self.assertRaisesRegex(ContractError, "role separation"):
            registry.deploy(candidate, stage3, current_revision=4)

    def test_rollback_changes_future_default_without_mutating_releases_or_runs(self):
        base, _, _, _, _, candidate = make_candidate()
        registry = ReleaseRegistry(base)
        registry.start_run("run_on_seed")
        _, deploy_approval = make_stage3(candidate)
        deployed = registry.deploy(candidate, deploy_approval, current_revision=4)
        registry.start_run("run_on_new")
        before = canonical_bytes(deployed)

        _, rollback_approval = approve_object(
            deployed,
            id_field="release_id",
            hash_field="release_hash",
            stage="release_deploy",
            action="rollback_release",
            role="release_manager",
            actor="release_admin_rollback",
            expected_revision=6,
        )
        event = registry.rollback(
            revoked_release_id=deployed["release_id"],
            target_release_id=base["release_id"],
            approval=rollback_approval,
            current_revision=6,
        )
        self.assertEqual(before, canonical_bytes(registry.get_release(deployed["release_id"])))
        self.assertEqual(base["release_id"], registry.active_release_id)
        self.assertEqual(base["release_id"], registry.start_run("run_after_rollback")["release_id"])
        self.assertEqual(deployed["release_id"], registry.release_for_run("run_on_new")["release_id"])
        self.assertEqual("rollback", event["event_type"])

    def test_release_objects_return_defensive_copies(self):
        base, _, _, _, _, _ = make_candidate()
        registry = ReleaseRegistry(base)
        returned = registry.get_release(base["release_id"])
        returned["artifact_manifest"].clear()
        self.assertNotEqual([], registry.get_release(base["release_id"])["artifact_manifest"])


if __name__ == "__main__":
    unittest.main()
