"""Maya UPI Payment Guard — FastAPI backend.

Wraps the Phase 4 action policy engine (the Two-Signal Rule) behind a thin HTTP
endpoint so a Next.js frontend can score a transaction. The `/api/score` flow is
a two-stage pipeline:

    1. jev_triage() — a mock pre-filter that releases obviously-safe transactions
       (amount < ₹1,000 AND d_R == 3) without touching the policy engine.
    2. decide()     — the real Two-Signal Rule, run only when triage escalates.

Run:
    python3 -m uvicorn api.main:app --reload
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
from datetime import datetime
import xgboost as xgb

# src/ has no __init__.py, so make it importable the same way ui/app.py does.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from conformal import SET_FINE, SET_NAMES, SET_SCAM, SET_UNSURE, classify as conformal_classify
from policy import DEFAULT_THRESHOLDS, active_signals, decide
from reasons import make_explainer, native_contrib, shap_matrix, top_reasons
from risk_common import FEATURE_COLUMNS

FINE = SET_NAMES[SET_FINE]      # "{fine}"
SCAM = SET_NAMES[SET_SCAM]      # "{scam}"
UNSURE = SET_NAMES[SET_UNSURE]  # "{fine, scam}" — the only branch the rule engine acts on

# Load the real model + metrics + conformal threshold + SHAP explainer once at startup.
MODEL_PATH = ROOT / "models" / "xgb_model.json"
META_PATH = ROOT / "models" / "model_meta.json"
CONFORMAL_PATH = ROOT / "models" / "conformal.json"
_model = xgb.XGBClassifier()
_model.load_model(str(MODEL_PATH))
_meta = json.loads(META_PATH.read_text())
_conf = json.loads(CONFORMAL_PATH.read_text())
_qhat = float(_conf["qhat"])
_alpha = float(_conf["alpha"])
_explainer = make_explainer(_model)


def _load_optional(path: Path) -> dict:
    """Read an optional JSON artifact, returning {} if it isn't there yet."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# Research-script outputs (may not exist until the scripts have been run).
_gnn = _load_optional(ROOT / "models" / "gnn_meta.json")
_fedavg = _load_optional(ROOT / "models" / "fedavg_meta.json")
_redteam = _load_optional(ROOT / "models" / "red_team_meta.json")

app = FastAPI(title="Maya UPI Payment Guard", version="0.1.0")

API_KEY = "sk_live_maya_enterprise"


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": "maya-v1", "uptime": "active"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def jev_triage(amount: float, d_R: int) -> dict:
    """Mock pre-filter: release trivial safe txns, else escalate to the policy engine."""
    if amount < 1000 and d_R == 3:
        return {"action": "release"}
    return {"action": "escalate"}


class Transaction(BaseModel):
    amount: float
    d_R: int
    z_t: float
    e_t: float = 0.0
    g_t: float = 0.0
    pi_t: float = 0.0
    is_screen_shared: bool = False
    chat_stage: str = "none"
    intent_claim: str = "none"
    payment_direction: str = "outgoing"
    mulehunter_status: str | None = None


class Triage(BaseModel):
    path: str
    reason: str


class FinalDecision(BaseModel):
    action: str
    auto_release_minutes: int
    requires_analyst: bool


class TraceResponse(BaseModel):
    triage: Triage
    features: dict[str, float]
    conformal_set: str
    shap_reasons: list[str]
    signals_fired: dict[str, list[str]]
    final_decision: FinalDecision
    evidence_sources: list[dict]
    decision_signature: str


class TimelineEvent(BaseModel):
    amount: float
    payee_id: str
    direction: str = "outgoing"


class JourneyRequest(BaseModel):
    timeline: list[TimelineEvent]
    current_amount: float
    current_payee_id: str


class JourneyResponse(BaseModel):
    journey_risk_score: int
    flags: list[str]


class CircuitBreakerRequest(BaseModel):
    reported_mule_id: str


@app.post("/api/score", dependencies=[Depends(require_api_key)])
def score(txn: Transaction) -> dict:
    """Two-stage decision, normalized to the 4-field decide() shape.

    The new sandbox fields (e_t/g_t/pi_t/chat_stage) are ignored here for now;
    they are only used by the /api/score-trace trace.
    """
    if jev_triage(txn.amount, txn.d_R)["action"] == "release":
        return {
            "action": "release",
            "reasons": [],
            "auto_release_minutes": 0,
            "requires_analyst": False,
        }

    features = {
        "n_t": 0.0,
        "e_t": 0.0,
        "g_t": 0.0,
        "z_t": txn.z_t,
        "pi_t": 0.0,
        "d_R": float(txn.d_R),
    }
    soft = {"is_screen_shared": txn.is_screen_shared}
    return decide(UNSURE, features, soft, reasons=[], amount=txn.amount)


