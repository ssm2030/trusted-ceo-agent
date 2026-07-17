from __future__ import annotations

import copy
import unittest

from tests.integration.test_accounting_dispatcher import _arguments
from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent import runtime_components


def professional_request(bundle: dict) -> dict:
    family = bundle["execution_manifest"]["family_records"][0]
    result_hash = family["parent_result_hash"]
    return {
        "runtime_input": {
            "work_plans": [{
                "local_key": "accounting-case",
                "domain": "accounting",
                "issue_family": family["issue_family_id"],
                "packet_hash": result_hash,
            }],
        },
        "task_results": {
            "accounting-case": {
                "findings": [{
                    "finding_key": "finding-accounting-case",
                    "spec": {
                        "issue_family_refs": [family["issue_family_id"]],
                        "procedure_result_refs": [result_hash],
                    },
                }],
            },
        },
        "task_failures": {},
    }


class SpecialistInputBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = dispatch_accounting_suite(**_arguments())

    def test_binds_verified_64_family_bundle_to_work_and_finding_refs(self) -> None:
        request = professional_request(self.bundle)

        first = runtime_components.bind_accounting_professional_inputs(
            self.bundle, request
        )
        second = runtime_components.bind_accounting_professional_inputs(
            self.bundle, copy.deepcopy(request)
        )

        self.assertEqual(first, second)
        self.assertEqual(64, first["available_family_count"])
        self.assertEqual(1, first["bound_work_item_count"])
        self.assertEqual(
            request["runtime_input"]["work_plans"][0]["packet_hash"],
            first["bindings"][0]["parent_result_hash"],
        )

    def test_packet_and_procedure_result_mismatch_fail_closed(self) -> None:
        packet_mismatch = professional_request(self.bundle)
        packet_mismatch["runtime_input"]["work_plans"][0]["packet_hash"] = "f" * 64
        with self.assertRaisesRegex(ContractError, "packet_hash"):
            runtime_components.bind_accounting_professional_inputs(
                self.bundle, packet_mismatch
            )

        result_mismatch = professional_request(self.bundle)
        result_mismatch["task_results"]["accounting-case"]["findings"][0]["spec"][
            "procedure_result_refs"
        ] = ["f" * 64]
        with self.assertRaisesRegex(ContractError, "procedure_result_refs"):
            runtime_components.bind_accounting_professional_inputs(
                self.bundle, result_mismatch
            )


if __name__ == "__main__":
    unittest.main()
