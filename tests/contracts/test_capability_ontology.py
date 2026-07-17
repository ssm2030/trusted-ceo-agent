import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.packs.schema_validation import (
    validate_pack_ontology,
    validate_problem_capability_contract,
)


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"
PROBLEM_ROOT = PLUGIN_ROOT / "packs" / "problem"
DOMAIN_PATH = PLUGIN_ROOT / "packs" / "domain" / "b2b-services" / "1.0.0" / "pack.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class CapabilityOntologyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.domain = load_json(DOMAIN_PATH)
        cls.problems = [
            load_json(path)
            for path in sorted(PROBLEM_ROOT.glob("*/1.0.0/pack.json"))
        ]

    def test_all_problem_packs_have_one_closed_requirement_per_capability(self) -> None:
        schema = load_json(PLUGIN_ROOT / "schemas" / "problem-pack.schema.json")
        validator = Draft202012Validator(schema)
        for problem in self.problems:
            with self.subTest(pack_id=problem["pack_id"]):
                validator.validate(problem)
                validate_problem_capability_contract(problem)
                required = problem["content"]["required_capabilities"]
                definitions = problem["content"]["capability_requirements"]
                self.assertEqual(sorted(required), sorted(item["capability_code"] for item in definitions))
                invalid = copy.deepcopy(problem)
                invalid["content"]["capability_requirements"][0]["unexpected"] = True
                self.assertTrue(list(validator.iter_errors(invalid)))

    def test_duplicate_or_missing_capability_definition_is_contract_error(self) -> None:
        problem = copy.deepcopy(self.problems[0])
        problem["content"]["capability_requirements"].append(
            copy.deepcopy(problem["content"]["capability_requirements"][0])
        )
        with self.assertRaisesRegex(ContractError, "duplicate capability requirement"):
            validate_problem_capability_contract(problem)

        problem = copy.deepcopy(self.problems[0])
        problem["content"]["capability_requirements"].pop()
        with self.assertRaisesRegex(ContractError, "capability requirement mismatch"):
            validate_problem_capability_contract(problem)

    def test_domain_and_problem_stack_has_reachable_raw_inputs_and_valid_roles(self) -> None:
        validate_pack_ontology(self.domain, self.problems)
        bad_domain = copy.deepcopy(self.domain)
        metric = next(
            item for item in bad_domain["content"]["metric_definitions"]
            if item["metric_code"] == "gross_margin"
        )
        metric["accepted_observation_roles"] = ["ledger"]
        with self.assertRaisesRegex(ContractError, "observation role"):
            validate_pack_ontology(bad_domain, self.problems)

    def test_duplicate_domain_metric_code_is_contract_error(self) -> None:
        bad_domain = copy.deepcopy(self.domain)
        bad_domain["content"]["metric_definitions"].append(
            copy.deepcopy(bad_domain["content"]["metric_definitions"][0])
        )
        with self.assertRaisesRegex(ContractError, "duplicate metric definition"):
            validate_pack_ontology(bad_domain, self.problems)


if __name__ == "__main__":
    unittest.main()
