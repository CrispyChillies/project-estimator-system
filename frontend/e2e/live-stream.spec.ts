/**
 * Manual live check (costs a fraction of a cent): LIVE_STREAM=1 with the backend in LLM_MODE=live.
 * Verifies tokens arrive incrementally in the agent panel and a proposal card renders.
 */
import { expect, request, test } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";

test.skip(!process.env.LIVE_STREAM, "manual live check");

test("live agent streams tokens incrementally in the browser", async ({ page }) => {
  const api = await request.newContext();
  const projects = await (await api.get(`${API}/projects?search=E2E`)).json();
  const pid = projects[0].id as string;
  const ests = await (await api.get(`${API}/projects/${pid}/estimates`)).json();
  const clone = await (await api.post(`${API}/estimates/${ests[0].id}/clone`)).json();
  await page.goto(`/projects/${pid}`);
  await page.getByRole("tab", { name: "Estimate" }).click();
  await page.getByRole("combobox").filter({ hasText: /v\d/ }).first().click();
  await page.getByRole("option", { name: new RegExp(`^v${clone.version} `) }).click();
  await page.getByRole("button", { name: "Agent" }).click();
  const box = page.getByPlaceholder("Ask or instruct…");
  await box.fill("increase QA hours by 10%");
  // sample the latest assistant bubble every ~10 ms inside the page
  await page.evaluate(() => {
    const w = window as unknown as { __lens: number[] };
    w.__lens = [];
    setInterval(() => {
      const els = document.querySelectorAll("div.bg-muted.whitespace-pre-wrap");
      w.__lens.push(els.length ? (els[els.length - 1] as HTMLElement).innerText.length : 0);
    }, 10);
  });
  await box.press("Enter");
  await expect(page.getByText("Proposed changes").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(3000);
  const lengths = await page.evaluate(() => (window as unknown as { __lens: number[] }).__lens);
  const distinct = [...new Set(lengths.filter((n) => n > 1))];
  console.log("bubble length samples", distinct.join(","));
  expect(distinct.length).toBeGreaterThan(2); // grew in several steps, not all at once
});
