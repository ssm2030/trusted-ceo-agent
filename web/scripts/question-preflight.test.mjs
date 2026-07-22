import assert from "node:assert/strict";
import {
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
} from "node:fs/promises";
import { EventEmitter } from "node:events";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  parseArguments,
  receiptHash,
  seatbeltProfile,
} from "./question-preflight-policy.mjs";
import {
  atomicReceipt,
  runBounded,
} from "./question-preflight-io.mjs";

test("preflight policy parses only absolute paths", () => {
  const root = path.resolve("preflight-fixture");
  assert.deepEqual(
    parseArguments([
      "--codex",
      path.join(root, "codex"),
      "--codex-home",
      path.join(root, "home"),
      "--output",
      path.join(root, "receipt.json"),
    ]),
    {
      codex: path.join(root, "codex"),
      codexHome: path.join(root, "home"),
      output: path.join(root, "receipt.json"),
    },
  );
});

test("preflight policy hashing and seatbelt rendering are deterministic", () => {
  assert.equal(receiptHash({ b: 2, a: 1 }), receiptHash({ a: 1, b: 2 }));
  assert.match(
    seatbeltProfile({
      codexExecutable: "/usr/local/bin/codex",
      questionRoot: "/tmp/question",
      outputRoot: "/tmp/output",
    }),
    /deny file-write/,
  );
});

test("preflight I/O exposes bounded execution and atomic receipt adapters", () => {
  assert.equal(typeof runBounded, "function");
  assert.equal(typeof atomicReceipt, "function");
});

test("runBounded returns stdout without exposing stderr", async () => {
  const result = await runBounded(
    process.execPath,
    [
      "-e",
      'process.stdout.write("visible"); process.stderr.write("secret");',
    ],
    { timeoutMs: 5_000 },
  );

  assert.deepEqual(result, {
    code: 0,
    stdout: "visible",
    exceeded: false,
    timedOut: false,
  });
  assert.doesNotMatch(result.stdout, /secret/);
});

test("runBounded terminates a child that exceeds its timeout", async () => {
  const result = await runBounded(
    process.execPath,
    ["-e", "setInterval(() => undefined, 1_000);"],
    { timeoutMs: 25 },
  );

  assert.equal(result.timedOut, true);
  assert.equal(result.exceeded, false);
});

test("runBounded timeout completes only after process-tree cleanup", async () => {
  const tree = { descendantAlive: true };
  const result = await runBounded(
    process.execPath,
    ["-e", "setInterval(() => undefined, 1_000);"],
    {
      timeoutMs: 25,
      async terminateProcessTree(child) {
        assert.ok(Number.isSafeInteger(child.pid) && child.pid > 0);
        child.kill("SIGKILL");
        await new Promise((resolve) => setTimeout(resolve, 25));
        tree.descendantAlive = false;
      },
    },
  );

  assert.equal(result.timedOut, true);
  assert.equal(tree.descendantAlive, false);
});

test("runBounded rejects when process-tree cleanup fails without a close event", async () => {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();

  await assert.rejects(
    runBounded("unused", [], {
      timeoutMs: 1,
      spawnProcess() {
        return child;
      },
      async terminateProcessTree() {
        throw new Error("cleanup failed");
      },
    }),
    /could not be terminated/,
  );
});

test("atomicReceipt writes canonical JSON without temporary residue", async (context) => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "trusted-ceo-preflight-"),
  );
  context.after(async () => {
    await rm(directory, { force: true, recursive: true });
  });
  const target = path.join(directory, "receipt.json");

  await atomicReceipt(target, { b: 2, a: 1 });

  assert.equal(await readFile(target, "utf8"), '{"a":1,"b":2}\n');
  assert.deepEqual(await readdir(directory), ["receipt.json"]);
  if (process.platform !== "win32") {
    assert.equal((await stat(target)).mode & 0o777, 0o600);
  }
});
