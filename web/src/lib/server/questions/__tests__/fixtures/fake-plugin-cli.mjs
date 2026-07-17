const mode = process.env.FAKE_PLUGIN_MODE ?? "success";
const command =
  process.argv.find((value) =>
    [
      "prepare-result-question",
      "validate-result-answer",
    ].includes(value),
  ) ?? "prepare-result-question";

if (mode === "oversize") {
  process.stdout.write("x".repeat(4096));
  process.exit(0);
}

if (mode === "invalid-json") {
  process.stdout.write("{");
  process.exit(0);
}

if (mode === "stderr") {
  process.stderr.write(
    `failure at ${process.cwd()} raw-secret-question`,
  );
  process.exit(5);
}

process.stdout.write(
  `${JSON.stringify({
    contract_version: "1.0.0",
    ok: true,
    code: 0,
    command,
    message: "ok",
    run_id: "run_20260717T010203Z_0123456789abcdef",
    revision: 3,
    state: "finalized",
    data: { marker: "validated" },
  })}\n`,
);
