from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.application.models import (
    ApplicationResult,
    AttachSourcesRequest,
    CreateRunRequest,
    HumanResponseRequest,
    RunRequest,
    SourceUpload,
)
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[3]
DRAFT_MISSION = {"confirmed": False, "objective": "", "customer_claims": []}


def _snapshot_files(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }


class ApplicationResultTests(unittest.TestCase):
    def test_cli_payload_contract_is_stable(self) -> None:
        result = ApplicationResult(
            command="status",
            ok=True,
            code=0,
            message="status read",
            run_id="run_test",
            revision=1,
            state="context_confirmation_required",
            data={"answer": 42},
        )

        self.assertEqual(
            {
                "command": "status",
                "ok": True,
                "code": 0,
                "message": "status read",
                "run_id": "run_test",
                "revision": 1,
                "state": "context_confirmation_required",
                "data": {"answer": 42},
            },
            result.to_cli_payload(),
        )


class TrustedCeoApplicationTests(unittest.TestCase):
    def test_create_run_accepts_service_id_and_draft_mission(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory) / "artifacts"
            application = TrustedCeoApplication(root)

            result = application.create_run(CreateRunRequest(
                mission=DRAFT_MISSION,
                run_id="run_browser_0123456789abcdef",
            ))

            self.assertEqual(0, result.code)
            self.assertEqual("run_browser_0123456789abcdef", result.run_id)
            self.assertEqual(1, result.revision)
            self.assertEqual("context_confirmation_required", result.state)
            self.assertEqual({"source_count": 0}, result.data)

            store = ArtifactStore(root)
            store.open_run(result.run_id or "")
            files = _snapshot_files(store, 1)
            self.assertEqual(DRAFT_MISSION, json.loads(files["mission/mission-contract.json"]))
            self.assertEqual([], json.loads(files["sources/registry.json"]))
            self.assertEqual({}, json.loads(files["sources/resolver.json"]))

    def test_create_run_validates_all_inputs_before_creating_storage(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory) / "artifacts"
            application = TrustedCeoApplication(root)
            run_id = "run_invalid_source_0123456789"

            with self.assertRaises(FileNotFoundError):
                application.create_run(CreateRunRequest(
                    mission=DRAFT_MISSION,
                    inputs=(Path(directory) / "missing.csv",),
                    run_id=run_id,
                ))

            self.assertFalse((root / run_id).exists())

    def test_attach_sources_is_atomic_deduplicated_and_path_opaque(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            root = workspace / "artifacts"
            first = workspace / "first.csv"
            alias = workspace / "alias.csv"
            first.write_bytes(b"amount\n10\n")
            alias.write_bytes(b"amount\n10\n")
            application = TrustedCeoApplication(root)
            created = application.create_run(CreateRunRequest(
                mission=DRAFT_MISSION,
                run_id="run_browser_attach_01234567",
            ))

            attached = application.attach_sources(AttachSourcesRequest(
                run_id=created.run_id or "",
                expected_revision=1,
                sources=(
                    SourceUpload(path=first, opaque_token="upload-first"),
                    SourceUpload(path=alias, opaque_token="upload-alias"),
                ),
            ))

            self.assertEqual(2, attached.revision)
            self.assertEqual({"source_count": 1, "attached_count": 1}, attached.data)
            store = ArtifactStore(root)
            store.open_run(created.run_id or "")
            files = _snapshot_files(store, 2)
            registry = json.loads(files["sources/registry.json"])
            resolver = json.loads(files["sources/resolver.json"])
            self.assertEqual(1, len(registry))
            self.assertEqual(["alias.csv"], registry[0]["aliases"])
            self.assertEqual(
                {"service-upload:upload-alias", "service-upload:upload-first"},
                set(resolver.values()),
            )
            self.assertNotIn(str(workspace), json.dumps(resolver))

            before = (root / (created.run_id or "") / "state.json").read_bytes()
            with self.assertRaises(RevisionConflict):
                application.attach_sources(AttachSourcesRequest(
                    run_id=created.run_id or "",
                    expected_revision=1,
                    sources=(SourceUpload(path=first, opaque_token="stale"),),
                ))
            self.assertEqual(before, (root / (created.run_id or "") / "state.json").read_bytes())

    def test_attach_sources_accumulates_aliases_and_rejects_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            root = workspace / 'artifacts'
            first = workspace / 'a.md'
            alias = workspace / 'copy.md'
            changed = workspace / 'changed.md'
            first.write_bytes(b'# Plan\nStable content\n')
            alias.write_bytes(first.read_bytes())
            changed.write_bytes(b'# Plan\nChanged content\n')
            application = TrustedCeoApplication(root)
            run_id = 'run_logical_alias_0123456789'
            application.create_run(CreateRunRequest(
                mission=DRAFT_MISSION,
                run_id=run_id,
            ))

            first_result = application.attach_sources(AttachSourcesRequest(
                run_id=run_id,
                expected_revision=1,
                sources=(SourceUpload(
                    path=first,
                    opaque_token='upload-a',
                    logical_path='folder-a/a.md',
                ),),
            ))
            alias_result = application.attach_sources(AttachSourcesRequest(
                run_id=run_id,
                expected_revision=first_result.revision or 0,
                sources=(SourceUpload(
                    path=alias,
                    opaque_token='upload-copy',
                    logical_path='folder-b/copy.md',
                ),),
            ))

            store = ArtifactStore(root)
            store.open_run(run_id)
            before_files = _snapshot_files(store, alias_result.revision or 0)
            registry_before = before_files['sources/registry.json']
            registry = json.loads(registry_before)
            self.assertEqual(1, len(registry))
            self.assertEqual('folder-a/a.md', registry[0]['display_name'])
            self.assertEqual(['folder-b/copy.md'], registry[0]['aliases'])
            self.assertEqual('text/markdown', registry[0]['media_type'])

            with self.assertRaisesRegex(ContractError, 'logical path'):
                application.attach_sources(AttachSourcesRequest(
                    run_id=run_id,
                    expected_revision=alias_result.revision or 0,
                    sources=(SourceUpload(
                        path=changed,
                        opaque_token='upload-changed',
                        logical_path='folder-a/a.md',
                    ),),
                ))

            self.assertEqual(alias_result.revision, store.state()['revision'])
            after_files = _snapshot_files(store, alias_result.revision or 0)
            self.assertEqual(registry_before, after_files['sources/registry.json'])

    def test_attach_sources_rejects_empty_and_model_started_runs(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            root = workspace / "artifacts"
            source = workspace / "data.json"
            source.write_text('{"revenue": 10}', encoding="utf-8")
            application = TrustedCeoApplication(root)
            run_id = "run_browser_late_0123456789"
            application.create_run(CreateRunRequest(mission=DRAFT_MISSION, run_id=run_id))

            with self.assertRaisesRegex(ContractError, "source"):
                application.attach_sources(AttachSourcesRequest(
                    run_id=run_id,
                    expected_revision=1,
                    sources=(),
                ))

            store = ArtifactStore(root)
            store.open_run(run_id)
            files = _snapshot_files(store, 1)
            state = json.loads(files["workflow/state.json"])
            state["state"] = "schema_mapping_job_ready"
            state["revision"] = 2
            files["workflow/state.json"] = canonical_bytes(state)
            store.publish(1, files)

            with self.assertRaisesRegex(ContractError, "model"):
                application.attach_sources(AttachSourcesRequest(
                    run_id=run_id,
                    expected_revision=2,
                    sources=(SourceUpload(path=source, opaque_token="late"),),
                ))

    def test_attach_sources_reupload_is_deduplicated_and_context_ready_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            root = workspace / "artifacts"
            source = workspace / "data.csv"
            source.write_bytes(b"amount\n10\n")
            run_id = "run_confirmed_attach_01234567"
            application = TrustedCeoApplication(root)
            application.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))

            first = application.attach_sources(AttachSourcesRequest(
                run_id=run_id,
                expected_revision=1,
                sources=(SourceUpload(path=source, opaque_token="upload-one"),),
            ))
            second = application.attach_sources(AttachSourcesRequest(
                run_id=run_id,
                expected_revision=first.revision or 0,
                sources=(SourceUpload(path=source, opaque_token="upload-two"),),
            ))

            self.assertEqual("context_ready", second.state)
            self.assertEqual(1, second.data["source_count"])
            self.assertEqual(0, second.data["attached_count"])

    def test_attach_sources_checks_cas_before_reading_uploads(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            root = workspace / "artifacts"
            run_id = "run_stale_attach_0123456789"
            application = TrustedCeoApplication(root)
            application.create_run(CreateRunRequest(mission=DRAFT_MISSION, run_id=run_id))

            with self.assertRaises(RevisionConflict):
                application.attach_sources(AttachSourcesRequest(
                    run_id=run_id,
                    expected_revision=0,
                    sources=(SourceUpload(
                        path=workspace / "does-not-exist.csv",
                        opaque_token="stale",
                    ),),
                ))

    def test_browser_mapping_response_normalizes_json_numbers_like_file_input(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory) / "artifacts"
            run_id = "run_numeric_response_01234567"
            application = TrustedCeoApplication(root)
            application.create_run(CreateRunRequest(
                mission=DRAFT_MISSION,
                run_owner_actor_id="ceo-1",
                run_id=run_id,
            ))
            pending = application.pending_action(RunRequest(run_id=run_id))
            card = pending.data["action"]
            self.assertIsInstance(card, dict)

            preview = application.preview_human_response(HumanResponseRequest(
                run_id=run_id,
                expected_revision=1,
                action_id=card["action_id"],
                action_content_hash=card["content_hash"],
                response={
                    "response_type": "request_changes",
                    "payload": {
                        "text": "숫자 기준을 조정합니다.",
                        "patch_operations": [{
                            "op": "add",
                            "path": "/mission_contract/materiality_context/threshold",
                            "value": 1.5,
                        }],
                    },
                    "actor_id": "ceo-1",
                },
            ))

            self.assertEqual(0, preview.code)
            self.assertEqual(1, preview.revision)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlink unsupported")
    def test_attach_sources_rejects_symbolic_link_upload(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            root = workspace / "artifacts"
            target = workspace / "target.csv"
            link = workspace / "link.csv"
            target.write_bytes(b"amount\n10\n")
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink privilege unavailable")
            run_id = "run_symlink_attach_01234567"
            application = TrustedCeoApplication(root)
            application.create_run(CreateRunRequest(mission=DRAFT_MISSION, run_id=run_id))

            with self.assertRaisesRegex(ValueError, "symbolic|reparse"):
                application.attach_sources(AttachSourcesRequest(
                    run_id=run_id,
                    expected_revision=1,
                    sources=(SourceUpload(path=link, opaque_token="linked"),),
                ))


if __name__ == "__main__":
    unittest.main()
