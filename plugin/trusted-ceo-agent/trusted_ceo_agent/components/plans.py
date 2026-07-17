from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.components.registry import (
    CONTRACTS,
    THRESHOLD_PARAMETER_KEYS,
    validate_component_parameters,
)
from trusted_ceo_agent.components.models import ComponentRunResult
from trusted_ceo_agent.components.runner import execute_component
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


_ID_PARAMETERS = frozenset(
    {
        "baseline_fact_id", "current_fact_id", "numerator_fact_id", "denominator_fact_id",
        "total_fact_id", "gap_fact_id", "earlier_fact_id", "later_fact_id",
        "observation_end_fact_id",
    }
)
_ID_LIST_PARAMETERS = frozenset({"part_fact_ids", "driver_fact_ids"})
_CODE_INPUT_COMPONENTS = frozenset(
    {"aggregate", "trend_persistence", "mix_concentration", "flow_aging"}
)
_SELECTOR_KEYS = frozenset(
    {"fact_code", "cardinality", "time_role", "scope_relation", "observation_role", "unit_code"}
)


class PlanContractError(ContractError):
    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True)
class ComponentPlanResult:
    entries: tuple[dict[str, Any], ...]
    thresholds: dict[str, dict[str, Any]]
    pack_manifest_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [dict(entry) for entry in self.entries],
            "thresholds": dict(self.thresholds),
            "pack_manifest_hash": self.pack_manifest_hash,
        }


def _plan_error(reason_code: str, message: str) -> PlanContractError:
    return PlanContractError(reason_code, message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return value
    if isinstance(value, dict):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_plain(child) for child in value]
    return value


