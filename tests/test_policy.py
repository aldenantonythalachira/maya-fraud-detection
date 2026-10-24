"""The Two-Signal Rule: the universal hold safeguard, the truth table, and
hard-signal edge cases. Independent of model weights.

HoldSafeguardTests is unittest-style; the rest are pytest functions. Run all
of them with `python -m pytest`.
"""

from __future__ import annotations

import itertools
import unittest

import pandas as pd
import pytest

from conformal import SET_NAMES, SET_UNSURE
from policy import DEFAULT_THRESHOLDS, SELF_TEST_CASES, decide, hard_signals, run_self_test

UNSURE = SET_NAMES[SET_UNSURE]


class HoldSafeguardTests(unittest.TestCase):
    def test_all_prediction_sets_and_signal_groups(self):
        for prediction, history, receiving, soft in itertools.product(
            ("{fine}", "{scam}", "{fine, scam}"), (False, True), (False, True), (False, True)
        ):
            with self.subTest(prediction=prediction, history=history, receiving=receiving, soft=soft):
                features = dict(n_t=0, e_t=0, z_t=3 if history else 0, pi_t=0,
                                d_R=0 if receiving else 3)
                result = decide(prediction, features, {"is_screen_shared": soft}, amount=100_001)
                eligible = (history and receiving) or ((history or receiving) and soft)
                expected = "release" if prediction == "{fine}" else "hold" if eligible else "nudge"
                self.assertEqual(result["action"], expected)
                self.assertEqual(result["requires_analyst"], expected == "hold")

    def test_multiple_history_features_are_one_group(self):
        features = dict(n_t=99, e_t=5, z_t=9, pi_t=8, d_R=3)
        self.assertEqual(decide("{scam}", features)["action"], "nudge")

    def test_multiple_soft_signals_cannot_hold(self):
        features = dict(n_t=0, e_t=0, z_t=0, pi_t=0, d_R=3)
        soft = dict(chat_stage="payment_demand", is_screen_shared=True, is_voice_active=True)
        self.assertEqual(decide("{scam}", features, soft)["action"], "nudge")

    def test_analyst_threshold_is_strict(self):
        features = dict(n_t=0, e_t=2, z_t=0, pi_t=0, d_R=0)
        for amount in (99_999, 100_000, 100_001):
            self.assertEqual(decide("{scam}", features, amount=amount)["requires_analyst"], amount > 100_000)

    def test_unknown_prediction_is_rejected(self):
        with self.assertRaises(ValueError):
            decide("typo", dict(n_t=0, e_t=0, z_t=0, pi_t=0, d_R=3))


@pytest.mark.parametrize("case", SELF_TEST_CASES, ids=[c[0] for c in SELF_TEST_CASES])
def test_truth_table(case):
    name, cset, feats, soft, amount, action, minutes, analyst, mulehunter = case
    got = decide(cset, feats, soft, ["r1", "r2", "r3", "r4"], amount, DEFAULT_THRESHOLDS, mulehunter)
    assert got == {
        "action": action,
        "reasons": ["r1", "r2", "r3"],  # capped at 3
        "auto_release_minutes": minutes,
        "requires_analyst": analyst,
    }


def test_self_test_passes():
    assert run_self_test()


def test_zc_falls_back_to_z_when_absent():
    base = {"n_t": 0.0, "e_t": 0.0, "pi_t": 0.0, "d_R": 3.0}
    assert hard_signals({**base, "z_t": 3.0})["zc_t"] is True
    assert hard_signals({**base, "z_t": 0.0})["zc_t"] is False
    assert hard_signals({**base, "z_t": 0.0, "zc_t": 5.0})["zc_t"] is True
    assert hard_signals({**base, "z_t": 3.0, "zc_t": 3.0})["zc_t"] is False  # own bar (4.2)


def test_split_payment_is_one_history_group():
    # zc_t is a payment-history signal: alone it cannot hold even a {scam} set
    feats = {"n_t": 0.0, "e_t": 0.0, "z_t": 1.0, "zc_t": 5.0, "pi_t": 0.0, "d_R": 3.0}
    assert decide("{scam}", feats)["action"] == "nudge"
    assert decide("{scam}", {**feats, "d_R": 0.0})["action"] == "hold"


def test_hard_signals_accept_a_series_with_nan():
    row = pd.Series({"n_t": 0.0, "e_t": float("nan"), "z_t": float("nan"),
                     "zc_t": float("nan"), "pi_t": 0.0, "d_R": 3.0})
    assert not any(hard_signals(row).values())
