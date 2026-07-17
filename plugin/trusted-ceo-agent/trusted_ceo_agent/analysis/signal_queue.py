from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, RevisionConflict


PRIORITY_DIMENSIONS = (
    "deterministic_risk",
    "amount_cash_impact",
    "legal_human_impact",
    "control_failure",
    "urgency",
    "data_sufficiency",
    "ceo_question_relevance",
)
PRIORITY_SORT_ORDER = (
    "deterministic_risk",
    "legal_human_impact",
    "control_failure",
    "urgency",
    "amount_cash_impact",
    "ceo_question_relevance",
    "data_sufficiency",
)
CASE_SPEC_FIELDS = frozenset({
    "case_key",
    "event_id",
    "signal_ids",
    "required_domain_routes",
    "optional_domain_routes",
    "related_case_keys",
    "priority_dimensions",
})
DOMAIN_ROUTES = frozenset({"accounting", "legal", "labor", "tax"})
PAUSE_STATUSES = frozenset({
    "needs_prioritization", "needs_input", "needs_expert", "paused",
})
TERMINAL_DISPOSITIONS = frozenset({
    "substantiated",
    "not_substantiated",
    "inconclusive",
    "merged",
    "out_of_scope",
    "expert_review_required",
    "deferred",
    "failed",
    "cancelled",
})
FINDING_DISPOSITIONS = frozenset({
    "substantiated",
    "not_substantiated",
    "inconclusive",
    "expert_review_required",
})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _content_hash(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_hash", None)
    return _digest(body)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ContractError(f"{field} must be <= {maximum}")
    return value


def _string_set(
    values: Any,
    field: str,
    *,
    non_empty: bool = False,
) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{field} must be an array")
    normalized = [_text(value, field) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ContractError(f"{field} contains duplicates")
    if non_empty and not normalized:
        raise ContractError(f"{field} must not be empty")
    return sorted(normalized)


def _domain_set(values: Any, field: str) -> list[str]:
    result = _string_set(values, field)
    unknown = set(result) - DOMAIN_ROUTES
    if unknown:
        raise ContractError(f"{field} contains unsupported domains: {sorted(unknown)}")
    return result


def _priority_dimensions(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(PRIORITY_DIMENSIONS):
        raise ContractError("priority_dimensions must contain the seven declared dimensions")
    return {
        name: _integer(value[name], name, maximum=100)
        for name in PRIORITY_DIMENSIONS
    }


def _normalize_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != CASE_SPEC_FIELDS:
        missing = sorted(CASE_SPEC_FIELDS - set(raw))
        extra = sorted(set(raw) - CASE_SPEC_FIELDS)
        raise ContractError(
            f"Signal Case spec fields are invalid: missing={missing}, extra={extra}"
        )
    required = _domain_set(raw["required_domain_routes"], "required_domain_routes")
    optional = _domain_set(raw["optional_domain_routes"], "optional_domain_routes")
    overlap = set(required) & set(optional)
    if overlap:
        raise ContractError(f"required and optional routes overlap: {sorted(overlap)}")
    return {
        "case_key": _text(raw["case_key"], "case_key"),
        "event_id": _text(raw["event_id"], "event_id"),
        "signal_ids": _string_set(raw["signal_ids"], "signal_ids", non_empty=True),
        "required_domain_routes": required,
        "optional_domain_routes": optional,
        "related_case_keys": _string_set(raw["related_case_keys"], "related_case_keys"),
        "priority_dimensions": _priority_dimensions(raw["priority_dimensions"]),
    }


def _verify_priority(record: Mapping[str, Any]) -> None:
    SchemaStore().validate("priority-record.schema.json", dict(record))
    expected_id = f"priority_{record['created_from_hash'][:24]}"
    if record["priority_record_id"] != expected_id:
        raise ContractError("PriorityRecord ID does not match created_from_hash")
    expected_vector = [
        record["dimensions"][name] for name in PRIORITY_SORT_ORDER
    ]
    if record["sort_vector"] != expected_vector:
        raise ContractError("PriorityRecord sort_vector does not match dimensions")
    if not hmac.compare_digest(str(record["content_hash"]), _content_hash(record)):
        raise ContractError("PriorityRecord content hash mismatch")


def _verify_case(record: Mapping[str, Any]) -> None:
    SchemaStore().validate("signal-case.schema.json", dict(record))
    expected_id = f"case_{record['created_from_hash'][:24]}"
    if record["case_id"] != expected_id:
        raise ContractError("SignalCase ID does not match created_from_hash")
    if set(record["required_domain_routes"]) & set(record["optional_domain_routes"]):
        raise ContractError("SignalCase required and optional routes overlap")
    if record["case_id"] in set(record["related_case_ids"]):
        raise ContractError("SignalCase cannot relate to itself")
    if not hmac.compare_digest(str(record["content_hash"]), _content_hash(record)):
        raise ContractError("SignalCase content hash mismatch")


def materialize_signal_cases(
    *,
    run_id: str,
    base_revision: int,
    signals: Sequence[Mapping[str, Any]],
    case_specs: Sequence[Mapping[str, Any]],
    priority_policy_ref: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Materialize D09 §10.1 cases without allowing a model to mint Signals."""

    run_id = _text(run_id, "run_id")
    if not run_id.startswith("run_"):
        raise ContractError("run_id must begin with run_")
    base_revision = _integer(base_revision, "base_revision")
    priority_policy_ref = _text(priority_policy_ref, "priority_policy_ref")
    if not isinstance(signals, (list, tuple)) or not signals:
        raise ContractError("at least one deterministic Signal is required")
    if not isinstance(case_specs, (list, tuple)) or not case_specs:
        raise ContractError("at least one Signal Case spec is required")

    schemas = SchemaStore()
    signal_by_id: dict[str, dict[str, Any]] = {}
    for raw_signal in signals:
        if not isinstance(raw_signal, Mapping):
            raise ContractError("Signal must be an object")
        signal = copy.deepcopy(dict(raw_signal))
        if signal.get("producer") != "deterministic_component":
            raise ContractError("only deterministic_component may mint a Signal")
        schemas.validate("signal.schema.json", signal)
        if signal.get("outcome") == "not_triggered":
            raise ContractError("not_triggered Signal cannot enter the deep-case queue")
        signal_id = str(signal["signal_id"])
        existing = signal_by_id.get(signal_id)
        if existing is not None and canonical_bytes(existing) != canonical_bytes(signal):
            raise ContractError(f"conflicting duplicate Signal: {signal_id}")
        signal_by_id[signal_id] = signal

    merged: dict[str, dict[str, Any]] = {}
    owner_by_signal: dict[str, str] = {}
    for raw_spec in case_specs:
        if not isinstance(raw_spec, Mapping):
            raise ContractError("Signal Case spec must be an object")
        spec = _normalize_spec(raw_spec)
        unknown_signals = set(spec["signal_ids"]) - set(signal_by_id)
        if unknown_signals:
            raise ContractError(f"Signal Case has dangling signals: {sorted(unknown_signals)}")
        for signal_id in spec["signal_ids"]:
            owner = owner_by_signal.setdefault(signal_id, spec["case_key"])
            if owner != spec["case_key"]:
                raise ContractError(
                    f"Signal cannot belong to multiple core cases: {signal_id}"
                )

        current = merged.get(spec["case_key"])
        if current is None:
            merged[spec["case_key"]] = copy.deepcopy(spec)
            continue
        if current["event_id"] != spec["event_id"]:
            raise ContractError(
                f"duplicate case key has conflicting event: {spec['case_key']}"
            )
        current["signal_ids"] = sorted(set(current["signal_ids"]) | set(spec["signal_ids"]))
        current["required_domain_routes"] = sorted(
            set(current["required_domain_routes"]) | set(spec["required_domain_routes"])
        )
        current["optional_domain_routes"] = sorted(
            set(current["optional_domain_routes"]) | set(spec["optional_domain_routes"])
        )
        overlap = set(current["required_domain_routes"]) & set(current["optional_domain_routes"])
        if overlap:
            raise ContractError(
                f"merged case has conflicting route authority: {sorted(overlap)}"
            )
        current["related_case_keys"] = sorted(
            set(current["related_case_keys"]) | set(spec["related_case_keys"])
        )
        current["priority_dimensions"] = {
            name: max(
                current["priority_dimensions"][name],
                spec["priority_dimensions"][name],
            )
            for name in PRIORITY_DIMENSIONS
        }

    case_keys = set(merged)
    for key, spec in merged.items():
        dangling = set(spec["related_case_keys"]) - case_keys
        if dangling:
            raise ContractError(f"Signal Case has dangling related cases: {sorted(dangling)}")
        if key in set(spec["related_case_keys"]):
            raise ContractError("Signal Case cannot relate to itself")
    for key, spec in list(merged.items()):
        for related_key in spec["related_case_keys"]:
            merged[related_key]["related_case_keys"] = sorted(
                set(merged[related_key]["related_case_keys"]) | {key}
            )

    case_source_by_key: dict[str, dict[str, Any]] = {}
    case_id_by_key: dict[str, str] = {}
    for key in sorted(merged):
        spec = merged[key]
        source = {
            "run_id": run_id,
            "base_revision": base_revision,
            "case_key": key,
            "event_id": spec["event_id"],
            "signal_ids": list(spec["signal_ids"]),
            "required_domain_routes": list(spec["required_domain_routes"]),
            "optional_domain_routes": list(spec["optional_domain_routes"]),
            "related_case_keys": list(spec["related_case_keys"]),
        }
        case_source_by_key[key] = source
        case_id_by_key[key] = f"case_{_digest(source)[:24]}"

    cases: list[dict[str, Any]] = []
    priorities: list[dict[str, Any]] = []
    for key in sorted(merged):
        spec = merged[key]
        case_id = case_id_by_key[key]
        dimensions = {
            name: spec["priority_dimensions"][name] for name in PRIORITY_DIMENSIONS
        }
        priority_source = {
            "case_id": case_id,
            "policy_ref": priority_policy_ref,
            "dimensions": dimensions,
        }
        priority_created_from_hash = _digest(priority_source)
        priority = {
            "priority_record_id": f"priority_{priority_created_from_hash[:24]}",
            "schema_version": "1.0.0",
            "case_id": case_id,
            "policy_ref": priority_policy_ref,
            "dimensions": dimensions,
            "sort_vector": [dimensions[name] for name in PRIORITY_SORT_ORDER],
            "created_from_hash": priority_created_from_hash,
            "content_hash": "",
        }
        priority["content_hash"] = _content_hash(priority)
        _verify_priority(priority)

        case_created_from_hash = _digest(case_source_by_key[key])
        case = {
            "case_id": case_id,
            "schema_version": "1.0.0",
            "run_id": run_id,
            "base_revision": base_revision,
            "case_revision": 0,
            "signal_ids": list(spec["signal_ids"]),
            "event_id": spec["event_id"],
            "priority_record_ref": priority["priority_record_id"],
            "required_domain_routes": list(spec["required_domain_routes"]),
            "optional_domain_routes": list(spec["optional_domain_routes"]),
            "current_stage": 1,
            "status": "queued",
            "disposition": None,
            "finding_ref": None,
            "related_case_ids": sorted(
                case_id_by_key[item] for item in spec["related_case_keys"]
            ),
            "checkpoint_ref": None,
            "lease_owner": None,
            "pause_reason": None,
            "terminal_reason": None,
            "created_from_hash": case_created_from_hash,
            "previous_content_hash": None,
            "content_hash": "",
        }
        case["content_hash"] = _content_hash(case)
        _verify_case(case)
        cases.append(case)
        priorities.append(priority)

    cases.sort(key=lambda item: item["case_id"])
    priorities.sort(key=lambda item: item["priority_record_id"])
    return cases, priorities


class SignalCaseQueue:
    """Copy-on-write, one-deep-case controller for D09 §§10.1 and 12.6."""

    def __init__(
        self,
        cases: Sequence[Mapping[str, Any]],
        priority_records: Sequence[Mapping[str, Any]],
    ) -> None:
        if not cases:
            raise ContractError("Signal Case Queue cannot be empty")
        self._cases: dict[str, dict[str, Any]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        for raw in cases:
            record = copy.deepcopy(dict(raw))
            _verify_case(record)
            case_id = record["case_id"]
            if case_id in self._cases:
                raise ContractError(f"duplicate SignalCase: {case_id}")
            self._cases[case_id] = record
            self._history[case_id] = [copy.deepcopy(record)]

        self._priorities: dict[str, dict[str, Any]] = {}
        case_ids_by_priority: set[str] = set()
        for raw in priority_records:
            record = copy.deepcopy(dict(raw))
            _verify_priority(record)
            priority_id = record["priority_record_id"]
            if priority_id in self._priorities:
                raise ContractError(f"duplicate PriorityRecord: {priority_id}")
            if record["case_id"] not in self._cases:
                raise ContractError(f"PriorityRecord has dangling case: {priority_id}")
            self._priorities[priority_id] = record
            case_ids_by_priority.add(record["case_id"])
        if case_ids_by_priority != set(self._cases):
            raise ContractError("each SignalCase must have exactly one PriorityRecord")
        for case in self._cases.values():
            priority = self._priorities.get(case["priority_record_ref"])
            if priority is None or priority["case_id"] != case["case_id"]:
                raise ContractError("SignalCase priority reference is invalid")

        revisions = {case["base_revision"] for case in self._cases.values()}
        if len(revisions) != 1:
            raise ContractError("all queued Signal Cases must share a base revision")
        self._revision = next(iter(revisions))
        self._idempotency: dict[str, tuple[str, dict[str, Any] | None]] = {}

    @property
    def revision(self) -> int:
        return self._revision

    def cases(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._cases[key]) for key in sorted(self._cases))

    def history(self, case_id: str) -> tuple[dict[str, Any], ...]:
        if case_id not in self._history:
            raise ContractError(f"unknown SignalCase: {case_id}")
        return tuple(copy.deepcopy(item) for item in self._history[case_id])

    def _idempotent_replay(
        self,
        idempotency_key: str,
        request: Mapping[str, Any],
    ) -> tuple[bool, dict[str, Any] | None]:
        key = _text(idempotency_key, "idempotency_key")
        request_hash = _digest(request)
        stored = self._idempotency.get(key)
        if stored is None:
            return False, None
        stored_hash, result = stored
        if not hmac.compare_digest(stored_hash, request_hash):
            raise ContractError("idempotency key was reused for a different request")
        return True, copy.deepcopy(result)

    def _remember(
        self,
        idempotency_key: str,
        request: Mapping[str, Any],
        result: Mapping[str, Any] | None,
    ) -> None:
        self._idempotency[idempotency_key] = (
            _digest(request),
            copy.deepcopy(dict(result)) if result is not None else None,
        )

    def _check_revision(self, expected_revision: int) -> None:
        expected = _integer(expected_revision, "expected_revision")
        if expected != self._revision:
            raise RevisionConflict(
                f"Signal Case Queue revision is stale: expected {expected}, current {self._revision}"
            )

    def _replace(self, case_id: str, changes: Mapping[str, Any]) -> dict[str, Any]:
        current = self._cases.get(case_id)
        if current is None:
            raise ContractError(f"unknown SignalCase: {case_id}")
        updated = copy.deepcopy(current)
        updated.update(copy.deepcopy(dict(changes)))
        updated["case_revision"] = current["case_revision"] + 1
        updated["previous_content_hash"] = current["content_hash"]
        updated["content_hash"] = ""
        updated["content_hash"] = _content_hash(updated)
        _verify_case(updated)
        self._history[case_id].append(copy.deepcopy(updated))
        self._cases[case_id] = updated
        self._revision += 1
        return copy.deepcopy(updated)

    def lease(
        self,
        worker_id: str,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        request = {
            "operation": "lease",
            "worker_id": _text(worker_id, "worker_id"),
            "expected_revision": expected_revision,
        }
        replay, result = self._idempotent_replay(idempotency_key, request)
        if replay:
            return result
        self._check_revision(expected_revision)
        if any(case["status"] == "investigating" for case in self._cases.values()):
            self._remember(idempotency_key, request, None)
            return None

        candidates = [
            case for case in self._cases.values() if case["status"] == "queued"
        ]
        if not candidates:
            self._remember(idempotency_key, request, None)
            return None

        def order(case: Mapping[str, Any]) -> tuple[Any, ...]:
            priority = self._priorities[case["priority_record_ref"]]
            return tuple(-value for value in priority["sort_vector"]) + (case["case_id"],)

        chosen = min(candidates, key=order)
        result = self._replace(
            chosen["case_id"],
            {
                "status": "investigating",
                "current_stage": max(2, chosen["current_stage"]),
                "lease_owner": worker_id,
                "pause_reason": None,
            },
        )
        self._remember(idempotency_key, request, result)
        return result

    def advance(
        self,
        case_id: str,
        worker_id: str,
        *,
        next_stage: int,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = {
            "operation": "advance",
            "case_id": case_id,
            "worker_id": worker_id,
            "next_stage": next_stage,
            "expected_revision": expected_revision,
        }
        replay, result = self._idempotent_replay(idempotency_key, request)
        if replay:
            if result is None:
                raise ContractError("invalid empty idempotent advance result")
            return result
        self._check_revision(expected_revision)
        case = self._owned_investigating(case_id, worker_id)
        next_stage = _integer(next_stage, "next_stage", minimum=2, maximum=5)
        if next_stage != case["current_stage"] + 1:
            raise ContractError("Signal Case stages must advance exactly one step")
        result = self._replace(case_id, {"current_stage": next_stage})
        self._remember(idempotency_key, request, result)
        return result

    def _owned_investigating(self, case_id: str, worker_id: str) -> dict[str, Any]:
        case = self._cases.get(case_id)
        if case is None:
            raise ContractError(f"unknown SignalCase: {case_id}")
        if case["status"] != "investigating":
            raise ContractError("SignalCase is not investigating")
        if case["lease_owner"] != _text(worker_id, "worker_id"):
            raise ContractError("SignalCase lease owner mismatch")
        return case

    def pause(
        self,
        case_id: str,
        worker_id: str,
        *,
        status: str,
        reason: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = {
            "operation": "pause",
            "case_id": case_id,
            "worker_id": worker_id,
            "status": status,
            "reason": reason,
            "expected_revision": expected_revision,
        }
        replay, result = self._idempotent_replay(idempotency_key, request)
        if replay:
            if result is None:
                raise ContractError("invalid empty idempotent pause result")
            return result
        self._check_revision(expected_revision)
        self._owned_investigating(case_id, worker_id)
        if status not in PAUSE_STATUSES:
            raise ContractError(f"invalid SignalCase pause status: {status}")
        result = self._replace(
            case_id,
            {
                "status": status,
                "lease_owner": None,
                "pause_reason": _text(reason, "reason"),
            },
        )
        self._remember(idempotency_key, request, result)
        return result

    def resume(
        self,
        case_id: str,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = {
            "operation": "resume",
            "case_id": case_id,
            "expected_revision": expected_revision,
        }
        replay, result = self._idempotent_replay(idempotency_key, request)
        if replay:
            if result is None:
                raise ContractError("invalid empty idempotent resume result")
            return result
        self._check_revision(expected_revision)
        case = self._cases.get(case_id)
        if case is None or case["status"] not in PAUSE_STATUSES:
            raise ContractError("only a paused SignalCase can resume")
        result = self._replace(
            case_id,
            {"status": "queued", "pause_reason": None, "lease_owner": None},
        )
        self._remember(idempotency_key, request, result)
        return result

    def cancel(
        self,
        case_id: str,
        *,
        reason: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = {
            "operation": "cancel",
            "case_id": case_id,
            "reason": reason,
            "expected_revision": expected_revision,
        }
        replay, result = self._idempotent_replay(idempotency_key, request)
        if replay:
            if result is None:
                raise ContractError("invalid empty idempotent cancellation result")
            return result
        self._check_revision(expected_revision)
        case = self._cases.get(case_id)
        if case is None:
            raise ContractError(f"unknown SignalCase: {case_id}")
        if case["status"] == "terminal":
            raise ContractError("terminal SignalCase cannot be cancelled again")
        result = self._replace(
            case_id,
            {
                "status": "terminal",
                "disposition": "cancelled",
                "finding_ref": None,
                "lease_owner": None,
                "pause_reason": None,
                "terminal_reason": _text(reason, "reason"),
            },
        )
        self._remember(idempotency_key, request, result)
        return result

    def complete(
        self,
        case_id: str,
        worker_id: str,
        *,
        disposition: str,
        finding_ref: str | None,
        reason: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = {
            "operation": "complete",
            "case_id": case_id,
            "worker_id": worker_id,
            "disposition": disposition,
            "finding_ref": finding_ref,
            "reason": reason,
            "expected_revision": expected_revision,
        }
        replay, result = self._idempotent_replay(idempotency_key, request)
        if replay:
            if result is None:
                raise ContractError("invalid empty idempotent completion result")
            return result
        self._check_revision(expected_revision)
        case = self._owned_investigating(case_id, worker_id)
        if case["current_stage"] != 5:
            raise ContractError("SignalCase cannot complete before Stage 5")
        if disposition not in TERMINAL_DISPOSITIONS - {"cancelled"}:
            raise ContractError(f"invalid SignalCase completion disposition: {disposition}")
        if disposition in FINDING_DISPOSITIONS:
            _text(finding_ref, "finding_ref")
        elif finding_ref is not None:
            raise ContractError("non-conclusion disposition cannot attach a Finding")
        result = self._replace(
            case_id,
            {
                "status": "terminal",
                "disposition": disposition,
                "finding_ref": finding_ref,
                "lease_owner": None,
                "pause_reason": None,
                "terminal_reason": _text(reason, "reason"),
            },
        )
        self._remember(idempotency_key, request, result)
        return result

    def assert_all_terminal(self) -> None:
        pending = sorted(
            case_id
            for case_id, case in self._cases.items()
            if case["status"] != "terminal" or case["disposition"] is None
        )
        if pending:
            raise ContractError(f"Signal Cases are not terminal: {pending}")
