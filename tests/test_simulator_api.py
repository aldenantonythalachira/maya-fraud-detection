import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient
from simulator_api import create_app
from simulator_service import LiveModel, Simulator
from test_wallet import ModelFixture

ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.service = Simulator(":memory:", ModelFixture())
        self.client = TestClient(create_app(self.service))
        self.world = self.client.post("/api/worlds", json=dict(seed=42)).json()
        self.base = "/api/worlds/" + self.world["id"]

    def tearDown(self):
        self.client.close()
        self.service.db.close()

    def test_api_complete_payment_and_idempotency(self):
        p = self.client.post(self.base + "/intents", json=dict(recipient=1, amount_paise=125050)).json()
        review = self.client.post(self.base + "/intents/" + p["id"] + "/review", json={}).json()
        route = self.base + "/intents/" + p["id"] + "/execute"
        body = dict(review_id=review["id"], confirmed=True, authorization="DEMO")
        first = self.client.post(route, json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), self.client.post(route, json=body).json())
        ledger = self.client.get(self.base + "/ledger/" + first.json()["id"]).json()
        self.assertEqual([r["delta"] for r in ledger], [-125050, 125050])
        observer = self.client.get("/api/observer", headers={"X-Maya-Access": self.world["observer"]}).json()
        self.assertEqual(len(observer["transfers"]), 1)
        events = self.client.get(self.base + "/events").json()
        self.assertIn("settled", [e["stage"] for e in events])

    def test_cross_session_origin_and_client_score_rejected(self):
        other = TestClient(create_app(self.service))
        try:
            self.assertEqual(other.get(self.base).status_code, 409)
        finally:
            other.close()
        self.assertEqual(self.client.post("/api/worlds", json=dict(seed=3), headers={"Origin":"https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.post(self.base + "/intents", json=dict(recipient=1, amount_paise=100, score=.1)).status_code, 422)
        self.assertEqual(self.client.post(self.base + "/intents", json=dict(recipient=1, amount_paise=True)).status_code, 422)
        self.assertEqual(self.client.get("/", headers={"Host":"evil.example"}).status_code, 400)

    def test_html_assets_and_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("MAYA", response.text)
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/assets/app.js").status_code, 200)

    @unittest.skipUnless((ROOT / "models/xgb_model.json").exists(), "Run bootstrap_demo.py for live-model integration")
    def test_actual_model_and_policy_replay(self):
        model = LiveModel(str(ROOT / "models/xgb_model.json"), str(ROOT / "models/conformal.json"))
        live = Simulator(":memory:", model)
        try:
            for preset in ("everyday", "investment", "refund", "probes"):
                w = live.create_world("live-test", 42, preset)
                p = live.intent(w["id"], "live-test", w["default_recipient"], w["default_amount_paise"])
                r = live.review(w["id"], "live-test", p["id"])
                self.assertEqual(len(r["model"]["contributions"]), 18)
                import math
                logit = r["model"]["base_margin"] + sum(c["value"] for c in r["model"]["contributions"])
                self.assertAlmostEqual(1 / (1 + math.exp(-logit)), r["model"]["score"], places=5)
                self.assertEqual(live.replay(w["id"], "live-test", r["id"], True), r)
        finally:
            live.db.close()


if __name__ == "__main__":
    unittest.main()
