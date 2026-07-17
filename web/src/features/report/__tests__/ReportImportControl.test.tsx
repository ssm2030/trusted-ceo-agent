import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReportImportControl } from "@/features/report/ReportImportControl";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReportImportControl", () => {
  it("sends one JSON file as the raw body with the localhost CSRF headers", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn().mockResolvedValue(undefined);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        imported: true,
        eligibility: {
          mode: "unverified_import",
          label: "독립 가져오기 · 미검증",
          trusted: false,
          questionsAllowed: false,
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["{}"], "web-report-bundle.json", {
      type: "application/json",
    });

    render(
      <ReportImportControl
        csrfToken="csrf_test_only"
        hasCurrentReport
        onImported={onImported}
      />,
    );

    await user.upload(
      screen.getByLabelText("웹 리포트 JSON 파일"),
      file,
    );
    await user.click(screen.getByRole("button", { name: "리포트 가져오기" }));

    expect(fetchMock).toHaveBeenCalledWith("/api/report/import", {
      body: file,
      headers: {
        "Content-Type": "application/json",
        "x-csrf-token": "csrf_test_only",
        "x-trusted-ceo-file-name": "web-report-bundle.json",
      },
      method: "POST",
    });
    expect(onImported).toHaveBeenCalledOnce();
    expect(
      await screen.findByText("검증된 결과로 교체했습니다."),
    ).toBeInTheDocument();
  });

  it("keeps the current report when server validation rejects the file", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 422 }),
    );

    render(
      <ReportImportControl
        csrfToken="csrf_test_only"
        hasCurrentReport
        onImported={onImported}
      />,
    );
    await user.upload(
      screen.getByLabelText("웹 리포트 JSON 파일"),
      new File(["{}"], "web-report-bundle.json", {
        type: "application/json",
      }),
    );
    await user.click(screen.getByRole("button", { name: "리포트 가져오기" }));

    expect(onImported).not.toHaveBeenCalled();
    expect(
      await screen.findByText(
        "묶음 검증에 실패했습니다. 기존 결과는 유지됩니다.",
      ),
    ).toBeInTheDocument();
  });

  it("rejects an unexpected filename before upload", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReportImportControl
        csrfToken="csrf_test_only"
        hasCurrentReport={false}
        onImported={vi.fn()}
      />,
    );
    await user.upload(
      screen.getByLabelText("웹 리포트 JSON 파일"),
      new File(["{}"], "other.json", { type: "application/json" }),
    );

    expect(
      screen.getByText("파일 이름은 web-report-bundle.json이어야 합니다."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "리포트 가져오기" }),
    ).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
