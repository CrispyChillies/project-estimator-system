import math
import random

import pytest

from app.services.calibration import (
    Analog,
    Sample,
    analog_estimate,
    blend,
    build_stats,
    calibrate,
    impact_score,
    predict_task,
    shrink,
    task_range,
    weighted_median,
)
from app.services.settings import LearningParams

P = LearningParams()


def test_shrink_formula():
    assert shrink(0, 1.0, 0.2, 5) == pytest.approx(0.2)
    assert shrink(5, 1.0, 0.0, 5) == pytest.approx(0.5)
    assert shrink(1000, 1.0, 0.0, 5) == pytest.approx(1.0, abs=0.01)


def test_hierarchy_global_then_category():
    samples = [Sample(0.3, "integration_3rd_party", "p1")] * 4 + [Sample(-0.1, "crud_admin", "p1")] * 6
    st = build_stats(samples, "edit", P)
    g = st[("global", "global")]
    n, k = 10, P.shrink_k
    assert g.mean == pytest.approx((4 * 0.3 + 6 * -0.1) / 10)
    assert g.shrunk_mean == pytest.approx(n * g.mean / (n + k))
    c = st[("category", "integration_3rd_party")]
    assert c.shrunk_mean == pytest.approx((4 * 0.3 + k * g.shrunk_mean) / (4 + k))
    assert g.shrunk_var == pytest.approx((n * g.var + k * P.default_sigma2) / (n + k))


def test_recompute_is_idempotent_and_order_invariant():
    rng = random.Random(1)
    samples = [Sample(rng.gauss(0.2, 0.3), rng.choice(["a", "b", "c"]), f"p{i % 4}", rng.choice(["u1", "u2"]))
               for i in range(80)]
    s1 = build_stats(samples, "edit", P)
    shuffled = samples[:]
    rng.shuffle(shuffled)
    s2 = build_stats(shuffled, "edit", P)
    assert s1.keys() == s2.keys()
    for k in s1:
        assert s1[k].shrunk_mean == pytest.approx(s2[k].shrunk_mean)
        assert s1[k].shrunk_var == pytest.approx(s2[k].shrunk_var)
        assert s1[k].n == s2[k].n


def test_cold_start_is_identity():
    cal = calibrate("auth", None, {}, {}, P)
    assert cal.factor == 1.0
    assert cal.sigma2 == pytest.approx(P.default_sigma2)
    pred = predict_task(10, 20, "auth", None, [], {}, {}, P)
    assert pred.mid == pytest.approx(15)


def test_edit_layer_is_prior_for_actual_layer():
    edit = build_stats([Sample(0.2, "x", "p")] * 50, "edit", P)
    actual0 = {}
    assert calibrate("x", None, edit, actual0, P).mu == pytest.approx(edit[("category", "x")].shrunk_mean)
    actual = build_stats([Sample(0.5, "x", "p")] * 40, "actual", P)
    cal = calibrate("x", None, edit, actual, P)
    mu_e = edit[("category", "x")].shrunk_mean
    assert cal.mu == pytest.approx((40 * 0.5 + P.actual_prior_k * mu_e) / (40 + P.actual_prior_k))
    assert cal.n_actual == 40


def test_author_scope_needs_enough_history():
    few = build_stats([Sample(0.5, "x", "p", "alice")] * 2 + [Sample(0.0, "x", "p", "bob")] * 20, "edit", P)
    assert calibrate("x", "alice", few, {}, P).scope_used.startswith("edit:category:")
    many = build_stats([Sample(0.5, "x", "p", "alice")] * 10 + [Sample(0.0, "x", "p", "bob")] * 20, "edit", P)
    assert "category_author" in calibrate("x", "alice", many, {}, P).scope_used


def test_analog_blend_weight_and_threshold():
    analogs = [Analog(str(i), "p", "P", "t", sim, 10, 20, None) for i, sim in enumerate([0.9, 0.8, 0.5])]
    a_mid, used = analog_estimate(analogs, P)
    assert len(used) == 2 and a_mid == 20
    mid_, w = blend(10, a_mid, len(used), P)
    assert w == pytest.approx(0.24)
    assert mid_ == pytest.approx(math.exp(0.76 * math.log(10) + 0.24 * math.log(20)))
    _, w_max = blend(10, 20, 100, P)
    assert w_max == P.w_max


def test_actual_preferred_over_final_in_analogs():
    a = Analog("1", "p", "P", "t", 0.9, 10, 20, 30)
    assert a.reference == 30


def test_weighted_median():
    assert weighted_median([1, 2, 100], [1, 1, 5]) == 100
    assert weighted_median([1, 2, 3], [1, 1, 1]) == 2


def test_range_clamps_and_rounding():
    lo, hi = task_range(0.3, 2.0, P)
    assert lo >= P.min_task_hours
    assert hi <= 0.3 * P.max_range_multiple
    lo, hi = task_range(10, 0.3, P)
    assert lo * 2 == int(lo * 2) and hi * 2 == int(hi * 2)
    assert lo < 10 < hi


def test_calibration_applied_to_raw_before_analog_blend():
    edit = build_stats([Sample(math.log(1.5), "x", "p")] * 1000, "edit", P)
    analogs = [Analog(str(i), "p", "P", "t", 0.95, None, 30, None) for i in range(5)]
    pred = predict_task(10, 10, "x", None, analogs, edit, {}, P)
    cal_mid = 10 * pred.calibration.factor
    w = min(P.w_per_analog * 5, P.w_max)
    assert pred.mid == pytest.approx(math.exp((1 - w) * math.log(cal_mid) + w * math.log(30)))


def test_impact_score_peaks_at_half():
    assert impact_score(100, 0.5) == pytest.approx(100)
    assert impact_score(100, 0.0) == 0
    assert impact_score(100, 1.0) == 0
    assert impact_score(100, 0.2) == pytest.approx(64)
