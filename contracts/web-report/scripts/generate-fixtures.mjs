import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";


const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const fixtureRoot = resolve(scriptDirectory, "..", "v1", "fixtures");
const trustedPath = resolve(fixtureRoot, "valid-trusted.json");

function canonicalize(value) {
  if (value === null || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("non-finite JSON number is forbidden");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }
  if (typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`)
      .join(",")}}`;
  }
  throw new TypeError(`unsupported JSON value: ${typeof value}`);
}

function sha256(value, omittedRootField) {
  const body = structuredClone(value);
  if (omittedRootField !== undefined) {
    delete body[omittedRootField];
  }
  return createHash("sha256").update(canonicalize(body), "utf8").digest("hex");
}

function finalized(bundle) {
  const result = structuredClone(bundle);
  for (const preview of result.source_previews) {
    preview.preview_hash = sha256(preview, "preview_hash");
  }
  result.bundle_hash = sha256(result, "bundle_hash");
  return result;
}

function approval({
  inputMethod,
  fixtureOnly,
  approvalId,
  actorRole = "ceo",
  resultArtifactRef = "revisions/2/final/result.json",
}) {
  return {
    gate: inputMethod === null ? null : "final",
    status: inputMethod === null ? null : "current",
    input_method: inputMethod,
    fixture_only: fixtureOnly,
    approval_id: approvalId,
    actor_role: actorRole,
    result_artifact_ref: resultArtifactRef,
  };
}

const trustedSource = JSON.parse(await readFile(trustedPath, "utf8"));
const trusted = finalized(trustedSource);

const poc = structuredClone(trusted);
const pocApproval = approval({
  inputMethod: "test_fixture",
  fixtureOnly: true,
  approvalId: "approval_fixture",
});
poc.viewer_eligibility_receipt.claimed_viewer_mode = "poc_fixture";
poc.viewer_eligibility_receipt.final_approval_summary = pocApproval;
poc.final_result.approvals = [pocApproval];
poc.trust_view.approval_summary = [pocApproval];
poc.trust_view.trust_events = [
  {
    event_id: "event_fixture",
    revision: 2,
    command: "poc-fixture",
    actor_kind: "runtime",
    gate: "final",
    sequence: 1,
    timestamp: null,
    invalidated_approval_refs: [],
  },
];
poc.trust_view.deidentification = {
  poc_only: true,
  direct_identifiers_removed: true,
  notice_ko: "검증된 POC 시연 실행본이며 실제 고객 승인 실행본이 아닙니다.",
};
const validPoc = finalized(poc);

const unverified = structuredClone(trusted);
const emptyApproval = approval({
  inputMethod: null,
  fixtureOnly: null,
  approvalId: null,
  actorRole: null,
  resultArtifactRef: null,
});
unverified.viewer_eligibility_receipt.claimed_viewer_mode = "unverified_import";
unverified.viewer_eligibility_receipt.approved_revision = null;
unverified.viewer_eligibility_receipt.snapshot_manifest_hash = null;
unverified.viewer_eligibility_receipt.final_result_hash = null;
unverified.viewer_eligibility_receipt.result_artifact_ref = null;
unverified.viewer_eligibility_receipt.revision_ancestry_hash = null;
unverified.viewer_eligibility_receipt.completed_checks = [];
unverified.viewer_eligibility_receipt.final_approval_summary = emptyApproval;
unverified.final_result.approvals = [emptyApproval];
unverified.trust_view.completed_checks = [];
unverified.trust_view.approval_summary = [];
unverified.trust_view.trust_events = [];
unverified.trust_view.limitations = ["registered_full_run_unavailable"];
unverified.trust_view.deidentification.notice_ko =
  "등록 full run이 없어 출처와 승인 계보를 확인할 수 없습니다.";
const validUnverified = finalized(unverified);

const invalidHash = structuredClone(trusted);
invalidHash.bundle_hash = "0".repeat(64);

const invalidReference = structuredClone(trusted);
invalidReference.final_result.issues[0].evidence_link_ids = ["evidence_missing"];
invalidReference.evidence_view.issue_claim_closure[0].evidence_link_ids = [
  "evidence_missing",
];
invalidReference.bundle_hash = sha256(invalidReference, "bundle_hash");

const outputs = new Map([
  ["valid-trusted.json", trusted],
  ["valid-poc.json", validPoc],
  ["valid-unverified-import.json", validUnverified],
  ["invalid-hash.json", invalidHash],
  ["invalid-reference.json", invalidReference],
]);

let stale = false;
for (const [name, value] of outputs) {
  const path = resolve(fixtureRoot, name);
  const expected = `${JSON.stringify(value, null, 2)}\n`;
  if (process.argv.includes("--check")) {
    let current;
    try {
      current = await readFile(path, "utf8");
    } catch {
      current = "";
    }
    if (current !== expected) {
      console.error(`contracts/web-report/v1/fixtures/${name} is stale`);
      stale = true;
    }
  } else {
    await writeFile(path, expected, "utf8");
  }
}

if (stale) {
  process.exit(1);
}
