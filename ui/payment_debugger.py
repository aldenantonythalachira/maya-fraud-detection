"""Run: python -m streamlit run ui/payment_debugger.py"""
import json
import sys
import time
import uuid
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from demo_scenarios import SCENARIOS, scenario
from payment_review import ModelAdapter, PaymentService

st.set_page_config(page_title="MAYA | Payment review", page_icon="🛡️", layout="wide")
st.markdown("""<style>
.stApp {background:#20211f;color:#f4eddd} h1,h2,h3 {font-family:Georgia,serif}
[data-testid="stMetricValue"] {font-family:monospace}
.stButton>button {border-color:#d5864b} .stButton>button[kind="primary"] {background:#d5864b;color:#20211f}
</style>""", unsafe_allow_html=True)
st.title("He typed his own PIN every time.")
st.caption("MAYA connects the story you were told to the payment you are about to make.")
st.info("Local simulator • synthetic identities and evidence • no real payment or notification is sent")
model_path, calibration_path = ROOT / "models/xgb_model.json", ROOT / "models/conformal.json"
if not model_path.exists() or not calibration_path.exists():
    st.warning("Build the synthetic baseline using the four commands in README.md, then reload.")
    st.stop()

@st.cache_resource
def adapter(model_stamp, calibration_stamp):
    return ModelAdapter(str(model_path), str(calibration_path))

if "debugger_service" not in st.session_state:
    st.session_state.offset = 0
    st.session_state.payer_session = uuid.uuid4().hex
    (ROOT / "data").mkdir(exist_ok=True)
    st.session_state.debugger_service = PaymentService(
        adapter(model_path.stat().st_mtime_ns, calibration_path.stat().st_mtime_ns),
        str(ROOT / "data/reviews.sqlite"), clock=lambda: time.time() + st.session_state.offset)
service = st.session_state.debugger_service
session = st.session_state.payer_session

with st.sidebar:
    st.header("Demo controls")
    selected = st.selectbox("Scenario", list(SCENARIOS))
    reset = st.button("Start a new payment")
    view = st.radio("View", ["Payment review", "Analyst evidence", "Judge challenges"])
    st.caption("Live XGBoost inference on a small synthetic journey adapter. The adapter mirrors endpoint features, as the baseline demo does; it is not the production feature pipeline.")
    coverage = json.loads(calibration_path.read_text()).get("test", {}).get("coverage")
    if coverage is not None:
        st.caption(f"Local smoke calibration coverage: {coverage:.2%}. Target: 90%.")

if reset or st.session_state.get("selected_scenario") != selected:
    s = scenario(selected, service.clock())
    st.session_state.fixture = s
    st.session_state.payment_id = service.create(session, s["recipient"], s["amount_paise"])["id"]
    st.session_state.review_id = None
    st.session_state.parent_review = None
    st.session_state.selected_scenario = selected
    st.session_state.recipient_input = s["recipient"]
    st.session_state.amount_input = s["amount_paise"] // 100
    st.session_state.claim_input = s["text"]
    st.session_state.consent_input = True
    st.session_state.confirm_input = False

s = st.session_state.fixture
pid = st.session_state.payment_id
p = service.get(pid, session)
st.subheader("Review your payment")
left, right = st.columns([3, 2])
with left:
    recipient = st.text_input("Recipient", key="recipient_input", disabled=p["state"] != "pending")
    amount = st.number_input("Amount (₹)", min_value=1, max_value=1_000_000, step=100, key="amount_input", disabled=p["state"] != "pending")
    if p["state"] == "pending" and (recipient != p["recipient"] or amount * 100 != p["amount_paise"]):
        try:
            p = service.change(pid, session, recipient, int(amount) * 100)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
    text = st.text_area("Voluntarily shared message", key="claim_input", max_chars=2000)
    consent = st.checkbox("Use this synthetic message for this review", key="consent_input")
    st.caption("Shared text is processed and saved locally with consent. No screenshot, PIN, contact list or call audio is collected.")
    if st.button("Review payment", type="primary", disabled=p["state"] != "pending"):
        r = service.review(pid, session, s["evidence"], text, consent, st.session_state.parent_review)
        st.session_state.review_id = r["id"]
        st.session_state.confirm_input = False

