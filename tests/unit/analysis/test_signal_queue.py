from __future__ import annotations

import copy
import hashlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.evidence.signals import build_signal


def _api():
    from trusted_ceo_agent.analysis.signal_queue import SignalCaseQueue, materialize_signal_cases

    return SignalCaseQueue, materialize_signal_cases


def _signal(code: str) -> dict:
    return build_signal(
        signal_code=code,
        rule_ref=f"rule_{code}",
        component_id="component_signal_scan",
        component_version="1.0.0",
        component_run_id="component_run_" + hashlib.sha256(code.encode("utf-8")).hexdigest()[:24],
        threshold_ref=f"threshold_{code}",
        input_fact_ids=["fact_" + code[-1] * 24],
        required_fact_codes=[f"fact_{code}"],
        missing_fact_codes=[],
        scope=[{"dimension_code": "company", "member_code": "all"}],
        time_context={"period": "2026-Q2"},
        evaluation={"triggered": True},
        outcome="triggered",
        impact_band_candidate="high",
        urgency_band_candidate="near_term",
    )


def _priority(value: int = 50) -> dict[str, int]:
    return {
        "deterministic_risk": value,
        "amount_cash_impact": value,
        "legal_human_impact": value,
        "control_failure": value,
        "urgency": value,
        "data_sufficiency": value,
        "ceo_question_relevance": value,
    }


def _spec(key: str, signal_id: str, *, value: int = 50) -> dict:
    return {
        "case_key": key,
        "event_id": f"event_{key}",
        "signal_ids": [signal_id],
        "required_domain_routes": ["accounting"],
        "optional_domain_routes": [],
        "related_case_keys": [],
        "priority_dimensions": _priority(value),
    }


def _materialize(specs):
    _, materialize = _api()
    signals = [_signal("alpha1"), _signal("beta2"), _signal("gamma3")]
    return materialize(
        run_id="run_signal_queue",
        base_revision=7,
        signals=signals,
        case_specs=specs(signals),
        priority_policy_ref="priority_policy_v1",
    )


