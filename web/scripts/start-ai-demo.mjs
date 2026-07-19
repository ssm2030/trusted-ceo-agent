#!/usr/bin/env node
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const LOOPBACK_HOST = "127.0.0.1";
const SERVICE_PORT = 8765;
const DEFAULT_HEALTH_ATTEMPTS = 120;
const HEALTH_INTERVAL_MS = 250;
const HEALTH_REQUEST_TIMEOUT_MS = 1_000;
const PUBLIC_PREFIX = "NEXT_PUBLIC_";
const PUBLIC_SECRET_PARTS = new Set([
  "CREDENTIAL",
  "KEY",
  "OPENAI",
  "SECRET",
  "TOKEN",
]);
const DEFAULT_REPOSITORY_ROOT = path.resolve(import.meta.dirname, "../..");

function hasSecretPublicName(name) {
  if (!name.startsWith(PUBLIC_PREFIX)) {
    return false;
  }
  return name
    .slice(PUBLIC_PREFIX.length)
    .toUpperCase()
    .split("_")
    .some((part) => PUBLIC_SECRET_PARTS.has(part));
}

function isUsableInternalToken(token) {
  return (
    typeof token === "string" &&
    token.length <= 256 &&
    /^[A-Za-z0-9_-]+$/u.test(token) &&
    Buffer.from(token, "base64url").byteLength >= 32
  );
}

function browserSafeEnvironment(
  environment,
  { existingInternalToken, internalToken, openAiApiKey },
) {
  const secretValues = new Set(
    [existingInternalToken, internalToken, openAiApiKey].filter(
      (value) => typeof value === "string" && value.length > 0,
    ),
  );
  return Object.fromEntries(
    Object.entries(environment).filter(
      ([name, value]) =>
        !hasSecretPublicName(name) && !secretValues.has(value),
    ),
  );
}

function npmInvocation(environment, platform, nodeExecutable) {
  const args = ["--prefix", "web", "run", "dev"];
  if (platform !== "win32") {
    return { args, executable: "npm" };
  }
  const configuredNpmCli = environment.npm_execpath;
  const npmCli =
    typeof configuredNpmCli === "string" &&
    path.isAbsolute(configuredNpmCli) &&
    path.basename(configuredNpmCli).toLowerCase() === "npm-cli.js"
      ? configuredNpmCli
      : path.join(
          path.dirname(nodeExecutable),
          "node_modules",
          "npm",
          "bin",
          "npm-cli.js",
        );
  return {
    args: [npmCli, ...args],
    executable: nodeExecutable,
  };
}

export function loadRootEnvironment(
  repositoryRoot,
  loadEnvFile = (filename) => process.loadEnvFile(filename),
) {
  const filename = path.join(path.resolve(repositoryRoot), ".env.local");
  try {
    loadEnvFile(filename);
    return true;
  } catch (error) {
    if (
      error !== null &&
      typeof error === "object" &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return false;
    }
    throw new Error("Repository environment could not be loaded.");
  }
}

