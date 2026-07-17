import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";


const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const fixtureRoot = resolve(
  scriptDirectory,
  "..",
  "v1",
  "fixtures",
  "questions",
);

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

function hashWithoutRootField(value, field) {
  const body = structuredClone(value);
  delete body[field];
  return createHash("sha256").update(canonicalize(body), "utf8").digest("hex");
}

function finalizedJob(value) {
  const result = structuredClone(value);
  result.job_hash = hashWithoutRootField(result, "job_hash");
  return result;
}

const jobSource = {
  job_version: "1.0.0",
  job_id: "job_01",
  job_hash: "0".repeat(64),
  run_id: "run_20260717T010203Z_0123456789abcdef",
  revision: 2,
  question: "이 문제를 뒷받침하는 근거는 무엇인가요?",
  response_locale: "ko-KR",
  privacy_classification: "company_restricted",
  scope: {
    scope_kind: "issue",
    scope_instance_id: "issue_01",
    start_refs: ["issue_01"],
    issue_id: "issue_01",
  },
  allowed_issue_refs: ["issue_01"],
  allowed_claim_refs: ["claim_01"],
  allowed_fact_refs: ["fact_01"],
  allowed_signal_refs: [],
  allowed_evidence_link_ids: ["evidence_01"],
  allowed_source_refs: ["source_01"],
  allowed_value_refs: ["value_01"],
  allowed_expert_packet_refs: [],
  allowed_revision_diff_refs: [],
  context_blocks: [
    {
      block_ref: "context_01",
      block_kind: "fact",
      subject_ref: "fact_01",
      text: "매출총이익률은 12.4%로 기록되었습니다.",
      claim_refs: ["claim_01"],
      evidence_link_ids: ["evidence_01"],
      source_refs: ["source_01"],
      value_refs: ["value_01"],
    },
  ],
  value_table: [
    {
      value_ref: "value_01",
      fact_or_signal_id: "fact_01",
      display_field: "value",
      display_text: "12.4%",
    },
  ],
  forbidden_conclusions: [],
  data_quality_conditions: [],
  not_assessable_conditions: [],
  deidentification: {
    poc_only: false,
    direct_identifiers_removed: true,
    notice_ko: "질문 작업에는 비식별화된 근거만 포함됩니다.",
  },
  privacy: {
    deidentified: true,
    excluded_fields: ["direct_identifiers"],
  },
  context_caps: {
    max_context_bytes: 131072,
    actual_context_bytes: 384,
    excluded_block_count: 0,
    max_answer_blocks: 12,
    max_block_characters: 800,
  },
  excluded_summary: {
    excluded: false,
    reason_codes: [],
    available_scope_instance_ids: [],
  },
  output_schema_version: "1.0.0",
};
const validJob = finalizedJob(jobSource);

const invalidMissingContext = structuredClone(validJob);
delete invalidMissingContext.context_blocks;
invalidMissingContext.job_hash = hashWithoutRootField(
  invalidMissingContext,
  "job_hash",
);

const supportedBlock = {
  block_id: "block_01",
  support_status: "supported",
  text_template: "매출총이익률은 {{value:value_01}}입니다.",
  value_refs: ["value_01"],
  claim_refs: ["claim_01"],
  evidence_link_ids: ["evidence_01"],
  source_refs: ["source_01"],
};
const validDraft = {
  draft_version: "1.0.0",
  job_id: validJob.job_id,
  run_id: validJob.run_id,
  revision: validJob.revision,
  answer_blocks: [supportedBlock],
};

const invalidSupportedDraft = structuredClone(validDraft);
invalidSupportedDraft.answer_blocks[0].claim_refs = [];
invalidSupportedDraft.answer_blocks[0].evidence_link_ids = [];

const invalidNotSupportedDraft = structuredClone(validDraft);
invalidNotSupportedDraft.answer_blocks[0] = {
  block_id: "block_01",
  support_status: "not_supported",
  text_template: "모델이 임의로 만든 판단불가 문구",
  value_refs: [],
  claim_refs: ["claim_01"],
  evidence_link_ids: ["evidence_01"],
  source_refs: ["source_01"],
};

const validAnswer = {
  answer_version: "1.0.0",
  job_id: validJob.job_id,
  run_id: validJob.run_id,
  revision: validJob.revision,
  scope: validJob.scope,
  validation: {
    schema_valid: true,
    references_valid: true,
    values_valid: true,
    semantic_entailment_verified: false,
    label_ko: "스키마·참조 검증 통과",
  },
  answer_blocks: [
    {
      block_id: "block_01",
      support_status: "supported",
      text: "매출총이익률은 12.4%입니다.",
      resolved_values: [
        {
          value_ref: "value_01",
          display_text: "12.4%",
        },
      ],
      claim_refs: ["claim_01"],
      evidence_link_ids: ["evidence_01"],
      source_refs: ["source_01"],
    },
  ],
};

const invalidAnswer = structuredClone(validAnswer);
delete invalidAnswer.validation;

const outputs = new Map([
  ["valid-result-question-job.json", validJob],
  ["invalid-result-question-job-missing-context.json", invalidMissingContext],
  ["valid-result-answer-draft.json", validDraft],
  ["invalid-result-answer-draft-supported.json", invalidSupportedDraft],
  ["invalid-result-answer-draft-not-supported.json", invalidNotSupportedDraft],
  ["valid-result-answer.json", validAnswer],
  ["invalid-result-answer-missing-validation.json", invalidAnswer],
]);

await mkdir(fixtureRoot, { recursive: true });
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
      console.error(`contracts/web-report/v1/fixtures/questions/${name} is stale`);
      stale = true;
    }
  } else {
    await writeFile(path, expected, "utf8");
  }
}

if (stale) {
  process.exit(1);
}
