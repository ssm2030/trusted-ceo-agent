from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator, assemble_evidence_core
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter
from trusted_ceo_agent.intake.capability import build_capability_map
from trusted_ceo_agent.intake.mapping import (
    ResolvedFieldMapping,
    build_canonical_mapping_proposal,
    resolve_confirmed_mappings,
)
from trusted_ceo_agent.intake.materialize import materialize_observed_facts
from trusted_ceo_agent.intake.models import ParsedDataset
from trusted_ceo_agent.intake.quality import quality_issue
from trusted_ceo_agent.packs.loader import PackLoader
from trusted_ceo_agent.packs.evidence_selection import (
    build_problem_capability_map,
    build_problem_selection,
)
from trusted_ceo_agent.packs.registry import PackRegistry
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.packs.selector import select_domain
from trusted_ceo_agent.runtime_components import execute_analysis_scope, merge_component_runs


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _dataset_document(dataset: ParsedDataset) -> dict[str, Any]:
    return {
        "source_id": dataset.source_id,
        "media_type": dataset.media_type,
        "fields": list(dataset.fields),
        "records": [
            {
                "logical_index": record.logical_index,
                "locator_type": record.locator_type,
                "locator": record.locator,
                "values": record.values,
            }
            for record in dataset.records
        ],
        "metadata": dataset.metadata,
        "quality_issues": dataset.quality_issues,
        "semantic_rows_hash": dataset.semantic_rows_hash,
    }


def _adapter(display_name: str) -> Any:
    suffix = Path(display_name).suffix.lower()
    if suffix == ".csv":
        return CsvAdapter()
    if suffix == ".json":
        return JsonAdapter()
    if suffix == ".xlsx":
        return XlsxAdapter()
    raise ContractError(f"unsupported input format: {suffix or '<none>'}")


def _mapping_document(mapping: ResolvedFieldMapping) -> dict[str, Any]:
    return {
        "mapping_question_ref": mapping.mapping_question_ref,
        "source_field_ref": mapping.source_field_ref,
        "source_id": mapping.source_id,
        "source_field": mapping.source_field,
        "observation_role": mapping.observation_role,
        "metric_code": mapping.metric_code,
        "data_type": mapping.data_type,
        "unit_policy": mapping.unit_policy,
        "unit_code": mapping.unit_code,
        "scale": mapping.scale,
        "time_role": mapping.time_role,
        "dimension_code": mapping.dimension_code,
        "time_field": mapping.time_field,
        "scope_fields": [
            {"source_field": field, "dimension_code": dimension}
            for field, dimension in mapping.scope_fields
        ],
        "confirmed": mapping.confirmed,
    }


def _pack_artifacts(mission: Mapping[str, Any]) -> tuple[dict[str, bytes], dict[str, Any], Any]:
    plugin_root = Path(__file__).resolve().parents[1]
    schema_root = plugin_root / "schemas"
    registry_path = plugin_root / "trust" / "pack-registry.json"
    registry = PackRegistry.load(registry_path, schema_root / "pack-registry.schema.json")
    packs = PackLoader(plugin_root / "packs", schema_root, registry).load_installed()
    selection = select_domain(
        packs,
        mission,
        {
            "industry": None,
            "available_data_roles": [],
        },
    )
    mission_packs = [pack for pack in packs if pack.pack_type == "mission"]
    problem_candidates = [
        pack
        for pack in packs
        if pack.pack_type == "problem"
        and selection.pack.effective_authority != "boundary"
        and selection.pack.ref in pack.document["content"]["domain_pack_refs"]
    ]
    selected = sorted(
        {
            pack.ref: pack
            for pack in [*mission_packs, selection.pack, *problem_candidates]
        }.values(),
        key=lambda pack: (pack.pack_type, pack.ref),
    )
    entries = [
        {
            "pack_type": pack.pack_type,
            "pack_id": pack.pack_id,
            "pack_version": pack.pack_version,
            "pack_sha256": pack.raw_sha256,
            "effective_authority": pack.effective_authority,
        }
        for pack in selected
    ]
    manifest_body = {"schema_version": "1.0.0", "packs": entries}
    manifest = {**manifest_body, "manifest_hash": _sha256(manifest_body)}
    SchemaStore(schema_root).validate("pack-manifest.schema.json", manifest)
    artifacts: dict[str, bytes] = {
        "packs/manifest.json": canonical_bytes(manifest),
        "packs/registry.json": registry_path.read_bytes(),
    }
    for pack in selected:
        payload = pack.path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != pack.raw_sha256:
            raise ContractError(f"Pack changed after validation: {pack.ref}")
        artifacts[f"packs/snapshots/{pack.raw_sha256}.json"] = payload
    return artifacts, manifest, selection


