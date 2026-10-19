# Agent audit (before the agent-panel work)

## What exists

| Area | Finding | Where |
|---|---|---|
| Agent runtime | LangChain 1.4 `create_agent` (LangGraph) with 11 tools; system prompt `chat-agent-v2` (document text is data, vague requests get a question). Offline mode: regex command parser; replay mode replays recorded cassettes when the prompt text matches exactly. | `backend/app/agents/chat_agent.py`, `app/agents/cassettes.py`, `app/prompts/chat_agent.md` |
| Streaming | `POST /estimates/{id}/agent/messages` returns SSE: `session`, `token`, `tool`, `proposal`, `done`, `error`. Tool events carry only a name (no args/result). | `app/api/agent.py`, `chat_agent.stream_agent` |
| Tools | 4 read-only (`list_tasks`, `get_task_details`, `explain_task`, `find_similar_past_tasks`) and 7 proposal-creating (`propose_*`). **None apply changes**; they append ops to a `change_proposal`, applied only after the user accepts. | `chat_agent.AgentTools`, `services/proposals.py` |
| Agent UI | `AgentPanel` exists but is mounted **only inside the Estimate tab behind an "Agent" toggle button** (default closed, `useState(false)`), as a `ResizablePanel` next to the table. It is not opened after upload and is not on any other tab. That is why the estimate view appears to have no agent. No dock exists. | `frontend/src/components/estimate/estimate-tab.tsx` (l. 121, 258, 312), `agent-panel.tsx` |
| Sessions | `agent_sessions` (estimate_id, mode, created_by) and `agent_messages` (role, content, tool_calls). One session is created per request unless the client sends `session_id`; the client keeps it in a `useRef`, so **a reload starts a new session**. | `db/models/estimate.py`, `agent-panel.tsx` |
| History to model | Prior user/assistant messages of the same session are loaded and passed on each turn **when a session_id is sent**. No tool messages, no summary, no token budget, no state, no cross-session memory. Survives backend restart (DB) but the UI cannot reach old sessions. `GET /agent/sessions/latest` exists but the UI does not use it. | `chat_agent.stream_agent` |
| Retrieval | Task-level only: pgvector cosine over `tasks.embedding` of other projects' *final* estimates, `top_k=5`, same-category preference when ≥3, similarity ≥ `sim_min`=0.75 used for the blend. Called from `services/generation.py` and `services/added_tasks.py` with `exclude_project_id`; backtest uses an in-memory `AnalogIndex` over the training fold only (leakage test in `tests/test_backtest.py`). Feeds `provenance.analogs`, `calibration.blend` (w ≤ 0.6) and the Why panel. **No project-level retrieval, no retrieval context in prompts.** | `services/retrieval.py`, `services/backtest.py` |
| Writes | All task/module writes go through `services/estimates.py` (diff + `edit_events` in one transaction). There is no typed operation object, no preview, no undo, no row versions. | `services/estimates.py` |
| Dock | No tabbed right-hand dock exists. A resizable right panel is added on the estimate page. | — |

## Assumptions that were wrong or incomplete
1. "The agent panel is missing": it exists but is hidden behind a button; it was never wired to the upload flow.
2. "Sessions persist": only server-side; the UI loses the session id on reload.
3. "History is passed back": only if the client resends `session_id`; tool results are not part of it.
4. The earlier brief said agent tools only create proposals; this brief moves to auto-apply with guardrails and undo (logged in DECISIONS.md).
5. `model_key` currently = `model|estimation prompt version|r=<effort>`; it does not include retrieval configuration yet.
