import pytest

from app.core.config import get_settings
from app.llm import budget


class FakeLedger:
    def __init__(self) -> None:
        self.spent = 0.0

    def __call__(self) -> float:
        return self.spent


@pytest.fixture
def ledger(monkeypatch):
    led = FakeLedger()
    monkeypatch.setattr(budget, "spend_fn", led)
    monkeypatch.setattr(get_settings(), "llm_budget_usd", 1.0)
    return led


TABLE = {"m": {"input": 1.0, "cached": 0.1, "output": 10.0}}


def test_cost_counts_cached_and_output_tokens():
    # 1M input of which 0.5M cached, 0.1M output (reasoning included)
    assert budget.cost_usd("m", 1_000_000, 100_000, 500_000, TABLE) == pytest.approx(0.5 + 0.05 + 1.0)


def test_unknown_model_price_is_an_error():
    with pytest.raises(budget.UnknownPrice):
        budget.cost_usd("nope", 1, 1, table=TABLE)


def test_global_cap(ledger):
    budget.check()
    ledger.spent = 0.99
    budget.check()
    with pytest.raises(budget.BudgetExceeded):
        budget.check(estimated=0.02)
    ledger.spent = 1.0
    with pytest.raises(budget.BudgetExceeded):
        budget.check()


def test_section_budget_is_relative_to_section_start(ledger):
    ledger.spent = 0.5
    with budget.budget("bakeoff", 0.2) as sec:
        assert budget.current_section() == "bakeoff" and sec.start == 0.5
        ledger.spent = 0.69
        budget.check()
        assert budget.section_spent() == pytest.approx(0.19)
        ledger.spent = 0.7
        with pytest.raises(budget.BudgetExceeded) as e:
            budget.check()
        assert "bakeoff" in e.value.message
    assert budget.current_section() is None
    budget.check()  # outside the section only the global cap applies


def test_nested_sections_all_enforced(ledger):
    with budget.budget("outer", 0.15):
        with budget.budget("inner", 0.1):
            ledger.spent = 0.1
            with pytest.raises(budget.BudgetExceeded) as e:
                budget.check()
            assert "inner" in e.value.message
        budget.check()
        with budget.budget("inner2", 0.5):
            ledger.spent = 0.15
            with pytest.raises(budget.BudgetExceeded) as e:
                budget.check()
            assert "outer" in e.value.message


def test_live_call_refused_before_network_when_over_budget(ledger, monkeypatch):
    from app.agents.schemas import LessonsResult
    from app.llm.gateway import LLMGateway

    gw = LLMGateway(model="gpt-6-luna", mode="live")
    monkeypatch.setattr(gw.s, "openai_api_key", "test-key-not-real")
    ledger.spent = 1.0

    def boom(*a, **k):
        raise AssertionError("network must not be touched")

    monkeypatch.setattr(gw, "_chat", boom)
    with pytest.raises(budget.BudgetExceeded):
        gw.structured("x", [("user", "hi")], LessonsResult, prompt_version="v", fake=lambda: LessonsResult(rules=[]))
