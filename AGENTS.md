# AGENTS.md

## Status

Python 3.12 ML/AI project, no git repo. Sources: `src/journey_generator.py`
(synthetic UPI scam-journey data generator), `src/features.py` (Phase 2 past-only
feature engineering), the Phase 3 risk stack `src/risk_common.py`,
`src/train_xgb.py`, `src/conformal.py`, `src/reasons.py`, the Phase 4 action
engine `src/policy.py`, Phase 6 `src/attack_sim.py` (red-teaming) +
`src/integrations.py` (ecosystem mocks), the Phase 7 GNN challenger
`src/gnn_challenger.py` (PyTorch Geometric GraphSAGE), the Phase 8 federated
learning simulation `src/federated_sim.py` (FedAvg across two banks), the
FastAPI backend `api/main.py` (wraps `policy.decide` behind `/api/score`), and
the Next.js frontend `frontend/` (TypeScript + Tailwind, talks to the API). No
formatter/test framework yet.

- No package manager/venv chosen. `pip` is externally managed on this box and
  `python3-venv` is unavailable, so installs here need `pip3 install --user
  --break-system-packages -r requirements.txt`. Re-verify before assuming.
- There is no `pyproject.toml`, `Makefile`, or CI. Do not assume lint/test
  commands exist; check the repo state first.

## Commands

- Generate data (writes 3 CSVs into `data/`):
  - `python3 src/journey_generator.py` (full: 20k users / 120 days, ~28s)
  - `python3 src/journey_generator.py --smoke` (600 users / 30 days, <1s; use
    this to iterate)
  - Flags: `--out-dir`, `--seed`, `--users N`, `--days N`.
- Build Phase 2 features (`data/features.csv`):
  - `python3 src/features.py` (full: ~3.06M rows, ~2.5 min)
  - `python3 src/features.py --smoke` (uses `/tmp/opencode/maya_smoke/*`, ~5s)
  - Flags: `--txns`, `--edges`, `--labels`, `--out`, `--days`. Regenerating the
    dataset requires re-running features afterwards.
- Phase 3 risk stack (reads `data/features.csv`, writes `models/`):
  - `python3 src/train_xgb.py` (~45s; `--smoke` for a fast 100k-row subset)
  - `python3 src/conformal.py` (calibrate on val; `--txn-id N` to score one txn)
  - `python3 src/reasons.py --txn-id N` (SHAP top-3; `--demo K` for top-risk txns)
  - Flag paths are `--features/--model/--model-out/--meta-out/--out`.
- Phase 4 action engine (reads `models/` + `data/features.csv`):
  - `python3 src/policy.py --self-test` (asserts the full Two-Signal truth table)
  - `python3 src/policy.py --txn-id N --soft-signals '{"chat_stage": "escalated"}'`
  - `python3 src/policy.py --demo K --soft-signals '{...}'` (top-risk txns)
  - Flags: `--model/--features/--conformal/--amount`, threshold overrides
    (`--n-t-threshold --e-t-threshold --z-t-threshold --pi-t-threshold --d-r-max`).
- Streamlit demo UI (reads `models/`, no `data/features.csv` needed):
  - `streamlit run ui/app.py` (from repo root)
