# Decision-platform validation — completed 23 October 2026

## Automated checks

- Full suite: **52 tests passed**, including actual HTTP/TCP SSE cursor recovery,
  forced owned-server process-tree termination, restart reconciliation and one
  matching debit/credit. The corrected Windows test verifies the old server is
  actually gone before starting a new one.
- Policy self-test: **20/20**. Dependency check clean. Browser ES modules passed
  Node syntax checking. Actual-model tests assert that sigmoid(base + SHAP sum)
  reconstructs the score from the same selected early-stopping tree range.
- New tests cover independent roles, exact-review approval, contact consent/
  acknowledgment, scoped sharing/expiry/revocation, purge, failed model trace,
  calculation witnesses, separate-world counterfactuals, rollback visibility,
  bundle tampering, disjoint tuning/calibration days and security boundaries.
- Initial baseline suite was interrupted because the sandbox blocked Windows
  socket-pair setup before API execution. Final suite ran in the authorized
  ordinary Windows environment; no API tests were disabled to avoid the issue.
- Starlette emits a non-fatal httpx deprecation warning in the pinned environment.

## Browser verification

Actual in-app browser actions demonstrated:

- Custom INR 1,250.50 payment: actual inference, warning confirmation, explicit
  demo authorization, receipt, matching credit and conserved ledger.
- Investment seed 42 / INR 125,000: actual two-group hold, separate contact inbox,
  acknowledgment, independent analyst case and no payer-side approval control.
- Controller advanced virtual time; payer obtained a fresh review; analyst
  approved that exact review; payer explicitly authorized; recipient view showed
  the same INR 125,000 credit. Timer/contact actions alone did not move money.
- Receipt recovered after reload/server restart; immutable original snapshots
  remain readable while incompatible recomputation is rejected.
- Home, receipt and expanded explorer checked at fixed 360/390/768/1280-pixel
  frame widths. No inner document horizontal overflow. Scrollbars account for
  15-pixel differences between frame width and document client width.
- Viewport override did not reliably change the native in-app view, so exact
  breakpoints were checked through `web/qa.html` and development-only `/qa/wallet`.
  Start with `--demo-docs` to use this harness; only that QA route allows same-origin
  framing. Ordinary wallet and console routes keep frame-ancestors none.
- Keyboard focus styles, semantic labels/status regions and navigation focus were
  inspected. This is not a complete screen-reader/device accessibility audit or
  a persistent automated browser end-to-end suite.

Screenshot: [wallet-v2.png](screenshots/wallet-v2.png).

## Model and evaluation

Rebuilt artifacts use earlier validation days for tuning and later validation
days for calibration. Current synthetic test: 5,252 transactions / 31 scam rows;
coverage **92.10%**; scam coverage **93.55%**; benign coverage **92.09%**;
test PR-AUC **0.4893**; recall at tuning-selected 1%-FPR threshold **35.48%**
(observed test FPR about **0.04%**). Recall misses the deck's 70% target.

Model hash: 5628beff937c30c425b957468a750d3ed45d5418743dfd13ea64d4526fa811a7.
Calibration hash: 0af61253e1bec4d46f38be310aa9eb0792eadbc06e5f1cb0241e45a962899c90.

Three-seed behavioral audit: 12/12 snapshot replays; recorded p95 review processing
20.36ms, excluding final review commit, HTTP/network, rendering and cold startup,
on Windows 11 / Python 3.12.14. This is not a 150ms end-to-end performance claim.
API Server-Timing and request/evaluation correlation supplement these measurements.

The unseen-type benchmark retains all nine seed/type configurations: four measured
with only one/two scam campaigns, five insufficient class support. See
EVALUATION_RESULTS.md for every result. Intervals are descriptive transaction-level
Wilson intervals; within-campaign correlation limits their interpretation. Gross
screened amounts are not realized fraud savings. No deployment/generalization,
fairness, voice/chat robustness or intervention efficacy claim is established.

## Remaining release limits

`model_health.py --require-promotable` deliberately refuses promotion. No public
bank deployment is authorized or justified. See DECK_CHECKLIST.md for all missing,
partial and research milestones. Legacy graph semantics remain explicit. Digests
and local access roles are not signatures, bank identities or HSM protection.

---

## Historical stage-03 validation (superseded by the measurements above)

# Validation recorded 22 October 2026

## Automated checks

- 39 unittest cases passed, including actual-model integrations for four world
  presets, API validation/session/origin boundaries, independent batch feature
  oracle checks, competing database connections, conservation, retry after
  restart, immutable policy/model replay, counterfactual preservation and safe
  version restore. The restore test uses its own temporary Git repository.
- Policy self-test: 20/20 cases passed. Python dependency check passed.
- Browser JavaScript passed Node syntax checking.
- Three-seed behavioral audit: seeds 11, 29, 47; four presets each; 12/12 saved
  model and policy outcomes reproduced. Recorded p95 review processing: 25.60ms
  on Windows 11 / Python 3.12.14, in-process memory DB. This includes features,
  model inference, SHAP, policy and preceding trace commits, but excludes final
  review commit, HTTP/network, browser rendering and cold startup. It is not
  a 150ms end-to-end latency claim or a new detection-accuracy benchmark.
- Model hash: dde9596c9f0aa9e10edd793f934b48667582235b71d856f08c09e90446e26dce.
- Calibration hash: 3ac42dfda9c5220ad60440f78a1311eeb6723f4793808ce8b5d382ef30b7314e.

Full behavioral-audit output is generated locally at data/evaluation-demo.json.
Generated datasets, model artifacts and wallet databases are not committed.

## Browser verification

Used the Codex in-app browser against the loopback API. Verified:

- Custom INR 1,250.50 dummy payment to Amma: warning confirmation, authorization,
  completion receipt, matching debit/credit and zero-net ledger movement.
- Investment seed 42: actual two-group hold on INR 20,000, contact inbox event,
  feature lineage, contributions and evidence-backed directed graph.
- Edited amount to INR 21,000: old review rejected at the backend boundary.
- Delayed report: separate linked evaluation changed hold to nudge; original
  snapshot recomputed successfully and original intent remained held.
- Authorized the separate INR 21,000 dummy payment and verified the corresponding
  incoming credit in the read-only recipient page.
- Reload recovered a completed receipt without sending another payment.
- Responsive widths 360, 390, 768 and 1280px: no document horizontal overflow
  in inspected states. Phone receipt and desktop receipt/inspector visually checked.
- Fixed desktop alignment so a long inspector does not vertically center the payer
  card far down the page. No browser errors/warnings were reported in the inspected
  payment session before the final layout-only correction.

Proof screenshot: screenshots/wallet-and-trace.jpg. This is manual browser QA,
not a claim of a persistent automated end-to-end browser suite or a full
screen-reader audit. CI rebuilds the smoke model before the integration tests.

## Remaining limits

The current smoke model can warn on benign familiar payments; calibration
coverage is approximately 85.83%, below target. Preserve this behavior visibly.
Legacy graph direction and day slicing are retained for existing model semantics.
Multilingual stage/voice models, a bank connector, calibrated production accuracy,
signed evidence, cloud hosting and full fairness evaluation are not implemented.
