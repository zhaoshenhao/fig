import { expect } from "@playwright/test";

export async function waitForStable(page) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
}

export async function expectPageLoaded(page) {
  await expect(page.locator("body")).toBeVisible();
  await page.waitForLoadState("networkidle");
}

export async function expectElementCount(page, selector, count) {
  await expect(page.locator(selector)).toHaveCount(count);
}

export async function expectInputValue(page, selector, value) {
  await expect(page.locator(selector)).toHaveValue(value);
}
