import copy
import hashlib
import json
import unittest
from pathlib import Path

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.components.plans import (
    PlanContractError,
    execute_materialized_plan,
    materialize_component_plan,
)


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


def _fact(identifier: str, code: str, value: str, *, member: str, period: str) -> dict:
    return {
        "fact_id": identifier,
        "fact_code": code,
        "observation_role": "ledger",
        "scope": [{"dimension_code": "portfolio", "member_code": member}],
        "time_context": {"period": period},
        "value": {"value_type": "decimal", "canonical_value": value, "unit_code": "KRW"},
    }


def _snapshot_files(problem: dict, domain: dict) -> tuple[dict[str, bytes], dict]:
    documents = [domain, problem]
    entries = []
    files: dict[str, bytes] = {}
    for document in documents:
        payload = canonical_bytes(document)
        digest = hashlib.sha256(payload).hexdigest()
        entries.append({
            "pack_type": document["pack_type"],
            "pack_id": document["pack_id"],
            "pack_version": document["pack_version"],
            "pack_sha256": digest,
            "effective_authority": "provisional",
        })
        files[f"packs/snapshots/{digest}.json"] = payload
    entries.sort(key=lambda item: (item["pack_type"], item["pack_id"], item["pack_version"]))
    body = {"schema_version": "1.0.0", "packs": entries}
    manifest = {**body, "manifest_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    files["packs/manifest.json"] = canonical_bytes(manifest)
    return files, manifest


class ComponentPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.domain = json.loads((
            PLUGIN_ROOT / "packs" / "domain" / "b2b-services" / "1.0.0" / "pack.json"
        ).read_text("utf-8"))
        self.problem = json.loads((
            PLUGIN_ROOT / "packs" / "problem" / "customer-concentration" / "1.0.0" / "pack.json"
        ).read_text("utf-8"))

    def _arguments(self, facts: list[dict]) -> dict:
        files, manifest = _snapshot_files(self.problem, self.domain)
        return {
            "files": files,
            "core": {
                "envelope": {"artifact_hash": "a" * 64},
                "pack_manifest": {
                    "pack_manifest_hash": manifest["manifest_hash"],
                    "pack_refs": ["b2b-services@1.0.0", "customer-concentration@1.0.0"],
                },
                "fact_register": facts,
            },
            "stage": "deep_dive",
            "integrated_assessment": {"payload": {"integrated_issues": [{
                "local_key": "issue_customer",
                "payload": {
                    "problem_family_ref": "customer-concentration@1.0.0",
                    "scope_key": "portfolio-a",
                },
            }]}},
            "approved_scope": {
                "issue_ids": ["issue_customer"],
                "component_ids": ["reconcile"],
            },
        }

    def test_materializes_exact_ids_and_domain_threshold_from_snapshots(self) -> None:
        facts = [
            _fact("fact_" + "1" * 24, "revenue", "100", member="portfolio-a", period="2026-03"),
            _fact("fact_" + "2" * 24, "customer_revenue", "60", member="portfolio-a", period="2026-03"),
            _fact("fact_" + "3" * 24, "customer_revenue", "40", member="portfolio-a", period="2026-03"),
            _fact("fact_" + "4" * 24, "revenue", "90", member="portfolio-a", period="2026-02"),
        ]
        result = materialize_component_plan(**self._arguments(list(reversed(facts))))
        self.assertEqual(1, len(result.entries))
        entry = result.entries[0]
        self.assertEqual("ready", entry["status"])
        self.assertEqual("fact_" + "1" * 24, entry["parameters"]["total_fact_id"])
        self.assertEqual(
            ["fact_" + "2" * 24, "fact_" + "3" * 24],
            entry["parameters"]["part_fact_ids"],
        )
        self.assertEqual(
            ["fact_" + "1" * 24, "fact_" + "2" * 24, "fact_" + "3" * 24],
            entry["input_fact_ids"],
        )
        self.assertEqual("0.01", result.thresholds["reconciliation_tolerance_ratio"]["value"])
        self.assertEqual(
            ["b2b-services@1.0.0", "customer-concentration@1.0.0"],
            entry["pack_refs"],
        )

    def test_valid_selector_with_no_fact_is_not_assessable(self) -> None:
        result = materialize_component_plan(**self._arguments([]))
        self.assertEqual("not_assessable", result.entries[0]["status"])
        self.assertEqual(["missing_input_fact"], result.entries[0]["reason_codes"])
        runs = execute_materialized_plan(result, [], input_artifact_hash="a" * 64)
        self.assertEqual(1, len(runs))
        self.assertEqual("not_assessable", runs[0].status)
        self.assertEqual(("missing_input_fact",), runs[0].reason_codes)

    def test_ready_plan_executes_with_only_bound_facts(self) -> None:
        facts = [
            _fact("fact_" + "1" * 24, "revenue", "100", member="portfolio-a", period="2026-03"),
            _fact("fact_" + "2" * 24, "customer_revenue", "60", member="portfolio-a", period="2026-03"),
            _fact("fact_" + "3" * 24, "customer_revenue", "40", member="portfolio-a", period="2026-03"),
            _fact("fact_" + "9" * 24, "unrelated", "5", member="portfolio-a", period="2026-03"),
        ]
        result = materialize_component_plan(**self._arguments(facts))
        runs = execute_materialized_plan(result, facts, input_artifact_hash="a" * 64, max_workers=4)
        self.assertEqual("completed", runs[0].status)
        self.assertEqual(
            ("fact_" + "1" * 24, "fact_" + "2" * 24, "fact_" + "3" * 24),
            runs[0].sorted_input_fact_ids,
        )

    def test_malformed_template_is_contract_failure_even_without_facts(self) -> None:
        del self.problem["content"]["deep_dive_plan"][0]["parameter_template"]["output_signal_code"]
        with self.assertRaises(PlanContractError) as captured:
            materialize_component_plan(**self._arguments([]))
        self.assertEqual("invalid_parameter_template", captured.exception.reason_code)

    def test_missing_threshold_is_pack_contract_failure_before_fact_resolution(self) -> None:
        invalid = copy.deepcopy(self.problem)
        invalid["content"]["deep_dive_plan"][0]["parameter_template"]["tolerance_ref"] = "absent"
        self.problem = invalid
        with self.assertRaises(PlanContractError) as captured:
            materialize_component_plan(**self._arguments([]))
        self.assertEqual("missing_threshold_ref", captured.exception.reason_code)

    def test_snapshot_hash_mismatch_is_contract_failure(self) -> None:
        arguments = self._arguments([])
        snapshot_path = next(path for path in arguments["files"] if path.startswith("packs/snapshots/"))
        arguments["files"][snapshot_path] += b" "
        with self.assertRaises(PlanContractError) as captured:
            materialize_component_plan(**arguments)
        self.assertEqual("pack_snapshot_hash_mismatch", captured.exception.reason_code)


if __name__ == "__main__":
    unittest.main()