- Phase 6 red-teaming + ecosystem mocks:
  - `python3 src/attack_sim.py` (~30s; 100 rewording attacks, prints catch-rate
    drop, exits 0 iff Maya's drop < 10 pts)
  - `python3 src/integrations.py` (prints the mock FRI / MuleHunter / 1930 calls)
- Phase 7 GNN challenger (CPU-only torch, demo-only):
  - `python3 src/gnn_challenger.py --smoke` (3 epochs, fast sanity check)
  - `python3 src/gnn_challenger.py` (full GraphSAGE training + verdict table)
- Phase 8 federated learning simulation (FedAvg across two banks):
  - `python3 src/federated_sim.py --smoke` (row-sampled, fast)
  - `python3 src/federated_sim.py` (full: ~45s, prints local vs global table)
- FastAPI backend (wraps the Phase 4 policy engine):
  - `python3 -m uvicorn api.main:app --reload` (serves `POST /api/score`)
- Next.js frontend (in `frontend/`, talks to the API at `127.0.0.1:8000`):
  - `cd frontend && npm run dev` (dev server on `http://localhost:3000`)
  - `cd frontend && npm run build` (type-check + production build)
  - `cd frontend && npm run lint` (ESLint)
- There are no tests; `--smoke` plus the built-in `validate()` summary printed on
  each run is the verification step. A generator run is only healthy if
  `campaign_split_violations == 0` and `ref_integrity == True`. A feature run is
  healthy if every entry of `sample max|diff|` is `0.0` (optimized loop vs an
  independent past-only brute force on 300 sampled txns).

## Phase 2 feature specifics (non-obvious)

- `src/features.py` is **strictly past-only**: every feature for a txn uses only
  rows with `ts < T` (same-second events are batched out, not included).
- Features are computed per endpoint (sender and receiver) and combined as the
  more anomalous (`n_t`/`e_t`/`pi_t` = max, `g_t` = OR, `z_t` = larger `|z|`,
  `d_R` = min). Per-side columns (`*_snd`, `*_rcv`) are kept in the output.
- `d_R` = min hops (<=2, cap `3`) from the txn's endpoints to a reported account in
  the directed `graph_edges` graph, time-sliced per day (`first_ts < day`) and
  gated by `labels.report_day < day` (leakage-safe).
- The combined `n_t`/`e_t` exclude business endpoints (hub accounts, i.e.
  employers/merchants, would otherwise dominate `n_t`); the per-side `*_snd`/
  `*_rcv` columns still include them. Other combined features are unaffected.
- Normal P2P generation makes ~2% of txns tiny probes (₹1/5/10), created before
  campaigns, so `pi_t` is nonzero (~0.2M rows full data).
- Remaining data caveat: `g_t` is near-constant (~0.997) on this synthetic
  random-friend graph (users keep receiving first-contact credits).

## Phase 3 risk model specifics (non-obvious)

- `src/risk_common.py` is the single source of truth: `FEATURE_COLUMNS` (18 = 6
  combined + 12 `_snd`/`_rcv`) and `ENGLISH_REASONS`. Import it; do not duplicate
  the feature list in the three scripts. `data/features.csv` also has `txn_id`,
  `ts`, `day`, `split`, `sender_id`, `receiver_id`, `amount`, `is_scam`.
- Model: `XGBClassifier(tree_method="hist")`, `scale_pos_weight = neg/pos (~987)`,
  early stopping on val AUC-PR. Test metrics currently AUROC 0.9983, AUPRC 0.913,
  recall@1%FPR 0.969 (threshold chosen on val, reported on test).
- Conformal is a **manual LAC** implementation (not MAPIE): nonconformity
  `1 - p(true class)`, `qhat` saved in `models/conformal.json`. Sets are only
  `{fine}`, `{scam}`, or `{fine, scam}`; the ambiguous middle band maps to
  `{fine, scam}`, so sets are never empty and coverage is never degraded.
- Caveat: with ~0.09% positives, marginal 90% coverage is easy (`qhat` is tiny),
  so `{scam}` singletons are rare and most scam hits are `{fine, scam}`. Use
  Mondrian/class-conditional calibration if a scam-specific guarantee is needed.
- SHAP uses log-odds (`TreeExplainer` on the booster), with native
  `pred_contribs=True` fallback for NaN rows; positive SHAP increases scam risk.
- `models/*.json` are generated artifacts; do not commit them alongside `data/`.

## Phase 4 action policy specifics (non-obvious)

- `src/policy.py` implements the **Two-Signal Rule**. `decide()` is a pure,
  I/O-free function returning exactly `{action, reasons, auto_release_minutes,
  requires_analyst}`; `reasons` are the 3 SHAP English strings from `reasons.py`.
  Actions: `release` / `nudge` / `hold`. Hold => 60 min auto-release.
- Rule by conformal set: `{fine}` -> release; `{scam}` -> hold; `{fine, scam}`
  (unsure) -> hold iff (payment-hard AND receiving-hard) OR (>=1 hard AND >=1
  soft), else nudge. Chat/voice/screen-share are **soft only** and can never hold
  alone.
- Hard signals: Payment History family `n_t/e_t/z_t/pi_t`, Receiving Account
  family `d_R`. Defaults (val-percentile informed, CLI-overridable): `n_t>=59`,
  `e_t>=1.0`, `z_t>=2.6`, `pi_t>=1`, `d_R<=1`. `n_t` is a weak discriminator on
  this data (scam median 50 vs overall 46) so its bar is deliberately high.
- **MuleHunter.AI integration**: `decide()` takes an optional `mulehunter_status`
  (from `integrations.check_mulehunter`); a `"mule"` verdict **while the conformal
  set is `{fine, scam}`** counts as a Receiving Account hard signal. It is ignored
  for `{fine}`/`{scam}` and for `"suspicious"`/`"clean"`. `decide()` stays pure
  (status is a plain input); the mock I/O happens in `run()`/the UI.
- Soft signals (mocked input): `is_screen_shared`, `is_voice_active`, and
  `chat_stage` in `{escalated, payment_demand}`.
- `requires_analyst` is True **only when the action is hold and amount > ₹100k**
  (not for release/nudge). Thresholds are a frozen `Thresholds` dataclass.
- Verification is `python3 src/policy.py --self-test` (20-case truth table,
  incl. 7 MuleHunter cases).

## Phase 6 specifics (non-obvious)

- `src/integrations.py` is dependency-free and deterministic (sha256 hashes +
  a small `KNOWN_ACCOUNTS` table so the UI scenarios hit known statuses). It
  mocks the DoT FRI (`check_fri`), MuleHunter.AI (`check_mulehunter`), and the
  NCRP 1930 portal (`file_1930_report`). `known accounts`: `1001`/`4004` clean,
  `2002`/`3003` mule.
- `src/attack_sim.py` red-teams the model with AI-rewritten chat scripts. Maya's
  "catch rate" is recall at the val-chosen 1%-FPR threshold (`model_meta.json`);
  because the 18 features are journey/money-flow only (no text), rewording is a
  no-op and the drop is 0.0 pts. A phrase-matching "text-only detector" is
  included as the contrast, collapsing by `REWORD_EVASION = 0.88` (the PDF figure).
  Exits 0 iff Maya's drop < `--drop-target` (default 10 pts). Reads full
  `data/features.csv` (~30s); no `--smoke`.

## Phase 7 GNN challenger specifics (non-obvious)

- `src/gnn_challenger.py` builds the PDF's GraphSAGE challenger: a 2-layer
  `SAGEConv` node classifier that predicts `labels.is_mule` (60 mules) from the
  account graph (`data/graph_edges.csv`, mapped `vpa -> node index`).
- Node features are leakage-free graph statistics only (`log1p` in/out/total
  degree); `role` and its derivatives (`is_mule`, `is_aggregator`, ...) are
  deliberately excluded so the model must learn mule-ness from neighbourhood
  structure (2-hop receptive field over the `victim -> entry mule -> mid mule ->
  aggregator` relay).
- Transductive (full undirected graph, node masks from `labels.split`); `shortcut:`
  not time-sliced — `graph_edges` is the aggregated full-history graph, upgrade to
  per-day edge slicing via `first_ts` for a true past-only comparison.
- Class imbalance handled via `BCEWithLogitsLoss(pos_weight = neg/pos on train)`;
  early stop (patience 25) on val AUROC. `labels.split` is heavily skewed
  (train ~21.2k / val 78 / test 63) so the test AUROC is high-variance.
- The verdict table compares **different targets** on purpose: champion
  `test_auroc` (0.9983) is txn-level `is_scam`, the GNN AUROC is account-level
  `is_mule`; the script labels both and does not roll the champion up to accounts.
  Conclusion: GNN slightly better at hidden multi-hop mule networks, but needs the
  whole graph resident at inference, so XGBoost stays in the 150 ms hot path.

## Phase 8 federated learning simulation (non-obvious)

- `src/federated_sim.py` simulates horizontal FedAvg across two banks: customers
  are split by `sender_id` (first half -> Bank A, rest -> Bank B) so each bank
  holds disjoint customers and no raw data is shared.
- Each bank trains a local `XGBClassifier` on its own train split (same
  hyperparameters as `train_xgb.py`: hist / aucpr / n_estimators=400 / depth 6 /
  lr 0.1 / early stop 40) with per-bank `scale_pos_weight`.
- `fedavg()` averages the two models' **raw margins**
  (`predict(..., output_margin=True)`) and passes the mean through sigmoid — the
  correct FedAvg for heterogeneous (non-aligned) tree ensembles. `base_score` is
  identical (0.5) in both models so averaging it is a no-op; true tree-weight
  averaging is ill-defined when the trees don't share structure.
- Evaluates both locals and the global on the **shared** test split (both banks):
  AUROC + recall@1%FPR (threshold chosen at 1% FPR on each model's own val; the
  global uses the combined val). The global beats both locals because each local
  is diluted by the other bank's unseen customers.
- `--smoke` row-samples train/val/test (100k/20k/20k) for a fast check; the smoke
  test has ~13 positives so its AUROC/recall are high-variance — the full run is
  the real number.

## FastAPI backend specifics (non-obvious)

- **API key auth**: `/api/score` and `/api/score-trace` require the header
  `X-API-Key: sk_live_maya_enterprise` (else `401`) via the `require_api_key`
  FastAPI dependency. `/health`, `/api/metrics`, and the other endpoints are
  unprotected. `GET /health` returns `{status, model_version: "maya-v1", uptime}`.
- `api/main.py` exposes `POST /api/score` (Pydantic `Transaction`: `amount: float`,
  `d_R: int`, `z_t: float`, plus optional `e_t/g_t/pi_t: float = 0.0`,
  `is_screen_shared: bool = False`, `chat_stage: str = "none"`,
  `intent_claim: str = "none"`, `payment_direction: str = "outgoing"`,
  `mulehunter_status: str | None = None`). CORS is scoped to `http://localhost:3000`.
- `src/` has no `__init__.py`, so the API injects `ROOT/src` onto `sys.path` and
  imports `from policy import decide` (same pattern as `ui/app.py`). At startup it
  loads `models/xgb_model.json`, `models/conformal.json` (qhat), and a SHAP
  `TreeExplainer` (`make_explainer`) once — this pulls numpy/xgboost/shap at
  import time (~1-2s), reused across requests.
- Two-stage pipeline: `jev_triage(amount, d_R)` mock-releases trivial safe txns
  (`amount < 1000 and d_R == 3`), else escalates to `decide()` with the conformal
  set **pinned to `{fine, scam}`** (same reasoning as the Sandbox tab — the only
  branch where the sliders/inputs change the outcome). `/api/score` ignores the new
  `e_t/g_t/pi_t/chat_stage` fields for now (it hardcodes `n_t/e_t/g_t/pi_t` to 0
  and only uses `z_t`/`d_R`/`is_screen_shared`).
- The response is **normalized** to `decide()`'s 4-field shape
  (`action`/`reasons`/`auto_release_minutes`/`requires_analyst`) on both the
  release and escalate paths so the frontend sees one contract.
- `POST /api/score-trace` returns a `TraceResponse` (`triage` {path, reason},
  `features` (the 6 raw features), `conformal_set`, `shap_reasons` (3 real SHAP
  strings), `signals_fired` {hard, soft}, `final_decision` {action,
  auto_release_minutes, requires_analyst}, `evidence_sources` (list of
  `{signal, source, source_id}`), `decision_signature` (SHA-256 of the
  `final_decision` JSON)). `features` uses the client's `z_t/e_t/g_t/pi_t` (with
  `n_t` set to a realistic `5.0` baseline), and `chat_stage` feeds the soft
  signals (alongside `is_screen_shared`). The slow path runs the REAL pipeline:
  `to_model_row()` mirrors the 6 combined features into `_snd`/`_rcv` to build an
  18-col row, then `predict_proba()` → `conformal_classify(p_scam, qhat)` (real
  set, no heuristic) → `shap_matrix()`/`top_reasons()` (with `native_contrib`
  fallback) → `decide()`. The fast path (jev_triage releases) short-circuits to
  `{fine}` + 3 hardcoded benign strings without touching the model.
  `signals_fired` reuses `active_signals()` with `DEFAULT_THRESHOLDS`.
