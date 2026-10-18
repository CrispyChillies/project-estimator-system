"""Single entry point for every LLM / embedding call.

Modes (env LLM_MODE):
  live   - call OpenAI
  record - call OpenAI and write responses to data/fixtures/llm_cache
  replay - serve only from cache; raise LLMCacheMiss on a miss
  fake   - deterministic offline heuristics (tests, offline demo without fixtures)

Every live call is budget-checked (app.llm.budget) and logged to llm_calls with its cost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypeVar

from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import LLMCall
from app.db.session import SessionLocal
from app.llm import budget

log = logging.getLogger("llm")
T = TypeVar("T", bound=BaseModel)
FAKE_MODEL_KEY = "fake-v1"


class LLMCacheMiss(AppError):
    def __init__(self, purpose: str, prompt_hash: str):
        super().__init__(
            "llm_cache_miss",
            f"LLM_MODE=replay but no cached response for '{purpose}' ({prompt_hash[:12]}). "
            "Run `make warm-cache` with OPENAI_API_KEY set, or use LLM_MODE=fake.",
            503,
        )


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def hash_embedding(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-words feature-hashing embedding for offline mode."""
    from app.agents.templates import tokens

    vec = [0.0] * dim
    toks = tokens(text)
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
    for f in feats:
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 64) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _usage(msg: Any) -> tuple[int, int, int, int]:
    """(input, output incl. reasoning, cached input, reasoning) from a LangChain AIMessage."""
    u = getattr(msg, "usage_metadata", None) or {}
    tin, tout = int(u.get("input_tokens", 0) or 0), int(u.get("output_tokens", 0) or 0)
    cached = int((u.get("input_token_details") or {}).get("cache_read", 0) or 0)
    reasoning = int((u.get("output_token_details") or {}).get("reasoning", 0) or 0)
    return tin, tout, cached, reasoning


