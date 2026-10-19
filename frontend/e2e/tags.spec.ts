/** Role/category cells render coloured tags with the expected tokens; light/dark screenshots (docs/screenshots/ux-*). */
import path from "node:path";

import { expect, test } from "@playwright/test";

import { ADMIN, apiCall, makeEstimate, openEstimateTab, signIn } from "./helpers";

const SHOTS = path.resolve(__dirname, "../../docs/screenshots");

test("table cells and breakdown render role/category tags with the central tokens", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  const { projectId } = await makeEstimate(page, "Tags");
  const roles: { name: string; color: string }[] = await (await apiCall(page, "GET", "/roles")).json();
  const cats: { name: string; color: string }[] = await (await apiCall(page, "GET", "/categories")).json();
  const roleToken = Object.fromEntries(roles.map((r) => [r.name, r.color]));
  const catToken = Object.fromEntries(cats.map((c) => [c.name, c.color]));
  expect(roleToken["Backend"]).toBe("indigo");
  expect(catToken["API / backend"]).toBe("indigo");
  expect(new Set(roles.map((r) => r.color)).size).toBe(roles.length); // 9 distinct role colours

  await openEstimateTab(page, projectId);
  const roleTags = page.locator('table [data-tag="role"]');
  const catTags = page.locator('table [data-tag="category"]');
  await expect(roleTags.first()).toBeVisible();
  expect(await roleTags.count()).toBeGreaterThan(2);
  for (const t of await roleTags.all()) expect(roleToken[(await t.innerText()).trim()]).toBe(await t.getAttribute("data-token"));
  for (const t of await catTags.all()) expect(catToken[(await t.innerText()).trim()]).toBe(await t.getAttribute("data-token"));
  // the by-role breakdown uses the same tags
  await expect(page.getByTestId("cost-summary")).toBeVisible();
  const byRole = page.locator('[data-slot="card"]').filter({ hasText: "By role" });
  expect(await byRole.locator('[data-tag="role"]').count()).toBeGreaterThan(0);

  // colour is never the only signal: tags carry their label; text colours differ per theme
  const first = roleTags.first();
  const light = await first.evaluate((el) => getComputedStyle(el).color);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(() => window.localStorage.setItem("theme", "dark"));
  await page.reload();
  await page.getByRole("tab", { name: "Estimate" }).click();
  const dark = await page.locator('table [data-tag="role"]').first().evaluate((el) => getComputedStyle(el).color);
  expect(dark).not.toBe(light);

  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await page.evaluate((t) => window.localStorage.setItem("theme", t), theme);
    await page.reload();
    await page.getByRole("tab", { name: "Estimate" }).click();
    await expect(page.locator('table [data-tag="role"]').first()).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, `ux-estimate-tags-${theme}.png`) });
  }
});

test("users can pick their own tag colour in Settings; it applies in the table", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto("/settings");
  const row = page.getByTestId("rate-row-QA");
  await row.getByTestId("color-picker").click();
  await page.getByRole("option", { name: "rose", exact: true }).click();
  await expect.poll(async () => (await (await apiCall(page, "GET", "/roles")).json()).find((r: { name: string }) => r.name === "QA").color).toBe("rose");
  await expect(row.locator('[data-tag="role"]')).toHaveAttribute("data-token", "rose");
  // reset to the default so later runs keep the documented palette
  await apiCall(page, "PUT", "/me/colors", { kind: "role", ref: (await (await apiCall(page, "GET", "/roles")).json()).find((r: { name: string }) => r.name === "QA").id, color: null });
});
