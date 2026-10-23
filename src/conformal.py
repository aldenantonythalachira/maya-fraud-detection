"""Phase 3: split-conformal wrapper around the XGBoost risk model.

LAC (least-ambiguous-set) nonconformity scores calibrated on the val split give a
marginal (1-alpha) coverage guarantee. The prediction set is one of:
    {fine}, {scam}, or {fine, scam} ("unsure")   -- never empty.

Saves models/conformal.json with q-hat. Run:
    python3 src/conformal.py
    python3 src/conformal.py --txn-id 12345
    python3 src/conformal.py --smoke   (smoke model + data/smoke/features.csv)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import xgboost as xgb

from risk_common import (
    FEATURE_COLUMNS, SMOKE_CONFORMAL, SMOKE_FEATURES, SMOKE_MODEL, TARGET, load_features,
)

SET_FINE, SET_SCAM, SET_UNSURE = 0, 1, 2
SET_NAMES = {SET_FINE: "{fine}", SET_SCAM: "{scam}", SET_UNSURE: "{fine, scam}"}


def fit_qhat(scores: np.ndarray, alpha: float) -> float:
    s = np.sort(scores)
    n = s.size
    k = min(n, int(math.ceil((n + 1) * (1.0 - alpha))))
    return float(s[k - 1])


def predict_sets(p_scam: np.ndarray, qhat: float) -> np.ndarray:
    inc_scam = p_scam >= (1.0 - qhat)
    inc_fine = p_scam <= qhat
    size = inc_scam.astype(np.int8) + inc_fine.astype(np.int8)
    out = np.full(p_scam.shape, SET_UNSURE, dtype=np.int8)
    out[(size == 1) & inc_fine] = SET_FINE
    out[(size == 1) & inc_scam] = SET_SCAM
    return out


def classify(p_scam: float, qhat: float) -> str:
    code = int(predict_sets(np.array([p_scam]), qhat)[0])
    return SET_NAMES[code]


def evaluate(sets: np.ndarray, y: np.ndarray) -> dict:
    scam_eff = (sets != SET_FINE)
    fine_eff = (sets != SET_SCAM)
    covered = np.where(y == 1, scam_eff, fine_eff)
    dist = {SET_NAMES[k]: int((sets == k).sum()) for k in (SET_FINE, SET_SCAM, SET_UNSURE)}
    pos = y == 1
    return {
        "coverage": float(covered.mean()),
        "set_distribution": dist,
        "scam_detection_rate": float(scam_eff[pos].mean()) if pos.any() else 0.0,
        "avg_set_size": float(np.where(sets == SET_UNSURE, 2, 1).mean()),
    }


def run(args) -> None:
    model = xgb.XGBClassifier()
    model.load_model(args.model)
    df = load_features(args.features)

    va = df[df["split"] == "val"]
    te = df[df["split"] == "test"]
    p_va = model.predict_proba(va[FEATURE_COLUMNS])[:, 1]
    p_te = model.predict_proba(te[FEATURE_COLUMNS])[:, 1]
    y_va = va[TARGET].to_numpy(np.int8)
    y_te = te[TARGET].to_numpy(np.int8)

    scores = np.where(y_va == 1, 1.0 - p_va, p_va)
    qhat = fit_qhat(scores, args.alpha)

    sets_te = predict_sets(p_te, qhat)
    rep = evaluate(sets_te, y_te)

    payload = {
        "alpha": args.alpha,
        "target_coverage": 1.0 - args.alpha,
        "qhat": qhat,
        "score": "lac: 1 - p(true class)",
        "calibration_rows": int(len(va)),
        "test": rep,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"[conformal] alpha={args.alpha} qhat={qhat:.6f} (calibrated on {len(va):,} val rows)")
    print(f"[conformal] test coverage={rep['coverage']:.4f} (target {1 - args.alpha:.2f}) "
          f"scam_detection_rate={rep['scam_detection_rate']:.4f} avg_set_size={rep['avg_set_size']:.4f}")
    print(f"[conformal] set distribution: {rep['set_distribution']}")

    if args.txn_id is not None:
        row = df[df["txn_id"] == args.txn_id]
        if row.empty:
            print(f"[conformal] txn_id {args.txn_id} not found")
        else:
            p = float(model.predict_proba(row[FEATURE_COLUMNS])[:, 1][0])
            print(f"[conformal] txn_id={args.txn_id} p_scam={p:.4f} -> {classify(p, qhat)}")
    print(f"[conformal] wrote {out.resolve()}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Conformal prediction sets for the risk model.")
    ap.add_argument("--model", default="models/xgb_model.json")
    ap.add_argument("--features", default="data/features.csv")
    ap.add_argument("--out", default="models/conformal.json")
    ap.add_argument("--alpha", type=float, default=0.10)
    ap.add_argument("--txn-id", type=int, default=None)
    ap.add_argument("--smoke", action="store_true",
                    help="calibrate the train_xgb --smoke model on data/smoke/features.csv")
    args = ap.parse_args(argv)
    if args.smoke:
        args.model = SMOKE_MODEL
        args.features = SMOKE_FEATURES
        args.out = SMOKE_CONFORMAL
    run(args)


if __name__ == "__main__":
    main()
