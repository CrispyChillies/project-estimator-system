"""CLI backtest. Never calls the LLM (uses cached raw estimates stored in the DB)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services.backtest import ESTIMATORS, run_backtest  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", choices=["loo", "chronological"], default="loo")
    args = ap.parse_args()
    with SessionLocal() as db:
        run = run_backtest(db, {"protocol": args.protocol}, lambda p, m="": print(f"[{p:4.0%}] {m}"))
        db.commit()
        s = run.summary
        print(f"\nBacktest {run.id} protocol={s['protocol']} projects={s['n_projects']}"
              + ("  ** SMALL SAMPLE: interpret with care **" if s["small_sample"] else ""))
        for level in ("task", "project"):
            print(f"\n{level.upper()} level")
            print(f"{'estimator':22s} {'n':>4s} {'MAPE':>7s} {'MdAPE':>7s} {'PRED25':>7s} {'bias':>7s} {'covP80':>7s} {'width':>6s}  MdAPE 95% CI")
            for e in ESTIMATORS:
                m = s["estimators"][e][level]
                ci = s["estimators"][e][f"{level}_ci"].get("MdAPE", [float("nan")] * 2)
                if not m.get("n"):
                    continue
                print(f"{e:22s} {m['n']:4d} {m['MAPE']:7.1f} {m['MdAPE']:7.1f} {m['PRED25']:7.2f} {m['bias']:7.3f} "
                      f"{m['coverage_p80']:7.2f} {m['interval_width']:6.2f}  [{ci[0]:.1f}, {ci[1]:.1f}]")
        if s.get("learning_curve"):
            print("\nLearning curve (task MdAPE %):")
            for row in s["learning_curve"]:
                print(f"  n_train={row['n_train']:2d}  " + "  ".join(f"{k}={v:.1f}" for k, v in row.items() if k != "n_train"))
