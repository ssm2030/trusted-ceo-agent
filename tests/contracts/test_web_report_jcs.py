from __future__ import annotations

import hashlib
import math
import unittest
from decimal import Decimal

from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256


class WebReportJcsTests(unittest.TestCase):
    def test_rfc8785_number_string_and_property_order_vector(self) -> None:
        value = {
            "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
            "string": "\u20ac$\u000f\nA'B\"\\\\\"/",
            "literals": [None, True, False],
        }
        expected = (
            '{"literals":[null,true,false],'
            '"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
            '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
        ).encode("utf-8")

        self.assertEqual(expected, jcs_bytes(value))

    def test_negative_zero_and_decimal_values_follow_jcs_number_format(self) -> None:
        self.assertEqual(
            b'{"decimal":0.002,"negativeZero":0}',
            jcs_bytes(
                {
                    "negativeZero": -0.0,
                    "decimal": Decimal("0.002"),
                }
            ),
        )

    def test_non_finite_numbers_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf, Decimal("NaN")):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                jcs_bytes({"number": value})

    def test_hash_can_omit_only_the_named_root_field(self) -> None:
        value = {
            "a": 1,
            "bundle_hash": "f" * 64,
            "nested": {"bundle_hash": "keep"},
        }
        expected = hashlib.sha256(
            jcs_bytes({"a": 1, "nested": {"bundle_hash": "keep"}})
        ).hexdigest()

        self.assertEqual(
            expected,
            jcs_sha256(value, omit_root_field="bundle_hash"),
        )

    def test_hashing_does_not_mutate_the_input(self) -> None:
        value = {
            "bundle_hash": "f" * 64,
            "nested": {"bundle_hash": "keep"},
        }

        jcs_sha256(value, omit_root_field="bundle_hash")

        self.assertEqual("f" * 64, value["bundle_hash"])
        self.assertEqual("keep", value["nested"]["bundle_hash"])


if __name__ == "__main__":
    unittest.main()
