from __future__ import annotations

import json
import unittest

from tests.unit.outputs.test_professional_publication_from_files import (
    FILE_RUN_ID,
    _files,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.runtime_finalization import (
    build_delivery_package,
    prepare_finalization,
)


class ProfessionalFinalizationTests(unittest.TestCase):
    def test_verified_professional_artifacts_are_the_only_published_analysis(self) -> None:
        files, professional_inputs = _files()
        files.update({
            "mission/mission-contract.json": canonical_bytes(
                {"objective": "Publish verified professional findings."}
            ),
            "workflow/hitl-overlay.json": canonical_bytes({}),
        })

        updates, data = prepare_finalization(
            files,
            run_id=FILE_RUN_ID,
            revision=8,
            parent_artifact_hash="9" * 64,
        )

        structured = json.loads(
            updates["final/structured-output.json"].decode("utf-8")
        )
        self.assertEqual(
            [item["case_id"] for item in professional_inputs["findings"]],
            [item["issue_id"] for item in structured["issues"]],
        )
        self.assertEqual(
            professional_inputs["relations"][0]["relation_id"],
            structured["cross_issue_relations"][0]["relation_id"],
        )
        self.assertIn("final/professional-publication.json", updates)
        self.assertEqual(2, data["active_issue_count"])
        self.assertEqual("full", data["effective_authority"])
        self.assertEqual("Full", data["product_display"])
        advanced_core = json.loads(updates["evidence/core.json"].decode("utf-8"))
        self.assertEqual(8, advanced_core["envelope"]["revision"])

        published = {**files, **updates}
        published["approvals/records/approval_final.json"] = canonical_bytes({
            "approval_id": "approval_final",
            "gate": "final",
            "status": "current",
            "input_method": "interactive_tty",
            "actor_role": "ceo",
            "result_artifact_ref": f"{FILE_RUN_ID}@r0008",
        })
        package = build_delivery_package(
            published,
            run_id=FILE_RUN_ID,
            revision=9,
        )
        result = json.loads(package["final/result.json"].decode("utf-8"))
        self.assertEqual(
            [item["case_id"] for item in professional_inputs["findings"]],
            [item["issue_id"] for item in result["issues"]],
        )
        self.assertEqual(
            structured["cross_issue_relations"],
            result["cross_issue_relations"],
        )

    def test_delivery_rejects_structured_output_changed_after_publication(self) -> None:
        files, _ = _files()
        files.update({
            "mission/mission-contract.json": canonical_bytes(
                {"objective": "Publish verified professional findings."}
            ),
            "workflow/hitl-overlay.json": canonical_bytes({}),
        })
        updates, _ = prepare_finalization(
            files,
            run_id=FILE_RUN_ID,
            revision=8,
            parent_artifact_hash="9" * 64,
        )
        tampered = {**files, **updates}
        structured = json.loads(
            tampered["final/structured-output.json"].decode("utf-8")
        )
        structured["issues"][0]["title_template"] = "Tampered conclusion"
        tampered["final/structured-output.json"] = canonical_bytes(structured)

        with self.assertRaisesRegex(
            IntegrityError, "professional publication structured output mismatch"
        ):
            build_delivery_package(
                tampered,
                run_id=FILE_RUN_ID,
                revision=9,
            )


if __name__ == "__main__":
    unittest.main()
