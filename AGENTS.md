# AGENTS.md

## Status

Python 3.12 ML/AI project, no git repo. Sources: `src/journey_generator.py`
(synthetic UPI scam-journey data generator), `src/features.py` (Phase 2 past-only
feature engineering), the Phase 3 risk stack `src/risk_common.py`,
`src/train_xgb.py`, `src/conformal.py`, `src/reasons.py`, the Phase 4 action
engine `src/policy.py`, Phase 6 `src/attack_sim.py` (red-teaming) +
`src/integrations.py` (ecosystem mocks), the Phase 7 GNN challenger
`src/gnn_challenger.py` (PyTorch Geometric GraphSAGE), and the Phase 8 federated
learning simulation `src/federated_sim.py` (FedAvg across two banks). No
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
- `ui/` — frontend / user interface
- `models/` — model code or weights
- `data/` — datasets (generated)
- `docs/` — documentation
