// @vitest-environment node
import { describe, expect, it } from "vitest";

import { assertOfficialUrl } from "@/lib/server/official-url-policy";

describe("official URL policy", () => {
  const policy = {
    allowed_schemes: ["https"] as ["https"],
    allowed_origins: ["https://official.example"],
    allow_redirects: true,
  };

  it("accepts initial and redirect-final URLs only when both origins are allowed", () => {
    expect(() =>
      assertOfficialUrl(
        "https://official.example/a",
        "https://official.example/b",
        policy,
      ),
    ).not.toThrow();
    expect(() =>
      assertOfficialUrl(
        "https://official.example/a",
        "https://evil.example/b",
        policy,
      ),
    ).toThrow("허용되지 않은 공식 자료 링크입니다.");
  });

  it("rejects redirects when the manifest disables them", () => {
    expect(() =>
      assertOfficialUrl(
        "https://official.example/a",
        "https://official.example/b",
        { ...policy, allow_redirects: false },
      ),
    ).toThrow("허용되지 않은 공식 자료 링크입니다.");
  });

  it("rejects allowlist entries that are URLs rather than exact origins", () => {
    expect(() =>
      assertOfficialUrl(
        "https://official.example/a",
        "https://official.example/a",
        {
          ...policy,
          allowed_origins: ["https://official.example/path"],
        },
      ),
    ).toThrow("허용되지 않은 공식 자료 링크입니다.");
  });
});
