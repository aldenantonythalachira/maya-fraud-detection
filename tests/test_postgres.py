"""Mandatory PostgreSQL integration job in CI; opt in locally with MAYA_TEST_DATABASE_URL."""
import os
import secrets
import pytest
from fastapi.testclient import TestClient
from product_api import create_app
from test_product import FixtureModel,post,payment


@pytest.mark.skipif(not os.getenv('MAYA_TEST_DATABASE_URL'),reason='PostgreSQL integration database not configured')
def test_postgres_atomicity_two_connections_pairing_and_restart():
    url=os.environ['MAYA_TEST_DATABASE_URL']
    apps=[create_app(url,FixtureModel(),secret='postgres-test-secret',raise_internal_errors=True) for _ in range(2)]
    clients=[TestClient(a) for a in apps]
    wid=None
    try:
        a,b=clients
        # No fixed ID: parallel test runs may use the same database.
        key=secrets.token_hex(16)
        first=post(a,'/v1/sandbox/worlds',{'seed':42},key=key)
        assert first.status_code==201,first.text
        assert isinstance(first.json()['accounts'][0]['balance_paise'],int)
        wid=first.json()['id'];b.cookies.update(dict(a.cookies))
        second=post(b,'/v1/sandbox/worlds',{'seed':42},key=key)
        assert first.json()==second.json()
        p,r=payment(a,wid)
        body=dict(review_id=r['id'],confirmed=True,authorization='DEMO')
        path=f'/v1/sandbox/worlds/{wid}/intents/{p["id"]}/execute'
        x=post(a,path,body);y=post(b,path,body)
        assert x.status_code==y.status_code==200,(x.text,y.text)
        assert x.json()==y.json()
        state=b.get(f'/v1/sandbox/worlds/{wid}').json()
        assert len(state['transfers'])==1
        grant=post(a,f'/v1/sandbox/worlds/{wid}/pair',{'role':'judge','account':1}).json()
        b.cookies.clear()
        assert post(b,'/v1/observe/pair',{'code':grant['code']}).status_code==200
        assert b.get('/v1/observe').json()['reviews'][0]['id']==r['id']
    finally:
        if wid:clients[0].delete('/v1/sandbox/worlds/'+wid)
        for c in clients:c.close()
        for a in apps:a.state.service.db.close()
