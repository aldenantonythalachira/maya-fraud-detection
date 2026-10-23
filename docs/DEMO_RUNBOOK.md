# MAYA local demo runbook

## Start

Use PowerShell from the repository root:

```powershell
Set-Location 'C:\Users\ashrith\Downloads\Projects\raksham\maya-fraud-detection'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe run_demo.py --bootstrap
```

Once installed, only the final command is needed. `--bootstrap` builds missing
model/calibration files; it preserves existing files. To rebuild the changed
training/calibration contract deliberately, back up models then run
`python scripts/bootstrap_demo.py`. The new default database is
`data/simulator-v2.sqlite`; previous v1 data is preserved. Use `--port 8002` if
8000 is occupied, and `--database data/simulator-my-demo.sqlite` for isolation.

Open the printed loopback wallet URL. Keep the terminal open. It prints a fresh
controller key for `/console`; keep that key out of payer screens and recordings.
No real payments or PINs are used. Missing/invalid models leave the wallet in a
blocked degraded state; bootstrap and restart. `--demo-docs` explicitly enables
the otherwise-disabled API documentation. Ctrl+C stops the server.

## Five-minute demonstration

1. Enter a recipient and arbitrary amount, including paise. Review the actual
   outcome, confirm a warning if requested, then **Confirm demo payment**. Do not
   promise a benign example will release without warning. Show the receipt.
2. Open **View decision**: current input, evidence cutoff, signal groups, feature
   witnesses, exact tree contributions, actual graph and saved versions. Click a
   contribution to expand its feature's source events. Download a verification bundle.
3. In the explorer choose investment history and seed 42, visibly a saved
   regression seed. Try INR 125,000 to R K Traders. The recorded current artifact
   run holds, but there is no preset outcome override. Show what actually happens.
4. Enable trusted-contact sharing on wallet home before creating the hold. In a
   separate `/console`, authenticate as controller with the terminal key. Issue
   a contact link and open its minimal inbox. Acknowledgment is not authorization.
5. Issue an analyst link. The payer has no analyst approval control. Advance
   virtual time one hour in the controller console, obtain a fresh payer review,
   refresh the analyst case, approve that exact review and explicitly confirm as
   payer. Approval for a previous review is rejected; expiry never sends money.
6. Open **Recipient view** from the receipt to see only that recipient's matching
   incoming transfers. Reload works until the 30-minute link expires. Payer can
   revoke all recipient links. No observer can execute or view other recipients.
7. For counterfactuals, paste the original review ID in the controller console
   and choose **Evaluate delayed reports separately**. This forks a new world
   from the saved eligible evidence, leaving the original world/review/hold
   unchanged. Open the separate wallet in the original payer browser session.
8. Edit a pending payment and review again; **Challenge a superseded review**
   exercises server rejection. Recompute/download never rewrites the original.
9. Set a synthetic provider delayed/unavailable/error; obtain a fresh review and
   inspect the envelope. Unknown never becomes a clean verdict. Synthetic NCRP
   filing needs independent analyst access and available mock provider state.
10. Reload after settlement, or stop/restart using the same database, and show
    the same receipt/transfer ID. Create a new random seed to demonstrate variation.

The virtual clock is deliberately paused. Role access expiry uses real time;
virtual advance cannot extend credentials. Holds do not reserve funds. Insufficient
funds at settlement rejects safely. A new review after analyst approval needs a
new approval even if amount/recipient are unchanged.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/policy.py --self-test
.\.venv\Scripts\python.exe scripts/evaluate_demo.py
.\.venv\Scripts\python.exe scripts/evaluate_heldout.py
.\.venv\Scripts\python.exe scripts/model_health.py
.\.venv\Scripts\python.exe scripts/verify_bundle.py 'C:\path\downloaded-bundle.json' --recompute
```

`evaluate_demo.py` is behavioral replay, not accuracy. `evaluate_heldout.py` trains
separate benchmark models and compares decisions on the same later-day test
inputs. It never overwrites the live model. Reports live under ignored `data/`;
benchmark scratch files under ignored `tmp/`. Small smoke samples may be
inconclusive. Gross screened amount is not fraud money saved.

Windows tests use local sockets in FastAPI TestClient; restricted sandboxes may
block event-loop creation. Run those tests in an ordinary authorized PowerShell
environment. This is not a reason to disable the API tests.

## Reset and recovery

Payer **Delete this wallet** purges its synthetic records after confirmation.
It does not delete other worlds. Keep backups if you need previous evidence.
See VERSION_RECOVERY.md for safe source restore and MODEL_LIFECYCLE.md for
artifact/database rollback. Never run older code on a newer schema blindly.

See DECK_CHECKLIST.md for scope, ARCHITECTURE.md for data/logic flow,
THREAT_MODEL.md for demo access/retention, and VALIDATION.md for measurements.
