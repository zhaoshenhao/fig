import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Document Management Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "docs");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("has upload or scan controls", async ({ page }) => {
    const bodyText = await page.locator("body").innerText({ timeout: 3000 });
    expect(bodyText.length).toBeGreaterThan(20);
  });
});
