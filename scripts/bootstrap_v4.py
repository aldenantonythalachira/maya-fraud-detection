"""Build an explicitly synthetic, compatible V4 bundle without losing old artifacts."""
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from online_features import FEATURE_VERSION
from risk_common import FEATURE_COLUMNS


def main():
    checkpoint = ROOT / 'data/checkpoints' / str(time.time_ns())
    checkpoint.mkdir(parents=True)
    for p in (ROOT / 'models').glob('*.json'):
        shutil.copy2(p, checkpoint / p.name)
    def run(*args):
        subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
    run('src/journey_generator.py', '--smoke', '--seed', '143')
    run('src/features.py', '--smoke')
    run('src/train_xgb.py', '--features', 'data/smoke/features.csv')
    run('src/conformal.py', '--features', 'data/smoke/features.csv')
    bundle = dict(schema='maya-bundle-v4', feature_version=FEATURE_VERSION,
                  features=FEATURE_COLUMNS, provenance='generated smoke data; not public UPI or real-bank validation',
                  checkpoint=str(checkpoint.relative_to(ROOT)), files={})
    for name in ('xgb_model.json', 'conformal.json', 'model_meta.json'):
        bundle['files'][name] = dict(sha256=hashlib.sha256((ROOT / 'models' / name).read_bytes()).hexdigest())
    (ROOT / 'models/manifest.json').write_text(json.dumps(bundle, indent=2))
    print('V4 bundle ready. Previous artifacts preserved in', checkpoint)


if __name__ == '__main__':
    main()
