from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.service.run_store import (
    RunStore,
    ServiceManifest,
    ServiceStoreError,
)


NOW = datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc)


class RunStoreTests(unittest.TestCase):
    def _store(self, root: Path) -> RunStore:
        return RunStore(root, clock=lambda: NOW)

    def test_idempotency_replays_same_body_and_rejects_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            store.create_manifest("run_store_12345678", engine_revision=0)
            first = store.store_idempotency_receipt(
                "run_store_12345678",
                idempotency_key="browser_action_1234",
                request_body={"action": "continue", "expected_revision": 0},
                status_code=200,
                response={"revision": 1, "status": "running"},
            )
            replay = store.store_idempotency_receipt(
                "run_store_12345678",
                idempotency_key="browser_action_1234",
                request_body={"expected_revision": 0, "action": "continue"},
                status_code=503,
                response={"ignored": True},
            )

            self.assertEqual(first, replay)
            self.assertEqual(200, replay.status_code)
            with self.assertRaisesRegex(ServiceStoreError, "IDEMPOTENCY_CONFLICT") as caught:
                store.store_idempotency_receipt(
                    "run_store_12345678",
                    idempotency_key="browser_action_1234",
                    request_body={"action": "stop", "expected_revision": 0},
                    status_code=200,
                    response={},
                )
            self.assertEqual("IDEMPOTENCY_CONFLICT", caught.exception.code)

    def test_only_a_pending_receipt_can_be_completed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            run_id = "run_receipt_cas_12345678"
            body = {"action": "continue", "expected_revision": 0}
            store.create_manifest(run_id, engine_revision=0)
            original = store.store_idempotency_receipt(
                run_id,
                idempotency_key="receipt_cas_action_0001",
                request_body=body,
                status_code=200,
                response={"revision": 1},
            )

            with self.assertRaisesRegex(IntegrityError, "not pending"):
                store.complete_idempotency_receipt(
                    run_id,
                    idempotency_key=original.idempotency_key,
                    request_body=body,
                    status_code=200,
                    response={"revision": 2},
                )

            replay = store.read_idempotency_receipt(
                run_id,
                idempotency_key=original.idempotency_key,
                request_body=body,
            )
            self.assertEqual(original, replay)

    def test_restart_recovers_running_but_preserves_human_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            running = store.create_manifest("run_running_12345678", engine_revision=2)
            store.save_manifest(
                running.model_copy(update={"status": "running", "stage": "lens"}),
                expected_revision=2,
            )
            waiting = store.create_manifest("run_waiting_12345678", engine_revision=4)
            store.save_manifest(
                waiting.model_copy(update={
                    "status": "awaiting_human",
                    "stage": "diagnostic_hitl",
                    "pending_approval_request_id": "approval_request_123",
                    "pending_approval_nonce": "private-nonce",
                }),
                expected_revision=4,
            )

            recovered = store.recover_interrupted()

            self.assertEqual(["run_running_12345678"], recovered)
            self.assertEqual(
                "retryable_failure",
                store.read_manifest("run_running_12345678").status,
            )
            preserved = store.read_manifest("run_waiting_12345678")
            self.assertEqual("awaiting_human", preserved.status)
            self.assertEqual("approval_request_123", preserved.pending_approval_request_id)

    def test_manifest_generation_prevents_same_revision_lost_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            original = store.create_manifest("run_generation_12345678", engine_revision=1)
            writer_a = original.model_copy(update={"status": "running", "stage": "lens"})
            writer_b = original.model_copy(update={"status": "stopped", "stage": "manual"})

            saved = store.save_manifest(writer_a, expected_revision=1)

            self.assertEqual(original.generation + 1, saved.generation)
            with self.assertRaisesRegex(ServiceStoreError, "STALE_REVISION"):
                store.save_manifest(writer_b, expected_revision=1)
            self.assertEqual("lens", store.read_manifest(original.run_id).stage)

    def test_restart_reconciles_engine_revision_advanced_before_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self._store(root)
            waiting = store.create_manifest("run_split_commit_12345678", engine_revision=2)
            waiting = store.save_manifest(
                waiting.model_copy(update={
                    "status": "awaiting_human",
                    "stage": "context_hitl",
                    "pending_approval_request_id": "approval_request_123",
                    "pending_approval_nonce": "private-nonce",
                }),
                expected_revision=2,
            )
            (store.run_root(waiting.run_id) / "state.json").write_bytes(canonical_bytes({
                "run_id": waiting.run_id,
                "revision": 3,
            }))

            recovered = store.recover_interrupted()

            self.assertEqual([waiting.run_id], recovered)
            reconciled = store.read_manifest(waiting.run_id)
            self.assertEqual(3, reconciled.engine_revision)
            self.assertEqual(3, reconciled.last_checkpoint_revision)
            self.assertEqual("retryable_failure", reconciled.status)
            self.assertIsNone(reconciled.pending_approval_request_id)
            self.assertIsNone(reconciled.pending_approval_nonce)

    def test_stale_revision_changes_neither_manifest_nor_engine_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self._store(root)
            manifest = store.create_manifest("run_stale_12345678", engine_revision=3)
            run_root = store.run_root("run_stale_12345678")
            state_path = run_root / "state.json"
            state_path.write_bytes(canonical_bytes({"run_id": manifest.run_id, "revision": 3}))
            before_manifest = (run_root / "service-manifest.json").read_bytes()
            before_state = state_path.read_bytes()

            with self.assertRaisesRegex(ServiceStoreError, "STALE_REVISION"):
                store.assert_revision("run_stale_12345678", expected_revision=2)
            with self.assertRaisesRegex(ServiceStoreError, "STALE_REVISION"):
                store.save_manifest(
                    manifest.model_copy(update={"status": "running"}),
                    expected_revision=2,
                )

            self.assertEqual(before_manifest, (run_root / "service-manifest.json").read_bytes())
            self.assertEqual(before_state, state_path.read_bytes())

    def test_manifest_excludes_source_and_model_bodies_and_delete_is_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            manifest = store.create_manifest("run_delete_12345678", engine_revision=0)
            payload = json.loads(
                (store.run_root(manifest.run_id) / "service-manifest.json").read_text("utf-8")
            )
            self.assertNotIn("source_body", payload)
            self.assertNotIn("model_output", payload)
            outside = Path(directory) / "outside.txt"
            outside.write_text("preserve", encoding="utf-8")

            with self.assertRaisesRegex(ServiceStoreError, "confirmation"):
                store.delete_run(
                    manifest.run_id,
                    expected_revision=0,
                    confirmed=False,
                    idempotency_key="delete_action_1234",
                )
            store.delete_run(
                manifest.run_id,
                expected_revision=0,
                confirmed=True,
                idempotency_key="delete_action_1234",
            )
            store.delete_run(
                manifest.run_id,
                expected_revision=0,
                confirmed=True,
                idempotency_key="delete_action_1234",
            )

            self.assertFalse(store.run_root(manifest.run_id).exists())
            self.assertEqual("preserve", outside.read_text("utf-8"))
            with self.assertRaisesRegex(ServiceStoreError, "cannot be reused"):
                store.create_manifest(manifest.run_id, engine_revision=0)
            with self.assertRaisesRegex(ServiceStoreError, "IDEMPOTENCY_CONFLICT"):
                store.delete_run(
                    manifest.run_id,
                    expected_revision=0,
                    confirmed=True,
                    idempotency_key="different_delete_1234",
                )

    def test_delete_rejects_engine_state_for_a_different_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            manifest = store.create_manifest("run_delete_guard_12345678", engine_revision=0)
            run_root = store.run_root(manifest.run_id)
            (run_root / "state.json").write_bytes(canonical_bytes({
                "run_id": "run_other_12345678",
                "revision": 0,
            }))

            with self.assertRaisesRegex(IntegrityError, "run ID"):
                store.delete_run(
                    manifest.run_id,
                    expected_revision=0,
                    confirmed=True,
                    idempotency_key="delete_guard_1234",
                )

            self.assertTrue(run_root.exists())
            self.assertTrue((run_root / "service-manifest.json").is_file())

    def test_delete_cleanup_failure_is_finished_on_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self._store(root)
            manifest = store.create_manifest("run_delete_retry_12345678", engine_revision=0)

            with patch(
                "trusted_ceo_agent.service.run_store.shutil.rmtree",
                side_effect=OSError("simulated cleanup interruption"),
            ):
                with self.assertRaisesRegex(OSError, "cleanup interruption"):
                    store.delete_run(
                        manifest.run_id,
                        expected_revision=0,
                        confirmed=True,
                        idempotency_key="delete_retry_1234",
                    )

            self.assertTrue((root / "trash" / manifest.run_id).is_dir())
            self.assertTrue((root / "tombstones" / f"{manifest.run_id}.json").is_file())
            restarted = self._store(root)
            self.assertFalse((root / "trash" / manifest.run_id).exists())
            restarted.delete_run(
                manifest.run_id,
                expected_revision=0,
                confirmed=True,
                idempotency_key="delete_retry_1234",
            )

    def test_recovery_rejects_engine_state_for_a_different_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory))
            manifest = store.create_manifest("run_recovery_guard_12345678", engine_revision=0)
            (store.run_root(manifest.run_id) / "state.json").write_bytes(canonical_bytes({
                "run_id": "run_other_12345678",
                "revision": 1,
            }))

            with self.assertRaisesRegex(IntegrityError, "run ID"):
                store.recover_interrupted()


if __name__ == "__main__":
    unittest.main()
