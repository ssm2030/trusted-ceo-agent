from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord
from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256
from trusted_ceo_agent.web_report.closure import EvidenceClosure
from trusted_ceo_agent.web_report.contracts import MAX_PREVIEW_BYTES


@dataclass(frozen=True)
class SourceViews:
    sources: tuple[dict[str, Any], ...]
    previews: tuple[dict[str, Any], ...]


def _source_index(closure: EvidenceClosure) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for source in closure.sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise IntegrityError("Source has an invalid source_id")
        if source_id in result:
            raise IntegrityError(f"duplicate Source: {source_id}")
        result[source_id] = dict(source)
    return result


def _source_references(
    closure: EvidenceClosure,
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for fact in closure.facts:
        refs = fact.get("source_refs", [])
        if not isinstance(refs, list):
            raise IntegrityError(f"Fact source_refs are invalid: {fact.get('fact_id')}")
        for source_ref in refs:
            if not isinstance(source_ref, Mapping):
                raise IntegrityError(
                    f"Fact Source reference is invalid: {fact.get('fact_id')}"
                )
            source_id = source_ref.get("source_id")
            extraction_hash = source_ref.get("extraction_hash")
            if not isinstance(source_id, str) or not isinstance(
                extraction_hash, str
            ):
                raise IntegrityError("Fact Source reference lacks stable IDs")
            by_hash = result.setdefault(source_id, {})
            candidate = dict(source_ref)
            existing = by_hash.get(extraction_hash)
            if existing is not None and canonical_bytes(existing) != canonical_bytes(
                candidate
            ):
                raise IntegrityError(
                    f"extraction hash collision for Source: {source_id}"
                )
            by_hash[extraction_hash] = candidate
    return result


def _verify_blob(snapshot_root: Path, source: Mapping[str, Any]) -> Path:
    snapshot_ref = source.get("snapshot_ref")
    if not isinstance(snapshot_ref, str):
        raise IntegrityError(f"Source snapshot ref is invalid: {source.get('source_id')}")
    try:
        path = ensure_within(snapshot_root, snapshot_root / snapshot_ref)
    except (OSError, ValueError) as error:
        raise IntegrityError(f"Source snapshot path is unsafe: {snapshot_ref}") from error
    if not path.is_file():
        raise IntegrityError(f"Source snapshot is missing: {source.get('source_id')}")
    payload = path.read_bytes()
    expected_size = source.get("size_bytes")
    if not isinstance(expected_size, (int, Decimal)) or int(expected_size) != len(
        payload
    ):
        raise IntegrityError(f"Source snapshot size mismatch: {source.get('source_id')}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != source.get("sha256"):
        raise IntegrityError(f"Source snapshot hash mismatch: {source.get('source_id')}")
    if snapshot_ref != f"sources/blobs/{digest}":
        raise IntegrityError(
            f"Source snapshot locator mismatch: {source.get('source_id')}"
        )
    return path


def _parse_dataset(path: Path, source: Mapping[str, Any]) -> ParsedDataset:
    source_id = str(source["source_id"])
    media_type = source.get("media_type")
    try:
        if media_type in {"text/csv", "application/csv"}:
            return CsvAdapter().parse(path, source_id)
        if media_type == "application/json":
            metadata = source.get("metadata")
            pointer = (
                metadata.get("records_pointer", "")
                if isinstance(metadata, Mapping)
                else ""
            )
            if not isinstance(pointer, str):
                raise IntegrityError("JSON records pointer must be a string")
            return JsonAdapter(records_pointer=pointer).parse(path, source_id)
        if media_type == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            return XlsxAdapter().parse(path, source_id)
    except ContractError as error:
        raise IntegrityError(
            f"Source cannot be reparsed safely: {source_id}: {error}"
        ) from error
    raise IntegrityError(f"unsupported preview media type: {media_type}")


def _find_record(dataset: ParsedDataset, source_ref: Mapping[str, Any]) -> ParsedRecord:
    locator_type = source_ref.get("locator_type")
    locator = source_ref.get("locator")
    for record in dataset.records:
        if record.locator_type == locator_type and record.locator == locator:
            return record
    raise IntegrityError(
        f"Source locator does not resolve: {source_ref.get('extraction_hash')}"
    )


def _verify_extraction(
    dataset: ParsedDataset,
    source_ref: Mapping[str, Any],
) -> ParsedRecord:
    record = _find_record(dataset, source_ref)
    selected_fields = source_ref.get("selected_fields")
    if not isinstance(selected_fields, list) or any(
        not isinstance(field, str) or not field for field in selected_fields
    ):
        raise IntegrityError("Source extraction selected_fields are invalid")
    if any(field not in record.values for field in selected_fields):
        raise IntegrityError("Source extraction selects an unknown field")
    try:
        recomputed = dataset.source_reference(
            record,
            selected_fields,
            str(source_ref.get("operation")),
            str(source_ref.get("lineage_set_ref")),
            observation_role=str(source_ref.get("observation_role")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IntegrityError("Source extraction cannot be recomputed") from error
    def native_integral_numbers(value: Any) -> Any:
        if isinstance(value, Decimal) and value == value.to_integral_value():
            return int(value)
        if isinstance(value, Mapping):
            return {
                str(key): native_integral_numbers(child)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [native_integral_numbers(child) for child in value]
        return value

    if canonical_bytes(recomputed) != canonical_bytes(
        native_integral_numbers(dict(source_ref))
    ):
        raise IntegrityError(
            f"Source extraction hash mismatch: {source_ref.get('extraction_hash')}"
        )
    return record


def _safe_scalar(value: Any) -> str | int | bool | None:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise IntegrityError("Source preview contains a non-finite number")
        if value == value.to_integral_value():
            return int(value)
        return canonical_decimal(value)
    if isinstance(value, float):
        raise IntegrityError("binary floating point is forbidden in Source preview")
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("=", "@")):
            return None
        if re.match(r"^[+-](?![0-9.])", stripped):
            return None
        return value
    raise IntegrityError(f"unsupported Source preview value: {type(value).__name__}")


def _locator(source_ref: Mapping[str, Any]) -> dict[str, Any]:
    locator_type = source_ref["locator_type"]
    locator = source_ref["locator"]
    if not isinstance(locator, Mapping):
        raise IntegrityError("Source locator must be an object")
    return {
        "locator_type": locator_type,
        "record_indices": (
            list(locator.get("record_indices", []))
            if locator_type == "csv_records"
            else []
        ),
        "json_pointer": (
            locator.get("pointer") if locator_type == "json_pointer" else None
        ),
        "sheet": locator.get("sheet") if locator_type == "xlsx_cells" else None,
        "cell_range": (
            locator.get("range") if locator_type == "xlsx_cells" else None
        ),
    }


def _display_locator(source_ref: Mapping[str, Any]) -> str:
    locator = source_ref["locator"]
    locator_type = source_ref["locator_type"]
    if locator_type == "csv_records":
        indices = ",".join(str(item) for item in locator["record_indices"])
        return f"레코드 {indices}"
    if locator_type == "json_pointer":
        return f"json-pointer:{locator['pointer']}"
    if locator_type == "xlsx_cells":
        return f"{locator['sheet']}!{locator['range']}"
    raise IntegrityError(f"unsupported Source locator type: {locator_type}")


def _official_url(source: Mapping[str, Any]) -> str | None:
    if source.get("source_type") != "official_external":
        return None
    metadata = source.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    candidate = metadata.get("official_url", metadata.get("url"))
    if not isinstance(candidate, str):
        return None
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
    ):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _preview(
    source: Mapping[str, Any],
    source_ref: Mapping[str, Any],
    record: ParsedRecord,
) -> dict[str, Any]:
    source_id = str(source["source_id"])
    extraction_hash = str(source_ref["extraction_hash"])
    access_policy = str(source["access_policy"])
    selected_fields = sorted(set(source_ref["selected_fields"]))
    permitted = access_policy == "permitted"
    preview = {
        "preview_ref": make_id(
            "preview",
            {
                "source_id": source_id,
                "extraction_hash": extraction_hash,
            },
        ),
        "source_ref": source_id,
        "locator": _locator(source_ref),
        "column_labels": selected_fields if permitted else [],
        "rows": (
            [[_safe_scalar(record.values[field]) for field in selected_fields]]
            if permitted
            else []
        ),
        "truncated": False,
        "truncation_reason": None,
        "masking_status": "none" if permitted else access_policy,
        "access_policy": access_policy,
        "preview_hash": "0" * 64,
    }
    preview["preview_hash"] = jcs_sha256(
        preview,
        omit_root_field="preview_hash",
    )
    return preview


def _truncate_preview(preview: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(preview)
    result.update(
        {
            "column_labels": [],
            "rows": [],
            "truncated": True,
            "truncation_reason": "bundle_preview_budget",
            "masking_status": "truncated",
            "preview_hash": "0" * 64,
        }
    )
    result["preview_hash"] = jcs_sha256(
        result,
        omit_root_field="preview_hash",
    )
    return result


def build_source_views(
    snapshot_root: Path,
    closure: EvidenceClosure,
    *,
    max_preview_bytes: int = MAX_PREVIEW_BYTES,
) -> SourceViews:
    if max_preview_bytes < 1:
        raise ValueError("max_preview_bytes must be positive")
    sources = _source_index(closure)
    refs_by_source = _source_references(closure)
    unknown_sources = set(refs_by_source) - set(sources)
    if unknown_sources:
        raise IntegrityError(f"unknown Source: {sorted(unknown_sources)[0]}")

    previews: list[dict[str, Any]] = []
    source_views: list[dict[str, Any]] = []
    for source_id in sorted(sources):
        source = sources[source_id]
        refs = refs_by_source.get(source_id, {})
        if not refs:
            raise IntegrityError(f"Source has no closed extraction: {source_id}")
        path = _verify_blob(snapshot_root, source)
        dataset = _parse_dataset(path, source)
        source_preview_refs: list[str] = []
        locator_summaries: list[dict[str, Any]] = []
        for extraction_hash in sorted(refs):
            source_ref = refs[extraction_hash]
            record = _verify_extraction(dataset, source_ref)
            preview = _preview(source, source_ref, record)
            previews.append(preview)
            source_preview_refs.append(preview["preview_ref"])
            locator_summaries.append(
                {
                    "locator_type": source_ref["locator_type"],
                    "display_locator": _display_locator(source_ref),
                    "extraction_hash": extraction_hash,
                }
            )
        source_views.append(
            {
                "source_ref": source_id,
                "display_name_ko": str(source["display_name"]),
                "snapshot_locator": str(source["snapshot_ref"]),
                "extraction_hashes": sorted(refs),
                "locator_summaries": sorted(
                    locator_summaries,
                    key=lambda item: (
                        item["extraction_hash"],
                        item["display_locator"],
                    ),
                ),
                "access_policy": source["access_policy"],
                "official_url": _official_url(source),
                "preview_refs": sorted(source_preview_refs),
            }
        )

    bounded: list[dict[str, Any]] = []
    used = 0
    for preview in sorted(previews, key=lambda item: item["preview_ref"]):
        candidate = preview
        candidate_size = len(jcs_bytes(candidate))
        if used + candidate_size > max_preview_bytes:
            if preview["access_policy"] != "permitted":
                raise IntegrityError("masked Source preview metadata exceeds budget")
            candidate = _truncate_preview(preview)
            candidate_size = len(jcs_bytes(candidate))
        if used + candidate_size > max_preview_bytes:
            raise IntegrityError("Source preview metadata exceeds bundle budget")
        bounded.append(candidate)
        used += candidate_size

    return SourceViews(
        sources=tuple(source_views),
        previews=tuple(bounded),
    )
