import json
import unittest
from pathlib import Path

from trusted_ceo_agent.intake.mapping import (
    build_canonical_mapping_proposal,
    resolve_confirmed_mappings,
)
from trusted_ceo_agent.intake.materialize import materialize_observed_facts
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord
from trusted_ceo_agent.packs.evidence_selection import (
    build_problem_capability_map,
    build_problem_selection,
)
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


class ProfitabilityIntakeReachabilityTests(unittest.TestCase):
    def test_three_gross_margin_periods_make_both_capabilities_available_and_select_pack(self) -> None:
        domain = json.loads(
            (PLUGIN_ROOT / "packs" / "domain" / "b2b-services" / "1.0.0" / "pack.json")
            .read_text(encoding="utf-8")
        )
        problem = json.loads(
            (PLUGIN_ROOT / "packs" / "problem" / "profitability-erosion" / "1.0.0" / "pack.json")
            .read_text(encoding="utf-8")
        )
        source_id = "source_" + "a" * 24
        source = ParsedDataset(
            source_id=source_id,
            media_type="application/json",
            fields=("period", "gross_margin"),
            records=tuple(
                ParsedRecord(
                    index,
                    "json_pointer",
                    {"pointer": f"/{index - 1}"},
                    {"period": period, "gross_margin": value},
                )
                for index, (period, value) in enumerate(
                    (("2026-01", "0.34"), ("2026-02", "0.32"), ("2026-03", "0.30")),
                    start=1,
                )
            ),
        )
        metrics = domain["content"]["metric_definitions"]
        proposal = build_canonical_mapping_proposal(source, metrics)
        question_ref = proposal["mappings"][0]["mapping_question_ref"]
        mappings = resolve_confirmed_mappings(
            source,
            proposal,
            {"mapping": {
                "sources": {source_id: {"included": True}},
                "columns": {question_ref: {
                    "observation_role": "calculated",
                    "unit_code": "ratio",
                    "scale": "1",
                    "time_role": "reporting_period",
                    "dimension_code": None,
                }},
            }},
            metrics,
        )
        materialized = materialize_observed_facts(source, mappings)
        index = RuntimePackIndex(
            manifest={"packs": [{"effective_authority": "provisional"}]},
            mission_pack={},
            domain_pack=domain,
            problem_packs=(problem,),
        )

        capability_map = build_problem_capability_map(
            index,
            materialized.fact_register,
            materialized.data_quality_register,
            [{"source_id": source_id, "observation_roles": ["calculated"]}],
        )
        selection = build_problem_selection(index, materialized.fact_register, [], capability_map)

        self.assertEqual(3, len(materialized.fact_register))
        self.assertEqual(
            {"gross_margin": "available", "monthly_profitability": "available"},
            {item["capability_code"]: item["status"] for item in capability_map["capabilities"]},
        )
        self.assertTrue(all(
            "capability_requirement_fallback_to_entry_fact_refs" not in item["reason_codes"]
            for item in capability_map["capabilities"]
        ))
        self.assertEqual(["profitability-erosion@1.0.0"], selection["selected_problem_refs"])


if __name__ == "__main__":
    unittest.main()
