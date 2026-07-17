import unittest

from trusted_ceo_agent.intake.mapping import (
    build_canonical_mapping_proposal,
    resolve_confirmed_mappings,
)
from trusted_ceo_agent.intake.materialize import materialize_observed_facts
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord


METRICS = [
    {
        "metric_code": "revenue",
        "accepted_observation_roles": ["ledger"],
        "data_type": "decimal",
        "unit_policy": "single_currency_or_verified_conversion",
        "time_role": "recognition_period",
        "allowed_dimensions": ["customer"],
    }
]


class CanonicalMappingTests(unittest.TestCase):
    def _dataset(self) -> ParsedDataset:
        return ParsedDataset(
            source_id="source_" + "a" * 24,
            media_type="application/json",
            fields=("period", "revenue", "Revenue Alias", "scope.customer"),
            records=(
                ParsedRecord(
                    1,
                    "json_pointer",
                    {"pointer": "/0"},
                    {
                        "period": "2026-01",
                        "revenue": "100",
                        "Revenue Alias": "100",
                        "scope.customer": "customer-a",
                    },
                ),
            ),
        )

    def test_proposal_uses_only_exact_metric_and_structural_headers(self) -> None:
        dataset = self._dataset()

        proposal = build_canonical_mapping_proposal(dataset, METRICS)

        self.assertEqual(1, len(proposal["mappings"]))
        mapping = proposal["mappings"][0]
        self.assertTrue(mapping["mapping_question_ref"].startswith("mappingquestion_"))
        self.assertTrue(mapping["source_field_ref"].startswith("sourcefield_"))
        self.assertEqual("revenue", mapping["candidate_mappings"][0]["metric_code"])
        self.assertEqual("customer", mapping["candidate_mappings"][0]["dimension_code"])
        self.assertEqual(2, len(mapping["candidate_mappings"][0]["supporting_header_refs"]))

    def test_data_gate_overlay_resolves_one_immutable_metric_candidate(self) -> None:
        dataset = self._dataset()
        proposal = build_canonical_mapping_proposal(dataset, METRICS)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        overlay = {
            "mapping": {
                "sources": {dataset.source_id: {"included": True}},
                "columns": {
                    question_ref: {
                        "observation_role": "ledger",
                        "unit_code": "KRW",
                        "scale": "1",
                        "time_role": "recognition_period",
                        "dimension_code": "customer",
                    }
                },
            }
        }

        resolved = resolve_confirmed_mappings(dataset, proposal, overlay, METRICS)

        self.assertEqual(1, len(resolved))
        self.assertEqual("revenue", resolved[0].source_field)
        self.assertEqual("revenue", resolved[0].metric_code)
        self.assertEqual("period", resolved[0].time_field)
        self.assertEqual((("scope.customer", "customer"),), resolved[0].scope_fields)
        self.assertEqual("KRW", resolved[0].unit_code)

    def test_confirmed_mapping_materializes_observed_fact_and_lineage_bytes(self) -> None:
        dataset = self._dataset()
        proposal = build_canonical_mapping_proposal(dataset, METRICS)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        overlay = {
            "mapping": {
                "sources": {dataset.source_id: {"included": True}},
                "columns": {
                    question_ref: {
                        "observation_role": "ledger",
                        "unit_code": "KRW",
                        "scale": "1",
                        "time_role": "recognition_period",
                        "dimension_code": "customer",
                    }
                },
            }
        }
        mappings = resolve_confirmed_mappings(dataset, proposal, overlay, METRICS)

        result = materialize_observed_facts(dataset, mappings)

        self.assertEqual(1, len(result.fact_register))
        self.assertEqual((), result.data_quality_register)
        fact = result.fact_register[0]
        self.assertEqual("revenue", fact["fact_code"])
        self.assertEqual({"period": "2026-01"}, fact["time_context"])
        self.assertEqual(
            [{"dimension_code": "customer", "member_code": "customer-a"}],
            fact["scope"],
        )
        self.assertEqual("100", fact["value"]["canonical_value"])
        self.assertEqual("KRW", fact["value"]["unit_code"])
        self.assertEqual("KRW", fact["value"]["currency_code"])
        lineage_ref = fact["source_refs"][0]["lineage_set_ref"]
        self.assertIn(lineage_ref, result.lineage_files)

    def test_invalid_decimal_becomes_quality_issue_and_never_a_fact(self) -> None:
        dataset = self._dataset()
        dataset.records[0].values["revenue"] = "not-a-number"
        proposal = build_canonical_mapping_proposal(dataset, METRICS)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        mappings = resolve_confirmed_mappings(
            dataset,
            proposal,
            {
                "mapping": {
                    "sources": {dataset.source_id: {"included": True}},
                    "columns": {
                        question_ref: {
                            "observation_role": "ledger",
                            "unit_code": "KRW",
                            "scale": "1",
                            "time_role": "recognition_period",
                            "dimension_code": "customer",
                        }
                    },
                }
            },
            METRICS,
        )

        result = materialize_observed_facts(dataset, mappings)

        self.assertEqual((), result.fact_register)
        self.assertEqual(1, len(result.data_quality_register))
        issue = result.data_quality_register[0]
        self.assertEqual("invalid_decimal", issue["issue_code"])
        self.assertEqual("blocking", issue["severity"])
        self.assertEqual("revenue", issue["affected_field"])

    def test_duplicate_business_key_is_blocking_and_suppresses_both_facts(self) -> None:
        dataset = self._dataset()
        dataset.records = (
            dataset.records[0],
            ParsedRecord(
                2,
                "json_pointer",
                {"pointer": "/1"},
                {
                    "period": "2026-01",
                    "revenue": "120",
                    "Revenue Alias": "120",
                    "scope.customer": "customer-a",
                },
            ),
        )
        proposal = build_canonical_mapping_proposal(dataset, METRICS)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        mappings = resolve_confirmed_mappings(
            dataset,
            proposal,
            {
                "mapping": {
                    "sources": {dataset.source_id: {"included": True}},
                    "columns": {
                        question_ref: {
                            "observation_role": "ledger",
                            "unit_code": "KRW",
                            "scale": "1",
                            "time_role": "recognition_period",
                            "dimension_code": "customer",
                        }
                    },
                }
            },
            METRICS,
        )

        result = materialize_observed_facts(dataset, mappings)

        self.assertEqual((), result.fact_register)
        self.assertEqual(1, len(result.data_quality_register))
        self.assertEqual("duplicate_business_key", result.data_quality_register[0]["issue_code"])
        self.assertEqual("blocking", result.data_quality_register[0]["severity"])

    def test_invalid_period_becomes_quality_issue_and_never_a_fact(self) -> None:
        dataset = self._dataset()
        dataset.records[0].values["period"] = "2026-13"
        proposal = build_canonical_mapping_proposal(dataset, METRICS)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        mappings = resolve_confirmed_mappings(
            dataset,
            proposal,
            {
                "mapping": {
                    "sources": {dataset.source_id: {"included": True}},
                    "columns": {
                        question_ref: {
                            "observation_role": "ledger",
                            "unit_code": "KRW",
                            "scale": "1",
                            "time_role": "recognition_period",
                            "dimension_code": "customer",
                        }
                    },
                }
            },
            METRICS,
        )

        result = materialize_observed_facts(dataset, mappings)

        self.assertEqual((), result.fact_register)
        self.assertEqual(1, len(result.data_quality_register))
        self.assertEqual("ambiguous_period", result.data_quality_register[0]["issue_code"])
        self.assertEqual("period", result.data_quality_register[0]["affected_field"])

    def test_missing_scope_member_becomes_quality_issue_and_never_a_fact(self) -> None:
        dataset = self._dataset()
        dataset.records[0].values["scope.customer"] = ""
        proposal = build_canonical_mapping_proposal(dataset, METRICS)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        mappings = resolve_confirmed_mappings(
            dataset,
            proposal,
            {
                "mapping": {
                    "sources": {dataset.source_id: {"included": True}},
                    "columns": {
                        question_ref: {
                            "observation_role": "ledger",
                            "unit_code": "KRW",
                            "scale": "1",
                            "time_role": "recognition_period",
                            "dimension_code": "customer",
                        }
                    },
                }
            },
            METRICS,
        )

        result = materialize_observed_facts(dataset, mappings)

        self.assertEqual((), result.fact_register)
        self.assertEqual(1, len(result.data_quality_register))
        self.assertEqual("inconsistent_dimension", result.data_quality_register[0]["issue_code"])
        self.assertEqual("scope.customer", result.data_quality_register[0]["affected_field"])


if __name__ == "__main__":
    unittest.main()
