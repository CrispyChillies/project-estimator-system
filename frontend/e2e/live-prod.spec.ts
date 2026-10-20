/** Post-deploy pass against the live site: E2E_BASE_URL=<url> LIVE_PROD=1 pnpm exec playwright test e2e/live-prod.spec.ts.
 *  Uses the real model for one estimate and one chat edit (a few cents). */
import { expect, test } from "@playwright/test";

import { apiCall } from "./helpers";

test.skip(!process.env.LIVE_PROD, "set LIVE_PROD=1 and E2E_BASE_URL");
test.setTimeout(600_000);

const BRIEF = "Booking app for a physiotherapy clinic.\n- Patients book and cancel appointments online.\n- Staff calendar and SMS reminders.\n- Admin back office for services and prices.\n";

const RUN = `CALIBR-RUN-${Date.now().toString(36)}`; // everything this run creates carries this prefix

test("live site: quick sign-in, VND default, toggle persists, pinned composer, real chat edit, tags, self-cleanup", async ({ page }) => {
  try {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/signin");
    await page.getByLabel("Name").fill(`${RUN} guest`);
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 60_000 });
    await apiCall(page, "PUT", "/auth/me/onboarding", { state: { welcome_seen: true, tour_done: true } });

    const p = await (await apiCall(page, "POST", "/projects", { name: `${RUN} project` })).json();
    await apiCall(page, "POST", `/projects/${p.id}/documents/paste`, { title: "brief", text: BRIEF });
    const job = await (await apiCall(page, "POST", `/projects/${p.id}/estimates/generate`, { document_ids: [], learning: true })).json();
    let done = false;
    for (let i = 0; i < 150 && !done; i++) {
      done = await apiCall(page, "GET", `/jobs/${job.id}`)
        .then(async (r) => (await r.json()).status === "done")
        .catch(() => false); // the small instance resets connections while the job runs
      if (!done) await page.waitForTimeout(2000);
    }
    expect(done).toBe(true);

    await page.goto(`/projects/${p.id}`);
    await page.getByRole("tab", { name: "Estimate" }).click();
    await expect(page.getByTestId("currency-VND")).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("cost-mid")).toContainText(/triệu|₫/);
    const vnd = await page.getByTestId("cost-mid").innerText();

    const saved = page.waitForResponse((r) => r.url().includes("/me/preferences") && r.request().method() === "PUT");
    await page.getByTestId("currency-USD").first().click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId("cost-mid")).toContainText("$");
    await page.reload();
    await page.getByRole("tab", { name: "Estimate" }).click();
    await expect(page.getByTestId("currency-USD").first()).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("currency-VND").first().click();
    await expect(page.getByTestId("cost-mid")).toContainText(/triệu|₫/);

    const box = page.getByRole("textbox", { name: "Message the agent" });
    if (!(await box.isVisible())) await page.getByRole("button", { name: "Agent", exact: true }).click();
    const inView = async () => {
      const b = await box.boundingBox();
      return !!b && b.y >= 0 && b.y + b.height <= 720;
    };
    expect(await inView(), "composer visible without scrolling").toBe(true);
    const before = await page.getByLabel("Max hours").evaluateAll((els) => els.map((e) => (e as HTMLInputElement).value));
    await box.fill("Reduce all backend tasks by 10%");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 30_000 });
    await box.press("Enter");
    await expect(page.getByTestId("tool-card").last()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText(/Working…/)).toHaveCount(0, { timeout: 120_000 });
    const after = await page.getByLabel("Max hours").evaluateAll((els) => els.map((e) => (e as HTMLInputElement).value));
    expect(after.filter((v, i) => v !== before[i]).length, "table changed from the real model's tool call").toBeGreaterThan(0);
    expect(await inView(), "composer still visible after the reply").toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1)).toBe(true);
    await expect(page.locator('[data-tag="role"]').first()).toBeVisible();
    console.log(`LIVE_OK cost-mid(before edit)=${vnd}`);

  } finally {
    // the guest deletes its own account, which also removes its projects and sessions (guest-only endpoint)
    const me = await apiCall(page, "GET", "/auth/me").catch(() => null);
    if (me?.ok() && (await me.json()).name === `${RUN} guest`) {
      const del = await apiCall(page, "DELETE", "/auth/me").catch(() => null);
      console.log(`CLEANUP ${RUN}: DELETE /auth/me -> ${del?.status() ?? "no response"}`);
    } else console.log(`CLEANUP ${RUN}: nothing to delete`);
  }
});
