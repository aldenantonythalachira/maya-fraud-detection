"""Separate synthetic benchmark: later test days, disjoint tuning/calibration,
whole-type exclusion before feature building, three seeds by default.

This evaluates decisions on recorded attempted transactions, not wallet settlement
or money saved. It never promotes or overwrites the live demo model.
"""
import argparse
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from features import load_inputs, endpoint_features, reported_proximity, combine
from risk_common import FEATURE_COLUMNS, validation_partitions
from conformal import fit_qhat, predict_sets, SET_NAMES, evaluate
from policy import decide
from train_xgb import recall_at_fpr


def interval(successes, total):
    if not total:
        return None
    z=1.96; p=successes/total; denom=1+z*z/total
    center=(p+z*z/(2*total))/denom
    radius=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denom
    return [max(0,center-radius),min(1,center+radius)]


def decision_metrics(frame, actions):
    scam=frame.is_scam.to_numpy()==1
    held=np.asarray(actions)=='hold'; interrupted=np.asarray(actions)!='release'
    honest=~scam
    return dict(rows=len(frame), scam_rows=int(scam.sum()), honest_rows=int(honest.sum()),
                held_scam=int((held&scam).sum()), held_honest=int((held&honest).sum()),
                scam_hold_rate=float(held[scam].mean()) if scam.any() else None,
                scam_hold_rate_95ci=interval(int((held&scam).sum()),int(scam.sum())),
                honest_interruption_rate=float(interrupted[honest].mean()) if honest.any() else None,
                honest_interruption_95ci=interval(int((interrupted&honest).sum()),int(honest.sum())),
                false_hold_rate=float(held[honest].mean()) if honest.any() else None,
                screened_positive_gross_rupees=float(frame.loc[held&scam,'amount'].sum()),
                money_saved=None, accounting='gross screened transfer value may include layering; not fraud savings')


