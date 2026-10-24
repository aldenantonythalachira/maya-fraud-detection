"""Maya risk-scoring API (src/api.py) via FastAPI's TestClient.

Most tests inject a fake scorer and a PaymentService with a fixture adapter, so
they run in CI without trained models. The real-model tests at the bottom are
skipped unless models/ exists (like tests/test_ui.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api
from conftest import ROOT
from payment_review import PaymentService
from risk_common import FEATURE_COLUMNS
from scenario_features import SCENARIO_FEATURES, model_matches


class FakeScorer:
    """Returns a fixed conformal set; records what it was asked to score."""
    model_version, calibration_version = "fake-model", "fake-calibration"

    def __init__(self, conf_set="{fine, scam}", p=0.5):
        self.conf_set, self.p, self.seen = conf_set, p, []

    def score(self, values, explain=False):
        self.seen.append(values)
        return {"p_scam": self.p, "conformal_set": self.conf_set, "reasons": ["r1", "r2", "r3"],
                "reason_features": ["z_t", "d_R", "n_t"]}

    def info(self):
        return {"model_version": self.model_version, "calibration_version": self.calibration_version,
                "conformal": {}, "metrics": {}}


class FixtureAdapter:
    """Policy-level input for the review service, explicitly not model inference."""
    version, calibration_version = "test-fixture", "test-calibration"

    def score(self, features):
        return dict(score=0.7, uncertainty="{fine, scam}")


def client(conf_set="{fine, scam}", now=100_000.0):
    scorer = FakeScorer(conf_set)
    service = PaymentService(FixtureAdapter(), clock=lambda: now)
    return TestClient(api.create_app(scorer, service, load_defaults=False)), scorer


def features(**overrides):
    f = {c: 0.0 for c in FEATURE_COLUMNS}
    f.update({"d_R": 3.0, "d_R_snd": 3.0, "d_R_rcv": 3.0})
    f.update(overrides)
    return f


def score(c, feats=None, **body):
    return c.post("/v1/score", json={"features": feats or features(), "amount_inr": 900.0, **body})


# --- stateless scoring ------------------------------------------------------------


def test_response_is_the_decide_contract_plus_metadata():
    c, _ = client()
    r = score(c, features(z_t=3.0, d_R=0.0), request_id="abc")
    assert r.status_code == 200
    body = r.json()
    assert (body["action"], body["auto_release_minutes"], body["requires_analyst"]) == ("hold", 60, False)
    assert body["reasons"] == ["r1", "r2", "r3"]
    assert body["conformal_set"] == "{fine, scam}" and body["request_id"] == "abc"
    assert body["fired_signals"]["hard"] == {"z_t": True, "d_R": True}
    assert body["policy_version"] == api.POLICY_VERSION and body["latency_ms"] >= 0


def test_safeguard_holds_through_the_api():
    c, _ = client("{scam}")
    # a confident {scam} with only one signal group is a nudge, not a hold
    assert score(c, features(z_t=3.0)).json()["action"] == "nudge"
    assert score(c, features(z_t=3.0), soft_signals={"is_screen_shared": True}).json()["action"] == "hold"
    assert score(c, features(), soft_signals={"is_screen_shared": True}).json()["action"] == "nudge"
    # a mule verdict is receiving-account evidence for a non-fine set
    assert score(c, features(z_t=3.0), mulehunter_status="mule").json()["action"] == "hold"


def test_fine_set_releases_and_analyst_threshold():
    c, _ = client("{fine}")
    assert score(c, features(z_t=3.0, d_R=0.0)).json()["action"] == "release"
    c, _ = client("{scam}")
    big = c.post("/v1/score", json={"features": features(z_t=3.0, d_R=0.0), "amount_inr": 150_000})
    assert big.json()["requires_analyst"] is True


@pytest.mark.parametrize("mutate", [
    lambda f: f.pop("v_t"),                         # missing feature
    lambda f: f.update(not_a_feature=1.0),          # unknown feature
])
def test_feature_contract_is_exact(mutate):
    c, _ = client()
    f = features()
    mutate(f)
    r = score(c, f)
    assert r.status_code == 422 and "maya-features-v1" in r.text


@pytest.mark.parametrize("body", [
    {"amount_inr": 0},
    {"amount_inr": -5},
    {"soft_signals": {"chat_stage": "made_up"}},
    {"mulehunter_status": "maybe"},
    {"conformal_set": "{fine}"},                    # callers can't pass a decision in
])
def test_bad_requests_are_rejected(body):
    c, _ = client()
    payload = {"features": features(), "amount_inr": 900.0, **body}
    assert c.post("/v1/score", json=payload).status_code == 422


def test_null_features_mean_missing():
    c, scorer = client()
    r = score(c, features(ptr_t=None, ptr_t_snd=None, ptr_t_rcv=None))
    assert r.status_code == 200
    assert all(v != v for k, v in scorer.seen[-1].items() if k.startswith("ptr_t"))  # NaN


def test_not_ready_without_models():
    c = TestClient(api.create_app(load_defaults=False))
    assert c.get("/v1/health").json()["status"] == "not_ready"
    assert score(c).status_code == 503
    assert c.get("/v1/model").status_code == 503


# --- demo data and frontends -------------------------------------------------------


def test_demo_scenarios_are_ready_for_score():
    c, _ = client()
    rows = c.get("/v1/demo/scenarios").json()
    assert [r["key"] for r in rows] == list(SCENARIO_FEATURES)
    for r in rows:
        assert set(r["features"]) == set(FEATURE_COLUMNS)
        assert r["label"]["en"] and r["label"]["hi"] and r["payee"]["en"] and r["note"]["hi"]
        assert r["mulehunter_status"] in ("clean", "suspicious", "mule")
        body = {k: r[k] for k in ("features", "amount_inr", "soft_signals", "mulehunter_status")}
        assert c.post("/v1/score", json=body).status_code == 200


def test_frontends_are_served():
    c, _ = client()
    for path, marker in (("/app/", 'src="user.js"'), ("/demo/", 'src="judge.js"')):
        r = c.get(path)
        assert r.status_code == 200 and marker in r.text
    assert c.get("/static/tokens.css").status_code == 200
    font = c.get("/static/fonts/anek-latin.woff2")
    assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"
    assert c.get("/", follow_redirects=False).headers["location"] == "/demo/"


# --- stateful payment review -------------------------------------------------------

H = {"X-Payer-Session": "payer"}
EVIDENCE = [
    {"id": "history", "kind": "payment", "direction": "outgoing", "recipient": "previous",
     "amount_paise": 500_000, "event_at": 1, "available_at": 2},
    {"id": "report", "kind": "report", "account": "recipient", "event_at": 1, "available_at": 2},
]


def new_payment(c, amount=2_000_000):
    r = c.post("/v1/payments", json={"recipient": "recipient", "amount_paise": amount}, headers=H)
    assert r.status_code == 201
    return r.json()


def test_review_flow_and_held_payment_is_refused():
    c, _ = client()
    p = new_payment(c)
    rv = c.post(f"/v1/payments/{p['id']}/reviews", json={"evidence": EVIDENCE}, headers=H)
    assert rv.status_code == 201 and rv.json()["outcome"]["action"] == "hold"
    ex = c.post(f"/v1/payments/{p['id']}/execute", json={"review_id": rv.json()["id"], "confirmed": True},
                headers=H)
    assert ex.status_code == 409 and "held" in ex.json()["detail"]
    replay = c.get(f"/v1/reviews/{rv.json()['id']}", params={"recompute": True}, headers=H)
    assert replay.status_code == 200 and replay.json()["digest"] == rv.json()["digest"]


def test_changed_payment_invalidates_review():
    c, _ = client()
    p = new_payment(c)
    rv = c.post(f"/v1/payments/{p['id']}/reviews", json={"evidence": []}, headers=H).json()
    assert c.patch(f"/v1/payments/{p['id']}", json={"recipient": "other", "amount_paise": 2_000_000},
                   headers=H).status_code == 200
    ex = c.post(f"/v1/payments/{p['id']}/execute", json={"review_id": rv["id"], "confirmed": True}, headers=H)
    assert ex.status_code == 409 and "changed" in ex.json()["detail"]


def test_error_codes():
    c, _ = client()
    p = new_payment(c)
    assert c.get("/v1/payments/nope", headers=H).status_code == 404
    assert c.get(f"/v1/payments/{p['id']}", headers={"X-Payer-Session": "someone"}).status_code == 403
    assert c.get(f"/v1/payments/{p['id']}").status_code == 422          # no session header
    assert c.post("/v1/payments", json={"recipient": "r", "amount_paise": 0}, headers=H).status_code == 422
    assert c.post(f"/v1/payments/{p['id']}/cancel", headers=H).json()["state"] == "cancelled"
    assert c.post(f"/v1/payments/{p['id']}/cancel", headers=H).status_code == 409  # terminal


def test_evidence_is_validated_per_kind():
    c, _ = client()
    p = new_payment(c)
    bad = [{"id": "x", "kind": "report", "event_at": 1, "available_at": 2}]  # report without account
    r = c.post(f"/v1/payments/{p['id']}/reviews", json={"evidence": bad}, headers=H)
    assert r.status_code == 422 and "account" in r.text


# --- real trained model (skipped without models/) -------------------------------

MODELS = [ROOT / "models" / n for n in ("xgb_model.json", "conformal.json")]
real = pytest.mark.skipif(not all(p.exists() for p in MODELS),
                          reason="trained models not present (run the pipeline first)")
picked = pytest.mark.skipif(not model_matches(MODELS[0]),
                            reason="model changed since the demo scenarios were picked: "
                                   "run python scripts/pick_scenarios.py and update src/scenario_features.py")


@pytest.fixture(scope="module")
def real_client():
    return TestClient(api.create_app())


@real
@picked
@pytest.mark.parametrize("key", list(SCENARIO_FEATURES))
def test_ui_scenarios_score_like_the_ui(real_client, key):
    from integrations import check_mulehunter

    sc = SCENARIO_FEATURES[key]
    r = real_client.post("/v1/score", json={
        "features": sc["features"], "amount_inr": sc["amount_inr"], "soft_signals": sc["soft"],
        "mulehunter_status": check_mulehunter(sc["account_id"])})
    assert r.status_code == 200
    body = r.json()
    assert body["conformal_set"] == sc["conf_set"]
    assert (body["action"], body["requires_analyst"]) == sc["expected"]


@real
def test_explain_and_reason_features(real_client):
    sc = SCENARIO_FEATURES["investment"]
    body = {"features": sc["features"], "amount_inr": sc["amount_inr"]}
    plain = real_client.post("/v1/score", json=body).json()
    assert plain["explanation"] is None
    assert len(plain["reason_features"]) == len(plain["reasons"]) > 0
    full = real_client.post("/v1/score", json={**body, "explain": True}).json()
    rows = full["explanation"]["contributions"]
    assert {r["feature"] for r in rows} == set(FEATURE_COLUMNS)
    assert all(set(r) == {"feature", "shap", "text", "value", "risky"} for r in rows)
    # every cited reason comes from a feature flagged as in its risky range
    risky_bases = {r["feature"].replace("_snd", "").replace("_rcv", "") for r in rows if r["risky"]}
    assert set(full["reason_features"]) <= risky_bases


@real
def test_latency_within_slo(real_client):
    sc = SCENARIO_FEATURES["investment"]
    body = {"features": sc["features"], "amount_inr": sc["amount_inr"]}
    real_client.post("/v1/score", json=body)  # warm-up
    times = sorted(real_client.post("/v1/score", json=body).json()["latency_ms"] for _ in range(50))
    assert times[int(0.95 * len(times))] < api.SLO_MS
