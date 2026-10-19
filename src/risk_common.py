"""Shared configuration for the maya Phase 3 risk stack.

Single source of truth for the model feature columns and the plain-English
reason strings used by src/reasons.py. Imported by train_xgb, conformal, reasons.
"""

from __future__ import annotations

import pandas as pd

FEATURE_COLUMNS = [
    "n_t", "e_t", "g_t", "z_t", "pi_t", "d_R",
    "n_t_snd", "n_t_rcv",
    "e_t_snd", "e_t_rcv",
    "g_t_snd", "g_t_rcv",
    "z_t_snd", "z_t_rcv",
    "pi_t_snd", "pi_t_rcv",
    "d_R_snd", "d_R_rcv",
]

TARGET = "is_scam"
SPLITS = ("train", "val", "test")

_BASE_REASONS = {
    "n_t": "Many new payees in the last 7 days",
    "e_t": "Amount is unusually high for a new payee",
    "g_t": "Received a credit from an unknown sender recently",
    "z_t": "Amount is unusually large vs the account's history",
    "pi_t": "Repeated tiny probe payments to the same payee within an hour",
    "d_R": "Within two payment hops of a reported fraudulent account",
}

ENGLISH_REASONS = {}
for _base, _text in _BASE_REASONS.items():
    ENGLISH_REASONS[_base] = _text
    ENGLISH_REASONS[f"{_base}_snd"] = "Payer side: " + _text
    ENGLISH_REASONS[f"{_base}_rcv"] = "Payee side: " + _text


def english_reason(feature: str) -> str:
    return ENGLISH_REASONS.get(feature, feature)


def load_features(path: str, columns=None) -> pd.DataFrame:
    cols = ["txn_id", "split", TARGET] + list(columns or FEATURE_COLUMNS)
    df = pd.read_csv(path, usecols=cols)
    for c in FEATURE_COLUMNS:
        if c in df.columns:
            df[c] = df[c].astype("float32")
    return df
