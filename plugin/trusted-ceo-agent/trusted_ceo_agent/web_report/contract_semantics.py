from __future__ import annotations

from typing import Any, Mapping

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.outputs.validation import (
    FinalValidationError,
    validate_no_absolute_paths,
)
from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256


MAX_BUNDLE_BYTES = 52_428_800
MAX_ISSUES = 500
MAX_CHARTS = 50
MAX_CHART_POINTS = 5_000
MAX_PREVIEW_BYTES = 10_485_760


class WebReportContractError(ContractError):
    """A web report does not satisfy the bounded display contract."""

def _index(
    items: list[dict[str, Any]],
    id_field: str,
    label: str,
    *,
    require_sorted: bool = True,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    identifiers: list[str] = []
    for item in items:
        identifier = item[id_field]
        if identifier in indexed:
            raise WebReportContractError(f"duplicate {label} ID: {identifier}")
        indexed[identifier] = item
        identifiers.append(identifier)
    if require_sorted and identifiers != sorted(identifiers):
        raise WebReportContractError(f"{label} IDs must be sorted")
    return indexed


def _require_refs(refs: list[str], known: set[str], label: str) -> None:
    for reference in refs:
        if reference not in known:
            raise WebReportContractError(f"unknown {label}: {reference}")


_SORTED_STRING_SET_KEYS = {
    "available_source_roles",
    "change_categories",
    "completed_checks",
    "extraction_hashes",
    "limitations",
    "missing_fact_codes",
    "missing_source_roles",
    "reason_codes",
    "required_fact_codes",
    "secondary_flags",
    "selected_fields",
    "group_by",
}
_DISPLAY_ORDER_KEYS = {"ceo_summary_issue_refs"}


def _validate_sorted_id_sets(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (
                isinstance(child, list)
                and child
                and all(isinstance(item, str) for item in child)
                and key not in _DISPLAY_ORDER_KEYS
                and (
                    key.endswith("_refs")
                    or key.endswith("_ids")
                    or key in _SORTED_STRING_SET_KEYS
                )
                and child != sorted(child)
            ):
                raise WebReportContractError(f"{key} must be sorted")
            _validate_sorted_id_sets(child)
    elif isinstance(value, list):
        for child in value:
            _validate_sorted_id_sets(child)


def validate_bundle_document(bundle: Mapping[str, Any]) -> None:
    """Validate semantic and integrity constraints not expressible in JSON Schema."""

    result = bundle["final_result"]
    evidence = bundle["evidence_view"]
    presentation = bundle["presentation_manifest"]

    if len(result["issues"]) > MAX_ISSUES:
        raise WebReportContractError("bundle contains more than 500 issues")
    if len(presentation["chart_specs"]) > MAX_CHARTS:
        raise WebReportContractError("bundle contains more than 50 charts")
    for chart in presentation["chart_specs"]:
        if len(chart["points"]) > MAX_CHART_POINTS:
            raise WebReportContractError(
                f"chart {chart['chart_id']} contains more than 5_000 points"
            )

    issues = _index(result["issues"], "issue_id", "issue")
    relations = _index(
        result["cross_issue_relations"],
        "relation_id",
        "relation",
    )
    responses = _index(
        result["conditional_responses"],
        "response_id",
        "response",
    )
    _index(result["monitoring"], "monitor_id", "monitor")
    _index(result["blind_spots"], "blind_spot_id", "blind spot")
    public_packets = _index(
        result["expert_review_packets"],
        "expert_packet_id",
        "public expert packet",
    )
    facts = _index(evidence["facts"], "fact_id", "Fact")
    signals = _index(evidence["signals"], "signal_id", "Signal")
    links = _index(
        evidence["evidence_links"],
        "evidence_link_id",
        "Evidence Link",
    )
    data_quality = _index(
        evidence["data_quality"],
        "quality_issue_id",
        "data quality",
    )
    capabilities = _index(
        evidence["capability_map"]["capabilities"],
        "capability_id",
        "capability",
    )
    claim_closures = _index(
        evidence["issue_claim_closure"],
        "issue_ref",
        "issue claim closure",
    )
    sources = _index(bundle["source_view"], "source_ref", "Source")
    previews = _index(
        bundle["source_previews"],
        "preview_ref",
        "source preview",
    )
    packets = _index(
        bundle["expert_packet_view"],
        "expert_packet_id",
        "expert packet",
    )
    _index(
        bundle["trust_view"]["trust_events"],
        "event_id",
        "trust event",
        require_sorted=False,
    )
    _index(bundle["trust_view"]["file_hashes"], "logical_path", "file hash")
    _index(bundle["file_manifest"], "logical_path", "file manifest entry")
    metric_cards = _index(
        presentation["metric_cards"],
        "metric_card_id",
        "metric card",
        require_sorted=False,
    )
    charts = _index(
        presentation["chart_specs"],
        "chart_id",
        "chart",
        require_sorted=False,
    )
    for chart in charts.values():
        _index(
            chart["points"],
            "point_id",
            "chart point",
            require_sorted=False,
        )

    _validate_sorted_id_sets(bundle)

    run = bundle["run"]
    receipt = bundle["viewer_eligibility_receipt"]
    run_summary = result["run_summary"]
    revision_view = bundle["revision_view"]
    if receipt["run_id"] != run["run_id"] or run_summary["run_id"] != run["run_id"]:
        raise WebReportContractError("run ID mismatch")
    if (
        receipt["finalized_revision"] != run["revision"]
        or run_summary["revision"] != run["revision"]
        or revision_view["compare_revision"] != run["revision"]
    ):
        raise WebReportContractError("revision mismatch")
    if (
        result["integrity"]["semantic_fingerprint"]
        != run["semantic_fingerprint"]
        or revision_view["current_semantic_fingerprint"]
        != run["semantic_fingerprint"]
    ):
        raise WebReportContractError("semantic fingerprint mismatch")

    issue_ids = set(issues)
    relation_ids = set(relations)
    response_ids = set(responses)
    packet_ids = set(public_packets) | set(packets)
    fact_ids = set(facts)
    signal_ids = set(signals)
    evidence_ids = set(links)
    source_ids = set(sources)
    preview_ids = set(previews)
    quality_ids = set(data_quality)
    value_ids = fact_ids | signal_ids
    claim_ids = {
        claim["claim_code"]
        for issue in issues.values()
        for field in ("cause_hypotheses", "counter_hypotheses")
        for claim in issue[field]
    }
    for issue in issues.values():
        _require_refs(issue["evidence_link_ids"], evidence_ids, "Evidence Link")
        _require_refs(issue["value_refs"], value_ids, "value reference")
        _require_refs(
            issue["conditional_response_refs"],
            response_ids,
            "conditional response",
        )
        _require_refs(issue["expert_review_refs"], packet_ids, "expert packet")

    for relation in relations.values():
        _require_refs(
            [relation["from_issue_ref"], relation["to_issue_ref"]],
            issue_ids,
            "issue reference",
        )

    target_refs = issue_ids | relation_ids | response_ids | packet_ids | claim_ids
    for link in links.values():
        if link["target_ref"] not in target_refs:
            raise WebReportContractError(
                f"unknown evidence target reference: {link['target_ref']}"
            )
        expected = facts if link["evidence_kind"] == "fact" else signals
        if link["evidence_ref"] not in expected:
            raise WebReportContractError(
                f"unknown evidence reference: {link['evidence_ref']}"
            )
        for value_ref in link["value_refs"]:
            if value_ref["fact_or_signal_id"] not in value_ids:
                raise WebReportContractError(
                    f"unknown value reference: {value_ref['fact_or_signal_id']}"
                )

    for signal in signals.values():
        _require_refs(signal["input_fact_ids"], fact_ids, "input Fact")

    for fact in facts.values():
        derivation = fact["derivation"]
        if derivation is not None:
            _require_refs(derivation["input_fact_ids"], fact_ids, "input Fact")
        _require_refs(fact["quality"], quality_ids, "data quality")
        for source_ref in fact["source_refs"]:
            source_id = source_ref["source_id"]
            if source_id not in source_ids:
                raise WebReportContractError(f"unknown Source: {source_id}")

    for quality in data_quality.values():
        source_ref = quality["source_ref"]
        if source_ref is not None:
            _require_refs([source_ref], source_ids, "Source")
    for capability in capabilities.values():
        _require_refs(
            capability["quality_issue_ids"],
            quality_ids,
            "data quality",
        )

    referenced_previews: set[str] = set()
    for source in sources.values():
        for preview_ref in source["preview_refs"]:
            if preview_ref not in preview_ids:
                raise WebReportContractError(
                    f"unknown source preview: {preview_ref}"
                )
            preview = previews[preview_ref]
            if preview["source_ref"] != source["source_ref"]:
                raise WebReportContractError(
                    f"source preview points to another Source: {preview_ref}"
                )
            if preview["access_policy"] != source["access_policy"]:
                raise WebReportContractError(
                    f"source preview access policy mismatch: {preview_ref}"
                )
            referenced_previews.add(preview_ref)
    for preview in previews.values():
        if preview["source_ref"] not in source_ids:
            raise WebReportContractError(
                f"unknown Source: {preview['source_ref']}"
            )
        if preview["preview_ref"] not in referenced_previews:
            raise WebReportContractError(
                "source preview is not referenced by its Source: "
                f"{preview['preview_ref']}"
            )
        if preview["access_policy"] in {"restricted", "prohibited"} and (
            preview["column_labels"] or preview["rows"]
        ):
            raise WebReportContractError(
                f"{preview['access_policy']} preview must not embed values: "
                f"{preview['preview_ref']}"
            )

    _require_refs(
        presentation["ceo_summary_issue_refs"],
        issue_ids,
        "issue reference",
    )
    for card in metric_cards.values():
        _require_refs([card["issue_ref"]], issue_ids, "issue reference")
        _require_refs([card["value_ref"]], value_ids, "value reference")
    for chart in charts.values():
        _require_refs(chart["issue_refs"], issue_ids, "issue reference")
        _require_refs(chart["fact_refs"], fact_ids, "Fact")
        _require_refs(chart["signal_refs"], signal_ids, "Signal")
        for point in chart["points"]:
            _require_refs([point["fact_id"]], fact_ids, "Fact")
            _require_refs([point["value_ref"]], value_ids, "value reference")
            _require_refs(
                point["evidence_link_ids"],
                evidence_ids,
                "Evidence Link",
            )
    graph_nodes = _index(
        presentation["issue_graph"]["nodes"],
        "issue_ref",
        "issue graph node",
    )
    if set(graph_nodes) != issue_ids:
        raise WebReportContractError(
            "issue graph nodes do not exactly match Final Result issues"
        )
    for issue_id, node in graph_nodes.items():
        issue = issues[issue_id]
        if (
            node["label_ko"] != issue["title_template"]
            or node["grade"] != issue["primary_grade"]
        ):
            raise WebReportContractError(
                f"issue graph node differs from Final Result issue: {issue_id}"
            )
    graph_edges = _index(
        presentation["issue_graph"]["edges"],
        "relation_id",
        "issue graph edge",
    )
    if set(graph_edges) != relation_ids:
        raise WebReportContractError(
            "issue graph edges do not exactly match Final Result relations"
        )
    for relation_id, edge in graph_edges.items():
        relation = relations[relation_id]
        if any(edge[field] != relation[field] for field in (
            "from_issue_ref", "to_issue_ref", "relation_type",
        )):
            raise WebReportContractError(
                f"issue graph edge differs from Final Result relation: {relation_id}"
            )
    for node in presentation["issue_graph"]["nodes"]:
        _require_refs([node["issue_ref"]], issue_ids, "issue reference")
    for edge in presentation["issue_graph"]["edges"]:
        _require_refs(
            [edge["from_issue_ref"], edge["to_issue_ref"]],
            issue_ids,
            "issue reference",
        )
        _require_refs([edge["relation_id"]], relation_ids, "relation")

    for closure in claim_closures.values():
        _require_refs([closure["issue_ref"]], issue_ids, "issue reference")
        _require_refs(closure["claim_refs"], claim_ids, "claim reference")
        _require_refs(
            closure["evidence_link_ids"],
            evidence_ids,
            "Evidence Link",
        )
        _require_refs(closure["fact_refs"], fact_ids, "Fact")
        _require_refs(closure["signal_refs"], signal_ids, "Signal")
        _require_refs(closure["source_refs"], source_ids, "Source")
        _require_refs(
            closure["expert_packet_refs"],
            packet_ids,
            "expert packet",
        )

    for packet in packets.values():
        if packet["run_id"] != run["run_id"]:
            raise WebReportContractError("expert packet run ID mismatch")
        if packet["revision"] != run["revision"]:
            raise WebReportContractError("expert packet revision mismatch")
        _require_refs(
            [packet["target_issue_ref"]],
            issue_ids,
            "issue reference",
        )
        _require_refs(packet["fact_refs"], fact_ids, "Fact")
        _require_refs(packet["evidence_link_ids"], evidence_ids, "Evidence Link")
        _require_refs(packet["source_refs"], source_ids, "Source")
        _require_refs(
            packet["cause_hypotheses"],
            claim_ids,
            "claim reference",
        )
        _require_refs(
            packet["counter_hypotheses"],
            claim_ids,
            "claim reference",
        )
        for locator in packet["source_locators"]:
            _require_refs([locator["source_ref"]], source_ids, "Source")
        expected_packet_hash = jcs_sha256(
            packet,
            omit_root_field="packet_hash",
        )
        if packet["packet_hash"] != expected_packet_hash:
            raise WebReportContractError(
                f"expert packet hash mismatch: {packet['expert_packet_id']}"
            )

    for preview in previews.values():
        expected_hash = jcs_sha256(preview, omit_root_field="preview_hash")
        if preview["preview_hash"] != expected_hash:
            raise WebReportContractError(
                f"source preview hash mismatch: {preview['preview_ref']}"
            )
    preview_bytes = sum(len(jcs_bytes(preview)) for preview in previews.values())
    if preview_bytes > MAX_PREVIEW_BYTES:
        raise WebReportContractError(
            f"source previews exceed 10_485_760 JCS bytes: {preview_bytes}"
        )

    expected_bundle_hash = jcs_sha256(bundle, omit_root_field="bundle_hash")
    if bundle["bundle_hash"] != expected_bundle_hash:
        raise WebReportContractError("bundle hash mismatch")

    try:
        validate_no_absolute_paths(bundle)
    except FinalValidationError as error:
        raise WebReportContractError(str(error)) from error
