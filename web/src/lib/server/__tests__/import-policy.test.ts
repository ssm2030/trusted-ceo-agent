// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  MAX_REPORT_IMPORT_BYTES,
  assertReportImport,
  readRequestBodyWithinLimit,
} from "@/lib/server/import-policy";

describe("report import policy", () => {
  it("accepts only the one exact JSON bundle filename and media type", () => {
    expect(() =>
      assertReportImport({
        fileName: "web-report-bundle.json",
        contentType: "application/json",
        contentLength: 1024,
      }),
    ).not.toThrow();

    for (const fileName of [
      "report.json",
      "web-report-bundle.zip",
      "../web-report-bundle.json",
      String.raw`C:\web-report-bundle.json`,
    ]) {
      expect(() =>
        assertReportImport({
          fileName,
          contentType: "application/json",
          contentLength: 1024,
        }),
      ).toThrow("web-report-bundle.json 한 파일");
    }
  });

  it("rejects missing, empty, and oversized request lengths before reading", () => {
    for (const contentLength of [0, -1, MAX_REPORT_IMPORT_BYTES + 1]) {
      expect(() =>
        assertReportImport({
          fileName: "web-report-bundle.json",
          contentType: "application/json",
          contentLength,
        }),
      ).toThrow();
    }
    expect(() =>
      assertReportImport({
        fileName: "web-report-bundle.json",
        contentType: "application/json; charset=utf-8",
        contentLength: 1,
      }),
    ).toThrow("application/json");
  });

  it("enforces the actual streamed byte limit instead of trusting metadata", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2, 3]));
        controller.enqueue(new Uint8Array([4, 5, 6]));
        controller.close();
      },
    });

    await expect(readRequestBodyWithinLimit(stream, 5)).rejects.toThrow(
      "50 MiB",
    );
  });
});
