from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError

from trusted_ceo_agent.service.contracts import (
    ERROR_CODES,
    HitlCard,
    HitlDecisionRequest,
    HitlSection,
    MutationBase,
    RunSnapshot,
    ServiceErrorBody,
)


class ServiceContractTests(unittest.TestCase):
    def test_run_snapshot_is_strict_and_contains_only_browser_state(self) -> None:
        snapshot = RunSnapshot(
            run_id="run_contract_12345678",
            revision=3,
            workflow_status="data_confirmation_required",
            ui_phase=2,
            pending_action="human_response",
            allowed_actions=["submit_human_response", "stop"],
            latest_event="mapping proposal ready",
            progress=24,
            result_ref=None,
            hitl_card=HitlCard(
                hitl_kind="context_data",
                request_id="approval_request_123",
                base_revision=3,
                title="맥락과 데이터 확인",
                summary="검증된 제안을 확인해 주세요.",
                target_refs=["mission/mission-contract.json"],
                allowed_decisions=["approve", "approve_with_edits", "stop"],
                editable_fields=["business_question"],
                sections=[HitlSection(
                    kind="facts",
                    title="검증된 사실",
                    items=["검증된 Fact 2개"],
                    target_refs=["evidence/core.json"],
                )],
            ),
            error=None,
        )

        self.assertEqual("service", snapshot.provider_kind)
        self.assertEqual("실시간 AI 분석", snapshot.display_badge)
        payload = snapshot.model_dump(mode="json")
        self.assertNotIn("filesystem_path", str(payload))
        self.assertNotIn("model_output", payload)
        with self.assertRaises(ValidationError):
            RunSnapshot.model_validate({**payload, "unexpected": True})
        with self.assertRaises(ValidationError):
            RunSnapshot.model_validate({**payload, "progress": 101})
        with self.assertRaises(ValidationError):
            RunSnapshot.model_validate({
                **payload,
                "hitl_card": {**payload["hitl_card"], "base_revision": 2},
            })
        with self.assertRaises(ValidationError):
            RunSnapshot.model_validate({
                **payload,
                "result_ref": str(Path("C:/private/report.json")),
            })
        with self.assertRaises(ValidationError):
            snapshot.progress = 50  # type: ignore[misc]

    def test_service_error_contract_exposes_every_stable_code(self) -> None:
        expected = {
            "INPUT_POLICY_FAILURE",
            "HUMAN_RESPONSE_REQUIRED",
            "AI_AUTH_FAILURE",
            "AI_TRANSIENT_FAILURE",
            "AI_REFUSAL",
            "AI_OUTPUT_INVALID",
            "VALIDATION_FAILURE",
            "STALE_REVISION",
            "ENGINE_FAILURE",
            "STOPPED",
            "CANCELLED",
            "IDEMPOTENCY_CONFLICT",
        }
        self.assertEqual(expected, ERROR_CODES)
        self.assertIsInstance(ERROR_CODES, frozenset)
        body = ServiceErrorBody(
            code="AI_TRANSIENT_FAILURE",
            message="잠시 후 다시 시도해 주세요.",
            retryable=True,
        )
        self.assertTrue(body.retryable)
        with self.assertRaises(ValidationError):
            ServiceErrorBody(code="UNKNOWN", message="x", retryable=False)

    def test_mutation_and_hitl_decision_are_strict_normalized_contracts(self) -> None:
        mutation = MutationBase(
            expected_revision=0,
            idempotency_key="browser_action_1234",
        )
        self.assertEqual(0, mutation.expected_revision)
        with self.assertRaises(ValidationError):
            MutationBase(
                expected_revision=0,
                idempotency_key="browser_action_1234",
                extra=True,
            )
        with self.assertRaises(ValidationError):
            MutationBase(expected_revision=-1, idempotency_key="short")

        decision = HitlDecisionRequest(
            expected_revision=4,
            idempotency_key="browser_decision_1234",
            decision="approve_with_edits",
            edits={"business_question": "Cafe\u0301 growth"},
            rationale="  확인 후 수정합니다.  ",
        )
        self.assertEqual("Café growth", decision.edits["business_question"])
        self.assertEqual("확인 후 수정합니다.", decision.rationale)
        for invalid in (
            {"decision": "delete", "rationale": "안 됨"},
            {"decision": "reanalyze", "rationale": None},
            {"decision": "stop", "rationale": ""},
            {"decision": "approve", "rationale": "bad\u0000text"},
            {
                "decision": "approve_with_edits",
                "edits": {"threshold": 1.25},
                "rationale": "binary float is not canonical",
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    HitlDecisionRequest(
                        expected_revision=4,
                        idempotency_key="browser_decision_1234",
                        edits=invalid.pop("edits", {}),
                        **invalid,
                    )


if __name__ == "__main__":
    unittest.main()
