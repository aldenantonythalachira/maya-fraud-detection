"""Open-loop complete-review load test; never counts cached replies as inference.

Use an isolated benchmark server/database, not the presentation wallet. Requests
are scheduled independently of response completion. Queue delay is included.
"""
import argparse
import asyncio
import json
import platform
import statistics
import time
import uuid
from pathlib import Path

import httpx
import numpy as np


async def run(url,rates,seconds):
    async with httpx.AsyncClient(base_url=url,timeout=30,limits=httpx.Limits(max_connections=128,max_keepalive_connections=128)) as c:
        async def post(path,body):
            r=await c.post(path,json=body,headers={'Idempotency-Key':uuid.uuid4().hex})
            r.raise_for_status();return r.json()
        w=await post('/v1/sandbox/worlds',{'seed':987,'preset':'everyday'})
        root='/v1/sandbox/worlds/'+w['id']
        records=[]
        try:
            for rate in rates:
                n=int(rate*seconds)
                intents=[]
                for i in range(n):
                    intents.append((await post(root+'/intents',{'recipient':1+i%3,'amount_paise':10000+i}))['id'])
                # Warm the model and feature path, then time fresh intents.
                await post(root+f'/intents/{intents[0]}/review',{})
                started=time.perf_counter();latencies=[];errors={};statuses={}
                async def one(i,pid):
                    due=started+i/rate
                    await asyncio.sleep(max(0,due-time.perf_counter()))
                    try:
                        r=await c.post(root+f'/intents/{pid}/review',json={})
                        elapsed=(time.perf_counter()-due)*1000
                        statuses[str(r.status_code)]=statuses.get(str(r.status_code),0)+1
                        if r.status_code==200:latencies.append(elapsed)
                        else:errors[str(r.status_code)]=errors.get(str(r.status_code),0)+1
                    except Exception as e:errors[type(e).__name__]=errors.get(type(e).__name__,0)+1
                await asyncio.gather(*(one(i,p) for i,p in enumerate(intents)))
                await asyncio.sleep(max(0,started+seconds-time.perf_counter()))
                total=time.perf_counter()-started
                records.append(dict(offered_rps=rate,scheduled=n,completed=len(latencies),errors=errors,statuses=statuses,
                                    measured_seconds=total,achieved_success_rps=len(latencies)/total,
                                    p50_ms=float(np.percentile(latencies,50)) if latencies else None,
                                    p95_ms=float(np.percentile(latencies,95)) if latencies else None,
                                    p99_ms=float(np.percentile(latencies,99)) if latencies else None))
                print(json.dumps(records[-1]),flush=True)
                if errors or records[-1]['p95_ms']>1000:
                    break
            return dict(hardware=platform.platform(),mode='full HTTP review including source features, model, policy and durable review/event writes',
                        workload='unique pending intents, shared synthetic world: hot-account contention',seconds_per_level=seconds,
                        runs=records,limits=['Short local measurements are not production capacity','No external bank network','Client scheduling delay included','No thresholds bypassed','Rates stop at errors or >1s p95'])
        finally:
            await c.delete(root)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8004');p.add_argument('--rates',default='1,10,25,50,100');p.add_argument('--seconds',type=int,default=10);p.add_argument('--out',default='reports/load.json');a=p.parse_args()
    result=asyncio.run(run(a.url,[int(x) for x in a.rates.split(',')],a.seconds))
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2))