def one(directory, heldout):
    raw=pd.read_csv(directory/'transactions.csv')
    removed=(raw.split!='test') & (raw.scam_type==heldout)
    removed_accounts=set(raw.loc[removed,'sender_id'])|set(raw.loc[removed,'receiver_id'])
    tx=raw.loc[~removed].copy()
    # Remove held-out campaigns from history before computing training features.
    filtered=directory/heldout; filtered.mkdir(exist_ok=True)
    tx.to_csv(filtered/'transactions.csv',index=False)
    labels=pd.read_csv(directory/'labels.csv')
    labels.loc[labels.account_id.isin(removed_accounts),'is_reported']=0
    labels.to_csv(filtered/'labels.csv',index=False)
    edges=tx.groupby(['sender_vpa','receiver_vpa'],sort=False).ts.min().reset_index()
    edges.columns=['src_vpa','dst_vpa','first_ts']
    edges.to_csv(filtered/'graph_edges.csv',index=False)
    t,e,l=load_inputs(str(filtered/'transactions.csv'),str(filtered/'graph_edges.csv'),str(filtered/'labels.csv'))
    count=len(l)
    ds,dr=reported_proximity(t,e,l,count,int(t.day.max())+1,int(t.ts_int.min()))
    business=l.set_index('account_id').role.reindex(np.arange(count)).eq('business').to_numpy()
    f=combine(endpoint_features(t),t,ds,dr,business)
    f=f.merge(tx[['txn_id','scam_type','campaign_id','category']],on='txn_id',validate='one_to_one')
    train=f[f.split=='train']; tuning,calibration=validation_partitions(f)
    # Final evaluation includes only honest rows and the unseen scam type.
    test=f[(f.split=='test') & ((f.is_scam==0)|(f.scam_type==heldout))]
    partitions=dict(train=train,tuning=tuning,calibration=calibration,test=test)
    support={name:dict(rows=len(part),positive=int(part.is_scam.sum()),days=sorted(map(int,part.day.unique()))) for name,part in partitions.items()}
    if any(part.is_scam.nunique()<2 for part in partitions.values()):
        return dict(heldout_type=heldout,status='insufficient class support',support=support)
    assert not any((part.scam_type==heldout).any() for part in (train,tuning,calibration))
    pos=int(train.is_scam.sum())
    model=xgb.XGBClassifier(n_estimators=120,max_depth=4,learning_rate=.08,tree_method='hist',
                            n_jobs=1,random_state=1729,scale_pos_weight=(len(train)-pos)/pos,
                            eval_metric='aucpr',early_stopping_rounds=20)
    model.fit(train[FEATURE_COLUMNS],train.is_scam,eval_set=[(tuning[FEATURE_COLUMNS],tuning.is_scam)],verbose=False)
    tune_p=model.predict_proba(tuning[FEATURE_COLUMNS])[:,1]
    threshold,_,_=recall_at_fpr(tuning.is_scam.to_numpy(),tune_p,.01,None)
    cal_p=model.predict_proba(calibration[FEATURE_COLUMNS])[:,1]
    q=fit_qhat(np.where(calibration.is_scam==1,1-cal_p,cal_p),.1)
    p=model.predict_proba(test[FEATURE_COLUMNS])[:,1]
    sets=predict_sets(p,q)
    actions=[decide(SET_NAMES[int(code)],row,{},[],float(row['amount']))['action']
             for code,row in zip(sets,test.to_dict('records'))]
    baseline=np.where(test.amount.to_numpy()>10000,'hold','release')
    pred=p>=threshold; y=test.is_scam.to_numpy()==1
    # Same-history perturbation; mathematically update amount-dependent features.
    edited=test[FEATURE_COLUMNS].copy()
    for key in ('e_t','e_t_snd','e_t_rcv'):
        edited[key]*=1.1
    for key in ('z_t','z_t_snd','z_t_rcv'):
        edited[key]+=math.log(1.1)
    changed_p=model.predict_proba(edited)[:,1]
    return dict(heldout_type=heldout,status='measured synthetic benchmark',support=support,
                excluded_pretest_rows=int(removed.sum()),report_accounts_suppressed=len(removed_accounts),
                test_auprc=float(average_precision_score(y,p)),test_auroc=float(roc_auc_score(y,p)),
                threshold_from_tuning=float(threshold),recall_at_tuning_threshold=float(pred[y].mean()),
                actual_test_fpr=float(pred[~y].mean()),calibration=evaluate(sets,y.astype(np.int8)),
                policies=dict(maya=decision_metrics(test,actions),amount_rule=decision_metrics(test,baseline)),
                scam_journeys=int(test.loc[y,'campaign_id'].nunique()),
                amount_perturbation=dict(multiplier=1.1,mean_absolute_score_change=float(np.abs(changed_p-p).mean())),
                limitations=['Synthetic simulator', 'Small campaign samples; report support',
                             'No fairness claim', 'No realized fraud savings or intervention efficacy estimate',
                             'Probe/graph policy has no chat/voice signals',
                             'Training reports for accounts touched by excluded campaigns suppressed conservatively'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seeds',default='11,29,47')
    ap.add_argument('--types',default='investment,digital_arrest,sextortion')
    ap.add_argument('--work-dir',default=str(ROOT/'tmp/heldout'))
    ap.add_argument('--out',default=str(ROOT/'data/evaluation-heldout.json'))
    args=ap.parse_args()
    rows=[]
    for seed in map(int,args.seeds.split(',')):
        directory=Path(args.work_dir)/str(seed);directory.mkdir(parents=True,exist_ok=True)
        subprocess.run([sys.executable,str(ROOT/'src/journey_generator.py'),'--smoke','--seed',str(seed),'--out-dir',str(directory)],check=True,cwd=ROOT)
        for kind in args.types.split(','):
            if kind not in ('investment','digital_arrest','sextortion'):
                raise ValueError('Unsupported held-out type')
            row=one(directory,kind);row['seed']=seed;rows.append(row)
            print(seed,kind,row['status'],flush=True)
    report=dict(kind='synthetic unseen-type, later-day benchmark; never live model promotion',
                hardware=platform.platform(),rows=rows,method='fixed hyperparameters; early tuning days, late calibration days, final test days',
                fairness='not assessed: no validated demographic data', savings='not measured; no causal intervention trial')
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print('Wrote',out)


if __name__=='__main__':
    main()
