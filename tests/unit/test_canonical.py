import unittest
from decimal import Decimal

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads


class CanonicalTests(unittest.TestCase):
    def test_duplicate_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            strict_loads('{"a":1,"a":2}')

    def test_non_finite_numbers_are_rejected(self) -> None:
        for payload in ('{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                strict_loads(payload)

    def test_decimal_and_declared_set_array_are_canonical(self) -> None:
        value = {"b": Decimal("-0"), "a": ["z", "a"]}
        actual = canonical_bytes(value, set_paths={"/a"})
        self.assertEqual(b'{"a":["a","z"],"b":"0"}', actual)

    def test_regular_array_order_is_preserved(self) -> None:
        self.assertEqual(
            b'{"a":["z","a"]}',
            canonical_bytes({"a": ["z", "a"]}),
        )


if __name__ == "__main__":
    unittest.main()

