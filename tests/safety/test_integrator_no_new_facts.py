import unittest

from trusted_ceo_agent.errors import ContractError

from tests.integrator_support import complete_inputs, rehash_assessment
from tests.unit.analysis.test_integrator import build_manifest, integrate


class IntegratorNoInventionSafetyTests(unittest.TestCase):
    def test_integrator_rejects_judgment_fields_and_only_projects_existing_refs(self) -> None:
        inputs = complete_inputs()
        inputs["domain_assessments"][0]["grade"] = "A"
        inputs["domain_assessments"][0] = rehash_assessment(
            inputs["domain_assessments"][0]
        )
        with self.assertRaises(ContractError):
            build_manifest(inputs)

        valid = complete_inputs()
        result = integrate(valid, build_manifest(valid))
        forbidden = {"facts", "signals", "grade", "approval", "new_fact", "new_evidence"}

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(result)
        self.assertTrue(set(result["common_fact_refs"]).issubset(valid["event"]["fact_refs"]))
        relation_refs = {item["relation_id"] for item in valid["relations"]}
        self.assertTrue(
            {item["relation_id"] for item in result["conflicts"]}.issubset(relation_refs)
        )


if __name__ == "__main__":
    unittest.main()
