"""Adaptive attack perturbations follow the features.py formulas."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from evasion import augment, extra_hop, no_probes, split_part, split_parts
from risk_common import FEATURE_COLUMNS

AMOUNT = 200_000.0
MED_SND, MED_RCV = math.log(20_000.0), math.log(50_000.0)  # past-log medians
PAIR24 = 10_000.0


def scam_row() -> pd.DataFrame:
    row = {c: 0.0 for c in FEATURE_COLUMNS}
    z_s, z_r = math.log(AMOUNT) - MED_SND, math.log(AMOUNT) - MED_RCV
    zc_s, zc_r = math.log(AMOUNT + PAIR24) - MED_SND, math.log(AMOUNT + PAIR24) - MED_RCV
    row.update({
        "z_t_snd": z_s, "z_t_rcv": z_r, "z_t": z_s,
        "e_t_snd": 6.0, "e_t_rcv": 0.5, "e_t": 6.0,
        "zc_t_snd": zc_s, "zc_t_rcv": zc_r, "zc_t": zc_s,
        "v_t_snd": 1.0, "v_t_rcv": 1.0, "v_t": 1.0,
        "ptr_t_snd": 0.5, "ptr_t_rcv": 0.9, "ptr_t": 0.9,
        "d_R_snd": 1.0, "d_R_rcv": 0.0, "d_R": 0.0,
        "pi_t_snd": 2.0, "pi_t_rcv": 0.0, "pi_t": 2.0,
    })
    row.update({"amount": AMOUNT, "pair24": PAIR24,
                "in24_snd": 40_000.0, "out24_snd": 20_000.0,
                "in24_rcv": 100_000.0, "out24_rcv": 90_000.0})
    return pd.DataFrame([row])


def test_split_into_one_part_is_identity():
    X = scam_row()
    pd.testing.assert_frame_equal(split_part(X, 1, 1)[FEATURE_COLUMNS], X[FEATURE_COLUMNS],
                                  check_dtype=False)


def test_split_part_formulas():
    X, k = scam_row(), 4
    first, last = split_part(X, k, 1).iloc[0], split_part(X, k, k).iloc[0]
    orig = X.iloc[0]
    assert first["z_t_snd"] == pytest.approx(orig["z_t_snd"] - math.log(k))
    assert first["e_t"] == pytest.approx(orig["e_t"] / k)
    assert last["e_t"] == pytest.approx(min(orig["e_t"] / k, 1.0))
    assert last["v_t"] == orig["v_t"] + (k - 1)
    # by the last part the 24 h pair total is back to the full amount
    assert last["zc_t_snd"] == pytest.approx(orig["zc_t_snd"])
    assert last["zc_t"] == pytest.approx(orig["zc_t"])
    # earlier parts add to sender outflow and receiver inflow
    prior = (k - 1) * AMOUNT / k
    assert last["ptr_t_snd"] == pytest.approx((20_000.0 + prior) / 40_000.0)
    assert last["ptr_t_rcv"] == pytest.approx(90_000.0 / (100_000.0 + prior))
    assert len(split_parts(X, k)) == k


def test_extra_hop_and_no_probes():
    X = scam_row()
    hop = extra_hop(X).iloc[0]
    assert (hop["d_R"], hop["d_R_snd"], hop["d_R_rcv"]) == (1.0, 2.0, 1.0)
    capped = extra_hop(X.assign(d_R=3.0)).iloc[0]
    assert capped["d_R"] == 3.0
    assert (no_probes(X)[["pi_t", "pi_t_snd", "pi_t_rcv"]].to_numpy() == 0).all()
    assert np.isclose(X["pi_t"].iloc[0], 2.0)  # inputs are not mutated


def test_augment_weights_each_attack_family_to_one():
    X = pd.concat([scam_row(), scam_row()], ignore_index=True)
    rows, w = augment(X, ("split_2", "split_4", "extra_hop"))
    assert len(rows) == len(w) == 2 * (2 + 4 + 1)
    # per original scam: each of the 3 attacks contributes total weight 1
    assert w.sum() == pytest.approx(2 * 3)
