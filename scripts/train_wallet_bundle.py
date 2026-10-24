"""Source-specific sandbox model on generated causes with disjoint world seeds.

The original batch-data bundle is preserved. This model is exclusively for the
interactive generator distribution, not bank/PaySim traffic. Preset, seed, account
ID and labels are never predictors. Final seeds are opened once after fitting.
"""
import hashlib
import json
import math
import random
import shutil
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import average_precision_score,confusion_matrix,roc_auc_score
from conformal import fit_mondrian,predict_sets,evaluate
from online_features import snapshot,FEATURE_VERSION
from risk_common import FEATURE_COLUMNS,recall_at_fpr
from simulation import generate_world


def frames(seeds):
    rows=[]
    for seed in seeds:
        rng=random.Random(seed+817)
        for preset in ('everyday','investment','probes'):
            w=generate_world(seed,preset)
            if preset=='everyday':
                candidates=[(1,rng.randint(100,8000)*100,0),(3,rng.randint(200,16000)*100,0),
                            (2,rng.randint(18000,25000)*100,0)]
            else:
                candidates=[(4,rng.randint(35000,180000)*100,1)]
            for recipient,amount,y in candidates:
                f=snapshot(w,0,recipient,amount,w['now'])['values']
                rows.append(dict(**f,label=y))
    return pd.DataFrame(rows)


def main():
    assignments=dict(train=range(0,120),val=range(300,340),calib=range(500,580),test=range(1000,1080))
    sets={}
    for split,seeds in assignments.items():
        sets[split]=frames(seeds)
        print(split,len(sets[split]),flush=True)
    tr,va,ca,te=(sets[s] for s in ('train','val','calib','test'))
    m=XGBClassifier(n_estimators=150,max_depth=3,learning_rate=.06,subsample=.9,colsample_bytree=.9,
                    n_jobs=2,tree_method='hist',random_state=42,eval_metric='aucpr',early_stopping_rounds=15)
    m.fit(tr[FEATURE_COLUMNS].astype('float32'),tr.label,eval_set=[(va[FEATURE_COLUMNS].astype('float32'),va.label)],verbose=False)
    pva=m.predict_proba(va[FEATURE_COLUMNS].astype('float32'))[:,1]
    threshold,_,_=recall_at_fpr(va.label.to_numpy(),pva,.01)
    pc=m.predict_proba(ca[FEATURE_COLUMNS].astype('float32'))[:,1]
    qf,qs=fit_mondrian(pc,ca.label.to_numpy(),.01,.10)
    # Frozen final world seeds; no tuning or example re-selection follows this score.
    pt=m.predict_proba(te[FEATURE_COLUMNS].astype('float32'))[:,1]
    matrix=confusion_matrix(te.label,pt>=threshold,labels=[0,1]).tolist()
    report=evaluate(predict_sets(pt,qf,qs),te.label.to_numpy())
    meta=dict(features=FEATURE_COLUMNS,source='generated interactive worlds only',test_auroc=float(roc_auc_score(te.label,pt)),
              test_auprc=float(average_precision_score(te.label,pt)),test_recall_at_1pct_fpr=float((pt[te.label.to_numpy()==1]>=threshold).mean()),
              test_benign_intervention_rate=float((pt[te.label.to_numpy()==0]>=threshold).mean()),
              threshold=float(threshold),confusion_matrix=matrix,best_iteration=int(m.best_iteration),
              splits={k:dict(first_seed=min(v),last_seed=max(v),world_count=len(v),rows=len(sets[k]),positives=int(sets[k].label.sum())) for k,v in assignments.items()},
              limits=['Same synthetic generator family across disjoint seeds','Positive labels authored from generator causes','Not UPI, public-data or real-world accuracy','Source-specific candidate; no universal fraud claim'])
    target=ROOT/'models/wallet';target.mkdir(parents=True,exist_ok=True)
    m.save_model(target/'xgb_model.json')
    (target/'model_meta.json').write_text(json.dumps(meta,indent=2))
    (target/'conformal.json').write_text(json.dumps(dict(method='mondrian-lac',qhat_fine=qf,qhat_scam=qs,alpha_fine=.01,alpha_scam=.10,
                                                      calibration_split='disjoint-world-seeds',test=report),indent=2))
    manifest=dict(schema='maya-bundle-v4',feature_version=FEATURE_VERSION,features=FEATURE_COLUMNS,
                  source='generated-interactive-worlds',files={})
    for name in ('xgb_model.json','conformal.json','model_meta.json'):
        manifest['files'][name]=dict(sha256=hashlib.sha256((target/name).read_bytes()).hexdigest())
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2))
    out=ROOT/'reports/wallet-model.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(**meta,conformal=report,promotion_scope='interactive-sandbox-only; not bank scoring'),indent=2))
    print(json.dumps(dict(**meta,conformal=report),indent=2))


if __name__=='__main__':main()
