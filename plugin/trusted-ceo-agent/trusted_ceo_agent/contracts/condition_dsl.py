from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.errors import ContractError


MAX_DEPTH = 8
MAX_NODES = 64
MAX_ARGS = 16

_COMPARISON_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "outcome_is"})
_MEMBERSHIP_OPERATORS = frozenset({"in", "not_in"})
_PRESENCE_OPERATORS = frozenset({"exists", "missing"})
_REDUCERS = frozenset({"only", "latest", "min", "max", "sum", "count"})
_MISSION_ROOTS = frozenset(
    {
        "business_question",
        "business_model",
        "current_symptoms",
        "customer_hypotheses",
        "decision_context",
        "decision_units",
        "decision_deadline",
        "analysis_horizon",
        "organization_scope",
        "priority_dimensions",
        "constraints",
        "recent_business_changes",
        "recent_organization_changes",
        "recent_policy_changes",
        "included_scopes",
        "excluded_scopes",
        "comparison_preferences",
        "materiality_context",
        "data_definitions",
        "confidentiality",
        "required_human_roles",
        "confirmation",
    }
)
_HITL_ROOTS = frozenset(
    {
        "mission_contract",
        "mapping",
        "scope_narrowing",
        "issue_dispositions",
        "decision_dispositions",
        "verification_authorizations",
        "issue_groups",
        "materiality_context",
        "requested_counter_checks",
        "deep_dive_scope",
        "response_dispositions",
        "expert_routing",
        "ceo_wording",
        "delivery_scope",
    }
)


@dataclass(frozen=True)
class ConditionContext:
    facts: Sequence[Mapping[str, Any]]
    signals: Sequence[Mapping[str, Any]]
    mission: Mapping[str, Any]
    hitl: Mapping[str, Any]


@dataclass(frozen=True)
class ConditionResult:
    outcome: str
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Resolved:
    value: Any = None
    value_type: str | None = None
    unit_code: str | None = None
    missing_reason: str | None = None

    @property
    def missing(self) -> bool:
        return self.missing_reason is not None


def _require_exact_keys(value: Mapping[str, Any], required: set[str], optional: set[str] | None = None) -> None:
    optional = optional or set()
    keys = set(value)
    if not required.issubset(keys) or keys - required - optional:
        raise ContractError(
            f"invalid condition keys: required={sorted(required)}, actual={sorted(keys)}"
        )


def _pointer_tokens(pointer: str, allowed_roots: frozenset[str]) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise ContractError("condition reference must be a non-root JSON Pointer")
    raw_tokens = pointer[1:].split("/")
    tokens = [token.replace("~1", "/").replace("~0", "~") for token in raw_tokens]
    if any("~" in raw.replace("~0", "").replace("~1", "") for raw in raw_tokens):
        raise ContractError("invalid JSON Pointer escape")
    if tokens[0] not in allowed_roots:
        raise ContractError(f"condition reference is not allowlisted: /{tokens[0]}")
    return tokens


def _validate_literal(body: Any) -> None:
    if not isinstance(body, Mapping):
        raise ContractError("literal must be an object")
    _require_exact_keys(body, {"type", "value"})
    literal_type = body["type"]
    value = body["value"]
    if literal_type == "decimal":
        if not isinstance(value, str):
            raise ContractError("decimal literal must be a canonical string")
        try:
            decimal = Decimal(value)
        except InvalidOperation as error:
            raise ContractError("invalid decimal literal") from error
        if not decimal.is_finite():
            raise ContractError("decimal literal must be finite")
    elif literal_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ContractError("integer literal must be an integer")
    elif literal_type == "string":
        if not isinstance(value, str):
            raise ContractError("string literal must be a string")
    elif literal_type == "boolean":
        if not isinstance(value, bool):
            raise ContractError("boolean literal must be a boolean")
    elif literal_type == "date":
        if not isinstance(value, str):
            raise ContractError("date literal must be an ISO date string")
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ContractError("invalid date literal") from error
    else:
        raise ContractError(f"unsupported literal type: {literal_type}")


def _validate_operand(operand: Any) -> None:
    if not isinstance(operand, Mapping) or len(operand) != 1:
        raise ContractError("condition operand must contain exactly one reference")
    kind, body = next(iter(operand.items()))
    if kind == "literal":
        _validate_literal(body)
        return
    if kind == "fact_ref":
        if not isinstance(body, Mapping):
            raise ContractError("fact_ref must be an object")
        _require_exact_keys(body, {"fact_code", "reducer"}, {"unit_code", "scope_key"})
        if not isinstance(body["fact_code"], str) or not body["fact_code"]:
            raise ContractError("fact_ref.fact_code is required")
        if body["reducer"] not in _REDUCERS:
            raise ContractError(f"unsupported fact reducer: {body['reducer']}")
        return
    if kind == "signal_ref":
        if not isinstance(body, Mapping):
            raise ContractError("signal_ref must be an object")
        _require_exact_keys(body, {"signal_code"}, {"outcome", "scope_key"})
        if not isinstance(body["signal_code"], str) or not body["signal_code"]:
            raise ContractError("signal_ref.signal_code is required")
        return
    if kind == "mission_ref":
        _pointer_tokens(body, _MISSION_ROOTS)
        return
    if kind == "hitl_ref":
        _pointer_tokens(body, _HITL_ROOTS)
        return
    raise ContractError(f"unsupported condition operand: {kind}")


