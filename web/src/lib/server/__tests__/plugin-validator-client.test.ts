// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  buildValidateWebReportCommand,
  parseValidateWebReportStdout,
} from "@/lib/server/plugin-validator-client";

const RUN_ID = "run_20260717T000000Z_aaaaaaaaaaaaaaaa";
const HASH = "a".repeat(64);

describe("plugin validator client", () => {
  it("uses the frozen offline launcher with a fixed executable and argv", () => {
    expect(
      buildValidateWebReportCommand({
        artifactRoot: "/approved/runs/run_1",
        bundlePath: "/runtime/candidate/web-report-bundle.json",
        runId: "run_1",
        revision: 9,
        expectedBundleHash: HASH,
      }),
    ).toEqual({
      file: "uv",
      args: [
        "run",
        "--project",
        "plugin/trusted-ceo-agent",
        "--frozen",
        "--offline",
        "--no-sync",
        "python",
        "plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py",
        "validate-web-report",
        "--artifact-root",
        "/approved/runs/run_1",
        "--run-id",
        "run_1",
        "--revision",
        "9",
        "--bundle",
        "/runtime/candidate/web-report-bundle.json",
      ],
    });
  });

  it("extracts and cross-checks the decision inside the CLI response envelope", async () => {
    const decision = {
      decision_version: "1.0.0",
      eligible: true,
      viewer_mode: "trusted_final",
      badge_label_ko: "승인·검증된 실행본",
      run_id: RUN_ID,
      revision: 9,
      bundle_hash: HASH,
      completed_checks: ["final_package"],
      failure_code: null,
      failure_message: null,
    };
    const stdout = JSON.stringify({
      contract_version: "1.0.0",
      ok: true,
      code: 0,
      command: "validate-web-report",
      message: "validated",
      run_id: RUN_ID,
      revision: 9,
      state: "finalized",
      data: decision,
    });

    await expect(
      parseValidateWebReportStdout(stdout, {
        runId: RUN_ID,
        revision: 9,
        expectedBundleHash: HASH,
      }),
    ).resolves.toEqual(decision);
  });

  it("rejects extra stdout and mismatched hashes", async () => {
    const base = {
      contract_version: "1.0.0",
      ok: true,
      code: 0,
      command: "validate-web-report",
      message: "validated",
      run_id: RUN_ID,
      revision: 9,
      state: "finalized",
      data: {
        decision_version: "1.0.0",
        eligible: true,
        viewer_mode: "trusted_final",
        badge_label_ko: "승인·검증된 실행본",
        run_id: RUN_ID,
        revision: 9,
        bundle_hash: "b".repeat(64),
        completed_checks: [],
        failure_code: null,
        failure_message: null,
      },
    };

    await expect(
      parseValidateWebReportStdout(`${JSON.stringify(base)}\nnoise`, {
        runId: RUN_ID,
        revision: 9,
        expectedBundleHash: HASH,
      }),
    ).rejects.toThrow("단일 JSON");
    await expect(
      parseValidateWebReportStdout(JSON.stringify(base), {
        runId: RUN_ID,
        revision: 9,
        expectedBundleHash: HASH,
      }),
    ).rejects.toThrow("bundle hash");
  });
});
