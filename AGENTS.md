# AGENTS.md

## Finale changes (2026-10-20; supersedes older status below)

- This is now a Git repository. All changes use feature branches and PRs.
- Core setup uses Python 3.12, `.venv`, and `requirements-core.txt`.
- Run `python -m pytest -v` (it also runs the unittest-style tests) and the
  policy self-test; CI (`.github/workflows/checks.yml`) runs both on
  `requirements-dev.txt` (= `requirements-core.txt` + pytest).
- Both `{scam}` and `{fine, scam}` require the two-group safeguard before a
  hold. A mule verdict counts as receiving-account evidence for either set.
  `{fine}` still releases. Unknown prediction sets raise ValueError.
- Preserve the four-field `decide()` contract. Record changes in docs/WORK_LOG.md
  and the user-requested workspace log at ../WORK_LOG.md.

## Status

Python 3.12 ML/AI project (git repo, default branch `main`). Sources: `src/journey_generator.py`
(synthetic UPI scam-journey data generator), `src/features.py` (Phase 2 past-only
feature engineering), the Phase 3 risk stack `src/risk_common.py`,
`src/train_xgb.py`, `src/conformal.py`, `src/reasons.py`, the Phase 4 action
engine `src/policy.py`, Phase 6 `src/attack_sim.py` (red-teaming, with the
evasion perturbations in `src/evasion.py`) + `src/integrations.py` (ecosystem
mocks), the Phase 7 GNN challenger `src/gnn_challenger.py` (PyTorch Geometric
GraphSAGE), and the Phase 8 federated learning simulation
`src/federated_sim.py` (FedAvg across two banks). Tests: `tests/` (pytest). No
formatter/linter.

- Environment: `python -m venv .venv`, then `.venv\Scripts\python -m pip install
  -r requirements-dev.txt` (core + pytest). `requirements-core.txt` holds the
  core ranges (`requirements-core.lock.txt` is the verified snapshot);
  `requirements.txt` is the full set incl. `torch` / `torch-geometric` for the
  Phase 7 GNN. `pyarrow` is core (features.py writes Parquet).
- CI: `.github/workflows/checks.yml` (pytest + policy self-test). No
  `pyproject.toml` or `Makefile`.

## Commands

All commands run from the repo root. `python` below means the venv
interpreter: activate it (`.venv\Scripts\activate`) or call
`.venv\Scripts\python` directly.

- Generate data (writes 3 CSVs into `data/`):
  - `python src/journey_generator.py` (full: 20k users / 120 days, ~28s)
  - `python src/journey_generator.py --smoke` (600 users / 30 days, <1s; use
    this to iterate). Writes to `data/smoke/` so it never clobbers the full data.
  - Flags: `--out-dir`, `--seed`, `--users N`, `--days N`.
- Build Phase 2 features (`data/features.csv` + `data/features.parquet`):
  - `python src/features.py` (full: ~3.06M rows, ~4 min)
  - `python src/features.py --smoke` (reads/writes `data/smoke/*`, 30 days, ~5s)
  - Flags: `--txns`, `--edges`, `--labels`, `--out`, `--days` (explicit flags
    override the `--smoke` defaults). Regenerating the dataset requires
    re-running features afterwards.
- Phase 3 risk stack (reads `data/features.csv`, writes `models/`):
  - `python src/train_xgb.py` (~40s; adversarial training on by default,
    `--no-augment` to disable; `--smoke` trains on `data/smoke/features.csv`
    and writes `models/*_smoke.json`)
  - `python src/conformal.py` (Mondrian calibration on the `calib` split;
    `--alpha-fine` / `--alpha-scam`; `--txn-id N` to score one txn;
    `--smoke` uses the smoke model and writes `models/conformal_smoke.json`)
  - Smoke chain (end to end, ~6s): `journey_generator.py --smoke` ->
    `features.py --smoke` -> `train_xgb.py --smoke` -> `conformal.py --smoke`.
    Smoke paths live in `risk_common.SMOKE_*`; the UI/policy still load the full
    `models/xgb_model.json` + `conformal.json`.
  - `python src/reasons.py --txn-id N` (SHAP top-3; `--demo K` for top-risk txns)
  - Flag paths are `--features/--model/--model-out/--meta-out/--out`.
