import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

async function actionable(page: Page, name: string): Promise<boolean> {
  const button = page.getByRole("button", { name, exact: true });
  return await button.isVisible().catch(() => false)
    && await button.isEnabled().catch(() => false);
}

async function driveToFinalized(page: Page): Promise<number> {
  let approvals = 0;
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    const failure = page.locator(".inline-error[role='alert']").last();
    if (await failure.isVisible().catch(() => false)) {
      throw new Error(`AI service flow failed: ${await failure.textContent()}`);
    }
    if (await actionable(page, "최종 보고서 열기")) return approvals;
    if (await actionable(page, "승인")) {
      await page.getByRole("button", { name: "승인", exact: true }).click();
      approvals += 1;
    } else if (await actionable(page, "분석 계속")) {
      await page.getByRole("button", { name: "분석 계속", exact: true }).click();
    } else if (await actionable(page, "실패 단계 다시 시도")) {
      await page.getByRole("button", { name: "실패 단계 다시 시도", exact: true }).click();
    } else {
      await page.waitForTimeout(250);
    }
  }
  throw new Error("AI service flow did not finalize within the 180 second deadline");
}

test.describe.configure({ mode: "serial" });

test("keyless localhost service completes HITL, report, question, and delete", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await page.goto("/analysis");

  await expect(page.getByRole("heading", { name: "실시간 AI 분석" })).toBeVisible();
  await expect(page.getByText("실시간 AI 분석", { exact: true }).last()).toBeVisible();
  const fileInput = page.getByLabel("분석 자료 선택");
  const folderInput = page.getByLabel("분석 폴더 선택");
  await fileInput.setInputFiles({
    name: "plan.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Strategy\nRevenue assumptions are provisional.\n"),
  });
  await expect(page.getByText("plan.md", { exact: true })).toBeVisible();
  await fileInput.setInputFiles(
    path.resolve("tests/fixtures/company-diagnostic.json"),
  );
  await expect(page.getByText("company-diagnostic.json")).toBeVisible();

  await folderInput.evaluate((element) => {
    const input = element as HTMLInputElement;
    const file = new File(
      ["period,gross_margin\n2026-01,0.42\n2026-02,0.39\n"],
      "data.csv",
      { type: "text/csv" },
    );
    Object.defineProperty(file, "webkitRelativePath", {
      configurable: true,
      value: "폴더B/sub/data.csv",
    });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await expect(page.getByRole("heading", { name: "개별 파일", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "폴더B", exact: true })).toBeVisible();
  await expect(page.getByText("폴더B/sub/data.csv", { exact: true })).toBeVisible();

  const runId = await page.locator(".run-header dd").nth(1).textContent();
  expect(runId).toMatch(/^run_/u);
  await page.reload();
  await expect(
    page.getByLabel("현재 실행 정보").getByText(runId!, { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "개별 파일", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "폴더B", exact: true })).toBeVisible();
  await expect(page.getByText("plan.md", { exact: true })).toBeVisible();
  await expect(page.getByText("폴더B/sub/data.csv", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "분석 계속", exact: true }).click();
  await expect(fileInput).toBeDisabled();
  await expect(folderInput).toBeDisabled();

  const approvals = await driveToFinalized(page);
  expect(approvals).toBeGreaterThanOrEqual(4);
  await expect(page.getByText("완료", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "최종 보고서 열기" }).click();
  await expect(page).toHaveURL(/\/report$/u, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "결과 리포트" })).toBeVisible();
  await expect(page.getByRole("button", { name: "결과에 질문하기" })).toBeVisible();
  await expect(page.getByText(/Codex|플러그인/u)).toHaveCount(0);

  await page.getByRole("button", { name: "결과에 질문하기" }).click();
  const questionBox = page.getByRole("textbox", { name: "결과 질문", exact: true });
  await expect(questionBox).toBeEnabled({ timeout: 15_000 });
  await questionBox.fill("이 결과를 뒷받침하는 검증된 값은 무엇인가요?");
  await page.getByRole("button", { name: "질문 보내기" }).click();
  await page.getByRole("checkbox", {
    name: "원격 처리 안내를 확인하고 동의합니다",
  }).check();
  await page.getByRole("button", { name: "동의하고 질문 보내기" }).click();
  await expect(
    page.getByText("현재 실행본의 근거로는 확인할 수 없습니다", { exact: true }),
  ).toBeVisible({ timeout: 30_000 });

  await page.goto("/analysis");
  await expect(page.getByRole("button", { name: "실행 데이터 삭제" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "실행 데이터 삭제" }).click();
  await expect(page.getByText("실행 데이터가 삭제되었습니다.")).toBeVisible({
    timeout: 30_000,
  });
  expect(await page.evaluate(() => sessionStorage.getItem("trusted-ceo-live-run-id"))).toBeNull();
});
