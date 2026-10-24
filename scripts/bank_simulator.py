"""Simulate an HDFC Bank remitter calling Maya's Bank API before NPCI routing.

Usage:
    python3 scripts/bank_simulator.py            # default payload (benign release)
    python3 scripts/bank_simulator.py --hold     # a hold-inducing payload
"""
from __future__ import annotations

import argparse
import json
import urllib.request

API_URL = "http://127.0.0.1:8000/api/score-trace"
API_KEY = "sk_live_maya_enterprise"

BENIGN = {"amount": 40000.0, "d_R": 3, "z_t": 0.4, "e_t": 0.1, "g_t": 0.0,
          "pi_t": 0.0, "is_screen_shared": False, "chat_stage": "none"}
SCAMMY = {"amount": 300000.0, "d_R": 1, "z_t": 3.0, "e_t": 1.5, "g_t": 1.0,
          "pi_t": 0.0, "is_screen_shared": False, "chat_stage": "none"}

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def call_maya(payload: dict) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser(description="HDFC bank simulator -> Maya Bank API")
    ap.add_argument("--hold", action="store_true", help="use a scam-like payload")
    args = ap.parse_args()

    payload = SCAMMY if args.hold else BENIGN
    trace = call_maya(payload)
    action = trace["final_decision"]["action"]

    print(f"[HDFC BANK] txn score-trace -> conformal_set={trace['conformal_set']} "
          f"p_scam features={trace['features']}")
    if action == "hold":
        print(f"{RED}❌ [HDFC BANK] Maya API returned HOLD. Transaction blocked. "
              f"Routing stopped before NPCI.{RESET}")
    elif action == "nudge":
        print(f"{YELLOW}⚠️ [HDFC BANK] Maya API returned NUDGE. "
              f"Warning surfaced to remitter; forwarding to NPCI.{RESET}")
    else:
        print(f"{GREEN}✅ [HDFC BANK] Maya API returned RELEASE. "
              f"Forwarding to NPCI for settlement.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
