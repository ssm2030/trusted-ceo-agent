import unittest

from trusted_ceo_agent.components import execute_component


def fact(
    fact_id: str,
    fact_code: str,
    value: str,
    *,
    unit: str = "KRW",
    period: str = "2026-01",
    member: str = "all",
    value_type: str = "decimal",
) -> dict:
    return {
        "fact_id": fact_id,
        "fact_code": fact_code,
        "fact_type": "observed",
        "metric_code": fact_code,
        "semantic_role": "actual",
        "observation_role": "ledger",
        "scope": [{"dimension_code": "segment", "member_code": member}],
        "time_context": {"period": period},
        "value": {
            "value_type": value_type,
            "canonical_value": value,
            "unit_code": unit,
            "currency_code": "KRW" if unit == "KRW" else None,
            "scale": "1",
        },
        "source_refs": [],
        "derivation": None,
        "quality": [],
        "producer": "runtime_intake",
        "integrity": {"payload_hash": "a" * 64},
    }


class ComponentExecutionTests(unittest.TestCase):
    def test_aggregate_sums_same_unit_facts(self) -> None:
        run = execute_component(
            "aggregate",
            [fact("fact_a", "revenue", "10", member="a"), fact("fact_b", "revenue", "20", member="b")],
            {
                "input_fact_code": "revenue",
                "operation": "sum",
                "output_fact_code": "revenue_total",
                "output_metric_code": "revenue",
                "scope": [{"dimension_code": "enterprise", "member_code": "all"}],
                "time_context": {"period": "2026-01"},
            },
        )
        self.assertEqual("completed", run.status)
        self.assertEqual("30", run.output_facts[0]["value"]["canonical_value"])
        self.assertEqual(["fact_a", "fact_b"], run.output_facts[0]["derivation"]["input_fact_ids"])

    def test_aggregate_rejects_mixed_units_without_conversion(self) -> None:
        run = execute_component(
            "aggregate",
            [fact("fact_a", "revenue", "10"), fact("fact_b", "revenue", "20", unit="USD")],
            {"input_fact_code": "revenue", "operation": "sum", "output_fact_code": "total"},
        )
        self.assertEqual("not_assessable", run.status)
        self.assertEqual(("unit_mismatch",), run.reason_codes)

    def test_compare_does_not_create_percent_change_from_zero_baseline(self) -> None:
        run = execute_component(
            "compare",
            [fact("base", "revenue", "0"), fact("current", "revenue", "10")],
            {
                "baseline_fact_id": "base",
                "current_fact_id": "current",
                "mode": "percent_change",
                "output_fact_code": "revenue_change_pct",
            },
        )
        self.assertEqual("not_assessable", run.status)
        self.assertEqual(("zero_baseline",), run.reason_codes)

    def test_compare_converts_ratio_difference_to_percentage_points(self) -> None:
        run = execute_component(
            "compare",
            [
                fact("base", "gross_margin", "0.31", unit="ratio", period="2026-01"),
                fact("current", "gross_margin", "0.27", unit="ratio", period="2026-02"),
            ],
            {
                "baseline_fact_id": "base",
                "current_fact_id": "current",
                "mode": "percentage_point_change",
                "output_fact_code": "gross_margin_change_pp",
            },
        )
        self.assertEqual("completed", run.status)
        self.assertEqual("-4", run.output_facts[0]["value"]["canonical_value"])
        self.assertEqual("percentage_point", run.output_facts[0]["value"]["unit_code"])

    def test_ratio_produces_decimal_ratio(self) -> None:
        run = execute_component(
            "ratio",
            [fact("num", "gross_profit", "24"), fact("den", "revenue", "100")],
            {
                "numerator_fact_id": "num",
                "denominator_fact_id": "den",
                "output_fact_code": "gross_margin",
                "output_metric_code": "gross_margin",
                "output_unit_code": "ratio",
            },
        )
        self.assertEqual("completed", run.status)
        self.assertEqual("0.24", run.output_facts[0]["value"]["canonical_value"])

    def test_trend_requires_pack_resolved_minimum_observations(self) -> None:
        run = execute_component(
            "trend_persistence",
            [
                fact("m1", "margin", "31", period="2026-01"),
                fact("m2", "margin", "28", period="2026-02"),
                fact("m3", "margin", "24", period="2026-03"),
            ],
            {
                "input_fact_code": "margin",
                "minimum_observations_ref": "trend_minimum",
                "direction": "decreasing",
                "output_signal_code": "margin_decline_persistent",
            },
            thresholds={"trend_minimum": "3"},
        )
        self.assertEqual("completed", run.status)
        self.assertEqual("triggered", run.output_signals[0]["outcome"])
        self.assertEqual("trend_minimum", run.output_signals[0]["threshold_ref"])

    def test_mix_concentration_calculates_top_n_share_and_hhi(self) -> None:
        run = execute_component(
            "mix_concentration",
            [
                fact("a", "customer_revenue", "70", member="A"),
                fact("b", "customer_revenue", "20", member="B"),
                fact("c", "customer_revenue", "10", member="C"),
            ],
            {
                "input_fact_code": "customer_revenue",
                "top_n": 2,
                "share_output_fact_code": "top2_share",
                "hhi_output_fact_code": "customer_hhi",
            },
        )
        self.assertEqual("completed", run.status)
        values = {item["fact_code"]: item["value"]["canonical_value"] for item in run.output_facts}
        self.assertEqual("0.9", values["top2_share"])
        self.assertEqual("0.54", values["customer_hhi"])

    def test_reconcile_uses_pack_tolerance(self) -> None:
        run = execute_component(
            "reconcile",
            [fact("total", "revenue", "100"), fact("a", "segment_revenue", "60"), fact("b", "segment_revenue", "39")],
            {
                "total_fact_id": "total",
                "part_fact_ids": ["a", "b"],
                "tolerance_ref": "reconcile_tolerance",
                "output_signal_code": "revenue_reconciles",
            },
            thresholds={"reconcile_tolerance": "0.02"},
        )
        self.assertEqual("completed", run.status)
        self.assertEqual("triggered", run.output_signals[0]["outcome"])

    def test_flow_aging_records_censoring_and_bucket_totals(self) -> None:
        first = fact("a", "open_receivable", "10")
        first["time_context"] = {"as_of": "2026-01-01"}
        second = fact("b", "open_receivable", "20")
        second["time_context"] = {"as_of": "2026-02-20"}
        observation_end = fact(
            "end", "analysis_as_of_date", "2026-03-01", unit="date", value_type="date",
        )
        run = execute_component(
            "flow_aging",
            [first, second, observation_end],
            {
                "input_fact_code": "open_receivable",
                "observation_end_fact_id": "end",
                "bucket_edges_days": [30, 60],
                "output_fact_code_prefix": "receivable_aging",
            },
        )
        self.assertEqual("completed", run.status)
        self.assertEqual(3, len(run.output_facts))
        self.assertTrue(all(item["derivation"]["formula_ref"] == "censored_at_observation_end" for item in run.output_facts))
        self.assertTrue(all("end" in item["derivation"]["input_fact_ids"] for item in run.output_facts))

    def test_bridge_blocks_cause_promotion_when_residual_is_too_large(self) -> None:
        run = execute_component(
            "bridge_decompose",
            [fact("gap", "margin_gap", "10"), fact("mix", "mix_driver", "4")],
            {
                "gap_fact_id": "gap",
                "driver_fact_ids": ["mix"],
                "residual_tolerance_ref": "bridge_residual_max",
                "output_fact_code": "bridge_residual",
            },
            thresholds={"bridge_residual_max": "0.2"},
        )
        self.assertEqual("not_assessable", run.status)
        self.assertEqual(("residual_reconciliation_failed",), run.reason_codes)

    def test_temporal_alignment_calculates_lag_from_explicit_date_roles(self) -> None:
        service = fact("service", "service_date", "2026-01-31", unit="date", value_type="date")
        recognition = fact("recognition", "recognition_date", "2026-02-05", unit="date", value_type="date")
        run = execute_component(
            "temporal_alignment",
            [service, recognition],
            {
                "earlier_fact_id": "service",
                "later_fact_id": "recognition",
                "max_lag_days_ref": "recognition_lag_max",
                "output_fact_code": "recognition_lag_days",
                "output_signal_code": "recognition_timing_mismatch",
            },
            thresholds={"recognition_lag_max": "3"},
        )
        self.assertEqual("completed", run.status)
        self.assertEqual("5", run.output_facts[0]["value"]["canonical_value"])
        self.assertEqual("triggered", run.output_signals[0]["outcome"])


if __name__ == "__main__":
    unittest.main()