- Provenance + intent: `build_evidence_sources(features, mulehunter_status)`
  marks `d_R` (graph) and `mulehunter` as sharing `source_id="report_123"` when
  `d_R <= 1` AND `mulehunter_status == "mule"` (so they aren't double-counted —
  `decide()` already ORs them into one "receiving" hard signal). `txn.mulehunter_status`
  is passed through to `decide()`/`active_signals()`. An **Intent Contradiction**
  (`intent_claim == "receive_refund"` + `payment_direction == "outgoing"`) is
  caught at the TOP of `/api/score-trace` (before fast/slow) and returns an
  immediate HOLD trace with the reason "Intent Contradiction: Claimed refund but
  initiating outgoing payment."
- `GET /api/metrics` returns the REAL metrics read from `models/model_meta.json`,
  `models/conformal.json`, and (when present) `models/gnn_meta.json`,
  `models/fedavg_meta.json`, `models/red_team_meta.json`:
  `{xgbAuroc: meta.test_auroc, auprc: meta.test_auprc, qhat: conf.qhat, alpha:
  conf.alpha, datasetSize: meta.total_rows, gnnAuroc, fedavgAuroc, redTeamDrop}`.
  The three research-derived keys fall back to `null` (not 0.0) when their JSON
  file is missing — the frontend renders `"N/A"` for null values.
  `model_meta.json` was extended with `val_rows`/`test_rows`/`total_rows` (real
  split counts) so `datasetSize` is 3,054,055 without being hardcoded.
