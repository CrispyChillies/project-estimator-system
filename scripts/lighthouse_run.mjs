// Runs from frontend/ (inside scripts/lighthouse.sh) so lighthouse + playwright resolve from frontend/node_modules.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(path.resolve("package.json"));
const chrome = require("@playwright/test").chromium.executablePath();
const url = `${process.env.E2E_BASE_URL ?? "http://localhost:3005"}/`;
const out = {};
for (const preset of ["mobile", "desktop"]) {
  const base = `/tmp/calibr-lh-${preset}`;
  const args = [url, "--quiet", "--output=json", "--output=html", `--output-path=${base}`, `--chrome-path=${chrome}`,
    "--chrome-flags=--headless=new --no-sandbox", "--only-categories=performance,accessibility,best-practices,seo"];
  if (preset === "desktop") args.push("--preset=desktop");
  execFileSync(path.resolve("node_modules/.bin/lighthouse"), args, { stdio: "inherit" });
  const r = JSON.parse(fs.readFileSync(`${base}.report.json`, "utf8"));
  out[preset] = {
    ...Object.fromEntries(Object.entries(r.categories).map(([k, v]) => [k, Math.round(v.score * 100)])),
    lcp_ms: Math.round(r.audits["largest-contentful-paint"].numericValue),
    cls: Number(r.audits["cumulative-layout-shift"].numericValue.toFixed(3)),
    tbt_ms: Math.round(r.audits["total-blocking-time"].numericValue),
    failing_a11y: Object.values(r.audits).filter((a) => r.categories.accessibility.auditRefs.some((x) => x.id === a.id) && a.score === 0).map((a) => a.id),
  };
}
const result = { url: "/ (landing, production build)", lighthouse: JSON.parse(fs.readFileSync("node_modules/lighthouse/package.json", "utf8")).version, measured_at: new Date().toISOString(), ...out };
fs.writeFileSync(path.resolve("../docs/lighthouse/landing-scores.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
