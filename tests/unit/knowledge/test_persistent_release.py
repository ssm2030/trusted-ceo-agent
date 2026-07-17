from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.knowledge.persistent_release import (
    PersistentReleaseRegistry,
    export_registry_state,
    import_registry_state,
)
from trusted_ceo_agent.knowledge.release import ReleaseRegistry
from trusted_ceo_agent.trust.artifact_store import ArtifactStore

from tests.foundry_support import approve_object, make_candidate, make_stage3


class PersistentReleaseRegistryTests(unittest.TestCase):
    def _store(self, root: Path, *, create: bool) -> ArtifactStore:
        store = ArtifactStore(root)
        if create:
            store.create_run("run_knowledge_registry")
        else:
            store.open_run("run_knowledge_registry")
        return store

    def test_state_export_import_is_hashed_and_restores_all_registry_state(self):
        base, _, _, _, _, candidate = make_candidate()
        registry = ReleaseRegistry(base)
        registry.start_run("run_seed")
        _, deploy_approval = make_stage3(candidate)
        deployed = registry.deploy(candidate, deploy_approval, current_revision=4)
        registry.start_run("run_deployed")
        _, rollback_approval = approve_object(
            deployed,
            id_field="release_id",
            hash_field="release_hash",
            stage="release_deploy",
            action="rollback_release",
            role="release_manager",
            actor="rollback_admin",
            expected_revision=6,
        )
        registry.rollback(
            revoked_release_id=deployed["release_id"],
            target_release_id=base["release_id"],
            approval=rollback_approval,
            current_revision=6,
        )

        payload = export_registry_state(registry)
        restored = import_registry_state(payload)

        self.assertEqual(base["release_id"], restored.active_release_id)
        self.assertEqual(base["release_id"], restored.release_for_run("run_seed")["release_id"])
        self.assertEqual(
            deployed["release_id"],
            restored.release_for_run("run_deployed")["release_id"],
        )
        tampered = payload.replace(
            b'"schema_version":"1.0.0"',
            b'"schema_version":"1.0.1"',
            1,
        )
        with self.assertRaises((ContractError, IntegrityError)):
            import_registry_state(tampered)

    def test_restart_preserves_old_pin_and_deploy_only_changes_future_runs(self):
        base, _, _, _, _, candidate = make_candidate()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persistent = PersistentReleaseRegistry.initialize(
                self._store(root, create=True),
                base,
                expected_revision=0,
            )
            persistent.start_run("run_before", expected_revision=1)
            _, approval = make_stage3(candidate)
            deployed = persistent.deploy(
                candidate,
                approval,
                current_revision=4,
                expected_revision=2,
            )
            persistent.start_run("run_after", expected_revision=3)

            restored = PersistentReleaseRegistry.restore(self._store(root, create=False))

            self.assertEqual(4, restored.revision)
            self.assertEqual(
                base["release_id"],
                restored.release_for_run("run_before")["release_id"],
            )
            self.assertEqual(
                deployed["release_id"],
                restored.release_for_run("run_after")["release_id"],
            )

    def test_concurrent_stale_writer_is_rejected_without_mutating_its_registry(self):
        base, _, _, _, _, _ = make_candidate()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            PersistentReleaseRegistry.initialize(
                self._store(root, create=True),
                base,
                expected_revision=0,
            )
            writer_a = PersistentReleaseRegistry.restore(self._store(root, create=False))
            writer_b = PersistentReleaseRegistry.restore(self._store(root, create=False))

            writer_a.start_run("run_a", expected_revision=1)
            with self.assertRaises(RevisionConflict):
                writer_b.start_run("run_b", expected_revision=1)
            with self.assertRaises(ContractError):
                writer_b.release_for_run("run_b")

    def test_rollback_recovers_after_restart_and_snapshot_tamper_fails_closed(self):
        base, _, _, _, _, candidate = make_candidate()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persistent = PersistentReleaseRegistry.initialize(
                self._store(root, create=True),
                base,
                expected_revision=0,
            )
            _, deploy_approval = make_stage3(candidate)
            deployed = persistent.deploy(
                candidate,
                deploy_approval,
                current_revision=4,
                expected_revision=1,
            )
            _, rollback_approval = approve_object(
                deployed,
                id_field="release_id",
                hash_field="release_hash",
                stage="release_deploy",
                action="rollback_release",
                role="release_manager",
                actor="rollback_admin",
                expected_revision=6,
            )
            persistent.rollback(
                revoked_release_id=deployed["release_id"],
                target_release_id=base["release_id"],
                approval=rollback_approval,
                current_revision=6,
                expected_revision=2,
            )

            store = self._store(root, create=False)
            restored = PersistentReleaseRegistry.restore(store)
            self.assertEqual(base["release_id"], restored.active_release_id)
            self.assertEqual(
                base["release_id"],
                restored.start_run("run_after_rollback", expected_revision=3)["release_id"],
            )

            snapshot = store.verify_revision(4)
            state_path = snapshot / PersistentReleaseRegistry.STATE_PATH
            altered = state_path.read_bytes()
            state_path.write_bytes(altered.replace(b'"schema_version":"1.0.0"', b'"schema_version":"9.0.0"'))
            with self.assertRaises(IntegrityError):
                PersistentReleaseRegistry.restore(self._store(root, create=False))


if __name__ == "__main__":
    unittest.main()
