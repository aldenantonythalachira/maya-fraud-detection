"""Shared config: calib split carving, recall@FPR, XGBoost params, reasons."""

from __future__ import annotations

import numpy as np
import pandas as pd

from risk_common import (
    ENGLISH_REASONS, FEATURE_COLUMNS, XGB_DEFAULTS, carve_calib, recall_at_fpr, xgb_params,
)


def test_carve_calib_takes_the_later_half_of_val_days():
    df = pd.DataFrame({
        "day": [0, 1, 10, 11, 12, 13, 20],
        "split": ["train", "train", "val", "val", "val", "val", "test"],
    })
    out = carve_calib(df.copy())
    assert out["split"].tolist() == ["train", "train", "val", "val", "calib", "calib", "test"]


def test_carve_calib_leaves_a_single_val_day_alone():
    df = pd.DataFrame({"day": [5, 5], "split": ["val", "val"]})
    assert carve_calib(df.copy())["split"].tolist() == ["val", "val"]


def test_recall_at_fpr_picks_a_threshold_within_the_fpr_budget():
    y = np.array([0] * 100 + [1] * 10)
    score = np.concatenate([np.linspace(0, 0.5, 100), np.linspace(0.4, 1.0, 10)])
    thr, recall, fpr = recall_at_fpr(y, score, 0.05)
    assert fpr <= 0.05
    assert 0 < recall <= 1
    # a fixed threshold is used as-is
    _, r2, f2 = recall_at_fpr(y, score, 0.05, threshold=2.0)
    assert (r2, f2) == (0.0, 0.0)


def test_xgb_params_defaults_and_overrides():
    p = xgb_params(10.0, 7)
    assert p["scale_pos_weight"] == 10.0 and p["random_state"] == 7
    assert all(p[k] == v for k, v in XGB_DEFAULTS.items())
    assert xgb_params(1.0, 0, max_depth=3)["max_depth"] == 3


def test_every_feature_has_an_english_reason():
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))
    for col in FEATURE_COLUMNS:
        assert col in ENGLISH_REASONS
