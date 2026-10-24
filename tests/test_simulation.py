import copy
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from simulation import generate_world
from online_features import snapshot
from features import brute_force, DAY


class WorldTests(unittest.TestCase):
    def test_seed_replay_and_variation(self):
        self.assertEqual(generate_world(42, "investment"), generate_world(42, "investment"))
        self.assertNotEqual(generate_world(42), generate_world(43))
        for invalid in (-1, True, "42", 2**32):
            with self.assertRaises(ValueError):
                generate_world(invalid)

    def test_future_and_same_time_evidence_excluded(self):
        world = generate_world(42)
        before = snapshot(world, 0, 4, 10000, world["now"])
        world["events"].append(dict(id="future", kind="payment", sender=0, receiver=4,
                                    amount_paise=100, event_at=world["now"], available_at=world["now"] - 1))
        world["events"].append(dict(id="delayed", kind="report", account=4,
                                    event_at=world["now"] - DAY, available_at=world["now"] + 1))
        self.assertEqual(snapshot(world, 0, 4, 10000, world["now"]), before)

    def test_independent_batch_oracle_random_worlds(self):
        for seed in range(5):
            world = generate_world(seed, "probes")
            now = world["now"]
            result = snapshot(world, 0, 4, 2_000_000, now)["values"]
            rows = [dict(txn_id=i, ts_int=e["event_at"], sender_id=e["sender"], receiver_id=e["receiver"],
                         amount=e["amount_paise"] / 100) for i, e in enumerate(world["events"]) if e["kind"] == "payment"]
            candidate = dict(txn_id=10000, ts_int=now, sender_id=0, receiver_id=4, amount=20000)
            tx = pd.DataFrame(rows + [candidate]).sort_values("ts_int", kind="stable")
            oracle = brute_force(tx, pd.DataFrame([candidate]), np.array([a["business"] for a in world["accounts"]])).iloc[0]
            for key in ("n_t", "e_t", "g_t", "z_t", "pi_t", "v_t", "zc_t", "ptr_t"):
                if pd.isna(oracle[key]):
                    self.assertIsNone(result[key])
                else:
                    self.assertAlmostEqual(result[key], oracle[key], places=10)

    def test_probe_window_and_counterparty(self):
        world = generate_world(42, "probes")
        self.assertEqual(snapshot(world, 0, 4, 100000, world["now"])["values"]["pi_t_snd"], 3)
        self.assertEqual(snapshot(world, 0, 1, 100000, world["now"])["values"]["pi_t_snd"], 0)
        self.assertEqual(snapshot(world, 0, 4, 100000, world["now"] + 3600)["values"]["pi_t_snd"], 0)

    def test_report_direction_and_previous_day_snapshot(self):
        world = generate_world(4, "investment")
        result = snapshot(world, 0, 4, 100000, world["now"])
        self.assertEqual(result["values"]["d_R_rcv"], 1)
        for event in world["events"]:
            if event["kind"] == "report":
                event["available_at"] = world["now"] - 1
        self.assertEqual(snapshot(world, 0, 4, 100000, world["now"])["values"]["d_R_rcv"], 3)

    def test_empty_history_has_missing_values(self):
        world = generate_world(42)
        world["events"] = []
        result = snapshot(world, 0, 4, 100000, world["now"])["values"]
        self.assertIsNone(result["e_t"])
        self.assertIsNone(result["z_t"])
        self.assertEqual(result["n_t"], 0)


if __name__ == "__main__":
    unittest.main()
