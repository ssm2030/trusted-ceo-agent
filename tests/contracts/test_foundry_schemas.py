from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

from tests.foundry_support import make_candidate, make_feedback


class FoundrySchemaTests(unittest.TestCase):
    def setUp(self):
        self.schemas = SchemaStore()

    def test_feedback_and_receipt_are_closed_contracts(self):
        _, request, approval, feedback, receipt = make_feedback()
        for schema, value in (
            ("knowledge-approval-request.schema.json", request),
            ("knowledge-approval.schema.json", approval),
            ("feedback-record.schema.json", feedback),
            ("feedback-receipt.schema.json", receipt),
        ):
            with self.subTest(schema=schema):
                self.schemas.validate(schema, value)
                invalid = copy.deepcopy(value)
                invalid["hidden_chain_of_thought"] = "forbidden"
                with self.assertRaises(ContractError):
                    self.schemas.validate(schema, invalid)

    def test_patch_regression_candidate_and_release_are_closed_contracts(self):
        base, regression, patch, _, _, candidate = make_candidate()
        for schema, value in (
            ("regression-case.schema.json", regression),
            ("patch-proposal.schema.json", patch),
            ("release-candidate.schema.json", candidate),
            ("knowledge-release.schema.json", base),
        ):
            with self.subTest(schema=schema):
                self.schemas.validate(schema, value)
                invalid = copy.deepcopy(value)
                invalid["reasoning_trace"] = ["private tokens"]
                with self.assertRaises(ContractError):
                    self.schemas.validate(schema, invalid)

    def test_structured_reasoning_has_only_auditable_slots(self):
        _, _, _, feedback, _ = make_feedback()
        invalid = copy.deepcopy(feedback)
        invalid["structured_content"]["internal_monologue"] = ["forbidden"]
        with self.assertRaises(ContractError):
            self.schemas.validate("feedback-record.schema.json", invalid)


if __name__ == "__main__":
    unittest.main()
