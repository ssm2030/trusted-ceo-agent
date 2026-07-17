// @vitest-environment node
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, it } from "vitest";

import { ReportStore } from "@/lib/server/report-store";

it("does not switch the authoritative pointer when publication cannot finish", async () => {
  const root = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-store-failure-"),
  );
  const store = new ReportStore(root);
  await store.publishVerified(Buffer.from('{"id":"old"}'), {
    bundle_hash: "old",
  });
  const before = await store.readCurrentPair();

  const compatibilityReport = path.join(
    root,
    "current-report.json",
  );
  await rm(compatibilityReport);
  await mkdir(compatibilityReport);

  await expect(
    store.publishVerified(Buffer.from('{"id":"new"}'), {
      bundle_hash: "new",
    }),
  ).rejects.toThrow();
  expect((await store.readCurrentPair())?.generation).toBe(
    before?.generation,
  );
});
