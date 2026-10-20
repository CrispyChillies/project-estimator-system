#!/usr/bin/env node
// Smoke-tests a deployment through its public URL and prints a pass/fail table.
//   make deploy-check URL=https://project-calibrate.vercel.app
// Optional (never printed): DEPLOY_CHECK_EMAIL / DEPLOY_CHECK_PASSWORD to test sign-in and authorised calls;
// DEPLOY_CHECK_AI=1 additionally generates an estimate and streams one agent run (live model, ~1 cent).
const BASE = (process.argv[2] || process.env.URL || "").replace(/\/$/, "");
if (!BASE) {
  console.error("usage: node scripts/deploy_check.mjs <url>");
  process.exit(2);
}
const RUN = `CALIBR-RUN-${Date.now().toString(36)}`; // prefix for everything this run creates
const HTTPS = BASE.startsWith("https://");
const jar = new Map();
const rawCookies = [];
const rows = [];
const check = (name, ok, detail = "") => rows.push({ name, result: ok === null ? "SKIP" : ok ? "PASS" : "FAIL", detail });

async function req(method, path, { body, headers = {}, csrf = true } = {}) {
  const h = { cookie: [...jar].map(([k, v]) => `${k}=${v}`).join("; "), ...headers };
  if (csrf && method !== "GET") h["X-CSRF-Token"] = jar.get("calibr_csrf") ?? "";
  if (body !== undefined) h["Content-Type"] = "application/json";
  const r = await fetch(BASE + path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body), redirect: "manual" });
  for (const c of r.headers.getSetCookie()) {
    rawCookies.push(c);
    const [kv] = c.split(";");
    const i = kv.indexOf("=");
    jar.set(kv.slice(0, i), kv.slice(i + 1));
  }
  return r;
}
const text = async (r) => (r.bodyUsed ? "" : r.text());
const cookieAttrs = (name) => rawCookies.filter((c) => c.startsWith(`${name}=`)).at(-1) ?? "";

