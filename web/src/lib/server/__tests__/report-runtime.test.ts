// @vitest-environment node
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { createReportRuntime } from "@/lib/server/report-runtime";

describe("report server runtime", () => {
  it("derives one exact Host and Origin from the configured local port", () => {
    const runtime = createReportRuntime({
      port: 3000,
      runtimeRoot: path.join(tmpdir(), "trusted-ceo-runtime-test"),
      sessionSecret: new Uint8Array(32).fill(5),
    });
    expect(runtime.security.host).toBe("127.0.0.1:3000");
    expect(runtime.security.origin).toBe("http://127.0.0.1:3000");
  });

  it("rejects relative runtime paths", () => {
    expect(() =>
      createReportRuntime({
        port: 3000,
        runtimeRoot: "relative/runtime",
        sessionSecret: new Uint8Array(32).fill(5),
      }),
    ).toThrow("absolute");
  });
});
