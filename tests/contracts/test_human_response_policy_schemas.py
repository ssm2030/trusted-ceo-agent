from __future__ import annotations

import hashlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.workflow.human_response_policy import (
    evaluate_human_response_policy,
    verify_human_response_policy,
    verify_human_response_policy_decision,
)


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _policy(*, restricted_source_allowlist: list[str] | None = None) -> dict:
    value = {
        "schema_version": "1.0.0",
        "policy_id": "human-response-local-owner",
        "policy_version": "1.0.0",
        "transport_principal": "local-owner",
        "authorized_actors": [{
            "actor_id": "ceo-1",
            "roles": ["run_owner"],
            "allowed_gates": ["context", "data", "scope_narrowing", "diagnostic", "final"],
        }],
        "restricted_source_allowlist": sorted(restricted_source_allowlist or []),
        "privacy_policy": {
            "direct_identifier_reasoning": "forbidden",
            "minimum_group_size": 5,
        },
    }
    value["policy_hash"] = _hash(value)
    return value


def _action(*, gate: str = "data") -> dict:
    return {
        "action_id": "action_0123456789abcdef01234567",
        "content_hash": "a" * 64,
        "gate": gate,
    }


def _normalized_response(
    *,
    response_type: str = "provide_data",
    payload: dict | None = None,
) -> dict:
    return {
        "response_type": response_type,
        "payload": payload if payload is not None else {
            "source_refs": ["source_0123456789abcdef01234567"],
        },
        "actor_id": "ceo-1",
    }


def _record(response: dict) -> dict:
    return {
        "response_id": "response_0123456789abcdef01234567",
        "action_id": "action_0123456789abcdef01234567",
        "action_content_hash": "a" * 64,
        "response_type": response["response_type"],
        "payload": response["payload"],
        "actor_id": response["actor_id"],
    }


def _files(policy: dict, *, access_policy: str = "permitted") -> dict[str, bytes]:
    return {
        "workflow/human-response-policy.json": canonical_bytes(policy),
        "sources/registry.json": canonical_bytes([{
            "source_id": "source_0123456789abcdef01234567",
            "access_policy": access_policy,
        }]),
    }


class HumanResponsePolicySchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = SchemaStore()

    def test_policy_decision_and_resolution_are_closed_contracts(self) -> None:
        policy = _policy()
        self.schemas.validate("human-response-policy.schema.json", policy)
        decision = {
            "schema_version": "1.0.0",
            "policy_id": policy["policy_id"],
            "policy_version": policy["policy_version"],
            "policy_hash": policy["policy_hash"],
            "action_id": "action_0123456789abcdef01234567",
            "response_id": "response_0123456789abcdef01234567",
            "gate": "data",
            "actor_id": "ceo-1",
            "transport_subject": "local-owner",
            "allowed": True,
            "reason_codes": ["authorized"],
            "evaluated_source_refs": ["source_0123456789abcdef01234567"],
            "created_at": "2026-07-17T00:01:00Z",
        }
        decision["decision_hash"] = _hash(decision)
        self.schemas.validate("human-response-policy-decision.schema.json", decision)
        resolution = {
            "schema_version": "1.0.0",
            "action_id": "action_0123456789abcdef01234567",
            "action_content_hash": "a" * 64,
            "response_id": "response_0123456789abcdef01234567",
            "result_revision": 5,
            "workflow_state": "data_confirmation_required",
            "disposition": "resolved",
            "created_at": "2026-07-17T00:01:00Z",
        }
        resolution["resolution_hash"] = _hash(resolution)
        self.schemas.validate("human-action-resolution.schema.json", resolution)

        for schema_name, value in (
            ("human-response-policy.schema.json", dict(policy)),
            ("human-response-policy-decision.schema.json", dict(decision)),
            ("human-action-resolution.schema.json", dict(resolution)),
        ):
            with self.subTest(schema=schema_name):
                value["unknown"] = True
                with self.assertRaises(ContractError):
                    self.schemas.validate(schema_name, value)

    def test_evaluator_allows_bound_permitted_response_and_verifies_hashes(self) -> None:
        policy = _policy()
        response = _normalized_response()
        decision = evaluate_human_response_policy(
            files=_files(policy),
            action=_action(),
            normalized_response=response,
            response_record=_record(response),
            trusted_principal={"subject": "local-owner", "roles": ["run_owner"]},
            created_at="2026-07-17T00:01:00Z",
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(["authorized"], decision["reason_codes"])
        verify_human_response_policy(policy)
        verify_human_response_policy_decision(decision)

        tampered = dict(decision)
        tampered["allowed"] = False
        with self.assertRaisesRegex(ContractError, "decision hash"):
            verify_human_response_policy_decision(tampered)

    def test_evaluator_denies_transport_actor_role_and_gate_failures(self) -> None:
        policy = _policy()
        response = _normalized_response()
        cases = (
            (
                {"subject": "another-user", "roles": ["run_owner"]},
                _action(),
                response,
                "transport_principal_mismatch",
            ),
            (
                {"subject": "local-owner", "roles": ["viewer"]},
                _action(),
                response,
                "transport_role_not_authorized",
            ),
            (
                {"subject": "local-owner", "roles": ["run_owner"]},
                _action(),
                {**response, "actor_id": "intruder"},
                "actor_not_authorized",
            ),
            (
                {"subject": "local-owner", "roles": ["run_owner"]},
                _action(gate="legal"),
                response,
                "gate_not_authorized",
            ),
        )
        for principal, action, candidate, reason in cases:
            with self.subTest(reason=reason):
                record = _record(candidate)
                record["action_id"] = action["action_id"]
                decision = evaluate_human_response_policy(
                    files=_files(policy),
                    action=action,
                    normalized_response=candidate,
                    response_record=record,
                    trusted_principal=principal,
                    created_at="2026-07-17T00:01:00Z",
                )
                self.assertFalse(decision["allowed"])
                self.assertIn(reason, decision["reason_codes"])
                verify_human_response_policy_decision(decision)

    def test_source_policy_is_fail_closed(self) -> None:
        response = _normalized_response()
        cases = (
            (_policy(), "prohibited", "source_prohibited"),
            (_policy(), "restricted", "source_restricted_not_allowlisted"),
        )
        for policy, access_policy, reason in cases:
            with self.subTest(reason=reason):
                decision = evaluate_human_response_policy(
                    files=_files(policy, access_policy=access_policy),
                    action=_action(),
                    normalized_response=response,
                    response_record=_record(response),
                    trusted_principal={"subject": "local-owner", "roles": ["run_owner"]},
                    created_at="2026-07-17T00:01:00Z",
                )
                self.assertFalse(decision["allowed"])
                self.assertIn(reason, decision["reason_codes"])

        source_id = response["payload"]["source_refs"][0]
        policy = _policy(restricted_source_allowlist=[source_id])
        allowed = evaluate_human_response_policy(
            files=_files(policy, access_policy="restricted"),
            action=_action(),
            normalized_response=response,
            response_record=_record(response),
            trusted_principal={"subject": "local-owner", "roles": ["run_owner"]},
            created_at="2026-07-17T00:01:00Z",
        )
        self.assertTrue(allowed["allowed"])

    def test_request_explanation_is_policy_evaluated_without_source_registry(self) -> None:
        policy = _policy()
        response = _normalized_response(
            response_type="request_explanation",
            payload={"question": "Why is this gate required?"},
        )
        decision = evaluate_human_response_policy(
            files={"workflow/human-response-policy.json": canonical_bytes(policy)},
            action=_action(gate="context"),
            normalized_response=response,
            response_record=_record(response),
            trusted_principal={"subject": "local-owner", "roles": ["run_owner"]},
            created_at="2026-07-17T00:01:00Z",
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual([], decision["evaluated_source_refs"])

    def test_policy_hash_and_response_binding_fail_closed(self) -> None:
        policy = _policy()
        corrupt = dict(policy)
        corrupt["transport_principal"] = "attacker"
        response = _normalized_response()
        with self.assertRaisesRegex(ContractError, "policy hash"):
            evaluate_human_response_policy(
                files=_files(corrupt),
                action=_action(),
                normalized_response=response,
                response_record=_record(response),
                trusted_principal={"subject": "local-owner", "roles": ["run_owner"]},
                created_at="2026-07-17T00:01:00Z",
            )

        record = _record(response)
        record["actor_id"] = "different"
        decision = evaluate_human_response_policy(
            files=_files(policy),
            action=_action(),
            normalized_response=response,
            response_record=record,
            trusted_principal={"subject": "local-owner", "roles": ["run_owner"]},
            created_at="2026-07-17T00:01:00Z",
        )
        self.assertFalse(decision["allowed"])
        self.assertIn("response_binding_mismatch", decision["reason_codes"])


if __name__ == "__main__":
    unittest.main()
