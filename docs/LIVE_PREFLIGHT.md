# Live preflight (2026-10-18)

Command (cost cap `preflight` = $0.05):

```bash
cd backend && LLM_MODE=live OPENAI_MODEL=gpt-6-luna OPENAI_EMBEDDING_MODEL=text-embedding-3-small \
  uv run python scripts/preflight.py --reasoning none
```

| Check | Result |
|---|---|
| Chat model responds (`gpt-6-luna`) | ✅ |
| Structured output (Pydantic via `with_structured_output(include_raw=True)`) | ✅ `{"answer": "pong", "number": 7}` |
| Tool calling (`bind_tools`) | ✅ `add(a=2, b=3)` |
| Reasoning-effort parameter | ✅ accepted; Luna supports `none` (docs: none/low/medium/high/xhigh/max). Used `none` for extraction, decomposition and estimation. Sol's lowest setting is `low`. |
| Custom temperature with `reasoning_effort=none` | ✅ accepted (the gateway omits temperature when reasoning is on, since reasoning models reject it) |
| Embeddings (`text-embedding-3-small`, cheapest current: $0.02/1M) | ✅ dim 1536 = `EMBEDDING_DIM` = pgvector column; no migration needed |
| LangChain agent API (`langchain` 1.4.6 `create_agent`) | ✅ tool executed, 4 messages; the agent path used by `chat_agent.py` works live |
| Spend logged to `llm_calls` with tokens/cost | ✅ total ≈ $0.00006 (first attempt logged nothing because the dev DB lacked migration 0002 — fixed: unlogged live spend now still counts against the cap) |

`model_key` = `gpt-6-luna|estimation-v1|r=none`.

Observation: `langchain-openai` routes these models through the Responses API; message `content` is a
list of content blocks (`[{"type": "text", ...}]`), not a string. Code that reads `.content` must handle both.
Prices (standard tier, per 1M tokens) re-verified on the pricing page today: Luna 0.10 / 0.01 cached / 0.50;
Sol 2.00 / 0.10 / 10.00; text-embedding-3-small 0.02.
