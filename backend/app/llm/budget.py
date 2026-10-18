"""Live-LLM spend accounting and hard caps.

Spend is the sum of `llm_calls.cost_usd` (cache hits and fake calls cost 0). Every live call checks the
global cap (`LLM_BUDGET_USD`) and the innermost active section budget (`with budget("bakeoff", 1.5)`).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import AppError

# USD per 1M tokens. Verified on https://developers.openai.com/api/docs/pricing (standard tier) on 2026-10-18.
PRICES: dict[str, dict[str, float]] = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "output": 0.50},
    "gpt-6.1-sol": {"input": 2.00, "cached": 0.10, "output": 10.00},
    "text-embedding-3-small": {"input": 0.02, "cached": 0.02, "output": 0.0},
    "text-embedding-3-large": {"input": 0.13, "cached": 0.13, "output": 0.0},
}


class BudgetExceeded(AppError):
    def __init__(self, scope: str, spent: float, limit: float):
        super().__init__("budget_exceeded",
                         f"LLM budget exceeded for {scope}: spent ${spent:.4f} of ${limit:.2f}. "
                         "Raise LLM_BUDGET_USD or the section budget deliberately; no fallback is attempted.",
                         402, {"scope": scope, "spent": spent, "limit": limit})


class UnknownPrice(AppError):
    def __init__(self, model: str):
        super().__init__("unknown_price", f"No price for model '{model}'. Add it to PRICES or LLM_PRICES_JSON.", 500)


def prices() -> dict[str, dict[str, float]]:
    override = get_settings().llm_prices_json
    return {**PRICES, **(json.loads(override) if override else {})}


def cost_usd(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0,
             table: dict[str, dict[str, float]] | None = None) -> float:
    """Reasoning tokens must already be included in output_tokens (they are billed as output)."""
    p = (table or prices()).get(model)
    if p is None:
        raise UnknownPrice(model)
    uncached = max(input_tokens - cached_tokens, 0)
    return (uncached * p["input"] + cached_tokens * p["cached"] + output_tokens * p["output"]) / 1e6


def ledger_path():
    return get_settings().fixtures_dir.parent / "llm_spend.jsonl"


def append_ledger(entry: dict) -> None:
    """Append-only spend ledger outside the DB, so `docker compose down -v` cannot reset the cap."""
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _ledger_spend() -> float:
    p = ledger_path()
    total = 0.0
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                total += float(json.loads(line).get("cost_usd", 0.0))
    return total + unlogged_spend


def _db_spend(section: str | None = None) -> float:
    from app.db.models import LLMCall
    from app.db.session import SessionLocal

    q = select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0))
    if section:
        q = q.where(LLMCall.section == section)
    with SessionLocal() as db:
        return float(db.scalar(q) or 0.0) + unlogged_spend


# Cost of live calls whose llm_calls row could not be written; still counts against the cap.
unlogged_spend = 0.0


def record_unlogged(cost: float) -> None:
    global unlogged_spend
    unlogged_spend += cost


@dataclass
class Section:
    name: str
    limit: float
    start: float


_sections: ContextVar[tuple[Section, ...]] = ContextVar("llm_budget_sections", default=())
EPS = 1e-9
spend_fn: Callable[[], float] = _ledger_spend  # swapped in tests


@contextmanager
def budget(name: str, limit: float) -> Iterator[Section]:
    sec = Section(name, limit, spend_fn())
    token = _sections.set((*_sections.get(), sec))
    try:
        yield sec
    finally:
        _sections.reset(token)


def current_section() -> str | None:
    s = _sections.get()
    return s[-1].name if s else None


def section_spent() -> float:
    s = _sections.get()
    return spend_fn() - s[-1].start if s else 0.0


def check(estimated: float = 0.0) -> None:
    """Raise before a live call if the global cap or ANY active (nested) section budget would be hit."""
    total = spend_fn()
    cap = get_settings().llm_budget_usd
    if total + estimated >= cap - EPS:
        raise BudgetExceeded("session (LLM_BUDGET_USD)", total, cap)
    for s in reversed(_sections.get()):
        if (total - s.start) + estimated >= s.limit - EPS:
            raise BudgetExceeded(f"section '{s.name}'", total - s.start, s.limit)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
