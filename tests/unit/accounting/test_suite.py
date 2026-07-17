import copy
import importlib
import unittest

from trusted_ceo_agent.errors import ContractError, IntegrityError


def _api():
    try:
        return importlib.import_module("trusted_ceo_agent.accounting.suite")
    except ModuleNotFoundError as error:
        raise AssertionError(f"accounting suite API is missing: {error}") from error


class AccountingSuiteTests(unittest.TestCase):
    def setUp(self):
        self.api = _api()
        self.suite = self.api.build_machine_draft_suite(
            release_id="accounting-suite-2026-07-17",
            effective_from="2026-07-17",
        )

    def test_seed_has_exact_four_packs_and_64_issue_families(self):
        expected = {
            f"{prefix}-{number:02d}"
            for prefix in ("AC", "RV", "CF", "CA")
            for number in range(1, 17)
        }
        self.assertEqual(
            {item["issue_family_id"] for item in self.suite["issue_families"]},
            expected,
        )
        self.assertEqual(len(self.suite["issue_families"]), 64)
        self.assertEqual(
            {pack["pack_id"] for pack in self.suite["packs"]},
            {
                "accounting-core",
                "contract-revenue",
                "cash-flow-working-capital",
                "project-cost-allocation",
            },
        )
        self.assertTrue(all(pack["issue_family_count"] == 16 for pack in self.suite["packs"]))

    def test_all_nine_suite_designs_are_required_inputs(self):
        self.assertEqual(len(self.suite["design_refs"]), 9)
        self.assertIn(
            "docs/superpowers/specs/2026-07-17-accounting-content-suite-index.md",
            self.suite["design_refs"],
        )
        self.assertIn(
            "docs/superpowers/specs/2026-07-17-accounting-norm-procedure-seed-catalog.md",
            self.suite["design_refs"],
        )

    def test_each_family_carries_minimum_contract_and_d1_to_d12_links(self):
        expected_depth = [f"D{number}" for number in range(1, 13)]
        for issue in self.suite["issue_families"]:
            self.assertEqual(issue["depth_gate_refs"], expected_depth)
            for field in (
                "economic_event_types",
                "accounts",
                "assertions",
                "mandatory_data_roles",
                "expectation_card_refs",
                "norm_card_refs",
                "procedure_card_refs",
                "counter_hypothesis_refs",
                "calculation_refs",
                "cross_domain_trigger_refs",
                "required_test_case_types",
                "not_assessable_conditions",
            ):
                self.assertTrue(issue[field], f"{issue['issue_family_id']} missing {field}")
            self.assertEqual(issue["authority_ceiling"], "Boundary")

    def test_tier_zero_is_exact_and_mandatory(self):
        self.assertEqual(
            self.suite["tier_zero"]["mandatory_issue_family_ids"],
            ["AC-01", "AC-02", "AC-03", "AC-04", "AC-05"],
        )
        self.assertEqual(
            set(self.suite["tier_zero"]["required_reconciliations"]),
            {"debit_credit", "opening_closing", "gl_tb", "subledger_gl", "bank_gl"},
        )

    def test_missing_duplicate_or_cross_pack_family_fails_closed(self):
        missing = copy.deepcopy(self.suite)
        missing["issue_families"].pop()
        missing = self.api.rehash_suite(missing)
        with self.assertRaisesRegex(ContractError, "64|missing"):
            self.api.validate_accounting_suite(missing)

        duplicate = copy.deepcopy(self.suite)
        duplicate["issue_families"][-1] = copy.deepcopy(duplicate["issue_families"][0])
        duplicate = self.api.rehash_suite(duplicate)
        with self.assertRaisesRegex(ContractError, "duplicate|missing"):
            self.api.validate_accounting_suite(duplicate)

        cross_pack = copy.deepcopy(self.suite)
        cross_pack["issue_families"][0]["cycle_id"] = "contract_revenue"
        cross_pack = self.api.rehash_suite(cross_pack)
        with self.assertRaisesRegex(ContractError, "cycle|pack"):
            self.api.validate_accounting_suite(cross_pack)

    def test_unknown_or_missing_norm_and_procedure_refs_fail_closed(self):
        unknown_norm = copy.deepcopy(self.suite)
        unknown_norm["issue_families"][0]["norm_card_refs"] = ["N-NOT-REAL"]
        unknown_norm = self.api.rehash_suite(unknown_norm)
        with self.assertRaisesRegex(ContractError, "Norm|norm"):
            self.api.validate_accounting_suite(unknown_norm)

        empty_procedure = copy.deepcopy(self.suite)
        empty_procedure["issue_families"][0]["procedure_card_refs"] = []
        empty_procedure = self.api.rehash_suite(empty_procedure)
        with self.assertRaises(ContractError):
            self.api.validate_accounting_suite(empty_procedure)

    def test_pack_and_suite_hashes_are_verified(self):
        tampered_pack = copy.deepcopy(self.suite)
        tampered_pack["packs"][0]["effective_period"]["from"] = "2026-07-18"
        with self.assertRaisesRegex(IntegrityError, "pack"):
            self.api.validate_accounting_suite(tampered_pack)

        tampered_suite = copy.deepcopy(self.suite)
        tampered_suite["release_id"] = "changed"
        with self.assertRaisesRegex(IntegrityError, "suite"):
            self.api.validate_accounting_suite(tampered_suite)

    def test_effective_period_is_ordered_and_pack_bound_to_suite(self):
        invalid = copy.deepcopy(self.suite)
        invalid["effective_period"] = {"from": "2026-08-01", "to": "2026-07-01"}
        invalid = self.api.rehash_suite(invalid)
        with self.assertRaisesRegex(ContractError, "effective"):
            self.api.validate_accounting_suite(invalid)

        divergent = copy.deepcopy(self.suite)
        divergent["packs"][0]["effective_period"]["from"] = "2026-07-18"
        divergent = self.api.rehash_suite(divergent, rehash_packs=True)
        with self.assertRaisesRegex(ContractError, "effective"):
            self.api.validate_accounting_suite(divergent)

    def test_machine_draft_cannot_be_promoted_without_expert_and_release_gates(self):
        for forbidden in ("Provisional", "Full"):
            promoted = copy.deepcopy(self.suite)
            promoted["authority"] = forbidden
            promoted = self.api.rehash_suite(promoted)
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ContractError, "expert|release|Full"):
                    self.api.validate_accounting_suite(promoted)

    def test_boundary_claim_requires_implemented_grounded_pack_not_just_label(self):
        relabeled = copy.deepcopy(self.suite)
        relabeled["authority"] = "Boundary"
        relabeled = self.api.rehash_suite(relabeled)
        with self.assertRaisesRegex(ContractError, "Procedure|Depth|Norm|authority"):
            self.api.assert_product_claim_allowed(relabeled, "three_cycles_boundary")

    def test_rehashed_design_content_and_pack_tier_zero_tampering_fails(self):
        changed_title = copy.deepcopy(self.suite)
        changed_title["issue_families"][0]["title"] = "plausible but unapproved replacement"
        changed_title = self.api.rehash_suite(changed_title)
        with self.assertRaisesRegex(ContractError, "seed|design|AC-01"):
            self.api.validate_accounting_suite(changed_title)

        tier_zero = copy.deepcopy(self.suite)
        tier_zero["packs"][0]["tier_zero_issue_family_ids"] = []
        tier_zero = self.api.rehash_suite(tier_zero, rehash_packs=True)
        with self.assertRaisesRegex(ContractError, "Tier 0"):
            self.api.validate_accounting_suite(tier_zero)

    def test_initial_suite_never_claims_company_wide_full(self):
        with self.assertRaisesRegex(ContractError, "company-wide|company_wide"):
            self.api.assert_product_claim_allowed(self.suite, "company_wide_accounting_full")
        self.assertEqual(
            self.api.assert_product_claim_allowed(self.suite, "machine_draft"),
            "machine_draft",
        )

    def test_readiness_exposes_unverified_norm_and_expert_boundaries(self):
        readiness = self.api.assess_suite_readiness(self.suite)
        self.assertFalse(readiness["analysis_plane_activation_allowed"])
        self.assertFalse(readiness["senior_accountant_claim_allowed"])
        self.assertIn("norm_grounding_unverified", readiness["blocker_codes"])
        self.assertIn("expert_review_required", readiness["blocker_codes"])
        self.assertIn("procedure_implementation_incomplete", readiness["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
