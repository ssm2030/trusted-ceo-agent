from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.integration.test_cli_accounting_components import accounting_request
from tests.integration.test_cli_components import call, prepare_authorized_scope
from tests.integration.test_cli_professional_runtime import professional_request
from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite
from trusted_ceo_agent.canonical import canonical_bytes


ROOT = Path(__file__).resolve().parents[2]


class CliSpecialistBindingTests(unittest.TestCase):
    def test_accounting_and_professional_inputs_publish_one_bound_revision(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, run_id, store, common, _, scope_ref, _, _ = prepare_authorized_scope(
                root,
                required_inputs=("accounting", "professional"),
            )
            accounting = accounting_request(run_id, 4, scope_ref)
            bundle = dispatch_accounting_suite(**{
                key: accounting[key]
                for key in (
                    "suite",
                    "tier_zero_input",
                    "raw_core_population",
                    "revenue_input",
                    "cashflow_input",
                    "project_cost_inputs",
                )
            })
            family = next(
                item
                for item in bundle["execution_manifest"]["family_records"]
                if item["issue_family_id"] == "AC-01"
            )
            parent_hash = family["parent_result_hash"]
            professional = professional_request(
                store,
                run_id=run_id,
                scope_ref=scope_ref,
            )
            professional["runtime_input"]["work_plans"][0]["packet_hash"] = parent_hash
            spec = professional["task_results"]["accounting-deep-case"]["findings"][0][
                "spec"
            ]
            spec["issue_family_refs"] = ["AC-01"]
            spec["procedure_result_refs"] = [parent_hash]

            accounting_path = root / "accounting.json"
            professional_path = root / "professional.json"
            accounting_path.write_bytes(canonical_bytes(accounting))
            professional_path.write_bytes(canonical_bytes(professional))

            code, result = call([
                "run-components",
                *common,
                "--scope-ref",
                scope_ref,
                "--accounting-input",
                str(accounting_path),
                "--professional-input",
                str(professional_path),
                "--expected-revision",
                "3",
            ])

            self.assertEqual(0, code, result)
            snapshot = store.verify_revision(4)
            binding = json.loads(
                (
                    snapshot / "analysis" / "professional"
                    / "accounting-binding.json"
                ).read_text("utf-8")
            )
            self.assertEqual(64, binding["available_family_count"])
            self.assertEqual(
                binding["content_hash"],
                result["data"]["accounting_professional_binding_hash"],
            )


if __name__ == "__main__":
    unittest.main()
