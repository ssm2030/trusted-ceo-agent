from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.components import component_contracts
from trusted_ceo_agent.contracts.condition_dsl import validate_condition
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.packs.models import LoadedPack
from trusted_ceo_agent.packs.registry import PackRegistry
from trusted_ceo_agent.packs.schema_validation import (
    validate_document,
    validate_problem_capability_contract,
)


MAX_PACK_BYTES = 1_048_576
_PACK_SCHEMAS = {
    "mission": "mission-pack.schema.json",
    "domain": "domain-pack.schema.json",
    "problem": "problem-pack.schema.json",
}


def _identity(path: Path) -> tuple[int, int, int, int]:
    details = path.stat(follow_symlinks=False)
    return (
        int(getattr(details, "st_dev", 0)),
        int(getattr(details, "st_ino", 0)),
        int(details.st_size),
        int(details.st_mtime_ns),
    )


def _stable_read(root: Path, path: Path) -> tuple[Path, bytes]:
    safe = ensure_within(root, path)
    if not safe.is_file() or safe.suffix.lower() != ".json":
        raise ValueError(f"Pack must be an existing JSON file: {path}")
    before = _identity(safe)
    if before[2] > MAX_PACK_BYTES:
        raise ContractError("Pack size limit exceeded")
    with safe.open("rb") as handle:
        payload = handle.read(MAX_PACK_BYTES + 1)
        opened = os.fstat(handle.fileno())
        opened_identity = (
            int(getattr(opened, "st_dev", 0)),
            int(getattr(opened, "st_ino", 0)),
            int(opened.st_size),
            int(opened.st_mtime_ns),
        )
    after = _identity(safe)
    if len(payload) > MAX_PACK_BYTES:
        raise ContractError("Pack size limit exceeded")
    if before != opened_identity or before != after:
        raise IntegrityError(f"Pack changed while being read: {safe.name}")
    return safe, payload


def _validate_semantics(document: Mapping[str, Any]) -> None:
    pack_type = document["pack_type"]
    content = document["content"]
    known_components = set(component_contracts())
    if pack_type == "domain":
        for threshold in content["threshold_definitions"]:
            validate_condition(threshold["condition_expression"])
        for rule in content["applicability_rules"]:
            validate_condition(rule)
        for trigger in content["expert_triggers"]:
            validate_condition(trigger["trigger_condition"])
    elif pack_type == "problem":
        validate_problem_capability_contract(document)
        for expression in content["entry_conditions"]:
            validate_condition(expression)
        for condition in content["blocking_counter_evidence_conditions"]:
            validate_condition(condition["condition_expression"])
        component_ids = {
            str(step["component_id"])
            for step in [*content["analysis_plan"], *content["deep_dive_plan"]]
        }
        unknown = component_ids - known_components
        if unknown:
            raise ContractError(f"unknown Component reference: {sorted(unknown)}")
        roles = {str(lens["role"]) for lens in content["lens_plan"] if lens["required"]}
        if "requested" not in roles or "challenge" not in roles:
            raise ContractError("Problem Pack must require requested and challenge lenses")


class PackLoader:
    def __init__(self, pack_root: Path, schema_root: Path, registry: PackRegistry) -> None:
        self.pack_root = pack_root.resolve(strict=True)
        self.schema_root = schema_root.resolve(strict=True)
        self.registry = registry

    def load_path(self, path: Path) -> LoadedPack:
        safe, payload = _stable_read(self.pack_root, path)
        document = strict_loads(payload)
        if not isinstance(document, Mapping):
            raise ContractError("Pack document must be an object")
        pack_type = document.get("pack_type")
        if pack_type not in _PACK_SCHEMAS:
            raise ContractError(f"unsupported Pack type: {pack_type}")
        validate_document(document, self.schema_root / _PACK_SCHEMAS[str(pack_type)])
        _validate_semantics(document)
        digest = hashlib.sha256(payload).hexdigest()
        registered = self.registry.authority_for(
            digest, str(document["pack_id"]), str(document["pack_version"])
        )
        requested = str(document["requested_authority"])
        if registered is None:
            effective = "provisional"
        elif registered == "boundary" or requested == "boundary":
            effective = "boundary"
        else:
            effective = "full"
        return LoadedPack(safe, digest, document, effective)

    def load_installed(self) -> tuple[LoadedPack, ...]:
        paths = sorted(self.pack_root.rglob("pack.json"), key=lambda path: path.as_posix())
        return tuple(sorted((self.load_path(path) for path in paths), key=lambda pack: (pack.pack_type, pack.ref)))
