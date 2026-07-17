import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter
from trusted_ceo_agent.intake.mapping import build_canonical_mapping_proposal, resolve_confirmed_mappings
from trusted_ceo_agent.intake.materialize import materialize_observed_facts


METRICS = [{
    "metric_code": "revenue",
    "accepted_observation_roles": ["ledger"],
    "data_type": "decimal",
    "unit_policy": "single_currency_or_verified_conversion",
    "time_role": "recognition_period",
    "allowed_dimensions": ["customer"],
}]


def materialize(dataset):
    proposal = build_canonical_mapping_proposal(dataset, METRICS)
    question_ref = proposal["mappings"][0]["mapping_question_ref"]
    mappings = resolve_confirmed_mappings(
        dataset,
        proposal,
        {
            "mapping": {
                "sources": {dataset.source_id: {"included": True}},
                "columns": {question_ref: {
                    "observation_role": "ledger",
                    "unit_code": "KRW",
                    "scale": "1",
                    "time_role": "recognition_period",
                    "dimension_code": "customer",
                }},
            }
        },
        METRICS,
    )
    return materialize_observed_facts(dataset, mappings)


class CanonicalMappingFormatIntegrationTests(unittest.TestCase):
    def test_csv_json_and_xlsx_produce_the_same_observed_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "input.csv"
            json_path = root / "input.json"
            xlsx_path = root / "input.xlsx"
            csv_path.write_text(
                "period,revenue,scope.customer\n2026-01,100,customer-a\n",
                encoding="utf-8",
            )
            json_path.write_text(json.dumps([{
                "period": "2026-01", "revenue": "100", "scope.customer": "customer-a",
            }]), encoding="utf-8")
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["period", "revenue", "scope.customer"])
            sheet.append(["2026-01", 100, "customer-a"])
            workbook.save(xlsx_path)
            workbook.close()

            datasets = [
                CsvAdapter().parse(csv_path, "source_" + "a" * 24),
                JsonAdapter().parse(json_path, "source_" + "b" * 24),
                XlsxAdapter().parse(xlsx_path, "source_" + "c" * 24),
            ]
            results = [materialize(dataset) for dataset in datasets]
            projections = []
            for result in results:
                self.assertEqual((), result.data_quality_register)
                self.assertEqual(1, len(result.fact_register))
                fact = result.fact_register[0]
                self.assertIn(fact["source_refs"][0]["lineage_set_ref"], result.lineage_files)
                projections.append({
                    "fact_code": fact["fact_code"],
                    "metric_code": fact["metric_code"],
                    "scope": fact["scope"],
                    "time_context": fact["time_context"],
                    "value": fact["value"],
                })
            self.assertEqual(projections[0], projections[1])
            self.assertEqual(projections[0], projections[2])


if __name__ == "__main__":
    unittest.main()
