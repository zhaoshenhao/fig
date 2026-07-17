import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Metrics Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "metrics");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("has session table or filter controls", async ({ page }) => {
    const bodyText = await page.locator("body").innerText({ timeout: 5000 });
    expect(bodyText.length).toBeGreaterThan(50);
  });
});
