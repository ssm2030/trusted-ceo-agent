import { createHash } from "node:crypto";

import type { WebReportBundleV1 } from "../../../../contracts/web-report/v1/generated/types";
import { canonicalize } from "json-canonicalize";

import {
  MAX_SOURCE_PREVIEW_JCS_BYTES,
  WebReportValidationError,
  assertNoAbsolutePaths,
} from "@/lib/server/bundle-document-policy";

function jcsHash(value: object, omittedRootField?: string): string {
  const body = structuredClone(value) as Record<string, unknown>;
  if (omittedRootField !== undefined) {
    delete body[omittedRootField];
  }
  return createHash("sha256")
    .update(canonicalize(body), "utf8")
    .digest("hex");
}

function indexBy<T, K extends keyof T>(
  items: readonly T[],
  field: K,
  label: string,
  requireSorted = false,
): Map<string, T> {
  const result = new Map<string, T>();
  const identifiers: string[] = [];
  for (const item of items) {
    const identifier = item[field];
    if (typeof identifier !== "string" || identifier.length === 0) {
      throw new WebReportValidationError(`invalid ${label} ID`);
    }
    if (result.has(identifier)) {
      throw new WebReportValidationError(
        `duplicate ${label}: ${identifier}`,
      );
    }
    result.set(identifier, item);
    identifiers.push(identifier);
  }
  if (
    requireSorted &&
    identifiers.some(
      (identifier, index) => index > 0 && identifiers[index - 1] > identifier,
    )
  ) {
    throw new WebReportValidationError(`${label} IDs must be sorted`);
  }
  return result;
}

function requireRefs(
  index: ReadonlyMap<string, unknown>,
  references: readonly string[],
  label: string,
): void {
  for (const reference of references) {
    if (!index.has(reference)) {
      throw new WebReportValidationError(
        `unknown ${label}: ${reference}`,
      );
    }
  }
}