def validate_condition(expression: Any) -> None:
    node_count = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_NODES:
            raise ContractError("condition expression node limit exceeded")
        if depth > MAX_DEPTH:
            raise ContractError("condition expression depth limit exceeded")
        if not isinstance(node, Mapping):
            raise ContractError("condition expression node must be an object")

        if set(node) == {"all"} or set(node) == {"any"}:
            args = node[next(iter(node))]
            if not isinstance(args, list) or not 1 <= len(args) <= MAX_ARGS:
                raise ContractError("logical condition requires 1 to 16 args")
            for child in args:
                visit(child, depth + 1)
            return
        if set(node) == {"not"}:
            visit(node["not"], depth + 1)
            return

        operation = node.get("op")
        if operation in _COMPARISON_OPERATORS:
            _require_exact_keys(node, {"op", "left", "right"})
            _validate_operand(node["left"])
            _validate_operand(node["right"])
            return
        if operation in _MEMBERSHIP_OPERATORS:
            _require_exact_keys(node, {"op", "left", "values"})
            _validate_operand(node["left"])
            values = node["values"]
            if not isinstance(values, list) or not 1 <= len(values) <= MAX_ARGS:
                raise ContractError("membership condition requires 1 to 16 values")
            for value in values:
                _validate_operand(value)
            return
        if operation in _PRESENCE_OPERATORS:
            _require_exact_keys(node, {"op", "operand"})
            _validate_operand(node["operand"])
            return
        raise ContractError(f"unsupported condition operator: {operation}")

    visit(expression, 1)


def _scope_matches(fact: Mapping[str, Any], scope_key: str | None) -> bool:
    if scope_key is None:
        return True
    if fact.get("scope_key") == scope_key:
        return True
    return any(
        item.get("member_code") == scope_key
        for item in fact.get("scope", ())
        if isinstance(item, Mapping)
    )


def _fact_value(fact: Mapping[str, Any]) -> _Resolved:
    body = fact.get("value")
    if not isinstance(body, Mapping):
        return _Resolved(missing_reason="invalid_fact_value")
    value_type = body.get("value_type")
    raw = body.get("canonical_value")
    try:
        if value_type == "decimal":
            value = Decimal(str(raw))
            if not value.is_finite():
                raise InvalidOperation
        elif value_type == "integer":
            value = int(raw)
        elif value_type == "boolean":
            value = bool(raw)
        elif value_type in {"string", "date"}:
            value = str(raw)
        else:
            return _Resolved(missing_reason="unsupported_fact_value_type")
    except (InvalidOperation, TypeError, ValueError):
        return _Resolved(missing_reason="invalid_fact_value")
    return _Resolved(value=value, value_type=str(value_type), unit_code=body.get("unit_code"))


def _reduce_facts(reference: Mapping[str, Any], facts: Sequence[Mapping[str, Any]]) -> _Resolved:
    selected = [
        fact
        for fact in facts
        if fact.get("fact_code") == reference["fact_code"]
        and _scope_matches(fact, reference.get("scope_key"))
    ]
    if not selected:
        return _Resolved(missing_reason="missing_fact")
    required_unit = reference.get("unit_code")
    resolved = [_fact_value(fact) for fact in selected]
    if any(item.missing for item in resolved):
        reasons = sorted(item.missing_reason for item in resolved if item.missing_reason)
        return _Resolved(missing_reason=reasons[0])
    units = {item.unit_code for item in resolved}
    if required_unit is not None and units != {required_unit}:
        return _Resolved(missing_reason="unit_mismatch")
    if len(units) > 1:
        return _Resolved(missing_reason="unit_mismatch")
    types = {item.value_type for item in resolved}
    if len(types) > 1:
        return _Resolved(missing_reason="type_mismatch")

    reducer = reference["reducer"]
    if reducer == "only":
        if len(resolved) != 1:
            return _Resolved(missing_reason="ambiguous_fact")
        return resolved[0]
    if reducer == "latest":
        pair = max(
            zip(selected, resolved),
            key=lambda item: repr(sorted(item[0].get("time_context", {}).items())),
        )
        return pair[1]
    if reducer == "count":
        return _Resolved(value=len(resolved), value_type="integer", unit_code=None)
    if not types.issubset({"decimal", "integer"}):
        return _Resolved(missing_reason="reducer_type_mismatch")
    values = [item.value for item in resolved]
    if reducer == "sum":
        return _Resolved(value=sum(values, Decimal("0")), value_type="decimal", unit_code=next(iter(units)))
    if reducer == "min":
        return _Resolved(value=min(values), value_type=resolved[0].value_type, unit_code=next(iter(units)))
    if reducer == "max":
        return _Resolved(value=max(values), value_type=resolved[0].value_type, unit_code=next(iter(units)))
    return _Resolved(missing_reason="unsupported_reducer")


