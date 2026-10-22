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
