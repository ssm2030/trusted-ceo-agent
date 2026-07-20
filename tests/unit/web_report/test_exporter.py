from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.trust.revision_validation import RevisionValidation
from trusted_ceo_agent.web_report.canonical import jcs_bytes
from trusted_ceo_agent.web_report.exporter import export_web_report


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "run_20260717T010203Z_0123456789abcdef"


def _approval(input_method: str = "interactive_tty") -> dict:
    record = {
        "approval_id": "approval_final",
        "approval_request_id": "approvalrequest_final",
        "gate": "final",
        "base_artifact_ref": f"{RUN_ID}@r0000",
        "result_artifact_ref": f"{RUN_ID}@r0001",
        "decision": "approve",
        "confirmed": True,
        "actor_id": "actor-1",
        "actor_role": "ceo",
        "target_refs": [],
        "authorized_component_ids": [],
        "patch_operations": [],
        "rationale": "browser approval" if input_method == "web_hitl" else "interactive approval",
        "created_at": "2026-07-17T00:00:00Z",
        "input_method": input_method,
        "nonce_hash": "a" * 64,
        "supersedes_approval_id": None,
        "status": "current",
    }
    if input_method == "web_hitl":
        record["browser_session_fingerprint"] = "b" * 64
        record["response_hash"] = "c" * 64
    else:
        record["tty_session_fingerprint"] = "b" * 64
    record["approval_hash"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
    return record


def _final_result(input_method: str = "interactive_tty") -> dict:
    body = {
        "run_summary": {"run_id": RUN_ID, "revision": 2},
        "mission_summary": {"objective": "승인된 결과를 확인합니다."},
        "capability_summary": {"status": "limited"},
        "issues": [],
        "cross_issue_relations": [],
        "conditional_responses": [],
        "monitoring": [],
        "blind_spots": [],
        "expert_review_packets": [],
        "approvals": [
            {
                "gate": "final",
                "status": "current",
                "input_method": input_method,
                "approval_id": "approval_final",
                "actor_role": "ceo",
                "result_artifact_ref": f"{RUN_ID}@r0001",
            }
        ],
    }
    body["integrity"] = {
        "semantic_fingerprint": hashlib.sha256(canonical_bytes(body)).hexdigest()
    }
    return body


def _core() -> dict:
    return {
        "fact_register": [],
        "signal_register": [],
        "evidence_links": [],
        "source_registry": [],
        "data_quality_register": [],
        "capability_map": {
            "capability_map_id": "capability_map_empty",
            "capabilities": [],
        },
    }


def _fixture(
    root: Path,
    input_method: str = "interactive_tty",
) -> tuple[ArtifactStore, RevisionValidation]:
    store = ArtifactStore(root / "artifacts")
    store.create_run(RUN_ID)
    approval = _approval(input_method)
    store.publish(
        0,
        {
            f"approvals/records/{approval['approval_id']}.json": canonical_bytes(
                approval
            ),
            "workflow/state.json": canonical_bytes(
                {"run_id": RUN_ID, "revision": 1, "state": "delivery_approved"}
            ),
        },
    )
    store.publish(
        1,
        {
            f"approvals/records/{approval['approval_id']}.json": canonical_bytes(
                approval
            ),
            "evidence/core.json": canonical_bytes(_core()),
            "final/result.json": canonical_bytes(_final_result(input_method)),
            "final/structured-output.json": canonical_bytes(
                {"issues": [], "expert_review_packets": []}
            ),
            "workflow/state.json": canonical_bytes(
                {"run_id": RUN_ID, "revision": 2, "state": "finalized"}
            ),
        },
    )
    snapshot = store.verify_revision(2)
    manifest = strict_loads((snapshot / "snapshot-manifest.json").read_bytes())
    files = {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }
    return store, RevisionValidation(
        revision=2,
        snapshot=snapshot,
        snapshot_manifest=manifest,
        files=files,
        checks=(
            "snapshot_manifest",
            "full_snapshot_contracts",
            "evidence_core",
            "grade_recomputation",
            "final_package",
        ),
    )


class WebReportExporterTests(unittest.TestCase):
    def test_web_hitl_final_approval_exports_as_trusted_final(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, validation = _fixture(Path(directory), "web_hitl")
            with patch(
                "trusted_ceo_agent.web_report.exporter.validate_revision",
                return_value=validation,
            ):
                exported = export_web_report(store, run_id=RUN_ID, revision=2)

        receipt = exported.bundle["viewer_eligibility_receipt"]
        self.assertEqual("trusted_final", receipt["claimed_viewer_mode"])
        self.assertEqual("web_hitl", receipt["final_approval_summary"]["input_method"])

    def test_export_requires_finalized_state_and_all_required_checks(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, validation = _fixture(Path(directory))
            not_final = dict(validation.files)
            not_final["workflow/state.json"] = canonical_bytes(
                {"run_id": RUN_ID, "revision": 2, "state": "writer_ready"}
            )
            with patch(
                "trusted_ceo_agent.web_report.exporter.validate_revision",
                return_value=RevisionValidation(
                    revision=2,
                    snapshot=validation.snapshot,
                    snapshot_manifest=validation.snapshot_manifest,
                    files=not_final,
                    checks=validation.checks,
                ),
            ), self.assertRaisesRegex(IntegrityError, "finalized"):
                export_web_report(store, run_id=RUN_ID, revision=2)

            with patch(
                "trusted_ceo_agent.web_report.exporter.validate_revision",
                return_value=RevisionValidation(
                    revision=2,
                    snapshot=validation.snapshot,
                    snapshot_manifest=validation.snapshot_manifest,
                    files=validation.files,
                    checks=tuple(
                        check
                        for check in validation.checks
                        if check != "grade_recomputation"
                    ),
                ),
            ), self.assertRaisesRegex(IntegrityError, "grade_recomputation"):
                export_web_report(store, run_id=RUN_ID, revision=2)

    def test_same_revision_exports_byte_identically_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, validation = _fixture(Path(directory))
            state_before = store.state()
            manifest_before = (
                store.verify_revision(2) / "snapshot-manifest.json"
            ).read_bytes()

            with patch(
                "trusted_ceo_agent.web_report.exporter.validate_revision",
                return_value=validation,
            ):
                first = export_web_report(store, run_id=RUN_ID, revision=2)
                second = export_web_report(store, run_id=RUN_ID, revision=2)

            self.assertEqual(first.payload, second.payload)
            self.assertEqual(
                first.bundle["bundle_hash"],
                second.bundle["bundle_hash"],
            )
            self.assertEqual(jcs_bytes(first.bundle), first.payload)
            self.assertEqual("trusted_final", first.bundle[
                "viewer_eligibility_receipt"
            ]["claimed_viewer_mode"])
            self.assertEqual(state_before, store.state())
            self.assertEqual(
                manifest_before,
                (store.verify_revision(2) / "snapshot-manifest.json").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
