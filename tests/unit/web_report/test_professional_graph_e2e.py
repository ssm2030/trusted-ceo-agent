from __future__ import annotations

import json
import unittest

from tests.unit.outputs.test_professional_publication_from_files import (
    FILE_RUN_ID,
    _files,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.runtime_finalization import (
    build_delivery_package,
    prepare_finalization,
)
from trusted_ceo_agent.web_report.closure import build_evidence_closure
from trusted_ceo_agent.web_report.presentation import build_presentation_manifest


class ProfessionalGraphEndToEndTests(unittest.TestCase):
    def test_findings_and_verified_relations_project_exactly_to_graph_arrays(self) -> None:
        files, inputs = _files()
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
        core = json.loads(updates["evidence/core.json"].decode("utf-8"))
        graph = build_presentation_manifest(
            result,
            build_evidence_closure(result, core),
        )["issue_graph"]

        self.assertEqual(
            sorted(item["case_id"] for item in inputs["findings"]),
            [item["issue_ref"] for item in graph["nodes"]],
        )
        self.assertEqual(
            [{
                "relation_id": inputs["relations"][0]["relation_id"],
                "from_issue_ref": inputs["findings"][0]["case_id"],
                "to_issue_ref": inputs["findings"][1]["case_id"],
                "relation_type": inputs["relations"][0]["relation_type"],
            }],
            graph["edges"],
        )
        grade_by_issue = {
            item["issue_id"]: item["primary_grade"]
            for item in inputs["grade_records"]
        }
        self.assertEqual(
            grade_by_issue,
            {item["issue_ref"]: item["grade"] for item in graph["nodes"]},
        )


if __name__ == "__main__":
    unittest.main()