- `POST /api/evaluate-journey` (Pydantic `JourneyRequest`: `timeline: list[TimelineEvent]`
  `{amount, payee_id, direction}`, `current_amount`, `current_payee_id`) is a
  pre-ML heuristic scorer returning `JourneyResponse {journey_risk_score, flags}`.
  Three flags weighted 40/30/30: `small_payment_before_credit` (outgoing <₹1,000
  then an incoming credit), `new_payee` (current payee not in timeline),
  `amount_spike` (current > 3× timeline mean); score = sum, capped 100.
- `POST /api/circuit-breaker` (Pydantic `CircuitBreakerRequest`:
  `reported_mule_id: str`) is a REAL Scam DNA circuit breaker: it lazily loads
  `data/transactions.csv` (`usecols=[sender_id, receiver_vpa, amount, ts]`, cached
  once), filters `receiver_vpa == reported_mule_id`, returns
  `victims_alerted = sender_id.nunique()`, the top-3 at-risk transactions by
  `amount` (`{amount, time}`), and `status: "alerts_sent"`. The frontend passes a
  real mule VPA (`u000849@okhdfcbank`).
- **Private Mode** (raw-text privacy): `POST /api/extract-claim` (Pydantic
  `ClaimRequest {chat_message: str}` → `ClaimResponse {intent_claim,
  processed_in_memory: true}`) runs a mock keyword `_extract_intent` (refund→
  receive_refund, fee/payment→pay_fee, buy/purchase→buy_item, else none) entirely
  in memory — the `chat_message` is never logged, persisted, or printed, and the
  raw string is never echoed back. `POST /api/privacy-canary`
  (`CanaryRequest {message: str}`) is a mock proof returning
  `{status: "processed", stored: false, network_sent: false}`. Verified by
  `/tmp/opencode/test_privacy.py` (intent + no-stdout-leak via `redirect_stdout`
  + canary flags).
