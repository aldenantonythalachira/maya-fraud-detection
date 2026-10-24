# Feature contract

Version: `batch-parity-27-report-outward-v2`. Witness schema: `witness-v1`.
Source of numeric truth: `src/features.py`, shared by `online_features.py`.
The witness builder explains the source inputs; it does not replace inference.

All history uses event time **and** availability time strictly before candidate
time T. Same-second candidate/history events are excluded. Training transactions
are assumed available at their recorded time; report availability is explicitly
delayed. No attempted or cancelled live transfer becomes settled history.

| Feature | Endpoint calculation | Missing and combined behavior |
|---|---|---|
| n_t | Number of distinct counterparties first seen in (T-7d,T) | Zero without qualifying history; max across user endpoints, excluding business endpoints when only one endpoint is a business |
| e_t | Candidate amount / largest first-counterparty amount in (T-14d,T) | Missing without denominator; user-endpoint max as for n_t |
| g_t | Any first-contact incoming credit in (T-7d,T) | Zero otherwise; OR across endpoints |
| z_t | log(candidate rupees) - median(log(all prior endpoint amounts)) | Missing without history; endpoint with largest absolute value, payer on tie |
| pi_t | Settled amounts <= INR 10 between the same pair, either direction, in (T-1h,T) | Zero without probes; max across endpoints |
| d_R | Directed outward reachability FROM reported accounts, 0/1/2 hops, cap 3; report and edge available before current UTC day | No known path ->3; min across endpoints. Cap 3 means no path within supported radius, not proof of safety |

| v_t | Same-direction pair payment count in (T-24h,T) | Zero without events; endpoint max |
| zc_t | log(candidate plus pair24 total) minus median all-prior log amount | Missing without history; largest absolute endpoint value |
| ptr_t | Endpoint outflow / inflow in (T-24h,T) | Missing without inflow; max ignoring missing |

Per-side `_snd` and `_rcv` columns remain in the 27-column model input.
Business exceptions apply only to combined n_t/e_t, preserving training semantics.
Endpoint histories include both directions. The deck's phrasing "new payees"
and "distance to reports" is narrower/different; do not equate them with this
trained contract. Missing JSON values become NaN only at the model boundary.

Each witness exposes exact feature value, endpoint/dependencies, window, cutoff,
calculation terms, contributing event IDs and report/graph path IDs. First-payee
features retain denominator events; median uses all eligible prior endpoint
amounts; graph witnesses show one shortest qualifying path. Combined witnesses
list endpoint dependencies and aggregation. Original eligible evidence includes
timestamps and provenance. An edge or a model contribution is not proof of fraud.

Tests cover five randomized histories against an independent brute-force oracle,
same-time/future events, missing history, probe windows/counterparties and directed
previous-day graph cases. Detailed witness tests verify event existence/cutoffs.
This is not exhaustive randomized graph equivalence over a bank dataset.

## Migration rule

Changing graph direction, endpoint aggregation, settlement eligibility, missing
values or time boundaries requires a new feature version, regenerated training
data, retraining, disjoint recalibration, model manifest, later-time evaluation,
batch/online parity evidence and explicit compatibility rules. Do not change
only the browser or live feature builder. Old reviews retain their recorded
contract; version mismatch rejects recomputation and authorization.