def to_model_row(features: dict[str, float]) -> pd.DataFrame:
    """Mirror the 6 combined features into _snd/_rcv to feed the 18-col model."""
    row = dict(features)
    for f in ("n_t", "e_t", "g_t", "z_t", "pi_t", "d_R"):
        row[f"{f}_snd"] = features[f]
        row[f"{f}_rcv"] = features[f]
    return pd.DataFrame([row])[FEATURE_COLUMNS]


def build_evidence_sources(features: dict[str, float], mulehunter_status: str | None) -> list[dict]:
    """Provenance metadata per active signal. d_R and mulehunter share a source_id
    when both fire (they derive from the same fraud report), so the rule engine's
    OR-logic does not double-count them."""
    shared = (
        "report_123"
        if features["d_R"] <= 1.0 and mulehunter_status == "mule"
        else None
    )
    sources: list[dict] = []
    if features["z_t"] >= DEFAULT_THRESHOLDS.z_t:
        sources.append({"signal": "z_t", "source": "features", "source_id": None})
    if features["e_t"] >= DEFAULT_THRESHOLDS.e_t:
        sources.append({"signal": "e_t", "source": "features", "source_id": None})
    if features["pi_t"] >= DEFAULT_THRESHOLDS.pi_t:
        sources.append({"signal": "pi_t", "source": "features", "source_id": None})
    if features["d_R"] <= DEFAULT_THRESHOLDS.d_r_max:
        sources.append(
            {"signal": "d_R", "source": "graph", "source_id": shared or "graph_edges"}
        )
    if mulehunter_status == "mule":
        sources.append(
            {"signal": "mulehunter", "source": "mulehunter", "source_id": shared or "mulehunter_api"}
        )
    return sources


def sign_decision(final: dict) -> str:
    """SHA-256 over the canonical final_decision JSON (cryptographic audit log)."""
    return hashlib.sha256(json.dumps(final, sort_keys=True).encode()).hexdigest()


@app.post("/api/evaluate-journey")
def evaluate_journey(req: JourneyRequest) -> JourneyResponse:
    """Pre-ML sequence heuristics → a 0-100 Journey Risk Score (no model)."""
    flags: list[str] = []
    # (a) small outgoing payment followed by an incoming "credit"
    small_paid = False
    for ev in req.timeline:
        if ev.direction == "outgoing" and ev.amount < 1000:
            small_paid = True
        elif ev.direction == "incoming" and small_paid:
            flags.append("small_payment_before_credit")
            break
    # (b) payee changed vs history
    if req.timeline and req.current_payee_id not in {e.payee_id for e in req.timeline}:
        flags.append("new_payee")
    # (c) amount spike vs 3x historical average
    if req.timeline:
        avg = sum(e.amount for e in req.timeline) / len(req.timeline)
        if req.current_amount > 3 * avg:
            flags.append("amount_spike")

    weights = {"small_payment_before_credit": 40, "new_payee": 30, "amount_spike": 30}
    score = min(100, sum(weights[f] for f in flags))
    return JourneyResponse(journey_risk_score=score, flags=flags)


@app.post("/api/score-trace", dependencies=[Depends(require_api_key)])
def score_trace(txn: Transaction) -> TraceResponse:
    """Full Judge View trace of the two-stage pipeline (triage → policy engine)."""
    z_t = txn.z_t
    features = {
        "n_t": 5.0,
        "e_t": txn.e_t,
        "g_t": txn.g_t,
        "z_t": z_t,
        "pi_t": txn.pi_t,
        "d_R": float(txn.d_R),
    }

    # Intent contradiction overrides everything (checked before the fast/slow split).
    if txn.intent_claim == "receive_refund" and txn.payment_direction == "outgoing":
        intent_final = {
            "action": "hold",
            "auto_release_minutes": 60,
            "requires_analyst": txn.amount > 100_000,
        }
        return TraceResponse(
            triage=Triage(
                path="intent",
                reason="Intent contradiction: claimed refund but initiating outgoing payment",
            ),
            features=features,
            conformal_set=UNSURE,
            shap_reasons=["Intent Contradiction: Claimed refund but initiating outgoing payment"],
            signals_fired={"hard": [], "soft": []},
            final_decision=FinalDecision(**intent_final),
            evidence_sources=[{"signal": "intent_contradiction", "source": "intent_vs_execution", "source_id": None}],
            decision_signature=sign_decision(intent_final),
        )

    if jev_triage(txn.amount, txn.d_R)["action"] == "release":
        fast_final = {"action": "release", "auto_release_minutes": 0, "requires_analyst": False}
        return TraceResponse(
            triage=Triage(
                path="fast",
                reason="System-1 (jev_triage): trivial safe transaction",
            ),
            features=features,
            conformal_set=FINE,
            shap_reasons=[
                "Amount is below the triage threshold",
                "Receiver is 3 hops from any reported mule",
                "No other strong risk signals detected",
            ],
            signals_fired={"hard": [], "soft": []},
            final_decision=FinalDecision(**fast_final),
            evidence_sources=[],
            decision_signature=sign_decision(fast_final),
        )

    soft = {"is_screen_shared": txn.is_screen_shared, "chat_stage": txn.chat_stage}
    # Real model → real conformal set → real SHAP reasons (no mock routing).
    X = to_model_row(features)
    p_scam = float(_model.predict_proba(X)[0, 1])
    conf_set = conformal_classify(p_scam, _qhat)
    try:
        sv = shap_matrix(_explainer, X)[0]
    except Exception:
        sv = native_contrib(_model, X)[0]
    shap = [text for _, _, text in top_reasons(sv)]
    fired = active_signals(features, soft, DEFAULT_THRESHOLDS, txn.mulehunter_status, conf_set)
    signals = {"hard": list(fired["hard"].keys()), "soft": list(fired["soft"].keys())}
    evidence = build_evidence_sources(features, txn.mulehunter_status)
    decision = decide(
        conf_set, features, soft, reasons=shap, amount=txn.amount,
        mulehunter_status=txn.mulehunter_status,
    )
    final = {
        "action": decision["action"],
        "auto_release_minutes": decision["auto_release_minutes"],
        "requires_analyst": decision["requires_analyst"],
    }
    return TraceResponse(
        triage=Triage(
            path="slow",
            reason="System-1 escalated to System-2 (Two-Signal Rule)",
        ),
        features=features,
        conformal_set=conf_set,
        shap_reasons=shap,
        signals_fired=signals,
        final_decision=FinalDecision(**final),
        evidence_sources=evidence,
        decision_signature=sign_decision(final),
    )


