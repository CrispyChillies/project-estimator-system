# Ship report — Prompt 5 ("Finish and ship Calibr")

Date: 2026-10-20. Every number below was measured in this run; nothing is estimated.

## Where it is

| | Status |
|---|---|
| Frontend | **Live:** https://project-calibrate.vercel.app (landing, help, sign-in/up pages). |
| API + database | **Ready to deploy, not deployed.** Render Blueprint (`render.yaml`) + production image; needs the owner's Render account and secrets ([DEPLOYMENT.md](DEPLOYMENT.md)). Until then `/api/*` on the Vercel URL returns 404. |
| End-to-end rehearsal | Production API image → empty Postgres → archive seed → production Next build → `make deploy-check` with sign-in, live estimate and streamed agent run: **21/21 passed**. |
| `make deploy-check URL=https://project-calibrate.vercel.app` today | 7 passed (pages, robots, CSP/nosniff, HSTS, docs hidden), 8 failed — all API checks, because the API is not deployed yet. |

## Requirements

| Requirement | Status | Evidence |
|---|---|---|
| A. Preserve test data | Done | `pg_dump` backup `backups/calibr-pre-prompt5-*.dump`; only additive migrations (0004, 0005); `compare pre-prompt5 final`: no table lost rows ([DATA_INVENTORY.md](DATA_INVENTORY.md)). All data owned by the admin. |
| B. Model locked, spend capped | Done | Body keys like `model`/`provider` → 400 `model_locked` (tests + deploy check); global `LLM_BUDGET_USD`, per-user daily cap, hourly limit, concurrency limit (tests). |
| C. Honesty | Done | Screenshots captured from the running product (`make landing-shots`), footnote "Screenshots show fictional sample data."; no testimonials, logos or invented metrics; copy check (`make check-copy`) passes on source and built pages. |
| D. Security | Done | argon2id, HttpOnly/Secure/SameSite=Lax cookies, double-submit CSRF, login throttling, per-endpoint authorization (`tests/test_authz.py`, 14 tests), CSP/HSTS/nosniff, docs off in production. |
| P1 Accounts / ownership / admin archive | Done | Phase 1+2 commits; admin panel (users, usage, archive switch, learning). |
| P2 Model lock + cost caps | Done | as B. |
| P3 Chat agent works | Done | Root causes in [CHAT_DIAGNOSIS.md](CHAT_DIAGNOSIS.md); live smoke 6/6 tool-call accuracy; SSE through production Next: first chunk 23–30 ms, uncompressed; polling fallback covered by E2E. |
| P4 No demo traces | Done | `scripts/check_no_demo_strings.mjs` in `make test` and CI. |
| P5 Onboarding, help, analytics | Done | Welcome + 8-step tour, checklist, `/help` guides, 8 analytics charts with sample sizes. |
| P6 Landing page | Done | Lighthouse (production build, `docs/lighthouse/landing-scores.json`): mobile performance **94**, accessibility **100**, best practices **100**; desktop **100 / 100 / 100**. SEO 69 only because indexing is off by default (`ROBOTS_INDEX`). axe (WCAG 2.1 A/AA, light + dark, public + app pages): 0 serious/critical. |
| P7 Deployment | Partly | Frontend deployed; API/DB config, image, seed/restore, deploy check and runbook done and rehearsed; Render deploy pending (owner action). |
| P8 Verification | Done | This report. |

## Tests

* Backend: **110 passed** (`pytest`), `ruff check` clean.
* E2E (Playwright, isolated stack): **23 passed, 2 skipped** (live-only specs) — app, chat, onboarding, a11y.
* Frontend: `pnpm lint` clean, `tsc` clean on sources, `pnpm build` OK.

## LLM spend

| | USD |
|---|---:|
| Ledger total, all time (`data/llm_spend.jsonl`) | 0.0604 |
| Ledger total at the start of Prompt 5 | 0.0345 |
| **Spent during Prompt 5** (live smoke, live UI checks, screenshots ×4, deploy rehearsal) | **0.0259** |
| Limit for this prompt | 3.00 |

## Chat root causes (summary)

1. `LLM_MODE=replay` exported in the shell forced replay mode → cache misses. Production now refuses non-live modes.
2. A stale uvicorn process (started before the Phase-4 commit) served old routes.
3. Cross-origin calls from a second dev port were blocked by CORS → the frontend now always calls a same-site
   `/api` proxy.
Hardening: heartbeat events, 20 s watchdog with polling fallback, error card with Retry.

## Owner actions to finish

1. `git push origin main`.
2. Render → New → Blueprint → this repo → enter `OPENAI_API_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `INVITE_CODE`.
3. Load the archive: `DATABASE_URL='<External Database URL>' ADMIN_EMAIL=… scripts/restore_admin_archive.sh`,
   then restart the API service.
4. If Render's URL differs from `https://project-calibrate-api.onrender.com`, update `BACKEND_URL` on Vercel and
   redeploy (commands in [DEPLOYMENT.md](DEPLOYMENT.md)).
5. `make deploy-check URL=https://project-calibrate.vercel.app` (add `DEPLOY_CHECK_EMAIL/PASSWORD` for sign-in).

Known issues: [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