- Phase 4 action engine (reads `models/` + `data/features.csv`):
  - `python src/policy.py --self-test` (asserts the full Two-Signal truth table)
  - `python src/policy.py --eval [SPLIT]` (runs `decide()` over every txn of the
    split, default `test`, and prints release/nudge/hold rates for scams vs
    legit + hold precision; ~25s on full data)
  - `python src/policy.py --txn-id N --soft-signals '{"chat_stage": "escalated"}'`
  - `python src/policy.py --demo K --soft-signals '{...}'` (top-risk txns)
  - Flags: `--model/--features/--conformal/--amount`, threshold overrides
    (`--n-t-threshold --e-t-threshold --z-t-threshold --zc-t-threshold
    --pi-t-threshold --d-r-max`).
- Streamlit demo UI (reads `models/`, no `data/features.csv` needed):
  - `streamlit run ui/app.py` (from repo root)
- Phase 6 red-teaming + ecosystem mocks:
  - `python src/attack_sim.py` (~30s; rewording + adaptive journey attacks on
    all test scams, prints catch-rate drops; `--strict` gates the adaptive
    attacks too; `--model/--meta` attack another model, e.g. an older one)
  - `python src/integrations.py` (prints the mock FRI / MuleHunter / 1930 calls)
- Phase 7 GNN challenger (CPU-only torch, demo-only):
  - `python src/gnn_challenger.py --smoke` (3 epochs, fast sanity check)
  - `python src/gnn_challenger.py` (full GraphSAGE training + verdict table)
- Phase 8 federated learning simulation (FedAvg across two banks):
  - `python src/federated_sim.py --smoke` (row-sampled, fast)
  - `python src/federated_sim.py` (full: ~60s, prints local vs global table)
