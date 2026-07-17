from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.packs.schema_validation import validate_document, validate_pack_ontology


_SCHEMA_BY_TYPE = {
    "mission": "mission-pack.schema.json",
    "domain": "domain-pack.schema.json",
    "problem": "problem-pack.schema.json",
}


@dataclass(frozen=True)
class RuntimePackIndex:
    manifest: Mapping[str, Any]
    mission_pack: Mapping[str, Any]
    domain_pack: Mapping[str, Any]
    problem_packs: tuple[Mapping[str, Any], ...]

    @property
    def domain_ref(self) -> str:
        return f"{self.domain_pack['pack_id']}@{self.domain_pack['pack_version']}"

    @property
    def effective_authority(self) -> str:
        authorities = {
            str(item["effective_authority"])
            for item in self.manifest["packs"]
        }
        if "boundary" in authorities:
            return "boundary"
        if "provisional" in authorities:
            return "provisional"
        return "full"

    @property
    def thresholds(self) -> dict[str, str]:
        return {
            str(item["threshold_id"]): str(item["value"])
            for item in self.domain_pack["content"]["threshold_definitions"]
            if item.get("value") is not None
        }

    @property
    def problems_by_family(self) -> dict[str, Mapping[str, Any]]:
        return {
            str(pack["content"]["problem_family_code"]): pack
            for pack in self.problem_packs
        }

    @classmethod
    def from_files(cls, files: Mapping[str, bytes]) -> "RuntimePackIndex":
        raw_manifest = files.get("packs/manifest.json")
        if raw_manifest is None:
            raise ContractError("Pack manifest is missing")
        manifest = strict_loads(raw_manifest)
        if not isinstance(manifest, Mapping):
            raise ContractError("Pack manifest must be an object")
        SchemaStore().validate("pack-manifest.schema.json", manifest)
        manifest_body = {
            "schema_version": manifest["schema_version"],
            "packs": manifest["packs"],
        }
        expected_manifest_hash = hashlib.sha256(canonical_bytes(manifest_body)).hexdigest()
        if manifest.get("manifest_hash") != expected_manifest_hash:
            raise IntegrityError("Pack manifest hash mismatch")

        documents: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        refs: set[str] = set()
        for entry in manifest["packs"]:
            digest = str(entry["pack_sha256"])
            path = f"packs/snapshots/{digest}.json"
            payload = files.get(path)
            if payload is None:
                raise IntegrityError(f"manifested Pack snapshot is missing: {digest}")
            if hashlib.sha256(payload).hexdigest() != digest:
                raise IntegrityError(f"Pack snapshot hash mismatch: {digest}")
            document = strict_loads(payload)
            if not isinstance(document, Mapping):
                raise ContractError("Pack snapshot must be an object")
            pack_type = str(entry["pack_type"])
            validate_document(
                document,
                Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_BY_TYPE[pack_type],
            )
            identity = (
                str(document.get("pack_type")),
                str(document.get("pack_id")),
                str(document.get("pack_version")),
            )
            expected_identity = (
                pack_type,
                str(entry["pack_id"]),
                str(entry["pack_version"]),
            )
            if identity != expected_identity:
                raise IntegrityError("Pack snapshot identity differs from manifest")
            ref = f"{identity[1]}@{identity[2]}"
            if ref in refs:
                raise ContractError(f"duplicate Pack ref in manifest: {ref}")
            refs.add(ref)
            documents.append((entry, document))

        missions = [document for entry, document in documents if entry["pack_type"] == "mission"]
        domains = [document for entry, document in documents if entry["pack_type"] == "domain"]
        problems = [document for entry, document in documents if entry["pack_type"] == "problem"]
        if len(missions) != 1 or len(domains) != 1:
            raise ContractError("runtime Pack stack requires exactly one Mission and one Domain Pack")
        domain_ref = f"{domains[0]['pack_id']}@{domains[0]['pack_version']}"
        domain_authority = next(
            str(entry["effective_authority"])
            for entry, _ in documents
            if entry["pack_type"] == "domain"
        )
        if domain_authority == "boundary" and problems:
            raise ContractError("Boundary Domain cannot authorize Problem Packs")
        for _, document in documents:
            missing = set(document.get("dependencies", [])) - refs
            if missing:
                raise ContractError(f"Pack dependency is not snapshotted: {sorted(missing)}")
        for problem in problems:
            if domain_ref not in problem["content"]["domain_pack_refs"]:
                raise ContractError("Problem Pack is not authorized by the selected Domain")
        validate_pack_ontology(domains[0], problems)
        return cls(
            manifest=dict(manifest),
            mission_pack=dict(missions[0]),
            domain_pack=dict(domains[0]),
            problem_packs=tuple(sorted((dict(item) for item in problems), key=lambda item: str(item["pack_id"]))),
        )
