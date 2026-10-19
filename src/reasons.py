"""Phase 3: plain-English SHAP reasons for a scored transaction.

Uses shap.TreeExplainer on the XGBoost booster and returns the top-3 features by
absolute SHAP value, mapped to English via risk_common.ENGLISH_REASONS.

Run:
    python3 src/reasons.py --txn-id 12345
    python3 src/reasons.py --demo 3
"""

from __future__ import annotations

import argparse

import numpy as np
import xgboost as xgb

from risk_common import FEATURE_COLUMNS, TARGET, english_reason, load_features


def make_explainer(model):
    import shap
    return shap.TreeExplainer(model.get_booster())


def shap_matrix(explainer, X) -> np.ndarray:
    sv = explainer.shap_values(X)
    if isinstance(sv, list):
        sv = sv[1] if len(sv) > 1 else sv[0]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        sv = sv[..., 1]
    return sv


def top_reasons(shap_row: np.ndarray, k: int = 3) -> list:
    order = np.argsort(-np.abs(shap_row))[:k]
    return [(FEATURE_COLUMNS[i], float(shap_row[i]), english_reason(FEATURE_COLUMNS[i]))
            for i in order]


def native_contrib(model, X) -> np.ndarray:
    booster = model.get_booster()
    dm = xgb.DMatrix(X, feature_names=FEATURE_COLUMNS)
    contribs = booster.predict(dm, pred_contribs=True)
    return contribs[:, :-1]


def explain_row(model, explainer, X, index: int) -> list:
    row = X.iloc[[index]]
    try:
        sv = shap_matrix(explainer, row)[0]
    except Exception:
        sv = native_contrib(model, row)[0]
    return top_reasons(sv)


def run(args) -> None:
    model = xgb.XGBClassifier()
    model.load_model(args.model)
    df = load_features(args.features)

    if args.txn_id is not None:
        mask = df.index[df["txn_id"] == args.txn_id]
        if len(mask) == 0:
            print(f"[reasons] txn_id {args.txn_id} not found")
            return
        sel = df.loc[mask]
    elif args.index is not None:
        sel = df.iloc[[args.index]]
    else:
        p = model.predict_proba(df[FEATURE_COLUMNS])[:, 1]
        top = np.argsort(-p)[: args.demo]
        sel = df.iloc[top]

    X = sel[FEATURE_COLUMNS]
    p = model.predict_proba(X)[:, 1]
    try:
        sv = shap_matrix(make_explainer(model), X)
    except Exception:
        sv = native_contrib(model, X)

    for j, (_, r) in enumerate(sel.iterrows()):
        print(f"txn_id={int(r['txn_id'])} p_scam={p[j]:.4f} is_scam={int(r[TARGET])} "
              f"split={r['split']}")
        for feat, val, text in top_reasons(sv[j], args.top_k):
            direction = "increases risk" if val > 0 else "decreases risk"
            print(f"   - {feat} ({val:+.4f}, {direction}): {text}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Explain a scored transaction with SHAP.")
    ap.add_argument("--model", default="models/xgb_model.json")
    ap.add_argument("--features", default="data/features.csv")
    ap.add_argument("--txn-id", type=int, default=None)
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--demo", type=int, default=3)
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
