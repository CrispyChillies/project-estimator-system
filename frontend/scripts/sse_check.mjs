// Streams one agent run through the Next.js proxy and reports whether the SSE response is compressed/buffered.
// Runs inside the isolated stack (STACK_CMD) with E2E_BASE_URL / E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD set.
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3005";
const jar = new Map();
async function call(method, path, body, extra = {}) {
  const headers = { cookie: [...jar].map(([k, v]) => `${k}=${v}`).join("; "), ...extra };
  if (method !== "GET") headers["X-CSRF-Token"] = jar.get("calibr_csrf") ?? "";
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(`${BASE}/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  for (const c of r.headers.getSetCookie()) {
    const [kv] = c.split(";");
    const i = kv.indexOf("=");
    jar.set(kv.slice(0, i), kv.slice(i + 1));
  }
  return r;
}
const json = async (...a) => {
  const r = await call(...a);
  if (!r.ok) throw new Error(`${a[0]} ${a[1]} -> ${r.status}`);
  return r.json();
};

await call("GET", "/auth/csrf");
await json("POST", "/auth/login", { email: process.env.E2E_ADMIN_EMAIL, password: process.env.E2E_ADMIN_PASSWORD });
const p = await json("POST", "/projects", { name: `SSE check ${Date.now()}` });
await json("POST", `/projects/${p.id}/documents/paste`, { title: "brief", text: "Booking web app with login, payments and an admin panel." });
const job = await json("POST", `/projects/${p.id}/estimates/generate`, { document_ids: [], learning: false });
for (let i = 0; i < 120 && (await json("GET", `/jobs/${job.id}`)).status !== "done"; i++) await new Promise((r) => setTimeout(r, 500));
const [est] = await json("GET", `/projects/${p.id}/estimates`);
const s = await json("POST", `/estimates/${est.id}/agent/sessions`, {});
const t0 = performance.now();
const r = await call("POST", `/agent/sessions/${s.id}/runs`, { text: "/similar" }, { Accept: "text/event-stream", "Accept-Encoding": "gzip, br" });
const reader = r.body.getReader();
let first = null;
let events = 0;
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  first ??= performance.now() - t0;
  events += (new TextDecoder().decode(value).match(/^event:/gm) ?? []).length;
}
const result = {
  status: r.status,
  content_type: r.headers.get("content-type"),
  content_encoding: r.headers.get("content-encoding") ?? "none",
  cache_control: r.headers.get("cache-control"),
  first_chunk_ms: Math.round(first),
  total_ms: Math.round(performance.now() - t0),
  events,
};
console.log(JSON.stringify(result));
await call("DELETE", `/projects/${p.id}`);
if (result.status !== 200 || result.content_encoding !== "none" || events < 2) process.exit(1);