export function buildLaunchPlan({
  environment = process.env,
  internalToken = randomBytes(32).toString("base64url"),
  nodeExecutable = process.execPath,
  platform = process.platform,
  repositoryRoot = DEFAULT_REPOSITORY_ROOT,
} = {}) {
  if (!isUsableInternalToken(internalToken)) {
    throw new Error("Internal token must contain at least 32 random bytes.");
  }

  const resolvedRoot = path.resolve(repositoryRoot);
  const serviceRoot = path.join(resolvedRoot, "web", "var", "ai-service");
  const serviceUrl = `http://${LOOPBACK_HOST}:${SERVICE_PORT}`;
  const {
    OPENAI_API_KEY: openAiApiKey,
    TRUSTED_CEO_INTERNAL_TOKEN: existingInternalToken,
    ...publicServerEnvironment
  } = environment;
  const sharedServiceEnvironment = {
    TRUSTED_CEO_INTERNAL_TOKEN: internalToken,
    TRUSTED_CEO_SERVICE_HOST: LOOPBACK_HOST,
    TRUSTED_CEO_SERVICE_PORT: String(SERVICE_PORT),
  };
  const nextEnvironment = {
    ...browserSafeEnvironment(publicServerEnvironment, {
      existingInternalToken,
      internalToken,
      openAiApiKey,
    }),
    ...sharedServiceEnvironment,
    HOSTNAME: LOOPBACK_HOST,
    TRUSTED_CEO_SERVICE_URL: serviceUrl,
  };
  const pythonEnvironment = {
    ...environment,
    ...sharedServiceEnvironment,
    TRUSTED_CEO_SERVICE_ROOT: serviceRoot,
  };

  const childOptions = (env) => ({
    cwd: resolvedRoot,
    env,
    shell: false,
    stdio: "inherit",
    windowsHide: true,
  });
  const nextInvocation = npmInvocation(
    environment,
    platform,
    nodeExecutable,
  );

  return {
    healthHeaders: {
      "X-Trusted-Ceo-Internal-Token": internalToken,
    },
    healthUrl: `${serviceUrl}/health`,
    internalToken,
    next: {
      ...nextInvocation,
      options: childOptions(nextEnvironment),
    },
    python: {
      args: [
        "run",
        "--project",
        "plugin/trusted-ceo-agent",
        "--frozen",
        "python",
        "-m",
        "trusted_ceo_agent.service.main",
      ],
      executable: "uv",
      options: childOptions(pythonEnvironment),
    },
    serviceRoot,
  };
}

function defaultDependencies(overrides) {
  return {
    ensureDirectory: (directory) => mkdir(directory, { recursive: true }),
    fetchImpl: globalThis.fetch.bind(globalThis),
    pause: (milliseconds) =>
      new Promise((resolve) => setTimeout(resolve, milliseconds)),
    registerSignal: (signal, handler) => process.once(signal, handler),
    removeSignal: (signal, handler) => process.off(signal, handler),
    setExitCode: (code) => {
      process.exitCode = code;
    },
    spawnProcess: spawn,
    ...overrides,
  };
}

function spawnChild(specification, dependencies, label) {
  try {
    return dependencies.spawnProcess(
      specification.executable,
      specification.args,
      specification.options,
    );
  } catch {
    throw new Error(`${label} child could not start.`);
  }
}

function observeChildStop(child) {
  let onError;
  let onExit;
  const promise = new Promise((resolve) => {
    onError = () => resolve({ kind: "stopped" });
    onExit = () => resolve({ kind: "stopped" });
    child.once("error", onError);
    child.once("exit", onExit);
  });
  return {
    dispose() {
      child.off("error", onError);
      child.off("exit", onExit);
    },
    promise,
  };
}

