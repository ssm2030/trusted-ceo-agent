import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from trusted_ceo_agent.components import component_contracts, execute_component
from trusted_ceo_agent.packs import PackLoader, PackRegistry
from tests.unit.components.test_components import fact


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"
SCHEMA_ROOT = PLUGIN_ROOT / "schemas"


class ComponentPackSchemaTests(unittest.TestCase):
    def validator(self, name: str) -> Draft202012Validator:
        schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_owned_schemas_are_valid_draft_2020_12(self) -> None:
        names = [
            "condition-expression.schema.json",
            "component-contract.schema.json",
            "component-run.schema.json",
            "mission-pack.schema.json",
            "domain-pack.schema.json",
            "problem-pack.schema.json",
            "pack-registry.schema.json",
            "pack-manifest.schema.json",
        ]
        for name in names:
            with self.subTest(name=name):
                self.validator(name)

    def test_component_contract_and_run_validate(self) -> None:
        contract_validator = self.validator("component-contract.schema.json")
        run_validator = self.validator("component-run.schema.json")
        for contract in component_contracts().values():
            contract_validator.validate(contract.to_dict())
        run = execute_component(
            "aggregate",
            [fact("fact_" + "a" * 24, "revenue", "10")],
            {"input_fact_code": "revenue", "operation": "sum", "output_fact_code": "total"},
        )
        run_validator.validate(run.to_dict())
        fact_validator = self.validator("fact.schema.json")
        for output_fact in run.output_facts:
            fact_validator.validate(output_fact)

        signal_run = execute_component(
            "trend_persistence",
            [
                fact("fact_" + "1" * 24, "margin", "3"),
                {**fact("fact_" + "2" * 24, "margin", "2"), "time_context": {"period": "2026-02"}},
                {**fact("fact_" + "3" * 24, "margin", "1"), "time_context": {"period": "2026-03"}},
            ],
            {
                "input_fact_code": "margin", "minimum_observations_ref": "minimum",
                "direction": "decreasing", "output_signal_code": "margin_decline",
            },
            thresholds={"minimum": "3"},
        )
        signal_validator = self.validator("signal.schema.json")
        for output_signal in signal_run.output_signals:
            signal_validator.validate(output_signal)

    def test_pack_schemas_reject_unknown_top_level_property(self) -> None:
        registry = PackRegistry.load(
            PLUGIN_ROOT / "trust" / "pack-registry.json", SCHEMA_ROOT / "pack-registry.schema.json"
        )
        pack = PackLoader(PLUGIN_ROOT / "packs", SCHEMA_ROOT, registry).load_installed()[0]
        document = json.loads(pack.path.read_text(encoding="utf-8"))
        validator = self.validator(f"{pack.pack_type}-pack.schema.json")
        validator.validate(document)
        invalid = copy.deepcopy(document)
        invalid["unexpected"] = True
        with self.assertRaises(ValidationError):
            validator.validate(invalid)

    def test_problem_pack_schema_rejects_malformed_fact_selector(self) -> None:
        registry = PackRegistry.load(
            PLUGIN_ROOT / "trust" / "pack-registry.json", SCHEMA_ROOT / "pack-registry.schema.json"
        )
        pack = next(
            item for item in PackLoader(PLUGIN_ROOT / "packs", SCHEMA_ROOT, registry).load_installed()
            if item.pack_type == "problem"
        )
        document = json.loads(pack.path.read_text(encoding="utf-8"))
        validator = self.validator("problem-pack.schema.json")
        validator.validate(document)
        invalid = copy.deepcopy(document)
        invalid["content"]["analysis_plan"][0]["parameter_template"] = {
            "input_fact_ids": {"fact_selector": {"fact_code": "revenue"}}
        }
        with self.assertRaises(ValidationError) as captured:
            validator.validate(invalid)
        self.assertIn("fact_selector", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