def build_scan_artifacts(
    *,
    files: Mapping[str, bytes],
    pointer: Mapping[str, Any],
    run_id: str,
    current_revision: int,
    source_root: Path,
    mission: Mapping[str, Any] | None = None,
    mapping_overlay: Mapping[str, Any] | None = None,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    effective_mission = mission
    if effective_mission is None:
        effective_mission = strict_loads(
            files.get("mission/effective-mission-contract.json", files["mission/mission-contract.json"])
        )
    if not isinstance(effective_mission, Mapping):
        raise ContractError("Mission Contract must be an object")
    sources = json.loads(files["sources/registry.json"].decode("utf-8"))
    if not isinstance(sources, list):
        raise ContractError("Source Registry must be an array")

    updates: dict[str, bytes] = {}
    quality_register: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, str]] = []
    datasets: list[ParsedDataset] = []
    parsed_count = 0
    for source in sources:
        source_id = str(source["source_id"])
        blob = source_root / str(source["snapshot_ref"])
        try:
            dataset = _adapter(str(source["display_name"])).parse(blob, source_id)
        except ContractError as error:
            quality_register.append(quality_issue(
                issue_code="unsupported_type",
                severity="blocking",
                reason_code="source_parse_failed",
                source_ref={"source_id": source_id},
                suggested_resolution=str(error),
            ))
            continue
        document = _dataset_document(dataset)
        updates[f"intake/datasets/{source_id}.json"] = canonical_bytes(document)
        quality_register.extend(dataset.quality_issues)
        semantic_rows.append({"source_id": source_id, "semantic_rows_hash": dataset.semantic_rows_hash})
        datasets.append(dataset)
        parsed_count += 1

    pack_updates, manifest, selection = _pack_artifacts(effective_mission)
    updates.update(pack_updates)
    metric_definitions = selection.pack.document["content"]["metric_definitions"]
    proposals: list[dict[str, Any]] = []
    for dataset in datasets:
        proposal = build_canonical_mapping_proposal(dataset, metric_definitions)
        proposals.extend(proposal["mappings"])
    canonical_proposal = {
        "mappings": sorted(proposals, key=lambda item: str(item["mapping_question_ref"])),
    }
    SchemaStore().validate("schema-mapping-draft.schema.json", canonical_proposal)
    updates["intake/canonical-mapping-proposal.json"] = canonical_bytes(canonical_proposal)

    facts: list[dict[str, Any]] = []
    resolved_mappings: list[ResolvedFieldMapping] = []
    if mapping_overlay is not None:
        for dataset in datasets:
            resolved = resolve_confirmed_mappings(
                dataset, canonical_proposal, mapping_overlay, metric_definitions,
            )
            resolved_mappings.extend(resolved)
            materialized = materialize_observed_facts(dataset, resolved)
            facts.extend(materialized.fact_register)
            quality_register.extend(materialized.data_quality_register)
            for path, payload in materialized.lineage_files.items():
                existing = updates.get(path)
                if existing is not None and existing != payload:
                    raise ContractError(f"lineage artifact collision: {path}")
                updates[path] = payload
    updates["intake/resolved-mappings.json"] = canonical_bytes([
        _mapping_document(item)
        for item in sorted(resolved_mappings, key=lambda item: (item.source_id, item.source_field))
    ])

    roles_by_source: dict[str, set[str]] = {str(source["source_id"]): set() for source in sources}
    for item in resolved_mappings:
        roles_by_source.setdefault(item.source_id, set()).add(item.observation_role)
    source_registry: list[dict[str, Any]] = []
    for source in sources:
        updated_source = dict(source)
        updated_source["observation_roles"] = sorted(roles_by_source.get(str(source["source_id"]), set()))
        source_registry.append(updated_source)
    updates["sources/registry.json"] = canonical_bytes(source_registry)

    fact_roles = {
        str(item.get("observation_role"))
        for item in facts
        if isinstance(item.get("observation_role"), str)
    }
    required_metrics = {
        f"metric:{metric['metric_code']}": list(metric.get("accepted_observation_roles", []))
        for metric in metric_definitions
    }
    capability = build_capability_map(
        required_metrics,
        fact_roles,
    )
    mission_ref = effective_mission.get("mission_contract_id")
    if not isinstance(mission_ref, str) or not mission_ref.startswith("mission_"):
        mission_ref = make_id("mission", effective_mission)
    semantic_seed = {
        "mission_contract_ref": mission_ref,
        "pack_manifest_hash": manifest["manifest_hash"],
        "semantic_rows": sorted(semantic_rows, key=lambda item: item["source_id"]),
        "quality_issue_ids": sorted(item["quality_issue_id"] for item in quality_register),
        "fact_ids": sorted(item["fact_id"] for item in facts),
        "mapping_question_refs": [
            item["mapping_question_ref"] for item in canonical_proposal["mappings"]
        ],
    }
    semantic_fingerprint = _sha256(semantic_seed)
    parent_hash = str(pointer.get("manifest_hash", ""))
    envelope_seed = {
        "run_id": run_id,
        "revision": current_revision + 1,
        "parent_artifact_hash": parent_hash,
        "semantic_fingerprint": semantic_fingerprint,
    }
    envelope = {
        "schema_version": "1.0.0",
        "artifact_id": make_id("artifact", envelope_seed),
        "run_id": run_id,
        "revision": current_revision + 1,
        "parent_artifact_hash": parent_hash,
        "stage": "evidence_ready" if mapping_overlay is not None else "schema_mapping_job_ready",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "semantic_fingerprint": semantic_fingerprint,
        "artifact_hash": _sha256(envelope_seed),
    }
    core = assemble_evidence_core(
        envelope=envelope,
        mission_contract_ref=mission_ref,
        pack_manifest={
            "pack_manifest_hash": manifest["manifest_hash"],
            "pack_refs": [f"{item['pack_id']}@{item['pack_version']}" for item in manifest["packs"]],
        },
        component_manifest={"component_refs": []},
        source_registry=source_registry,
        data_quality_register=quality_register,
        fact_register=facts,
        signal_register=[],
        evidence_links=[],
        capability_map=capability,
    )
    pack_files = {**files, **updates}
    pack_index = RuntimePackIndex.from_files(pack_files)
    analysis_run_count = 0
    if mapping_overlay is not None:
        problem_refs = tuple(
            f"{pack['pack_id']}@{pack['pack_version']}"
            for pack in pack_index.problem_packs
        )
        plan, runs = execute_analysis_scope(pack_files, core, problem_refs)
        updates["components/plans/analysis.json"] = canonical_bytes(plan.to_dict())
        entries = list(plan.entries)
        for run in runs:
            if run.get("status") == "failed":
                raise ContractError(
                    f"analysis Component failed: {run.get('component_run_id')}"
                )
            run_id_value = str(run["component_run_id"])
            updates[f"components/runs/{run_id_value}.json"] = canonical_bytes(run)
            candidates = [
                entry for entry in entries
                if entry["component_id"] == run["component_id"]
                and sorted(entry.get("input_fact_ids", [])) == sorted(run.get("sorted_input_fact_ids", []))
                and sorted(entry.get("pack_refs", [])) == sorted(run.get("pack_refs", []))
                and (
                    entry.get("parameter_hash", entry.get("parameter_template_hash"))
                    == run.get("parameter_hash")
                )
            ]
            if len(candidates) != 1:
                raise ContractError(
                    f"Component run cannot be traced to one plan entry: {run_id_value}"
                )
            updates[f"components/inputs/{run_id_value}.json"] = canonical_bytes({
                "component_run_id": run_id_value,
                "plan_entry_id": candidates[0]["plan_entry_id"],
                "input_fact_ids": sorted(run.get("sorted_input_fact_ids", [])),
                "input_artifact_hash": run["input_artifact_hash"],
            })
        if runs:
            core = merge_component_runs(
                core,
                runs,
                run_id=run_id,
                revision=current_revision + 1,
                parent_artifact_hash=parent_hash,
                stage="analysis_ready",
            )
        analysis_run_count = len(runs)

    capability = build_problem_capability_map(
        pack_index,
        core.get("fact_register", []),
        core.get("data_quality_register", []),
        source_registry,
    )
    problem_selection = build_problem_selection(
        pack_index,
        core.get("fact_register", []),
        core.get("signal_register", []),
        capability,
    )
    updates["packs/selection.json"] = canonical_bytes(problem_selection)
    core = assemble_evidence_core(
        envelope=core["envelope"],
        mission_contract_ref=core["mission_contract_ref"],
        pack_manifest=core["pack_manifest"],
        component_manifest=core["component_manifest"],
        source_registry=core["source_registry"],
        data_quality_register=core["data_quality_register"],
        fact_register=core["fact_register"],
        signal_register=core["signal_register"],
        evidence_links=core["evidence_links"],
        capability_map=capability,
    )
    EvidenceCoreValidator().validate(core, source_root=source_root)
    updates["evidence/core.json"] = canonical_bytes(core)
    updates["evidence/data-quality-register.json"] = canonical_bytes(quality_register)
    updates["evidence/fact-register.json"] = canonical_bytes(core["fact_register"])
    updates["evidence/signal-register.json"] = canonical_bytes(core["signal_register"])
    updates["evidence/capability-map.json"] = canonical_bytes(capability)
    if analysis_run_count:
        revalidate_component_artifacts({**files, **updates})
    return updates, {
        "parsed_source_count": parsed_count,
        "quality_issue_count": len(quality_register),
        "mapping_question_count": len(canonical_proposal["mappings"]),
        "mapping_applied": mapping_overlay is not None,
        "materialized_fact_count": len(facts),
        "analysis_component_run_count": analysis_run_count,
        "selected_problem_refs": problem_selection["selected_problem_refs"],
        "not_assessable_problem_refs": problem_selection["not_assessable_problem_refs"],
        "domain_pack_ref": selection.pack.ref,
        "domain_pack_authority": selection.pack.effective_authority,
        "domain_selection_status": selection.status,
        "domain_selection_reason_codes": list(selection.reason_codes),
    }
