from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


TERMINAL = {"completed", "valid_not_assessable", "not_applicable", "timed_out", "failed_contract", "superseded"}
ACCEPTED = {"completed", "valid_not_assessable", "not_applicable"}


class JoinBlocked(ContractError):
    """The frozen Join Barrier cannot be satisfied by the submitted results."""


def _id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_bytes(value)).hexdigest()[:24]


def freeze_join_manifest(
    artifact_ref: str,
    mission_contract_hash: str,
    pack_manifest_hash: str,
    tasks: Sequence[Mapping[str, Any]],
    cutoff_at: str,
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in tasks:
        job_id = raw.get("job_id")
        if not isinstance(job_id, str) or not job_id or job_id in seen:
            raise ContractError("Join task job_id must be unique")
        seen.add(job_id)
        normalized.append({
            "job_id": job_id,
            "required": bool(raw.get("required", False)),
            "required_signal_ids": sorted(set(raw.get("required_signal_ids", []))),
        })
    normalized.sort(key=lambda item: item["job_id"])
    body = {
        "artifact_ref": artifact_ref,
        "mission_contract_hash": mission_contract_hash,
        "pack_manifest_hash": pack_manifest_hash,
        "cutoff_at": cutoff_at,
        "tasks": normalized,
    }
    body["join_manifest_id"] = _id("join_", body)
    return body


def _pre_join_clusters(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, tuple[str, ...]], list[str]] = {}
    for card in cards:
        for candidate in card.get("normalized_payload", {}).get("problem_candidates", []):
            evidence = tuple(sorted(
                proposal.get("evidence_ref", "") for proposal in candidate.get("evidence_proposals", [])
            ))
            key = (
                str(candidate.get("problem_family_ref", "")),
                str(candidate.get("scope_key", "")),
                str(candidate.get("period_key", "")),
                evidence,
            )
            candidate_id = candidate.get("claim_id") or f"{card.get('card_id')}:{candidate.get('local_key')}"
            grouped.setdefault(key, []).append(str(candidate_id))
    clusters: list[dict[str, Any]] = []
    for key, candidate_ids in sorted(grouped.items()):
        if len(candidate_ids) < 2:
            continue
        item = {
            "problem_family_ref": key[0], "scope_key": key[1], "period_key": key[2],
            "shared_evidence_ids": list(key[3]), "source_candidate_ids": sorted(candidate_ids),
        }
        item["pre_join_cluster_id"] = _id("prejoin_", item)
        clusters.append(item)
    return clusters


def reduce_join(manifest: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    task_by_id = {task["job_id"]: task for task in manifest.get("tasks", [])}
    result_by_id: dict[str, dict[str, Any]] = {}
    late: list[dict[str, Any]] = []
    for raw in results:
        result = copy.deepcopy(dict(raw))
        job_id = result.get("job_id")
        if job_id not in task_by_id:
            raise JoinBlocked(f"unknown Join task: {job_id}")
        if job_id in result_by_id:
            late.append({"job_id": job_id, "status": "superseded", "attempt": result.get("attempt")})
            continue
        result_by_id[job_id] = result
    if set(result_by_id) != set(task_by_id):
        raise JoinBlocked(f"non-terminal tasks remain: {sorted(set(task_by_id) - set(result_by_id))}")

    cards: list[dict[str, Any]] = []
    terminal_records: list[dict[str, Any]] = []
    for job_id in sorted(task_by_id):
        task = task_by_id[job_id]
        result = result_by_id[job_id]
        status = result.get("status")
        if status not in TERMINAL:
            raise JoinBlocked(f"task is not terminal: {job_id}")
        if task["required"] and status not in ACCEPTED:
            raise JoinBlocked(f"required task did not reach accepted terminal: {job_id}")
        card = result.get("card")
        if status in {"completed", "valid_not_assessable"}:
            if not isinstance(card, dict):
                raise JoinBlocked(f"accepted task lacks card: {job_id}")
            if card.get("job_id") != job_id:
                raise JoinBlocked(f"card Job mismatch: {job_id}")
            if card.get("artifact_ref") != manifest.get("artifact_ref"):
                raise JoinBlocked(f"card artifact is stale: {job_id}")
            if card.get("pack_manifest_hash") != manifest.get("pack_manifest_hash"):
                raise JoinBlocked(f"card Pack manifest is stale: {job_id}")
            dispositions = {
                item.get("signal_id") for item in card.get("normalized_payload", {}).get("signal_dispositions", [])
            }
            missing = set(task.get("required_signal_ids", [])) - dispositions
            if missing:
                raise JoinBlocked(f"required Signal disposition missing for {job_id}: {sorted(missing)}")
            cards.append(card)
        terminal_records.append({"job_id": job_id, "required": task["required"], "status": status})
    cards.sort(key=lambda item: item["job_id"])
    body = {
        "join_manifest_ref": manifest["join_manifest_id"],
        "artifact_ref": manifest["artifact_ref"],
        "mission_contract_hash": manifest["mission_contract_hash"],
        "pack_manifest_hash": manifest["pack_manifest_hash"],
        "task_results": terminal_records,
        "card_refs": [card["card_id"] for card in cards],
        "pre_join_clusters": _pre_join_clusters(cards),
        "late_results": sorted(late, key=lambda item: (item["job_id"], str(item.get("attempt", "")))),
    }
    body["join_result_id"] = _id("joinresult_", body)
    return body
