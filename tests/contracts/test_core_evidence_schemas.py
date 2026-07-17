import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


SHA = "a" * 64


def source_reference() -> dict:
    return {
        "source_id": "source_" + "a" * 24,
        "observation_role": "revenue_ledger",
        "locator_type": "csv_records",
        "locator": {"record_indices": [1]},
        "selected_fields": ["revenue"],
        "record_count": 1,
        "filters": [],
        "group_by": [],
        "operation": "observe",
        "normalized_rows_hash": SHA,
        "row_multiset_hash": SHA,
        "lineage_set_ref": f"lineage/sets/{SHA}.json",
        "extraction_hash": SHA,
    }


def observed_fact() -> dict:
    return {
        "fact_id": "fact_" + "b" * 24,
        "fact_code": "revenue.observed",
        "fact_type": "observed",
        "metric_code": "revenue",
        "semantic_role": "observation",
        "observation_role": "revenue_ledger",
        "scope": [{"dimension_code": "business_unit", "member_code": "all"}],
        "time_context": {"period": "2026-01"},
        "value": {
            "value_type": "decimal",
            "canonical_value": "100",
            "unit_code": "currency",
            "currency_code": "KRW",
            "scale": "1",
        },
        "source_refs": [source_reference()],
        "derivation": None,
        "quality": [],
        "producer": "runtime_intake",
        "integrity": {"payload_hash": SHA},
    }


class CoreSchemaContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SchemaStore()

    def test_all_owned_core_schemas_are_valid_local_resources(self) -> None:
        names = (
            "source.schema.json", "source-reference.schema.json", "source-resolver.schema.json",
            "data-quality.schema.json", "lineage-set.schema.json", "fact.schema.json",
            "signal.schema.json", "evidence-link.schema.json", "capability-map.schema.json",
            "evidence-core.schema.json", "mission-contract.schema.json", "snapshot-manifest.schema.json",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIsInstance(self.store.load(name), dict)

    def test_source_fact_and_reference_accept_valid_payloads(self) -> None:
        source = {
            "source_id": "source_" + "a" * 24,
            "source_type": "uploaded_file",
            "access_policy": "permitted",
            "evidence_usage": "primary",
            "observation_roles": ["revenue_ledger"],
            "display_name": "ledger.csv",
            "media_type": "text/csv",
            "sha256": SHA,
            "size_bytes": 10,
            "received_at": "2026-07-17T00:00:00Z",
            "snapshot_ref": f"sources/blobs/{SHA}",
            "original_path_token": "path_" + "c" * 24,
            "aliases": [],
            "metadata": {},
        }
        self.store.validate("source.schema.json", source)
        self.store.validate("source-reference.schema.json", source_reference())
        self.store.validate("fact.schema.json", observed_fact())

    def test_unknown_properties_and_invalid_observed_derivation_are_rejected(self) -> None:
        fact = observed_fact()
        fact["model_confidence"] = 0.9
        with self.assertRaises(ContractError):
            self.store.validate("fact.schema.json", fact)

        fact = observed_fact()
        fact["derivation"] = {
            "component_id": "ratio",
            "component_version": "1.0.0",
            "operation_code": "ratio",
            "formula_ref": "ratio.v1",
            "parameter_hash": SHA,
            "input_fact_ids": [fact["fact_id"]],
            "component_run_id": "component_run_" + "d" * 24,
        }
        with self.assertRaises(ContractError):
            self.store.validate("fact.schema.json", fact)

    def test_not_assessable_signal_requires_missing_fact_or_reason(self) -> None:
        signal = {
            "signal_id": "signal_" + "d" * 24,
            "signal_code": "margin.not_assessable",
            "rule_ref": "rule.margin.v1",
            "component_ref": {
                "component_id": "compare",
                "component_version": "1.0.0",
                "component_run_id": "component_run_" + "e" * 24,
            },
            "threshold_ref": None,
            "input_fact_ids": [],
            "required_fact_codes": ["gross_margin"],
            "missing_fact_codes": [],
            "scope": [],
            "time_context": {"period": "2026-01"},
            "evaluation": {},
            "outcome": "not_assessable",
            "direction": None,
            "impact_band_candidate": None,
            "urgency_band_candidate": None,
            "reason_codes": [],
            "producer": "deterministic_component",
        }
        with self.assertRaises(ContractError):
            self.store.validate("signal.schema.json", signal)
        signal["missing_fact_codes"] = ["gross_margin"]
        self.store.validate("signal.schema.json", signal)

    def test_customer_hypothesis_must_remain_unverified(self) -> None:
        mission = {
            "mission_contract_id": "mission_" + "f" * 24,
            "contract_version": "1.0.0",
            "business_question": "Find material hidden issues",
            "business_model": "B2B services",
            "current_symptoms": [],
            "customer_hypotheses": [{
                "hypothesis_id": "hypothesis_" + "1" * 24,
                "statement": "Payroll caused the decline",
                "status": "verified",
                "source": "customer",
            }],
            "decision_context": "portfolio review",
            "decision_units": [],
            "decision_deadline": None,
            "analysis_horizon": {"start": "2025-01-01", "end": "2026-06-30"},
            "organization_scope": [],
            "priority_dimensions": [],
            "constraints": [],
            "recent_business_changes": [],
            "recent_organization_changes": [],
            "recent_policy_changes": [],
            "included_scopes": [],
            "excluded_scopes": [],
            "comparison_preferences": [],
            "materiality_context": {},
            "data_definitions": [],
            "confidentiality": "confidential",
            "required_human_roles": ["ceo"],
            "confirmation": {
                "confirmed": True,
                "actor_id": "actor-1",
                "actor_role": "ceo",
                "confirmed_at": "2026-07-17T00:00:00Z",
                "contract_hash": SHA,
            },
        }
        with self.assertRaises(ContractError):
            self.store.validate("mission-contract.schema.json", mission)
        mission["customer_hypotheses"][0]["status"] = "unverified"
        self.store.validate("mission-contract.schema.json", mission)

    def test_snapshot_manifest_rejects_unsafe_paths(self) -> None:
        manifest = {
            "revision": 1,
            "parent_revision": 0,
            "files": [{"path": "../escape.json", "sha256": SHA, "size": 1}],
            "manifest_hash": SHA,
        }
        with self.assertRaises(ContractError):
            self.store.validate("snapshot-manifest.schema.json", manifest)

    def test_remote_and_escaping_refs_are_rejected_before_validation(self) -> None:
        for ref in ("https://example.com/schema.json", "file:///tmp/schema.json", "../outside.json"):
            with self.subTest(ref=ref), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "bad.schema.json").write_text(json.dumps({
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": ref,
                }), encoding="utf-8")
                with self.assertRaises(ContractError):
                    SchemaStore(root).load("bad.schema.json")


if __name__ == "__main__":
    unittest.main()
