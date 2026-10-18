/**
 * Browser E2E against a backend running in LLM_MODE=replay (no live LLM cost) and a seeded DB.
 *   cd backend && LLM_MODE=replay uvicorn app.main:app --port 8000
 *   cd frontend && pnpm dev   # then: pnpm exec playwright test
 */
import { expect, request, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";
const SHOTS = path.resolve(__dirname, "../../docs/screenshots");
const BRIEF = path.resolve(__dirname, "../../data/fixtures/demo_brief_2.md");

test.describe.configure({ mode: "serial" });

let projectId = "";
let page: Page;

const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const api = await request.newContext();
  const p = await (
    await api.post(`${API}/projects`, { data: { name: `FreshRoute dispatch (E2E ${Date.now()})`, client_name: "FreshRoute" } })
  ).json();
  projectId = p.id;
  const up = await api.post(`${API}/projects/${projectId}/documents`, {
    multipart: { file: { name: "demo_brief_2.md", mimeType: "text/markdown", buffer: fs.readFileSync(BRIEF) } },
  });
  expect(up.status()).toBe(201);
  page = await browser.newPage();
});

test("projects list shows seeded history with data badges", async () => {
  await page.goto("/projects");
  await expect(page.getByText("Synthetic").first()).toBeVisible();
  await shot("projects");
});

test("generate an estimate with learning", async () => {
  await page.goto(`/projects/${projectId}`);
  await page.getByRole("button", { name: "Generate estimate" }).click();
  await page.getByRole("button", { name: "Generate with learning" }).click();
  await expect(page.getByRole("tab", { name: "Estimate" })).toHaveAttribute("aria-selected", "true", { timeout: 90_000 });
  await expect(page.getByLabel("Max hours").first()).toBeVisible();
  await shot("estimate");
});

test("inline edit shows non-blocking Why? chips", async () => {
  const max = page.getByLabel("Max hours").first();
  const value = Number(await max.inputValue());
  await max.fill(String(Math.round(value * 3)));
  await max.press("Enter");
  await expect(page.getByText("why? (optional)")).toBeVisible();
  await page.getByRole("button", { name: "Risk buffer" }).first().click();
  await expect(page.getByText("Reason saved")).toBeVisible();
});

test("Why this number? sheet shows provenance", async () => {
  await page.getByRole("button", { name: "Why this number?" }).first().click();
  await expect(page.getByText("Raw LLM samples")).toBeVisible();
  await expect(page.getByText("Calibration", { exact: true })).toBeVisible();
  await shot("why-this-number");
  await page.keyboard.press("Escape");
  await expect(page.getByText("Raw LLM samples")).toBeHidden();
});

test("drag reorder within a module persists", async () => {
  const rows = page.locator("tbody tr");
  // first pair of adjacent task rows (same module: no module header between them)
  const idx = await rows.evaluateAll((trs) =>
    trs.findIndex((tr, i) => !!tr.querySelector("button[aria-label='Drag']") && !!trs[i + 1]?.querySelector("button[aria-label='Drag']")),
  );
  expect(idx).toBeGreaterThanOrEqual(0);
  const title = (i: number) => rows.nth(i).locator("td").nth(1).innerText();
  const [t0, t1] = [await title(idx), await title(idx + 1)];
  // keyboard drag (dnd-kit KeyboardSensor): deterministic and checks the accessible path
  const handle = rows.nth(idx + 1).getByRole("button", { name: "Drag" });
  await handle.focus();
  await page.keyboard.press("Space");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Space");
  await expect.poll(() => title(idx)).toBe(t1);
  await page.reload();
  await page.getByRole("tab", { name: "Estimate" }).click();
  await expect.poll(() => title(idx)).toBe(t1);
  expect(await title(idx + 1)).toBe(t0);
});

test("agent chat streams and shows a reviewable proposal (recorded live conversation)", async () => {
  await page.getByRole("button", { name: "Agent" }).click();
  const box = page.getByPlaceholder("Ask or instruct…");
  await box.fill("increase backend hours by 20%");
  await box.press("Enter");
  await expect(page.getByText("Proposed changes").first()).toBeVisible();
  await shot("agent");
  await page.getByRole("button", { name: "Accept" }).first().click();
  await expect(page.getByText("Applied and logged")).toBeVisible();
});

test("finalize updates learning", async () => {
  await page.getByRole("button", { name: "Finalize" }).click();
  await page.getByRole("button", { name: "Finalize & learn" }).click();
  await expect(page.getByText("Finalized — edit-layer calibration updated")).toBeVisible();
});

test("actuals: inline edits, invalid CSV, unplanned work, mark delivered", async () => {
  await page.getByRole("tab", { name: "Actuals" }).click();
  const inputs = page.getByLabel(/^Actual hours for/);
  await expect(inputs.first()).toBeVisible();
  const n = await inputs.count();
  for (let i = 0; i < n; i++) await inputs.nth(i).fill(String(10 + i));
  await page.getByRole("button", { name: "Save actuals" }).click();
  await expect(page.getByText("Actuals saved")).toBeVisible();
  await page.locator("input[type=file][accept='.csv']").setInputFiles({
    name: "bad.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("task_id,actual_hours\nnot-a-task,5\n"),
  });
  await expect(page.getByText(/invalid row/)).toBeVisible();
  await page.getByPlaceholder("What was done").fill("Change request after UAT");
  await page.getByPlaceholder("h", { exact: true }).fill("12");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Change request after UAT")).toBeVisible();
  await page.getByRole("button", { name: "Mark delivered" }).click();
  await page.getByRole("button", { name: "Deliver & learn" }).click();
  await expect(page.getByText(/Delivered — actual-layer calibration updated/)).toBeVisible();
  await expect(page.getByText(/within P80|above P80/)).toBeVisible();
  await shot("actuals");
});

test("settings: rate card, hyperparameter, reset dialog, LLM usage", async () => {
  await page.goto("/settings");
  const rate = page.locator("table").first().getByRole("textbox").first();
  await expect(rate).not.toHaveValue("");
  await rate.fill(String(Number(await rate.inputValue()) + 1));
  await rate.blur();
  await expect(page.getByText(/rate saved/)).toBeVisible();
  const wmax = page.locator("div", { has: page.locator("code", { hasText: /^w_max$/ }) }).getByRole("textbox").last();
  await wmax.fill("0.5");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Hyperparameters saved")).toBeVisible();
  await page.getByRole("button", { name: "Defaults" }).click();
  await page.getByRole("button", { name: "Reset learned data" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("alertdialog")).toBeHidden();
  await expect(page.getByText(/mode: (replay|live|record|fake)/)).toBeVisible();
  await expect(page.getByText(/Live spend, all time/)).toBeVisible();
  await shot("settings");
});

test("insights and backtest render", async () => {
  await page.goto("/insights");
  await expect(page.getByText("Calibration factor by category")).toBeVisible();
  await shot("insights");
  await page.goto("/backtest");
  await page.getByRole("button", { name: "Re-run backtest" }).click();
  await expect(page.getByText(/Estimators × metrics/)).toBeVisible({ timeout: 90_000 });
  await shot("backtest");
});
