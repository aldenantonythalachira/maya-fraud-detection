"""Actual TCP/SSE/restart checks; uses only a child server and disposable data."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'models/xgb_model.json').exists(), 'Bootstrap real model before HTTP recovery test')
class HttpRecoveryTests(unittest.TestCase):
    def test_real_http_sse_cursor_and_restart_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            process=None
            def stop():
                if process and process.poll() is None:
                    if os.name == 'nt':
                        # Windows venv python is a launcher: terminate only this
                        # test's owned process tree, including its actual interpreter.
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                    else:
                        process.terminate()
                    process.wait(timeout=10)
            def start():
                nonlocal process
                process=subprocess.Popen([sys.executable,'run_demo.py','--port',str(port),'--database',str(Path(directory)/'wallet.sqlite')],
                                         cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    if process.poll() is not None:
                        self.fail('Child server failed to start')
                    try:
                        if client.get('/api/health').status_code==200:
                            return
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                self.fail('Child server readiness timed out')
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3) as client:
                try:
                    start()
                    w=client.post('/api/worlds',json={'seed':2026,'preset':'everyday'}).json()
                    base='/api/worlds/'+w['id']
                    p=client.post(base+'/intents',json={'recipient':1,'amount_paise':125050}).json()
                    response=client.post(base+'/intents/'+p['id']+'/review',json={})
                    response.raise_for_status();r=response.json()
                    self.assertIn('request;dur=',response.headers['Server-Timing'])
                    self.assertEqual(r['request_id'],response.headers['X-Request-ID'])
                    committed=client.get(base+'/events').json()
                    cursor=committed[-2]['sequence']
                    with client.stream('GET',base+'/stream',headers={'Last-Event-ID':str(cursor)}) as stream:
                        stream.raise_for_status()
                        event=next(line for line in stream.iter_lines() if line.startswith('data: '))
                        self.assertEqual(json.loads(event[6:])['sequence'],committed[-1]['sequence'])
                    body={'review_id':r['id'],'confirmed':True,'authorization':'DEMO'}
                    sent=client.post(base+'/intents/'+p['id']+'/execute',json=body)
                    sent.raise_for_status();transfer=sent.json()
                    stop()
                    with self.assertRaises(httpx.TransportError):
                        client.get('/api/health')
                    start()
                    again=client.post(base+'/intents/'+p['id']+'/execute',json=body)
                    again.raise_for_status()
                    self.assertEqual(transfer,again.json())
                    ledger=client.get(base+'/ledger/'+transfer['id']).json()
                    self.assertEqual(sorted(e['delta'] for e in ledger),[-125050,125050])
                    self.assertEqual(len(client.get(base).json()['transfers']),1)
                finally:
                    stop()
