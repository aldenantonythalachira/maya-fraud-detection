"""Phase 4: the Maya Action Policy Engine (the Two-Signal Rule).

Turns a conformal prediction set plus raw features and mocked soft signals into
one of three actions -- release / nudge / hold -- under the hard rule that a hold
requires two independent signals to agree and at least one of them must be a
*hard* signal (Payment History or Receiving Account). Chat / voice / screen-share
are soft only and can never trigger a hold on their own.

Decision table (conformal set -> action):
    {fine}          -> release
    {scam}          -> hold (analyst review when amount > 100,000)
    {fine, scam}    -> hold if (payment-hard AND receiving-hard)
                              or (any hard AND any soft)
                       else nudge

Run:
    python3 src/policy.py --self-test
    python3 src/policy.py --txn-id 2002885 --soft-signals '{"chat_stage": "escalated"}'
    python3 src/policy.py --demo 3 --soft-signals '{"is_screen_shared": true}'
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xgboost as xgb

from conformal import SET_FINE, SET_NAMES, SET_SCAM, SET_UNSURE, classify as conformal_classify
from reasons import make_explainer, native_contrib, shap_matrix, top_reasons
from risk_common import FEATURE_COLUMNS, load_features

# --- hard-rule constants ----------------------------------------------------

PAYMENT_HISTORY_FEATURES = ("n_t", "e_t", "z_t", "pi_t")
RECEIVING_ACCOUNT_FEATURES = ("d_R",)

HOLD_ANALYST_AMOUNT = 100_000.0
AUTO_RELEASE_MINUTES = 60

CHAT_SIGNAL_STAGES = {"escalated", "payment_demand"}


@dataclass(frozen=True)
class Thresholds:
    """Fixed defaults (val-percentile informed), CLI-overridable."""

    n_t: float = 59.0
    e_t: float = 1.0
    z_t: float = 2.6
    pi_t: float = 1.0
    d_r_max: float = 1.0


DEFAULT_THRESHOLDS = Thresholds()

ACTION_RELEASE = "release"
ACTION_NUDGE = "nudge"
ACTION_HOLD = "hold"


def hard_signals(features, thr: Thresholds = DEFAULT_THRESHOLDS) -> dict:
    """One bool per hard trigger. `features` is a Series or a plain mapping."""
    return {
        "n_t": float(features["n_t"]) >= thr.n_t,
        "e_t": float(features["e_t"]) >= thr.e_t,
        "z_t": float(features["z_t"]) >= thr.z_t,
        "pi_t": float(features["pi_t"]) >= thr.pi_t,
        "d_R": float(features["d_R"]) <= thr.d_r_max,
    }


def soft_signals(soft=None) -> dict:
    """Normalize the mocked soft-signal inputs into booleans."""
    soft = soft or {}
    stage = str(soft.get("chat_stage", "none")).lower()
    return {
        "is_screen_shared": bool(soft.get("is_screen_shared", False)),
        "is_voice_active": bool(soft.get("is_voice_active", False)),
        "chat_stage": stage in CHAT_SIGNAL_STAGES,
    }


def decide(
    conf_set: str,
    features,
    soft=None,
    reasons=None,
    amount: float = 0.0,
    thr: Thresholds = DEFAULT_THRESHOLDS,
) -> dict:
    """Pure policy function: no I/O, no model. Returns the 4 contract fields."""
    soft = soft_signals(soft)
    n_soft = sum(soft.values())

    hard = hard_signals(features, thr)
    payment = any(hard[f] for f in PAYMENT_HISTORY_FEATURES)
    receiving = any(hard[f] for f in RECEIVING_ACCOUNT_FEATURES)
    n_hard = int(payment) + int(receiving)

    if conf_set == SET_NAMES[SET_FINE]:
        action = ACTION_RELEASE
    elif conf_set == SET_NAMES[SET_SCAM]:
        action = ACTION_HOLD
    else:  # unsure: {fine, scam}
        if (payment and receiving) or (n_hard >= 1 and n_soft >= 1):
            action = ACTION_HOLD
        else:
            action = ACTION_NUDGE

    is_hold = action == ACTION_HOLD
    return {
        "action": action,
        "reasons": list(reasons or [])[:3],
        "auto_release_minutes": AUTO_RELEASE_MINUTES if is_hold else 0,
        "requires_analyst": bool(is_hold and amount > HOLD_ANALYST_AMOUNT),
    }


# --- I/O plumbing -----------------------------------------------------------


def load_qhat(path: str) -> float:
    payload = json.loads(Path(path).read_text())
    return float(payload["qhat"])


def thresholds_from_args(args) -> Thresholds:
    return Thresholds(
        n_t=args.n_t_threshold,
        e_t=args.e_t_threshold,
        z_t=args.z_t_threshold,
        pi_t=args.pi_t_threshold,
        d_r_max=args.d_r_max,
    )


def active_signals(features, soft, thr: Thresholds) -> dict:
    """Diagnostic view of which signals fired (not part of the return contract)."""
    hard = hard_signals(features, thr)
    soft_norm = soft_signals(soft)
    return {
        "hard": {k: v for k, v in hard.items() if v},
        "soft": {k: v for k, v in soft_norm.items() if v},
    }


def run(args) -> int:
    thr = thresholds_from_args(args)
    if args.self_test:
        return 0 if run_self_test() else 1

    model = xgb.XGBClassifier()
    model.load_model(args.model)
    df = load_features(args.features, columns=FEATURE_COLUMNS + ["amount"])
    qhat = load_qhat(args.conformal)
    soft = json.loads(args.soft_signals) if args.soft_signals else {}

    if args.txn_id is not None:
        sel = df[df["txn_id"] == args.txn_id]
        if sel.empty:
            print(f"[policy] txn_id {args.txn_id} not found")
            return 1
        p = model.predict_proba(sel[FEATURE_COLUMNS])[:, 1]
    elif args.demo:
        p_all = model.predict_proba(df[FEATURE_COLUMNS])[:, 1]
        top = np.argsort(-p_all)[: args.demo]
        sel = df.iloc[top]
        p = p_all[top]
    else:
        print("[policy] provide --txn-id N or --demo K (or --self-test)")
        return 1

    explainer = make_explainer(model)
    X = sel[FEATURE_COLUMNS]

    for j, (_, row) in enumerate(sel.iterrows()):
        conf_set = conformal_classify(float(p[j]), qhat)
        amount = float(args.amount) if args.amount is not None else float(row["amount"])
        try:
            sv = shap_matrix(explainer, X.iloc[[j]])[0]
        except Exception:
            sv = native_contrib(model, X.iloc[[j]])[0]
        reasons = [text for _, _, text in top_reasons(sv)]

        decision = decide(conf_set, row, soft, reasons, amount, thr)
        fired = active_signals(row, soft, thr)

        print(f"txn_id={int(row['txn_id'])} p_scam={float(p[j]):.4f} set={conf_set} "
              f"amount={amount:,.2f}")
        print(f"   hard={fired['hard'] or '{}'} soft={fired['soft'] or '{}'}")
        for text in decision["reasons"]:
            print(f"   - {text}")
        print(f"   decision={json.dumps(decision)}")
    return 0


# --- self-test (the truth table) --------------------------------------------


def run_self_test() -> bool:
    none_feats = {"n_t": 0.0, "e_t": 0.0, "z_t": 0.0, "pi_t": 0.0, "d_R": 3.0}
    pay_feats = {"n_t": 0.0, "e_t": 0.0, "z_t": 3.0, "pi_t": 0.0, "d_R": 3.0}
    rcv_feats = {"n_t": 0.0, "e_t": 0.0, "z_t": 0.0, "pi_t": 0.0, "d_R": 0.0}
    both_feats = {"n_t": 0.0, "e_t": 0.0, "z_t": 3.0, "pi_t": 0.0, "d_R": 0.0}

    fine, scam, unsure = SET_NAMES[SET_FINE], SET_NAMES[SET_SCAM], SET_NAMES[SET_UNSURE]
    chat = {"chat_stage": "escalated"}
    screen = {"is_screen_shared": True}
    soft_off = {"chat_stage": "none"}

    cases = [
        # name, set, features, soft, amount, action, minutes, analyst
        ("fine releases", fine, both_feats, chat, 500_000.0, "release", 0, False),
        ("scam holds small", scam, none_feats, soft_off, 500.0, "hold", 60, False),
        ("scam holds big + analyst", scam, none_feats, soft_off, 150_000.0, "hold", 60, True),
        ("unsure no signals -> nudge", unsure, none_feats, soft_off, 900.0, "nudge", 0, False),
        ("unsure soft only -> nudge", unsure, none_feats, chat, 900.0, "nudge", 0, False),
        ("unsure screen only -> nudge", unsure, none_feats, screen, 900.0, "nudge", 0, False),
        ("unsure 1 hard no soft -> nudge", unsure, pay_feats, soft_off, 900.0, "nudge", 0, False),
        ("unsure 1 rcv no soft -> nudge", unsure, rcv_feats, soft_off, 900.0, "nudge", 0, False),
        ("unsure pay + soft -> hold", unsure, pay_feats, chat, 900.0, "hold", 60, False),
        ("unsure rcv + soft -> hold", unsure, rcv_feats, screen, 900.0, "hold", 60, False),
        ("unsure pay + rcv -> hold", unsure, both_feats, soft_off, 900.0, "hold", 60, False),
        ("unsure pay + rcv big -> analyst", unsure, both_feats, soft_off, 150_000.0, "hold", 60, True),
        ("unsure hold analyst only if >100k", unsure, both_feats, soft_off, 99_999.0, "hold", 60, False),
    ]

    n_pass = 0
    for name, cset, feats, soft, amt, exp_action, exp_min, exp_analyst in cases:
        got = decide(cset, feats, soft, ["r1", "r2", "r3"], amt)
        ok = (
            got["action"] == exp_action
            and got["auto_release_minutes"] == exp_min
            and got["requires_analyst"] == exp_analyst
            and got["reasons"] == ["r1", "r2", "r3"]
        )
        n_pass += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {got['action']} "
              f"min={got['auto_release_minutes']} analyst={got['requires_analyst']}")
        if not ok:
            print(f"   expected action={exp_action} min={exp_min} analyst={exp_analyst}")

    print(f"[policy] self-test {n_pass}/{len(cases)} passed")
    return n_pass == len(cases)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Maya action policy engine (Two-Signal Rule).")
    ap.add_argument("--model", default="models/xgb_model.json")
    ap.add_argument("--features", default="data/features.csv")
    ap.add_argument("--conformal", default="models/conformal.json")
    ap.add_argument("--txn-id", type=int, default=None)
    ap.add_argument("--demo", type=int, default=0)
    ap.add_argument("--amount", type=float, default=None, help="override the txn amount")
    ap.add_argument("--soft-signals", default="", help='JSON, e.g. \'{"is_screen_shared": true}\'')
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--n-t-threshold", type=float, default=DEFAULT_THRESHOLDS.n_t)
    ap.add_argument("--e-t-threshold", type=float, default=DEFAULT_THRESHOLDS.e_t)
    ap.add_argument("--z-t-threshold", type=float, default=DEFAULT_THRESHOLDS.z_t)
    ap.add_argument("--pi-t-threshold", type=float, default=DEFAULT_THRESHOLDS.pi_t)
    ap.add_argument("--d-r-max", type=float, default=DEFAULT_THRESHOLDS.d_r_max)
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
