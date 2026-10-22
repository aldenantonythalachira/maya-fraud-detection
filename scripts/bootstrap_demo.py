"""Build a reproducible small baseline without downloading bank data."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for args in (["src/journey_generator.py", "--smoke", "--out-dir", "data"],
             ["src/features.py", "--days", "30"], ["src/train_xgb.py"], ["src/conformal.py"], ["scripts/model_manifest.py"]):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
print("Smoke baseline ready. These synthetic results are not evidence of real-world accuracy.")