class SignalQueueTests(unittest.TestCase):
    """D09 §§8.4, 10.1, 12.6; Integration Index Task I."""

    def test_materialization_is_order_invariant_and_merges_duplicate_case_keys(self) -> None:
        _, materialize = _api()
        signals = [_signal("alpha1"), _signal("beta2"), _signal("gamma3")]
        specs = [
            _spec("revenue", signals[0]["signal_id"], value=70),
            _spec("cash", signals[2]["signal_id"], value=60),
            _spec("revenue", signals[1]["signal_id"], value=80),
        ]
        original_signals = copy.deepcopy(signals)
        original_specs = copy.deepcopy(specs)
        cases_a, priorities_a = materialize(
            run_id="run_signal_queue",
            base_revision=7,
            signals=signals,
            case_specs=specs,
            priority_policy_ref="priority_policy_v1",
        )
        cases_b, priorities_b = materialize(
            run_id="run_signal_queue",
            base_revision=7,
            signals=list(reversed(signals)),
            case_specs=list(reversed(specs)),
            priority_policy_ref="priority_policy_v1",
        )
        self.assertEqual(canonical_bytes(cases_a), canonical_bytes(cases_b))
        self.assertEqual(canonical_bytes(priorities_a), canonical_bytes(priorities_b))
        self.assertEqual(2, len(cases_a))
        revenue = next(case for case in cases_a if len(case["signal_ids"]) == 2)
        priority = next(
            item for item in priorities_a
            if item["priority_record_id"] == revenue["priority_record_ref"]
        )
        self.assertEqual(80, priority["dimensions"]["deterministic_risk"])
        self.assertEqual(original_signals, signals)
        self.assertEqual(original_specs, specs)

    def test_priority_tie_uses_case_id_and_only_one_deep_case_is_active(self) -> None:
        Queue, materialize = _api()
        signals = [_signal("alpha1"), _signal("beta2")]
        specs = [_spec("a", signals[0]["signal_id"]), _spec("b", signals[1]["signal_id"])]
        cases, priorities = materialize(
            run_id="run_signal_queue",
            base_revision=7,
            signals=signals,
            case_specs=specs,
            priority_policy_ref="priority_policy_v1",
        )
        queue = Queue(cases, priorities)
        first = queue.lease(
            "worker_a", expected_revision=7, idempotency_key="lease-a"
        )
        self.assertEqual(min(case["case_id"] for case in cases), first["case_id"])
        self.assertIsNone(
            queue.lease(
                "worker_b",
                expected_revision=queue.revision,
                idempotency_key="lease-b",
            )
        )
        active = [case for case in queue.cases() if case["status"] == "investigating"]
        self.assertEqual(1, len(active))

    def test_lease_is_idempotent_and_stale_or_reused_keys_fail_closed(self) -> None:
        Queue, materialize = _api()
        signals = [_signal("alpha1")]
        cases, priorities = materialize(
            run_id="run_signal_queue",
            base_revision=7,
            signals=signals,
            case_specs=[_spec("a", signals[0]["signal_id"])],
            priority_policy_ref="priority_policy_v1",
        )
        queue = Queue(cases, priorities)
        first = queue.lease(
            "worker_a", expected_revision=7, idempotency_key="same-key"
        )
        revision = queue.revision
        replay = queue.lease(
            "worker_a", expected_revision=7, idempotency_key="same-key"
        )
        self.assertEqual(first, replay)
        self.assertEqual(revision, queue.revision)
        with self.assertRaises(ContractError):
            queue.lease(
                "worker_b", expected_revision=7, idempotency_key="same-key"
            )
        with self.assertRaises(RevisionConflict):
            queue.cancel(
                first["case_id"],
                reason="stale cancellation",
                expected_revision=7,
                idempotency_key="cancel-stale",
            )

    def test_pause_resume_stage_progression_cancel_and_terminal_audit(self) -> None:
        Queue, materialize = _api()
        signals = [_signal("alpha1"), _signal("beta2")]
        cases, priorities = materialize(
            run_id="run_signal_queue",
            base_revision=7,
            signals=signals,
            case_specs=[
                _spec("a", signals[0]["signal_id"], value=90),
                _spec("b", signals[1]["signal_id"], value=80),
            ],
            priority_policy_ref="priority_policy_v1",
        )
        queue = Queue(cases, priorities)
        first = queue.lease("worker_a", expected_revision=7, idempotency_key="lease-a")
        advanced = queue.advance(
            first["case_id"],
            "worker_a",
            next_stage=3,
            expected_revision=queue.revision,
            idempotency_key="advance-a",
        )
        self.assertEqual(3, advanced["current_stage"])
        paused = queue.pause(
            first["case_id"],
            "worker_a",
            status="needs_input",
            reason="contract register is missing",
            expected_revision=queue.revision,
            idempotency_key="pause-a",
        )
        self.assertEqual("needs_input", paused["status"])

        second = queue.lease(
            "worker_b", expected_revision=queue.revision, idempotency_key="lease-b"
        )
        cancelled = queue.cancel(
            second["case_id"],
            reason="human stopped this case",
            expected_revision=queue.revision,
            idempotency_key="cancel-b",
        )
        self.assertEqual("cancelled", cancelled["disposition"])
        resumed = queue.resume(
            first["case_id"],
            expected_revision=queue.revision,
            idempotency_key="resume-a",
        )
        self.assertEqual("queued", resumed["status"])
        leased_again = queue.lease(
            "worker_a", expected_revision=queue.revision, idempotency_key="re-lease-a"
        )
        stage_four = queue.advance(
            leased_again["case_id"],
            "worker_a",
            next_stage=4,
            expected_revision=queue.revision,
            idempotency_key="advance-a-4",
        )
        queue.advance(
            stage_four["case_id"],
            "worker_a",
            next_stage=5,
            expected_revision=queue.revision,
            idempotency_key="advance-a-5",
        )
        terminal = queue.complete(
            leased_again["case_id"],
            "worker_a",
            disposition="inconclusive",
            finding_ref="finding_" + "f" * 24,
            reason="required contract evidence remains unavailable",
            expected_revision=queue.revision,
            idempotency_key="complete-a",
        )
        self.assertEqual("terminal", terminal["status"])
        queue.assert_all_terminal()

    def test_each_state_change_preserves_prior_case_bytes(self) -> None:
        Queue, materialize = _api()
        signals = [_signal("alpha1")]
        cases, priorities = materialize(
            run_id="run_signal_queue",
            base_revision=7,
            signals=signals,
            case_specs=[_spec("a", signals[0]["signal_id"])],
            priority_policy_ref="priority_policy_v1",
        )
        queue = Queue(cases, priorities)
        case_id = cases[0]["case_id"]
        before = canonical_bytes(queue.history(case_id)[0])
        queue.lease("worker_a", expected_revision=7, idempotency_key="lease")
        history = queue.history(case_id)
        self.assertEqual(before, canonical_bytes(history[0]))
        self.assertEqual(history[0]["content_hash"], history[1]["previous_content_hash"])

    def test_model_authored_signal_cannot_enter_the_queue(self) -> None:
        _, materialize = _api()
        signal = _signal("alpha1")
        signal["producer"] = "llm"
        with self.assertRaises(ContractError):
            materialize(
                run_id="run_signal_queue",
                base_revision=7,
                signals=[signal],
                case_specs=[_spec("a", signal["signal_id"])],
                priority_policy_ref="priority_policy_v1",
            )


if __name__ == "__main__":
    unittest.main()
