import { expect, type Page } from "@playwright/test";

export const ADMIN = { email: process.env.E2E_ADMIN_EMAIL ?? "", password: process.env.E2E_ADMIN_PASSWORD ?? "" };

export async function signIn(page: Page, email: string, password: string) {
  await page.goto("/signin");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

/** Same-site API call that reuses the page's session cookie and echoes the CSRF cookie. */
export async function apiCall(page: Page, method: string, path: string, data?: unknown, multipart?: Record<string, unknown>) {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "calibr_csrf")?.value ?? "";
  const res = await page.request.fetch(`/api/v1${path}`, {
    method,
    headers: method === "GET" ? {} : { "X-CSRF-Token": csrf },
    data: data as never,
    multipart: multipart as never,
  });
  return res;
}

const SAMPLE_BRIEF = `Courier dispatch platform.
- Customer portal to book deliveries with live tracking.
- Admin back office to manage couriers and pricing rules.
- Payments with Stripe and monthly invoicing.
- Push notifications for status changes.
`;

/** Creates a project with a generated estimate (fake LLM) through the API of the signed-in page. */
export async function makeEstimate(page: Page, name: string): Promise<{ projectId: string; estimateId: string }> {
  const p = await (await apiCall(page, "POST", "/projects", { name: `${name} ${Date.now()}` })).json();
  await apiCall(page, "POST", `/projects/${p.id}/documents/paste`, { title: "brief", text: SAMPLE_BRIEF });
  const job = await (await apiCall(page, "POST", `/projects/${p.id}/estimates/generate`, { document_ids: [], learning: true })).json();
  for (let i = 0; i < 120; i++) {
    const j = await (await apiCall(page, "GET", `/jobs/${job.id}`)).json();
    if (j.status === "done") return { projectId: p.id, estimateId: j.result_ref };
    await page.waitForTimeout(500);
  }
  throw new Error("estimate generation did not finish");
}

/** A fresh member account (e2e stack runs with SIGNUP_MODE=open); leaves the page signed in as that member. */
export async function signUpMember(page: Page, label: string): Promise<{ email: string; password: string }> {
  const email = `${label}-${Date.now()}@example.com`;
  const password = `pw-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill(label);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await apiCall(page, "PUT", "/auth/me/onboarding", { state: { welcome_seen: true, tour_done: true } }); // no welcome dialog in the way
  return { email, password };
}

export async function openEstimateTab(page: Page, projectId: string, agent = false) {
  await page.addInitScript((open) => window.localStorage.setItem("calibr.agentOpen", open ? "1" : "0"), agent);
  await page.goto(`/projects/${projectId}`);
  await page.getByRole("tab", { name: "Estimate" }).click();
  await expect(page.getByTestId("table-pane")).toBeVisible();
}
