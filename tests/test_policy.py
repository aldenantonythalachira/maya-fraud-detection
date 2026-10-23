"""Regression tests for the universal hold safeguard, independent of model weights."""
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from policy import decide


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


if __name__ == "__main__":
    unittest.main()