export function validateBundleSemantics(bundle: WebReportBundleV1): void {
  const issues = indexBy(
    bundle.final_result.issues,
    "issue_id",
    "issue",
  );
  const relations = indexBy(
    bundle.final_result.cross_issue_relations,
    "relation_id",
    "relation",
  );
  const responses = indexBy(
    bundle.final_result.conditional_responses,
    "response_id",
    "conditional response",
  );
  const publicPackets = indexBy(
    bundle.final_result.expert_review_packets,
    "expert_packet_id",
    "public expert packet",
  );
  const packets = indexBy(
    bundle.expert_packet_view,
    "expert_packet_id",
    "expert packet",
  );
  const facts = indexBy(bundle.evidence_view.facts, "fact_id", "Fact");
  const signals = indexBy(
    bundle.evidence_view.signals,
    "signal_id",
    "Signal",
  );
  const evidenceLinks = indexBy(
    bundle.evidence_view.evidence_links,
    "evidence_link_id",
    "Evidence Link",
  );
  const sources = indexBy(bundle.source_view, "source_ref", "Source");
  const previews = indexBy(
    bundle.source_previews,
    "preview_ref",
    "Source Preview",
  );
  const charts = indexBy(
    bundle.presentation_manifest.chart_specs,
    "chart_id",
    "chart",
  );
  const graphNodes = indexBy(
    bundle.presentation_manifest.issue_graph.nodes,
    "issue_ref",
    "issue graph node",
    true,
  );
  if (graphNodes.size !== issues.size) {
    throw new WebReportValidationError(
      "issue graph nodes do not exactly match Final Result issues",
    );
  }
  for (const [issueId, node] of graphNodes) {
    const issue = issues.get(issueId);
    if (
      issue === undefined ||
      node.label_ko !== issue.title_template ||
      node.grade !== issue.primary_grade
    ) {
      throw new WebReportValidationError(
        `issue graph node differs from Final Result issue: ${issueId}`,
      );
    }
  }
  const graphEdges = indexBy(
    bundle.presentation_manifest.issue_graph.edges,
    "relation_id",
    "issue graph edge",
    true,
  );
  if (graphEdges.size !== relations.size) {
    throw new WebReportValidationError(
      "issue graph edges do not exactly match Final Result relations",
    );
  }
  for (const [relationId, edge] of graphEdges) {
    const relation = relations.get(relationId);
    if (
      relation === undefined ||
      edge.from_issue_ref !== relation.from_issue_ref ||
      edge.to_issue_ref !== relation.to_issue_ref ||
      edge.relation_type !== relation.relation_type
    ) {
      throw new WebReportValidationError(
        `issue graph edge differs from Final Result relation: ${relationId}`,
      );
    }
  }

  for (const issue of issues.values()) {
    requireRefs(evidenceLinks, issue.evidence_link_ids, "Evidence Link");
    for (const valueReference of issue.value_refs) {
      if (!facts.has(valueReference) && !signals.has(valueReference)) {
        throw new WebReportValidationError(
          `unknown value reference: ${valueReference}`,
        );
      }
    }
    requireRefs(
      responses,
      issue.conditional_response_refs,
      "conditional response",
    );
    requireRefs(
      publicPackets,
      issue.expert_review_refs,
      "public expert packet",
    );
  }
  for (const relation of relations.values()) {
    requireRefs(
      issues,
      [relation.from_issue_ref, relation.to_issue_ref],
      "issue",
    );
  }
  for (const fact of facts.values()) {
    for (const sourceReference of fact.source_refs) {
      requireRefs(sources, [sourceReference.source_id], "Source");
    }
    if (fact.derivation !== null) {
      requireRefs(facts, fact.derivation.input_fact_ids, "Fact");
    }
  }
  for (const signal of signals.values()) {
    requireRefs(facts, signal.input_fact_ids, "Fact");
  }
  for (const link of evidenceLinks.values()) {
    requireRefs(
      link.evidence_kind === "fact" ? facts : signals,
      [link.evidence_ref],
      link.evidence_kind,
    );
    for (const valueReference of link.value_refs) {
      if (
        !facts.has(valueReference.fact_or_signal_id) &&
        !signals.has(valueReference.fact_or_signal_id)
      ) {
        throw new WebReportValidationError(
          `unknown Evidence Link value: ${valueReference.fact_or_signal_id}`,
        );
      }
    }
  }
  const referencedPreviews = new Set<string>();
  for (const source of sources.values()) {
    for (const previewReference of source.preview_refs) {
      const preview = previews.get(previewReference);
      if (preview === undefined) {
        throw new WebReportValidationError(
          `unknown Source Preview: ${previewReference}`,
        );
      }
      if (
        preview.source_ref !== source.source_ref ||
        preview.access_policy !== source.access_policy
      ) {
        throw new WebReportValidationError(
          `Source Preview backlink mismatch: ${previewReference}`,
        );
      }
      referencedPreviews.add(previewReference);
    }
  }
  let previewBytes = 0;
  for (const preview of previews.values()) {
    requireRefs(sources, [preview.source_ref], "Source");
    if (!referencedPreviews.has(preview.preview_ref)) {
      throw new WebReportValidationError(
        `unreferenced Source Preview: ${preview.preview_ref}`,
      );
    }
    if (
      preview.access_policy !== "permitted" &&
      (preview.column_labels.length !== 0 || preview.rows.length !== 0)
    ) {
      throw new WebReportValidationError(
        `masked Source Preview contains values: ${preview.preview_ref}`,
      );
    }
    if (preview.preview_hash !== jcsHash(preview, "preview_hash")) {
      throw new WebReportValidationError(
        `preview hash mismatch: ${preview.preview_ref}`,
      );
    }
    previewBytes += Buffer.byteLength(canonicalize(preview), "utf8");
  }
  if (previewBytes > MAX_SOURCE_PREVIEW_JCS_BYTES) {
    throw new WebReportValidationError(
      `source preview budget exceeded: ${previewBytes}`,
    );
  }
  requireRefs(
    issues,
    bundle.presentation_manifest.ceo_summary_issue_refs,
    "issue",
  );
  for (const card of bundle.presentation_manifest.metric_cards) {
    requireRefs(issues, [card.issue_ref], "issue");
    if (!facts.has(card.value_ref) && !signals.has(card.value_ref)) {
      throw new WebReportValidationError(
        `unknown metric value reference: ${card.value_ref}`,
      );
    }
  }
  for (const chart of charts.values()) {
    requireRefs(issues, chart.issue_refs, "issue");
    requireRefs(facts, chart.fact_refs, "Fact");
    requireRefs(signals, chart.signal_refs, "Signal");
    indexBy(chart.points, "point_id", "chart point");
    for (const point of chart.points) {
      requireRefs(facts, [point.fact_id], "Fact");
      requireRefs(
        evidenceLinks,
        point.evidence_link_ids,
        "Evidence Link",
      );
    }
  }
  for (const closure of bundle.evidence_view.issue_claim_closure) {
    requireRefs(issues, [closure.issue_ref], "issue");
    requireRefs(
      evidenceLinks,
      closure.evidence_link_ids,
      "Evidence Link",
    );
    requireRefs(facts, closure.fact_refs, "Fact");
    requireRefs(signals, closure.signal_refs, "Signal");
    requireRefs(sources, closure.source_refs, "Source");
    requireRefs(
      packets,
      closure.expert_packet_refs,
      "expert packet",
    );
  }
  for (const packet of packets.values()) {
    requireRefs(issues, [packet.target_issue_ref], "issue");
    requireRefs(facts, packet.fact_refs, "Fact");
    requireRefs(
      evidenceLinks,
      packet.evidence_link_ids,
      "Evidence Link",
    );
    requireRefs(sources, packet.source_refs, "Source");
    if (packet.packet_hash !== jcsHash(packet, "packet_hash")) {
      throw new WebReportValidationError(
        `expert packet hash mismatch: ${packet.expert_packet_id}`,
      );
    }
  }

  if (bundle.bundle_hash !== jcsHash(bundle, "bundle_hash")) {
    throw new WebReportValidationError("bundle hash mismatch");
  }
  assertNoAbsolutePaths(bundle);
}
