import { writeFile } from "node:fs/promises";

const mode = process.env.FAKE_CODEX_MODE ?? "success";
const outputIndex = process.argv.indexOf("--output-last-message");
const outputPath =
  outputIndex >= 0 ? process.argv[outputIndex + 1] : undefined;

if (mode === "timeout") {
  setInterval(() => undefined, 1000);
} else if (mode === "oversize") {
  process.stdout.write("x".repeat(4096));
} else {
  process.stdout.write(
    `${JSON.stringify({ type: "turn.started" })}\n`,
  );
  if (mode === "stderr-warning") {
    process.stderr.write("non-fatal warning\n");
  }
  if (outputPath === undefined) {
    process.exitCode = 5;
  } else if (mode === "invalid-json") {
    await writeFile(outputPath, "{", "utf8");
  } else {
    await writeFile(
      outputPath,
      JSON.stringify({
        draft_version: "1.0.0",
        job_id: "job_123",
        run_id: "run_20260717T010203Z_0123456789abcdef",
        revision: 3,
        answer_blocks: [],
      }),
      "utf8",
    );
  }
}
