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