- Risk-scoring API: `python -m uvicorn api:app --app-dir src` (needs `models/`),
  then `python scripts/demo_bank_client.py [--url ...]`. Reference: `docs/API.md`.
  The same server hosts the web frontends: `/app/` (user app) and `/demo/`
  (judges' view, QR pairing). `python src/attack_sim.py --json-out models/attack_results.json`
  feeds the demo's Robustness tab.
- Public demo site: `python scripts/build_space.py` builds `dist/space/`
  (gitignored; includes the trained bundle, so weights never enter the team
  repo). `--github USER/maya-site` force-pushes it to a private deploy repo that
  **Render** (free, `render.yaml` Blueprint) builds; `--upload USER/maya
  [--private]` targets Hugging Face Spaces (Docker Spaces now need PRO: a free
  account gets HTTP 402). `serve.py` binds `$PORT` (Render) or 7860, one worker
  (rooms are in memory), `MAYA_TRUST_PROXY=1`. ~320 MB RSS. Slim deps in
  `deploy/space/requirements.txt`. See `docs/DEPLOY_SPACE.md`.
- After retraining: `python scripts/pick_scenarios.py` re-picks the four demo
  transactions and prints rows + `PICKED_FOR_MODEL_SHA256` for
  `src/scenario_features.py`. Outcome-specific UI/API tests run only when the
  model hash matches (they skip with that instruction otherwise).
- Tests: `python -m pytest` (~15-35s, 92 tests incl. the unittest-style payment
  review / safeguard suites). `tests/test_pipeline.py` runs the
  whole smoke chain (generator -> features with the exact brute-force check ->
  train -> conformal -> policy --eval) in a temp dir, so it needs no `data/`.
  `tests/test_ui.py` drives `ui/app.py` with Streamlit's AppTest and needs the
  trained `models/` (skipped otherwise). The rest are pure unit tests.
- Built-in health checks still apply: a generator run is only healthy if
  `campaign_split_violations == 0` and `ref_integrity == True`; a feature run
  is healthy if every entry of `sample max|diff|` is `0.0` (optimized loop vs an
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
- **Anti-evasion features** (24 h window `(T - 1 day, T)`, same past-only rule):
  `v_t` = past payments sender -> receiver; `zc_t` = log(amount + those
  payments' total) - median past log amount (so a split payment's last part
  sees the full amount); `ptr_t` = the account's 24 h outflow / inflow (NaN if
  no inflow; mules forward what they receive). Combined: `v_t` max, `zc_t`
  larger |z|, `ptr_t` fmax. Window sums use `math.fsum` in both the loop and
  the brute force, so they match bit-for-bit.
- Note: legit accounts repeat-pay merchants, so legit `zc_t` is large too
  (val legit median ~3.2, p99 ~4.2) — it needs its own policy bar.
- **Helper columns** (not model features): `pair24`, `in24_snd/out24_snd`,
  `in24_rcv/out24_rcv` — the raw 24 h sums, used by `src/evasion.py` to
  recompute the anti-evasion features exactly under attack.
- `features.py` also writes `data/features.parquet` (~450 MB vs ~1.2 GB CSV).
  `risk_common.load_features()` reads it instead of the CSV whenever it is at
  least as new (`fresh_parquet()`), ~1.4s vs ~15s for a full load.

## Phase 3 risk model specifics (non-obvious)

- `src/risk_common.py` is the single source of truth: `FEATURE_COLUMNS` (27 = 9
  combined + 18 `_snd`/`_rcv`), `ENGLISH_REASONS`, the XGBoost hyperparameters
  (`XGB_DEFAULTS` / `xgb_params()`), and the `recall_at_fpr()` metric. Import
  them; do not duplicate the feature list, params, or metric in the scripts. `data/features.csv` also has `txn_id`,
  `ts`, `day`, `split`, `sender_id`, `receiver_id`, `amount`, `is_scam`.
- Model: `XGBClassifier(tree_method="hist")`, early stopping on val AUC-PR.
- **Adversarial training** (default): `evasion.augment()` adds evasive copies
  of the *train* scams for `evasion.TRAIN_ATTACKS` (split_2, split_4,
  extra_hop) — 11,480 extra positive rows, each attack family weighted 1 per
  original scam — and `scale_pos_weight = neg / total positive weight`
  (~247). val/calib/test are never augmented. `--no-augment` disables it.
- Test metrics currently AUROC 1.0000, AUPRC 0.998, recall@1%FPR 0.993
  (threshold chosen on val, reported on test; see `models/model_meta.json`).
  These are **too good to mean much**: the synthetic generator makes scams very
  separable (the 18-feature model was already AUROC 0.9995). The new features
  are verified past-only, so this is data easiness, not leakage.
- **Splits**: `risk_common.load_features()` calls `carve_calib()`, which relabels
  the later half of the val days as `calib`. `val` (earlier days, e.g. 72–83)
  is for early stopping + the 1%-FPR threshold; `calib` (84–95) is used only
  for conformal calibration. Every script that loads features sees the same 4
  splits (`train/val/calib/test`); `test` is unchanged.
- Conformal is a **manual Mondrian (class-conditional) LAC** implementation
  (not MAPIE): nonconformity `1 - p(true class)` with a separate quantile per
  class, `qhat_fine` (alpha_fine=0.01, i.e. >=99% of legit txns admit `fine`)
  and `qhat_scam` (alpha_scam=0.10, >=90% of scams admit `scam`), saved in
  `models/conformal.json`. Sets are only `{fine}`, `{scam}`, or
  `{fine, scam}`; a txn admitted by both classes **or by neither** maps to
  `{fine, scam}`, so sets are never empty. Load with
  `conformal.load_conformal()` (returns `(qhat_fine, qhat_scam)`; still reads
  an old single-`qhat` file); `classify(p, qhat_fine, qhat_scam)`.
- Why Mondrian: a single marginal qhat at ~0.09% positives collapsed to
  ~0.0002, so `{scam}` needed p >= 0.9998 and ~6.6% of test txns were
  `{fine, scam}`. Current full-data result: `{fine}` if p <= 0.00063,
  `{scam}` if p >= 0.9963, unsure share 0.51%, scam coverage 1.00.
- Current policy eval (`policy.py --eval`, test, no soft signals/MuleHunter,
  universal two-group safeguard): release 99.43% / nudge 0.30% / hold 0.26% of
  txns; 89.6% of scams held, 10.4% nudged, 0 released; 0.196% of legit held;
  hold precision 0.26. (Before the safeguard, when `{scam}` held outright, the
  same model held 95.2% of scams.) History, pre-safeguard: marginal conformal
  87.9% held / 1.22% legit held / precision 0.05; Mondrian + 18 features
  92.1% / 0.23% / 0.23.
- SHAP uses log-odds (`TreeExplainer` on the booster), with native
  `pred_contribs=True` fallback for NaN rows; positive SHAP increases scam risk.
  Both explain exactly the trees the model scores with (early stopping keeps
  `best_iteration + 1`; the fallback passes `iteration_range`) —
  `tests/test_reasons.py` checks SHAP sum + base == the scored margin.
- `models/*.json` are generated artifacts; do not commit them alongside `data/`.

## Phase 4 action policy specifics (non-obvious)

- `src/policy.py` implements the **Two-Signal Rule**. `decide()` is a pure,
  I/O-free function returning exactly `{action, reasons, auto_release_minutes,
  requires_analyst}`; `reasons` are the 3 SHAP English strings from `reasons.py`.
  Actions: `release` / `nudge` / `hold`. Hold => 60 min auto-release.
- Rule by conformal set (universal two-group safeguard): `{fine}` -> release;
  `{scam}` **and** `{fine, scam}` -> hold iff (payment-hard AND receiving-hard)
  OR (>=1 hard AND >=1 soft), else nudge. A model prediction never bypasses the
  safeguard. Chat/voice/screen-share are **soft only** and can never hold
  alone. Unknown sets raise `ValueError`.
- Hard signals: Payment History family `n_t/e_t/z_t/zc_t/pi_t`, Receiving
  Account family `d_R`. Defaults (val-percentile informed, CLI-overridable):
  `n_t>=59`, `e_t>=1.0`, `z_t>=2.6`, `zc_t>=4.2`, `pi_t>=1`, `d_R<=1`. `z_t`'s
  2.6 and `zc_t`'s 4.2 both sit at ~val legit p99. `zc_t` keeps a split
  payment's signal alive; rows without `zc_t` fall back to the `z_t` check.
  `n_t` is a weak discriminator on this data (scam median 50 vs overall 46) so
  its bar is deliberately high.
- **MuleHunter.AI integration**: `decide()` takes an optional `mulehunter_status`
  (from `integrations.check_mulehunter`); a `"mule"` verdict **while the conformal
  set is not `{fine}`** counts as a Receiving Account hard signal. It is ignored
  for `{fine}` and for `"suspicious"`/`"clean"`. `decide()` stays pure
  (status is a plain input); the mock I/O happens in `run()`/the UI.
- Soft signals (mocked input): `is_screen_shared`, `is_voice_active`, and
  `chat_stage` in `{escalated, payment_demand}`.
- `requires_analyst` is True **only when the action is hold and amount > ₹100k**
  (not for release/nudge). Thresholds are a frozen `Thresholds` dataclass.
- **Risk-scoring API** (`src/api.py`, FastAPI): `create_app(scorer, service,
  load_defaults)` builds it; module-level `app` loads `models/` (env overrides
  `MAYA_MODEL` / `MAYA_CONFORMAL` / `MAYA_REVIEW_DB`) and reports `not_ready`
  (503 on scoring) when they are absent. `POST /v1/score` validates the exact
  27-column feature contract `maya-features-v1` (`null` = missing → NaN),
  computes the conformal set server-side, and returns `decide()`'s 4 fields +
  `p_scam`, `conformal_set`, `fired_signals`, version hashes and latency.
  Reasons use `reasons.risk_reasons()` (shared with the UI). `/v1/payments...`
  wraps `PaymentService`; `http_error()` maps its ValueError messages to
  404 / 403 / 422 / 409. Session = `X-Payer-Session` header (simulated, not
  auth). The four UI scenarios' feature rows live in `src/scenario_features.py`
  (shared by `ui/app.py`, `scripts/demo_bank_client.py`, `tests/test_api.py`),
  with their en/hi story text in `SCENARIO_STORY` (served by
  `GET /v1/demo/scenarios`). `/v1/score` always returns `reason_features` and,
  with `"explain": true`, every feature's SHAP contribution.
  Local latency ~6 ms server-side, ~30 ms round-trip p95 (SLO 150 ms).
- **Web frontends** (`frontend/`, plain HTML/CSS/ES modules, no build step,
  mounted by `create_app()` with `StaticFiles`): `frontend/user` → `/app`,
  `frontend/judge` → `/demo`, `frontend/shared` → `/static` (tokens.css,
  api.js, i18n.js, self-hosted Anek fonts, OFL). Kept apart from Ashrith's
  unmerged `web/` wallet so the two don't collide.
  - Design system: rupee palette (ink `#23264F`, paper `#F5F4FA`, lavender
    `#C9C3EA`, leaf / turmeric / sindoor for release / nudge / hold; turmeric is
    a fill only, `--turmeric-ink` for text — all pairs WCAG AA). One family,
    Anek; its width axis does the work (wide amounts, condensed tables).
  - User app: one orchestrated moment — the send line's dot travels and stops
    part-way on a hold (red dashed remainder). Plain-language reasons come from
    `reason_features` via `i18n.REASONS` (en/hi), plus the phone's own soft
    signals; avatar initials always come from the English name.
  - Judges' view is its own page (no iframe): it creates a **demo room**
    (`src/rooms.py`, in memory), shows a QR of `/app/?code=XXXXXX` and the
    code, and follows the room over Server-Sent Events (JSON polling fallback
    after 3 stream errors). Phones join with the code; `/v1/score` with
    `room` = the phone's publish token makes the *server* publish its own
    result. Its moment: the three signal groups light in sequence, then the
    latch closes on two. "Run the built-in scenarios here" needs no phone.
  - **Your own payment** (user app, Settings): a plain-language form whose
    answers `frontend/shared/custom.js` maps to the 27 features with the
    `features.py` formulas, starting from a *typical legit payment* in the
    generated data (e.g. a regular contact has the data's typical 12 same-payee
    payments / 24 h; "first time paying" removes that history). Checked against
    the model: ordinary -> release, much larger than usual -> nudge, first-time
    + pressure -> hold, first-time large to a reported account -> hold.
  - Shared CSS rule: `[hidden] { display: none !important }` (component
    `display: grid/flex` rules otherwise override `hidden`).
  - Hindi copy is a draft — get a native-speaker check before public use.
  - Visual check: Playwright with the installed Edge (`channel="msedge"`) —
    screenshots at 360 / 390 / 768 / 1280 / 1920 px, keyboard-only pay flow,
    reduced motion; no console errors.
- `src/payment_review.py` (simulated payment service) loads the conformal file
  with `load_conformal()` and calls `classify(p, qhat_fine, qhat_scam)`. Its
  `feature_snapshot()` adapter fills `v_t` / `zc_t` from same-recipient history
  in the evidence window and sets `ptr_t=None` (not observable there;
  JSON-safe for review digests, NaN to the model). Its independent hold
  verifier includes `zc_t >= 4.2`. `POLICY_VERSION` is `payment-review-v2`.
  Known: the adapter's features are far from the real data (e.g. `n_t=1`), so
  with the 27-feature model the "Rent" demo is `{fine, scam}` -> nudge (it was
  `{fine}` -> release with the 18-feature model).
- Verification is `python src/policy.py --self-test` (22-case truth table,
  incl. 7 MuleHunter and 2 split-payment cases). The cases live in
  `policy.SELF_TEST_CASES`, shared with `tests/test_policy.py`.

## Phase 6 specifics (non-obvious)

- `src/integrations.py` is dependency-free and deterministic (sha256 hashes +
  a small `KNOWN_ACCOUNTS` table so the UI scenarios hit known statuses). It
  mocks the DoT FRI (`check_fri`), MuleHunter.AI (`check_mulehunter`), and the
  NCRP 1930 portal (`file_1930_report`). `known accounts`: `1001`/`4004` clean,
  `2002`/`3003` mule.
- `src/attack_sim.py` red-teams the model on **all** test-split scams (or
  `--n-attacks N` sampled). "Catch rate" = recall at the val-chosen 1%-FPR
  threshold (`model_meta.json`). Two parts:
  - **Text rewording** is *illustrative only*: no chat text is a model input,
    so Maya's drop is 0.0 by construction, and the phrase-matching text
    detector's ~88% collapse is set by `REWORD_EVASION` (the PDF figure).
  - **Adaptive journey attacks** are the real test: the scammer perturbs what
    they control and features are recomputed with the `features.py` formulas
    by `src/evasion.py` (`split_k` into k parts within 24 h, `extra_hop`,
    `no_probes`, `all` = split_4 + extra_hop + no_probes; exact formulas and
    the two conservative approximations are in its docstring). A split scam is
    **caught if any part is caught**. Scoring uses the model's own feature
    list, so `--model/--meta` can attack an older 18-feature model.
  - Results (catch rate after attack, full test data):

    | attack | 18-feat model | 27-feat, no adv. training | current |
    |---|---|---|---|
    | none | 96.7 | 99.5 | 99.3 |
    | split_2 | 91.8 | 97.4 | 99.6 |
    | split_4 | 84.4 | 90.5 | 99.3 |
    | split_10 (held out) | 72.2 | 65.0 | 95.8 |
    | extra_hop | 80.0 | 74.2 | 99.6 |
    | all (held out) | 62.3 | 61.4 | 99.5 |

    The new features alone did **not** help (the model kept trusting `z_t`
    because no training scam was ever split); adversarial training on
    split_2 / split_4 / extra_hop did, and transfers to the held-out
    split_10 and combined `all`. Caveat: these are **known, white-box
    attacks** scored with the same perturbation model used to train — real
    scammers will try evasions not modelled here (e.g. a never-used entry
    mule with no history, which `extra_hop` does not simulate).
  - Exits 0 iff the rewording drop < `--drop-target` (always, by
    construction); `--strict` also gates every adaptive attack (currently
    passes, worst drop split_10 -3.5 pts). Reads full features (~30s); no
    `--smoke`.

## Phase 7 GNN challenger specifics (non-obvious)

- `src/gnn_challenger.py` builds the PDF's GraphSAGE challenger: a 2-layer
  `SAGEConv` node classifier that predicts `labels.is_mule` (60 mules) from the
  account graph (`data/graph_edges.csv`, mapped `vpa -> node index`).
- Node features are leakage-free graph statistics only (`log1p` in/out/total
  degree); `role` and its derivatives (`is_mule`, `is_aggregator`, ...) are
  deliberately excluded so the model must learn mule-ness from neighbourhood
  structure (2-hop receptive field over the `victim -> entry mule -> mid mule ->
  aggregator` relay).
- **Past-only, time-sliced snapshots** (node masks from `labels.split`): an
  edge is in a snapshot iff its `first_ts` day < cutoff. Fit on the `train`
  snapshot (cutoff = first val day, 72), early-stop on the `val` snapshot
  (cutoff = first test day, 96), score test on the full graph. Degree features
  are recomputed per snapshot; GraphSAGE is inductive so weights transfer.
  Split start days come from `transactions.csv` (`--txns`); `first_ts` day =
  days since 2024-01-01 (= `transactions.day`).
- Class imbalance handled via `BCEWithLogitsLoss(pos_weight = neg/pos on train)`;
  early stop (patience 25) on val AUROC; the best state is **cloned** (a bare
  `state_dict()` aliases live weights and silently returned the last epoch).
- `labels.split` is heavily skewed: accounts 21,221 / 78 / 63 with only
  **55 / 3 / 2 mules** (train/val/test), so val/test AUROC are close to noise
  (the script prints a warning). Full-history graph (old): test 0.98;
  time-sliced (now): val 0.94, test 0.51. A real comparison needs more
  val/test mules (a generator change).
- The verdict table compares **different targets** on purpose: champion
  `test_auroc` (1.0000) is txn-level `is_scam`, the GNN AUROC is account-level
  `is_mule`; the script labels both and does not roll the champion up to accounts.
  The printed verdict is computed by `verdict_lines()` from the measured GNN
  AUROC (usable iff >= `GNN_USEFUL_AUROC` = 0.70) and forward latency vs the
  150 ms SLO; it never claims the GNN beats the champion (different targets).
  XGBoost always stays in the per-payment hot path (the GNN scores accounts).

## Phase 8 federated learning simulation (non-obvious)

- `src/federated_sim.py` simulates horizontal FedAvg across two banks: customers
  are split by `sender_id` (first half -> Bank A, rest -> Bank B) so each bank
  holds disjoint customers and no raw data is shared.
- Each bank trains a local `XGBClassifier` on its own train split (same
  hyperparameters as `train_xgb.py`: hist / aucpr / n_estimators=400 / depth 6 /
  lr 0.1 / early stop 40) with per-bank `scale_pos_weight`. No adversarial
  training here (it compares federation setups, not robustness).
- `fedavg()` averages the two models' **prior-corrected margins**
  (`predict(..., output_margin=True) - log(spw)` per bank) and passes the mean
  through sigmoid. This is output-level model averaging (an ensemble) — true
  tree-weight averaging is ill-defined for non-aligned trees. Subtracting
  `log(spw)` removes each bank's class-weight shift so neither dominates; the
  resulting probabilities are base-rate calibrated, so thresholds are tiny
  (printed in `e` notation).
- Evaluates both locals and the global on the **shared** test split (both
  banks): AUROC + recall@1%FPR. Thresholds are chosen at 1% FPR on val
  **without pooling val**: each local on its own val; the global = mean of
  the threshold each bank picks for the global model on its own val (only
  scalars are shared). WIN / TIE / LOSE via `outcome()` (tolerance 1e-4).
- A **pooled-data** baseline (one model on both banks' train, what data
  sharing would give) is also trained and printed as "cost of federation".
  Full run (27 features): locals recall 0.894 / 0.991, global 0.991 (TIE with
  the best local), pooled 1.000 — federation costs ~0.9 pts vs sharing data.
  (With the old 18 features the global beat even pooled, i.e. the gain was
  ensembling; if that recurs the script prints a note saying so.)
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
- `data/*.csv` / `data/*.parquet` are regenerated artifacts (transactions
  ~350 MB, features ~1.2 GB CSV + ~450 MB parquet); they are not tracked and
  should not be committed.

## UI specifics (non-obvious)

- `ui/app.py` is a Streamlit demo (`streamlit run ui/app.py` from repo root). It
  adds `src/` to `sys.path` and imports the real `policy.decide`, `conformal`,
  and `risk_common`; it does **not** need `data/features.csv` (scenario
  features are hardcoded) but does load `models/xgb_model.json` +
  `models/conformal.json` for the live `p_scam`, conformal set and SHAP.
- Four scenario buttons. Each scenario's **27 features are copied from a real
  test-split txn** (`source_txn`, built with `real_features(comb, snd, rcv)`
  from 9-tuples) and its `amount` is that txn's amount: normal #2391121
  (Rs 36,308, `{fine}` -> release), investment scam #2861134 (Rs 1,96,538,
  `{scam}` -> hold + `requires_analyst`), fake-police screen-share #2599999
  (Rs 3,592, unsure, receiving-hard `d_R=0` only + soft -> hold + "Priya
  Alerted" panel), and soft-only unclear #2415533 (Rs 4,729, unsure, 0 hard
  -> nudge with a "Pay anyway" second click). **If the model or features
  change, re-pick them** (`scripts/pick_scenarios.py`) so the model-implied sets
  still match the scripted `conf_set` — the strict tests skip until you do.
