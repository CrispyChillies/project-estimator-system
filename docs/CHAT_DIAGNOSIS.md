# Chat agent diagnosis

## What broke (root causes, with evidence)

| # | Suspected cause | Real? | Evidence | Fix |
|---|---|---|---|---|
| 1 | Backend running in **replay** mode, so any new brief, upload or estimate failed with a cache miss | **Yes** | The reported error read *"LLM_MODE=replay but no cached response for 'embedding'"*. `.env` said `LLM_MODE=record`, but `ps eww <uvicorn pid>` showed `LLM_MODE=replay` exported in the shell. Process environment overrides `.env`, so restarting with `--reload` kept replay. | Production now refuses to start unless `LLM_MODE=live` (`app/core/bootstrap.py::validate_config`, test `test_production_refuses_fake_llm`). The mode is never user-selectable. Fake/replay remain test-only. |
| 2 | A **stale backend process** served old routes, so the new panel got 404s and appeared dead | **Yes** | The local uvicorn on :8000 (PID 25602) started at 11:11 without `--reload`. The Phase 4 agent API (`/agent/sessions/*`) was committed at 11:23 and the Phase 5 panel at 17:38. Every panel call hit routes the running process did not have. | `/api/v1/health` and `/ready` report the migration revision. The panel now shows a readable error card with **Retry** instead of an endless spinner. The deployment runbook restarts on release. |
| 3 | **CORS / cookie** problems when the UI ran on another port (:3001) | **Yes** (dev) | `CORS_ORIGINS` only allowed `:3000`, so the browser blocked the :3001 dev server's API calls. | The browser now calls the API **same-site** (`/api/*` is rewritten by Next.js to the backend), so there are no CORS or third-party cookies. Session and CSRF cookies are first-party. |
| 4 | Session creation failing | No | The `POST /estimates/{id}/agent/sessions` path is covered by the E2E `chat.spec.ts` and by `test_authz` (create + cross-user 404). | — |
| 5 | Auth/CSRF header missing on the stream request | Fixed preventively | Sign-in did not exist before this work. `postSSE` now sends `X-CSRF-Token` and same-origin credentials. A missing token gives a 403 with a readable message, which the panel shows. | `frontend/src/lib/api.ts` |
| 6 | SSE buffered or dropped by the dev proxy, rewrite or compression | Not observed. Hardened anyway | Live run through the Next.js rewrite: response `text/event-stream` in **45 ms**, first tool card after **3.0 s**, run finished in **4.8 s** (`data/inventory/live-chat-diagnosis.json`). | `compress: false` in Next.js; `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`. **Heartbeat** event every 15 s from a worker thread. Automatic **polling fallback** (`POST …/runs/async` + polling) when no event arrives within 20 s or the stream cannot connect; covered by E2E with the stream request aborted. |
| 7 | Frontend state machine stuck after the first event | No | The timeline is rebuilt from persisted messages and operations after every run. A client disconnect no longer aborts the run (it now runs in a worker thread), and the panel resumes by polling `run_state`. | — |
| 8 | Agent loop erroring on tool schemas | Minor | Live run: the model passed `category: "Authentication"` (a display name) and got a validation error, then retried with `auth` and succeeded. | Tools now also accept category display names. |
| 9 | Panel not mounted on the estimate page | No | It mounts with the toggle button or Ctrl/⌘+J, and auto-opens after generation (E2E). | — |
| 10 | Errors swallowed | Partly | The old panel only showed a toast. | Error card with the server's message and **Retry**. Allowance, rate-limit and "run in progress" errors are shown, never silently retried. |

## Live smoke test (real model, `backend/scripts/live_chat_smoke.py`, section cap $0.50)

Model: the configured production model (cheapest passing one from the bake-off). The estimate was generated offline,
so only chat cost money.

| # | Scenario | Prompt | Tools called | Run status | Pass | Cost USD | Tokens |
|---|---|---|---|---|---|---:|---:|
| 1 | fit-to-budget | Fit the whole estimate to 400 hours | fit_to_budget | completed | yes | 0.0003 | 4635 |
| 2 | add task | Add an SSO task under <group> with 12-20 hours | create_task (category name rejected), create_task | completed | yes | 0.0004 | 7403 |
| 3 | bulk adjust | Reduce QA by 20% | list_tasks, bulk_adjust | completed | yes | 0.0004 | 8079 |
| 4 | explain | Why is the <largest> task so high? | explain_task | completed | yes | 0.0004 | 5731 |
| 5 | ambiguous | Make it cheaper | ask_user | awaiting_user | yes | 0.0001 | 4709 |
| 6 | nonexistent target | Add … under the Billing Reports group … | list_tasks, ask_user | awaiting_user | yes | 0.0001 | 7244 |

**Result: tool-call accuracy 6/6 (100 %); total cost $0.0018.**

How each scenario was graded:
- **Fit-to-budget:** the total of max hours became exactly 400 h.
- **Add task:** SSO was created at 12–20 h.
- **Bulk adjust:** QA was reduced by 20 %.
- **Explain:** made no changes.
- **Ambiguous:** asked with options ("cut all tasks by 10% or 20%, fit a budget, or reduce a group").
- **Nonexistent target:** answered *"'Billing Reports' doesn't exist in the estimate. Should I create it, or add … to 'Reporting & analytics' or 'Payments'?"* and created nothing.

Live UI pass (`frontend/e2e/live-chat.spec.ts`, `E2E_LLM_MODE=live LIVE=1`):
- Prompt: "Reduce all backend tasks by 10%".
- Result: 6 rows changed in the table, no console errors, and the streamed response arrived through the same-site proxy.

## Tests that guard this

- **Backend:** `tests/test_agent_panel.py`, 16 tests. They cover:
  - streaming events and the apply policy
  - confirmation, undo and partial undo
  - idempotency, the run lock, memory and rolling summary
  - selection, document injection, heartbeat and the polling transport
  - the live tool loop driven by a scripted model
- **Authorization:** `tests/test_authz.py`. A member's agent cannot read or run on another member's estimate (404).
- **E2E (fake LLM):** `frontend/e2e/chat.spec.ts` covers:
  - streamed answer and tool card with JSON args
  - live table change, then undo restores the table
  - delete confirmation and the selection chip
  - polling fallback with the stream blocked
  - a new session, and reload keeping history

## Remaining limits

- The hourly request limiter is per process (approximate when several workers run).
- Over SSE the panel shows streamed text as it arrives. In polling mode, text appears when the turn finishes.
