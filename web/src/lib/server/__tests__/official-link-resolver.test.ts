// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { resolveOfficialUrl } from "@/lib/server/official-link-resolver";

const policy = {
  allowed_schemes: ["https"] as ["https"],
  allowed_origins: ["https://official.example"],
  allow_redirects: true,
};

describe("official link redirect resolver", () => {
  it("follows bounded redirects and validates the final origin", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 302,
          headers: { location: "/final" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 200 }));

    await expect(
      resolveOfficialUrl(
        "https://official.example/start",
        policy,
        {
          fetcher,
          assertPublicDestination: async () => undefined,
        },
      ),
    ).resolves.toBe("https://official.example/final");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("rejects a redirect target outside the exact origin allowlist", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(
      new Response(null, {
        status: 302,
        headers: { location: "https://evil.example/final" },
      }),
    );

    await expect(
      resolveOfficialUrl(
        "https://official.example/start",
        policy,
        {
          fetcher,
          assertPublicDestination: async () => undefined,
        },
      ),
    ).rejects.toThrow("허용되지 않은 공식 자료 링크입니다.");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("rejects every redirect when redirects are disabled", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(
      new Response(null, {
        status: 302,
        headers: { location: "/final" },
      }),
    );

    await expect(
      resolveOfficialUrl(
        "https://official.example/start",
        { ...policy, allow_redirects: false },
        {
          fetcher,
          assertPublicDestination: async () => undefined,
        },
      ),
    ).rejects.toThrow("허용되지 않은 공식 자료 링크입니다.");
  });
});
