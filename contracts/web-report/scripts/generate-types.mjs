import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { compileFromFile } from "json-schema-to-typescript";


const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDirectory, "..");
const schemaRoot = resolve(root, "v1");
const input = resolve(schemaRoot, "web-report-contracts.schema.json");
const output = resolve(schemaRoot, "generated", "types.ts");
const banner = [
  "/* eslint-disable */",
  "/** Generated from Contract 0. Do not edit by hand. */",
  "",
].join("\n");

const generated = await compileFromFile(input, {
  cwd: schemaRoot,
  bannerComment: banner,
  additionalProperties: false,
  declareExternallyReferenced: true,
  enableConstEnums: false,
  unreachableDefinitions: true,
  style: {
    singleQuote: false,
    semi: true,
    tabWidth: 2,
  },
});

if (process.argv.includes("--check")) {
  let current;
  try {
    current = await readFile(output, "utf8");
  } catch {
    console.error("contracts/web-report/v1/generated/types.ts is missing");
    process.exit(1);
  }
  if (current !== generated) {
    console.error("contracts/web-report/v1/generated/types.ts is stale");
    process.exit(1);
  }
} else {
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, generated, "utf8");
}
