import numpy as np
import pandas as pd
import pytest
from paysim_adapter import INPUT,FEATURES,adapt


def data():
    return pd.DataFrame([dict(step=i,type='TRANSFER',amount=10+i,nameOrig='a',oldbalanceOrg=1000,nameDest='b',oldbalanceDest=200,isFraud=i%2) for i in range(1,21)])


def test_labels_future_balances_and_ids_cannot_be_features():
    raw=data();raw['newbalanceOrig']=np.arange(len(raw));raw['isFlaggedFraud']=raw.isFraud
    prepared=adapt(raw)
    assert set(prepared)==set(FEATURES+['step','split','isFraud'])
    assert not {'nameOrig','nameDest','newbalanceOrig','isFlaggedFraud'} & set(FEATURES)


def test_same_hour_is_never_history_and_labels_do_not_change_features():
    raw=data();raw.loc[1,'step']=1
    prepared=adapt(raw)
    assert prepared.loc[prepared.step==1,'sender_prior_count'].eq(0).all()
    raw['isFraud']=1-raw.isFraud
    pd.testing.assert_frame_equal(prepared[FEATURES],adapt(raw)[FEATURES])
    for earlier,later in zip(['train','val','calib'],['val','calib','test']):
        assert prepared.loc[prepared.split==earlier,'step'].max()<prepared.loc[prepared.split==later,'step'].min()


def test_past_history_changes_actual_features():
    raw=data();a=adapt(raw)
    raw.loc[0,'amount']=500
    b=adapt(raw)
    assert a.loc[1,'sender_prior_total']!=b.loc[1,'sender_prior_total']
    assert a.loc[0,'sender_prior_total']==b.loc[0,'sender_prior_total']==0
