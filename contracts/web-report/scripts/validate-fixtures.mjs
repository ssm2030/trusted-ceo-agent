import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";


const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const contractRoot = resolve(scriptDirectory, "..", "v1");
const fixtureRoot = resolve(contractRoot, "fixtures");

function canonicalize(value) {
  if (
    value === null ||
    typeof value === "boolean" ||
    typeof value === "number" ||
    typeof value === "string"
  ) {
    if (typeof value === "number" && !Number.isFinite(value)) {
      throw new TypeError("non-finite JSON number is forbidden");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`)
    .join(",")}}`;
}

function jcsHash(value, omittedRootField) {
  const body = structuredClone(value);
  if (omittedRootField !== undefined) {
    delete body[omittedRootField];
  }
  return createHash("sha256").update(canonicalize(body), "utf8").digest("hex");
}

function indexBy(items, field, label) {
  const result = new Map();
  for (const item of items) {
    const identifier = item[field];
    if (result.has(identifier)) {
      throw new Error(`duplicate ${label}: ${identifier}`);
    }
    result.set(identifier, item);
  }
  return result;
}

function requireRef(index, reference, label) {
  if (!index.has(reference)) {
    throw new Error(`unknown ${label}: ${reference}`);
  }
}

function requireRefs(index, references, label) {
  for (const reference of references) {
    requireRef(index, reference, label);
  }
}

function validateSemantic(bundle) {
  const issues = indexBy(bundle.final_result.issues, "issue_id", "issue");
  const relations = indexBy(
    bundle.final_result.cross_issue_relations,
    "relation_id",
    "relation",
  );
  const responses = indexBy(
    bundle.final_result.conditional_responses,
    "response_id",
    "response",
  );
  const packets = indexBy(
    bundle.expert_packet_view,
    "expert_packet_id",
    "expert packet",
  );
  const publicPackets = indexBy(
    bundle.final_result.expert_review_packets,
    "expert_packet_id",
    "public expert packet",
  );
  const facts = indexBy(bundle.evidence_view.facts, "fact_id", "Fact");
  const signals = indexBy(bundle.evidence_view.signals, "signal_id", "Signal");
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
  indexBy(
    bundle.trust_view.trust_events,
    "event_id",
    "Trust Event",
  );
  indexBy(bundle.presentation_manifest.metric_cards, "metric_card_id", "metric card");
  const charts = indexBy(
    bundle.presentation_manifest.chart_specs,
    "chart_id",
    "chart",
  );

  for (const issue of issues.values()) {
    requireRefs(evidenceLinks, issue.evidence_link_ids, "Evidence Link");
    for (const valueRef of issue.value_refs) {
      if (!facts.has(valueRef) && !signals.has(valueRef)) {
        throw new Error(`unknown value reference: ${valueRef}`);
      }
    }
    requireRefs(responses, issue.conditional_response_refs, "response");
    requireRefs(publicPackets, issue.expert_review_refs, "public expert packet");
  }
  for (const relation of relations.values()) {
    requireRef(issues, relation.from_issue_ref, "issue");
    requireRef(issues, relation.to_issue_ref, "issue");
  }
  for (const fact of facts.values()) {
    for (const sourceRef of fact.source_refs) {
      requireRef(sources, sourceRef.source_id, "Source");
    }
    if (fact.derivation !== null) {
      requireRefs(facts, fact.derivation.input_fact_ids, "Fact");
    }
  }
  for (const signal of signals.values()) {
    requireRefs(facts, signal.input_fact_ids, "Fact");
  }
  for (const link of evidenceLinks.values()) {
    const evidenceIndex = link.evidence_kind === "fact" ? facts : signals;
    requireRef(evidenceIndex, link.evidence_ref, link.evidence_kind);
    if (link.target_type === "integrated_issue") {
      requireRef(issues, link.target_ref, "issue");
    }
    for (const valueRef of link.value_refs) {
      if (
        !facts.has(valueRef.fact_or_signal_id) &&
        !signals.has(valueRef.fact_or_signal_id)
      ) {
        throw new Error(
          `unknown Evidence Link value: ${valueRef.fact_or_signal_id}`,
        );
      }
    }
  }
  for (const source of sources.values()) {
    for (const previewRef of source.preview_refs) {
      const preview = previews.get(previewRef);
      if (preview === undefined) {
        throw new Error(`unknown Source Preview: ${previewRef}`);
      }
      if (preview.source_ref !== source.source_ref) {
        throw new Error(`Source Preview backlink mismatch: ${previewRef}`);
      }
    }
  }
  for (const preview of previews.values()) {
    requireRef(sources, preview.source_ref, "Source");
    if (
      preview.access_policy !== "permitted" &&
      (preview.column_labels.length !== 0 || preview.rows.length !== 0)
    ) {
      throw new Error(`masked Source Preview contains values: ${preview.preview_ref}`);
    }
    if (preview.preview_hash !== jcsHash(preview, "preview_hash")) {
      throw new Error(`preview hash mismatch: ${preview.preview_ref}`);
    }
  }
  for (const issueRef of bundle.presentation_manifest.ceo_summary_issue_refs) {
    requireRef(issues, issueRef, "issue");
  }
  for (const card of bundle.presentation_manifest.metric_cards) {
    requireRef(issues, card.issue_ref, "issue");
    if (!facts.has(card.value_ref) && !signals.has(card.value_ref)) {
      throw new Error(`unknown metric value reference: ${card.value_ref}`);
    }
  }
  for (const chart of charts.values()) {
    requireRefs(issues, chart.issue_refs, "issue");
    requireRefs(facts, chart.fact_refs, "Fact");
    requireRefs(signals, chart.signal_refs, "Signal");
    indexBy(chart.points, "point_id", "chart point");
    for (const point of chart.points) {
      requireRef(facts, point.fact_id, "Fact");
      requireRefs(evidenceLinks, point.evidence_link_ids, "Evidence Link");
    }
  }
  for (const closure of bundle.evidence_view.issue_claim_closure) {
    requireRef(issues, closure.issue_ref, "issue");
    requireRefs(evidenceLinks, closure.evidence_link_ids, "Evidence Link");
    requireRefs(facts, closure.fact_refs, "Fact");
    requireRefs(signals, closure.signal_refs, "Signal");
    requireRefs(sources, closure.source_refs, "Source");
    requireRefs(packets, closure.expert_packet_refs, "expert packet");
  }
  for (const packet of packets.values()) {
    requireRef(issues, packet.target_issue_ref, "issue");
    requireRefs(facts, packet.fact_refs, "Fact");
    requireRefs(evidenceLinks, packet.evidence_link_ids, "Evidence Link");
    requireRefs(sources, packet.source_refs, "Source");
    if (packet.packet_hash !== jcsHash(packet, "packet_hash")) {
      throw new Error(`packet hash mismatch: ${packet.expert_packet_id}`);
    }
  }

  const previewBytes = Buffer.byteLength(
    bundle.source_previews.map(canonicalize).join(""),
    "utf8",
  );
  if (previewBytes > 10_485_760) {
    throw new Error(`source preview budget exceeded: ${previewBytes}`);
  }
  if (bundle.bundle_hash !== jcsHash(bundle, "bundle_hash")) {
    throw new Error("bundle hash mismatch");
  }

  const serialized = JSON.stringify(bundle);
  if (
    /(?:[A-Za-z]:[\\/]|file:\/\/|\/Users\/|\/home\/|\\\\[^\\]+\\[^\\]+)/.test(
      serialized,
    )
  ) {
    throw new Error("absolute path leak");
  }
}

const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
addFormats(ajv);
for (const name of (await readdir(contractRoot)).filter((item) =>
  item.endsWith(".schema.json"),
)) {
  ajv.addSchema(
    JSON.parse(await readFile(join(contractRoot, name), "utf8")),
    name,
  );
}
const validateSchema = ajv.getSchema("web-report-bundle.schema.json");
if (validateSchema === undefined) {
  throw new Error("web-report-bundle.schema.json did not compile");
}

function validateDocument(document) {
  if (!validateSchema(document)) {
    throw new Error(ajv.errorsText(validateSchema.errors));
  }
  validateSemantic(document);
}

for (const name of [
  "valid-trusted.json",
  "valid-poc.json",
  "valid-unverified-import.json",
]) {
  validateDocument(JSON.parse(await readFile(join(fixtureRoot, name), "utf8")));
}

const invalidExpectations = new Map([
  ["invalid-hash.json", /bundle hash mismatch/],
  ["invalid-reference.json", /unknown Evidence Link/],
]);
for (const [name, expected] of invalidExpectations) {
  const document = JSON.parse(await readFile(join(fixtureRoot, name), "utf8"));
  try {
    validateDocument(document);
    throw new Error(`${name} unexpectedly passed`);
  } catch (error) {
    if (!expected.test(String(error.message))) {
      throw error;
    }
  }
}

const oversize = JSON.parse(
  await readFile(join(fixtureRoot, "oversize.json"), "utf8"),
);
if (
  oversize.fixture_kind !== "generated_oversize" ||
  oversize.target_bytes !== 52_428_801
) {
  throw new Error("oversize descriptor is invalid");
}

console.log("web report contract fixtures validated");
