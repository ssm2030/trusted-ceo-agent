import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { setTimeout as pause } from "node:timers/promises";

export const DEFAULT_HEALTH_ATTEMPTS = 120;
const HEALTH_INTERVAL_MS = 250;
const HEALTH_REQUEST_TIMEOUT_MS = 1_000;
const PROCESS_TREE_GRACE_MS = 1_000;
const initialWindowsRoot =
  process.env.SystemRoot ?? process.env.WINDIR ?? "C:\\Windows";
const windowsTaskkillExecutable = path.win32.join(
  path.win32.isAbsolute(initialWindowsRoot)
    ? initialWindowsRoot
    : "C:\\Windows",
  "System32",
  "taskkill.exe",
);

export function defaultDependencies(overrides) {
  return {
    ensureDirectory: (directory) => mkdir(directory, { recursive: true }),
    fetchImpl: globalThis.fetch.bind(globalThis),
    pause: (milliseconds) =>
      new Promise((resolve) => setTimeout(resolve, milliseconds)),
    platform: process.platform,
    registerSignal: (signal, handler) => process.on(signal, handler),
    removeSignal: (signal, handler) => process.off(signal, handler),
    setExitCode: (code) => {
      process.exitCode = code;
    },
    spawnProcess: spawn,
    terminateProcessTree: terminateChild,
    ...overrides,
  };
}

export function windowsJobSpecification(specification) {
  const cwd = specification?.options?.cwd;
  if (typeof cwd !== "string" || !path.isAbsolute(cwd)) {
    throw new Error("Windows child working directory must be absolute.");
  }
  const payload = Buffer.from(
    JSON.stringify({
      executable: specification.executable,
      args: specification.args,
      cwd,
    }),
    "utf8",
  ).toString("base64url");
  return {
    ...specification,
    executable: path.join(
      cwd,
      "plugin",
      "trusted-ceo-agent",
      ".venv",
      "Scripts",
      "python.exe",
    ),
    args: [
      path.join(cwd, "web", "scripts", "windows-job-runner.py"),
      payload,
    ],
  };
}

export function spawnChild(specification, dependencies, label) {
  const supervised =
    dependencies.platform === "win32"
      ? windowsJobSpecification(specification)
      : specification;
  try {
    return dependencies.spawnProcess(
      supervised.executable,
      supervised.args,
      supervised.options,
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

function directChildSignal(child, signal) {
  if (!childIsRunning(child)) {
    return;
  }
  try {
    child.kill(signal);
  } catch {
    // The child may have exited between the state check and kill request.
  }
}

function signalProcessGroup(killProcess, pid, signal) {
  try {
    killProcess(-pid, signal);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") {
      return false;
    }
    throw error;
  }
}

function defaultWindowsTreeTermination(pid, spawnProcess) {
  return new Promise((resolve, reject) => {
    let killer;
    try {
      killer = spawnProcess(
        windowsTaskkillExecutable,
        ["/PID", String(pid), "/T", "/F"],
        {
          shell: false,
          stdio: "ignore",
          windowsHide: true,
        },
      );
    } catch {
      reject(new Error("Windows process tree could not be terminated."));
      return;
    }
    let settled = false;
    const finish = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      if (error === undefined) {
        resolve();
      } else {
        reject(error);
      }
    };
    killer.once("error", () => {
      finish(new Error("Windows process tree could not be terminated."));
    });
    killer.once("close", (code) => {
      finish(
        code === 0
          ? undefined
          : new Error("Windows process tree could not be terminated."),
      );
    });
  });
}

export async function terminateChild(
  child,
  {
    graceMs = PROCESS_TREE_GRACE_MS,
    killProcess = process.kill.bind(process),
    pause: pauseImpl = pause,
    platform = process.platform,
    spawnProcess = spawn,
    terminateWindowsTree,
  } = {},
) {
  if (child === undefined) {
    return;
  }
  if (!Number.isInteger(graceMs) || graceMs < 0) {
    throw new Error("Process tree grace period is invalid.");
  }
  if (platform === "win32" && !childIsRunning(child)) {
    return;
  }
  const pid = child.pid;
  if (!Number.isSafeInteger(pid) || pid < 1) {
    directChildSignal(child, "SIGTERM");
    return;
  }
  if (platform === "win32") {
    const terminate =
      terminateWindowsTree ??
      ((targetPid) => defaultWindowsTreeTermination(targetPid, spawnProcess));
    await terminate(pid);
    return;
  }
  if (!signalProcessGroup(killProcess, pid, "SIGTERM")) {
    directChildSignal(child, "SIGTERM");
    return;
  }
  await pauseImpl(graceMs);
  signalProcessGroup(killProcess, pid, "SIGKILL");
}
