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
  waitForAuthenticatedHealth,
} from "./child-supervisor.mjs";

export { buildLaunchPlan, loadRootEnvironment };

export function launchFailureExitCode(currentExitCode) {
  return Number.isInteger(currentExitCode) && currentExitCode > 0
    ? currentExitCode
    : 1;
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
  let stopPromise;
  let detachRuntimeListeners = () => undefined;
  const signalHandlers = new Map();

  const removeSignalHandlers = () => {
    for (const [signal, handler] of signalHandlers) {
      dependencies.removeSignal(signal, handler);
    }
    signalHandlers.clear();
  };

  const stop = (exitCode) => {
    if (stopPromise !== undefined) {
      return stopPromise;
    }
    stopping = true;
    detachRuntimeListeners();
    if (exitCode !== undefined) {
      dependencies.setExitCode(exitCode);
    }
    const terminate = (child) => {
      try {
        return Promise.resolve(dependencies.terminateProcessTree(child));
      } catch (error) {
        return Promise.reject(error);
      }
    };
    stopPromise = Promise.allSettled([
      terminate(nextChild),
      terminate(pythonChild),
    ])
      .then((results) => {
        const failure = results.find((result) => result.status === "rejected");
        if (failure !== undefined) {
          throw failure.reason;
        }
      })
      .finally(removeSignalHandlers);
    return stopPromise;
  };

  const stopAfterRuntimeEvent = (exitCode) => {
    const stoppingNow = stop(exitCode);
    void stoppingNow.catch(() => {
      dependencies.setExitCode(launchFailureExitCode(exitCode));
    });
    return stoppingNow;
  };

  for (const [signal, exitCode] of [
    ["SIGINT", 130],
    ["SIGTERM", 143],
  ]) {
    const handler = () => stopAfterRuntimeEvent(exitCode);
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

    const onPythonStop = () => stopAfterRuntimeEvent(1);
    const onNextError = () => stopAfterRuntimeEvent(1);
    const onNextExit = (code) =>
      stopAfterRuntimeEvent(
        Number.isInteger(code) && code >= 0 ? code : 1,
      );
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
    await stop();
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
    process.exitCode = launchFailureExitCode(process.exitCode);
  });
}
