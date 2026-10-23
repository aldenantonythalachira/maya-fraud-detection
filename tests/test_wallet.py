import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from simulator_service import Simulator


class ModelFixture:
    """Explicit policy fixture; separate tests use actual XGBoost artifacts."""
    version, calibration_version = "fixture", "fixture-calibration"
    def score(self, values):
        return dict(score=0.7, uncertainty="{fine, scam}", contributions=[], base_margin=0)


class WalletTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "wallet.sqlite")
        self.service = Simulator(self.path, ModelFixture())
        self.world = self.service.create_world("owner", 42, "everyday")
        self.wid = self.world["id"]

    def tearDown(self):
        self.service.db.close()
        self.temp.cleanup()

    def payment(self, recipient=1, amount=10000):
        p = self.service.intent(self.wid, "owner", recipient, amount)
        r = self.service.review(self.wid, "owner", p["id"])
        return p, r

    def send(self, p, r, service=None):
        return (service or self.service).execute(self.wid, "owner", p["id"], r["id"], True, "DEMO")

    def test_conservation_retries_restart(self):
        initial = [a["balance_paise"] for a in self.world["accounts"]]
        p, r = self.payment()
        result = self.send(p, r)
        self.assertEqual(result, self.send(p, r))
        restarted = Simulator(self.path, ModelFixture())
        try:
            self.assertEqual(result, self.send(p, r, restarted))
        finally:
            restarted.db.close()
        after = self.service.read_world(self.wid, "owner")
        balances = [a["balance_paise"] for a in after["accounts"]]
        self.assertEqual(sum(initial), sum(balances))
        self.assertEqual(balances[0], initial[0] - 10000)
        self.assertEqual(balances[1], initial[1] + 10000)
        self.assertEqual(sum(e["delta"] for e in self.service.ledger(self.wid, "owner", result["id"])), 0)

    def test_separate_connections_competing_spends(self):
        balance = self.service.balance(self.wid, 0)
        p1, r1 = self.payment(amount=balance)
        p2, r2 = self.payment(amount=balance)
        other = Simulator(self.path, ModelFixture())
        outcomes = []
        def send(service, p, r):
            try:
                self.send(p, r, service)
                outcomes.append("sent")
            except ValueError:
                outcomes.append("rejected")
        threads = [threading.Thread(target=send, args=args) for args in
                   ((self.service, p1, r1), (other, p2, r2))]
        try:
            for t in threads: t.start()
            for t in threads: t.join()
            self.assertCountEqual(outcomes, ["sent", "rejected"])
            self.assertEqual(self.service.balance(self.wid, 0), 0)
        finally:
            other.db.close()

    def test_consent_edit_and_evidence_invalidate_review(self):
        p, r = self.payment()
        self.service.intent(self.wid, "owner", 1, 10000, "Pay your rent", True, p["id"])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.send(p, r)
        r2 = self.service.review(self.wid, "owner", p["id"])
        self.service.control(self.wid, "owner", "report", account=4)
        with self.assertRaisesRegex(ValueError, "Evidence"):
            self.send(p, r2)

    def test_unknown_session_and_observer_read_only(self):
        with self.assertRaises(ValueError):
            self.service.read_world(self.wid, "other")
        observation = self.service.observe(self.world["observer"])
        self.assertNotIn("observer", observation)
        self.assertNotIn("intents", observation)
        with self.assertRaises(ValueError):
            self.service.intent(self.wid, self.world["observer"], 1, 1000)

    def test_no_consent_never_persists_text(self):
        p = self.service.intent(self.wid, "owner", 1, 10000, "private text", False)
        r = self.service.review(self.wid, "owner", p["id"])
        self.assertNotIn("private text", json.dumps(r))

    def test_cancel_and_insufficient_funds(self):
        p, r = self.payment(amount=100_000_000)
        with self.assertRaisesRegex(ValueError, "balance"):
            self.send(p, r)
        self.service.cancel(self.wid, "owner", p["id"])
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.send(p, r)
        self.assertEqual(self.service.balance(self.wid, 0), self.world["accounts"][0]["balance_paise"])

    def test_hold_expiry_fresh_review_and_analyst(self):
        w = self.service.create_world("owner", 42, "investment")
        self.wid = w["id"]
        p, r = self.payment(4, 20_000_000)
        self.assertEqual(r["decision"]["action"], "hold")
        with self.assertRaisesRegex(ValueError, "held"):
            self.send(p, r)
        self.service.control(self.wid, "owner", "advance", seconds=3600)
        fresh = self.service.review(self.wid, "owner", p["id"])
        with self.assertRaisesRegex(ValueError, "analyst"):
            self.send(p, fresh)
        with self.assertRaisesRegex(ValueError, "Independent"):
            self.service.control(self.wid, "owner", "approve", pid=p["id"], review_id=fresh["id"])
        analyst = self.service.provision(self.wid, "analyst")["token"]
        self.service.role_action(analyst, "approve", p["id"], fresh["id"])
        self.send(p, fresh)

    def test_events_and_snapshot_immutable(self):
        p, r = self.payment()
        original = self.service.replay(self.wid, "owner", r["id"], True)
        self.send(p, r)
        self.assertEqual(original, self.service.replay(self.wid, "owner", r["id"], True))
        events = self.service.events(self.wid, "owner")
        self.assertEqual(events[-1]["stage"], "settled")
        self.assertEqual(self.service.events(self.wid, "owner", events[-1]["sequence"]), [])

    def test_counterfactual_preserves_original_hold_and_outcome(self):
        world = self.service.create_world("owner", 42, "investment")
        self.wid = world["id"]
        p, original = self.payment(4, 2_000_000)
        self.assertEqual(original["decision"]["action"], "hold")
        self.service.control(self.wid, "owner", "delay_reports")
        child_payment = self.service.intent(self.wid, "owner", 4, 2_000_000)
        child = self.service.review(self.wid, "owner", child_payment["id"], original["id"])
        self.assertEqual(child["decision"]["action"], "nudge")
        self.assertEqual(child["parent"], original["id"])
        self.assertEqual(self.service.replay(self.wid, "owner", original["id"], True), original)
        fresh = self.service.review(self.wid, "owner", p["id"])
        with self.assertRaisesRegex(ValueError, "held"):
            self.send(p, fresh)


if __name__ == "__main__":
    unittest.main()
