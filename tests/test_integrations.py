"""Ecosystem mocks are deterministic and honour the known-account table."""

from __future__ import annotations

from integrations import KNOWN_ACCOUNTS, check_fri, check_mulehunter, file_1930_report


def test_fri_is_deterministic_and_banded():
    a, b = check_fri("9876543210"), check_fri("9876543210")
    assert a == b
    assert 0 <= a["fri_score"] <= 100
    expected = "HIGH" if a["fri_score"] >= 70 else "MEDIUM" if a["fri_score"] >= 35 else "LOW"
    assert a["risk_band"] == expected


def test_mulehunter_known_accounts_and_fallback():
    for acct, status in KNOWN_ACCOUNTS.items():
        assert check_mulehunter(acct) == status
        assert check_mulehunter(int(acct)) == status  # ids may arrive as ints
    assert check_mulehunter("9999") in {"clean", "suspicious", "mule"}
    assert check_mulehunter("9999") == check_mulehunter("9999")


def test_1930_ref_id_is_stable_per_txn():
    r1, r2 = file_1930_report(100002, 196538.18), file_1930_report(100002, 196538.18)
    assert r1["ref_id"] == r2["ref_id"]
    assert r1["ref_id"].startswith("NCRP-") and r1["status"] == "filed"
