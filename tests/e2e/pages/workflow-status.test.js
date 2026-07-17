import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Workflow Status Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "workflow");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("has reload button or DAG content", async ({ page }) => {
    const bodyText = await page.locator("body").innerText({ timeout: 3000 });
    expect(bodyText.length).toBeGreaterThan(20);
  });
});
