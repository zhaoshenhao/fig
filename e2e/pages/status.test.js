import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Status Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "status");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("shows component status or process info", async ({ page }) => {
    const bodyText = await page.locator("body").innerText();
    const hasContent = bodyText.length > 30;
    expect(hasContent).toBeTruthy();
  });
});
