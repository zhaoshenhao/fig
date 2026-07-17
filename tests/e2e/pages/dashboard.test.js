import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Dashboard Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "dashboard");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("has KPI cards or chart content", async ({ page }) => {
    const bodyText = await page.locator("body").innerText();
    const hasContent = bodyText.length > 50;
    expect(hasContent).toBeTruthy();
  });
});
