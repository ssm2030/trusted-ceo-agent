import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type {
  ViewerEligibilityDecisionV1,
  WebReportBundleV1,
} from "../../../../contracts/web-report/v1/generated/types";
import type { AnySchema } from "ajv";
import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { canonicalize } from "json-canonicalize";

import { MAX_REPORT_IMPORT_BYTES } from "@/lib/server/import-policy";

export { MAX_REPORT_IMPORT_BYTES };

export const MAX_REPORT_JSON_DEPTH = 64;
export const MAX_REPORT_ARRAY_ITEMS = 5_000;
const MAX_SOURCE_PREVIEW_JCS_BYTES = 10 * 1024 * 1024;

type ContractValidators = Readonly<{
  bundle: ValidateFunction;
  decision: ValidateFunction;
}>;

let validatorsPromise: Promise<ContractValidators> | undefined;

export class WebReportValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WebReportValidationError";
  }
}

function contractRoot(): string {
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  const candidates = [
    path.resolve(process.cwd(), "contracts/web-report/v1"),
    path.resolve(process.cwd(), "../contracts/web-report/v1"),
    path.resolve(moduleDirectory, "../../../../contracts/web-report/v1"),
  ];
  return candidates[0] === candidates[1]
    ? candidates[0]
    : candidates.find((candidate) =>
        path.isAbsolute(candidate),
      ) ?? candidates[0];
}

async function readSchema(name: string): Promise<AnySchema> {
  const candidates = [
    path.resolve(process.cwd(), "contracts/web-report/v1", name),
    path.resolve(process.cwd(), "../contracts/web-report/v1", name),
    path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../../../contracts/web-report/v1",
      name,
    ),
  ];
  let lastError: unknown;
  for (const candidate of candidates) {
    try {
      return JSON.parse(await readFile(candidate, "utf8")) as AnySchema;
    } catch (error) {
      lastError = error;
    }
  }
  throw new WebReportValidationError(
    `web report contract schema is unavailable under ${contractRoot()}: ${String(lastError)}`,
  );
}

async function contractValidators(): Promise<ContractValidators> {
  validatorsPromise ??= (async () => {
    const ajv = new Ajv2020({
      allErrors: true,
      allowUnionTypes: true,
      strict: true,
    });
    addFormats(ajv);
    const [bundleSchema, decisionSchema, presentationSchema] = await Promise.all([
      readSchema("web-report-bundle.schema.json"),
      readSchema("viewer-eligibility-decision.schema.json"),
      readSchema("presentation-manifest.schema.json"),
    ]);
    ajv.addSchema(presentationSchema);
    const bundle = ajv.compile(bundleSchema);
    const decision = ajv.compile(decisionSchema);
    return Object.freeze({ bundle, decision });
  })();
  return validatorsPromise;
}

function assertBoundedJson(
  value: unknown,
  depth = 0,
  seen = new Set<unknown>(),
): void {
  if (depth > MAX_REPORT_JSON_DEPTH) {
    throw new WebReportValidationError(
      `JSON depth exceeds ${MAX_REPORT_JSON_DEPTH}`,
    );
  }
  if (value === null || typeof value !== "object") {
    return;
  }
  if (seen.has(value)) {
    throw new WebReportValidationError("circular JSON value is forbidden");
  }
  seen.add(value);
  if (Array.isArray(value)) {
    if (value.length > MAX_REPORT_ARRAY_ITEMS) {
      throw new WebReportValidationError(
        `JSON array exceeds ${MAX_REPORT_ARRAY_ITEMS} items`,
      );
    }
    for (const child of value) {
      assertBoundedJson(child, depth + 1, seen);
    }
  } else {
    for (const child of Object.values(value)) {
      assertBoundedJson(child, depth + 1, seen);
    }
  }
  seen.delete(value);
}

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
): Map<string, T> {
  const result = new Map<string, T>();
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

function validateSemantic(bundle: WebReportBundleV1): void {
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
  const serialized = JSON.stringify(bundle);
  if (
    /(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|file:\/\/|\/Users\/|\/home\/|\\\\[^\\]+\\[^\\]+)/.test(
      serialized,
    )
  ) {
    throw new WebReportValidationError("absolute path leak");
  }
}

export async function validateBundleBytes(
  bytes: Uint8Array,
): Promise<WebReportBundleV1> {
  if (bytes.byteLength > MAX_REPORT_IMPORT_BYTES) {
    throw new WebReportValidationError(
      "web report bundle exceeds 52,428,800 bytes",
    );
  }
  let document: unknown;
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    document = JSON.parse(text) as unknown;
  } catch {
    throw new WebReportValidationError("web report bundle JSON is invalid");
  }
  assertBoundedJson(document);
  const validators = await contractValidators();
  if (!validators.bundle(document)) {
    throw new WebReportValidationError(
      `web report bundle schema is invalid: ${validators.bundle.errors?.[0]?.instancePath ?? "/"}`,
    );
  }
  const bundle = document as WebReportBundleV1;
  validateSemantic(bundle);
  return bundle;
}

const DECISION_BADGES = {
  trusted_final: "승인·검증된 실행본",
  poc_fixture: "검증된 POC 시연 실행본",
  unverified_import: "출처 미확인 묶음",
  rejected: "열 수 없는 묶음",
} as const;

export async function validateEligibilityDecision(
  value: unknown,
): Promise<ViewerEligibilityDecisionV1> {
  const validators = await contractValidators();
  if (!validators.decision(value)) {
    throw new WebReportValidationError(
      "viewer eligibility decision schema is invalid",
    );
  }
  const decision = value as ViewerEligibilityDecisionV1;
  if (decision.badge_label_ko !== DECISION_BADGES[decision.viewer_mode]) {
    throw new WebReportValidationError(
      "viewer eligibility badge label mismatch",
    );
  }
  if (
    (decision.viewer_mode === "rejected" &&
      (decision.eligible ||
        decision.failure_code === null ||
        decision.failure_message === null)) ||
    (decision.viewer_mode !== "rejected" &&
      (!decision.eligible ||
        decision.failure_code !== null ||
        decision.failure_message !== null))
  ) {
    throw new WebReportValidationError(
      "viewer eligibility decision is inconsistent",
    );
  }
  return decision;
}
