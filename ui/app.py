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
from integrations import check_fri, check_mulehunter, file_1930_report
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


def scam_dna_figure():
    """Directed Plotly/NetworkX graph of the investment scam's money-layering chain."""
    import networkx as nx
    import plotly.graph_objects as go

    nodes = [
        ("you", "You", "Victim"),
        ("entry", "WealthGrow", "Entry mule"),
        ("mid", "Mule #7782", "Layering"),
        ("agg", "Aggregator #12", "Consolidation"),
        ("exit", "Crypto exit", "Cash-out"),
    ]
    edges = [("you", "entry"), ("entry", "mid"), ("mid", "agg"), ("agg", "exit")]
    role_color = {
        "Victim": "#4C78A8",
        "Entry mule": "#F58518",
        "Layering": "#F58518",
        "Consolidation": "#F58518",
        "Cash-out": "#E45756",
    }

    G = nx.DiGraph()
    for nid, name, role in nodes:
        G.add_node(nid, name=name, role=role)
    G.add_edges_from(edges)

    pos = {nid: (i, 0.0) for i, (nid, _, _) in enumerate(nodes)}

    fig = go.Figure()
    gap = 0.30
    for s, t in edges:
        fig.add_annotation(
            x=pos[t][0] - gap, y=0.0, ax=pos[s][0] + gap, ay=0.0,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=3, arrowsize=1.4,
            arrowwidth=2, arrowcolor="#90A4AE",
        )
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n, _, _ in nodes],
        y=[0.0] * len(nodes),
        mode="markers+text",
        text=[f"<b>{name}</b><br>{role}" for _, name, role in nodes],
        textposition="top center",
        marker=dict(size=30, color=[role_color[role] for _, _, role in nodes],
                    line=dict(color="white", width=2)),
        hoverinfo="text",
    ))
    fig.update_layout(
        showlegend=False,
        xaxis=dict(visible=False, range=[-0.9, 4.9]),
        yaxis=dict(visible=False, range=[-1.1, 1.7]),
        margin=dict(l=10, r=10, t=20, b=10),
        height=280,
    )
    return fig


