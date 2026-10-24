import json
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient

from product_api import create_app


class FixtureModel:
    """Policy fixture; actual model tests use a separately built artifact bundle."""
    version, calibration_version, ready = 'fixture', 'calibration-fixture', True
    def score(self, values):
        return dict(score=.7, uncertainty='{fine, scam}', contributions=[], base_margin=0)


@pytest.fixture
def product(tmp_path):
    app=create_app(str(tmp_path/'product.sqlite'), FixtureModel(), secret='test-secret'*5)
    yield app
    app.state.service.db.close()


@pytest.fixture
def customer(product):
    with TestClient(product) as c:
        yield c


def post(c,path,body=None,key=None):
    return c.post(path,json=body or {},headers={'Idempotency-Key':key or secrets.token_hex(12)})


def world(c,preset='everyday'):
    r=post(c,'/v1/sandbox/worlds',{'seed':42,'preset':preset})
    assert r.status_code==201,r.text
    return r.json()


def payment(c,wid,recipient=1,amount=10000):
    root=f'/v1/sandbox/worlds/{wid}'
    p=post(c,root+'/intents',{'recipient':recipient,'amount_paise':amount}).json()
    r=post(c,root+f'/intents/{p["id"]}/review')
    assert r.status_code==200,r.text
    return p,r.json()


def test_transfer_receipt_is_durable_conserved_and_idempotent(customer,product):
    w=world(customer); root=f'/v1/sandbox/worlds/{w["id"]}'
    p,r=payment(customer,w['id'])
    body=dict(review_id=r['id'],confirmed=True,authorization='DEMO')
    first=post(customer,root+f'/intents/{p["id"]}/execute',body)
    assert first.status_code==200,first.text
    assert post(customer,root+f'/intents/{p["id"]}/execute',body).json()==first.json()
    after=customer.get(root).json()
    assert after['accounts'][0]['balance_paise']==w['accounts'][0]['balance_paise']-10000
    assert sum(a['balance_paise'] for a in after['accounts'])==sum(a['balance_paise'] for a in w['accounts'])
    assert len(after['transfers'])==1


def test_paired_judge_is_read_only_and_recipient_is_scoped(customer,product):
    w=world(customer); root=f'/v1/sandbox/worlds/{w["id"]}'
    p,r=payment(customer,w['id'])
    grant=post(customer,root+'/pair',{'role':'judge','account':1}).json()
    with TestClient(product) as judge:
        assert post(judge,'/v1/observe/pair',{'code':grant['code']}).status_code==200
        viewed=judge.get('/v1/observe').json()
        assert viewed['reviews'][0]['id']==r['id']
        assert '"text":' not in json.dumps(viewed)
        assert post(judge,root+f'/intents/{p["id"]}/cancel').status_code!=200
        assert post(judge,root+'/pair',{'role':'judge','account':1}).status_code!=200
        assert post(judge,'/v1/observe/pair',{'code':grant['code']}).status_code==403
        assert post(customer,root+'/revoke').status_code==200
        assert judge.get('/v1/observe').status_code==403
    grant=post(customer,root+'/pair',{'role':'recipient','account':1}).json()
    with TestClient(product) as recipient:
        post(recipient,'/v1/observe/pair',{'code':grant['code']})
        result=recipient.get('/v1/observe').json()
        assert result['role']=='recipient' and 'reviews' not in result and 'accounts' not in result
        assert recipient.get('/v1/observe/events').status_code==403


def test_held_payment_cannot_be_edited_into_release_without_checks(customer):
    w=world(customer,'probes');root=f'/v1/sandbox/worlds/{w["id"]}'
    p,r=payment(customer,w['id'],4,20_000_000)
    assert r['decision']['action']=='hold'
    response=post(customer,root+f'/intents/{p["id"]}/execute',dict(review_id=r['id'],confirmed=True,authorization='DEMO'))
    assert response.status_code==409
    assert post(customer,root+'/pair',dict(role='analyst',account=1)).status_code==422
    edited=customer.put(root+f'/intents/{p["id"]}',json=dict(recipient=1,amount_paise=10000))
    assert edited.status_code==200
    assert post(customer,root+f'/intents/{p["id"]}/execute',dict(review_id=r['id'],confirmed=True,authorization='DEMO')).status_code==409


def test_idempotent_creation_is_atomic_and_conflicts(customer,product):
    body={'seed':45,'preset':'everyday'}
    a=post(customer,'/v1/sandbox/worlds',body,key='same')
    b=post(customer,'/v1/sandbox/worlds',body,key='same')
    assert a.json()==b.json()
    assert post(customer,'/v1/sandbox/worlds',{'seed':46},key='same').status_code==409
    assert product.state.service.db.execute('SELECT count(*) FROM sim_world').fetchone()[0]==1


def test_private_canary_rejected_and_derived_check_has_no_fraud_score(customer,product):
    canary='PRIVATE-CANARY-UNIQUE'
    assert post(customer,'/v1/checks',{'text':canary}).status_code==422
    r=post(customer,'/v1/checks',{'direction':'incoming','purpose':'refund','operation':'transfer'})
    assert r.status_code==201
    assert r.json()['score'] is None and r.json()['action']=='nudge'
    # Request validation errors are not stored in any application table.
    assert canary not in '\n'.join(product.state.service.db.iterdump())
    cid=r.json()['id']
    assert customer.delete('/v1/checks/'+cid).status_code==200
    assert customer.get('/v1/checks/'+cid).status_code==404


