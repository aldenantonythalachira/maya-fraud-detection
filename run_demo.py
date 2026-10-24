"""Start the V4 customer product; use --host 0.0.0.0 behind the HTTPS proxy."""
import argparse
import ipaddress
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))

if __name__ == '__main__':
    import uvicorn
    from product_api import create_app
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    trusted=os.getenv('MAYA_PROXY_IP','127.0.0.1')
    ipaddress.ip_address(trusted)  # An exact address only; wildcard/CIDR trust is refused.
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False,
                forwarded_allow_ips=trusted)
