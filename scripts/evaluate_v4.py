"""Authored event-level robustness kit, separate from held-out model accuracy.

Attacks modify actual prior payment events, then recompute all features. No
scenario name, label or desired verdict is passed to inference.
"""
import copy
import json
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from online_features import snapshot,numeric
from simulator_service import LiveModel,apply_policy
from simulation import generate_world


def run(folder=None):
    import os
    folder=Path(folder or os.getenv('MAYA_MODEL_DIR',str(ROOT/'models/wallet')))
    model=LiveModel(folder/'xgb_model.json',folder/'conformal.json')
    rows=[]
    for seed in range(200,220):
        for kind in ('benign','probes','split_10','fresh_recipient'):
            w=generate_world(seed,'everyday' if kind=='benign' else 'probes')
            recipient=1 if kind=='benign' else 4
            amount=10000 if kind=='benign' else 6_000_000
            if kind=='split_10':
                amount//=10
                for i in range(9):
                    w['events'].append(dict(id=f'attack-split-{i}',kind='payment',sender=0,receiver=4,
                                            amount_paise=amount,event_at=w['now']-100+i,available_at=w['now']-100+i,
                                            provenance='authored split-transfer attack'))
            if kind=='fresh_recipient':
                recipient=79
                w['events']=[e for e in w['events'] if e['kind']!='payment' or recipient not in (e['sender'],e['receiver'])]
            features=snapshot(w,0,recipient,amount,w['now'])
            result=model.score(numeric(features['values']))
            decision,_,_,_=apply_policy(dict(text='',consent=False,amount_paise=amount),features,result)
            rows.append(dict(seed=seed,case=kind,authored_label='benign' if kind=='benign' else 'fraud-intent scenario',
                             score=result['score'],set=result['uncertainty'],action=decision['action']))
    groups={}
    for k in ('benign','probes','split_10','fresh_recipient'):
        part=[r for r in rows if r['case']==k]
        groups[k]=dict(n=len(part),release=sum(r['action']=='release' for r in part),
                       nudge=sum(r['action']=='nudge' for r in part),hold=sum(r['action']=='hold' for r in part))
    return dict(task='authored event-level scenarios, not real-world fraud accuracy',model_version=model.version,
                groups=groups,cases=rows,platform=platform.platform(),
                limits=['Small authored kit; presets represent causes, not universal fraud labels',
                        'Fresh-recipient and split_10 attacks are evaluation-only here',
                        'No human usability/comprehension claims','No tuning on this report'])


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--model-dir');p.add_argument('--out',default='reports/validation.json');a=p.parse_args()
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    report=run(a.model_dir);path.write_text(json.dumps(report,indent=2));print(json.dumps(report['groups'],indent=2))
