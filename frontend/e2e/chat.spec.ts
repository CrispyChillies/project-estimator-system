/**
 * Chat agent E2E (fake LLM, isolated stack via e2e/run.sh): streamed answer → tool card → live table change → undo,
 * confirmation for delete, selection chip, polling fallback when the stream is blocked, sessions survive reload.
 */
import { expect, test, type Page } from "@playwright/test";

import { ADMIN, apiCall, signIn } from "./helpers";

test.describe.configure({ mode: "serial" });

let page: Page;
let estimateId = "";
let projectId = "";

const BRIEF = `Courier dispatch platform.
- Customer portal to book deliveries with live tracking.
- Admin back office to manage couriers and pricing rules.
- Payments with Stripe and monthly invoicing.
- Push notifications for status changes.
`;

async function maxValues() {
  return page.getByLabel("Max hours").evaluateAll((els) => els.map((e) => (e as HTMLInputElement).value));
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  await signIn(page, ADMIN.email, ADMIN.password);
  const p = await (await apiCall(page, "POST", "/projects", { name: `Chat E2E ${Date.now()}` })).json();
  projectId = p.id;
  await apiCall(page, "POST", `/projects/${projectId}/documents/paste`, { title: "brief", text: BRIEF });
  const job = await (await apiCall(page, "POST", `/projects/${projectId}/estimates/generate`, { document_ids: [], learning: true })).json();
  for (let i = 0; i < 60; i++) {
    const j = await (await apiCall(page, "GET", `/jobs/${job.id}`)).json();
    if (j.status === "done") {
      estimateId = j.result_ref;
      break;
    }
    await page.waitForTimeout(500);
  }
  expect(estimateId).not.toBe("");
  await page.goto(`/projects/${projectId}`);
  await page.getByRole("tab", { name: "Estimate" }).click();
  const box = page.getByRole("textbox", { name: "Message the agent" });
  if (!(await box.isVisible())) await page.getByRole("button", { name: "Agent", exact: true }).click();
  await expect(box).toBeEnabled();
});

const box = () => page.getByRole("textbox", { name: "Message the agent" });

test("message streams, tool card appears, table changes live, undo restores", async () => {
  const before = await maxValues();
  await box().fill("increase backend hours by 20%");
  await box().press("Enter");
  const card = page.getByTestId("tool-card").last();
  await expect(card).toContainText("Bulk adjust");
  await expect(card).toContainText("applied");
  await expect(card).toContainText("percent: 20");
  await expect(page.getByText(/^Done: /).last()).toBeVisible();
  await expect.poll(maxValues).not.toEqual(before);
  await card.getByRole("button", { name: "JSON" }).click();
  await expect(card.locator("pre")).toContainText('"percent": 20');
  await card.getByRole("button", { name: "Undo" }).click();
  await expect(card).toContainText("reverted");
  await expect.poll(maxValues).toEqual(before);
});

test("delete needs confirmation", async () => {
  const title = (await page.locator("[data-task-id] td:nth-child(2) span.truncate").first().textContent())!.trim();
  await box().fill(`delete the ${title} task`);
  await box().press("Enter");
  const card = page.getByTestId("tool-card").last();
  await expect(card).toContainText("awaiting confirmation");
  await expect(card).toContainText("Deletes always need confirmation");
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(card).toContainText("applied");
  await expect(page.locator("[data-task-id] span.truncate", { hasText: title })).toHaveCount(0);
});

test("selection chip scopes the change to the selected rows", async () => {
  const before = await maxValues();
  await page.getByRole("checkbox", { name: /^Select / }).nth(0).check();
  await page.getByRole("checkbox", { name: /^Select / }).nth(1).check();
  await expect(page.getByTestId("selection-chip")).toContainText("Selection (2)");
  await box().fill("make these 20% shorter");
  await box().press("Enter");
  await expect(page.getByTestId("tool-card").last()).toContainText("applied");
  await expect.poll(async () => (await maxValues()).filter((v, i) => v !== before[i]).length).toBe(2);
});

test("falls back to polling when the event stream is blocked", async () => {
  await page.route(/\/agent\/sessions\/[^/]+\/runs$/, (r) => r.abort());
  await box().fill("/round");
  await box().press("Enter");
  await expect(page.getByTestId("tool-card").last()).toContainText(/Bulk adjust/);
  await expect(page.getByText(/Working…|still working/)).toHaveCount(0, { timeout: 30_000 });
  await page.unroute(/\/agent\/sessions\/[^/]+\/runs$/);
});

test("new session starts clean; reload keeps history", async () => {
  await page.getByRole("button", { name: /brief/ }).first().click();
  await page.getByRole("menuitem", { name: "New session" }).click();
  await expect(page.getByRole("button", { name: /Analyze & draft estimate/ })).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "Estimate" }).click();
  await expect(box()).toBeVisible();
  await page.getByRole("button", { name: /brief/ }).first().click();
  // Sessions are listed most recent first: [new empty session, the earlier one].
  await page.getByRole("menuitem").nth(1).click();
  await expect(page.getByTestId("tool-card").first()).toContainText("Bulk adjust");
  await expect(page.getByTestId("tool-card").first()).toContainText("reverted");
});