- **Legitimate User Recourse**: `POST /api/request-review` (Pydantic
  `ReviewRequest {trace_id: str, reason: str}` → `ReviewResponse {status,
  reference_id, message}`) returns `status: "review_requested"` and a
  deterministic `reference_id: "REQ-" + sha256(f"{trace_id}:{reason}")[:8].upper()`
  (matching `integrations.py`'s NCRP pattern) with the fixed message "An
  independent analyst will review this shortly."

## Next.js frontend specifics (non-obvious)

- `frontend/` was scaffolded with `create-next-app` (TypeScript, Tailwind v4,
  ESLint flat config, App Router, `src/` dir, `@/*` alias, npm). Next.js 16.4.3 /
  React 19.3.0. Tailwind v4 needs no `tailwind.config` file (CSS-first).
- `frontend/src/lib/api.ts` exports the `Transaction`/`Decision` types mirroring
  the Pydantic model + 4-field response and `scoreTransaction(data)` (POSTs to
  `/api/score`), plus the Judge View types `FinalDecision`/`TraceResponse` and
  `fetchTrace(data)` (POSTs to `/api/score-trace`). All return `res.json()`.
  `Transaction` now has optional `e_t?/g_t?/pi_t?: number`, `chat_stage?: string`,
  `intent_claim?/payment_direction?: string`, `mulehunter_status?: string | null`.
  `TraceResponse` carries `evidence_sources: EvidenceSource[]`
  (`{signal, source, source_id: string | null}`) and `decision_signature: string`,
  and `triage.path` is `"fast" | "slow" | "intent"`. It exports `SCENARIOS` (6 demo
  scenarios whose `payload` carries all 8 fields — the Fake Police and Unclear
  scenarios set `g_t: 1.0`; the Fake Police one is titled "…(Priya Alert + Screen
  Share)" and sets `intent_claim: "pay_fee"` + `payment_direction: "outgoing"`; the 6th "Intent Contradiction (Refund Scam)" sets
  `intent_claim: "receive_refund"` + `payment_direction: "outgoing"`; Scenario 2
  (Investment) and Scenario 6 also set `mulehunter_status: "mule"` so Scenario 2's
  `d_R: 1` + mule shows the shared `source_id: "report_123"` provenance), a
  `Metrics`
  type + `fetchMetrics()` (GETs `/api/metrics`), `fetchCircuitBreaker(muleId)` +
  `AtRiskTransaction`/`CircuitBreakerResponse` types (POSTs `{reported_mule_id}` to
  `/api/circuit-breaker`), and `extractClaim(data)` +
  `ClaimRequest`/`ClaimResponse` types (POSTs `{chat_message}` to
  `/api/extract-claim`), and `requestReview(data)` +
  `ReviewRequest`/`ReviewResponse` types (POSTs `{trace_id, reason}` to
  `/api/request-review`). The hardcoded `PROJECT_METRICS` object was removed.
