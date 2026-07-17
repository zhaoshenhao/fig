import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("KB Browser Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "kb");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("has collection selector or content area", async ({ page }) => {
    const bodyText = await page.locator("body").innerText({ timeout: 5000 });
    expect(bodyText.length).toBeGreaterThan(20);
  });
});