async function requestAuthenticatedHealth(plan, fetchImpl) {
  try {
    const response = await fetchImpl(plan.healthUrl, {
      cache: "no-store",
      headers: plan.healthHeaders,
      method: "GET",
      signal: AbortSignal.timeout(HEALTH_REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      return false;
    }
    const body = await response.json();
    return body !== null && typeof body === "object" && body.status === "ok";
  } catch {
    return false;
  }
}

async function waitForAuthenticatedHealth(
  plan,
  pythonChild,
  dependencies,
  attempts,
) {
  const stopped = observeChildStop(pythonChild);
  try {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const outcome = await Promise.race([
        requestAuthenticatedHealth(plan, dependencies.fetchImpl).then(
          (ready) => ({ kind: "health", ready }),
        ),
        stopped.promise,
      ]);
      if (outcome.kind === "stopped") {
        throw new Error(
          "Python service stopped before authenticated health succeeded.",
        );
      }
      if (outcome.ready) {
        return;
      }
      if (attempt + 1 < attempts) {
        await dependencies.pause(HEALTH_INTERVAL_MS);
      }
    }
  } finally {
    stopped.dispose();
  }
  throw new Error("Python service did not pass authenticated health.");
}

function childIsRunning(child) {
  return (
    child !== undefined &&
    child.exitCode === null &&
    child.signalCode === null &&
    !child.killed
  );
}

function terminateChild(child) {
  if (!childIsRunning(child)) {
    return;
  }
  try {
    child.kill("SIGTERM");
  } catch {
    // The child may have exited between the state check and kill request.
  }
}

export async function startAiDemo(options = {}, dependencyOverrides = {}) {
  const dependencies = defaultDependencies(dependencyOverrides);
  const plan = buildLaunchPlan(options);
  const healthAttempts = options.healthAttempts ?? DEFAULT_HEALTH_ATTEMPTS;
  if (!Number.isInteger(healthAttempts) || healthAttempts < 1) {
    throw new Error("healthAttempts must be a positive integer.");
  }

  await dependencies.ensureDirectory(plan.serviceRoot);
  const pythonChild = spawnChild(plan.python, dependencies, "Python");
  let nextChild;
  let stopping = false;
  let detachRuntimeListeners = () => undefined;
  const signalHandlers = new Map();

  const removeSignalHandlers = () => {
    for (const [signal, handler] of signalHandlers) {
      dependencies.removeSignal(signal, handler);
    }
    signalHandlers.clear();
  };

  const stop = (exitCode) => {
    if (stopping) {
      return;
    }
    stopping = true;
    removeSignalHandlers();
    detachRuntimeListeners();
    terminateChild(nextChild);
    terminateChild(pythonChild);
    if (exitCode !== undefined) {
      dependencies.setExitCode(exitCode);
    }
  };

  for (const [signal, exitCode] of [
    ["SIGINT", 130],
    ["SIGTERM", 143],
  ]) {
    const handler = () => stop(exitCode);
    signalHandlers.set(signal, handler);
    dependencies.registerSignal(signal, handler);
  }

  try {
    await waitForAuthenticatedHealth(
      plan,
      pythonChild,
      dependencies,
      healthAttempts,
    );
    if (
      stopping ||
      pythonChild.exitCode !== null ||
      pythonChild.signalCode !== null
    ) {
      throw new Error(
        "Python service stopped before authenticated health succeeded.",
      );
    }
    nextChild = spawnChild(plan.next, dependencies, "Next");

    const onPythonStop = () => stop(1);
    const onNextError = () => stop(1);
    const onNextExit = (code) =>
      stop(Number.isInteger(code) && code >= 0 ? code : 1);
    pythonChild.once("error", onPythonStop);
    pythonChild.once("exit", onPythonStop);
    nextChild.once("error", onNextError);
    nextChild.once("exit", onNextExit);
    detachRuntimeListeners = () => {
      pythonChild.off("error", onPythonStop);
      pythonChild.off("exit", onPythonStop);
      nextChild.off("error", onNextError);
      nextChild.off("exit", onNextExit);
    };

    if (nextChild.exitCode !== null || nextChild.signalCode !== null) {
      onNextExit(nextChild.exitCode);
    }
  } catch (error) {
    stop();
    throw error;
  }

  return Object.freeze({
    plan,
    stop: () => stop(),
  });
}

export async function main() {
  loadRootEnvironment(DEFAULT_REPOSITORY_ROOT);
  await startAiDemo({ repositoryRoot: DEFAULT_REPOSITORY_ROOT });
}

const modulePath = path.resolve(fileURLToPath(import.meta.url));
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
const isMain =
  process.platform === "win32"
    ? invokedPath.toLowerCase() === modulePath.toLowerCase()
    : invokedPath === modulePath;

if (isMain) {
  main().catch(() => {
    process.stderr.write("Trusted CEO Agent demo launcher could not start.\n");
    process.exitCode = 1;
  });
}
