# Maya — Pilot Blueprint (Shadow Mode)

A one-page plan for a bank to deploy Maya in shadow mode and graduate to full
intervention without ever blocking a legitimate payment by surprise.

## Phases

1. **Baseline (Shadow Mode)** — Maya runs in parallel, logs every decision, and takes
   NO action on real payments. Establish the false-positive baseline.
2. **Opt-in Pilot** — a consenting cohort gets live interventions (nudge/hold), with the
   "Request Review" recourse flow enabled. Measure intervention accuracy.
3. **Default On** — interventions roll out to all users. Analyst review is gated on
   `requires_analyst` (hold AND amount > ₹1,00,000). Auto-release keeps holds ≤ 60 min.
4. **Shared FedAvg** — participating banks average model margins (no raw data shared,
   see `src/federated_sim.py`) to lift recall across banks.

## Key Metrics to Track

- Recall @ 1% FPR (target ≥ 0.90 at ~0.09% prevalence).
- False-positive / intervention rate (nudge + hold as a fraction of total volume).
- Auto-release rate (holds released without analyst action).
- Analyst-review volume (held AND > ₹1,00,000).
- End-to-end latency (budget: 150 ms hot path).

## Rollback Plan

- **Kill switch** back to Baseline (log-only) via a feature flag — no payment is ever
  blocked in shadow mode, so rollback is instantaneous.
- Model versions are pinned (`models/model_meta.json`), and every decision carries a
  SHA-256 `decision_signature` for audit/replay.
- If recall or the false-positive rate drifts past thresholds, revert to the previous
  model version and re-enter Opt-in Pilot.
