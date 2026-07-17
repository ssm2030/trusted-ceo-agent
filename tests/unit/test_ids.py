import unittest

from trusted_ceo_agent.contracts.ids import fact_id, make_id


class IdTests(unittest.TestCase):
    def test_id_has_kind_and_24_hex_digest(self) -> None:
        value = make_id("source", {"sha256": "a" * 64})
        kind, digest = value.split("_", 1)
        self.assertEqual("source", kind)
        self.assertEqual(24, len(digest))
        int(digest, 16)

    def test_observed_roles_and_lineages_do_not_collide(self) -> None:
        left = fact_id(
            "observed", "revenue", "ledger", {"bu": "A"},
            {"period": "2026-01"}, "rows-a"
        )
        right = fact_id(
            "observed", "revenue", "operations", {"bu": "A"},
            {"period": "2026-01"}, "rows-b"
        )
        self.assertNotEqual(left, right)


if __name__ == "__main__":
    unittest.main()