class LLMGateway:
    def __init__(self, model: str | None = None, mode: str | None = None, reasoning: str | None = None) -> None:
        self.s = get_settings()
        self.mode = mode or self.s.llm_mode
        self._model = model or self.s.openai_model
        self.reasoning = self.s.llm_reasoning_effort if reasoning is None else reasoning
        self.cache_dir: Path = self.s.fixtures_dir / "llm_cache"

    @property
    def model(self) -> str:
        return "fake-heuristic" if self.mode == "fake" else (self._model or "unset")

    @property
    def embedding_model(self) -> str:
        return "fake-hash" if self.mode == "fake" else (self.s.openai_embedding_model or "unset")

    @property
    def model_key(self) -> str:
        """Partition key for learning: fake and each live model/prompt/reasoning combo never mix."""
        if self.mode == "fake":
            return FAKE_MODEL_KEY
        from app.prompts import PROMPT_VERSIONS

        return f"{self.model}|{PROMPT_VERSIONS['estimation']}|r={self.reasoning or 'default'}"

    # ---------- cache ----------
    def _cache_path(self, h: str) -> Path:
        return self.cache_dir / h[:2] / f"{h}.json"

    def _cache_get(self, h: str) -> Any | None:
        p = self._cache_path(h)
        return json.loads(p.read_text()) if p.exists() else None

    def _cache_put(self, h: str, purpose: str, value: Any) -> None:
        p = self._cache_path(h)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"purpose": purpose, "value": value}, default=str))

    def log_call(self, **kw: Any) -> None:
        kw.setdefault("model_key", self.model_key)
        kw.setdefault("section", budget.current_section())
        try:
            with SessionLocal() as db:
                db.add(LLMCall(**kw))
                db.commit()
        except Exception:  # logging must never break the main flow
            log.exception("failed to log llm call")

    def _require_live(self) -> None:
        if not self.s.openai_api_key or not self._model:
            raise AppError("llm_not_configured", "OPENAI_API_KEY and OPENAI_MODEL must be set for live LLM calls", 503)

    def _chat(self, temperature: float | None, streaming: bool = False, callbacks: list | None = None):
        from langchain_openai import ChatOpenAI

        kw: dict[str, Any] = {"model": self._model, "api_key": self.s.openai_api_key, "max_retries": 0,
                              "timeout": self.s.llm_timeout_s, "streaming": streaming, "stream_usage": True}
        if self.reasoning:
            kw["reasoning_effort"] = self.reasoning
        # Reasoning models reject custom temperature unless reasoning is disabled ("none").
        if temperature is not None and (not self.reasoning or self.reasoning == "none"):
            kw["temperature"] = temperature
        if callbacks:
            kw["callbacks"] = callbacks
        return ChatOpenAI(**kw)

    def cost(self, tin: int, tout: int, cached: int = 0) -> float:
        return budget.cost_usd(self._model, tin, tout, cached)

    # ---------- structured output ----------
    def structured(self, purpose: str, messages: list[tuple[str, str]], schema: type[T], *,
                   prompt_version: str, fake: Callable[[], T], temperature: float = 0.0,
                   sample_idx: int = 0) -> T:
        key = {"model": self.model, "pv": prompt_version, "schema": schema.__name__, "messages": messages,
               "sample": sample_idx, "t": temperature, "r": self.reasoning or None}
        h = _hash(key)
        req = {"purpose": purpose, "messages": [(r, c[:2000]) for r, c in messages]}
        if self.mode == "fake":
            out = fake()
            self.log_call(purpose=purpose, model=self.model, prompt_hash=h, cache_hit=False, request=req,
                          response=out.model_dump(mode="json"))
            return out
        if self.mode in ("replay", "record"):
            cached = self._cache_get(h)
            if cached is not None:
                self.log_call(purpose=purpose, model=self.model, prompt_hash=h, cache_hit=True, request=req)
                return schema.model_validate(cached["value"])
            if self.mode == "replay":
                raise LLMCacheMiss(purpose, h)
        self._require_live()
        budget.check()
        runnable = self._chat(temperature).with_structured_output(schema, include_raw=True)
        t0 = time.monotonic()
        result: dict[str, Any] = self._retry(lambda: runnable.invoke(messages))
        latency = int((time.monotonic() - t0) * 1000)
        tin, tout, cached_t, reasoning_t = _usage(result.get("raw"))
        parsed = result.get("parsed")
        ok = not result.get("parsing_error") and parsed is not None
        self.log_call(purpose=purpose, model=self.model, prompt_hash=h, cache_hit=False, request=req,
                      response=parsed.model_dump(mode="json") if ok else {"error": str(result.get("parsing_error"))[:500]},
                      input_tokens=tin, output_tokens=tout, cached_tokens=cached_t, reasoning_tokens=reasoning_t,
                      latency_ms=latency, cost_usd=self.cost(tin, tout, cached_t))
        if not ok:
            raise AppError("llm_bad_output", f"{purpose}: structured output failed to parse", 502)
        if self.mode == "record":
            self._cache_put(h, purpose, parsed.model_dump(mode="json"))
        return parsed

    def _retry(self, fn: Callable[[], Any], attempts: int = 4) -> Any:
        for i in range(attempts):
            try:
                return fn()
            except budget.BudgetExceeded:
                raise
            except Exception as e:  # network / rate limit
                status = getattr(e, "status_code", None)
                if status in (400, 401, 403, 404) or i == attempts - 1:
                    raise AppError("llm_error", f"LLM call failed: {type(e).__name__}: {str(e)[:300]}", 502) from e
                time.sleep(min(2**i, 10))
        raise RuntimeError("unreachable")

    # ---------- embeddings ----------
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        dim = self.s.embedding_dim
        if self.mode == "fake":
            return [hash_embedding(t, dim) for t in texts]
        out: list[list[float] | None] = [None] * len(texts)
        missing: list[int] = []
        hashes = [_hash({"emb": self.embedding_model, "dim": dim, "t": t}) for t in texts]
        for i, h in enumerate(hashes):
            c = self._cache_get(h) if self.mode != "live" else None
            if c is not None:
                out[i] = c["value"]
            else:
                missing.append(i)
        if len(missing) < len(texts):
            self.log_call(purpose="embedding", model=self.embedding_model, prompt_hash=hashes[0], cache_hit=True,
                          request={"count": len(texts) - len(missing)})
        if missing and self.mode == "replay":
            raise LLMCacheMiss("embedding", hashes[missing[0]])
        if missing:
            self._require_live()
            budget.check()
            from langchain_openai import OpenAIEmbeddings

            emb = OpenAIEmbeddings(model=self.s.openai_embedding_model, api_key=self.s.openai_api_key,
                                   dimensions=dim, max_retries=0)
            t0 = time.monotonic()
            vecs: list[list[float]] = []
            for start in range(0, len(missing), 256):
                batch = missing[start:start + 256]
                vecs += self._retry(lambda b=batch: emb.embed_documents([texts[i] for i in b]))
            tokens = sum(budget.estimate_tokens(texts[i]) for i in missing)  # API usage not exposed by LangChain
            self.log_call(purpose="embedding", model=self.embedding_model, prompt_hash=hashes[missing[0]],
                          cache_hit=False, latency_ms=int((time.monotonic() - t0) * 1000), input_tokens=tokens,
                          request={"count": len(missing), "tokens": "estimated"},
                          cost_usd=budget.cost_usd(self.embedding_model, tokens, 0))
            for i, v in zip(missing, vecs, strict=True):
                out[i] = v
                if self.mode == "record":
                    self._cache_put(hashes[i], "embedding", v)
        return [v for v in out if v is not None]

    def chat_model(self, temperature: float = 0.2):
        self._require_live()
        return self._chat(temperature, streaming=True, callbacks=[UsageCallback(self)])


class UsageCallback(BaseCallbackHandler):
    """Budget check before, cost logging after, every chat-model call made inside the LangChain agent."""

    def __init__(self, gw: LLMGateway):
        self.gw = gw
        self._t0: dict[Any, float] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):  # noqa: ANN001
        budget.check()
        self._t0[run_id] = time.monotonic()

    def on_llm_end(self, response, *, run_id, **kwargs):  # noqa: ANN001
        msg = response.generations[0][0].message if response.generations and response.generations[0] else None
        tin, tout, cached, reasoning = _usage(msg)
        calls = getattr(msg, "tool_calls", None) or []
        self.gw.log_call(purpose="chat_agent", model=self.gw.model, prompt_hash=str(run_id), cache_hit=False,
                         input_tokens=tin, output_tokens=tout, cached_tokens=cached, reasoning_tokens=reasoning,
                         latency_ms=int((time.monotonic() - self._t0.pop(run_id, time.monotonic())) * 1000),
                         cost_usd=self.gw.cost(tin, tout, cached),
                         response={"tool_calls": [{"name": c.get("name"), "args": c.get("args")} for c in calls]})


_default: LLMGateway | None = None
_override: ContextVar[LLMGateway | None] = ContextVar("llm_gateway_override", default=None)


def get_gateway() -> LLMGateway:
    global _default
    o = _override.get()
    if o is not None:
        return o
    if _default is None:
        _default = LLMGateway()
    return _default


@contextmanager
def use_gateway(gw: LLMGateway) -> Iterator[LLMGateway]:
    token = _override.set(gw)
    try:
        yield gw
    finally:
        _override.reset(token)
