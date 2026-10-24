# Maya Bank API — Enterprise Integration Guide

Maya is a UPI fraud decision engine exposed as a FastAPI service. A bank's
**remitter system** calls Maya in the 150 ms hot path — *before* the UPI
transaction is routed to NPCI — and acts on the returned action.

## Overview

```
Remitter (bank) ──POST /api/score-trace──▶ Maya Bank API ──▶ {action: release|nudge|hold}
      │                                                                  
      │ action == "hold"   → block, stop before NPCI
      │ action == "release"→ forward to NPCI for settlement
```

## API Key Flow

- Send the header `X-API-Key: sk_live_maya_enterprise` on every call to
  `/api/score` and `/api/score-trace`.
- A missing or wrong key returns `401 Unauthorized`.
- `/health` and the read-only `/api/metrics` do **not** require a key (for
  uptime probes and dashboards).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | liveness: `{status, model_version, uptime}` |
| POST | `/api/score` | key | 4-field decision (`action/reasons/auto_release_minutes/requires_analyst`) |
| POST | `/api/score-trace` | key | full Judge View trace + `decision_signature` audit hash |
| GET | `/api/metrics` | none | model metrics (AUROC/AUPRC/qhat/alpha/datasetSize + GNN/FedAvg/red-team) |

## Request body (`/api/score-trace`)

```json
{
  "amount": 300000.0,
  "d_R": 1,
  "z_t": 3.0,
  "e_t": 1.5,
  "g_t": 1.0,
  "pi_t": 0.0,
  "is_screen_shared": false,
  "chat_stage": "none",
  "intent_claim": "none",
  "payment_direction": "outgoing"
}
```

## Response (`final_decision`)

```json
{ "action": "hold", "auto_release_minutes": 60, "requires_analyst": true }
```

## 150 ms Latency SLA

- The hot path is `XGBoost.predict_proba` + conformal + SHAP top-3 (log-odds) —
  single-row inference, well under the 150 ms budget on CPU.
- Load the model, conformal `qhat`, and the SHAP `TreeExplainer` **once at
  startup** (they are reused across requests) — do not reload per transaction.
- Keep `/api/score` (not the trace) as the strict hot-path call if you want the
  absolute minimum payload; `/api/score-trace` returns the full audit trail.

## Worked example (HDFC remitter)

See `scripts/bank_simulator.py` — it POSTs a transaction to
`http://127.0.0.1:8000/api/score-trace` with the `X-API-Key` header and prints:

- `❌ … HOLD. Transaction blocked. Routing stopped before NPCI.`
- `✅ … RELEASE. Forwarding to NPCI for settlement.`
