import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  buildLaunchPlan,
  launchFailureExitCode,
  loadRootEnvironment,
  startAiDemo,
} from "./start-ai-demo.mjs";
import { buildLaunchPlan as plannedLaunch } from "./ai-launch-plan.mjs";
import {
  childIsRunning,
  spawnChild,
  terminateChild,
  windowsJobSpecification,
} from "./child-supervisor.mjs";

const REPOSITORY_ROOT = path.resolve(import.meta.dirname, "../..");
const INTERNAL_TOKEN = "t".repeat(43);

test("launcher facade reexports plan and supervision boundaries", () => {
  assert.equal(buildLaunchPlan, plannedLaunch);
  assert.equal(typeof childIsRunning, "function");
});

test("launch failure preserves an exit code already set by a signal", () => {
  assert.equal(launchFailureExitCode(130), 130);
  assert.equal(launchFailureExitCode(143), 143);
  assert.equal(launchFailureExitCode(undefined), 1);
  assert.equal(launchFailureExitCode(0), 1);
});

class FakeChild extends EventEmitter {
  constructor() {
    super();
    this.exitCode = null;
    this.signalCode = null;
    this.killed = false;
    this.killSignals = [];
    this.treeTerminated = false;
  }

  kill(signal = "SIGTERM") {
    this.killed = true;
    this.killSignals.push(signal);
    return true;
  }
}

function simulatedTree() {
  const parentPid = 42_001;
  const alive = new Set([parentPid, parentPid + 1]);
  const child = new FakeChild();
  child.pid = parentPid;
  const directKill = child.kill.bind(child);
  child.kill = (signal) => {
    alive.delete(parentPid);
    return directKill(signal);
  };
  return { alive, child, parentPid };
}

test("terminateChild escalates a POSIX process group until descendants stop", async () => {
  const tree = simulatedTree();
  const lifecycle = [];

  await terminateChild(tree.child, {
    graceMs: 25,
    killProcess(target, signal) {
      assert.equal(target, -tree.parentPid);
      lifecycle.push(signal);
      if (signal === "SIGTERM") {
        tree.alive.delete(tree.parentPid);
      } else {
        tree.alive.clear();
      }
    },
    pause: async () => {
      lifecycle.push("grace");
    },
    platform: "linux",
  });

  assert.deepEqual(lifecycle, ["SIGTERM", "grace", "SIGKILL"]);
  assert.deepEqual([...tree.alive], []);
});

test("terminateChild invokes and awaits the exact Windows tree-kill command", async () => {
  const tree = simulatedTree();
  const killer = new FakeChild();
  let spawnCall;

  const termination = terminateChild(tree.child, {
    platform: "win32",
    spawnProcess(executable, args, options) {
      spawnCall = { executable, args, options };
      return killer;
    },
  });
  let settled = false;
  void termination.then(() => {
    settled = true;
  });
  await Promise.resolve();

  assert.equal(settled, false);
  assert.equal(path.win32.isAbsolute(spawnCall.executable), true);
  assert.equal(path.win32.basename(spawnCall.executable).toLowerCase(), "taskkill.exe");
  assert.equal(
    path.win32.basename(path.win32.dirname(spawnCall.executable)).toLowerCase(),
    "system32",
  );
  assert.deepEqual(spawnCall.args, ["/PID", String(tree.parentPid), "/T", "/F"]);
  assert.deepEqual(spawnCall.options, {
    shell: false,
    stdio: "ignore",
    windowsHide: true,
  });

  tree.alive.clear();
  killer.emit("close", 0);
  await termination;
  assert.equal(settled, true);
  assert.deepEqual([...tree.alive], []);
});

test("terminateChild never targets an already-exited Windows PID", async () => {
  const tree = simulatedTree();
  tree.child.exitCode = 0;
  let spawnCount = 0;

  await terminateChild(tree.child, {
    platform: "win32",
    spawnProcess() {
      spawnCount += 1;
      const killer = new FakeChild();
      queueMicrotask(() => killer.emit("close", 0));
      return killer;
    },
  });

  assert.equal(spawnCount, 0);
});

