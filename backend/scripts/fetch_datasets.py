import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasets import mendeley  # noqa: E402

if __name__ == "__main__":
    ok = mendeley.fetch()
    if ok:
        print(json.dumps(mendeley.inspect(), indent=1))
    print("Synthetic data needs no download (see scripts/synthetic_projects.py).")
