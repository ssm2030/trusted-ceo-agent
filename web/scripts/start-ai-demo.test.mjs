import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import path from "node:path";
import test from "node:test";

import {
  buildLaunchPlan,
  loadRootEnvironment,
  startAiDemo,
} from "./start-ai-demo.mjs";

const REPOSITORY_ROOT = path.resolve(import.meta.dirname, "../..");
const INTERNAL_TOKEN = "t".repeat(43);

class FakeChild extends EventEmitter {
  constructor() {
    super();
    this.exitCode = null;
    this.signalCode = null;
    this.killed = false;
    this.killSignals = [];
  }

  kill(signal = "SIGTERM") {
    this.killed = true;
    this.killSignals.push(signal);
    return true;
  }
}

function okHealth() {
  return {
    ok: true,
    async json() {
      return { status: "ok", ai_ready: false, model: "gpt-5.6" };
    },
  };
}

function launcherHarness({
  healthResponses = [okHealth()],
  onSpawn,
} = {}) {
  const children = [];
  const spawnCalls = [];
  const healthCalls = [];
  const signalHandlers = new Map();
  let responseIndex = 0;

  const spawnProcess = (executable, args, options) => {
    const child = new FakeChild();
    children.push(child);
    spawnCalls.push({ executable, args, options });
    onSpawn?.({ child, executable, args, options, index: children.length - 1 });
    return child;
  };

  const fetchImpl = async (url, options) => {
    healthCalls.push({ url, options });
    const response =
      healthResponses[Math.min(responseIndex, healthResponses.length - 1)];
    responseIndex += 1;
    if (response instanceof Error) {
      throw response;
    }
    return response;
  };

  return {
    children,
    dependencies: {
      ensureDirectory: async () => undefined,
      fetchImpl,
      pause: async () => undefined,
      registerSignal(signal, handler) {
        signalHandlers.set(signal, handler);
      },
      removeSignal(signal, handler) {
        if (signalHandlers.get(signal) === handler) {
          signalHandlers.delete(signal);
        }
      },
      setExitCode: () => undefined,
      spawnProcess,
    },
    healthCalls,
    signalHandlers,
    spawnCalls,
  };
}

test("buildLaunchPlan creates a fresh token with at least 32 random bytes", () => {
  const first = buildLaunchPlan({
    environment: {},
    repositoryRoot: REPOSITORY_ROOT,
  });
  const second = buildLaunchPlan({
    environment: {},
    repositoryRoot: REPOSITORY_ROOT,
  });

  assert.ok(Buffer.from(first.internalToken, "base64url").byteLength >= 32);
  assert.ok(Buffer.from(second.internalToken, "base64url").byteLength >= 32);
  assert.notEqual(first.internalToken, second.internalToken);
});

test("buildLaunchPlan isolates the API key and browser-public secrets", () => {
  const apiKey = "test-openai-key";
  const plan = buildLaunchPlan({
    environment: {
      OPENAI_API_KEY: apiKey,
      TRUSTED_CEO_INTERNAL_TOKEN: "attacker-controlled-token",
      NEXT_PUBLIC_OPENAI_API_KEY: apiKey,
      NEXT_PUBLIC_TRUSTED_CEO_INTERNAL_TOKEN: "public-token",
      NEXT_PUBLIC_THEME: "dark",
      PATH: "test-path",
    },
    internalToken: INTERNAL_TOKEN,
    repositoryRoot: REPOSITORY_ROOT,
  });

  assert.equal(plan.python.options.env.OPENAI_API_KEY, apiKey);
  assert.equal(
    plan.python.options.env.TRUSTED_CEO_INTERNAL_TOKEN,
    INTERNAL_TOKEN,
  );
  assert.equal(
    plan.next.options.env.TRUSTED_CEO_INTERNAL_TOKEN,
    INTERNAL_TOKEN,
  );
  assert.equal(plan.next.options.env.OPENAI_API_KEY, undefined);
  assert.equal(plan.next.options.env.NEXT_PUBLIC_OPENAI_API_KEY, undefined);
  assert.equal(
    plan.next.options.env.NEXT_PUBLIC_TRUSTED_CEO_INTERNAL_TOKEN,
    undefined,
  );
  assert.equal(plan.next.options.env.NEXT_PUBLIC_THEME, "dark");
  assert.equal(plan.python.options.env.TRUSTED_CEO_SERVICE_HOST, "127.0.0.1");
  assert.equal(
    plan.python.options.env.PYTHONPATH.split(path.delimiter)[0],
    path.join(REPOSITORY_ROOT, "plugin", "trusted-ceo-agent"),
  );
  assert.equal(plan.next.options.env.TRUSTED_CEO_SERVICE_HOST, "127.0.0.1");
  assert.equal(plan.healthUrl, "http://127.0.0.1:8765/health");
  assert.deepEqual(plan.healthHeaders, {
    "X-Trusted-Ceo-Internal-Token": INTERNAL_TOKEN,
  });
});

