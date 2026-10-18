import copy

import pytest

from app.datasets.synthetic import generate
from app.services.backtest import ESTIMATORS, metrics, predict, run_backtest_core, splits
from app.services.settings import LearningParams
from tests.helpers import to_records

P = LearningParams()


@pytest.fixture(scope="module")
def recs():
    return to_records(generate(n=12, seed=3))


@pytest.mark.parametrize("est", ESTIMATORS)
def test_held_out_project_cannot_influence_its_own_prediction(recs, est):
    target, train = recs[0], recs[1:]
    before, proj_before = predict(target, train, est, P, draws=1000)
    poisoned = copy.deepcopy(target)
    for t in poisoned.tasks:
        if t.final_min is not None:
            t.final_min, t.final_max = t.final_min * 7, t.final_max * 7
    # Actuals are the evaluation label; predictions must not change if we poison the edits.
    after, proj_after = predict(poisoned, train, est, P, draws=1000)
    assert [x.p50 for x in before] == pytest.approx([x.p50 for x in after])
    assert proj_before.p50 == pytest.approx(proj_after.p50)
    # And the target never enters training: poisoning *its* actuals must leave other folds untouched.
    poisoned2 = copy.deepcopy(target)
    for t in poisoned2.tasks:
        if t.actual:
            t.actual *= 10
    other = recs[1]
    rest = [r for r in recs if r.id != other.id]
    rest_poisoned = [poisoned2 if r.id == target.id else r for r in rest]
    a, _ = predict(other, [r for r in rest if r.id != target.id], est, P, draws=1000)
    b, _ = predict(other, [r for r in rest_poisoned if r.id != target.id], est, P, draws=1000)
    assert [x.p50 for x in a] == pytest.approx([x.p50 for x in b])


def test_target_in_train_is_rejected(recs):
    with pytest.raises(AssertionError):
        predict(recs[0], recs, "E4_calibrated_full", P)


def test_loo_splits_exclude_target(recs):
    for target, train in splits(recs, "loo"):
        assert target.id not in {r.id for r in train}
    chrono = splits(recs, "chronological")
    for target, train in chrono:
        assert all((r.date or target.date) <= target.date for r in train)


def test_learning_beats_raw_llm_on_planted_bias(recs):
    out = run_backtest_core(recs, P, "loo", with_curve=False)
    est = out["summary"]["estimators"]
    full, raw = est["E4_calibrated_full"], est["E1_raw_llm"]
    assert full["project"]["MdAPE"] < raw["project"]["MdAPE"]
    assert full["project"]["coverage_p80"] > raw["project"]["coverage_p80"]
    assert abs(full["task"]["bias"]) < abs(raw["task"]["bias"])
    assert full["task"]["coverage_p80"] > raw["task"]["coverage_p80"]
    assert out["summary"]["small_sample"] is True


def test_calibration_without_analogs_improves_task_error(recs):
    # On synthetic data the raw LLM already encodes project size, so analogs (other projects' absolute hours)
    # add noise at task level; calibration alone must still beat raw. See docs/DECISIONS.md.
    est = run_backtest_core(recs, P.model_copy(update={"w_max": 0.0}), "loo", with_curve=False)["summary"]["estimators"]
    assert est["E4_calibrated_full"]["task"]["MdAPE"] < est["E1_raw_llm"]["task"]["MdAPE"]


def test_metrics_basic():
    from app.services.backtest import Pred

    m = metrics([Pred(None, 10, 12, 8, 13, 10), Pred(None, 15, 18, 12, 20, 10)])
    assert m["MdAPE"] == pytest.approx(25)
    assert m["PRED25"] == 0.5
    assert m["coverage_p80"] == 1.0
