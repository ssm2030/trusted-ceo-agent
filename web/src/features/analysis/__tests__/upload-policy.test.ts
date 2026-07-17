import { describe, expect, it } from "vitest";

import { validateReplayFile } from "@/features/analysis/replay-provider";

describe("validateReplayFile", () => {
  it.each(["company.csv", "company.json", "company.xlsx"])(
    "accepts %s in the analysis workspace",
    (name) => {
      expect(validateReplayFile({ name, size: 128, type: "" }).accepted).toBe(true);
    },
  );

  it("rejects archives", () => {
    expect(
      validateReplayFile({
        name: "company.zip",
        size: 128,
        type: "application/zip",
      }),
    ).toEqual({
      accepted: false,
      message: "분석 자료는 CSV, JSON, XLSX 파일만 선택할 수 있습니다.",
    });
  });
});
