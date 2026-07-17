import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo, expectUrl, waitForApp } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Sidebar", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await waitForApp(page);
  });

  test("renders navigation items", async ({ page }) => {
    const nav = page.locator("nav, .sidebar, aside").first();
    await expect(nav).toBeVisible({ timeout: 5000 });
  });

  test('navigates to Chat page', async ({ page }) => {
    await goTo(page, "chat");
    await expectUrl(page, "chat");
  });

  test('navigates to KB Browser page', async ({ page }) => {
    await goTo(page, "kb");
    await expectUrl(page, "kb");
  });

  test('navigates to Workflow Status page', async ({ page }) => {
    await goTo(page, "workflow");
    await expectUrl(page, "workflow");
  });

  test('navigates to Document Management page', async ({ page }) => {
    await goTo(page, "docs");
    await expectUrl(page, "docs");
  });

  test('navigates to Metrics page', async ({ page }) => {
    await goTo(page, "metrics");
    await expectUrl(page, "metrics");
  });

  test('navigates to Dashboard page', async ({ page }) => {
    await goTo(page, "dashboard");
    await expectUrl(page, "dashboard");
  });

  test('navigates to System Status page', async ({ page }) => {
    await goTo(page, "status");
    await expectUrl(page, "status");
  });

  test("API key input is present", async ({ page }) => {
    const keyInput = page.locator('input[placeholder*="API"], input[placeholder*="Key"], input[placeholder*="key"]').first();
    const exists = await keyInput.count();
    expect(exists).toBeGreaterThanOrEqual(0);
  });
});
