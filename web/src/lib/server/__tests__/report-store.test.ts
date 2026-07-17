// @vitest-environment node
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { ReportStore } from "@/lib/server/report-store";

describe("ReportStore", () => {
  it("keeps the current report and decision when candidate validation fails", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-web-"));
    const store = new ReportStore(root);
    await store.publishVerified(Buffer.from('{"id":"old"}'), {
      bundle_hash: "old",
    });

    await expect(
      store.replaceAfterValidation(Buffer.from('{"id":"bad"}'), async () => {
        throw new Error("invalid");
      }),
    ).rejects.toThrow("invalid");

    expect(Buffer.from((await store.readCurrent()) ?? []).toString("utf8")).toBe(
      '{"id":"old"}',
    );
    expect(await store.readCurrentDecision()).toEqual({ bundle_hash: "old" });
    expect(
      await readFile(path.join(root, "current-report.json"), "utf8"),
    ).toBe('{"id":"old"}');
  });

  it("publishes report and decision from one committed generation", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-web-"));
    const store = new ReportStore(root);

    await store.publishVerified(Buffer.from('{"id":"new"}'), {
      bundle_hash: "new",
    });

    const pair = await store.readCurrentPair();
    expect(Buffer.from(pair?.bytes ?? []).toString("utf8")).toBe('{"id":"new"}');
    expect(pair?.decision).toEqual({ bundle_hash: "new" });
    expect(pair?.generation).toMatch(/^[0-9a-f-]+$/);
  });
});
