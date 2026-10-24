# Repository work log

## 2026-10-20 - Finale foundation

- User approved the staged finale plan. Branch: `codex/finale-foundation`, base
  `687635e` on `main`. Workspace-level running log is `../WORK_LOG.md`.
- Audited Python/Streamlit baseline. Models/data are generated and absent from
  Git; scenario decisions are pinned rather than driven by model inference.
- Fixed unconditional holds for scam-only conformal predictions. Every hold
  now needs two signal groups, with at least one hard group. Mule verdicts count
  as recipient evidence in both non-fine prediction sets. Unknown sets fail
  explicitly rather than falling into the unsure branch.
- Added exhaustive signal-group regression checks, a core dependency manifest,
  setup instructions, and GitHub Actions checks. Optional GNN dependencies stay
  out of the core installation path.
- Updated AGENTS.md to document this intentional change from its earlier table.
- Validation pending; no new accuracy claims are made.

### Foundation validation and PR

- PR #1: https://github.com/aldenantonythalachira/maya-fraud-detection/pull/1
- 5 regression tests and 20 built-in policy cases passed; pip check passed.
- Smoke generation: 600 users, 30 days, 23,278 transactions, 18 campaigns;
  zero split violations and valid references. Past-only sample differences zero.
- Training/calibration completed: test AUROC 0.9477, AUPRC 0.6838, recall 0.6774
  at validation-selected threshold. Coverage 85.83%, below the 90% target.
  These measurements are not B4 results or real-world validation.

## 2026-10-20 - Payment review (dependent branch codex/payment-review)

- Added SQLite-backed operations and immutable review records, atomic revision,
  session, expiry and version checks, cancellation and duplicate-send prevention.
- Holds persist for an hour on the original operation; a later evaluation cannot
  erase the hold. After expiry, require fresh review and explicit confirmation.
  Over INR 100,000 also requires simulated analyst approval for that revision.
- Added narrow English claim grammar, supporting spans and abstention. All text
  remains local. Evidence templates are labeled separately from SHAP attribution.
- Added actual model adapter with model/calibration content hashes and a small
  synthetic event adapter. This adapter mirrors endpoint columns and is not a
  substitute for the full historical feature pipeline.
- Added payer, analyst and judge views; graph edges come only from recorded
  available evidence. Counterfactual records link to original records.
- 19 tests pass. Live smoke model: rent release, investment hold, refund nudge.
- UI verification and behavioral evaluation still in progress.

## 2026-10-22 - End-to-end execution plan

- Read all 21 pages of the user-specified deck at
  `C:/Users/ashrith/Downloads/Projects/NIT Warangal-sazi-maya.pdf`; rendered and
  inspected selected journey, UI, architecture, safety and results pages.
- Added docs/EXECUTION_PLAN.md: deck mapping, current-code audit, generated worlds,
  batch/online feature parity, dummy wallet ledger, backend event streaming,
  UPI-style UI, decision lineage, review binding, acceptance gates and staged PRs.
- Plan estimates 12-15 engineering days for the core; distinguishes a 48-hour
  cut and later multilingual/voice/GNN/privacy research. No runtime code changed.
- Preserved existing uncommitted work on codex/payment-review. Re-ran all
  19 regression tests and 20 policy self-test cases successfully.
- Identified feature-adapter mismatch as a priority; retained existing hold
  semantics and made deck conflicts explicit. Historical B4 and local smoke
  results remain separate; no new detection or UI verification claims.

### Implementation authorized; stage 01

- User authorized staged implementation and GitHub pushes, with version recovery
  and continued running logs. Preserved and prepared the existing payment-review
  work for a checkpoint rather than overwriting it.
- Added scripts/versions.py and docs/VERSION_RECOVERY.md. Restore creates a new
  branch and refuses local changes; no reset, clean or force-push is used.
- Stage 01 checkpoint contains the review service, claim grammar, debugger,
  regression tests, dependency snapshot and execution plan. Wallet settlement
  remains a later stage, not a claim of this checkpoint.

### Evasion hardening, honest evaluations, pytest suite (branch feature/evasion-hardening)

- Rebased onto main (after the universal hold safeguard and payment review);
  main's policy semantics are kept unchanged.
- Risk stack: held-out `calib` split (later half of val days) for conformal;
  class-conditional (Mondrian) conformal with `qhat_fine` / `qhat_scam`
  (`conformal.load_conformal()`; old single-`qhat` files still load).
- Features: past-only anti-evasion features `v_t`, `zc_t`, `ptr_t` (27 model
  columns), exact brute-force check still 0.0; Parquet twin for fast loading.
- `zc_t` joins the payment-history group (bar 4.2, ~val legit p99).
- Adversarial training on split payments / extra mule hop (`src/evasion.py`);
  `attack_sim.py` now measures real adaptive attacks (worst drop 34.4 -> 3.5
  pts, split_10 and the combined attack held out of training). Known,
  white-box attacks on synthetic data only.
