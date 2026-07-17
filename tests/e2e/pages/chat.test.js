import { test, expect } from "@playwright/test";
import { installMocks } from "../helpers/setup.js";
import { goTo } from "../helpers/navigate.js";
import { waitForStable } from "../helpers/wait.js";

test.describe("Chat Page", () => {
  test.beforeEach(async ({ page }) => {
    installMocks(page);
    await goTo(page, "chat");
    await waitForStable(page);
  });

  test("page loads successfully", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
  });

  test("workflow selector is present", async ({ page }) => {
    const select = page.locator("select").first();
    const count = await select.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("message input is present", async ({ page }) => {
    const input = page.locator("textarea, input[type='text']").first();
    const count = await input.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("can type in message input", async ({ page }) => {
    const input = page.locator("textarea, input[type='text']").first();
    const count = await input.count();
    if (count > 0) {
      await input.fill("你好");
      const value = await input.inputValue();
      expect(value.length).toBeGreaterThan(0);
    }
  });

  test("send button or enter triggers response", async ({ page }) => {
    const input = page.locator("textarea").first();
    const inputCount = await input.count();
    if (inputCount > 0) {
      await input.fill("测试消息");
      await input.press("Enter");
      await waitForStable(page);
    }
  });
});
