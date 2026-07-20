from __future__ import annotations

import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


class HumanInteractionSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = SchemaStore()

    def card(self) -> dict:
        return {
            "action_id": "action_0123456789abcdef01234567",
            "schema_version": "1.0.0",
            "run_id": "run_20260717T000000Z_0123456789abcdef",
            "base_revision": 4,
            "workflow_state": "data_confirmation_required",
            "gate": "data",
            "action_type": "data_request",
            "title": "추가 자료가 필요합니다",
            "question": "자료 제공 방식을 선택해 주세요.",
            "why_asked": "필수 절차 근거가 부족합니다.",
            "current_interpretation": "현재 자료로 판단할 수 없습니다.",
            "evidence_refs": [],
            "required": True,
            "allowed_response_types": [
                "provide_data", "proceed_limited", "request_explanation", "stop"
            ],
            "options": [{
                "option_id": "provide_now",
                "label": "지금 제공",
                "response_type": "provide_data",
                "description": "자료를 추가합니다.",
            }],
            "recommended_option_id": None,
            "recommendation_reason": None,
            "unanswered_effect": "Not Assessable로 남습니다.",
            "next_step_by_option": {"provide_now": "snapshot을 검증합니다."},
            "expires_at": "2026-07-17T00:10:00Z",
            "content_hash": "a" * 64,
        }

    def test_card_response_and_receipt_are_closed_contracts(self) -> None:
        card = self.card()
        self.schemas.validate("human-action-card.schema.json", card)
        response = {
            "response_id": "response_0123456789abcdef01234567",
            "schema_version": "1.0.0",
            "run_id": card["run_id"],
            "base_revision": 4,
            "action_id": card["action_id"],
            "action_content_hash": card["content_hash"],
            "response_type": "proceed_limited",
            "payload": {
                "unavailable_reason": "not_collected",
                "missing_source_roles": ["contract_register"],
                "missing_capabilities": ["revenue_contract_terms"],
                "executable_procedure_refs": ["procedure_ratio_scan"],
                "unexecutable_procedure_refs": ["procedure_contract_reperformance"],
                "affected_issue_family_refs": ["RV-03"],
                "affected_domains": ["accounting"],
                "expected_limits": ["Not Assessable"],
                "confirmed_limitations": True,
                "patch_operations": [],
                "runtime_context": {},
            },
            "actor_id": "ceo-1",
            "response_hash": "b" * 64,
            "idempotency_key_hash": "c" * 64,
            "created_at": "2026-07-17T00:01:00Z",
        }
        self.schemas.validate("human-response.schema.json", response)
        receipt = {
            "response_id": response["response_id"],
            "run_id": card["run_id"],
            "base_revision": 4,
            "result_revision": 5,
            "action_id": card["action_id"],
            "response_hash": response["response_hash"],
            "affected_paths": ["/mapping"],
            "invalidated_approval_refs": ["approval_0123456789abcdef01234567"],
            "workflow_state": "data_confirmation_required",
            "pending_action_ref": None,
            "terminal_approval_required": True,
            "created_at": "2026-07-17T00:01:00Z",
        }
        self.schemas.validate("human-response-receipt.schema.json", receipt)
        card["unknown"] = True
        with self.assertRaises(ContractError):
            self.schemas.validate("human-action-card.schema.json", card)

    def test_proceed_limited_requires_explicit_limit_fields(self) -> None:
        card = self.card()
        response = {
            "response_id": "response_0123456789abcdef01234567",
            "schema_version": "1.0.0",
            "run_id": card["run_id"],
            "base_revision": 4,
            "action_id": card["action_id"],
            "action_content_hash": card["content_hash"],
            "response_type": "proceed_limited",
            "payload": {},
            "actor_id": "ceo-1",
            "response_hash": "b" * 64,
            "idempotency_key_hash": "c" * 64,
            "created_at": "2026-07-17T00:01:00Z",
        }
        with self.assertRaises(ContractError):
            self.schemas.validate("human-response.schema.json", response)

    def test_read_only_and_terminal_response_payloads_cannot_smuggle_changes(self) -> None:
        card = self.card()
        base = {
            "response_id": "response_0123456789abcdef01234567",
            "schema_version": "1.0.0",
            "run_id": card["run_id"],
            "base_revision": 4,
            "action_id": card["action_id"],
            "action_content_hash": card["content_hash"],
            "actor_id": "ceo-1",
            "response_hash": "b" * 64,
            "idempotency_key_hash": "c" * 64,
            "created_at": "2026-07-17T00:01:00Z",
        }
        cases = (
            ("confirm", {"patch_operations": []}),
            ("request_explanation", {"question": "왜인가요?", "patch_operations": []}),
            ("stop", {"reason": "중단", "patch_operations": []}),
            ("request_changes", {"text": "변경", "runtime_context": {"chain_of_thought": "forbidden"}}),
        )
        for response_type, payload in cases:
            with self.subTest(response_type=response_type):
                candidate = {**base, "response_type": response_type, "payload": payload}
                with self.assertRaises(ContractError):
                    self.schemas.validate("human-response.schema.json", candidate)

    def test_approval_schema_separates_tty_and_web_provenance(self) -> None:
        base = {
            "approval_id": "approval_0123456789abcdef01234567",
            "approval_request_id": "approvalrequest_0123456789abcdef01234567",
            "gate": "final",
            "base_artifact_ref": "artifact_001@r0000",
            "result_artifact_ref": "artifact_001@r0002",
            "decision": "approve",
            "confirmed": True,
            "actor_id": "ceo-1",
            "actor_role": "ceo",
            "target_refs": [],
            "authorized_component_ids": [],
            "patch_operations": [],
            "rationale": "검토 후 승인",
            "created_at": "2026-07-17T00:01:00Z",
            "nonce_hash": "a" * 64,
            "supersedes_approval_id": None,
            "status": "current",
            "approval_hash": "b" * 64,
        }
        tty = {
            **base,
            "input_method": "interactive_tty",
            "tty_session_fingerprint": "c" * 64,
        }
        web = {
            **base,
            "input_method": "web_hitl",
            "browser_session_fingerprint": "d" * 64,
            "response_hash": "e" * 64,
        }
        self.schemas.validate("approval.schema.json", tty)
        self.schemas.validate("approval.schema.json", web)

        with self.assertRaises(ContractError):
            self.schemas.validate(
                "approval.schema.json",
                {**web, "tty_session_fingerprint": "f" * 64},
            )


if __name__ == "__main__":
    unittest.main()
