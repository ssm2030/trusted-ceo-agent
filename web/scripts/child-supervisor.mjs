import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";


export const DEFAULT_HEALTH_ATTEMPTS = 120;
const HEALTH_INTERVAL_MS = 250;
const HEALTH_REQUEST_TIMEOUT_MS = 1_000;

export function defaultDependencies(overrides) {
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

export function spawnChild(specification, dependencies, label) {
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

export async function waitForAuthenticatedHealth(
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

export function childIsRunning(child) {
  return (
    child !== undefined &&
    child.exitCode === null &&
    child.signalCode === null &&
    !child.killed
  );
}

export function terminateChild(child) {
  if (!childIsRunning(child)) {
    return;
  }
  try {
    child.kill("SIGTERM");
  } catch {
    // The child may have exited between the state check and kill request.
  }
}
