import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.approvals import ApprovalService
from trusted_ceo_agent.workflow.revisions import RevisionManager


class TtyApprovalSafetyTests(unittest.TestCase):
    def test_pipe_or_redirect_cannot_approve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            store.create_run("run_20260717T000000Z_0123456789abcdef")
            service = ApprovalService(
                RevisionManager(store),
                clock=lambda: datetime(2026, 7, 17, tzinfo=timezone.utc),
                nonce_factory=lambda: "nonce",
            )
            request, _, revision = service.request(
                expected_revision=0, gate="diagnostic", base_artifact_ref="artifact_1", base_artifact_hash="a" * 64,
                patch_operations=[], invalidated_approval_ids=[], result_preview_hash="b" * 64,
            )
            with self.assertRaisesRegex(ContractError, "TTY"):
                service.approve_interactive(
                    request["approval_request_id"], expected_revision=revision,
                    input_stream=io.StringIO("ceo\nceo\nnonce\nAPPROVE\n"), output_stream=io.StringIO(),
                )


if __name__ == "__main__":
    unittest.main()
