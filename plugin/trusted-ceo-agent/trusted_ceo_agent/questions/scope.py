from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.outputs.validation import (
    FinalValidationError,
    validate_no_absolute_paths,
)
from trusted_ceo_agent.questions.index import QuestionIndex


SCOPE_KINDS = frozenset(
    {
        "run",
        "issue",
        "section",
        "claim",
        "evidence",
        "source",
        "expert_packet",
        "revision_diff",
    }
)


@dataclass(frozen=True)
class ScopeClosure:
    scope_kind: str
    scope_instance_id: str
    start_refs: tuple[str, ...]
    issue_ids: tuple[str, ...]
    claim_refs: tuple[str, ...]
    fact_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]
    evidence_link_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    value_refs: tuple[str, ...]
    expert_packet_ids: tuple[str, ...]
    revision_diff_ids: tuple[str, ...]
    context_blocks: tuple[Mapping[str, Any], ...]
    actual_context_bytes: int


class ScopeRequired(ContractError):
    code = "SCOPE_REQUIRED"

    def __init__(self, suggestions: Sequence[Mapping[str, str]]) -> None:
        normalized = tuple(
            {
                "scope_kind": str(item["scope_kind"]),
                "scope_instance_id": str(item["scope_instance_id"]),
            }
            for item in suggestions
        )
        if not normalized:
            raise ValueError("ScopeRequired needs at least one suggestion")
        self.suggestions = normalized
        super().__init__("complete question scope exceeds the context limit")


