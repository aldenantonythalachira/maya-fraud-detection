# Maya risk-scoring API (v1)

Maya runs as a service that a **bank or UPI app calls before releasing a
payment**. A separate phone app cannot do this: apps are sandboxed, and only the
payer's UPI app / bank can see a payment in flight and hold it. This API is a
**local simulator** on synthetic data — no bank connection, no real money, and
the MuleHunter.AI / DoT FRI / NCRP feeds are mocks.

Code: `src/api.py` (FastAPI). Interactive docs: `http://127.0.0.1:8000/docs`.

## Run it

```powershell
# once: core + test dependencies (includes fastapi, uvicorn, httpx)
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# the API needs trained models/: build them with the README pipeline commands
.\.venv\Scripts\python.exe -m uvicorn api:app --app-dir src            # http://127.0.0.1:8000
# second terminal: the demo bank client
.\.venv\Scripts\python.exe scripts\demo_bank_client.py
```

Environment overrides: `MAYA_MODEL` (default `models/xgb_model.json`),
`MAYA_CONFORMAL` (default `models/conformal.json`), `MAYA_REVIEW_DB` (default
`:memory:`; a file path keeps reviews across restarts).

## 1. Stateless scoring — `POST /v1/score`

The bank's hot path. The caller's own feature pipeline computes the features;
Maya scores them, computes the conformal set **on the server**, and applies the
Two-Signal Rule. Callers can never pass a decision or set in (extra fields are
rejected).

**Feature contract `maya-features-v1`:** exactly the 27 columns in
`risk_common.FEATURE_COLUMNS` — `n_t e_t g_t z_t pi_t d_R v_t zc_t ptr_t`, each
combined and as `_snd` (payer side) / `_rcv` (payee side). Definitions are in
`src/features.py`; every value must use only data from before the payment.
`null` means "not available" (the model treats it as missing). Missing or
unknown keys → 422.

Request:

```json
{
  "features": {"n_t": 65.0, "e_t": 6.3706, "...": "all 27 columns"},
  "amount_inr": 196538.18,
  "soft_signals": {"is_screen_shared": false, "is_voice_active": false, "chat_stage": "none"},
  "mulehunter_status": "mule",
  "request_id": "bank-txn-0001"
}
```

`soft_signals` and `mulehunter_status` are optional. `chat_stage` is one of
`none | escalated | payment_demand`; `mulehunter_status` one of
`clean | suspicious | mule`.

Response:

```json
{
  "action": "hold",
  "reasons": ["Payer side: Total sent to this payee in 24 hours is unusually large",
              "Within two payment hops of a reported fraudulent account",
              "Payee side: Account forwards most of the money it receives within a day"],
  "auto_release_minutes": 60,
  "requires_analyst": true,
  "p_scam": 0.9994,
  "conformal_set": "{scam}",
  "fired_signals": {"hard": {"z_t": true, "zc_t": true, "d_R": true, "mulehunter": true}, "soft": {}},
  "model_version": "de9181e3...",
  "calibration_version": "b346a802...",
  "policy_version": "payment-review-v2",
  "request_id": "bank-txn-0001",
  "latency_ms": 6.1
}
```

- The first four fields are exactly `policy.decide()`'s contract.
- `action`: `release` (send), `nudge` (warn; the payer must confirm), `hold`
  (stop for `auto_release_minutes`; an analyst reviews when `requires_analyst`).
- **Universal safeguard:** a hold always needs two independent groups
  (payment history AND receiving account, or one of them AND a soft signal).
  A confident `{scam}` alone is a nudge.
- `reasons` are SHAP-ranked risk factors whose values are actually in the risky
  range, so every sentence is true for this payment. They are returned for any
  action — a released payment can still list factors that were outweighed.
- Version hashes let the bank record exactly which model / calibration / policy
  produced the decision.

## 2. Stateful payment review

Thin wrappers over `payment_review.PaymentService` (immutable reviews, evidence
replay, invalidation when the payment changes). Every call needs the
`X-Payer-Session` header — a **simulated** payer binding, not authentication.

