import copy
import importlib
import unittest

from trusted_ceo_agent.errors import ContractError


def _apis():
    try:
        suite = importlib.import_module("trusted_ceo_agent.accounting.suite")
        coverage = importlib.import_module("trusted_ceo_agent.accounting.coverage")
    except ModuleNotFoundError as error:
        raise AssertionError(f"accounting coverage API is missing: {error}") from error
    return suite, coverage


def _record(account_family_id, state, *, material=True, pack_id=None, **extra):
    value = {
        "account_family_id": account_family_id,
        "amount_fact_ref": f"fact_{account_family_id}",
        "risk": "high" if material else "low",
        "material": material,
        "state": state,
        "pack_id": pack_id,
        "missing_capabilities": [],
        "next_actions": ["review"],
        "evidence_refs": [f"evidence_{account_family_id}"],
    }
    value.update(extra)
    return value


class AccountUniverseCoverageTests(unittest.TestCase):
    def setUp(self):
        suite_api, self.api = _apis()
        self.suite = suite_api.build_machine_draft_suite(
            release_id="accounting-suite-2026-07-17",
            effective_from="2026-07-17",
        )

    def test_declared_account_universe_has_no_missing_or_extra_rows(self):
        report = self.api.assess_account_universe(
            source_account_family_ids=["revenue", "leases"],
            records=[
                _record("revenue", "deep_reviewed", pack_id="contract-revenue"),
                _record(
                    "leases", "pack_required",
                    missing_capabilities=["lease_contract", "approved_lease_pack"],
                ),
            ],
            suite=self.suite,
        )
        self.assertEqual(report["coverage_gap_count"], 1)
        self.assertIn("leases", report["material_gap_account_family_ids"])
        self.assertFalse(report["company_wide_full_allowed"])

        with self.assertRaisesRegex(ContractError, "missing"):
            self.api.assess_account_universe(
                source_account_family_ids=["revenue", "leases"],
                records=[_record("revenue", "deep_reviewed", pack_id="contract-revenue")],
                suite=self.suite,
            )

    def test_blank_or_unknown_state_is_rejected(self):
        for state in ("", "reviewed"):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ContractError, "state"):
                    self.api.assess_account_universe(
                        source_account_family_ids=["revenue"],
                        records=[_record("revenue", state)],
                        suite=self.suite,
                    )

    def test_core_screened_never_becomes_professional_review(self):
        report = self.api.assess_account_universe(
            source_account_family_ids=["leases"],
            records=[_record("leases", "core_screened")],
            suite=self.suite,
        )
        self.assertIn("material_core_screened", report["blocker_codes"])
        self.assertFalse(report["senior_accountant_claim_allowed"])

    def test_scope_exclusion_requires_approval_reason_and_period(self):
        incomplete = _record(
            "tax", "excluded_by_approved_scope", approval_ref=None,
            exclusion_reason=None, exclusion_effective_period=None,
        )
        with self.assertRaisesRegex(ContractError, "approval|exclusion"):
            self.api.assess_account_universe(
                source_account_family_ids=["tax"], records=[incomplete], suite=self.suite,
            )

        complete = copy.deepcopy(incomplete)
        complete.update(
            approval_ref="approval_tax_scope",
            exclusion_reason="Board-approved separate tax review",
            exclusion_effective_period={"from": "2026-01-01", "to": "2026-12-31"},
        )
        report = self.api.assess_account_universe(
            source_account_family_ids=["tax"], records=[complete], suite=self.suite,
        )
        self.assertEqual(report["coverage_gap_count"], 0)

    def test_not_assessable_and_pack_required_need_explicit_capability_and_action(self):
        for state in ("not_assessable", "pack_required"):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ContractError, "capabilit|action"):
                    self.api.assess_account_universe(
                        source_account_family_ids=["tax"],
                        records=[_record("tax", state)],
                        suite=self.suite,
                    )

    def test_deep_review_requires_known_pack_and_non_draft_authority(self):
        report = self.api.assess_account_universe(
            source_account_family_ids=["revenue"],
            records=[_record("revenue", "deep_reviewed", pack_id="contract-revenue")],
            suite=self.suite,
        )
        self.assertIn("deep_review_pack_not_activated", report["blocker_codes"])
        self.assertFalse(report["senior_accountant_claim_allowed"])

        with self.assertRaisesRegex(ContractError, "pack"):
            self.api.assess_account_universe(
                source_account_family_ids=["revenue"],
                records=[_record("revenue", "deep_reviewed", pack_id="unknown-pack")],
                suite=self.suite,
            )

    def test_requested_full_claim_fails_closed(self):
        with self.assertRaisesRegex(ContractError, "Full|full"):
            self.api.assess_account_universe(
                source_account_family_ids=["revenue"],
                records=[_record("revenue", "deep_reviewed", pack_id="contract-revenue")],
                suite=self.suite,
                requested_product_claim="company_wide_accounting_full",
            )


if __name__ == "__main__":
    unittest.main()