- Honest demos: model-driven UI scenarios from real test transactions;
  federated sim without pooled val plus a pooled-data baseline; GNN on
  time-sliced snapshots (only 2 test mules: its AUROC is noise).
- payment_review updated for the new conformal API and features
  (POLICY_VERSION payment-review-v2). Behaviour change: the "Rent" demo is now
  nudged (adapter features are far from the training data).
- Tests: CI switched to `python -m pytest -v` on requirements-dev.txt (core +
  pytest); 71 tests + policy self-test pass locally on pandas 3 and on the
  CI-style requirements. No model or data files committed.

### Risk-scoring API (branch feature/scoring-api)

- Why: a phone app cannot plug into Paytm/PhonePe (sandboxing; only the payer's
  UPI app or bank can hold a payment), so Maya is exposed the way a bank would
  integrate it: an HTTP risk-scoring service called before release.
- Added src/api.py (FastAPI): stateless `POST /v1/score` on the 27-feature
  contract `maya-features-v1`, stateful `/v1/payments...` wrappers over
  PaymentService, `/v1/health`, `/v1/model`; docs in docs/API.md.
- Moved the "only cite true reasons" filter into src/reasons.py and the four UI
  scenario rows into src/scenario_features.py (shared by UI, API tests, client).
- Added scripts/demo_bank_client.py (stdlib) and tests/test_api.py (21 tests;
  real-model ones skip without models/). 92 tests pass with models; 83 pass /
  9 skip without (CI-style, pandas 2.3.3). Demo: all scenario outcomes as
  expected, server-side ~6 ms, round-trip p95 ~31 ms vs 150 ms budget.
- Dependencies: fastapi + uvicorn in core, httpx in dev; lock file extended.

### Web frontends: user app + judges' demo (branch feature/scoring-api)

- Two new frontends on the scoring API, under `frontend/` (no build step):
  `/app/` everyday-user payment app (English / Hindi, phone-first) and `/demo/`
  judges' demo (live app + decision board + Evidence / Robustness / Model card
  / Try it). Streamlit apps unchanged; Ashrith's `web/` untouched.
- Design: rupee palette, Anek (Latin + Devanagari) self-hosted; contrast-checked
  to WCAG AA; one orchestrated moment per surface; keyboard and reduced-motion
  checked.
- Backend: `GET /v1/demo/scenarios`, `reason_features` and `explain` on
  `/v1/score`, `attack_sim.py --json-out` (shown in `/v1/model`), static mounts.
  Scenario story text (en/hi) moved into `src/scenario_features.py`.
- Verified: 95 tests pass with models (85 pass / 10 skip without); Playwright +
  Edge screenshots of every scenario at 360–1920 px in both languages, no
  console errors; keyboard-only pay reaches a hold. Hindi copy needs a native
  speaker's review.

### Own website, paired judge view, review fixes (branch feature/live-site)

- Judges' view is now its own page: it creates an in-memory demo room
  (`src/rooms.py`) and shows a QR + code; phones join from the QR and every
  payment they score is published to the room by the server (SSE stream with
  a JSON polling fallback). Per-client rate limits; rooms, phones and events
  are capped and expire.
- Frontends redesigned to be more minimal (no boxes or dark bars; one
  settings sheet; outcomes as a thin coloured rule). Fixed a CSS class of bug
  where `display: grid/flex` overrode `[hidden]`.
- Public site: `deploy/space/` + `scripts/build_space.py` build a ~3 MB bundle
  (slim deps, trained weights only in `dist/`, never in Git) for Hugging Face
  Spaces. Verified the bundle runs on its own in a slim venv (no Docker on
  this PC) with the two-device flow and per-IP limits behind a proxy header.
- Review fixes: SHAP fallback now explains only the scored trees (TreeExplainer
  already did) with an additivity test; outcome-specific scenario tests are
  guarded by the model hash, and `scripts/pick_scenarios.py` re-picks the
  scenarios after a retrain (reproduces the current four).
- Added "Your own payment" to the user app: a plain-language form mapped to
  the 27 signals (`frontend/shared/custom.js`) from a typical-legit baseline.
  Prototyped and checked against the model first (ordinary -> release,
  first-time + pressure -> hold, reported recipient -> hold); verified in Edge
  with the payment appearing live on the judge screen.
- Hosting: Hugging Face now requires PRO for Docker Spaces (HTTP 402 on create),
  so the site deploys to Render's free tier instead: `serve.py` binds `$PORT`,
  `render.yaml` Blueprint, and `build_space.py --github` force-pushes the bundle
  to a private deploy repo (`ldcode20/maya-site`). Measured ~320 MB RSS.
