"""Tiny live smoke tests (structured output, tool calling, reasoning param, embeddings, agent API).

Usage: LLM_MODE=live OPENAI_MODEL=gpt-6-luna OPENAI_EMBEDDING_MODEL=text-embedding-3-small \
       python scripts/preflight.py [--reasoning none]
Spend is capped by the 'preflight' section budget. Never prints the API key.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.llm import budget  # noqa: E402
from app.llm.gateway import LLMGateway, UsageCallback  # noqa: E402


class Pong(BaseModel):
    answer: str
    number: int


def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def run(name: str, fn) -> dict:
    t0 = time.monotonic()
    try:
        out = fn()
        return {"check": name, "ok": True, "detail": out, "ms": int((time.monotonic() - t0) * 1000)}
    except Exception as e:  # report, don't crash: this is a diagnostic
        msg = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
        return {"check": name, "ok": False, "detail": str(msg)[:400], "ms": int((time.monotonic() - t0) * 1000)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reasoning", default=None)
    ap.add_argument("--limit", type=float, default=0.05)
    args = ap.parse_args()
    s = get_settings()
    gw = LLMGateway(mode="live", reasoning=args.reasoning)
    results = []
    with budget.budget("preflight", args.limit):
        results.append(run("structured_output", lambda: gw.structured(
            "preflight", [("user", "Reply with answer='pong' and number=7.")], Pong,
            prompt_version="preflight-v1", fake=lambda: Pong(answer="", number=0)).model_dump()))

        def tools():
            llm = gw._chat(0.0, callbacks=[UsageCallback(gw)]).bind_tools([add])
            msg = llm.invoke("Use the add tool to compute 2 + 3.")
            return [{"name": c["name"], "args": c["args"]} for c in msg.tool_calls]
        results.append(run("tool_calling", tools))

        def temperature():
            llm = gw._chat(None, callbacks=[UsageCallback(gw)])
            llm.temperature = 0.2
            return llm.invoke("Say ok.").content[:20]
        results.append(run("temperature_0.2_accepted", temperature))

        def embeddings():
            v = gw.embed(["calibr preflight embedding check"])
            return {"dim": len(v[0]), "expected": s.embedding_dim}
        results.append(run("embeddings", embeddings))

        def agent():
            from langchain.agents import create_agent

            a = create_agent(gw._chat(0.0, callbacks=[UsageCallback(gw)]), tools=[add],
                             system_prompt="Use tools for arithmetic.")
            out = a.invoke({"messages": [{"role": "user", "content": "What is 40 + 2? Use the tool."}]})
            msgs = out["messages"]
            return {"n_messages": len(msgs), "tool_called": any(getattr(m, "type", "") == "tool" for m in msgs),
                    "final": str(msgs[-1].content)[:60]}
        results.append(run("langchain_create_agent", agent))

        results.append({"check": "section_spend_usd", "ok": True, "detail": round(budget.section_spent(), 6)})
    import langchain
    import langchain_openai  # noqa: F401
    print(json.dumps({"model": gw.model, "reasoning": gw.reasoning, "model_key": gw.model_key,
                      "embedding_model": gw.embedding_model, "langchain": langchain.__version__,
                      "results": results}, indent=1, default=str))


if __name__ == "__main__":
    main()
