#!/usr/bin/env node
/**
 * Fails when user-facing text contains demo/sample wording.
 *  - Source: string literals and JSX text in frontend/src (attribute names, Tailwind variants and
 *    allow-listed files are ignored).
 *  - Built output: visible text of pre-rendered HTML pages in frontend/.next/server/app (if a build exists).
 * Usage: node scripts/check_no_demo_strings.mjs   (exit 1 on findings)
 */
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const SRC = path.join(ROOT, "frontend", "src");
const BUILD = path.join(ROOT, "frontend", ".next", "server", "app");
const PATTERN = /\b(demo|synthetic|fake|offline agent|offline planner|lorem|placeholder|sample data)\b/i;
// Files where these words are legitimate (admin archive wording, generated API types, tests).
const ALLOW_FILES = [
  "frontend/src/lib/api-types.ts",
  "frontend/src/app/(app)/admin/page.tsx",
  "frontend/src/components/admin/",
];
// Literals that are code, not copy.
const CODE_LIKE = /^[\w./@:-]+$|placeholder:|^[a-z0-9-]+(\s+[a-z0-9:/[\]().%-]+)+$/;

function walk(dir, exts, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, exts, out);
    else if (exts.some((x) => e.name.endsWith(x))) out.push(p);
  }
  return out;
}

const findings = [];
for (const file of walk(SRC, [".ts", ".tsx"])) {
  const rel = path.relative(ROOT, file);
  if (ALLOW_FILES.some((a) => rel.startsWith(a))) continue;
  const lines = fs.readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    if (/^\s*(\/\/|\*|\/\*|import )/.test(line)) return;
    const literals = [...line.matchAll(/"([^"]*)"|'([^']*)'|`([^`]*)`/g)].map((m) => m[1] ?? m[2] ?? m[3]);
    const jsxText = [...line.matchAll(/>([^<>{}]+)</g)].map((m) => m[1]);
    const bare = /^\s*[A-Za-z][^=<>{}();]*$/.test(line) && !/[;{}]$/.test(line.trim()) ? [line.trim()] : [];
    for (const text of [...literals, ...jsxText, ...bare]) {
      if (!text || CODE_LIKE.test(text.trim())) continue;
      if (PATTERN.test(text)) findings.push(`${rel}:${i + 1}: ${text.trim().slice(0, 120)}`);
    }
  });
}
for (const file of walk(BUILD, [".html"])) {
  const rel = path.relative(ROOT, file);
  const text = fs
    .readFileSync(file, "utf8")
    .replace(/<script[\s\S]*?<\/script>/g, " ")
    .replace(/<style[\s\S]*?<\/style>/g, " ")
    .replace(/<[^>]+>/g, " ");
  const m = text.match(new RegExp(`.{0,40}${PATTERN.source}.{0,40}`, "i"));
  if (m && !rel.includes("admin")) findings.push(`${rel}: ${m[0].trim()}`);
}

if (findings.length) {
  console.error(`Demo/sample wording found in user-facing text (${findings.length}):\n` + findings.join("\n"));
  process.exit(1);
}
console.log("check_no_demo_strings: OK (source" + (fs.existsSync(BUILD) ? " + built pages" : "") + ")");
