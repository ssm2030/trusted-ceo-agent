// @vitest-environment node
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

type ChildPlan = Readonly<{
  executable: string;
  args: readonly string[];
  options: Readonly<{
    cwd: string;
    env: Readonly<Record<string, string | undefined>>;
    shell: false;
  }>;
}>;

type LaunchPlan = Readonly<{
  internalToken: string;
  healthUrl: string;
  healthHeaders: Readonly<Record<string, string>>;
  python: ChildPlan;
  next: ChildPlan;
}>;

type LauncherModule = Readonly<{
  buildLaunchPlan(input: {
    environment: Readonly<Record<string, string | undefined>>;
    platform?: string;
    repositoryRoot: string;
  }): LaunchPlan;
}>;

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(currentDirectory, "../../../../..");
const repositoryRoot = path.dirname(webRoot);
const launcherPath = path.join(webRoot, "scripts", "start-ai-demo.mjs");

async function importLauncher(): Promise<LauncherModule> {
  return import(pathToFileURL(launcherPath).href) as Promise<LauncherModule>;
}

describe("secure local AI demo launcher boundary", () => {
  it("shares only a server-side random token and isolates the OpenAI key", async () => {
    const launcher = await importLauncher();
    const openAiApiKey = "test-openai-key";
    const plan = launcher.buildLaunchPlan({
      environment: {
        OPENAI_API_KEY: openAiApiKey,
        TRUSTED_CEO_INTERNAL_TOKEN: "untrusted-existing-token",
        NEXT_PUBLIC_OPENAI_API_KEY: openAiApiKey,
        NEXT_PUBLIC_TRUSTED_CEO_INTERNAL_TOKEN: "public-token",
        NEXT_PUBLIC_THEME: "dark",
      },
      repositoryRoot,
    });

    expect(Buffer.from(plan.internalToken, "base64url").byteLength).toBeGreaterThanOrEqual(32);
    expect(plan.python.options.env.OPENAI_API_KEY).toBe(openAiApiKey);
    expect(plan.next.options.env.OPENAI_API_KEY).toBeUndefined();
    expect(plan.python.options.env.TRUSTED_CEO_INTERNAL_TOKEN).toBe(plan.internalToken);
    expect(plan.next.options.env.TRUSTED_CEO_INTERNAL_TOKEN).toBe(plan.internalToken);
    expect(plan.next.options.env.NEXT_PUBLIC_OPENAI_API_KEY).toBeUndefined();
    expect(plan.next.options.env.NEXT_PUBLIC_TRUSTED_CEO_INTERNAL_TOKEN).toBeUndefined();
    expect(plan.next.options.env.NEXT_PUBLIC_THEME).toBe("dark");
  });

  it("pins both children and authenticated health to exact IPv4 loopback without a shell", async () => {
    const launcher = await importLauncher();
    const plan = launcher.buildLaunchPlan({
      environment: {},
      platform: "linux",
      repositoryRoot,
    });

    expect(plan.python.executable).toBe("uv");
    expect(plan.python.args).toEqual([
      "run",
      "--project",
      "plugin/trusted-ceo-agent",
      "--frozen",
      "python",
      "-m",
      "trusted_ceo_agent.service.main",
    ]);
    expect(plan.next.executable).toBe("npm");
    expect(plan.next.args).toEqual(["--prefix", "web", "run", "dev"]);
    expect(plan.python.options.shell).toBe(false);
    expect(plan.next.options.shell).toBe(false);
    expect(plan.python.options.env.TRUSTED_CEO_SERVICE_HOST).toBe("127.0.0.1");
    expect(plan.next.options.env.TRUSTED_CEO_SERVICE_HOST).toBe("127.0.0.1");
    expect(plan.healthUrl).toBe("http://127.0.0.1:8765/health");
    expect(plan.healthHeaders).toEqual({
      "X-Trusted-Ceo-Internal-Token": plan.internalToken,
    });
  });

  it("registers the exact package scripts and secret/runtime ignores", async () => {
    const packageJson = JSON.parse(
      await readFile(path.join(webRoot, "package.json"), "utf8"),
    ) as { scripts: Record<string, string> };
    const ignoreLines = new Set(
      (await readFile(path.join(repositoryRoot, ".gitignore"), "utf8"))
        .split(/\r?\n/u)
        .filter(Boolean),
    );

    expect(packageJson.scripts["dev:ai"]).toBe("node scripts/start-ai-demo.mjs");
    expect(packageJson.scripts["test:launcher"]).toBe(
      "node --test scripts/start-ai-demo.test.mjs",
    );
    expect(packageJson.scripts.dev).toBe("next dev --hostname 127.0.0.1");
    for (const ignored of [
      ".env",
      ".env.local",
      "web/.env.local",
      "web/var/ai-service/",
    ]) {
      expect(ignoreLines.has(ignored)).toBe(true);
    }
  });
});
