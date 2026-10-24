# Maya — Model Metrics Report

Generated from `models/model_meta.json` and `models/conformal.json`.

## Real XGBoost metrics

| Metric | Value |
|---|---|
| AUROC (test) | 0.9983 |
| AUPRC (test) | 0.9130 |
| Recall @ 1% FPR | 0.9689 |
| Conformal q̂ (qhat) | 0.000246 |
| Alpha | 0.10 |
| Calibration Rows | 726,915 |

## Coverage

The conformal predictor provides a **90% marginal coverage guarantee** (alpha = 0.10).
On the held-out test split it achieves observed coverage ≈ 0.99999 (target ≥ 0.90), with
prediction sets limited to `{fine}`, `{scam}`, or `{fine, scam}` (never empty).

Note: at ~0.09% scam prevalence, marginal coverage is easy to satisfy — `qhat` is tiny
(≈0.000246), so confident `{scam}` singletons are rare and most scam hits land in the
ambiguous `{fine, scam}` set (then resolved by the Two-Signal Rule). Use Mondrian /
class-conditional calibration if a scam-specific coverage guarantee is required.

## Benchmarking Methodology

- Data: synthetic UPI journeys (3,054,055 transactions, ~0.09% scam).
- Temporal split by contiguous day blocks (60 / 20 / 20):
  - **Train**: days 1–72
  - **Validation**: days 73–96
  - **Test**: days 97–120
- Model: `XGBClassifier(tree_method="hist")`, `scale_pos_weight = neg/pos ≈ 987`, early
  stopping on validation AUPRC.
- Thresholds chosen on **validation**, reported on **test** (recall @ 1% FPR).

## Known Gaps

- **Synthetic vs. real world**: these metrics are measured on synthetic data and may not
  hold on real-world traffic. This is a research prototype, not production-validated.
- **Feature coverage**: the 18 features are journey/money-flow only — no text or imagery
  signals (see `docs/FAILURE_REGISTER.md` for F01 and F09).
- **Data quirks**: `g_t` is near-constant (~0.997) on the synthetic random-friend graph,
  and the combined `n_t`/`e_t` exclude business endpoints, which may bias the feature
  distribution.
- **Imbalance**: with ~0.09% positives, all metrics are highly sensitive to threshold
  choice.
