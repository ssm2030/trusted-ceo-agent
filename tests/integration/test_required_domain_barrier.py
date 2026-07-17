import unittest

from trusted_ceo_agent.errors import ContractError

from tests.integrator_support import complete_inputs, rehash_assessment, rehash_route
from tests.unit.analysis.test_integrator import build_manifest


class RequiredDomainBarrierIntegrationTests(unittest.TestCase):
    def test_required_failure_cannot_be_hidden_by_other_completed_domains(self) -> None:
        inputs = complete_inputs(include_unsupported=True)
        legal_route = inputs["routes"][-1]
        legal_route["status"] = "failed"
        inputs["routes"][-1] = rehash_route(legal_route)
        legal_assessment = inputs["domain_assessments"][-1]
        legal_assessment["status"] = "failed"
        inputs["domain_assessments"][-1] = rehash_assessment(legal_assessment)
        with self.assertRaises(ContractError):
            build_manifest(inputs)


if __name__ == "__main__":
    unittest.main()
