# Recorded synthetic evaluation — 22 October 2026

The complete generated output is `data/evaluation-heldout.json` (ignored runtime artifact).
Command: `python scripts/evaluate_heldout.py`. Default fixed hyperparameters; no live artifact promotion.
Held-out type removed before features from train/tuning/calibration; reports touching removed accounts suppressed.
Only honest rows and unseen-type positives are included in final evaluation. All runs are retained.
Intervals in the generated output are descriptive transaction-level Wilson intervals; transactions within campaigns are correlated.
One or two scam campaigns cannot substantiate deployment/generalization claims.

| Seed | Unseen type | Status | Test scam campaigns | Recall at tuning-selected threshold | False hold rate |
|---|---|---|---|---|---|
| 11 | investment | Measured, very low support | 2 | 10.00% | 0.72% |
| 11 | digital_arrest | Insufficient class support | — | — | — |
| 11 | sextortion | Insufficient class support | — | — | — |
| 29 | investment | Insufficient class support | — | — | — |
| 29 | digital_arrest | Insufficient class support | — | — | — |
| 29 | sextortion | Measured, very low support | 1 | 40.00% | 1.84% |
| 47 | investment | Insufficient class support | — | — | — |
| 47 | digital_arrest | Measured, very low support | 1 | 42.86% | 1.49% |
| 47 | sextortion | Measured, very low support | 1 | 0.00% | 1.49% |

The amount-rule baseline and MAYA are compared on identical rows. Policy actions are evaluated
offline; gross screened transfer value may include layering and is explicitly not realized savings.
Fairness, voice/text robustness, intervention efficacy and bank-load latency are not established.
No assumption-based text evasion number is used as a benchmark result.

Current live seed-42 smoke model: test PR-AUC 0.4893; recall 35.48% at the tuning-selected
1%-FPR operating threshold (observed test FPR about 0.04%). Separate-day calibration gives
92.10% marginal test coverage on 5,252 rows, including only 31 scam rows. This misses the
deck recall target. Coverage alone is not sufficient for model promotion.
