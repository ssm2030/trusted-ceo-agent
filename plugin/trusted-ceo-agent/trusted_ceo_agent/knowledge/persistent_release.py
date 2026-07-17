from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.knowledge.release import ReleaseRegistry, verify_knowledge_release
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


_STATE_KEYS = frozenset(
    {
        "schema_version",
        "releases",
        "active_release_id",
        "run_pins",
        "revoked_release_ids",
        "consumed_approval_ids",
        "rollback_events",
        "state_hash",
    }
)
_EVENT_KEYS = frozenset(
    {
        "event_type",
        "from_release_id",
        "to_release_id",
        "approval_id",
        "approval_hash",
        "effective_for_runs_after_revision",
        "created_at",
        "event_id",
        "event_hash",
    }
)
_T = TypeVar("_T")


def _native(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ContractError("registry state numbers must be finite integers")
        return int(value)
    if isinstance(value, dict):
        return {key: _native(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native(child) for child in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field} must be an object")
    return copy.deepcopy(dict(value))


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    return copy.deepcopy(value)


def _registry_body(registry: ReleaseRegistry) -> dict[str, Any]:
    releases = sorted(
        (copy.deepcopy(value) for value in registry._releases.values()),
        key=lambda value: (value["release_sequence"], value["release_id"]),
    )
    return {
        "schema_version": "1.0.0",
        "releases": releases,
        "active_release_id": registry._active_release_id,
        "run_pins": [
            {"run_id": run_id, "release_id": release_id}
            for run_id, release_id in sorted(registry._run_releases.items())
        ],
        "revoked_release_ids": sorted(registry._revoked),
        "consumed_approval_ids": sorted(registry._consumed_approvals),
        "rollback_events": copy.deepcopy(registry._events),
    }


def export_registry_state(registry: ReleaseRegistry) -> bytes:
    """Export every mutable registry pointer as one deterministic, hashed value."""
    if not isinstance(registry, ReleaseRegistry):
        raise TypeError("registry must be a ReleaseRegistry")
    body = _registry_body(registry)
    payload = dict(body)
    payload["state_hash"] = _digest(body)
    return canonical_bytes(payload)


def _verify_event(event: Any, releases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    value = _mapping(event, "rollback event")
    if frozenset(value) != _EVENT_KEYS:
        raise ContractError("rollback event fields are invalid")
    if value["event_type"] != "rollback":
        raise ContractError("rollback event type is invalid")
    from_id = _text(value["from_release_id"], "from_release_id")
    to_id = _text(value["to_release_id"], "to_release_id")
    if from_id not in releases or to_id not in releases or from_id == to_id:
        raise ContractError("rollback event release references are invalid")
    approval_id = _text(value["approval_id"], "approval_id")
    approval_hash = _text(value["approval_hash"], "approval_hash")
    if len(approval_hash) != 64 or any(char not in "0123456789abcdef" for char in approval_hash):
        raise ContractError("rollback approval_hash is invalid")
    revision = value["effective_for_runs_after_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ContractError("rollback effective revision is invalid")
    _text(value["created_at"], "created_at")
    event_id = _text(value["event_id"], "event_id")
    event_hash = _text(value["event_hash"], "event_hash")
    body_without_ids = dict(value)
    body_without_ids.pop("event_hash")
    body_without_ids.pop("event_id")
    expected_id = "knowledgerollback_" + _digest(body_without_ids)[:24]
    if not hmac.compare_digest(event_id, expected_id):
        raise IntegrityError("rollback event ID is invalid")
    expected_hash = _digest({key: child for key, child in value.items() if key != "event_hash"})
    if not hmac.compare_digest(event_hash, expected_hash):
        raise IntegrityError("rollback event hash is invalid")
    return value


def import_registry_state(payload: bytes) -> ReleaseRegistry:
    """Verify and reconstruct a ReleaseRegistry without replaying mutations."""
    if not isinstance(payload, bytes):
        raise TypeError("registry state payload must be bytes")
    try:
        value = _native(strict_loads(payload))
    except (UnicodeError, ValueError) as error:
        raise IntegrityError("registry state is not valid canonical JSON") from error
    state = _mapping(value, "registry state")
    if frozenset(state) != _STATE_KEYS or state["schema_version"] != "1.0.0":
        raise ContractError("registry state fields or schema version are invalid")
    supplied_hash = _text(state.pop("state_hash"), "state_hash")
    if len(supplied_hash) != 64 or not hmac.compare_digest(supplied_hash, _digest(state)):
        raise IntegrityError("registry state hash mismatch")

    release_values = _list(state["releases"], "releases")
    if not release_values:
        raise ContractError("registry state requires at least one release")
    releases: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    sequences: set[int] = set()
    for item in release_values:
        release = _mapping(item, "release")
        verify_knowledge_release(release)
        release_id = _text(release["release_id"], "release_id")
        sequence = release["release_sequence"]
        if release_id in releases or sequence in sequences:
            raise ContractError("release IDs and sequences must be unique")
        releases[release_id] = release
        sequences.add(sequence)
        if release["base_release_id"] is None:
            roots.append(release)
    if len(roots) != 1:
        raise ContractError("registry state must contain exactly one root release")
    for release in releases.values():
        base_id = release["base_release_id"]
        if base_id is None:
            continue
        if base_id not in releases:
            raise ContractError("release base is missing")
        if not hmac.compare_digest(release["base_release_hash"], releases[base_id]["release_hash"]):
            raise ContractError("release base hash does not match its registry object")

    active_release_id = _text(state["active_release_id"], "active_release_id")
    if active_release_id not in releases:
        raise ContractError("active Knowledge Release is missing")

    run_pins: dict[str, str] = {}
    for item in _list(state["run_pins"], "run_pins"):
        pin = _mapping(item, "run pin")
        if frozenset(pin) != frozenset({"run_id", "release_id"}):
            raise ContractError("run pin fields are invalid")
        run_id = _text(pin["run_id"], "run_id")
        release_id = _text(pin["release_id"], "release_id")
        if run_id in run_pins or release_id not in releases:
            raise ContractError("run pin is duplicated or references an unknown release")
        run_pins[run_id] = release_id

    revoked_values = _list(state["revoked_release_ids"], "revoked_release_ids")
    revoked = {_text(item, "revoked_release_id") for item in revoked_values}
    if len(revoked) != len(revoked_values) or not revoked.issubset(releases):
        raise ContractError("revoked release set is invalid")
    if active_release_id in revoked:
        raise ContractError("active Knowledge Release cannot be revoked")

    approval_values = _list(state["consumed_approval_ids"], "consumed_approval_ids")
    consumed = {_text(item, "consumed_approval_id") for item in approval_values}
    if len(consumed) != len(approval_values):
        raise ContractError("consumed approval IDs must be unique")

    events = [
        _verify_event(item, releases)
        for item in _list(state["rollback_events"], "rollback_events")
    ]
    if {item["from_release_id"] for item in events} != revoked:
        raise ContractError("revoked releases and rollback events disagree")
    required_approvals = {
        release["stage3_approval_ref"]["knowledge_approval_id"]
        for release in releases.values()
        if release["stage3_approval_ref"] is not None
    } | {item["approval_id"] for item in events}
    if required_approvals != consumed:
        raise ContractError("consumed approvals disagree with release history")

    registry = ReleaseRegistry(roots[0])
    registry._releases = copy.deepcopy(releases)
    registry._active_release_id = active_release_id
    registry._run_releases = copy.deepcopy(run_pins)
    registry._revoked = set(revoked)
    registry._consumed_approvals = set(consumed)
    registry._events = copy.deepcopy(events)
    return registry


class PersistentReleaseRegistry:
    """ArtifactStore-backed CAS adapter for ReleaseRegistry state."""

    STATE_PATH = "knowledge/release-registry.json"

    def __init__(
        self,
        store: ArtifactStore,
        registry: ReleaseRegistry,
        revision: int,
    ) -> None:
        self._store = store
        self._registry = registry
        self._revision = revision

    @classmethod
    def initialize(
        cls,
        store: ArtifactStore,
        initial_release: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> PersistentReleaseRegistry:
        registry = ReleaseRegistry(initial_release)
        store.publish(
            expected_revision,
            {cls.STATE_PATH: export_registry_state(registry)},
        )
        return cls(store, registry, expected_revision + 1)

    @classmethod
    def restore(cls, store: ArtifactStore) -> PersistentReleaseRegistry:
        state = store.state()
        revision = state.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ContractError("Knowledge Release registry has not been initialized")
        snapshot = store.verify_revision(revision)
        state_path = snapshot / Path(cls.STATE_PATH)
        if not state_path.is_file():
            raise IntegrityError("Knowledge Release registry state is missing")
        registry = import_registry_state(state_path.read_bytes())
        return cls(store, registry, revision)

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def active_release_id(self) -> str:
        return self._registry.active_release_id

    def get_release(self, release_id: str) -> dict[str, Any]:
        return self._registry.get_release(release_id)

    def release_for_run(self, run_id: str) -> dict[str, Any]:
        return self._registry.release_for_run(run_id)

    def _mutate(
        self,
        expected_revision: int,
        operation: Callable[[ReleaseRegistry], _T],
    ) -> _T:
        if expected_revision != self._revision:
            raise RevisionConflict(
                f"expected revision {expected_revision}, adapter is at {self._revision}"
            )
        working = import_registry_state(export_registry_state(self._registry))
        result = operation(working)
        self._store.publish(
            expected_revision,
            {self.STATE_PATH: export_registry_state(working)},
        )
        self._registry = working
        self._revision = expected_revision + 1
        return copy.deepcopy(result)

    def start_run(self, run_id: str, *, expected_revision: int) -> dict[str, Any]:
        return self._mutate(
            expected_revision,
            lambda registry: registry.start_run(run_id),
        )

    def deploy(
        self,
        candidate: Mapping[str, Any],
        approval: Mapping[str, Any],
        *,
        current_revision: int,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self._mutate(
            expected_revision,
            lambda registry: registry.deploy(
                candidate,
                approval,
                current_revision=current_revision,
            ),
        )

    def rollback(
        self,
        *,
        revoked_release_id: str,
        target_release_id: str,
        approval: Mapping[str, Any],
        current_revision: int,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self._mutate(
            expected_revision,
            lambda registry: registry.rollback(
                revoked_release_id=revoked_release_id,
                target_release_id=target_release_id,
                approval=approval,
                current_revision=current_revision,
            ),
        )
