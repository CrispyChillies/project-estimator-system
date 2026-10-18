"""The learning system must recover the biases planted in the synthetic generator."""

import math

import pytest

from app.datasets.synthetic import ACTUAL_BIAS, EDIT_BIAS, generate
from app.services.learning import samples_from_records, stats_from_records, structural_signals
from app.services.settings import LearningParams
from tests.helpers import to_records

P = LearningParams()


@pytest.fixture(scope="module")
def recs():
    return to_records(generate(n=40, seed=7))


@pytest.mark.parametrize("cat", ["integration_3rd_party", "crud_admin", "ml_cv", "data_migration"])
def test_actual_layer_recovers_planted_bias(recs, cat):
    _, actual = stats_from_records(recs, P)
    s = actual[("category", cat)]
    assert s.n >= 15
    # raw sees size**0.5 with size ~ U(0.8, 1.4) => E[ln ratio] gains ~0.5 * E[ln size] ~= 0.04
    expected = math.log(ACTUAL_BIAS[cat]) + 0.04
    assert abs(s.mean - expected) < 2.5 * math.sqrt(s.var / s.n) + 0.02


def test_edit_layer_recovers_pm_ml_bump(recs):
    edit, _ = stats_from_records(recs, P)
    assert math.exp(edit[("category", "ml_cv")].mean) == pytest.approx(EDIT_BIAS["ml_cv"], rel=0.08)


def test_learning_uses_raw_denominator(recs):
    xs = samples_from_records(recs[:1], "actual")
    t = next(t for t in recs[0].tasks if t.raw_mid and t.actual and t.final_mid)
    assert any(math.isclose(s.x, math.log(t.actual / t.raw_mid)) for s in xs)


def test_structural_signals_and_unplanned_share(recs):
    sig = structural_signals(recs)
    sec = next(c for c in sig["categories"] if c["category"] == "security_compliance")
    assert sec["added"] > 0 and sec["missing_task_rate"] > 0
    assert sig["unplanned_share_mean"] == pytest.approx(0.12, abs=0.04)
