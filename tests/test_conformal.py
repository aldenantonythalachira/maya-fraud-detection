"""Mondrian conformal: quantiles, set construction, coverage, file format."""

from __future__ import annotations

import json

import numpy as np
import pytest

from conformal import (
    SET_FINE, SET_NAMES, SET_SCAM, SET_UNSURE, classify, evaluate, fit_mondrian, fit_qhat,
    load_conformal, predict_sets,
)


def test_fit_qhat_is_the_finite_sample_quantile():
    scores = np.arange(1, 101) / 100.0  # 0.01 .. 1.00
    # k = ceil((n + 1) * (1 - alpha)) = ceil(101 * 0.9) = 91 -> 0.91
    assert fit_qhat(scores, 0.10) == pytest.approx(0.91)
    assert fit_qhat(scores, 0.0) == pytest.approx(1.0)  # capped at n


def test_fit_qhat_without_data_admits_everything():
    assert fit_qhat(np.array([]), 0.1) == 1.0


def test_predict_sets_bands():
    qhat_fine, qhat_scam = 0.01, 0.10  # fine if p <= 0.01, scam if p >= 0.90
    p = np.array([0.0, 0.01, 0.5, 0.9, 1.0])
    sets = predict_sets(p, qhat_fine, qhat_scam)
    assert sets.tolist() == [SET_FINE, SET_FINE, SET_UNSURE, SET_SCAM, SET_SCAM]


def test_predict_sets_never_empty_and_both_maps_to_unsure():
    # overlapping bands: p = 0.5 is admitted by both classes
    assert classify(0.5, 0.6, 0.6) == SET_NAMES[SET_UNSURE]
    rng = np.random.default_rng(0)
    for qf, qs in rng.uniform(0, 1, size=(50, 2)):
        sets = predict_sets(rng.uniform(0, 1, 200), qf, qs)
        assert set(np.unique(sets)) <= {SET_FINE, SET_SCAM, SET_UNSURE}


def test_mondrian_meets_per_class_coverage():
    rng = np.random.default_rng(1)

    def sample(n_fine, n_scam):
        p = np.concatenate([rng.beta(1, 30, n_fine), rng.beta(8, 2, n_scam)])
        y = np.concatenate([np.zeros(n_fine, np.int8), np.ones(n_scam, np.int8)])
        return p, y

    p_cal, y_cal = sample(20_000, 400)
    qf, qs = fit_mondrian(p_cal, y_cal, alpha_fine=0.01, alpha_scam=0.10)
    p_te, y_te = sample(20_000, 400)
    rep = evaluate(predict_sets(p_te, qf, qs), y_te)
    assert rep["coverage_fine"] >= 0.98   # target 0.99, sampling slack
    assert rep["coverage_scam"] >= 0.86   # target 0.90, sampling slack (400 scams)


def test_load_conformal_new_and_legacy(tmp_path):
    new = tmp_path / "new.json"
    new.write_text(json.dumps({"qhat_fine": 0.002, "qhat_scam": 0.05}))
    assert load_conformal(new) == (0.002, 0.05)
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"qhat": 0.0002}))
    assert load_conformal(old) == (0.0002, 0.0002)
