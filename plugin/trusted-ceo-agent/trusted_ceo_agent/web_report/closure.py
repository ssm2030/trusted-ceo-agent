from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.errors import IntegrityError


@dataclass(frozen=True)
class EvidenceClosure:
    facts: tuple[dict[str, Any], ...]
    signals: tuple[dict[str, Any], ...]
    evidence_links: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    data_quality: tuple[dict[str, Any], ...]
    capability_map: dict[str, Any]


def _index(
    values: Any,
    identifier_field: str,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(
        values, (str, bytes, bytearray)
    ):
        raise IntegrityError(f"{label} register must be an array")
    indexed: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, Mapping):
            raise IntegrityError(f"{label} entry must be an object")
        identifier = item.get(identifier_field)
        if not isinstance(identifier, str) or not identifier:
            raise IntegrityError(f"{label} entry has an invalid {identifier_field}")
        if identifier in indexed:
            raise IntegrityError(f"duplicate {label}: {identifier}")
        indexed[identifier] = deepcopy(dict(item))
    return indexed


def _string_refs(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise IntegrityError(f"{label} must be an array")
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise IntegrityError(f"{label} contains an invalid reference")
        refs.append(item)
    return tuple(refs)


def _normalized_capability_map(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IntegrityError("capability map must be an object")
    result = deepcopy(dict(value))
    capabilities = result.get("capabilities")
    indexed = _index(capabilities, "capability_id", "capability")
    for capability in indexed.values():
        for key in (
            "available_source_roles",
            "missing_source_roles",
            "quality_issue_ids",
            "reason_codes",
        ):
            if key in capability:
                capability[key] = sorted(_string_refs(capability[key], key))
    result["capabilities"] = [
        indexed[identifier] for identifier in sorted(indexed)
    ]
    return result


def _wire_signal(signal: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(signal)
    evaluation = result.get("evaluation")
    if isinstance(evaluation, Mapping):
        result["evaluation"] = [
            {"key": str(key), "value": str(value)}
            for key, value in sorted(evaluation.items(), key=lambda item: str(item[0]))
        ]
    return result


def build_evidence_closure(
    final_result: Mapping[str, Any],
    core: Mapping[str, Any],
) -> EvidenceClosure:
    """Close delivered issue evidence transitively without synthesizing content."""

    issues = _index(final_result.get("issues", []), "issue_id", "issue")
    links = _index(core.get("evidence_links", []), "evidence_link_id", "Evidence Link")
    facts = _index(core.get("fact_register", []), "fact_id", "Fact")
    signals = _index(core.get("signal_register", []), "signal_id", "Signal")
    sources = _index(core.get("source_registry", []), "source_id", "Source")
    quality = _index(
        core.get("data_quality_register", []),
        "quality_issue_id",
        "data quality issue",
    )
    capability_map = _normalized_capability_map(core.get("capability_map"))

    included_link_ids: set[str] = set()
    included_signal_ids: set[str] = set()
    included_fact_ids: set[str] = set()
    included_source_ids: set[str] = set()
    included_quality_ids: set[str] = set()
    visiting_facts: set[str] = set()
    visited_facts: set[str] = set()

    def include_quality(quality_id: str) -> None:
        item = quality.get(quality_id)
        if item is None:
            raise IntegrityError(f"unknown data quality issue: {quality_id}")
        included_quality_ids.add(quality_id)
        source_ref = item.get("source_ref")
        if source_ref is not None:
            if not isinstance(source_ref, str) or source_ref not in sources:
                raise IntegrityError(
                    f"data quality issue references unknown Source: {source_ref}"
                )
            included_source_ids.add(source_ref)

    def include_fact(fact_id: str) -> None:
        if fact_id in visited_facts:
            return
        if fact_id in visiting_facts:
            raise IntegrityError(f"Fact derivation cycle detected: {fact_id}")
        fact = facts.get(fact_id)
        if fact is None:
            raise IntegrityError(f"unknown Fact: {fact_id}")
        visiting_facts.add(fact_id)
        derivation = fact.get("derivation")
        if derivation is not None:
            if not isinstance(derivation, Mapping):
                raise IntegrityError(f"Fact derivation is invalid: {fact_id}")
            for input_id in _string_refs(
                derivation.get("input_fact_ids", []),
                f"Fact {fact_id} input_fact_ids",
            ):
                include_fact(input_id)
        source_refs = fact.get("source_refs", [])
        if not isinstance(source_refs, Sequence) or isinstance(
            source_refs, (str, bytes, bytearray)
        ):
            raise IntegrityError(f"Fact source_refs must be an array: {fact_id}")
        for source_ref in source_refs:
            if not isinstance(source_ref, Mapping):
                raise IntegrityError(f"Fact Source reference is invalid: {fact_id}")
            source_id = source_ref.get("source_id")
            if not isinstance(source_id, str) or source_id not in sources:
                raise IntegrityError(f"unknown Source: {source_id}")
            included_source_ids.add(source_id)
        for quality_id in _string_refs(
            fact.get("quality", []),
            f"Fact {fact_id} quality",
        ):
            include_quality(quality_id)
        visiting_facts.remove(fact_id)
        visited_facts.add(fact_id)
        included_fact_ids.add(fact_id)

    def include_signal(signal_id: str) -> None:
        signal = signals.get(signal_id)
        if signal is None:
            raise IntegrityError(f"unknown Signal: {signal_id}")
        included_signal_ids.add(signal_id)
        for fact_id in _string_refs(
            signal.get("input_fact_ids", []),
            f"Signal {signal_id} input_fact_ids",
        ):
            include_fact(fact_id)

    for issue_id in sorted(issues):
        issue = issues[issue_id]
        for link_id in _string_refs(
            issue.get("evidence_link_ids", []),
            f"issue {issue_id} evidence_link_ids",
        ):
            link = links.get(link_id)
            if link is None:
                raise IntegrityError(f"unknown Evidence Link: {link_id}")
            included_link_ids.add(link_id)
            evidence_ref = link.get("evidence_ref")
            evidence_kind = link.get("evidence_kind")
            if not isinstance(evidence_ref, str):
                raise IntegrityError(f"Evidence Link has invalid evidence_ref: {link_id}")
            if evidence_kind == "fact":
                include_fact(evidence_ref)
            elif evidence_kind == "signal":
                include_signal(evidence_ref)
            else:
                raise IntegrityError(
                    f"Evidence Link has invalid evidence_kind: {link_id}"
                )

    for capability in capability_map["capabilities"]:
        for quality_id in _string_refs(
            capability.get("quality_issue_ids", []),
            f"capability {capability['capability_id']} quality_issue_ids",
        ):
            include_quality(quality_id)

    return EvidenceClosure(
        facts=tuple(deepcopy(facts[item]) for item in sorted(included_fact_ids)),
        signals=tuple(_wire_signal(signals[item]) for item in sorted(included_signal_ids)),
        evidence_links=tuple(
            deepcopy(links[item]) for item in sorted(included_link_ids)
        ),
        sources=tuple(
            deepcopy(sources[item]) for item in sorted(included_source_ids)
        ),
        data_quality=tuple(
            deepcopy(quality[item]) for item in sorted(included_quality_ids)
        ),
        capability_map=capability_map,
    )
