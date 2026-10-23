# Deck implementation checklist

Reviewed 22 October 2026 against the 21-page NIT Warangal SAZI MAYA deck.
"Verified" means demonstrated local behavior, not bank readiness or real accuracy.
Research items are retained explicitly; missing models/weights are never fabricated.

| Deck item / PDF pages | Status | Evidence and limits |
|---|---|---|
| Seeded multi-day histories, 3, 12, 16 | Verified local | `simulation.py`; `test_simulation.py` seed/variation tests; generator remains synthetic |
| Dummy payer/recipient loop, 6, 10 | Verified local | `simulator_service.py`, `web/app.js`; wallet/API tests; recorded browser payments |
| 18 batch/online features, 5, 12 | Partial | Shared `features.py`; independent history oracle and boundary tests. Per-feature witnesses in `feature_lineage.py`. Full randomized graph oracle across training datasets remains a gap |
| Probe counter, 8, 12, 13 | Verified local | Same-counterparty settled INR <=10, exclusive one-hour window; `test_probe_window_and_counterparty` |
| Temporal availability, 12, 16 | Verified local | Strict event/availability cutoff, prior-day graph, delayed reports; simulation and wallet tests |
| Directed distance **to** reports, 12 | Partial, legacy convention retained | Existing trained contract propagates outward **from** reports. Explorer says so. Reverse-direction migration requires joint feature/training/calibration validation |
| XGBoost, 5, 18 | Verified local | `LiveModel`; actual-model integration and selected-tree SHAP reconstruction test |
| Capped soft-signal log-odds fusion, 5 | Missing research | No trained device/context scores or validated weights; no arbitrary weights inserted |
| Conformal uncertainty, 5 | Partial | Marginal LAC, disjoint calibration days. Empirical 92.10% current synthetic test coverage; no class-conditional guarantee or drift guarantee |
| Two independent evidence groups, 5, 8 | Verified local | `policy.py` 20-case self-test, policy group tests and independent verifier; certainty is not a group |
| Cost-sensitive action optimization, 5 | Missing research | Current deterministic policy has no validated efficacy/friction estimates |
| One alert/day, 5, 8 | Partial | Consent-gated durable contact inbox deduplicates per payer/world/day. No global optimization across all warning types |
| Three SHAP user reasons, 5, 6 | Partial | Exact contributions shown and linked to feature calculations; payer reasons are labeled policy templates. No unsupported forced three reasons |
| Multilingual chat stage, 7, 10, 15, 18 | Missing research | `claims.py` is a narrow whole-message English grammar with abstention, not a stage model |
| Consented stage bar, 6 | Missing research | No fake stage progress displayed |
| Voice-note anti-spoofing, 7, 15 | Missing research | No AASIST model, training data or evaluated EER |
| Screen/call/typing signals, 8, 12 | Intentionally outside browser demo | No real device data collection; no PIN, contacts or call capture |
| Per-signal consent/on-device processing, 8, 11 | Partial | Separate message/contact consent, revocation and world deletion. Consented synthetic text is processed on local server; no on-device inference claim |
| One-hour hold and review, 3, 8, 13 | Verified local with explicit interpretation | Virtual clock; fresh review and explicit authorization after expiry; no automatic transfer. Resolves conflicting deck bypass/release copy conservatively |
| Trusted contact, 3, 6, 13 | Verified local simulation | Independent scoped contact capability, minimal durable inbox, acknowledgment, consent/revocation tests; no external messages |
| Analyst > INR 100,000, 8, 13 | Verified local simulation | Independent capability, exact-review approval, strict amount boundary, payer cannot approve. Bearer capability is not bank identity |
| FRI/MuleHunter/NCRP, 4, 9, 11 | Partial mocks | `provider_evidence.py`; available/delayed/error/unavailable envelopes; analyst-only synthetic NCRP reference. No real providers or invented clean verdict |
| Evidence timeline and replay, 8, 11, 13 | Verified local | Immutable review rows, correlated events, artifact/version checks, original replay, separate-world counterfactuals and verification bundle |
| Signed evidence/model artifacts, 11, 13 | Missing security milestone | SHA256 digests/manifest are consistency checks, not signatures or administrator-resistant storage |
| GNN challenger, 11, 15, 18 | Partial research | Legacy separate experiment, full-history graph; not in wallet or fair same-target temporal comparison |
| Scam DNA library, 11, 13 | Missing research | No trained pattern library or live stage matcher |
| FedAvg + DP + secure aggregation, 8, 13 | Missing research | Legacy margin averaging experiment is not private federated training |
| Confirmed-outcome retraining, 8, 13 | Missing research | Demo has no reliable bank outcome source; user feedback does not retrain models |
| Drift checks/fallback, 8, 13 | Partial | `model_health.py` reports artifact gates; runtime blocks authorization on unavailable model. No scheduled production drift monitor or bank-rules fallback |
| Fairness <=3-point gap, 7, 8 | Not established | No validated demographic cohorts; promotion guard remains false |
| Later days/3 seeds/unseen type, 7, 16 | Partial measured | `evaluate_heldout.py`: type removed before features, tuning/calibration split, report suppression. Smoke: four measured low-support runs, five inconclusive runs; cannot substantiate generalization |
| Baseline comparison, 7, 17 | Partial measured | Same-input amount rule vs policy, denominators and intervals. Gross screened value is not money saved; no intervention efficacy trial |
| Adversarial robustness, 7 | Partial | Amount perturbation, stale evidence/report scenarios and probe tests. No measured multilingual/voice robustness; legacy assumed text evasion constant is not evidence |
| p95 <=150ms total, 7, 11 | Not established | Review-processing timing and request header timing exist. No bank network/load/user-visible p95 claim |
| SDK, shadow pilot/fast path, 9 | Future deployment | Local API only; no bank integration or unvalidated bypass path |
| AWS Kinesis/DynamoDB/Neptune, 9 | Intentionally outside local scope | No measured need; local modular service and durable SQLite events |
| Encryption/HSM/dual-person evidence access, 13 | Missing security milestone | Local origin/session protections, scoped capabilities and access audit implemented; no production banking certification |
| Clean UPI-style UI | Verified local, QA scope documented | Concise payer flow; technical explanations live in explorer; roles/operations use separate console |

## Release decision

Suitable for a clearly labeled local synthetic demo. **Not eligible for bank
deployment:** current recall gate fails; unseen-type samples are weak; fairness,
privacy training, real integrations and production security are not established.
Run `python scripts/model_health.py --require-promotable` to see that promotion
is deliberately refused. Passing software tests does not override model gates.
