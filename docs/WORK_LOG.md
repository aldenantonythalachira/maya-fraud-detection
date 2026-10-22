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

### Stage 02 - Generated worlds and feature parity

- Stage 01 pushed as 031321b with tag maya/01-payment-review; draft PR #2:
  https://github.com/aldenantonythalachira/maya-fraud-detection/pull/2.
- Added seeded account/payment/report generation and exact live reuse of batch
  endpoint/combine logic, preserving missing history instead of invented zeroes.
- Found an important legacy convention: batch graph distances propagate outward
  from reported accounts, not toward them. Preserved it for existing weights,
  labeled the convention, and test the previous-UTC-day report/edge snapshot.
  Correcting direction requires a separately versioned retrain, not a silent fix.
- 25 tests pass, including independent brute-force feature comparison across
  five random worlds, seed replay, probe windows and future-evidence exclusion.

### Stage 03 - Interactive wallet and transparent execution

- Stage 02 pushed as dc6884a, tag maya/02-generated-worlds, draft PR #3:
  https://github.com/aldenantonythalachira/maya-fraud-detection/pull/3.
- Added a loopback FastAPI service, persistent ordered SSE events, world/session
  binding, actual XGBoost/native tree-SHAP inference and immutable policy replay.
- Added a balanced dummy wallet ledger, integer paise, server-side review/context/
  evidence/version checks, atomic execution, durable intent idempotency, recovery
  after restart, cancellation, timed holds and revision-bound analyst approval.
- Added clean mobile-first payer, recipient, review, warning, demo authorization,
  receipt and history screens. Inspector exposes real features, graph edges,
  uncertainty, policy groups, versions, execution events and JSON downloads.
- Added report-delay counterfactuals retaining original snapshots/holds, virtual
  clock controls and daily-deduplicated synthetic contact alerts.
- Deliberately used native browser ES modules/CSS instead of React/Vite so the
  demo starts with one Python command and has no extra frontend dependency/build.
  Kept existing Streamlit demos and all risk policy contracts intact.
- Fixed a held-review snapshot aliasing bug discovered by actual-model tests;
  saved input objects are copied before updating the intent's hold metadata.
- 39 automated tests and 20 policy cases pass; pip check and JS syntax check pass.
  Twelve three-seed behavioral replays pass; processing p95 25.60ms with stated
  limits, not end-to-end latency or accuracy. Details: docs/VALIDATION.md.
- Browser QA completed custom paise transfer, live hold, stale-review rejection,
  changed-evidence nudge, original replay, receipt reload and recipient credit.
  Checked responsive widths 360/390/768/1280; corrected desktop vertical alignment.
- Added clean-clone bootstrap, runbook, CI smoke rebuild and behavioral audit.
  Research/calibration limits remain explicit; no verdict is pinned for demo polish.

### Publication receipt

- Interactive stage commit: 396ac26 on codex/interactive-wallet, pushed to origin.
- Draft PR #4: https://github.com/aldenantonythalachira/maya-fraud-detection/pull/4.
  Review/merge order is foundation #1 -> payment review #2 -> generated worlds #3
  -> interactive wallet #4. No PR was merged and main was not changed.
- Published recovery tags: maya/00-original (687635e), maya/01-payment-review
  (031321b), maya/02-generated-worlds (dc6884a), maya/03-interactive-wallet (396ac26).
- GitHub Actions push run 39744982587 completed successfully for 396ac26;
  the separate PR-triggered run was still running when checked.
- Working tree was clean after stage publication. Runtime data/models are ignored.
  Subsequent commit only records this publication receipt in the running log.

### Decision-platform baseline and staged scope
- Started from clean d1a01ff on codex/decision-platform. Policy 20/20 and pip check pass.
- Scope and stage exit checks are in docs/DELIVERY_REVIEW.md. Full baseline suite running.
- Preserve graph/model compatibility; unvalidated research features remain explicitly partial.

