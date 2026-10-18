"""Print the synthetic projects and their planted biases (no DB writes)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasets.synthetic import ACTUAL_BIAS, EDIT_BIAS, UNPLANNED_SHARE, generate  # noqa: E402

if __name__ == "__main__":
    projects = generate()
    print(f"{len(projects)} projects, unplanned share ~{UNPLANNED_SHARE:.0%}")
    for c in sorted(ACTUAL_BIAS):
        print(f"  {c:24s} actual/raw={ACTUAL_BIAS[c]:.2f}  final/raw={EDIT_BIAS[c]:.2f}")
    for p in projects:
        print(f"- {p.name}: {len(p.tasks)} tasks, actual {sum(t.actual or 0 for t in p.tasks):.0f} h")
