import assert from "node:assert/strict";
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
