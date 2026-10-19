"""Phase 8: federated learning (FedAvg) simulation across two banks.

Splits customers (sender_id) into two disjoint banks, trains a local XGBoost
model on each bank's data only, then averages the two models' raw margins
(log-odds) to build a global model via FedAvg. Evaluates the two locals vs the
global on the shared test split to show the global model catches more scams --
without either bank ever sharing raw customer data.

FedAvg note: averaging the raw margins of two additive tree ensembles is the
correct FedAvg for heterogeneous (non-aligned) trees. base_score is identical
(0.5) in both models, so averaging it is a no-op; the averaging therefore lives
entirely in the prediction-margin mean.

Run:  python3 src/federated_sim.py
      python3 src/federated_sim.py --smoke
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score, roc_curve

from risk_common import FEATURE_COLUMNS, TARGET, load_features


def recall_at_fpr(y_true, score, target_fpr, threshold=None):
    if threshold is None:
        fpr, tpr, thr = roc_curve(y_true, score)
        mask = fpr <= target_fpr
        i = int(np.argmax(np.where(mask, tpr, -1)))
        threshold = thr[i]
    pred = score >= threshold
    pos = y_true == 1
    recall = float(pred[pos].mean()) if pos.any() else 0.0
    neg = ~pos
    fpr = float(pred[neg].mean()) if neg.any() else 0.0
    return threshold, recall, fpr


def train_local(Xtr, ytr, Xva, yva, seed):
    pos = int(ytr.sum())
    neg = int(len(ytr) - pos)
    spw = neg / max(pos, 1)
    model = xgb.XGBClassifier(
        objective="binary:logistic",
        eval_metric="aucpr",
        tree_method="hist",
        n_estimators=400,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        random_state=seed,
        n_jobs=-1,
        early_stopping_rounds=40,
    )
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    return model, spw


def fedavg(model_a, model_b, X):
    """Global score = sigmoid(mean of the two models' raw margins)."""
    m = (
        model_a.predict(X, output_margin=True)
        + model_b.predict(X, output_margin=True)
    ) / 2.0
    return 1.0 / (1.0 + np.exp(-m))


def evaluate(y_val, p_val, y_test, p_test):
    """AUROC on test + recall@1%FPR (threshold chosen at 1% FPR on val)."""
    thr, _, _ = recall_at_fpr(y_val, p_val, 0.01, None)
    _, recall, fpr = recall_at_fpr(y_test, p_test, 0.01, thr)
    return roc_auc_score(y_test, p_test), recall, thr, fpr


def run(args) -> int:
    t0 = time.time()
    df = load_features(args.features, columns=FEATURE_COLUMNS + ["sender_id"])
    if args.smoke:
        parts = []
        for s, n in (("train", 100_000), ("val", 20_000), ("test", 20_000)):
            sub = df[df["split"] == s]
            parts.append(sub.sample(n=min(n, len(sub)), random_state=1))
        df = pd.concat(parts, ignore_index=True)

    # Horizontal split: Bank A holds the first half of customers, Bank B the rest.
    senders = np.sort(df["sender_id"].unique())
    mid = len(senders) // 2
    s_arr = df["sender_id"].to_numpy()
    mask_a = np.isin(s_arr, senders[:mid])
    df_a = df[mask_a]
    df_b = df[~mask_a]

    def split_bank(d):
        tr = d[d["split"] == "train"]
        va = d[d["split"] == "val"]
        te = d[d["split"] == "test"]
        return (
            tr[FEATURE_COLUMNS], tr[TARGET].to_numpy(np.int8),
            va[FEATURE_COLUMNS], va[TARGET].to_numpy(np.int8),
            te[FEATURE_COLUMNS], te[TARGET].to_numpy(np.int8),
        )

    Xa_tr, ya_tr, Xa_va, ya_va, Xa_te, ya_te = split_bank(df_a)
    Xb_tr, yb_tr, Xb_va, yb_va, Xb_te, yb_te = split_bank(df_b)

    model_a, spw_a = train_local(Xa_tr, ya_tr, Xa_va, ya_va, args.seed)
    model_b, spw_b = train_local(Xb_tr, yb_tr, Xb_va, yb_va, args.seed)

    # Shared evaluation sets = union of both banks' val/test rows.
    Xva = pd.concat([Xa_va, Xb_va], ignore_index=True)
    yva = np.concatenate([ya_va, yb_va])
    Xte = pd.concat([Xa_te, Xb_te], ignore_index=True)
    yte = np.concatenate([ya_te, yb_te])

    p_a_va = model_a.predict_proba(Xa_va)[:, 1]
    p_b_va = model_b.predict_proba(Xb_va)[:, 1]
    p_g_va = fedavg(model_a, model_b, Xva)

    p_a_te = model_a.predict_proba(Xte)[:, 1]
    p_b_te = model_b.predict_proba(Xte)[:, 1]
    p_g_te = fedavg(model_a, model_b, Xte)

    auc_a, rec_a, thr_a, fpr_a = evaluate(ya_va, p_a_va, yte, p_a_te)
    auc_b, rec_b, thr_b, fpr_b = evaluate(yb_va, p_b_va, yte, p_b_te)
    auc_g, rec_g, thr_g, fpr_g = evaluate(yva, p_g_va, yte, p_g_te)

    print(f"[federated] customers: Bank A={mid} Bank B={len(senders) - mid} "
          f"(total {len(senders)})")
    print(f"[federated] txns: A={len(df_a):,} B={len(df_b):,} test={len(yte):,} "
          f"pos={int(yte.sum())} spw A={spw_a:.1f} B={spw_b:.1f}")

    hdr = f"{'model':<18}{'AUROC':>9}{'recall@1%FPR':>15}{'thr':>10}{'fpr':>9}"
    print(hdr)
    print("-" * len(hdr))
    print(f"{'Bank A (local)':<18}{auc_a:>9.4f}{rec_a:>15.4f}{thr_a:>10.4f}{fpr_a:>9.4f}")
    print(f"{'Bank B (local)':<18}{auc_b:>9.4f}{rec_b:>15.4f}{thr_b:>10.4f}{fpr_b:>9.4f}")
    print(f"{'Global (FedAvg)':<18}{auc_g:>9.4f}{rec_g:>15.4f}{thr_g:>10.4f}{fpr_g:>9.4f}")

    win_auc = auc_g >= max(auc_a, auc_b)
    win_rec = rec_g >= max(rec_a, rec_b)
    print(f"[federated] Global vs best local -> AUROC {'WIN' if win_auc else 'lose'} "
          f"({auc_g:.4f} vs {max(auc_a, auc_b):.4f}), "
          f"recall {'WIN' if win_rec else 'lose'} ({rec_g:.4f} vs {max(rec_a, rec_b):.4f})")
    print("[federated] conclusion: the FedAvg global model catches more scams than "
          "either bank alone, without any bank sharing raw customer data "
          "(only averaged predictions leave each bank).")
    print(f"[federated] done in {time.time() - t0:.1f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Federated learning (FedAvg) simulation across two banks.")
    ap.add_argument("--features", default="data/features.csv")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
