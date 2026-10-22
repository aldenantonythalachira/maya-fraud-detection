"""Verify exported review/ledger digests and optionally recompute actual inference.

Digests establish internal consistency, not independent authenticity.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from payment_review import digest
from simulator_service import LiveModel, apply_policy, POLICY_VERSION, INFERENCE_VERSION
from online_features import FEATURE_VERSION, numeric


def verify(bundle, model=None):
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(bundle['schema']=='maya-verification-v1', 'Unsupported bundle')
    require(digest({k:v for k,v in bundle.items() if k!='digest'})==bundle['digest'], 'Bundle digest mismatch')
    r=bundle['review']
    require(digest({k:v for k,v in r.items() if k!='digest'})==r['digest'], 'Review digest mismatch')
    if bundle['transfer']:
        t=bundle['transfer']; rows=bundle['ledger']
        require(t['review_id']==r['id'] and t['payment_id']==r['payment']['id'], 'Transfer binding mismatch')
        require(len(rows)==2 and sum(e['delta'] for e in rows)==0, 'Unbalanced ledger')
        require(sorted((e['account'],e['delta']) for e in rows)==sorted([(0,-t['amount_paise']),(t['recipient'],t['amount_paise'])]), 'Ledger amount mismatch')
    else:
        require(not bundle['ledger'], 'Unsettled review has transfer ledger')
    if model:
        require(r['versions']==dict(model=model.version,calibration=model.calibration_version,features=FEATURE_VERSION,policy=POLICY_VERSION,inference=INFERENCE_VERSION), 'Artifact version mismatch')
        actual=model.score(numeric(r['feature_snapshot']['values']))
        require(actual==r['model'], 'Model result mismatch')
        d,c,x,g=apply_policy(r['payment'],r['feature_snapshot'],actual)
        require((d,c,x,g)==(r['decision'],r['claim'],r['comparison'],r['groups']), 'Policy result mismatch')
    return dict(verified=True, inference_recomputed=bool(model), independent_signature=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bundle',type=Path)
    ap.add_argument('--recompute',action='store_true')
    args=ap.parse_args()
    model=LiveModel(str(ROOT/'models/xgb_model.json'),str(ROOT/'models/conformal.json')) if args.recompute else None
    try:
        print(json.dumps(verify(json.loads(args.bundle.read_text(encoding='utf-8')),model),indent=2))
    except (AssertionError,ValueError,KeyError) as error:
        raise SystemExit(str(error))


if __name__=='__main__':
    main()
