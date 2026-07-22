import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  lstat,
  mkdir,
  open,
  rename,
  rm,
} from "node:fs/promises";
import path from "node:path";

import {
  MAX_OUTPUT_BYTES,
  TIMEOUT_MS,
  canonicalize,
} from "./question-preflight-policy.mjs";
import { terminateChild } from "./child-supervisor.mjs";

export async function runBounded(
  executable,
  args,
  {
    cwd,
    env,
    platform = process.platform,
    spawnProcess = spawn,
    terminateProcessTree = terminateChild,
    timeoutMs = TIMEOUT_MS,
  } = {},
) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawnProcess(executable, args, {
        cwd,
        detached: platform !== "win32",
        env,
        shell: false,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch {
      resolve({ code: null, stdout: "", exceeded: false });
      return;
    }
    const stdout = [];
    let bytes = 0;
    let exceeded = false;
    let timedOut = false;
    let settled = false;
    let termination;
    let timer;
    const stopProcessTree = () => {
      if (termination === undefined) {
        termination = Promise.resolve().then(() =>
          terminateProcessTree(child, { platform }),
        );
      }
      return termination;
    };
    const settle = async (result) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      try {
        await termination;
        resolve(result);
      } catch {
        reject(new Error("Preflight process tree could not be terminated."));
      }
    };
    const settleAfterTermination = (result) => {
      void stopProcessTree().then(
        () => settle(result),
        () => settle(result),
      );
    };
    const accept = (chunk, keep) => {
      bytes += chunk.byteLength;
      if (bytes > MAX_OUTPUT_BYTES) {
        exceeded = true;
        settleAfterTermination({
          code: null,
          stdout: Buffer.concat(stdout).toString("utf8"),
          exceeded,
          timedOut,
        });
      } else if (keep) {
        stdout.push(chunk);
      }
    };
    child.stdout.on("data", (chunk) => accept(chunk, true));
    child.stderr.on("data", (chunk) => accept(chunk, false));
    timer = setTimeout(() => {
      timedOut = true;
      settleAfterTermination({
        code: null,
        stdout: Buffer.concat(stdout).toString("utf8"),
        exceeded,
        timedOut,
      });
    }, timeoutMs);
    child.once("error", () => {
      void settle({
        code: null,
        stdout: "",
        exceeded,
        timedOut,
      });
    });
    child.once("close", (code) => {
      void settle({
        code,
        stdout: Buffer.concat(stdout).toString("utf8"),
        exceeded,
        timedOut,
      });
    });
  });
}


export async function writePrivate(filePath, value) {
  const handle = await open(filePath, "wx", 0o600);
  try {
    await handle.chmod(0o600);
    await handle.writeFile(value);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

export async function atomicReceipt(filePath, receipt) {
  const parent = path.dirname(filePath);
  await mkdir(parent, { recursive: true, mode: 0o700 });
  const temporary = `${filePath}.${randomUUID()}.tmp`;
  try {
    await writePrivate(
      temporary,
      `${canonicalize(receipt)}\n`,
    );
    await rename(temporary, filePath);
  } finally {
    await rm(temporary, { force: true });
  }
}

export async function hasFileBackedAuth(codexHome) {
  for (const name of ["auth.json", "credentials.json"]) {
    try {
      const details = await lstat(path.join(codexHome, name));
      if (details.isFile()) {
        return true;
      }
    } catch (error) {
      if (
        typeof error !== "object" ||
        error === null ||
        error.code !== "ENOENT"
      ) {
        return true;
      }
    }
  }
  return false;
}
