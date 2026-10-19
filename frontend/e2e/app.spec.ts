/**
 * Browser E2E on an isolated stack (see e2e/run.sh): fake LLM, separate database, signed in as the admin who holds
 * the archived data.   make e2e
 */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { ADMIN, apiCall, signIn } from "./helpers";

const SHOTS = path.resolve(__dirname, "../../docs/screenshots");
const BRIEF = path.resolve(__dirname, "../../data/fixtures/demo_brief_2.md");

test.describe.configure({ mode: "serial" });

let projectId = "";
let page: Page;

const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  page = await browser.newPage();
  await signIn(page, ADMIN.email, ADMIN.password);
  const p = await (
    await apiCall(page, "POST", "/projects", { name: `FreshRoute dispatch (E2E ${Date.now()})`, client_name: "FreshRoute" })
  ).json();
  projectId = p.id;
  const up = await apiCall(page, "POST", `/projects/${projectId}/documents`, undefined, {
    file: { name: "brief.md", mimeType: "text/markdown", buffer: fs.readFileSync(BRIEF) },
  });
  expect(up.status()).toBe(201);
});

test("projects list shows the admin's archived projects like normal data", async () => {
  await page.goto("/projects");
  await expect(page.getByRole("link", { name: /FreshRoute dispatch/ }).first()).toBeVisible();
  await expect(page.getByText(/^(Synthetic|Demo data)$/)).toHaveCount(0);
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

test("agent panel edits the estimate directly and can undo", async () => {
  const box = page.getByRole("textbox", { name: "Message the agent" });
  // The panel auto-opens after generation; the toolbar button / Ctrl+J toggles it.
  await expect(box).toBeVisible();
  await page.keyboard.press("ControlOrMeta+j");
  await expect(box).toBeHidden();
  await page.getByRole("button", { name: "Agent", exact: true }).click();
  await expect(box).toBeEnabled();
  await box.fill("increase backend hours by 20%");
  await box.press("Enter");
  const card = page.getByTestId("tool-card").last();
  await expect(card).toContainText("Bulk adjust");
  await expect(card).toContainText("applied");
  await shot("agent");
  await card.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("Undone")).toBeVisible();
  await expect(card).toContainText("reverted");
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

test("settings has no model controls; admin page holds learning, usage and archive", async () => {
  await page.goto("/settings");
  const rate = page.getByRole("textbox", { name: /Hourly rate for/ }).first();
  await expect(rate).not.toHaveValue("");
  await rate.fill(String(Number(await rate.inputValue()) + 1));
  await rate.blur();
  await expect(page.getByText(/rate saved/)).toBeVisible();
  await expect(page.getByText(/LLM|model|Hyperparameters|Reset learned data/i)).toHaveCount(0);
  await shot("settings");
  await page.goto("/admin");
  await page.getByRole("tab", { name: "Data archive" }).click();
  await expect(page.getByText("Archived synthetic test data, kept for storage and reference.")).toBeVisible();
  await page.getByRole("tab", { name: "Learning" }).click();
  const wmax = page.locator("div", { has: page.locator("code", { hasText: /^w_max$/ }) }).getByRole("textbox").last();
  await wmax.fill("0.5");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Hyperparameters saved")).toBeVisible();
  await page.getByRole("button", { name: "Defaults" }).click();
  await expect(page.getByRole("textbox", { name: "retrieval_k" })).toHaveValue("3");
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
