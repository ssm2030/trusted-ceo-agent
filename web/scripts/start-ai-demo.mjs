import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_REPOSITORY_ROOT,
  buildLaunchPlan,
  loadRootEnvironment,
} from "./ai-launch-plan.mjs";
import {
  DEFAULT_HEALTH_ATTEMPTS,
  defaultDependencies,
  spawnChild,
  terminateChild,
  waitForAuthenticatedHealth,
} from "./child-supervisor.mjs";

export { buildLaunchPlan, loadRootEnvironment };

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
