import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.facts import build_calculated_fact, build_observed_fact
from trusted_ceo_agent.evidence.links import build_evidence_link
from trusted_ceo_agent.evidence.signals import build_signal


SHA = "a" * 64
SOURCE_ID = "source_" + "a" * 24


def source_ref() -> dict:
    return {
        "source_id": SOURCE_ID,
        "observation_role": "ledger",
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


class EvidenceBuilderTests(unittest.TestCase):
    def test_observed_calculated_signal_and_link_are_deterministic(self) -> None:
        observed = build_observed_fact(
            fact_code="revenue.observed",
            metric_code="revenue",
            semantic_role="observation",
            observation_role="ledger",
            scope=[{"dimension_code": "business_unit", "member_code": "all"}],
            time_context={"period": "2026-01"},
            value={"value_type": "decimal", "canonical_value": "100", "unit_code": "currency", "currency_code": "KRW", "scale": "1"},
            source_refs=[source_ref()],
        )
        calculated = build_calculated_fact(
            fact_type="calculated",
            fact_code="revenue.change",
            metric_code="revenue_change",
            semantic_role="comparison",
            observation_role="derived",
            scope=observed["scope"],
            time_context=observed["time_context"],
            value={"value_type": "decimal", "canonical_value": "10", "unit_code": "percent", "currency_code": None, "scale": "1"},
            component_id="compare",
            component_version="1.0.0",
            operation_code="period_compare",
            formula_ref="compare.period.v1",
            parameter_hash=SHA,
            input_fact_ids=[observed["fact_id"]],
            component_run_id="component_run_" + "b" * 24,
        )
        signal = build_signal(
            signal_code="revenue.increase",
            rule_ref="rule.revenue.increase.v1",
            component_id="compare",
            component_version="1.0.0",
            component_run_id="component_run_" + "b" * 24,
            threshold_ref="threshold.revenue.increase",
            input_fact_ids=[calculated["fact_id"]],
            required_fact_codes=["revenue.change"],
            missing_fact_codes=[],
            scope=calculated["scope"],
            time_context=calculated["time_context"],
            evaluation={"operator": "gte", "actual": "10", "threshold": "5"},
            outcome="triggered",
            direction="up",
            impact_band_candidate="medium",
            urgency_band_candidate="routine",
        )
        link = build_evidence_link(
            target_ref="problem_candidate_" + "c" * 24,
            target_type="problem_candidate",
            evidence_ref=signal["signal_id"],
            evidence_kind="signal",
            evidence_outcome="triggered",
            polarity="supports",
            role="observation",
            rationale_template="Revenue changed by {value}",
            value_refs=[{"token": "value", "fact_or_signal_id": signal["signal_id"], "display_field": "evaluation.actual", "display_format_ref": "percent"}],
            stage="evidence_scan",
            materialized_by="runtime_normalizer",
            origin={"origin_type": "deterministic_rule", "origin_job_id": None, "model_profile": None, "prompt_hash": None, "proposal_hash": SHA},
            independence_group_id="independence_" + "d" * 24,
        )
        self.assertTrue(observed["fact_id"].startswith("fact_"))
        self.assertEqual([observed["fact_id"]], calculated["derivation"]["input_fact_ids"])
        self.assertEqual("deterministic_component", signal["producer"])
        self.assertTrue(link["evidence_link_id"].startswith("evidence_"))

    def test_unknown_values_and_invalid_not_assessable_signal_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            build_observed_fact(
                fact_code="bad", metric_code="bad", semantic_role="observation", observation_role="ledger",
                scope=[], time_context={"period": "2026-01"},
                value={"value_type": "string", "canonical_value": "n/a", "unit_code": None, "currency_code": None, "scale": None},
                source_refs=[source_ref()],
            )
        with self.assertRaises(ContractError):
            build_signal(
                signal_code="missing", rule_ref="r", component_id="ratio", component_version="1.0.0",
                component_run_id="component_run_" + "e" * 24, threshold_ref=None, input_fact_ids=[],
                required_fact_codes=["x"], missing_fact_codes=[], scope=[], time_context={"period": "2026-01"},
                evaluation={}, outcome="not_assessable",
            )

    def test_not_assessable_signal_cannot_support_problem(self) -> None:
        with self.assertRaises(ContractError):
            build_evidence_link(
                target_ref="problem_candidate_" + "c" * 24,
                target_type="problem_candidate",
                evidence_ref="signal_" + "d" * 24,
                evidence_kind="signal",
                evidence_outcome="not_assessable",
                polarity="supports",
                role="boundary",
                rationale_template="Missing data",
                value_refs=[], stage="lens", materialized_by="runtime_normalizer",
                origin={"origin_type": "model_proposal", "origin_job_id": "job_" + "e" * 24, "model_profile": "balanced", "prompt_hash": SHA, "proposal_hash": SHA},
                independence_group_id="independence_" + "f" * 24,
            )


if __name__ == "__main__":
    unittest.main()
