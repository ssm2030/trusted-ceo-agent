from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256


@dataclass(frozen=True)
class RevisionArtifacts:
    revision_ancestry_hash: str
    trust_events: tuple[dict[str, Any], ...]
    file_manifest: tuple[dict[str, Any], ...]
    revision_view: dict[str, Any]


_COLLECTIONS = (
    ("issues", "issue_id"),
    ("cross_issue_relations", "relation_id"),
    ("conditional_responses", "response_id"),
    ("monitoring", "monitor_id"),
    ("blind_spots", "blind_spot_id"),
    ("expert_review_packets", "expert_packet_id"),
)

_EVIDENCE_COLLECTIONS = (
    ("fact_register", "fact_id"),
    ("signal_register", "signal_id"),
    ("evidence_links", "evidence_link_id"),
    ("source_registry", "source_id"),
)

_PATH_CATEGORY_PREFIXES = (
    ("sources/", "data"),
    ("intake/", "data"),
    ("mapping/", "mapping"),
    ("mission/", "mission"),
    ("packs/", "pack"),
    ("components/", "component"),
    ("evidence/", "evidence"),
    ("grading/", "grade"),
    ("approvals/", "approval"),
    ("final/expert", "expert_packet"),
    ("final/", "wording"),
)


def _native_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise IntegrityError(f"{label} must be an integer")
    integer = int(value)
    if value != integer:
        raise IntegrityError(f"{label} must be an integer")
    return integer


def _manifest(store: ArtifactStore, revision: int) -> tuple[Any, dict[str, Any]]:
    snapshot = store.verify_revision(revision)
    try:
        value = strict_loads((snapshot / "snapshot-manifest.json").read_bytes())
    except (UnicodeError, ValueError) as error:
        raise IntegrityError(f"invalid snapshot manifest at revision {revision}") from error
    if not isinstance(value, Mapping):
        raise IntegrityError(f"snapshot manifest is not an object: {revision}")
    manifest = dict(value)
    if _native_int(manifest.get("revision"), "manifest revision") != revision:
        raise IntegrityError(f"snapshot manifest revision mismatch: {revision}")
    if _native_int(
        manifest.get("parent_revision"), "manifest parent revision"
    ) != revision - 1:
        raise IntegrityError(f"snapshot ancestry is interrupted at revision {revision}")
    return snapshot, manifest