test("spawnChild wraps a Windows command in the repository job runner", () => {
  let spawnCall;
  const child = new FakeChild();
  const specification = {
    executable: "tool.exe",
    args: ["--value", "argument with spaces"],
    options: {
      cwd: REPOSITORY_ROOT,
      env: { PATH: "C:\\Windows\\System32" },
      shell: false,
      stdio: "inherit",
      windowsHide: true,
    },
  };

  const result = spawnChild(
    specification,
    {
      platform: "win32",
      spawnProcess(executable, args, options) {
        spawnCall = { executable, args, options };
        return child;
      },
    },
    "fixture",
  );

  assert.equal(result, child);
  assert.equal(
    spawnCall.executable,
    path.join(
      REPOSITORY_ROOT,
      "plugin",
      "trusted-ceo-agent",
      ".venv",
      "Scripts",
      "python.exe",
    ),
  );
  assert.equal(
    spawnCall.args[0],
    path.join(REPOSITORY_ROOT, "web", "scripts", "windows-job-runner.py"),
  );
  const payload = JSON.parse(
    Buffer.from(spawnCall.args[1], "base64url").toString("utf8"),
  );
  assert.deepEqual(payload, {
    executable: specification.executable,
    args: specification.args,
    cwd: REPOSITORY_ROOT,
  });
  assert.equal(spawnCall.options, specification.options);
});

test(
  "Windows job runner kills descendants when their direct parent exits",
  { skip: process.platform !== "win32" },
  async (context) => {
    const directory = await mkdtemp(path.join(os.tmpdir(), "trusted-ceo-job-"));
    const pidFile = path.join(directory, "descendant.pid");
    let descendantPid;
    context.after(async () => {
      if (Number.isSafeInteger(descendantPid)) {
        try {
          process.kill(descendantPid, "SIGKILL");
        } catch (error) {
          if (error?.code !== "ESRCH") throw error;
        }
      }
      await rm(directory, { force: true, recursive: true });
    });
    const target = {
      executable: process.execPath,
      args: [
        "-e",
        [
          'const { spawn } = require("node:child_process");',
          'const { writeFileSync } = require("node:fs");',
          "const child = spawn(process.execPath,",
          '  ["-e", "setTimeout(() => undefined, 5000);"],',
          '  { stdio: "ignore", windowsHide: true });',
          "writeFileSync(process.argv[1], String(child.pid));",
          "child.unref();",
        ].join("\n"),
        pidFile,
      ],
      options: {
        cwd: REPOSITORY_ROOT,
        env: process.env,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      },
    };
    const supervised = windowsJobSpecification(target);
    const startedAt = Date.now();
    const wrapper = spawn(
      supervised.executable,
      supervised.args,
      supervised.options,
    );
    let stderr = "";
    wrapper.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    const code = await new Promise((resolve, reject) => {
      wrapper.once("error", reject);
      wrapper.once("close", resolve);
    });

    assert.equal(code, 0, stderr);
    assert.ok(Date.now() - startedAt < 2_000, "wrapper waited for the orphan");
    descendantPid = Number.parseInt(await readFile(pidFile, "utf8"), 10);
    assert.ok(Number.isSafeInteger(descendantPid) && descendantPid > 0);
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.throws(
      () => process.kill(descendantPid, 0),
      (error) => error?.code === "ESRCH",
    );
  },
);

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
  const exitCodes = [];
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
      platform: "linux",
      registerSignal(signal, handler) {
        signalHandlers.set(signal, handler);
      },
      removeSignal(signal, handler) {
        if (signalHandlers.get(signal) === handler) {
          signalHandlers.delete(signal);
        }
      },
      setExitCode(code) {
        exitCodes.push(code);
      },
      spawnProcess,
    },
    healthCalls,
    exitCodes,
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
  assert.equal(plan.next.options.env.NEXT_PUBLIC_THEME, undefined);
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

