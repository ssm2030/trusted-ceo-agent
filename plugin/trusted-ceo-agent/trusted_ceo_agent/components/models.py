from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ComponentContract:
    component_id: str
    version: str
    supported_input_fact_codes: tuple[str, ...]
    required_dimensions: tuple[str, ...]
    parameter_schema: Mapping[str, Any]
    output_fact_codes: tuple[str, ...]
    output_signal_codes: tuple[str, ...]
    failure_reason_codes: tuple[str, ...]
    parallel_safe: bool
    max_input_records: int
    timeout_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "version": self.version,
            "supported_input_fact_codes": list(self.supported_input_fact_codes),
            "required_dimensions": list(self.required_dimensions),
            "parameter_schema": dict(self.parameter_schema),
            "output_fact_codes": list(self.output_fact_codes),
            "output_signal_codes": list(self.output_signal_codes),
            "failure_reason_codes": list(self.failure_reason_codes),
            "parallel_safe": self.parallel_safe,
            "max_input_records": self.max_input_records,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class ComponentRunResult:
    component_run_id: str
    component_id: str
    component_version: str
    input_artifact_hash: str
    sorted_input_fact_ids: tuple[str, ...]
    parameter_hash: str
    pack_refs: tuple[str, ...]
    output_facts: tuple[dict[str, Any], ...]
    output_signals: tuple[dict[str, Any], ...]
    status: str
    reason_codes: tuple[str, ...]
    duration: str = "0"

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "component_run_id": self.component_run_id,
            "component_id": self.component_id,
            "component_version": self.component_version,
            "input_artifact_hash": self.input_artifact_hash,
            "sorted_input_fact_ids": list(self.sorted_input_fact_ids),
            "parameter_hash": self.parameter_hash,
            "pack_refs": list(self.pack_refs),
            "output_fact_ids": [fact["fact_id"] for fact in self.output_facts],
            "output_signal_ids": [signal["signal_id"] for signal in self.output_signals],
            "output_facts": list(self.output_facts),
            "output_signals": list(self.output_signals),
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.semantic_dict()
        value["duration"] = self.duration
        return value


class NotAssessable(Exception):
    def __init__(self, *reason_codes: str) -> None:
        self.reason_codes = tuple(sorted(set(reason_codes))) or ("not_assessable",)
        super().__init__(", ".join(self.reason_codes))


ComponentFunction = Any
