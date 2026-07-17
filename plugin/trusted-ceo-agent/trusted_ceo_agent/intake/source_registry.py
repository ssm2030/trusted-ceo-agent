from __future__ import annotations

from copy import deepcopy

from trusted_ceo_agent.intake.snapshot import SnapshotResult


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, dict] = {}
        self._resolver: list[dict[str, str]] = []

    def add(self, snapshot: SnapshotResult) -> dict:
        incoming = deepcopy(snapshot.source)
        existing = self._sources.get(incoming["source_id"])
        if existing is None:
            self._sources[incoming["source_id"]] = incoming
            existing = incoming
        else:
            alias = incoming["display_name"]
            if alias != existing["display_name"] and alias not in existing["aliases"]:
                existing["aliases"].append(alias)
                existing["aliases"].sort()
            existing["observation_roles"] = sorted(set(existing["observation_roles"]) | set(incoming["observation_roles"]))
        self._resolver.append(dict(snapshot.resolver_entry))
        self._resolver.sort(key=lambda item: item["original_path_token"])
        return deepcopy(existing)

    @property
    def sources(self) -> list[dict]:
        return [deepcopy(self._sources[key]) for key in sorted(self._sources)]

    @property
    def resolver_entries(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._resolver]

    def customer_view(self) -> list[dict]:
        return self.sources

