from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from trusted_ceo_agent.analysis.economic_events import materialize_economic_event
from trusted_ceo_agent.analysis.findings import (
    build_finding,
    build_finding_relation,
    build_issue_cluster,
)
from trusted_ceo_agent.analysis.integrator import (
    freeze_finding_join_manifest,
    integrate_cross_domain,
)
from trusted_ceo_agent.analysis.signal_queue import (
    FINDING_DISPOSITIONS,
    SignalCaseQueue,
    materialize_signal_cases,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.orchestration.budget import verify_work_budget_policy
from trusted_ceo_agent.orchestration.graph import (
    FAILURE_CODES,
    compile_work_graph,
    work_idempotency_key,
)
from trusted_ceo_agent.orchestration.scheduler import WorkScheduler
from trusted_ceo_agent.routing.domain_router import route_economic_event
from trusted_ceo_agent.workflow.completion import (
    assess_completion,
    assess_completion_from_artifacts,
)


TaskExecutor = Callable[[dict[str, Any]], Mapping[str, Any]]

_CASE_PLAN_FIELDS = frozenset({
    "case_key",
    "signal_ids",
    "required_domain_routes",
    "optional_domain_routes",
    "related_case_keys",
    "priority_dimensions",
})
_WORK_PLAN_FIELDS = frozenset({
    "local_key",
    "signal_id",
    "domain",
    "issue_family",
    "procedure_refs",
    "dependency_keys",
    "required",
    "packet_ref",
    "packet_hash",
    "pack_release_id",
    "timeout_policy",
})
_EXECUTOR_RESULT_FIELDS = frozenset({
    "status",
    "findings",
    "expert_packet_refs",
})
_FINDING_ENTRY_FIELDS = frozenset({
    "finding_key",
    "assessment_domains",
    "spec",
})
_RUNTIME_FINDING_FIELDS = frozenset({
    "run_id",
    "revision",
    "case_id",
    "event_id",
    "signal_ids",
    "domain_assessment_refs",
})
_RELATION_PLAN_FIELDS = frozenset({
    "relation_key",
    "source_finding_key",
    "target_finding_key",
    "relation_type",
    "evidence_refs",
    "confidence_status",
    "contradicting_evidence_refs",
})
_CLUSTER_PLAN_FIELDS = frozenset({
    "cluster_key",
    "finding_keys",
    "relation_keys",
    "decision_unit",
    "unresolved_conflicts",
})
_BOUNDARY_ROUTE_STATUSES = frozenset({
    "unsupported_pack",
    "not_assessable",
    "expert_review_required",
})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(
            f"{label} fields are invalid: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _string_set(value: Any, label: str, *, non_empty: bool = False) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ContractError(f"{label} must be an array")
    values = [_text(item, label) for item in value]
    normalized = sorted(set(values))
    if len(values) != len(normalized):
        raise ContractError(f"{label} contains duplicates")
    if non_empty and not normalized:
        raise ContractError(f"{label} cannot be empty")
    return normalized


class TaskExecutionFailure(Exception):
    """Declared Pack failure, eligible only for the scheduler's frozen policy."""

    def __init__(self, failure_code: str) -> None:
        if failure_code not in FAILURE_CODES:
            raise ContractError(f"unknown task execution failure code: {failure_code}")
        super().__init__(failure_code)
        self.failure_code = failure_code


class _ResultCAS:
    def __init__(self) -> None:
        self._by_hash: dict[str, dict[str, Any]] = {}
        self._by_task: dict[str, dict[str, Any]] = {}

    def put(self, task_id: str, payload: Mapping[str, Any]) -> tuple[str, bytes]:
        record = copy.deepcopy(dict(payload))
        encoded = canonical_bytes(record)
        result_hash = hashlib.sha256(encoded).hexdigest()
        result_ref = f"cas/results/{result_hash}.json"
        entry = {
            "result_ref": result_ref,
            "result_hash": result_hash,
            "payload": record,
        }
        prior = self._by_hash.get(result_hash)
        if prior is not None and canonical_bytes(prior) != canonical_bytes(entry):
            raise ContractError("content-addressed task result collision")
        existing = self._by_task.get(task_id)
        if existing is not None and canonical_bytes(existing) != canonical_bytes(entry):
            raise ContractError("task produced conflicting deterministic results")
        self._by_hash[result_hash] = entry
        self._by_task[task_id] = entry
        return result_ref, encoded

    def records(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._by_hash[key]) for key in sorted(self._by_hash)]


def _assessment_id(route: Mapping[str, Any]) -> str:
    return "assessment_" + _digest({
        "route_id": route["route_id"],
        "event_id": route["event_id"],
        "revision": route["base_revision"],
    })[:24]


def _assessment(
    route: Mapping[str, Any],
    finding_ids: Sequence[str],
    additional_data_refs: Sequence[str],
) -> dict[str, Any]:
    body = {
        "assessment_id": _assessment_id(route),
        "route_id": route["route_id"],
        "event_id": route["event_id"],
        "domain": route["domain"],
        "revision": route["base_revision"],
        "status": route["status"],
        "authority": route["effective_authority"],
        "finding_ids": sorted(set(finding_ids)),
        "additional_data_refs": sorted(set(additional_data_refs)),
        "expert_role": route["expert_role"],
    }
    return {**body, "content_hash": _digest(body)}


def _case_specs(
    case_plans: Sequence[Mapping[str, Any]],
    event_id: str,
) -> list[dict[str, Any]]:
    if not case_plans:
        raise ContractError("Professional runtime requires Signal Case plans")
    result: list[dict[str, Any]] = []
    for raw in case_plans:
        if not isinstance(raw, Mapping):
            raise ContractError("Signal Case plan must be an object")
        _exact_fields(raw, _CASE_PLAN_FIELDS, "Signal Case plan")
        result.append({**copy.deepcopy(dict(raw)), "event_id": event_id})
    return result


def _case_for_signal(
    signal_id: str,
    cases: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    matches = [case for case in cases if signal_id in set(case["signal_ids"])]
    if len(matches) != 1:
        raise ContractError(
            f"work plan signal must select exactly one Signal Case: {signal_id}"
        )
    return matches[0]


def _work_specs_by_case(
    work_plans: Sequence[Mapping[str, Any]],
    *,
    cases: Sequence[Mapping[str, Any]],
    event_id: str,
    routes: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    if not work_plans:
        raise ContractError("Professional runtime requires Work Item plans")
    route_by_domain = {str(route["domain"]): route for route in routes}
    local_keys: set[str] = set()
    result: dict[str, list[dict[str, Any]]] = {
        str(case["case_id"]): [] for case in cases
    }
    for raw in work_plans:
        if not isinstance(raw, Mapping):
            raise ContractError("Work Item plan must be an object")
        _exact_fields(raw, _WORK_PLAN_FIELDS, "Work Item plan")
        local_key = _text(raw["local_key"], "work plan local_key")
        if local_key in local_keys:
            raise ContractError(f"duplicate runtime Work Item local_key: {local_key}")
        local_keys.add(local_key)
        signal_id = _text(raw["signal_id"], "work plan signal_id")
        case = _case_for_signal(signal_id, cases)
        domain = _text(raw["domain"], "work plan domain")
        route = route_by_domain.get(domain)
        if route is None or route["status"] != "deep_review_pending":
            raise ContractError(
                f"Work Item cannot execute without a selected Pack route: {domain}"
            )
        spec = {
            key: copy.deepcopy(value)
            for key, value in raw.items()
            if key != "signal_id"
        }
        spec.update({
            "signal_case_id": case["case_id"],
            "event_id": event_id,
        })
        result[str(case["case_id"])].append(spec)
    for case_id, specs in result.items():
        if not specs:
            raise ContractError(f"Signal Case lacks Work Item plans: {case_id}")
        own_keys = {str(spec["local_key"]) for spec in specs}
        for spec in specs:
            dangling = set(spec["dependency_keys"]) - own_keys
            if dangling:
                raise ContractError(
                    f"cross-case or dangling Work dependencies: {sorted(dangling)}"
                )
    return result


def _task_result(
    raw: Mapping[str, Any],
    *,
    task_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractError("task executor result must be an object")
    _exact_fields(raw, _EXECUTOR_RESULT_FIELDS, "task executor result")
    status = raw["status"]
    if status not in {"succeeded", "expert_review_required", "not_assessable"}:
        raise ContractError(f"task executor status is invalid: {status}")
    findings = raw["findings"]
    if not isinstance(findings, Sequence) or isinstance(
        findings, (str, bytes, bytearray)
    ):
        raise ContractError("task executor findings must be an array")
    normalized_findings: list[dict[str, Any]] = []
    keys: set[str] = set()
    for item in findings:
        if not isinstance(item, Mapping):
            raise ContractError("task executor Finding entry must be an object")
        _exact_fields(item, _FINDING_ENTRY_FIELDS, "task executor Finding entry")
        key = _text(item["finding_key"], "finding_key")
        if key in keys:
            raise ContractError(f"duplicate task Finding key: {key}")
        keys.add(key)
        domains = _string_set(
            item["assessment_domains"],
            "assessment_domains",
            non_empty=True,
        )
        spec = item["spec"]
        if not isinstance(spec, Mapping):
            raise ContractError("task Finding spec must be an object")
        forbidden = set(spec) & _RUNTIME_FINDING_FIELDS
        if forbidden:
            raise ContractError(
                f"Pack executor may not set runtime Finding lineage: {sorted(forbidden)}"
            )
        normalized_findings.append({
            "finding_key": key,
            "assessment_domains": domains,
            "spec": copy.deepcopy(dict(spec)),
        })
    body = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "work_idempotency_key": idempotency_key,
        "producer": "approved_pack_procedure",
        "status": status,
        "findings": sorted(
            normalized_findings,
            key=lambda item: item["finding_key"],
        ),
        "expert_packet_refs": _string_set(
            raw["expert_packet_refs"],
            "expert_packet_refs",
        ),
    }
    record = {**body, "content_hash": _digest(body)}
    SchemaStore().validate("professional-task-result.schema.json", record)
    return record


def _completion_input(
    *,
    run_id: str,
    revision: int,
    cases: Sequence[Mapping[str, Any]],
    work_items: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    findings: Sequence[Mapping[str, Any]],
    coverage_gaps: Sequence[str],
    expert_review_refs: Sequence[str],
    contract_failure_refs: Sequence[str],
    limited_basis: str,
    user_confirmed_limitations: bool,
    final_validator_passed: bool,
    tty_final_approval_ready: bool,
    integrated: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "signal_cases": [copy.deepcopy(dict(item)) for item in cases],
        "work_items": [copy.deepcopy(dict(item)) for item in work_items],
        "domain_routes": [copy.deepcopy(dict(item)) for item in routes],
        "findings": [copy.deepcopy(dict(item)) for item in findings],
        "integrity_failure_refs": [],
        "contract_failure_refs": sorted(set(contract_failure_refs)),
        "stale_revision_refs": [],
        "coverage_gaps": sorted(set(coverage_gaps)),
        "expert_review_refs": sorted(set(expert_review_refs)),
        "blind_spot_refs": sorted(set(coverage_gaps)),
        "limited_basis": limited_basis,
        "user_confirmed_limitations": user_confirmed_limitations,
        "cross_finding_join_complete": integrated,
        "cross_domain_integrator_complete": integrated,
        "duplicate_merge_complete": integrated,
        "conflicts_disclosed": integrated,
        "coverage_complete": integrated,
        "final_validator_passed": final_validator_passed,
        "tty_final_approval_ready": tty_final_approval_ready,
    }


class ProfessionalAnalysisRuntime:
    """Deterministic, fail-closed vertical runtime over approved contracts."""

    def run(
        self,
        *,
        run_id: str,
        revision: int,
        evidence_core: Mapping[str, Any],
        expected_evidence_core_hash: str,
        event_type: str,
        field_fact_refs: Mapping[str, Sequence[str]],
        registered_domains: Sequence[str],
        candidate_sets: Mapping[str, Sequence[Mapping[str, Any]]],
        screen_results: Sequence[Mapping[str, Any]],
        pack_manifest: Mapping[str, Any],
        pack_catalog: Sequence[Mapping[str, Any]],
        jurisdiction: str,
        effective_at: str,
        signals: Sequence[Mapping[str, Any]],
        case_plans: Sequence[Mapping[str, Any]],
        work_plans: Sequence[Mapping[str, Any]],
        priority_policy_ref: str,
        policy: Mapping[str, Any],
        policy_release_id: str,
        concurrency_profile_id: str,
        task_executor: TaskExecutor,
        relation_plans: Sequence[Mapping[str, Any]],
        cluster_plans: Sequence[Mapping[str, Any]],
        boundary_packet_refs: Mapping[str, Sequence[str]],
        limited_basis: str,
        user_confirmed_limitations: bool,
        final_validator_passed: bool,
        tty_final_approval_ready: bool,
        worker_id: str = "professional-analysis-runtime",
        integrator_writer_id: str = "professional-analysis-integrator",
    ) -> dict[str, Any]:
        if not callable(task_executor):
            raise ContractError("task_executor must be callable")
        run_id = _text(run_id, "run_id")
        if not run_id.startswith("run_"):
            raise ContractError("run_id must begin with run_")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ContractError("revision must be a positive integer")
        verify_work_budget_policy(policy)
        if int(policy["max_active_signal_cases"]) != 1:
            raise ContractError("Professional runtime requires one active Signal Case")
        if policy["approved_concurrency_profile_id"] != concurrency_profile_id:
            raise ContractError("runtime concurrency profile differs from WorkBudgetPolicy")

        event = materialize_economic_event(
            evidence_core=evidence_core,
            expected_revision=revision,
            expected_artifact_hash=expected_evidence_core_hash,
            event_type=event_type,
            field_fact_refs=field_fact_refs,
        )
        routes = list(route_economic_event(
            event=event,
            expected_revision=revision,
            expected_event_hash=event["integrity"]["payload_hash"],
            registered_domains=registered_domains,
            candidate_sets=candidate_sets,
            screen_results=screen_results,
            pack_manifest=pack_manifest,
            pack_catalog=pack_catalog,
            jurisdiction=jurisdiction,
            effective_at=effective_at,
        ))
        routing_decisions = copy.deepcopy(routes)
        cases, priorities = materialize_signal_cases(
            run_id=run_id,
            base_revision=revision,
            signals=signals,
            case_specs=_case_specs(case_plans, str(event["event_id"])),
            priority_policy_ref=priority_policy_ref,
        )
        queue = SignalCaseQueue(cases, priorities)
        specs_by_case = _work_specs_by_case(
            work_plans,
            cases=cases,
            event_id=str(event["event_id"]),
            routes=routes,
        )
        route_by_domain = {str(route["domain"]): route for route in routes}
        original_case_by_id = {str(case["case_id"]): case for case in cases}
        cas = _ResultCAS()
        graphs: list[dict[str, Any]] = []
        final_work_items: list[dict[str, Any]] = []
        finding_by_key: dict[str, dict[str, Any]] = {}
        all_findings: list[dict[str, Any]] = []
        failure_refs: list[str] = []
        clock = 0
        lease_sequence = 0

        while True:
            case = queue.lease(
                worker_id,
                expected_revision=queue.revision,
                idempotency_key=f"runtime-case-lease-{lease_sequence}",
            )
            lease_sequence += 1
            if case is None:
                break
            case_id = str(case["case_id"])
            graph, work_items = compile_work_graph(
                run_id=run_id,
                base_revision=revision,
                signal_case_ids=[case_id],
                work_item_specs=specs_by_case[case_id],
                policy_release_id=policy_release_id,
                concurrency_profile_id=concurrency_profile_id,
            )
            scheduler = WorkScheduler(graph, work_items, policy)
            task_records: list[dict[str, Any]] = []
            while True:
                leased = scheduler.lease(worker_id, now=clock)
                clock += 1
                if leased is None:
                    break
                running = scheduler.start(str(leased["task_id"]), worker_id)
                route = route_by_domain[str(running["domain"])]
                matching_specs = [
                    spec
                    for spec in specs_by_case[case_id]
                    if all(
                        spec[field] == running[field]
                        for field in (
                            "domain",
                            "issue_family",
                            "packet_ref",
                            "pack_release_id",
                        )
                    )
                ]
                if len(matching_specs) != 1:
                    raise ContractError(
                        "running Work Item does not bind to one work plan key"
                    )
                request = {
                    "work_plan_key": matching_specs[0]["local_key"],
                    "event": copy.deepcopy(event),
                    "domain_route": copy.deepcopy(route),
                    "signal_case": copy.deepcopy(original_case_by_id[case_id]),
                    "work_item": copy.deepcopy(running),
                    "work_idempotency_key": work_idempotency_key(running),
                }
                try:
                    raw_result = task_executor(request)
                    record = _task_result(
                        raw_result,
                        task_id=str(running["task_id"]),
                        idempotency_key=str(request["work_idempotency_key"]),
                    )
                except TaskExecutionFailure as error:
                    failed = scheduler.fail(
                        str(running["task_id"]),
                        worker_id,
                        failure_code=error.failure_code,
                        active_created_from_hash=graph["created_from_hash"],
                    )
                    if failed["status"] not in {"ready", "succeeded"}:
                        failure_refs.append(
                            f"{failed['task_id']}:{failed['failure_code']}"
                        )
                    continue
                result_ref, result_payload = cas.put(str(running["task_id"]), record)
                scheduler.complete(
                    str(running["task_id"]),
                    worker_id,
                    result_ref=result_ref,
                    result_payload=result_payload,
                    active_created_from_hash=graph["created_from_hash"],
                )
                task_records.append(record)

            graph = scheduler.graph_snapshot()
            current_items = scheduler.work_items()
            graphs.append(graph)
            final_work_items.extend(current_items)
            required_blocked = any(
                item["required"] and item["status"] != "succeeded"
                for item in current_items
            )
            if required_blocked:
                queue.pause(
                    case_id,
                    worker_id,
                    status="needs_expert",
                    reason="required Work Item did not produce a verified result",
                    expected_revision=queue.revision,
                    idempotency_key=f"runtime-case-pause-{case_id}",
                )
                continue

            entries = [
                (record, entry)
                for record in sorted(task_records, key=lambda item: item["task_id"])
                for entry in record["findings"]
            ]
            if len(entries) != 1:
                failure_refs.append(f"{case_id}:finding_cardinality")
                queue.pause(
                    case_id,
                    worker_id,
                    status="needs_expert",
                    reason="Signal Case must yield exactly one verified Finding",
                    expected_revision=queue.revision,
                    idempotency_key=f"runtime-case-pause-finding-{case_id}",
                )
                continue
            record, entry = entries[0]
            finding_key = str(entry["finding_key"])
            if finding_key in finding_by_key:
                raise ContractError(f"duplicate runtime Finding key: {finding_key}")
            assessment_domains = set(entry["assessment_domains"])
            producing_domain = str(next(
                item["domain"]
                for item in current_items
                if item["task_id"] == record["task_id"]
            ))
            if producing_domain not in assessment_domains:
                raise ContractError("Finding must include its producing domain assessment")
            unknown_domains = assessment_domains - set(route_by_domain)
            if unknown_domains:
                raise ContractError(
                    f"Finding uses unknown assessment domains: {sorted(unknown_domains)}"
                )
            structural = {
                "run_id": run_id,
                "revision": revision,
                "case_id": case_id,
                "event_id": event["event_id"],
                "signal_ids": list(case["signal_ids"]),
                "domain_assessment_refs": sorted(
                    _assessment_id(route_by_domain[domain])
                    for domain in assessment_domains
                ),
            }
            finding = build_finding({**copy.deepcopy(entry["spec"]), **structural})
            finding_by_key[finding_key] = finding
            all_findings.append(finding)
            for next_stage in (3, 4, 5):
                queue.advance(
                    case_id,
                    worker_id,
                    next_stage=next_stage,
                    expected_revision=queue.revision,
                    idempotency_key=f"runtime-case-stage-{case_id}-{next_stage}",
                )
            queue.complete(
                case_id,
                worker_id,
                disposition=str(finding["disposition"]),
                finding_ref=(
                    str(finding["finding_id"])
                    if finding["disposition"] in FINDING_DISPOSITIONS
                    else None
                ),
                reason="verified Pack result completed the Signal Case",
                expected_revision=queue.revision,
                idempotency_key=f"runtime-case-complete-{case_id}",
            )

        graphs.sort(key=lambda item: item["graph_id"])
        final_work_items.sort(key=lambda item: item["task_id"])
        all_findings.sort(key=lambda item: item["finding_id"])
        current_cases = list(queue.cases())
        hard_blocked = bool(failure_refs) or any(
            item["required"] and item["status"] != "succeeded"
            for item in final_work_items
        )

        successful_domains = {
            str(item["domain"])
            for item in final_work_items
            if item["status"] == "succeeded"
        }
        blocked_domains = {
            str(item["domain"])
            for item in final_work_items
            if item["required"] and item["status"] != "succeeded"
        }
        terminal_routes: list[dict[str, Any]] = []
        for source_route in routes:
            route = copy.deepcopy(source_route)
            domain = str(route["domain"])
            if (
                route["status"] == "deep_review_pending"
                and domain in successful_domains
                and domain not in blocked_domains
            ):
                route["status"] = "completed"
                route["integrity"]["payload_hash"] = _digest({
                    key: value for key, value in route.items() if key != "integrity"
                })
            terminal_routes.append(route)
        routes = terminal_routes
        route_by_domain = {str(route["domain"]): route for route in routes}

        domain_assessments: list[dict[str, Any]] = []
        boundary_missing: list[str] = []
        for route in routes:
            domain = str(route["domain"])
            owned = [
                finding["finding_id"]
                for finding in all_findings
                if _assessment_id(route) in finding["domain_assessment_refs"]
            ]
            packet_refs = _string_set(
                boundary_packet_refs.get(domain, []),
                f"boundary_packet_refs.{domain}",
            )
            if route["status"] in _BOUNDARY_ROUTE_STATUSES and not packet_refs:
                boundary_missing.append(f"boundary_packet_missing:{domain}")
            domain_assessments.append(_assessment(route, owned, packet_refs))
        domain_assessments.sort(key=lambda item: item["domain"])
        failure_refs.extend(boundary_missing)
        hard_blocked = hard_blocked or bool(boundary_missing)

        relation_by_key: dict[str, dict[str, Any]] = {}
        relations: list[dict[str, Any]] = []
        for raw in sorted(
            relation_plans if not hard_blocked else (),
            key=lambda item: str(item.get("relation_key", "")),
        ):
            if not isinstance(raw, Mapping):
                raise ContractError("relation plan must be an object")
            _exact_fields(raw, _RELATION_PLAN_FIELDS, "relation plan")
            key = _text(raw["relation_key"], "relation_key")
            if key in relation_by_key:
                raise ContractError(f"duplicate relation key: {key}")
            source_key = _text(raw["source_finding_key"], "source_finding_key")
            target_key = _text(raw["target_finding_key"], "target_finding_key")
            if source_key not in finding_by_key or target_key not in finding_by_key:
                raise ContractError("relation plan has a dangling Finding key")
            relation = build_finding_relation({
                "run_id": run_id,
                "revision": revision,
                "source_finding_id": finding_by_key[source_key]["finding_id"],
                "target_finding_id": finding_by_key[target_key]["finding_id"],
                "relation_type": raw["relation_type"],
                "evidence_refs": raw["evidence_refs"],
                "confidence_status": raw["confidence_status"],
                "contradicting_evidence_refs": raw["contradicting_evidence_refs"],
            }, all_findings)
            relation_by_key[key] = relation
            relations.append(relation)

        clusters: list[dict[str, Any]] = []
        cluster_keys: set[str] = set()
        for raw in sorted(
            cluster_plans if not hard_blocked else (),
            key=lambda item: str(item.get("cluster_key", "")),
        ):
            if not isinstance(raw, Mapping):
                raise ContractError("cluster plan must be an object")
            _exact_fields(raw, _CLUSTER_PLAN_FIELDS, "cluster plan")
            key = _text(raw["cluster_key"], "cluster_key")
            if key in cluster_keys:
                raise ContractError(f"duplicate cluster key: {key}")
            cluster_keys.add(key)
            finding_keys = _string_set(
                raw["finding_keys"], "cluster finding_keys", non_empty=True
            )
            relation_keys = _string_set(raw["relation_keys"], "cluster relation_keys")
            if not set(finding_keys).issubset(finding_by_key):
                raise ContractError("cluster plan has a dangling Finding key")
            if not set(relation_keys).issubset(relation_by_key):
                raise ContractError("cluster plan has a dangling relation key")
            clusters.append(build_issue_cluster(
                {
                    "run_id": run_id,
                    "revision": revision,
                    "finding_ids": [
                        finding_by_key[item]["finding_id"] for item in finding_keys
                    ],
                    "relation_ids": [
                        relation_by_key[item]["relation_id"] for item in relation_keys
                    ],
                    "decision_unit": raw["decision_unit"],
                    "unresolved_conflicts": raw["unresolved_conflicts"],
                },
                findings=all_findings,
                relations=relations,
            ))

        join_manifest: dict[str, Any] | None = None
        integration: dict[str, Any] | None = None
        completed_route_domains = {
            str(route["domain"]) for route in routes if route["status"] == "completed"
        }
        assessed_finding_domains = {
            str(assessment["domain"])
            for assessment in domain_assessments
            if assessment["finding_ids"]
        }
        if not completed_route_domains.issubset(assessed_finding_domains):
            hard_blocked = True
            failure_refs.extend(
                f"completed_route_without_finding:{domain}"
                for domain in sorted(completed_route_domains - assessed_finding_domains)
            )
        if not hard_blocked:
            join_manifest = freeze_finding_join_manifest(
                run_id=run_id,
                revision=revision,
                event=event,
                routes=routes,
                domain_assessments=domain_assessments,
                findings=all_findings,
                relations=relations,
                clusters=clusters,
                writer_id=integrator_writer_id,
            )
            integration = integrate_cross_domain(
                manifest=join_manifest,
                expected_manifest_hash=join_manifest["integrity"]["payload_hash"],
                writer_id=integrator_writer_id,
                event=event,
                routes=routes,
                domain_assessments=domain_assessments,
                findings=all_findings,
                relations=relations,
                clusters=clusters,
            )

        coverage_gaps = [
            str(route["route_id"])
            for route in routes
            if route["status"] in _BOUNDARY_ROUTE_STATUSES
        ]
        expert_review_refs = [
            ref
            for route in routes
            for ref in boundary_packet_refs.get(str(route["domain"]), [])
            if route["status"] in _BOUNDARY_ROUTE_STATUSES
        ]
        expert_review_refs.extend(
            str(finding["expert_review"]["packet_ref"])
            for finding in all_findings
            if finding["expert_review"]["required"]
        )
        completion_input = _completion_input(
            run_id=run_id,
            revision=revision,
            cases=current_cases,
            work_items=final_work_items,
            routes=routes,
            findings=all_findings,
            coverage_gaps=coverage_gaps,
            expert_review_refs=expert_review_refs,
            contract_failure_refs=failure_refs,
            limited_basis=limited_basis,
            user_confirmed_limitations=user_confirmed_limitations,
            final_validator_passed=final_validator_passed,
            tty_final_approval_ready=tty_final_approval_ready,
            integrated=integration is not None,
        )
        if join_manifest is not None and integration is not None:
            completion = assess_completion_from_artifacts(
                completion_input,
                finding_join_manifest=join_manifest,
                cross_domain_integration=integration,
            )
        else:
            completion = assess_completion(completion_input)

        body = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "revision": revision,
            "event": event,
            "routing_decisions": routing_decisions,
            "domain_routes": routes,
            "signal_cases": current_cases,
            "priority_records": priorities,
            "graphs": graphs,
            "work_items": final_work_items,
            "result_cas": cas.records(),
            "domain_assessments": domain_assessments,
            "findings": all_findings,
            "relations": sorted(relations, key=lambda item: item["relation_id"]),
            "clusters": sorted(clusters, key=lambda item: item["cluster_id"]),
            "finding_join_manifest": join_manifest,
            "cross_domain_integration": integration,
            "completion": completion,
            "finalization_allowed": completion["status"] in {
                "finalization_ready",
                "limited_completion_ready",
            },
        }
        record = {**body, "content_hash": _digest(body)}
        SchemaStore().validate(
            "professional-analysis-runtime-result.schema.json", record
        )
        return record