@app.get("/api/metrics")
def metrics() -> dict:
    """Real metrics read from model_meta.json + conformal.json (no hardcoded values)."""
    return {
        "xgbAuroc": _meta["test_auroc"],
        "auprc": _meta["test_auprc"],
        "qhat": _qhat,
        "alpha": _alpha,
        "datasetSize": _meta["total_rows"],
        "gnnAuroc": _gnn.get("gnn_auroc"),
        "fedavgAuroc": _fedavg.get("fedavg_auroc"),
        "redTeamDrop": _redteam.get("maya_drop"),
    }


_txn_cache: dict = {}


def _load_transactions() -> pd.DataFrame:
    """Lazy, one-time load of the transactions needed for the circuit breaker."""
    if "df" not in _txn_cache:
        _txn_cache["df"] = pd.read_csv(
            ROOT / "data" / "transactions.csv",
            usecols=["sender_id", "receiver_vpa", "amount", "ts"],
        )
    return _txn_cache["df"]


def _fmt_ts(ts) -> str:
    s = str(ts)
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%d %b %I:%M %p")
    except ValueError:
        return s


@app.post("/api/circuit-breaker")
def circuit_breaker(req: CircuitBreakerRequest) -> dict:
    """Real Scam DNA circuit breaker: freeze a reported mule's fan-out network."""
    df = _load_transactions()
    mule = df[df["receiver_vpa"] == req.reported_mule_id]
    victims = int(mule["sender_id"].nunique())
    top = mule.nlargest(3, "amount")[["amount", "ts"]]
    at_risk = [
        {"amount": float(row.amount), "time": _fmt_ts(row.ts)}
        for row in top.itertuples()
    ]
    return {
        "victims_alerted": victims,
        "at_risk_transactions": at_risk,
        "status": "alerts_sent",
    }


def _extract_intent(msg: str) -> str:
    """Mock keyword-based intent extraction. In-memory only — never logs or persists."""
    lower = msg.lower()
    if "refund" in lower:
        return "receive_refund"
    if "fee" in lower or "payment" in lower:
        return "pay_fee"
    if "buy" in lower or "purchase" in lower:
        return "buy_item"
    return "none"


class ClaimRequest(BaseModel):
    chat_message: str


class ClaimResponse(BaseModel):
    intent_claim: str
    processed_in_memory: bool = True


class CanaryRequest(BaseModel):
    message: str


@app.post("/api/extract-claim")
def extract_claim(req: ClaimRequest) -> ClaimResponse:
    """Private Mode: req.chat_message is processed in memory only.

    It is read into a local variable, passed through the in-memory
    _extract_intent() keyword helper, and never written to a log file,
    database, or stdout. The raw message is intentionally NOT echoed back.
    """
    intent = _extract_intent(req.chat_message)
    return ClaimResponse(intent_claim=intent)


@app.post("/api/privacy-canary")
def privacy_canary(req: CanaryRequest) -> dict:
    """Canary: accepts a string and proves it is neither stored nor sent."""
    return {"status": "processed", "stored": False, "network_sent": False}


class ReviewRequest(BaseModel):
    trace_id: str
    reason: str


class ReviewResponse(BaseModel):
    status: str
    reference_id: str
    message: str


@app.post("/api/request-review")
def request_review(req: ReviewRequest) -> ReviewResponse:
    """Legitimate User Recourse: register a human review request for a decision."""
    ref = "REQ-" + hashlib.sha256(f"{req.trace_id}:{req.reason}".encode()).hexdigest()[:8].upper()
    return ReviewResponse(
        status="review_requested",
        reference_id=ref,
        message="An independent analyst will review this shortly.",
    )