test("buildLaunchPlan allowlists only minimal POSIX and named server settings", () => {
  const plan = buildLaunchPlan({
    environment: {
      HOME: "/home/demo",
      LANG: "ko_KR.UTF-8",
      LC_ALL: "ko_KR.UTF-8",
      LC_CTYPE: "ko_KR.UTF-8",
      PATH: "/usr/local/bin:/usr/bin:/bin",
      TEMP: "/tmp",
      TMP: "/tmp",
      TMPDIR: "/tmp",
      OPENAI_API_KEY: "python-only-key",
      AWS_ACCESS_KEY_ID: "cloud-access",
      AWS_SECRET_ACCESS_KEY: "cloud-secret",
      GOOGLE_APPLICATION_CREDENTIALS: "/tmp/cloud.json",
      DATABASE_PASSWORD: "database-password",
      AUTH_SECRET: "auth-secret",
      NEXT_PUBLIC_THEME: "dark",
      NEXT_PUBLIC_PASSWORD: "public-password",
      PORT: "4000",
      TRUSTED_CEO_CODEX_EXECUTABLE: "/usr/local/bin/codex",
      TRUSTED_CEO_CODEX_HOME: "/home/demo/.codex",
      TRUSTED_CEO_INTERNAL_TOKEN: "attacker-token",
      TRUSTED_CEO_REPO_ROOT: "/srv/trusted-ceo",
      TRUSTED_CEO_RUN_ALLOWLIST_ROOT: "/srv/trusted-ceo/runs",
      TRUSTED_CEO_RUN_REGISTRY_PATH: "/srv/trusted-ceo/registry.json",
      TRUSTED_CEO_SERVICE_HOST: "0.0.0.0",
      TRUSTED_CEO_SERVICE_PORT: "9999",
      TRUSTED_CEO_SERVICE_TIMEOUT_MS: "45000",
      TRUSTED_CEO_SERVICE_URL: "https://attacker.invalid",
      TRUSTED_CEO_WEB_PORT: "3100",
      TRUSTED_CEO_WEB_RUNTIME_ROOT: "/srv/trusted-ceo/web-runtime",
      TRUSTED_CEO_UNUSED_CREDENTIAL: "must-not-pass",
    },
    internalToken: INTERNAL_TOKEN,
    platform: "linux",
    repositoryRoot: REPOSITORY_ROOT,
  });

  assert.deepEqual(plan.next.options.env, {
    HOME: "/home/demo",
    LANG: "ko_KR.UTF-8",
    LC_ALL: "ko_KR.UTF-8",
    LC_CTYPE: "ko_KR.UTF-8",
    PATH: "/usr/local/bin:/usr/bin:/bin",
    TEMP: "/tmp",
    TMP: "/tmp",
    TMPDIR: "/tmp",
    TRUSTED_CEO_CODEX_EXECUTABLE: "/usr/local/bin/codex",
    TRUSTED_CEO_CODEX_HOME: "/home/demo/.codex",
    TRUSTED_CEO_REPO_ROOT: "/srv/trusted-ceo",
    TRUSTED_CEO_RUN_ALLOWLIST_ROOT: "/srv/trusted-ceo/runs",
    TRUSTED_CEO_RUN_REGISTRY_PATH: "/srv/trusted-ceo/registry.json",
    TRUSTED_CEO_SERVICE_TIMEOUT_MS: "45000",
    TRUSTED_CEO_WEB_PORT: "3100",
    TRUSTED_CEO_WEB_RUNTIME_ROOT: "/srv/trusted-ceo/web-runtime",
    TRUSTED_CEO_INTERNAL_TOKEN: INTERNAL_TOKEN,
    TRUSTED_CEO_SERVICE_HOST: "127.0.0.1",
    TRUSTED_CEO_SERVICE_PORT: "8765",
    HOSTNAME: "127.0.0.1",
    PORT: "3100",
    TRUSTED_CEO_SERVICE_URL: "http://127.0.0.1:8765",
  });
  assert.equal(plan.next.options.detached, true);
});

