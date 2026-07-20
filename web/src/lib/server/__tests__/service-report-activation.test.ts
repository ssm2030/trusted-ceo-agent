// @vitest-environment node
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  activateServiceReport,
} from "@/lib/server/service-report-activation";
import { ReportStore } from "@/lib/server/report-store";
import type { QuestionRunContext } from "@/lib/server/questions/types";

const roots: string[] = [];

async function fixture(): Promise<Record<string, unknown>> {
  const candidates = [
    path.resolve(process.cwd(), "contracts/web-report/v1/fixtures/valid-trusted.json"),
    path.resolve(process.cwd(), "../contracts/web-report/v1/fixtures/valid-trusted.json"),
  ];
  for (const candidate of candidates) {
    try {
      return JSON.parse(await readFile(candidate, "utf8")) as Record<string, unknown>;
    } catch {
      // Try the next supported test working directory.
    }
  }
  throw new Error("valid trusted fixture unavailable");
}

function eligibility(bundle: Record<string, unknown>) {
  const run = bundle.run as { run_id: string; revision: number };
  return {
    decision_version: "1.0.0",
    eligible: true,
    viewer_mode: "trusted_final",
    badge_label_ko: "승인·검증된 실행본",
    run_id: run.run_id,
    revision: run.revision,
    bundle_hash: bundle.bundle_hash,
    completed_checks: [
      "evidence_core",
      "final_package",
      "grade_recomputation",
      "snapshot_manifest",
    ],
    failure_code: null,
    failure_message: null,
  };
}

async function store(): Promise<ReportStore> {
  const root = await mkdtemp(path.join(tmpdir(), "service-report-test-"));
  roots.push(root);
  return new ReportStore(root);
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) =>
    rm(root, { recursive: true, force: true }),
  ));
});

describe("activateServiceReport", () => {
  it("atomically validates and publishes a trusted service report before activating questions", async () => {
    const bundle = await fixture();
    const reportStore = await store();
    const setContext = vi.fn<(context: QuestionRunContext) => void>();

    const decision = await activateServiceReport(
      { bundle, eligibility: eligibility(bundle) },
      { store: reportStore, setContext },
    );

    expect(decision.viewer_mode).toBe("trusted_final");
    expect(await reportStore.readCurrent()).not.toBeNull();
    expect(setContext).toHaveBeenCalledWith(expect.objectContaining({
      runId: (bundle.run as { run_id: string }).run_id,
      revision: (bundle.run as { revision: number }).revision,
      bundleHash: bundle.bundle_hash,
      viewerMode: "trusted_final",
      privacyClassification: "company_restricted",
    }));
  });

  it("keeps the previous report and context when a candidate is inconsistent", async () => {
    const bundle = await fixture();
    const reportStore = await store();
    const setContext = vi.fn<(context: QuestionRunContext) => void>();
    await activateServiceReport(
      { bundle, eligibility: eligibility(bundle) },
      { store: reportStore, setContext },
    );
    const previous = await reportStore.readCurrent();
    setContext.mockClear();
    const invalid = structuredClone(bundle);
    (invalid.run as Record<string, unknown>).workflow_state = "running";

    await expect(activateServiceReport(
      { bundle: invalid, eligibility: eligibility(bundle) },
      { store: reportStore, setContext },
    )).rejects.toThrow();

    expect(await reportStore.readCurrent()).toEqual(previous);
    expect(setContext).not.toHaveBeenCalled();
  });
});