from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.resolver import resolve_norm

from tests.professional_knowledge_support import make_knowledge_bundle


class NormResolverTests(unittest.TestCase):
    def test_effective_period_boundaries_and_jurisdiction(self):
        _, cards, _, _ = make_knowledge_bundle()
        norm = [card for card in cards if card["artifact_type"] == "norm_card"][0]
        self.assertEqual(
            norm["artifact_id"],
            resolve_norm(
                [norm],
                issue_family_id="AC-TEST",
                jurisdiction="KR",
                effective_on="2026-01-01",
            )["artifact_id"],
        )
        self.assertEqual(
            norm["artifact_id"],
            resolve_norm(
                [norm],
                issue_family_id="AC-TEST",
                jurisdiction="KR",
                effective_on="2026-12-31",
            )["artifact_id"],
        )
        with self.assertRaisesRegex(ContractError, "effective_period_gap"):
            resolve_norm(
                [norm],
                issue_family_id="AC-TEST",
                jurisdiction="KR",
                effective_on="2027-01-01",
            )
        with self.assertRaisesRegex(ContractError, "jurisdiction_mismatch"):
            resolve_norm(
                [norm],
                issue_family_id="AC-TEST",
                jurisdiction="US",
                effective_on="2026-06-30",
            )

    def test_revoked_or_source_hash_mismatched_norm_is_rejected(self):
        _, cards, _, _ = make_knowledge_bundle()
        norm = [card for card in cards if card["artifact_type"] == "norm_card"][0]
        revoked = copy.deepcopy(norm)
        revoked["status"] = "revoked"
        with self.assertRaisesRegex(ContractError, "norm_contract_invalid"):
            resolve_norm(
                [revoked],
                issue_family_id="AC-TEST",
                jurisdiction="KR",
                effective_on="2026-06-30",
            )

        _, mismatched_cards, _, _ = make_knowledge_bundle(
            source_hash="a" * 64, verified_hash="d" * 64
        )
        mismatched = [
            card for card in mismatched_cards if card["artifact_type"] == "norm_card"
        ][0]
        with self.assertRaisesRegex(ContractError, "source_hash_mismatch"):
            resolve_norm(
                [mismatched],
                issue_family_id="AC-TEST",
                jurisdiction="KR",
                effective_on="2026-06-30",
            )


if __name__ == "__main__":
    unittest.main()