| Method & path | Body | Does |
|---|---|---|
| `POST /v1/payments` | `recipient`, `amount_paise`, `direction` | create a pending payment (201) |
| `GET /v1/payments/{id}` | — | current state |
| `PATCH /v1/payments/{id}` | `recipient`, `amount_paise` | change it (new revision; old reviews go stale) |
| `POST /v1/payments/{id}/reviews` | `evidence[]`, `text`, `consent`, `parent` | review it (201) |
| `GET /v1/reviews/{id}?recompute=true` | — | replay; `recompute` re-runs and must match |
| `POST /v1/payments/{id}/execute` | `review_id`, `confirmed` | send, if the review still allows it |
| `POST /v1/payments/{id}/cancel` | — | cancel |
| `POST /v1/payments/{id}/analyst-approval` | `review_id` | simulated analyst approval |

Evidence items: `id`, `kind` (`payment` needs `recipient`, `direction`,
`amount_paise`; `report` needs `account`; `edge` needs `source`, `target`),
`event_at`, `available_at` (epoch seconds). See `src/demo_scenarios.py`.

Errors: unknown id → 404, wrong session → 403, bad input or missing header →
422, stale / expired / held / terminal / unconfirmed nudge → 409, model not
built → 503.

## 3. Meta

- `GET /v1/health` → `{"status": "ok" | "not_ready", ...}`
- `GET /v1/model` → versions, feature contract, policy thresholds, conformal
  cutoffs, test metrics, the 150 ms latency budget, and `attacks` (the
  `attack_sim.py --json-out models/attack_results.json` results, or `null`).
- `GET /v1/demo/scenarios` → the four demo scenarios: story text in English and
  Hindi (`label`, `story`, `payee`, `note`, optional `journey` / `money_path`),
  the 27 features, the payer's `soft_signals`, the mock `mulehunter_status` and
  the expected outcome — ready to post to `/v1/score`.

`/v1/score` options for the frontends:
- `reason_features` (always returned): the base feature behind each reason, in
  order, so a client can show its own localised wording.
- `"explain": true` in the request adds `explanation.contributions`: every
  feature's value, Tree-SHAP contribution (log-odds) and whether its value is in
  the risky range. Off by default to keep the hot path fast.

## 4. Frontends

Served by the same app (plain HTML / CSS / ES modules, no build step):

| URL | What | For |
|---|---|---|
| `/app/` | Everyday-user payment app: pay → Maya's check → hold / nudge / receipt, English / हिंदी | phones (360 px up) |
| `/demo/` | Judges' demo: the live user app beside the decision board (three signal groups, the two-signal gate, the decision), money path, and tabs for Evidence, Robustness, Model card and Try it | projector (1920×1080), laptops |
| `/` | redirects to `/demo/` | |

`/app/?s=police&lang=hi` opens a scenario in a language; `/app/?embed=1` is the
mode the demo uses (it then takes `postMessage` commands from the demo page).
Fonts (Anek Latin + Devanagari, OFL) are self-hosted under `/static/fonts/`, so
the demo works offline. The Hindi copy is a draft for the demo: have a native
speaker check it before public use.

## What a real integration would still need

This API shows the shape of the integration; a production deployment also needs:

1. **A bank-side feature pipeline** computing the 27 features from the bank's
   own transaction history and account graph in real time (`src/features.py` is
   the batch reference implementation and its brute-force checker).
2. **Real authentication and transport**: mTLS or signed requests between the
   bank and Maya, not a session header.
3. **Real feeds** for MuleHunter.AI, DoT FRI and NCRP reporting, which require
   RBI / DoT / bank agreements.
4. **Soft signals from the payer's app** (screen sharing, active call, chat
   stage), which only the UPI app itself can observe.
5. **RBI / data-protection compliance**: data residency, retention, audit, and
   customer notice for holds.
6. **Validation on real fraud data.** On this synthetic data the model scores
   near-perfectly (see `AGENTS.md`), which says nothing about real accuracy.

Local demo latency is ~6 ms server-side and ~30 ms round-trip p95, well within
the 150 ms budget; a real deployment adds network and feature-lookup time.
