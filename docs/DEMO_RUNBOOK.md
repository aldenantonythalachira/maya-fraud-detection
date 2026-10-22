# Interactive MAYA wallet

## Start from the repository directory

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe scripts/bootstrap_demo.py
.\.venv\Scripts\python.exe run_demo.py
```

Open http://127.0.0.1:8000. Use `--port 8001` if 8000 is busy. No real bank,
payment provider, API key or UPI PIN is used. Keep this server on loopback.
Default database: data/simulator-v1.sqlite. Override `--database` for an isolated
demo or code-version change. Bootstrap regenerates model/data files; skip it
when keeping an existing model for exact review replay.

The browser uses native ES modules and CSS, served by the same Python API.
This intentionally simplifies the proposed React/Vite stack: one server, no
Node build or second dev port, and no duplicate decision logic. FastAPI owns
validation and state. Legacy Streamlit demos remain available unchanged.

## Demonstrate the flow

1. Pay Amma a custom amount including paise. Review, explicitly confirm any
   warning, then press **Authorize dummy payment**. Compare the receipt's debit,
   credit and balances. Repeated requests/reloads do not duplicate a transfer.
2. **How it works** opens world controls and the actual event trace. Choose
   investment, seed 42, and generate a world. Pay R K Traders INR 20,000. With
   current smoke artifacts this holds, but generation and inference always run;
   the preset does not prescribe the action.
3. Inspect feature windows, endpoint columns, tree contributions, graph edges and
   snapshot versions. SHAP explains the model; payer text is separately labeled
   evidence templates. Unsupported context abstains. No trained stage model is claimed.
4. Edit amount, review again, then **Try old review after an edit**. The service
   rejects the old revision. **Recompute original snapshot** verifies model and
   policy against saved inputs and matching versions.
5. **Delay reports** creates a separate evaluation linked to the original. With
   current seed/artifacts the hold becomes a nudge as recipient evidence disappears.
   The original review and active hold on the original intent remain intact.
6. Open recipient view to see committed incoming transfers. This local observer
   link exposes dummy accounts, balances and transfers; it cannot execute a payment.
   It polls actual state every two seconds; no authorization is needed to receive.
7. Advance the paused virtual clock to test expiry. A hold never auto-sends.
   Above INR 100,000, obtain a fresh review, record simulated analyst approval
   for that revision, then explicitly authorize after the timer. Priya's in-app
   inbox deduplicates held-payment alerts per world/payer/simulated day.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/policy.py --self-test
.\.venv\Scripts\python.exe scripts/evaluate_demo.py
.\.venv\Scripts\python.exe scripts/versions.py list
```

CI rebuilds a small model before tests so actual-model integration is not silently
skipped. The evaluation JSON is a three-seed behavioral audit, not a held-out
accuracy benchmark. Tests cover independent feature-oracle comparison, evidence
timing, settlement conservation, competing connections, restart/retry, API/session
boundaries, replay and safe code restore.

## Interpretation and limits

- Smoke calibration coverage is approximately 85.83%, below the 90% target.
  Everyday payments can be warned on. Preserve those outcomes; never pin a clean
  scenario to release to make the model look better.
- Graph semantics preserve the trained baseline: directed traversal outward from
  reported accounts, with previous-UTC-day edges/reports. Correct distance-to-report
  semantics need new feature versions, retraining and evaluation.
- Generated opening funds and prior settled transfers populate the ledger. Holds
  do not debit or reserve funds. Dummy authorization checks funds and settles in
  one SQLite transaction; there is no delayed external rail.
- Generated histories are not an independent real-world validation dataset.
  FRI/MuleHunter/NCRP connectivity, voice analysis, trained multilingual stage
  inference, production GNN, DP and secure aggregation remain research milestones.
- All feeds in a world share an evidence revision, conservatively invalidating
  reviews even for unrelated new reports. Per-account invalidation can narrow this
  later while preserving relevant evidence checks.
- Sessions and analyst controls model local roles, not production authentication.
  No PIN is requested. Consented synthetic text stays local; unconsented text is
  excluded from requests, snapshots and traces.
- Review hashes/triggers detect accidental changes, not administrator tampering.
  Stop the app before backing up its database and any WAL/SHM files.

See VERSION_RECOVERY.md for source checkpoints versus runtime database/model
recovery. Never force-reset shared main.