- `frontend/src/components/Navbar.tsx` is a permanently-dark top navbar (title
  "Maya — AI Fraud Engine" + a green `animate-ping` pulse dot with "System
  Online"). It is rendered at the top of `app/layout.tsx` (the layout sets the
  body to `min-h-screen bg-zinc-950 font-sans text-white`).
- `frontend/src/app/page.tsx` is the "Pipeline Storyteller" dashboard: a fixed
  left sidebar (`w-1/3`, sticky) + a main right story area (`flex-1`). The sidebar
  has a red "Circuit Breaker" button (top) that calls `fetchCircuitBreaker("mule_123")`
  and shows a "⚠️ Circuit Breaker Triggered" banner + at-risk table in the story
  area, a "System Metrics" card that fetches `/api/metrics` via `useEffect` on
  mount and renders 8 metrics through a `formatMetric` helper (bold gradient text
  values; `null` → "N/A") — the 5 core metrics plus dynamic `gnnAuroc`/`fedavgAuroc`/
  `redTeamDrop` read from the research scripts' JSON outputs. A bottom section toggles between the 5
  `SCENARIOS` buttons and a Sandbox form. The Sandbox form's top is a "Jury
  Workbench" block (a green "🔒 Private Mode: Raw text processed in memory only."
  badge + a "Raw Chat Message (Untrusted)" `textarea` + an "Extract Intent &
  Auto-Fill" button that calls `extractClaim()` and auto-fills `intent_claim`
  (setting `payment_direction="outgoing"` when the extract is `receive_refund`) with
  an inline "✓ Intent extracted: … Text was not stored." toast), then a divider and
  a "Manual Override" form (6 number inputs Amount/d_R/z_t/e_t/g_t/pi_t, a Screen
  Shared checkbox, Chat Stage + Intent Claim + Payment Direction + MuleHunter
  Status `<select>`s, and a "Simulate Custom Trace" button). Both
  scenarios and the
  sandbox call `fetchTrace` and render a vertical stepper of the ML pipeline (local
  `Step`/`Badge`/`Icon` components, inline SVG icons): Step 1 Raw Input
  (amount/d_R/screen-shared from the submitted `payload`), Step 2 System-1 Triage
  (fast→emerald / intent→red / slow→amber badge + reason), Step 3 Conformal
  Prediction (qhat/alpha from the fetched `metrics`, set from the trace), Step 4
  Explainability (up to 3 SHAP reasons), Step 5 Two-Signal Policy (hard=red /
  soft=amber badges), Step 6 Final Action (massive tinted box; when `nudge`/`hold`
  shows a "This was a mistake / Request Review" button that opens an inline
  recourse panel — "Submit Request" calls `requestReview({trace_id:
  decision_signature, reason})` and shows the `reference_id`/`message` in a green
  box, and "Simulate Analyst Approval" flips `reviewApproved` → green Release;
  also renders a rose/pink "🚨 Priya Alert Triggered…" banner when `hold` AND the
  scenario name includes "Priya" AND `!reviewApproved`),
  Step 7 Analyst Review (only when `requires_analyst`; the fixed note + mock
  Approve Release / File 1930 Report buttons). A tab bar (Pipeline | Evidence &
  Audit) wraps the stepper; the "Evidence & Audit" tab shows three cards — "Intent
  Verification" (`payload.intent_claim` vs `payment_direction`, red alert on
  refund+outgoing contradiction), "Evidence Sources" (maps `trace.evidence_sources`),
  and "Signed Audit Record" (`trace.decision_signature` in monospace + lock icon).
  The old sliders/3-tab Simulator were removed.