rid = st.session_state.review_id
r = service.replay(rid, session) if rid else None
with right:
    st.metric("Pending outgoing payment", f"₹{p['amount_paise']/100:,.2f}")
    st.write(f"Recipient: **{p['recipient']}**")
    st.caption(f"Revision {p['revision']} · {p['state']}")
    if r:
        outcome = r["outcome"]
        stale = r["payment"] != p or r["shared_text"] != (text if consent else "") or r["consent"] != consent
        expired = service.clock() >= r["expires_at"]
        if stale or expired:
            st.warning("This review is no longer current. Review the payment again.")
        display = {"release": st.success, "nudge": st.warning, "hold": st.error}[outcome["action"]]
        display({"release": "Review complete", "nudge": "Pause and check", "hold": "Payment held for review"}[outcome["action"]])
        for reason in outcome["reasons"]:
            st.write("• " + reason)
        st.write("Message comparison: " + outcome["comparison"].replace("_", " "))
        if outcome["claim"]["status"] in ("unclear", "not_shared"):
            st.caption("MAYA could not establish the message's meaning. This is not a finding that it is safe.")
        confirmed = st.checkbox("I understand the warning and confirm this simulated payment", key="confirm_input")
        if st.button("Send simulated payment", disabled=stale or expired or p["state"] != "pending"):
            try:
                service.execute(pid, session, rid, confirmed)
                st.success("Simulated payment completed. No money moved.")
            except ValueError as exc:
                st.error(str(exc))
    if st.button("Cancel payment", disabled=p["state"] != "pending"):
        service.cancel(pid, session)
        st.rerun()

if r and view != "Payment review":
    st.divider()
    st.subheader("Evidence available at this review")
    st.caption("Evidence templates explain observed facts; they are not SHAP attributions. Scores are restricted to this synthetic analyst/judge view.")
    st.write(f"Model set: {r['outcome']['uncertainty']} · score: {r['outcome']['score']:.4f}")
    st.dataframe(r["evidence"], hide_index=True)
    edges = [e for e in r["evidence"] if e["kind"] == "edge"]
    if edges:
        # JSON escaping prevents evidence labels from injecting DOT syntax.
        st.graphviz_chart('digraph { ' + ' '.join(f'{json.dumps(e["source"])} -> {json.dumps(e["target"])};' for e in edges) + ' }')
    with st.expander("Saved inputs, features and versions"):
        st.json(r)
    st.download_button("Download original review", json.dumps(r, indent=2), file_name=f"review-{rid}.json", mime="application/json")
    if st.button("Replay original and verify"):
        try:
            service.replay(rid, session, recompute=True)
            st.success("Original outcome reproduced with matching versions.")
        except ValueError as exc:
            st.error(str(exc))

if r and view == "Judge challenges":
    st.subheader("Change one fact")
    st.caption("Edit the recipient or amount above, then attempt to reuse the old review. The service also rejects stale reviews independently of the UI.")
    if st.button("Attempt old review at service boundary"):
        current = service.get(pid, session)
        if current == r["payment"]:
            st.info("Change the recipient or amount first; this challenge does not execute an unchanged payment.")
        else:
            try:
                service.execute(pid, session, rid, True)
                st.error("Unexpected execution")
            except ValueError as exc:
                st.success(f"Rejected: {exc}")
    if st.button("Delay report and evaluate separate scenario"):
        import copy
        changed = copy.deepcopy(s)
        for e in changed["evidence"]:
            if e["kind"] == "report":
                e["available_at"] = service.clock() + 86400
        new = service.create(session, p["recipient"], p["amount_paise"])
        child = service.review(new["id"], session, changed["evidence"], text, consent, parent=rid)
        st.write(f"Original: {r['outcome']['action']} → changed scenario: {child['outcome']['action']}")
        st.caption("This is a separate counterfactual payment. The original record and any original hold remain intact.")
        st.json(child)
    if st.button("Advance simulator clock one hour"):
        st.session_state.offset += 3600
        st.info("Clock advanced. Obtain a fresh review and explicitly confirm before execution.")
    if st.button("Simulated analyst approval"):
        try:
            service.approve_by_analyst(pid, session, rid)
            st.success("Approval recorded for this exact revision. The hold timer still applies.")
        except ValueError as exc:
            st.error(str(exc))
