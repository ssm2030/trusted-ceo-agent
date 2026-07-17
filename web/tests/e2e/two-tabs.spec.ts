import { expect, test } from "@playwright/test";

test("분석 작업과 결과 리포트 탭을 왕복한다", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/analysis$/);
  await expect(page.getByRole("heading", { name: "분석 작업" })).toBeVisible();

  await page.getByRole("link", { name: "결과 리포트" }).click();
  await expect(page).toHaveURL(/\/report$/);
  await expect(page.getByRole("heading", { name: "결과 리포트" })).toBeVisible();

  await page.getByRole("link", { name: "분석 작업" }).click();
  await expect(page).toHaveURL(/\/analysis$/);
});
