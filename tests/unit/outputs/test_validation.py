import unittest

import trusted_ceo_agent.outputs as outputs
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.outputs import validation
from trusted_ceo_agent.outputs.audit import build_audit_manifest
from trusted_ceo_agent.outputs.render import render_package


def _issue() -> dict:
    return {
        "issue_id": "issue_a",
        "title_template": "Issue A",
        "primary_grade": "Decision Required",
        "secondary_flags": [],
        "why_it_matters_template": "Evidence-backed issue.",
        "value_refs": ["fact_a"],
        "evidence_link_ids": ["link_a"],
        "cause_hypotheses": [],
        "counter_hypotheses": [],
        "unresolved_conflicts": [],
        "verification_next_steps": [],
        "conditional_response_refs": [],
        "expert_review_refs": [],
    }


def _result() -> dict:
    return {
        "run_summary": {"run_id": "run_x", "revision": 4},
        "mission_summary": {"objective": "diagnose"},
        "capability_summary": {"status": "sufficient"},
        "issues": [_issue()],
        "cross_issue_relations": [],
        "conditional_responses": [],
        "monitoring": [],
        "blind_spots": [],
        "expert_review_packets": [],
        "approvals": [{"gate": "final", "status": "current"}],
        "integrity": {"semantic_fingerprint": "a" * 64},
    }


def _evidence_links() -> dict:
    return {"link_a": {"source_ids": ["source_a"]}}


class ValidationSummaryTests(unittest.TestCase):
    def test_summary_names_only_the_check_it_performs(self) -> None:
        summary = validation.validation_summary({"issues": [], "approvals": []})

        self.assertEqual(["absolute_path_redaction"], summary["checks"])

    def test_windows_unc_absolute_path_is_rejected(self) -> None:
        with self.assertRaises(validation.FinalValidationError):
            validation.validation_summary(
                {"issues": [], "source_hint": r"\\server\share\source.xlsx"}
            )

    def test_absolute_path_embedded_in_customer_text_is_rejected(self) -> None:
        with self.assertRaises(validation.FinalValidationError):
            validation.validation_summary(
                {
                    "issues": [],
                    "note": r"Source snapshot was C:\Users\analyst\secret.xlsx",
                }
            )

    def test_structured_source_json_pointer_is_not_treated_as_a_file_path(self) -> None:
        validation.validate_no_absolute_paths({
            "source_refs": [{
                "locator": {"pointer": "/0/gross_margin"},
            }],
            "preview": {"json_pointer": "/0/gross_margin"},
        })

    def test_unstructured_pointer_field_cannot_hide_an_absolute_path(self) -> None:
        with self.assertRaises(validation.FinalValidationError):
            validation.validate_no_absolute_paths({"pointer": r"C:\Users\secret.txt"})
        with self.assertRaises(validation.FinalValidationError):
            validation.validate_no_absolute_paths({
                "source_ref": {"locator": {"pointer": r"C:\Users\secret.txt"}},
            })

    def test_validate_final_result_performs_all_contextual_checks(self) -> None:
        validator = getattr(validation, "validate_final_result", None)
        self.assertIsNotNone(validator)

        summary = validator(_result(), evidence_links=_evidence_links())

        self.assertEqual(
            [
                "active_evidence_link_reachability",
                "final_approval_current",
                "absolute_path_redaction",
                "final_result_schema",
            ],
            summary["checks"],
        )

    def test_schema_rejects_malformed_issue_shape_as_final_validation_error(self) -> None:
        malformed = _result()
        malformed["issues"] = {"not": "an array"}

        captured = None
        try:
            validation.validate_final_result(
                malformed,
                evidence_links=_evidence_links(),
            )
        except Exception as exc:  # noqa: BLE001 - assert the public error boundary
            captured = exc

        self.assertIsInstance(captured, validation.FinalValidationError)

    def test_revalidate_package_verifies_audit_and_byte_equivalent_rerender(self) -> None:
        revalidate = getattr(outputs, "revalidate_package", None)
        self.assertIsNotNone(revalidate)

        result = _result()
        summary = revalidate(
            result,
            render_package(result),
            evidence_links=_evidence_links(),
        )

        self.assertEqual(
            [
                "active_evidence_link_reachability",
                "final_approval_current",
                "absolute_path_redaction",
                "final_result_schema",
                "audit_manifest",
                "deterministic_rerender_byte_equivalence",
            ],
            summary["checks"],
        )

    def test_revalidate_package_rejects_audit_manifest_mismatch(self) -> None:
        result = _result()
        package = render_package(result)
        package["final/ceo-brief.md"] += b"tampered"

        with self.assertRaisesRegex(validation.FinalValidationError, "audit manifest"):
            outputs.revalidate_package(
                result,
                package,
                evidence_links=_evidence_links(),
            )

    def test_revalidate_package_rejects_non_deterministic_bytes_after_reaudit(self) -> None:
        result = _result()
        package = render_package(result)
        package["final/ceo-brief.md"] += b"tampered"
        covered = {
            path: payload
            for path, payload in package.items()
            if path != "final/audit-manifest.json"
        }
        package["final/audit-manifest.json"] = canonical_bytes(
            build_audit_manifest(covered)
        )

        with self.assertRaisesRegex(
            validation.FinalValidationError,
            "differs at final/ceo-brief.md",
        ):
            outputs.revalidate_package(
                result,
                package,
                evidence_links=_evidence_links(),
            )


if __name__ == "__main__":
    unittest.main()
