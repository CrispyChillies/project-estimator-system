# Agent Panel protocol

Base path `/api/v1`. Sessions belong to an estimate. One run per session at a time.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/estimates/{id}/agent/sessions` | pinned first, then most recent |
| POST | `/estimates/{id}/agent/sessions` | `{title?, apply_mode: auto\|review}` |
| PATCH | `/agent/sessions/{sid}` | `title, pinned, apply_mode, use_memory, state, status(active\|archived)` |
| DELETE | `/agent/sessions/{sid}` | soft delete |
| GET | `/agent/sessions/{sid}/messages` | roles `user, assistant, system_event` |
| GET | `/agent/sessions/{sid}/operations` | all operations with status |
| POST | `/agent/sessions/{sid}/runs` | `{text, idempotency_key?}` → SSE stream; **409** if a run is active |
| POST | `/agent/sessions/{sid}/cancel` | stops the run at the next step boundary |
| POST | `/agent/operations/{oid}/confirm` · `/reject` · `/undo` | confirm applies; undo may be partial |
| POST | `/agent/batches/{batch_id}/undo` | "Undo all" for one turn |
| GET/POST | `/estimates/{id}/memories` | project memories; PATCH/DELETE `/memories/{mid}` |

## SSE events (in order of a typical run)

| Event | Data |
|---|---|
| `run_started` | `run_id, session_id, batch_id, message_id, apply_mode` (`duplicate: true` for a repeated idempotency key) |
| `stage` | `label` |
| `tool_call_started` | `id, name, args` |
| `tool_call_result` | `id, name, ok, status?, summary?, operation_id?, before?, after?, error?, message?, data?` |
| `table_patch` | `operation_id, batch_id, task_ids, created_ids, before:[min,max], after:[min,max]` — refetch/highlight rows |
| `confirmation_required` | `operation_id, summary, reasons[], before, after, delta_pct, touched_task_ids` |
| `ask_user` | `question, options[]` |
| `references` | `items[]` (similar projects), `error?` |
| `memory_updated` | `state, memories[]` |
| `message_delta` | `text` |
| `message_done` | `message_id, text` |
| `cost_update` | `tokens, cost_usd, session_cost_usd, offline` |
| `error` | `code, message` |
| `run_done` | `status: completed\|awaiting_confirmation\|awaiting_user\|cancelled\|failed\|duplicate, batch_id, applied` |

Every stream ends with `run_done`. Changes are committed as each tool finishes, so a `table_patch` can be
refetched immediately.

## Apply policy

`auto` applies writes immediately. Always ask first (operation `awaiting_confirmation`, run pauses) when:
the session is in `review` mode; the tool deletes (tasks or a group); the visible total midpoint changes by more
than `AGENT_CONFIRM_DELTA_PCT` (30%); the turn exceeds `AGENT_MAX_OPS_PER_TURN` (25) primitive changes; or a
touched task was edited by a user in the last `AGENT_RECENT_EDIT_MINUTES` (30). After a pause no further writes
run in that turn. Confirm/reject are recorded as `system_event` messages so the model sees them next turn.

## Limits

`AGENT_MAX_STEPS` = 12 model steps; `AGENT_HISTORY_TOKEN_BUDGET` = 6000 (older turns are folded into an
extractive rolling summary); a stale run lock (no activity for 300 s) can be taken over.

## Modes

`live`/`record`: LangChain tool-calling agent over the typed tools. `fake`/`replay` and any message starting
with `/`: the deterministic planner (`app/agents/planner.py`) issues the same tool calls. Slash commands:
`/fit N`, `/adjust ±P% [role|group]`, `/round [step]`, `/similar [k]`, `/remember text`, `/budget N`
(`/new` is handled by the client).
