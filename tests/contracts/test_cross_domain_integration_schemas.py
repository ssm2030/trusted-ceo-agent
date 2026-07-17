import copy
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

from tests.integrator_support import complete_inputs
from tests.unit.analysis.test_integrator import build_manifest, integrate


class CrossDomainIntegrationSchemaTests(unittest.TestCase):
    def test_closed_manifest_and_result_contracts(self) -> None:
        inputs = complete_inputs()
        manifest = build_manifest(inputs)
        result = integrate(inputs, manifest)
        schemas = SchemaStore()
        schemas.validate("finding-join-manifest.schema.json", manifest)
        schemas.validate("cross-domain-integration.schema.json", result)

        for document, schema in (
            (manifest, "finding-join-manifest.schema.json"),
            (result, "cross-domain-integration.schema.json"),
        ):
            invalid = copy.deepcopy(document)
            invalid["hidden_reasoning"] = "forbidden"
            with self.assertRaises(ContractError):
                schemas.validate(schema, invalid)


if __name__ == "__main__":
    unittest.main()
