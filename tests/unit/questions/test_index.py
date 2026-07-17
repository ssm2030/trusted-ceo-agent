from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.questions.index import QuestionIndex
from tests.unit.questions.support import ROOT, RUN_ID, copy_files, finalized_files


class QuestionIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        _, cls.files = finalized_files(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_finalized_snapshot_indexes_only_plugin_owned_references(self) -> None:
        index = QuestionIndex.from_snapshot(self.files)

        self.assertEqual(RUN_ID, index.run_id)
        self.assertEqual(2, index.revision)
        self.assertEqual(["issue_main"], sorted(index.issues))
        self.assertEqual(["cause_main"], sorted(index.claims))
        self.assertEqual(1, len(index.facts))
        self.assertEqual(1, len(index.evidence_links))
        self.assertEqual(1, len(index.sources))
        self.assertEqual(1, len(index.value_table))

    def test_unfinalized_snapshot_is_rejected(self) -> None:
        files = copy_files(self.files)
        files["workflow/state.json"] = canonical_bytes(
            {"run_id": RUN_ID, "revision": 2, "state": "writer_ready"}
        )

        with self.assertRaisesRegex(ContractError, "finalized"):
            QuestionIndex.from_snapshot(files)


if __name__ == "__main__":
    unittest.main()