test("buildLaunchPlan keeps the minimal Windows runtime environment", () => {
  const environment = {
    APPDATA: "C:\\Users\\demo\\AppData\\Roaming",
    ComSpec: "C:\\Windows\\System32\\cmd.exe",
    HOMEDRIVE: "C:",
    HOMEPATH: "\\Users\\demo",
    LOCALAPPDATA: "C:\\Users\\demo\\AppData\\Local",
    Path: "C:\\Windows\\System32",
    PATHEXT: ".COM;.EXE;.BAT;.CMD",
    SYSTEMDRIVE: "C:",
    SystemRoot: "C:\\Windows",
    TEMP: "C:\\Temp",
    TMP: "C:\\Temp",
    USERPROFILE: "C:\\Users\\demo",
    windir: "C:\\Windows",
    HOME: "C:\\Users\\demo",
    NEXT_PUBLIC_THEME: "dark",
    AZURE_CLIENT_SECRET: "cloud-secret",
  };
  const plan = buildLaunchPlan({
    environment,
    internalToken: INTERNAL_TOKEN,
    platform: "win32",
    repositoryRoot: REPOSITORY_ROOT,
  });

  assert.deepEqual(plan.next.options.env, {
    LOCALAPPDATA: environment.LOCALAPPDATA,
    Path: environment.Path,
    PATHEXT: environment.PATHEXT,
    SystemRoot: environment.SystemRoot,
    TEMP: environment.TEMP,
    TMP: environment.TMP,
    USERPROFILE: environment.USERPROFILE,
    windir: environment.windir,
    TRUSTED_CEO_INTERNAL_TOKEN: INTERNAL_TOKEN,
    TRUSTED_CEO_SERVICE_HOST: "127.0.0.1",
    TRUSTED_CEO_SERVICE_PORT: "8765",
    HOSTNAME: "127.0.0.1",
    PORT: "3000",
    TRUSTED_CEO_SERVICE_URL: "http://127.0.0.1:8765",
    TRUSTED_CEO_WEB_PORT: "3000",
  });
  assert.equal(plan.next.options.detached, false);
});

test("buildLaunchPlan rejects invalid trusted web ports", () => {
  for (const webPort of ["0", "65536", "not-a-port"]) {
    assert.throws(
      () =>
        buildLaunchPlan({
          environment: {
            PATH: "test-path",
            TRUSTED_CEO_WEB_PORT: webPort,
          },
          internalToken: INTERNAL_TOKEN,
          repositoryRoot: REPOSITORY_ROOT,
        }),
      /TRUSTED_CEO_WEB_PORT must be an integer from 1 through 65535/u,
    );
  }
});

