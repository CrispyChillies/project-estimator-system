/** VND by default, ₫ | $ toggle that persists, rates stored in VND, exports and chat with a VND budget (fake LLM). */
import { expect, test } from "@playwright/test";

import { ADMIN, apiCall, makeEstimate, openEstimateTab, signIn, signUpMember } from "./helpers";

test("a new account sees VND by default; the toggle updates every money surface and persists", async ({ page }) => {
  await signUpMember(page, "vn-user");
  const { projectId } = await makeEstimate(page, "Currency");
  await openEstimateTab(page, projectId);
  await expect(page.getByTestId("currency-VND")).toHaveAttribute("aria-checked", "true");
  const cost = page.getByTestId("cost-mid");
  await expect(cost).toContainText(/triệu|₫/);
  await expect(page.getByTestId("fx-note").first()).toContainText("1 USD =");
  const vndRange = await page.getByTestId("cost-range").innerText();
  expect(vndRange).toMatch(/triệu|tỷ|₫/);

  await page.getByTestId("currency-USD").first().click();
  await expect(cost).toContainText("$");
  await expect(page.getByTestId("cost-range")).toContainText("$");
  await expect(page.getByTestId("currency-USD").first()).toHaveAttribute("aria-checked", "true");

  await page.reload();
  await page.getByRole("tab", { name: "Estimate" }).click();
  await expect(page.getByTestId("currency-USD").first()).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("cost-mid")).toContainText("$");
  expect((await (await apiCall(page, "GET", "/auth/me")).json()).display_currency).toBe("USD");

  // the user menu carries the same switch; back to VND
  await page.locator('[data-tour="account-menu"]').click();
  await page.getByRole("menu").getByTestId("currency-VND").click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("cost-mid")).toContainText(/triệu|₫/);
});

test("editing a rate in USD stores the right VND; export shows currency and rate", async ({ page }) => {
  await signUpMember(page, "rate-user");
  const { estimateId } = await makeEstimate(page, "Rates");
  await apiCall(page, "PUT", "/me/preferences", { display_currency: "USD" });
  await page.goto("/settings");
  const fx = await (await apiCall(page, "GET", "/fx")).json();
  const field = page.getByLabel("Your hourly rate for Backend");
  await field.fill("100");
  await field.blur();
  await expect(page.getByText("Backend: your rate saved")).toBeVisible();
  const roles = await (await apiCall(page, "GET", "/roles")).json();
  const backend = roles.find((r: { name: string }) => r.name === "Backend");
  expect(backend.my_rate_vnd).toBe(Math.round((100 * fx.usd_vnd_rate) / 1000) * 1000);

  const csv = await (await apiCall(page, "GET", `/estimates/${estimateId}/export?format=csv&currency=USD`)).text();
  const [header, first] = csv.trim().split("\n");
  expect(header).toContain("Currency");
  expect(header).toContain("Rate used (VND per USD)");
  expect(first).toContain("USD");
  expect(first).toContain(String(fx.usd_vnd_rate));
});

test("chat: a Vietnamese VND budget leads to a visible, undoable change within budget", async ({ page }) => {
  await signUpMember(page, "chat-user");
  const { projectId, estimateId } = await makeEstimate(page, "VND chat");
  const before = await (await apiCall(page, "GET", `/estimates/${estimateId}/summary`)).json();
  const target = Math.floor((before.total_cost_max * 0.85) / 1000) * 1000;
  await openEstimateTab(page, projectId, true);
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 20_000 }); // session ready
  await page.getByLabel("Message the agent").fill(`ngân sách ${target.toLocaleString("vi-VN")} ₫`);
  await page.getByLabel("Message the agent").press("Enter");
  const card = page.getByTestId("tool-card").filter({ hasText: "Fit to cost budget" });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByRole("button", { name: "Undo" })).toBeVisible();
  const after = await (await apiCall(page, "GET", `/estimates/${estimateId}/summary`)).json();
  expect(after.total_cost_max).toBeLessThanOrEqual(target + 1);
  expect(after.total_cost_max).toBeLessThan(before.total_cost_max);
  await card.getByRole("button", { name: "Undo" }).click();
  await expect
    .poll(async () => (await (await apiCall(page, "GET", `/estimates/${estimateId}/summary`)).json()).total_cost_max)
    .toBe(before.total_cost_max);
});

test("admin can set the workspace exchange rate; members see it", async ({ page, browser }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  const before = await (await apiCall(page, "GET", "/fx")).json();
  await page.goto("/settings");
  await page.getByLabel("VND per 1 USD").fill("26000");
  await page.getByRole("button", { name: "Save rate" }).click();
  await expect(page.getByText("Exchange rate saved")).toBeVisible();
  const member = await browser.newPage();
  await signUpMember(member, "fx-member");
  expect((await (await apiCall(member, "GET", "/fx")).json()).usd_vnd_rate).toBe(26000);
  await member.close();
  await apiCall(page, "PUT", "/admin/fx", { rate: before.usd_vnd_rate });
});
