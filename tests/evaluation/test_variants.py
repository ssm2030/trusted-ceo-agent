import unittest

from trusted_ceo_agent.poc import semantic_fingerprint


class VariantTests(unittest.TestCase):
    def test_key_and_record_order_do_not_change_semantics(self) -> None:
        left = {"rows": [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}], "unit": "KRW"}
        right = {"unit": "KRW", "rows": [{"b": "4", "a": "3"}, {"b": "2", "a": "1"}]}
        self.assertEqual(semantic_fingerprint(left), semantic_fingerprint(right))


if __name__ == "__main__":
    unittest.main()