test("buildLaunchPlan gives keyless E2E actions the bounded long timeout", () => {
  const plan = buildLaunchPlan({
    environment: {
      PATH: "test-path",
      TRUSTED_CEO_SERVICE_TIMEOUT_MS: "30000",
    },
    internalToken: INTERNAL_TOKEN,
    pythonModule: "trusted_ceo_agent.service.testing_main",
    repositoryRoot: REPOSITORY_ROOT,
    serviceDirectory: "ai-e2e",
  });

  assert.equal(
    plan.next.options.env.TRUSTED_CEO_SERVICE_TIMEOUT_MS,
    "120000",
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

test("controller stop resolves only after both process trees terminate", async () => {
  const harness = launcherHarness();
  const releases = [];
  harness.dependencies.terminateProcessTree = (child) =>
    new Promise((resolve) => {
      releases.push(() => {
        child.treeTerminated = true;
        child.kill("SIGTERM");
        resolve();
      });
    });
  const controller = await startAiDemo(
    {
      environment: {},
      internalToken: INTERNAL_TOKEN,
      repositoryRoot: REPOSITORY_ROOT,
    },
    harness.dependencies,
  );

  const stopping = controller.stop();

  assert.ok(stopping instanceof Promise);
  assert.equal(releases.length, 2);
  assert.equal(harness.children.some((child) => child.treeTerminated), false);
  for (const release of releases) {
    release();
  }
  await stopping;
  assert.equal(harness.children.every((child) => child.treeTerminated), true);
});

test("controller stop waits for the other process tree when one cleanup fails", async () => {
  const harness = launcherHarness();
  let releasePython;
  harness.dependencies.terminateProcessTree = (child) => {
    if (child === harness.children[1]) {
      return Promise.reject(new Error("Next cleanup failed"));
    }
    return new Promise((resolve) => {
      releasePython = resolve;
    });
  };
  const controller = await startAiDemo(
    {
      environment: {},
      internalToken: INTERNAL_TOKEN,
      repositoryRoot: REPOSITORY_ROOT,
    },
    harness.dependencies,
  );

  const stopping = controller.stop();
  let completed = false;
  const outcome = stopping.then(
    () => undefined,
    (error) => error,
  );
  void outcome.then(() => {
    completed = true;
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(completed, false);
  assert.equal(harness.signalHandlers.size, 2);
  releasePython();
  const error = await outcome;
  assert.match(error.message, /Next cleanup failed/);
  assert.equal(harness.signalHandlers.size, 0);
});

test("signal handlers remain active until process-tree cleanup finishes", async () => {
  const harness = launcherHarness();
  const releases = [];
  harness.dependencies.terminateProcessTree = (child) =>
    new Promise((resolve) => {
      releases.push(() => {
        child.treeTerminated = true;
        child.kill("SIGTERM");
        resolve();
      });
    });
  await startAiDemo(
    {
      environment: {},
      internalToken: INTERNAL_TOKEN,
      repositoryRoot: REPOSITORY_ROOT,
    },
    harness.dependencies,
  );

  const stopping = harness.signalHandlers.get("SIGTERM")();
  try {
    assert.equal(harness.signalHandlers.size, 2);
    const repeatedStop = harness.signalHandlers.get("SIGINT")();
    assert.equal(repeatedStop, stopping);
  } finally {
    for (const release of releases) {
      release();
    }
    await stopping;
  }
  assert.equal(harness.signalHandlers.size, 0);
});

for (const [signal, expectedExitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  test(`${signal} preserves its exit code when tree cleanup fails`, async () => {
    const harness = launcherHarness();
    harness.dependencies.terminateProcessTree = () =>
      Promise.reject(new Error("tree cleanup failed"));
    await startAiDemo(
      {
        environment: {},
        internalToken: INTERNAL_TOKEN,
        repositoryRoot: REPOSITORY_ROOT,
      },
      harness.dependencies,
    );

    await assert.rejects(
      harness.signalHandlers.get(signal)(),
      /tree cleanup failed/,
    );

    assert.deepEqual(harness.exitCodes, [expectedExitCode, expectedExitCode]);
  });
}

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

test("startAiDemo cleans up Python when authenticated health never succeeds", async () => {
  const harness = launcherHarness({
    healthResponses: [{
      ok: false,
      async json() {
        return { status: "starting" };
      },
    }],
  });

  await assert.rejects(
    startAiDemo(
      {
        environment: {},
        healthAttempts: 2,
        internalToken: INTERNAL_TOKEN,
        repositoryRoot: REPOSITORY_ROOT,
      },
      harness.dependencies,
    ),
    /Python service did not pass authenticated health/,
  );

  assert.equal(harness.healthCalls.length, 2);
  assert.equal(harness.spawnCalls.length, 1);
  assert.deepEqual(harness.children[0].killSignals, ["SIGTERM"]);
  assert.equal(harness.signalHandlers.size, 0);
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
    await harness.signalHandlers.get(signal)();

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
