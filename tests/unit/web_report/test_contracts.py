from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256
from trusted_ceo_agent.web_report.contracts import (
    MAX_BUNDLE_BYTES,
    MAX_CHARTS,
    MAX_CHART_POINTS,
    MAX_ISSUES,
    MAX_PREVIEW_BYTES,
    WebReportContractError,
    load_bundle_bytes,
    validate_bundle_document,
    validate_eligibility_decision,
)
from trusted_ceo_agent.web_report.contract_semantics import (
    validate_bundle_document as semantic_validator,
)


FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "web-report"
    / "v1"
    / "fixtures"
)


class WebReportContractModuleBoundaryTests(unittest.TestCase):
    def test_semantic_validator_is_reexported_by_contract_facade(self) -> None:
        self.assertIs(validate_bundle_document, semantic_validator)


def _valid_bundle() -> dict:
    return json.loads(
        (FIXTURES / "valid-unverified-import.json").read_text(encoding="utf-8")
    )


def _rehash_bundle(bundle: dict, *, previews: bool = False) -> dict:
    if previews:
        for preview in bundle["source_previews"]:
            preview["preview_hash"] = jcs_sha256(
                preview,
                omit_root_field="preview_hash",
            )
    bundle["bundle_hash"] = jcs_sha256(bundle, omit_root_field="bundle_hash")
    return bundle


def _attach_expert_packet(bundle: dict) -> dict:
    packet = {
        "expert_packet_id": "packet_main",
        "profession": "legal",
        "target_issue_ref": "issue_main",
        "fact_refs": ["fact_main"],
        "evidence_link_ids": ["evidence_main"],
        "source_refs": ["source_main"],
        "cause_hypotheses": ["cause_main"],
        "counter_hypotheses": [],
        "unresolved_uncertainties": [],
        "required_document_refs": ["document_main"],
        "review_question": "Review the supplied evidence.",
        "forbidden_conclusions": [],
        "source_locators": [{"source_ref": "source_main", "locator": "row 1"}],
        "run_id": bundle["run"]["run_id"],
        "revision": bundle["run"]["revision"],
        "packet_hash": "0" * 64,
    }
    packet["packet_hash"] = jcs_sha256(packet, omit_root_field="packet_hash")
    bundle["expert_packet_view"] = [packet]
    return bundle


class WebReportContractBoundaryTests(unittest.TestCase):
    def test_size_is_rejected_before_json_parsing(self) -> None:
        payload = b"{" + (b" " * MAX_BUNDLE_BYTES)

        with self.assertRaisesRegex(WebReportContractError, "52_428_800"):
            load_bundle_bytes(payload)

    def test_strict_json_rejects_duplicate_keys(self) -> None:
        with self.assertRaisesRegex(WebReportContractError, "invalid web report JSON"):
            load_bundle_bytes(b'{"bundle_version":"1.0.0","bundle_version":"1.0.0"}')

    def test_bundle_root_must_be_an_object(self) -> None:
        with self.assertRaisesRegex(
            WebReportContractError,
            "web report bundle must be an object",
        ):
            load_bundle_bytes(b"[]")


