from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


def _native_integers(value: Any) -> Any:
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, dict):
        return {str(key): _native_integers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native_integers(child) for child in value]
    return value


def _object(files: Mapping[str, bytes], path: str) -> dict[str, Any]:
    payload = files.get(path)
    if payload is None:
        raise ContractError(f"result question snapshot lacks {path}")
    try:
        value = _native_integers(strict_loads(payload))
    except (UnicodeError, ValueError) as error:
        raise ContractError(f"result question snapshot has invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"result question snapshot artifact must be an object: {path}")
    return value


def _index(
    values: Any,
    identifier: str,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(values, list):
        raise ContractError(f"{label} register must be an array")
    result: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, Mapping):
            raise ContractError(f"{label} entry must be an object")
        item_id = item.get(identifier)
        if not isinstance(item_id, str) or not item_id:
            raise ContractError(f"{label} entry has an invalid {identifier}")
        if item_id in result:
            raise ContractError(f"duplicate {label}: {item_id}")
        result[item_id] = copy.deepcopy(dict(item))
    return result


def _readonly(
    values: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Mapping[str, Any]]:
    return MappingProxyType(
        {
            key: MappingProxyType(copy.deepcopy(dict(value)))
            for key, value in sorted(values.items())
        }
    )


def _display_text(fact: Mapping[str, Any]) -> str:
    value = fact.get("value")
    if not isinstance(value, Mapping):
        raise ContractError(f"Fact value is missing: {fact.get('fact_id')}")
    canonical = value.get("canonical_value")
    if isinstance(canonical, bool):
        return "true" if canonical else "false"
    if isinstance(canonical, (str, int)):
        return str(canonical)
    raise ContractError(f"Fact canonical value is invalid: {fact.get('fact_id')}")


def _accepted_claims(
    issues: Mapping[str, Mapping[str, Any]],
    files: Mapping[str, bytes],
) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for issue_id, issue in issues.items():
        for kind in ("cause_hypotheses", "counter_hypotheses"):
            values = issue.get(kind, [])
            if not isinstance(values, list):
                raise ContractError(f"issue {kind} must be an array")
            for value in values:
                if not isinstance(value, Mapping):
                    raise ContractError("claim must be an object")
                claim_code = value.get("claim_code")
                if not isinstance(claim_code, str) or not claim_code:
                    raise ContractError("claim code is invalid")
                if claim_code in claims:
                    raise ContractError(f"duplicate accepted claim: {claim_code}")
                claims[claim_code] = {
                    **copy.deepcopy(dict(value)),
                    "claim_ref": claim_code,
                    "issue_ref": issue_id,
                    "claim_kind": kind,
                }

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            claim_code = value.get("claim_code")
            if isinstance(claim_code, str) and claim_code in claims:
                existing = claims[claim_code]
                for key, child in value.items():
                    if key not in existing and not str(key).startswith("_"):
                        existing[str(key)] = copy.deepcopy(child)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for path in (
        "reasoning/integrated-assessment.json",
        "reasoning/deep-dive-result.json",
    ):
        if path in files:
            walk(_object(files, path))
    return claims


def _expert_packets(
    result: Mapping[str, Any],
    structured: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    packets = _index(
        result.get("expert_review_packets", []),
        "expert_packet_id",
        "expert packet",
    )
    structured_packets = {
        str(item["expert_packet_id"]): item
        for item in structured.get("expert_review_packets", [])
        if isinstance(item, Mapping) and isinstance(item.get("expert_packet_id"), str)
    }
    for packet_id, packet in packets.items():
        structured_packet = structured_packets.get(packet_id)
        target = (
            structured_packet.get("_target_issue_ref")
            if isinstance(structured_packet, Mapping)
            else None
        )
        packet["target_issue_ref"] = target if isinstance(target, str) else None
    return packets


def _trust_events(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for path, payload in sorted(files.items()):
        if not path.startswith("audit/events/") or not path.endswith(".json"):
            continue
        try:
            value = _native_integers(strict_loads(payload))
        except (UnicodeError, ValueError) as error:
            raise ContractError(f"invalid audit event: {path}") from error
        if not isinstance(value, Mapping):
            raise ContractError(f"audit event must be an object: {path}")
        safe = {
            key: copy.deepcopy(child)
            for key, child in value.items()
            if key
            in {
                "command",
                "gate",
                "from_revision",
                "to_revision",
                "timestamp",
                "created_at",
            }
        }
        event_id = make_id("event", {"path": path, "event": safe})
        events[event_id] = {"event_id": event_id, **safe}
    return events


def _revision_diffs(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path, payload in sorted(files.items()):
        if not path.startswith("revision/diffs/") or not path.endswith(".json"):
            continue
        value = _native_integers(strict_loads(payload))
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ContractError(f"revision diff must be an object: {path}")
            identifier = entry.get("diff_entry_id")
            if not isinstance(identifier, str) or not identifier:
                raise ContractError(f"revision diff lacks diff_entry_id: {path}")
            if identifier in result:
                raise ContractError(f"duplicate revision diff: {identifier}")
            result[identifier] = copy.deepcopy(dict(entry))
    return result


@dataclass(frozen=True)
class QuestionIndex:
    run_id: str
    revision: int
    issues: Mapping[str, Mapping[str, Any]]
    claims: Mapping[str, Mapping[str, Any]]
    facts: Mapping[str, Mapping[str, Any]]
    signals: Mapping[str, Mapping[str, Any]]
    evidence_links: Mapping[str, Mapping[str, Any]]
    sources: Mapping[str, Mapping[str, Any]]
    expert_packets: Mapping[str, Mapping[str, Any]]
    revision_diffs: Mapping[str, Mapping[str, Any]]
    trust_events: Mapping[str, Mapping[str, Any]]
    value_table: Mapping[str, Mapping[str, str]]
    data_quality: Mapping[str, Mapping[str, Any]]
    capability_map: Mapping[str, Any]

    @classmethod
    def from_snapshot(cls, files: Mapping[str, bytes]) -> "QuestionIndex":
        state = _object(files, "workflow/state.json")
        if state.get("state") != "finalized":
            raise ContractError("result questions require a finalized snapshot")
        run_id = state.get("run_id")
        revision = state.get("revision")
        if (
            not isinstance(run_id, str)
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
        ):
            raise ContractError("finalized workflow identity is invalid")

        final_result = _object(files, "final/result.json")
        structured = _object(files, "final/structured-output.json")
        core = _object(files, "evidence/core.json")
        SchemaStore().validate("final-result.schema.json", final_result)
        SchemaStore().validate("evidence-core.schema.json", core)
        summary = final_result.get("run_summary")
        if not isinstance(summary, Mapping) or (
            summary.get("run_id") != run_id or summary.get("revision") != revision
        ):
            raise ContractError("Final Result identity differs from workflow state")

        issues = _index(final_result.get("issues", []), "issue_id", "issue")
        facts = _index(core.get("fact_register", []), "fact_id", "Fact")
        signals = _index(core.get("signal_register", []), "signal_id", "Signal")
        links = _index(
            core.get("evidence_links", []),
            "evidence_link_id",
            "Evidence Link",
        )
        sources = _index(
            core.get("source_registry", []),
            "source_id",
            "Source",
        )
        quality = _index(
            core.get("data_quality_register", []),
            "quality_issue_id",
            "data quality",
        )
        values: dict[str, dict[str, str]] = {}
        for fact_id, fact in sorted(facts.items()):
            identity = {
                "fact_or_signal_id": fact_id,
                "display_field": "value.canonical_value",
            }
            value_ref = make_id("value", identity)
            values[value_ref] = {
                "value_ref": value_ref,
                **identity,
                "display_text": _display_text(fact),
            }
        capability = core.get("capability_map")
        if not isinstance(capability, Mapping):
            raise ContractError("Evidence Core capability map is invalid")
        return cls(
            run_id=run_id,
            revision=revision,
            issues=_readonly(issues),
            claims=_readonly(_accepted_claims(issues, files)),
            facts=_readonly(facts),
            signals=_readonly(signals),
            evidence_links=_readonly(links),
            sources=_readonly(sources),
            expert_packets=_readonly(_expert_packets(final_result, structured)),
            revision_diffs=_readonly(_revision_diffs(files)),
            trust_events=_readonly(_trust_events(files)),
            value_table=_readonly(values),
            data_quality=_readonly(quality),
            capability_map=MappingProxyType(copy.deepcopy(dict(capability))),
        )
