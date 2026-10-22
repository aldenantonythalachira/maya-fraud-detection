"""Exact batch semantics on a small live world's available event slice.

The batch graph propagates OUTWARD from reported accounts, using the previous
UTC-day snapshot. Preserve this legacy convention for existing trained weights;
do not advertise it as directed distance *to* a report. A correction needs retraining.
Missing history remains None in JSON, converted to NaN only at model/policy input.
"""
import math

import numpy as np
import pandas as pd

from features import DAY, combine, endpoint_features, reported_proximity
from risk_common import FEATURE_COLUMNS

FEATURE_VERSION = "batch-parity-report-outward-v1"


def snapshot(world, sender, recipient, amount_paise, at):
    eligible = [e for e in world["events"] if e["event_at"] < at and e["available_at"] < at]
    payments = [e for e in eligible if e["kind"] == "payment"]
    rows = [dict(txn_id=i, sender_id=e["sender"], receiver_id=e["receiver"],
                 amount=e["amount_paise"] / 100, ts_int=int(e["event_at"])) for i, e in enumerate(payments)]
    candidate_id = len(rows)
    rows.append(dict(txn_id=candidate_id, sender_id=sender, receiver_id=recipient,
                     amount=amount_paise / 100, ts_int=int(at)))
    tx = pd.DataFrame(rows).sort_values("ts_int", kind="stable").reset_index(drop=True)
    tx["ts"] = pd.to_datetime(tx.ts_int, unit="s")
    origin = int(tx.ts_int.min()) // DAY * DAY
    tx["day"] = (tx.ts_int - origin) // DAY
    tx["split"], tx["is_scam"] = "live", 0
    account_map = {a["id"]: a for a in world["accounts"]}
    # Labels include all accounts; report_day is based on availability as well as event time.
    labels = pd.DataFrame([dict(account_id=a["id"], vpa=a["vpa"], is_reported=0, report_day=float("inf"))
                           for a in world["accounts"]])
    for e in eligible:
        if e["kind"] == "report":
            index = e["account"]
            day = (max(e["event_at"], e["available_at"]) - origin) // DAY
            labels.loc[index, "is_reported"] = 1
            labels.loc[index, "report_day"] = min(labels.loc[index, "report_day"], day)
    # Earliest available settled edge; same-day edges are excluded by batch graph logic.
    edge_times = {}
    for e in payments:
        pair = (e["sender"], e["receiver"])
        edge_times[pair] = min(edge_times.get(pair, float("inf")), max(e["event_at"], e["available_at"]))
    edges = pd.DataFrame([dict(src_vpa=account_map[s]["vpa"], dst_vpa=account_map[r]["vpa"],
                               first_ts=pd.to_datetime(t, unit="s")) for (s, r), t in edge_times.items()],
                         columns=["src_vpa", "dst_vpa", "first_ts"])
    ds, dr = reported_proximity(tx, edges, labels, len(labels), int(tx.day.max()) + 1, origin)
    business = np.array([a["business"] for a in world["accounts"]], dtype=bool)
    features = combine(endpoint_features(tx), tx, ds, dr, business)
    row = features[features.txn_id == candidate_id].iloc[0]
    values = {k: None if pd.isna(row[k]) else float(row[k]) for k in FEATURE_COLUMNS}
    return dict(values=values, version=FEATURE_VERSION, evidence=eligible,
                candidate_time=at, graph_cutoff=int(at) // DAY * DAY,
                graph_convention="directed outward reachability from reports; previous UTC day",
                lineage=dict(history_event_ids=[e["id"] for e in payments],
                             report_event_ids=[e["id"] for e in eligible if e["kind"] == "report"],
                             windows=dict(n_t="first counterparties in (t-7d,t)",
                                          e_t="amount / max first-counterparty payment in (t-14d,t)",
                                          g_t="first-contact incoming credit in (t-7d,t)",
                                          z_t="log amount - median log all prior endpoint amounts",
                                          pi_t="same-counterparty settled amounts <= INR 10 in (t-1h,t)",
                                          d_R="legacy report-outward directed reachability, capped at 3")))


def numeric(values):
    return {k: float("nan") if v is None else v for k, v in values.items()}
