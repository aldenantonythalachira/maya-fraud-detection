import copy
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from claims import compare_claim, extract_claim
from payment_review import PaymentService, available_evidence


class FixtureAdapter:
    """Policy unit-test input, explicitly not trained model inference."""
    version, calibration_version = "test-fixture", "test-calibration"
    def score(self, features):
        return dict(score=0.7, uncertainty="{fine, scam}")


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.now = 100_000.0
        self.adapter = FixtureAdapter()
        self.service = PaymentService(self.adapter, clock=lambda: self.now)
        self.payment = self.service.create("payer", "recipient", 2_000_000)

    def tearDown(self):
        self.service.db.close()

    def review(self, evidence=None):
        return self.service.review(self.payment["id"], "payer", evidence or [])

    def evidence(self):
        return [dict(id="history", kind="payment", direction="outgoing", recipient="previous",
                     amount_paise=500_000, event_at=1, available_at=2),
                dict(id="report", kind="report", account="recipient", event_at=1, available_at=2)]

    def test_payment_change_invalidates_even_if_changed_back(self):
        r = self.review()
        for recipient, amount in (("other", 2_000_000), ("recipient", 2_000_000), ("recipient", 3_000_000)):
            self.service.change(self.payment["id"], "payer", recipient, amount)
            with self.assertRaisesRegex(ValueError, "changed"):
                self.service.execute(self.payment["id"], "payer", r["id"], True)

    def test_expiry_boundary_and_versions(self):
        r = self.review()
        self.now = r["expires_at"]
        with self.assertRaisesRegex(ValueError, "expired"):
            self.service.execute(self.payment["id"], "payer", r["id"], True)
        self.now -= 1
        self.adapter.version = "new-model"
        with self.assertRaisesRegex(ValueError, "versions"):
            self.service.execute(self.payment["id"], "payer", r["id"], True)

    def test_wrong_session_and_payment(self):
        r = self.review()
        with self.assertRaisesRegex(ValueError, "session"):
            self.service.execute(self.payment["id"], "other", r["id"], True)
        other = self.service.create("payer", "recipient", 2_000_000)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.service.execute(other["id"], "payer", r["id"], True)

    def test_confirmation_and_double_execution(self):
        r = self.review()
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.service.execute(self.payment["id"], "payer", r["id"])
        self.service.execute(self.payment["id"], "payer", r["id"], True)
        with self.assertRaises(ValueError):
            self.service.execute(self.payment["id"], "payer", r["id"], True)

    def test_cancel_is_terminal(self):
        r = self.review()
        self.service.cancel(self.payment["id"], "payer")
        with self.assertRaises(ValueError):
            self.service.execute(self.payment["id"], "payer", r["id"], True)

    def test_replay_is_immutable_and_recomputed(self):
        r = self.review(self.evidence())
        original = copy.deepcopy(r)
        r["outcome"]["action"] = "release"
        self.assertEqual(self.service.replay(r["id"], "payer", True), original)
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.db.execute("UPDATE reviews SET body='{}'")
        self.service.db.rollback()

    def test_delayed_report_excluded_and_child_retains_parent(self):
        evidence = self.evidence()
        r = self.review(evidence)
        self.assertEqual(r["outcome"]["action"], "hold")
        evidence[1]["available_at"] = self.now + 1
        child = self.service.review(self.payment["id"], "payer", evidence, parent=r["id"])
        self.assertEqual(child["outcome"]["action"], "nudge")
        self.assertEqual(child["parent"], r["id"])
        self.assertEqual(self.service.replay(r["id"], "payer")["outcome"]["action"], "hold")
        # New evidence cannot erase an already active hold on the same operation.
        with self.assertRaisesRegex(ValueError, "held"):
            self.service.execute(self.payment["id"], "payer", child["id"], True)

    def test_hold_expiry_requires_fresh_review(self):
        r = self.review(self.evidence())
        self.now += 3600
        with self.assertRaisesRegex(ValueError, "expired"):
            self.service.execute(self.payment["id"], "payer", r["id"], True)
        fresh = self.review(self.evidence())
        self.service.execute(self.payment["id"], "payer", fresh["id"], True)

    def test_analyst_required_above_threshold(self):
        self.service.change(self.payment["id"], "payer", "recipient", 20_000_000)
        self.review(self.evidence())
        self.now += 3600
        fresh = self.review(self.evidence())
        with self.assertRaisesRegex(ValueError, "Analyst"):
            self.service.execute(self.payment["id"], "payer", fresh["id"], True)
        self.service.approve_by_analyst(self.payment["id"], "payer", fresh["id"])
        self.service.execute(self.payment["id"], "payer", fresh["id"], True)

    def test_concurrent_execution_completes_once(self):
        r = self.review()
        outcomes = []
        def execute():
            try:
                self.service.execute(self.payment["id"], "payer", r["id"], True)
                outcomes.append("sent")
            except ValueError:
                outcomes.append("rejected")
        threads = [threading.Thread(target=execute) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertCountEqual(outcomes, ["sent", "rejected"])

    def test_amount_validation(self):
        for amount in (True, 1.2, 0, -1, 100_000_001):
            with self.assertRaises(ValueError):
                self.service.create("payer", "recipient", amount)


class ClaimTests(unittest.TestCase):
    def test_contradiction_and_future_promise_are_different(self):
        for text, expected in (("Approve to receive your refund", "direction_contradiction"),
                               ("Pay ₹20,000 to release your investment withdrawal", "unverified_future_benefit"),
                               ("Pay the agreed booking deposit", "consistent"),
                               ("Send the refund to your customer", "consistent")):
            claim = extract_claim(text, True)
            self.assertEqual(compare_claim(claim, "outgoing"), expected)
            self.assertEqual(text[claim["span"]["start"]:claim["span"]["end"]], claim["span"]["text"])

    def test_abstention_negation_and_consent(self):
        for text in ("Do not approve to receive a refund", "They said: approve to receive a refund", "Maybe later", "", "pay rent and receive a refund"):
            self.assertEqual(extract_claim(text, True)["status"], "unclear")
        self.assertEqual(extract_claim("Approve to receive a refund", False)["status"], "not_shared")

    def test_available_time_and_event_time_are_strict(self):
        rows = [dict(kind="report", event_at=9, available_at=9), dict(kind="report", event_at=10, available_at=9), dict(kind="report", event_at=9, available_at=10)]
        self.assertEqual(available_evidence(rows, 10), rows[:1])


if __name__ == "__main__":
    unittest.main()
