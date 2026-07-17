from __future__ import annotations

import copy
import hmac
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.condition_dsl import ConditionContext, evaluate_condition
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.evidence.core import assemble_evidence_core
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.grading.reducer import derive_grading_input
from trusted_ceo_agent.outputs.final_result import build_final_result
from trusted_ceo_agent.outputs.professional_publication import build_professional_publication_from_files
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.outputs.validation import revalidate_package
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex


IMPACT_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
URGENCY_ORDER = {"immediate": 0, "near_term": 1, "routine": 2}
NUMBER_LITERAL = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?\s*%?")


def _load(files: Mapping[str, bytes], path: str, default: Any = None) -> Any:
    payload = files.get(path)
    if payload is None:
        if default is not None:
            return default
        raise ContractError(f"required artifact is missing: {path}")
    return json.loads(payload.decode("utf-8"))


def _status(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("status", value.get("diagnostic_disposition"))
        return str(raw) if raw is not None else None
    return None


def _pack_authority(manifest: Mapping[str, Any]) -> str:
    domains = [item for item in manifest.get("packs", []) if item.get("pack_type") == "domain"]
    if not domains or domains[0].get("pack_id") == "generic-business-boundary":
        return "boundary"
    authority = domains[0].get("effective_authority")
    return str(authority) if authority in {"full", "provisional", "boundary"} else "boundary"


def _runtime_pack_index(
    files: Mapping[str, bytes], issues: list[Any],
) -> RuntimePackIndex | None:
    has_snapshots = any(path.startswith("packs/snapshots/") for path in files)
    if has_snapshots or issues:
        return RuntimePackIndex.from_files(files)
    return None


def _mission(files: Mapping[str, bytes]) -> Mapping[str, Any]:
    path = (
        "mission/effective-mission-contract.json"
        if "mission/effective-mission-contract.json" in files
        else "mission/mission-contract.json"
    )
    mission = _load(files, path)
    if not isinstance(mission, Mapping):
        raise ContractError("Mission contract must be an object")
    return mission


def _problem_pack(index: RuntimePackIndex, reference: Any) -> Mapping[str, Any]:
    if not isinstance(reference, str) or not reference:
        raise ContractError("integrated issue lacks a Problem family reference")
    direct = index.problems_by_family.get(reference)
    if direct is not None:
        return direct
    matches = [
        pack for pack in index.problem_packs
        if reference == f"{pack['pack_id']}@{pack['pack_version']}"
    ]
    if len(matches) != 1:
        raise ContractError(f"Problem Pack is not authorized by the runtime stack: {reference}")
    return matches[0]


def _problem_requirement(problem: Mapping[str, Any]) -> tuple[set[str], int]:
    roles: set[str] = set()
    minimum = 1
    for requirement in problem["content"].get("evidence_requirements", []):
        if not isinstance(requirement, Mapping):
            raise ContractError("Problem evidence requirement must be an object")
        raw_roles = requirement.get("required_roles", [])
        if not isinstance(raw_roles, list) or any(not isinstance(role, str) for role in raw_roles):
            raise ContractError("Problem required evidence roles must be strings")
        roles.update(raw_roles)
        raw_minimum = requirement.get("minimum_independent_chains", 1)
        if (
            not isinstance(raw_minimum, (int, Decimal))
            or isinstance(raw_minimum, bool)
            or raw_minimum != int(raw_minimum)
            or raw_minimum < 1
        ):
            raise ContractError("Problem minimum independent chains must be a positive integer")
        minimum = max(minimum, int(raw_minimum))
    return roles, minimum


def _domain_minimum(index: RuntimePackIndex) -> int:
    value = index.domain_pack["content"].get("independence_policy", {}).get(
        "minimum_independent_chains_for_leading_cause", 1,
    )
    if (
        not isinstance(value, (int, Decimal))
        or isinstance(value, bool)
        or value != int(value)
        or value < 1
    ):
        raise ContractError("Domain independence policy must contain a positive integer")
    return int(value)


def _capability(
    core: Mapping[str, Any], missing_roles: set[str] | None = None,
) -> tuple[str, list[str], bool]:
    capabilities = core.get("capability_map", {}).get("capabilities", [])
    if not isinstance(capabilities, list):
        raise ContractError("capability map capabilities must be an array")
    reasons = {
        reason for item in capabilities if isinstance(item, Mapping)
        for reason in item.get("reason_codes", []) if isinstance(reason, str)
    }
    statuses = [item.get("status") for item in capabilities if isinstance(item, Mapping)]
    if capabilities and statuses and all(status == "available" for status in statuses):
        assessability = "assessable"
    elif any(status == "available" for status in statuses):
        assessability = "partial"
        reasons.add("capability_partially_available")
    else:
        assessability = "not_assessable"
        reasons.add("capability_not_available")
    missing = sorted(missing_roles or set())
    reasons.update(f"missing_evidence_role:{role}" for role in missing)
    if missing and assessability == "assessable":
        assessability = "partial"
    return assessability, sorted(reasons), not missing


def _mission_priority_match(mission: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    priorities = mission.get("priority_dimensions", [])
    if not isinstance(priorities, list):
        return False
    targets = {
        str(payload.get("problem_family_ref", "")),
        str(payload.get("scope_key", "")),
        str(payload.get("decision_unit_ref", "")),
    }
    normalized_targets = {value.lower().replace("-", "_").strip() for value in targets if value}
    for priority in priorities:
        if not isinstance(priority, str):
            continue
        normalized = priority.lower().replace("-", "_").strip()
        if normalized in normalized_targets:
            return True
        tokens = {token for token in normalized.replace("_", " ").split() if len(token) > 3}
        if any(tokens & set(target.replace("_", " ").split()) for target in normalized_targets):
            return True
    return False


def _fact_sources(
    fact_id: str, facts: Mapping[str, Mapping[str, Any]], visiting: set[str] | None = None,
) -> set[str]:
    if fact_id not in facts:
        raise ContractError(f"Evidence lineage references an unknown Fact: {fact_id}")
    visiting = set(visiting or set())
    if fact_id in visiting:
        raise ContractError(f"Evidence lineage cycle detected: {fact_id}")
    visiting.add(fact_id)
    fact = facts[fact_id]
    sources = {
        f"source:{item['source_id']}" for item in fact.get("source_refs", [])
        if isinstance(item, Mapping) and isinstance(item.get("source_id"), str)
    }
    derivation = fact.get("derivation")
    if not sources and isinstance(derivation, Mapping):
        for input_id in derivation.get("input_fact_ids", []):
            if isinstance(input_id, str):
                sources.update(_fact_sources(input_id, facts, visiting))
    return sources or {f"fact:{fact_id}"}


def _evidence_fact_ids(
    evidence_ref: str,
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    if evidence_ref in facts:
        return {evidence_ref}
    if evidence_ref in signals:
        return {
            fact_id for fact_id in signals[evidence_ref].get("input_fact_ids", [])
            if isinstance(fact_id, str)
        }
    raise ContractError(f"unknown evidence reference: {evidence_ref}")


def _evidence_sources(
    evidence_ref: str,
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    sources: set[str] = set()
    for fact_id in _evidence_fact_ids(evidence_ref, facts, signals):
        sources.update(_fact_sources(fact_id, facts))
    return sources or {f"evidence:{evidence_ref}"}


def _observation_roles(
    evidence_refs: list[str],
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    roles: set[str] = set()
    pending = {
        fact_id for reference in evidence_refs
        for fact_id in _evidence_fact_ids(reference, facts, signals)
    }
    visited: set[str] = set()
    while pending:
        fact_id = pending.pop()
        if fact_id in visited or fact_id not in facts:
            continue
        visited.add(fact_id)
        fact = facts[fact_id]
        role = fact.get("observation_role")
        if isinstance(role, str) and role:
            roles.add(role)
        derivation = fact.get("derivation")
        if isinstance(derivation, Mapping):
            pending.update(
                item for item in derivation.get("input_fact_ids", []) if isinstance(item, str)
            )
    return roles


def _bands(refs: list[str], signals: Mapping[str, Mapping[str, Any]]) -> tuple[str, str]:
    impacts = [
        signals[ref]["impact_band_candidate"] for ref in refs
        if ref in signals and signals[ref].get("outcome") == "triggered"
        and signals[ref].get("impact_band_candidate") in IMPACT_ORDER
    ]
    urgencies = [
        signals[ref]["urgency_band_candidate"] for ref in refs
        if ref in signals and signals[ref].get("outcome") == "triggered"
        and signals[ref].get("urgency_band_candidate") in URGENCY_ORDER
    ]
    return (
        min(impacts, key=IMPACT_ORDER.get) if impacts else "unknown",
        min(urgencies, key=URGENCY_ORDER.get) if urgencies else "unknown",
    )


def _link(
    issue_id: str, evidence_ref: str, polarity: str, independence_group_id: str,
) -> dict[str, Any]:
    seed = {"issue_id": issue_id, "evidence_ref": evidence_ref, "polarity": polarity}
    body = {
        "target_ref": issue_id, "target_type": "integrated_issue",
        "evidence_ref": evidence_ref,
        "evidence_kind": "fact" if evidence_ref.startswith("fact_") else "signal",
        "polarity": polarity,
        "role": "observation" if polarity == "supports" else "counter_evidence",
        "rationale_template": "결정적 런타임이 통합 이슈와 검증된 근거를 연결했습니다.",
        "value_refs": [], "stage": "integrated", "materialized_by": "runtime_integrator",
        "origin": {
            "origin_type": "deterministic_rule", "origin_job_id": None,
            "model_profile": None, "prompt_hash": None,
            "proposal_hash": hashlib.sha256(canonical_bytes(seed)).hexdigest(),
        },
        "independence_group_id": independence_group_id,
    }
    body["rationale_template"] = "This runtime-integrated issue is linked to validated evidence."
    return {"evidence_link_id": make_id("evidence", body), **body}


def _condition_context(
    core: Mapping[str, Any], mission: Mapping[str, Any], overlay: Mapping[str, Any],
) -> ConditionContext:
    return ConditionContext(
        facts=core.get("fact_register", []), signals=core.get("signal_register", []),
        mission=mission, hitl=overlay,
    )


def _problem_tests(problem: Mapping[str, Any]) -> set[str]:
    return {
        str(item["test_ref"]) for item in problem["content"].get("distinguishing_tests", [])
        if isinstance(item, Mapping) and isinstance(item.get("test_ref"), str)
    }


def _response_catalog(problem: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["response_ref"]): item
        for item in problem["content"].get("conditional_response_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("response_ref"), str)
    }


def _expert_catalog(index: RuntimePackIndex) -> dict[str, Mapping[str, Any]]:
    catalog = {
        str(item["expert_trigger_ref"]): item
        for item in index.domain_pack["content"].get("expert_triggers", [])
        if isinstance(item, Mapping) and isinstance(item.get("expert_trigger_ref"), str)
    }
    for problem in index.problem_packs:
        for reference in problem["content"].get("expert_trigger_refs", []):
            if reference not in catalog:
                raise ContractError(f"Problem Pack references an unknown Domain expert trigger: {reference}")
    return catalog


def _blocking_counter_evidence(
    problem: Mapping[str, Any], context: ConditionContext,
) -> bool:
    family = str(problem["content"]["problem_family_code"])
    for condition in problem["content"].get("blocking_counter_evidence_conditions", []):
        if not isinstance(condition, Mapping):
            raise ContractError("blocking counter-evidence condition must be an object")
        if condition.get("target_problem_family") not in {None, family}:
            continue
        expression = condition.get("condition_expression")
        if not isinstance(expression, Mapping):
            raise ContractError("blocking counter-evidence condition lacks an expression")
        if evaluate_condition(expression, context).outcome == "true":
            return True
    return False


def _expert_state(
    problem: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Any]],
    candidate_refs: set[str],
    evidence_roles: set[str],
    context: ConditionContext,
) -> tuple[str, list[tuple[Mapping[str, Any], str]]]:
    allowed = {
        str(reference) for reference in problem["content"].get("expert_trigger_refs", [])
    }
    unknown = candidate_refs - allowed
    if unknown:
        raise ContractError(f"expert candidate is outside the Problem Pack: {sorted(unknown)}")
    states: list[str] = []
    active: list[tuple[Mapping[str, Any], str]] = []
    for reference in sorted(allowed):
        trigger = catalog.get(reference)
        if trigger is None:
            raise ContractError(f"Domain expert trigger is unavailable: {reference}")
        expression = trigger.get("trigger_condition")
        if not isinstance(expression, Mapping):
            raise ContractError(f"Domain expert trigger lacks a condition: {reference}")
        outcome = evaluate_condition(expression, context).outcome
        required_roles = {
            str(role) for role in trigger.get("required_evidence_roles", [])
        }
        if outcome == "true" and required_roles.issubset(evidence_roles):
            state = "required"
        elif outcome in {"true", "not_assessable"} or reference in candidate_refs:
            state = "possible"
        else:
            continue
        states.append(state)
        active.append((trigger, state))
    if "required" in states:
        return "required", active
    if "possible" in states:
        return "possible", active
    return "none", []


def _artifact_payload(document: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(document, Mapping):
        raise ContractError(f"{label} must be an object")
    payload = document.get("payload", document)
    if not isinstance(payload, Mapping):
        raise ContractError(f"{label} payload must be an object")
    return payload


def _entries(payload: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    result: list[Mapping[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("local_key"), str):
            raise ContractError(f"{field} entry identity is invalid")
        body = entry.get("payload")
        if not isinstance(body, Mapping):
            raise ContractError(f"{field} entry payload is invalid")
        result.append(entry)
    return result


def _validate_evidence_proposals(
    proposals: Any,
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    if not isinstance(proposals, list):
        raise ContractError(f"{label} evidence proposals must be an array")
    for proposal in proposals:
        if not isinstance(proposal, Mapping):
            raise ContractError(f"{label} evidence proposal must be an object")
        reference = proposal.get("evidence_ref")
        if reference not in facts and reference not in signals:
            raise ContractError(f"{label} references unknown evidence: {reference}")


def _resolve_issue_key(reference: Any, issue_meta: Mapping[str, Mapping[str, Any]]) -> str:
    if isinstance(reference, str) and reference in issue_meta:
        return reference
    matches = [key for key, meta in issue_meta.items() if meta["issue_id"] == reference]
    if len(matches) != 1:
        raise ContractError(f"Deep Dive references an unknown integrated issue: {reference}")
    return matches[0]


def _deep_index(
    files: Mapping[str, bytes],
    overlay: Mapping[str, Any],
    issue_meta: Mapping[str, Mapping[str, Any]],
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
    pack_index: RuntimePackIndex,
) -> dict[str, dict[str, list[Mapping[str, Any]]]]:
    fields = (
        "updated_cause_hypotheses", "updated_counter_hypotheses",
        "distinguishing_test_results", "conditional_response_candidates",
        "expert_review_candidates", "remaining_uncertainties", "additional_data_requests",
    )
    indexed = {key: {field: [] for field in fields} for key in issue_meta}
    if "reasoning/deep-dive-result.json" not in files:
        return indexed
    payload = _artifact_payload(_load(files, "reasoning/deep-dive-result.json"), "Deep Dive result")
    scope = overlay.get("deep_dive_scope", {})
    if not isinstance(scope, Mapping):
        raise ContractError("Deep Dive scope must be an object")
    raw_allowed = scope.get("issue_ids", [])
    if not isinstance(raw_allowed, list):
        raise ContractError("Deep Dive issue scope must be an array")
    allowed = {_resolve_issue_key(reference, issue_meta) for reference in raw_allowed}
    mechanisms = {
        str(item["mechanism_ref"])
        for item in pack_index.domain_pack["content"].get("mechanism_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("mechanism_ref"), str)
    }
    known_metrics = {
        str(item.get("metric_code")) for item in pack_index.domain_pack["content"].get("metric_definitions", [])
        if isinstance(item, Mapping) and isinstance(item.get("metric_code"), str)
    }
    known_metrics.update(
        str(fact.get("metric_code", fact.get("fact_code"))) for fact in facts.values()
        if isinstance(fact.get("metric_code", fact.get("fact_code")), str)
    )
    seen_keys: set[str] = set()
    expert_catalog = _expert_catalog(pack_index)
    for field in fields:
        for entry in _entries(payload, field):
            local_key = str(entry["local_key"])
            if local_key in seen_keys:
                raise ContractError(f"duplicate Deep Dive local key: {local_key}")
            seen_keys.add(local_key)
            body = entry["payload"]
            target = _resolve_issue_key(body.get("target_issue_ref"), issue_meta)
            if target not in allowed:
                raise ContractError(f"Deep Dive target is outside the approved scope: {target}")
            meta = issue_meta[target]
            problem = meta["problem"]
            tests = _problem_tests(problem)
            responses = _response_catalog(problem)
            allowed_experts = set(problem["content"].get("expert_trigger_refs", []))
            if field == "updated_cause_hypotheses":
                if body.get("claim_ref") not in meta["payload"].get("cause_hypothesis_refs", []):
                    raise ContractError("Deep Dive cause update references an unknown cause claim")
                if body.get("mechanism_ref") not in mechanisms:
                    raise ContractError("Deep Dive cause update uses an unauthorized mechanism")
                if not set(body.get("distinguishing_test_refs", [])).issubset(tests):
                    raise ContractError("Deep Dive cause update uses an unauthorized test")
                _validate_evidence_proposals(body.get("evidence_proposals", []), facts, signals, field)
            elif field == "updated_counter_hypotheses":
                if body.get("claim_ref") not in meta["payload"].get("counter_hypothesis_refs", []):
                    raise ContractError("Deep Dive counter update references an unknown counter claim")
                if body.get("challenged_hypothesis_ref") not in meta["payload"].get("cause_hypothesis_refs", []):
                    raise ContractError("Deep Dive counter update challenges an unknown cause claim")
                if body.get("mechanism_ref") not in mechanisms:
                    raise ContractError("Deep Dive counter update uses an unauthorized mechanism")
                _validate_evidence_proposals(body.get("evidence_proposals", []), facts, signals, field)
            elif field == "distinguishing_test_results":
                if body.get("test_ref") not in tests:
                    raise ContractError("Deep Dive result uses a test outside the Problem Pack")
                if not set(body.get("result_fact_ids", [])).issubset(facts):
                    raise ContractError("Deep Dive test result references an unknown Fact")
                if not set(body.get("result_signal_ids", [])).issubset(signals):
                    raise ContractError("Deep Dive test result references an unknown Signal")
            elif field == "conditional_response_candidates":
                response = responses.get(str(body.get("response_ref")))
                if response is None:
                    raise ContractError("Deep Dive response is outside the Problem Pack")
                if not set(body.get("precondition_refs", [])).issubset(set(response.get("preconditions", []))):
                    raise ContractError("Deep Dive response uses an unauthorized precondition")
                if not set(body.get("disqualifier_refs", [])).issubset(set(response.get("disqualifiers", []))):
                    raise ContractError("Deep Dive response uses an unauthorized disqualifier")
                if not set(body.get("monitoring_metric_refs", [])).issubset(known_metrics):
                    raise ContractError("Deep Dive response uses an unknown monitoring metric")
                if not set(body.get("expert_review_refs", [])).issubset(allowed_experts):
                    raise ContractError("Deep Dive response uses an unauthorized expert trigger")
            elif field == "expert_review_candidates":
                reference = body.get("expert_trigger_ref")
                if reference not in allowed_experts or reference not in expert_catalog:
                    raise ContractError("Deep Dive expert candidate is outside the Pack stack")
                _validate_evidence_proposals(body.get("evidence_proposals", []), facts, signals, field)
            indexed[target][field].append(entry)
    return indexed


def _candidate_expert_refs(
    integrated_payload: Mapping[str, Any],
    issue_meta: Mapping[str, Mapping[str, Any]],
    deep: Mapping[str, Mapping[str, list[Mapping[str, Any]]]],
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
) -> dict[str, set[str]]:
    result = {
        key: {str(item) for item in meta["payload"].get("expert_trigger_refs", [])}
        for key, meta in issue_meta.items()
    }
    for entry in _entries(integrated_payload, "expert_review_candidates"):
        body = entry["payload"]
        target = _resolve_issue_key(body.get("target_issue_local_key"), issue_meta)
        reference = body.get("expert_trigger_ref")
        allowed = set(issue_meta[target]["problem"]["content"].get("expert_trigger_refs", []))
        if reference not in allowed:
            raise ContractError("integrated expert candidate is outside the Problem Pack")
        _validate_evidence_proposals(body.get("evidence_proposals", []), facts, signals, "expert candidate")
        result[target].add(str(reference))
    for target, fields in deep.items():
        for entry in fields["expert_review_candidates"]:
            result[target].add(str(entry["payload"]["expert_trigger_ref"]))
        for entry in fields["conditional_response_candidates"]:
            result[target].update(str(item) for item in entry["payload"].get("expert_review_refs", []))
    return result


def _build_relations(
    integrated_payload: Mapping[str, Any],
    issue_meta: Mapping[str, Mapping[str, Any]],
    pack_index: RuntimePackIndex,
    facts: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    mechanisms = {
        str(item["mechanism_ref"])
        for item in pack_index.domain_pack["content"].get("mechanism_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("mechanism_ref"), str)
    }
    relations: list[dict[str, Any]] = []
    for entry in _entries(integrated_payload, "causal_relation_hypotheses"):
        body = entry["payload"]
        source = _resolve_issue_key(body.get("from_issue_local_key"), issue_meta)
        target = _resolve_issue_key(body.get("to_issue_local_key"), issue_meta)
        if body.get("mechanism_ref") not in mechanisms:
            raise ContractError("causal relation uses a mechanism outside the Domain Pack")
        tests = _problem_tests(issue_meta[source]["problem"]) | _problem_tests(issue_meta[target]["problem"])
        if not set(body.get("distinguishing_test_refs", [])).issubset(tests):
            raise ContractError("causal relation uses a test outside its Problem Packs")
        _validate_evidence_proposals(body.get("supports_evidence_proposals", []), facts, signals, "causal relation")
        _validate_evidence_proposals(body.get("contradicts_evidence_proposals", []), facts, signals, "causal relation")
        seed = {"local_key": entry["local_key"], "payload": body}
        relations.append({
            "relation_id": make_id("relation", seed),
            "from_issue_ref": issue_meta[source]["issue_id"],
            "to_issue_ref": issue_meta[target]["issue_id"],
            "relation_type": f"{body.get('status', 'hypothesis')}:{body['mechanism_ref']}",
        })
    return sorted(relations, key=lambda item: item["relation_id"])


def _condition_template(preconditions: list[Any], disqualifiers: list[Any]) -> str:
    before = "; ".join(sorted(str(item) for item in preconditions)) or "approved evidence conditions"
    blocked = "; ".join(sorted(str(item) for item in disqualifiers)) or "no Pack disqualifier"
    return f"Proceed only when {before}; stop when {blocked}."


def _build_responses_and_monitoring(
    integrated_payload: Mapping[str, Any],
    issue_meta: Mapping[str, Mapping[str, Any]],
    deep: Mapping[str, Mapping[str, list[Mapping[str, Any]]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    responses: list[dict[str, Any]] = []
    monitoring: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()

    def add_candidate(entry: Mapping[str, Any], target: str, *, deep_candidate: bool) -> None:
        candidate_ref = str(entry["local_key"])
        if candidate_ref in seen_candidates:
            raise ContractError(f"duplicate response candidate key: {candidate_ref}")
        seen_candidates.add(candidate_ref)
        body = entry["payload"]
        problem = issue_meta[target]["problem"]
        catalog = _response_catalog(problem)
        response_ref = str(body.get("response_ref"))
        definition = catalog.get(response_ref)
        if definition is None:
            raise ContractError("response candidate is outside the Problem Pack")
        if response_ref not in issue_meta[target]["payload"].get("response_type_refs", []):
            raise ContractError("response candidate was not declared by the integrated issue")
        preconditions = list(body.get("precondition_refs", []))
        disqualifiers = list(body.get("disqualifier_refs", []))
        if not set(preconditions).issubset(set(definition.get("preconditions", []))):
            raise ContractError("response candidate uses an unauthorized precondition")
        if not set(disqualifiers).issubset(set(definition.get("disqualifiers", []))):
            raise ContractError("response candidate uses an unauthorized disqualifier")
        if not deep_candidate and not set(body.get("verification_requirement_refs", [])).issubset(_problem_tests(problem)):
            raise ContractError("response candidate uses an unauthorized verification test")
        direction = (
            str(body["action_template"])
            if deep_candidate
            else "Proceed only after the approved verification requirements are satisfied."
        )
        seed = {"candidate_ref": candidate_ref, "target": target, "response_ref": response_ref}
        response_id = make_id("response", seed)
        responses.append({
            "response_id": response_id,
            "condition_template": _condition_template(preconditions, disqualifiers),
            "direction_template": direction,
            "_candidate_ref": candidate_ref,
            "_target_issue_ref": issue_meta[target]["issue_id"],
            "_response_ref": response_ref,
        })
        if deep_candidate:
            for metric_ref in sorted(set(body.get("monitoring_metric_refs", []))):
                monitor_seed = {"response_id": response_id, "metric_ref": metric_ref}
                monitoring.append({
                    "monitor_id": make_id("monitor", monitor_seed),
                    "metric_ref": str(metric_ref),
                    "condition_template": f"Monitor {metric_ref} while this response remains conditional.",
                    "_candidate_ref": candidate_ref,
                    "_target_issue_ref": issue_meta[target]["issue_id"],
                })

    for entry in _entries(integrated_payload, "response_type_candidates"):
        target = _resolve_issue_key(entry["payload"].get("target_issue_local_key"), issue_meta)
        add_candidate(entry, target, deep_candidate=False)
    for target, fields in deep.items():
        for entry in fields["conditional_response_candidates"]:
            add_candidate(entry, target, deep_candidate=True)
    return (
        sorted(responses, key=lambda item: item["response_id"]),
        sorted(monitoring, key=lambda item: item["monitor_id"]),
    )


def _build_blind_spots(
    integrated_payload: Mapping[str, Any],
    issue_meta: Mapping[str, Mapping[str, Any]],
    deep: Mapping[str, Mapping[str, list[Mapping[str, Any]]]],
) -> list[dict[str, Any]]:
    spots: list[dict[str, Any]] = []
    for entry in _entries(integrated_payload, "blind_spots"):
        body = entry["payload"]
        spots.append({
            "blind_spot_id": make_id("blind_spot", {"local_key": entry["local_key"], "payload": body}),
            "description_template": str(body["consequence_template"]),
        })
    for target, fields in deep.items():
        for entry in fields["remaining_uncertainties"]:
            body = entry["payload"]
            spots.append({
                "blind_spot_id": make_id("blind_spot", {"local_key": entry["local_key"], "payload": body}),
                "description_template": str(body["statement_template"]),
                "_target_issue_ref": issue_meta[target]["issue_id"],
            })
        for entry in fields["additional_data_requests"]:
            body = entry["payload"]
            spots.append({
                "blind_spot_id": make_id("blind_spot", {"local_key": entry["local_key"], "payload": body}),
                "description_template": str(body["purpose_template"]),
                "_target_issue_ref": issue_meta[target]["issue_id"],
            })
    return sorted(spots, key=lambda item: item["blind_spot_id"])


def _verification_steps(
    problem: Mapping[str, Any], missing_roles: set[str], completed_test: bool,
) -> list[str]:
    steps = [f"Verify required evidence role: {role}." for role in sorted(missing_roles)]
    if not completed_test:
        steps.extend(f"Complete distinguishing test: {reference}." for reference in sorted(_problem_tests(problem)))
    return steps or ["Confirm the approved evidence conditions and unresolved counter-evidence."]


_PROFESSIONAL_PUBLICATION_PATHS = {
    "analysis/professional/findings.json",
    "analysis/professional/relations.json",
    "analysis/professional/issue-clusters.json",
    "analysis/professional/completion-assessment.json",
    "analysis/professional/grading-inputs.json",
    "analysis/professional/grade-records.json",
    "analysis/professional/execution-authority.json",
    "analysis/professional/runtime-result.json",
}


def _prepare_professional_finalization(
    files: Mapping[str, bytes],
    *,
    run_id: str,
    revision: int,
    parent_artifact_hash: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    core = _load(files, "evidence/core.json")
    if not isinstance(core, Mapping) or not isinstance(core.get("envelope"), Mapping):
        raise ContractError("Evidence Core envelope is missing")
    source_revision = core["envelope"].get("revision")
    if (
        core["envelope"].get("run_id") != run_id
        or not isinstance(source_revision, int)
        or source_revision + 1 != revision
    ):
        raise IntegrityError("professional publication revision lineage mismatch")
    publication = build_professional_publication_from_files(
        files,
        expected_run_id=run_id,
        expected_revision=source_revision,
    )
    grading_inputs = _load(
        files, "analysis/professional/grading-inputs.json"
    )
    grade_records = _load(
        files, "analysis/professional/grade-records.json"
    )
    if not isinstance(grading_inputs, list) or not isinstance(grade_records, list):
        raise ContractError("professional grading artifacts must be arrays")

    semantic_seed = {
        "previous": core["envelope"]["semantic_fingerprint"],
        "professional_publication_hash": publication["content_hash"],
        "grade_record_ids": publication["structured_output"]["grade_record_ids"],
        "evidence_link_ids": sorted(
            item["evidence_link_id"] for item in core["evidence_links"]
        ),
    }
    semantic_fingerprint = hashlib.sha256(
        canonical_bytes(semantic_seed)
    ).hexdigest()
    envelope_seed = {
        "run_id": run_id,
        "revision": revision,
        "parent_artifact_hash": parent_artifact_hash,
        "semantic_fingerprint": semantic_fingerprint,
    }
    envelope = {
        "schema_version": "1.0.0",
        "artifact_id": make_id("artifact", envelope_seed),
        "run_id": run_id,
        "revision": revision,
        "parent_artifact_hash": parent_artifact_hash,
        "stage": "finalization_jobs_ready",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "semantic_fingerprint": semantic_fingerprint,
        "artifact_hash": hashlib.sha256(canonical_bytes(envelope_seed)).hexdigest(),
    }
    advanced_core = assemble_evidence_core(
        envelope=envelope,
        mission_contract_ref=core["mission_contract_ref"],
        pack_manifest=core["pack_manifest"],
        component_manifest=core["component_manifest"],
        source_registry=core["source_registry"],
        data_quality_register=core["data_quality_register"],
        fact_register=core["fact_register"],
        signal_register=core["signal_register"],
        evidence_links=core["evidence_links"],
        capability_map=core["capability_map"],
    )
    structured = publication["structured_output"]
    updates = {
        "evidence/core.json": canonical_bytes(advanced_core),
        "final/structured-output.json": canonical_bytes(structured),
        "final/professional-publication.json": canonical_bytes(publication),
        "grading/inputs.json": canonical_bytes(grading_inputs),
        "grading/diagnostic-audit.json": canonical_bytes(
            structured["diagnostic_audit"]
        ),
    }
    for record in grade_records:
        updates[f"grading/records/{record['grade_record_id']}.json"] = canonical_bytes(
            record
        )
    return updates, {
        "grade_record_ids": structured["grade_record_ids"],
        "active_issue_count": len(structured["issues"]),
        "professional_publication_hash": publication["content_hash"],
        "effective_authority": publication["effective_authority"],
        "product_display": publication["product_display"],
    }

def prepare_finalization(
    files: Mapping[str, bytes], *, run_id: str, revision: int, parent_artifact_hash: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    professional_paths = _PROFESSIONAL_PUBLICATION_PATHS & set(files)
    if professional_paths:
        return _prepare_professional_finalization(
            files, run_id=run_id, revision=revision,
            parent_artifact_hash=parent_artifact_hash,
        )
    integrated = _load(files, "reasoning/integrated-assessment.json")
    integrated_payload = _artifact_payload(integrated, "integrated assessment")
    issues = integrated_payload.get("integrated_issues", [])
    if not isinstance(issues, list):
        raise ContractError("integrated issues must be an array")
    pack_index = _runtime_pack_index(files, issues)
    overlay = _load(files, "workflow/hitl-overlay.json", {})
    if not isinstance(overlay, Mapping):
        raise ContractError("HITL overlay must be an object")
    issue_dispositions = overlay.get("issue_dispositions", {})
    decision_dispositions = overlay.get("decision_dispositions", {})
    verification = overlay.get("verification_authorizations", {})
    if not all(isinstance(item, Mapping) for item in (issue_dispositions, decision_dispositions, verification)):
        raise ContractError("diagnostic HITL overlay sections must be objects")
    core = _load(files, "evidence/core.json")
    if not isinstance(core, Mapping):
        raise ContractError("Evidence Core must be an object")
    mission = _mission(files)
    facts = {
        str(item["fact_id"]): item for item in core.get("fact_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("fact_id"), str)
    }
    signals = {
        str(item["signal_id"]): item for item in core.get("signal_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("signal_id"), str)
    }
    links = {
        str(item["evidence_link_id"]): item for item in core.get("evidence_links", [])
        if isinstance(item, Mapping) and isinstance(item.get("evidence_link_id"), str)
    }
    authority = (
        pack_index.effective_authority
        if pack_index is not None
        else _pack_authority(_load(files, "packs/manifest.json"))
    )

    issue_meta: dict[str, dict[str, Any]] = {}
    assessment_id = integrated.get("integrated_assessment_id") if isinstance(integrated, Mapping) else None
    for item in sorted(issues, key=lambda value: str(value.get("local_key", "")) if isinstance(value, Mapping) else ""):
        if not isinstance(item, Mapping) or not isinstance(item.get("local_key"), str):
            raise ContractError("integrated issue identity is invalid")
        key = str(item["local_key"])
        if key in issue_meta:
            raise ContractError(f"duplicate integrated issue key: {key}")
        payload = item.get("payload")
        if not isinstance(payload, Mapping):
            raise ContractError(f"integrated issue payload is invalid: {key}")
        if pack_index is None:
            raise ContractError("non-empty integrated assessment requires immutable Pack snapshots")
        problem = _problem_pack(pack_index, payload.get("problem_family_ref"))
        issue_id = make_id("issue", {"assessment": assessment_id, "key": key, "payload": payload})
        issue_meta[key] = {
            "item": item, "payload": payload, "problem": problem, "issue_id": issue_id,
        }

    if pack_index is not None:
        deep = _deep_index(files, overlay, issue_meta, facts, signals, pack_index)
        relations = _build_relations(integrated_payload, issue_meta, pack_index, facts, signals)
        responses, monitoring = _build_responses_and_monitoring(integrated_payload, issue_meta, deep)
        blind_spots = _build_blind_spots(integrated_payload, issue_meta, deep)
        candidate_experts = _candidate_expert_refs(
            integrated_payload, issue_meta, deep, facts, signals,
        )
        expert_catalog = _expert_catalog(pack_index)
        context = _condition_context(core, mission, overlay)
    else:
        deep = {}
        relations, responses, monitoring, blind_spots = [], [], [], []
        candidate_experts, expert_catalog = {}, {}
        context = _condition_context(core, mission, overlay)

    responses_by_issue: dict[str, list[str]] = {key: [] for key in issue_meta}
    for response in responses:
        target_id = response["_target_issue_ref"]
        for key, meta in issue_meta.items():
            if meta["issue_id"] == target_id:
                responses_by_issue[key].append(response["response_id"])
                break
    tracked_issue_ids = {item["_target_issue_ref"] for item in monitoring}

    final_issues: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    expert_packets: list[dict[str, Any]] = []
    seen_packets: set[tuple[str, str]] = set()

    for key in sorted(issue_meta):
        meta = issue_meta[key]
        payload = meta["payload"]
        problem = meta["problem"]
        issue_id = meta["issue_id"]
        disposition = _status(issue_dispositions.get(key))
        if disposition not in {"accepted", "rejected", "disputed"}:
            raise ContractError(f"Diagnostic disposition is incomplete: {key}")
        decision = _status(decision_dispositions.get(key))
        if disposition != "rejected" and decision not in {"needed", "not_needed", "disputed"}:
            raise ContractError(f"Decision disposition is incomplete: {key}")
        authorized = bool(verification.get(key, False))
        if disposition == "disputed" and not authorized:
            raise ContractError(f"Disputed issue lacks verification authorization: {key}")

        impact_candidates = payload.get("impact_evidence_refs", [])
        counter_candidates = payload.get("counter_evidence_refs", [])
        if not isinstance(impact_candidates, list) or not isinstance(counter_candidates, list):
            raise ContractError(f"issue evidence references must be arrays: {key}")
        support_refs = sorted({
            str(reference) for reference in impact_candidates
            if reference in facts or (
                reference in signals and signals[str(reference)].get("outcome") == "triggered"
            )
        })
        counter_refs = sorted({
            str(reference) for reference in counter_candidates
            if reference in facts or reference in signals
        })
        declared_evidence = set(impact_candidates) | set(counter_candidates)
        unknown_evidence = declared_evidence - set(facts) - set(signals)
        if unknown_evidence:
            raise ContractError(f"integrated issue references unknown evidence: {sorted(unknown_evidence)}")
        if disposition != "rejected" and not support_refs:
            raise ContractError(f"accepted or disputed issue lacks material evidence: {key}")

        issue_link_ids: list[str] = []
        support_groups: list[str] = []
        for evidence_ref, polarity in [
            *((reference, "supports") for reference in support_refs),
            *((reference, "contradicts") for reference in counter_refs),
        ]:
            group_id = make_id(
                "independence",
                {"lineage_sources": sorted(_evidence_sources(evidence_ref, facts, signals))},
            )
            link = _link(issue_id, evidence_ref, polarity, group_id)
            prior = links.get(link["evidence_link_id"])
            if prior is not None and canonical_bytes(prior) != canonical_bytes(link):
                raise ContractError(f"Evidence Link collision: {link['evidence_link_id']}")
            links[link["evidence_link_id"]] = link
            issue_link_ids.append(link["evidence_link_id"])
            if polarity == "supports":
                support_groups.append(group_id)

        required_roles, problem_minimum = _problem_requirement(problem)
        evidence_roles = _observation_roles(support_refs, facts, signals)
        missing_roles = required_roles - evidence_roles
        assessability, capability_reasons, roles_met = _capability(core, missing_roles)
        impact, urgency = _bands(support_refs, signals)
        materiality: bool | str = (
            True if impact in {"critical", "high"} or urgency in {"immediate", "near_term"}
            else False if impact == "low" and urgency == "routine" else "unknown"
        )
        issue_deep = deep[key]
        completed_test = any(
            entry["payload"].get("status") == "completed"
            for entry in issue_deep["distinguishing_test_results"]
        )
        blocking = _blocking_counter_evidence(problem, context)
        counter_check = bool(
            payload.get("counter_hypothesis_refs") or issue_deep["updated_counter_hypotheses"]
        )
        expert_state, active_triggers = _expert_state(
            problem, expert_catalog, candidate_experts[key], evidence_roles, context,
        )
        response_eligibility = (
            "prohibited" if blocking else "eligible" if completed_test else "needs_verification"
        )
        runtime_issue = {
            "issue_id": issue_id,
            "impact_band": impact,
            "urgency_band": urgency,
            "mission_priority_match": _mission_priority_match(mission, payload),
            "executive_materiality": materiality,
            "expert_trigger_state": expert_state,
            "trackable": issue_id in tracked_issue_ids,
            "response_eligibility": response_eligibility,
            "provenance_refs": support_refs,
        }
        diagnostic = {
            "diagnostic_disposition": disposition,
            "decision_needed": (
                "unknown" if disposition == "disputed" or decision == "disputed"
                else True if decision == "needed" else False if decision == "not_needed" else "unknown"
            ),
            "verification_authorized": authorized,
            "issue_disposition": "standalone",
        }
        minimum_chains = max(problem_minimum, _domain_minimum(pack_index))
        grading_input = derive_grading_input(
            runtime_issue,
            capability={"assessability": assessability, "reason_codes": capability_reasons},
            evidence={
                "support_independence_groups": support_groups,
                "blocking_unresolved_contradiction": blocking,
                "minimum_independent_chains": minimum_chains,
                "valid_independent_chain_count": len(set(support_groups)),
                "required_roles_met": roles_met,
                "counter_check_met": counter_check,
                "distinguishing_test_met": completed_test,
            },
            pack_authority=authority,
            diagnostic=diagnostic,
        )
        record = grade(grading_input)
        SchemaStore().validate("grading-input.schema.json", grading_input)
        SchemaStore().validate("grade-record.schema.json", record)
        inputs.append(grading_input)
        records.append(record)
        audit.append({
            "issue_id": issue_id, "local_key": key,
            "diagnostic_disposition": disposition,
            "problem_family_ref": problem["content"]["problem_family_code"],
            "minimum_independent_chains": minimum_chains,
            "valid_independent_chain_count": len(set(support_groups)),
            "missing_evidence_roles": sorted(missing_roles),
        })

        active_refs: list[str] = []
        for trigger, trigger_state in active_triggers:
            trigger_ref = str(trigger["expert_trigger_ref"])
            active_refs.append(trigger_ref)
            packet_key = (issue_id, trigger_ref)
            if packet_key in seen_packets:
                continue
            seen_packets.add(packet_key)
            packet_seed = {"issue_id": issue_id, "trigger_ref": trigger_ref}
            expert_packets.append({
                "expert_packet_id": make_id("expert_packet", packet_seed),
                "profession": str(trigger["profession"]),
                "question_template": str(trigger["review_question_template"]),
                "forbidden_conclusions": [str(item) for item in trigger.get("prohibited_agent_conclusions", [])],
                "_trigger_ref": trigger_ref,
                "_target_issue_ref": issue_id,
                "_required": trigger_state == "required",
            })

        if record["publication_status"] == "published":
            cause_refs = set(str(item) for item in payload.get("cause_hypothesis_refs", []))
            cause_refs.update(
                str(entry["payload"]["claim_ref"])
                for entry in issue_deep["updated_cause_hypotheses"]
            )
            counter_claim_refs = set(str(item) for item in payload.get("counter_hypothesis_refs", []))
            counter_claim_refs.update(
                str(entry["payload"]["claim_ref"])
                for entry in issue_deep["updated_counter_hypotheses"]
            )
            final_issues.append({
                "issue_id": issue_id,
                "local_key": key,
                "problem_family_ref": str(problem["content"]["problem_family_code"]),
                "title_template": str(problem.get("title", problem["content"]["problem_family_code"])),
                "primary_grade": record["primary_grade"],
                "secondary_flags": record["secondary_flags"],
                "why_it_matters_template": (
                    "The approved diagnostic links this issue to verified evidence and documented counter-evidence."
                ),
                "value_refs": support_refs,
                "evidence_link_ids": sorted(set(issue_link_ids)),
                "cause_hypotheses": [{"claim_code": reference} for reference in sorted(cause_refs)],
                "counter_hypotheses": [
                    {"claim_code": reference} for reference in sorted(counter_claim_refs)
                ],
                "unresolved_conflicts": [str(item) for item in payload.get("unresolved_conflict_refs", [])],
                "verification_next_steps": _verification_steps(problem, missing_roles, completed_test),
                "conditional_response_refs": sorted(responses_by_issue[key]),
                "expert_review_refs": sorted(set(active_refs)),
                "disposition": "accepted",
            })

    semantic_seed = {
        "previous": core["envelope"]["semantic_fingerprint"],
        "grade_record_ids": [item["grade_record_id"] for item in records],
        "evidence_link_ids": sorted(links),
    }
    semantic_fingerprint = hashlib.sha256(canonical_bytes(semantic_seed)).hexdigest()
    envelope_seed = {
        "run_id": run_id, "revision": revision,
        "parent_artifact_hash": parent_artifact_hash,
        "semantic_fingerprint": semantic_fingerprint,
    }
    envelope = {
        "schema_version": "1.0.0", "artifact_id": make_id("artifact", envelope_seed),
        "run_id": run_id, "revision": revision,
        "parent_artifact_hash": parent_artifact_hash,
        "stage": "finalization_jobs_ready",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "semantic_fingerprint": semantic_fingerprint,
        "artifact_hash": hashlib.sha256(canonical_bytes(envelope_seed)).hexdigest(),
    }
    updated_core = assemble_evidence_core(
        envelope=envelope, mission_contract_ref=core["mission_contract_ref"],
        pack_manifest=core["pack_manifest"], component_manifest=core["component_manifest"],
        source_registry=core["source_registry"], data_quality_register=core["data_quality_register"],
        fact_register=core["fact_register"], signal_register=core["signal_register"],
        evidence_links=list(links.values()), capability_map=core["capability_map"],
    )
    structured = {
        "schema_version": "1.0.0",
        "issues": sorted(final_issues, key=lambda item: item["issue_id"]),
        "grade_record_ids": [item["grade_record_id"] for item in records],
        "diagnostic_audit": sorted(audit, key=lambda item: item["issue_id"]),
        "cross_issue_relations": relations,
        "conditional_responses": responses,
        "monitoring": monitoring,
        "blind_spots": blind_spots,
        "expert_review_packets": sorted(expert_packets, key=lambda item: item["expert_packet_id"]),
    }
    updates: dict[str, bytes] = {
        "evidence/core.json": canonical_bytes(updated_core),
        "final/structured-output.json": canonical_bytes(structured),
        "grading/inputs.json": canonical_bytes(inputs),
        "grading/diagnostic-audit.json": canonical_bytes(structured["diagnostic_audit"]),
    }
    for record in records:
        updates[f"grading/records/{record['grade_record_id']}.json"] = canonical_bytes(record)
    return updates, {
        "grade_record_ids": structured["grade_record_ids"],
        "active_issue_count": len(final_issues),
    }


def _reject_runtime_owned(value: Any) -> None:
    forbidden = {"primary_grade", "grade", "secondary_flags", "evidence_link_ids", "value_refs"}
    if isinstance(value, Mapping):
        overlap = forbidden & set(value)
        if overlap:
            raise ContractError(f"overlay attempts to modify runtime-owned fields: {sorted(overlap)}")
        for child in value.values():
            _reject_runtime_owned(child)
    elif isinstance(value, list):
        for child in value:
            _reject_runtime_owned(child)


def _template_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 400:
        raise ContractError(f"{label} must be a non-empty template of at most 400 characters")
    if NUMBER_LITERAL.search(value):
        raise ContractError(f"numeric literal is forbidden in {label}")
    return value


def _apply_writer(structured: dict[str, Any], files: Mapping[str, bytes]) -> None:
    if "reasoning/writer-result.json" not in files:
        return
    document = _load(files, "reasoning/writer-result.json")
    _reject_runtime_owned(document)
    payload = _artifact_payload(document, "writer result")
    if payload.get("structured_output_ref") != "final/structured-output.json":
        raise ContractError("writer result references a stale structured output")
    issue_by_id = {
        item["issue_id"]: item for item in structured.get("issues", [])
        if isinstance(item, dict) and isinstance(item.get("issue_id"), str)
    }
    packet_by_id = {
        item["expert_packet_id"]: item for item in structured.get("expert_review_packets", [])
        if isinstance(item, dict) and isinstance(item.get("expert_packet_id"), str)
    }
    seen: set[str] = set()
    templates = payload.get("claim_templates", [])
    if not isinstance(templates, list):
        raise ContractError("writer claim templates must be an array")
    for item in templates:
        if not isinstance(item, Mapping) or not isinstance(item.get("claim_id"), str):
            raise ContractError("writer claim template identity is invalid")
        claim_id = str(item["claim_id"])
        if claim_id in seen or claim_id not in issue_by_id:
            raise ContractError(f"writer references an unknown or duplicate issue: {claim_id}")
        seen.add(claim_id)
        issue_by_id[claim_id]["why_it_matters_template"] = _template_text(
            item.get("template"), "writer claim template",
        )
    seen_packets: set[str] = set()
    packet_templates = payload.get("expert_packet_templates", [])
    if not isinstance(packet_templates, list):
        raise ContractError("writer expert packet templates must be an array")
    for item in packet_templates:
        if not isinstance(item, Mapping) or not isinstance(item.get("claim_id"), str):
            raise ContractError("writer expert packet template identity is invalid")
        packet_id = str(item["claim_id"])
        if packet_id in seen_packets or packet_id not in packet_by_id:
            raise ContractError(f"writer references an unknown or duplicate expert packet: {packet_id}")
        seen_packets.add(packet_id)
        packet_by_id[packet_id]["question_template"] = _template_text(
            item.get("template"), "writer expert packet template",
        )
    order = payload.get("ceo_brief_section_order", [])
    if not isinstance(order, list) or any(not isinstance(item, str) for item in order):
        raise ContractError("writer section order must be an array of strings")


def _dispositions(
    raw: Any, expected: set[str], label: str,
) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise ContractError(f"{label} must be an object")
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise ContractError(f"{label} contains unknown references: {sorted(unknown)}")
    if missing:
        raise ContractError(f"{label} is incomplete: {sorted(missing)}")
    result: dict[str, str] = {}
    for reference in sorted(expected):
        status = _status(raw[reference])
        if status not in {"accepted", "rejected"}:
            raise ContractError(f"{label} has an invalid disposition: {reference}")
        result[reference] = status
    return result


def _public_item(item: Mapping[str, Any], *, issue: bool = False) -> dict[str, Any]:
    omitted = {"local_key", "problem_family_ref"} if issue else set()
    return {
        key: copy.deepcopy(value)
        for key, value in item.items()
        if key not in omitted and not key.startswith("_")
    }


def _verify_structured_grades(
    structured: Mapping[str, Any], files: Mapping[str, bytes],
) -> None:
    inputs = _load(files, "grading/inputs.json")
    if not isinstance(inputs, list):
        raise IntegrityError("grading inputs must be an array")
    records_by_issue: dict[str, Mapping[str, Any]] = {}
    records_by_id: dict[str, Mapping[str, Any]] = {}
    for path in sorted(files):
        if not path.startswith("grading/records/") or not path.endswith(".json"):
            continue
        record = _load(files, path)
        if not isinstance(record, Mapping):
            raise IntegrityError(f"Grade Record must be an object: {path}")
        issue_id = record.get("issue_id")
        record_id = record.get("grade_record_id")
        if not isinstance(issue_id, str) or not isinstance(record_id, str):
            raise IntegrityError(f"Grade Record identity is invalid: {path}")
        if issue_id in records_by_issue or record_id in records_by_id:
            raise IntegrityError("duplicate Grade Record identity")
        records_by_issue[issue_id] = record
        records_by_id[record_id] = record
    recomputed_ids: set[str] = set()
    for grading_input in inputs:
        if not isinstance(grading_input, Mapping):
            raise IntegrityError("grading input must be an object")
        recomputed = grade(grading_input)
        stored = records_by_issue.get(str(grading_input.get("issue_id")))
        if stored is None or canonical_bytes(stored) != canonical_bytes(recomputed):
            raise IntegrityError(f"Grade Record mismatch: {grading_input.get('issue_id')}")
        recomputed_ids.add(str(stored["grade_record_id"]))
    declared_ids = structured.get("grade_record_ids", [])
    if not isinstance(declared_ids, list) or set(declared_ids) != recomputed_ids:
        raise IntegrityError("structured output Grade Record references do not match recomputation")
    for issue in structured.get("issues", []):
        if not isinstance(issue, Mapping) or not isinstance(issue.get("issue_id"), str):
            raise IntegrityError("structured issue identity is invalid")
        record = records_by_issue.get(str(issue["issue_id"]))
        if record is None or record.get("publication_status") != "published":
            raise IntegrityError(f"structured issue lacks a published Grade Record: {issue['issue_id']}")
        if issue.get("primary_grade") != record.get("primary_grade"):
            raise IntegrityError(f"structured issue grade differs from Grade Record: {issue['issue_id']}")
        if sorted(issue.get("secondary_flags", [])) != sorted(record.get("secondary_flags", [])):
            raise IntegrityError(f"structured issue flags differ from Grade Record: {issue['issue_id']}")


def _verify_professional_publication_binding(
    files: Mapping[str, bytes],
    structured: Mapping[str, Any],
) -> None:
    path = "final/professional-publication.json"
    if path not in files:
        return
    publication = _load(files, path)
    if not isinstance(publication, Mapping):
        raise IntegrityError("professional publication must be an object")
    claimed_hash = publication.get("content_hash")
    body = {
        key: copy.deepcopy(value)
        for key, value in publication.items()
        if key != "content_hash"
    }
    if (
        not isinstance(claimed_hash, str)
        or not hmac.compare_digest(
            claimed_hash, hashlib.sha256(canonical_bytes(body)).hexdigest()
        )
    ):
        raise IntegrityError("professional publication content hash mismatch")
    if canonical_bytes(body.get("structured_output")) != canonical_bytes(structured):
        raise IntegrityError("professional publication structured output mismatch")


def build_delivery_package(
    files: Mapping[str, bytes], *, run_id: str, revision: int,
) -> dict[str, bytes]:
    loaded = _load(files, "final/structured-output.json")
    if not isinstance(loaded, Mapping):
        raise ContractError("structured output must be an object")
    structured = copy.deepcopy(dict(loaded))
    _verify_professional_publication_binding(files, structured)
    _verify_structured_grades(structured, files)
    core = _load(files, "evidence/core.json")
    if not isinstance(core, Mapping):
        raise ContractError("Evidence Core must be an object")
    mission = _mission(files)
    _apply_writer(structured, files)

    overlay = _load(files, "workflow/hitl-overlay.json", {})
    if not isinstance(overlay, Mapping):
        raise ContractError("HITL overlay must be an object")
    _reject_runtime_owned(overlay)
    issues = [item for item in structured.get("issues", []) if isinstance(item, dict)]
    issue_by_ref: dict[str, dict[str, Any]] = {}
    for issue in issues:
        issue_id = issue.get("issue_id")
        local_key = issue.get("local_key")
        if not isinstance(issue_id, str):
            raise ContractError("structured issue identity is invalid")
        issue_by_ref[issue_id] = issue
        if isinstance(local_key, str):
            if local_key in issue_by_ref:
                raise ContractError(f"duplicate structured issue reference: {local_key}")
            issue_by_ref[local_key] = issue
    wording = overlay.get("ceo_wording", {})
    if not isinstance(wording, Mapping):
        raise ContractError("CEO wording overlay must be an object")
    for reference, changes in wording.items():
        issue = issue_by_ref.get(str(reference))
        if issue is None or not isinstance(changes, Mapping):
            raise ContractError(f"CEO wording references an unknown issue: {reference}")
        unknown = set(changes) - {"title_template", "why_it_matters_template"}
        if unknown:
            raise ContractError(f"CEO wording attempts to modify forbidden fields: {sorted(unknown)}")
        for field in sorted(changes):
            issue[field] = _template_text(changes[field], f"CEO wording {field}")

    active_issue_ids = {str(item["issue_id"]) for item in issues}
    relations = [
        item for item in structured.get("cross_issue_relations", [])
        if isinstance(item, Mapping)
        and item.get("from_issue_ref") in active_issue_ids
        and item.get("to_issue_ref") in active_issue_ids
    ]
    response_candidates = [
        item for item in structured.get("conditional_responses", [])
        if isinstance(item, Mapping) and item.get("_target_issue_ref") in active_issue_ids
    ]
    response_refs = {
        str(item["_candidate_ref"]) for item in response_candidates
        if isinstance(item.get("_candidate_ref"), str)
    }
    if len(response_refs) != len(response_candidates):
        raise ContractError("structured response candidate identities are invalid or duplicated")
    response_decisions = _dispositions(
        overlay.get("response_dispositions", {}), response_refs, "response dispositions",
    )
    accepted_responses = [
        item for item in response_candidates
        if response_decisions[str(item["_candidate_ref"])] == "accepted"
    ]
    accepted_candidate_refs = {str(item["_candidate_ref"]) for item in accepted_responses}
    accepted_response_ids = {str(item["response_id"]) for item in accepted_responses}
    monitoring = [
        item for item in structured.get("monitoring", [])
        if isinstance(item, Mapping)
        and item.get("_target_issue_ref") in active_issue_ids
        and item.get("_candidate_ref") in accepted_candidate_refs
    ]

    packets = [
        item for item in structured.get("expert_review_packets", [])
        if isinstance(item, Mapping) and item.get("_target_issue_ref") in active_issue_ids
    ]
    trigger_refs = {
        str(item["_trigger_ref"]) for item in packets
        if isinstance(item.get("_trigger_ref"), str)
    }
    routing = _dispositions(
        overlay.get("expert_routing", {}), trigger_refs, "expert routing",
    )
    for item in packets:
        reference = str(item["_trigger_ref"])
        if item.get("_required") is True and routing[reference] == "rejected":
            raise ContractError(f"required expert routing cannot be rejected: {reference}")
    accepted_packets = [
        item for item in packets if routing[str(item["_trigger_ref"])] == "accepted"
    ]
    accepted_experts_by_issue: dict[str, set[str]] = {}
    for item in accepted_packets:
        accepted_experts_by_issue.setdefault(str(item["_target_issue_ref"]), set()).add(
            str(item["_trigger_ref"])
        )
    for issue in issues:
        issue["conditional_response_refs"] = sorted(
            set(issue.get("conditional_response_refs", [])) & accepted_response_ids
        )
        issue["expert_review_refs"] = sorted(
            set(issue.get("expert_review_refs", []))
            & accepted_experts_by_issue.get(str(issue["issue_id"]), set())
        )

    delivery_scope = overlay.get("delivery_scope", {})
    if not isinstance(delivery_scope, Mapping):
        raise ContractError("delivery scope must be an object")

    approvals: list[dict[str, Any]] = []
    for path in sorted(files):
        if not path.startswith("approvals/records/") or not path.endswith(".json"):
            continue
        record = _load(files, path)
        if not isinstance(record, Mapping) or record.get("status") != "current":
            continue
        if record.get("gate") == "final" and record.get("decision") not in {
            None, "approve", "approve_with_edits",
        }:
            continue
        approvals.append({
            key: record[key]
            for key in (
                "gate", "status", "input_method", "fixture_only", "approval_id",
                "actor_role", "result_artifact_ref",
            )
            if key in record
        })
    if not any(item.get("gate") == "final" for item in approvals):
        raise ContractError("a current approved interactive Final approval is required")

    capabilities = core.get("capability_map", {}).get("capabilities", [])
    capability_status = "evaluated" if capabilities and all(
        item.get("status") == "available" for item in capabilities if isinstance(item, Mapping)
    ) else "limited"
    blind_spots = [
        item for item in structured.get("blind_spots", [])
        if isinstance(item, Mapping)
        and item.get("_target_issue_ref", next(iter(active_issue_ids), None)) in active_issue_ids
    ]
    result = build_final_result(
        run_summary={"run_id": run_id, "revision": revision},
        mission_summary={
            "objective": str(mission.get("objective", mission.get("business_question", "")))
        },
        capability_summary={"status": capability_status},
        issues=[_public_item(item, issue=True) for item in issues],
        evidence_links={
            item["evidence_link_id"]: item for item in core.get("evidence_links", [])
        },
        approvals=approvals,
        cross_issue_relations=[_public_item(item) for item in relations],
        conditional_responses=[_public_item(item) for item in accepted_responses],
        monitoring=[_public_item(item) for item in monitoring],
        blind_spots=[_public_item(item) for item in blind_spots],
        expert_review_packets=[_public_item(item) for item in accepted_packets],
    )
    SchemaStore().validate("final-result.schema.json", result)
    package = render_package(result)
    revalidate_package(
        result, package,
        evidence_links={
            item["evidence_link_id"]: item for item in core.get("evidence_links", [])
        },
    )
    return package
