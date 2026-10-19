/**
 * New member journey (fresh account, empty workspace): welcome → tour (keyboard, resumable) → checklist →
 * empty-state charts; admin sees charts with data; help pages are public.
 */
import { expect, test } from "@playwright/test";

import { ADMIN, signIn } from "./helpers";

test.describe.configure({ mode: "serial" });

const email = `member-${Date.now()}@example.com`;
const password = "member password 123";

test("sign up starts a clean, demo-free workspace with a welcome dialog and tour", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Mia Member");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  if (await page.getByLabel("Invite code").isVisible()) test.skip(true, "e2e stack runs with SIGNUP_MODE=open");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("dialog", { name: /Welcome to Calibr/ })).toBeVisible();
  await expect(page.getByText(/demo|synthetic|sample data/i)).toHaveCount(0);
  await page.getByRole("button", { name: "Take the 1-minute tour" }).click();
  const tour = page.getByTestId("tour");
  await expect(tour).toContainText("1. Create a project");
  await page.keyboard.press("ArrowRight");
  await expect(tour).toContainText("2. Generate an estimate");
  // Resumable: reload continues at the same step.
  await page.reload();
  await expect(page.getByTestId("tour")).toContainText("2. Generate an estimate");
  await page.getByTestId("tour").getByRole("button", { name: "Next" }).click();
  await expect(page.getByTestId("tour")).toContainText("3. Read the ranges");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tour")).toHaveCount(0);
  await expect(page.getByText("Getting started")).toBeVisible();
  await expect(page.getByText(/0 of 7 done/)).toBeVisible();
  await page.goto("/projects");
  await expect(page.getByText(/Create a project, upload or paste/)).toBeVisible();
});

test("member insights show 'not enough data' instead of numbers", async ({ page }) => {
  await signIn(page, email, password);
  await page.goto("/insights");
  await expect(page.getByTestId("chart-estimate-vs-actual").getByTestId("not-enough")).toBeVisible();
  await expect(page.getByTestId("chart-learning-impact").getByTestId("not-enough")).toBeVisible();
  await page.goto("/dashboard");
  await expect(page.getByText(/1 of 7 done/)).toBeVisible(); // viewing Insights ticks its item
});

test("admin insights render all eight charts with data and a how-to-read drawer", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto("/insights");
  for (const id of ["estimate-vs-actual", "accuracy-over-time", "bias-by-category", "range-coverage", "unplanned-work",
    "planned-vs-actual", "estimating-productivity", "learning-impact"]) {
    const card = page.getByTestId(`chart-${id}`);
    await expect(card).toBeVisible();
    await expect(card.getByTestId("not-enough")).toHaveCount(0);
  }
  await page.getByTestId("chart-bias-by-category").getByRole("button", { name: /How to read/ }).click();
  await expect(page.getByRole("dialog")).toContainText("How it is computed");
  await page.getByRole("link", { name: "Open the full guide" }).click();
  await expect(page).toHaveURL(/\/help\/analytics#bias-by-category/);
});

test("help pages are public", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/help");
  for (const t of ["Getting started", "Working with the chat agent", "Understanding an estimate", "Closing the loop",
    "Analyzing productivity with the charts", "Glossary", "FAQ"]) {
    await expect(page.getByRole("main").getByRole("link", { name: new RegExp(t) })).toBeVisible();
  }
  await page.getByRole("main").getByRole("link", { name: /FAQ/ }).click();
  await expect(page.getByRole("heading", { name: "What is the AI allowance?" })).toBeVisible();
  await ctx.close();
});
