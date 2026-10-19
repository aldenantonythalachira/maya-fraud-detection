"""Maya -- Streamlit demo UI for the Phase 4 action policy engine.

Simulates a UPI payment screen and shows Maya's real-time intervention. Four
hardcoded scenarios exercise every branch of the Two-Signal Rule. The decision
math is produced by the *real* src/policy.py `decide()` (imported), and the real
models/xgb_model.json + models/conformal.json are loaded to show the live model
score alongside each scenario's pinned conformal set.

Run from the repo root:
    streamlit run ui/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from conformal import SET_FINE, SET_NAMES, SET_SCAM, SET_UNSURE, classify as conformal_classify
from policy import DEFAULT_THRESHOLDS, active_signals, decide
from risk_common import ENGLISH_REASONS, FEATURE_COLUMNS

MODEL_PATH = ROOT / "models" / "xgb_model.json"
CONFORMAL_PATH = ROOT / "models" / "conformal.json"
META_PATH = ROOT / "models" / "model_meta.json"

FINE = SET_NAMES[SET_FINE]      # "{fine}"
SCAM = SET_NAMES[SET_SCAM]      # "{scam}"
UNSURE = SET_NAMES[SET_UNSURE]  # "{fine, scam}"


# --- helpers ----------------------------------------------------------------


def inr(x: float) -> str:
    """Format an amount with Indian digit grouping, e.g. 200000 -> 2,00,000."""
    s = str(int(round(float(x))))
    if len(s) <= 3:
        return "Rs " + s
    head, tail = s[:-3], s[-3:]
    head = ",".join(head[::-1][i:i + 2] for i in range(0, len(head), 2))[::-1]
    return "Rs " + head + "," + tail


@st.cache_resource
def load_model(path: str):
    import xgboost as xgb

    model = xgb.XGBClassifier()
    model.load_model(path)
    return model


@st.cache_data
def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def synthesized_matrix(feats6: dict) -> pd.DataFrame:
    """Expand the 6 combined features into the model's 18-col row."""
    row = {}
    for col in FEATURE_COLUMNS:
        base = col.replace("_snd", "").replace("_rcv", "")
        row[col] = float(feats6.get(base, 0.0))
    return pd.DataFrame([row], columns=FEATURE_COLUMNS).astype("float32")


def live_score(model, feats6: dict) -> float:
    return float(model.predict_proba(synthesized_matrix(feats6))[:, 1][0])


def live_shap(model, feats6: dict):
    """Real SHAP top-3 for the synthesized row (empty list on any failure)."""
    try:
        from reasons import make_explainer, native_contrib, shap_matrix, top_reasons

        X = synthesized_matrix(feats6)
        try:
            sv = shap_matrix(make_explainer(model), X)[0]
        except Exception:
            sv = native_contrib(model, X)[0]
        return top_reasons(sv)
    except Exception:
        return []


# --- scenarios --------------------------------------------------------------

