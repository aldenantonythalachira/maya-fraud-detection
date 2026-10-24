"""Maya -- Streamlit demo UI for the Phase 4 action policy engine.

Simulates a UPI payment screen and shows Maya's real-time intervention. Four
scenarios exercise every branch of the Two-Signal Rule. Each scenario's 18
features are copied from a real test-split transaction (`source_txn`), scored
live by models/xgb_model.json, turned into a conformal set with
models/conformal.json, and passed to the *real* src/policy.py `decide()`
together with live SHAP reasons. A sidebar toggle can pin each scenario's
scripted set instead (the pre-model demo behaviour).

Run from the repo root:
    streamlit run ui/app.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from conformal import (
    SET_FINE, SET_NAMES, SET_SCAM, SET_UNSURE, classify as conformal_classify, load_conformal,
)
from integrations import check_fri, check_mulehunter, file_1930_report
from policy import AUTO_RELEASE_MINUTES, DEFAULT_THRESHOLDS, HOLD_ANALYST_AMOUNT, active_signals, decide
from risk_common import ENGLISH_REASONS, FEATURE_COLUMNS
from scenario_features import SCENARIO_FEATURES, SCENARIO_STORY

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


def synthesized_matrix(feats: dict) -> pd.DataFrame:
    """The model's 18-col row: used as-is when all 18 are given (scenarios),
    otherwise the 6 combined features are mirrored into `_snd`/`_rcv` (sandbox)."""
    row = {}
    for col in FEATURE_COLUMNS:
        base = col.replace("_snd", "").replace("_rcv", "")
        row[col] = float(feats.get(col, feats.get(base, 0.0)))
    return pd.DataFrame([row], columns=FEATURE_COLUMNS).astype("float32")


def live_score(model, feats6: dict) -> float:
    return float(model.predict_proba(synthesized_matrix(feats6))[:, 1][0])


def live_shap(model, feats: dict):
    """Real SHAP rows for the synthesized row, all 18 by |SHAP| (empty list on any failure)."""
    try:
        from reasons import make_explainer, native_contrib, shap_matrix, top_reasons

        X = synthesized_matrix(feats)
        try:
            sv = shap_matrix(make_explainer(model), X)[0]
        except Exception:
            sv = native_contrib(model, X)[0]
        return top_reasons(sv, k=len(FEATURE_COLUMNS))
    except Exception:
        return []


def risk_reasons(shap_rows: list, feats: dict, k: int = 3) -> list:
    """The shared "only cite true reasons" filter (src/reasons.py), applied to
    the synthesized 27-col row."""
    from reasons import risk_reasons as shared

    return shared(shap_rows, synthesized_matrix(feats).iloc[0], k)


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

# Each scenario's features are copied (rounded to 4 dp) from the real test-split
# txn in `source_txn`, picked to match the story; `amount` is that txn's amount.
# `conf_set` is the scripted set, used only when the sidebar pin toggle is on.
SCENARIOS = [
    {
        "key": "normal",
        "label": "Normal Transfer (Rs 36k to Mom)",
        "icon": "🟢",
        "payee": SCENARIO_STORY["normal"]["payee"]["en"],
        "upi": SCENARIO_STORY["normal"]["upi"],
        "amount": SCENARIO_FEATURES["normal"]["amount_inr"],
        "note": SCENARIO_STORY["normal"]["note"]["en"],
        "phone": "9876543210",
        "account_id": "1001",
        "txn_id": 100001,
        "source_txn": SCENARIO_FEATURES["normal"]["source_txn"],
        "features": SCENARIO_FEATURES["normal"]["features"],
        "soft": {},
        "conf_set": FINE,
        "reasons": [
            "Payee has no link to any reported fraudulent account",
            "Payment history matches a long-standing contact",
            "No probe payments or new-payee burst",
        ],
    },
    {
        "key": "investment",
        "label": "Investment Scam (High Amount)",
        "icon": "🔴",
        "payee": SCENARIO_STORY["investment"]["payee"]["en"],
        "upi": SCENARIO_STORY["investment"]["upi"],
        "amount": SCENARIO_FEATURES["investment"]["amount_inr"],
        "note": SCENARIO_STORY["investment"]["note"]["en"],
        "phone": "9812345678",
        "account_id": "2002",
        "txn_id": 100002,
        "source_txn": SCENARIO_FEATURES["investment"]["source_txn"],
        "features": SCENARIO_FEATURES["investment"]["features"],
        "soft": {},
        "conf_set": SCAM,
        "reasons": [ENGLISH_REASONS["z_t"], ENGLISH_REASONS["e_t"], ENGLISH_REASONS["d_R"]],
        "network": True,
        "journey": [
            {"Day": 1, "Stage": "Hook", "Amount": 10_000.0, "Direction": "Sent"},
            {"Day": 2, "Stage": "Fake Profit", "Amount": 5_000.0, "Direction": "Received"},
            {"Day": 3, "Stage": "Trust", "Amount": 50_000.0, "Direction": "Sent"},
            {"Day": 5, "Stage": "Escalate", "Amount": 196_538.18, "Direction": "Sent"},
        ],
    },
    {
        "key": "police",
        "label": "Fake Police Call (Screen Shared)",
        "icon": "🔴",
        "payee": SCENARIO_STORY["police"]["payee"]["en"],
        "upi": SCENARIO_STORY["police"]["upi"],
        "amount": SCENARIO_FEATURES["police"]["amount_inr"],
        "note": SCENARIO_STORY["police"]["note"]["en"],
        "phone": "9000000001",
        "account_id": "3003",
        "txn_id": 100003,
        "source_txn": SCENARIO_FEATURES["police"]["source_txn"],
        "features": SCENARIO_FEATURES["police"]["features"],
        "soft": {"is_screen_shared": True, "chat_stage": "payment_demand"},
        "conf_set": UNSURE,
        "reasons": [ENGLISH_REASONS["d_R"], ENGLISH_REASONS["n_t"], ENGLISH_REASONS["g_t"]],
    },
    {
        "key": "unclear",
        "label": "Unclear Edge Case (Soft only)",
        "icon": "🟡",
        "payee": SCENARIO_STORY["unclear"]["payee"]["en"],
        "upi": SCENARIO_STORY["unclear"]["upi"],
        "amount": SCENARIO_FEATURES["unclear"]["amount_inr"],
        "note": SCENARIO_STORY["unclear"]["note"]["en"],
        "phone": "9123456789",
        "account_id": "4004",
        "txn_id": 100004,
        "source_txn": SCENARIO_FEATURES["unclear"]["source_txn"],
        "features": SCENARIO_FEATURES["unclear"]["features"],
        "soft": {"is_voice_active": True},
        "conf_set": UNSURE,
        "reasons": [
            "Amount is a little above this account's usual range",
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
st.session_state.setdefault("report", None)

model = load_model(str(MODEL_PATH)) if MODEL_PATH.exists() else None
conformal = load_json(str(CONFORMAL_PATH)) if CONFORMAL_PATH.exists() else {}
qhats = load_conformal(CONFORMAL_PATH) if conformal else None  # (qhat_fine, qhat_scam)
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
            st.session_state.report = None
            st.rerun()

    pin_sets = st.toggle(
        "Pin scripted conformal sets", value=False,
        help="Off: the live model + conformal.json decide each scenario's set. "
             "On: use each scenario's scripted set instead.",
    )

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
    if qhats:
        test = conformal.get("test", {})
        c1, c2 = st.columns(2)
        c1.metric("{fine} if p ≤", f"{qhats[0]:.4f}")
        c2.metric("{scam} if p ≥", f"{1 - qhats[1]:.4f}")
        c1.metric("scam coverage", f"{test.get('coverage_scam', test.get('coverage', 0)):.4f}")
        c2.metric("legit coverage", f"{test.get('coverage_fine', test.get('coverage', 0)):.4f}")
        st.caption(f"sets: {test.get('set_distribution', {})}")

sc = SCENARIOS_BY_KEY[st.session_state.scenario]

fri = check_fri(sc["phone"])
mh = check_mulehunter(sc["account_id"])

p_live = live_score(model, sc["features"]) if model is not None else None
implied_set = conformal_classify(p_live, *qhats) if p_live is not None and qhats else None
shap_rows = live_shap(model, sc["features"]) if model is not None else []
model_driven = implied_set is not None and not pin_sets
conf_set = implied_set if model_driven else sc["conf_set"]
reasons = (risk_reasons(shap_rows, sc["features"]) if model_driven else []) or sc["reasons"]

decision = decide(
    conf_set,
    sc["features"],
    sc["soft"],
    reasons,
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
                st.session_state.report = None

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
                        f"🧑💼 **Analyst review required** — amount exceeds {inr(HOLD_ANALYST_AMOUNT)}; "
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
                            rep = st.session_state.report
                            st.success(f"Report filed with NCRP (ref {rep['ref_id']}). Account blocked.")
                        elif st.session_state.released:
                            st.info("Auto-released before analyst review — no action available.")
                        else:
                            a1, a2 = st.columns(2)
                            if a1.button("Approve Release", width="stretch"):
                                st.session_state.analyst_action = "approved"
                                st.rerun()
                            if a2.button("File 1930 Report & Block", width="stretch"):
                                # File once on click; reruns reuse the stored filing.
                                st.session_state.report = file_1930_report(sc["txn_id"], sc["amount"])
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
                    st.success(f"Auto-released after {AUTO_RELEASE_MINUTES} minutes — payment sent.")
                elif st.button(f"⏭ Advance {AUTO_RELEASE_MINUTES} min (demo)", width="stretch"):
                    st.session_state.released = True
                    st.rerun()

    with right:
        st.subheader("🧮 Judge view")
        st.caption("Raw features, conformal set, and the exact policy.decide() output.")

        with st.expander("Raw features (t = now)", expanded=True):
            st.caption(f"Copied from real test-split txn #{sc['source_txn']}.")
            st.dataframe(pd.DataFrame([sc["features"]]), width="stretch", hide_index=True)

        with st.expander("Soft signals & conformal set", expanded=True):
            st.markdown("**Soft signals (mocked)**")
            st.json(sc["soft"] or {})
            st.markdown(f"**Conformal set used ({'live model' if model_driven else 'pinned script'})**")
            st.code(conf_set, language="text")
            if p_live is not None:
                st.metric("live model p_scam", f"{p_live:.4f}")
                st.caption(f"model-implied set: {implied_set} · scripted set: {sc['conf_set']}")

        with st.expander("Active hard / soft signals", expanded=False):
            st.json(active_signals(sc["features"], sc["soft"], DEFAULT_THRESHOLDS, mh, conf_set))

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
            rows = shap_rows[:3]
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
    st.caption(
        "Tune the six journey features, score them with the live model, and watch the "
        "Two-Signal Rule decide. Defaults are a typical legit payment (test-split medians). "
        "Each feature is applied to both payer and payee sides, and earlier payments to the "
        "same payee today are assumed to be the same size as this one (zc_t = z_t + log(1 + v_t)), "
        "so this is an approximation of a real 27-feature row."
    )
    f1, f2 = st.columns(2)
    amount = f1.slider("Amount (₹) — drives analyst review only", 1_000, 500_000, 50_000, step=1_000)
    n_t = f1.slider("n_t: new payees in last 7 days", 0, 100, 56)
    e_t = f1.slider("e_t: amount vs usual for a new payee", 0.0, 8.0, 0.01, step=0.01)
    z_t = f2.slider("z_t: amount z-score vs account history", -2.0, 9.0, 0.0, step=0.1)
    pi_t = f2.slider("pi_t: tiny probe payments within an hour", 0, 5, 0)
    d_r = f2.slider("d_R: hops to a reported account (3 = none within 2)", 0, 3, 2)
    v_t = f1.slider("v_t: earlier payments to this payee in 24 h", 0, 20, 0)
    ptr_t = f2.slider("ptr_t: share of 24 h inflow forwarded on", 0.0, 1.5, 0.4, step=0.05)
    s1, s2, s3 = st.columns(3)
    screen_shared = s1.toggle("Screen shared", value=False)
    voice_active = s2.toggle("Voice call active", value=False)
    chat_stage = s3.selectbox("Chat stage", ["none", "escalated", "payment_demand"])
    force_unsure = st.toggle(
        "Force the unsure set {fine, scam}", value=False,
        help="Skip the model and test the hard/soft-signal rule directly.",
    )
    st.divider()
    if st.button("Simulate Payment", type="primary", width="stretch"):
        features = {"n_t": float(n_t), "e_t": e_t, "g_t": 1.0, "z_t": z_t,
                    "pi_t": float(pi_t), "d_R": float(d_r), "v_t": float(v_t),
                    "zc_t": z_t + math.log1p(v_t), "ptr_t": ptr_t}
        soft = {"is_screen_shared": screen_shared, "is_voice_active": voice_active,
                "chat_stage": chat_stage}
        if force_unsure or model is None or not qhats:
            sandbox_set, p_sandbox = UNSURE, None
        else:
            p_sandbox = live_score(model, features)
            sandbox_set = conformal_classify(p_sandbox, *qhats)
        sandbox_reasons = risk_reasons(live_shap(model, features), features) if model is not None else []
        sandbox_decision = decide(sandbox_set, features, soft, reasons=sandbox_reasons,
                                  amount=float(amount))
        m1, m2 = st.columns(2)
        m1.metric("live model p_scam", "forced" if p_sandbox is None else f"{p_sandbox:.4f}")
        m2.metric("conformal set", sandbox_set)
        action = sandbox_decision["action"]
        if action == "release":
            st.success("✅ Release — Maya saw no risk and would let this payment through.")
        elif action == "nudge":
            st.warning("⚠️ Nudge — unusual signalling, but not enough to block the payment.")
        else:
            st.error(f"🛑 Hold — two independent signals agreed (auto-release in {sandbox_decision['auto_release_minutes']} min).")
        st.markdown("**Exact `policy.decide()` output**")
        st.json(sandbox_decision)