- **Model-driven by default**: `decide()` gets the model-implied conformal set
  (live `p_scam` + `load_conformal`). The sidebar toggle "Pin scripted
  conformal sets" switches to each scenario's scripted `conf_set` instead.
- **Reasons** passed to `decide()` come from live SHAP via `risk_reasons()`:
  ranked by SHAP, only features that push risk up **and** whose value is in the
  risky range (`in_risky_range()`, same bars as the policy hard signals; `g_t`
  never cited since it is ~constant), one per base feature, max 3. Falls back
  to the scenario's scripted `reasons` if none qualify or the set is pinned.
- Each scenario also carries a `phone` / `account_id` / `txn_id` so the UI calls
  the real `integrations.check_fri` + `check_mulehunter` mocks and passes the
  MuleHunter status into `decide()`. Scenario account ids map to known statuses
  (normal/unclear -> clean, investment/police -> mule).
- **Analyst Dashboard**: shown only when `requires_analyst` is True (held AND
  amount > Rs 1 Lakh — just the investment scenario). It shows the mock FRI score
  and MuleHunter status plus two buttons ("Approve Release" / "File 1930 Report &
  Block") driven by `st.session_state.analyst_action`; the report button calls
  `file_1930_report` **once on click** and stores it in
  `st.session_state.report` (reruns reuse it, so the NCRP ref id is stable).
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
  `amount` (Rs 1,96,538).
- **Tabs**: the page body is split into two `st.tabs` — "Scenario Demo" (all the
  scenario UI above) and "Sandbox Mode". The sidebar (scenario buttons + model
  metrics) stays global, outside the tabs.
- **Sandbox Mode** (second tab): sliders for the journey features (`n_t`,
  `e_t`, `z_t`, `pi_t`, `d_R`, `v_t`, `ptr_t`; `g_t` fixed at 1, `zc_t` derived
  as `z_t + log(1 + v_t)`, i.e. earlier same-payee payments assumed the same
  size) with defaults at typical legit values, an Amount slider (drives
  `requires_analyst` only), and soft
  toggles (screen shared, voice call, chat stage). "Simulate Payment" scores
  the row with the live model and uses the **model-implied conformal set**;
  the "Force the unsure set" toggle pins `{fine, scam}` to test the hard/soft
  rule directly. The 6 features are mirrored into `*_snd`/`*_rcv` (an
  approximation; `synthesized_matrix()` uses all 18 when given). Result is
  transient (recomputed on click only), with the exact `decide()` JSON below.
- Hold shows a static 60-min auto-release badge plus an "Advance 60 min (demo)"
  button (no live countdown / no auto-refresh).
- A hold resolves **exactly once**: analyst Approve (released), analyst Report
  (blocked, auto-release cancelled), or Advance 60 min (auto-released, analyst
  actions closed) — whichever comes first hides the other controls.

## Layout

- `src/` — application code and entrypoints
- `ui/` — frontend / user interface
- `models/` — trained model artifacts (generated JSON, gitignored)
- `data/` — datasets (generated CSVs, gitignored)
- `.claude/launch.json` — launches the Streamlit UI from `.venv` on port 8501
