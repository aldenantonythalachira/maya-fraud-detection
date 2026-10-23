# MAYA

A local synthetic payment wallet with an inspectable fraud-decision pipeline.
Generate a history, enter a free-form dummy payment, inspect its actual model and
policy result, and follow authorization through a balanced debit/credit ledger.

## Run (Python 3.12)

From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.lock.txt
.\.venv\Scripts\python.exe run_demo.py --bootstrap
```

Open the printed loopback URL, normally http://127.0.0.1:8000. Subsequent runs
need only the last command. Use `--port 8002` if 8000 is occupied. Keep the
terminal open; Ctrl+C stops the server. Restart an older running server to load
backend changes. No real bank, payment rail, money or UPI PIN is involved.

`--bootstrap` builds missing artifacts without replacing existing ones. To
deliberately rebuild the updated tuning/calibration contract, back up existing
artifacts and run `python scripts/bootstrap_demo.py`. Generated data, model JSON
and databases stay ignored. Default database: `data/simulator-v2.sqlite`; stage-03
v1 data is preserved. Never silently reuse an incompatible runtime database.

## Explore

- **Wallet:** recipient, amount, review, explicit dummy authorization, receipt and history.
- **View decision:** correlated execution events, exact feature witnesses, actual model
  contributions, policy groups, synthetic providers, replay and verification bundle.
- **Console:** independent contact/analyst views and restricted simulator controls.
  A controller key is printed to the server terminal; do not share it with payers.
- **Recipient view:** scoped, expiring and revocable access to one recipient's credits.

Every review calls the model. Presets generate inputs, not outcomes. SHAP uses
the same selected trees as scoring and must reconstruct its score. A hold requires
independent evidence groups. Timer expiry never transfers money automatically;
fresh review, exact-review analyst approval where required, and payer confirmation
are checked by the backend. Retries/restarts return one durable settlement.

## Verification and evidence

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/policy.py --self-test
.\.venv\Scripts\python.exe scripts/evaluate_demo.py
.\.venv\Scripts\python.exe scripts/evaluate_heldout.py
.\.venv\Scripts\python.exe scripts/model_health.py
```

See [validation](docs/VALIDATION.md), [recorded evaluation](docs/EVALUATION_RESULTS.md)
and the [deck checklist](docs/DECK_CHECKLIST.md). Software tests demonstrate local
behavior, not detection accuracy. Current rebuilt smoke artifacts show 92.10%
marginal test coverage but only 35.48% recall at the tuning-selected operating
threshold. The recall gate fails. Unseen-type smoke samples are weak or
inconclusive. Fairness and bank-load performance are not established.

Voice, a trained multilingual stage model, private federated training, real bank
providers, signed evidence and production identity/security remain separate
milestones. The existing graph convention propagates outward from reported
accounts; it is not the deck's directed distance to reports. These limits are
explicit in the explorer, contracts and checklist. The legacy Streamlit fixture
demo remains at `streamlit run ui/app.py` and does not establish live wallet behavior.

## Handoff and recovery

Read the [runbook](docs/DEMO_RUNBOOK.md), [architecture](docs/ARCHITECTURE.md),
[feature contract](docs/FEATURE_CONTRACT.md), [threat model](docs/THREAT_MODEL.md)
and [model lifecycle](docs/MODEL_LIFECYCLE.md). Native ES modules/CSS are served by
FastAPI; no Node build or second frontend server is required. On Linux/macOS use
`.venv/bin/python`. Full experimental dependencies remain in `requirements.txt`.

Recovery instructions are in [VERSION_RECOVERY.md](docs/VERSION_RECOVERY.md).
`python scripts/versions.py list` lists checkpoints; restore creates a new branch
and refuses dirty work. Source checkpoints do not restore ignored model/database
files. Keep a complete matching runtime backup. Work stays on feature branches
and draft PRs; no merge or default-branch rewrite is part of this delivery.
