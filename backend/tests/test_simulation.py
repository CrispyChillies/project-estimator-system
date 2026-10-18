import numpy as np

from app.services.calibration import Sample, build_stats
from app.services.settings import LearningParams
from app.services.simulation import SimTask, simulate

P = LearningParams()
TASKS = [SimTask(10, "a", 0.3), SimTask(20, "b", 0.4), SimTask(5, "a", 0.2)]


def test_seeded_reproducible_and_ordered():
    a = simulate(TASKS, {}, P, seed=1, draws=5000)
    b = simulate(TASKS, {}, P, seed=1, draws=5000)
    assert a == b
    assert a["p10"] < a["p50"] < a["p80"] < a["p90"]
    assert sum(h["count"] for h in a["histogram"]) == 5000


def test_median_close_to_sum_of_medians_without_shared_factor():
    r = simulate(TASKS, {}, P, seed=3, draws=20000, shared_factor=False)
    assert abs(r["p50"] - 35) / 35 < 0.1


def test_shared_factor_widens_interval():
    no = simulate(TASKS * 10, {}, P, seed=2, draws=20000, shared_factor=False)
    yes = simulate(TASKS * 10, {}, P.model_copy(update={"sigma_proj": 0.3}), seed=2, draws=20000, shared_factor=True)
    assert (yes["p90"] - yes["p10"]) > 1.5 * (no["p90"] - no["p10"])


def test_empirical_residual_pool_used_when_enough_data():
    rng = np.random.default_rng(0)
    samples = [Sample(float(x), "a", f"p{i % 6}") for i, x in enumerate(rng.normal(0, 0.5, 40))]
    actual = build_stats(samples, "actual", P)
    r = simulate(TASKS, actual, P, seed=1, draws=2000)
    assert r["empirical_categories"] == ["a"]
    assert r["shared"].startswith("empirical")