def _files(snapshot: Any, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    entries = manifest.get("files", [])
    if not isinstance(entries, list):
        raise IntegrityError("snapshot manifest files must be an array")
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise IntegrityError("snapshot manifest file entry is invalid")
        result[str(entry["path"])] = (snapshot / str(entry["path"])).read_bytes()
    return result


def _json(files: Mapping[str, bytes], path: str) -> Mapping[str, Any] | None:
    payload = files.get(path)
    if payload is None:
        return None
    try:
        value = strict_loads(payload)
    except (UnicodeError, ValueError) as error:
        raise IntegrityError(f"invalid immutable JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise IntegrityError(f"immutable JSON must be an object: {path}")
    return value


def _stable_objects(
    result: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
) -> dict[str, bytes]:
    objects: dict[str, bytes] = {}
    for collection, id_field in _COLLECTIONS:
        values = result.get(collection, [])
        if not isinstance(values, list):
            raise IntegrityError(f"{collection} must be an array")
        for value in values:
            if not isinstance(value, Mapping):
                raise IntegrityError(f"{collection} entry must be an object")
            identifier = value.get(id_field)
            if not isinstance(identifier, str) or not identifier:
                raise IntegrityError(f"{collection} entry has an invalid {id_field}")
            if identifier in objects:
                raise IntegrityError(f"duplicate stable ID: {identifier}")
            objects[identifier] = jcs_bytes(value)
    if evidence is not None:
        for collection, id_field in _EVIDENCE_COLLECTIONS:
            values = evidence.get(collection, [])
            if not isinstance(values, list):
                raise IntegrityError(f"{collection} must be an array")
            for value in values:
                if not isinstance(value, Mapping):
                    raise IntegrityError(f"{collection} entry must be an object")
                identifier = value.get(id_field)
                if not isinstance(identifier, str) or not identifier:
                    raise IntegrityError(
                        f"{collection} entry has an invalid {id_field}"
                    )
                if identifier in objects:
                    raise IntegrityError(f"duplicate stable ID: {identifier}")
                objects[identifier] = jcs_bytes(value)
    return objects


def _changed_paths(
    previous_manifest: Mapping[str, Any],
    current_manifest: Mapping[str, Any],
) -> set[str]:
    def indexed(manifest: Mapping[str, Any]) -> dict[str, str]:
        return {
            str(item["path"]): str(item["sha256"])
            for item in manifest.get("files", [])
            if isinstance(item, Mapping)
            and isinstance(item.get("path"), str)
            and isinstance(item.get("sha256"), str)
        }

    previous = indexed(previous_manifest)
    current = indexed(current_manifest)
    return {
        path
        for path in set(previous) | set(current)
        if previous.get(path) != current.get(path)
    }


def _categories(paths: set[str], changed_refs: set[str]) -> list[str]:
    categories: set[str] = set()
    for path in paths:
        for prefix, category in _PATH_CATEGORY_PREFIXES:
            if path.startswith(prefix):
                categories.add(category)
                break
    if changed_refs and not categories:
        categories.add("wording")
    order = [
        "data",
        "mapping",
        "mission",
        "scope",
        "pack",
        "component",
        "evidence",
        "grade",
        "approval",
        "wording",
        "expert_packet",
    ]
    return [category for category in order if category in categories]


def _invalidated_approvals(
    files: Mapping[str, bytes],
    *,
    revision: int | None = None,
) -> list[str]:
    result: list[str] = []
    for path, payload in files.items():
        if not path.startswith("approvals/records/") or not path.endswith(".json"):
            continue
        try:
            record = strict_loads(payload)
        except (UnicodeError, ValueError) as error:
            raise IntegrityError(f"invalid Approval Record: {path}") from error
        if not isinstance(record, Mapping):
            raise IntegrityError(f"Approval Record must be an object: {path}")
        invalidated = record.get("invalidated_by_revision")
        if invalidated is None:
            continue
        invalidated_revision = _native_int(
            invalidated,
            "Approval invalidated revision",
        )
        if revision is None or invalidated_revision == revision:
            approval_id = record.get("approval_id")
            if not isinstance(approval_id, str):
                raise IntegrityError(f"Approval Record lacks an ID: {path}")
            result.append(approval_id)
    return sorted(set(result))


def _trust_events(
    snapshots: list[tuple[int, Mapping[str, bytes]]],
) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    sequence = 0
    for revision, files in snapshots:
        paths = sorted(
            path
            for path in files
            if path.startswith("audit/events/") and path.endswith(".json")
            and path.startswith(f"audit/events/r{revision:04d}-")
        )
        for path in paths:
            event = _json(files, path)
            if event is None:
                continue
            command = event.get("command")
            if not isinstance(command, str) or not command:
                raise IntegrityError(f"audit event lacks a command: {path}")
            sequence += 1
            body = {
                "revision": revision,
                "command": command,
                "logical_path": path,
            }
            timestamp = event.get("timestamp", event.get("created_at"))
            gate = event.get("gate")
            events.append(
                {
                    "event_id": make_id("event", body),
                    "revision": revision,
                    "command": command,
                    "actor_kind": (
                        "human"
                        if command in {"approve-interactive", "decide-interactive"}
                        else "runtime"
                    ),
                    "gate": gate if isinstance(gate, str) else None,
                    "sequence": sequence,
                    "timestamp": timestamp if isinstance(timestamp, str) else None,
                    "invalidated_approval_refs": _invalidated_approvals(
                        files,
                        revision=revision,
                    ),
                }
            )
    return tuple(events)


def _file_manifest(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, Mapping):
            raise IntegrityError("snapshot manifest file entry is invalid")
        path = entry.get("path")
        if not isinstance(path, str):
            raise IntegrityError("snapshot manifest path is invalid")
        lowered = path.casefold()
        if (
            path == "snapshot-manifest.json"
            or "web-report-bundle" in lowered
            or lowered.startswith("web-report/")
        ):
            continue
        result.append(
            {
                "logical_path": path,
                "length_bytes": _native_int(entry.get("size"), "manifest file size"),
                "sha256": str(entry["sha256"]),
            }
        )
    return tuple(sorted(result, key=lambda item: item["logical_path"]))


def build_revision_artifacts(
    store: ArtifactStore,
    *,
    current_revision: int,
) -> RevisionArtifacts:
    if current_revision < 1:
        raise ValueError("current_revision must be positive")
    ordered_manifests: list[dict[str, Any]] = []
    snapshots: list[tuple[int, Mapping[str, bytes]]] = []
    current_manifest: dict[str, Any] | None = None
    current_files: dict[str, bytes] | None = None
    previous_final: tuple[int, dict[str, Any], dict[str, bytes]] | None = None

    for revision in range(1, current_revision + 1):
        snapshot, manifest = _manifest(store, revision)
        files = _files(snapshot, manifest)
        snapshots.append((revision, files))
        ordered_manifests.append(
            {
                "revision": revision,
                "manifest_hash": str(manifest["manifest_hash"]),
            }
        )
        if revision < current_revision and "final/result.json" in files:
            previous_final = (revision, manifest, files)
        if revision == current_revision:
            current_manifest = manifest
            current_files = files

    if current_manifest is None or current_files is None:
        raise IntegrityError("current revision could not be loaded")
    current_result = _json(current_files, "final/result.json")
    if current_result is None:
        raise IntegrityError("current revision has no Final Result")
    current_fingerprint = current_result.get("integrity", {}).get(
        "semantic_fingerprint"
    )
    if not isinstance(current_fingerprint, str):
        raise IntegrityError("current Final Result lacks a semantic fingerprint")

    if previous_final is None:
        revision_view = {
            "available": False,
            "unavailable_reason": "NO_PRIOR_FINAL_RESULT",
            "base_revision": None,
            "compare_revision": current_revision,
            "change_categories": [],
            "added_refs": [],
            "changed_refs": [],
            "removed_refs": [],
            "invalidated_approval_refs": _invalidated_approvals(current_files),
            "previous_semantic_fingerprint": None,
            "current_semantic_fingerprint": current_fingerprint,
            "display_message_ko": "비교할 이전 최종 결과가 없습니다.",
        }
    else:
        base_revision, previous_manifest, previous_files = previous_final
        previous_result = _json(previous_files, "final/result.json")
        if previous_result is None:
            raise IntegrityError("previous Final Result disappeared")
        previous_fingerprint = previous_result.get("integrity", {}).get(
            "semantic_fingerprint"
        )
        if not isinstance(previous_fingerprint, str):
            raise IntegrityError(
                "previous Final Result lacks a semantic fingerprint"
            )
        current_objects = _stable_objects(
            current_result,
            _json(current_files, "evidence/core.json"),
        )
        previous_objects = _stable_objects(
            previous_result,
            _json(previous_files, "evidence/core.json"),
        )
        current_ids = set(current_objects)
        previous_ids = set(previous_objects)
        added = current_ids - previous_ids
        removed = previous_ids - current_ids
        changed = {
            identifier
            for identifier in current_ids & previous_ids
            if current_objects[identifier] != previous_objects[identifier]
        }
        paths = _changed_paths(previous_manifest, current_manifest)
        revision_view = {
            "available": True,
            "unavailable_reason": None,
            "base_revision": base_revision,
            "compare_revision": current_revision,
            "change_categories": _categories(paths, added | removed | changed),
            "added_refs": sorted(added),
            "changed_refs": sorted(changed),
            "removed_refs": sorted(removed),
            "invalidated_approval_refs": _invalidated_approvals(current_files),
            "previous_semantic_fingerprint": previous_fingerprint,
            "current_semantic_fingerprint": current_fingerprint,
            "display_message_ko": (
                f"최종 결과 리비전 {base_revision}과 {current_revision}의 "
                "검증된 변경입니다."
            ),
        }

    return RevisionArtifacts(
        revision_ancestry_hash=jcs_sha256({"manifests": ordered_manifests}),
        trust_events=_trust_events(snapshots),
        file_manifest=_file_manifest(current_manifest),
        revision_view=revision_view,
    )