SCENARIOS = [
    {
        "key": "normal",
        "label": "Normal Transfer (Rs 40k to Mom)",
        "icon": "🟢",
        "payee": "Mom",
        "upi": "mom@okhdfcbank",
        "amount": 40_000.0,
        "note": "Rent help",
        "features": {"n_t": 5.0, "e_t": 0.0, "g_t": 0.0, "z_t": 0.0, "pi_t": 0.0, "d_R": 3.0},
        "soft": {},
        "conf_set": FINE,
        "reasons": [
            "Amount is in line with this payee's history",
            "Payee is an established, trusted contact",
            "No link to any reported fraudulent account",
        ],
    },
    {
        "key": "investment",
        "label": "Investment Scam (High Amount)",
        "icon": "🔴",
        "payee": "WealthGrow Investments",
        "upi": "wealthgrow@ybl",
        "amount": 200_000.0,
        "note": "IPO allotment fee",
        "features": {"n_t": 12.0, "e_t": 1.5, "g_t": 1.0, "z_t": 4.5, "pi_t": 0.0, "d_R": 1.0},
        "soft": {},
        "conf_set": SCAM,
        "reasons": [ENGLISH_REASONS["z_t"], ENGLISH_REASONS["e_t"], ENGLISH_REASONS["d_R"]],
    },
    {
        "key": "police",
        "label": "Fake Police Call (Screen Shared)",
        "icon": "🔴",
        "payee": "Officer R. Sharma (CBI)",
        "upi": "cbi.verify@upi",
        "amount": 75_000.0,
        "note": "'Verification deposit'",
        "features": {"n_t": 8.0, "e_t": 1.2, "g_t": 1.0, "z_t": 3.5, "pi_t": 0.0, "d_R": 1.0},
        "soft": {"is_screen_shared": True, "chat_stage": "payment_demand"},
        "conf_set": UNSURE,
        "reasons": [ENGLISH_REASONS["d_R"], ENGLISH_REASONS["z_t"], ENGLISH_REASONS["g_t"]],
    },
    {
        "key": "unclear",
        "label": "Unclear Edge Case (Soft only)",
        "icon": "🟡",
        "payee": "Rohan (marketplace)",
        "upi": "rohan.p2p@okicici",
        "amount": 5_000.0,
        "note": "Second-hand phone",
        "features": {"n_t": 6.0, "e_t": 0.2, "g_t": 0.0, "z_t": 1.5, "pi_t": 0.0, "d_R": 3.0},
        "soft": {"is_voice_active": True},
        "conf_set": UNSURE,
        "reasons": [
            "No payment-history anomaly: amount matches this payee",
            "Voice call active during payment",
            "Payee has no link to reported accounts",
        ],
    },
]
SCENARIOS_BY_KEY = {s["key"]: s for s in SCENARIOS}


# --- page -------------------------------------------------------------------


st.set_page_config(page_title="Maya -- UPI Payment Guard", page_icon="🛡️", layout="wide")

st.session_state.setdefault("scenario", SCENARIOS[0]["key"])
st.session_state.setdefault("checked", False)
st.session_state.setdefault("override", False)
st.session_state.setdefault("released", False)

model = load_model(str(MODEL_PATH)) if MODEL_PATH.exists() else None
conformal = load_json(str(CONFORMAL_PATH)) if CONFORMAL_PATH.exists() else {}
meta = load_json(str(META_PATH)) if META_PATH.exists() else {}

with st.sidebar:
    st.header("🧪 Scenarios")
    for sc in SCENARIOS:
        if st.button(f"{sc['icon']} {sc['label']}", width="stretch"):
            st.session_state.scenario = sc["key"]
            st.session_state.checked = False
            st.session_state.override = False
            st.session_state.released = False
            st.rerun()

    st.divider()
    st.header("🔬 Model & Conformal")
    if meta:
        c1, c2 = st.columns(2)
        c1.metric("AUROC", f"{meta.get('test_auroc', 0):.4f}")
        c2.metric("AUPRC", f"{meta.get('test_auprc', 0):.4f}")
        st.caption(
            f"best_iteration={meta.get('best_iteration')} · "
            f"scale_pos_weight={meta.get('scale_pos_weight', 0):.0f}"
        )
    if conformal:
        c1, c2 = st.columns(2)
        c1.metric("alpha", f"{conformal.get('alpha', 0):.2f}")
        c2.metric("q-hat", f"{conformal.get('qhat', 0):.6f}")
        st.metric("test coverage", f"{conformal.get('test', {}).get('coverage', 0):.4f}")
        st.caption(f"sets: {conformal.get('test', {}).get('set_distribution', {})}")

sc = SCENARIOS_BY_KEY[st.session_state.scenario]

decision = decide(
    sc["conf_set"],
    sc["features"],
    sc["soft"],
    sc["reasons"],
    sc["amount"],
    DEFAULT_THRESHOLDS,
)

st.title("🛡️ Maya")
st.caption("Real-time AI intervention layer for UPI payments — the Two-Signal Rule in action.")

left, right = st.columns([3, 2])

