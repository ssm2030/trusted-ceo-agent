import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.evidence.lineage import LineageStore


class LineageTests(unittest.TestCase):
    def test_multiset_preserves_duplicate_occurrences_and_exact_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LineageStore(Path(directory))
            left = store.put([{"id": "1"}, {"id": "1"}, {"id": "2"}])
            right = store.put([{"id": "1"}, {"id": "3"}])
            payload = store.load(left)
            duplicate_entries = [entry for entry in payload["entries"] if entry["occurrence_index"] in (1, 2)]
            self.assertGreaterEqual(len(duplicate_entries), 2)
            self.assertEqual(1, store.intersection_count(left, right))


if __name__ == "__main__":
    unittest.main()
