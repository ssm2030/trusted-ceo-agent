from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256
from trusted_ceo_agent.web_report.closure import EvidenceClosure


def _document(
    files: Mapping[str, bytes],
    path: str,
    *,
    default: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = files.get(path)
    if payload is None:
        if default is not None:
            return default
        raise IntegrityError(f"required expert packet artifact is missing: {path}")
    try:
        value = strict_loads(payload)
    except (UnicodeError, ValueError) as error:
        raise IntegrityError(f"invalid expert packet artifact: {path}") from error
    if not isinstance(value, Mapping):
        raise IntegrityError(f"expert packet artifact must be an object: {path}")
    return value


def _payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = value.get("payload", value)
    if not isinstance(payload, Mapping):
        raise IntegrityError("expert candidate payload must be an object")
    return payload


def _entries(value: Mapping[str, Any], field: str) -> tuple[Mapping[str, Any], ...]:
    raw = value.get(field, [])
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise IntegrityError(f"{field} must be an array")
    entries: list[Mapping[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise IntegrityError(f"{field} entry must be an object")
        entries.append(entry)
    return tuple(entries)


def _index(
    values: Sequence[Mapping[str, Any]],
    field: str,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for value in values:
        identifier = value.get(field)
        if not isinstance(identifier, str) or not identifier:
            raise IntegrityError(f"{label} has an invalid {field}")
        if identifier in result:
            raise IntegrityError(f"duplicate {label}: {identifier}")
        result[identifier] = value
    return result


def _candidate_body(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    body = entry.get("payload")
    if not isinstance(body, Mapping):
        raise IntegrityError("expert candidate body must be an object")
    return body


def _matching_candidates(
    integrated: Mapping[str, Any],
    deep: Mapping[str, Any],
    *,
    trigger_ref: str,
    target_issue_ref: str,
    issue_aliases: Mapping[str, str],
) -> tuple[Mapping[str, Any], ...]:
    candidates: list[Mapping[str, Any]] = []
    for container in (integrated, deep):
        for entry in _entries(container, "expert_review_candidates"):
            body = _candidate_body(entry)
            raw_target = body.get(
                "target_issue_local_key",
                body.get("target_issue_ref"),
            )
            resolved_target = (
                issue_aliases.get(raw_target)
                if isinstance(raw_target, str)
                else None
            )
            if (
                body.get("expert_trigger_ref") == trigger_ref
                and resolved_target == target_issue_ref
            ):
                candidates.append(body)
    return tuple(candidates)


def _candidate_evidence(
    candidates: Sequence[Mapping[str, Any]],
) -> set[str]:
    refs: set[str] = set()
    for candidate in candidates:
        proposals = candidate.get("evidence_proposals", [])
        if not isinstance(proposals, Sequence) or isinstance(
            proposals, (str, bytes, bytearray)
        ):
            raise IntegrityError("expert evidence proposals must be an array")
        for proposal in proposals:
            if not isinstance(proposal, Mapping):
                raise IntegrityError("expert evidence proposal must be an object")
            reference = proposal.get("evidence_ref")
            if not isinstance(reference, str) or not reference:
                raise IntegrityError("expert evidence proposal lacks a reference")
            refs.add(reference)
    return refs


def _facts_for_evidence(
    refs: set[str],
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    result: set[str] = set()
    for reference in refs:
        if reference in facts:
            result.add(reference)
            continue
        signal = signals.get(reference)
        if signal is None:
            raise IntegrityError(f"expert candidate references unknown evidence: {reference}")
        inputs = signal.get("input_fact_ids", [])
        if not isinstance(inputs, list):
            raise IntegrityError(f"Signal input facts are invalid: {reference}")
        for fact_id in inputs:
            if not isinstance(fact_id, str) or fact_id not in facts:
                raise IntegrityError(f"Signal references unknown Fact: {fact_id}")
            result.add(fact_id)
    return result


def _fact_sources(
    fact_id: str,
    facts: Mapping[str, Mapping[str, Any]],
    *,
    visiting: set[str] | None = None,
) -> tuple[set[str], list[dict[str, str]]]:
    if fact_id not in facts:
        raise IntegrityError(f"unknown Fact: {fact_id}")
    visiting = set(visiting or ())
    if fact_id in visiting:
        raise IntegrityError(f"Fact derivation cycle: {fact_id}")
    visiting.add(fact_id)
    fact = facts[fact_id]
    sources: set[str] = set()
    locators: list[dict[str, str]] = []
    source_refs = fact.get("source_refs", [])
    if not isinstance(source_refs, list):
        raise IntegrityError(f"Fact Source refs are invalid: {fact_id}")
    for source_ref in source_refs:
        if not isinstance(source_ref, Mapping):
            raise IntegrityError(f"Fact Source ref is invalid: {fact_id}")
        source_id = source_ref.get("source_id")
        locator = source_ref.get("locator")
        if not isinstance(source_id, str) or not isinstance(locator, Mapping):
            raise IntegrityError(f"Fact Source locator is invalid: {fact_id}")
        sources.add(source_id)
        locators.append(
            {
                "source_ref": source_id,
                "locator": jcs_bytes(locator).decode("utf-8"),
            }
        )
    derivation = fact.get("derivation")
    if isinstance(derivation, Mapping):
        inputs = derivation.get("input_fact_ids", [])
        if not isinstance(inputs, list):
            raise IntegrityError(f"Fact derivation inputs are invalid: {fact_id}")
        for input_fact_id in inputs:
            if not isinstance(input_fact_id, str):
                raise IntegrityError(f"Fact derivation input is invalid: {fact_id}")
            nested_sources, nested_locators = _fact_sources(
                input_fact_id,
                facts,
                visiting=visiting,
            )
            sources.update(nested_sources)
            locators.extend(nested_locators)
    return sources, locators


def _uncertainties(
    deep: Mapping[str, Any],
    *,
    target_issue_ref: str,
    issue_aliases: Mapping[str, str],
) -> set[str]:
    result: set[str] = set()
    for entry in _entries(deep, "remaining_uncertainties"):
        body = _candidate_body(entry)
        raw_target = body.get("target_issue_ref")
        if isinstance(raw_target, str) and issue_aliases.get(raw_target) == target_issue_ref:
            identifier = entry.get("local_key", body.get("reason_code"))
            if isinstance(identifier, str) and identifier:
                result.add(identifier)
    return result


def build_expert_packet_view(
    files: Mapping[str, bytes],
    final_result: Mapping[str, Any],
    closure: EvidenceClosure,
    *,
    run_id: str,
    revision: int,
) -> tuple[dict[str, Any], ...]:
    """Expand accepted public packets without adding an expert-response channel."""

    structured = _document(files, "final/structured-output.json")
    integrated = _payload(
        _document(
            files,
            "reasoning/integrated-assessment.json",
            default={"payload": {}},
        )
    )
    deep = _payload(
        _document(
            files,
            "reasoning/deep-dive-result.json",
            default={"payload": {}},
        )
    )

    public_packets = _index(
        tuple(
            item
            for item in final_result.get("expert_review_packets", [])
            if isinstance(item, Mapping)
        ),
        "expert_packet_id",
        "public expert packet",
    )
    structured_packets = _index(
        tuple(
            item
            for item in structured.get("expert_review_packets", [])
            if isinstance(item, Mapping)
        ),
        "expert_packet_id",
        "structured expert packet",
    )
    issues = _index(
        tuple(
            item
            for item in final_result.get("issues", [])
            if isinstance(item, Mapping)
        ),
        "issue_id",
        "issue",
    )
    structured_issues = tuple(
        item
        for item in structured.get("issues", [])
        if isinstance(item, Mapping)
    )
    issue_aliases: dict[str, str] = {
        issue_id: issue_id for issue_id in issues
    }
    for issue in structured_issues:
        issue_id = issue.get("issue_id")
        local_key = issue.get("local_key")
        if isinstance(issue_id, str):
            issue_aliases[issue_id] = issue_id
            if isinstance(local_key, str):
                issue_aliases[local_key] = issue_id

    facts = _index(closure.facts, "fact_id", "Fact")
    signals = _index(closure.signals, "signal_id", "Signal")
    links = _index(closure.evidence_links, "evidence_link_id", "Evidence Link")
    known_sources = {
        str(source["source_id"])
        for source in closure.sources
        if isinstance(source.get("source_id"), str)
    }

    packets: list[dict[str, Any]] = []
    for packet_id in sorted(public_packets):
        public = public_packets[packet_id]
        structured_packet = structured_packets.get(packet_id)
        if structured_packet is None:
            raise IntegrityError(
                f"public expert packet lacks a structured candidate: {packet_id}"
            )
        trigger_ref = structured_packet.get("_trigger_ref")
        target_issue_ref = structured_packet.get("_target_issue_ref")
        if not isinstance(trigger_ref, str) or not isinstance(
            target_issue_ref, str
        ):
            raise IntegrityError(f"structured expert packet is incomplete: {packet_id}")
        if target_issue_ref not in issues:
            raise IntegrityError(f"expert packet targets unknown issue: {target_issue_ref}")
        candidates = _matching_candidates(
            integrated,
            deep,
            trigger_ref=trigger_ref,
            target_issue_ref=target_issue_ref,
            issue_aliases=issue_aliases,
        )
        if not candidates:
            raise IntegrityError(
                f"public expert packet lacks an accepted candidate: {packet_id}"
            )
        evidence_refs = _candidate_evidence(candidates)
        fact_refs = _facts_for_evidence(evidence_refs, facts, signals)
        evidence_link_ids = sorted(
            link_id
            for link_id, link in links.items()
            if link.get("target_ref") == target_issue_ref
            and (
                link.get("evidence_ref") in evidence_refs
                or link.get("evidence_ref") in fact_refs
            )
        )
        source_refs: set[str] = set()
        source_locators: list[dict[str, str]] = []
        for fact_id in sorted(fact_refs):
            nested_sources, nested_locators = _fact_sources(fact_id, facts)
            source_refs.update(nested_sources)
            source_locators.extend(nested_locators)
        unknown_sources = source_refs - known_sources
        if unknown_sources:
            raise IntegrityError(
                f"expert packet references unknown Source: {sorted(unknown_sources)[0]}"
            )
        required_documents = sorted(
            {
                str(reference)
                for candidate in candidates
                for reference in candidate.get("required_document_refs", [])
                if isinstance(reference, str) and reference
            }
        )
        issue = issues[target_issue_ref]
        cause_hypotheses = sorted(
            str(item["claim_code"])
            for item in issue.get("cause_hypotheses", [])
            if isinstance(item, Mapping) and isinstance(item.get("claim_code"), str)
        )
        counter_hypotheses = sorted(
            str(item["claim_code"])
            for item in issue.get("counter_hypotheses", [])
            if isinstance(item, Mapping) and isinstance(item.get("claim_code"), str)
        )
        uncertainty_refs = {
            str(item)
            for item in issue.get("unresolved_conflicts", [])
            if isinstance(item, str) and item
        }
        uncertainty_refs.update(
            _uncertainties(
                deep,
                target_issue_ref=target_issue_ref,
                issue_aliases=issue_aliases,
            )
        )
        deduped_locators = {
            (item["source_ref"], item["locator"]): item
            for item in source_locators
        }
        packet = {
            "expert_packet_id": packet_id,
            "profession": str(public["profession"]),
            "target_issue_ref": target_issue_ref,
            "fact_refs": sorted(fact_refs),
            "evidence_link_ids": evidence_link_ids,
            "source_refs": sorted(source_refs),
            "cause_hypotheses": cause_hypotheses,
            "counter_hypotheses": counter_hypotheses,
            "unresolved_uncertainties": sorted(uncertainty_refs),
            "required_document_refs": required_documents,
            "review_question": str(public["question_template"]),
            "forbidden_conclusions": sorted(
                str(item)
                for item in public.get("forbidden_conclusions", [])
                if isinstance(item, str)
            ),
            "source_locators": [
                deduped_locators[key] for key in sorted(deduped_locators)
            ],
            "run_id": run_id,
            "revision": revision,
            "packet_hash": "0" * 64,
        }
        packet["packet_hash"] = jcs_sha256(
            packet,
            omit_root_field="packet_hash",
        )
        packets.append(packet)
    return tuple(packets)
