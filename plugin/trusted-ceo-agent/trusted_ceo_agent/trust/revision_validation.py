from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.outputs.validation import revalidate_package
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.snapshot_validation import validate_snapshot_files


REQUIRED_WEB_REPORT_CHECKS = frozenset(
    {
        "snapshot_manifest",
        "evidence_core",
        "grade_recomputation",
        "final_package",
    }
)


@dataclass(frozen=True)
class RevisionValidation:
    revision: int
    snapshot: Path
    snapshot_manifest: dict[str, Any]
    files: dict[str, bytes]
    checks: tuple[str, ...]


def _schema_numbers(value: Any) -> Any:
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, dict):
        return {key: _schema_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_schema_numbers(child) for child in value]
    return value


def _manifest_files(snapshot: Path, manifest: dict[str, Any]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for item in manifest.get("files", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise IntegrityError("snapshot manifest contains an invalid file entry")
        relative = Path(item["path"])
        path = (snapshot / relative).resolve()
        try:
            path.relative_to(snapshot.resolve())
        except ValueError as error:
            raise IntegrityError(
                f"snapshot manifest path escapes revision: {item['path']}"
            ) from error
        files[item["path"]] = path.read_bytes()
    return files


def validate_revision(store: ArtifactStore, revision: int) -> RevisionValidation:
    """Run the existing full revision validation once and expose its artifacts."""

    snapshot = store.verify_revision(revision)
    manifest_value = strict_loads((snapshot / "snapshot-manifest.json").read_bytes())
    if not isinstance(manifest_value, dict):
        raise IntegrityError("snapshot manifest must be an object")
    manifest = dict(manifest_value)
    if int(manifest.get("revision", -1)) != revision:
        raise IntegrityError("snapshot manifest revision mismatch")
    files = _manifest_files(snapshot, manifest)

    validate_snapshot_files(files)
    checks = ["snapshot_manifest", "full_snapshot_contracts"]

    if "packs/manifest.json" in files:
        SchemaStore().validate(
            "pack-manifest.schema.json",
            _schema_numbers(strict_loads(files["packs/manifest.json"])),
        )
        checks.append("pack_manifest_schema")

    if "evidence/core.json" in files:
        core = strict_loads(files["evidence/core.json"])
        if not isinstance(core, dict):
            raise ContractError("Evidence Core must be an object")
        EvidenceCoreValidator().validate(_schema_numbers(core), source_root=snapshot)
        checks.append("evidence_core")

    component_paths = [
        path
        for path in files
        if path.startswith("components/runs/") and path.endswith(".json")
    ]
    for path in sorted(component_paths):
        SchemaStore().validate(
            "component-run.schema.json",
            _schema_numbers(strict_loads(files[path])),
        )
    if component_paths:
        revalidate_component_artifacts(files)
        checks.append("component_run_recomputation")

    if "grading/inputs.json" in files:
        grading_inputs = _schema_numbers(
            strict_loads(files["grading/inputs.json"])
        )
        if not isinstance(grading_inputs, list):
            raise IntegrityError("grading inputs must be an array")
        records: dict[str, Any] = {}
        for path, payload in sorted(files.items()):
            if not path.startswith("grading/records/") or not path.endswith(".json"):
                continue
            record = _schema_numbers(strict_loads(payload))
            if not isinstance(record, dict) or not isinstance(
                record.get("issue_id"), str
            ):
                raise IntegrityError(f"invalid Grade Record: {path}")
            records[record["issue_id"]] = record
        for grading_input in grading_inputs:
            if not isinstance(grading_input, dict):
                raise IntegrityError("grading input must be an object")
            recomputed = grade(grading_input)
            issue_id = grading_input.get("issue_id")
            stored = records.get(str(issue_id))
            if stored is None or canonical_bytes(stored) != canonical_bytes(recomputed):
                raise IntegrityError(f"Grade Record mismatch: {issue_id}")
        checks.append("grade_recomputation")

    if "final/result.json" in files:
        result = strict_loads(files["final/result.json"])
        evidence = strict_loads(files.get("evidence/core.json", b"{}"))
        result_for_validation = _schema_numbers(result)
        evidence_for_validation = _schema_numbers(evidence)
        if not isinstance(result, dict) or not isinstance(evidence, dict):
            raise IntegrityError("Final Result and Evidence Core must be objects")
        expected_paths = set(render_package(result_for_validation))
        package = {
            path: files[path]
            for path in expected_paths
            if path in files
        }
        revalidate_package(
            result_for_validation,
            package,
            evidence_links={
                item["evidence_link_id"]: item
                for item in evidence_for_validation.get("evidence_links", [])
                if isinstance(item, dict) and isinstance(
                    item.get("evidence_link_id"), str
                )
            },
        )
        checks.append("final_package")

    return RevisionValidation(
        revision=revision,
        snapshot=snapshot,
        snapshot_manifest=manifest,
        files=files,
        checks=tuple(checks),
    )
