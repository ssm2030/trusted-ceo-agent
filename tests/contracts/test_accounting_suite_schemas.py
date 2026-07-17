import copy
import importlib
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


def _apis():
    try:
        suite = importlib.import_module("trusted_ceo_agent.accounting.suite")
        coverage = importlib.import_module("trusted_ceo_agent.accounting.coverage")
    except ModuleNotFoundError as error:
        raise AssertionError(f"accounting contract API is missing: {error}") from error
    return suite, coverage


class AccountingSuiteSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schemas = SchemaStore()
        self.suite_api, self.coverage_api = _apis()

    def test_suite_and_all_issue_families_validate_as_closed_contracts(self):
        suite = self.suite_api.build_machine_draft_suite(
            release_id="accounting-suite-2026-07-17", effective_from="2026-07-17",
        )
        self.schemas.validate("accounting-content-suite.schema.json", suite)
        for issue in suite["issue_families"]:
            self.schemas.validate("accounting-issue-family.schema.json", issue)

        invalid = copy.deepcopy(suite)
        invalid["hidden_chain_of_thought"] = "forbidden"
        with self.assertRaises(ContractError):
            self.schemas.validate("accounting-content-suite.schema.json", invalid)

    def test_account_universe_assessment_is_closed(self):
        suite = self.suite_api.build_machine_draft_suite(
            release_id="accounting-suite-2026-07-17", effective_from="2026-07-17",
        )
        report = self.coverage_api.assess_account_universe(
            source_account_family_ids=["revenue"],
            records=[{
                "account_family_id": "revenue", "amount_fact_ref": "fact_revenue",
                "risk": "high", "material": True, "state": "pack_required",
                "pack_id": None, "missing_capabilities": ["approved_pack"],
                "next_actions": ["expert_pack"], "evidence_refs": ["evidence_revenue"],
            }],
            suite=suite,
        )
        self.schemas.validate("account-universe-assessment.schema.json", report)

        invalid = copy.deepcopy(report)
        invalid["new_analysis_judgment"] = True
        with self.assertRaises(ContractError):
            self.schemas.validate("account-universe-assessment.schema.json", invalid)


if __name__ == "__main__":
    unittest.main()
