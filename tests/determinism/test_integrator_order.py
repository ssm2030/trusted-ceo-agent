import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes

from tests.integrator_support import complete_inputs
from tests.unit.analysis.test_integrator import build_manifest, integrate


class IntegratorOrderDeterminismTests(unittest.TestCase):
    def test_completion_and_input_order_are_byte_equivalent(self) -> None:
        first = complete_inputs(include_unsupported=True)
        second = copy.deepcopy(first)
        for key in ("routes", "domain_assessments", "findings", "relations", "clusters"):
            second[key].reverse()
        first_manifest = build_manifest(first)
        second_manifest = build_manifest(second)
        self.assertEqual(canonical_bytes(first_manifest), canonical_bytes(second_manifest))
        self.assertEqual(
            canonical_bytes(integrate(first, first_manifest)),
            canonical_bytes(integrate(second, second_manifest)),
        )


if __name__ == "__main__":
    unittest.main()
