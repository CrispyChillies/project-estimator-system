/**
 * Live diagnosis of the chat panel against the real model (run with E2E_LLM_MODE=live LIVE=1 e2e/run.sh
 * e2e/live-chat.spec.ts). Records network/console evidence for docs/CHAT_DIAGNOSIS.md. Skipped otherwise.
 */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { ADMIN, apiCall, signIn } from "./helpers";

test.skip(!process.env.LIVE, "live model test; set LIVE=1");

test("live: chat edits the table through the same-site proxy with streaming", async ({ page }) => {
  const consoleErrors: string[] = [];
  const network: { url: string; status: number; type: string | null; ms: number }[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const started = new Map<string, number>();
  page.on("request", (r) => started.set(r.url(), Date.now()));
  page.on("response", (r) => {
    if (r.url().includes("/api/v1/agent/"))
      network.push({ url: new URL(r.url()).pathname, status: r.status(), type: r.headers()["content-type"] ?? null, ms: Date.now() - (started.get(r.url()) ?? Date.now()) });
  });
  await signIn(page, ADMIN.email, ADMIN.password);
  const p = await (await apiCall(page, "POST", "/projects", { name: `Live diagnosis ${Date.now()}` })).json();
  await apiCall(page, "POST", `/projects/${p.id}/documents/paste`, {
    title: "brief",
    text: "Booking app for a physiotherapy clinic.\n- Patients book and cancel appointments online.\n- Staff calendar and reminders by SMS.\n- Admin back office for services and prices.\n",
  });
  const job = await (await apiCall(page, "POST", `/projects/${p.id}/estimates/generate`, { document_ids: [], learning: true })).json();
  let done = false;
  for (let i = 0; i < 120 && !done; i++) {
    done = (await (await apiCall(page, "GET", `/jobs/${job.id}`)).json()).status === "done";
    if (!done) await page.waitForTimeout(1000);
  }
  expect(done).toBe(true);
  await page.goto(`/projects/${p.id}`);
  await page.getByRole("tab", { name: "Estimate" }).click();
  const box = page.getByRole("textbox", { name: "Message the agent" });
  if (!(await box.isVisible())) await page.getByRole("button", { name: "Agent", exact: true }).click();
  const before = await page.getByLabel("Max hours").evaluateAll((els) => els.map((e) => (e as HTMLInputElement).value));
  const t0 = Date.now();
  await box.fill("Reduce all backend tasks by 10%");
  await box.press("Enter");
  const card = page.getByTestId("tool-card").last();
  await expect(card).toBeVisible({ timeout: 60_000 });
  const firstCardMs = Date.now() - t0;
  await expect(page.getByText(/Working…/)).toHaveCount(0, { timeout: 120_000 });
  const totalMs = Date.now() - t0;
  const after = await page.getByLabel("Max hours").evaluateAll((els) => els.map((e) => (e as HTMLInputElement).value));
  const out = { firstCardMs, totalMs, changedRows: after.filter((v, i) => v !== before[i]).length, network, consoleErrors };
  fs.writeFileSync(path.resolve(__dirname, "../../data/inventory/live-chat-diagnosis.json"), JSON.stringify(out, null, 1));
  expect(out.changedRows).toBeGreaterThan(0);
  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
