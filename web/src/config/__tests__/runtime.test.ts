import { describe, expect, it } from "vitest";

import { RUNTIME_CONTRACT } from "@/config/runtime";

describe("RUNTIME_CONTRACT", () => {
  it("pins the tournament runtime and localhost boundary", () => {
    expect(RUNTIME_CONTRACT).toEqual({
      node: "22.22.0",
      nextMajor: 16,
      host: "127.0.0.1",
      packageManager: "npm",
    });
  });
});
