"""Create a local .env without printing credentials or overwriting existing setup."""
import argparse
import re
import secrets
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--domain',required=True)
    a=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?',a.domain) or '.' not in a.domain:
        p.error('Use a hostname without a scheme or path')
    target=Path(__file__).resolve().parents[1]/'.env'
    with target.open('x',encoding='utf-8') as f:
        f.write(f'MAYA_DOMAIN={a.domain}\nMAYA_SESSION_SECRET={secrets.token_hex(32)}\nPOSTGRES_PASSWORD={secrets.token_hex(24)}\nMAYA_OPERATOR_KEY=\nMAYA_PARTNER_KEY=\nMAYA_MAX_INFLIGHT=8\nMAYA_REQUESTS_PER_MINUTE=600\n')
    target.chmod(0o600)
    print('Created private .env. Preserve it across upgrades; no secrets printed.')
