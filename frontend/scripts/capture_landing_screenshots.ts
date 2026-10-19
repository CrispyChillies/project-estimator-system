/**
 * Captures real product screenshots for the landing page and the help guides (Playwright, 1440×900, DPR 2,
 * light + dark). Signed in as the admin of the isolated stack (archived reference data, fictional).
 *   make landing-shots      (starts the isolated stack, runs this script, stops the stack)
 * Output: frontend/public/landing/*.webp, frontend/public/help/*.png, frontend/public/og.png
 */
import { chromium, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3005";
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const PUB = path.resolve(__dirname, "../public");
const BRIEF = `Field service app for an HVAC maintenance company

Goals
- Customers book maintenance visits online and see technician arrival windows.
- Dispatchers plan daily routes for 25 technicians and reassign jobs when someone is sick.
- Technicians use a mobile app (offline capable) to see jobs, record parts used and capture a customer signature.

Integrations
- Existing accounting system (invoices are created there), via its REST API.
- SMS reminders the day before a visit.

Constraints
- Web back office plus iOS and Android apps.
- Single sign-on for staff with Microsoft 365.`;

async function api(page: Page, method: string, p: string, data?: unknown) {
  const csrf = (await page.context().cookies()).find((c) => c.name === "calibr_csrf")?.value ?? "";
  const r = await page.request.fetch(`${BASE}/api/v1${p}`, { method, data: data as never, headers: method === "GET" ? {} : { "X-CSRF-Token": csrf } });
  if (!r.ok()) throw new Error(`${method} ${p} -> ${r.status()} ${await r.text()}`);
  return r.json();
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600); // chart animations
}

async function save(buf: Buffer, name: string, kinds: ("webp" | "help")[]) {
  if (kinds.includes("webp")) {
    await sharp(buf).webp({ quality: 78 }).toFile(path.join(PUB, "landing", `${name}.webp`));
    if (((await sharp(buf).metadata()).width ?? 0) > 1280) await sharp(buf).resize(1280).webp({ quality: 80 }).toFile(path.join(PUB, "landing", `${name}-sm.webp`));
  }
  if (kinds.includes("help")) await sharp(buf).resize(1440).png({ compressionLevel: 9, palette: true }).toFile(path.join(PUB, "help", `${name.replace(/-light$/, "")}.png`));
}

async function main() {
  fs.mkdirSync(path.join(PUB, "landing"), { recursive: true });
  fs.mkdirSync(path.join(PUB, "help"), { recursive: true });
  const browser = await chromium.launch();
  const setup = await (await browser.newContext({ baseURL: BASE })).newPage();
  await setup.goto("/signin");
  await setup.getByLabel("Email").fill(EMAIL);
  await setup.getByLabel("Password").fill(PASSWORD);
  await setup.getByRole("button", { name: "Sign in" }).click();
  await setup.waitForURL(/dashboard/);
  const project = await api(setup, "POST", "/projects", { name: "Field service app — HVAC", client_name: "Northwind Climate", domain: "field service" });
  await api(setup, "POST", `/projects/${project.id}/documents/paste`, { title: "client-brief", text: BRIEF });
  const job = await api(setup, "POST", `/projects/${project.id}/estimates/generate`, { document_ids: [], learning: true });
  for (let i = 0; i < 360; i++) {
    if ((await api(setup, "GET", `/jobs/${job.id}`)).status === "done") break;
    await setup.waitForTimeout(500);
  }
  const state = await setup.context().storageState();

  for (const theme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: theme, storageState: state });
    await ctx.addInitScript((t) => window.localStorage.setItem("theme", t), theme);
    const page = await ctx.newPage();
    const shot = async (name: string, kinds: ("webp" | "help")[] = ["webp"], el?: string, top = true) => {
      if (top) await page.evaluate(() => window.scrollTo(0, 0));
      await settle(page);
      const buf = el ? await page.locator(el).first().screenshot() : await page.screenshot({ mask: [page.getByText(/@[\w.-]+\.\w+/)] });
      await save(buf, `${name}-${theme}`, theme === "light" ? kinds : ["webp"]);
    };

    await page.goto("/dashboard");
    await shot("dashboard");
    await shot("checklist", ["webp"], "[data-tour=checklist]");
    await page.goto("/projects");
    await shot("projects", ["webp", "help"]);

    await page.goto(`/projects/${project.id}`);
    await page.getByRole("tab", { name: "Estimate" }).click();
    const box = page.getByRole("textbox", { name: "Message the agent" });
    if (!(await box.isVisible())) await page.getByRole("button", { name: "Agent", exact: true }).click();
    if (theme === "light") {
      const sendBtn = page.getByRole("button", { name: "Send", exact: true });
      for (const msg of ["/similar", "Reduce QA by 20%", "Add a task for offline sync conflict handling in the technician app, 16-24 hours"]) {
        for (let i = 0; i < 60 && !(await sendBtn.isEnabled().catch(() => false)); i++) await page.waitForTimeout(250);
        await box.fill(msg);
        await box.press("Enter");
        await sendBtn.waitFor({ state: "visible", timeout: 60_000 });
        await page.waitForTimeout(500);
      }
    }
    const chatLog = page.locator("[data-slot=scroll-area-viewport]", { has: page.getByText("/similar", { exact: true }) });
    await shot("agent-refs", ["webp"]);
    await chatLog.evaluate((el) => (el.scrollTop = el.scrollHeight));
    await page.getByTestId("tool-card").last().evaluate((el) => el.scrollIntoView({ block: "end" }));
    await page.waitForTimeout(300);
    await shot("agent", ["webp", "help"], undefined, false);
    await shot("references", ["webp"], "[data-testid=references-card]");
    await page.getByRole("button", { name: "Close agent panel" }).click();
    await shot("estimate", ["webp", "help"]);
    await page.getByRole("button", { name: /Why this number/ }).first().click();
    await page.getByRole("dialog").waitFor();
    await shot("why", ["webp", "help"]);
    await page.keyboard.press("Escape");

    await page.goto("/insights");
    await shot("insights", ["webp", "help"]);
    await page.getByTestId("chart-bias-by-category").scrollIntoViewIfNeeded();
    await shot("insights-charts", ["webp"], undefined, false);
    await page.goto("/backtest");
    await shot("backtest");
    await page.goto("/help/getting-started");
    await shot("help");
    await ctx.close();
  }
  const og = await sharp(path.join(PUB, "landing", "estimate-light.webp")).resize(1200, 630, { fit: "cover", position: "top" }).png().toBuffer();
  await sharp(og).toFile(path.join(PUB, "og.png"));
  await browser.close();
  console.log("screenshots written to frontend/public/{landing,help}");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