## Data generator specifics (non-obvious)

- Determinism via `seed=42` and per-namespace RNGs (`make_rng`), so a given seed
  reproduces byte-identical output.
- Outputs: `data/transactions.csv` (per-txn), `data/graph_edges.csv`
  (aggregated `src->dst`), `data/labels.csv` (per account/node). Styles: scam
  journeys are 5 stages across 3 types (investment, digital arrest, sextortion);
  money is layered `victim -> entry mule -> mid mule -> aggregator -> exit`.
- **Leakage control is the point**: split is by contiguous day blocks
  (train/val/test = 60/20/20); every scam campaign is confined to one split.
  `transactions.split` comes from `day`; `graph_edges.split` is the plurality
  split of the edge's txns; `labels.split` is the campaign split for scam
  accounts, otherwise the plurality split of the account's txns.
- Reports are deliberately *slow and partial*: `is_reported`, `report_day`,
  `report_delay_days`, `report_coverage`, and per-txn `is_in_report`. Both
  `ground_truth_label` and `reported_label` are in `labels.csv`; do not treat
  `reported_label` as ground truth.
- `data/*.csv` are regenerated artifacts (transactions ~350 MB, features ~670 MB);
  they are not tracked and should not be committed.

## UI specifics (non-obvious)

- `ui/app.py` is a Streamlit demo (`streamlit run ui/app.py` from repo root). It
  adds `src/` to `sys.path` and imports the real `policy.decide`, `conformal`,
  and `risk_common`; it does **not** need `data/features.csv` (scenarios are
  synthetic feature rows) but does load `models/xgb_model.json` +
  `models/conformal.json` for the live `p_scam` and SHAP panel.
- Four hardcoded scenario buttons: normal (`{fine}` -> release), investment scam
  (`{scam}` -> hold, `requires_analyst` at Rs 2,00,000), fake-police screen-share
  (unsure, 1 hard + soft -> hold + "Priya Alerted" panel), and soft-only unclear
  (unsure, 0 hard -> nudge with a "Pay anyway" second click).