def test_csrf_operator_partner_and_legacy_routes_are_closed(customer):
    assert customer.post('/v1/sandbox/worlds',json={},headers={'Origin':'https://evil.example','Idempotency-Key':'key'}).status_code==403
    assert post(customer,'/v1/payments',{}).status_code==404
    assert post(customer,'/v1/score',{}).status_code==404
    assert customer.post('/v1/partner/score',json={},headers={'X-Api-Key':'fake'}).status_code==403
    assert customer.post('/v1/operator/worlds/x/review',json={'review_id':'x'},headers={'X-Operator-Key':'fake'}).status_code==403


def test_restart_retains_session_payment_and_atomic_records(tmp_path):
    path=str(tmp_path/'restart.sqlite')
    app=create_app(path,FixtureModel(),secret='persistent-test-secret')
    with TestClient(app) as c:
        w=world(c);cookies=dict(c.cookies)
    app.state.service.db.close()
    other=create_app(path,FixtureModel(),secret='persistent-test-secret')
    try:
        with TestClient(other) as c:
            c.cookies.update(cookies)
            assert c.get('/v1/sandbox/worlds/'+w['id']).status_code==200
    finally:
        other.state.service.db.close()


def test_model_failure_and_overload_never_confirm(customer,product):
    w=world(customer);root=f'/v1/sandbox/worlds/{w["id"]}'
    p=post(customer,root+'/intents',{'recipient':1,'amount_paise':10000}).json()
    product.state.service.model.ready=False
    assert post(customer,root+f'/intents/{p["id"]}/review').status_code==503
    assert not customer.get(root).json()['transfers']


def test_deleted_world_revokes_grants_and_removes_records(customer,product):
    w=world(customer);root=f'/v1/sandbox/worlds/{w["id"]}'
    p,r=payment(customer,w['id'])
    post(customer,root+'/cases',{'review_id':r['id']})
    post(customer,root+'/pair',{'role':'judge','account':1})
    assert customer.delete(root).status_code==200
    for table in ('sim_world','sim_review','sim_ledger','product_pair','product_grant','product_case','product_idempotency'):
        assert product.state.service.db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0


def test_production_configuration_is_required(monkeypatch,tmp_path):
    monkeypatch.setenv('MAYA_ENV','production')
    monkeypatch.delenv('MAYA_SESSION_SECRET',raising=False)
    with pytest.raises(RuntimeError,match='Production requires'):
        create_app(str(tmp_path/'secure.sqlite'),FixtureModel())


def test_removing_context_cannot_clear_hold_on_same_financial_operation(customer,product):
    w=world(customer,'everyday');root=f'/v1/sandbox/worlds/{w["id"]}'
    p=post(customer,root+'/intents',{'recipient':1,'amount_paise':20_000_000,'context':'refund'}).json()
    r=post(customer,root+f'/intents/{p["id"]}/review').json()
    assert r['decision']['action']=='hold'
    customer.put(root+f'/intents/{p["id"]}',json={'recipient':1,'amount_paise':20_000_000,'context':'none'})
    fresh=post(customer,root+f'/intents/{p["id"]}/review').json()
    assert fresh['decision']['action']=='nudge'
    result=post(customer,root+f'/intents/{p["id"]}/execute',{'review_id':fresh['id'],'confirmed':True,'authorization':'DEMO'})
    assert result.status_code==409 and 'held' in result.text


def test_projection_signature_detects_tampering(customer,product):
    import hashlib,hmac
    from payment_review import digest
    w=world(customer);p,r=payment(customer,w['id'])
    expected=r.pop('projection_signature');fingerprint=r.pop('projection_digest')
    assert digest(r)==fingerprint
    assert hmac.compare_digest(expected,hmac.new(('test-secret'*5).encode(),fingerprint.encode(),hashlib.sha256).hexdigest())
    r['amount_paise']+=1
    assert digest(r)!=fingerprint


def test_model_bundle_schema_and_hash_are_enforced(tmp_path):
    from pathlib import Path
    import shutil
    from simulator_service import LiveModel
    source=Path(__file__).resolve().parents[1]/'models/wallet'
    if not source.exists():pytest.skip('Generated sandbox bundle not built')
    for p in source.glob('*.json'):shutil.copy2(p,tmp_path/p.name)
    m=LiveModel(tmp_path/'xgb_model.json',tmp_path/'conformal.json')
    assert m.ready
    conf=tmp_path/'conformal.json'
    c=json.loads(conf.read_text());c['qhat_fine']=.999;conf.write_text(json.dumps(c))
    with pytest.raises(ValueError,match='hash mismatch'):
        LiveModel(tmp_path/'xgb_model.json',conf)


def test_partner_missing_observations_cannot_produce_release(customer,monkeypatch):
    from risk_common import FEATURE_COLUMNS
    monkeypatch.setenv('MAYA_PARTNER_KEY','independent-partner-key-32-characters')
    response=customer.post('/v1/partner/score',json={'features':{k:None for k in FEATURE_COLUMNS},'amount_inr':100},
                           headers={'X-Api-Key':'independent-partner-key-32-characters'})
    assert response.status_code==503 and 'no approval' in response.text
