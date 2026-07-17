import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";


const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const contractRoot = resolve(scriptDirectory, "..", "v1");
const fixtureRoot = resolve(contractRoot, "fixtures", "questions");

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

const fixtureCases = [
  [
    "valid-result-question-job.json",
    "result-question-job.schema.json",
    true,
  ],
  [
    "invalid-result-question-job-missing-context.json",
    "result-question-job.schema.json",
    false,
  ],
  [
    "valid-result-answer-draft.json",
    "result-answer-draft.schema.json",
    true,
  ],
  [
    "invalid-result-answer-draft-supported.json",
    "result-answer-draft.schema.json",
    false,
  ],
  [
    "invalid-result-answer-draft-not-supported.json",
    "result-answer-draft.schema.json",
    false,
  ],
  ["valid-result-answer.json", "result-answer.schema.json", true],
  [
    "invalid-result-answer-missing-validation.json",
    "result-answer.schema.json",
    false,
  ],
];

for (const [fixtureName, schemaName, expectedValid] of fixtureCases) {
  const validate = ajv.getSchema(schemaName);
  if (validate === undefined) {
    throw new Error(`${schemaName} did not compile`);
  }
  const document = JSON.parse(
    await readFile(join(fixtureRoot, fixtureName), "utf8"),
  );
  const valid = validate(document);
  if (valid !== expectedValid) {
    throw new Error(
      `${fixtureName} validity was ${valid}; expected ${expectedValid}: ` +
        ajv.errorsText(validate.errors),
    );
  }
  if (
    fixtureName === "valid-result-question-job.json" &&
    document.job_hash !== hashWithoutRootField(document, "job_hash")
  ) {
    throw new Error(`${fixtureName} job hash mismatch`);
  }
}

console.log("result question contract fixtures validated");