with left:
    with st.container(border=True):
        st.subheader("💸 UPI Payment")
        st.markdown(f"**Paying:** {sc['payee']}")
        st.caption(f"UPI ID: `{sc['upi']}`")
        pm, nm = st.columns(2)
        pm.metric("Amount", inr(sc["amount"]))
        nm.metric("Note", sc["note"])
        st.divider()
        if st.button(f"Pay {inr(sc['amount'])}", type="primary", width="stretch"):
            st.session_state.checked = True
            st.session_state.override = False
            st.session_state.released = False

    if not st.session_state.checked:
        st.info("Maya screens this payment in the background before it settles.")
    else:
        action = decision["action"]
        if action == "release":
            st.success(
                f"✅ **Payment sent** — {inr(sc['amount'])} to {sc['payee']}. "
                "Maya saw no risk and let it through."
            )
        elif action == "nudge":
            st.warning(
                "⚠️ **Maya: Proceed with caution.** Unusual signalling on this payment, "
                "but Maya is not confident enough to block it. If someone told you to pay, stop."
            )
            if not st.session_state.override:
                if st.button("Pay anyway", width="stretch"):
                    st.session_state.override = True
                    st.rerun()
            else:
                st.success(f"Payment sent after you confirmed — {inr(sc['amount'])} to {sc['payee']}.")
        elif action == "hold":
            st.error(
                f"🛑 **Payment held for review.** Maya detected two independent risk signals "
                f"and stopped this payment. It auto-releases in "
                f"{decision['auto_release_minutes']} minutes if not reviewed."
            )
            tm, am = st.columns(2)
            tm.metric("⏳ Auto-release", f"{decision['auto_release_minutes']} min")
            am.metric("Action", action)
            st.markdown("**Why Maya flagged this:**")
            for reason in decision["reasons"]:
                st.markdown(f"- {reason}")

            if decision["requires_analyst"]:
                st.error(
                    "🧑💼 **Analyst review required** — amount exceeds Rs 1,00,000; "
                    "routed to the bank fraud desk."
                )
            if sc["key"] == "police":
                st.error(
                    "📣 **Priya Alerted** — Maya silently notified your trusted contact "
                    "**Priya** and flagged this payment to the fraud desk. Screen-sharing "
                    "during a payment demand is a classic 'digital arrest' pattern."
                )
            if not st.session_state.released:
                if st.button("⏭ Advance 60 min (demo)", width="stretch"):
                    st.session_state.released = True
                    st.rerun()
            else:
                st.success("Auto-released after 60 minutes — payment sent.")

with right:
    st.subheader("🧮 Judge view")
    st.caption("Raw features, conformal set, and the exact policy.decide() output.")

    with st.expander("Raw features (t = now)", expanded=True):
        st.dataframe(pd.DataFrame([sc["features"]]), width="stretch", hide_index=True)

    with st.expander("Soft signals & conformal set", expanded=True):
        st.markdown("**Soft signals (mocked)**")
        st.json(sc["soft"] or {})
        st.markdown("**Conformal set (pinned for scenario)**")
        st.code(sc["conf_set"], language="text")
        if model is not None and conformal:
            p = live_score(model, sc["features"])
            implied = conformal_classify(p, float(conformal["qhat"]))
            st.metric("live model p_scam", f"{p:.4f}")
            st.caption(f"model-implied set: {implied} (scenario pins {sc['conf_set']})")

    with st.expander("Active hard / soft signals", expanded=False):
        st.json(active_signals(sc["features"], sc["soft"], DEFAULT_THRESHOLDS))

    with st.expander("Live SHAP top-3 (from xgb_model.json)", expanded=False):
        rows = live_shap(model, sc["features"]) if model is not None else []
        if rows:
            df = pd.DataFrame(
                [
                    {
                        "feature": f,
                        "shap": round(v, 4),
                        "direction": "increases risk" if v > 0 else "decreases risk",
                        "reason": t,
                    }
                    for f, v, t in rows
                ]
            )
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.caption("SHAP unavailable.")

    st.markdown("**Exact `policy.decide()` output**")
    st.json(decision)