async function main() {
  const home = await req("GET", "/");
  const html = await text(home);
  check("landing page", home.status === 200 && html.includes("Calibr"), `HTTP ${home.status}`);
  const help = await req("GET", "/help");
  check("help pages", help.status === 200, `HTTP ${help.status}`);
  const robots = await req("GET", "/robots.txt");
  check("robots.txt", robots.status === 200, (await text(robots)).split("\n").slice(0, 2).join(" ").trim());
  const csp = home.headers.get("content-security-policy") ?? "";
  check("security headers", !!csp && home.headers.get("x-content-type-options") === "nosniff" && /frame-ancestors 'none'/.test(csp),
    `CSP ${csp ? "set" : "missing"}, nosniff ${home.headers.get("x-content-type-options") ?? "missing"}`);
  if (HTTPS) check("HSTS", !!home.headers.get("strict-transport-security"), home.headers.get("strict-transport-security") ?? "missing");

  const health = await req("GET", "/api/v1/health");
  check("API reachable via same-site proxy", health.status === 200, `HTTP ${health.status}`);
  const ready = await req("GET", "/api/v1/ready");
  check("database migrated (/ready)", ready.status === 200, (await text(ready)).slice(0, 80));
  const docs = await req("GET", "/api/v1/docs");
  check("API docs not exposed", docs.status === 404 || docs.status === 401, `HTTP ${docs.status}`);

  const session = await req("GET", "/api/v1/auth/session");
  check("anonymous session = null", session.status === 200 && (await session.json()).user === null, `HTTP ${session.status}`);
  const anon = await req("GET", "/api/v1/projects");
  check("unauthenticated API → 401", anon.status === 401, `HTTP ${anon.status}`);
  await req("GET", "/api/v1/auth/csrf");
  const csrfCookie = cookieAttrs("calibr_csrf");
  check("CSRF cookie flags", !!csrfCookie && /samesite=lax|samesite=strict/i.test(csrfCookie) && (!HTTPS || /secure/i.test(csrfCookie)),
    csrfCookie.split(";").slice(1).map((s) => s.trim()).join("; "));
  const noCsrf = await req("POST", "/api/v1/auth/login", { body: { email: "x@example.com", password: "x" }, csrf: false });
  check("write without CSRF token → 403", noCsrf.status === 403, `HTTP ${noCsrf.status}`);
  const cfg = await (await req("GET", "/api/v1/auth/config")).json().catch(() => ({}));
  const signup = await req("POST", "/api/v1/auth/signup", { body: { name: `${RUN} signup`, email: `${RUN.toLowerCase()}@example.com`, password: "a-long-password-123" } });
  const mode = cfg.signup_mode ?? cfg.mode ?? "?";
  check(`sign-up rules (mode: ${mode})`, mode === "?" ? false : mode === "open" ? signup.status < 300 : signup.status >= 400, `HTTP ${signup.status}`);
  const bad = await req("POST", "/api/v1/auth/login", { body: { email: "nobody@example.com", password: "wrong-password-123" } });
  check("bad login → generic 401", bad.status === 401, `HTTP ${bad.status}`);

  const email = process.env.DEPLOY_CHECK_EMAIL;
  const password = process.env.DEPLOY_CHECK_PASSWORD;
  if (!email || !password) {
    check("sign-in (set DEPLOY_CHECK_EMAIL/PASSWORD)", null);
  } else {
    const login = await req("POST", "/api/v1/auth/login", { body: { email, password } });
    const sc = cookieAttrs("calibr_session");
    check("sign-in", login.status === 200, `HTTP ${login.status}`);
    check("session cookie flags", /httponly/i.test(sc) && /samesite/i.test(sc) && (!HTTPS || /secure/i.test(sc)),
      sc.split(";").slice(1).map((s) => s.trim()).join("; "));
    const me = await req("GET", "/api/v1/auth/me");
    check("/auth/me", me.status === 200, `HTTP ${me.status}`);
    const projects = await req("GET", "/api/v1/projects");
    const list = projects.status === 200 ? await projects.json() : [];
    check("projects visible", projects.status === 200, `${list.length} projects`);
    const locked = await req("POST", "/api/v1/projects", { body: { name: "model override check", model: "some-other-model" } });
    check("model cannot be changed by users", locked.status === 400, `HTTP ${locked.status}`);
    if (process.env.DEPLOY_CHECK_AI === "1") {
      const p = await (await req("POST", "/api/v1/projects", { body: { name: `${RUN} project` } })).json();
      try {
        await req("POST", `/api/v1/projects/${p.id}/documents/paste`, { body: { title: "brief", text: "Booking web app with customer login, online payments and an admin panel for staff." } });
        const job = await (await req("POST", `/api/v1/projects/${p.id}/estimates/generate`, { body: { document_ids: [], learning: true } })).json();
        let status = "";
        for (let i = 0; i < 240 && !["done", "failed"].includes(status); i++) {
          status = (await (await req("GET", `/api/v1/jobs/${job.id}`)).json()).status;
          if (status !== "done") await new Promise((r) => setTimeout(r, 1000));
        }
        check("estimate generation (live model)", status === "done", status);
        const [est] = await (await req("GET", `/api/v1/projects/${p.id}/estimates`)).json();
        const s = await (await req("POST", `/api/v1/estimates/${est.id}/agent/sessions`, { body: {} })).json();
        const t0 = Date.now();
        const run = await req("POST", `/api/v1/agent/sessions/${s.id}/runs`, { body: { text: "Reduce QA by 10%" }, headers: { Accept: "text/event-stream" } });
        let first = 0;
        let body = "";
        const reader = run.body.getReader();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          first ||= Date.now() - t0;
          body += new TextDecoder().decode(value);
        }
        check("agent chat streams (SSE)", run.status === 200 && /event: run_done/.test(body) && !/event: error/.test(body),
          `first chunk ${first} ms, total ${Date.now() - t0} ms, encoding ${run.headers.get("content-encoding") ?? "none"}`);
      } finally {
        const del = await req("DELETE", `/api/v1/projects/${p.id}`);
        check("cleanup (own project removed)", del.status < 300, `HTTP ${del.status}`);
      }
    }
    await req("POST", "/api/v1/auth/logout");
  }

  report();
}

function report() {
  const w = Math.max(...rows.map((r) => r.name.length));
  console.log(`\nDeploy check: ${BASE}\n`);
  for (const r of rows) console.log(`${r.result.padEnd(5)} ${r.name.padEnd(w)}  ${r.detail}`);
  const failed = rows.filter((r) => r.result === "FAIL").length;
  console.log(`\n${rows.filter((r) => r.result === "PASS").length} passed, ${failed} failed, ${rows.filter((r) => r.result === "SKIP").length} skipped`);
  process.exit(failed ? 1 : 0);
}

main().catch((e) => {
  check("deploy check crashed", false, e.message);
  report();
});
