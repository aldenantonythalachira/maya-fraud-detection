"""Hash the local artifact bundle and its training contract; this is not signing."""
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from online_features import FEATURE_VERSION
from risk_common import FEATURE_COLUMNS


def manifest(directory):
    result = dict(schema='maya-artifact-manifest-v1', python=platform.python_version(),
                  feature_version=FEATURE_VERSION, features=FEATURE_COLUMNS, files={},
                  limitations=['Synthetic data', 'No cryptographic signature', 'No production accuracy claim'])
    for name in ('xgb_model.json','model_meta.json','conformal.json'):
        path=directory/name
        result['files'][name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    meta=json.loads((directory/'model_meta.json').read_text())
    calibration=json.loads((directory/'conformal.json').read_text())
    result.update(validation_contract=meta.get('validation_contract','legacy shared validation; rebuild required'),
                  calibration=calibration, promotion='unapproved local demo artifact')
    return result


if __name__ == '__main__':
    directory=ROOT/'models'
    output=directory/'manifest.json'
    output.write_text(json.dumps(manifest(directory),indent=2),encoding='utf-8')
    print('Wrote',output)