def _fact_source_ids(fact: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    refs = fact.get("source_refs", [])
    if not isinstance(refs, list):
        raise ContractError(f"Fact source refs are invalid: {fact.get('fact_id')}")
    for reference in refs:
        if not isinstance(reference, Mapping) or not isinstance(
            reference.get("source_id"), str
        ):
            raise ContractError(f"Fact Source ref is invalid: {fact.get('fact_id')}")
        result.add(str(reference["source_id"]))
    return result


def _value_refs(index: QuestionIndex, facts: set[str], signals: set[str]) -> set[str]:
    subjects = facts | signals
    return {
        value_ref
        for value_ref, entry in index.value_table.items()
        if entry.get("fact_or_signal_id") in subjects
    }


def _context_block(
    *,
    kind: str,
    subject_ref: str,
    document: Mapping[str, Any],
    claim_refs: set[str],
    evidence_ids: set[str],
    source_refs: set[str],
    value_refs: set[str],
) -> dict[str, Any]:
    safe = copy.deepcopy(dict(document))
    try:
        validate_no_absolute_paths(safe)
    except FinalValidationError as error:
        raise ContractError(
            f"question context contains an absolute path: {subject_ref}"
        ) from error
    text = canonical_bytes(safe).decode("utf-8")
    identity = {
        "block_kind": kind,
        "subject_ref": subject_ref,
        "text": text,
    }
    return {
        "block_ref": make_id("contextblock", identity),
        "block_kind": kind,
        "subject_ref": subject_ref,
        "text": text,
        "claim_refs": sorted(claim_refs),
        "evidence_link_ids": sorted(evidence_ids),
        "source_refs": sorted(source_refs),
        "value_refs": sorted(value_refs),
    }


def _source_context(source: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "source_type",
        "access_policy",
        "evidence_usage",
        "observation_roles",
        "display_name",
        "media_type",
        "sha256",
        "size_bytes",
        "snapshot_ref",
    )
    return {
        key: copy.deepcopy(source[key])
        for key in allowed
        if key in source
    }


def _narrower_suggestions(
    index: QuestionIndex,
    *,
    issue_ids: set[str],
    evidence_ids: set[str],
    source_ids: set[str],
) -> list[dict[str, str]]:
    if len(issue_ids) > 1:
        return [
            {"scope_kind": "issue", "scope_instance_id": item}
            for item in sorted(issue_ids)
        ]
    if evidence_ids:
        return [
            {"scope_kind": "evidence", "scope_instance_id": item}
            for item in sorted(evidence_ids)
        ]
    if source_ids:
        return [
            {"scope_kind": "source", "scope_instance_id": item}
            for item in sorted(source_ids)
        ]
    if index.issues:
        return [
            {"scope_kind": "issue", "scope_instance_id": item}
            for item in sorted(index.issues)
        ]
    return [{"scope_kind": "run", "scope_instance_id": "run"}]


def resolve_scope(
    index: QuestionIndex,
    scope_kind: str,
    scope_instance_id: str,
    *,
    maximum_bytes: int = 131_072,
) -> ScopeClosure:
    if scope_kind not in SCOPE_KINDS:
        raise ContractError(f"unknown result question scope: {scope_kind}")
    if not isinstance(scope_instance_id, str) or not scope_instance_id:
        raise ContractError("scope instance ID is required")
    if maximum_bytes < 1 or maximum_bytes > 131_072:
        raise ContractError("maximum context bytes must be in 1..131072")

    issue_ids: set[str] = set()
    claim_refs: set[str] = set()
    fact_ids: set[str] = set()
    signal_ids: set[str] = set()
    evidence_ids: set[str] = set()
    source_ids: set[str] = set()
    packet_ids: set[str] = set()
    diff_ids: set[str] = set()
    include_trust = scope_kind in {"run", "section"}

    def add_fact(fact_id: str, visiting: set[str] | None = None) -> None:
        if fact_id in fact_ids:
            return
        fact = index.facts.get(fact_id)
        if fact is None:
            raise ContractError(f"scope references unknown Fact: {fact_id}")
        active = set(visiting or ())
        if fact_id in active:
            raise ContractError(f"Fact derivation cycle: {fact_id}")
        active.add(fact_id)
        source_ids.update(_fact_source_ids(fact))
        derivation = fact.get("derivation")
        if isinstance(derivation, Mapping):
            inputs = derivation.get("input_fact_ids", [])
            if not isinstance(inputs, list):
                raise ContractError(f"Fact derivation is invalid: {fact_id}")
            for nested in inputs:
                if not isinstance(nested, str):
                    raise ContractError(f"Fact derivation ref is invalid: {fact_id}")
                add_fact(nested, active)
        fact_ids.add(fact_id)

    def add_signal(signal_id: str) -> None:
        signal = index.signals.get(signal_id)
        if signal is None:
            raise ContractError(f"scope references unknown Signal: {signal_id}")
        signal_ids.add(signal_id)
        inputs = signal.get("input_fact_ids", [])
        if not isinstance(inputs, list):
            raise ContractError(f"Signal input refs are invalid: {signal_id}")
        for fact_id in inputs:
            if not isinstance(fact_id, str):
                raise ContractError(f"Signal input ref is invalid: {signal_id}")
            add_fact(fact_id)

    def add_evidence(evidence_id: str) -> None:
        link = index.evidence_links.get(evidence_id)
        if link is None:
            raise ContractError(
                f"scope references unknown Evidence Link: {evidence_id}"
            )
        evidence_ids.add(evidence_id)
        reference = link.get("evidence_ref")
        if not isinstance(reference, str):
            raise ContractError(f"Evidence Link reference is invalid: {evidence_id}")
        if link.get("evidence_kind") == "fact":
            add_fact(reference)
        elif link.get("evidence_kind") == "signal":
            add_signal(reference)
        else:
            raise ContractError(f"Evidence Link kind is invalid: {evidence_id}")
        target = link.get("target_ref")
        if isinstance(target, str):
            if target in index.issues:
                issue_ids.add(target)
                for claim_ref, claim in index.claims.items():
                    if claim.get("issue_ref") == target:
                        claim_refs.add(claim_ref)
            if target in index.claims:
                claim_refs.add(target)
                issue_ref = index.claims[target].get("issue_ref")
                if isinstance(issue_ref, str):
                    issue_ids.add(issue_ref)

    def add_issue(issue_id: str) -> None:
        issue = index.issues.get(issue_id)
        if issue is None:
            raise ContractError(f"scope references unknown issue: {issue_id}")
        issue_ids.add(issue_id)
        for claim_ref, claim in index.claims.items():
            if claim.get("issue_ref") == issue_id:
                claim_refs.add(claim_ref)
        for evidence_id in issue.get("evidence_link_ids", []):
            if not isinstance(evidence_id, str):
                raise ContractError(f"issue evidence ref is invalid: {issue_id}")
            add_evidence(evidence_id)
        for packet_id, packet in index.expert_packets.items():
            if packet.get("target_issue_ref") == issue_id:
                packet_ids.add(packet_id)

    def select_reference(reference: str) -> None:
        if reference in index.issues:
            add_issue(reference)
        elif reference in index.claims:
            claim_refs.add(reference)
            issue_ref = index.claims[reference].get("issue_ref")
            if not isinstance(issue_ref, str):
                raise ContractError(f"claim has no issue: {reference}")
            add_issue(issue_ref)
        elif reference in index.evidence_links:
            add_evidence(reference)
        elif reference in index.sources:
            source_ids.add(reference)
            for fact_id, fact in index.facts.items():
                if reference in _fact_source_ids(fact):
                    add_fact(fact_id)
            for evidence_id, link in index.evidence_links.items():
                evidence_ref = link.get("evidence_ref")
                if evidence_ref in fact_ids:
                    add_evidence(evidence_id)
                elif evidence_ref in index.signals:
                    signal = index.signals[str(evidence_ref)]
                    if set(signal.get("input_fact_ids", [])) & fact_ids:
                        add_evidence(evidence_id)
        elif reference in index.expert_packets:
            packet_ids.add(reference)
            target = index.expert_packets[reference].get("target_issue_ref")
            if isinstance(target, str):
                add_issue(target)
        elif reference in index.revision_diffs:
            diff_ids.add(reference)
        else:
            raise ContractError(f"unknown result question scope instance: {reference}")

    if scope_kind == "run":
        if scope_instance_id != "run":
            raise ContractError("run scope instance ID must be run")
        for issue_id in index.issues:
            add_issue(issue_id)
        packet_ids.update(index.expert_packets)
        diff_ids.update(index.revision_diffs)
    elif scope_kind == "issue":
        add_issue(scope_instance_id)
    elif scope_kind == "section":
        parts = scope_instance_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "section" or not parts[1]:
            raise ContractError("section scope instance ID is invalid")
        if parts[2] == "all":
            for issue_id in index.issues:
                add_issue(issue_id)
        else:
            select_reference(parts[2])
    elif scope_kind == "claim":
        if scope_instance_id not in index.claims:
            raise ContractError(f"unknown claim: {scope_instance_id}")
        claim_refs.add(scope_instance_id)
        issue_ref = index.claims[scope_instance_id].get("issue_ref")
        if not isinstance(issue_ref, str):
            raise ContractError(f"claim has no issue: {scope_instance_id}")
        add_issue(issue_ref)
    elif scope_kind == "evidence":
        add_evidence(scope_instance_id)
    elif scope_kind == "source":
        if scope_instance_id not in index.sources:
            raise ContractError(f"unknown Source: {scope_instance_id}")
        select_reference(scope_instance_id)
    elif scope_kind == "expert_packet":
        if scope_instance_id not in index.expert_packets:
            raise ContractError(f"unknown expert packet: {scope_instance_id}")
        select_reference(scope_instance_id)
    elif scope_kind == "revision_diff":
        if scope_instance_id not in index.revision_diffs:
            raise ContractError(f"unknown revision diff: {scope_instance_id}")
        diff_ids.add(scope_instance_id)

    for source_id in source_ids:
        if source_id not in index.sources:
            raise ContractError(f"scope references unknown Source: {source_id}")
    values = _value_refs(index, fact_ids, signal_ids)
    blocks: list[dict[str, Any]] = []
    for issue_id in sorted(issue_ids):
        issue = index.issues[issue_id]
        local_claims = {
            ref for ref in claim_refs if index.claims[ref].get("issue_ref") == issue_id
        }
        local_evidence = set(issue.get("evidence_link_ids", [])) & evidence_ids
        blocks.append(
            _context_block(
                kind="issue",
                subject_ref=issue_id,
                document=issue,
                claim_refs=local_claims,
                evidence_ids=local_evidence,
                source_refs=source_ids,
                value_refs=values,
            )
        )
    for claim_ref in sorted(claim_refs):
        blocks.append(
            _context_block(
                kind="claim",
                subject_ref=claim_ref,
                document=index.claims[claim_ref],
                claim_refs={claim_ref},
                evidence_ids=evidence_ids,
                source_refs=source_ids,
                value_refs=values,
            )
        )
    for fact_id in sorted(fact_ids):
        local_sources = _fact_source_ids(index.facts[fact_id])
        blocks.append(
            _context_block(
                kind="fact",
                subject_ref=fact_id,
                document=index.facts[fact_id],
                claim_refs=claim_refs,
                evidence_ids={
                    item
                    for item in evidence_ids
                    if index.evidence_links[item].get("evidence_ref") == fact_id
                },
                source_refs=local_sources,
                value_refs=_value_refs(index, {fact_id}, set()),
            )
        )
    for signal_id in sorted(signal_ids):
        blocks.append(
            _context_block(
                kind="signal",
                subject_ref=signal_id,
                document=index.signals[signal_id],
                claim_refs=claim_refs,
                evidence_ids={
                    item
                    for item in evidence_ids
                    if index.evidence_links[item].get("evidence_ref") == signal_id
                },
                source_refs=source_ids,
                value_refs=_value_refs(index, set(), {signal_id}),
            )
        )
    for evidence_id in sorted(evidence_ids):
        blocks.append(
            _context_block(
                kind="evidence",
                subject_ref=evidence_id,
                document=index.evidence_links[evidence_id],
                claim_refs=claim_refs,
                evidence_ids={evidence_id},
                source_refs=source_ids,
                value_refs=values,
            )
        )
    for source_id in sorted(source_ids):
        blocks.append(
            _context_block(
                kind="source",
                subject_ref=source_id,
                document=_source_context(index.sources[source_id]),
                claim_refs=claim_refs,
                evidence_ids=evidence_ids,
                source_refs={source_id},
                value_refs=values,
            )
        )
    for packet_id in sorted(packet_ids):
        blocks.append(
            _context_block(
                kind="expert_packet",
                subject_ref=packet_id,
                document=index.expert_packets[packet_id],
                claim_refs=claim_refs,
                evidence_ids=evidence_ids,
                source_refs=source_ids,
                value_refs=values,
            )
        )
    for diff_id in sorted(diff_ids):
        blocks.append(
            _context_block(
                kind="revision_diff",
                subject_ref=diff_id,
                document=index.revision_diffs[diff_id],
                claim_refs=claim_refs,
                evidence_ids=evidence_ids,
                source_refs=source_ids,
                value_refs=values,
            )
        )
    if include_trust:
        for event_id in sorted(index.trust_events):
            blocks.append(
                _context_block(
                    kind="trust",
                    subject_ref=event_id,
                    document=index.trust_events[event_id],
                    claim_refs=set(),
                    evidence_ids=set(),
                    source_refs=set(),
                    value_refs=set(),
                )
            )
    blocks.sort(key=lambda item: (item["block_kind"], item["subject_ref"]))
    actual_bytes = len(canonical_bytes(blocks))
    if actual_bytes > maximum_bytes:
        raise ScopeRequired(
            _narrower_suggestions(
                index,
                issue_ids=issue_ids,
                evidence_ids=evidence_ids,
                source_ids=source_ids,
            )
        )
    start_refs = ("run",) if scope_kind == "run" else (scope_instance_id,)
    return ScopeClosure(
        scope_kind=scope_kind,
        scope_instance_id=scope_instance_id,
        start_refs=start_refs,
        issue_ids=tuple(sorted(issue_ids)),
        claim_refs=tuple(sorted(claim_refs)),
        fact_ids=tuple(sorted(fact_ids)),
        signal_ids=tuple(sorted(signal_ids)),
        evidence_link_ids=tuple(sorted(evidence_ids)),
        source_refs=tuple(sorted(source_ids)),
        value_refs=tuple(sorted(values)),
        expert_packet_ids=tuple(sorted(packet_ids)),
        revision_diff_ids=tuple(sorted(diff_ids)),
        context_blocks=tuple(blocks),
        actual_context_bytes=actual_bytes,
    )
