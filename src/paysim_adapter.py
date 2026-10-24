"""Source-specific pre-transaction PaySim features; no UPI feature fabrication."""
import numpy as np
import pandas as pd

TYPES=('CASH_IN','CASH_OUT','DEBIT','PAYMENT','TRANSFER')
FEATURES=['amount','oldbalanceOrg','oldbalanceDest','sender_prior_count','sender_prior_total',
          'receiver_prior_count','receiver_prior_total']+['type_'+k for k in TYPES]
INPUT=['step','type','amount','nameOrig','oldbalanceOrg','nameDest','oldbalanceDest','isFraud']


def adapt(df):
    if df.empty or not set(INPUT)<=set(df):
        raise ValueError('PaySim input columns missing')
    if not df['type'].isin(TYPES).all() or not df['isFraud'].isin([0,1]).all():
        raise ValueError('Unexpected PaySim type or label')
    data=df[INPUT].sort_values('step',kind='stable').copy()
    numeric=['step','amount','oldbalanceOrg','oldbalanceDest']
    if not np.isfinite(data[numeric]).all().all() or (data[numeric]<0).any().any():
        raise ValueError('Invalid numeric input')
    # Aggregate by complete hour before cumsum; the current hour contributes zero.
    for prefix,account in [('sender','nameOrig'),('receiver','nameDest')]:
        groups=data.groupby([account,'step'],sort=True)['amount'].agg(['size','sum']).reset_index()
        grouped=groups.groupby(account,sort=False)
        groups[prefix+'_prior_count']=grouped['size'].cumsum()-groups['size']
        groups[prefix+'_prior_total']=grouped['sum'].cumsum()-groups['sum']
        lookup=groups.set_index([account,'step'])
        keys=pd.MultiIndex.from_frame(data[[account,'step']])
        for field in (prefix+'_prior_count',prefix+'_prior_total'):
            data[field]=lookup[field].reindex(keys).to_numpy()
    for k in TYPES:data['type_'+k]=(data['type']==k).astype('int8')
    steps=np.sort(data.step.unique())
    if len(steps)<8:raise ValueError('Need at least eight distinct hours for four held-out splits')
    cuts=[max(1,int(len(steps)*f)) for f in (.60,.75,.85)]
    data['split']=np.select([data.step<steps[cuts[0]],data.step<steps[cuts[1]],data.step<steps[cuts[2]]],['train','val','calib'],default='test')
    return data[FEATURES+['step','split','isFraud']].reset_index(drop=True)
