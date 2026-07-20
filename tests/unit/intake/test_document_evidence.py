from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.intake.document_evidence import (
    MAX_CHUNK_CHARACTERS,
    build_document_evidence,
    validate_document_evidence_registry,
)


SOURCE = {
    'source_id': 'source_' + 'a' * 24,
    'display_name': 'strategy/plan.md',
}


class DocumentEvidenceTests(unittest.TestCase):
    def test_heading_chunks_ignore_heading_looking_text_inside_fences(self) -> None:
        markdown = (
            '# 개요\n'
            '매출 가정을 검토합니다.\n'
            '\n'
            '# 세부/리스크\n'
            '```markdown\n'
            '## 실제 제목이 아님\n'
            '```\n'
        )

        evidence = build_document_evidence(SOURCE, markdown)

        self.assertEqual(
            [('개요', 1, 3), ('세부/리스크', 4, 7)],
            [
                ('/'.join(item['heading_path']), item['line_start'], item['line_end'])
                for item in evidence
            ],
        )
        self.assertIn('## 실제 제목이 아님', evidence[1]['content'])
        self.assertTrue(all(len(item['content']) <= MAX_CHUNK_CHARACTERS for item in evidence))
        self.assertTrue(all(item['locator_type'] == 'markdown_lines' for item in evidence))

    def test_crlf_and_lf_build_byte_identical_evidence(self) -> None:
        lf = '# 개요\n본문\n'
        crlf = lf.replace('\n', '\r\n')

        self.assertEqual(
            canonical_bytes(build_document_evidence(SOURCE, lf)),
            canonical_bytes(build_document_evidence(SOURCE, crlf)),
        )

    def test_overlong_line_splits_at_unicode_boundaries_with_original_line_number(self) -> None:
        evidence = build_document_evidence(SOURCE, '# 길이\n' + '가' * 2_001)

        self.assertGreaterEqual(len(evidence), 2)
        self.assertTrue(all(len(item['content']) <= 2_000 for item in evidence))
        line_two = [item for item in evidence if item['line_start'] == 2]
        self.assertTrue(line_two)
        self.assertTrue(all(item['line_end'] == 2 for item in line_two))
        self.assertEqual('가' * 2_001, ''.join(item['content'] for item in line_two))

    def test_output_is_stable_and_registry_tampering_is_rejected(self) -> None:
        markdown = '# 계획\n현금 흐름을 우선합니다.\n'
        first = build_document_evidence(SOURCE, markdown)
        second = build_document_evidence(dict(SOURCE), markdown)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        validate_document_evidence_registry(SOURCE, markdown, first)

        mutations = (
            ('content_sha256', '0' * 64),
            ('line_start', first[0]['line_start'] + 1),
            ('source_id', 'source_' + 'b' * 24),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                tampered = copy.deepcopy(first)
                tampered[0][field] = value
                with self.assertRaises(IntegrityError):
                    validate_document_evidence_registry(SOURCE, markdown, tampered)


if __name__ == '__main__':
    unittest.main()
