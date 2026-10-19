/**
 * Fixed-height estimate workspace: the page never scrolls, the chat composer is always visible, messages follow the
 * newest one unless the user scrolled up ("Jump to latest"). 60+ seeded messages, four viewports, axe, keyboard.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { ADMIN, apiCall, makeEstimate, openEstimateTab, signIn } from "./helpers";

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x720", width: 1280, height: 720 },
  { name: "1024x700", width: 1024, height: 700 },
  { name: "390x800", width: 390, height: 800 },
];

let projectId = "";
let estimateId = "";

async function seedChat(page: Page, estimateId: string, runs: number) {
  const s = await (await apiCall(page, "POST", `/estimates/${estimateId}/agent/sessions`, { title: "Layout seed" })).json();
  for (let i = 0; i < runs; i++) {
    const r = await apiCall(page, "POST", `/agent/sessions/${s.id}/runs/async`, { text: i % 2 ? "/similar" : "/adjust +1%" });
    expect(r.status()).toBeLessThan(300);
    for (let k = 0; k < 80; k++) {
      const st = await (await apiCall(page, "GET", `/agent/sessions/${s.id}`)).json();
      if (st.run_state !== "running") break;
      await page.waitForTimeout(100);
    }
  }
  const msgs = await (await apiCall(page, "GET", `/agent/sessions/${s.id}/messages`)).json();
  expect(msgs.length).toBeGreaterThanOrEqual(60);
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page, ADMIN.email, ADMIN.password);
  ({ projectId, estimateId } = await makeEstimate(page, "Layout"));
  await seedChat(page, estimateId, 32);
  await page.close();
});

async function pageDoesNotScroll(page: Page) {
  const m = await page.evaluate(() => ({ sh: document.scrollingElement!.scrollHeight, ih: window.innerHeight }));
  expect(m.sh, "document scrollHeight <= innerHeight").toBeLessThanOrEqual(m.ih);
}

async function composerVisible(page: Page) {
  const box = await page.getByLabel("Message the agent").boundingBox();
  const ih = await page.evaluate(() => window.innerHeight);
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(ih + 0.5);
}

const atBottom = (page: Page) =>
  page.getByTestId("chat-log").evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight <= 4);

for (const vp of VIEWPORTS) {
  test.describe(`viewport ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("composer visible without scrolling the page; send works; auto-scroll and jump-to-latest", async ({ page }) => {
      await signIn(page, ADMIN.email, ADMIN.password);
      await openEstimateTab(page, projectId, true);
      await expect(page.getByLabel("Message the agent")).toBeVisible();
      await expect(page.getByTestId("chat-log")).toBeVisible();
      await expect.poll(() => atBottom(page)).toBe(true); // opening a session shows the latest message
      await pageDoesNotScroll(page);
      await composerVisible(page);

      // collapsed tool cards: one line each, details on click
      await expect(page.locator('[data-testid="tool-card"][data-expanded="false"]').first()).toBeVisible();

      const box = page.getByLabel("Message the agent");
      const before = await page.getByTestId("chat-log").locator("[data-testid=tool-card]").count();
      await box.fill("/adjust -1%");
      await box.press("Enter");
      await expect.poll(async () => page.getByTestId("chat-log").locator("[data-testid=tool-card]").count(), { timeout: 20_000 }).toBeGreaterThan(before);
      await expect.poll(() => atBottom(page)).toBe(true);
      await pageDoesNotScroll(page);
      await composerVisible(page);

      // scrolled up: new messages do not yank the view; "Jump to latest" appears and works
      await page.getByTestId("chat-log").evaluate((el) => (el.scrollTop = 0));
      await box.fill("/similar");
      await box.press("Enter");
      await expect(page.getByTestId("jump-to-latest")).toBeVisible({ timeout: 20_000 });
      expect(await atBottom(page)).toBe(false);
      await page.getByTestId("jump-to-latest").click();
      await expect(page.getByTestId("jump-to-latest")).toBeHidden();
      expect(await atBottom(page)).toBe(true);
      await pageDoesNotScroll(page);
    });

    test("keyboard: Tab reaches the composer, Shift+Enter adds a line, Enter sends; no axe violations", async ({ page }) => {
      await signIn(page, ADMIN.email, ADMIN.password);
      await openEstimateTab(page, projectId, true);
      const box = page.getByLabel("Message the agent");
      await expect(box).toBeVisible();
      await page.getByRole("button", { name: "Memory" }).focus();
      let reached = false;
      for (let i = 0; i < 80 && !reached; i++) {
        await page.keyboard.press("Tab");
        reached = await page.evaluate(() => document.activeElement?.getAttribute("aria-label") === "Message the agent");
      }
      expect(reached, "Tab reaches the composer").toBe(true);
      await page.keyboard.type("line one");
      await page.keyboard.press("Shift+Enter");
      await page.keyboard.type("line two");
      expect(await box.inputValue()).toBe("line one\nline two");
      const h = (await box.boundingBox())!.height;
      expect(h).toBeGreaterThan(36); // auto-grew to two lines
      await box.fill("");
      await page.keyboard.type("/similar");
      await expect(page.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 30_000 });
      await page.keyboard.press("Enter");
      await expect(box).toHaveValue("");
      await pageDoesNotScroll(page);

      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      const bad = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(bad.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
    });
  });
}