def journey_dataframe(journey: list):
    """Build a Styler for a scenario's transaction journey, flagging the escalation."""
    df = pd.DataFrame(journey)
    df["Amount"] = df["Amount"].apply(inr)

    def highlight(row):
        if row["Stage"] == "Escalate":
            return ["background-color: #ffcccc; font-weight: bold"] * len(row)
        if row["Stage"] == "Fake Profit":
            return ["background-color: #ccffcc"] * len(row)
        return [""] * len(row)

    return df.style.apply(highlight, axis=1)


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
        "phone": "9876543210",
        "account_id": "1001",
        "txn_id": 100001,
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
        "phone": "9812345678",
        "account_id": "2002",
        "txn_id": 100002,
        "features": {"n_t": 12.0, "e_t": 1.5, "g_t": 1.0, "z_t": 4.5, "pi_t": 0.0, "d_R": 1.0},
        "soft": {},
        "conf_set": SCAM,
        "reasons": [ENGLISH_REASONS["z_t"], ENGLISH_REASONS["e_t"], ENGLISH_REASONS["d_R"]],
        "network": True,
        "journey": [
            {"Day": 1, "Stage": "Hook", "Amount": 10_000.0, "Direction": "Sent"},
            {"Day": 2, "Stage": "Fake Profit", "Amount": 5_000.0, "Direction": "Received"},
            {"Day": 3, "Stage": "Trust", "Amount": 50_000.0, "Direction": "Sent"},
            {"Day": 5, "Stage": "Escalate", "Amount": 200_000.0, "Direction": "Sent"},
        ],
    },
    {
        "key": "police",
        "label": "Fake Police Call (Screen Shared)",
        "icon": "🔴",
        "payee": "Officer R. Sharma (CBI)",
        "upi": "cbi.verify@upi",
        "amount": 75_000.0,
        "note": "'Verification deposit'",
        "phone": "9000000001",
        "account_id": "3003",
        "txn_id": 100003,
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
        "phone": "9123456789",
        "account_id": "4004",
        "txn_id": 100004,
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
st.session_state.setdefault("analyst_action", None)

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
            st.session_state.analyst_action = None
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

fri = check_fri(sc["phone"])
mh = check_mulehunter(sc["account_id"])

decision = decide(
    sc["conf_set"],
    sc["features"],
    sc["soft"],
    sc["reasons"],
    sc["amount"],
    DEFAULT_THRESHOLDS,
    mulehunter_status=mh,
)

st.title("🛡️ Maya")
st.caption("Real-time AI intervention layer for UPI payments — the Two-Signal Rule in action.")

tab_demo, tab_sandbox = st.tabs(["🧪 Scenario Demo", "🧪 Sandbox Mode"])

with tab_demo:
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
                st.session_state.analyst_action = None

        if sc.get("journey"):
            with st.expander("📈 Transaction Journey", expanded=True):
                st.dataframe(journey_dataframe(sc["journey"]), hide_index=True)

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

                if sc.get("network"):
                    with st.expander("🕸️ Scam DNA — money-flow network", expanded=True):
                        st.caption("Once you pay, the money is layered through mules to a crypto exit.")
                        st.plotly_chart(scam_dna_figure(), width="stretch")

                if decision["requires_analyst"]:
                    st.error(
                        "🧑💼 **Analyst review required** — amount exceeds Rs 1,00,000; "
                        "routed to the bank fraud desk."
                    )
                    with st.expander("🧑💼 Analyst Dashboard", expanded=True):
                        st.caption(f"Transaction {sc['txn_id']} · {inr(sc['amount'])} · held by Maya")
                        c1, c2 = st.columns(2)
                        c1.metric("DoT FRI score", f"{fri['fri_score']} / 100")
                        c1.caption(f"Risk band: {fri['risk_band']}")
                        if mh == "mule":
                            c2.error(f"MuleHunter.AI: {mh}")
                        elif mh == "suspicious":
                            c2.warning(f"MuleHunter.AI: {mh}")
                        else:
                            c2.success(f"MuleHunter.AI: {mh}")
                        # The hold resolves exactly once: analyst approve / report, or the
                        # 60-min auto-release, whichever comes first.
                        if st.session_state.analyst_action == "approved":
                            st.success(f"Release approved — payment released to {sc['payee']}.")
                        elif st.session_state.analyst_action == "reported":
                            rep = file_1930_report(sc["txn_id"], sc["amount"])
                            st.success(f"Report filed with NCRP (ref {rep['ref_id']}). Account blocked.")
                        elif st.session_state.released:
                            st.info("Auto-released before analyst review — no action available.")
                        else:
                            a1, a2 = st.columns(2)
                            if a1.button("Approve Release", width="stretch"):
                                st.session_state.analyst_action = "approved"
                                st.rerun()
                            if a2.button("File 1930 Report & Block", width="stretch"):
                                st.session_state.analyst_action = "reported"
                                st.rerun()
                if sc["key"] == "police":
                    st.error(
                        "📣 **Priya Alerted** — Maya silently notified your trusted contact "
                        "**Priya** and flagged this payment to the fraud desk. Screen-sharing "
                        "during a payment demand is a classic 'digital arrest' pattern."
                    )
                if st.session_state.analyst_action == "reported":
                    st.info("Auto-release cancelled — funds blocked after the 1930 report.")
                elif st.session_state.analyst_action == "approved":
                    pass  # already released by the analyst
                elif st.session_state.released:
                    st.success("Auto-released after 60 minutes — payment sent.")
                elif st.button("⏭ Advance 60 min (demo)", width="stretch"):
                    st.session_state.released = True
                    st.rerun()

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
            st.json(active_signals(sc["features"], sc["soft"], DEFAULT_THRESHOLDS, mh, sc["conf_set"]))

        with st.expander("Ecosystem signals (mocked)", expanded=False):
            c1, c2 = st.columns(2)
            c1.metric("DoT FRI score", f"{fri['fri_score']} / 100")
            c1.caption(f"Risk band: {fri['risk_band']}")
            if mh == "mule":
                c2.error(f"MuleHunter.AI: {mh}")
            elif mh == "suspicious":
                c2.warning(f"MuleHunter.AI: {mh}")
            else:
                c2.success(f"MuleHunter.AI: {mh}")

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

with tab_sandbox:
    st.subheader("🧪 Sandbox Mode")
    st.caption("Tune the raw inputs and watch the Two-Signal Rule decide in real time.")
    amount = st.slider("Amount (₹)", 1_000, 500_000, 50_000, step=1_000)
    mule_hops = st.slider("Mule Hops", 0, 3, 3, step=1)
    screen_shared = st.toggle("Screen Shared", value=False)
    st.divider()
    if st.button("Simulate Payment", type="primary", width="stretch"):
        z_t = amount / 100_000.0
        features = {"n_t": 0.0, "e_t": 0.0, "g_t": 0.0, "z_t": z_t, "pi_t": 0.0, "d_R": float(mule_hops)}
        soft = {"is_screen_shared": screen_shared}
        sandbox_decision = decide(UNSURE, features, soft, reasons=[], amount=float(amount))
        action = sandbox_decision["action"]
        if action == "release":
            st.success("✅ Release — Maya saw no risk and would let this payment through.")
        elif action == "nudge":
            st.warning("⚠️ Nudge — unusual signalling, but not enough to block the payment.")
        else:
            st.error(f"🛑 Hold — two independent signals agreed (auto-release in {sandbox_decision['auto_release_minutes']} min).")
        st.markdown("**Exact `policy.decide()` output**")
        st.json(sandbox_decision)
