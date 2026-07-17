import { expect } from "@playwright/test";

export async function goTo(page, hash) {
  await page.goto(`/#/${hash}`);
  await page.waitForLoadState("networkidle");
}

export async function waitForApp(page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
}

export async function expectText(page, text) {
  await expect(page.locator("body")).toContainText(text);
}

export async function expectNoText(page, text) {
  await expect(page.locator("body")).not.toContainText(text);
}

export async function selectOption(page, selector, value) {
  await page.locator(selector).selectOption(value);
}

export async function fillInput(page, selector, text) {
  await page.locator(selector).fill(text);
}

export async function clickButton(page, text, { exact = false } = {}) {
  if (exact) {
    await page.locator("button", { hasText: text }).first().click();
  } else {
    await page.getByRole("button", { name: text }).first().click();
  }
}

export async function clickLink(page, text) {
  await page.getByRole("link", { name: text }).click();
}

export async function expectVisible(page, selector) {
  await expect(page.locator(selector).first()).toBeVisible();
}

export async function expectUrl(page, hash) {
  await expect(page).toHaveURL(new RegExp(`/#/${hash}`));
}
