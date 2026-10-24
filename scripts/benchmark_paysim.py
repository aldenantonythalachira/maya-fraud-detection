"""Frozen chronological public-data benchmark. Separate task/model from the wallet.

--max-rows selects a chronological prefix and drops the final possibly incomplete
hour. Reports always disclose the subset. Never run the resulting model as UPI scoring.
"""
import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score,confusion_matrix,roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
from conformal import fit_mondrian,predict_sets,evaluate
from paysim_adapter import FEATURES,INPUT,adapt
from risk_common import recall_at_fpr


def run(source,max_rows=None,challenger=False):
    started=time.time()
    raw=pd.read_csv(source,usecols=INPUT,nrows=max_rows)
    if max_rows and len(raw)==max_rows:
        raw=raw[raw.step<raw.step.max()].copy()
    df=adapt(raw)
    frames={s:df[df.split==s] for s in ('train','val','calib','test')}
    for s,d in frames.items():
        if d.isFraud.nunique()<2:raise ValueError(f'{s} lacks both classes; change dataset scope before evaluating, not after inspecting scores')
    tr,va,ca,te=(frames[s] for s in ('train','val','calib','test'))
    candidates={'logistic':make_pipeline(SimpleImputer(),StandardScaler(),LogisticRegression(max_iter=400,class_weight='balanced')),
                'xgboost':XGBClassifier(n_estimators=150,max_depth=4,learning_rate=.08,n_jobs=2,tree_method='hist',random_state=42,eval_metric='aucpr')}
    if challenger:
        candidates['mlp']=make_pipeline(SimpleImputer(),StandardScaler(),MLPClassifier(hidden_layer_sizes=(32,16),max_iter=40,early_stopping=False,random_state=42))
    results={}
    for name,m in candidates.items():
        fit=time.perf_counter();m.fit(tr[FEATURES],tr.isFraud)
        pva=m.predict_proba(va[FEATURES])[:,1]
        threshold,_,_=recall_at_fpr(va.isFraud.to_numpy(),pva,.01)
        p=m.predict_proba(te[FEATURES])[:,1]
        matrix=confusion_matrix(te.isFraud,p>=threshold,labels=[0,1]).tolist()
        tn,fp,fn,tp=np.array(matrix).ravel()
        qf,qs=fit_mondrian(m.predict_proba(ca[FEATURES])[:,1],ca.isFraud.to_numpy(),.01,.10)
        timings=[]
        for i in range(min(100,len(te))):
            before=time.perf_counter();m.predict_proba(te[FEATURES].iloc[[i]]);timings.append((time.perf_counter()-before)*1000)
        results[name]=dict(pr_auc=float(average_precision_score(te.isFraud,p)),auroc=float(roc_auc_score(te.isFraud,p)),
                           recall=float(tp/(tp+fn)),precision=float(tp/max(tp+fp,1)),benign_intervention_rate=float(fp/(fp+tn)),
                           threshold=float(threshold),confusion_matrix=matrix,fit_and_evaluate_seconds=time.perf_counter()-fit,
                           uncertainty=evaluate(predict_sets(p,qf,qs),te.isFraud.to_numpy()),
                           score_only_p95_ms=float(np.percentile(timings,95)))
    h=hashlib.sha256()
    with Path(source).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return dict(dataset='PaySim public synthetic mobile-money; not UPI',source_sha256=h.hexdigest(),
                requested_max_rows=max_rows,actual_rows=len(df),features=FEATURES,
                split_contract='whole chronological hours, 60/15/10/15; no current-hour history',
                splits={s:dict(rows=len(d),positives=int(d.isFraud.sum()),first_step=int(d.step.min()),last_step=int(d.step.max())) for s,d in frames.items()},
                excluded=['isFraud as predictor','isFlaggedFraud','newbalanceOrig','newbalanceDest','raw account IDs','post-transfer differences'],
                opening_balance_assumption='Source opening balances assumed available before transfer; partner availability must be validated',
                baseline_all_legitimate=dict(accuracy=float((te.isFraud==0).mean()),fraud_recall=0),
                candidates=results,hardware=platform.platform(),elapsed_seconds=time.time()-started,
                limits=['Score-only timings are not service capacity','Synthetic source does not validate UPI intent or coercion','No model automatically promoted','No real-world accuracy claim'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default='data/v4/paysim/transactions.csv');p.add_argument('--max-rows',type=int);p.add_argument('--challenger',action='store_true');p.add_argument('--out',default='reports/paysim.json');a=p.parse_args()
    result=run(a.source,a.max_rows,a.challenger)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