def _load_pack_stack(files: Mapping[str, bytes], core: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_payload = files.get("packs/manifest.json")
    if manifest_payload is None:
        raise _plan_error("pack_manifest_missing", "Pack manifest is absent from the immutable revision")
    try:
        manifest = _plain(strict_loads(manifest_payload))
        SchemaStore().validate("pack-manifest.schema.json", manifest)
    except (ContractError, UnicodeError, ValueError) as error:
        raise _plan_error("pack_manifest_invalid", f"Pack manifest is invalid: {error}") from error
    body = {"schema_version": manifest["schema_version"], "packs": manifest["packs"]}
    expected_manifest_hash = _sha256(canonical_bytes(body))
    if manifest["manifest_hash"] != expected_manifest_hash:
        raise _plan_error("pack_manifest_hash_mismatch", "Pack manifest semantic hash does not match")
    core_manifest = core.get("pack_manifest", {})
    if not isinstance(core_manifest, Mapping) or core_manifest.get("pack_manifest_hash") != expected_manifest_hash:
        raise _plan_error("pack_manifest_core_mismatch", "Evidence Core uses a different Pack manifest")
    core_refs = set(core_manifest.get("pack_refs", []))

    packs: dict[str, dict[str, Any]] = {}
    schemas = SchemaStore()
    for entry in manifest["packs"]:
        digest = str(entry["pack_sha256"])
        path = f"packs/snapshots/{digest}.json"
        payload = files.get(path)
        if payload is None:
            raise _plan_error("pack_snapshot_missing", f"Pack snapshot is missing: {path}")
        if _sha256(payload) != digest:
            raise _plan_error("pack_snapshot_hash_mismatch", f"Pack snapshot hash differs: {path}")
        try:
            document = _plain(strict_loads(payload))
            schemas.validate(f"{entry['pack_type']}-pack.schema.json", document)
        except (ContractError, UnicodeError, ValueError) as error:
            raise _plan_error("pack_snapshot_invalid", f"Pack snapshot is invalid: {path}: {error}") from error
        if any(
            document.get(key) != entry[manifest_key]
            for key, manifest_key in (
                ("pack_type", "pack_type"), ("pack_id", "pack_id"), ("pack_version", "pack_version")
            )
        ):
            raise _plan_error("pack_snapshot_identity_mismatch", f"Pack snapshot identity differs: {path}")
        reference = f"{document['pack_id']}@{document['pack_version']}"
        if reference in packs:
            raise _plan_error("duplicate_pack_ref", f"Duplicate Pack reference: {reference}")
        if reference not in core_refs:
            raise _plan_error("pack_ref_not_in_core", f"Pack snapshot is not declared by Evidence Core: {reference}")
        packs[reference] = document
    return manifest, packs


def _problem_aliases(packs: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for reference, pack in sorted(packs.items()):
        if pack.get("pack_type") != "problem":
            continue
        candidates = {
            reference,
            str(pack["pack_id"]),
            str(pack["content"]["problem_family_code"]),
        }
        for candidate in candidates:
            previous = aliases.get(candidate)
            if previous is not None and previous != reference:
                raise _plan_error("ambiguous_problem_family_ref", f"Problem family alias is ambiguous: {candidate}")
            aliases[candidate] = reference
    return aliases


def _thresholds_for_problem(
    problem: Mapping[str, Any], packs: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    values: dict[str, dict[str, Any]] = {}
    domain_refs: list[str] = []
    for reference in problem["content"]["domain_pack_refs"]:
        domain = packs.get(str(reference))
        if domain is None or domain.get("pack_type") != "domain":
            raise _plan_error("problem_domain_pack_missing", f"Problem Pack Domain dependency is absent: {reference}")
        domain_refs.append(str(reference))
        for threshold in domain["content"]["threshold_definitions"]:
            threshold_id = str(threshold["threshold_id"])
            previous = values.get(threshold_id)
            plain = dict(threshold)
            if previous is not None and canonical_bytes(previous) != canonical_bytes(plain):
                raise _plan_error("ambiguous_threshold_ref", f"Threshold ref differs across Domain Packs: {threshold_id}")
            values[threshold_id] = plain
    return values, sorted(set(domain_refs))


def _selector(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != {"fact_selector"}:
        return None
    body = value["fact_selector"]
    if not isinstance(body, Mapping):
        raise _plan_error("invalid_fact_selector", "fact_selector must be an object")
    keys = set(body)
    required = {"fact_code", "cardinality", "time_role", "scope_relation"}
    if not required.issubset(keys) or keys - _SELECTOR_KEYS:
        raise _plan_error("invalid_fact_selector", f"fact_selector keys are invalid: {sorted(keys)}")
    result = {str(key): _plain(child) for key, child in body.items()}
    if not isinstance(result["fact_code"], str) or not result["fact_code"]:
        raise _plan_error("invalid_fact_selector", "fact_selector.fact_code must be a non-empty string")
    if result["cardinality"] not in {"one", "many"}:
        raise _plan_error("invalid_fact_selector", "fact_selector.cardinality must be one or many")
    if result["time_role"] not in {"all", "earliest", "previous", "latest"}:
        raise _plan_error("invalid_fact_selector", "fact_selector.time_role is invalid")
    if result["scope_relation"] not in {"any", "issue"}:
        raise _plan_error("invalid_fact_selector", "fact_selector.scope_relation is invalid")
    for optional in ("observation_role", "unit_code"):
        if optional in result and (not isinstance(result[optional], str) or not result[optional]):
            raise _plan_error("invalid_fact_selector", f"fact_selector.{optional} must be a non-empty string")
    return result


def _template_skeleton(component_id: str, template: Mapping[str, Any]) -> dict[str, Any]:
    if component_id in _CODE_INPUT_COMPONENTS and "input_fact_ids" not in template:
        raise _plan_error("invalid_parameter_template", f"{component_id} requires explicit input_fact_ids selection")
    result: dict[str, Any] = {}
    for key, value in template.items():
        selector = _selector(value)
        if key == "input_fact_ids":
            if selector is None or selector["cardinality"] != "many":
                raise _plan_error("invalid_parameter_template", "input_fact_ids requires a many fact_selector")
            continue
        if key in _ID_PARAMETERS:
            if selector is None or selector["cardinality"] != "one":
                raise _plan_error("invalid_parameter_template", f"{key} requires a one fact_selector")
            result[key] = "fact_" + "0" * 24
        elif key in _ID_LIST_PARAMETERS:
            if selector is None or selector["cardinality"] != "many":
                raise _plan_error("invalid_parameter_template", f"{key} requires a many fact_selector")
            result[key] = ["fact_" + "0" * 24]
        elif selector is not None:
            raise _plan_error("invalid_parameter_template", f"fact_selector is not allowed for {key}")
        else:
            result[str(key)] = _plain(value)
    try:
        validate_component_parameters(component_id, result)
    except ContractError as error:
        raise _plan_error("invalid_parameter_template", str(error)) from error
    if component_id in _CODE_INPUT_COMPONENTS:
        selector = _selector(template["input_fact_ids"])
        if selector is None or selector["fact_code"] != result.get("input_fact_code"):
            raise _plan_error("invalid_parameter_template", "input_fact_ids selector must match input_fact_code")
    return result


def _time_key(fact: Mapping[str, Any]) -> bytes:
    return canonical_bytes(fact.get("time_context", {}))


def _scope_matches(fact: Mapping[str, Any], issue_scope_key: str | None, relation: str) -> bool:
    if relation == "any":
        return True
    if not issue_scope_key:
        raise _plan_error("issue_scope_missing", "An issue-scoped selector requires issue.scope_key")
    if fact.get("scope_key") == issue_scope_key:
        return True
    return any(
        isinstance(item, Mapping) and item.get("member_code") == issue_scope_key
        for item in fact.get("scope", [])
    )


def _select_fact_ids(
    selector: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], *, issue_scope_key: str | None,
) -> tuple[list[str], str | None]:
    if issue_scope_key is not None and selector["scope_relation"] != "issue":
        raise _plan_error("unsafe_deep_scope_selector", "Deep-dive fact selectors must be issue-scoped")
    if issue_scope_key is None and selector["scope_relation"] != "any":
        raise _plan_error("analysis_scope_selector_invalid", "Analysis fact selectors cannot require an issue")
    selected = [
        fact for fact in facts
        if isinstance(fact, Mapping)
        and fact.get("fact_code") == selector["fact_code"]
        and _scope_matches(fact, issue_scope_key, str(selector["scope_relation"]))
        and ("observation_role" not in selector or fact.get("observation_role") == selector["observation_role"])
        and (
            "unit_code" not in selector
            or isinstance(fact.get("value"), Mapping)
            and fact["value"].get("unit_code") == selector["unit_code"]
        )
    ]
    selected.sort(key=lambda fact: (_time_key(fact), str(fact.get("fact_id", ""))))
    time_role = selector["time_role"]
    if selected and time_role != "all":
        distinct = sorted({_time_key(fact) for fact in selected})
        if time_role == "earliest":
            chosen = distinct[0]
        elif time_role == "latest":
            chosen = distinct[-1]
        else:
            if len(distinct) < 2:
                return [], "missing_input_fact"
            chosen = distinct[-2]
        selected = [fact for fact in selected if _time_key(fact) == chosen]
    identifiers = sorted({str(fact.get("fact_id", "")) for fact in selected if fact.get("fact_id")})
    if not identifiers:
        return [], "missing_input_fact"
    if selector["cardinality"] == "one" and len(identifiers) != 1:
        return identifiers, "ambiguous_input_fact"
    return identifiers, None


def _threshold_refs(
    skeleton: Mapping[str, Any], available: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    references: list[str] = []
    resolved: dict[str, dict[str, Any]] = {}
    for key in sorted(THRESHOLD_PARAMETER_KEYS & set(skeleton)):
        reference = skeleton[key]
        if not isinstance(reference, str) or reference not in available:
            raise _plan_error("missing_threshold_ref", f"Pack threshold ref is unavailable: {key}={reference!r}")
        definition = dict(available[reference])
        try:
            numeric = Decimal(str(definition.get("value")))
        except (InvalidOperation, TypeError) as error:
            raise _plan_error("invalid_threshold", f"Threshold value is invalid: {reference}") from error
        if not numeric.is_finite():
            raise _plan_error("invalid_threshold", f"Threshold value is non-finite: {reference}")
        references.append(reference)
        resolved[reference] = definition
    return references, resolved


def _materialize_step(
    *,
    step: Mapping[str, Any],
    index: int,
    facts: Sequence[Mapping[str, Any]],
    issue_ref: str | None,
    issue_scope_key: str | None,
    problem_ref: str,
    domain_refs: Sequence[str],
    available_thresholds: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    component_id = str(step.get("component_id", ""))
    if component_id not in CONTRACTS:
        raise _plan_error("unknown_component_ref", f"Problem Pack references unknown Component: {component_id}")
    template = step.get("parameter_template")
    if not isinstance(template, Mapping):
        raise _plan_error("invalid_parameter_template", f"Component template must be an object: {component_id}")
    skeleton = _template_skeleton(component_id, template)
    threshold_refs, thresholds = _threshold_refs(skeleton, available_thresholds)

    parameters: dict[str, Any] = {}
    input_ids: set[str] = set()
    reasons: set[str] = set()
    for key, value in template.items():
        selector = _selector(value)
        if selector is None:
            parameters[str(key)] = _plain(value)
            continue
        identifiers, reason = _select_fact_ids(selector, facts, issue_scope_key=issue_scope_key)
        input_ids.update(identifiers)
        if reason is not None:
            reasons.add(reason)
        if key == "input_fact_ids":
            continue
        parameters[str(key)] = identifiers[0] if selector["cardinality"] == "one" and len(identifiers) == 1 else identifiers
    parameters.pop("input_fact_ids", None)

    common = {
        "component_id": component_id,
        "component_version": CONTRACTS[component_id].version,
        "problem_pack_ref": problem_ref,
        "target_issue_ref": issue_ref,
        "pack_refs": sorted(set([*domain_refs, problem_ref])),
        "threshold_refs": threshold_refs,
        "parameter_template_hash": _sha256(canonical_bytes(_plain(template))),
        "input_fact_ids": sorted(input_ids),
        "plan_index": index,
    }
    if reasons:
        body = {
            **common,
            "status": "not_assessable",
            "parameters": {},
            "reason_codes": sorted(reasons),
        }
    else:
        try:
            validate_component_parameters(component_id, parameters)
        except ContractError as error:
            raise _plan_error("invalid_materialized_parameters", str(error)) from error
        if len(input_ids) > CONTRACTS[component_id].max_input_records:
            raise _plan_error("component_input_limit_exceeded", f"Component input limit exceeded: {component_id}")
        body = {
            **common,
            "status": "ready",
            "parameters": parameters,
            "parameter_hash": _sha256(canonical_bytes(parameters)),
            "reason_codes": [],
        }
    body["plan_entry_id"] = make_id("plan_entry", body)
    return body, thresholds


def materialize_component_plan(
    *,
    files: Mapping[str, bytes],
    core: Mapping[str, Any],
    stage: str,
    integrated_assessment: Mapping[str, Any] | None = None,
    approved_scope: Mapping[str, Any] | None = None,
    problem_family_refs: Sequence[str] = (),
) -> ComponentPlanResult:
    if stage not in {"analysis", "deep_dive"}:
        raise _plan_error("unsupported_component_stage", f"Unsupported Component plan stage: {stage}")
    manifest, packs = _load_pack_stack(files, core)
    aliases = _problem_aliases(packs)
    facts = core.get("fact_register", [])
    if not isinstance(facts, list):
        raise _plan_error("invalid_fact_register", "Evidence Core fact_register must be an array")

    targets: list[tuple[str | None, str | None, str]] = []
    allowed_components: set[str] | None = None
    if stage == "analysis":
        for supplied in sorted(set(problem_family_refs)):
            reference = aliases.get(supplied)
            if reference is None:
                raise _plan_error("unknown_problem_family_ref", f"Unknown Problem family ref: {supplied}")
            targets.append((None, None, reference))
    else:
        if not isinstance(integrated_assessment, Mapping) or not isinstance(approved_scope, Mapping):
            raise _plan_error("deep_scope_context_missing", "Deep-dive planning requires assessment and approved scope")
        issue_ids = approved_scope.get("issue_ids", [])
        component_ids = approved_scope.get("component_ids", [])
        if not isinstance(issue_ids, list) or any(not isinstance(item, str) or not item for item in issue_ids):
            raise _plan_error("invalid_approved_scope", "approved issue_ids must contain non-empty strings")
        if not isinstance(component_ids, list) or any(not isinstance(item, str) or not item for item in component_ids):
            raise _plan_error("invalid_approved_scope", "approved component_ids must contain non-empty strings")
        allowed_components = set(component_ids)
        unknown_components = allowed_components - set(CONTRACTS)
        if unknown_components:
            raise _plan_error("unknown_component_ref", f"Approved scope has unknown Components: {sorted(unknown_components)}")
        issues = integrated_assessment.get("payload", {}).get("integrated_issues", [])
        if not isinstance(issues, list):
            raise _plan_error("invalid_integrated_assessment", "integrated_issues must be an array")
        by_key: dict[str, Mapping[str, Any]] = {}
        for item in issues:
            if not isinstance(item, Mapping) or not isinstance(item.get("local_key"), str) or not isinstance(item.get("payload"), Mapping):
                raise _plan_error("invalid_integrated_assessment", "integrated issue shape is invalid")
            key = str(item["local_key"])
            if key in by_key:
                raise _plan_error("duplicate_integrated_issue", f"Duplicate integrated issue: {key}")
            by_key[key] = item["payload"]
        for issue_id in sorted(set(issue_ids)):
            payload = by_key.get(issue_id)
            if payload is None:
                raise _plan_error("unapproved_issue_ref", f"Approved issue does not exist: {issue_id}")
            supplied_family = payload.get("problem_family_ref")
            reference = aliases.get(str(supplied_family))
            if reference is None:
                raise _plan_error("unknown_problem_family_ref", f"Issue uses unknown Problem family: {supplied_family}")
            scope_key = payload.get("scope_key")
            if not isinstance(scope_key, str) or not scope_key:
                raise _plan_error("issue_scope_missing", f"Issue scope_key is missing: {issue_id}")
            targets.append((issue_id, scope_key, reference))
        if allowed_components and not targets:
            raise _plan_error("component_scope_has_no_issue", "Approved Components require at least one approved issue")

    entries: list[dict[str, Any]] = []
    used_components: set[str] = set()
    resolved_thresholds: dict[str, dict[str, Any]] = {}
    for issue_ref, issue_scope_key, problem_ref in sorted(targets, key=lambda item: (item[2], item[0] or "")):
        problem = packs[problem_ref]
        available_thresholds, domain_refs = _thresholds_for_problem(problem, packs)
        plan_name = "analysis_plan" if stage == "analysis" else "deep_dive_plan"
        for index, step in enumerate(problem["content"][plan_name]):
            component_id = str(step.get("component_id", ""))
            if allowed_components is not None and component_id not in allowed_components:
                continue
            entry, thresholds = _materialize_step(
                step=step,
                index=index,
                facts=facts,
                issue_ref=issue_ref,
                issue_scope_key=issue_scope_key,
                problem_ref=problem_ref,
                domain_refs=domain_refs,
                available_thresholds=available_thresholds,
            )
            used_components.add(component_id)
            entries.append(entry)
            for reference, definition in thresholds.items():
                previous = resolved_thresholds.get(reference)
                if previous is not None and canonical_bytes(previous) != canonical_bytes(definition):
                    raise _plan_error("ambiguous_threshold_ref", f"Resolved threshold differs: {reference}")
                resolved_thresholds[reference] = definition
    if allowed_components is not None:
        absent = allowed_components - used_components
        if absent:
            raise _plan_error("component_not_in_problem_plan", f"Approved Component is not in selected Problem plans: {sorted(absent)}")
    entries.sort(key=lambda item: (str(item["problem_pack_ref"]), str(item.get("target_issue_ref") or ""), int(item["plan_index"]), str(item["plan_entry_id"])))
    return ComponentPlanResult(tuple(entries), dict(sorted(resolved_thresholds.items())), str(manifest["manifest_hash"]))


def _not_assessable_run(entry: Mapping[str, Any], input_artifact_hash: str) -> ComponentRunResult:
    component_id = str(entry["component_id"])
    parameter_hash = str(entry["parameter_template_hash"])
    input_ids = tuple(sorted(set(str(item) for item in entry.get("input_fact_ids", []))))
    pack_refs = tuple(sorted(set(str(item) for item in entry.get("pack_refs", []))))
    run_body = {
        "component_id": component_id,
        "component_version": str(entry["component_version"]),
        "input_artifact_hash": input_artifact_hash,
        "sorted_input_fact_ids": list(input_ids),
        "parameter_hash": parameter_hash,
        "pack_refs": list(pack_refs),
    }
    return ComponentRunResult(
        component_run_id=make_id("component_run", run_body),
        component_id=component_id,
        component_version=str(entry["component_version"]),
        input_artifact_hash=input_artifact_hash,
        sorted_input_fact_ids=input_ids,
        parameter_hash=parameter_hash,
        pack_refs=pack_refs,
        output_facts=(),
        output_signals=(),
        status="not_assessable",
        reason_codes=tuple(sorted(set(str(item) for item in entry.get("reason_codes", [])))),
    )


def execute_materialized_plan(
    plan: ComponentPlanResult,
    facts: Sequence[Mapping[str, Any]],
    *,
    input_artifact_hash: str,
    max_workers: int = 1,
) -> tuple[ComponentRunResult, ...]:
    if max_workers not in {1, 2, 3, 4}:
        raise ValueError("component workers must be between 1 and 4")
    by_id: dict[str, Mapping[str, Any]] = {}
    for fact in facts:
        identifier = fact.get("fact_id")
        if not isinstance(identifier, str) or not identifier:
            raise _plan_error("invalid_fact_register", "Fact selected for execution has no fact_id")
        if identifier in by_id:
            raise _plan_error("duplicate_fact_id", f"Evidence Core has duplicate Fact ID: {identifier}")
        by_id[identifier] = fact

    def run(entry: Mapping[str, Any]) -> ComponentRunResult:
        status = entry.get("status")
        if status == "not_assessable":
            return _not_assessable_run(entry, input_artifact_hash)
        if status != "ready":
            raise _plan_error("invalid_plan_entry_status", f"Unsupported plan entry status: {status}")
        identifiers = [str(item) for item in entry.get("input_fact_ids", [])]
        missing = sorted(set(identifiers) - set(by_id))
        if missing:
            raise _plan_error("bound_fact_missing", f"Bound Facts are absent from Evidence Core: {missing}")
        selected = tuple(by_id[identifier] for identifier in sorted(set(identifiers)))
        return execute_component(
            str(entry["component_id"]),
            selected,
            entry.get("parameters", {}),
            thresholds=plan.thresholds,
            pack_refs=entry.get("pack_refs", []),
            input_artifact_hash=input_artifact_hash,
        )

    ordered = sorted(plan.entries, key=lambda entry: str(entry["plan_entry_id"]))
    if max_workers == 1:
        runs = [run(entry) for entry in ordered]
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="trusted-ceo-bound-component") as pool:
            runs = list(pool.map(run, ordered))
    return tuple(sorted(runs, key=lambda item: item.component_run_id))


def inspect_pack_component_contracts(
    *, files: Mapping[str, bytes], core: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Inspect every immutable Problem Pack step without weakening runtime fail-closed behavior."""
    _, packs = _load_pack_stack(files, core)
    report: list[dict[str, Any]] = []
    for problem_ref, problem in sorted(packs.items()):
        if problem.get("pack_type") != "problem":
            continue
        available_thresholds, _ = _thresholds_for_problem(problem, packs)
        for stage, plan_name in (("analysis", "analysis_plan"), ("deep_dive", "deep_dive_plan")):
            for index, step in enumerate(problem["content"][plan_name]):
                component_id = str(step.get("component_id", ""))
                base = {
                    "problem_pack_ref": problem_ref,
                    "stage": stage,
                    "plan_index": index,
                    "component_id": component_id,
                }
                try:
                    if component_id not in CONTRACTS:
                        raise _plan_error("unknown_component_ref", f"Unknown Component: {component_id}")
                    template = step.get("parameter_template")
                    if not isinstance(template, Mapping):
                        raise _plan_error("invalid_parameter_template", "parameter_template must be an object")
                    skeleton = _template_skeleton(component_id, template)
                    threshold_refs, _ = _threshold_refs(skeleton, available_thresholds)
                except PlanContractError as error:
                    report.append({
                        **base,
                        "status": "invalid",
                        "reason_code": error.reason_code,
                        "message": str(error),
                        "threshold_refs": [],
                    })
                else:
                    report.append({
                        **base,
                        "status": "ready",
                        "reason_code": None,
                        "message": "",
                        "threshold_refs": threshold_refs,
                    })
    return tuple(sorted(
        report,
        key=lambda item: (
            str(item["problem_pack_ref"]), str(item["stage"]),
            int(item["plan_index"]), str(item["component_id"]),
        ),
    ))


__all__ = [
    "ComponentPlanResult",
    "PlanContractError",
    "execute_materialized_plan",
    "inspect_pack_component_contracts",
    "materialize_component_plan",
]
