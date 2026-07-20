#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  loadRootEnvironment,
  startAiDemo,
} from "./start-ai-demo.mjs";

const repositoryRoot = path.resolve(import.meta.dirname, "../..");

export async function main() {
  loadRootEnvironment(repositoryRoot);
  const {
    OPENAI_API_KEY: _ignoredOpenAiApiKey,
    ...keylessEnvironment
  } = process.env;
  void _ignoredOpenAiApiKey;
  await startAiDemo({
    environment: keylessEnvironment,
    pythonModule: "trusted_ceo_agent.service.testing_main",
    repositoryRoot,
    serviceDirectory: "ai-e2e",
  });
}

const modulePath = path.resolve(fileURLToPath(import.meta.url));
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
const isMain = process.platform === "win32"
  ? invokedPath.toLowerCase() === modulePath.toLowerCase()
  : invokedPath === modulePath;

if (isMain) {
  main().catch(() => {
    process.stderr.write("Trusted CEO Agent E2E service could not start.\n");
    process.exitCode = 1;
  });
}