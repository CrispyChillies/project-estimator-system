import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { ADMIN, apiCall, signIn } from "./helpers";

// WCAG 2.1 A/AA automated checks (axe-core) in light and dark themes. Serious/critical violations fail the test.
async function audit(page: Page, label: string) {
  await page.waitForLoadState("networkidle");
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = bad.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => `${n.target.join(" ")} ${n.html.slice(0, 160)}`).join(" | ")}`);
  expect(summary, `${label}: axe violations`).toEqual([]);
}

for (const theme of ["light", "dark"] as const) {
  test.describe(`axe (${theme})`, () => {
    test.use({ colorScheme: theme });
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => window.localStorage.setItem("theme", t), theme);
    });

    test("public pages", async ({ page }) => {
      for (const path of ["/", "/signin", "/signup", "/help", "/help/getting-started", "/help/analytics"]) {
        await page.goto(path);
        await audit(page, path);
      }
    });

    test("app pages", async ({ page }) => {
      await signIn(page, ADMIN.email, ADMIN.password);
      const p = await (await apiCall(page, "POST", "/projects", { name: `A11y ${Date.now()}` })).json();
      await apiCall(page, "POST", `/projects/${p.id}/documents/paste`, { title: "brief", text: "Booking app with login and payments." });
      const job = await (await apiCall(page, "POST", `/projects/${p.id}/estimates/generate`, { document_ids: [], learning: true })).json();
      await expect.poll(async () => (await (await apiCall(page, "GET", `/jobs/${job.id}`)).json()).status, { timeout: 60_000 }).toBe("done");
      for (const path of ["/dashboard", "/projects", "/insights", "/backtest", "/settings", "/profile", "/admin"]) {
        await page.goto(path);
        await audit(page, path);
      }
      await page.goto(`/projects/${p.id}`);
      await page.getByRole("tab", { name: "Estimate" }).click();
      await audit(page, "estimate tab");
      await apiCall(page, "DELETE", `/projects/${p.id}`);
    });
  });
}
