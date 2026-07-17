from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.filesystem import ensure_within


def _payload_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def assemble_evidence_core(
    *,
    envelope: Mapping[str, Any],
    mission_contract_ref: str,
    pack_manifest: Mapping[str, Any],
    component_manifest: Mapping[str, Any],
    source_registry: Sequence[Mapping[str, Any]],
    data_quality_register: Sequence[Mapping[str, Any]],
    fact_register: Sequence[Mapping[str, Any]],
    signal_register: Sequence[Mapping[str, Any]],
    evidence_links: Sequence[Mapping[str, Any]],
    capability_map: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "envelope": deepcopy(dict(envelope)),
        "mission_contract_ref": mission_contract_ref,
        "pack_manifest": deepcopy(dict(pack_manifest)),
        "component_manifest": deepcopy(dict(component_manifest)),
        "source_registry": sorted((deepcopy(dict(item)) for item in source_registry), key=lambda item: item["source_id"]),
        "data_quality_register": sorted((deepcopy(dict(item)) for item in data_quality_register), key=lambda item: item["quality_issue_id"]),
        "fact_register": sorted((deepcopy(dict(item)) for item in fact_register), key=lambda item: item["fact_id"]),
        "signal_register": sorted((deepcopy(dict(item)) for item in signal_register), key=lambda item: item["signal_id"]),
        "evidence_links": sorted((deepcopy(dict(item)) for item in evidence_links), key=lambda item: item["evidence_link_id"]),
        "capability_map": deepcopy(dict(capability_map)),
    }
    return {**body, "integrity": {"payload_hash": _payload_hash(body)}}


class EvidenceCoreValidator:
    def __init__(self, schema_store: SchemaStore | None = None) -> None:
        self.schemas = schema_store or SchemaStore()

    def validate(self, core: Mapping[str, Any], *, source_root: Path | None = None) -> None:
        self.schemas.validate("evidence-core.schema.json", core)
        body = {key: deepcopy(value) for key, value in core.items() if key != "integrity"}
        if _payload_hash(body) != core["integrity"]["payload_hash"]:
            raise IntegrityError("Evidence Core payload hash mismatch")

        sources = self._unique(core["source_registry"], "source_id")
        quality = self._unique(core["data_quality_register"], "quality_issue_id")
        facts = self._unique(core["fact_register"], "fact_id")
        signals = self._unique(core["signal_register"], "signal_id")
        links = self._unique(core["evidence_links"], "evidence_link_id")

        if source_root is not None:
            root = source_root.resolve(strict=True)
            for source in sources.values():
                path = ensure_within(root, root / source["snapshot_ref"])
                payload = path.read_bytes()
                if len(payload) != source["size_bytes"] or hashlib.sha256(payload).hexdigest() != source["sha256"]:
                    raise IntegrityError(f"Source snapshot hash mismatch: {source['source_id']}")

        for fact in facts.values():
            fact_body = {key: deepcopy(value) for key, value in fact.items() if key != "integrity"}
            if _payload_hash(fact_body) != fact["integrity"]["payload_hash"]:
                raise IntegrityError(f"Fact payload hash mismatch: {fact['fact_id']}")
            for issue_id in fact["quality"]:
                if issue_id not in quality:
                    raise IntegrityError(f"Fact references unknown Quality issue: {issue_id}")
            for source_ref in fact["source_refs"]:
                if source_ref["source_id"] not in sources:
                    raise IntegrityError(f"Fact references unknown Source: {source_ref['source_id']}")
            if fact["derivation"] is not None:
                for input_id in fact["derivation"]["input_fact_ids"]:
                    if input_id not in facts:
                        raise IntegrityError(f"Fact derivation references unknown Fact: {input_id}")

        for signal in signals.values():
            for fact_id in signal["input_fact_ids"]:
                if fact_id not in facts:
                    raise IntegrityError(f"Signal references unknown Fact: {fact_id}")
            if signal["outcome"] == "not_assessable" and not (signal["missing_fact_codes"] or signal["reason_codes"]):
                raise IntegrityError(f"not_assessable Signal lacks boundary reason: {signal['signal_id']}")

        for link in links.values():
            evidence_ref = link["evidence_ref"]
            evidence = facts.get(evidence_ref) if link["evidence_kind"] == "fact" else signals.get(evidence_ref)
            if evidence is None:
                raise IntegrityError(f"Evidence Link references unknown Evidence: {evidence_ref}")
            if link["evidence_kind"] == "signal":
                outcome = evidence["outcome"]
                if outcome == "not_assessable" and link["polarity"] == "supports" and link["target_type"] != "expert_review_need":
                    raise IntegrityError("not_assessable Signal illegally supports a material claim")
                if outcome == "not_triggered" and link["polarity"] == "supports" and link["target_type"] != "counter_hypothesis":
                    raise IntegrityError("not_triggered Signal illegally supports a material claim")

        for capability in core["capability_map"]["capabilities"]:
            for issue_id in capability["quality_issue_ids"]:
                if issue_id not in quality:
                    raise IntegrityError(f"Capability references unknown Quality issue: {issue_id}")

        for fact_id in facts:
            if not self._reaches_source(fact_id, facts, set()):
                raise IntegrityError(f"Fact lineage does not reach Source: {fact_id}")

    @staticmethod
    def _unique(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for item in items:
            identifier = str(item[key])
            if identifier in result:
                raise IntegrityError(f"duplicate ID: {identifier}")
            result[identifier] = item
        return result

    def _reaches_source(self, fact_id: str, facts: Mapping[str, Mapping[str, Any]], visiting: set[str]) -> bool:
        if fact_id in visiting:
            raise IntegrityError(f"Fact derivation cycle: {fact_id}")
        fact = facts[fact_id]
        if fact["source_refs"]:
            return True
        derivation = fact["derivation"]
        if derivation is None:
            return False
        next_visiting = set(visiting)
        next_visiting.add(fact_id)
        return bool(derivation["input_fact_ids"]) and all(
            self._reaches_source(input_id, facts, next_visiting) for input_id in derivation["input_fact_ids"]
        )