def _resolve_pointer(document: Mapping[str, Any], pointer: str, roots: frozenset[str]) -> _Resolved:
    tokens = _pointer_tokens(pointer, roots)
    current: Any = document
    for token in tokens:
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return _Resolved(missing_reason="missing_reference")
    if isinstance(current, bool):
        return _Resolved(value=current, value_type="boolean")
    if isinstance(current, int):
        return _Resolved(value=current, value_type="integer")
    if isinstance(current, str):
        return _Resolved(value=current, value_type="string")
    return _Resolved(value=current, value_type="json")


def _resolve_operand(operand: Mapping[str, Any], context: ConditionContext) -> _Resolved:
    kind, body = next(iter(operand.items()))
    if kind == "fact_ref":
        return _reduce_facts(body, context.facts)
    if kind == "signal_ref":
        selected = [
            signal
            for signal in context.signals
            if signal.get("signal_code") == body["signal_code"]
            and _scope_matches(signal, body.get("scope_key"))
        ]
        if body.get("outcome") is not None:
            selected = [signal for signal in selected if signal.get("outcome") == body["outcome"]]
        if not selected:
            return _Resolved(missing_reason="missing_signal")
        outcomes = {signal.get("outcome") for signal in selected}
        if len(outcomes) != 1:
            return _Resolved(missing_reason="ambiguous_signal")
        return _Resolved(value=next(iter(outcomes)), value_type="string")
    if kind == "mission_ref":
        return _resolve_pointer(context.mission, body, _MISSION_ROOTS)
    if kind == "hitl_ref":
        return _resolve_pointer(context.hitl, body, _HITL_ROOTS)
    literal_type = body["type"]
    raw = body["value"]
    if literal_type == "decimal":
        raw = Decimal(raw)
    elif literal_type == "date":
        raw = date.fromisoformat(raw).isoformat()
    return _Resolved(value=raw, value_type=literal_type)


def _result(outcome: str, *reasons: str) -> ConditionResult:
    return ConditionResult(outcome, tuple(sorted(set(reason for reason in reasons if reason))))


def _compatible(left: _Resolved, right: _Resolved) -> str | None:
    numeric = {"decimal", "integer"}
    if left.value_type in numeric and right.value_type in numeric:
        if left.unit_code is not None and right.unit_code is not None and left.unit_code != right.unit_code:
            return "unit_mismatch"
        return None
    if left.value_type != right.value_type:
        return "type_mismatch"
    return None


def evaluate_condition(expression: Mapping[str, Any], context: ConditionContext) -> ConditionResult:
    validate_condition(expression)

    def evaluate(node: Mapping[str, Any]) -> ConditionResult:
        if "all" in node:
            results = [evaluate(child) for child in node["all"]]
            if any(result.outcome == "false" for result in results):
                return _result("false")
            if any(result.outcome == "not_assessable" for result in results):
                return _result(
                    "not_assessable",
                    *(reason for result in results for reason in result.reason_codes),
                )
            return _result("true")
        if "any" in node:
            results = [evaluate(child) for child in node["any"]]
            if any(result.outcome == "true" for result in results):
                return _result("true")
            if any(result.outcome == "not_assessable" for result in results):
                return _result(
                    "not_assessable",
                    *(reason for result in results for reason in result.reason_codes),
                )
            return _result("false")
        if "not" in node:
            child = evaluate(node["not"])
            if child.outcome == "not_assessable":
                return child
            return _result("false" if child.outcome == "true" else "true")

        operation = node["op"]
        if operation in _PRESENCE_OPERATORS:
            value = _resolve_operand(node["operand"], context)
            exists = not value.missing
            return _result("true" if exists == (operation == "exists") else "false")

        left = _resolve_operand(node["left"], context)
        if left.missing:
            return _result("not_assessable", left.missing_reason or "missing_operand")
        if operation in _MEMBERSHIP_OPERATORS:
            values = [_resolve_operand(value, context) for value in node["values"]]
            if any(value.missing for value in values):
                return _result(
                    "not_assessable",
                    *(value.missing_reason or "missing_operand" for value in values if value.missing),
                )
            compatible_values = [value for value in values if _compatible(left, value) is None]
            if not compatible_values:
                return _result("not_assessable", "type_mismatch")
            contains = any(left.value == value.value for value in compatible_values)
            if operation == "not_in":
                contains = not contains
            return _result("true" if contains else "false")

        right = _resolve_operand(node["right"], context)
        if right.missing:
            return _result("not_assessable", right.missing_reason or "missing_operand")
        mismatch = _compatible(left, right)
        if mismatch:
            return _result("not_assessable", mismatch)
        comparisons = {
            "eq": left.value == right.value,
            "ne": left.value != right.value,
            "gt": left.value > right.value,
            "gte": left.value >= right.value,
            "lt": left.value < right.value,
            "lte": left.value <= right.value,
            "outcome_is": left.value == right.value,
        }
        return _result("true" if comparisons[operation] else "false")

    return evaluate(expression)
