from __future__ import annotations

import unittest
from decimal import Decimal

from trusted_ceo_agent.service.source_uploads import (
    registry_upload_usage,
    uploaded_file_summaries,
)


class SourceUploadProjectionTests(unittest.TestCase):
    def test_registry_usage_and_public_summaries_share_one_projection(self) -> None:
        registry = [{
            'source_id': 'source_' + ('a' * 24),
            'sha256': 'b' * 64,
            'size_bytes': Decimal(12),
            'display_name': 'strategy/plan.md',
            'aliases': ['plan.md'],
            'media_type': 'text/markdown',
        }]

        paths, sizes = registry_upload_usage(registry)
        summaries = uploaded_file_summaries(registry)

        self.assertEqual({
            'strategy/plan.md': 'source_' + ('a' * 24),
            'plan.md': 'source_' + ('a' * 24),
        }, paths)
        self.assertEqual({'b' * 64: 12}, sizes)
        self.assertEqual(
            ['plan.md', 'strategy/plan.md'],
            [item.logical_path for item in summaries],
        )
        self.assertEqual(
            ['\uac1c\ubcc4 \ud30c\uc77c', 'strategy'],
            [item.collection_label for item in summaries],
        )


if __name__ == '__main__':
    unittest.main()
