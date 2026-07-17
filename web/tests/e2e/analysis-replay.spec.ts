import { expect, test } from "@playwright/test";

test("replay 업로드와 사람 확인 흐름을 정직하게 표시한다", async ({ page }) => {
  await page.goto("/analysis");

  await expect(
    page.getByText("저장된 시연 흐름", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/선택한 파일 내용을 새로 분석하지 않습니다/),
  ).toBeVisible();

  await page.getByLabel("분석 자료 선택").setInputFiles({
    name: "현금흐름.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("period,cash\\nQ1,100"),
  });
  await expect(page.getByText("현금흐름.csv")).toBeVisible();

  await page.getByRole("button", { name: "시연 흐름 시작" }).click();
  await expect(page.getByLabel("사람 확인 답변")).toBeVisible();
  await expect(page.getByRole("button", { name: /웹에서 승인/ })).toHaveCount(0);
});