class WebReportContractSemanticBoundaryTests(unittest.TestCase):
    def test_direct_semantics_enforces_all_array_caps(self) -> None:
        bundle = _valid_bundle()
        issue = bundle["final_result"]["issues"][0]
        bundle["final_result"]["issues"] = [
            {**copy.deepcopy(issue), "issue_id": f"issue_{index:04d}"}
            for index in range(MAX_ISSUES + 1)
        ]
        with self.assertRaisesRegex(WebReportContractError, "more than 500 issues"):
            validate_bundle_document(bundle)

        bundle = _valid_bundle()
        bundle["presentation_manifest"]["chart_specs"] = [
            {"chart_id": f"chart_{index:04d}", "points": []}
            for index in range(MAX_CHARTS + 1)
        ]
        with self.assertRaisesRegex(WebReportContractError, "more than 50 charts"):
            validate_bundle_document(bundle)

        bundle = _valid_bundle()
        bundle["presentation_manifest"]["chart_specs"] = [
            {"chart_id": "chart_main", "points": [{}] * (MAX_CHART_POINTS + 1)}
        ]
        with self.assertRaisesRegex(WebReportContractError, "more than 5_000 points"):
            validate_bundle_document(bundle)

    def test_run_receipt_result_and_fingerprints_must_match(self) -> None:
        cases = []
        receipt = _valid_bundle()
        receipt["viewer_eligibility_receipt"]["run_id"] = "run_20260717T000000Z_bbbbbbbbbbbbbbbb"
        cases.append((receipt, "run ID mismatch"))
        result = _valid_bundle()
        result["final_result"]["run_summary"]["revision"] = 2
        cases.append((result, "revision mismatch"))
        fingerprint = _valid_bundle()
        fingerprint["final_result"]["integrity"]["semantic_fingerprint"] = "b" * 64
        cases.append((fingerprint, "semantic fingerprint mismatch"))
        for bundle, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(WebReportContractError, message):
                load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_orphan_preview_and_unknown_quality_refs_are_rejected(self) -> None:
        orphan = _valid_bundle()
        orphan["source_view"][0]["preview_refs"] = []
        with self.assertRaisesRegex(WebReportContractError, "not referenced by its Source"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(orphan)))
        quality = _valid_bundle()
        quality["evidence_view"]["facts"][0]["quality"] = ["quality_missing"]
        with self.assertRaisesRegex(WebReportContractError, "unknown data quality"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(quality)))

    def test_packet_hash_and_claim_refs_are_closed(self) -> None:
        bundle = _attach_expert_packet(_valid_bundle())
        load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))
        bundle["expert_packet_view"][0]["review_question"] = "Tampered"
        with self.assertRaisesRegex(WebReportContractError, "expert packet hash"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

        bundle = _attach_expert_packet(_valid_bundle())
        bundle["expert_packet_view"][0]["cause_hypotheses"] = ["claim_missing"]
        bundle["expert_packet_view"][0]["packet_hash"] = jcs_sha256(
            bundle["expert_packet_view"][0], omit_root_field="packet_hash"
        )
        with self.assertRaisesRegex(WebReportContractError, "unknown claim reference"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_id_set_arrays_must_be_sorted(self) -> None:
        bundle = _valid_bundle()
        bundle["trust_view"]["limitations"] = ["z_limit", "a_limit"]
        with self.assertRaisesRegex(WebReportContractError, "limitations must be sorted"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_duplicate_id_precedes_dangling_reference(self) -> None:
        bundle = _valid_bundle()
        bundle["final_result"]["issues"][0]["evidence_link_ids"] = [
            "evidence_missing"
        ]
        duplicate = copy.deepcopy(bundle["final_result"]["issues"][0])
        duplicate["title_template"] = "중복 문제"
        bundle["final_result"]["issues"].append(duplicate)
        with self.assertRaisesRegex(WebReportContractError, "duplicate issue ID"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_dangling_issue_evidence_fact_source_and_preview_refs_are_rejected(
        self,
    ) -> None:
        cases = []
        issue = _valid_bundle()
        issue["presentation_manifest"]["ceo_summary_issue_refs"] = ["issue_missing"]
        cases.append((issue, "unknown issue reference"))
        link = _valid_bundle()
        link["final_result"]["issues"][0]["evidence_link_ids"] = [
            "evidence_missing"
        ]
        cases.append((link, "unknown Evidence Link"))
        fact = _valid_bundle()
        fact["evidence_view"]["evidence_links"][0]["evidence_ref"] = "fact_missing"
        cases.append((fact, "unknown evidence reference"))
        source = _valid_bundle()
        source["evidence_view"]["facts"][0]["source_refs"][0]["source_id"] = (
            "source_missing"
        )
        cases.append((source, "unknown Source"))
        preview = _valid_bundle()
        preview["source_view"][0]["preview_refs"] = ["preview_missing"]
        cases.append((preview, "unknown source preview"))
        for bundle, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                WebReportContractError,
                message,
            ):
                load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_preview_hash_is_checked_before_bundle_hash(self) -> None:
        bundle = _valid_bundle()
        bundle["source_previews"][0]["rows"][0][0] = "101"
        with self.assertRaisesRegex(WebReportContractError, "preview hash"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_bundle_hash_detects_other_tampering(self) -> None:
        bundle = _valid_bundle()
        bundle["final_result"]["issues"][0]["title_template"] = "변조"
        bundle["presentation_manifest"]["issue_graph"]["nodes"][0][
            "label_ko"
        ] = bundle["final_result"]["issues"][0]["title_template"]
        with self.assertRaisesRegex(WebReportContractError, "bundle hash"):
            load_bundle_bytes(jcs_bytes(bundle))

    def test_preview_budget_is_enforced_on_jcs_bytes(self) -> None:
        bundle = _valid_bundle()
        bundle["source_previews"][0]["rows"] = [["x" * MAX_PREVIEW_BYTES]]
        _rehash_bundle(bundle, previews=True)
        with self.assertRaisesRegex(WebReportContractError, "10_485_760"):
            validate_bundle_document(bundle)

    def test_absolute_paths_are_rejected_after_integrity_checks(self) -> None:
        bundle = _valid_bundle()
        bundle["source_view"][0]["display_name_ko"] = r"C:\secret\ledger.csv"
        with self.assertRaisesRegex(WebReportContractError, "absolute paths"):
            load_bundle_bytes(jcs_bytes(_rehash_bundle(bundle)))

    def test_restricted_preview_cannot_embed_values(self) -> None:
        bundle = _valid_bundle()
        bundle["source_view"][0]["access_policy"] = "restricted"
        bundle["source_previews"][0]["access_policy"] = "restricted"
        bundle["source_previews"][0]["masking_status"] = "restricted"
        _rehash_bundle(bundle, previews=True)
        with self.assertRaisesRegex(WebReportContractError, "restricted preview"):
            validate_bundle_document(bundle)

    def test_eligibility_decision_uses_the_frozen_schema(self) -> None:
        decision = {
            "decision_version": "1.0.0",
            "eligible": False,
            "viewer_mode": "rejected",
            "badge_label_ko": "열 수 없는 묶음",
            "run_id": None,
            "revision": None,
            "bundle_hash": None,
            "completed_checks": [],
            "failure_code": "BUNDLE_SCHEMA_INVALID",
            "failure_message": "invalid",
        }
        validate_eligibility_decision(decision)
        decision["unknown"] = True
        with self.assertRaises(WebReportContractError):
            validate_eligibility_decision(decision)

    def test_eligibility_decision_mode_badge_and_failure_are_consistent(self) -> None:
        decision = {
            "decision_version": "1.0.0", "eligible": True,
            "viewer_mode": "trusted_final", "badge_label_ko": "출처 미확인 묶음",
            "run_id": "run_1", "revision": 1, "bundle_hash": "a" * 64,
            "completed_checks": [], "failure_code": None, "failure_message": None,
        }
        with self.assertRaisesRegex(WebReportContractError, "badge label"):
            validate_eligibility_decision(decision)
        decision.update({"viewer_mode": "rejected", "badge_label_ko": "열 수 없는 묶음", "eligible": False})
        with self.assertRaisesRegex(WebReportContractError, "failure code and message"):
            validate_eligibility_decision(decision)


    def test_issue_graph_exactly_projects_final_result_values(self) -> None:
        node_mismatch = _valid_bundle()
        node_mismatch["presentation_manifest"]["issue_graph"]["nodes"][0][
            "label_ko"
        ] = "tampered label"
        with self.assertRaisesRegex(
            WebReportContractError,
            "graph node differs",
        ):
            validate_bundle_document(node_mismatch)

        edge_mismatch = _valid_bundle()
        peer = copy.deepcopy(edge_mismatch["final_result"]["issues"][0])
        peer["issue_id"] = "issue_peer"
        edge_mismatch["final_result"]["issues"].append(peer)
        edge_mismatch["presentation_manifest"]["issue_graph"]["nodes"].append({
            "issue_ref": "issue_peer",
            "label_ko": peer["title_template"],
            "grade": peer["primary_grade"],
        })
        relation = {
            "relation_id": "relation_main",
            "from_issue_ref": "issue_main",
            "to_issue_ref": "issue_peer",
            "relation_type": "supports",
        }
        edge_mismatch["final_result"]["cross_issue_relations"].append(relation)
        edge_mismatch["presentation_manifest"]["issue_graph"]["edges"].append({
            **relation,
            "relation_type": "contradicts",
        })
        with self.assertRaisesRegex(
            WebReportContractError,
            "graph edge differs",
        ):
            validate_bundle_document(edge_mismatch)

if __name__ == "__main__":
    unittest.main()
