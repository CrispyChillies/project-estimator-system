"""Single entry point for every LLM / embedding call.

Modes (env LLM_MODE):
  live   - call OpenAI
  record - call OpenAI and write responses to data/fixtures/llm_cache
  replay - serve only from cache; raise LLMCacheMiss on a miss
  fake   - deterministic offline heuristics (tests, offline demo without fixtures)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import LLMCall
from app.db.session import SessionLocal

log = logging.getLogger("llm")
T = TypeVar("T", bound=BaseModel)

# Rough USD per 1M tokens; override via env if needed. Only used for the usage card.
PRICE_IN_PER_M = 0.4
PRICE_OUT_PER_M = 1.6


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


class LLMGateway:
    def __init__(self) -> None:
        self.s = get_settings()
        self.mode = self.s.llm_mode
        self.cache_dir: Path = self.s.fixtures_dir / "llm_cache"

    @property
    def model(self) -> str:
        return "fake-heuristic" if self.mode == "fake" else (self.s.openai_model or "unset")

    @property
    def embedding_model(self) -> str:
        return "fake-hash" if self.mode == "fake" else (self.s.openai_embedding_model or "unset")

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

    def _log(self, **kw: Any) -> None:
        try:
            with SessionLocal() as db:
                db.add(LLMCall(**kw))
                db.commit()
        except Exception:  # logging must never break the main flow
            log.exception("failed to log llm call")

    def _require_live(self) -> None:
        if not self.s.openai_api_key or not self.s.openai_model:
            raise AppError("llm_not_configured", "OPENAI_API_KEY and OPENAI_MODEL must be set for live LLM calls", 503)

    # ---------- structured output ----------
    def structured(self, purpose: str, messages: list[tuple[str, str]], schema: type[T], *,
                   prompt_version: str, fake: Callable[[], T], temperature: float = 0.0,
                   sample_idx: int = 0) -> T:
        key = {"model": self.model, "pv": prompt_version, "schema": schema.__name__,
               "messages": messages, "sample": sample_idx, "t": temperature}
        h = _hash(key)
        req = {"purpose": purpose, "messages": [(r, c[:2000]) for r, c in messages]}
        if self.mode == "fake":
            out = fake()
            self._log(purpose=purpose, model=self.model, prompt_hash=h, cache_hit=False, request=req,
                      response=out.model_dump(mode="json"))
            return out
        if self.mode in ("replay", "record", "live"):
            cached = self._cache_get(h) if self.mode != "live" else None
            if cached is not None:
                self._log(purpose=purpose, model=self.model, prompt_hash=h, cache_hit=True, request=req)
                return schema.model_validate(cached["value"])
            if self.mode == "replay":
                raise LLMCacheMiss(purpose, h)
        self._require_live()
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=self.s.openai_model, api_key=self.s.openai_api_key, temperature=temperature,
                         max_retries=0, timeout=120)
        runnable = llm.with_structured_output(schema, include_raw=True)
        t0 = time.monotonic()
        result: dict[str, Any] = self._retry(lambda: runnable.invoke(messages))
        if result.get("parsing_error") or result.get("parsed") is None:
            raise AppError("llm_bad_output", f"{purpose}: structured output failed to parse", 502)
        parsed: T = result["parsed"]
        usage = getattr(result.get("raw"), "usage_metadata", None) or {}
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        self._log(purpose=purpose, model=self.model, prompt_hash=h, cache_hit=False, request=req,
                  response=parsed.model_dump(mode="json"), input_tokens=tin, output_tokens=tout,
                  latency_ms=int((time.monotonic() - t0) * 1000),
                  cost_usd=(tin * PRICE_IN_PER_M + tout * PRICE_OUT_PER_M) / 1e6)
        if self.mode == "record":
            self._cache_put(h, purpose, parsed.model_dump(mode="json"))
        return parsed

    def _retry(self, fn: Callable[[], Any], attempts: int = 4) -> Any:
        for i in range(attempts):
            try:
                return fn()
            except Exception as e:  # network / rate limit
                if i == attempts - 1:
                    raise AppError("llm_error", f"LLM call failed: {type(e).__name__}", 502) from e
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
        hashes = [_hash({"emb": self.embedding_model, "t": t}) for t in texts]
        for i, h in enumerate(hashes):
            c = self._cache_get(h) if self.mode != "live" else None
            if c is not None:
                out[i] = c["value"]
            else:
                missing.append(i)
        if missing and self.mode == "replay":
            raise LLMCacheMiss("embedding", hashes[missing[0]])
        if missing:
            self._require_live()
            from langchain_openai import OpenAIEmbeddings

            emb = OpenAIEmbeddings(model=self.s.openai_embedding_model, api_key=self.s.openai_api_key,
                                   dimensions=dim)
            t0 = time.monotonic()
            vecs = self._retry(lambda: emb.embed_documents([texts[i] for i in missing]))
            self._log(purpose="embedding", model=self.embedding_model, prompt_hash=hashes[missing[0]],
                      cache_hit=False, latency_ms=int((time.monotonic() - t0) * 1000),
                      input_tokens=sum(len(texts[i]) // 4 for i in missing),
                      request={"count": len(missing)})
            for i, v in zip(missing, vecs, strict=True):
                out[i] = v
                if self.mode == "record":
                    self._cache_put(hashes[i], "embedding", v)
        return [v for v in out if v is not None]

    def chat_model(self, temperature: float = 0.2):
        self._require_live()
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=self.s.openai_model, api_key=self.s.openai_api_key,
                          temperature=temperature, streaming=True)


_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
