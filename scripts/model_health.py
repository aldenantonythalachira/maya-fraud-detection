"""Report measured release gates. No automated promotion and no drift guarantee."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def health(directory):
    calibration=json.loads((directory/'conformal.json').read_text())
    model=json.loads((directory/'model_meta.json').read_text())
    coverage=calibration.get('test',{}).get('coverage')
    recall=model.get('test_recall_at_1pct_fpr')
    return dict(schema='maya-model-health-v1',kind='artifact evaluation gates; not live drift detection',
                coverage=dict(value=coverage,target=.9,pass_gate=coverage is not None and coverage>=.9),
                recall=dict(value=recall,target=.7,pass_gate=recall is not None and recall>=.7),
                class_support=calibration.get('test',{}).get('scam_rows'),
                fairness=dict(status='not established',pass_gate=False),
                end_to_end_latency=dict(status='not established at bank load',pass_gate=False),
                deployment='local synthetic research demo only',promotable=False)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--require-promotable',action='store_true')
    args=ap.parse_args()
    report=health(ROOT/'models')
    print(json.dumps(report,indent=2))
    if args.require_promotable and not report['promotable']:
        raise SystemExit(2)
