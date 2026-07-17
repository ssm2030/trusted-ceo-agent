import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from trusted_ceo_agent.poc import run_scenario


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "plugin" / "trusted-ceo-agent" / "schemas"


class FinalOutputSchemaTests(unittest.TestCase):
    def load_schema(self, name: str) -> dict:
        schema = json.loads((SCHEMAS / name).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        return schema

    def test_poc_oracles_validate(self) -> None:
        validator = Draft202012Validator(self.load_schema("poc-oracle.schema.json"))
        for path in (ROOT / "tests" / "evaluation" / "oracles").glob("*.json"):
            validator.validate(json.loads(path.read_text("utf-8")))

    def test_canned_final_result_validates_and_unknown_root_field_fails(self) -> None:
        schema = self.load_schema("final-result.schema.json")
        validator = Draft202012Validator(schema)
        result = run_scenario(ROOT / "tests" / "fixtures" / "evaluation" / "normal_vertical")["result"]
        validator.validate(result)
        with self.assertRaises(Exception):
            validator.validate({**result, "invented": True})


if __name__ == "__main__":
    unittest.main()
