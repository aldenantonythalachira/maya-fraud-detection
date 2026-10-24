"""Demo "bank": calls a running Maya API the way a UPI app or bank would.

Start the API first (from the repo root):
    uvicorn api:app --app-dir src
then, in a second terminal:
    python scripts/demo_bank_client.py                 # default http://127.0.0.1:8000
    python scripts/demo_bank_client.py --url http://127.0.0.1:9000 --calls 500

It runs three parts:
  1. Hot-path scoring: the four UI scenarios' real-transaction features go to
     POST /v1/score; prints action, conformal set, score and reasons.
  2. Stateful review: the three payment-review demo scenarios go through
     create -> review -> execute, showing a held payment being refused and a
     nudge that needs explicit confirmation.
  3. Latency: N calls to /v1/score, p50 / p95 / max against the 150 ms SLO.

Standard library only (urllib), so it runs with any Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from demo_scenarios import SCENARIOS as REVIEW_SCENARIOS, scenario  # noqa: E402
from integrations import check_mulehunter  # noqa: E402
from scenario_features import SCENARIO_FEATURES  # noqa: E402

SLO_MS = 150.0


def call(base: str, method: str, path: str, body=None, session: str | None = None):
    """(status, json) for one HTTP request; HTTP errors are returned, not raised."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-Payer-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def score_body(key: str) -> dict:
    sc = SCENARIO_FEATURES[key]
    # The bank looks up its MuleHunter feed for the payee before calling Maya.
    return {"features": sc["features"], "amount_inr": sc["amount_inr"],
            "soft_signals": sc["soft"], "mulehunter_status": check_mulehunter(sc["account_id"]),
            "request_id": f"demo-{key}"}


def part1_scoring(base: str) -> bool:
    print("\n== 1. Hot-path scoring: POST /v1/score ==")
    ok = True
    for key, sc in SCENARIO_FEATURES.items():
        status, r = call(base, "POST", "/v1/score", score_body(key))
        if status != 200:
            print(f"  {key:<11} HTTP {status}: {r}")
            ok = False
            continue
        expected = sc["expected"]
        match = (r["action"], r["requires_analyst"]) == expected
        ok &= match
        print(f"  {key:<11} Rs {sc['amount_inr']:>11,.2f}  {r['action'].upper():<7} "
              f"set={r['conformal_set']:<13} p={r['p_scam']:.4f}  analyst={r['requires_analyst']!s:<5} "
              f"{'ok' if match else 'UNEXPECTED (wanted ' + str(expected) + ')'}  ({r['latency_ms']:.1f} ms)")
        for reason in r["reasons"]:
            print(f"      - {reason}")
    return ok


def part2_review(base: str) -> bool:
    print("\n== 2. Stateful payment review: create -> review -> execute ==")
    ok = True
    session = f"demo-payer-{int(time.time())}"
    for name in REVIEW_SCENARIOS:
        s = scenario(name, time.time())
        st, p = call(base, "POST", "/v1/payments",
                     {"recipient": s["recipient"], "amount_paise": s["amount_paise"]}, session)
        if st != 201:
            print(f"  {name}: create failed HTTP {st}: {p}")
            ok = False
            continue
        st, rv = call(base, "POST", f"/v1/payments/{p['id']}/reviews",
                      {"evidence": s["evidence"], "text": s["text"], "consent": True}, session)
        if st != 201:
            print(f"  {name}: review failed HTTP {st}: {rv}")
            ok = False
            continue
        out = rv["outcome"]
        print(f"  {name:<22} {out['action'].upper():<7} set={out['uncertainty']:<13} "
              f"(synthetic scam={s['scam']})")
        for reason in out["reasons"]:
            print(f"      - {reason}")
        # Try to send it without confirming, then with confirmation.
        st1, r1 = call(base, "POST", f"/v1/payments/{p['id']}/execute",
                       {"review_id": rv["id"], "confirmed": False}, session)
        st2, r2 = call(base, "POST", f"/v1/payments/{p['id']}/execute",
                       {"review_id": rv["id"], "confirmed": True}, session)
        for label, code, body in (("execute unconfirmed", st1, r1), ("execute confirmed", st2, r2)):
            detail = body.get("detail") or f"state={body.get('state')}"
            print(f"      {label:<20} -> HTTP {code}: {detail}")
        if out["action"] == "hold":
            ok &= st2 == 409  # a hold must refuse execution during the hour
        if out["action"] == "nudge":
            ok &= st1 == 409  # a nudge must need explicit confirmation
    st, _ = call(base, "GET", "/v1/payments/does-not-exist", session=session)
    print(f"  unknown payment id   -> HTTP {st}")
    return ok


def part3_latency(base: str, n: int) -> bool:
    print(f"\n== 3. Latency: {n} calls to /v1/score ==")
    body = score_body("investment")
    call(base, "POST", "/v1/score", body)  # warm-up
    wall, server = [], []
    for _ in range(n):
        t0 = time.perf_counter()
        st, r = call(base, "POST", "/v1/score", body)
        wall.append((time.perf_counter() - t0) * 1000.0)
        if st == 200:
            server.append(r["latency_ms"])
    def pct(xs, q):
        return sorted(xs)[min(len(xs) - 1, int(q * len(xs)))]
    for label, xs in (("round trip", wall), ("server-side", server)):
        print(f"  {label:<12} p50 {statistics.median(xs):6.1f} ms   p95 {pct(xs, 0.95):6.1f} ms   "
              f"max {max(xs):6.1f} ms")
    p95 = pct(wall, 0.95)
    print(f"  SLO {SLO_MS:.0f} ms per payment: {'met' if p95 < SLO_MS else 'MISSED'} (round-trip p95)")
    return p95 < SLO_MS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Demo bank client for the Maya API.")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--calls", type=int, default=200)
    args = ap.parse_args(argv)
    base = args.url.rstrip("/")
    try:
        st, health = call(base, "GET", "/v1/health")
    except urllib.error.URLError as err:
        print(f"Cannot reach {base} ({err.reason}). Start it with: uvicorn api:app --app-dir src")
        return 2
    print(f"Maya API at {base}: {health}")
    if health.get("status") != "ok":
        print("API is not ready: build models/ first (see README), then restart it.")
        return 2
    st, info = call(base, "GET", "/v1/model")
    print(f"model {info['model_version'][:12]}... policy {info['policy_version']} "
          f"contract {info['feature_contract']['name']} ({len(info['feature_contract']['columns'])} features)")
    results = [part1_scoring(base), part2_review(base), part3_latency(base, args.calls)]
    print("\nAll checks passed." if all(results) else "\nSome checks did not match (see above).")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
