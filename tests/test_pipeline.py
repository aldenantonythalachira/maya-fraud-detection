"""End-to-end smoke pipeline on a fresh synthetic dataset in a temp dir (~15 s).

generator --smoke -> features (optimized loop must equal the brute force
exactly) -> train_xgb -> conformal -> policy --eval.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import conformal
import features
import journey_generator
import policy
import train_xgb
from risk_common import FEATURE_COLUMNS


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    d = tmp_path_factory.mktemp("smoke")
    journey_generator.main(["--smoke", "--out-dir", str(d)])
    return d


def test_generator_outputs(smoke):
    for name in ("transactions.csv", "graph_edges.csv", "labels.csv"):
        assert (smoke / name).exists()
    tx = pd.read_csv(smoke / "transactions.csv", usecols=["split", "campaign_id", "is_scam"])
    # every scam campaign stays inside one split (the generator's leakage control)
    per_campaign = tx.dropna(subset=["campaign_id"]).groupby("campaign_id")["split"].nunique()
    assert (per_campaign == 1).all()
    assert tx["is_scam"].sum() > 0


@pytest.fixture(scope="module")
def feats(smoke):
    tx, edges, labels = features.load_inputs(
        str(smoke / "transactions.csv"), str(smoke / "graph_edges.csv"), str(smoke / "labels.csv"))
    start_ts = int(tx["ts_int"].min())
    acc_count = int(max(tx["sender_id"].max(), tx["receiver_id"].max())) + 1
    role = labels.set_index("account_id")["role"]
    is_business = role.reindex(np.arange(acc_count)).eq("business").to_numpy()
    ev = features.endpoint_features(tx)
    dR_snd, dR_rcv = features.reported_proximity(tx, edges, labels, acc_count, 30, start_ts)
    out = features.combine(ev, tx, dR_snd, dR_rcv, is_business)
    report = features.validate(tx, out, 30, (0.6, 0.2, 0.2), is_business)
    path = smoke / "features.csv"
    out.to_csv(path, index=False)
    return out, report, path


def test_features_match_brute_force_exactly(feats):
    _, report, _ = feats
    assert report["max_abs_diff_sample"] == {k: 0.0 for k in report["max_abs_diff_sample"]}
    assert set(report["max_abs_diff_sample"]) >= {"n_t", "e_t", "z_t", "pi_t", "g_t",
                                                  "v_t", "zc_t", "ptr_t"}


def test_features_have_every_model_column(feats):
    out, _, _ = feats
    assert set(FEATURE_COLUMNS) <= set(out.columns)
    assert out["d_R"].between(0, 3).all()


def test_train_calibrate_and_evaluate(feats, tmp_path):
    _, _, path = feats
    model, meta, conf = tmp_path / "m.json", tmp_path / "meta.json", tmp_path / "c.json"
    train_xgb.main(["--features", str(path), "--model-out", str(model), "--meta-out", str(meta)])
    m = json.loads(meta.read_text())
    assert m["features"] == FEATURE_COLUMNS
    assert m["calib_rows_held_out"] > 0
    assert m["test_auroc"] > 0.8

    conformal.main(["--model", str(model), "--features", str(path), "--out", str(conf)])
    c = json.loads(conf.read_text())
    assert c["method"] == "mondrian-lac" and c["calibration_split"] == "calib"
    assert 0 <= c["qhat_fine"] <= 1 and 0 <= c["qhat_scam"] <= 1

    assert policy.main(["--model", str(model), "--features", str(path),
                        "--conformal", str(conf), "--eval"]) == 0