test("buildLaunchPlan remains usable without an OpenAI API key", () => {
  const plan = buildLaunchPlan({
    environment: { PATH: "test-path" },
    internalToken: INTERNAL_TOKEN,
    repositoryRoot: REPOSITORY_ROOT,
  });

  assert.equal(plan.python.options.env.OPENAI_API_KEY, undefined);
  assert.equal(plan.next.options.env.OPENAI_API_KEY, undefined);
  assert.equal(
    plan.python.options.env.TRUSTED_CEO_INTERNAL_TOKEN,
    INTERNAL_TOKEN,
  );
});

test("buildLaunchPlan invokes npm through Node without a Windows shell", () => {
  const npmCliPath = path.join(REPOSITORY_ROOT, "tools", "npm-cli.js");
  const nodeExecutable = path.join(REPOSITORY_ROOT, "tools", "node.exe");
  const plan = buildLaunchPlan({
    environment: { npm_execpath: npmCliPath },
    internalToken: INTERNAL_TOKEN,
    nodeExecutable,
    platform: "win32",
    repositoryRoot: REPOSITORY_ROOT,
  });

  assert.equal(plan.next.executable, nodeExecutable);
  assert.deepEqual(plan.next.args, [
    npmCliPath,
    "--prefix",
    "web",
    "run",
    "dev",
  ]);
  assert.equal(plan.next.options.shell, false);
});

test("loadRootEnvironment treats a missing root .env.local as optional", () => {
  let requestedPath;
  const loaded = loadRootEnvironment(REPOSITORY_ROOT, (candidate) => {
    requestedPath = candidate;
    const error = new Error("missing");
    error.code = "ENOENT";
    throw error;
  });

  assert.equal(loaded, false);
  assert.equal(requestedPath, path.join(REPOSITORY_ROOT, ".env.local"));
});

test("startAiDemo waits for authenticated health before spawning Next", async () => {
  const harness = launcherHarness({
    healthResponses: [
      { ok: false, async json() { return {}; } },
      okHealth(),
    ],
  });

  const controller = await startAiDemo(
    {
      environment: { OPENAI_API_KEY: "test-openai-key" },
      healthAttempts: 3,
      internalToken: INTERNAL_TOKEN,
      platform: "linux",
      repositoryRoot: REPOSITORY_ROOT,
    },
    harness.dependencies,
  );

  assert.deepEqual(
    harness.spawnCalls.map(({ executable }) => executable),
    ["uv", "npm"],
  );
  assert.equal(harness.healthCalls.length, 2);
  for (const call of harness.healthCalls) {
    assert.equal(call.url, "http://127.0.0.1:8765/health");
    assert.equal(
      call.options.headers["X-Trusted-Ceo-Internal-Token"],
      INTERNAL_TOKEN,
    );
  }
  assert.deepEqual(harness.spawnCalls[0].args, [
    "run",
    "--project",
    "plugin/trusted-ceo-agent",
    "--frozen",
    "python",
    "-m",
    "trusted_ceo_agent.service.main",
  ]);
  assert.deepEqual(harness.spawnCalls[1].args, [
    "--prefix",
    "web",
    "run",
    "dev",
  ]);
  assert.equal(harness.spawnCalls[0].options.shell, false);
  assert.equal(harness.spawnCalls[1].options.shell, false);

  controller.stop();
});

test("startAiDemo never starts Next when Python exits before health", async () => {
  const harness = launcherHarness({
    healthResponses: [new Promise(() => undefined)],
    onSpawn({ child, index }) {
      if (index === 0) {
        queueMicrotask(() => {
          child.exitCode = 1;
          child.emit("exit", 1, null);
        });
      }
    },
  });
  harness.dependencies.fetchImpl = async () => new Promise(() => undefined);

  await assert.rejects(
    startAiDemo(
      {
        environment: {},
        healthAttempts: 1,
        internalToken: INTERNAL_TOKEN,
        repositoryRoot: REPOSITORY_ROOT,
      },
      harness.dependencies,
    ),
    /Python service stopped before authenticated health/,
  );
  assert.equal(harness.spawnCalls.length, 1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  test(`${signal} terminates both children and removes signal handlers`, async () => {
    const harness = launcherHarness();
    const controller = await startAiDemo(
      {
        environment: {},
        internalToken: INTERNAL_TOKEN,
        repositoryRoot: REPOSITORY_ROOT,
      },
      harness.dependencies,
    );

    assert.equal(harness.signalHandlers.size, 2);
    harness.signalHandlers.get(signal)();

    assert.deepEqual(harness.children[0].killSignals, ["SIGTERM"]);
    assert.deepEqual(harness.children[1].killSignals, ["SIGTERM"]);
    assert.equal(harness.signalHandlers.size, 0);
    controller.stop();
  });
}

test("an unexpected Next exit terminates the Python child", async () => {
  const harness = launcherHarness();
  const controller = await startAiDemo(
    {
      environment: {},
      internalToken: INTERNAL_TOKEN,
      repositoryRoot: REPOSITORY_ROOT,
    },
    harness.dependencies,
  );

  harness.children[1].exitCode = 1;
  harness.children[1].emit("exit", 1, null);

  assert.deepEqual(harness.children[0].killSignals, ["SIGTERM"]);
  controller.stop();
});