- Each scenario also carries a `phone` / `account_id` / `txn_id` so the UI calls
  the real `integrations.check_fri` + `check_mulehunter` mocks and passes the
  MuleHunter status into `decide()`. Scenario account ids map to known statuses
  (normal/unclear -> clean, investment/police -> mule).
- **Analyst Dashboard**: shown only when `requires_analyst` is True (held AND
  amount > Rs 1 Lakh — just the investment scenario). It shows the mock FRI score
  and MuleHunter status plus two buttons ("Approve Release" / "File 1930 Report &
  Block") driven by `st.session_state.analyst_action`; the report button calls
  `file_1930_report` and shows the NCRP ref id.
- **Scam DNA graph**: the investment scenario (held) also renders a directed
  Plotly/NetworkX money-flow graph below the SHAP reasons when the user clicks
  Pay — `victim -> entry mule -> layering -> aggregator -> crypto exit` — gated on
  `sc.get("network")`. Built by `scam_dna_figure()` (lazy `import plotly` /
  `networkx`); `plotly` was added to `requirements.txt`.
- **Transaction Journey**: the investment scenario also shows a 4-row Pandas
  dataframe under the payment block (`Day`/`Stage`/`Amount`/`Direction`), in a
  `📈 Transaction Journey` expander, gated on `sc.get("journey")`.
  `journey_dataframe()` applies a Styler: the final "Escalate" row is red+bold,
  the "Fake Profit" row (a credit) is green. Day 5 amount = the scenario's
  `amount` (Rs 2,00,000).
- **Tabs**: the page body is split into two `st.tabs` — "Scenario Demo" (all the
  scenario UI above) and "Sandbox Mode". The sidebar (scenario buttons + model
  metrics) stays global, outside the tabs.
- **Sandbox Mode** (second tab): free-form inputs to exercise the Two-Signal Rule
  directly. `st.slider` for Amount (₹1,000–₹5,00,000, step ₹1,000) and Mule Hops
  (0–3), plus a `st.toggle` for Screen Shared. "Simulate Payment" builds a mock
  feature dict (`n_t/e_t/g_t/pi_t = 0`, `z_t = amount/100_000` i.e. ₹ in lakhs,
  `d_R = mule_hops`) and soft dict (`is_screen_shared`), then calls `decide()`
  with the conformal set **pinned to `{fine, scam}`** (the only branch where the
  sliders change the outcome). Result is transient (recomputed on click only):
  Release/Nudge/Hold via `st.success`/`warning`/`error`, with the exact
  `decide()` JSON below it.
- Design choice: the **scenario's pinned conformal set** drives `decide()` (so
  the demo matches the spec deterministically); the model-implied set from the
  live `p_scam` is shown next to it in the judge view for reference. The 6
  combined features are mirrored into the `*_snd`/`*_rcv` columns to feed the
  18-col model.
- Hold shows a static 60-min auto-release badge plus an "Advance 60 min (demo)"
  button (no live countdown / no auto-refresh).

## Layout

- `src/` — application code and entrypoints
- `scripts/` — `bank_simulator.py` (High-Throughput UPI Switch Simulator: 100 mock
  txns via `rich`/`requests`, live progress bar + `rich.table` BANK SWITCH REPORT +
  red "❌ CRITICAL ALERTS BLOCKED BEFORE NPCI" banner; `--n`/`--seed`/`--release`)
- `api/` — FastAPI backend (`main.py`)
- `ui/` — frontend / user interface
- `frontend/` — Next.js web app (TypeScript + Tailwind)
- `models/` — model code or weights
- `data/` — datasets (generated)
- `docs/` — documentation: `METRICS_REPORT.md` (real model metrics + coverage +
  benchmarking + known gaps), `FAILURE_REGISTER.md` (F01–F12 failure/mitigation
  table), `DELIVERY_LEDGER.md` (phase-by-phase status + files), `PILOT_BLUEPRINT.md`
  (shadow-mode deployment + rollback)
