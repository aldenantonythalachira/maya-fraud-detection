"""Re-pick the four demo scenarios' source transactions for the current model.

The demo scenarios (src/scenario_features.py) use the features of real
test-split transactions, chosen so each one shows a branch of the Two-Signal
Rule under the trained model:

  normal      legit, model says {fine}, d_R = 3, amount near Rs 40k       -> release
  investment  scam,  model says {scam}, amount near Rs 2L                  -> hold + analyst
  police      scam,  model unsure, only the receiving-account group fires,
              amount < Rs 1L (the screen-share soft signal makes it hold)   -> hold
  unclear     model unsure, no hard signal, at most 5 same-day payments to
              the payee (a one-off purchase), amount near Rs 5k (the voice
              call soft signal alone can only nudge)                       -> nudge

After a retrain, run this, paste the printed rows and hash into
src/scenario_features.py, and the strict scenario tests run again.

Run:  python scripts/pick_scenarios.py [--features data/features.csv] [--model models/xgb_model.json]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import xgboost as xgb  # noqa: E402

from conformal import SET_FINE, SET_SCAM, SET_UNSURE, load_conformal, predict_sets  # noqa: E402
from policy import DEFAULT_THRESHOLDS as T  # noqa: E402
from risk_common import FEATURE_COLUMNS, load_features  # noqa: E402
from scenario_features import BASES  # noqa: E402


def nearest(df: pd.DataFrame, amount: float) -> pd.Series | None:
    if df.empty:
        return None
    return df.assign(_d=(df["amount"] - amount).abs()).sort_values("_d").iloc[0]


def row_tuple(r: pd.Series, side: str) -> str:
    return "(" + ", ".join(f"{float(r[b + side]):.4f}" for b in BASES) + ")"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--features", default=str(ROOT / "data" / "features.csv"))
    ap.add_argument("--model", default=str(ROOT / "models" / "xgb_model.json"))
    ap.add_argument("--conformal", default=str(ROOT / "models" / "conformal.json"))
    args = ap.parse_args(argv)

    model = xgb.XGBClassifier()
    model.load_model(args.model)
    qhats = load_conformal(args.conformal)
    df = load_features(args.features, columns=FEATURE_COLUMNS + ["amount"])
    te = df[df["split"] == "test"].copy()
    te["p"] = model.predict_proba(te[FEATURE_COLUMNS])[:, 1]
    te["set"] = predict_sets(te["p"].to_numpy(), *qhats)
    pay = ((te.n_t >= T.n_t) | (te.e_t >= T.e_t) | (te.z_t >= T.z_t) | (te.zc_t >= T.zc_t)
           | (te.pi_t >= T.pi_t))
    rcv = te.d_R <= T.d_r_max
    scam, legit = te.is_scam == 1, te.is_scam == 0

    picks = {
        "normal": nearest(te[legit & (te.set == SET_FINE) & (te.d_R >= 3)], 40_000),
        # {scam} alone no longer holds (universal safeguard): needs both hard groups
        "investment": nearest(te[scam & (te.set == SET_SCAM) & pay & rcv & (te.amount > 100_000)], 200_000),
        "police": nearest(te[scam & (te.set == SET_UNSURE) & rcv & ~pay & (te.amount < 100_000)], 75_000),
        # a one-off purchase: not many same-day payments to this payee
        "unclear": nearest(te[(te.set == SET_UNSURE) & ~pay & ~rcv & (te.v_t <= 5)], 5_000),
    }
    digest = hashlib.sha256(Path(args.model).read_bytes()).hexdigest()
    missing = [k for k, r in picks.items() if r is None]
    print(f'PICKED_FOR_MODEL_SHA256 = "{digest}"\n')
    for key, r in picks.items():
        if r is None:
            print(f"# {key}: NO CANDIDATE under this model -- adjust the criteria above\n")
            continue
        print(f'# {key}: txn {int(r.txn_id)}  p={r.p:.4f}  is_scam={int(r.is_scam)}')
        print(f'"source_txn": {int(r.txn_id)},')
        print(f'"amount_inr": {float(r.amount):_.2f},')
        print('"features": real_features(')
        for side in ("", "_snd", "_rcv"):
            print(f"    {row_tuple(r, side)},")
        print("),\n")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
