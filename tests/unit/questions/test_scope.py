from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.questions.index import QuestionIndex
from trusted_ceo_agent.questions.scope import ScopeRequired, resolve_scope
from tests.unit.questions.support import ROOT, finalized_files


class QuestionScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        _, files = finalized_files(Path(cls.temporary.name))
        cls.index = QuestionIndex.from_snapshot(files)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_issue_scope_walks_only_reachable_refs_in_id_order(self) -> None:
        closure = resolve_scope(
            self.index,
            "issue",
            "issue_main",
            maximum_bytes=131_072,
        )

        self.assertEqual(("issue_main",), closure.issue_ids)
        self.assertEqual(tuple(sorted(closure.claim_refs)), closure.claim_refs)
        self.assertEqual(
            tuple(sorted(closure.evidence_link_ids)),
            closure.evidence_link_ids,
        )
        self.assertTrue(closure.fact_ids)
        self.assertTrue(closure.source_refs)

    def test_complete_scope_overflow_requires_narrower_scope(self) -> None:
        with self.assertRaises(ScopeRequired) as raised:
            resolve_scope(self.index, "run", "run", maximum_bytes=64)

        self.assertEqual("SCOPE_REQUIRED", raised.exception.code)
        self.assertTrue(raised.exception.suggestions)

    def test_evidence_and_source_have_distinct_scope_identity(self) -> None:
        evidence_id = next(iter(self.index.evidence_links))
        source_id = next(iter(self.index.sources))

        evidence = resolve_scope(self.index, "evidence", evidence_id)
        source = resolve_scope(self.index, "source", source_id)

        self.assertNotEqual(evidence.start_refs, source.start_refs)
        self.assertEqual("evidence", evidence.scope_kind)
        self.assertEqual("source", source.scope_kind)


if __name__ == "__main__":
    unittest.main()
