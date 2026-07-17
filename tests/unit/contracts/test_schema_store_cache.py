from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


class SchemaStoreCacheTests(unittest.TestCase):
    def test_unchanged_bundle_reuses_cache_and_changed_bundle_invalidates(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            path = root / "value.schema.json"
            path.write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "value.schema.json",
                "const": 1,
            }), encoding="utf-8")
            first = SchemaStore(root)
            second = SchemaStore(root)
            self.assertIs(first._state, second._state)
            second.validate("value.schema.json", 1)

            path.write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "value.schema.json",
                "const": 22,
            }), encoding="utf-8")
            third = SchemaStore(root)
            self.assertIsNot(first._state, third._state)
            third.validate("value.schema.json", 22)
            with self.assertRaises(ContractError):
                third.validate("value.schema.json", 1)


if __name__ == "__main__":
    unittest.main()
